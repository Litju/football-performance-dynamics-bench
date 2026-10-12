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
    assert "no `citation.cff` is created" in policy


def test_code_license_does_not_change_skillcorner_data_rights() -> None:
    policy = (ROOT / "docs/licensing-and-governance.md").read_text().lower()
    rights = (ROOT / "docs/data-rights.md").read_text().lower()

    assert "must never be interpreted as licensing" in policy
    assert "core tracking, events, phase data, aggregates, or row-level derivatives" in policy
    assert "**conditional go**" in rights
    assert "row-level redistribution gate remain unchanged" in rights
