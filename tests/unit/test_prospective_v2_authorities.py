from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import cast

import pytest

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    ForecastOrigin,
    empirical_experiment_plan,
    invert_origin_relative_displacement,
    make_absolute_position_target,
    make_origin_relative_displacement_target,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.evaluation_population import (
    EvaluationPopulationAuthorityV2,
    EvaluationPopulationOutput,
    load_prospective_result_v2,
    prospective_window_id,
    prospective_window_id_v2,
    truth_mask_sha256,
    truth_sha256,
    validate_evaluation_population_authority_v2_document,
    validate_evaluation_population_schema_v2,
    validate_population_bound_evaluation,
    validate_prospective_result_document_v2,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.prospective_protocol import (
    EXPECTED_ELIGIBILITY_POLICY_V2_HASH,
    EXPECTED_MEASUREMENT_STATE_V2_HASH,
    EXPECTED_SOURCE_POPULATION_HASH,
    EXPECTED_SOURCE_RELEASE_HASH,
    PROTOCOL_V2_SHA256,
)
from fpdbench.data_sources.skillcorner import canonical_bytes

ROOT = Path(__file__).resolve().parents[2]
_SHA = "a" * 64


def _digest(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _population_document() -> dict[str, object]:
    roles = cast(dict[str, list[str]], empirical_experiment_plan.protocol_split_v2()["roles"])
    matches: list[dict[str, object]] = []
    for role in ("training", "validation", "evaluation"):
        for match_id in roles[role]:
            origin_id = "period_1/sample_25"
            window = {
                "window_id": prospective_window_id_v2(match_id, origin_id),
                "origin_sample_id": origin_id,
                "eligibility_result_sha256": _SHA,
                "scenes": [
                    {
                        "scene_id": scene,
                        "player_ids": [str(value) for value in range(1001, 1008)],
                        "absolute_xy_truth_sha256": _SHA,
                        "displacement_truth_sha256": "b" * 64,
                        "truth_mask_sha256": "c" * 64,
                    }
                    for scene in ("home", "away")
                ],
            }
            matches.append({"role": role, "match_id": match_id, "windows": [window]})
    document: dict[str, object] = {
        "schema_id": "fpdbench.prospective-evaluation-population",
        "schema_version": "2.0.0",
        "population_id": "skillcorner.prospective.conditional_motion.population_v2",
        "source_release_id": "skillcorner_open_data_v1",
        "source_release_version": "1.0.0",
        "source_release_hash": EXPECTED_SOURCE_RELEASE_HASH,
        "source_population_hash": EXPECTED_SOURCE_POPULATION_HASH,
        "measurement_state_id": "skillcorner_5hz_v2",
        "measurement_state_version": "2.0.0",
        "measurement_state_hash": EXPECTED_MEASUREMENT_STATE_V2_HASH,
        "eligibility_policy_id": "skillcorner_window_v2",
        "eligibility_policy_version": "2.0.0",
        "eligibility_policy_hash": EXPECTED_ELIGIBILITY_POLICY_V2_HASH,
        "protocol_id": "skillcorner.prospective_conditional_motion",
        "protocol_version": "2.0.0",
        "protocol_sha256": PROTOCOL_V2_SHA256,
        "plan_id": "skillcorner.prospective_conditional_motion.execution",
        "plan_version": "2.0.0",
        "plan_sha256": empirical_experiment_plan.load_empirical_experiment_plan_v2()["plan_sha256"],
        "ball_null_flag_finite_xy_count": 0,
        "candidate_window_count": 20,
        "eligible_window_count": 20,
        "candidate_origin_population_sha256": "d" * 64,
        "matches": matches,
        "membership_sha256": _digest(matches),
    }
    document["manifest_sha256"] = _digest(document)
    return document


def _population() -> tuple[dict[str, object], EvaluationPopulationAuthorityV2]:
    document = _population_document()
    return document, validate_evaluation_population_authority_v2_document(document)


def _result(population: EvaluationPopulationAuthorityV2) -> dict[str, object]:
    plan = empirical_experiment_plan.load_empirical_experiment_plan_v2()
    old_plan = empirical_experiment_plan.load_empirical_experiment_plan()
    cell = cast(dict[str, object], old_plan["factorial"]["cells"][0])
    validation_ids = cast(
        list[str], empirical_experiment_plan.protocol_split()["roles"]["validation"]
    )
    result: dict[str, object] = {
        "schema_id": "fpdbench.prospective-experiment-result",
        "schema_version": "2.0.0",
        "source_release_id": population.source_release_id,
        "source_release_version": population.source_release_version,
        "source_release_hash": population.source_release_hash,
        "source_population_hash": population.source_population_hash,
        "measurement_state_id": population.measurement_state_id,
        "measurement_state_version": population.measurement_state_version,
        "measurement_state_hash": population.measurement_state_hash,
        "eligibility_policy_id": population.eligibility_policy_id,
        "eligibility_policy_version": population.eligibility_policy_version,
        "eligibility_policy_hash": population.eligibility_policy_hash,
        "plan_id": plan["plan_id"],
        "plan_version": plan["plan_version"],
        "plan_sha256": plan["plan_sha256"],
        "protocol_id": population.protocol_id,
        "protocol_version": population.protocol_version,
        "protocol_sha256": population.protocol_sha256,
        "population_id": population.population_id,
        "population_schema_id": "fpdbench.prospective-evaluation-population",
        "population_schema_version": "2.0.0",
        "run_id": f"{cell['cell_id']}|baseline|final|deterministic",
        "cell_id": cell["cell_id"],
        "model_class_id": cell["model_class_id"],
        "information_regime": cell["information_regime"],
        "target_representation": cell["target_representation"],
        "fit_role": "baseline",
        "lomo_fold_id": None,
        "held_out_match_id": None,
        "seed": None,
        "train_match_ids": [],
        "validation_match_ids": validation_ids,
        "population_authority_sha256": population.manifest_sha256,
        "configuration_sha256": "e" * 64,
        "environment_sha256": "f" * 64,
        "checkpoint_sha256": None,
        "selected_step": None,
        "stopping_reason": "invalid_population",
        "status": "failed_validation",
        "output_artifacts": [],
        "metrics": [],
    }
    result["manifest_sha256"] = _digest(result)
    return result


def test_v2_population_schema_and_complete_synthetic_membership() -> None:
    document, authority = _population()

    assert validate_evaluation_population_schema_v2(ROOT) == ()
    assert authority.population_id == "skillcorner.prospective.conditional_motion.population_v2"
    assert authority.eligible_window_count == 20
    assert len(authority.matches) == 20
    assert len(authority.match_ids("training")) == 12
    assert len(authority.match_ids("validation")) == 4
    assert len(authority.match_ids("evaluation")) == 4
    assert authority.matches[0].windows[0].window_id == prospective_window_id_v2(
        authority.matches[0].match_id, "period_1/sample_25"
    )
    assert authority.matches[0].windows[0].window_id != prospective_window_id(
        authority.matches[0].match_id, "period_1/sample_25"
    )
    assert document["ball_null_flag_finite_xy_count"] == 0


def test_v2_population_fails_closed_for_global_drift_and_membership_mutations() -> None:
    document = _population_document()
    changed = copy.deepcopy(document)
    changed["ball_null_flag_finite_xy_count"] = 1
    changed["manifest_sha256"] = _digest(
        {key: item for key, item in changed.items() if key != "manifest_sha256"}
    )
    with pytest.raises(ValueError, match="BALL_NULL_FLAG_WITH_FINITE_XY_UNAPPROVED"):
        validate_evaluation_population_authority_v2_document(changed)

    changed = copy.deepcopy(document)
    matches = cast(list[dict[str, object]], changed["matches"])
    matches[0]["role"] = "evaluation"
    changed["membership_sha256"] = _digest(matches)
    changed["manifest_sha256"] = _digest(
        {key: item for key, item in changed.items() if key != "manifest_sha256"}
    )
    with pytest.raises(ValueError, match="role, identity, or canonical order drift"):
        validate_evaluation_population_authority_v2_document(changed)


def test_v2_result_manifest_binds_population_and_all_successor_hashes(tmp_path: Path) -> None:
    _document, population = _population()
    result = _result(population)
    validate_prospective_result_document_v2(result, population)

    path = tmp_path / "result-v2.json"
    path.write_text(json.dumps(result))
    assert load_prospective_result_v2(path, population) == result

    changed = copy.deepcopy(result)
    changed["measurement_state_hash"] = "0" * 64
    changed["manifest_sha256"] = _digest(
        {key: item for key, item in changed.items() if key != "manifest_sha256"}
    )
    with pytest.raises(ValueError, match="measurement_state_hash"):
        validate_prospective_result_document_v2(changed, population)


def _reseal(document: dict[str, object]) -> None:
    document["membership_sha256"] = _digest(document["matches"])
    document["manifest_sha256"] = _digest(
        {key: item for key, item in document.items() if key != "manifest_sha256"}
    )


@pytest.mark.parametrize(
    "mutation", ["none", "empty_match", "all_empty", "truth", "mask", "candidate", "receipt"]
)
def test_at07_structural_manifests_cannot_be_promoted_to_res501_qualification(mutation) -> None:
    document = _population_document()
    matches = cast(list[dict[str, object]], document["matches"])
    if mutation in {"empty_match", "all_empty"}:
        emptied = matches[:1] if mutation == "empty_match" else matches
        for match in emptied:
            match["windows"] = []
        document["eligible_window_count"] = 20 - len(emptied)
    elif mutation in {"truth", "mask"}:
        window = cast(list[dict[str, object]], matches[0]["windows"])[0]
        scene = cast(list[dict[str, object]], window["scenes"])[0]
        field = "absolute_xy_truth_sha256" if mutation == "truth" else "truth_mask_sha256"
        scene[field] = "f" * 64
    elif mutation == "candidate":
        document["candidate_origin_population_sha256"] = "f" * 64
    elif mutation == "receipt":
        document["qualification_receipt"] = {"status": "PASS", "receipt_sha256": _SHA}
        _reseal(document)
        with pytest.raises(ValueError):
            validate_evaluation_population_authority_v2_document(document)
        return
    _reseal(document)
    population = validate_evaluation_population_authority_v2_document(document)
    assert population.empirically_qualified is False
    with pytest.raises(ValueError, match="protected-population"):
        population.require_empirical_qualification()
    result = _result(population)
    result["status"] = "completed"
    result["manifest_sha256"] = _digest(
        {key: item for key, item in result.items() if key != "manifest_sha256"}
    )
    with pytest.raises(ValueError, match="protected-population"):
        validate_prospective_result_document_v2(result, population)


@pytest.mark.parametrize("regime", ["history_only", "future_ball", "future_opponent_plus_ball"])
def test_at05_common_physical_truth_and_masks_do_not_imply_population_qualification(regime) -> None:

    origins = tuple((10.0 + player, -5.0 - player) for player in range(11))
    origin = ForecastOrigin(5.0, (5.0,), ("history_target_team_xy",), origins)
    physical = tuple(tuple((x + time, y - 2 * time) for x, y in origins) for time in range(15))
    absolute_target = make_absolute_position_target(physical)
    displacement_target = make_origin_relative_displacement_target(physical, origin)
    recovered = invert_origin_relative_displacement(displacement_target, origin)
    for expected_row, actual_row, normalized_row in zip(
        physical, recovered, absolute_target, strict=True
    ):
        for expected, actual, normalized in zip(
            expected_row, actual_row, normalized_row, strict=True
        ):
            assert actual == pytest.approx(expected)
            assert (normalized[0] * 52.5, normalized[1] * 34.0) == pytest.approx(expected)
    absolute = tuple(
        tuple(
            None if time == 3 and player == 2 else (x + time, y - 2 * time)
            for player, (x, y) in enumerate(origins)
        )
        for time in range(15)
    )
    displacement = tuple(
        tuple(
            None if pair is None else (pair[0] - x, pair[1] - y)
            for pair, (x, y) in zip(row, origins, strict=True)
        )
        for row in absolute
    )
    reconstructed = tuple(
        tuple(
            None if pair is None else (pair[0] + x, pair[1] + y)
            for pair, (x, y) in zip(row, origins, strict=True)
        )
        for row in displacement
    )
    assert reconstructed == absolute
    assert truth_mask_sha256(absolute) == truth_mask_sha256(displacement)
    changed = list(displacement)
    changed[0] = (None, *changed[0][1:])
    assert truth_mask_sha256(changed) != truth_mask_sha256(absolute)
    document = _population_document()
    for match in document["matches"]:
        for window in match["windows"]:
            for scene in window["scenes"]:
                scene["absolute_xy_truth_sha256"] = truth_sha256(
                    absolute, target_representation="absolute_xy"
                )
                scene["displacement_truth_sha256"] = truth_sha256(
                    displacement, target_representation="origin_relative_displacement"
                )
                scene["truth_mask_sha256"] = truth_mask_sha256(absolute)
    _reseal(document)
    population = validate_evaluation_population_authority_v2_document(document)
    for representation in ("absolute_xy", "origin_relative_displacement"):
        output = EvaluationPopulationOutput(population.manifest_sha256, {}, representation)
        with pytest.raises(ValueError, match="independently verified protected-population"):
            validate_population_bound_evaluation(
                population, output, cell_id=f"origin_persistence_v1|{regime}|{representation}"
            )
