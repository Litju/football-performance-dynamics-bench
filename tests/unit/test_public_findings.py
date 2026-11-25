"""Public aggregate verification must reject invented or mismatched match-level evidence."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[2] / "tools" / "inspect_public_findings.py"
SPEC = importlib.util.spec_from_file_location("public_findings_check", MODULE)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


def test_published_aggregate_accounting_and_tables() -> None:
    report = checker.render(checker.load())
    assert report.startswith("PUBLIC AGGREGATE CHECK: PASS")
    assert "research-only NOT_QUALIFIED" in report
    assert "51,713" not in report  # Raw accounting is printed without locale conversion.
    assert "51713" in report
    assert "1.6680" in report
    assert "2.1216" in report
    assert "1.2958" in report
    assert "Only history_only is an ex-ante forecast." in report


def test_changed_match_mean_fails_closed() -> None:
    data = copy.deepcopy(checker.load())
    data["match_means"][0]["ade_m"] += 0.02
    with pytest.raises(ValueError, match="public aggregate does not reconcile"):
        checker.audit(data)


def test_wrong_window_and_match_counts_fail_closed() -> None:
    data = copy.deepcopy(checker.load())
    data["windows"] += 1
    with pytest.raises(ValueError, match="window accounting"):
        checker.audit(data)
    data = copy.deepcopy(checker.load())
    data["denominators"].pop()
    with pytest.raises(ValueError, match="match keys"):
        checker.audit(data)


def test_changed_paired_contrast_fails_closed() -> None:
    data = copy.deepcopy(checker.load())
    data["contrasts"][0]["mean_m"] += 0.01
    with pytest.raises(ValueError, match="public aggregate does not reconcile"):
        checker.audit(data)


def test_fake_baseline_improvement_fails_closed() -> None:
    data = copy.deepcopy(checker.load())
    data["history_baseline_comparisons"][0]["reduction_percent"] = 100.0
    with pytest.raises(ValueError, match="baseline reduction percent"):
        checker.audit(data)


def test_protected_qualification_claim_is_refused() -> None:
    data = copy.deepcopy(checker.load())
    data["classification"] = "protected qualified"
    with pytest.raises(ValueError, match="scope changed"):
        checker.audit(data)
