"""RES614 adversarial regressions: completion must be verified against frozen campaign metadata."""

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


def cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, os.fspath(TOOL), *args], capture_output=True, text=True, check=False
    )


@pytest.fixture
def done(tmp_path: Path) -> Path:
    out = cli(
        "run",
        "--campaign-dir",
        str(tmp_path / "camp"),
        "--ledger-dir",
        str(tmp_path / "camp.ledger"),
        "--matches",
        "3",
        "--windows-per-match",
        "4",
    )
    assert out.returncode == 0, out.stderr
    assert r.verify_campaign(tmp_path / "camp") == []
    return tmp_path / "camp"


def _rewrite_result(camp: Path, mutate: Callable[[dict[str, Any]], None]) -> None:
    """Forge a *self-consistent* result (valid result_sha256) after mutating its body."""
    path = camp / "campaign-result.json"
    doc = json.loads(path.read_text())
    doc.pop("result_sha256")
    mutate(doc)
    doc["result_sha256"] = hashlib.sha256(r.canonical(doc)).hexdigest()
    path.write_text(json.dumps(doc))


def _reseal_receipts(camp: Path, mutate: Callable[[int, dict[str, Any]], None]) -> None:
    """Rebuild a fully self-consistent receipt chain with a mutation applied."""
    chain = "0" * 64
    for match in range(3):
        path = camp / "receipts" / f"match-{match}.json"
        doc = json.loads(path.read_text())
        doc.pop("sha256")
        mutate(match, doc)
        doc["previous_receipt_sha256"] = chain
        chain = hashlib.sha256(r.canonical(doc)).hexdigest()
        path.write_text(json.dumps({**doc, "sha256": chain}))


def _assert_rejected(camp: Path, fragment: str) -> None:
    problems = r.verify_campaign(camp)
    assert problems, "forged or altered bundle must not verify"
    assert any(fragment in p for p in problems), problems
    info = r.classify(camp)
    assert info["state"] != "COMPLETED"
    assert not r.verify_completed(camp)


def test_untouched_campaign_is_completed(done: Path) -> None:
    assert r.classify(done)["state"] == "COMPLETED"
    assert cli("verify", "--campaign-dir", str(done)).returncode == 0


def test_result_file_alone_is_not_completion(tmp_path: Path) -> None:
    camp = tmp_path / "camp"
    camp.mkdir()
    (camp / "campaign-result.json").write_text("{}")
    info = r.classify(camp)
    assert info["state"] == "CORRUPT"
    assert not r.verify_completed(camp)


def test_self_consistent_zero_receipt_result_is_rejected(done: Path) -> None:
    def forge(doc: dict[str, Any]) -> None:
        doc.update(receipts=[], matches=0, windows=0, final_chain_sha256=None)

    _rewrite_result(done, forge)
    _assert_rejected(done, "field receipts")


@pytest.mark.parametrize("content", ["", "{", "[]", "null", '{"status":"COMPLETED"}'])
def test_empty_malformed_or_truncated_result_is_rejected(done: Path, content: str) -> None:
    (done / "campaign-result.json").write_text(content)
    _assert_rejected(done, "final result")


def test_dropped_result_index_entry_is_rejected(done: Path) -> None:
    _rewrite_result(done, lambda d: d["receipts"].pop())
    _assert_rejected(done, "field receipts")


def test_reordered_result_index_is_rejected(done: Path) -> None:
    _rewrite_result(done, lambda d: d["receipts"].reverse())
    _assert_rejected(done, "field receipts")


def test_forged_hash_in_result_index_is_rejected(done: Path) -> None:
    def forge(doc: dict[str, Any]) -> None:
        doc["receipts"][1]["sha256"] = "ab" * 32

    _rewrite_result(done, forge)
    _assert_rejected(done, "field receipts")


def test_final_chain_mismatch_is_rejected(done: Path) -> None:
    _rewrite_result(done, lambda d: d.update(final_chain_sha256="cd" * 32))
    _assert_rejected(done, "final_chain_sha256")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("scope_sha256", "ef" * 32),
        ("matches", 2),
        ("windows_per_match", 5),
        ("windows", 11),
        ("status", "PARTIAL"),
        ("synthetic_only", False),
    ],
)
def test_inconsistent_result_scope_or_counts_are_rejected(
    done: Path, field: str, value: object
) -> None:
    _rewrite_result(done, lambda d: d.update({field: value}))
    _assert_rejected(done, f"field {field}")


def test_unhashed_extra_key_in_result_is_rejected(done: Path) -> None:
    _rewrite_result(done, lambda d: d.update(note="extra"))
    _assert_rejected(done, "schema or hash")


def test_resealed_receipts_with_wrong_window_count_are_rejected(done: Path) -> None:
    _reseal_receipts(done, lambda m, d: d.update(windows=3) if m == 1 else None)
    _assert_rejected(done, "window count")


def test_swapped_receipt_files_break_the_chain(done: Path) -> None:
    a, b = done / "receipts" / "match-0.json", done / "receipts" / "match-1.json"
    ta, tb = a.read_text(), b.read_text()
    a.write_text(tb)
    b.write_text(ta)
    _assert_rejected(done, "match-0")


def test_extra_receipt_file_is_rejected(done: Path) -> None:
    shutil.copy(done / "receipts" / "match-2.json", done / "receipts" / "match-9.json")
    _assert_rejected(done, "unexpected receipt file")


def test_missing_receipt_with_intact_result_is_rejected(done: Path) -> None:
    (done / "receipts" / "match-2.json").unlink()
    _assert_rejected(done, "frozen receipts are sealed")


def test_terminal_marker_coexisting_with_result_is_rejected(done: Path) -> None:
    (done / ".failed.json").write_text("{}")
    _assert_rejected(done, "coexists")


def test_forged_campaign_metadata_is_rejected_even_if_result_matches(done: Path) -> None:
    meta_path = done / r.MARKER
    meta = json.loads(meta_path.read_text())
    meta.pop("metadata_sha256")
    meta["config"]["matches"] = 2
    meta["scope_sha256"] = r.Config(matches=2, windows_per_match=4).scope_sha256()
    meta["metadata_sha256"] = hashlib.sha256(r.canonical(meta)).hexdigest()
    meta_path.write_text(json.dumps(meta))
    # The independent one-shot ledger still pins the original configuration.
    _assert_rejected(done, "ledger")


def test_metadata_tamper_without_rehash_is_rejected(done: Path) -> None:
    meta_path = done / r.MARKER
    meta = json.loads(meta_path.read_text())
    meta["config"]["matches"] = 1
    meta_path.write_text(json.dumps(meta))
    _assert_rejected(done, "metadata hash")


def test_missing_ledger_fails_closed(done: Path, tmp_path: Path) -> None:
    shutil.rmtree(tmp_path / "camp.ledger")
    _assert_rejected(done, "ledger")


@pytest.mark.parametrize(
    "bad",
    [
        ["--matches", "0"],
        ["--matches", "-3"],
        ["--windows-per-match", "0"],
        ["--windows-per-match", "-1"],
        ["--telemetry-every", "0"],
    ],
)
def test_zero_or_negative_work_is_refused_before_any_state_is_created(
    tmp_path: Path, bad: list[str]
) -> None:
    out = cli(
        "run",
        "--campaign-dir",
        str(tmp_path / "camp"),
        "--ledger-dir",
        str(tmp_path / "led"),
        *bad,
    )
    assert out.returncode == r.EXIT_BAD_INPUT
    assert not (tmp_path / "camp").exists() and not (tmp_path / "led").exists()


@pytest.mark.parametrize("kwargs", [{"matches": 0}, {"matches": -1}, {"windows_per_match": 0}])
def test_config_rejects_non_positive_counts(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        r.Config(**kwargs)


def test_forged_empty_result_written_by_a_worker_is_not_completed(tmp_path: Path) -> None:
    out = cli(
        "run",
        "--campaign-dir",
        str(tmp_path / "camp"),
        "--ledger-dir",
        str(tmp_path / "camp.ledger"),
        "--matches",
        "3",
        "--windows-per-match",
        "3",
        "--fault-forge-empty-result",
    )
    assert out.returncode == 0  # the worker itself cannot vouch for completion
    assert (tmp_path / "camp" / "campaign-result.json").exists()
    assert r.classify(tmp_path / "camp")["state"] == "CORRUPT"
    assert cli("verify", "--campaign-dir", str(tmp_path / "camp")).returncode == r.EXIT_UNVERIFIED
