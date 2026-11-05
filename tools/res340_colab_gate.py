"""Read-only host preflight before an owner-approved RES340 Colab allocation."""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import res340_lomo
import train_res338_final_fits as trainer

BALANCE = re.compile(r"Current balance:\s*([0-9]+(?:\.[0-9]+)?)\s*compute units")
RATE = re.compile(r"Usage rate:\s*([0-9]+(?:\.[0-9]+)?)/hr")
ASSIGNMENTS = re.compile(r"Active assignments:\s*(\d+)")
SESSION = re.compile(r"^\[([^]]+)\].*?Hardware:\s*A100\b", re.MULTILINE)


def parse_usage_snapshot(output: str) -> dict[str, float | int]:
    balance = BALANCE.search(output)
    rate = RATE.search(output)
    assignments = ASSIGNMENTS.search(output)
    if not balance or not rate or not assignments:
        raise ValueError("colab usage output did not contain balance, rate, and assignment count")
    values = {
        "compute_unit_balance": float(balance.group(1)),
        "compute_unit_rate_per_hour": float(rate.group(1)),
        "active_assignments": int(assignments.group(1)),
    }
    if any(
        not math.isfinite(float(values[key]))
        for key in ("compute_unit_balance", "compute_unit_rate_per_hour")
    ):
        raise ValueError("Colab usage values must be finite")
    return values


def parse_active_a100_sessions(output: str) -> list[str]:
    return SESSION.findall(output)


def validate_preflight(
    snapshot: dict[str, float | int],
    approval: dict[str, object] | None,
    active_a100_sessions: list[str] | None = None,
) -> dict[str, object]:
    balance = float(snapshot["compute_unit_balance"])
    rate = float(snapshot["compute_unit_rate_per_hour"])
    result: dict[str, object] = {
        **snapshot,
        "required_compute_unit_spend_cap": res340_lomo.PROPOSED_COMPUTE_UNIT_SPEND_CAP,
        "allocation_started": False,
        "fit_execution_authorized": False,
    }
    if approval is None:
        result.update(
            status="OWNER_APPROVAL_REQUIRED", reason="no owner execution authorization provided"
        )
        return result
    plan, protocol, roles = trainer._frozen_split_and_authorities()
    matrix = res340_lomo.build_fit_matrix(plan, protocol, roles)
    amendment_sha = trainer._sha256_file(trainer.RES340_GPU_EXECUTION_AMENDMENT)
    cloud_sha = trainer._sha256_file(trainer.RES340_PRIVATE_CLOUD_AMENDMENT)
    code_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=trainer.REPO, text=True
    ).strip()
    res340_lomo.verify_execution_approval(
        approval,
        amendment_sha256=amendment_sha,
        private_cloud_amendment_sha256=cloud_sha,
        fit_matrix_sha256=res340_lomo.matrix_sha256(matrix),
        cache_manifest_sha256=str(approval.get("cache_manifest_sha256", "")),
        cache_ledger_sha256=str(approval.get("cache_ledger_sha256", "")),
        code_sha=code_sha,
        compute_unit_spend_cap=res340_lomo.PROPOSED_COMPUTE_UNIT_SPEND_CAP,
    )
    if balance < res340_lomo.PROPOSED_COMPUTE_UNIT_SPEND_CAP:
        result.update(
            status="BLOCKED_INSUFFICIENT_COMPUTE_UNITS",
            deficit_compute_units=round(res340_lomo.PROPOSED_COMPUTE_UNIT_SPEND_CAP - balance, 2),
            reason="do not allocate or start a partial campaign",
        )
        return result
    if balance != float(approval["compute_unit_balance_at_start"]):
        result.update(
            status="BLOCKED_BALANCE_SNAPSHOT_CHANGED",
            authorized_start_balance=approval["compute_unit_balance_at_start"],
            reason="refresh the owner authorization with the current read-only balance",
        )
        return result
    other_sessions = [
        session for session in (active_a100_sessions or []) if session != "res340-lomo"
    ]
    if other_sessions:
        result.update(
            status="BLOCKED_ACTIVE_A100_SESSION",
            active_a100_sessions=other_sessions,
            reason="reuse or stop the other GPU session before starting the one-worker campaign",
        )
        return result
    approved_rate = float(approval["a100_compute_unit_rate_per_hour"])
    if rate > 0 and rate != approved_rate:
        result.update(
            status="BLOCKED_A100_RATE_CHANGED",
            approved_a100_rate_per_hour=approved_rate,
            reason="recalculate the fixed CU cap and obtain a new owner approval",
        )
        return result
    result.update(
        status=(
            "OWNER_AUTHORIZED_REUSE_EXISTING_SESSION"
            if "res340-lomo" in (active_a100_sessions or [])
            else "OWNER_AUTHORIZED_PREFLIGHT_ONLY"
        ),
        approved_a100_rate_per_hour=approved_rate,
        a100_rate_confirmation=(
            "active rate matches approval" if rate > 0 else "recheck after A100 allocation"
        ),
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorization", type=Path)
    args = parser.parse_args()
    usage = subprocess.run(
        ["colab", "usage"], check=True, capture_output=True, text=True, timeout=60
    )
    sessions = subprocess.run(
        ["colab", "sessions"], check=True, capture_output=True, text=True, timeout=60
    )
    approval = (
        cast(dict[str, object], json.loads(args.authorization.read_bytes()))
        if args.authorization is not None
        else None
    )
    result = validate_preflight(
        parse_usage_snapshot(usage.stdout),
        approval,
        parse_active_a100_sessions(sessions.stdout),
    )
    print(json.dumps(result, sort_keys=True))
    if str(result["status"]).startswith("BLOCKED_"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
