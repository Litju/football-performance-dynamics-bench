"""Source-only versioning, citation and manual publication boundary checks."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_candidate_package_and_lockfile_are_same_version() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    version = project["project"]["version"]
    assert version == "1.0.0"
    packages = [
        pkg
        for pkg in lock["package"]
        if pkg["name"] == "football-performance-dynamics-bench"
    ]
    assert len(packages) == 1
    assert packages[0]["version"] == version


def test_approved_software_citation_is_versioned_without_fabricated_doi() -> None:
    lines = (ROOT / "CITATION.cff").read_text().splitlines()
    expected = {
        "cff-version: 1.2.0",
        'title: "Football Performance Dynamics Bench"',
        'family-names: "Rodriguez"',
        'given-names: "Julio"',
        'license: "Apache-2.0"',
        'version: "1.0.0"',
        'repository-code: "https://github.com/Litju/football-performance-dynamics-bench"',
    }
    assert expected.issubset(set(line.strip() for line in lines))
    assert not any(re.match(r"^(doi|date-released|preferred-citation):", line) for line in lines)
    assert (ROOT / "AUTHORS.md").is_file()


def test_source_publication_requires_manual_main_owner_dispatch() -> None:
    path = ROOT / ".github" / "workflows" / "publish-source-release.yml"
    workflow = path.read_text()
    assert "workflow_dispatch:" in workflow
    assert "\n  push:" not in workflow
    assert "github.ref == 'refs/heads/main'" in workflow
    assert "github.actor == 'Litju'" in workflow
    assert "RELEASE_V1_SOURCE_ONLY" in workflow
    assert "expected_commit_sha:" in workflow
    assert "EXPECTED_SHA:" in workflow
    assert 'test "$GITHUB_SHA" = "$EXPECTED_SHA"' in workflow
    assert "contents: write" in workflow
    assert "uv run pytest" in workflow
    assert "uv run fpdbench validate" in workflow
    assert "tools/public_release_asset_manifest.py" in workflow
    assert workflow.index("uv run pytest") < workflow.index("git tag -a")
    assert workflow.index("git tag -a") < workflow.index("gh release create")
    assert "dist/*.whl dist/*.tar.gz" in workflow


def test_tagged_software_release_notes_retains_scientific_and_rights_boundary() -> None:
    notes = (ROOT / "docs" / "release-v1.0.0.md").read_text()
    for phrase in (
        "NOT_QUALIFIED",
        "four matches",
        "216-fit training LOMO",
        "SkillCorner",
        "PySport",
        "not",
    ):
        assert phrase.casefold() in notes.casefold()
    assert "2.2433" in notes
    assert "1.6680" in notes
    assert "25.6%" in notes
    assert "No DOI" in notes
