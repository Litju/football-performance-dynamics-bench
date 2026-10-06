"""ADE, FDE, and physical XY-RMSE for batched trajectories."""

import math
from collections.abc import Sequence
from dataclasses import dataclass

type TrajectoryBatch = Sequence[Sequence[Sequence[Sequence[float]]]]
type ScaleXY = tuple[float, float]
PITCH_SCALE_M: ScaleXY = (52.5, 34.0)


@dataclass(frozen=True, slots=True)
class TrajectoryMetrics:
    ade_m: float
    fde_m: float
    xy_rmse_m: float


def physical_trajectory_metrics(
    prediction: TrajectoryBatch,
    truth: TrajectoryBatch,
    scale_xy_m: ScaleXY = PITCH_SCALE_M,
) -> TrajectoryMetrics:
    """Compute global entity-step mean errors after pitch-normalized XY scaling."""
    if len(prediction) != len(truth) or not prediction:
        raise ValueError("prediction and truth must contain the same nonempty batch")
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
