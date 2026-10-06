"""Typed scientific benchmark contracts; identity is independent of release."""

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


@dataclass(frozen=True, slots=True)
class BenchmarkIdentity:
    scientific_id: str
    family_id: str
    task_id: str | None


@dataclass(frozen=True, slots=True)
class TemporalContract:
    history_seconds: float | None = None
    history_hz: float | None = None
    history_steps: int | None = None
    horizon_seconds: float | None = None
    horizon_hz: float | None = None
    horizon_steps: int | None = None

    def __post_init__(self) -> None:
        for value in (self.history_seconds, self.history_hz, self.horizon_seconds, self.horizon_hz):
            if value is not None and value <= 0:
                raise ValueError("temporal durations and cadences must be positive")
        for value in (self.history_steps, self.horizon_steps):
            if value is not None and value <= 0:
                raise ValueError("temporal step counts must be positive")

    def cadence_compatible_with(self, other: TemporalContract) -> bool:
        """R1 requires explicit new identity when any canonical temporal contract changes."""
        return self == other


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
class BenchmarkDefinition:
    identity: BenchmarkIdentity
    task: TechnicalTaskContract

    def __post_init__(self) -> None:
        if not self.identity.scientific_id or not self.identity.family_id:
            raise ValueError("benchmark identity and family are required")
        if self.identity.task_id is None and self.task.execution_status is not ExecutionStatus.UNRECOVERABLE:
            raise ValueError("family-only records must not claim an executable task")


@dataclass(frozen=True, slots=True)
class BenchmarkRelease:
    benchmark_id: str
    version: str
    scientific_lock_hash: str

    def __post_init__(self) -> None:
        if not self.benchmark_id or not self.version or len(self.scientific_lock_hash) != 64:
            raise ValueError("release requires benchmark ID, version, and scientific lock hash")
