"""A checked, clamped piecewise-linear score transform."""

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PiecewiseLinearTransform:
    knots: tuple[tuple[float, float], ...]

    def __post_init__(self) -> None:
        if len(self.knots) < 2:
            raise ValueError("a piecewise-linear transform needs at least two knots")
        if not all(math.isfinite(x) and math.isfinite(y) for x, y in self.knots):
            raise ValueError("calibration knots must be finite")
        if any(
            a[0] >= b[0] or a[1] > b[1] for a, b in zip(self.knots, self.knots[1:], strict=False)
        ):
            raise ValueError("calibration x values must rise and y values must not fall")

    def apply(self, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("calibration input must be finite")
        if value <= self.knots[0][0]:
            return self.knots[0][1]
        if value >= self.knots[-1][0]:
            return self.knots[-1][1]
        for (left_x, left_y), (right_x, right_y) in zip(self.knots, self.knots[1:], strict=False):
            if left_x <= value <= right_x:
                fraction = (value - left_x) / (right_x - left_x)
                return left_y + fraction * (right_y - left_y)
        raise AssertionError("validated knots must span every finite input")
