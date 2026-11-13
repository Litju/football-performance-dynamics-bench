"""Only invented tracking, artificial checkpoints and ephemeral test signing keys."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from test_res646_authorization import build_auth, sign

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import res635_execution as e
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    res635_post_failure_evaluation as s,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import res645_fixtures as fx
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import res645_workloads as wl
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import res646_authorization as a
from fpdbench.data_sources import protected_skillcorner as protected
from fpdbench.data_sources.skillcorner import canonical_bytes


def write(path: Path, data: bytes) -> None:
    path.write_bytes(data)
    path.chmod(0o600)


def signed_campaign(base: Path, bundle: Path) -> Path:
    base.mkdir(mode=0o700)
    root, output = base / "ledger", base / "output"
    root.mkdir(mode=0o700)
    output.mkdir(mode=0o700)
    config = base / "campaign.json"
    write(
        config,
        canonical_bytes(
            {
                "schema": "fpdbench.res646.campaign/1",
                "namespace": a.SYNTHETIC,
                "fixture_bundle": str(bundle),
                "ledger_root": str(root),
                "output": str(output),
                "independent_report_sha256": "c" * 64,
            }
        ),
    )
    campaign = a.CampaignPlan(config)
    key = base / "synthetic-key"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
    signers = (
        a.PRINCIPAL.encode()
        + b" "
        + b" ".join(key.with_suffix(".pub").read_bytes().split()[:2])
        + b"\n"
    )
    auth = build_auth()
    auth.update(
        new_scope_sha256=campaign.scope,
        scorer_code_sha256=campaign.identities["scorer_sha256"],
        ledger_root_identity_sha256=campaign.identities["ledger_sha256"],
        independent_verifier_identity=campaign.identities["verifier_sha256"],
        independent_validation_report_sha256=campaign.identities["independent_report_sha256"],
        authorized_at_utc=(datetime.now(UTC) - timedelta(minutes=1))
        .isoformat()
        .replace("+00:00", "Z"),
    )
    body = {
        "schema": a.ENVELOPE,
        "namespace": a.SYNTHETIC,
        "authorization": auth,
        "identities": campaign.identities,
        "expires_at_utc": (datetime.now(UTC) + timedelta(hours=6))
        .isoformat()
        .replace("+00:00", "Z"),
        "key_fingerprint": next(iter(protected._signer_fingerprints(signers, a.PRINCIPAL))),
    }
    write(config.with_suffix(".approval.json"), canonical_bytes(body))
    write(config.with_suffix(".approval.sig"), sign(body, key))
    write(config.with_suffix(".synthetic-signers"), signers)
    return config


@pytest.fixture(scope="module")
def bundle(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return fx.build_bundle(tmp_path_factory.mktemp("res646-artificial") / "bundle", samples=42)


def wait(output: Path, timeout: int = 120) -> dict[str, Any]:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if (output / "status.json").exists():
            return e.read(output / "status.json")
        time.sleep(0.05)
    raise AssertionError((output / "supervisor.log").read_text())


def supervise(config: Path, workload: wl.RealWorkload) -> subprocess.CompletedProcess[str]:
    campaign = workload.campaign
    return subprocess.run(
        [
            sys.executable,
            "-m",
            e.MODULE,
            "_supervise",
            "--campaign-config",
            str(config),
            "--output",
            str(campaign.output),
            "--ledger-root",
            str(campaign.root),
            "--count",
            str(workload.windows),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_signed_campaign_and_single_pass_verification(
    tmp_path: Path,
    bundle: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = signed_campaign(tmp_path / "complete", bundle)
    workload = wl.RealWorkload(config)
    campaign = workload.campaign
    with pytest.raises((OSError, ValueError)):
        workload.prepare()
    e.reserve(campaign.root, campaign.output, workload.windows, True, workload=workload)
    with pytest.raises(PermissionError, match="direct or unreserved"):
        e.worker(campaign.output, workload.windows, 0, -1, workload, ledger_root=campaign.root)
    with pytest.raises(ValueError):
        e.reserve(campaign.root, campaign.output, workload.windows, True, workload=workload)
    done = supervise(config, workload)
    assert done.returncode == 0, (done.stdout, done.stderr)
    monkeypatch.setattr(
        wl.ck, "load_models", lambda *args, **kwargs: pytest.fail("second model load")
    )
    monkeypatch.setattr(wl.pipe, "predictions", lambda *args: pytest.fail("second inference"))
    manifest = e.verify_complete(
        campaign.root, campaign.output, workload.windows, workload=workload
    )
    assert manifest["aggregate"]["records"] == 72
    assert manifest["status"] == "COMPLETED_VERIFIED_SYNTHETIC_ONLY"
    ledger = campaign.record()
    assert len(ledger["seals"]) == 4
    for i in range(4):
        receipt = e.read(campaign.output / f"match-{i}.json")
        assert receipt["match"] == wl.v.EVALUATION_MATCHES[i]
        assert s.digest(receipt) == ledger["seals"][i]
    target = campaign.output / "match-2.json"
    saved = target.read_bytes()
    receipt = json.loads(saved)
    receipt["records"].pop()
    write(target, canonical_bytes(receipt))
    with pytest.raises(ValueError, match="seal"):
        e.verify_complete(campaign.root, campaign.output, workload.windows, workload=workload)
    write(target, saved)
    target.unlink()
    with pytest.raises(ValueError, match="prefix"):
        e.verify_complete(campaign.root, campaign.output, workload.windows, workload=workload)


def test_config_tampering_and_unsigned_campaign_fail_before_reservation(
    tmp_path: Path,
    bundle: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = signed_campaign(tmp_path / "tamper", bundle)
    original = config.read_bytes()
    value = json.loads(original)
    value["independent_report_sha256"] = "f" * 64
    write(config, canonical_bytes(value))
    with pytest.raises(ValueError, match="identities"):
        wl.RealWorkload(config)
    write(config, original)
    config.with_suffix(".approval.sig").unlink()
    with pytest.raises(OSError):
        wl.RealWorkload(config)
    assert not list((config.parent / "ledger").iterdir())


def test_signed_interruption_continues_without_model_replay(
    tmp_path: Path,
    bundle: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = signed_campaign(tmp_path / "interrupted", bundle)
    workload = wl.RealWorkload(config)
    campaign = workload.campaign
    e.launch(
        campaign.root,
        campaign.output,
        workload.windows,
        continuation=True,
        pause=0,
        wall_limit=15,
        workload=workload,
    )
    assert wait(campaign.output)["status"] == "CONTINUATION_READY_SAME_SCOPE"
    sealed = (campaign.output / "match-0.json").read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(workload, "prepare", lambda: pytest.fail("continuation model replay"))
        e.continue_campaign(campaign.root, campaign.output, workload.windows, workload=workload)
    done = supervise(config, workload)
    assert done.returncode == 0, done.stderr
    assert (campaign.output / "match-0.json").read_bytes() == sealed
    assert (
        e.verify_complete(campaign.root, campaign.output, workload.windows, workload=workload)[
            "aggregate"
        ]["records"]
        == 72
    )
    with pytest.raises(ValueError):
        e.continue_campaign(campaign.root, campaign.output, workload.windows, workload=workload)


def test_crash_after_exclusive_reservation_cannot_replay(
    tmp_path: Path,
    bundle: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = signed_campaign(tmp_path / "crash", bundle)
    workload = wl.RealWorkload(config)
    campaign = workload.campaign
    with monkeypatch.context() as patch:
        patch.setattr(e, "atomic", lambda *args: (_ for _ in ()).throw(OSError("synthetic crash")))
        with pytest.raises(OSError, match="synthetic crash"):
            e.reserve(campaign.root, campaign.output, workload.windows, True, workload=workload)
    assert campaign.record()["status"] == "RESERVED"
    with pytest.raises(FileExistsError):
        e.reserve(campaign.root, campaign.output, workload.windows, True, workload=workload)


@pytest.mark.parametrize("resource_name", ["cpu_s", "rss_bytes", "disk_bytes"])
def test_signed_resource_exhaustion_is_terminal(
    tmp_path: Path,
    bundle: Path,
    monkeypatch: pytest.MonkeyPatch,
    resource_name: str,
) -> None:
    config = signed_campaign(tmp_path / resource_name, bundle)
    workload = wl.RealWorkload(config)
    campaign = workload.campaign
    # A stricter ceiling is permitted; raising the frozen ceiling is never permitted.
    with monkeypatch.context() as patch:
        patch.setattr(e, "REAL_BUDGET", {**e.REAL_BUDGET, resource_name: 1})
        e.reserve(campaign.root, campaign.output, workload.windows, True, workload=workload)
    done = supervise(config, workload)
    assert done.returncode == e.EXIT_BUDGET, done.stderr
    assert campaign.record()["status"] == "FAILED_PERMANENTLY"
    assert not (campaign.output / "result.json").exists()
    with pytest.raises(ValueError):
        e.continue_campaign(campaign.root, campaign.output, workload.windows, workload=workload)


def test_every_entrypoint_requires_signed_authority(
    tmp_path: Path,
    bundle: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = signed_campaign(tmp_path / "unsigned", bundle)
    campaign = a.Campaign(config)
    config.with_suffix(".approval.sig").unlink()
    for action in ("start", "_supervise", "_worker", "continue", "verify", "status"):
        done = subprocess.run(
            [
                sys.executable,
                "-m",
                e.MODULE,
                action,
                "--campaign-config",
                str(config),
                "--output",
                str(campaign.output),
                "--ledger-root",
                str(campaign.root),
                "--count",
                str(sum(campaign.declared)),
            ],
            capture_output=True,
            timeout=30,
        )
        assert done.returncode != 0
    assert not list(campaign.root.iterdir())
    assert not list(campaign.output.iterdir())


def test_independent_features_and_one_prediction_pass(bundle: Path) -> None:
    fixture = wl.FixtureWorkload(bundle)
    frozen = fixture.prepare()
    spec = fixture.specs[0]
    match = wl.src.SourceMatch(spec, "synthetic")
    match.prepare()
    calls = []
    hooks = [m.register_forward_hook(lambda *args: calls.append(1)) for m in frozen.models.values()]
    try:
        receipt = wl.pipe.score_stream(
            spec.label,
            spec.match_id,
            match.windows(),
            frozen,
            fixture.declared[0],
            source_audit=wl.ind.SourcePredictionAudit(spec.directory, spec.label, spec.locked_path),
        )
    finally:
        for hook in hooks:
            hook.remove()
    assert len(calls) == 18 * fixture.declared[0]
    assert receipt["independent_audit"]["records"] == receipt["records"] or (
        s.digest(receipt["independent_audit"]["records"]) == receipt["independent_records_sha256"]
    )


@pytest.mark.parametrize("samples", [60, 240])
def test_long_fixture_preserves_frozen_panels_and_clock(tmp_path: Path, samples: int) -> None:
    for index in range(4):
        directory = tmp_path / f"match-{index}"
        fx.build_match(directory, index, samples)
        spec = wl.src.SourceMatchSpec(
            f"synthetic-match-{index}", fx.FIXTURE_MATCH_IDS[index], directory
        )
        source = wl.src.SourceMatch(spec, "synthetic")
        source.prepare()
        count = 0
        for window in source.windows():
            count += 1
            assert all(len(scene["player_ids"]) == 11 for scene in window["scenes"])
        assert count == samples - 40


def test_frozen_loaders_refuse_duck_typed_authority_before_input_open(
    bundle: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = fx.read_bundle(bundle)[0][0]
    fake = SimpleNamespace(
        allow_source=lambda *args: None,
        allow_models=lambda *args: None,
        allow_input=lambda *args: None,
    )
    manifest = wl.ck.frozen_manifest()
    records = wl.ck.validate_records(manifest)
    cell = next(iter(records))
    with monkeypatch.context() as patch:
        patch.setattr(
            wl.paths, "read_regular_file", lambda *args, **kwargs: pytest.fail("input opened")
        )
        with pytest.raises(PermissionError, match="Campaign authority"):
            wl.src.SourceMatch(spec, "frozen", fake)
        with pytest.raises(PermissionError, match="Campaign authority"):
            wl.ck.load_models(
                manifest, bundle / "checkpoints", "frozen", bundle / "receipts", campaign=fake
            )
        with pytest.raises(PermissionError, match="Campaign authority"):
            wl.ck.load_checkpoint(bundle / "fake.pt", records[cell], cell, campaign=fake)
    with pytest.raises(PermissionError, match="Campaign authority"):
        wl.paths.read_regular_file(bundle / "metadata.json", max_bytes=100, campaign=fake)


def test_worker_and_supervisor_reject_namespace_impersonation(tmp_path: Path) -> None:
    root, output = tmp_path / "ledger", tmp_path / "output"
    fake = SimpleNamespace(namespace=a.REAL, cli=[])
    attempts = [
        lambda: e.reserve(root, output, 1, False, workload=fake),
        lambda: e.bound_record(root, output, 1, workload=fake),
        lambda: e.worker(output, 1, 0, -1, fake, ledger_root=root),
        lambda: e.supervise(root, output, 1, workload=fake),
        lambda: e.continue_campaign(root, output, 1, workload=fake),
        lambda: e.verify_complete(root, output, 1, workload=fake),
        lambda: e.launch(root, output, 1, workload=fake),
    ]
    for attempt in attempts:
        with pytest.raises(PermissionError, match="unregistered workload"):
            attempt()
    synthetic = wl.SyntheticWorkload()
    synthetic.namespace = a.REAL
    with pytest.raises(PermissionError, match="namespace impersonation"):
        e.worker(output, 1, 0, -1, synthetic)
    assert not root.exists() and not output.exists()
