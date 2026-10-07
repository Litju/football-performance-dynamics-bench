"""Scientific evidence references and non-executable historical aliases."""

from dataclasses import dataclass

from fpdbench.provenance.scientific_lock import (
    build_scientific_lock,
    canonical_scientific_bytes,
    compute_scientific_lock_hash,
    validate_scientific_lock_provenance,
    verify_scientific_lock,
)


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    uri: str
    sha256: str | None = None
    description: str = ""
    authority_id: str = "historical_research_registry"

    def __post_init__(self) -> None:
        if not self.uri or not self.authority_id:
            raise ValueError("evidence URI and authority are required")


@dataclass(frozen=True, slots=True)
class HistoricalAlias:
    value: str
    canonical_id: str
    evidence: EvidenceReference

    def __post_init__(self) -> None:
        if not self.value or not self.canonical_id:
            raise ValueError("historical alias value and canonical target are required")


__all__ = [
    "EvidenceReference",
    "HistoricalAlias",
    "build_scientific_lock",
    "canonical_scientific_bytes",
    "compute_scientific_lock_hash",
    "validate_scientific_lock_provenance",
    "verify_scientific_lock",
]
