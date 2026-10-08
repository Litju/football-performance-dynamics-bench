"""Content-addressed bindings and execution provenance for experiment manifests."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar, cast

from fpdbench.data import ArtifactReference
from fpdbench.provenance import (
    EvidenceReference,
    validate_evidence_reference_shape,
    verify_scientific_lock,
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SHA256_URI = re.compile(r"^registry://sha256/([0-9a-f]{64})$")


def validate_sha256(value: object, field: str) -> None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")


def stable_manifest_hash(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def evidence_sha256(reference: EvidenceReference) -> str:
    errors = validate_evidence_reference_shape(reference)
    if errors:
        raise ValueError("; ".join(errors))
    if reference.sha256 is not None:
        return reference.sha256
    match = _SHA256_URI.fullmatch(reference.uri)
    if match is None:
        raise ValueError("immutable evidence requires a SHA-256 reference")
    return match.group(1)


_BINDING_FIELDS = (
    ("benchmark_id", "benchmark_id"),
    ("data_release_id", "data_release_id"),
    ("data_release_version", "data_release_version"),
    ("data_manifest_hash", "data_manifest_hash"),
    ("data_state_id", "data_state_id"),
    ("split_protocol_id", "split_protocol_id"),
    ("split_protocol_version", "split_protocol_version"),
    ("split_protocol_hash", "split_protocol_hash"),
    ("evaluator_id", "evaluator_id"),
    ("evaluator_version", "evaluator_version"),
    ("evaluator_hash", "evaluator_hash"),
    ("schema_version", "schema_version"),
    ("schema_hash", "schema_hash"),
    ("fixture_manifest_hash", "fixture_manifest_hash"),
)


@dataclass(frozen=True, slots=True, init=False)
class ScientificStateBinding:
    """Inspectable scientific identity copied only from a verified lock."""

    scientific_lock_hash: str
    benchmark_id: str
    data_release_id: str
    data_release_version: str
    data_manifest_hash: str
    data_state_id: str
    split_protocol_id: str
    split_protocol_version: str
    split_protocol_hash: str
    evaluator_id: str
    evaluator_version: str
    evaluator_hash: str
    schema_version: str
    schema_hash: str
    fixture_manifest_hash: str

    def __init__(self, scientific_lock: object) -> None:
        if not isinstance(scientific_lock, Mapping) or not verify_scientific_lock(
            cast(Mapping[str, object], scientific_lock)
        ):
            raise ValueError("ScientificStateBinding requires a verified scientific lock")
        lock = cast(Mapping[str, object], scientific_lock)
        lock_hash = lock.get("scientific_lock_hash")
        if not isinstance(lock_hash, str):
            raise ValueError("verified scientific lock has no hash")
        object.__setattr__(self, "scientific_lock_hash", lock_hash)
        for attribute, lock_field in _BINDING_FIELDS:
            value = lock.get(lock_field)
            if not isinstance(value, str):
                raise ValueError(f"verified scientific lock has invalid {lock_field}")
            object.__setattr__(self, attribute, value)

    @classmethod
    def from_verified_lock(cls, scientific_lock: object) -> ScientificStateBinding:
        return cls(scientific_lock)

    def matches(self, scientific_lock: object) -> bool:
        try:
            return self == ScientificStateBinding.from_verified_lock(scientific_lock)
        except ValueError:
            return False

    def identity_payload(self) -> dict[str, str]:
        return {
            "scientific_lock_hash": self.scientific_lock_hash,
            **{attribute: getattr(self, attribute) for attribute, _ in _BINDING_FIELDS},
        }


class ProvenanceCompleteness(StrEnum):
    EXECUTION_MANIFEST_BOUND = "execution_manifest_bound"
    HISTORICAL_EVIDENCE_BOUND = "historical_evidence_bound"


@dataclass(frozen=True, slots=True)
class EnvironmentFingerprint:
    """Deterministic runtime identity; host-specific metadata is not represented."""

    runtime_version: str
    dependency_lock_sha256: str
    source_revision: str
    source_tree_sha256: str | None = None
    container_image_digest: str | None = None
    platform_accelerator: tuple[tuple[str, str], ...] = ()

    SCHEMA_ID: ClassVar[str] = "fpdbench.environment-fingerprint"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if not self.runtime_version or not self.source_revision:
            raise ValueError("environment runtime and source revision are required")
        if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", self.source_revision):
            raise ValueError("source revision must be an immutable Git SHA-1 or SHA-256")
        validate_sha256(self.dependency_lock_sha256, "dependency lock SHA-256")
        if self.source_tree_sha256 is not None:
            validate_sha256(self.source_tree_sha256, "source tree SHA-256")
        if self.container_image_digest is not None and not re.fullmatch(
            r"sha256:[0-9a-f]{64}", self.container_image_digest
        ):
            raise ValueError("container image digest must use sha256:<lowercase digest>")
        object.__setattr__(self, "platform_accelerator", tuple(self.platform_accelerator))
        names = [name for name, _ in self.platform_accelerator]
        if any(not name or not value for name, value in self.platform_accelerator):
            raise ValueError("platform descriptors must have nonempty names and values")
        if len(names) != len(set(names)):
            raise ValueError("platform descriptor names must be unique")

    def identity_payload(self) -> dict[str, object]:
        return {
            "schema_id": self.SCHEMA_ID,
            "schema_version": self.SCHEMA_VERSION,
            "runtime_version": self.runtime_version,
            "dependency_lock_sha256": self.dependency_lock_sha256,
            "source_revision": self.source_revision,
            "source_tree_sha256": self.source_tree_sha256,
            "container_image_digest": self.container_image_digest,
            "platform_accelerator": sorted(self.platform_accelerator),
        }

    @property
    def manifest_hash(self) -> str:
        return stable_manifest_hash(self.identity_payload())


@dataclass(frozen=True, slots=True)
class ExecutionProvenance:
    """Execution identifier and immutable evidence; metadata is descriptive only."""

    execution_id: str
    evidence: tuple[EvidenceReference, ...] = ()
    metadata: tuple[tuple[str, str], ...] = ()

    SCHEMA_ID: ClassVar[str] = "fpdbench.execution-provenance"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if not self.execution_id:
            raise ValueError("execution provenance requires an execution ID")
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "metadata", tuple(self.metadata))
        if len({key for key, _ in self.metadata}) != len(self.metadata):
            raise ValueError("execution metadata keys must be unique")
        for reference in self.evidence:
            evidence_sha256(reference)

    def identity_payload(self) -> dict[str, object]:
        return {
            "schema_id": self.SCHEMA_ID,
            "schema_version": self.SCHEMA_VERSION,
            "execution_id": self.execution_id,
            "evidence_sha256": sorted(evidence_sha256(item) for item in self.evidence),
        }

    @property
    def manifest_hash(self) -> str:
        return stable_manifest_hash(self.identity_payload())


class ArtifactRelation(StrEnum):
    INPUT = "input"
    OUTPUT = "output"
    DIAGNOSTIC = "diagnostic"


@dataclass(frozen=True, slots=True)
class ArtifactDeclaration:
    artifact_id: str
    role: str
    relation: ArtifactRelation
    reference: ArtifactReference
    content_type: str | None = None

    def __post_init__(self) -> None:
        if not self.artifact_id or not self.role:
            raise ValueError("artifact ID and role are required")
        if self.content_type is not None and not self.content_type:
            raise ValueError("artifact content type must be nonempty when supplied")

    def identity_payload(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "role": self.role,
            "relation": self.relation.value,
            "content_type": self.content_type,
            "sha256": self.reference.sha256,
            "size_bytes": self.reference.size_bytes,
        }


__all__ = [
    "ArtifactDeclaration",
    "ArtifactRelation",
    "EnvironmentFingerprint",
    "ExecutionProvenance",
    "ProvenanceCompleteness",
    "ScientificStateBinding",
    "evidence_sha256",
    "stable_manifest_hash",
    "validate_sha256",
]
