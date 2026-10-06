"""Scientific evidence references and non-executable historical aliases."""

from dataclasses import dataclass

from fpdbench.provenance.scientific_lock import (
    build_scientific_lock,
    canonical_scientific_bytes,
    compute_scientific_lock_hash,
    verify_scientific_lock,
)


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    uri: str
    sha256: str | None = None
    description: str = ""


@dataclass(frozen=True, slots=True)
class HistoricalAlias:
    value: str
    canonical_id: str
    evidence: EvidenceReference


__all__ = [
    "EvidenceReference",
    "HistoricalAlias",
    "build_scientific_lock",
    "canonical_scientific_bytes",
    "compute_scientific_lock_hash",
    "verify_scientific_lock",
]
