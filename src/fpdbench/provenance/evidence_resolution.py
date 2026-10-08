"""Optional local, read-only resolution of content-addressed evidence references.

Catalogue support is limited to the forensic ``data_assets.preflight.jsonl``
and R2 absolute-position ``EVALUATOR_STATES.json`` authority records.
"""

import hashlib
import json
import re
import stat
from collections import Counter, defaultdict
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import cast

from fpdbench.provenance import EvidenceReference, validate_evidence_reference_shape
from fpdbench.provenance.registry_digest import registry_content_manifest

_SHA256_URI = re.compile(r"^registry://sha256/([0-9a-f]{64})$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REGISTRY_SLUG = "soccer-trainingload-" + "bmcb"
_DATA_ASSETS = (
    Path("registry") / _REGISTRY_SLUG / "forensic_freeze/preflight/data_assets.preflight.jsonl"
)
_EVALUATOR_SOURCE_TYPES = {
    "DATASET_SCHEMA_OR_MANIFEST",
    "SCIENTIFIC_CODE_OR_TOOL",
    "SCIENTIFIC_CONFIGURATION_OR_RESULT",
}
_EVALUATOR_STATES = (
    Path("registry")
    / _REGISTRY_SLUG
    / "r2/conditional_team_response_absolute_position/EVALUATOR_STATES.json"
)


class EvidenceMatchStatus(StrEnum):
    ZERO_MATCHES = "zero_matches"
    ONE_MATCH = "one_match"
    MULTIPLE_MATCHES = "multiple_matches"


class EvidenceMatchKind(StrEnum):
    DIRECT_REGISTRY_FILE = "DIRECT_REGISTRY_FILE"
    CATALOGUED_SOURCE_ASSET = "CATALOGUED_SOURCE_ASSET"


@dataclass(frozen=True, slots=True)
class EvidenceMatch:
    kind: EvidenceMatchKind
    authority_catalogue_path: str | None
    catalogue_record: str | None
    source_identifier: str
    verified_sha256: str
    asset_role: str | None = None


@dataclass(frozen=True, slots=True)
class EvidenceDigestResolution:
    sha256: str
    reference_count: int
    status: EvidenceMatchStatus
    matches: tuple[EvidenceMatch, ...]


@dataclass(frozen=True, slots=True)
class EvidenceResolutionReport:
    total_references: int
    unique_digests: int
    zero_match_count: int
    single_match_count: int
    multi_match_count: int
    resolutions: tuple[EvidenceDigestResolution, ...]
    errors: tuple[str, ...]


def _safe_source_identifier(source: Path) -> str:
    parts = source.parts
    if _REGISTRY_SLUG in parts:
        suffix = Path(*parts[parts.index(_REGISTRY_SLUG) :]).as_posix()
    else:
        suffix = source.name
    return f"local-source://{suffix}"


def _hash_local_source(source_text: object) -> tuple[str | None, str | None, str | None]:
    if not isinstance(source_text, str) or not source_text:
        return None, None, "source path is missing or not a string"
    source = Path(source_text)
    if not source.is_absolute() or ".." in source.parts:
        return None, None, "source pointer is not an unambiguous absolute local path"
    if any(
        "j03wmx" in part.lower() or ("private" in part.lower() and "truth" in part.lower())
        for part in source.parts
    ):
        return None, None, "source pointer names forbidden private qualification truth"
    identifier = _safe_source_identifier(source)
    try:
        source_stat = source.lstat()
        if not stat.S_ISREG(source_stat.st_mode):
            return identifier, None, "source is not a regular file"
        digest = hashlib.sha256()
        with source.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        return identifier, None, f"source cannot be read ({exc.__class__.__name__})"
    return identifier, digest.hexdigest(), None


def _catalogue_is_regular(path: Path, errors: list[str]) -> bool:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return False
    except OSError as exc:
        errors.append(f"{path}: cannot inspect catalogue ({exc.__class__.__name__})")
        return False
    if not stat.S_ISREG(mode):
        errors.append(f"{path}: catalogue is not a regular file")
        return False
    return True


def _catalogued_match(
    *,
    catalogue_path: str,
    catalogue_record: str,
    source_text: object,
    expected_sha256: object,
    asset_role: str | None,
    errors: list[str],
) -> EvidenceMatch | None:
    if not isinstance(expected_sha256, str) or not _SHA256.fullmatch(expected_sha256):
        errors.append(f"{catalogue_path} {catalogue_record}: malformed expected SHA-256")
        return None
    identifier, actual_sha256, error = _hash_local_source(source_text)
    if error is not None or identifier is None or actual_sha256 is None:
        errors.append(
            f"{catalogue_path} {catalogue_record}: {error or 'source could not be verified'}"
        )
        return None
    if actual_sha256 != expected_sha256:
        errors.append(
            f"{catalogue_path} {catalogue_record}: expected SHA-256 {expected_sha256}, "
            f"found {actual_sha256} ({identifier})"
        )
        return None
    return EvidenceMatch(
        kind=EvidenceMatchKind.CATALOGUED_SOURCE_ASSET,
        authority_catalogue_path=catalogue_path,
        catalogue_record=catalogue_record,
        source_identifier=identifier,
        verified_sha256=actual_sha256,
        asset_role=asset_role,
    )


def _catalogue_source_matches(
    root: Path, requested_sha256s: set[str], errors: list[str]
) -> dict[str, list[EvidenceMatch]]:
    matches: dict[str, list[EvidenceMatch]] = defaultdict(list)
    data_catalogue = root / _DATA_ASSETS
    if _catalogue_is_regular(data_catalogue, errors):
        try:
            with data_catalogue.open(encoding="utf-8") as stream:
                for line_number, line in enumerate(stream, 1):
                    try:
                        parsed: object = json.loads(line)
                    except json.JSONDecodeError:
                        errors.append(f"{_DATA_ASSETS} line:{line_number}: invalid JSON record")
                        continue
                    if not isinstance(parsed, dict):
                        errors.append(
                            f"{_DATA_ASSETS} line:{line_number}: unsupported record shape"
                        )
                        continue
                    record = cast(dict[str, object], parsed)
                    digest = record.get("recorded_sha256")
                    if not isinstance(digest, str) or digest not in requested_sha256s:
                        continue
                    artifact_id = record.get("artifact_id")
                    artifact_type = record.get("artifact_type")
                    category = record.get("category")
                    original_path = record.get("original_path")
                    if (
                        not isinstance(artifact_id, str)
                        or not artifact_id
                        or not isinstance(artifact_type, str)
                        or not artifact_type
                        or not isinstance(category, str)
                        or not category
                        or not isinstance(original_path, str)
                        or not original_path
                    ):
                        record_id = f"line:{line_number}"
                        errors.append(f"{_DATA_ASSETS} {record_id}: unsupported record shape")
                        continue
                    record_id = f"line:{line_number} artifact_id={artifact_id}"
                    if artifact_type != "DATA_ASSET":
                        errors.append(f"{_DATA_ASSETS} {record_id}: unsupported asset type")
                        continue
                    if (
                        record.get("availability") != "PRESENT"
                        or record.get("exists") is not True
                        or record.get("is_file") is not True
                        or record.get("inventory_stable") is not True
                        or record.get("inventory_error") is not None
                    ):
                        errors.append(
                            f"{_DATA_ASSETS} {record_id}: catalogue does not mark source "
                            "present and stable"
                        )
                        continue
                    match = _catalogued_match(
                        catalogue_path=_DATA_ASSETS.as_posix(),
                        catalogue_record=record_id,
                        source_text=original_path,
                        expected_sha256=digest,
                        asset_role=category,
                        errors=errors,
                    )
                    if match is not None:
                        matches[digest].append(match)
        except OSError as exc:
            errors.append(f"{_DATA_ASSETS}: cannot read catalogue ({exc.__class__.__name__})")

    evaluator_catalogue = root / _EVALUATOR_STATES
    if _catalogue_is_regular(evaluator_catalogue, errors):
        try:
            with evaluator_catalogue.open(encoding="utf-8") as stream:
                evaluator_state: object = json.load(stream)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{_EVALUATOR_STATES}: cannot read catalogue ({exc.__class__.__name__})")
        else:
            states_value = (
                cast(dict[str, object], evaluator_state).get("states")
                if isinstance(evaluator_state, dict)
                else None
            )
            if not isinstance(states_value, dict):
                errors.append(f"{_EVALUATOR_STATES}: unsupported catalogue shape")
            else:
                for state_id, state_value in cast(dict[str, object], states_value).items():
                    evidence_value = (
                        cast(dict[str, object], state_value).get("evidence")
                        if isinstance(state_value, dict)
                        else None
                    )
                    if not isinstance(evidence_value, list):
                        errors.append(
                            f"{_EVALUATOR_STATES} states.{state_id}: unsupported evidence shape"
                        )
                        continue
                    for index, record_value in enumerate(cast(list[object], evidence_value)):
                        if not isinstance(record_value, dict):
                            errors.append(
                                f"{_EVALUATOR_STATES} states.{state_id}.evidence[{index}]: "
                                "unsupported record shape"
                            )
                            continue
                        record = cast(dict[str, object], record_value)
                        digest = record.get("sha256")
                        if not isinstance(digest, str) or digest not in requested_sha256s:
                            continue
                        artifact_id = record.get("artifact_id")
                        artifact_type = record.get("artifact_type")
                        source_path = record.get("path")
                        supports = record.get("supports")
                        if (
                            not isinstance(artifact_id, str)
                            or not artifact_id
                            or not isinstance(artifact_type, str)
                            or not artifact_type
                            or not isinstance(source_path, str)
                            or not source_path
                            or not isinstance(supports, str)
                            or not supports
                        ):
                            record_id = f"states.{state_id}.evidence[{index}]"
                            errors.append(
                                f"{_EVALUATOR_STATES} {record_id}: unsupported record shape"
                            )
                            continue
                        record_id = f"states.{state_id}.evidence[{index}] artifact_id={artifact_id}"
                        if artifact_type not in _EVALUATOR_SOURCE_TYPES:
                            errors.append(
                                f"{_EVALUATOR_STATES} {record_id}: unsupported asset type "
                                f"{artifact_type}"
                            )
                            continue
                        match = _catalogued_match(
                            catalogue_path=_EVALUATOR_STATES.as_posix(),
                            catalogue_record=record_id,
                            source_text=source_path,
                            expected_sha256=digest,
                            asset_role=artifact_type,
                            errors=errors,
                        )
                        if match is not None:
                            matches[digest].append(match)
    return matches


def resolve_evidence_references(
    references: tuple[EvidenceReference, ...], registry_root: Path
) -> EvidenceResolutionReport:
    """Resolve SHA URIs from direct registry files and explicit authority catalogues."""
    errors: list[str] = []
    references_by_digest: dict[str, list[EvidenceReference]] = defaultdict(list)
    for reference in references:
        errors.extend(validate_evidence_reference_shape(reference))
        match = _SHA256_URI.fullmatch(reference.uri)
        if match is None:
            errors.append(f"strict resolution requires a registry://sha256 URI: {reference.uri}")
        else:
            references_by_digest[match.group(1)].append(reference)

    matches_by_digest: dict[str, list[EvidenceMatch]] = defaultdict(list)
    for entry in registry_content_manifest(registry_root):
        if entry.kind == "file" and entry.sha256 in references_by_digest:
            matches_by_digest[entry.sha256].append(
                EvidenceMatch(
                    kind=EvidenceMatchKind.DIRECT_REGISTRY_FILE,
                    authority_catalogue_path=None,
                    catalogue_record=None,
                    source_identifier=entry.path,
                    verified_sha256=entry.sha256,
                )
            )

    catalogued = _catalogue_source_matches(registry_root, set(references_by_digest), errors)
    for digest, matches in catalogued.items():
        matches_by_digest[digest].extend(matches)

    resolutions: list[EvidenceDigestResolution] = []
    for digest in sorted(references_by_digest):
        matches = tuple(
            sorted(
                matches_by_digest[digest],
                key=lambda item: (
                    item.kind.value,
                    item.authority_catalogue_path or "",
                    item.catalogue_record or "",
                    item.source_identifier,
                ),
            )
        )
        status = (
            EvidenceMatchStatus.ZERO_MATCHES
            if not matches
            else EvidenceMatchStatus.ONE_MATCH
            if len(matches) == 1
            else EvidenceMatchStatus.MULTIPLE_MATCHES
        )
        if status is EvidenceMatchStatus.ZERO_MATCHES:
            errors.append(f"no verified evidence source matches SHA-256 {digest}")
        resolutions.append(
            EvidenceDigestResolution(digest, len(references_by_digest[digest]), status, matches)
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
