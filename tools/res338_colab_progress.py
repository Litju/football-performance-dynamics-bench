"""Maintain a private, content-addressed research fit progress index."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from collections.abc import Sequence
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
    fit_role: str = "final_train",
    compute_unit_spend_cap: float | None = None,
    compute_unit_rate_per_hour: float | None = None,
    owner_authorization_sha256: str | None = None,
    final_checkpoint_sha256s: Sequence[str] = (),
    lomo_cache_manifest_sha256: str | None = None,
    lomo_cache_ledger_sha256: str | None = None,
    compute_unit_balance_at_start: float | None = None,
) -> tuple[Path, str]:
    if fit_role not in {"final_train", "lomo"}:
        raise ValueError("unknown progress fit role")
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
    matrix_sha256: str | None = None
    if fit_role == "lomo":
        import res340_lomo

        if compute_unit_spend_cap is None or compute_unit_rate_per_hour is None:
            raise ValueError("RES340 needs a fixed spend cap and current A100 consumption rate")
        if (
            owner_authorization_sha256 is None
            or SHA256.fullmatch(owner_authorization_sha256) is None
        ):
            raise ValueError("RES340 progress needs the owner authorization SHA-256")
        if compute_unit_balance_at_start is None:
            raise ValueError("RES340 progress needs the pre-allocation balance snapshot")
        res340_lomo.require_compute_unit_budget(
            current_balance=compute_unit_balance,
            current_rate_per_hour=compute_unit_rate_per_hour,
            spend_cap=compute_unit_spend_cap,
            starting_balance=compute_unit_balance_at_start,
            remaining_work_units=(res340_lomo.FIT_COUNT * 1.25 * compute_unit_rate_per_hour),
        )
        if (
            len(final_checkpoint_sha256s) != 18
            or len(set(final_checkpoint_sha256s)) != 18
            or any(SHA256.fullmatch(value) is None for value in final_checkpoint_sha256s)
        ):
            raise ValueError("RES340 progress must bind all 18 final checkpoint identities")
        if any(
            value is None or SHA256.fullmatch(value) is None
            for value in (lomo_cache_manifest_sha256, lomo_cache_ledger_sha256)
        ):
            raise ValueError("RES340 progress must bind its verified RES338 cache records")
        matrix = res340_lomo.build_fit_matrix(plan, protocol, roles)
        matrix_sha256 = res340_lomo.matrix_sha256(matrix)
        configs = res340_lomo.expand_fit_matrix(matrix)
        required_fit_count = res340_lomo.FIT_COUNT
    else:
        configs = trainer._fit_order(training, validation)
        required_fit_count = 18
    fits = []
    for fit in configs:
        if fit_role == "lomo":
            config = res340_lomo.fit_configuration(
                fit,
                plan_sha256=str(plan["plan_sha256"]),
                protocol_sha256=str(protocol["protocol_sha256"]),
                device="cuda",
            )
        else:
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
                "lomo_fold_id": fit.get("fold_id"),
                "lomo_held_out_match_id": fit.get("held_out_match_id"),
                "train_match_ids": fit.get("train_match_ids"),
                "validation_match_ids": fit.get("validation_match_ids"),
                "configuration_sha256": hashlib.sha256(_canonical(config)).hexdigest(),
                "status": "NOT_STARTED",
                "attempt_count": 0,
                "attempts": [],
            }
        )
    if (
        len(fits) != required_fit_count
        or len({fit["run_id"] for fit in fits}) != required_fit_count
    ):
        raise ValueError("the frozen progress schedule has missing or duplicate fit IDs")
    index: dict[str, object] = {
        "schema_id": (
            "fpdbench.res340.lomo-colab-progress"
            if fit_role == "lomo"
            else "fpdbench.res338.colab-progress"
        ),
        "schema_version": "1.0.0",
        "sequence": 0,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "updated_at_utc": datetime.now(UTC).isoformat(),
        "campaign_started_at_utc": datetime.now(UTC).isoformat(),
        "campaign_wall_budget_seconds": 336 * 60 * 60,
        "previous_index_sha256": None,
        "required_fit_count": required_fit_count,
        "fit_role": fit_role,
        "fit_matrix_sha256": matrix_sha256,
        "owner_authorization_sha256": owner_authorization_sha256,
        "final_checkpoint_sha256s": list(final_checkpoint_sha256s),
        "lomo_cache_manifest_sha256": lomo_cache_manifest_sha256,
        "lomo_cache_ledger_sha256": lomo_cache_ledger_sha256,
        "completed_fit_count": 0,
        "parent_research_manifest_sha256": trainer.RESEARCH_MANIFEST_SHA256,
        "plan_sha256": plan["plan_sha256"],
        "protocol_sha256": protocol["protocol_sha256"],
        "research_reference_sha256": reference_sha256,
        "gpu_runtime_sha256": runtime_sha256,
        "gpu_execution_amendment_sha256": amendment_sha256,
        "accelerator": accelerator,
        "compute_unit_balance_at_start": (
            compute_unit_balance_at_start if fit_role == "lomo" else compute_unit_balance
        ),
        "compute_unit_spend_cap": (
            compute_unit_spend_cap if fit_role == "lomo" else compute_unit_balance
        ),
        "compute_unit_balance_latest": compute_unit_balance,
        "compute_unit_spent": 0.0,
        "compute_unit_rate_per_hour_at_start": compute_unit_rate_per_hour,
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
        raise ValueError("run ID is outside the frozen fit schedule")
    fit_role = str(index.get("fit_role", "final_train"))
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
        if str(index.get("fit_role", "final_train")) == "lomo":
            receipt_value = trainer._read_private_json(cast(Path, receipt_path))
            prior_lomo_checkpoint_shas = {
                str(attempt.get("checkpoint_sha256"))
                for item in fits
                if item is not fit and item.get("status") == "COMPLETED_AND_VERIFIED"
                for attempt in cast(list[dict[str, object]], item.get("attempts", []))
                if attempt.get("status") == "COMPLETED_AND_VERIFIED"
            }
            if (
                receipt_value.get("run_id") != run_id
                or receipt_value.get("status") != "completed"
                or receipt_value.get("fit_role") != "lomo"
                or receipt_value.get("configuration_sha256") != fit["configuration_sha256"]
                or receipt_value.get("lomo_fold_id") != fit.get("lomo_fold_id")
                or receipt_value.get("lomo_held_out_match_id") != fit.get("lomo_held_out_match_id")
                or receipt_value.get("information_regime") != fit["information_regime"]
                or receipt_value.get("target_representation") != fit["target_representation"]
                or receipt_value.get("seed") != fit["seed"]
                or receipt_value.get("train_match_ids") != fit["train_match_ids"]
                or receipt_value.get("validation_match_ids") != fit["validation_match_ids"]
                or receipt_value.get("plan_sha256") != index["plan_sha256"]
                or receipt_value.get("protocol_sha256") != index["protocol_sha256"]
                or receipt_value.get("population_manifest_sha256")
                != index["parent_research_manifest_sha256"]
                or receipt_value.get("checkpoint_sha256") != checkpoint_sha256
                or checkpoint_sha256 in set(cast(list[str], index["final_checkpoint_sha256s"]))
                or checkpoint_sha256 in prior_lomo_checkpoint_shas
            ):
                raise ValueError(
                    "RES340 receipt differs from its frozen fit or final checkpoint set"
                )
            checkpoint_value = trainer.load_checkpoint_verified(
                cast(Path, checkpoint_path), checkpoint_sha256
            )
            metadata = cast(dict[str, object], checkpoint_value["metadata"])
            if (
                metadata.get("run_id") != run_id
                or metadata.get("configuration_sha256") != fit["configuration_sha256"]
                or metadata.get("attempt_number") != attempt_number
            ):
                raise ValueError("RES340 checkpoint metadata differs from its receipt")
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
        if fit_role == "lomo":
            started = datetime.fromisoformat(str(index["campaign_started_at_utc"]))
            if (datetime.now(UTC) - started).total_seconds() >= float(
                index["campaign_wall_budget_seconds"]
            ):
                raise TimeoutError("RES340 total campaign wall ceiling reached before fit start")
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
        if fit_role == "lomo" and compute_unit_rate_per_hour != float(
            index["compute_unit_rate_per_hour_at_start"]
        ):
            raise ValueError("live A100 rate changed from the owner-approved resource freeze")
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
    if fit_role == "lomo" and starts_attempt:
        assert compute_unit_balance is not None and compute_unit_rate_per_hour is not None
        remaining_seconds = 0.0
        for item in fits:
            item_status = str(item["status"])
            attempts_used = int(item["attempt_count"])
            if item_status in {"COMPLETED_AND_VERIFIED", "FAILED"}:
                continue
            if item is fit:
                remaining_seconds += 900.0 if attempt_number == 2 else 4500.0
            elif item_status == "INTERRUPTED_RETRY_ELIGIBLE":
                remaining_seconds += 900.0
            elif attempts_used == 0:
                remaining_seconds += 4500.0
            else:
                remaining_seconds += 900.0
        remaining_units = remaining_seconds / 3600.0 * compute_unit_rate_per_hour
        start_balance = float(index["compute_unit_balance_at_start"])
        spent = start_balance - compute_unit_balance
        if compute_unit_balance < remaining_units or spent + remaining_units > float(
            index["compute_unit_spend_cap"]
        ):
            raise ValueError("remaining balance cannot cover all unstarted LOMO fits")
    index["sequence"] = int(index["sequence"]) + 1
    index["updated_at_utc"] = datetime.now(UTC).isoformat()
    index["previous_index_sha256"] = old_sha
    index["completed_fit_count"] = sum(item["status"] == "COMPLETED_AND_VERIFIED" for item in fits)
    if int(index["completed_fit_count"]) > int(index["required_fit_count"]):
        raise ValueError("progress index exceeds its frozen fit schedule")
    return _write_version(index, directory)


def verify(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    index = cast(dict[str, object], json.loads(payload))
    fits = cast(list[dict[str, object]], index["fits"])
    fit_role = str(index.get("fit_role", "final_train"))
    required_fit_count = 216 if fit_role == "lomo" else 18
    schema_id = (
        "fpdbench.res340.lomo-colab-progress"
        if fit_role == "lomo"
        else "fpdbench.res338.colab-progress"
    )
    if (
        index.get("schema_id") != schema_id
        or index.get("required_fit_count") != required_fit_count
        or len(fits) != required_fit_count
        or len({fit["run_id"] for fit in fits}) != required_fit_count
        or index.get("completed_fit_count")
        != sum(fit["status"] == "COMPLETED_AND_VERIFIED" for fit in fits)
    ):
        raise ValueError("progress index is incomplete or inconsistent")
    if fit_role == "lomo":
        import res340_lomo

        plan, protocol, roles = trainer._frozen_split_and_authorities()
        expected_matrix = res340_lomo.build_fit_matrix(plan, protocol, roles)
        expected_fits = cast(list[dict[str, object]], expected_matrix["fits"])
        if (
            index.get("fit_matrix_sha256") != res340_lomo.matrix_sha256(expected_matrix)
            or [fit["run_id"] for fit in fits] != [fit["run_id"] for fit in expected_fits]
            or [fit["configuration_sha256"] for fit in fits]
            != [fit["configuration_sha256"] for fit in expected_fits]
        ):
            raise ValueError("RES340 progress identities differ from the frozen 216-fit matrix")
        if (
            float(index.get("compute_unit_spend_cap", 0.0))
            < res340_lomo.PROPOSED_COMPUTE_UNIT_SPEND_CAP
            or float(index.get("compute_unit_rate_per_hour_at_start", 0.0)) <= 0
            or SHA256.fullmatch(str(index.get("owner_authorization_sha256", ""))) is None
            or SHA256.fullmatch(str(index.get("lomo_cache_manifest_sha256", ""))) is None
            or SHA256.fullmatch(str(index.get("lomo_cache_ledger_sha256", ""))) is None
            or index.get("campaign_wall_budget_seconds") != 336 * 60 * 60
            or len(cast(list[str], index.get("final_checkpoint_sha256s", []))) != 18
            or len(set(cast(list[str], index.get("final_checkpoint_sha256s", [])))) != 18
            or any(
                SHA256.fullmatch(value) is None
                for value in cast(list[str], index.get("final_checkpoint_sha256s", []))
            )
        ):
            raise ValueError("RES340 progress index lacks the fixed compute budget")
    return {
        "sha256": hashlib.sha256(payload).hexdigest(),
        "completed_fit_count": index["completed_fit_count"],
        "required_fit_count": required_fit_count,
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
    init.add_argument("--fit-role", choices=("final_train", "lomo"), default="final_train")
    init.add_argument("--compute-unit-spend-cap", type=float)
    init.add_argument("--compute-unit-rate-per-hour", type=float)
    init.add_argument("--owner-authorization-sha256")
    init.add_argument("--final-checkpoint-shas-json", type=Path)
    init.add_argument("--lomo-cache-manifest-sha256")
    init.add_argument("--lomo-cache-ledger-sha256")
    init.add_argument("--compute-unit-balance-at-start", type=float)
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
            fit_role=args.fit_role,
            compute_unit_spend_cap=args.compute_unit_spend_cap,
            compute_unit_rate_per_hour=args.compute_unit_rate_per_hour,
            owner_authorization_sha256=args.owner_authorization_sha256,
            final_checkpoint_sha256s=(
                cast(list[str], json.loads(args.final_checkpoint_shas_json.read_text()))
                if args.final_checkpoint_shas_json is not None
                else ()
            ),
            lomo_cache_manifest_sha256=args.lomo_cache_manifest_sha256,
            lomo_cache_ledger_sha256=args.lomo_cache_ledger_sha256,
            compute_unit_balance_at_start=args.compute_unit_balance_at_start,
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
