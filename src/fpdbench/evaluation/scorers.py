"""Exact historical absolute-position evaluator and calibrated scorer."""

import hashlib
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from fpdbench.evaluation.calibration import PiecewiseLinearTransform
from fpdbench.evaluation.configuration import EvaluatorConfiguration
from fpdbench.evaluation.displacement import evaluate_population_sre_targets
from fpdbench.evaluation.metrics import PositionTrajectory, immutable_xy_trajectory

ABSOLUTE_POSITION_TARGET_SHAPE = (15, 11, 2)
ABSOLUTE_POSITION_TARGET_COUNT = math.prod(ABSOLUTE_POSITION_TARGET_SHAPE)
ABSOLUTE_POSITION_CALIBRATION_LOCK_SHA256 = (
    "f3b4155899c5d8e9632e9cab7a25e471411c62c4a9a7489c58c1edb16180ce94"
)
ABSOLUTE_POSITION_EVALUATOR_SOURCE_SHA256 = (
    "41db5a6fb1d4a05db0bf2060b96336a2c3e86ec9ab25dfd7aaa16390e0c0defa"
)
ABSOLUTE_POSITION_TARGET_IDS = tuple(
    f"sre_t{step:02d}_p{player:02d}_{axis}"
    for step in range(1, ABSOLUTE_POSITION_TARGET_SHAPE[0] + 1)
    for player in range(1, ABSOLUTE_POSITION_TARGET_SHAPE[1] + 1)
    for axis in ("x", "y")
)


@dataclass(frozen=True, slots=True)
class AbsolutePositionTargetCalibration:
    target_id: str
    weight: float
    reference_sre: float
    raw_floor: float
    no_information_ceiling: float

    @property
    def effective_floor(self) -> float:
        return min(self.raw_floor, self.no_information_ceiling)


@dataclass(frozen=True, slots=True)
class AbsolutePositionCalibration:
    source_sha256: str
    schema_version: str
    policy: str
    quality_floor_mode: str
    targets: tuple[AbsolutePositionTargetCalibration, ...]
    transform: PiecewiseLinearTransform
    x_ref: float
    reference_score: float


def _load_calibration() -> AbsolutePositionCalibration:
    content = Path(__file__).with_name("absolute_xy_calibration_lock.json").read_bytes()
    source_sha256 = hashlib.sha256(content).hexdigest()
    if source_sha256 != ABSOLUTE_POSITION_CALIBRATION_LOCK_SHA256:
        raise RuntimeError("absolute-position calibration lock does not match its evidence SHA-256")
    lock = cast(dict[str, object], json.loads(content))
    records = cast(dict[str, dict[str, object]], lock["targets"])
    if tuple(records) != ABSOLUTE_POSITION_TARGET_IDS:
        raise RuntimeError("absolute-position calibration target order/geometry changed")
    targets = tuple(
        AbsolutePositionTargetCalibration(
            target_id=name,
            weight=cast(float, record["weight"]),
            reference_sre=cast(float, record["reference"]),
            raw_floor=cast(float, record["raw_floor"]),
            no_information_ceiling=cast(float, record["no_info_ceiling"]),
        )
        for name, record in records.items()
    )
    curve = cast(dict[str, object], lock["curve"])
    knots_raw = cast(list[list[float]], curve["knots"])
    knots = tuple((knot[0], knot[1]) for knot in knots_raw)
    qualification = cast(dict[str, object], lock["qualification"])
    return AbsolutePositionCalibration(
        source_sha256=source_sha256,
        schema_version=str(lock["schema_version"]),
        policy=str(lock["policy"]),
        quality_floor_mode=str(lock["quality_floor_mode"]),
        targets=targets,
        transform=PiecewiseLinearTransform(knots),
        x_ref=cast(float, curve["x_ref"]),
        reference_score=cast(float, qualification["reference_score"]),
    )


ABSOLUTE_POSITION_CALIBRATION = _load_calibration()
ABSOLUTE_POSITION_RAW_EVALUATOR = EvaluatorConfiguration.from_state(
    "absolute_position.population_sre_targets",
    "1.0.0",
    {
        "degrees_of_freedom": "0",
        "metric_id": "sre.rmse_over_population_std.v1",
        "population": "evaluated truth rows per scalar target",
        "target_count": str(ABSOLUTE_POSITION_TARGET_COUNT),
        "target_order": "forecast timestep, player, x then y",
        "target_representation": "absolute pitch-normalized XY",
        "zero_variance_policy": "RMSE fallback",
    },
    provenance=(f"registry://sha256/{ABSOLUTE_POSITION_EVALUATOR_SOURCE_SHA256}",),
)
ABSOLUTE_POSITION_PROGRESS_TRANSFORM = EvaluatorConfiguration.from_state(
    "absolute_position.per_target_progress",
    "1.0.0",
    {
        "aggregation": "weighted arithmetic mean of per-target progress",
        "clipping": "raw SRE unbounded; per-target progress clamped to [0,1]",
        "effective_floor": "min(raw floor, no-information ceiling)",
        "per_target_progress": "clamp(1 - raw SRE / effective floor, 0, 1)",
        "target_count": str(ABSOLUTE_POSITION_TARGET_COUNT),
        "target_weighting": "calibration lock target weights; equal 1/330",
    },
    calibration_sha256=ABSOLUTE_POSITION_CALIBRATION_LOCK_SHA256,
)
ABSOLUTE_POSITION_HISTORICAL_SCORER = EvaluatorConfiguration.from_state(
    "absolute_position.historical_continuous_pwl_v3",
    "1.0.0",
    {
        "direction": "higher progress produces higher score",
        "input": "weighted aggregate progress",
        "score_bounds": "0,1",
        "transform": "clamped continuous piecewise-linear calibration",
    },
    calibration_sha256=ABSOLUTE_POSITION_CALIBRATION_LOCK_SHA256,
    description="Exact recovered absolute-XY calibrated scorer.",
    provenance=(
        f"registry://sha256/{ABSOLUTE_POSITION_EVALUATOR_SOURCE_SHA256}",
        f"registry://sha256/{ABSOLUTE_POSITION_CALIBRATION_LOCK_SHA256}",
    ),
)


@dataclass(frozen=True, slots=True)
class AbsolutePositionRawEvaluation:
    per_target_sre: tuple[tuple[str, float], ...]
    population_rows: int

    def __post_init__(self) -> None:
        names = tuple(name for name, _ in self.per_target_sre)
        if len(names) != ABSOLUTE_POSITION_TARGET_COUNT or len(set(names)) != len(names):
            raise ValueError("absolute-position raw evaluation must contain 330 unique targets")
        if any(not math.isfinite(value) or value < 0 for _, value in self.per_target_sre):
            raise ValueError("absolute-position target SRE values must be finite and nonnegative")
        if self.population_rows <= 0:
            raise ValueError("absolute-position raw evaluation needs a nonempty population")


@dataclass(frozen=True, slots=True)
class AbsolutePositionProgress:
    per_target_progress: tuple[tuple[str, float], ...]
    aggregate_progress: float

    def __post_init__(self) -> None:
        names = tuple(name for name, _ in self.per_target_progress)
        if len(names) != ABSOLUTE_POSITION_TARGET_COUNT or len(set(names)) != len(names):
            raise ValueError("absolute-position progress must contain 330 unique targets")
        if any(
            not math.isfinite(value) or not 0.0 <= value <= 1.0
            for _, value in self.per_target_progress
        ):
            raise ValueError("absolute-position per-target progress must be within [0,1]")
        if not math.isfinite(self.aggregate_progress) or not 0.0 <= self.aggregate_progress <= 1.0:
            raise ValueError("absolute-position aggregate progress must be within [0,1]")


@dataclass(frozen=True, slots=True)
class AbsolutePositionScoredResult:
    aggregate_progress: float
    score: float


def evaluate_absolute_position_population_sre(
    prediction: Sequence[PositionTrajectory], truth: Sequence[PositionTrajectory]
) -> AbsolutePositionRawEvaluation:
    """Compute ordered per-target SREs across evaluated absolute-XY rows."""
    if not truth or len(prediction) != len(truth):
        raise ValueError("prediction and truth must have the same nonempty population")
    steps, entities, _ = ABSOLUTE_POSITION_TARGET_SHAPE
    prediction_rows = tuple(
        immutable_xy_trajectory(
            row,
            expected_steps=steps,
            expected_entities=entities,
            name=f"prediction[{index}]",
        )
        for index, row in enumerate(prediction)
    )
    truth_rows = tuple(
        immutable_xy_trajectory(
            row,
            expected_steps=steps,
            expected_entities=entities,
            name=f"truth[{index}]",
        )
        for index, row in enumerate(truth)
    )
    prediction_targets = tuple(
        tuple(prediction_rows[row][step][player][axis] for row in range(len(truth_rows)))
        for step in range(steps)
        for player in range(entities)
        for axis in range(2)
    )
    truth_targets = tuple(
        tuple(truth_rows[row][step][player][axis] for row in range(len(truth_rows)))
        for step in range(steps)
        for player in range(entities)
        for axis in range(2)
    )
    values = evaluate_population_sre_targets(prediction_targets, truth_targets)
    return AbsolutePositionRawEvaluation(
        per_target_sre=tuple(zip(ABSOLUTE_POSITION_TARGET_IDS, values, strict=True)),
        population_rows=len(truth_rows),
    )


def absolute_position_progress(raw: AbsolutePositionRawEvaluation) -> AbsolutePositionProgress:
    """Apply the locked per-target floor and equal-weight progress aggregation."""
    target_scores = dict(raw.per_target_sre)
    if len(target_scores) != ABSOLUTE_POSITION_TARGET_COUNT or set(target_scores) != set(
        ABSOLUTE_POSITION_TARGET_IDS
    ):
        raise ValueError("absolute-position progress requires the exact 330 registered targets")
    per_target: list[tuple[str, float]] = []
    weighted_progress = weight_sum = 0.0
    for target in ABSOLUTE_POSITION_CALIBRATION.targets:
        value = min(1.0, max(0.0, 1.0 - target_scores[target.target_id] / target.effective_floor))
        per_target.append((target.target_id, value))
        weighted_progress += target.weight * value
        weight_sum += target.weight
    aggregate_progress = weighted_progress / weight_sum
    return AbsolutePositionProgress(tuple(per_target), aggregate_progress)


def score_absolute_position(progress: AbsolutePositionProgress) -> AbsolutePositionScoredResult:
    """Apply the historical clamped piecewise-linear transform to aggregate progress."""
    target_progress = dict(progress.per_target_progress)
    if set(target_progress) != set(ABSOLUTE_POSITION_TARGET_IDS):
        raise ValueError("absolute-position score requires the exact 330 registered targets")
    weighted = weight_sum = 0.0
    for target in ABSOLUTE_POSITION_CALIBRATION.targets:
        weighted += target.weight * target_progress[target.target_id]
        weight_sum += target.weight
    aggregate_progress = progress.aggregate_progress
    if aggregate_progress != weighted / weight_sum:
        raise ValueError("absolute-position aggregate progress must equal weighted target progress")
    return AbsolutePositionScoredResult(
        aggregate_progress=aggregate_progress,
        score=ABSOLUTE_POSITION_CALIBRATION.transform.apply(aggregate_progress),
    )


__all__ = [
    "ABSOLUTE_POSITION_CALIBRATION",
    "ABSOLUTE_POSITION_CALIBRATION_LOCK_SHA256",
    "ABSOLUTE_POSITION_EVALUATOR_SOURCE_SHA256",
    "ABSOLUTE_POSITION_HISTORICAL_SCORER",
    "ABSOLUTE_POSITION_PROGRESS_TRANSFORM",
    "ABSOLUTE_POSITION_RAW_EVALUATOR",
    "ABSOLUTE_POSITION_TARGET_COUNT",
    "ABSOLUTE_POSITION_TARGET_IDS",
    "ABSOLUTE_POSITION_TARGET_SHAPE",
    "AbsolutePositionCalibration",
    "AbsolutePositionProgress",
    "AbsolutePositionRawEvaluation",
    "AbsolutePositionScoredResult",
    "AbsolutePositionTargetCalibration",
    "absolute_position_progress",
    "evaluate_absolute_position_population_sre",
    "score_absolute_position",
]
