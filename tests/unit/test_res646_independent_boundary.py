"""Direct independent API attacks use invented files and instrument protected operations."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import res645_checkpoints as ck
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import res645_fixtures as fx
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import res645_independent as ind
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import res646_authorization as a


@pytest.mark.parametrize("api", ["raw", "models", "match"])
@pytest.mark.parametrize("authority", [None, object()])
def test_direct_frozen_calls_deny_before_input_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    api: str,
    authority: object,
) -> None:
    manifest = ck.frozen_manifest()
    opened = Mock(side_effect=AssertionError("protected input opened"))
    loaded = Mock(side_effect=AssertionError("tensor deserialized"))
    forward = Mock(side_effect=AssertionError("model forwarded"))
    monkeypatch.setattr(ind.paths, "read_regular_file", opened)
    monkeypatch.setattr(ind.torch, "load", loaded)
    monkeypatch.setattr(ind.lds.PerTargetContextDeepSetsMLP, "forward", forward)
    with pytest.raises((PermissionError, ValueError)):
        if api == "raw":
            list(ind.raw_windows(tmp_path, "1874553", mode="frozen", campaign=authority))
        elif api == "models":
            ind.load_models(manifest, tmp_path, tmp_path, mode="frozen", campaign=authority)
        else:
            ind.match_body(
                tmp_path, "1874553", manifest, tmp_path, tmp_path, mode="frozen", campaign=authority
            )
    opened.assert_not_called()
    loaded.assert_not_called()
    forward.assert_not_called()


def test_synthetic_manifest_cannot_substitute_exact_frozen_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = fx.build_bundle(tmp_path / "bundle", samples=42)
    _, manifest, checkpoints = fx.read_bundle(bundle)
    frozen = ck.frozen_manifest()["checkpoints"][0]
    manifest["checkpoints"][0]["checkpoint_sha256"] = frozen["checkpoint_sha256"]
    opened = Mock(side_effect=AssertionError("protected input opened"))
    monkeypatch.setattr(ind.paths, "read_regular_file", opened)
    with pytest.raises(ValueError, match="masquerade"):
        ind.load_models(manifest, checkpoints, bundle / "receipts")
    opened.assert_not_called()


@pytest.mark.parametrize("alias", ["identity", "symlink", "hardlink"])
def test_invented_marker_cannot_admit_evaluation_or_aliased_tracking(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    alias: str,
) -> None:
    import json
    import os

    bundle = fx.build_bundle(tmp_path / "bundle", samples=42)
    specs, _, _ = fx.read_bundle(bundle)
    spec = specs[0]
    if alias == "identity":
        meta = spec.directory / "metadata.json"
        document = json.loads(meta.read_bytes())
        document["id"] = 1874553
        meta.write_text(json.dumps(document))
    else:
        tracking = spec.directory / "tracking.jsonl"
        target = tmp_path / "invented-tracking"
        tracking.rename(target)
        tracking.symlink_to(target) if alias == "symlink" else os.link(target, tracking)
    loaded = Mock(side_effect=AssertionError("tensor deserialized"))
    monkeypatch.setattr(ind.torch, "load", loaded)
    with pytest.raises((PermissionError, OSError)):
        list(ind.raw_windows(spec.directory, spec.label))
    loaded.assert_not_called()


@pytest.mark.parametrize("failure", ["namespace", "worker", "unreserved"])
def test_real_source_requires_reserved_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    # Use the exact authority type; no fake capability is accepted by require_campaign.
    campaign = object.__new__(a.Campaign)
    campaign.namespace = a.SYNTHETIC if failure == "namespace" else a.REAL
    campaign.specs = [ind.source.SourceMatchSpec("1874553", "1874553", tmp_path)]
    deny = Mock(side_effect=PermissionError(failure))
    monkeypatch.setattr(a.Campaign, "require_worker", deny)
    opened = Mock(side_effect=AssertionError("protected input opened"))
    monkeypatch.setattr(ind.paths, "read_regular_file", opened)
    with pytest.raises(PermissionError):
        list(ind.raw_windows(tmp_path, "1874553", mode="frozen", campaign=campaign))
    opened.assert_not_called()
