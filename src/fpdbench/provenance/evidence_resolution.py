"""Optional local, read-only resolution of content-addressed evidence references."""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from fpdbench.provenance import EvidenceReference, validate_evidence_reference_shape
from fpdbench.provenance.registry_digest import registry_content_manifest

_SHA256_URI = re.compile(r"^registry://sha256/([0-9a-f]{64})$")


class EvidenceMatchStatus(StrEnum):
    ZERO_MATCHES = "zero_matches"
    ONE_MATCH = "one_match"
    MULTIPLE_MATCHES = "multiple_matches"


@dataclass(frozen=True, slots=True)
class EvidenceDigestResolution:
    sha256: str
    reference_count: int
    status: EvidenceMatchStatus
    paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvidenceResolutionReport:
    total_references: int
    unique_digests: int
    zero_match_count: int
    single_match_count: int
    multi_match_count: int
    resolutions: tuple[EvidenceDigestResolution, ...]
    errors: tuple[str, ...]


def resolve_evidence_references(
    references: tuple[EvidenceReference, ...], registry_root: Path
) -> EvidenceResolutionReport:
    """Resolve every SHA URI; duplicate-content paths are all returned in sorted order."""
    errors: list[str] = []
    references_by_digest: dict[str, list[EvidenceReference]] = defaultdict(list)
    for reference in references:
        errors.extend(validate_evidence_reference_shape(reference))
        match = _SHA256_URI.fullmatch(reference.uri)
        if match is None:
            errors.append(f"strict resolution requires a registry://sha256 URI: {reference.uri}")
        else:
            references_by_digest[match.group(1)].append(reference)

    paths_by_digest: dict[str, list[str]] = defaultdict(list)
    for entry in registry_content_manifest(registry_root):
        if entry.kind == "file" and entry.sha256 in references_by_digest:
            paths_by_digest[entry.sha256].append(entry.path)

    resolutions: list[EvidenceDigestResolution] = []
    for digest in sorted(references_by_digest):
        paths = tuple(sorted(paths_by_digest[digest]))
        status = (
            EvidenceMatchStatus.ZERO_MATCHES
            if not paths
            else EvidenceMatchStatus.ONE_MATCH
            if len(paths) == 1
            else EvidenceMatchStatus.MULTIPLE_MATCHES
        )
        if status is EvidenceMatchStatus.ZERO_MATCHES:
            errors.append(f"no registry file matches SHA-256 {digest}")
        resolutions.append(
            EvidenceDigestResolution(digest, len(references_by_digest[digest]), status, paths)
        )

    counts = Counter(item.status for item in resolutions)
    return EvidenceResolutionReport(
        total_references=len(references),
        unique_digests=len(resolutions),
        zero_match_count=counts[EvidenceMatchStatus.ZERO_MATCHES],
        single_match_count=counts[EvidenceMatchStatus.ONE_MATCH],
        multi_match_count=counts[EvidenceMatchStatus.MULTIPLE_MATCHES],
        resolutions=tuple(resolutions),
        errors=tuple(sorted(set(errors))),
    )
