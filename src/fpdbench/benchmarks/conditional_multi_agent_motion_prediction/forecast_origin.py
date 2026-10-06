"""A forecast origin binds only information available at or before its time."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.geometry import (
    PositionFrame,
    immutable_xy_frame,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.information import (
    validate_information_boundary,
)


@dataclass(frozen=True, slots=True)
class ForecastOrigin:
    timestamp_s: float
    available_information_times_s: tuple[float, ...]
    feature_names: tuple[str, ...]
    target_origin_positions_m: PositionFrame | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.timestamp_s):
            raise ValueError("forecast origin timestamp must be finite")
        times = tuple(self.available_information_times_s)
        if not times or not all(math.isfinite(value) for value in times):
            raise ValueError("forecast origin requires finite observation timestamps")
        if any(left >= right for left, right in zip(times, times[1:], strict=False)):
            raise ValueError("observation timestamps must be strictly increasing")
        if times[-1] > self.timestamp_s:
            raise ValueError("future observations cross the causal forecast origin")
        feature_names = tuple(self.feature_names)
        validate_information_boundary(feature_names)
        object.__setattr__(self, "available_information_times_s", times)
        object.__setattr__(self, "feature_names", feature_names)
        if self.target_origin_positions_m is not None:
            positions = immutable_xy_frame(
                self.target_origin_positions_m,
                expected_entities=11,
                name="target positions at the forecast origin",
            )
            object.__setattr__(self, "target_origin_positions_m", positions)

    @classmethod
    def from_observations(
        cls,
        timestamp_s: float,
        available_information_times_s: Sequence[float],
        feature_names: Sequence[str],
        target_origin_positions_m: Sequence[Sequence[float]] | None = None,
    ) -> ForecastOrigin:
        positions = (
            None
            if target_origin_positions_m is None
            else immutable_xy_frame(
                target_origin_positions_m,
                expected_entities=11,
                name="target positions at the forecast origin",
            )
        )
        return cls(
            timestamp_s=timestamp_s,
            available_information_times_s=tuple(available_information_times_s),
            feature_names=tuple(feature_names),
            target_origin_positions_m=positions,
        )
