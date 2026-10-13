"""Protocol-aware scoring for the prospective SkillCorner trajectory study."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from fpdbench.evaluation.metrics import MaskedTrajectoryMetrics, TrajectoryMetrics
from fpdbench.evaluation.metrics.trajectory import masked_physical_trajectory_metrics

from .prospective_protocol import load_prospective_protocol

type DirectedScenePrediction = Sequence[Sequence[Sequence[float]]]
type DirectedSceneTruth = Sequence[Sequence[Sequence[float] | None]]
type MatchPrediction = Sequence[Sequence[DirectedScenePrediction]]
type MatchTruth = Sequence[Sequence[DirectedSceneTruth]]
type EvaluationPrediction = Mapping[str, MatchPrediction]
type EvaluationTruth = Mapping[str, MatchTruth]

_PROTOCOL_STATE = cast(dict[str, object], load_prospective_protocol()["scientific_state"])
_PROTOCOL_SPLIT = cast(dict[str, object], _PROTOCOL_STATE["split"])
_PROTOCOL_ROLES = cast(dict[str, object], _PROTOCOL_SPLIT["roles"])
EVALUATION_MATCH_IDS = tuple(cast(list[str], _PROTOCOL_ROLES["evaluation"]))
FORECAST_SAMPLE_COUNT = 15
DIRECTED_SCENES_PER_WINDOW = 2


@dataclass(frozen=True, slots=True)
class DirectedSceneScore:
    metrics: MaskedTrajectoryMetrics | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class PhysicalWindowScore:
    scenes: tuple[DirectedSceneScore, ...]
    metrics: TrajectoryMetrics | None


@dataclass(frozen=True, slots=True)
class MatchScore:
    match_id: str
    windows: tuple[PhysicalWindowScore, ...]
    metrics: TrajectoryMetrics | None


@dataclass(frozen=True, slots=True)
class ProspectiveEvaluationScore:
    matches: tuple[MatchScore, ...]
    metrics: TrajectoryMetrics | None


def _mean_metrics(
    values: Sequence[MaskedTrajectoryMetrics | TrajectoryMetrics],
) -> TrajectoryMetrics:
    if not values:
        raise ValueError("at least one score is required for equal-weight aggregation")
    count = len(values)
    return TrajectoryMetrics(
        ade_m=math.fsum(value.ade_m for value in values) / count,
        fde_m=math.fsum(value.fde_m for value in values) / count,
        xy_rmse_m=math.fsum(value.xy_rmse_m for value in values) / count,
    )


def _score_scene(
    prediction: DirectedScenePrediction,
    truth: DirectedSceneTruth,
) -> DirectedSceneScore:
    if len(prediction) != FORECAST_SAMPLE_COUNT or len(truth) != FORECAST_SAMPLE_COUNT:
        raise ValueError("each directed scene must contain exactly 15 future samples")
    try:
        metrics = masked_physical_trajectory_metrics((prediction,), (truth,), scale_xy_m=(1.0, 1.0))
    except ValueError as exc:
        if str(exc) in {
            "trajectories contain no valid truth targets",
            "trajectories contain no valid final-horizon targets",
        }:
            return DirectedSceneScore(metrics=None, reason="NO_FINAL_TARGET")
        raise
    return DirectedSceneScore(metrics=metrics, reason=None)


def evaluate_prospective_trajectories(
    prediction: EvaluationPrediction,
    truth: EvaluationTruth,
) -> ProspectiveEvaluationScore:
    """Score every scene, window, and match using the locked equal-weight order.

    The mapping must contain the four fixed evaluation match IDs. Each match
    contains eligible windows, each with its home and away directed scenes.
    """
    if set(prediction) != set(EVALUATION_MATCH_IDS) or set(truth) != set(EVALUATION_MATCH_IDS):
        raise ValueError("prediction and truth must contain all four evaluation matches")
    match_scores: list[MatchScore] = []
    for match_id in EVALUATION_MATCH_IDS:
        predicted_match = prediction[match_id]
        actual_match = truth[match_id]
        if len(predicted_match) != len(actual_match):
            raise ValueError("prediction and truth must contain the same windows per match")
        window_scores: list[PhysicalWindowScore] = []
        for predicted_window, actual_window in zip(predicted_match, actual_match, strict=True):
            if (
                len(predicted_window) != DIRECTED_SCENES_PER_WINDOW
                or len(actual_window) != DIRECTED_SCENES_PER_WINDOW
            ):
                raise ValueError("each physical window must contain home and away directed scenes")
            scene_scores = tuple(
                _score_scene(predicted_scene, actual_scene)
                for predicted_scene, actual_scene in zip(
                    predicted_window, actual_window, strict=True
                )
            )
            scoreable_scenes = tuple(
                score.metrics for score in scene_scores if score.metrics is not None
            )
            window_metrics = _mean_metrics(scoreable_scenes) if scoreable_scenes else None
            window_scores.append(PhysicalWindowScore(scene_scores, window_metrics))
        scoreable_windows = tuple(
            window.metrics for window in window_scores if window.metrics is not None
        )
        match_metrics = _mean_metrics(scoreable_windows) if scoreable_windows else None
        match_scores.append(MatchScore(match_id, tuple(window_scores), match_metrics))

    match_metrics = tuple(match.metrics for match in match_scores)
    population_metrics = (
        _mean_metrics(tuple(metrics for metrics in match_metrics if metrics is not None))
        if all(metrics is not None for metrics in match_metrics)
        else None
    )
    return ProspectiveEvaluationScore(tuple(match_scores), population_metrics)


__all__ = [
    "DIRECTED_SCENES_PER_WINDOW",
    "EVALUATION_MATCH_IDS",
    "FORECAST_SAMPLE_COUNT",
    "DirectedSceneScore",
    "MatchScore",
    "PhysicalWindowScore",
    "ProspectiveEvaluationScore",
    "evaluate_prospective_trajectories",
]
