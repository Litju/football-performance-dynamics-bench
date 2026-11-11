"""Real process faults on invented data; no private or historical input access."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    res635_execution as e,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    res635_post_failure_evaluation as s,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    res635_verification as v,
)


def wait_file(path, timeout=30):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if path.exists():
            return e.read(path)
        time.sleep(0.05)
    raise AssertionError(f"timeout waiting for {path}; log: {list(path.parent.glob('*'))}")


def run(root, output, **kwargs):
    e.launch(root, output, 1, **kwargs)
    return wait_file(output / "status.json")


def test_detached_completion_and_replay_refusal(tmp_path):
    root, output = tmp_path / "ledger", tmp_path / "output"
    # A short-lived launcher exits; its detached supervisor and isolated worker complete.
    launcher = subprocess.run(
        [
            sys.executable,
            "-m",
            e.MODULE,
            "start",
            "--ledger-root",
            str(root),
            "--output",
            str(output),
            "--count",
            "1",
        ],
        capture_output=True,
        timeout=20,
    )
    assert launcher.returncode == 0, launcher.stderr
    status = wait_file(output / "status.json")
    assert status["exit_code"] == 0, (output / "supervisor.log").read_text()
    manifest = e.verify_complete(root, output, 1)
    assert manifest["aggregate"]["records"] == 72
    record = e.bound_record(root, output, 1)
    assert 0 < record["cpu_used"] < 600
    assert 0 < record["wall_used"] < 900
    assert (root.stat().st_mode & 0o777) == 0o700
    assert (output / "telemetry.jsonl").stat().st_size > 0
    with pytest.raises(FileExistsError):
        e.reserve(root, tmp_path / "other-output", 1, False)
    with pytest.raises(ValueError):
        e.continue_campaign(root, output, 1)
    assert e.bound_record(root, output, 1)["status"] == "COMPLETED_VERIFIED"
    receipt = output / "match-0.json"
    body = e.read(receipt)
    body["records"][0]["strata"]["all"]["metrics"]["ade_m"] += 1
    e.atomic(receipt, body)
    with pytest.raises(ValueError):
        e.verify_complete(root, output, 1)


def test_controlled_sigterm_boundary_continuation_bitwise(tmp_path):
    root, output = tmp_path / "ledger", tmp_path / "continued"
    status = run(root, output, continuation=True, pause=0, wall_limit=12)
    assert status == {"status": "CONTINUATION_READY_SAME_SCOPE", "exit_code": 143}, (
        output / "supervisor.log"
    ).read_text()
    terminal = e.read(output / "worker-terminal.json")
    processes = e.read(output / "processes.json")
    assert terminal["signals"][0]["sender_pid"] == processes["supervisor_pid"]
    first_receipt = (output / "match-0.json").read_bytes()
    status = run(root, output, resume=True)
    assert status["exit_code"] == 0, (output / "supervisor.log").read_text()
    assert (output / "match-0.json").read_bytes() == first_receipt
    uninterrupted = tmp_path / "uninterrupted"
    assert run(tmp_path / "second-ledger", uninterrupted)["exit_code"] == 0
    for i in range(4):
        assert (output / f"match-{i}.json").read_bytes() == (
            uninterrupted / f"match-{i}.json"
        ).read_bytes()
    assert (
        e.verify_complete(root, output, 1)["aggregate"]
        == e.verify_complete(tmp_path / "second-ledger", uninterrupted, 1)["aggregate"]
    )
    assert e.bound_record(root, output, 1)["attempt"] == 1


def test_unexpected_sigkill_has_supervisor_evidence(tmp_path):
    root, output = tmp_path / "ledger", tmp_path / "killed"
    e.launch(root, output, 1, continuation=True, pause=0)
    boundary = wait_file(output / "boundary.json")
    assert e.bound_record(root, output, 1)["status"] == "RUNNING"
    os.kill(boundary["pid"], signal.SIGKILL)
    status = wait_file(output / "status.json")
    assert status["status"] == "CONTINUATION_READY_SAME_SCOPE"
    assert not (output / "worker-terminal.json").exists()
    record = e.bound_record(root, output, 1)
    attestation = e.authenticated(output / "postmortem.json", record["key"])
    assert attestation["wait_returncode"] == -signal.SIGKILL
    e.continue_campaign(root, output, 1)
    with pytest.raises(ValueError):
        e.continue_campaign(root, output, 1)


def test_unknown_sigterm_is_permanent(tmp_path):
    root, output = tmp_path / "ledger", tmp_path / "unknown"
    e.launch(root, output, 1, continuation=True, pause=0)
    boundary = wait_file(output / "boundary.json")
    os.kill(boundary["pid"], signal.SIGTERM)
    status = wait_file(output / "status.json")
    assert status["status"] == "FAILED_PERMANENTLY"
    with pytest.raises(ValueError):
        e.continue_campaign(root, output, 1)
    assert not (output / "result.json").exists()


def test_supervisor_loss_kills_worker_and_refuses_continuation(tmp_path):
    root, output = tmp_path / "ledger", tmp_path / "lost"
    e.launch(root, output, 1, continuation=True, pause=0)
    boundary = wait_file(output / "boundary.json")
    processes = e.read(output / "processes.json")
    os.kill(processes["supervisor_pid"], signal.SIGKILL)
    end = time.monotonic() + 5
    while time.monotonic() < end:
        try:
            state = Path(f"/proc/{boundary['pid']}/stat").read_text().rsplit(")", 1)[1].split()[0]
        except FileNotFoundError:
            break
        if state == "Z":
            break
        time.sleep(0.05)
    else:
        raise AssertionError("worker survived supervisor loss")
    assert not (output / "result.json").exists()
    assert not (output / "postmortem.json").exists()
    with pytest.raises(ValueError):
        e.continue_campaign(root, output, 1)


@pytest.fixture(scope="module")
def prefix():
    return s.score_match(s.MATCHES[0], 1, s.models())


def interrupted_fixture(tmp_path, prefix):
    root, output = tmp_path / "ledger", tmp_path / "output"
    record = e.reserve(root, output, 1, True)
    receipt = {**prefix, "scope_sha256": record["scope_sha256"], "previous_sha256": "0" * 64}
    e.atomic(output / "match-0.json", receipt)
    record.update(
        status="CONTINUATION_READY_SAME_SCOPE",
        seals=[s.digest(receipt)],
        cpu_used=1.0,
        wall_used=1.0,
    )
    e.store_ledger(root, 1, record)
    attestation = {
        "scope_sha256": record["scope_sha256"],
        "output": record["output"],
        "seals": record["seals"],
        "cpu_used": 1.0,
        "wall_used": 1.0,
        "attempt": 0,
        "protocol_sha256": s.PROTOCOL_SHA256,
        "outcome_accessed": False,
        "reason": "EXIT",
        "wait_returncode": -signal.SIGKILL,
    }
    e.atomic(output / "postmortem.json", e.signed(attestation, record["key"]))
    return root, output, record, attestation


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "forged",
        "oom_without_host_evidence",
        "host_loss_without_attestation",
        "peeked",
        "scientific",
        "cpu",
        "wall",
        "receipt",
        "parity",
        "missing_receipt",
        "duplicate",
    ],
)
def test_adversarial_continuations_fail_permanently(tmp_path, prefix, fault):
    root, output, record, attestation = interrupted_fixture(tmp_path, prefix)
    if fault == "missing":
        (output / "postmortem.json").unlink()
    elif fault == "forged":
        e.atomic(output / "postmortem.json", e.signed(attestation, "00" * 32))
    elif fault in ("oom_without_host_evidence", "host_loss_without_attestation", "scientific"):
        attestation["reason"] = fault
        e.atomic(output / "postmortem.json", e.signed(attestation, record["key"]))
    elif fault == "peeked":
        attestation["outcome_accessed"] = True
        e.atomic(output / "postmortem.json", e.signed(attestation, record["key"]))
    elif fault in ("cpu", "wall"):
        record[f"{fault}_used"] = 599.0 if fault == "cpu" else 899.0
        attestation[f"{fault}_used"] = record[f"{fault}_used"]
        e.store_ledger(root, 1, record)
        e.atomic(output / "postmortem.json", e.signed(attestation, record["key"]))
    elif fault == "missing_receipt":
        (output / "match-0.json").unlink()
    elif fault == "duplicate":
        e.atomic(output / "match-1.json", e.read(output / "match-0.json"))
    else:
        receipt = e.read(output / "match-0.json")
        receipt["records"][0]["strata"]["all"]["metrics"]["ade_m"] += 1
        e.atomic(output / "match-0.json", receipt)
        if fault == "parity":
            record["seals"] = [s.digest(receipt)]
            attestation["seals"] = record["seals"]
            e.store_ledger(root, 1, record)
            e.atomic(output / "postmortem.json", e.signed(attestation, record["key"]))
    with pytest.raises((ValueError, OSError)):
        e.continue_campaign(root, output, 1)
    assert e.bound_record(root, output, 1)["status"] == "FAILED_PERMANENTLY"
    assert not (output / "result.json").exists()


@pytest.mark.parametrize("fragment", ["res594-scope", "fpdbench-private", "checkpoints", "heldout"])
def test_forbidden_paths_and_ledger_aliases(tmp_path, fragment):
    with pytest.raises(PermissionError):
        e.safe_path(tmp_path / fragment)
    with pytest.raises(PermissionError):
        e.private_root(tmp_path / "output" / "ledger", tmp_path / "output")
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target)
    with pytest.raises(PermissionError):
        e.safe_path(link)


@pytest.mark.parametrize(
    "ceiling,value", [("wall_s", 0.001), ("cpu_s", 0.001), ("rss_bytes", 1), ("disk_bytes", 1)]
)
def test_resource_ceiling_is_terminal(tmp_path, ceiling, value):
    root, output = tmp_path / "ledger", tmp_path / "output"
    record = e.reserve(root, output, 1, True)
    record["budget"] = {**e.BUDGET, ceiling: value}
    e.store_ledger(root, 1, record)
    supervised = subprocess.run(
        [
            sys.executable,
            "-m",
            e.MODULE,
            "_supervise",
            "--output",
            str(output),
            "--ledger-root",
            str(root),
            "--count",
            "1",
        ],
        timeout=30,
    )
    assert supervised.returncode == e.EXIT_BUDGET
    assert e.bound_record(root, output, 1)["status"] == "FAILED_PERMANENTLY"


@pytest.mark.parametrize(
    "option,value",
    [
        ("--authorization", "RES594-GO"),
        ("--scope", "d359751e969767f30ed6e90c65b13d0eec49f11c9e33e1d2319b19530d28f2e0"),
        ("--checkpoint", "private.pt"),
        ("--source", "snapshot.jsonl"),
    ],
)
def test_cli_has_no_real_authority_or_input_options(monkeypatch, tmp_path, option, value):
    monkeypatch.setattr(
        sys, "argv", ["fpdbench-res635", "start", "--output", str(tmp_path), option, value]
    )
    with pytest.raises(SystemExit) as exc:
        e.main()
    assert exc.value.code == 2


def test_new_modules_do_not_import_or_execute_historical_scorer():
    import ast

    for module in (e, s, v):
        source = Path(module.__file__).read_text()
        tree = ast.parse(source)
        imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        assert not any(
            "amended_heldout_evaluation" in name or "protected_skillcorner" in name
            for name in imports
        )
        assert "torch.load(" not in source
        assert "load_checkpoint_verified(" not in source
