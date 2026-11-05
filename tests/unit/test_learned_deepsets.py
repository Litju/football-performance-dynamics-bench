"""Synthetic qualification for the frozen learned model."""

from __future__ import annotations

import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import cast

import numpy as np
import pytest
import torch
from torch import nn

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from train_res338_final_fits import MatchCache, _fit_one  # noqa: E402

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.learned_deepsets import (
    FUTURE_TRACK_FEATURES,
    HEAD_FEATURE_LAYOUT,
    HISTORY_TRACK_FEATURES,
    INFORMATION_REGIMES,
    INPUT_DIMS,
    CheckpointSelection,
    PerTargetContextDeepSetsMLP,
    build_scene_feature_payload,
    checkpoint_sha256,
    collate_feature_payloads,
    configure_deterministic_cpu,
    equal_match_mean,
    fit_failure_category,
    load_checkpoint_verified,
    make_optimizer,
    masked_scene_ade_loss,
    physical_metrics,
    retry_allowed,
    sample_scene_index,
    save_checkpoint_atomically,
    seed_training,
    validate_feature_payload,
    validate_truth_scene,
    validation_due,
)
from fpdbench.evaluation.metrics.trajectory import masked_physical_trajectory_metrics

configure_deterministic_cpu()


def _support(
    *,
    future_target_shift: float = 0.0,
    future_opponent_shift: float = 0.0,
    future_ball_shift: float = 0.0,
) -> list[dict[str, object]]:
    support: list[dict[str, object]] = []
    for sample_index in range(41):
        players: list[dict[str, object]] = []
        for side, ids in (("home", range(1, 12)), ("away", range(21, 33))):
            for player_id in ids:
                if player_id == 32 and sample_index < 26:
                    continue
                shift = (
                    future_target_shift
                    if side == "home" and sample_index >= 26
                    else future_opponent_shift
                    if side == "away" and sample_index >= 26
                    else 0.0
                )
                missing = (player_id == 1 and sample_index == 0) or (
                    player_id == 2 and sample_index == 3
                )
                players.append(
                    {
                        "player_id": player_id,
                        "group": side,
                        "x_m": None if missing else float(player_id + sample_index + shift),
                        "y_m": None if missing else float(player_id - sample_index + shift),
                        "is_detected": None,
                    }
                )
        ball_shift = future_ball_shift if sample_index >= 26 else 0.0
        ball = (
            None
            if sample_index == 0
            else {
                "x_m": float(sample_index + ball_shift),
                "y_m": float(-sample_index + ball_shift),
                "is_detected": None,
            }
        )
        support.append({"players": players, "ball": ball})
    return support


def _payload(support: list[dict[str, object]], regime: str, side: str = "home"):
    ids = list(range(1, 12)) if side == "home" else list(range(21, 32))
    return build_scene_feature_payload(
        support,
        target_side=side,
        target_player_ids=ids,
        home_player_ids=list(range(1, 12)),
        away_player_ids=list(range(21, 33)),
        regime=regime,  # type: ignore[arg-type]
    )


def test_exact_architecture_dimensions_and_output() -> None:
    support = _support()
    assert sum(width for _, width in HEAD_FEATURE_LAYOUT[:6]) == 215
    assert sum(width for _, width in HEAD_FEATURE_LAYOUT[:7]) == 260
    assert sum(width for _, width in HEAD_FEATURE_LAYOUT) == 276
    for regime in INFORMATION_REGIMES:
        payloads = [_payload(support, regime), _payload(support, regime, "away")]
        model = PerTargetContextDeepSetsMLP(regime)
        assert INPUT_DIMS[regime] in {215, 260, 276}
        assert [
            (layer.in_features, layer.out_features)
            for layer in model.history_player_encoder
            if isinstance(layer, nn.Linear)
        ] == [(78, 32), (32, 16)]
        assert [type(layer) for layer in model.history_player_encoder] == [
            nn.Linear,
            nn.ReLU,
            nn.Linear,
            nn.ReLU,
        ]
        assert [type(layer) for layer in model.prediction_head] == [
            nn.Linear,
            nn.ReLU,
            nn.Dropout,
            nn.Linear,
            nn.ReLU,
            nn.Dropout,
            nn.Linear,
        ]
        assert [layer.p for layer in model.prediction_head if isinstance(layer, nn.Dropout)] == [
            0.1,
            0.1,
        ]
        assert [
            (layer.in_features, layer.out_features)
            for layer in model.prediction_head
            if isinstance(layer, nn.Linear)
        ] == [(INPUT_DIMS[regime], 128), (128, 128), (128, 30)]
        if regime == "future_opponent_plus_ball":
            assert model.future_opponent_encoder is not None
            assert [
                (layer.in_features, layer.out_features)
                for layer in model.future_opponent_encoder
                if isinstance(layer, nn.Linear)
            ] == [(45, 32), (32, 16)]
        else:
            assert model.future_opponent_encoder is None
        model.eval()
        with torch.inference_mode():
            assert model(collate_feature_payloads(payloads, regime)).shape == (2, 11, 15, 2)


def test_missing_xy_masks_and_future_substitutes_are_encoded() -> None:
    payload = _payload(_support(), "future_opponent_plus_ball")
    assert payload["target_history"][0, :3].tolist() == [0.0, 0.0, 0.0]
    assert payload["history_ball"][:3].tolist() == [0.0, 0.0, 0.0]
    assert payload["history_ball"][3:6].tolist() == [1.0, -1.0, 1.0]
    assert payload["target_side"].item() == 1.0
    assert payload["future_opponent_mask"].shape == (12,)
    assert payload["future_opponent_mask"][-1]
    assert payload["future_opponent_tracks"].shape == (12, FUTURE_TRACK_FEATURES)
    assert payload["history_team_tracks"].shape[2] == HISTORY_TRACK_FEATURES
    malformed = _support()
    cast(dict[str, object], malformed[1]["players"][0])["x_m"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        _payload(malformed, "history_only")


def test_deepsets_team_and_opponent_pools_are_permutation_invariant() -> None:
    payloads = [
        _payload(_support(), "future_opponent_plus_ball"),
        _payload(_support(), "future_opponent_plus_ball", "away"),
    ]
    inputs = collate_feature_payloads(payloads, "future_opponent_plus_ball")
    model = PerTargetContextDeepSetsMLP("future_opponent_plus_ball").eval()
    reverse_history = torch.arange(inputs.history_team_tracks.shape[2] - 1, -1, -1)
    reverse_future = torch.arange(inputs.future_opponent_tracks.shape[1] - 1, -1, -1)
    permuted = replace(
        inputs,
        history_team_tracks=inputs.history_team_tracks.index_select(2, reverse_history),
        history_team_mask=inputs.history_team_mask.index_select(2, reverse_history),
        future_opponent_tracks=inputs.future_opponent_tracks.index_select(1, reverse_future),
        future_opponent_mask=inputs.future_opponent_mask.index_select(1, reverse_future),
    )
    with torch.inference_mode():
        expected = model(inputs)
        actual = model(permuted)
    torch.testing.assert_close(actual, expected, rtol=1e-6, atol=1e-6)


def test_regimes_and_future_target_isolation() -> None:
    original = _support()
    changed_target = _support(future_target_shift=500.0)
    history = _payload(original, "history_only")
    history_changed = _payload(changed_target, "history_only")
    future_ball = _payload(original, "future_ball")
    future_ball_changed = _payload(changed_target, "future_ball")
    future_opponents = _payload(original, "future_opponent_plus_ball")
    future_opponents_changed = _payload(changed_target, "future_opponent_plus_ball")
    assert "future_ball" not in history
    assert "future_opponent_tracks" not in future_ball
    for key in history:
        np.testing.assert_array_equal(history[key], history_changed[key])
    for key in future_ball:
        np.testing.assert_array_equal(future_ball[key], future_ball_changed[key])
    for key in future_opponents:
        np.testing.assert_array_equal(future_opponents[key], future_opponents_changed[key])

    changed_opponent = _payload(_support(future_opponent_shift=500.0), "future_opponent_plus_ball")
    assert not np.array_equal(
        future_opponents["future_opponent_tracks"], changed_opponent["future_opponent_tracks"]
    )
    changed_ball = _payload(_support(future_ball_shift=500.0), "future_ball")
    assert not np.array_equal(future_ball["future_ball"], changed_ball["future_ball"])

    injected = {**future_ball, "future_target_xy": np.zeros((11, 15, 2))}
    with pytest.raises(ValueError, match="frozen information regime"):
        validate_feature_payload(injected, "future_ball")  # type: ignore[arg-type]
    injected_mask = {**future_ball, "future_target_availability": np.ones((11, 15))}
    with pytest.raises(ValueError, match="frozen information regime"):
        validate_feature_payload(injected_mask, "future_ball")  # type: ignore[arg-type]


def test_absolute_and_displacement_truth_share_the_locked_mask() -> None:
    origin = [[float(index + 10), float(index - 10)] for index in range(11)]
    absolute: list[list[list[float] | None]] = []
    displacement: list[list[list[float] | None]] = []
    mask: list[list[bool]] = []
    for timestep in range(15):
        a_row: list[list[float] | None] = []
        d_row: list[list[float] | None] = []
        m_row: list[bool] = []
        for player_index in range(11):
            if timestep == 4 and player_index == 3:
                a_row.append(None)
                d_row.append(None)
                m_row.append(False)
            else:
                xy = [float(player_index + timestep), float(player_index - timestep)]
                a_row.append(xy)
                d_row.append([xy[0] - origin[player_index][0], xy[1] - origin[player_index][1]])
                m_row.append(True)
        absolute.append(a_row)
        displacement.append(d_row)
        mask.append(m_row)
    scene = {
        "absolute_xy": absolute,
        "origin_relative_displacement": displacement,
        "origin_xy": origin,
        "truth_mask": mask,
        "scoreable": True,
    }
    abs_values, delta_values, valid = validate_truth_scene(scene)
    np.testing.assert_allclose(
        abs_values[valid] - np.repeat(np.asarray(origin)[:, None, :], 15, 1)[valid],
        delta_values[valid],
    )
    assert not valid[3, 4]
    scene["truth_mask"] = [[True] * 11 for _ in range(15)]
    with pytest.raises(ValueError, match="share the locked truth mask"):
        validate_truth_scene(scene)


def test_hierarchical_sampler_and_with_replacement() -> None:
    class ScriptedRng:
        def __init__(self) -> None:
            self.integer_choices = iter((1, 0, 1, 0))
            self.choice_calls = 0

        def integers(self, stop: int) -> int:
            choice = next(self.integer_choices)
            assert 0 <= choice < stop
            return choice

        def choice(self, values: np.ndarray) -> int:
            self.choice_calls += 1
            assert values.tolist() == [0, 1]
            return 1

    windows = [
        np.asarray([[True, False]], dtype=np.bool_),
        np.asarray([[True, True], [False, True]], dtype=np.bool_),
    ]
    rng = ScriptedRng()
    assert sample_scene_index(windows, rng) == (1, 0, 1)
    assert sample_scene_index(windows, rng) == (1, 0, 1)
    assert rng.choice_calls == 2


def test_runtime_seeding_optimizer_cadence_and_validation_aggregation() -> None:
    configure_deterministic_cpu()
    assert torch.get_num_threads() == torch.get_num_interop_threads() == 1
    assert torch.are_deterministic_algorithms_enabled()
    seed_training(2718)
    first = PerTargetContextDeepSetsMLP("history_only").state_dict()
    seed_training(2718)
    second = PerTargetContextDeepSetsMLP("history_only").state_dict()
    assert all(torch.equal(first[key], second[key]) for key in first)
    seed_training(31415)
    expected_first_linear = nn.Linear(78, 32)
    seed_training(31415)
    default_initialized = PerTargetContextDeepSetsMLP("history_only").history_player_encoder[0]
    assert isinstance(default_initialized, nn.Linear)
    assert torch.equal(default_initialized.weight, expected_first_linear.weight)
    assert torch.equal(default_initialized.bias, expected_first_linear.bias)
    optimizer = make_optimizer(PerTargetContextDeepSetsMLP("history_only"))
    assert isinstance(optimizer, torch.optim.AdamW)
    assert optimizer.defaults["lr"] == 0.001
    assert optimizer.defaults["betas"] == (0.9, 0.999)
    assert optimizer.defaults["eps"] == 1e-8
    assert optimizer.defaults["weight_decay"] == 0.0001
    assert [validation_due(step) for step in (0, 99, 100, 200, 201)] == [
        False,
        False,
        True,
        True,
        False,
    ]
    assert equal_match_mean({"a": 0.0, "b": 10.0, "c": 10.0, "d": 0.0}, ("a", "b", "c", "d")) == 5.0
    with pytest.raises(ValueError, match="exactly all four"):
        equal_match_mean({"a": 1.0}, ("a", "b", "c", "d"))


def test_early_stopping_is_strict_and_ties_keep_the_earliest_step() -> None:
    selection = CheckpointSelection()
    assert selection.observe(100, 1.0)
    for step in range(200, 1100, 100):
        assert not selection.observe(step, 1.0)
    assert selection.best_step == 100
    assert selection.checks_without_improvement == 9
    assert not selection.should_stop
    assert not selection.observe(1100, 1.0)
    assert selection.should_stop
    assert selection.best_step == 100
    assert selection.observe(1200, 0.999)
    assert selection.best_step == 1200


def test_checkpoint_integrity_and_retry_restrictions(tmp_path) -> None:
    model = PerTargetContextDeepSetsMLP("history_only")
    path = tmp_path / "checkpoint.pt"
    digest = save_checkpoint_atomically(
        path, {"state_dict": model.state_dict(), "selected_step": 100}
    )
    loaded = load_checkpoint_verified(path, digest)
    assert loaded["selected_step"] == 100
    assert checkpoint_sha256(path) == digest
    raw = bytearray(path.read_bytes())
    raw[-1] ^= 0x01
    path.write_bytes(raw)
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        load_checkpoint_verified(path, digest)
    assert retry_allowed("uncommitted", "external_worker_interruption", 1, True)
    assert not retry_allowed("failed", "out_of_memory", 1, True)
    assert not retry_allowed("uncommitted", "out_of_memory", 1, True)
    assert not retry_allowed("uncommitted", "external_worker_interruption", 2, True)
    assert not retry_allowed("uncommitted", "external_worker_interruption", 1, False)


def test_nonfinite_and_out_of_memory_failures_are_not_retryable() -> None:
    assert fit_failure_category(FloatingPointError("synthetic nonfinite")) == "non_finite_fit"
    assert fit_failure_category(torch.OutOfMemoryError("synthetic OOM")) == "out_of_memory"
    assert fit_failure_category(RuntimeError("CPU out of memory")) == "out_of_memory"
    assert fit_failure_category(RuntimeError("other failure")) == "fit_failure"
    model = PerTargetContextDeepSetsMLP("history_only")
    with torch.no_grad():
        model.prediction_head[-1].weight.fill_(float("nan"))
    payload = _payload(_support(), "history_only")
    inputs = collate_feature_payloads([payload], "history_only")
    with pytest.raises(FloatingPointError, match="non-finite prediction"):
        model(inputs)
    prediction = torch.zeros((1, 11, 15, 2))
    truth = torch.zeros_like(prediction)
    truth[0, 0, 0, 0] = float("nan")
    with pytest.raises(FloatingPointError, match="finite"):
        masked_scene_ade_loss(prediction, truth, torch.ones((1, 11, 15), dtype=torch.bool))


def test_physical_metrics_match_the_existing_masked_xy_evaluator() -> None:
    prediction = np.zeros((1, 11, 15, 2), dtype=np.float32)
    truth = np.ones((1, 11, 15, 2), dtype=np.float64)
    mask = np.ones((1, 11, 15), dtype=np.bool_)
    mask[0, 0, 3] = False
    truth_rows = [
        [list(point) if mask[0, player, step] else None for player, point in enumerate(frame)]
        for step, frame in enumerate(truth[0].transpose(1, 0, 2))
    ]
    prediction_rows = [frame.tolist() for frame in prediction[0].transpose(1, 0, 2)]
    expected = masked_physical_trajectory_metrics((prediction_rows,), (truth_rows,), (1.0, 1.0))
    actual = physical_metrics(prediction, truth, mask)
    assert actual["ade_m"] == pytest.approx(expected.ade_m, abs=1e-12)
    assert actual["fde_m"] == pytest.approx(expected.fde_m, abs=1e-12)
    assert actual["xy_rmse_m"] == pytest.approx(expected.xy_rmse_m, abs=1e-12)


def test_synthetic_fit_commits_one_validation_selected_checkpoint(tmp_path) -> None:
    rng = np.random.default_rng(7)
    training_matches = tuple(f"train-{index}" for index in range(12))
    validation_matches = tuple(f"validation-{index}" for index in range(4))
    caches: dict[str, MatchCache] = {}
    for role, matches in (("training", training_matches), ("validation", validation_matches)):
        for match_id in matches:
            arrays = {
                "target_history": rng.normal(size=(1, 2, 11, 78)).astype(np.float32),
                "history_team_tracks": rng.normal(size=(1, 2, 3, 78)).astype(np.float32),
                "history_team_mask": np.ones((1, 2, 3), dtype=np.bool_),
                "history_ball": rng.normal(size=(1, 78)).astype(np.float32),
                "target_side": np.asarray([[1.0, -1.0]], dtype=np.float32),
                "future_ball": rng.normal(size=(1, 45)).astype(np.float32),
                "future_opponent_tracks": rng.normal(size=(1, 2, 3, 45)).astype(np.float32),
                "future_opponent_mask": np.ones((1, 2, 3), dtype=np.bool_),
                "target_absolute_xy": rng.normal(size=(1, 2, 11, 15, 2)).astype(np.float64),
                "target_displacement": rng.normal(size=(1, 2, 11, 15, 2)).astype(np.float64),
                "target_mask": np.ones((1, 2, 11, 15), dtype=np.bool_),
                "scoreable": np.ones((1, 2), dtype=np.bool_),
            }
            caches[match_id] = MatchCache(match_id, role, tmp_path, arrays)

    (tmp_path / "runs").mkdir()
    receipt = _fit_one(
        run_root=tmp_path,
        cache_by_match=caches,
        train_matches=training_matches,
        validation_matches=validation_matches,
        regime="future_ball",
        representation="absolute_xy",
        seed=1729,
        plan_sha256="1" * 64,
        protocol_sha256="2" * 64,
        population_sha256="3" * 64,
        target_mask_identity_sha256="4" * 64,
        environment_sha256="5" * 64,
        campaign_cpu_start=time.process_time(),
        campaign_wall_start=time.monotonic(),
    )
    assert receipt["status"] == "completed", (
        receipt.get("stopping_reason"),
        receipt.get("failure_type"),
        receipt.get("failure_message"),
        receipt.get("optimizer_steps"),
    )
    assert set(receipt["validation_match_metrics"]) == set(validation_matches)
    checks = receipt["validation_history"]
    assert checks[0]["step"] == 100
    assert all(item["step"] % 100 == 0 for item in checks)
    assert receipt["selected_step"] <= receipt["optimizer_steps"]
    run_dir = tmp_path / "runs" / receipt["run_id"].replace("|", "--")
    checkpoint = load_checkpoint_verified(run_dir / "checkpoint.pt", receipt["checkpoint_sha256"])
    assert checkpoint["metadata"]["selected_step"] == receipt["selected_step"]
    assert {path.name for path in (tmp_path / "runs").iterdir()} == {run_dir.name}
