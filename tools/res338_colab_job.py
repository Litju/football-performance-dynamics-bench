"""Run one supervised Colab operation in the pinned research environment."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
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
    raise ValueError("unknown supervised Colab job kind")


def _campaign_summary() -> dict[str, object]:
    path = CAMPAIGN / "campaign.json"
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
        return cache_archive.pack_training_validation_caches(
            CAMPAIGN / "feature-cache", archive_dir, REFERENCE, REFERENCE_SHA
        )

    command = _command(kind)
    env = os.environ.copy()
    env.update(
        CUBLAS_WORKSPACE_CONFIG=":4096:8",
        RES338_COLAB_SESSION_NAME=os.environ.get("RES338_COLAB_SESSION_NAME", ""),
        RES338_COLAB_SESSION_ID=os.environ.get("RES338_COLAB_SESSION_ID", ""),
        PYTHONPATH=f"{REPO / 'src'}:{REPO / 'tools'}",
    )
    if kind in {"prepare-campaign", "fit-one"}:
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
                snapshot = _campaign_summary() if kind in {"prepare-campaign", "fit-one"} else {}
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
    campaign = _campaign_summary() if kind in {"prepare-campaign", "fit-one"} else {}
    updates = {
        **campaign,
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
        choices=("probe", "prepare", "qualify", "prepare-campaign", "fit-one", "pack-caches"),
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
