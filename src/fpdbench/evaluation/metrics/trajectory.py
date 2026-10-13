"""ADE, FDE, and physical XY-RMSE for batched trajectories."""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from fpdbench.evaluation.configuration import EvaluatorConfiguration

type XY = tuple[float, float]
type PositionFrame = tuple[XY, ...]
type PositionTrajectory = tuple[PositionFrame, ...]
type TrajectoryBatch = Sequence[Sequence[Sequence[Sequence[float]]]]
type MaskedTrajectoryBatch = Sequence[Sequence[Sequence[Sequence[float] | None]]]
type ScaleXY = tuple[float, float]
PITCH_SCALE_M: ScaleXY = (52.5, 34.0)
ADE_METRIC_ID = "trajectory.ade_m.v1"
FDE_METRIC_ID = "trajectory.fde_m.v1"
XY_RMSE_METRIC_ID = "trajectory.xy_rmse_m.v1"
PHYSICAL_TRAJECTORY_EVALUATOR: EvaluatorConfiguration = EvaluatorConfiguration.from_state(
    "physical_trajectory.ade_fde_xy_rmse",
    "1.0.0",
    {
        "ade": "mean Euclidean distance over batch, entity, and timestep",
        "fde": "mean Euclidean distance over batch and entities at final timestep",
        "scale_xy_m": "52.5,34.0",
        "xy_rmse": "scalar-coordinate RMSE in metres over batch, entity, timestep, and x/y",
    },
    description="Physical trajectory diagnostics for pitch-normalized XY tasks.",
)


def immutable_xy_frame(
    values: Sequence[Sequence[float]], *, expected_entities: int | None, name: str
) -> PositionFrame:
    if expected_entities is not None and len(values) != expected_entities:
        raise ValueError(f"{name} must contain {expected_entities} entities")
    if not values:
        raise ValueError(f"{name} must be nonempty")
    frame: list[XY] = []
    for point in values:
        if len(point) != 2 or not all(math.isfinite(value) for value in point):
            raise ValueError(f"{name} coordinates must be finite XY pairs")
        frame.append((float(point[0]), float(point[1])))
    return tuple(frame)


def immutable_xy_vector(values: Sequence[float], *, name: str) -> XY:
    if len(values) != 2 or not all(math.isfinite(value) for value in values):
        raise ValueError(f"{name} must be a finite XY pair")
    return (float(values[0]), float(values[1]))


def immutable_xy_trajectory(
    values: Sequence[Sequence[Sequence[float]]],
    *,
    expected_steps: int | None,
    expected_entities: int | None,
    name: str,
) -> PositionTrajectory:
    if expected_steps is not None and len(values) != expected_steps:
        raise ValueError(f"{name} must contain {expected_steps} time steps")
    if not values:
        raise ValueError(f"{name} must contain at least one time step")
    return tuple(
        immutable_xy_frame(step, expected_entities=expected_entities, name=f"{name}[{index}]")
        for index, step in enumerate(values)
    )


@dataclass(frozen=True, slots=True)
class TrajectoryMetrics:
    ade_m: float
    fde_m: float
    xy_rmse_m: float


@dataclass(frozen=True, slots=True)
class MaskedTrajectoryMetrics:
    ade_m: float
    fde_m: float
    xy_rmse_m: float
    scored_points: int
    final_targets: int


def masked_physical_trajectory_metrics(
    prediction: TrajectoryBatch,
    truth: MaskedTrajectoryBatch,
    scale_xy_m: ScaleXY = (1.0, 1.0),
) -> MaskedTrajectoryMetrics:
    """Score variable-size target panels; a null truth XY pair is the only mask."""
    if len(prediction) != len(truth) or not prediction:
        raise ValueError("prediction and truth must contain the same nonempty batch")
    if len(scale_xy_m) != 2 or any(not math.isfinite(scale) or scale <= 0 for scale in scale_xy_m):
        raise ValueError("physical XY scales must contain two finite positive values")

    distance_sum = final_distance_sum = squared_sum = 0.0
    scored_points = final_targets = scalar_count = 0
    expected_steps: int | None = None
    for predicted, actual in zip(prediction, truth, strict=True):
        if not predicted or len(predicted) != len(actual):
            raise ValueError("each trajectory must have matching nonempty horizons")
        if expected_steps is None:
            expected_steps = len(predicted)
        elif len(predicted) != expected_steps:
            raise ValueError("all trajectories must use the same horizon")
        expected_entities: int | None = None
        for step_index, (predicted_step, actual_step) in enumerate(
            zip(predicted, actual, strict=True)
        ):
            if not predicted_step or len(predicted_step) != len(actual_step):
                raise ValueError("each time step must contain the same nonempty target panel")
            if expected_entities is None:
                expected_entities = len(predicted_step)
            elif len(predicted_step) != expected_entities:
                raise ValueError("target entity order and cardinality must stay fixed per scene")
            for predicted_xy_raw, actual_xy_raw in zip(predicted_step, actual_step, strict=True):
                try:
                    predicted_xy = immutable_xy_vector(
                        predicted_xy_raw, name="predicted physical XY"
                    )
                except (TypeError, ValueError) as exc:
                    raise ValueError("predictions must contain finite XY pairs") from exc
                if actual_xy_raw is None:
                    continue
                try:
                    actual_xy = immutable_xy_vector(actual_xy_raw, name="truth physical XY")
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        "truth must contain finite XY pairs or a null XY mask"
                    ) from exc
                dx = (predicted_xy[0] - actual_xy[0]) * scale_xy_m[0]
                dy = (predicted_xy[1] - actual_xy[1]) * scale_xy_m[1]
                distance = math.hypot(dx, dy)
                distance_sum += distance
                squared_sum += dx * dx + dy * dy
                scored_points += 1
                scalar_count += 2
                if step_index == len(predicted) - 1:
                    final_distance_sum += distance
                    final_targets += 1
    if not scored_points:
        raise ValueError("trajectories contain no valid truth targets")
    if not final_targets:
        raise ValueError("trajectories contain no valid final-horizon targets")
    return MaskedTrajectoryMetrics(
        ade_m=distance_sum / scored_points,
        fde_m=final_distance_sum / final_targets,
        xy_rmse_m=math.sqrt(squared_sum / scalar_count),
        scored_points=scored_points,
        final_targets=final_targets,
    )


def physical_trajectory_metrics(
    prediction: TrajectoryBatch,
    truth: TrajectoryBatch,
    scale_xy_m: ScaleXY = PITCH_SCALE_M,
) -> TrajectoryMetrics:
    """Compute global entity-step mean errors after pitch-normalized XY scaling."""
    if len(prediction) != len(truth) or not prediction:
        raise ValueError("prediction and truth must contain the same nonempty batch")
    if len(scale_xy_m) != 2:
        raise ValueError("physical XY scales must contain exactly two axes")
    if any(not math.isfinite(scale) or scale <= 0 for scale in scale_xy_m):
        raise ValueError("physical XY scales must be finite and positive")

    distance_sum = final_distance_sum = squared_sum = 0.0
    entity_steps = final_entities = scalar_count = 0
    expected_steps: int | None = None
    expected_entities: int | None = None
    for predicted, actual in zip(prediction, truth, strict=True):
        if len(predicted) == 0 or len(predicted) != len(actual):
            raise ValueError("each trajectory must have matching nonempty horizons")
        if expected_steps is None:
            expected_steps = len(predicted)
        elif len(predicted) != expected_steps:
            raise ValueError("all trajectories must use the same horizon")
        for step_index, (predicted_step, actual_step) in enumerate(
            zip(predicted, actual, strict=True)
        ):
            if not predicted_step or len(predicted_step) != len(actual_step):
                raise ValueError("each time step must have matching nonempty entities")
            if expected_entities is None:
                expected_entities = len(predicted_step)
            elif len(predicted_step) != expected_entities:
                raise ValueError("all time steps must contain the same entities")
            for predicted_xy, actual_xy in zip(predicted_step, actual_step, strict=True):
                if len(predicted_xy) != 2 or len(actual_xy) != 2:
                    raise ValueError("trajectory coordinates must have x and y components")
                if not all(math.isfinite(value) for value in (*predicted_xy, *actual_xy)):
                    raise ValueError("trajectory coordinates must be finite")
                dx = (predicted_xy[0] - actual_xy[0]) * scale_xy_m[0]
                dy = (predicted_xy[1] - actual_xy[1]) * scale_xy_m[1]
                distance = math.hypot(dx, dy)
                distance_sum += distance
                squared_sum += dx * dx + dy * dy
                entity_steps += 1
                scalar_count += 2
                if step_index == len(predicted) - 1:
                    final_distance_sum += distance
                    final_entities += 1
    if not entity_steps or not final_entities:
        raise ValueError("trajectories contain no scored coordinates")
    return TrajectoryMetrics(
        ade_m=distance_sum / entity_steps,
        fde_m=final_distance_sum / final_entities,
        xy_rmse_m=math.sqrt(squared_sum / scalar_count),
    )
