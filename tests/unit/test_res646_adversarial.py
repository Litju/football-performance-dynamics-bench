"""Adversarial refusal matrix for the signed artificial campaign (invented data only)."""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable, Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from test_res646_campaign import signed_campaign, supervise, write

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import res635_execution as e
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    res635_post_failure_evaluation as s,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import res645_fixtures as fx
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import res645_workloads as wl
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import res646_authorization as a

Mutation = Callable[[dict[str, Any]], None]
REFUSED = (ValueError, PermissionError, OSError)


@pytest.fixture(scope="module")
def finished(tmp_path_factory: pytest.TempPathFactory) -> wl.RealWorkload:
    base = tmp_path_factory.mktemp("res646-adversarial")
    config = signed_campaign(base / "campaign", fx.build_bundle(base / "bundle", samples=42))
    workload = wl.RealWorkload(config)
    campaign = workload.campaign
    e.reserve(campaign.root, campaign.output, workload.windows, True, workload=workload)
    assert supervise(config, workload).returncode == 0
    e.verify_complete(campaign.root, campaign.output, workload.windows, workload=workload)
    return workload


@pytest.fixture
def pristine(finished: wl.RealWorkload) -> Iterator[wl.RealWorkload]:
    """Restore every receipt and the ledger after each destructive case."""
    campaign = finished.campaign
    files = [*campaign.output.glob("match-*.json"), e.ledger_path(campaign.root, campaign.scope)]
    saved = {path: path.read_bytes() for path in files}
    yield finished
    for path, data in saved.items():
        write(path, data)
    for path in campaign.output.glob("match-*.json"):
        if path not in saved:
            path.unlink()


def verify(workload: wl.RealWorkload) -> Any:
    campaign = workload.campaign
    return e.verify_complete(campaign.root, campaign.output, workload.windows, workload=workload)


def reseal_last(workload: wl.RealWorkload, mutate: Mutation) -> None:
    """A ledger-key holder re-seals the final receipt; the other checks must still fail."""
    campaign = workload.campaign
    target = campaign.output / "match-3.json"
    receipt = json.loads(target.read_bytes())
    mutate(receipt)
    record = campaign.record()
    try:
        write(target, s.canonical(receipt))
        record["seals"][3] = s.digest(receipt)
    except ValueError:  # non-finite numbers cannot even be canonically sealed
        write(target, json.dumps(receipt).encode())
        record["seals"][3] = "0" * 64
    e.store_ledger(campaign.root, workload.windows, record)


def test_complete_campaign_has_four_receipts_and_72_records(pristine: wl.RealWorkload) -> None:
    manifest = verify(pristine)
    assert manifest["aggregate"]["records"] == 72
    assert len(pristine.campaign.record()["seals"]) == 4


def _cell(r: dict[str, Any]) -> None:
    r["records"][0]["cell"] = ["history_only", "absolute_xy", 1730]


def _metric(r: dict[str, Any]) -> None:
    r["records"][0]["strata"]["all"]["metrics"]["ade_m"] += 1.0


def _nan(r: dict[str, Any]) -> None:
    r["records"][0]["strata"]["all"]["metrics"]["fde_m"] = float("nan")


def _denominator(r: dict[str, Any]) -> None:
    r["identity"]["windows"] += 1


def _mask(r: dict[str, Any]) -> None:
    r["identity"]["mask_sha256"] = "1" * 64


def _source(r: dict[str, Any]) -> None:
    r["source"]["tracking_raw_sha256"] = "2" * 64


def _checkpoint(r: dict[str, Any]) -> None:
    r["provenance"]["checkpoint_bindings"][0]["checkpoint_sha256"] = "3" * 64


def _match(r: dict[str, Any]) -> None:
    r["match"] = wl.v.EVALUATION_MATCHES[0]


def _drop(r: dict[str, Any]) -> None:
    r["records"].pop()


def _chain(r: dict[str, Any]) -> None:
    r["previous_sha256"] = "4" * 64


def _scope(r: dict[str, Any]) -> None:
    r["scope_sha256"] = "5" * 64


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (_cell, "identity, denominator, or provenance differs"),
        (_metric, "independent metric parity failed"),
        (_nan, "not JSON compliant"),
        (_denominator, "independent denominator or source identity differs"),
        (_mask, "independent denominator or source identity differs"),
        (_source, "final bundle differs"),
        (_checkpoint, "checkpoint provenance differs from signed manifest"),
        (_match, "receipt seal, scope or match differs"),
        (_drop, "incomplete cell matrix"),
        (_chain, "receipt seal, scope or match differs"),
        (_scope, "receipt seal, scope or match differs"),
    ],
    ids=lambda v: v.__name__.strip("_") if callable(v) else "reason",
)
def test_rekeyed_receipt_tampering_is_rejected(
    pristine: wl.RealWorkload, mutate: Mutation, reason: str
) -> None:
    reseal_last(pristine, mutate)
    with pytest.raises(ValueError, match=reason):
        verify(pristine)


def test_unsealed_receipt_edit_breaks_seal(pristine: wl.RealWorkload) -> None:
    target = pristine.campaign.output / "match-1.json"
    receipt = json.loads(target.read_bytes())
    _metric(receipt)
    write(target, json.dumps(receipt, sort_keys=True).encode())
    with pytest.raises(ValueError, match="seal"):
        verify(pristine)


def test_reordered_duplicated_and_missing_receipts(pristine: wl.RealWorkload) -> None:
    output = pristine.campaign.output
    one, two = output / "match-1.json", output / "match-2.json"
    first, second = one.read_bytes(), two.read_bytes()
    write(one, second)
    write(two, first)
    with pytest.raises(REFUSED):
        verify(pristine)
    write(two, first)  # duplicate of match 1 in match 2's slot
    write(one, first)
    with pytest.raises(REFUSED):
        verify(pristine)
    two.unlink()
    with pytest.raises(REFUSED):
        verify(pristine)


def test_ledger_edit_without_independent_key_is_rejected(pristine: wl.RealWorkload) -> None:
    campaign = pristine.campaign
    path = e.ledger_path(campaign.root, campaign.scope)
    record = json.loads(path.read_bytes())
    record["seals"][3] = "6" * 64
    record["record_sha256"] = s.digest({k: v for k, v in record.items() if k != "record_sha256"})
    write(path, s.canonical(record))  # attacker recomputes the public self-hash only
    with pytest.raises(PermissionError, match="independent key"):
        verify(pristine)
    del record["ledger_mac"]
    record["record_sha256"] = s.digest({k: v for k, v in record.items() if k != "record_sha256"})
    write(path, s.canonical(record))
    with pytest.raises(PermissionError, match="independent key"):
        verify(pristine)


def test_replaced_ledger_key_is_rejected(pristine: wl.RealWorkload) -> None:
    key = pristine.campaign.root.with_name("ledger.ledger-key")
    original = key.read_bytes()
    try:
        write(key, os.urandom(32))
        with pytest.raises(PermissionError, match="independent key"):
            verify(pristine)
    finally:
        write(key, original)


def test_ledger_key_must_live_outside_ledger_and_output(pristine: wl.RealWorkload) -> None:
    campaign = pristine.campaign
    key = campaign.root.with_name("ledger.ledger-key")
    assert campaign.root not in key.parents and campaign.output not in key.parents
    assert all(b"ledger-key" not in p.name.encode() for p in campaign.root.iterdir())
    assert (
        key.read_bytes().hex().encode()
        not in e.ledger_path(campaign.root, campaign.scope).read_bytes()
    )


def test_expired_approval_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = signed_campaign(tmp_path / "expired", fx.build_bundle(tmp_path / "b", samples=42))
    real_datetime = a.datetime

    class Later(real_datetime):  # type: ignore[misc]
        @classmethod
        def now(cls, tz: Any = None) -> Any:  # noqa: ANN401
            return real_datetime.now(tz) + timedelta(hours=7)

    monkeypatch.setattr(a, "datetime", Later)
    with pytest.raises(ValueError, match="not currently valid"):
        wl.RealWorkload(config)


def test_synthetic_approval_cannot_authorize_production(pristine: wl.RealWorkload) -> None:
    campaign = pristine.campaign
    payload = campaign.path.with_suffix(".approval.json").read_bytes()
    signature = campaign.path.with_suffix(".approval.sig").read_bytes()
    with pytest.raises(ValueError):
        a.verify_real(payload, signature, campaign.identities)
    forged = json.loads(campaign.path.read_bytes())
    forged["namespace"] = a.REAL
    stash = campaign.path.read_bytes()
    try:
        write(campaign.path, s.canonical(forged))
        with pytest.raises(REFUSED):
            wl.RealWorkload(campaign.path)
    finally:
        write(campaign.path, stash)


def test_wrong_scope_and_wrong_ledger_root_are_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = signed_campaign(tmp_path / "scope", fx.build_bundle(tmp_path / "b", samples=42))
    workload = wl.RealWorkload(config)
    campaign = workload.campaign
    with pytest.raises(REFUSED):
        e.reserve(campaign.root, campaign.output, workload.windows + 1, True, workload=workload)
    other = tmp_path / "other-ledger"
    other.mkdir(mode=0o700)
    with pytest.raises(REFUSED):
        e.reserve(other, campaign.output, workload.windows, True, workload=workload)
    assert not list(campaign.root.iterdir())


def test_premature_calls_and_duplicate_launch_are_refused(tmp_path: Path) -> None:
    config = signed_campaign(tmp_path / "early", fx.build_bundle(tmp_path / "b", samples=42))
    workload = wl.RealWorkload(config)
    campaign = workload.campaign
    with pytest.raises(REFUSED):
        verify(workload)  # nothing reserved yet
    e.reserve(campaign.root, campaign.output, workload.windows, True, workload=workload)
    with pytest.raises(ValueError):
        verify(workload)  # reserved but incomplete
    with pytest.raises(ValueError):
        e.continue_campaign(campaign.root, campaign.output, workload.windows, workload=workload)
    with pytest.raises(REFUSED):
        e.launch(campaign.root, campaign.output, workload.windows, workload=workload)
    with pytest.raises(PermissionError):
        e.worker(campaign.output, workload.windows, 0, -1, workload, ledger_root=campaign.root)


@pytest.mark.parametrize(
    "corrupt",
    ["match-0/tracking.jsonl", "match-0/locked.jsonl", "match-1/metadata.json", "manifest.json"],
)
def test_input_changed_after_signing_is_refused_before_any_open(
    tmp_path: Path, corrupt: str
) -> None:
    bundle = fx.build_bundle(tmp_path / "b", samples=42)
    config = signed_campaign(tmp_path / "campaign", bundle)
    target = bundle / corrupt
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(REFUSED):
        wl.RealWorkload(config)


def test_substituted_checkpoint_after_signing_is_refused(tmp_path: Path) -> None:
    bundle = fx.build_bundle(tmp_path / "b", samples=42)
    config = signed_campaign(tmp_path / "campaign", bundle)
    first, second = sorted((bundle / "checkpoints").glob("*.pt"))[:2]
    shutil.copyfile(second, first)
    with pytest.raises(REFUSED):
        wl.RealWorkload(config)
