"""Canonical experiment, system, and run-configuration manifests."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from fpdbench.experiments.provenance import (
    ArtifactDeclaration,
    ArtifactRelation,
    EnvironmentFingerprint,
    ExecutionProvenance,
    ScientificStateBinding,
    evidence_sha256,
    stable_manifest_hash,
    validate_sha256,
)
from fpdbench.models import ModelCheckpoint
from fpdbench.provenance import EvidenceReference


def _is_binding(value: object) -> bool:
    return isinstance(value, ScientificStateBinding)


def _is_nonnegative_seed(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


class SystemKind(StrEnum):
    LEARNED_MODEL = "learned_model"
    BASELINE = "baseline"
    REFERENCE = "reference"
    ORACLE = "oracle"


class ModelSelectionUse(StrEnum):
    UNKNOWN = "unknown"
    NONE = "none"
    USED = "used"


@dataclass(frozen=True, slots=True)
class SystemIdentity:
    system_id: str
    kind: SystemKind
    checkpoint_sha256: str | None = None
    architecture_config_sha256: str | None = None
    training_config_sha256: str | None = None
    evidence: tuple[EvidenceReference, ...] = ()

    def __post_init__(self) -> None:
        if not self.system_id:
            raise ValueError("system identity is required")
        for field, value in (
            ("checkpoint SHA-256", self.checkpoint_sha256),
            ("architecture config SHA-256", self.architecture_config_sha256),
            ("training config SHA-256", self.training_config_sha256),
        ):
            if value is not None:
                validate_sha256(value, field)
        if self.kind is SystemKind.LEARNED_MODEL and self.checkpoint_sha256 is None:
            raise ValueError("learned systems require a checkpoint SHA-256")
        object.__setattr__(self, "evidence", tuple(self.evidence))
        for reference in self.evidence:
            evidence_sha256(reference)

    @classmethod
    def from_checkpoint(cls, checkpoint: ModelCheckpoint) -> SystemIdentity:
        return cls(
            system_id=checkpoint.model_id,
            kind=SystemKind.LEARNED_MODEL,
            checkpoint_sha256=checkpoint.checkpoint_sha256,
            training_config_sha256=checkpoint.training_config_sha256,
        )

    def identity_payload(self) -> dict[str, object]:
        return {
            "system_id": self.system_id,
            "kind": self.kind.value,
            "checkpoint_sha256": self.checkpoint_sha256,
            "architecture_config_sha256": self.architecture_config_sha256,
            "training_config_sha256": self.training_config_sha256,
            "evidence_sha256": sorted(evidence_sha256(item) for item in self.evidence),
        }


@dataclass(frozen=True, slots=True)
class RunConfiguration:
    configuration_sha256: str
    seed: int | None = None
    model_selection_use: ModelSelectionUse = ModelSelectionUse.UNKNOWN

    SCHEMA_ID: ClassVar[str] = "fpdbench.run-configuration"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        validate_sha256(self.configuration_sha256, "run configuration SHA-256")
        if self.seed is not None and not _is_nonnegative_seed(self.seed):
            raise ValueError("run seed must be a nonnegative integer")

    def identity_payload(self) -> dict[str, object]:
        return {
            "schema_id": self.SCHEMA_ID,
            "schema_version": self.SCHEMA_VERSION,
            "configuration_sha256": self.configuration_sha256,
            "seed": self.seed,
            "model_selection_use": self.model_selection_use.value,
        }

    @property
    def manifest_hash(self) -> str:
        return stable_manifest_hash(self.identity_payload())


@dataclass(frozen=True, slots=True)
class ExperimentManifest:
    run_id: str
    scientific_state: ScientificStateBinding
    system: SystemIdentity
    run_configuration: RunConfiguration
    environment: EnvironmentFingerprint
    input_artifacts: tuple[ArtifactDeclaration, ...]
    output_artifacts: tuple[ArtifactDeclaration, ...]
    execution_provenance: ExecutionProvenance
    metadata: tuple[tuple[str, str], ...] = ()

    SCHEMA_ID: ClassVar[str] = "fpdbench.experiment-manifest"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("experiment/run ID is required")
        if not _is_binding(self.scientific_state):
            raise ValueError("experiment requires a verified scientific-state binding")
        if self.run_configuration.model_selection_use is ModelSelectionUse.UNKNOWN:
            raise ValueError("future experiment manifests must declare model-selection use")
        object.__setattr__(self, "input_artifacts", tuple(self.input_artifacts))
        object.__setattr__(self, "output_artifacts", tuple(self.output_artifacts))
        object.__setattr__(self, "metadata", tuple(self.metadata))
        if any(item.relation is not ArtifactRelation.INPUT for item in self.input_artifacts):
            raise ValueError("experiment inputs must use the input artifact relation")
        if any(
            item.relation not in {ArtifactRelation.OUTPUT, ArtifactRelation.DIAGNOSTIC}
            for item in self.output_artifacts
        ):
            raise ValueError("experiment outputs must use output or diagnostic relations")
        artifact_ids = [
            item.artifact_id for item in (*self.input_artifacts, *self.output_artifacts)
        ]
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("experiment artifact IDs must be unique")
        if len({key for key, _ in self.metadata}) != len(self.metadata):
            raise ValueError("experiment metadata keys must be unique")

    def identity_payload(self) -> dict[str, object]:
        return {
            "schema_id": self.SCHEMA_ID,
            "schema_version": self.SCHEMA_VERSION,
            "run_id": self.run_id,
            "scientific_state": self.scientific_state.identity_payload(),
            "system": self.system.identity_payload(),
            "run_configuration": self.run_configuration.identity_payload(),
            "environment": self.environment.identity_payload(),
            "input_artifacts": sorted(
                (item.identity_payload() for item in self.input_artifacts),
                key=lambda item: str(item["artifact_id"]),
            ),
            "output_artifacts": sorted(
                (item.identity_payload() for item in self.output_artifacts),
                key=lambda item: str(item["artifact_id"]),
            ),
            "execution_provenance": self.execution_provenance.identity_payload(),
        }

    @property
    def manifest_hash(self) -> str:
        return stable_manifest_hash(self.identity_payload())

    @property
    def model_selection_use(self) -> ModelSelectionUse:
        return self.run_configuration.model_selection_use


RunManifest = ExperimentManifest


@dataclass(frozen=True, slots=True)
class ExperimentRun:
    """Compatibility view retained for the original small run descriptor."""

    run_id: str
    benchmark_id: str
    scientific_lock_hash: str
    model: ModelCheckpoint
    split_protocol_id: str
    configuration_sha256: str

    def __post_init__(self) -> None:
        if not self.run_id or not self.benchmark_id or not self.split_protocol_id:
            raise ValueError("experiment run identity fields are required")
        validate_sha256(self.scientific_lock_hash, "scientific lock SHA-256")
        validate_sha256(self.configuration_sha256, "run configuration SHA-256")


__all__ = [
    "ExperimentManifest",
    "ExperimentRun",
    "ModelSelectionUse",
    "RunConfiguration",
    "RunManifest",
    "SystemIdentity",
    "SystemKind",
]
