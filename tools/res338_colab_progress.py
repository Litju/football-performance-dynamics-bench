"""Maintain a private, content-addressed research fit progress index."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import train_res338_final_fits as trainer

STATUSES = {
    "NOT_STARTED",
    "RUNNING",
    "COMPLETED_AND_VERIFIED",
    "FAILED",
    "INTERRUPTED_RETRY_ELIGIBLE",
}
SHA256 = re.compile(r"[0-9a-f]{64}")


def _canonical(value: object) -> bytes:
    return trainer._canonical(value)


def _write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    trainer._fsync_directory(path.parent)


def _write_version(index: dict[str, object], directory: Path) -> tuple[Path, str]:
    payload = _canonical(index)
    digest = hashlib.sha256(payload).hexdigest()
    path = directory / f"progress-index-{digest}.json"
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError("content-addressed progress path already contains different bytes")
    if not path.exists():
        _write_atomic(path, payload)
    _write_atomic(
        directory / "progress-index-latest.json",
        _canonical(
            {"schema_id": "fpdbench.res338.progress-pointer", "sha256": digest, "file": path.name}
        ),
    )
    return path, digest


def initialize(
    directory: Path,
    *,
    reference_sha256: str,
    runtime_sha256: str,
    amendment_sha256: str,
    accelerator: dict[str, object],
    compute_unit_balance: float,
) -> tuple[Path, str]:
    for value in (reference_sha256, runtime_sha256, amendment_sha256):
        if SHA256.fullmatch(value) is None:
            raise ValueError("progress identity must be a lowercase SHA-256")
    if not math.isfinite(compute_unit_balance) or compute_unit_balance <= 0:
        raise ValueError("an existing positive compute-unit balance is required")
    plan, protocol, roles = trainer._frozen_split_and_authorities()
    if set(roles) != {"training", "validation", "evaluation"}:
        raise ValueError("frozen plan no longer contains the original 12/4/4 roles")
    training = roles["training"]
    validation = roles["validation"]
    if len(training) != 12 or len(validation) != 4:
        raise ValueError(
            "progress schedule must be the frozen 12 training and 4 validation matches"
        )
    configs = trainer._fit_order(training, validation)
    fits = []
    for fit in configs:
        config = trainer._per_fit_config(
            cast(trainer.InformationRegime, fit["information_regime"]),
            cast(trainer.TargetRepresentation, fit["target_representation"]),
            int(fit["seed"]),
            training,
            validation,
            str(plan["plan_sha256"]),
            str(protocol["protocol_sha256"]),
            "cuda",
        )
        fits.append(
            {
                "run_id": trainer._fit_run_id(fit),
                "information_regime": fit["information_regime"],
                "target_representation": fit["target_representation"],
                "seed": fit["seed"],
                "configuration_sha256": hashlib.sha256(_canonical(config)).hexdigest(),
                "status": "NOT_STARTED",
                "attempt_count": 0,
                "attempts": [],
            }
        )
    if len(fits) != 18 or len({fit["run_id"] for fit in fits}) != 18:
        raise ValueError("the frozen progress schedule must contain exactly 18 unique fits")
    index: dict[str, object] = {
        "schema_id": "fpdbench.res338.colab-progress",
        "schema_version": "1.0.0",
        "sequence": 0,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "updated_at_utc": datetime.now(UTC).isoformat(),
        "previous_index_sha256": None,
        "required_fit_count": 18,
        "completed_fit_count": 0,
        "parent_research_manifest_sha256": trainer.RESEARCH_MANIFEST_SHA256,
        "plan_sha256": plan["plan_sha256"],
        "protocol_sha256": protocol["protocol_sha256"],
        "research_reference_sha256": reference_sha256,
        "gpu_runtime_sha256": runtime_sha256,
        "gpu_execution_amendment_sha256": amendment_sha256,
        "accelerator": accelerator,
        "compute_unit_balance_at_start": compute_unit_balance,
        "compute_unit_spend_cap": compute_unit_balance,
        "compute_unit_balance_latest": compute_unit_balance,
        "compute_unit_spent": 0.0,
        "fits": fits,
    }
    return _write_version(index, directory)


def advance(
    current_path: Path,
    directory: Path,
    run_id: str,
    status: str,
    *,
    attempt_number: int,
    checkpoint_path: Path | None = None,
    receipt_path: Path | None = None,
    checkpoint_readback_path: Path | None = None,
    receipt_readback_path: Path | None = None,
    checkpoint_drive_file_id: str | None = None,
    receipt_drive_file_id: str | None = None,
    infrastructure_confirmed: bool = False,
    oom_excluded: bool = False,
    reason: str | None = None,
    compute_unit_balance: float | None = None,
    compute_unit_rate_per_hour: float | None = None,
) -> tuple[Path, str]:
    if status not in STATUSES:
        raise ValueError("unknown progress status")
    current_bytes = current_path.read_bytes()
    old_sha = hashlib.sha256(current_bytes).hexdigest()
    index = cast(dict[str, object], json.loads(current_bytes))
    fits = cast(list[dict[str, object]], index["fits"])
    fit = next((item for item in fits if item["run_id"] == run_id), None)
    if fit is None:
        raise ValueError("run ID is outside the frozen 18-fit schedule")
    old_status, old_attempts = str(fit["status"]), int(fit["attempt_count"])
    allowed = {
        "NOT_STARTED": {"RUNNING"},
        "RUNNING": {
            "COMPLETED_AND_VERIFIED",
            "FAILED",
            "INTERRUPTED_RETRY_ELIGIBLE",
        },
        "INTERRUPTED_RETRY_ELIGIBLE": {"RUNNING"},
        "FAILED": set(),
        "COMPLETED_AND_VERIFIED": set(),
    }
    if status not in allowed[old_status]:
        raise ValueError(f"invalid progress transition {old_status} -> {status}")
    starts_attempt = status == "RUNNING"
    if starts_attempt:
        expected_attempt = old_attempts + 1
    else:
        expected_attempt = old_attempts
    if attempt_number != expected_attempt or attempt_number > 2:
        raise ValueError("attempt number exceeds the frozen one-retry allowance")
    checkpoint_sha256: str | None = None
    receipt_sha256: str | None = None
    if status == "COMPLETED_AND_VERIFIED":
        if any(
            path is None
            for path in (
                checkpoint_path,
                receipt_path,
                checkpoint_readback_path,
                receipt_readback_path,
            )
        ):
            raise ValueError("verified completion requires local files and Drive readbacks")
        checkpoint_sha256 = trainer._sha256_file(cast(Path, checkpoint_path))
        receipt_sha256 = trainer._sha256_file(cast(Path, receipt_path))
        if (
            SHA256.fullmatch(checkpoint_sha256) is None
            or SHA256.fullmatch(receipt_sha256) is None
            or trainer._sha256_file(cast(Path, checkpoint_readback_path)) != checkpoint_sha256
            or trainer._sha256_file(cast(Path, receipt_readback_path)) != receipt_sha256
        ):
            raise ValueError("Drive readback SHA-256 differs from the local fit artifact")
        if not checkpoint_drive_file_id or not receipt_drive_file_id:
            raise ValueError("completion requires verified Drive readbacks for both artifacts")
    if status == "INTERRUPTED_RETRY_ELIGIBLE":
        if attempt_number != 1 or not infrastructure_confirmed or not oom_excluded or not reason:
            raise ValueError(
                "retry eligibility requires an infrastructure interruption and OOM exclusion"
            )
    if status == "FAILED" and not reason:
        raise ValueError("failed fit requires its preserved failure reason")
    if starts_attempt:
        if compute_unit_balance is None or compute_unit_rate_per_hour is None:
            raise ValueError("starting a GPU fit requires fresh Colab usage and rate readings")
        reserved_hours = 0.25 if attempt_number == 2 else 1.0
        if compute_unit_balance < compute_unit_rate_per_hour * reserved_hours:
            raise ValueError("remaining compute units do not cover this frozen fit budget")
    if compute_unit_balance is not None:
        start_balance = float(index["compute_unit_balance_at_start"])
        spent = start_balance - compute_unit_balance
        if (
            not math.isfinite(compute_unit_balance)
            or compute_unit_balance < 0
            or compute_unit_balance > start_balance
            or spent > float(index["compute_unit_spend_cap"])
        ):
            raise ValueError(
                "Colab usage exceeds the owner-authorized existing compute-unit balance"
            )
        index["compute_unit_balance_latest"] = compute_unit_balance
        index["compute_unit_spent"] = round(spent, 6)
    if compute_unit_rate_per_hour is not None:
        if not math.isfinite(compute_unit_rate_per_hour) or compute_unit_rate_per_hour < 0:
            raise ValueError("Colab usage rate must be a nonnegative finite number")
        index["compute_unit_rate_per_hour_latest"] = compute_unit_rate_per_hour

    attempts = cast(list[dict[str, object]], fit["attempts"])
    if starts_attempt:
        attempt: dict[str, object] = {
            "attempt_number": attempt_number,
            "status": status,
            "started_at_utc": datetime.now(UTC).isoformat(),
            "reserved_compute_units": (
                compute_unit_rate_per_hour * (0.25 if attempt_number == 2 else 1.0)
            ),
        }
        attempts.append(attempt)
        fit["attempt_count"] = attempt_number
    else:
        if not attempts or int(attempts[-1]["attempt_number"]) != attempt_number:
            raise ValueError("terminal status does not match the active progress attempt")
        attempt = attempts[-1]
        attempt.update(status=status, updated_at_utc=datetime.now(UTC).isoformat())
    for key, value in (
        ("checkpoint_sha256", checkpoint_sha256),
        ("receipt_sha256", receipt_sha256),
        ("checkpoint_drive_file_id", checkpoint_drive_file_id),
        ("receipt_drive_file_id", receipt_drive_file_id),
        ("reason", reason),
        ("infrastructure_confirmed", infrastructure_confirmed),
        ("oom_excluded", oom_excluded),
        (
            "readback_verified",
            status == "COMPLETED_AND_VERIFIED" and checkpoint_readback_path is not None,
        ),
    ):
        if value is not None:
            attempt[key] = value
    fit["status"] = status
    index["sequence"] = int(index["sequence"]) + 1
    index["updated_at_utc"] = datetime.now(UTC).isoformat()
    index["previous_index_sha256"] = old_sha
    index["completed_fit_count"] = sum(item["status"] == "COMPLETED_AND_VERIFIED" for item in fits)
    if int(index["completed_fit_count"]) > 18:
        raise ValueError("progress index exceeds the exact 18-fit schedule")
    return _write_version(index, directory)


def verify(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    index = cast(dict[str, object], json.loads(payload))
    fits = cast(list[dict[str, object]], index["fits"])
    if (
        index.get("schema_id") != "fpdbench.res338.colab-progress"
        or index.get("required_fit_count") != 18
        or len(fits) != 18
        or len({fit["run_id"] for fit in fits}) != 18
        or index.get("completed_fit_count")
        != sum(fit["status"] == "COMPLETED_AND_VERIFIED" for fit in fits)
    ):
        raise ValueError("progress index is incomplete or inconsistent")
    return {
        "sha256": hashlib.sha256(payload).hexdigest(),
        "completed_fit_count": index["completed_fit_count"],
        "required_fit_count": 18,
        "next_incomplete_fit": next(
            (
                fit["run_id"]
                for fit in fits
                if fit["status"] not in {"COMPLETED_AND_VERIFIED", "FAILED"}
            ),
            None,
        ),
        "status_counts": {
            status: sum(fit["status"] == status for fit in fits) for status in sorted(STATUSES)
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    init = modes.add_parser("init")
    init.add_argument("directory", type=Path)
    init.add_argument("--reference-sha256", required=True)
    init.add_argument("--runtime-sha256", required=True)
    init.add_argument("--amendment-sha256", required=True)
    init.add_argument("--accelerator-json", type=Path, required=True)
    init.add_argument("--compute-unit-balance", type=float, required=True)
    update = modes.add_parser("advance")
    update.add_argument("current_index", type=Path)
    update.add_argument("directory", type=Path)
    update.add_argument("run_id")
    update.add_argument("status", choices=sorted(STATUSES))
    update.add_argument("--attempt-number", type=int, required=True)
    update.add_argument("--checkpoint", type=Path)
    update.add_argument("--receipt", type=Path)
    update.add_argument("--checkpoint-readback", type=Path)
    update.add_argument("--receipt-readback", type=Path)
    update.add_argument("--checkpoint-drive-file-id")
    update.add_argument("--receipt-drive-file-id")
    update.add_argument("--infrastructure-confirmed", action="store_true")
    update.add_argument("--oom-excluded", action="store_true")
    update.add_argument("--reason")
    update.add_argument("--compute-unit-balance", type=float)
    update.add_argument("--compute-unit-rate-per-hour", type=float)
    check = modes.add_parser("verify")
    check.add_argument("index", type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    if args.mode == "init":
        accelerator = cast(dict[str, object], json.loads(args.accelerator_json.read_text()))
        path, digest = initialize(
            args.directory,
            reference_sha256=args.reference_sha256,
            runtime_sha256=args.runtime_sha256,
            amendment_sha256=args.amendment_sha256,
            accelerator=accelerator,
            compute_unit_balance=args.compute_unit_balance,
        )
        result = {"path": str(path), "sha256": digest}
    elif args.mode == "advance":
        path, digest = advance(
            args.current_index,
            args.directory,
            args.run_id,
            args.status,
            attempt_number=args.attempt_number,
            checkpoint_path=args.checkpoint,
            receipt_path=args.receipt,
            checkpoint_readback_path=args.checkpoint_readback,
            receipt_readback_path=args.receipt_readback,
            checkpoint_drive_file_id=args.checkpoint_drive_file_id,
            receipt_drive_file_id=args.receipt_drive_file_id,
            infrastructure_confirmed=args.infrastructure_confirmed,
            oom_excluded=args.oom_excluded,
            reason=args.reason,
            compute_unit_balance=args.compute_unit_balance,
            compute_unit_rate_per_hour=args.compute_unit_rate_per_hour,
        )
        result = {"path": str(path), "sha256": digest, **verify(path)}
    else:
        result = verify(args.index)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
