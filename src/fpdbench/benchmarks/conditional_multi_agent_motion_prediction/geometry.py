"""Validated two-dimensional position shapes shared by motion tasks."""

import math
from collections.abc import Sequence

type XY = tuple[float, float]
type PositionFrame = tuple[XY, ...]
type PositionTrajectory = tuple[PositionFrame, ...]


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
