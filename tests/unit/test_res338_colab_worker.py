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


def test_execute_keeps_the_colab_kernel_attached_until_job_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = worker
    repo = tmp_path / "repo"
    repo.mkdir()
    python = tmp_path / "venv" / "python"
    python.parent.mkdir()
    python.touch()
    monkeypatch.setattr(job, "ROOT", tmp_path)
    monkeypatch.setattr(job, "REPO", repo)
    monkeypatch.setattr(job, "PYTHON", python)
    monkeypatch.setattr(job, "JOBS", tmp_path / "jobs")
    monkeypatch.setenv("RES338_JOB_KIND", "qualify")
    monkeypatch.setenv("RES338_CODE_SHA", "a" * 40)
    monkeypatch.setenv("RES338_COLAB_SESSION_NAME", "test-session")
    monkeypatch.setenv("RES338_COLAB_SESSION_ID", "test-session-id")
    monkeypatch.setattr(job.subprocess, "check_output", lambda *_args, **_kwargs: "a" * 40)
    monkeypatch.setattr(job.time, "sleep", lambda _seconds: None)

    class FinishedProcess:
        pid = 123
        args = ["synthetic-qualification"]

        def poll(self) -> int:
            return 0

        def wait(self) -> int:
            return 0

    def finished_child(_command: list[str], **kwargs: object) -> FinishedProcess:
        assert kwargs["start_new_session"] is False
        status_path = Path(str(kwargs["env"]["RES338_JOB_STATUS_PATH"]))
        status = json.loads(status_path.read_bytes())
        status["status"] = "COMPLETED"
        status_path.write_text(json.dumps(status))
        return FinishedProcess()

    monkeypatch.setattr(job.subprocess, "Popen", finished_child)
    result = job.execute()

    assert result["status"] == "COMPLETED"
    assert result["process_exit_code"] == 0
