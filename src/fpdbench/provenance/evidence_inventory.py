"""Complete, deterministic inventory of evidence consumed by the public stack."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from fpdbench.benchmarks.transition_graph import TRANSITION_GRAPH, validate_transition_graph
from fpdbench.evaluation import (
    ABSOLUTE_POSITION_HISTORICAL_SCORER,
    ABSOLUTE_POSITION_PROGRESS_TRANSFORM,
    ABSOLUTE_POSITION_RAW_EVALUATOR,
    RAW_DISPLACEMENT_EVALUATOR_CONFIGURATION,
    SENSOR_STATE_EVALUATOR,
    SENSOR_STATE_PUBLIC_NONEXPERT_GATE,
    SIGNED_TANGENTIAL_ACCELERATION_EVALUATOR,
)
from fpdbench.evaluation.metrics.trajectory import PHYSICAL_TRAJECTORY_EVALUATOR
from fpdbench.experiments.provenance import evidence_sha256
from fpdbench.protocols import BENCHMARK_PROTOCOL_BINDINGS, validate_canonical_protocols
from fpdbench.provenance import EvidenceReference, validate_evidence_reference_shape
from fpdbench.provenance.aliases import HISTORICAL_ALIASES
from fpdbench.provenance.evidence_resolution import (
    EvidenceResolutionReport,
    resolve_evidence_references,
)
from fpdbench.provenance.registry_digest import registry_content_digest
from fpdbench.provenance.scientific_lock import validate_scientific_lock_provenance

from ..benchmarks.conditional_multi_agent_motion_prediction import (
    displacement_reconstruction as displacement,
)

EXPECTED_REGISTRY_PATH_COUNT = 793
EXPECTED_REGISTRY_SHA256 = "539f453eedd2e11b5ee5c2346df4c5ee360a04f5daa55e66e0c0810ed7d20511"


@dataclass(frozen=True, slots=True)
class EvidenceValidationReport:
    reference_count: int
    unique_digests: int
    reference_counts_by_digest: tuple[tuple[str, int], ...]
    category_counts: tuple[tuple[str, int], ...]
    legacy_alias_count: int
    legacy_alias_sha_reference_count: int
    strict_resolution: EvidenceResolutionReport | None
    registry_before: tuple[int, str] | None
    registry_after: tuple[int, str] | None
    errors: tuple[str, ...]


def _lock_citations() -> tuple[EvidenceReference, ...]:
    references: list[EvidenceReference] = []
    locks = (
        displacement.PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK,
        displacement.LOMO_RAW_SCIENTIFIC_LOCK,
        displacement.PUBLIC_VALIDATION_PHYSICAL_SCIENTIFIC_LOCK,
    )
    for lock in locks:
        snapshot = lock.get("scientific_provenance_snapshot")
        if not isinstance(snapshot, dict):
            continue
        citations = cast(dict[object, object], snapshot).get("citations")
        if isinstance(citations, list):
            references.extend(
                EvidenceReference(item)
                for item in cast(list[object], citations)
                if isinstance(item, str)
            )
    return tuple(references)


def _evaluator_references() -> tuple[EvidenceReference, ...]:
    evaluators = (
        SIGNED_TANGENTIAL_ACCELERATION_EVALUATOR,
        SENSOR_STATE_EVALUATOR,
        SENSOR_STATE_PUBLIC_NONEXPERT_GATE,
        ABSOLUTE_POSITION_RAW_EVALUATOR,
        ABSOLUTE_POSITION_PROGRESS_TRANSFORM,
        ABSOLUTE_POSITION_HISTORICAL_SCORER,
        RAW_DISPLACEMENT_EVALUATOR_CONFIGURATION,
        PHYSICAL_TRAJECTORY_EVALUATOR,
    )
    return tuple(EvidenceReference(uri) for evaluator in evaluators for uri in evaluator.provenance)


def evidence_categories() -> tuple[tuple[str, tuple[EvidenceReference, ...]], ...]:
    """Return each consumed SHA evidence occurrence grouped by its owning surface."""
    aliases = tuple(alias.evidence for alias in HISTORICAL_ALIASES)
    alias_sha = tuple(item for item in aliases if item.uri.startswith("registry://sha256/"))
    source_state = (
        *displacement.POSITION_MEASUREMENT_EVIDENCE,
        *displacement.TARGET_TEAM_ORIENTATION_EVIDENCE,
        *displacement.DISPLACEMENT_DATA_STATE_EVIDENCE,
        *displacement.PUBLIC_TRAIN.evidence,
        *displacement.PUBLIC_VALIDATION.evidence,
        *displacement.HISTORICAL_PRIVATE.evidence,
    )
    campaigns = (
        *displacement.FIRST_LOMO_CAMPAIGN.evidence,
        *displacement.SECOND_LOMO_CAMPAIGN.evidence,
        displacement.INVALIDATED_SECOND_CAMPAIGN_AGGREGATE.evidence,
        displacement.CORRECTED_AGGREGATION.evidence,
    )
    model = displacement.FINAL_PUBLIC_MODEL.evidence
    systems = tuple(item.evidence for item in displacement.SYSTEM_VALIDATION_EVIDENCE)
    memberships = tuple(
        evidence
        for binding in BENCHMARK_PROTOCOL_BINDINGS
        for evidence in binding.membership.evidence
    )
    results = tuple(
        evidence for result in displacement.HISTORICAL_RESULTS for evidence in result.evidence
    )
    return (
        (
            "transition_graph",
            tuple(evidence for transition in TRANSITION_GRAPH for evidence in transition.evidence),
        ),
        ("protocol_memberships", memberships),
        ("scientific_lock_provenance", _lock_citations()),
        ("historical_results", results),
        ("historical_displacement_state", source_state),
        ("historical_campaign_state", campaigns),
        ("historical_model_state", tuple(model)),
        ("historical_system_state", systems),
        ("sha_addressed_provenance_aliases", alias_sha),
        ("evaluator_scorer_provenance", _evaluator_references()),
    )


def validate_evidence_inventory(registry_root: Path | None = None) -> EvidenceValidationReport:
    """Validate all public evidence references and optionally resolve them read-only."""
    categories = evidence_categories()
    references = tuple(item for _, values in categories for item in values)
    aliases = tuple(alias.evidence for alias in HISTORICAL_ALIASES)
    legacy_aliases = tuple(
        item for item in aliases if not item.uri.startswith("registry://sha256/")
    )
    errors = [
        f"{category}: {error}"
        for category, values in categories
        for reference in values
        for error in validate_evidence_reference_shape(reference)
    ]
    errors.extend(
        f"legacy alias: {error}"
        for reference in legacy_aliases
        for error in validate_evidence_reference_shape(reference)
    )
    errors.extend(validate_transition_graph())
    errors.extend(validate_canonical_protocols())

    output_hashes = tuple(
        digest for result in displacement.HISTORICAL_RESULTS for digest in result.output_sha256s
    )
    locks = (
        displacement.PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK,
        displacement.LOMO_RAW_SCIENTIFIC_LOCK,
        displacement.PUBLIC_VALIDATION_PHYSICAL_SCIENTIFIC_LOCK,
    )
    for lock in locks:
        errors.extend(validate_scientific_lock_provenance(lock, output_hashes))

    counts: Counter[str] = Counter()
    for reference in references:
        try:
            counts[evidence_sha256(reference)] += 1
        except ValueError as exc:
            errors.append(str(exc))

    strict: EvidenceResolutionReport | None = None
    before: tuple[int, str] | None = None
    after: tuple[int, str] | None = None
    if registry_root is not None:
        try:
            before_digest, before_count = registry_content_digest(registry_root)
            before = (before_count, before_digest)
            if before != (EXPECTED_REGISTRY_PATH_COUNT, EXPECTED_REGISTRY_SHA256):
                errors.append(
                    "registry baseline mismatch before resolution: "
                    f"expected {EXPECTED_REGISTRY_PATH_COUNT} paths / {EXPECTED_REGISTRY_SHA256}, "
                    f"found {before_count} paths / {before_digest}"
                )
            strict = resolve_evidence_references(references, registry_root)
            errors.extend(strict.errors)
        except (OSError, ValueError) as exc:
            errors.append(f"cannot read supplied evidence registry: {exc}")
        finally:
            try:
                after_digest, after_count = registry_content_digest(registry_root)
                after = (after_count, after_digest)
                if before is not None and after != before:
                    errors.append("evidence registry changed during read-only resolution")
                if after != (EXPECTED_REGISTRY_PATH_COUNT, EXPECTED_REGISTRY_SHA256):
                    errors.append(
                        "registry baseline mismatch after resolution: "
                        f"expected {EXPECTED_REGISTRY_PATH_COUNT} paths / "
                        f"{EXPECTED_REGISTRY_SHA256}, "
                        f"found {after_count} paths / {after_digest}"
                    )
            except (OSError, ValueError) as exc:
                errors.append(f"cannot recheck supplied evidence registry: {exc}")

    return EvidenceValidationReport(
        reference_count=len(references),
        unique_digests=len(counts),
        reference_counts_by_digest=tuple(sorted(counts.items())),
        category_counts=tuple((name, len(values)) for name, values in categories),
        legacy_alias_count=len(legacy_aliases),
        legacy_alias_sha_reference_count=len(aliases) - len(legacy_aliases),
        strict_resolution=strict,
        registry_before=before,
        registry_after=after,
        errors=tuple(sorted(set(errors))),
    )


__all__ = ["EvidenceValidationReport", "evidence_categories", "validate_evidence_inventory"]
