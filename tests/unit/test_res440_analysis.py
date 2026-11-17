"""Aggregation is seed-first, irrespective of unequal match window counts."""

import importlib.util
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
    matches[0]["records"][0] = matches[0]["records"][1]
    with pytest.raises(AssertionError):
        analysis.calculate(matches)
