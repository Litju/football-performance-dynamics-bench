"""Frozen, target-only deterministic trajectory baselines."""

import math
from collections.abc import Sequence


def predict_baseline(
    model: str, history: Sequence[tuple[float, float] | None]
) -> tuple[tuple[float, float], ...]:
    """Predict physical XY at 0.2-second intervals from six historical samples."""
    if model not in {"origin_persistence_v1", "constant_velocity_1s_v1"}:
        raise ValueError("unknown deterministic baseline")
    if len(history) != 6 or history[-1] is None or not all(map(math.isfinite, history[-1])):
        raise ValueError("six samples and a finite origin are required")
    origin = history[-1]
    points = [
        ((index - 5) * 0.2, point)
        for index, point in enumerate(history)
        if point is not None and all(map(math.isfinite, point))
    ]
    if model == "origin_persistence_v1" or len(points) < 2:
        return (origin,) * 15
    mean_t = sum(t for t, _ in points) / len(points)
    denom = sum((t - mean_t) ** 2 for t, _ in points)
    means = tuple(sum(p[i] for _, p in points) / len(points) for i in range(2))
    slopes = tuple(
        sum((t - mean_t) * (p[i] - means[i]) for t, p in points) / denom for i in range(2)
    )
    return tuple(
        (means[0] + slopes[0] * (step * 0.2 - mean_t), means[1] + slopes[1] * (step * 0.2 - mean_t))
        for step in range(1, 16)
    )


def predict_displacement(
    model: str, history: Sequence[tuple[float, float] | None]
) -> tuple[tuple[float, float], ...]:
    """Express the same physical predictions relative to the observed origin."""
    prediction = predict_baseline(model, history)
    origin = history[-1]
    assert origin is not None
    return tuple((x - origin[0], y - origin[1]) for x, y in prediction)
