"""Typed scientific benchmark contracts; identity is independent of release."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum


class ExecutionStatus(StrEnum):
    EXECUTABLE = "executable"
    PARTIAL = "partial"
    NON_EXECUTABLE = "non_executable"
    UNRECOVERABLE = "unrecoverable"


class ScientificMaturity(StrEnum):
    RECONSTRUCTED = "reconstructed"
    PARTIAL = "partial"
    INVALIDATED = "invalidated"
    NEGATIVE = "negative"
    UNRECOVERABLE = "unrecoverable"


class ResearchObjectType(StrEnum):
    RESEARCH_FAMILY = "research_family"
    HISTORICAL_STUDY = "historical_study"
    INVALIDATED_FORMULATION = "invalidated_formulation"
    NEGATIVE_RESULT = "negative_result"
    CANDIDATE_FORMULATION = "candidate_formulation"
    BENCHMARK = "benchmark"
    DATA_STATE = "data_state"


class UnknownValue(StrEnum):
    UNKNOWN = "UNKNOWN"


UNKNOWN = UnknownValue.UNKNOWN
type TextOrUnknown = str | UnknownValue
type StringListOrUnknown = tuple[str, ...] | UnknownValue


class ScientificTaskType(StrEnum):
    ESTIMATION = "estimation"
    RECONSTRUCTION = "reconstruction"
    FORECASTING = "forecasting"
    CONDITIONAL_RESPONSE_PREDICTION = "conditional_response_prediction"
    UNKNOWN = "unknown"


class CausalStatus(StrEnum):
    CAUSAL = "causal"
    CONDITIONAL_ON_REALIZED_FUTURE_CONTEXT = "conditional_on_realized_future_context"
    UNKNOWN = "unknown"


class ReleaseStatus(StrEnum):
    UNRELEASED = "unreleased"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ResearchObjectIdentity:
    scientific_id: str
    family_id: str
    task_id: str | None

    def __post_init__(self) -> None:
        if not self.scientific_id or not self.family_id:
            raise ValueError("research-object identity and family are required")


@dataclass(frozen=True, slots=True)
class BenchmarkIdentity(ResearchObjectIdentity):
    def __post_init__(self) -> None:
        ResearchObjectIdentity.__post_init__(self)
        if self.task_id is None:
            raise ValueError("benchmark identity requires a task ID")


@dataclass(frozen=True, slots=True)
class TemporalContract:
    history_seconds: float | None = None
    history_hz: float | None = None
    history_steps: int | None = None
    target_hz: float | None = None
    horizon_seconds: float | None = None
    horizon_hz: float | None = None
    horizon_steps: int | None = None

    def __post_init__(self) -> None:
        for value in (
            self.history_seconds,
            self.history_hz,
            self.target_hz,
            self.horizon_seconds,
            self.horizon_hz,
        ):
            if value is not None and (not math.isfinite(value) or value <= 0):
                raise ValueError("temporal durations and cadences must be finite and positive")
        for value in (self.history_steps, self.horizon_steps):
            if value is not None and value <= 0:
                raise ValueError("temporal step counts must be positive")
        for duration, cadence, steps in (
            (self.history_seconds, self.history_hz, self.history_steps),
            (self.horizon_seconds, self.horizon_hz, self.horizon_steps),
        ):
            if (
                duration is not None
                and cadence is not None
                and steps is not None
                and not math.isclose(duration * cadence, steps)
            ):
                raise ValueError("temporal duration, cadence, and steps must agree")

    def same_canonical_grid_as(self, other: TemporalContract) -> bool:
        """Whether result interfaces use the same canonical sample grid."""
        return (
            self.history_hz == other.history_hz
            and self.history_steps == other.history_steps
            and self.target_hz == other.target_hz
            and self.horizon_hz == other.horizon_hz
            and self.horizon_steps == other.horizon_steps
        )


@dataclass(frozen=True, slots=True)
class TemporalWindowContract:
    duration_seconds: float | UnknownValue
    interpretation: TextOrUnknown

    def __post_init__(self) -> None:
        if isinstance(self.duration_seconds, float) and (
            not math.isfinite(self.duration_seconds) or self.duration_seconds <= 0
        ):
            raise ValueError("temporal window duration must be finite and positive")


@dataclass(frozen=True, slots=True)
class CanonicalSampling:
    history_hz: float | UnknownValue
    history_steps: int | UnknownValue
    horizon_hz: float | UnknownValue
    horizon_steps: int | UnknownValue
    target_hz: float | UnknownValue

    def __post_init__(self) -> None:
        for cadence in (self.history_hz, self.horizon_hz, self.target_hz):
            if isinstance(cadence, float) and (not math.isfinite(cadence) or cadence <= 0):
                raise ValueError("canonical sampling cadences must be finite and positive")
        for steps in (self.history_steps, self.horizon_steps):
            if isinstance(steps, int) and steps <= 0:
                raise ValueError("canonical sampling step counts must be positive")


@dataclass(frozen=True, slots=True)
class ScientificDescriptor:
    public_name: str
    technical_name: str
    research_question: TextOrUnknown
    scientific_task_type: ScientificTaskType
    prediction_or_inference_target: TextOrUnknown
    input_modalities: StringListOrUnknown
    conditioning_information: StringListOrUnknown
    information_boundary: InformationBoundary
    target_representation: TextOrUnknown
    reference_frame: TextOrUnknown
    history_contract: TemporalWindowContract
    horizon_contract: TemporalWindowContract
    canonical_sampling: CanonicalSampling
    source_sampling_hz: float | UnknownValue
    population_semantics: TextOrUnknown
    unit_of_evaluation: TextOrUnknown
    causal_status: CausalStatus
    scientific_metric_family: StringListOrUnknown
    known_non_claims: tuple[str, ...]
    scientific_maturity: ScientificMaturity
    research_object_type: ResearchObjectType
    release_status: ReleaseStatus

    def __post_init__(self) -> None:
        if not self.public_name or not self.technical_name:
            raise ValueError("scientific descriptor names are required")
        for name in (
            "input_modalities",
            "conditioning_information",
            "scientific_metric_family",
            "known_non_claims",
        ):
            value = getattr(self, name)
            if value is not UNKNOWN:
                object.__setattr__(self, name, tuple(value))

    def scientific_identity_compatible_with(self, other: ScientificDescriptor) -> bool:
        """Compare task meaning while allowing a release to change its canonical grid."""
        fields = (
            "research_question",
            "scientific_task_type",
            "prediction_or_inference_target",
            "input_modalities",
            "conditioning_information",
            "information_boundary",
            "target_representation",
            "reference_frame",
            "history_contract",
            "horizon_contract",
            "population_semantics",
            "unit_of_evaluation",
            "causal_status",
            "scientific_metric_family",
        )
        return all(getattr(self, name) == getattr(other, name) for name in fields)

    def release_compatible_with(self, other: ScientificDescriptor) -> bool:
        """A canonical-grid change breaks release compatibility, not task identity."""
        return self.scientific_identity_compatible_with(other) and (
            self.canonical_sampling == other.canonical_sampling
        )

    @classmethod
    def from_task(
        cls,
        task: TechnicalTaskContract,
        *,
        public_name: str,
        technical_name: str,
        research_question: TextOrUnknown,
        scientific_task_type: ScientificTaskType,
        prediction_or_inference_target: TextOrUnknown,
        input_modalities: StringListOrUnknown,
        conditioning_information: StringListOrUnknown,
        target_representation: TextOrUnknown,
        reference_frame: TextOrUnknown,
        history_interpretation: TextOrUnknown,
        horizon_interpretation: TextOrUnknown,
        source_sampling_hz: float | UnknownValue,
        unit_of_evaluation: TextOrUnknown,
        causal_status: CausalStatus,
        scientific_metric_family: StringListOrUnknown,
        research_object_type: ResearchObjectType,
        release_status: ReleaseStatus = ReleaseStatus.UNRELEASED,
    ) -> ScientificDescriptor:
        temporal = task.temporal
        return cls(
            public_name=public_name,
            technical_name=technical_name,
            research_question=research_question,
            scientific_task_type=scientific_task_type,
            prediction_or_inference_target=prediction_or_inference_target,
            input_modalities=input_modalities,
            conditioning_information=conditioning_information,
            information_boundary=task.information_boundary,
            target_representation=target_representation,
            reference_frame=reference_frame,
            history_contract=TemporalWindowContract(
                temporal.history_seconds if temporal.history_seconds is not None else UNKNOWN,
                history_interpretation,
            ),
            horizon_contract=TemporalWindowContract(
                temporal.horizon_seconds if temporal.horizon_seconds is not None else UNKNOWN,
                horizon_interpretation,
            ),
            canonical_sampling=CanonicalSampling(
                temporal.history_hz if temporal.history_hz is not None else UNKNOWN,
                temporal.history_steps if temporal.history_steps is not None else UNKNOWN,
                temporal.horizon_hz if temporal.horizon_hz is not None else UNKNOWN,
                temporal.horizon_steps if temporal.horizon_steps is not None else UNKNOWN,
                temporal.target_hz if temporal.target_hz is not None else UNKNOWN,
            ),
            source_sampling_hz=source_sampling_hz,
            population_semantics=task.population_semantics,
            unit_of_evaluation=unit_of_evaluation,
            causal_status=causal_status,
            scientific_metric_family=scientific_metric_family,
            known_non_claims=task.non_claims,
            scientific_maturity=task.scientific_maturity,
            research_object_type=research_object_type,
            release_status=release_status,
        )


@dataclass(frozen=True, slots=True)
class InformationBoundary:
    available_inputs: tuple[str, ...]
    withheld_targets: tuple[str, ...]
    forbidden_information: tuple[str, ...] = ()
    conditional_future_context: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TechnicalTaskContract:
    inputs: tuple[str, ...]
    targets: tuple[str, ...]
    temporal: TemporalContract
    information_boundary: InformationBoundary
    population_semantics: str
    data_state_binding: str | None
    split_protocol_binding: str | None
    evaluator_binding: str | None
    execution_status: ExecutionStatus
    scientific_maturity: ScientificMaturity
    reconstruction_blockers: tuple[str, ...] = ()
    non_claims: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ResearchObjectDefinition:
    identity: ResearchObjectIdentity
    descriptor: ScientificDescriptor
    task: TechnicalTaskContract
    direct_model_bindings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.identity.scientific_id or not self.identity.family_id:
            raise ValueError("research-object identity and family are required")
        is_benchmark = self.descriptor.research_object_type is ResearchObjectType.BENCHMARK
        if is_benchmark != isinstance(self, BenchmarkDefinition):
            raise ValueError("benchmark classification and definition type must agree")
        if self.descriptor.scientific_maturity is not self.task.scientific_maturity:
            raise ValueError("descriptor and technical task maturity must agree")
        if self.descriptor.information_boundary != self.task.information_boundary:
            raise ValueError("descriptor and technical task information boundaries must agree")
        if self.descriptor.population_semantics != self.task.population_semantics:
            raise ValueError("descriptor and technical task population semantics must agree")
        if self.descriptor.known_non_claims != self.task.non_claims:
            raise ValueError("descriptor and technical task non-claims must agree")
        if self.descriptor.research_object_type is ResearchObjectType.RESEARCH_FAMILY:
            if (
                self.identity.task_id is not None
                or self.identity.scientific_id != self.identity.family_id
            ):
                raise ValueError("research families require a family-only scientific identity")
        elif self.identity.task_id is None:
            raise ValueError("non-family research objects require a task ID")
        object.__setattr__(self, "direct_model_bindings", tuple(self.direct_model_bindings))


@dataclass(frozen=True, slots=True)
class BenchmarkDefinition(ResearchObjectDefinition):
    identity: BenchmarkIdentity


@dataclass(frozen=True, slots=True)
class ResearchFamilyDefinition:
    family_id: str
    public_name: str
    technical_name: str
    research_question: str
    scientific_scope: str
    known_non_claims: tuple[str, ...]
    scientific_maturity: ScientificMaturity
    release_status: ReleaseStatus
    unresolved_task_fields: tuple[tuple[str, UnknownValue], ...] = ()

    def __post_init__(self) -> None:
        if not all((self.family_id, self.public_name, self.technical_name)):
            raise ValueError("research-family identifiers and names are required")
        if not self.research_question or not self.scientific_scope:
            raise ValueError("research-family question and scope are required")
        object.__setattr__(self, "known_non_claims", tuple(self.known_non_claims))
        object.__setattr__(self, "unresolved_task_fields", tuple(self.unresolved_task_fields))
        fields = [name for name, _ in self.unresolved_task_fields]
        if len(fields) != len(set(fields)) or any(not name for name in fields):
            raise ValueError("unresolved research-family task fields must be uniquely named")
        if any(value is not UNKNOWN for _, value in self.unresolved_task_fields):
            raise ValueError("unresolved research-family task fields must be UNKNOWN")


@dataclass(frozen=True, slots=True)
class BenchmarkRelease:
    benchmark_id: str
    version: str
    scientific_lock_hash: str

    def __post_init__(self) -> None:
        if not self.benchmark_id or not self.version or len(self.scientific_lock_hash) != 64:
            raise ValueError("release requires benchmark ID, version, and scientific lock hash")
