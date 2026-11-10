"""RES614: synthetic-only harness tests (no real data, checkpoints or scorer entrypoint)."""

from __future__ import annotations

import ast
import hashlib
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import res614_synthetic_workload as w  # noqa: E402

TOOL = REPO / "tools" / "res614_synthetic_workload.py"
SMALL = w.Scenario("unit", roster_per_team=12)


def test_forbidden_imports_and_entrypoints_are_absent() -> None:
    tree = ast.parse(TOOL.read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(alias.name for alias in node.names)
    joined = " ".join(sorted(imported))
    for banned in (
        "amended_heldout_evaluation",
        "protected_skillcorner",
        "research_population_v1",
        "streaming_population_producer",
        "fpdbench.cli",
    ):
        assert banned not in joined
    text = TOOL.read_text()
    assert "load_frozen_models" not in text
    assert "torch.load" not in text
    assert "run_authorized_campaign" not in text


def test_window_has_41_samples_and_two_scenes() -> None:
    rng = np.random.default_rng(1)
    row = w.synthesize_window(rng, SMALL, 0)
    assert len(row["support"]) == 41
    assert [s["scene_id"] for s in row["scenes"]] == ["home", "away"]
    assert all(len(s["player_ids"]) == 11 for s in row["scenes"])


def test_eighteen_forward_calls_per_two_scene_window(tmp_path: Path) -> None:
    w.configure_cpu()
    models = w.build_random_models()
    assert len(models) == 18
    budget = w.Budget()
    result = w.run_scenario(SMALL, 3, tmp_path, budget, models)
    assert result.forward_calls == 3 * 18
    assert result.windows == 3
    assert not list(tmp_path.glob("*.jsonl")), "temporary snapshot and receipts must be cleaned up"
    assert budget.disk_used == 0


def test_run_is_deterministic(tmp_path: Path) -> None:
    w.configure_cpu()
    models = w.build_random_models()
    first = w.run_scenario(SMALL, 2, tmp_path, w.Budget(), models)
    second = w.run_scenario(SMALL, 2, tmp_path, w.Budget(), models)
    assert first.deterministic_digest == second.deterministic_digest
    assert first.row_bytes == second.row_bytes


def test_cpu_budget_is_enforced(tmp_path: Path) -> None:
    w.configure_cpu()
    models = w.build_random_models()
    with pytest.raises(w.BudgetExceeded, match="CPU"):
        w.run_scenario(SMALL, 5, tmp_path, w.Budget(cpu_seconds=0.0), models)


def test_disk_budget_is_enforced(tmp_path: Path) -> None:
    w.configure_cpu()
    models = w.build_random_models()
    with pytest.raises(w.BudgetExceeded, match="storage"):
        w.run_scenario(SMALL, 5, tmp_path, w.Budget(disk_bytes=1024), models)


def test_rss_budget_is_enforced() -> None:
    with pytest.raises(w.BudgetExceeded, match="RSS"):
        w.Budget(rss_bytes=1).check()


@pytest.mark.parametrize("fragment", ["/srv/fpdbench-private/x", "/tmp/res594-anything"])
def test_private_and_historical_paths_are_refused(fragment: str) -> None:
    with pytest.raises(PermissionError):
        w.assert_synthetic_path(Path(fragment))


def test_benchmark_report_shape_and_projection(tmp_path: Path) -> None:
    out = tmp_path / "report.json"
    report = w.run_benchmark(
        out,
        tmp_path / "work",
        windows=2,
        repeats=1,
        budget=w.Budget(),
        scenarios=(SMALL, w.Scenario("single", roster_per_team=12, scoreable_scenes=1)),
    )
    assert report["synthetic_only"] is True
    assert report["completed"] is True
    assert report["runtime"]["gpu_used"] is False
    assert report["historical_workload"]["forward_calls"] == 930_834
    unit = report["scenarios"]["unit"]
    assert unit["forward_calls_per_window"] == 18
    assert report["scenarios"]["single"]["forward_calls_per_window"] == 18
    proj = unit["projection_to_historical_workload"]
    lo, hi = proj["projected_scoring_path_total_ci95_s"]
    assert 0 < lo <= proj["projected_scoring_path_total_s"] <= hi
    assert hashlib.sha256(b"").hexdigest()  # keep hashlib import honest
    assert out.read_text().endswith("\n")


def test_budget_exceeded_marks_report_incomplete(tmp_path: Path) -> None:
    report = w.run_benchmark(
        tmp_path / "r.json",
        tmp_path / "work",
        windows=2,
        repeats=1,
        budget=w.Budget(cpu_seconds=0.0),
        scenarios=(SMALL,),
    )
    assert report["completed"] is False


def test_percentiles_and_bootstrap() -> None:
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert w._percentile(values, 0.5) == 3.0
    assert w._percentile(values, 0.95) == pytest.approx(4.8)
    mean, lo, hi = w.bootstrap_mean_ci(values)
    assert lo <= mean <= hi
    assert w.bootstrap_mean_ci(values) == (mean, lo, hi)
