"""RES614 adversarial synthetic tests for the resilient execution runner prototype."""

from __future__ import annotations

import ast
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "tools" / "res614_resilient_runner.py"
sys.path.insert(0, str(REPO / "tools"))

import res614_resilient_runner as r  # noqa: E402


def run_cli(*args: str, timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, os.fspath(TOOL), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def common(tmp: Path, name: str = "camp") -> list[str]:
    return ["--campaign-dir", str(tmp / name), "--ledger-dir", str(tmp / f"{name}.ledger")]


def start_worker(tmp: Path, *extra: str, name: str = "camp") -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, os.fspath(TOOL), "run", *common(tmp, name), *extra],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def wait_for(path: Path, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while not path.exists():
        assert time.monotonic() < deadline, f"timed out waiting for {path}"
        time.sleep(0.02)


def test_happy_path_completes_and_verifies(tmp_path: Path) -> None:
    done = run_cli("run", *common(tmp_path), "--matches", "3", "--windows-per-match", "5")
    assert done.returncode == r.EXIT_OK, done.stderr
    info = r.classify(tmp_path / "camp")
    assert info["state"] == "COMPLETED"
    assert info["sealed_matches"] == [0, 1, 2]
    assert r.verify_completed(tmp_path / "camp")
    assert oct((tmp_path / "camp" / "campaign-result.json").stat().st_mode & 0o777) == "0o600"
    assert not info["stray_tmp_files"]


def test_duplicate_scope_is_refused_even_after_directory_removal(tmp_path: Path) -> None:
    args = ["run", *common(tmp_path), "--matches", "2", "--windows-per-match", "3"]
    assert run_cli(*args).returncode == r.EXIT_OK
    again = run_cli(*args)
    assert again.returncode == r.EXIT_DUPLICATE
    assert "already consumed" in again.stderr or "already populated" in again.stderr
    # Deleting the campaign directory must not reset the one-shot ledger.
    import shutil

    shutil.rmtree(tmp_path / "camp")
    assert run_cli(*args).returncode == r.EXIT_DUPLICATE


def test_concurrent_starts_allow_exactly_one_execution(tmp_path: Path) -> None:
    extra = ("--matches", "2", "--windows-per-match", "20", "--window-delay-s", "0.02")
    # Same scope, different campaign directories, shared ledger directory.
    ledger = ["--ledger-dir", str(tmp_path / "shared-ledger")]
    outs = [
        subprocess.Popen(
            [
                sys.executable,
                os.fspath(TOOL),
                "run",
                "--campaign-dir",
                str(tmp_path / f"race{i}"),
                *ledger,
                *extra,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for i in range(4)
    ]
    codes = sorted(p.wait(timeout=30) for p in outs)
    assert codes.count(r.EXIT_OK) == 1
    assert codes.count(r.EXIT_DUPLICATE) == 3


def test_historical_scope_and_private_paths_are_refused(tmp_path: Path) -> None:
    refused = run_cli("run", "--campaign-dir", "/srv/fpdbench-private/evidence/x")
    assert refused.returncode == r.EXIT_BAD_INPUT
    assert not Path("/srv/fpdbench-private/evidence/x").exists()
    named = run_cli("run", "--campaign-dir", str(tmp_path / "res594-amended-heldout"))
    assert named.returncode == r.EXIT_BAD_INPUT
    cfg = r.Config()
    assert cfg.scope_sha256() != r.HISTORICAL_SCOPE_SHA256
    monkey = r.Config.scope_sha256
    try:
        r.Config.scope_sha256 = lambda self: r.HISTORICAL_SCOPE_SHA256  # type: ignore[method-assign]
        with pytest.raises(PermissionError):
            r.consume_scope(tmp_path / "led", cfg, tmp_path / "c")
    finally:
        r.Config.scope_sha256 = monkey  # type: ignore[method-assign]


def test_sigterm_is_graceful_attributed_and_leaves_sealed_prefix(tmp_path: Path) -> None:
    worker = start_worker(
        tmp_path, "--matches", "4", "--windows-per-match", "10", "--window-delay-s", "0.05"
    )
    wait_for(tmp_path / "camp" / "receipts" / "match-0.json")
    os.kill(worker.pid, signal.SIGTERM)
    assert worker.wait(timeout=10) == r.EXIT_INTERRUPTED
    doc = json.loads((tmp_path / "camp" / ".interrupted.json").read_text())
    assert doc["status"] == "INTERRUPTED" and doc["retry_allowed"] is False
    event = doc["signal_events"][0]
    assert event["signal"] == "SIGTERM"
    assert event["sender_pid"] == os.getpid(), "sender must be attributed to the test process"
    assert event["sender_uid"] == os.getuid()
    info = r.classify(tmp_path / "camp")
    assert info["state"] == "INTERRUPTED"
    assert info["sealed_matches"] and info["missing_matches"]
    assert info["partial_results_are_scientifically_usable"] is False
    assert not (tmp_path / "camp" / "campaign-result.json").exists()
    # No automatic resume: a second start is refused by the consumed ledger.
    again = run_cli("run", *common(tmp_path), "--matches", "4", "--windows-per-match", "10")
    assert again.returncode == r.EXIT_DUPLICATE


def test_bounded_shutdown_forces_exit_when_window_overruns_grace(tmp_path: Path) -> None:
    worker = start_worker(
        tmp_path,
        "--matches",
        "2",
        "--windows-per-match",
        "5",
        "--window-delay-s",
        "30",
        "--grace-s",
        "0.4",
    )
    wait_for(tmp_path / "camp" / r.MARKER)
    time.sleep(0.3)
    started = time.monotonic()
    os.kill(worker.pid, signal.SIGTERM)
    assert worker.wait(timeout=10) == r.EXIT_WATCHDOG
    assert time.monotonic() - started < 5, "shutdown must be bounded by the grace period"
    doc = json.loads((tmp_path / "camp" / ".interrupted.json").read_text())
    assert doc["watchdog_forced"] is True


def test_sigkill_leaves_no_false_completion_and_is_classified(tmp_path: Path) -> None:
    worker = start_worker(
        tmp_path, "--matches", "4", "--windows-per-match", "10", "--window-delay-s", "0.05"
    )
    wait_for(tmp_path / "camp" / "receipts" / "match-1.json")
    os.kill(worker.pid, signal.SIGKILL)
    assert worker.wait(timeout=10) == -signal.SIGKILL
    info = r.classify(tmp_path / "camp")
    assert info["state"] == "CRASHED_OR_KILLED"
    assert info["sealed_matches"][:2] == [0, 1]
    assert not (tmp_path / "camp" / "campaign-result.json").exists()
    assert run_cli("run", *common(tmp_path)).returncode == r.EXIT_DUPLICATE


def test_injected_crash_between_windows_keeps_durable_telemetry(tmp_path: Path) -> None:
    done = run_cli(
        "run",
        *common(tmp_path),
        "--matches",
        "3",
        "--windows-per-match",
        "10",
        "--crash-after-windows",
        "17",
        "--telemetry-every",
        "5",
    )
    assert done.returncode == r.EXIT_CRASH_INJECTED
    lines = (tmp_path / "camp" / "telemetry.jsonl").read_text().splitlines()
    assert [json.loads(line)["windows_done"] for line in lines] == [5, 10, 15]
    assert r.classify(tmp_path / "camp")["sealed_matches"] == [0]


def test_torn_write_never_becomes_a_receipt(tmp_path: Path) -> None:
    done = run_cli(
        "run",
        *common(tmp_path),
        "--matches",
        "3",
        "--windows-per-match",
        "4",
        "--torn-write-at-match",
        "1",
    )
    assert done.returncode == r.EXIT_CRASH_INJECTED
    info = r.classify(tmp_path / "camp")
    assert info["sealed_matches"] == [0]
    assert info["stray_tmp_files"], "torn temporary file must be surfaced, never trusted"
    assert info["state"] == "CRASHED_OR_KILLED"


@pytest.mark.parametrize(
    ("flag", "value", "reason"),
    [
        ("--wall-limit-s", "0.2", "wall-time"),
        ("--cpu-limit-s", "0.0", "CPU-time"),
        ("--rss-limit-bytes", "1", "RSS"),
    ],
)
def test_resource_ceilings_stop_with_failure_marker(
    tmp_path: Path, flag: str, value: str, reason: str
) -> None:
    done = run_cli(
        "run",
        *common(tmp_path),
        "--matches",
        "2",
        "--windows-per-match",
        "50",
        "--window-delay-s",
        "0.05",
        flag,
        value,
    )
    assert done.returncode == r.EXIT_FAILED
    doc = json.loads((tmp_path / "camp" / ".failed.json").read_text())
    assert reason in doc["reason"] and doc["retry_allowed"] is False
    assert r.classify(tmp_path / "camp")["state"] == "FAILED"


def test_tampered_receipt_chain_is_detected(tmp_path: Path) -> None:
    assert (
        run_cli("run", *common(tmp_path), "--matches", "3", "--windows-per-match", "3").returncode
        == 0
    )
    receipt = tmp_path / "camp" / "receipts" / "match-1.json"
    doc = json.loads(receipt.read_text())
    doc["mean_score"] = 0.123456
    receipt.write_text(json.dumps(doc))
    info = r.classify(tmp_path / "camp")
    assert info["state"] == "CORRUPT"
    assert any("match-1" in problem for problem in info["problems"])
    assert not r.verify_completed(tmp_path / "camp")


def test_missing_middle_receipt_is_a_partial_gap(tmp_path: Path) -> None:
    assert (
        run_cli("run", *common(tmp_path), "--matches", "3", "--windows-per-match", "3").returncode
        == 0
    )
    (tmp_path / "camp" / "receipts" / "match-1.json").unlink()
    info = r.classify(tmp_path / "camp")
    assert info["missing_matches"] == [1, 2]
    assert not r.verify_completed(tmp_path / "camp")


def test_supervisor_enforces_hard_timeout_and_records_the_sender(tmp_path: Path) -> None:
    done = run_cli(
        "supervise",
        *common(tmp_path),
        "--matches",
        "2",
        "--windows-per-match",
        "100",
        "--window-delay-s",
        "0.05",
        "--hard-timeout-s",
        "0.6",
        "--grace-s",
        "2",
    )
    assert done.returncode == 0, done.stderr
    sup = json.loads((tmp_path / "camp.supervisor" / "supervisor.json").read_text())
    assert sup["terminated_by"] == "supervisor_timeout_sigterm"
    assert sup["worker_returncode"] == r.EXIT_INTERRUPTED
    doc = json.loads((tmp_path / "camp" / ".interrupted.json").read_text())
    assert doc["signal_events"][0]["sender_pid"] == sup["supervisor_pid"]


def test_supervisor_sigkills_a_worker_that_ignores_sigterm(tmp_path: Path) -> None:
    done = run_cli(
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
        "--grace-s",
        "0.5",
        "--ignore-sigterm",
    )
    assert done.returncode == 0
    sup = json.loads((tmp_path / "camp.supervisor" / "supervisor.json").read_text())
    assert sup["terminated_by"] == "supervisor_timeout_sigkill_after_grace"
    assert sup["worker_signal"] == "SIGKILL"
    assert r.classify(tmp_path / "camp")["state"] == "CRASHED_OR_KILLED"


def test_detached_launch_survives_launcher_exit_and_new_session(tmp_path: Path) -> None:
    out = run_cli(
        "launch",
        *common(tmp_path),
        "--matches",
        "2",
        "--windows-per-match",
        "10",
        "--window-delay-s",
        "0.02",
    )
    assert out.returncode == 0
    supervisor_pid = json.loads(out.stdout)["supervisor_pid"]
    # The launcher has exited; supervision continues in its own session.
    assert os.getsid(supervisor_pid) == supervisor_pid
    wait_for(tmp_path / "camp" / "campaign-result.json", timeout=20)
    assert r.verify_completed(tmp_path / "camp")
    wait_for(tmp_path / "camp.supervisor" / "supervisor.json")
    sup = json.loads((tmp_path / "camp.supervisor" / "supervisor.json").read_text())
    assert sup["worker_returncode"] == 0 and sup["terminated_by"] == "none"


def test_supervisor_survives_sighup_of_its_session(tmp_path: Path) -> None:
    out = run_cli(
        "launch",
        *common(tmp_path),
        "--matches",
        "2",
        "--windows-per-match",
        "10",
        "--window-delay-s",
        "0.03",
    )
    supervisor_pid = json.loads(out.stdout)["supervisor_pid"]
    time.sleep(0.15)
    os.kill(supervisor_pid, signal.SIGHUP)  # terminal-teardown analogue
    wait_for(tmp_path / "camp" / "campaign-result.json", timeout=20)
    assert r.verify_completed(tmp_path / "camp")


def test_atomic_write_is_all_or_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "doc.json"
    r.atomic_write(target, b"old")

    def boom(*_: object) -> None:
        raise OSError("rename failed")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        r.atomic_write(target, b"new")
    assert target.read_bytes() == b"old"
    assert not list(tmp_path.glob(".*.tmp"))


def test_runner_has_no_real_scorer_or_data_dependencies() -> None:
    tree = ast.parse(TOOL.read_text())
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add(node.module or "")
    assert not any(m.startswith(("fpdbench", "torch", "numpy")) for m in modules)
    text = TOOL.read_text()
    assert "torch.load" not in text and "amended_heldout" not in text
