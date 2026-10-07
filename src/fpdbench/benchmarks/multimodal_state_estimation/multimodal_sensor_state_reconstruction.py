"""Unselected sensor-state pilot contracts and its diagnostic SRE/q/gate."""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from fpdbench.benchmarks.base import (
    UNKNOWN,
    CausalStatus,
    ExecutionStatus,
    InformationBoundary,
    ResearchObjectDefinition,
    ResearchObjectIdentity,
    ResearchObjectType,
    ScientificDescriptor,
    ScientificMaturity,
    ScientificTaskType,
    TechnicalTaskContract,
    TemporalContract,
)
from fpdbench.evaluation.evaluators import (
    SENSOR_CORRUPTION_MIN_ROWS_PER_CHANNEL as _SENSOR_CORRUPTION_MIN_ROWS_PER_CHANNEL,
)
from fpdbench.evaluation.evaluators import (
    SENSOR_GATE_MAX_QUALITY,
)
from fpdbench.evaluation.evaluators import (
    evaluate_sensor_state_channels as _evaluate_sensor_state_channels,
)
from fpdbench.evaluation.evaluators import (
    evaluate_sensor_state_gate as _evaluate_sensor_state_gate,
)
from fpdbench.evaluation.evaluators import (
    quality_from_sre as _quality_from_sre,
)

RESEARCH_OBJECT_ID = "multimodal_state_estimation/multimodal_sensor_state_reconstruction"
SENSOR_CORRUPTION_MIN_ROWS_PER_CHANNEL = _SENSOR_CORRUPTION_MIN_ROWS_PER_CHANNEL
quality_from_sre = _quality_from_sre


class SensorCandidateFamily(StrEnum):
    CLEAN_HORIZONTAL_MOTION = "clean_horizontal_motion_state"
    CLEAN_EXTERNAL_LOAD = "clean_external_load_temporal_state"
    JOINT_EXTERNAL_INTERNAL = "joint_external_internal_state"
    CORRUPTION_REGION = "corruption_region_reconstruction"


@dataclass(frozen=True, slots=True)
class ModalityContract:
    name: str
    fields: tuple[str, ...]
    native_rate_hz: float | None
    rate_approximate: bool = False
    recovery_gaps: tuple[str, ...] = ()


MODALITIES = (
    ModalityContract(
        "GNSS",
        ("position", "speed", "validity", "quality"),
        10.0,
        rate_approximate=True,
        recovery_gaps=("exact timestamps", "coordinate frame and units", "full channel schema"),
    ),
    ModalityContract(
        "IMU",
        ("acceleration", "gyroscope", "validity", "quality"),
        25.0,
        recovery_gaps=("exact timestamps", "axis calibration and units", "full channel schema"),
    ),
    ModalityContract(
        "heart_rate",
        ("heart-rate observations", "quality and validity where present"),
        1.0,
        recovery_gaps=("exact timestamps", "clean target mapping"),
    ),
    ModalityContract(
        "timestamps",
        ("per-observation times",),
        None,
        recovery_gaps=("IMU and heart-rate timestamp vectors", "missingness encoding"),
    ),
)

CANDIDATE_TARGET_FAMILIES = tuple(SensorCandidateFamily)
SELECTED_TARGET_FAMILY: None = None


@dataclass(frozen=True, slots=True)
class TimestampedObservation:
    timestamp_s: float
    values: tuple[float | None, ...]
    valid: bool | None = None
    quality: float | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.timestamp_s):
            raise ValueError("sensor observation timestamps must be finite")
        if not self.values:
            raise ValueError("sensor observations must contain at least one channel")
        if any(value is not None and not math.isfinite(value) for value in self.values):
            raise ValueError("present sensor values must be finite")
        if self.quality is not None and not math.isfinite(self.quality):
            raise ValueError("sensor quality must be finite")
        object.__setattr__(self, "values", tuple(self.values))


@dataclass(frozen=True, slots=True)
class NativeSensorStream:
    modality: str
    observations: tuple[TimestampedObservation, ...]

    def __post_init__(self) -> None:
        if not self.modality:
            raise ValueError("sensor modality is required")
        observations = tuple(self.observations)
        times = tuple(item.timestamp_s for item in observations)
        if any(left >= right for left, right in zip(times, times[1:], strict=False)):
            raise ValueError("native sensor timestamps must be strictly increasing")
        object.__setattr__(self, "observations", observations)

    def causal_prefix(self, query_time_s: float) -> tuple[TimestampedObservation, ...]:
        """Return available observations only; no hold, interpolation, or tie rule is inferred."""
        if not math.isfinite(query_time_s):
            raise ValueError("query time must be finite")
        return tuple(item for item in self.observations if item.timestamp_s <= query_time_s)


@dataclass(frozen=True, slots=True)
class TemporalAlignmentContract:
    candidate_target_hz: float
    native_rates_hz: tuple[tuple[str, float | None], ...]
    known_rule: str
    unresolved_behavior: tuple[str, ...]
    representation_selected: bool = False


TEMPORAL_ALIGNMENT = TemporalAlignmentContract(
    candidate_target_hz=10.0,
    native_rates_hz=(("GNSS", 10.0), ("IMU", 25.0), ("heart_rate", 1.0)),
    known_rule="Causal native observations are sampled or held at query times.",
    unresolved_behavior=(
        "Exact timestamps and time origin",
        "As-of, hold, age, tie, and missing-value behavior",
        "GNSS tolerance and common input channel set",
    ),
)


@dataclass(frozen=True, slots=True)
class SensorStateEvaluation:
    candidate_family: SensorCandidateFamily
    per_channel_sre: tuple[tuple[str, float], ...]
    per_channel_quality: tuple[tuple[str, float], ...]
    mean_sre: float
    mean_quality: float
    benchmark_reward_emitted: bool = False


def evaluate_sensor_state_channels(
    predictions: Mapping[str, Sequence[float]],
    truths: Mapping[str, Sequence[float]],
    candidate_family: SensorCandidateFamily,
    *,
    region_mask: Sequence[bool] | None = None,
) -> SensorStateEvaluation:
    """Equal-channel pilot diagnostic; constant truth fails closed."""
    if not predictions or predictions.keys() != truths.keys():
        raise ValueError("nonempty identical channel sets are required")
    if candidate_family is SensorCandidateFamily.CORRUPTION_REGION:
        if region_mask is None:
            raise ValueError("corruption-region scoring requires the fixed region mask")
    elif region_mask is not None:
        raise ValueError("a region mask is only valid for corruption-region scoring")
    result = _evaluate_sensor_state_channels(predictions, truths, region_mask=region_mask)
    return SensorStateEvaluation(
        candidate_family=candidate_family,
        per_channel_sre=result.per_channel_sre,
        per_channel_quality=result.per_channel_quality,
        mean_sre=result.mean_sre,
        mean_quality=result.mean_quality,
    )


@dataclass(frozen=True, slots=True)
class SensorGateResult:
    maximum_public_nonexpert_quality: float
    threshold: float = SENSOR_GATE_MAX_QUALITY
    passes: bool = False


def evaluate_sensor_state_gate(public_nonexpert_qualities: Sequence[float]) -> SensorGateResult:
    result = _evaluate_sensor_state_gate(public_nonexpert_qualities)
    return SensorGateResult(
        maximum_public_nonexpert_quality=result.maximum_public_nonexpert_quality,
        threshold=result.threshold,
        passes=result.passes,
    )


_TASK = TechnicalTaskContract(
    inputs=(
        "timestamped GNSS",
        "timestamped IMU",
        "heart-rate observations",
        "quality channels",
    ),
    targets=tuple(family.value for family in CANDIDATE_TARGET_FAMILIES),
    temporal=TemporalContract(target_hz=10.0),
    information_boundary=InformationBoundary(
        available_inputs=("causal native-rate sensor observations", "validity and quality"),
        withheld_targets=("private clean sensor-state candidates",),
        forbidden_information=("future sensor samples",),
    ),
    population_semantics="Synthetic player exposures grouped by player-week; pilot only.",
    data_state_binding=None,
    split_protocol_binding=None,
    evaluator_binding="validation-population SRE with equal-channel q and attack gate",
    execution_status=ExecutionStatus.PARTIAL,
    scientific_maturity=ScientificMaturity.NEGATIVE,
    reconstruction_blockers=(
        "No candidate target family was selected.",
        "Exact asynchronous timestamp alignment and channel schemas are incomplete.",
        "No per-target score table or target viability selection survives.",
    ),
    non_claims=(
        "The scoped pilot negative is not a universal impossibility result.",
        "No benchmark reward is emitted and no legal clearance is claimed.",
    ),
)

RESEARCH_OBJECT = ResearchObjectDefinition(
    identity=ResearchObjectIdentity(
        scientific_id=RESEARCH_OBJECT_ID,
        family_id="multimodal_state_estimation",
        task_id="multimodal_sensor_state_reconstruction",
    ),
    descriptor=ScientificDescriptor.from_task(
        _TASK,
        public_name="Multimodal sensor-state reconstruction pilot",
        technical_name="multimodal_sensor_state_reconstruction",
        research_question=UNKNOWN,
        scientific_task_type=ScientificTaskType.RECONSTRUCTION,
        prediction_or_inference_target=UNKNOWN,
        input_modalities=("GNSS", "IMU", "heart rate", "timestamps", "quality channels"),
        conditioning_information=(
            "causal native-rate sensor observations",
            "validity and quality",
        ),
        target_representation=UNKNOWN,
        reference_frame=UNKNOWN,
        history_interpretation=UNKNOWN,
        horizon_interpretation=UNKNOWN,
        source_sampling_hz=UNKNOWN,
        unit_of_evaluation=UNKNOWN,
        causal_status=CausalStatus.CAUSAL,
        scientific_metric_family=(
            "population-standardized relative error",
            "equal-channel quality",
            "attack gate",
        ),
        research_object_type=ResearchObjectType.NEGATIVE_RESULT,
    ),
    task=_TASK,
)
