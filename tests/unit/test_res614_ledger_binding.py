"""RES614 adversarial regressions: the one-shot ledger must be bound to this campaign."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "tools" / "res614_resilient_runner.py"
sys.path.insert(0, str(REPO / "tools"))

import res614_resilient_runner as r  # noqa: E402

CAMPAIGN_CONFIG = {"matches": 3, "windows_per_match": 4, "seed": 614}


def cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, os.fspath(TOOL), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False,
    )


@pytest.fixture
def campaign(tmp_path: Path) -> tuple[Path, Path]:
    authority = tmp_path / "authority"
    out = cli(
        "run",
        "--campaign-dir",
        str(tmp_path / "camp"),
        "--ledger-dir",
        str(authority),
        "--matches",
        str(CAMPAIGN_CONFIG["matches"]),
        "--windows-per-match",
        str(CAMPAIGN_CONFIG["windows_per_match"]),
        "--seed",
        str(CAMPAIGN_CONFIG["seed"]),
    )
    assert out.returncode == 0, out.stderr
    camp = tmp_path / "camp"
    assert r.verify_campaign(camp, authority) == []
    return camp, authority


def ledger_path(authority: Path) -> Path:
    scope = r.Config(**CAMPAIGN_CONFIG).scope_sha256()
    return authority / f".consumed-{scope}.json"


def rewrite_ledger(
    authority: Path,
    mutate: Callable[[dict[str, Any]], None],
    *,
    rehash: bool = True,
) -> None:
    path = ledger_path(authority)
    doc = json.loads(path.read_text())
    if rehash:
        doc.pop("record_sha256", None)
        mutate(doc)
        doc["record_sha256"] = hashlib.sha256(r.canonical(doc)).hexdigest()
    else:
        mutate(doc)
    path.write_text(json.dumps(doc))


def test_untouched_ledger_binds_to_the_exact_campaign(campaign: tuple[Path, Path]) -> None:
    camp, authority = campaign
    path = ledger_path(authority)
    doc = json.loads(path.read_text())
    assert set(doc) == r._LEDGER_KEYS
    assert doc["schema_id"] == r.LEDGER_SCHEMA_ID
    assert doc["synthetic_only"] is True
    assert doc["status"] == "CONSUMED_IRREVERSIBLY"
    assert doc["retry_allowed"] is False
    assert doc["campaign_directory"] == str(camp.resolve())
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    assert r.verify_campaign(camp, authority) == []
    assert r.classify(camp, authority)["state"] == "COMPLETED"


def test_copied_campaign_with_copied_ledger_is_rejected(
    campaign: tuple[Path, Path], tmp_path: Path
) -> None:
    camp, authority = campaign
    copied_camp = tmp_path / "copied-camp"
    copied_authority = tmp_path / "copied-authority"
    shutil.copytree(camp, copied_camp)
    shutil.copytree(authority, copied_authority)
    problems = r.verify_campaign(copied_camp, copied_authority)
    assert any("different campaign directory" in problem for problem in problems), problems
    assert r.classify(copied_camp, copied_authority)["state"] == "CORRUPT"


def test_mismatched_campaign_directory_with_recomputed_hash_is_rejected(
    campaign: tuple[Path, Path], tmp_path: Path
) -> None:
    camp, authority = campaign
    rewrite_ledger(
        authority,
        lambda doc: doc.update(campaign_directory=str(tmp_path / "elsewhere")),
    )
    problems = r.verify_campaign(camp, authority)
    assert any("different campaign directory" in problem for problem in problems), problems


@pytest.mark.parametrize(
    ("field", "value", "fragment"),
    [
        ("schema_id", "fpdbench.res614.other.ledger", "schema identity"),
        ("synthetic_only", False, "synthetic-only"),
        ("status", "RETRY_ALLOWED", "CONSUMED_IRREVERSIBLY"),
        ("retry_allowed", True, "retry"),
        ("scope_sha256", "ab" * 32, "scope"),
        (
            "config",
            {"matches": 2, "windows_per_match": 4, "seed": 614},
            "configuration",
        ),
        ("campaign_directory", "/tmp/another-campaign", "different campaign directory"),
        ("consumer_pid", 0, "consumer PID"),
        ("consumed_at_utc", "not-a-timestamp", "timestamp"),
    ],
)
def test_altered_ledger_field_is_rejected(
    campaign: tuple[Path, Path], field: str, value: object, fragment: str
) -> None:
    camp, authority = campaign
    rewrite_ledger(authority, lambda doc: doc.update({field: value}))
    problems = r.verify_campaign(camp, authority)
    assert any(fragment in problem for problem in problems), problems
    assert not r.verify_completed(camp, authority)
    assert r.classify(camp, authority)["state"] == "CORRUPT"


def test_extra_ledger_field_with_recomputed_hash_is_rejected(
    campaign: tuple[Path, Path],
) -> None:
    camp, authority = campaign
    rewrite_ledger(authority, lambda doc: doc.update(note="extra"))
    problems = r.verify_campaign(camp, authority)
    assert any("schema invalid" in problem for problem in problems), problems


def test_missing_required_ledger_field_with_recomputed_hash_is_rejected(
    campaign: tuple[Path, Path],
) -> None:
    camp, authority = campaign
    rewrite_ledger(authority, lambda doc: doc.pop("synthetic_only"))
    problems = r.verify_campaign(camp, authority)
    assert any("schema invalid" in problem for problem in problems), problems


def test_altered_ledger_without_rehash_is_rejected(campaign: tuple[Path, Path]) -> None:
    camp, authority = campaign
    rewrite_ledger(authority, lambda doc: doc.update(retry_allowed=True), rehash=False)
    problems = r.verify_campaign(camp, authority)
    assert any("hash mismatch" in problem for problem in problems), problems


def test_ledger_file_permissions_must_be_owner_private(campaign: tuple[Path, Path]) -> None:
    camp, authority = campaign
    ledger_path(authority).chmod(0o644)
    problems = r.verify_campaign(camp, authority)
    assert any("owner-private" in problem for problem in problems), problems


def test_ledger_symlink_is_rejected(campaign: tuple[Path, Path]) -> None:
    camp, authority = campaign
    path = ledger_path(authority)
    real = authority / "real-ledger.json"
    path.rename(real)
    path.symlink_to(real)
    problems = r.verify_campaign(camp, authority)
    assert any("symbolic link" in problem for problem in problems), problems


def test_relative_campaign_paths_still_bind_to_the_canonical_directory(tmp_path: Path) -> None:
    out = cli(
        "run",
        "--campaign-dir",
        "camp",
        "--ledger-dir",
        "authority",
        "--matches",
        str(CAMPAIGN_CONFIG["matches"]),
        "--windows-per-match",
        str(CAMPAIGN_CONFIG["windows_per_match"]),
        cwd=tmp_path,
    )
    assert out.returncode == 0, out.stderr
    doc = json.loads(ledger_path(tmp_path / "authority").read_text())
    assert doc["campaign_directory"] == str((tmp_path / "camp").resolve())
    assert r.verify_campaign(tmp_path / "camp", tmp_path / "authority") == []
    verified = cli(
        "verify",
        "--campaign-dir",
        "camp",
        "--ledger-dir",
        "authority",
        cwd=tmp_path,
    )
    assert verified.returncode == 0, verified.stderr
