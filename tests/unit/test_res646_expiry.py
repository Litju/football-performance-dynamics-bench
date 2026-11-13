"""Approval expiry never revives execution or erases authenticated historical evidence."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from test_res646_campaign import signed_campaign, supervise, write

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import res635_execution as e
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    res635_post_failure_evaluation as s,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import res645_fixtures as fx
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import res645_workloads as wl
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import res646_authorization as a


@pytest.fixture(scope="module")
def bundle(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return fx.build_bundle(tmp_path_factory.mktemp("res646-expiry-fixture") / "bundle", samples=42)


def after_expiry(monkeypatch: pytest.MonkeyPatch, campaign: a.Campaign) -> None:
    body = json.loads(campaign.path.with_suffix(".approval.json").read_bytes())
    future = datetime.fromisoformat(body["expires_at_utc"].replace("Z", "+00:00"))
    future += timedelta(seconds=1)

    class ExpiredClock(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            return future.astimezone(tz) if tz is not None else future.replace(tzinfo=None)

    monkeypatch.setattr(a, "datetime", ExpiredClock)


def test_expired_approval_cannot_reserve_even_when_historical_signature_is_valid(
    tmp_path: Path,
    bundle: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = signed_campaign(tmp_path / "expired-before-reservation", bundle)
    original = wl.RealWorkload(config)
    after_expiry(monkeypatch, original.campaign)
    historical = wl.RealWorkload(config)
    historical.campaign.verify()
    with pytest.raises(ValueError, match="currently valid"):
        e.reserve(
            historical.campaign.root,
            historical.campaign.output,
            historical.windows,
            True,
            workload=historical,
        )
    assert list(historical.campaign.root.iterdir()) == []
    assert list(historical.campaign.output.iterdir()) == []


def test_valid_approval_reserves_one_atomic_scope(tmp_path: Path, bundle: Path) -> None:
    workload = wl.RealWorkload(signed_campaign(tmp_path / "atomic-reservation", bundle))
    campaign = workload.campaign
    first = e.reserve(campaign.root, campaign.output, workload.windows, True, workload=workload)
    assert first["reserved_at_utc"] == first["attempt_authorized_at_utc"][0]
    assert campaign.record() == first
    path = e.ledger_path(campaign.root, campaign.scope)
    saved = path.read_bytes()
    # Remove the ordinary output marker to exercise the ledger's exclusive-create refusal itself.
    (campaign.output / "campaign.json").unlink()
    with pytest.raises(FileExistsError):
        e.reserve(campaign.root, campaign.output, workload.windows, True, workload=workload)
    assert path.read_bytes() == saved
    assert list(campaign.root.iterdir()) == [path]


@pytest.fixture(scope="module")
def completed(bundle: Path, tmp_path_factory: pytest.TempPathFactory) -> wl.RealWorkload:
    config = signed_campaign(
        tmp_path_factory.mktemp("res646-expiry-completed") / "campaign", bundle
    )
    workload = wl.RealWorkload(config)
    campaign = workload.campaign
    e.reserve(campaign.root, campaign.output, workload.windows, True, workload=workload)
    done = supervise(config, workload)
    assert done.returncode == 0, (done.stdout, done.stderr)
    assert (
        e.verify_complete(campaign.root, campaign.output, workload.windows, workload=workload)[
            "aggregate"
        ]["records"]
        == 72
    )
    return workload


@pytest.fixture
def historical(completed: wl.RealWorkload) -> Iterator[wl.RealWorkload]:
    path = e.ledger_path(completed.campaign.root, completed.campaign.scope)
    saved = path.read_bytes()
    yield completed
    write(path, saved)


def test_completed_results_verify_after_expiry_without_model_replay(
    historical: wl.RealWorkload,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign = historical.campaign
    after_expiry(monkeypatch, campaign)
    loaded = Mock(side_effect=AssertionError("historical verification loaded a checkpoint"))
    forwarded = Mock(side_effect=AssertionError("historical verification repeated inference"))
    monkeypatch.setattr(wl.ck, "load_models", loaded)
    monkeypatch.setattr(wl.ck.lds.PerTargetContextDeepSetsMLP, "forward", forwarded)
    reconstructed = wl.RealWorkload(campaign.path)
    result = e.verify_complete(
        campaign.root, campaign.output, reconstructed.windows, workload=reconstructed
    )
    assert result["aggregate"]["records"] == 72
    assert len(reconstructed.campaign.record()["seals"]) == 4
    loaded.assert_not_called()
    forwarded.assert_not_called()


def test_expired_completed_scope_cannot_reserve_continue_or_reenter_worker(
    historical: wl.RealWorkload,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign = historical.campaign
    after_expiry(monkeypatch, campaign)
    saved = e.ledger_path(campaign.root, campaign.scope).read_bytes()
    for action in (
        lambda: e.reserve(
            campaign.root, campaign.output, historical.windows, True, workload=historical
        ),
        lambda: e.continue_campaign(
            campaign.root, campaign.output, historical.windows, workload=historical
        ),
        campaign.require_worker,
    ):
        with pytest.raises((PermissionError, ValueError), match="currently valid"):
            action()
    assert e.ledger_path(campaign.root, campaign.scope).read_bytes() == saved
    assert not (campaign.root / f"{campaign.scope}.continuation").exists()


def test_expiry_stops_an_already_authorized_attempt_at_next_scoring_check(
    tmp_path: Path,
    bundle: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workload = wl.RealWorkload(signed_campaign(tmp_path / "expiry-during-attempt", bundle))
    campaign = workload.campaign
    e.reserve(campaign.root, campaign.output, workload.windows, True, workload=workload)
    record = campaign.record()
    record.update(status="RUNNING", supervisor_pid=os.getppid())
    e.store_ledger(campaign.root, workload.windows, record)
    # Simulate the reserved worker's next scoring check without signals or learned weights.
    monkeypatch.setattr(e.threading, "Thread", Mock())
    monkeypatch.setattr(e.signal, "pthread_sigmask", Mock())
    monkeypatch.setattr(workload, "prepare", lambda: object())
    forward = Mock()

    def score(i: int, count: int, prepared: Any, check: Any) -> dict[str, Any]:
        forward()
        after_expiry(monkeypatch, campaign)
        check()
        forward()
        raise AssertionError("expired scoring reached another forward call")

    monkeypatch.setattr(workload, "score", score)
    assert (
        e.worker(campaign.output, workload.windows, 0, -1, workload, ledger_root=campaign.root)
        == e.EXIT_INTEGRITY
    )
    assert forward.call_count == 1
    terminal = e.read(campaign.output / "worker-terminal.json")
    assert terminal == {"status": "SCIENTIFIC_OR_INTEGRITY_FAILURE", "error": "PermissionError"}
    assert not list(campaign.output.glob("match-*.json"))
    assert campaign.record()["seals"] == []
    with pytest.raises(ValueError, match="currently valid"):
        campaign.require_worker()


@pytest.mark.parametrize("reseal", [False, True])
@pytest.mark.parametrize("stamp", ["before", "after", "future"])
def test_tampered_historical_times_never_become_execution_authority(
    historical: wl.RealWorkload,
    reseal: bool,
    stamp: str,
) -> None:
    campaign = historical.campaign
    record = campaign.record()
    body = json.loads(campaign.path.with_suffix(".approval.json").read_bytes())
    if stamp == "before":
        instant = datetime.fromisoformat(
            body["authorization"]["authorized_at_utc"].replace("Z", "+00:00")
        ) - timedelta(seconds=1)
    elif stamp == "after":
        instant = datetime.fromisoformat(body["expires_at_utc"].replace("Z", "+00:00"))
    else:
        instant = datetime.now(UTC) + timedelta(minutes=1)
    value = instant.isoformat().replace("+00:00", "Z")
    record["reserved_at_utc"] = value
    record["attempt_authorized_at_utc"][0] = value
    if reseal:
        e.store_ledger(campaign.root, historical.windows, record)
    else:
        record["record_sha256"] = s.digest(
            {k: v for k, v in record.items() if k != "record_sha256"}
        )
        write(e.ledger_path(campaign.root, campaign.scope), s.canonical(record))
    with pytest.raises(PermissionError, match="authorization time|authenticated"):
        campaign.record()


def test_forged_historical_ledger_is_rejected_after_expiry(
    historical: wl.RealWorkload,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign = historical.campaign
    record = campaign.record()
    after_expiry(monkeypatch, campaign)
    record["seals"][0] = "a" * 64
    record["record_sha256"] = s.digest({k: v for k, v in record.items() if k != "record_sha256"})
    write(e.ledger_path(campaign.root, campaign.scope), s.canonical(record))
    with pytest.raises(PermissionError, match="not authenticated"):
        e.verify_complete(campaign.root, campaign.output, historical.windows, workload=historical)
