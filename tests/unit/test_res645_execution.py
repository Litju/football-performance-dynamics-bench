"""RES645 execution boundary: SIGKILL is an observation, never a permission."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import Any

import pytest

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    res635_execution as e,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    res635_post_failure_evaluation as s,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    res645_evidence as ev,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    res645_fixtures as fx,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    res645_workloads as wl,
)


def wait_file(path: Path, timeout: float = 240) -> dict[str, Any]:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if path.exists():
            return e.read(path)
        time.sleep(0.05)
    raise AssertionError(f"timeout waiting for {path}")


def cli(action: str, root: Path, output: Path, bundle: Path, count: int, *extra: str):
    return subprocess.run(
        [
            sys.executable,
            "-m",
            e.MODULE,
            action,
            "--ledger-root",
            str(root),
            "--output",
            str(output),
            "--count",
            str(count),
            "--fixture-bundle",
            str(bundle),
            *extra,
        ],
        capture_output=True,
        timeout=240,
        check=False,
    )


@pytest.fixture(scope="module")
def bundle(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return fx.build_bundle(tmp_path_factory.mktemp("res645exec") / "bundle")


@pytest.fixture(scope="module")
def workload(bundle: Path) -> wl.FixtureWorkload:
    return wl.FixtureWorkload(bundle)


@pytest.fixture(scope="module")
def uninterrupted(
    tmp_path_factory: pytest.TempPathFactory, bundle: Path, workload: wl.FixtureWorkload
):
    base = tmp_path_factory.mktemp("uninterrupted")
    root, output = base / "ledger", base / "output"
    started = cli("start", root, output, bundle, workload.windows)
    assert started.returncode == 0, started.stderr
    status = wait_file(output / "status.json")
    assert status["exit_code"] == 0, (output / "supervisor.log").read_text()
    return root, output


def test_production_path_campaign_completes_and_verifies(
    uninterrupted: tuple[Path, Path], bundle: Path, workload: wl.FixtureWorkload
) -> None:
    root, output = uninterrupted
    for action in ("status", "verify"):
        result = cli(action, root, output, bundle, workload.windows)
        assert result.returncode == 0, (result.stdout, result.stderr)
    verified = cli("verify", root, output, bundle, workload.windows)
    assert verified.returncode == 0, (verified.stdout, verified.stderr)
    assert json.loads(verified.stdout)["records"] == 72
    manifest = e.verify_complete(root, output, workload.windows, workload=workload)
    assert manifest["aggregate"]["records"] == 72
    record = e.bound_record(root, output, workload.windows, workload=workload)
    assert record["namespace"] == wl.FIXTURE_NAMESPACE and record["status"] == "COMPLETED_VERIFIED"
    assert 0 < record["cpu_used"] < record["budget"]["cpu_s"]
    assert 0 < record["wall_used"] < record["budget"]["wall_s"]
    # The supervised scorer equals a direct in-process run of the same workload.
    prepared = workload.prepare()
    for i in range(4):
        direct = workload.score(i, workload.windows, prepared, lambda: None)
        sealed = e.read(output / f"match-{i}.json")
        assert s.canonical(
            {k: v for k, v in sealed.items() if k not in ("scope_sha256", "previous_sha256")}
        ) == s.canonical(direct)
    assert (output / "result.json").exists() and not list(output.glob("*.tmp"))


def test_completed_bundle_tamper_and_scope_reuse_are_refused(
    uninterrupted: tuple[Path, Path], bundle: Path, workload: wl.FixtureWorkload, tmp_path: Path
) -> None:
    root, output = uninterrupted
    copy = tmp_path / "copy"
    shutil.copytree(output, copy)
    target = copy / "match-2.json"
    receipt = e.read(target)
    receipt["records"][5]["strata"]["all"]["metrics"]["xy_rmse_m"] += 1e-9
    e.atomic(target, receipt)
    with pytest.raises(ValueError):
        workload.verify_prefix(
            copy, workload.windows, e.read(output / "result.json")["body"]["seals"]
        )
    with pytest.raises(FileExistsError):  # the one-shot scope cannot be reserved again
        e.reserve(root, tmp_path / "other", workload.windows, False, workload=workload)
    with pytest.raises(ValueError):
        e.continue_campaign(root, output, workload.windows, workload=workload)


def test_cli_exposes_no_real_source_or_checkpoint_inputs(tmp_path: Path, bundle: Path) -> None:
    help_text = subprocess.run(
        [sys.executable, "-m", e.MODULE, "--help"], capture_output=True, text=True, check=True
    ).stdout
    for forbidden in ("--source", "--checkpoint", "--authorization", "--manifest", "--snapshot"):
        assert forbidden not in help_text
    assert "--fixture-bundle" in help_text
    for victim in (tmp_path / "res594-bundle", tmp_path / "heldout"):
        shutil.copytree(bundle, victim)
        result = cli("start", tmp_path / "ledger", tmp_path / "out", victim, 24)
        assert result.returncode == e.EXIT_INTEGRITY and b"refused" in result.stderr.lower()
    empty = tmp_path / "empty"
    empty.mkdir(mode=0o700)
    assert cli("start", tmp_path / "l2", tmp_path / "o2", empty, 24).returncode == e.EXIT_INTEGRITY
    wrong_count = cli("start", tmp_path / "l3", tmp_path / "o3", bundle, 5)
    assert wrong_count.returncode == e.EXIT_INTEGRITY


# ------------------------------------------------------------------ cause evidence unit tests
def snap(**overrides: Any) -> dict[str, Any]:
    return {"available": True, "cgroup": "/x", "oom_kill": 0, "boot_id": "b" * 36, **overrides}


def assess(**overrides: Any):
    arguments = {
        "wait_returncode": -9,
        "supervisor_signals": 0,
        "worker_cpu_s": 1.0,
        "cpu_ceiling_s": 100.0,
    }
    after = overrides.pop("after", snap(oom_kill=1))
    before = overrides.pop("before", snap())
    return ev.assess(before, after, **{**arguments, **overrides})


def test_sigkill_status_alone_never_yields_evidence() -> None:
    assert assess() is None  # a shared counter never identifies the killed worker
    assert assess(after=snap(oom_kill=0)) is None  # counter unchanged
    assert assess(after=snap(oom_kill=0), wait_returncode=-9) is None
    assert assess(before={"available": False}) is None  # no kernel evidence available
    assert assess(after={"available": False}) is None
    assert assess(supervisor_signals=1) is None  # the supervisor itself escalated
    assert assess(worker_cpu_s=100.0) is None  # RLIMIT_CPU also delivers SIGKILL
    assert assess(wait_returncode=-15) is None
    assert assess(wait_returncode=137) is None
    assert assess(after=snap(oom_kill=1, boot_id="c" * 36)) is None  # different boot
    assert assess(after=snap(oom_kill=1, cgroup="/y")) is None  # different cgroup
    assert assess(before=snap(oom_kill=5), after=snap(oom_kill=3)) is None  # counter went backwards


def test_recorded_evidence_is_revalidated() -> None:
    assert not ev.valid_attestation(assess())
    assert not ev.valid_attestation({"kind": ev.KIND, "oom_kill_before": 0, "oom_kill_after": 1})


def test_kernel_cgroup_reader_is_truthful_or_unavailable(tmp_path: Path) -> None:
    live = ev.CgroupEvidence().snapshot(os.getpid())
    assert live["available"] is False or (type(live["oom_kill"]) is int and live["oom_kill"] >= 0)
    fake = tmp_path / "cg" / "job"
    fake.mkdir(parents=True)
    (fake / "memory.events").write_text("low 0\nhigh 0\nmax 0\noom 1\noom_kill 3\n")
    reader = ev.CgroupEvidence(tmp_path / "cg", "/job")
    assert reader.snapshot(os.getpid())["oom_kill"] == 3
    (fake / "memory.events").write_text("garbage")
    assert reader.snapshot(os.getpid())["available"] is False
    assert ev.CgroupEvidence(tmp_path / "missing", "/job").snapshot(1)["available"] is False


# -------------------------------------------------------------------- real SIGKILL scenarios
SUPERVISE = textwrap.dedent(
    """
    import sys
    from pathlib import Path
    from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
        res635_execution as e, res645_evidence as ev, res645_workloads as wl)
    root, output, count, fake, bundle = sys.argv[1:6]
    workload = wl.make(Path(bundle) if bundle != "-" else None)
    provider = ev.CgroupEvidence(Path(fake), "/job")
    raise SystemExit(e.supervise(Path(root), Path(output), int(count), 0, None,
                                 workload=workload, evidence=provider))
    """
)


def sigkill_with_counter(
    tmp_path: Path, name: str, count: int, bundle: Path | None, *, increment: bool, workload=None
) -> tuple[Path, Path, subprocess.CompletedProcess[bytes]]:
    root, output = tmp_path / f"{name}-ledger", tmp_path / f"{name}-output"
    fake = tmp_path / f"{name}-cg"
    (fake / "job").mkdir(parents=True)
    events = fake / "job" / "memory.events"
    events.write_text("oom 0\noom_kill 0\n")
    e.reserve(root, output, count, True, workload=workload)
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            SUPERVISE,
            str(root),
            str(output),
            str(count),
            str(fake),
            str(bundle) if bundle else "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    boundary = wait_file(output / "boundary.json")
    if increment:
        events.write_text("oom 1\noom_kill 1\n")  # kernel-owned counter in the fake cgroup
    os.kill(boundary["pid"], signal.SIGKILL)
    out, err = process.communicate(timeout=240)
    return root, output, subprocess.CompletedProcess(process.args, process.returncode, out, err)


def test_sigkill_without_counter_increase_is_permanent(tmp_path: Path) -> None:
    root, output, done = sigkill_with_counter(tmp_path, "bare", 1, None, increment=False)
    assert done.returncode == e.EXIT_WORKER, done.stderr
    assert e.read(output / "status.json")["status"] == "FAILED_PERMANENTLY"
    record = e.bound_record(root, output, 1)
    assert e.authenticated(output / "postmortem.json", record["key"])["cause_evidence"] is None
    with pytest.raises(ValueError):
        e.continue_campaign(root, output, 1)


def test_shared_cgroup_oom_and_unrelated_worker_kill_is_permanent(tmp_path: Path) -> None:
    root, output, done = sigkill_with_counter(tmp_path, "oom", 1, None, increment=True)
    assert done.returncode == e.EXIT_WORKER, done.stderr
    assert e.read(output / "status.json")["status"] == "FAILED_PERMANENTLY"
    record = e.bound_record(root, output, 1)
    assert e.authenticated(output / "postmortem.json", record["key"])["cause_evidence"] is None
    with pytest.raises(ValueError):
        e.continue_campaign(root, output, 1)


def test_sender_verified_continuation_is_bitwise_identical_on_the_production_path(
    tmp_path: Path, bundle: Path, workload: wl.FixtureWorkload, uninterrupted: tuple[Path, Path]
) -> None:
    root, output = tmp_path / "prod-ledger", tmp_path / "prod-output"
    e.launch(
        root, output, workload.windows, continuation=True, pause=0, wall_limit=30, workload=workload
    )
    assert wait_file(output / "status.json")["status"] == "CONTINUATION_READY_SAME_SCOPE"
    sealed = (output / "match-0.json").read_bytes()
    pid = e.launch(root, output, workload.windows, resume=True, workload=workload)
    assert pid > 0
    status = wait_file(output / "status.json")
    assert status["exit_code"] == 0, (output / "supervisor.log").read_text()
    assert (output / "match-0.json").read_bytes() == sealed
    reference = uninterrupted[1]
    for i in range(4):
        assert (output / f"match-{i}.json").read_bytes() == (
            reference / f"match-{i}.json"
        ).read_bytes()
    assert (
        e.verify_complete(root, output, workload.windows, workload=workload)["aggregate"]
        == e.verify_complete(uninterrupted[0], reference, workload.windows, workload=workload)[
            "aggregate"
        ]
    )
    record = e.bound_record(root, output, workload.windows, workload=workload)
    assert record["attempt"] == 1
    assert record["cpu_used"] > 0 and record["wall_used"] > 0  # cumulative across both attempts
    with pytest.raises(ValueError):  # at most one continuation, ever
        e.continue_campaign(root, output, workload.windows, workload=workload)


def test_scientific_failure_is_terminal_even_with_oom_evidence(tmp_path: Path) -> None:
    root, output = tmp_path / "ledger", tmp_path / "output"
    fake = tmp_path / "cg"
    (fake / "job").mkdir(parents=True)
    events = fake / "job" / "memory.events"
    events.write_text("oom_kill 0\n")
    e.reserve(root, output, 1, True)
    process = subprocess.Popen(
        [sys.executable, "-c", SUPERVISE, str(root), str(output), "1", str(fake), "-"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    boundary = wait_file(output / "boundary.json")
    e.atomic(output / "worker-terminal.json", {"status": "SCIENTIFIC_OR_INTEGRITY_FAILURE"})
    events.write_text("oom_kill 1\n")
    os.kill(boundary["pid"], signal.SIGKILL)
    process.communicate(timeout=240)
    assert e.read(output / "status.json") == {
        "status": "FAILED_PERMANENTLY",
        "exit_code": e.EXIT_INTEGRITY,
    }
    with pytest.raises(ValueError):
        e.continue_campaign(root, output, 1)


def test_consumed_res594_scope_and_real_ledger_aliases_stay_refused(
    tmp_path: Path, bundle: Path
) -> None:
    with pytest.raises(PermissionError):
        e.safe_path(tmp_path / "res594-consumed-scope")
    with pytest.raises(PermissionError):
        e.reserve(
            tmp_path / "ledger",
            tmp_path / "res594" / "out",
            24,
            False,
            workload=wl.FixtureWorkload(bundle),
        )
    assert e.PROTOCOL_SHA256 if hasattr(e, "PROTOCOL_SHA256") else True
    assert s.PROTOCOL_SHA256 == "ac931391ecb0afcb68974e1765f65fbff17071ade2bcaab93bdadd22f84a0305"
