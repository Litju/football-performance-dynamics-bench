"""RES614: supervisor/launcher terminal status must propagate to the invoking process."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "tools" / "res614_resilient_runner.py"
sys.path.insert(0, str(REPO / "tools"))

import res614_resilient_runner as r  # noqa: E402


def common(tmp: Path) -> list[str]:
    return ["--campaign-dir", str(tmp / "camp"), "--ledger-dir", str(tmp / "camp.ledger")]


def cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, os.fspath(TOOL), *args], capture_output=True, text=True, check=False
    )


def record(tmp: Path) -> dict[str, object]:
    return json.loads((tmp / "camp.supervisor" / "supervisor.json").read_text())


def test_verified_success_is_the_only_zero(tmp_path: Path) -> None:
    out = cli("supervise", *common(tmp_path), "--matches", "2", "--windows-per-match", "3")
    assert out.returncode == 0
    rec = record(tmp_path)
    assert rec["supervisor_status"] == "COMPLETED_VERIFIED" and rec["verification_problems"] == []
    assert cli("status", *common(tmp_path)).returncode == 0


def test_worker_crash_propagates_nonzero(tmp_path: Path) -> None:
    out = cli(
        "supervise",
        *common(tmp_path),
        "--matches",
        "3",
        "--windows-per-match",
        "5",
        "--crash-after-windows",
        "4",
    )
    assert out.returncode == r.EXIT_WORKER_FAILED
    assert record(tmp_path)["supervisor_status"] == "WORKER_FAILED"
    assert cli("status", *common(tmp_path)).returncode == r.EXIT_WORKER_FAILED


def test_worker_validation_refusal_propagates_nonzero(tmp_path: Path) -> None:
    first = cli("run", *common(tmp_path), "--matches", "2", "--windows-per-match", "2")
    assert first.returncode == 0
    # Same scope again: the worker refuses (duplicate) and the supervisor must not report success.
    out = cli("supervise", *common(tmp_path), "--matches", "2", "--windows-per-match", "2")
    assert out.returncode == r.EXIT_WORKER_FAILED
    assert record(tmp_path)["worker_returncode"] == r.EXIT_DUPLICATE


def test_timeout_propagates_nonzero_even_after_graceful_worker_exit(tmp_path: Path) -> None:
    out = cli(
        "supervise",
        *common(tmp_path),
        "--matches",
        "2",
        "--windows-per-match",
        "100",
        "--window-delay-s",
        "0.05",
        "--hard-timeout-s",
        "0.5",
    )
    assert out.returncode == r.EXIT_SUPERVISED_TIMEOUT
    assert record(tmp_path)["supervisor_status"] == "WORKER_TIMED_OUT"


def test_external_sigkill_of_worker_propagates_nonzero(tmp_path: Path) -> None:
    sup = subprocess.Popen(
        [
            sys.executable,
            os.fspath(TOOL),
            "supervise",
            *common(tmp_path),
            "--matches",
            "2",
            "--windows-per-match",
            "100",
            "--window-delay-s",
            "0.05",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    children = Path(f"/proc/{sup.pid}/task/{sup.pid}/children")
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not children.read_text().split():
        time.sleep(0.02)
    time.sleep(0.2)
    os.kill(int(children.read_text().split()[0]), signal.SIGKILL)
    assert sup.wait(timeout=20) == r.EXIT_WORKER_FAILED
    rec = record(tmp_path)
    assert rec["supervisor_status"] == "WORKER_KILLED" and rec["worker_signal"] == "SIGKILL"


def test_forged_completion_is_reported_unverified(tmp_path: Path) -> None:
    out = cli(
        "supervise",
        *common(tmp_path),
        "--matches",
        "3",
        "--windows-per-match",
        "3",
        "--fault-forge-empty-result",
    )
    assert out.returncode == r.EXIT_UNVERIFIED
    rec = record(tmp_path)
    assert rec["supervisor_status"] == "COMPLETION_UNVERIFIED" and rec["verification_problems"]


def test_status_without_record_is_not_success(tmp_path: Path) -> None:
    assert cli("status", *common(tmp_path)).returncode == r.EXIT_NOT_FINISHED


def test_launch_returns_zero_only_for_launch_and_status_gives_the_outcome(tmp_path: Path) -> None:
    out = cli(
        "launch",
        *common(tmp_path),
        "--matches",
        "2",
        "--windows-per-match",
        "50",
        "--crash-after-windows",
        "10",
        "--window-delay-s",
        "0.01",
    )
    assert out.returncode == 0 and json.loads(out.stdout)["launched_only"] is True
    deadline = time.monotonic() + 20
    while cli("status", *common(tmp_path)).returncode == r.EXIT_NOT_FINISHED:
        assert time.monotonic() < deadline
        time.sleep(0.1)
    assert cli("status", *common(tmp_path)).returncode == r.EXIT_WORKER_FAILED


def test_tampered_supervisor_record_cannot_launder_a_failed_campaign(tmp_path: Path) -> None:
    cli(
        "supervise",
        *common(tmp_path),
        "--matches",
        "3",
        "--windows-per-match",
        "5",
        "--crash-after-windows",
        "4",
    )
    path = tmp_path / "camp.supervisor" / "supervisor.json"
    rec = json.loads(path.read_text())
    rec["supervisor_status"] = "COMPLETED_VERIFIED"
    path.write_text(json.dumps(rec))  # stale record hash
    assert cli("status", *common(tmp_path)).returncode == r.EXIT_UNVERIFIED
    # Even with a recomputed record hash, status re-verifies the campaign itself.
    rec.pop("record_sha256")
    rec["record_sha256"] = hashlib.sha256(r.canonical(rec)).hexdigest()
    path.write_text(json.dumps(rec))
    assert cli("status", *common(tmp_path)).returncode == r.EXIT_UNVERIFIED
