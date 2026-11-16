"""Synthetic-only parity, stream accounting and independent aggregation."""

from __future__ import annotations

import copy
import hashlib
import tracemalloc

import numpy as np
import pytest

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    learned_deepsets as lds,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    res635_post_failure_evaluation as s,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    res635_verification as v,
)
from fpdbench.evaluation.metrics.trajectory import masked_physical_trajectory_metrics


@pytest.fixture(scope="module")
def models():
    return s.models()


def test_matrix_and_public_parity(models):
    assert len(models) == 18
    actual = s.score_match(s.MATCHES[0], 3, models)
    expected = v.independent_match(s.MATCHES[0], 3, models)
    v.assert_equivalent(actual, expected)
    assert s.score_match(s.MATCHES[0], 3, models) == actual
    assert actual["identity"]["scoreable_scenes"] == 5
    assert actual["identity"]["scalar_coordinates"] == 2 * actual["identity"]["scored_points"]


def test_scalar_coordinate_rmse_and_mask():
    scene = s.window(s.MATCHES[0], 0)["scenes"][0]
    truth, displacement, mask = lds.validate_truth_scene(scene)
    origin = np.array(scene["origin_xy"])
    np.testing.assert_allclose(
        (displacement + origin[:, None])[mask], truth[mask], atol=1e-12, rtol=0
    )
    prediction = truth + np.array([3.0, 4.0])
    result = s.scene_metrics(prediction, scene, "all")
    assert result["ade_m"] == 5
    assert result["fde_m"] == 5
    assert result["xy_rmse_m"] == pytest.approx(np.sqrt(12.5))
    public = masked_physical_trajectory_metrics(
        [prediction.transpose(1, 0, 2).tolist()], [scene["absolute_xy"]]
    )
    assert public.xy_rmse_m == result["xy_rmse_m"]
    bad = copy.deepcopy(scene)
    bad["truth_mask"][0][0] = not bad["truth_mask"][0][0]
    with pytest.raises(ValueError):
        lds.validate_truth_scene(bad)


def test_cached_scene_truth_preserves_all_stratum_metrics():
    for scene in s.window(s.MATCHES[0], 1)["scenes"]:
        truth, _, mask = lds.validate_truth_scene(scene)
        prediction = np.nan_to_num(truth) + np.array([3.0, 4.0])
        for stratum in s.STRATA:
            assert s.validated_scene_metrics(prediction, scene, stratum, truth, mask) == (
                s.scene_metrics(prediction, scene, stratum)
            )


def test_feature_boundary_and_source_mask():
    row = s.window(s.MATCHES[0], 1)
    for regime in lds.INFORMATION_REGIMES:
        payload = lds.build_scene_feature_payload(
            row["support"],
            target_side="home",
            target_player_ids=range(1, 12),
            home_player_ids=range(1, 12),
            away_player_ids=range(12, 23),
            regime=regime,
        )
        assert ("future_ball" in payload) == (regime != "history_only")
        payload["forbidden_truth"] = np.zeros(1)
        with pytest.raises(ValueError):
            lds.validate_feature_payload(payload, regime)
    assert not row["scenes"][1]["scoreable"]
    identity = s.StreamIdentity(s.MATCHES[0])
    first = s.window(s.MATCHES[0], 0)
    identity.observe(first)
    with pytest.raises(ValueError, match="order"):
        identity.observe(first)
    first["index"] = 1
    first["window_id"] = f"{s.MATCHES[0]}:00000001"
    with pytest.raises(ValueError):
        identity.observe(first)


def test_unscoreable_and_incomplete(models):
    row = s.window(s.MATCHES[0], 6)
    assert not any(scene["scoreable"] for scene in row["scenes"])
    with pytest.raises(ValueError, match="incomplete"):
        s.score_match(s.MATCHES[0], 2, models, source=s.windows(s.MATCHES[0], 1))
    with pytest.raises(ValueError):
        s.window("1874553", 0)


def test_independent_72_aggregation(models):
    receipts = [s.score_match(match, 1 + i, models) for i, match in enumerate(s.MATCHES)]
    result = v.aggregate(receipts)
    assert result["records"] == 72
    assert len(result["contrasts"]) == 4
    key = "history_only/absolute_xy"
    expected = (
        sum(
            sum(r["strata"]["all"]["metrics"]["ade_m"] for r in match["records"][:3]) / 3
            for match in receipts
        )
        / 4
    )
    assert result["equal_match_means"][key]["ade_m"] == expected
    with pytest.raises(ValueError):
        v.aggregate(receipts[:-1])
    receipts[0]["records"][0]["cell"] = receipts[0]["records"][1]["cell"]
    with pytest.raises(ValueError):
        v.aggregate(receipts)


def test_stream_memory_is_bounded():
    def measure(count):
        tracemalloc.start()
        identity = s.StreamIdentity(s.MATCHES[0])
        for row in s.windows(s.MATCHES[0], count):
            identity.observe(row)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return identity.result(), peak

    small, small_peak = measure(8)
    large, large_peak = measure(80)
    assert large["windows"] == 80
    assert large_peak < small_peak * 2
    assert small["input_sha256"] != large["input_sha256"]
    assert len(hashlib.sha256(s.canonical(large)).hexdigest()) == 64


def test_census_lightweight_denominators_match_full_source():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "tools" / "res643_synthetic_qualification.py"
    spec = importlib.util.spec_from_file_location("res643_census", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.census(32)
    identities = []
    digest = hashlib.sha256()
    for match in s.MATCHES:
        identity = s.StreamIdentity(match)
        for row in s.windows(match, 8):
            identity.observe(row)
            mask = np.array([scene["truth_mask"] for scene in row["scenes"]])
            digest.update(np.packbits(np.concatenate([mask[0], mask[1]], axis=1)).tobytes())
        identities.append(identity.result())
    for key in (
        "windows",
        "scoreable_windows",
        "scoreable_scenes",
        "scored_points",
        "final_targets",
        "scalar_coordinates",
    ):
        assert result[key] == sum(i[key] for i in identities)
    assert result["mask_sha256"] == digest.hexdigest()
    assert result["snapshot_bytes"] == result["forward_calls"] == 0
