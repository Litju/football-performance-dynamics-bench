from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_project_declares_apache_license_with_spdx_metadata() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]

    assert project["license"] == "Apache-2.0"
    assert project["license-files"] == ["LICENSE"]

    license_text = (ROOT / "LICENSE").read_text()
    assert "Version 2.0, January 2004" in license_text
    assert "Grant of Patent License" in license_text
    assert "APPENDIX: How to apply the Apache License to your work." in license_text
    assert license_text.rstrip().endswith("limitations under the License.")


def test_governance_separates_commit_and_publication_authorship() -> None:
    policy = (ROOT / "docs/licensing-and-governance.md").read_text().lower()

    assert "git commit authorship" in policy
    assert "scientific authorship" in policy
    assert "explicit approval" in policy
    assert "institutional affiliation" in policy
    assert "no `notice` file is added" in policy
    assert "julio rodriguez as the sole software citation author" in policy
    citation = (ROOT / "CITATION.cff").read_text()
    assert "cff-version: 1.2.0" in citation
    assert 'family-names: "Rodriguez"' in citation
    assert 'given-names: "Julio"' in citation
    assert 'license: "Apache-2.0"' in citation
    assert not any(line.startswith("doi:") for line in citation.splitlines())



def test_approved_citation_scope_excludes_third_party_and_paper_authorship() -> None:
    """Approved software authorship cannot silently grant dataset or paper rights."""
    citation = (ROOT / "CITATION.cff").read_text()
    authors = (ROOT / "AUTHORS.md").read_text()
    assert citation.count('family-names: "Rodriguez"') == 1
    assert citation.count('given-names: "Julio"') == 1
    assert 'license: "Apache-2.0"' in citation
    assert "sole software citation author" in authors
    assert "original code and project-written documentation" in authors
    assert "SkillCorner" in authors and "PySport" in authors
    assert "Paper A" in authors and "Paper B" in authors
    assert not any(line.startswith(("doi:", "date-released:")) for line in citation.splitlines())

def test_code_license_does_not_change_skillcorner_data_rights() -> None:
    policy = (ROOT / "docs/licensing-and-governance.md").read_text().lower()
    rights = (ROOT / "docs/data-rights.md").read_text().lower()

    assert "must never be interpreted as licensing" in policy
    assert "core tracking, events, phase data, aggregates, or row-level derivatives" in policy
    assert "**conditional go**" in rights
    assert "row-level redistribution gate remain unchanged" in rights
