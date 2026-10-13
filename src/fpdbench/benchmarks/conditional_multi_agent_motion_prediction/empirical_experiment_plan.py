"""Load and fail-closed validate the prospective experiment plan."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from importlib.resources import files
from pathlib import Path
from typing import cast

from .prospective_protocol import PROTOCOL_SHA256, load_prospective_protocol

PLAN_FILE = "empirical_experiment_plan_v1.json"
PLAN_SHA256 = "f5bc1b9d6735436df520272f9c601f530b33bd1072f11e39d73e3e0e4274422a"
_PLAN_ID = "skillcorner.prospective_conditional_motion.execution"
_PLAN_VERSION = "1.0.0"
_REGIMES = ("history_only", "future_ball", "future_opponent_plus_ball")
_TARGETS = ("absolute_xy", "origin_relative_displacement")
_MODELS = (
    "origin_persistence_v1",
    "constant_velocity_1s_v1",
    "per_target_context_deepsets_mlp_v1",
)
_SEEDS = (1729, 2718, 31415)
_RESULT_MANIFEST_FIELDS = (
    "schema_id",
    "schema_version",
    "plan_id",
    "plan_version",
    "plan_sha256",
    "protocol_id",
    "protocol_version",
    "protocol_sha256",
    "run_id",
    "cell_id",
    "model_class_id",
    "information_regime",
    "target_representation",
    "fit_role",
    "lomo_fold_id",
    "held_out_match_id",
    "seed",
    "train_match_ids",
    "validation_match_ids",
    "population_authority_sha256",
    "configuration_sha256",
    "environment_sha256",
    "checkpoint_sha256",
    "selected_step",
    "stopping_reason",
    "status",
    "output_artifacts",
    "metrics",
    "manifest_sha256",
)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    typed_value = cast(Mapping[object, object], value)
    if not all(isinstance(key, str) for key in typed_value):
        raise ValueError(f"{label} must have string keys")
    return cast(Mapping[str, object], value)


def _list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return cast(list[object], value)


def _digest(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_empirical_experiment_plan() -> dict[str, object]:
    """Load the packaged immutable execution-plan authority."""
    value = json.loads(
        files(__package__).joinpath(PLAN_FILE).read_text(encoding="utf-8"),
        object_pairs_hook=_unique_object,
    )
    mapping = _mapping(value, PLAN_FILE)
    return cast(dict[str, object], mapping)


def validate_empirical_experiment_plan_document(
    document: Mapping[str, object], protocol: Mapping[str, object] | None = None
) -> None:
    """Reject any plan that drifts from the reviewed execution and protocol authorities."""
    plan = _mapping(document, "experiment plan")
    if plan.get("schema_id") != "fpdbench.prospective-experiment-plan":
        raise ValueError("unexpected experiment-plan schema_id")
    if plan.get("schema_version") != "1.0.0":
        raise ValueError("unsupported experiment-plan schema_version")
    if plan.get("plan_id") != _PLAN_ID or plan.get("plan_version") != _PLAN_VERSION:
        raise ValueError("unexpected experiment-plan identity")
    if plan.get("protocol_sha256") != PROTOCOL_SHA256:
        raise ValueError("experiment plan does not preserve the frozen protocol SHA-256")
    if plan.get("protocol_id") != "skillcorner.prospective_conditional_motion":
        raise ValueError("experiment plan protocol_id drift")
    if plan.get("protocol_version") != "1.1.0":
        raise ValueError("experiment plan protocol_version drift")
    digest = _digest({key: value for key, value in plan.items() if key != "plan_sha256"})
    if plan.get("plan_sha256") != digest or digest != PLAN_SHA256:
        raise ValueError("experiment-plan content SHA-256 mismatch")

    protocol_document = _mapping(protocol or load_prospective_protocol(), "protocol")
    if protocol_document.get("protocol_sha256") != PROTOCOL_SHA256:
        raise ValueError("loaded scientific protocol does not match its frozen authority")
    state = _mapping(protocol_document.get("scientific_state"), "protocol scientific_state")
    split = _mapping(state.get("split"), "protocol split")
    roles = _mapping(split.get("roles"), "protocol match roles")
    validation = _list(roles.get("validation"), "protocol validation matches")
    evaluation = _list(roles.get("evaluation"), "protocol evaluation matches")
    lomo = _mapping(split.get("lomo"), "protocol LOMO")
    folds = _list(lomo.get("folds"), "protocol LOMO folds")
    if len(folds) != 12:
        raise ValueError("the twelve frozen LOMO folds are required")

    factorial = _mapping(plan.get("factorial"), "factorial")
    if tuple(_list(factorial.get("information_regimes"), "information regimes")) != _REGIMES:
        raise ValueError("experiment plan information-regime order drift")
    if tuple(_list(factorial.get("target_representations"), "target representations")) != _TARGETS:
        raise ValueError("experiment plan target-representation order drift")
    model_values = _list(factorial.get("model_classes"), "model classes")
    model_ids = tuple(_mapping(value, "model class").get("class_id") for value in model_values)
    if model_ids != _MODELS:
        raise ValueError("experiment plan must declare the exact baseline ladder and primary class")
    if factorial.get("primary_model_class_id") != _MODELS[-1]:
        raise ValueError("experiment plan must designate exactly one frozen primary model class")
    cells = _list(factorial.get("cells"), "factorial cells")
    expected_cells = [
        {
            "cell_id": f"{model}|{regime}|{target}",
            "model_class_id": model,
            "information_regime": regime,
            "target_representation": target,
        }
        for model in _MODELS
        for target in _TARGETS
        for regime in _REGIMES
    ]
    if cells != expected_cells or len(cells) != 18:
        raise ValueError("experiment plan must contain the exact 3 x 2 x 3 cell matrix")

    seeds = _mapping(plan.get("seeds"), "seeds")
    if seeds.get("stochastic_seed_ids") != list(_SEEDS):
        raise ValueError("experiment plan stochastic seed schedule drift")
    if seeds.get("shared_across_comparable_cells") is not True:
        raise ValueError("comparable learned cells must share the exact seed IDs")
    expected_counts = {
        "final_fit_count": 6 * len(_SEEDS),
        "lomo_fit_count": 6 * len(_SEEDS) * len(folds),
        "total_learned_fits": 6 * len(_SEEDS) * (len(folds) + 1),
    }
    for field, expected in expected_counts.items():
        if seeds.get(field) != expected:
            raise ValueError(f"experiment plan {field} does not match the frozen factors")

    selection = _mapping(plan.get("selection"), "selection")
    if selection.get("validation_match_ids_from_protocol") is not True:
        raise ValueError("validation selection must use the frozen protocol matches")
    if len(validation) != 4 or len(evaluation) != 4:
        raise ValueError("the protocol requires four validation and four evaluation matches")
    if (
        selection.get("metric")
        != "equal mean of the four validation-match physical XY ADE values in metres"
    ):
        raise ValueError("checkpoint selection metric drift")
    if selection.get("maximum_optimizer_steps") != 5000:
        raise ValueError("maximum optimizer-step ceiling drift")
    if selection.get("early_stopping_patience_validation_checks") != 10:
        raise ValueError("early-stopping patience drift")
    if selection.get("evaluation_or_lomo_used_for_checkpoint_selection") is not False:
        raise ValueError("evaluation or LOMO scores cannot select checkpoints")

    budget = _mapping(plan.get("compute_budget"), "compute_budget")
    retry_count = budget.get("maximum_infrastructure_retries_per_fit")
    if retry_count != 1:
        raise ValueError("exactly one infrastructure retry per learned fit is frozen")
    total_fits = expected_counts["total_learned_fits"]
    training_hours = total_fits * (
        cast(float, budget.get("per_fit_initial_cpu_core_hours"))
        + cast(float, budget.get("per_fit_retry_cpu_core_hours"))
    )
    if training_hours != budget.get("campaign_training_cpu_core_hours"):
        raise ValueError("per-fit budgets do not reconcile with the campaign training ceiling")
    if training_hours + cast(
        float, budget.get("campaign_preparation_scoring_cpu_core_hours")
    ) != budget.get("campaign_total_cpu_core_hours"):
        raise ValueError("campaign compute ceilings do not reconcile")

    population_authority = _mapping(plan.get("population_authority"), "population_authority")
    schema_file = population_authority.get("schema_file")
    if (
        population_authority.get("schema_id") != "fpdbench.prospective-evaluation-population"
        or population_authority.get("schema_version") != "1.0.0"
        or schema_file != "evaluation_population_authority_v1.schema.json"
        or population_authority.get("required_before_training_or_scoring") is not True
        or population_authority.get("match_roles")
        != "all 20 matches and the exact protocol role assignment"
    ):
        raise ValueError("population-authority contract drift")
    schema_sha256 = hashlib.sha256(
        files(__package__).joinpath(cast(str, schema_file)).read_bytes()
    ).hexdigest()
    if population_authority.get("schema_sha256") != schema_sha256:
        raise ValueError("population-authority JSON Schema SHA-256 mismatch")

    result_schema = _mapping(plan.get("result_manifest_schema"), "result manifest schema")
    if (
        result_schema.get("schema_id") != "fpdbench.prospective-experiment-result"
        or result_schema.get("schema_version") != "1.0.0"
        or result_schema.get("schema_file") != "prospective_experiment_result_v1.schema.json"
        or tuple(_list(result_schema.get("required_fields"), "result-manifest fields"))
        != _RESULT_MANIFEST_FIELDS
        or result_schema.get("status_values")
        != ["completed", "failed_infrastructure", "failed_model", "failed_validation", "incomplete"]
        or result_schema.get("metric_ids") != ["ade_m", "fde_m", "xy_rmse_m"]
        or result_schema.get("metric_unit") != "metres"
    ):
        raise ValueError("result-manifest schema drift")
    result_schema_bytes = (
        files(__package__).joinpath(cast(str, result_schema.get("schema_file"))).read_bytes()
    )
    if result_schema.get("schema_sha256") != hashlib.sha256(result_schema_bytes).hexdigest():
        raise ValueError("result-manifest JSON Schema SHA-256 mismatch")
    result_document = _mapping(
        json.loads(result_schema_bytes, object_pairs_hook=_unique_object),
        "result-manifest JSON Schema",
    )
    result_properties = _mapping(result_document.get("properties"), "result-manifest properties")
    result_metric_properties = _mapping(
        _mapping(
            _mapping(result_properties.get("metrics"), "result metrics schema").get("items"),
            "result metric item schema",
        ).get("properties"),
        "result metric properties",
    )
    status_schema = _mapping(result_properties.get("status"), "result status schema")
    cell_schema = _mapping(result_properties.get("cell_id"), "result cell schema")
    cell_ids = tuple(_mapping(item, "result cell").get("cell_id") for item in cells)
    if (
        result_document.get("$schema") != "https://json-schema.org/draft/2020-12/schema"
        or result_document.get("$id") != "fpdbench.prospective-experiment-result/1.0.0"
        or result_document.get("additionalProperties") is not False
        or tuple(_list(result_document.get("required"), "result-manifest schema required"))
        != _RESULT_MANIFEST_FIELDS
        or result_properties.get("schema_id") != {"const": "fpdbench.prospective-experiment-result"}
        or result_properties.get("schema_version") != {"const": "1.0.0"}
        or cell_schema.get("enum") != list(cell_ids)
        or status_schema.get("enum") != result_schema.get("status_values")
        or _mapping(result_metric_properties.get("metric_id"), "result metric ID schema").get(
            "enum"
        )
        != result_schema.get("metric_ids")
        or _mapping(result_metric_properties.get("unit"), "result metric unit schema").get("const")
        != result_schema.get("metric_unit")
    ):
        raise ValueError("result-manifest JSON Schema differs from its frozen contract")

    analysis = _mapping(state.get("analysis"), "protocol analysis")
    protocol_contrasts = _list(
        analysis.get("planned_directional_contrasts"), "protocol directional contrasts"
    )
    plan_contrasts = _list(plan.get("primary_contrasts"), "plan primary contrasts")
    protocol_contrast_rows = tuple(
        (
            "absolute_xy"
            if row.get("benchmark_id") == "skillcorner.prospective.conditional_motion.absolute_xy"
            else "origin_relative_displacement"
            if row.get("benchmark_id")
            == "skillcorner.prospective.conditional_motion.origin_relative_displacement"
            else None,
            row.get("control_regime"),
            row.get("context_regime"),
        )
        for row in (_mapping(item, "protocol directional contrast") for item in protocol_contrasts)
    )
    plan_contrast_rows = tuple(
        (
            row.get("target_representation"),
            row.get("control_regime"),
            row.get("context_regime"),
        )
        for row in (_mapping(item, "plan directional contrast") for item in plan_contrasts)
    )
    if len(plan_contrasts) != 4 or plan_contrast_rows != protocol_contrast_rows:
        raise ValueError("experiment plan must preserve all four protocol ADE contrasts")
    if (
        _mapping(plan.get("plan_constraints"), "plan_constraints").get(
            "protocol_sha256_must_remain"
        )
        != PROTOCOL_SHA256
    ):
        raise ValueError("experiment plan does not pin the unchanged protocol hash")


def validate_empirical_experiment_plan(root: Path) -> tuple[str, ...]:
    """Validate the source-tree plan as part of the repository's full local gates."""
    try:
        path = (
            root
            / "src"
            / "fpdbench"
            / "benchmarks"
            / "conditional_multi_agent_motion_prediction"
            / PLAN_FILE
        )
        document = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
        mapping = _mapping(document, path.name)
        validate_empirical_experiment_plan_document(mapping)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return (f"prospective experiment plan: {exc}",)
    return ()


__all__ = [
    "PLAN_FILE",
    "PLAN_SHA256",
    "load_empirical_experiment_plan",
    "validate_empirical_experiment_plan",
    "validate_empirical_experiment_plan_document",
]
