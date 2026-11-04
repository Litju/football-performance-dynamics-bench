from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
import res338_colab_worker as worker  # noqa: E402


@pytest.mark.parametrize(
    ("initial_status", "expected_status"),
    [("FAILED", "FAILED"), ("RUNNING", "INTERRUPTED")],
)
def test_worker_status_preserves_a_written_terminal_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    initial_status: str,
    expected_status: str,
) -> None:
    monkeypatch.setattr(worker, "JOBS", tmp_path)
    job_id = "job-1"
    (tmp_path / "current.json").write_text(json.dumps({"job_id": job_id}))
    (tmp_path / f"{job_id}.json").write_text(
        json.dumps({"job_id": job_id, "pid": 987654321, "status": initial_status})
    )
    monkeypatch.setattr(
        worker,
        "_current_job",
        lambda: {"job_id": job_id, "pid": 987654321, "status": "RUNNING"},
    )

    def missing_process(_pid: int, _signal: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(worker.os, "kill", missing_process)
    result = worker.status()

    assert result["status"] == expected_status
    assert json.loads((tmp_path / f"{job_id}.json").read_text())["status"] == expected_status
