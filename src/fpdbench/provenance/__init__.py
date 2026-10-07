"""Scientific evidence references and non-executable historical aliases."""

import re
from dataclasses import dataclass

from fpdbench.provenance.scientific_lock import (
    build_scientific_lock,
    canonical_scientific_bytes,
    compute_scientific_lock_hash,
    validate_scientific_lock_provenance,
    verify_scientific_lock,
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SHA256_URI = re.compile(r"^registry://sha256/([0-9a-f]{64})$")


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    uri: str
    sha256: str | None = None
    description: str = ""
    authority_id: str = "historical_research_registry"

    def __post_init__(self) -> None:
        if not self.uri or not self.authority_id:
            raise ValueError("evidence URI and authority are required")
        errors = validate_evidence_reference_shape(self)
        if errors:
            raise ValueError("; ".join(errors))


@dataclass(frozen=True, slots=True)
class HistoricalAlias:
    value: str
    canonical_id: str
    evidence: EvidenceReference

    def __post_init__(self) -> None:
        if not self.value or not self.canonical_id:
            raise ValueError("historical alias value and canonical target are required")


def validate_evidence_reference_shape(reference: EvidenceReference) -> tuple[str, ...]:
    """Validate content-addressed URI syntax without opening a local registry."""
    errors: list[str] = []
    uri_digest: str | None = None
    if reference.uri.lower().startswith("registry://sha256"):
        match = _SHA256_URI.fullmatch(reference.uri)
        if match is None:
            errors.append(f"malformed SHA-256 evidence URI: {reference.uri}")
        else:
            uri_digest = match.group(1)
    if reference.sha256 is not None and not _SHA256.fullmatch(reference.sha256):
        errors.append(f"malformed EvidenceReference SHA-256 field: {reference.sha256}")
    if uri_digest is not None and reference.sha256 is not None and uri_digest != reference.sha256:
        errors.append("EvidenceReference URI digest and sha256 field disagree")
    return tuple(errors)


__all__ = [
    "EvidenceReference",
    "HistoricalAlias",
    "validate_evidence_reference_shape",
    "build_scientific_lock",
    "canonical_scientific_bytes",
    "compute_scientific_lock_hash",
    "validate_scientific_lock_provenance",
    "verify_scientific_lock",
]
