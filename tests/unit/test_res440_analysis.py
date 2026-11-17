"""Aggregation is seed-first, irrespective of unequal match window counts."""

import importlib.util
import json
import itertools
from pathlib import Path
from statistics import mean

import pytest

spec = importlib.util.spec_from_file_location(
    "res440", Path(__file__).resolve().parents[2] / "tools/analyze_res440.py"
)
assert spec is not None and spec.loader is not None
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


def test_seed_then_equal_match_and_duplicate_rejection():
    matches = []
    for i, count in enumerate((10, 100, 1000, 10000)):
        records = []
        for regime, rep, seed in itertools.product(analysis.REGIMES, analysis.REPS, analysis.SEEDS):
            value = i * 10 + analysis.SEEDS.index(seed)
            records.append(
                {
                    "cell": [regime, rep, seed],
                    "strata": {
                        "all": {"windows": count, "metrics": dict.fromkeys(analysis.METRICS, value)}
                    },
                }
            )
        matches.append({"match_id": str(i), "windows": count, "records": records})
    rows = analysis.calculate(matches)
    assert [r["ade_m"] for r in rows[::6]] == [1, 11, 21, 31]
    assert mean(r["xy_rmse_m"] for r in rows[::6]) == 16
    for row in analysis.seed_dispersion(matches):
        assert row["mean_within_match_seed_sd_m"] == 1
        assert row["max_within_match_seed_range_m"] == 2
    matches[0]["records"][0] = matches[0]["records"][1]
    with pytest.raises(AssertionError):
        analysis.calculate(matches)


def test_public_json_preserves_all_aggregate_tables_without_csv_files():
    root = Path(__file__).resolve().parents[2]
    directory = root / "docs/res440"
    findings = json.loads((directory / "findings.json").read_text())
    assert findings["classification"] == "research-only NOT_QUALIFIED"
    assert findings["records"] == 72
    assert findings["independent_units"] == 4
    assert findings["windows"] == 51713
    assert len(findings["summary"]) == 6
    assert len(findings["match_means"]) == 24
    assert len(findings["contrasts"]) == 4
    assert len(findings["history_baseline_comparisons"]) == 12
    assert len(findings["strata"]) == 30
    assert len(findings["seed_sensitivity"]) == 18
    assert len(findings["denominators"]) == 4
    assert not list(directory.glob("*.csv"))
