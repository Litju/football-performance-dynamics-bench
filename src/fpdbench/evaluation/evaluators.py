"""Reusable raw evaluators and diagnostic quality transforms."""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from fpdbench.evaluation.configuration import EvaluatorConfiguration
from fpdbench.evaluation.metrics import population_standardized_relative_error, rmse

SENSOR_GATE_MAX_QUALITY = 0.30
SENSOR_CORRUPTION_MIN_ROWS_PER_CHANNEL = 256

SIGNED_TANGENTIAL_ACCELERATION_EVALUATOR = EvaluatorConfiguration.from_state(
    "signed_tangential_acceleration.global_full_row_rmse",
    "1.0.0",
    {"aggregation": "global full-row RMSE", "normalization": "none", "unit": "m/s^2"},
)
SENSOR_STATE_EVALUATOR = EvaluatorConfiguration.from_state(
    "multimodal_sensor_state.equal_channel_population_sre",
    "1.0.0",
    {
        "aggregation": "equal arithmetic mean across channels",
        "corruption_region_minimum_rows_per_channel": "256",
        "metric_id": "sre.rmse_over_population_std.v1",
        "q_transform": "clamp(1-SRE,0,1)",
        "zero_variance_policy": "error",
    },
)
SENSOR_STATE_PUBLIC_NONEXPERT_GATE = EvaluatorConfiguration.from_state(
    "multimodal_sensor_state.public_nonexpert_quality_gate",
    "1.0.0",
    {"maximum_quality_inclusive": "0.30", "population": "public non-expert"},
)


@dataclass(frozen=True, slots=True)
class SignedTangentialAccelerationEvaluation:
    rmse_m_s2: float
    scored_samples: int
    normalization: str = "none"
    aggregation: str = "global full-row RMSE"


def evaluate_signed_tangential_acceleration(
    prediction_m_s2: Sequence[float], truth_m_s2: Sequence[float]
) -> SignedTangentialAccelerationEvaluation:
    """Recovered B1/B4 global RMSE; no lost B5 submetric is inferred."""
    return SignedTangentialAccelerationEvaluation(
        rmse_m_s2=rmse(prediction_m_s2, truth_m_s2),
        scored_samples=len(truth_m_s2),
    )


def quality_from_sre(raw_sre: float) -> float:
    if not math.isfinite(raw_sre):
        raise ValueError("SRE must be finite")
    return min(1.0, max(0.0, 1.0 - raw_sre))


@dataclass(frozen=True, slots=True)
class SensorStateChannelMetrics:
    per_channel_sre: tuple[tuple[str, float], ...]
    per_channel_quality: tuple[tuple[str, float], ...]
    mean_sre: float
    mean_quality: float


def evaluate_sensor_state_channels(
    predictions: Mapping[str, Sequence[float]],
    truths: Mapping[str, Sequence[float]],
    *,
    region_mask: Sequence[bool] | None = None,
) -> SensorStateChannelMetrics:
    """Return equal-channel SRE/q diagnostics; constant truth fails closed."""
    if not predictions or predictions.keys() != truths.keys():
        raise ValueError("nonempty identical channel sets are required")
    if region_mask is not None:
        if any(
            len(values) != len(region_mask) for values in (*predictions.values(), *truths.values())
        ):
            raise ValueError("region mask and channel vectors must have equal lengths")
        selected = tuple(index for index, include in enumerate(region_mask) if include)
        if len(selected) < SENSOR_CORRUPTION_MIN_ROWS_PER_CHANNEL:
            raise ValueError("corruption region requires 256 rows per channel")
        predictions = {
            name: tuple(values[index] for index in selected) for name, values in predictions.items()
        }
        truths = {
            name: tuple(values[index] for index in selected) for name, values in truths.items()
        }
    per_channel_sre = tuple(
        (
            name,
            population_standardized_relative_error(
                predictions[name], truths[name], zero_variance="error"
            ),
        )
        for name in sorted(truths)
    )
    per_channel_quality = tuple((name, quality_from_sre(value)) for name, value in per_channel_sre)
    return SensorStateChannelMetrics(
        per_channel_sre=per_channel_sre,
        per_channel_quality=per_channel_quality,
        mean_sre=sum(value for _, value in per_channel_sre) / len(per_channel_sre),
        mean_quality=sum(value for _, value in per_channel_quality) / len(per_channel_quality),
    )


@dataclass(frozen=True, slots=True)
class QualityGateResult:
    maximum_public_nonexpert_quality: float
    threshold: float = SENSOR_GATE_MAX_QUALITY
    passes: bool = False


def evaluate_sensor_state_gate(public_nonexpert_qualities: Sequence[float]) -> QualityGateResult:
    if not public_nonexpert_qualities or not all(
        math.isfinite(value) for value in public_nonexpert_qualities
    ):
        raise ValueError("gate requires finite public-only non-expert qualities")
    maximum = max(public_nonexpert_qualities)
    return QualityGateResult(maximum, passes=maximum <= SENSOR_GATE_MAX_QUALITY)


__all__ = [
    "QualityGateResult",
    "SENSOR_CORRUPTION_MIN_ROWS_PER_CHANNEL",
    "SENSOR_GATE_MAX_QUALITY",
    "SENSOR_STATE_EVALUATOR",
    "SENSOR_STATE_PUBLIC_NONEXPERT_GATE",
    "SIGNED_TANGENTIAL_ACCELERATION_EVALUATOR",
    "SensorStateChannelMetrics",
    "SignedTangentialAccelerationEvaluation",
    "evaluate_sensor_state_channels",
    "evaluate_sensor_state_gate",
    "evaluate_signed_tangential_acceleration",
    "quality_from_sre",
]
