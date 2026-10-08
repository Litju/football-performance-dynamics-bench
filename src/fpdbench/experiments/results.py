"""Scientific result records and deterministic structured result manifests."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import ClassVar

from fpdbench.data import ArtifactReference
from fpdbench.experiments.manifests import ExperimentManifest
from fpdbench.experiments.provenance import (
    ArtifactDeclaration,
    ArtifactRelation,
    ProvenanceCompleteness,
    ScientificStateBinding,
    evidence_sha256,
    stable_manifest_hash,
    validate_sha256,
)
from fpdbench.experiments.uncertainty import UncertaintyReport
from fpdbench.provenance import EvidenceReference, validate_evidence_reference_shape

type MetricValues = tuple[tuple[str, float], ...]


def _finite_metric(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def _numeric_value(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("result metric value must be numeric")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError("result metric value must be finite")
    return normalized


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


_EVALUATOR_STATES_BY_ID: dict[str, EvaluatorState] = {
    "origin_relative_displacement_raw_population_sre": EvaluatorState.RAW_EVALUATION,
    "physical_trajectory.ade_fde_xy_rmse": EvaluatorState.PHYSICAL_DIAGNOSTIC,
    "absolute_position.population_sre_targets": EvaluatorState.RAW_EVALUATION,
    "absolute_position.historical_continuous_pwl_v3": EvaluatorState.CALIBRATED_REWARD,
}
_POPULATIONS_BY_SPLIT_PROTOCOL: dict[str, frozenset[ResultPopulation]] = {
    "match_grouped_cross_match_split": frozenset({ResultPopulation.LOMO_CROSS_MATCH}),
    "match_grouped_displacement_public_split": frozenset({ResultPopulation.PUBLIC_VALIDATION}),
    "conditional_motion.public_train_lomo": frozenset({ResultPopulation.LOMO_CROSS_MATCH}),
    "conditional_motion.match_role_assignment": frozenset(
        {ResultPopulation.PUBLIC_TRAIN, ResultPopulation.PUBLIC_VALIDATION}
    ),
}


def validate_result_scope(
    scientific_state: ScientificStateBinding,
    population: ResultPopulation,
    evaluator_state: EvaluatorState,
) -> None:
    """Reject result labels that contradict an explicitly registered scientific scope."""
    expected_evaluator_state = _EVALUATOR_STATES_BY_ID.get(scientific_state.evaluator_id)
    if expected_evaluator_state is None:
        raise ValueError(
            f"unsupported evaluator identity for result scope: {scientific_state.evaluator_id}"
        )
    if evaluator_state is not expected_evaluator_state:
        raise ValueError(
            f"evaluator state {evaluator_state.value} contradicts scientific evaluator "
            f"{scientific_state.evaluator_id}"
        )

    allowed_populations = _POPULATIONS_BY_SPLIT_PROTOCOL.get(scientific_state.split_protocol_id)
    if allowed_populations is None:
        raise ValueError(
            f"unsupported split protocol for result scope: {scientific_state.split_protocol_id}"
        )
    if population not in allowed_populations:
        raise ValueError(
            f"result population {population.value} is incompatible with scientific split "
            f"protocol {scientific_state.split_protocol_id}"
        )


class ResultValidity(StrEnum):
    RECORDED = "recorded"
    RECOVERED = "recovered"
    RECOMPUTED = "recomputed"
    INVALIDATED = "invalidated"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ResultMetric:
    metric_id: str
    value: float
    unit: str | None = None

    def __post_init__(self) -> None:
        if not self.metric_id:
            raise ValueError("result metric ID is required")
        normalized = _numeric_value(self.value)
        object.__setattr__(self, "value", normalized)
        if self.unit is not None and not self.unit:
            raise ValueError("result metric unit must be nonempty when supplied")

    def identity_payload(self) -> dict[str, str | None]:
        return {"metric_id": self.metric_id, "value_hex": self.value.hex(), "unit": self.unit}


def _evidence_payload(evidence: tuple[EvidenceReference, ...]) -> list[str]:
    return sorted(evidence_sha256(item) for item in evidence)


def _validate_artifacts(artifacts: tuple[ArtifactDeclaration, ...]) -> None:
    for artifact in artifacts:
        if artifact.relation not in {ArtifactRelation.OUTPUT, ArtifactRelation.DIAGNOSTIC}:
            raise ValueError("result artifacts must be outputs or diagnostics")


def _validate_completeness(
    *,
    run_id: str,
    scientific_lock_hash: str,
    model_checkpoint_sha256: str | None,
    evidence: tuple[EvidenceReference, ...],
    provenance_completeness: ProvenanceCompleteness,
    experiment_manifest: ExperimentManifest | None,
) -> None:
    if provenance_completeness is ProvenanceCompleteness.HISTORICAL_EVIDENCE_BOUND:
        if experiment_manifest is not None:
            raise ValueError("historical records must not invent a modern execution manifest")
        if not evidence:
            raise ValueError("historical evidence-bound records require explicit evidence")
        return
    if experiment_manifest is None:
        raise ValueError("execution-bound results require an experiment manifest")
    if (
        experiment_manifest.run_id != run_id
        or experiment_manifest.scientific_state.scientific_lock_hash != scientific_lock_hash
    ):
        raise ValueError("execution manifest does not match result run or scientific lock")
    if (
        model_checkpoint_sha256 is not None
        and experiment_manifest.system.checkpoint_sha256 != model_checkpoint_sha256
    ):
        raise ValueError("execution manifest model checkpoint does not match result")


@dataclass(frozen=True, slots=True)
class ResultRecord:
    run_id: str
    scientific_lock_hash: str
    model_checkpoint_sha256: str | None
    metrics: MetricValues
    population: ResultPopulation
    evaluator_state: EvaluatorState
    validity: ResultValidity
    output_sha256: str | None = None
    evidence: tuple[EvidenceReference, ...] = ()
    provenance_completeness: ProvenanceCompleteness = field(kw_only=True)
    experiment_manifest: ExperimentManifest | None = None
    uncertainty: UncertaintyReport | None = None
    output_artifacts: tuple[ArtifactDeclaration, ...] = ()

    SCHEMA_ID: ClassVar[str] = "fpdbench.result-record"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("result identity is required")
        validate_sha256(self.scientific_lock_hash, "scientific lock SHA-256")
        if self.model_checkpoint_sha256 is not None:
            validate_sha256(self.model_checkpoint_sha256, "model checkpoint SHA-256")
        if self.output_sha256 is not None:
            validate_sha256(self.output_sha256, "result output SHA-256")
        object.__setattr__(self, "metrics", tuple(self.metrics))
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "output_artifacts", tuple(self.output_artifacts))
        names = [name for name, _ in self.metrics]
        if len(names) != len(set(names)) or any(not name for name in names):
            raise ValueError("result metric names must be unique and nonempty")
        if any(not _finite_metric(value) for _, value in self.metrics):
            raise ValueError("result metric values must be finite numbers")
        if self.validity is ResultValidity.INVALIDATED and self.metrics:
            raise ValueError("invalidated results cannot publish metrics")
        for reference in self.evidence:
            errors = validate_evidence_reference_shape(reference)
            if errors:
                raise ValueError("; ".join(errors))
            evidence_sha256(reference)
        _validate_artifacts(self.output_artifacts)
        artifact_ids = [item.artifact_id for item in self.output_artifacts]
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("result artifact IDs must be unique")
        _validate_completeness(
            run_id=self.run_id,
            scientific_lock_hash=self.scientific_lock_hash,
            model_checkpoint_sha256=self.model_checkpoint_sha256,
            evidence=self.evidence,
            provenance_completeness=self.provenance_completeness,
            experiment_manifest=self.experiment_manifest,
        )
        if (
            self.provenance_completeness is ProvenanceCompleteness.EXECUTION_MANIFEST_BOUND
            and self.experiment_manifest is not None
        ):
            validate_result_scope(
                self.experiment_manifest.scientific_state,
                self.population,
                self.evaluator_state,
            )

    @property
    def metric_records(self) -> tuple[ResultMetric, ...]:
        """Structured adapter over the preserved historical tuple metric keys."""
        return tuple(ResultMetric(metric_id, value) for metric_id, value in self.metrics)

    @property
    def output_sha256s(self) -> tuple[str, ...]:
        digests = ([self.output_sha256] if self.output_sha256 is not None else []) + [
            item.reference.sha256 for item in self.output_artifacts
        ]
        return tuple(sorted(set(digests)))

    def identity_payload(self) -> dict[str, object]:
        return {
            "schema_id": self.SCHEMA_ID,
            "schema_version": self.SCHEMA_VERSION,
            "run_id": self.run_id,
            "scientific_lock_hash": self.scientific_lock_hash,
            "model_checkpoint_sha256": self.model_checkpoint_sha256,
            "metrics": [
                item.identity_payload()
                for item in sorted(self.metric_records, key=lambda m: m.metric_id)
            ],
            "population": self.population.value,
            "evaluator_state": self.evaluator_state.value,
            "validity": self.validity.value,
            "output_sha256s": list(self.output_sha256s),
            "output_artifacts": sorted(
                (item.identity_payload() for item in self.output_artifacts),
                key=lambda item: str(item["artifact_id"]),
            ),
            "evidence_sha256": _evidence_payload(self.evidence),
            "provenance_completeness": self.provenance_completeness.value,
            "experiment_manifest_hash": (
                None if self.experiment_manifest is None else self.experiment_manifest.manifest_hash
            ),
            "uncertainty": (
                None if self.uncertainty is None else self.uncertainty.identity_payload()
            ),
        }

    @property
    def result_hash(self) -> str:
        return stable_manifest_hash(self.identity_payload())

    def to_manifest(
        self,
        scientific_lock: object,
        *,
        uncertainty: UncertaintyReport | None = None,
    ) -> ResultManifest:
        return ResultManifest.from_record(self, scientific_lock, uncertainty=uncertainty)


@dataclass(frozen=True, slots=True)
class ResultManifest:
    run_id: str
    scientific_state: ScientificStateBinding
    metrics: tuple[ResultMetric, ...]
    population: ResultPopulation
    evaluator_state: EvaluatorState
    validity: ResultValidity
    model_checkpoint_sha256: str | None
    output_artifacts: tuple[ArtifactDeclaration, ...]
    evidence: tuple[EvidenceReference, ...]
    provenance_completeness: ProvenanceCompleteness
    experiment_manifest: ExperimentManifest | None = None
    uncertainty: UncertaintyReport | None = None

    SCHEMA_ID: ClassVar[str] = "fpdbench.result-manifest"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("result identity is required")
        if self.model_checkpoint_sha256 is not None:
            validate_sha256(self.model_checkpoint_sha256, "model checkpoint SHA-256")
        object.__setattr__(self, "metrics", tuple(self.metrics))
        object.__setattr__(self, "output_artifacts", tuple(self.output_artifacts))
        object.__setattr__(self, "evidence", tuple(self.evidence))
        metric_ids = [item.metric_id for item in self.metrics]
        if len(metric_ids) != len(set(metric_ids)):
            raise ValueError("result metric IDs must be unique")
        if self.validity is ResultValidity.INVALIDATED and self.metrics:
            raise ValueError("invalidated results cannot publish metrics")
        _validate_artifacts(self.output_artifacts)
        for reference in self.evidence:
            errors = validate_evidence_reference_shape(reference)
            if errors:
                raise ValueError("; ".join(errors))
            evidence_sha256(reference)
        artifact_ids = [item.artifact_id for item in self.output_artifacts]
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("result artifact IDs must be unique")
        _validate_completeness(
            run_id=self.run_id,
            scientific_lock_hash=self.scientific_state.scientific_lock_hash,
            model_checkpoint_sha256=self.model_checkpoint_sha256,
            evidence=self.evidence,
            provenance_completeness=self.provenance_completeness,
            experiment_manifest=self.experiment_manifest,
        )
        validate_result_scope(self.scientific_state, self.population, self.evaluator_state)

    @classmethod
    def from_record(
        cls,
        record: ResultRecord,
        scientific_lock: object,
        *,
        uncertainty: UncertaintyReport | None = None,
    ) -> ResultManifest:
        binding = ScientificStateBinding.from_verified_lock(scientific_lock)
        if record.scientific_lock_hash != binding.scientific_lock_hash:
            raise ValueError("result record and scientific lock do not match")
        artifacts = list(record.output_artifacts)
        if record.output_sha256 is not None:
            artifacts.append(
                ArtifactDeclaration(
                    artifact_id="legacy-output",
                    role="result_output",
                    relation=ArtifactRelation.OUTPUT,
                    reference=ArtifactReference(
                        uri=f"urn:sha256:{record.output_sha256}", sha256=record.output_sha256
                    ),
                )
            )
        return cls(
            run_id=record.run_id,
            scientific_state=binding,
            metrics=record.metric_records,
            population=record.population,
            evaluator_state=record.evaluator_state,
            validity=record.validity,
            model_checkpoint_sha256=record.model_checkpoint_sha256,
            output_artifacts=tuple(artifacts),
            evidence=record.evidence,
            provenance_completeness=record.provenance_completeness,
            experiment_manifest=record.experiment_manifest,
            uncertainty=uncertainty if uncertainty is not None else record.uncertainty,
        )

    def identity_payload(self) -> dict[str, object]:
        return {
            "schema_id": self.SCHEMA_ID,
            "schema_version": self.SCHEMA_VERSION,
            "run_id": self.run_id,
            "scientific_state": self.scientific_state.identity_payload(),
            "model_checkpoint_sha256": self.model_checkpoint_sha256,
            "metrics": [
                item.identity_payload() for item in sorted(self.metrics, key=lambda m: m.metric_id)
            ],
            "population": self.population.value,
            "evaluator_state": self.evaluator_state.value,
            "validity": self.validity.value,
            "output_artifacts": sorted(
                (item.identity_payload() for item in self.output_artifacts),
                key=lambda item: str(item["artifact_id"]),
            ),
            "evidence_sha256": _evidence_payload(self.evidence),
            "provenance_completeness": self.provenance_completeness.value,
            "experiment_manifest_hash": (
                None if self.experiment_manifest is None else self.experiment_manifest.manifest_hash
            ),
            "uncertainty": (
                None if self.uncertainty is None else self.uncertainty.identity_payload()
            ),
        }

    @property
    def manifest_hash(self) -> str:
        return stable_manifest_hash(self.identity_payload())


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


__all__ = [
    "EvaluatorState",
    "MetricValues",
    "PublicReleaseManifest",
    "ResultManifest",
    "ResultMetric",
    "ResultPopulation",
    "ResultRecord",
    "ResultValidity",
    "validate_result_scope",
]
