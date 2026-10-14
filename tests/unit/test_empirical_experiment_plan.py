from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    empirical_experiment_plan,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.prospective_protocol import (
    PROTOCOL_SHA256,
)


def test_plan_freezes_exact_factorial_seeds_lomo_fits_and_protocol_hash() -> None:
    plan = empirical_experiment_plan.load_empirical_experiment_plan()
    factorial = plan["factorial"]

    empirical_experiment_plan.validate_empirical_experiment_plan_document(plan)
    assert plan["plan_sha256"] == empirical_experiment_plan.PLAN_SHA256
    assert plan["protocol_sha256"] == PROTOCOL_SHA256
    assert len(factorial["cells"]) == 18
    assert plan["seeds"]["stochastic_seed_ids"] == [1729, 2718, 31415]
    assert plan["seeds"]["final_fit_count"] == 18
    assert plan["seeds"]["lomo_fit_count"] == 216
    assert plan["seeds"]["total_learned_fits"] == 234
    assert plan["compute_budget"]["campaign_total_cpu_core_hours"] == 312.0


def test_repository_gate_loads_the_reviewed_plan() -> None:
    assert empirical_experiment_plan.validate_empirical_experiment_plan(Path.cwd()) == ()


def test_result_manifest_schema_is_pinned_to_the_plan() -> None:
    plan = empirical_experiment_plan.load_empirical_experiment_plan()
    schema_reference = plan["result_manifest_schema"]
    schema_path = (
        Path(__file__).resolve().parents[2]
        / "src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction"
        / schema_reference["schema_file"]
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    assert schema["$id"] == "fpdbench.prospective-experiment-result/1.1.0"
    assert hashlib.sha256(schema_path.read_bytes()).hexdigest() == schema_reference["schema_sha256"]
    assert schema["required"] == schema_reference["required_fields"]
    assert len(schema["properties"]["cell_id"]["enum"]) == 18


def test_plan_rejects_cell_seed_and_contrast_drift() -> None:
    plan = empirical_experiment_plan.load_empirical_experiment_plan()
    changed = copy.deepcopy(plan)
    changed["factorial"]["cells"].pop()
    with pytest.raises(ValueError, match="content SHA-256"):
        empirical_experiment_plan.validate_empirical_experiment_plan_document(changed)

    changed = copy.deepcopy(plan)
    changed["seeds"]["stochastic_seed_ids"] = [1, 2, 3]
    with pytest.raises(ValueError, match="content SHA-256"):
        empirical_experiment_plan.validate_empirical_experiment_plan_document(changed)

    changed = copy.deepcopy(plan)
    changed["primary_contrasts"][0]["context_regime"] = "future_opponent_plus_ball"
    with pytest.raises(ValueError, match="content SHA-256"):
        empirical_experiment_plan.validate_empirical_experiment_plan_document(changed)
