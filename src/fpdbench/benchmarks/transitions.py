"""Typed evidence-backed transitions between scientific objects and states."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from fpdbench.provenance import EvidenceReference


class TransitionStatus(StrEnum):
    SAME = "SAME"
    CHANGED = "CHANGED"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class TransitionKind(StrEnum):
    BENCHMARK_PARITY = "BENCHMARK_PARITY"
    DATA_STATE_REPAIR = "DATA_STATE_REPAIR"
    DATASET_MEMBERSHIP_CHANGE = "DATASET_MEMBERSHIP_CHANGE"
    EVALUATOR_CHANGE = "EVALUATOR_CHANGE"
    CALIBRATION_CHANGE = "CALIBRATION_CHANGE"
    RELEASE_CHANGE = "RELEASE_CHANGE"
    RESEARCH_LINEAGE = "RESEARCH_LINEAGE"
    PROJECT_LEVEL_SWITCH = "PROJECT_LEVEL_SWITCH"
    EXPLICIT_NON_TRANSITION = "EXPLICIT_NON_TRANSITION"


class IdentityConsequence(StrEnum):
    SAME_BENCHMARK_IDENTITY = "SAME_BENCHMARK_IDENTITY"
    NEW_BENCHMARK_IDENTITY = "NEW_BENCHMARK_IDENTITY"
    NON_BENCHMARK_RESEARCH_LINEAGE = "NON_BENCHMARK_RESEARCH_LINEAGE"
    NO_SUPPORTED_TRANSITION = "NO_SUPPORTED_TRANSITION"


_IDENTITY_CONSEQUENCES = {
    TransitionKind.BENCHMARK_PARITY: IdentityConsequence.NEW_BENCHMARK_IDENTITY,
    TransitionKind.DATA_STATE_REPAIR: IdentityConsequence.SAME_BENCHMARK_IDENTITY,
    TransitionKind.DATASET_MEMBERSHIP_CHANGE: IdentityConsequence.SAME_BENCHMARK_IDENTITY,
    TransitionKind.EVALUATOR_CHANGE: IdentityConsequence.SAME_BENCHMARK_IDENTITY,
    TransitionKind.CALIBRATION_CHANGE: IdentityConsequence.SAME_BENCHMARK_IDENTITY,
    TransitionKind.RELEASE_CHANGE: IdentityConsequence.SAME_BENCHMARK_IDENTITY,
    TransitionKind.RESEARCH_LINEAGE: IdentityConsequence.NON_BENCHMARK_RESEARCH_LINEAGE,
    TransitionKind.PROJECT_LEVEL_SWITCH: IdentityConsequence.NO_SUPPORTED_TRANSITION,
    TransitionKind.EXPLICIT_NON_TRANSITION: IdentityConsequence.NO_SUPPORTED_TRANSITION,
}


def identity_consequence_for_kind(kind: TransitionKind) -> IdentityConsequence:
    """Keep data, evaluator, release, and research-lineage consequences separate."""
    return _IDENTITY_CONSEQUENCES[kind]


@dataclass(frozen=True, slots=True)
class TransitionEndpoint:
    object_id: str
    state: str

    def __post_init__(self) -> None:
        if not self.object_id or not self.state:
            raise ValueError("transition endpoints require object and state identities")


@dataclass(frozen=True, slots=True)
class ScientificTransition:
    transition_id: str
    transition_group_id: str
    source: TransitionEndpoint
    target: TransitionEndpoint
    transition_kind: TransitionKind
    layer: str
    status: TransitionStatus
    explanation: str
    evidence: tuple[EvidenceReference, ...]
    identity_consequence: IdentityConsequence
    data_state_consequence: TransitionStatus = TransitionStatus.NOT_APPLICABLE
    evaluator_consequence: TransitionStatus = TransitionStatus.NOT_APPLICABLE
    release_consequence: TransitionStatus = TransitionStatus.NOT_APPLICABLE
    research_lineage_consequence: TransitionStatus = TransitionStatus.NOT_APPLICABLE

    def __post_init__(self) -> None:
        if not all((self.transition_id, self.transition_group_id, self.layer)):
            raise ValueError("transition ID, group, and layer are required")
        if not self.explanation.strip() or not self.evidence:
            raise ValueError("every transition assessment requires an explanation and evidence")
        object.__setattr__(self, "evidence", tuple(self.evidence))
        if self.identity_consequence is not identity_consequence_for_kind(self.transition_kind):
            raise ValueError("identity consequence disagrees with transition kind")

    @property
    def field(self) -> str:
        """Compatibility name for the original parity field."""
        return self.layer
