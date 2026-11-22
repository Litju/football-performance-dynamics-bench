"""Run one supervised Colab operation in the pinned research environment."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

ROOT = Path("/content/res338")
REPO = ROOT / "repo"
PYTHON = ROOT / "venv" / "bin" / "python"
REFERENCE = ROOT / "manifests" / "training-validation-reference.json"
REFERENCE_SHA = os.environ.get("RES338_REFERENCE_SHA256", "")
SOURCE = ROOT / "source"
RESEARCH = ROOT / "research"
CAMPAIGN = ROOT / "campaign"
LOMO_ROOT = ROOT / "res340-lomo"
LOMO_CAMPAIGN = LOMO_ROOT / "campaign"
LOMO_PRELOADED = LOMO_ROOT / "preloaded-cache"
LOMO_FEATURE_CACHE = LOMO_CAMPAIGN / "feature-cache"
LOMO_TRANSFER_CHUNKS = LOMO_ROOT / "transfer" / "chunks"
LOMO_CACHE_ARCHIVES = LOMO_ROOT / "cache-archives"
LOMO_APPROVAL = ROOT / "manifests" / "res340-execution-authorization.json"
LOMO_CACHE_MANIFEST = ROOT / "manifests" / "res338-reproducibility-manifest.json"
LOMO_CACHE_LEDGER = ROOT / "manifests" / "res338-progress-index.json"
PRELOADED = ROOT / "preloaded-cache"
TRANSFER_CHUNKS = ROOT / "transfer" / "chunks"
QUALIFICATION = ROOT / "runtime" / "cuda-qualification.json"
STATUS_PATH = Path(os.environ["RES338_JOB_STATUS_PATH"])
JOB_ID = os.environ["RES338_JOB_ID"]


def _status(updates: dict[str, object]) -> None:
    current = cast(dict[str, object], json.loads(STATUS_PATH.read_bytes()))
    current.update(updates, updated_at_utc=datetime.now(UTC).isoformat())
    temporary = STATUS_PATH.with_name(f".{STATUS_PATH.name}.{os.getpid()}.tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(json.dumps(current, sort_keys=True, separators=(",", ":")).encode())
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, STATUS_PATH)


def _require_lomo_execution_gate(kind: str) -> None:
    balance = float(os.environ["RES340_COMPUTE_UNIT_BALANCE"])
    rate = float(os.environ["RES340_COMPUTE_UNIT_RATE_PER_HOUR"])
    manifest_sha = os.environ["RES340_CACHE_MANIFEST_SHA256"]
    ledger_sha = os.environ["RES340_CACHE_LEDGER_SHA256"]
    manifest_path = Path(os.environ.get("RES340_CACHE_MANIFEST_PATH", str(LOMO_CACHE_MANIFEST)))
    ledger_path = Path(os.environ.get("RES340_CACHE_LEDGER_PATH", str(LOMO_CACHE_LEDGER)))
    progress_path_value = os.environ.get("RES340_PROGRESS_INDEX_PATH", "")
    progress_path = Path(progress_path_value)
    progress_sha256 = os.environ.get("RES340_PROGRESS_INDEX_SHA256", "")
    if not progress_path_value:
        raise ValueError("the exact content-addressed RES340 progress index path is required")
    sys.path.insert(0, str(REPO / "src"))
    sys.path.insert(0, str(REPO / "tools"))
    import res338_colab_progress as progress
    import res340_lomo
    import train_res338_final_fits as trainer

    plan, protocol, roles = trainer._frozen_split_and_authorities()
    if os.environ.get("RES340_CACHE_CHUNK_INDEX_SHA256") != (
        res340_lomo.RES338_CACHE_CHUNK_INDEX_SHA256
    ):
        raise ValueError("RES340 cache chunk index differs from the owner-verified RES338 archive")
    matrix = res340_lomo.build_fit_matrix(plan, protocol, roles)
    if json.loads((REPO / "docs/res340-lomo-fit-matrix.json").read_bytes()) != matrix:
        raise ValueError("RES340 fit matrix differs from the pinned plan and protocol")
    approval = trainer._read_private_json(LOMO_APPROVAL)
    if (
        trainer._sha256_file(manifest_path) != manifest_sha
        or trainer._sha256_file(ledger_path) != ledger_sha
    ):
        raise ValueError("RES338 cache reuse identities differ from the approved source record")
    amendment_sha = trainer._sha256_file(REPO / "docs/res340-lomo-gpu-execution-amendment.md")
    cloud_sha = trainer._sha256_file(REPO / "docs/res340-private-cloud-research-amendment.md")
    code_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    matrix_sha = res340_lomo.matrix_sha256(matrix)
    res340_lomo.verify_execution_approval(
        approval,
        amendment_sha256=amendment_sha,
        private_cloud_amendment_sha256=cloud_sha,
        fit_matrix_sha256=matrix_sha,
        cache_manifest_sha256=manifest_sha,
        cache_ledger_sha256=ledger_sha,
        code_sha=code_sha,
        compute_unit_spend_cap=trainer.RES340_COMPUTE_UNIT_SPEND_CAP,
    )
    if (
        len(progress_sha256) != 64
        or progress_path.name != f"progress-index-{progress_sha256}.json"
        or trainer._sha256_file(progress_path) != progress_sha256
    ):
        raise ValueError("the current content-addressed RES340 progress index is required")
    progress_index = trainer._read_private_json(progress_path)
    progress_snapshot = progress.verify(progress_path)
    campaign_started_at = str(progress_index["campaign_started_at_utc"])
    started_at = datetime.fromisoformat(campaign_started_at)
    if started_at.tzinfo is None or (datetime.now(UTC) - started_at).total_seconds() >= (
        336 * 60 * 60
    ):
        raise TimeoutError("RES340 total campaign wall ceiling reached before job start")
    os.environ["RES340_CAMPAIGN_STARTED_AT_UTC"] = campaign_started_at
    approval_sha256 = hashlib.sha256(trainer._canonical(approval)).hexdigest()
    res338_progress = trainer._read_private_json(ledger_path)
    expected_final_checkpoint_sha256s = res340_lomo.res338_final_checkpoint_hashes(
        res338_progress,
        reference_sha256=REFERENCE_SHA,
    )
    if (
        progress_index.get("fit_role") != "lomo"
        or progress_index.get("owner_authorization_sha256") != approval_sha256
        or progress_index.get("fit_matrix_sha256") != matrix_sha
        or progress_index.get("compute_unit_spend_cap") != trainer.RES340_COMPUTE_UNIT_SPEND_CAP
        or progress_index.get("compute_unit_balance_at_start")
        != approval["compute_unit_balance_at_start"]
        or progress_index.get("compute_unit_rate_per_hour_at_start")
        != approval["a100_compute_unit_rate_per_hour"]
        or progress_index.get("campaign_wall_budget_seconds") != 336 * 60 * 60
        or progress_index.get("lomo_cache_manifest_sha256") != manifest_sha
        or progress_index.get("lomo_cache_ledger_sha256") != ledger_sha
        or progress_index.get("final_checkpoint_sha256s") != expected_final_checkpoint_sha256s
    ):
        raise ValueError("the progress index does not bind this owner-approved LOMO campaign")
    status_counts = cast(dict[str, int], progress_snapshot["status_counts"])
    if status_counts.get("FAILED", 0):
        raise ValueError("RES340 progress contains a terminal scientific fit failure")
    if rate != float(approval["a100_compute_unit_rate_per_hour"]):
        raise ValueError("live A100 rate differs from the owner-approved compute contract")
    starting_balance = float(approval["compute_unit_balance_at_start"])
    remaining_fits = res340_lomo.FIT_COUNT - int(progress_index["completed_fit_count"])
    if kind == "restore-lomo-caches" and (LOMO_CAMPAIGN / "campaign.json").exists():
        raise ValueError("RES340 already has a frozen campaign; resume without restaging")
    if kind == "fit-lomo-one":
        ledger = trainer._read_private_json(LOMO_CAMPAIGN / "campaign.json")
        if (
            ledger.get("schema_id") != "fpdbench.res340.lomo-campaign-ledger"
            or ledger.get("required_fit_count") != res340_lomo.FIT_COUNT
            or int(ledger.get("failed_fit_count", 0)) != 0
        ):
            raise ValueError("RES340 progress is not eligible for a LOMO fit job")
        freeze_sha = str(ledger["frozen_manifest_sha256"])
        freeze = trainer._read_private_json(LOMO_CAMPAIGN / "reproducibility-manifest.json")
        if (
            trainer._sha256_file(LOMO_CAMPAIGN / "reproducibility-manifest.json") != freeze_sha
            or freeze.get("lomo_fit_matrix_sha256") != matrix_sha
        ):
            raise ValueError("RES340 campaign freeze differs from the approved fit matrix")
        remaining_fits -= int(ledger["completed_fit_count"])
        if remaining_fits <= 0:
            raise ValueError("RES340 campaign is already complete")
        progress_completed = {
            str(item["run_id"])
            for item in cast(list[dict[str, object]], progress_index["fits"])
            if item.get("status") == "COMPLETED_AND_VERIFIED"
        }
        ledger_completed = {
            str(item["run_id"])
            for item in cast(list[dict[str, object]], ledger.get("runs", []))
            if item.get("status") == "completed"
        }
        next_run_id = str(progress_snapshot["next_incomplete_fit"])
        fit_progress = next(
            item
            for item in cast(list[dict[str, object]], progress_index["fits"])
            if item.get("run_id") == next_run_id
        )
        retry_id = os.environ.get("RES340_RETRY_RUN_ID")
        current_run_id = ledger.get("current_run_id")
        attempt_count = int(fit_progress["attempt_count"])
        attempts = cast(list[dict[str, object]], fit_progress.get("attempts", []))
        retry_proof = attempts[0] if attempt_count == 2 and attempts else {}
        retry_proven = (
            attempt_count == 2
            and retry_proof.get("status") == "INTERRUPTED_RETRY_ELIGIBLE"
            and retry_proof.get("infrastructure_confirmed") is True
            and retry_proof.get("oom_excluded") is True
            and bool(retry_proof.get("reason"))
        )
        if (
            progress_completed != ledger_completed
            or fit_progress.get("status") != "RUNNING"
            or (attempt_count == 1 and retry_id is not None)
            or (attempt_count == 2 and (retry_id != next_run_id or not retry_proven))
            or attempt_count not in {1, 2}
            or (current_run_id is not None and retry_id != current_run_id)
            or (current_run_id is None and retry_id is not None and not retry_proven)
        ):
            raise ValueError("Drive progress and the local campaign disagree on the next fit")
        if retry_proven:
            os.environ["RES340_RETRY_INFRASTRUCTURE_CONFIRMED"] = "1"
            os.environ["RES340_RETRY_OOM_EXCLUDED"] = "1"
            os.environ["RES340_RETRY_REASON"] = str(retry_proof["reason"])
        starting_balance = float(freeze["compute_unit_balance_at_start"])
    elif kind == "prepare-lomo" and (
        progress_snapshot["completed_fit_count"] != 0
        or status_counts.get("NOT_STARTED", 0) != res340_lomo.FIT_COUNT
    ):
        raise ValueError("cache staging and fit preparation require a fresh LOMO progress index")
    res340_lomo.require_compute_unit_budget(
        current_balance=balance,
        current_rate_per_hour=rate,
        spend_cap=trainer.RES340_COMPUTE_UNIT_SPEND_CAP,
        starting_balance=starting_balance,
        remaining_work_units=remaining_fits * 1.25 * rate,
    )


def _command(kind: str) -> list[str]:
    if kind == "probe":
        return [
            str(PYTHON),
            str(REPO / "tools/res338_colab_gpu_probe.py"),
            "--output",
            str(ROOT / "runtime/gpu-runtime.json"),
        ]
    if kind == "prepare":
        return [
            str(PYTHON),
            str(REPO / "tools/res338_colab_prepare.py"),
            "--reference",
            str(REFERENCE),
            "--reference-sha256",
            REFERENCE_SHA,
            "--source-root",
            str(SOURCE),
            "--research-root",
            str(RESEARCH),
            "--repo-root",
            str(REPO),
        ]
    if kind == "qualify":
        return [
            str(PYTHON),
            str(REPO / "tools/res338_cuda_qualification.py"),
            "--output",
            str(QUALIFICATION),
        ]
    if kind == "stage-preloaded":
        index_sha = os.environ.get("RES338_CACHE_CHUNK_INDEX_SHA256", "")
        if len(index_sha) != 64 or any(char not in "0123456789abcdef" for char in index_sha):
            raise ValueError("a content-addressed preloaded cache chunk index SHA-256 is required")
        return [
            str(PYTHON),
            str(REPO / "tools/res338_cache_archive.py"),
            "stage-preloaded",
            str(ROOT / "manifests" / f"cache-chunk-index-{index_sha}.json"),
            index_sha,
            str(REFERENCE),
            REFERENCE_SHA,
            str(TRANSFER_CHUNKS),
            str(ROOT / "cache-archives"),
            str(PRELOADED),
        ]
    if kind == "restore-cache-archives":
        index_sha = os.environ.get("RES338_CACHE_CHUNK_INDEX_SHA256", "")
        if len(index_sha) != 64 or any(char not in "0123456789abcdef" for char in index_sha):
            raise ValueError("a content-addressed cache chunk index SHA-256 is required")
        return [
            str(PYTHON),
            str(REPO / "tools/res338_cache_archive.py"),
            "stage-all",
            str(ROOT / "manifests" / f"cache-chunk-index-{index_sha}.json"),
            index_sha,
            str(REFERENCE),
            REFERENCE_SHA,
            str(TRANSFER_CHUNKS),
            str(ROOT / "cache-archives" / "restored"),
            str(CAMPAIGN / "feature-cache"),
        ]
    if kind == "restore-lomo-caches":
        _require_lomo_execution_gate(kind)
        index_sha = os.environ.get("RES340_CACHE_CHUNK_INDEX_SHA256", "")
        if len(index_sha) != 64 or any(char not in "0123456789abcdef" for char in index_sha):
            raise ValueError("a content-addressed all-cache chunk index SHA-256 is required")
        return [
            str(PYTHON),
            str(REPO / "tools/res338_cache_archive.py"),
            "stage-all",
            str(ROOT / "manifests" / f"cache-chunk-index-{index_sha}.json"),
            index_sha,
            str(REFERENCE),
            REFERENCE_SHA,
            str(LOMO_TRANSFER_CHUNKS),
            str(LOMO_CACHE_ARCHIVES / "restored"),
            str(LOMO_PRELOADED),
        ]
    trainer = str(REPO / "tools/train_res338_final_fits.py")
    common = [
        str(PYTHON),
        trainer,
        str(RESEARCH),
        str(SOURCE),
        str(CAMPAIGN),
        "--device",
        "cuda",
        "--research-scope",
        "training-validation",
        "--reference-manifest",
        str(REFERENCE),
        "--reference-manifest-sha256",
        REFERENCE_SHA,
        "--preloaded-cache-root",
        str(PRELOADED),
        "--toy-preflight",
        str(QUALIFICATION),
    ]
    if kind == "prepare-campaign":
        return [*common, "--prepare-only"]
    if kind == "fit-one":
        command = [*common, "--resume", "--max-new-fits", "1"]
        retry_id = os.environ.get("RES338_RETRY_RUN_ID")
        if retry_id:
            command.extend(["--retry-interrupted-run", retry_id])
        return command
    if kind in {"prepare-lomo", "fit-lomo-one"}:
        _require_lomo_execution_gate(kind)
        balance = os.environ.get("RES340_COMPUTE_UNIT_BALANCE", "")
        rate = os.environ.get("RES340_COMPUTE_UNIT_RATE_PER_HOUR", "")
        cache_manifest_sha = os.environ.get("RES340_CACHE_MANIFEST_SHA256", "")
        cache_ledger_sha = os.environ.get("RES340_CACHE_LEDGER_SHA256", "")
        cache_manifest_path = Path(
            os.environ.get("RES340_CACHE_MANIFEST_PATH", str(LOMO_CACHE_MANIFEST))
        )
        cache_ledger_path = Path(os.environ.get("RES340_CACHE_LEDGER_PATH", str(LOMO_CACHE_LEDGER)))
        for label, value in (
            ("Colab balance", balance),
            ("A100 consumption rate", rate),
            ("RES338 cache manifest SHA-256", cache_manifest_sha),
            ("RES338 campaign ledger SHA-256", cache_ledger_sha),
        ):
            if not value:
                raise ValueError(f"fresh {label} is required for RES340")
        common_lomo = [
            str(PYTHON),
            trainer,
            str(RESEARCH),
            str(SOURCE),
            str(LOMO_CAMPAIGN),
            "--device",
            "cuda",
            "--research-scope",
            "training-validation",
            "--reference-manifest",
            str(REFERENCE),
            "--reference-manifest-sha256",
            REFERENCE_SHA,
            "--preloaded-cache-root",
            str(LOMO_FEATURE_CACHE),
            "--toy-preflight",
            str(QUALIFICATION),
            "--fit-role",
            "lomo",
            "--owner-approval",
            str(LOMO_APPROVAL),
            "--compute-unit-balance",
            balance,
            "--compute-unit-rate-per-hour",
            rate,
            "--campaign-started-at-utc",
            os.environ["RES340_CAMPAIGN_STARTED_AT_UTC"],
            "--lomo-cache-manifest",
            str(cache_manifest_path),
            "--lomo-cache-manifest-sha256",
            cache_manifest_sha,
            "--lomo-cache-ledger",
            str(cache_ledger_path),
            "--lomo-cache-ledger-sha256",
            cache_ledger_sha,
        ]
        if kind == "prepare-lomo":
            return [*common_lomo, "--prepare-only"]
        command = [*common_lomo, "--resume", "--max-new-fits", "1"]
        retry_id = os.environ.get("RES340_RETRY_RUN_ID")
        if retry_id:
            command.extend(["--retry-interrupted-run", retry_id])
            if os.environ.get("RES340_RETRY_INFRASTRUCTURE_CONFIRMED") == "1":
                command.append("--retry-infrastructure-confirmed")
            if os.environ.get("RES340_RETRY_OOM_EXCLUDED") == "1":
                command.append("--retry-oom-excluded")
            retry_reason = os.environ.get("RES340_RETRY_REASON")
            if retry_reason:
                command.extend(["--retry-reason", retry_reason])
        return command
    raise ValueError("unknown supervised Colab job kind")


def _campaign_summary(kind: str) -> dict[str, object]:
    campaign_root = LOMO_CAMPAIGN if kind in {"prepare-lomo", "fit-lomo-one"} else CAMPAIGN
    path = campaign_root / "campaign.json"
    if not path.is_file():
        return {}
    ledger = cast(dict[str, object], json.loads(path.read_bytes()))
    return {
        "campaign_status": ledger.get("status"),
        "completed_fit_count": ledger.get("completed_fit_count"),
        "failed_fit_count": ledger.get("failed_fit_count"),
        "current_run_id": ledger.get("current_run_id"),
        "current_attempt": ledger.get("current_attempt"),
        "reserved_gpu_wall_seconds": ledger.get("reserved_gpu_wall_seconds"),
        "recorded_gpu_wall_seconds": ledger.get("recorded_gpu_wall_seconds"),
    }


def _remove_verified_preparation_inputs() -> list[str]:
    ledger_path = CAMPAIGN / "campaign.json"
    freeze_path = CAMPAIGN / "reproducibility-manifest.json"
    ledger = cast(dict[str, object], json.loads(ledger_path.read_bytes()))
    freeze_bytes = freeze_path.read_bytes()
    freeze = cast(dict[str, object], json.loads(freeze_bytes))
    roles = cast(dict[str, list[str]], freeze["research_roles"])
    caches = cast(dict[str, object], freeze["feature_cache"])
    selected = set(roles["training"]) | set(roles["validation"])
    if (
        ledger.get("status") != "PREPARED"
        or ledger.get("completed_fit_count") != 0
        or ledger.get("failed_fit_count") != 0
        or ledger.get("required_fit_count") != 18
        or hashlib.sha256(freeze_bytes).hexdigest() != ledger.get("frozen_manifest_sha256")
        or freeze.get("schema_id") != "fpdbench.res338-research-final-fit-campaign"
        or freeze.get("research_scope") != "training-validation"
        or freeze.get("protected_status") != "NOT_QUALIFIED"
        or len(roles.get("training", [])) != 12
        or len(roles.get("validation", [])) != 4
        or len(caches) != 16
        or set(caches) != selected
    ):
        raise ValueError("cannot remove source inputs before the exact 16-cache campaign is frozen")
    removed = []
    for path in (SOURCE, RESEARCH, PRELOADED, TRANSFER_CHUNKS):
        if path.is_symlink() or ROOT.resolve() not in path.resolve().parents:
            raise ValueError("Colab preparation cleanup path escaped its private workspace")
        if not path.exists():
            continue
        shutil.rmtree(path)
        removed.append(path.relative_to(ROOT).as_posix())
    return removed


def _finalize_lomo_cache_stage() -> list[str]:
    import sys

    sys.path.insert(0, str(REPO / "src"))
    sys.path.insert(0, str(REPO / "tools"))
    import train_res338_final_fits as trainer

    _, _, roles = trainer._frozen_split_and_authorities()
    expected = set(roles["training"]) | set(roles["validation"])
    expected_roles = {
        **{match_id: "training" for match_id in roles["training"]},
        **{match_id: "validation" for match_id in roles["validation"]},
    }
    manifest_path = Path(os.environ.get("RES340_CACHE_MANIFEST_PATH", str(LOMO_CACHE_MANIFEST)))
    manifest_sha = os.environ["RES340_CACHE_MANIFEST_SHA256"]
    if trainer._sha256_file(manifest_path) != manifest_sha:
        raise ValueError("RES338 cache manifest changed during RES340 staging")
    freeze = trainer._read_private_json(manifest_path)
    identities = cast(dict[str, dict[str, object]], freeze.get("feature_cache", {}))
    if set(identities) != expected or len(identities) != 16:
        raise ValueError("RES338 cache manifest does not contain the exact 16 matches")
    for match_id, identity in identities.items():
        if identity.get("role") != expected_roles[match_id]:
            raise ValueError("RES338 cache manifest contains a role mismatch")

    def verify_root(path: Path) -> None:
        if not trainer._has_staged_preloaded_caches(path, expected, expected_roles):
            raise ValueError("RES340 restore did not stage all 16 verified caches")
        for match_id, identity in identities.items():
            trainer._verified_preloaded_cache(
                path / expected_roles[match_id] / match_id,
                match_id,
                expected_roles[match_id],
                identity,
            )

    verify_root(LOMO_PRELOADED)
    LOMO_CAMPAIGN.mkdir(mode=0o700, parents=True, exist_ok=True)
    LOMO_CAMPAIGN.chmod(0o700)
    feature_cache = LOMO_CAMPAIGN / "feature-cache"
    if feature_cache.exists() or feature_cache.is_symlink():
        verify_root(feature_cache)
        shutil.rmtree(LOMO_PRELOADED)
    else:
        os.rename(LOMO_PRELOADED, feature_cache)
        trainer._fsync_directory(LOMO_CAMPAIGN)
    removed: list[str] = []
    for path in (LOMO_TRANSFER_CHUNKS.parent, LOMO_CACHE_ARCHIVES):
        if path.is_symlink() or LOMO_ROOT.resolve() not in path.resolve().parents:
            raise ValueError("RES340 cache cleanup escaped its private workspace")
        if path.exists():
            shutil.rmtree(path)
            removed.append(path.relative_to(ROOT).as_posix())
    return removed


def run(kind: str) -> dict[str, object]:
    if not PYTHON.is_file():
        raise FileNotFoundError("the pinned Colab Python environment is missing")
    expected_code_sha = os.environ.get("RES338_CODE_SHA")
    current_code_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
    ).strip()
    if not expected_code_sha or current_code_sha != expected_code_sha:
        raise RuntimeError("Colab job checkout differs from the frozen campaign code SHA")
    if (
        not REFERENCE.is_file()
        or hashlib.sha256(REFERENCE.read_bytes()).hexdigest() != REFERENCE_SHA
    ):
        raise ValueError("Colab job reference manifest differs from its frozen SHA-256")
    if kind == "pack-caches":
        import sys

        sys.path.insert(0, str(REPO / "src"))
        sys.path.insert(0, str(REPO / "tools"))
        import res338_cache_archive as cache_archive

        archive_dir = ROOT / "cache-archives"
        archive_dir.mkdir(mode=0o700, exist_ok=True)
        _status({"status": "RUNNING", "started_at_utc": datetime.now(UTC).isoformat()})
        start = time.monotonic()
        result = cache_archive.pack_training_validation_caches(
            CAMPAIGN / "feature-cache", archive_dir, REFERENCE, REFERENCE_SHA
        )
        _status(
            {
                "status": "COMPLETED",
                "elapsed_seconds": round(time.monotonic() - start, 3),
                "finished_at_utc": datetime.now(UTC).isoformat(),
                "exit_code": 0,
            }
        )
        return result

    command = _command(kind)
    env = os.environ.copy()
    env.update(
        CUBLAS_WORKSPACE_CONFIG=":4096:8",
        RES338_COLAB_SESSION_NAME=os.environ.get("RES338_COLAB_SESSION_NAME", ""),
        RES338_COLAB_SESSION_ID=os.environ.get("RES338_COLAB_SESSION_ID", ""),
        PYTHONPATH=f"{REPO / 'src'}:{REPO / 'tools'}",
    )
    if kind in {"prepare-campaign", "fit-one", "prepare-lomo", "fit-lomo-one"}:
        env["RES338_COLAB_SESSION_NAME"] = os.environ.get("RES338_COLAB_SESSION_NAME", "")
        env["RES338_COLAB_SESSION_ID"] = os.environ.get("RES338_COLAB_SESSION_ID", "")
    log_path = ROOT / "logs" / f"{JOB_ID}.log"
    log_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _status(
        {"status": "RUNNING", "pid": os.getpid(), "started_at_utc": datetime.now(UTC).isoformat()}
    )
    start = time.monotonic()
    _status({"command_kind": kind})
    with log_path.open("ab", buffering=0) as log:
        process = subprocess.Popen(command, cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT)
        _status({"child_pid": process.pid, "log_path": str(log_path)})
        last_heartbeat = 0.0
        while process.poll() is None:
            elapsed = time.monotonic() - start
            if elapsed - last_heartbeat >= 30:
                snapshot = (
                    _campaign_summary(kind)
                    if kind in {"prepare-campaign", "fit-one", "prepare-lomo", "fit-lomo-one"}
                    else {}
                )
                gpu = subprocess.run(
                    [
                        "nvidia-smi",
                        "--query-gpu=name,utilization.gpu,memory.used,memory.total",
                        "--format=csv,noheader,nounits",
                    ],
                    capture_output=True,
                    check=False,
                    text=True,
                    timeout=10,
                )
                _status(
                    {
                        **snapshot,
                        "elapsed_seconds": round(elapsed, 3),
                        "gpu": gpu.stdout.strip() if gpu.returncode == 0 else "unavailable",
                    }
                )
                last_heartbeat = elapsed
            time.sleep(5)
        returncode = process.wait()
    if kind == "restore-lomo-caches" and returncode == 0:
        _finalize_lomo_cache_stage()
    cleanup = (
        {"temporary_inputs_removed": _remove_verified_preparation_inputs()}
        if kind == "prepare-campaign" and returncode == 0
        else {}
    )
    campaign = (
        _campaign_summary(kind)
        if kind in {"prepare-campaign", "fit-one", "prepare-lomo", "fit-lomo-one"}
        else {}
    )
    updates = {
        **campaign,
        **cleanup,
        "elapsed_seconds": round(time.monotonic() - start, 3),
        "finished_at_utc": datetime.now(UTC).isoformat(),
        "exit_code": returncode,
        "status": "COMPLETED" if returncode == 0 else "FAILED",
    }
    if returncode != 0:
        updates["error_message"] = f"worker exited with status {returncode}; see private Colab log"
    _status(updates)
    return updates


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "kind",
        choices=(
            "probe",
            "prepare",
            "qualify",
            "stage-preloaded",
            "restore-cache-archives",
            "prepare-campaign",
            "fit-one",
            "pack-caches",
        ),
    )
    args = parser.parse_args()
    try:
        result = run(args.kind)
    except Exception as exc:
        _status(
            {
                "status": "FAILED",
                "error_type": type(exc).__name__,
                "error_message": str(exc)[:1000],
                "finished_at_utc": datetime.now(UTC).isoformat(),
            }
        )
        raise
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
