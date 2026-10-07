"""Runs, results, and governance release records stay independent of locks."""

from dataclasses import dataclass
from enum import StrEnum

from fpdbench.models import ModelCheckpoint
from fpdbench.provenance import EvidenceReference

type MetricValues = tuple[tuple[str, float], ...]


class ResultPopulation(StrEnum):
    PUBLIC_TRAIN = "public_training"
    PUBLIC_VALIDATION = "public_validation"
    LOMO_CROSS_MATCH = "lomo_cross_match"
    HISTORICAL_PRIVATE = "historical_private"
    RELEASE_SYSTEM_VALIDATION = "release_system_validation"


class EvaluatorState(StrEnum):
    RAW_EVALUATION = "raw_evaluation"
    CALIBRATED_REWARD = "calibrated_reward"
    PHYSICAL_DIAGNOSTIC = "physical_trajectory_diagnostic"
    RELEASE_ENGINEERING = "release_engineering"


class ResultValidity(StrEnum):
    RECORDED = "recorded"
    RECOVERED = "recovered"
    RECOMPUTED = "recomputed"
    INVALIDATED = "invalidated"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ExperimentRun:
    run_id: str
    benchmark_id: str
    scientific_lock_hash: str
    model: ModelCheckpoint
    split_protocol_id: str
    configuration_sha256: str


@dataclass(frozen=True, slots=True)
class ResultRecord:
    run_id: str
    scientific_lock_hash: str | None
    model_checkpoint_sha256: str | None
    metrics: MetricValues
    population: ResultPopulation
    evaluator_state: EvaluatorState
    validity: ResultValidity
    output_sha256: str | None = None
    evidence: tuple[EvidenceReference, ...] = ()

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("result identity is required")
        object.__setattr__(self, "metrics", tuple(self.metrics))
        object.__setattr__(self, "evidence", tuple(self.evidence))
        names = [name for name, _ in self.metrics]
        if len(names) != len(set(names)) or any(not name for name in names):
            raise ValueError("result metric names must be unique and nonempty")
        if self.validity is ResultValidity.INVALIDATED and self.metrics:
            raise ValueError("invalidated results cannot publish metrics")


@dataclass(frozen=True, slots=True)
class PublicReleaseManifest:
    """Governance and hosting metadata; this object is never input to a scientific lock."""

    scientific_lock_hash: str
    legal_status: str
    license_status: str
    publication_status: str
    public_release_authority: str | None = None
    artifact_availability: str | None = None
    license_clearance_snapshot: str | None = None
    artifact_uris: tuple[str, ...] = ()
    hosting_provider: str | None = None
    release_timestamp: str | None = None
