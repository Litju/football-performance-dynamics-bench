import hashlib
import json
import os
from pathlib import Path

import pytest

from fpdbench.provenance import EvidenceReference
from fpdbench.provenance.aliases import HISTORICAL_ALIASES
from fpdbench.provenance.evidence_inventory import validate_evidence_inventory
from fpdbench.provenance.evidence_resolution import (
    EvidenceMatchKind,
    EvidenceMatchStatus,
    resolve_evidence_references,
)
from fpdbench.provenance.registry_digest import registry_content_digest

_REGISTRY_SLUG = "soccer-trainingload-" + "bmcb"
_DATA_ASSETS = (
    Path("registry") / _REGISTRY_SLUG / "forensic_freeze/preflight/data_assets.preflight.jsonl"
)
_EVALUATOR_STATES = (
    Path("registry")
    / _REGISTRY_SLUG
    / "r2/conditional_team_response_absolute_position/EVALUATOR_STATES.json"
)


def _reference(digest: str) -> EvidenceReference:
    return EvidenceReference(f"registry://sha256/{digest}", digest)


def _data_asset_record(digest: str, path: Path) -> dict[str, object]:
    return {
        "artifact_id": "data-test-asset",
        "artifact_type": "DATA_ASSET",
        "availability": "PRESENT",
        "category": "Public train fixture",
        "exists": True,
        "inventory_error": None,
        "inventory_stable": True,
        "is_file": True,
        "original_path": str(path),
        "recorded_sha256": digest,
    }


def _write_data_assets(root: Path, records: list[dict[str, object]]) -> None:
    path = root / _DATA_ASSETS
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(record) + "\n" for record in records))


def test_registry_digest_normalizes_paths_excludes_git_and_hashes_symlinks(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "ignored").write_bytes(b"ignored")
    (tmp_path / ".hidden").write_bytes(b"hidden")
    (tmp_path / "visible").write_bytes(b"evidence")
    (tmp_path / "e\u0301.txt").write_bytes(b"unicode")
    os.symlink("visible", tmp_path / "link")

    digest, count = registry_content_digest(tmp_path)
    records = [
        {
            "kind": "file",
            "path": ".hidden",
            "sha256": hashlib.sha256(b"hidden").hexdigest(),
        },
        {
            "kind": "symlink",
            "path": "link",
            "sha256": hashlib.sha256(b"visible").hexdigest(),
        },
        {
            "kind": "file",
            "path": "visible",
            "sha256": hashlib.sha256(b"evidence").hexdigest(),
        },
        {
            "kind": "file",
            "path": "\u00e9.txt",
            "sha256": hashlib.sha256(b"unicode").hexdigest(),
        },
    ]
    records.sort(key=lambda record: str(record["path"]).encode("utf-8"))
    manifest = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for record in records
    ).encode("utf-8")

    assert count == 4
    assert digest == hashlib.sha256(manifest).hexdigest()


def test_registry_root_must_not_be_a_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    root_link = tmp_path / "root-link"
    os.symlink(target, root_link, target_is_directory=True)

    with pytest.raises(ValueError, match="must not be a symlink"):
        registry_content_digest(root_link)


def test_direct_registry_file_resolution_reports_every_match_read_only(tmp_path: Path) -> None:
    (tmp_path / "first.txt").write_bytes(b"duplicate evidence")
    (tmp_path / "second.txt").write_bytes(b"duplicate evidence")
    (tmp_path / "unique.txt").write_bytes(b"single evidence")
    os.symlink("first.txt", tmp_path / "link.txt")

    duplicate_digest = hashlib.sha256(b"duplicate evidence").hexdigest()
    unique_digest = hashlib.sha256(b"single evidence").hexdigest()
    missing_digest = "a" * 64
    references = (
        _reference(duplicate_digest),
        _reference(duplicate_digest),
        _reference(unique_digest),
        _reference(missing_digest),
    )
    before = registry_content_digest(tmp_path)
    report = resolve_evidence_references(references, tmp_path)
    after = registry_content_digest(tmp_path)

    assert before == after
    assert report.total_references == 4
    assert report.unique_digests == 3
    assert (report.zero_match_count, report.single_match_count, report.multi_match_count) == (
        1,
        1,
        1,
    )
    duplicate = next(item for item in report.resolutions if item.sha256 == duplicate_digest)
    assert duplicate.status is EvidenceMatchStatus.MULTIPLE_MATCHES
    assert tuple(match.source_identifier for match in duplicate.matches) == (
        "first.txt",
        "second.txt",
    )
    assert all(match.kind is EvidenceMatchKind.DIRECT_REGISTRY_FILE for match in duplicate.matches)
    unique = next(item for item in report.resolutions if item.sha256 == unique_digest)
    assert unique.status is EvidenceMatchStatus.ONE_MATCH
    assert unique.matches[0].verified_sha256 == unique_digest
    assert unique.matches[0].authority_catalogue_path is None
    missing = next(item for item in report.resolutions if item.sha256 == missing_digest)
    assert missing.status is EvidenceMatchStatus.ZERO_MATCHES
    assert report.errors == (f"no verified evidence source matches SHA-256 {missing_digest}",)


def test_forensic_asset_catalogue_rehashes_local_source_bytes(tmp_path: Path) -> None:
    root = tmp_path / "registry"
    source = tmp_path / "source" / "part-000.parquet"
    source.parent.mkdir()
    source.write_bytes(b"catalogued fixture bytes")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    _write_data_assets(root, [_data_asset_record(digest, source)])
    before = registry_content_digest(root)

    report = resolve_evidence_references((_reference(digest),), root)

    assert registry_content_digest(root) == before
    assert report.errors == ()
    match = report.resolutions[0].matches[0]
    assert report.resolutions[0].status is EvidenceMatchStatus.ONE_MATCH
    assert match.kind is EvidenceMatchKind.CATALOGUED_SOURCE_ASSET
    assert match.authority_catalogue_path == _DATA_ASSETS.as_posix()
    assert match.catalogue_record == "line:1 artifact_id=data-test-asset"
    assert match.source_identifier == "local-source://part-000.parquet"
    assert match.verified_sha256 == digest


def test_evaluator_state_catalogue_rehashes_source_code(tmp_path: Path) -> None:
    root = tmp_path / "registry"
    source = tmp_path / "source" / "s6f_platform_metrics.py"
    source.parent.mkdir()
    source.write_bytes(b"metric implementation")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    catalogue = root / _EVALUATOR_STATES
    catalogue.parent.mkdir(parents=True)
    state_id = "SC-" + "R0-" + "SC-005"
    catalogue.write_text(
        json.dumps(
            {
                "states": {
                    state_id: {
                        "evidence": [
                            {
                                "artifact_id": "art-source",
                                "artifact_type": "SCIENTIFIC_CODE_OR_TOOL",
                                "path": str(source),
                                "sha256": digest,
                                "supports": "metric arithmetic",
                            }
                        ]
                    }
                }
            }
        )
    )

    report = resolve_evidence_references((_reference(digest),), root)

    assert report.errors == ()
    match = report.resolutions[0].matches[0]
    assert match.kind is EvidenceMatchKind.CATALOGUED_SOURCE_ASSET
    assert match.authority_catalogue_path == _EVALUATOR_STATES.as_posix()
    assert match.catalogue_record == f"states.{state_id}.evidence[0] artifact_id=art-source"
    assert match.source_identifier == "local-source://s6f_platform_metrics.py"
    assert match.verified_sha256 == digest


def test_catalogue_record_with_missing_source_fails_closed(tmp_path: Path) -> None:
    digest = hashlib.sha256(b"expected bytes").hexdigest()
    _write_data_assets(
        tmp_path,
        [_data_asset_record(digest, tmp_path / "absent.parquet")],
    )

    report = resolve_evidence_references((_reference(digest),), tmp_path)

    assert report.resolutions[0].status is EvidenceMatchStatus.ZERO_MATCHES
    assert len(report.errors) == 2
    assert any("FileNotFoundError" in error for error in report.errors)


def test_catalogue_digest_mismatch_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "part.parquet"
    source.write_bytes(b"actual bytes")
    expected = hashlib.sha256(b"expected bytes").hexdigest()
    _write_data_assets(tmp_path, [_data_asset_record(expected, source)])

    report = resolve_evidence_references((_reference(expected),), tmp_path)

    assert report.resolutions[0].status is EvidenceMatchStatus.ZERO_MATCHES
    assert any("expected SHA-256" in error and "found" in error for error in report.errors)


def test_catalogue_non_regular_source_fails_closed(tmp_path: Path) -> None:
    digest = hashlib.sha256(b"expected bytes").hexdigest()
    source = tmp_path / "source-directory"
    source.mkdir()
    _write_data_assets(tmp_path, [_data_asset_record(digest, source)])

    report = resolve_evidence_references((_reference(digest),), tmp_path)

    assert report.resolutions[0].status is EvidenceMatchStatus.ZERO_MATCHES
    assert any("source is not a regular file" in error for error in report.errors)


def test_network_only_catalogue_source_is_not_fetched(tmp_path: Path) -> None:
    digest = hashlib.sha256(b"remote bytes").hexdigest()
    _write_data_assets(
        tmp_path,
        [_data_asset_record(digest, Path("https://example.invalid/asset.parquet"))],
    )

    report = resolve_evidence_references((_reference(digest),), tmp_path)

    assert report.resolutions[0].status is EvidenceMatchStatus.ZERO_MATCHES
    assert any("absolute local path" in error for error in report.errors)


def test_private_qualification_source_is_not_opened(tmp_path: Path) -> None:
    digest = hashlib.sha256(b"private bytes").hexdigest()
    source = Path("/tmp/J03WMX/private_truth.parquet")
    _write_data_assets(tmp_path, [_data_asset_record(digest, source)])

    report = resolve_evidence_references((_reference(digest),), tmp_path)

    assert report.resolutions[0].status is EvidenceMatchStatus.ZERO_MATCHES
    assert any("forbidden private qualification truth" in error for error in report.errors)


def test_unsupported_matching_catalogue_shape_fails_closed(tmp_path: Path) -> None:
    digest = hashlib.sha256(b"expected bytes").hexdigest()
    record = _data_asset_record(digest, tmp_path / "part.parquet")
    del record["original_path"]
    _write_data_assets(tmp_path, [record])

    report = resolve_evidence_references((_reference(digest),), tmp_path)

    assert report.resolutions[0].status is EvidenceMatchStatus.ZERO_MATCHES
    assert any("unsupported record shape" in error for error in report.errors)


def test_all_verified_direct_and_catalogue_matches_are_reported(tmp_path: Path) -> None:
    root = tmp_path / "registry"
    content = b"same evidence from three sources"
    digest = hashlib.sha256(content).hexdigest()
    (root / "direct.bin").parent.mkdir(parents=True)
    (root / "direct.bin").write_bytes(content)
    first = tmp_path / "source-one" / "fixture.bin"
    second = tmp_path / "source-two" / "fixture.bin"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_bytes(content)
    second.write_bytes(content)
    _write_data_assets(
        root,
        [_data_asset_record(digest, first), _data_asset_record(digest, second)],
    )

    report = resolve_evidence_references((_reference(digest),), root)

    resolution = report.resolutions[0]
    assert resolution.status is EvidenceMatchStatus.MULTIPLE_MATCHES
    assert len(resolution.matches) == 3
    assert (
        sum(match.kind is EvidenceMatchKind.DIRECT_REGISTRY_FILE for match in resolution.matches)
        == 1
    )
    assert (
        sum(match.kind is EvidenceMatchKind.CATALOGUED_SOURCE_ASSET for match in resolution.matches)
        == 2
    )
    assert {match.verified_sha256 for match in resolution.matches} == {digest}
    assert {match.catalogue_record for match in resolution.matches if match.catalogue_record} == {
        "line:1 artifact_id=data-test-asset",
        "line:2 artifact_id=data-test-asset",
    }


def test_public_inventory_is_registry_independent_and_legacy_aliases_stay_legacy(
    tmp_path: Path,
) -> None:
    report = validate_evidence_inventory(None)
    legacy = tuple(
        alias.evidence.uri
        for alias in HISTORICAL_ALIASES
        if alias.evidence.uri.startswith("registry://r2/")
    )
    legacy_resolution = resolve_evidence_references(
        tuple(EvidenceReference(uri) for uri in legacy), tmp_path
    )

    assert report.errors == ()
    assert report.strict_resolution is None
    assert report.reference_count == 232
    assert report.unique_digests == 63
    assert report.legacy_alias_count == 5
    assert len(legacy) == 5
    assert legacy_resolution.unique_digests == 0
    assert all("strict resolution requires" in error for error in legacy_resolution.errors)


def test_evidence_reference_rejects_malformed_or_disagreeing_hashes() -> None:
    for uri in (
        "registry://sha256/not-a-digest",
        f"registry://SHA256/{'a' * 64}",
    ):
        with pytest.raises(ValueError, match="malformed SHA-256 evidence URI"):
            EvidenceReference(uri)

    with pytest.raises(ValueError, match="disagree"):
        EvidenceReference(f"registry://sha256/{'a' * 64}", "b" * 64)
