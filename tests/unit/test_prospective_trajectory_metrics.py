from __future__ import annotations

import math

import pytest

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.prospective_evaluator import (
    EVALUATION_MATCH_IDS,
    evaluate_prospective_trajectories,
)


def _scene(error: float, targets: int = 1) -> tuple[tuple[object, ...], tuple[object, ...]]:
    prediction = tuple(tuple((error, 0.0) for _ in range(targets)) for _ in range(15))
    truth = tuple(tuple((0.0, 0.0) for _ in range(targets)) for _ in range(15))
    return prediction, truth


def _window(
    *scenes: tuple[tuple[object, ...], tuple[object, ...]],
) -> tuple[tuple[object, ...], tuple[object, ...]]:
    return tuple(scene[0] for scene in scenes), tuple(scene[1] for scene in scenes)


def _match(
    *windows: tuple[tuple[object, ...], tuple[object, ...]],
) -> tuple[tuple[object, ...], tuple[object, ...]]:
    return tuple(window[0] for window in windows), tuple(window[1] for window in windows)


def _evaluate(*matches: tuple[tuple[object, ...], tuple[object, ...]]):
    return evaluate_prospective_trajectories(
        dict(zip(EVALUATION_MATCH_IDS, (match[0] for match in matches), strict=True)),
        dict(zip(EVALUATION_MATCH_IDS, (match[1] for match in matches), strict=True)),
    )


def test_no_final_target_excludes_the_whole_directed_scene() -> None:
    scoreable = _scene(1.0)
    no_final_target = (
        tuple(((100.0, 0.0),) for _ in range(15)),
        (((0.0, 0.0),), *((None,) for _ in range(14))),
    )
    match = _match(
        _window(scoreable, no_final_target),
        _window(no_final_target, no_final_target),
    )

    result = _evaluate(match, match, match, match)
    first_window = result.matches[0].windows[0]

    assert first_window.scenes[1].metrics is None
    assert first_window.scenes[1].reason == "NO_FINAL_TARGET"
    assert first_window.metrics is not None
    assert first_window.metrics.ade_m == pytest.approx(1.0)
    assert result.matches[0].windows[1].metrics is None
    assert result.matches[0].metrics is not None
    assert result.matches[0].metrics.ade_m == pytest.approx(1.0)
    assert result.metrics is not None
    assert result.metrics.ade_m == pytest.approx(1.0)
    assert (
        sum(
            scene.reason == "NO_FINAL_TARGET"
            for match_score in result.matches
            for window_score in match_score.windows
            for scene in window_score.scenes
        )
        == 12
    )


def test_scene_window_and_match_aggregation_are_equal_weighted() -> None:
    first_window = _window(_scene(0.0), _scene(6.0, targets=3))
    second_window = _window(_scene(10.0), _scene(10.0))
    first_match = _match(first_window, second_window)
    other_match = _match(_window(_scene(0.0), _scene(0.0)))

    result = _evaluate(first_match, other_match, other_match, other_match)

    assert result.matches[0].windows[0].metrics is not None
    assert result.matches[0].windows[0].metrics.ade_m == pytest.approx(3.0)
    assert result.matches[0].metrics is not None
    assert result.matches[0].metrics.ade_m == pytest.approx(6.5)
    assert result.metrics is not None
    assert result.metrics.ade_m == pytest.approx(1.625)
    assert result.matches[0].windows[0].scenes[1].metrics is not None
    assert result.matches[0].windows[0].scenes[1].metrics.scored_points == 45


def test_match_without_scoreable_scenes_makes_population_mean_null() -> None:
    valid_match = _match(_window(_scene(0.0), _scene(0.0)))
    null_scene = (tuple(((1.0, 0.0),) for _ in range(15)), tuple((None,) for _ in range(15)))
    unscoreable_match = _match(_window(null_scene, null_scene))

    result = _evaluate(valid_match, valid_match, valid_match, unscoreable_match)

    assert result.matches[3].metrics is None
    assert result.metrics is None


def test_invalid_prediction_fails_even_when_truth_is_null() -> None:
    bad_prediction = tuple(
        (((math.nan, 0.0),) if index == 0 else ((1.0, 0.0),)) for index in range(15)
    )
    no_truth = tuple((None,) for _ in range(15))
    bad_scene = (bad_prediction, no_truth)
    match = _match(_window(bad_scene, _scene(0.0)))

    with pytest.raises(ValueError, match="predictions must contain finite XY pairs"):
        _evaluate(match, match, match, match)


def test_null_truth_xy_masks_only_that_target_sample_and_partial_xy_is_invalid() -> None:
    prediction = tuple(
        (((1.0, 0.0), (100.0, 0.0)) if index == 0 else ((3.0, 0.0), (4.0, 0.0)))
        for index in range(15)
    )
    truth = tuple(
        (
            ((0.0, 0.0), None)
            if index == 0
            else ((0.0, 0.0), (0.0, 0.0))
            if index == 14
            else (None, None)
        )
        for index in range(15)
    )
    scene = (prediction, truth)
    match = _match(_window(scene, scene))

    result = _evaluate(match, match, match, match)
    metrics = result.matches[0].windows[0].scenes[0].metrics

    assert metrics is not None
    assert metrics.scored_points == 3
    assert metrics.final_targets == 2
    assert metrics.ade_m == pytest.approx(8.0 / 3.0)
    assert metrics.fde_m == pytest.approx(3.5)
    assert metrics.xy_rmse_m == pytest.approx(math.sqrt(26.0 / 6.0))

    partial_truth = tuple(
        (
            ((0.0, None), None)
            if index == 0
            else ((0.0, 0.0), (0.0, 0.0))
            if index == 14
            else (None, None)
        )
        for index in range(15)
    )
    bad_scene = (prediction, partial_truth)
    bad_match = _match(_window(bad_scene, scene))
    with pytest.raises(ValueError, match="finite XY pairs or a null XY mask"):
        _evaluate(bad_match, bad_match, bad_match, bad_match)
