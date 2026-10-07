"""Raw origin-relative displacement scorer with frozen public semantics."""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from fpdbench.evaluation.configuration import EvaluatorConfiguration
from fpdbench.evaluation.metrics import population_standardized_relative_error
from fpdbench.evaluation.metrics.relative_error import ZeroVariancePolicy
from fpdbench.unknown import UNKNOWN, UnknownValue

DISPLACEMENT_TARGET_COUNT = 330


@dataclass(frozen=True, slots=True)
class GeneratedCalibrationContract:
    """Known wrapper metadata; unrecovered displacement calibration stays UNKNOWN."""

    lower_is_better: bool = True
    target_weight: float = 1.0
    floor: float = 1.0
    perfect: float = 0.0
    quality_floor_mode: str = "effective_no_info"
    naive_score_bounds: tuple[float, float] = (1e-6, 0.10)
    calibration_lock_state: str | UnknownValue = UNKNOWN
    reference_vector: tuple[float, ...] | UnknownValue = UNKNOWN
    no_information_ceiling_vector: tuple[float, ...] | UnknownValue = UNKNOWN
    x_ref: float | UnknownValue = UNKNOWN
    calibrated_reward: float | UnknownValue = UNKNOWN

    def __post_init__(self) -> None:
        known_calibration = (
            self.calibration_lock_state is not UNKNOWN
            and self.reference_vector is not UNKNOWN
            and self.no_information_ceiling_vector is not UNKNOWN
            and self.x_ref is not UNKNOWN
        )
        if self.calibrated_reward is not UNKNOWN and not known_calibration:
            raise ValueError("calibrated reward requires a known calibration lock and inputs")


@dataclass(frozen=True, slots=True)
class RawDisplacementEvaluatorConfiguration:
    metric_id: str = "sre.rmse_over_population_std.v1"
    target_type: str = "PopulationSRETarget"
    target_count: int = DISPLACEMENT_TARGET_COUNT
    degrees_of_freedom: int = 0
    standard_deviation_population: str = "evaluated population truth per scalar target"
    per_target_weight: float = 1.0
    aggregation: str = "equal arithmetic mean across scalar targets"
    raw_clipping: tuple[float, float] | None = None
    zero_variance_policy: ZeroVariancePolicy = "rmse"
    lower_is_better: bool = True
    perfect_score: float = 0.0
    population_mean_predictor_sre: float = 1.0
    no_information_condition: str = "target variance is nonzero"

    @property
    def formula(self) -> str:
        return f"RMSE(prediction, truth) / population_std(truth, ddof={self.degrees_of_freedom})"

    def scientific_state(self) -> dict[str, str]:
        clipping = "none" if self.raw_clipping is None else ",".join(map(str, self.raw_clipping))
        return {
            "aggregation": self.aggregation,
            "degrees_of_freedom": str(self.degrees_of_freedom),
            "formula": self.formula,
            "lower_is_better": str(self.lower_is_better).lower(),
            "metric_id": self.metric_id,
            "no_information_condition": self.no_information_condition,
            "no_information_raw_sre": str(self.population_mean_predictor_sre),
            "population": self.standard_deviation_population,
            "raw_clipping": clipping,
            "raw_perfect_score": str(self.perfect_score),
            "per_target_weight": str(self.per_target_weight),
            "target_count": str(self.target_count),
            "target_type": self.target_type,
            "zero_variance_policy": self.zero_variance_policy,
        }


RAW_DISPLACEMENT_EVALUATOR = RawDisplacementEvaluatorConfiguration()
DISPLACEMENT_GENERATED_CALIBRATION = GeneratedCalibrationContract()
RAW_DISPLACEMENT_EVALUATOR_CONFIGURATION: EvaluatorConfiguration = (
    EvaluatorConfiguration.from_state(
        "origin_relative_displacement_raw_population_sre",
        "1.0.0",
        RAW_DISPLACEMENT_EVALUATOR.scientific_state(),
        description="330 equal-weight evaluated-population scalar SRE targets.",
    )
)


def raw_evaluator_scientific_state(
    evaluator: RawDisplacementEvaluatorConfiguration = RAW_DISPLACEMENT_EVALUATOR,
) -> dict[str, str]:
    return evaluator.scientific_state()


def raw_evaluator_hash(
    evaluator: RawDisplacementEvaluatorConfiguration = RAW_DISPLACEMENT_EVALUATOR,
) -> str:
    return EvaluatorConfiguration.from_state(
        "origin_relative_displacement_raw_population_sre",
        "1.0.0",
        raw_evaluator_scientific_state(evaluator),
    ).scientific_config_sha256


def evaluate_population_sre_targets(
    prediction_targets: Sequence[Sequence[float]],
    truth_targets: Sequence[Sequence[float]],
    *,
    zero_variance: ZeroVariancePolicy = "rmse",
) -> tuple[float, ...]:
    """Return one evaluation-population SRE per ordered scalar target."""
    if len(prediction_targets) != DISPLACEMENT_TARGET_COUNT or len(truth_targets) != (
        DISPLACEMENT_TARGET_COUNT
    ):
        raise ValueError("PopulationSRETarget evaluation requires exactly 330 scalar targets")
    if not truth_targets[0] or len(prediction_targets[0]) != len(truth_targets[0]):
        raise ValueError("each scalar target needs the same nonempty evaluated population")
    population_rows = len(truth_targets[0])
    if any(
        len(predicted) != population_rows or len(actual) != population_rows
        for predicted, actual in zip(prediction_targets, truth_targets, strict=True)
    ):
        raise ValueError("all scalar targets must use the same evaluated population")
    return tuple(
        population_standardized_relative_error(predicted, actual, zero_variance=zero_variance)
        for predicted, actual in zip(prediction_targets, truth_targets, strict=True)
    )


@dataclass(frozen=True, slots=True)
class RawDisplacementSRE:
    per_scalar_sre: tuple[float, ...]
    raw_sre: float
    population_rows: int

    def __post_init__(self) -> None:
        if len(self.per_scalar_sre) != DISPLACEMENT_TARGET_COUNT:
            raise ValueError("raw displacement SRE must contain 330 scalar targets")
        if any(not math.isfinite(score) or score < 0 for score in self.per_scalar_sre):
            raise ValueError("per-scalar displacement SRE values must be finite and nonnegative")
        if self.population_rows <= 0 or not math.isfinite(self.raw_sre):
            raise ValueError("raw displacement SRE requires a finite score and nonempty population")
        if self.raw_sre != math.fsum(self.per_scalar_sre) / DISPLACEMENT_TARGET_COUNT:
            raise ValueError("raw displacement SRE must be the equal-weight arithmetic mean")


def evaluate_raw_displacement_sre(
    prediction_targets: Sequence[Sequence[float]],
    truth_targets: Sequence[Sequence[float]],
) -> RawDisplacementSRE:
    """Aggregate 330 ordered scalar PopulationSRETarget values equally."""
    scores = evaluate_population_sre_targets(
        prediction_targets,
        truth_targets,
        zero_variance=RAW_DISPLACEMENT_EVALUATOR.zero_variance_policy,
    )
    return RawDisplacementSRE(
        per_scalar_sre=scores,
        raw_sre=math.fsum(scores) / len(scores),
        population_rows=len(truth_targets[0]),
    )


__all__ = [
    "DISPLACEMENT_TARGET_COUNT",
    "DISPLACEMENT_GENERATED_CALIBRATION",
    "GeneratedCalibrationContract",
    "RAW_DISPLACEMENT_EVALUATOR",
    "RAW_DISPLACEMENT_EVALUATOR_CONFIGURATION",
    "RawDisplacementEvaluatorConfiguration",
    "RawDisplacementSRE",
    "evaluate_raw_displacement_sre",
    "evaluate_population_sre_targets",
    "raw_evaluator_hash",
    "raw_evaluator_scientific_state",
]
