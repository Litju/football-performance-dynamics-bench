"""Start or inspect one supervised Colab operation."""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

ROOT = Path("/content/res338")
REPO = ROOT / "repo"
PYTHON = ROOT / "venv" / "bin" / "python"
JOBS = ROOT / "jobs"


def _write_json(path: Path, value: object) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _read_json(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_bytes()))


def _current_job() -> dict[str, object] | None:
    pointer = JOBS / "current.json"
    if not pointer.exists():
        return None
    reference = _read_json(pointer)
    path = JOBS / f"{reference['job_id']}.json"
    return _read_json(path)


def start() -> dict[str, object]:
    os.umask(0o077)
    kind = os.environ.get("RES338_JOB_KIND")
    if kind not in {
        "prepare",
        "qualify",
        "stage-preloaded",
        "prepare-campaign",
        "pack-caches",
        "fit-one",
    }:
        raise ValueError("unknown Colab job kind")
    if not PYTHON.is_file() or not REPO.is_dir():
        raise FileNotFoundError("pinned Colab environment is not installed")
    expected_code_sha = os.environ.get("RES338_CODE_SHA")
    current_code_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
    ).strip()
    if not expected_code_sha or current_code_sha != expected_code_sha:
        raise RuntimeError("Colab worker checkout differs from the frozen campaign code SHA")
    JOBS.mkdir(mode=0o700, parents=True, exist_ok=True)
    JOBS.chmod(0o700)
    current = _current_job()
    if current is not None and current.get("status") in {"STARTING", "RUNNING"}:
        raise RuntimeError("another supervised Colab worker is still active")
    job_id = uuid.uuid4().hex
    status_path = JOBS / f"{job_id}.json"
    log_path = ROOT / "logs" / f"{job_id}.log"
    log_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _write_json(
        status_path,
        {
            "schema_id": "fpdbench.res338.colab-job",
            "schema_version": "1.0.0",
            "job_id": job_id,
            "kind": kind,
            "status": "STARTING",
            "started_at_utc": datetime.now(UTC).isoformat(),
            "session_name": os.environ.get("RES338_COLAB_SESSION_NAME"),
            "session_id": os.environ.get("RES338_COLAB_SESSION_ID"),
        },
    )
    env = os.environ.copy()
    env["RES338_JOB_ID"] = job_id
    env["RES338_JOB_STATUS_PATH"] = str(status_path)
    command = [str(PYTHON), str(REPO / "tools/res338_colab_job.py"), kind]
    with log_path.open("ab", buffering=0) as log:
        process = subprocess.Popen(
            command,
            cwd=REPO,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    _write_json(JOBS / "current.json", {"job_id": job_id})
    print(json.dumps({"status": "STARTED", "job_id": job_id, "kind": kind, "pid": process.pid}))
    return {"job_id": job_id, "pid": process.pid}


def status() -> dict[str, object]:
    current = _current_job()
    if current is None:
        result = {"status": "NO_JOB"}
        print(json.dumps(result))
        return result
    if current.get("status") in {"STARTING", "RUNNING"}:
        try:
            os.kill(int(current["pid"]), 0)
        except (KeyError, ProcessLookupError):
            status_path = JOBS / f"{current['job_id']}.json"
            current = _read_json(status_path)
            if current.get("status") in {"STARTING", "RUNNING"}:
                current.update(
                    status="INTERRUPTED",
                    interrupted_at_utc=datetime.now(UTC).isoformat(),
                    interruption_reason=(
                        "supervised process disappeared before writing a terminal status"
                    ),
                )
                _write_json(status_path, current)
    summary = {
        key: current.get(key)
        for key in (
            "job_id",
            "kind",
            "status",
            "started_at_utc",
            "updated_at_utc",
            "finished_at_utc",
            "pid",
            "campaign_status",
            "completed_fit_count",
            "failed_fit_count",
            "current_run_id",
            "current_attempt",
            "gpu",
            "elapsed_seconds",
            "error_type",
            "error_message",
        )
        if key in current
    }
    print(json.dumps(summary, sort_keys=True))
    return summary


def main() -> None:
    os.umask(0o077)
    operation = os.environ.get("RES338_OPERATION", "status")
    if operation == "start":
        start()
    elif operation == "status":
        status()
    else:
        raise ValueError("RES338_OPERATION must be start or status")


if __name__ == "__main__":
    main()
