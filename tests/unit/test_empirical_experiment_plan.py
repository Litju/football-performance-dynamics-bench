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


def test_v2_plan_binds_successor_authorities_and_exact_schema_bytes() -> None:
    plan = empirical_experiment_plan.load_empirical_experiment_plan_v2()
    v1 = empirical_experiment_plan.load_empirical_experiment_plan()
    schema_root = (
        Path(__file__).resolve().parents[2]
        / "src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction"
    )
    population = plan["population_authority"]
    result = plan["result_manifest_schema"]

    empirical_experiment_plan.validate_empirical_experiment_plan_v2_document(plan)
    assert empirical_experiment_plan.validate_empirical_experiment_plan_v2(Path.cwd()) == ()
    assert plan["plan_sha256"] == empirical_experiment_plan.PLAN_V2_SHA256
    assert plan["protocol_sha256"] != PROTOCOL_SHA256
    assert plan["factorial"] == v1["factorial"]
    assert plan["seeds"] == v1["seeds"]
    assert plan["compute_budget"] == v1["compute_budget"]
    assert population["ball_null_flag_finite_xy_count"] == 0
    assert (
        hashlib.sha256((schema_root / population["schema_file"]).read_bytes()).hexdigest()
        == population["schema_sha256"]
    )
    assert (
        hashlib.sha256((schema_root / result["schema_file"]).read_bytes()).hexdigest()
        == (result["schema_sha256"])
    )
    assert empirical_experiment_plan.experiment_cell_v2(
        "origin_persistence_v1|history_only|absolute_xy"
    ) == empirical_experiment_plan.experiment_cell("origin_persistence_v1|history_only|absolute_xy")

    changed = copy.deepcopy(plan)
    changed["population_authority"]["plan_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="frozen execution contract"):
        empirical_experiment_plan.validate_empirical_experiment_plan_v2_document(changed)


def test_v2_plan_rejects_one_field_schema_byte_mutations() -> None:
    plan = empirical_experiment_plan.load_empirical_experiment_plan_v2()
    schema_root = (
        Path(__file__).resolve().parents[2]
        / "src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction"
    )
    population_schema = (
        schema_root / "evaluation_population_authority_v2.schema.json"
    ).read_bytes()
    result_schema = (schema_root / "prospective_experiment_result_v2.schema.json").read_bytes()

    with pytest.raises(ValueError, match="v2 plan hash"):
        empirical_experiment_plan.validate_empirical_experiment_plan_v2_document(
            plan,
            population_schema_bytes=population_schema.replace(b"title", b"titlex", 1),
            result_schema_bytes=result_schema,
        )
    with pytest.raises(ValueError, match="v2 plan hash"):
        empirical_experiment_plan.validate_empirical_experiment_plan_v2_document(
            plan,
            population_schema_bytes=population_schema,
            result_schema_bytes=result_schema.replace(b"title", b"titlex", 1),
        )


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
