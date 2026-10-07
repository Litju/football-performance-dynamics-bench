import hashlib
import json
import os
from pathlib import Path

import pytest

from fpdbench.provenance import EvidenceReference
from fpdbench.provenance.evidence_resolution import (
    EvidenceMatchStatus,
    resolve_evidence_references,
)
from fpdbench.provenance.registry_digest import registry_content_digest


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
    records.sort(key=lambda record: record["path"].encode("utf-8"))
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


def test_strict_evidence_resolution_reports_all_duplicate_paths_read_only(tmp_path: Path) -> None:
    (tmp_path / "first.txt").write_bytes(b"duplicate evidence")
    (tmp_path / "second.txt").write_bytes(b"duplicate evidence")
    (tmp_path / "unique.txt").write_bytes(b"single evidence")
    os.symlink("first.txt", tmp_path / "link.txt")

    duplicate_digest = hashlib.sha256(b"duplicate evidence").hexdigest()
    unique_digest = hashlib.sha256(b"single evidence").hexdigest()
    missing_digest = "a" * 64
    references = (
        EvidenceReference(f"registry://sha256/{duplicate_digest}", duplicate_digest),
        EvidenceReference(f"registry://sha256/{duplicate_digest}", duplicate_digest),
        EvidenceReference(f"registry://sha256/{unique_digest}", unique_digest),
        EvidenceReference(f"registry://sha256/{missing_digest}", missing_digest),
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
    assert duplicate.paths == ("first.txt", "second.txt")
    unique = next(item for item in report.resolutions if item.sha256 == unique_digest)
    assert unique.status is EvidenceMatchStatus.ONE_MATCH
    assert unique.paths == ("unique.txt",)
    missing = next(item for item in report.resolutions if item.sha256 == missing_digest)
    assert missing.status is EvidenceMatchStatus.ZERO_MATCHES
    assert report.errors == (f"no registry file matches SHA-256 {missing_digest}",)


def test_evidence_reference_rejects_malformed_or_disagreeing_hashes() -> None:
    for uri in (
        "registry://sha256/not-a-digest",
        f"registry://SHA256/{'a' * 64}",
    ):
        with pytest.raises(ValueError, match="malformed SHA-256 evidence URI"):
            EvidenceReference(uri)

    with pytest.raises(ValueError, match="disagree"):
        EvidenceReference(f"registry://sha256/{'a' * 64}", "b" * 64)
