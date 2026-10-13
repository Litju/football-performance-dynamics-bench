"""Load and fail-closed validate the prospective SkillCorner protocol lock."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from importlib.resources import files
from pathlib import Path
from typing import cast

from fpdbench.evaluation.metrics import ADE_METRIC_ID, FDE_METRIC_ID, XY_RMSE_METRIC_ID

PROTOCOL_FILE = "prospective_skillcorner_protocol_v1.json"
PROTOCOL_SHA256 = "865601662f4462178eaf7e1049075668176a9bd35f3bf4b1b6b8aa370de1d26c"
EXPECTED_SOURCE_RELEASE_HASH = "e92c417b7640b27399451134ee3fce4b1961b0c0dfc2e01175a8f3c906a9ae07"
EXPECTED_SOURCE_POPULATION_HASH = "e9054b7ddc2dfeff4dd8425ea61a23ed0b326076a08899e47502484228fdbdf4"
EXPECTED_MEASUREMENT_STATE_HASH = "4c29471c7fccc037dcfafd30222991e06d150e0887c0b667918bfa374262c6c3"
EXPECTED_ELIGIBILITY_POLICY_HASH = (
    "f0e1186f765cc7ce19c95152d8d6eacc66382f7e7f5a9ad1aa11c88c8a12f70b"
)

_PROTOCOL_ID = "skillcorner.prospective_conditional_motion"
_PROTOCOL_VERSION = "1.1.0"
_BENCHMARK_IDS = (
    "skillcorner.prospective.conditional_motion.absolute_xy",
    "skillcorner.prospective.conditional_motion.origin_relative_displacement",
)
_RESEARCH_QUESTION = (
    "On the pinned 20-match SkillCorner population, how does access to realized future ball "
    "and opponent trajectories change three-second multi-agent player-position error, for "
    "absolute pitch XY and origin-relative displacement targets?"
)
_FEATURES = {
    "history_only": (
        "history.target_team.xy_m",
        "history.target_team.observation_mask",
        "history.opponent_team.xy_m",
        "history.opponent_team.observation_mask",
        "history.ball.xy_m",
        "history.ball.observation_mask",
        "relative_time_offsets_s",
        "target_team.home_away_side",
    ),
    "future_ball": (
        "history.target_team.xy_m",
        "history.target_team.observation_mask",
        "history.opponent_team.xy_m",
        "history.opponent_team.observation_mask",
        "history.ball.xy_m",
        "history.ball.observation_mask",
        "relative_time_offsets_s",
        "target_team.home_away_side",
        "future.ball.xy_m",
        "future.ball.observation_mask",
    ),
    "future_opponent_plus_ball": (
        "history.target_team.xy_m",
        "history.target_team.observation_mask",
        "history.opponent_team.xy_m",
        "history.opponent_team.observation_mask",
        "history.ball.xy_m",
        "history.ball.observation_mask",
        "relative_time_offsets_s",
        "target_team.home_away_side",
        "future.ball.xy_m",
        "future.ball.observation_mask",
        "future.opponent_team.xy_m",
        "future.opponent_team.observation_mask",
    ),
}
_FORBIDDEN_FEATURES = (
    "future.target_team.xy_m",
    "future target positions or target-derived features",
    "future eligibility decisions or reason codes",
    "future phase/event/possession annotations",
    "future quality-audit fields or strata",
    "future target masks or target membership",
    "future target is_detected flags",
    "numeric match, team, or player identifiers as learned features",
    "absolute match clock, file identity, or row order",
    "cross-match player identity joins",
)
_MATCH_FEATURE = "FPDBench prospective/v1/match/"


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    return _mapping(value, path.name)


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    raw = cast(dict[object, object], value)
    if not all(isinstance(key, str) for key in raw):
        raise ValueError(f"{label} must have string keys")
    return cast(dict[str, object], value)


def _list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a JSON array")
    return cast(list[object], value)


def _integer(value: object, label: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{label} must be an integer")
    return value


def _expect(actual: object, expected: object, label: str) -> None:
    if type(actual) is not type(expected) or actual != expected:
        raise ValueError(f"{label} differs from the Linear issue 336 v1.1.0 authority")


def _expect_keys(value: Mapping[str, object], keys: set[str], label: str) -> None:
    _expect(set(value), keys, f"{label} fields")


def _digest(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _match_roles(match_ids: Sequence[str]) -> dict[str, list[str]]:
    ranked = sorted(
        (hashlib.sha256(f"{_MATCH_FEATURE}{match_id}".encode()).hexdigest(), match_id)
        for match_id in match_ids
    )
    return {
        "training": sorted(match for _, match in ranked[:12]),
        "validation": sorted(match for _, match in ranked[12:16]),
        "evaluation": sorted(match for _, match in ranked[16:]),
    }


def load_prospective_protocol() -> dict[str, object]:
    """Load the packaged machine-readable protocol authority."""
    resource = files(__package__).joinpath(PROTOCOL_FILE)
    value = json.loads(resource.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    return _mapping(value, PROTOCOL_FILE)


def _validate_protocol(protocol: Mapping[str, object]) -> dict[str, object]:
    document = _mapping(dict(protocol), "protocol")
    _expect_keys(
        document,
        {
            "schema_id",
            "schema_version",
            "protocol_id",
            "protocol_version",
            "protocol_sha256",
            "scientific_state",
        },
        "protocol",
    )
    _expect(document["schema_id"], "fpdbench.prospective-benchmark-protocol", "schema_id")
    _expect(document["schema_version"], "1.1.0", "schema_version")
    _expect(document["protocol_id"], _PROTOCOL_ID, "protocol_id")
    _expect(document["protocol_version"], _PROTOCOL_VERSION, "protocol_version")
    state = _mapping(document["scientific_state"], "scientific_state")
    _expect_keys(
        state,
        {
            "identity",
            "authorities",
            "benchmarks",
            "time_grid",
            "window_population",
            "information_regimes",
            "forbidden_model_information",
            "target_panel",
            "split",
            "evaluation",
            "analysis",
            "selection_and_execution",
            "delegations_and_gates",
        },
        "scientific state",
    )
    identity = _mapping(state["identity"], "identity")
    _expect_keys(
        identity,
        {"research_question_id", "research_question", "research_question_sha256"},
        "research identity",
    )
    _expect(
        identity["research_question_id"],
        "skillcorner.prospective.conditional_motion.context_ablation",
        "research question ID",
    )
    _expect(identity["research_question"], _RESEARCH_QUESTION, "research question")
    _expect(
        identity["research_question_sha256"],
        _digest(_RESEARCH_QUESTION),
        "research question digest",
    )

    authorities = _mapping(state["authorities"], "authorities")
    _expect(authorities["source_release_hash"], EXPECTED_SOURCE_RELEASE_HASH, "source release hash")
    _expect(
        authorities["source_population_hash"],
        EXPECTED_SOURCE_POPULATION_HASH,
        "source population hash",
    )
    _expect(
        authorities["measurement_state_hash"],
        EXPECTED_MEASUREMENT_STATE_HASH,
        "measurement state hash",
    )
    _expect(
        authorities["eligibility_policy_hash"],
        EXPECTED_ELIGIBILITY_POLICY_HASH,
        "eligibility policy hash",
    )
    _expect(authorities["source_release_id"], "skillcorner_open_data_v1", "source release ID")
    _expect(authorities["measurement_state_id"], "skillcorner_5hz_v1", "measurement state ID")
    _expect(authorities["eligibility_policy_id"], "skillcorner_window_v1", "eligibility policy ID")

    benchmarks = _list(state["benchmarks"], "benchmarks")
    if len(benchmarks) != 2:
        raise ValueError("the two prospective target identities are required")
    for index, raw in enumerate(benchmarks):
        benchmark = _mapping(raw, "benchmark")
        _expect(benchmark["benchmark_id"], _BENCHMARK_IDS[index], "prospective benchmark identity")
        _expect(benchmark["benchmark_version"], "1.0.0", "benchmark version")
        _expect(
            benchmark["target_representation"],
            ("absolute_xy", "origin_relative_displacement")[index],
            "target representation",
        )
        _expect(benchmark["target_units"], "metres", "target units")
        benchmark_id = benchmark.get("benchmark_id")
        if not isinstance(benchmark_id, str):
            raise ValueError("benchmark ID must be a string")
        if benchmark_id.startswith("conditional_multi_agent_motion_prediction/"):
            raise ValueError("prospective identities cannot reuse historical benchmark IDs")
        material = {key: value for key, value in benchmark.items() if key != "benchmark_sha256"}
        _expect(benchmark["benchmark_sha256"], _digest(material), "benchmark digest")

    time_grid = _mapping(state["time_grid"], "time grid")
    _expect(time_grid["frequency_hz"], 5, "grid frequency")
    _expect(time_grid["sample_interval_seconds"], 0.2, "grid interval")
    _expect(time_grid["history_seconds"], 5, "history duration")
    _expect(time_grid["history_intervals"], 25, "history intervals")
    _expect(time_grid["history_samples_including_origin"], 26, "history sample count")
    _expect(time_grid["origin_samples"], 1, "origin sample count")
    _expect(time_grid["origin_index_in_support"], 25, "origin sample index")
    _expect(time_grid["forecast_horizon_seconds"], 3, "forecast horizon")
    _expect(time_grid["future_intervals"], 15, "forecast intervals")
    _expect(time_grid["future_samples_excluding_origin"], 15, "forecast sample count")
    _expect(time_grid["total_support_samples"], 41, "total support sample count")
    _expect(
        _integer(time_grid["history_intervals"], "history intervals")
        + _integer(time_grid["origin_samples"], "origin samples")
        + _integer(time_grid["future_intervals"], "future intervals"),
        time_grid["total_support_samples"],
        "temporal count compatibility",
    )
    windows = _mapping(state["window_population"], "window population")
    _expect(windows.get("window_counts_claimed"), False, "window counts claim")

    regimes = _list(state["information_regimes"], "information regimes")
    if tuple(_mapping(item, "regime").get("regime_id") for item in regimes) != tuple(_FEATURES):
        raise ValueError("all information regimes must be declared in canonical order")
    for item in regimes:
        regime = _mapping(item, "regime")
        regime_id = cast(str, regime["regime_id"])
        features = _list(regime.get("model_visible_features"), f"{regime_id} features")
        if not all(isinstance(feature, str) for feature in features):
            raise ValueError(f"{regime_id} features must be strings")
        _expect(tuple(features), _FEATURES[regime_id], f"{regime_id} information boundary")
        if len(features) != len(set(features)):
            raise ValueError(f"duplicate model feature in {regime_id}")
    forbidden = _list(state["forbidden_model_information"], "forbidden information")
    _expect(tuple(forbidden), _FORBIDDEN_FEATURES, "forbidden information")

    targets = _mapping(state["target_panel"], "target panel")
    _expect(
        targets["target_cardinality"],
        "variable and fixed per directed scene from the origin sample; no fixed "
        "eleven-player shape or cap",
        "target cardinality",
    )
    _expect(targets["minimum_target_cardinality_claimed"], False, "minimum target cardinality")
    _expect(
        targets["target_entity_order"],
        "ascending provider player_id within match and team",
        "target ordering",
    )
    _expect(
        targets["target_truth_mask"],
        "one null XY pair only when that origin target is absent or either source "
        "coordinate is null/nonfinite at that future sample",
        "target mask",
    )
    _expect(
        targets["prediction_mask"],
        "none; each model must emit finite XY predictions for every origin target "
        "at every future sample",
        "prediction mask",
    )
    _expect(targets["mask_use"], "evaluation only; never a model input", "mask boundary")
    _expect(
        targets["substitution"],
        "target membership stays fixed from the origin sample; a departing target is "
        "null-masked only when its source position is absent or invalid, and later "
        "entrants are never added",
        "substitution rule",
    )

    split = _mapping(state["split"], "split")
    population = _list(split["population_match_ids"], "split population")
    if not all(isinstance(match_id, str) for match_id in population):
        raise ValueError("split population IDs must be strings")
    population_ids = cast(list[str], population)
    if population_ids != sorted(population_ids, key=int):
        raise ValueError("split population IDs must be sorted numerically")
    roles = _mapping(split["roles"], "split roles")
    _expect(roles, _match_roles(population_ids), "match role assignment")
    role_values = [match for values in roles.values() for match in _list(values, "role matches")]
    if len(role_values) != len(set(role_values)) or set(role_values) != set(population_ids):
        raise ValueError("match roles must partition the pinned population without overlap")
    if "J03WMX" in role_values:
        raise ValueError("historical private qualification data cannot enter the prospective split")
    _expect(split["role_assignment_sha256"], _digest(roles), "role assignment digest")

    lomo = _mapping(split["lomo"], "LOMO")
    training = cast(list[str], roles["training"])
    expected_folds = [
        {"fold_id": f"fold-{index + 1:02d}", "held_out_match": match}
        for index, match in enumerate(training)
    ]
    folds = _list(lomo["folds"], "LOMO folds")
    _expect(folds, expected_folds, "LOMO fold assignments")
    _expect(split["lomo_assignment_sha256"], _digest(folds), "LOMO assignment digest")
    _expect(
        split["split_sha256"],
        _digest({"roles": roles, "lomo_folds": folds}),
        "split digest",
    )

    evaluation = _mapping(state["evaluation"], "evaluation")
    _expect(
        evaluation["evaluator_id"], "skillcorner.prospective.masked_physical_xy", "evaluator ID"
    )
    _expect(evaluation["evaluator_version"], "2.0.0", "prospective evaluator version")
    _expect(evaluation["coordinate_units"], "metres", "metric units")
    _expect(evaluation["xy_scale_m"], [1.0, 1.0], "physical XY scale")
    primary = _mapping(evaluation["primary_metric"], "primary metric")
    _expect(primary["metric_id"], ADE_METRIC_ID, "primary metric compatibility")
    _expect(primary["unit"], "m", "primary metric unit")
    secondary = _list(evaluation["secondary_metrics"], "secondary metrics")
    secondary_ids = tuple(
        _mapping(metric, "secondary metric").get("metric_id") for metric in secondary
    )
    _expect(secondary_ids, (FDE_METRIC_ID, XY_RMSE_METRIC_ID), "secondary metric compatibility")
    if any(_mapping(metric, "secondary metric").get("unit") != "m" for metric in secondary):
        raise ValueError("all physical trajectory metrics must use metres")
    metric_state = {
        key: value for key, value in evaluation.items() if key != "metric_contract_sha256"
    }
    _expect(evaluation["metric_contract_sha256"], _digest(metric_state), "metric contract digest")
    if not isinstance(evaluation.get("null_and_error_rules"), dict):
        raise ValueError("metric null and error rules are required")

    analysis = _mapping(state["analysis"], "analysis")
    contrasts = _list(analysis["planned_directional_contrasts"], "planned directional contrasts")
    expected_contrast_ids = (
        "C1_ABSOLUTE_XY_FUTURE_BALL",
        "C1_DISPLACEMENT_FUTURE_BALL",
        "C2_ABSOLUTE_XY_FUTURE_OPPONENT",
        "C2_DISPLACEMENT_FUTURE_OPPONENT",
    )
    if (
        tuple(_mapping(item, "directional contrast").get("contrast_id") for item in contrasts)
        != expected_contrast_ids
    ):
        raise ValueError("the four preregistered directional ADE contrasts are missing or changed")
    _expect(
        analysis["confirmatory_scope"],
        "none; the four preregistered directional ADE contrasts are descriptive and carry no "
        "significance claims",
        "confirmatory scope",
    )
    uncertainty = _mapping(analysis["uncertainty"], "analysis uncertainty")
    _expect(uncertainty["independent_unit"], "physical_match", "uncertainty unit")
    _expect(
        uncertainty["method"],
        "descriptive match-level directional ADE contrasts; no inferential tests",
        "analysis method",
    )
    _expect(uncertainty["confidence_interval"], "none", "descriptive uncertainty")
    _expect(
        uncertainty["multiplicity"],
        "not applicable; no hypothesis tests or significance claims",
        "multiplicity policy",
    )
    _expect(
        analysis["directional_contrast_reporting"],
        "report all four match-level control-minus-context ADE differences and their equal-match "
        "mean as descriptive values; no p-values, confidence intervals, multiplicity corrections, "
        "or significance claims",
        "directional contrast reporting",
    )

    selection = _mapping(state["selection_and_execution"], "selection and execution")
    _expect(selection["final_fit_role"], "training", "final fit role")
    _expect(selection["selection_direction"], "minimize", "model selection direction")
    for section_name, owner_field in (
        ("seed_policy", "seed_list_and_exact_count_owner"),
        ("early_stopping", "patience_and_maximum_steps_owner"),
        ("compute_budget", "exact_per_run_and_campaign_ceilings_owner"),
        ("failure_and_retry", "exact_retry_count_owner"),
    ):
        section = _mapping(selection[section_name], section_name)
        _expect(section.get(owner_field), "Linear issue 339", f"{section_name} decision owner")
    seed_policy = _mapping(selection["seed_policy"], "seed policy")
    _expect(seed_policy["minimum_distinct_seeds_per_stochastic_cell"], 3, "minimum seed count")

    gates = _mapping(state["delegations_and_gates"], "training gates")
    _expect(gates["training_authorized_by_this_protocol_alone"], False, "training authorization")
    _expect(
        gates["scientific_choices_changeable_after_first_model_outcome"],
        False,
        "outcome-driven protocol change",
    )
    _expect(
        gates["payload_rows_or_row_level_derivatives_committed"], False, "payload rights boundary"
    )
    if not _list(
        _mapping(gates.get("issue_339"), "issue 339 delegation").get("owns_before_any_training"),
        "issue 339 decisions",
    ):
        raise ValueError("pretraining decisions delegated to issue 339 are missing")
    _expect(
        _mapping(gates.get("issue_439"), "issue 439 delegation").get("included_in_this_lock"),
        False,
        "issue 439 scope",
    )

    _expect(document["protocol_sha256"], _digest(state), "protocol content digest")
    _expect(document["protocol_sha256"], PROTOCOL_SHA256, "reviewed protocol digest")
    return state


def validate_prospective_protocol_document(
    protocol: Mapping[str, object],
    source_manifest: Mapping[str, object],
    measurement_manifest: Mapping[str, object],
    eligibility_manifest: Mapping[str, object],
) -> None:
    """Validate the frozen authority against upstream population, measurement, and policy."""
    state = _validate_protocol(protocol)
    authorities = _mapping(state["authorities"], "authorities")
    _expect(
        authorities["source_release_hash"],
        source_manifest.get("source_release_hash"),
        "source authority hash",
    )
    _expect(
        authorities["source_population_hash"],
        source_manifest.get("source_population_hash"),
        "source population authority",
    )
    _expect(
        authorities["measurement_state_hash"],
        measurement_manifest.get("data_state_hash"),
        "measurement authority hash",
    )
    _expect(
        authorities["eligibility_policy_hash"],
        eligibility_manifest.get("policy_hash"),
        "eligibility authority hash",
    )
    _expect(
        authorities["source_release_id"], source_manifest.get("source_id"), "source authority ID"
    )
    _expect(
        authorities["measurement_state_id"],
        measurement_manifest.get("data_state_id"),
        "measurement authority ID",
    )
    _expect(
        authorities["eligibility_policy_id"],
        eligibility_manifest.get("policy_id"),
        "eligibility authority ID",
    )

    source_ids = _source_match_ids(source_manifest)
    split = _mapping(state["split"], "split")
    population = _list(split["population_match_ids"], "split population")
    if tuple(population) != tuple(source_ids):
        raise ValueError("split population differs from the pinned source population")
    policy = _mapping(eligibility_manifest.get("scientific_policy"), "eligibility policy")
    quality = _mapping(policy.get("quality_strata"), "eligibility quality strata")
    analysis = _mapping(state["analysis"], "analysis")
    _expect(analysis["robustness_strata"], quality.get("dimensions"), "robustness strata")
    gates = _mapping(state["delegations_and_gates"], "training gates")
    _expect(gates["training_authorized_by_this_protocol_alone"], False, "training authorization")
    _expect(
        gates["scientific_choices_changeable_after_first_model_outcome"],
        False,
        "outcome-driven protocol change",
    )
    _expect(
        gates["payload_rows_or_row_level_derivatives_committed"], False, "payload rights boundary"
    )


def _source_match_ids(source_manifest: Mapping[str, object]) -> list[str]:
    matches = _list(source_manifest.get("available_matches"), "source matches")
    result: list[str] = []
    for value in matches:
        match = _mapping(value, "source match")
        match_id = match.get("match_id")
        if type(match_id) is not int or match_id <= 0:
            raise ValueError("source match IDs must be positive integers")
        result.append(str(match_id))
    result.sort(key=int)
    return result


def validate_prospective_protocol(root: Path) -> tuple[str, ...]:
    """Validate the protocol file against the three checked-in scientific authorities."""
    try:
        base = root / "src" / "fpdbench"
        protocol = _read_json(
            base / "benchmarks" / "conditional_multi_agent_motion_prediction" / PROTOCOL_FILE
        )
        source = _read_json(base / "data_sources" / "skillcorner_open_data_v1.json")
        measurement = _read_json(base / "data_states" / "skillcorner_5hz_v1.json")
        eligibility = _read_json(base / "eligibility" / "skillcorner_window_v1.json")
        validate_prospective_protocol_document(protocol, source, measurement, eligibility)
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return (f"prospective protocol: {exc}",)
    return ()


__all__ = [
    "EXPECTED_ELIGIBILITY_POLICY_HASH",
    "EXPECTED_MEASUREMENT_STATE_HASH",
    "EXPECTED_SOURCE_POPULATION_HASH",
    "EXPECTED_SOURCE_RELEASE_HASH",
    "PROTOCOL_FILE",
    "PROTOCOL_SHA256",
    "load_prospective_protocol",
    "validate_prospective_protocol",
    "validate_prospective_protocol_document",
]
