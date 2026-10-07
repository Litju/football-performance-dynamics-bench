"""RMSE and population-standardized relative error."""

import math
from collections.abc import Sequence
from typing import Literal

ZeroVariancePolicy = Literal["error", "rmse"]
RMSE_METRIC_ID = "rmse.global.v1"
POPULATION_SRE_METRIC_ID = "sre.rmse_over_population_std.v1"


def rmse(prediction: Sequence[float], truth: Sequence[float]) -> float:
    if len(prediction) != len(truth) or not truth:
        raise ValueError("prediction and truth must have the same nonzero length")
    if not all(math.isfinite(value) for value in (*prediction, *truth)):
        raise ValueError("prediction and truth must be finite")
    return math.sqrt(
        sum((predicted - actual) ** 2 for predicted, actual in zip(prediction, truth, strict=True))
        / len(truth)
    )


def population_standardized_relative_error(
    prediction: Sequence[float],
    truth: Sequence[float],
    *,
    zero_variance: ZeroVariancePolicy = "error",
) -> float:
    """RMSE divided by population SD (ddof=0), with an explicit zero-SD policy."""
    error = rmse(prediction, truth)
    mean = sum(truth) / len(truth)
    variance = sum((value - mean) ** 2 for value in truth) / len(truth)
    standard_deviation = math.sqrt(variance)
    if standard_deviation == 0:
        if zero_variance == "rmse":
            return error
        if zero_variance != "error":
            raise ValueError(f"unknown zero-variance policy: {zero_variance}")
        raise ValueError("population SRE is undefined for constant truth")
    if zero_variance not in ("error", "rmse"):
        raise ValueError(f"unknown zero-variance policy: {zero_variance}")
    return error / standard_deviation
