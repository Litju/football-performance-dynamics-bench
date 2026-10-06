"""Scientific evidence references and non-executable historical aliases."""

from dataclasses import dataclass


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
