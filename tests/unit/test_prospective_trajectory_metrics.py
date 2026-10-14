from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    empirical_experiment_plan,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.evaluation_population import (
    EvaluationPopulationOutput,
    PopulationBoundScene,
    PopulationBoundWindow,
    load_evaluation_population_authority,
    prospective_window_id,
    truth_mask_sha256,
    truth_sha256,
    validate_evaluation_population_authority_document,
    validate_evaluation_population_schema,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.prospective_evaluator import (
    EVALUATION_MATCH_IDS,
    evaluate_prospective_trajectories,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.prospective_protocol import (
    EXPECTED_ELIGIBILITY_POLICY_HASH,
    EXPECTED_MEASUREMENT_STATE_HASH,
    EXPECTED_SOURCE_POPULATION_HASH,
    EXPECTED_SOURCE_RELEASE_HASH,
    PROTOCOL_SHA256,
    load_prospective_protocol,
)
from fpdbench.data_sources.skillcorner import canonical_bytes

ROOT = Path(__file__).resolve().parents[2]
type Truth = tuple[tuple[tuple[float, float] | None, ...], ...]


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _truth(*, final_target: bool = True, targets: int = 7) -> Truth:
    return tuple(
        tuple((0.0, 0.0) if final_target or time_index == 0 else None for _ in range(targets))
        for time_index in range(15)
    )


def _prediction(error: float, targets: int = 7) -> tuple[tuple[tuple[float, float], ...], ...]:
    return tuple(tuple((error, 0.0) for _ in range(targets)) for _ in range(15))


def _seal(document: dict[str, object]) -> None:
    matches = cast(list[object], document["matches"])
    document["membership_sha256"] = _sha(canonical_bytes(matches))
    document["manifest_sha256"] = _sha(
        canonical_bytes({key: value for key, value in document.items() if key != "manifest_sha256"})
    )


def _roles() -> tuple[tuple[str, tuple[str, ...]], ...]:
    protocol = load_prospective_protocol()
    state = cast(dict[str, object], protocol["scientific_state"])
    split = cast(dict[str, object], state["split"])
    roles = cast(dict[str, object], split["roles"])
    return tuple(
        (role, tuple(cast(list[str], roles[role])))
        for role in ("training", "validation", "evaluation")
    )


def _fixture(
    *,
    window_count: int = 2,
    error_for: Callable[[str, int, int], float] | None = None,
    truth_for: Callable[[str, int, int], Truth] | None = None,
    scoring_role: str = "evaluation",
    target_representation: str = "absolute_xy",
) -> tuple[dict[str, object], EvaluationPopulationOutput]:
    match_documents: list[dict[str, object]] = []
    all_truths: dict[tuple[str, int, int], Truth] = {}
    for role, match_ids in _roles():
        for match_id in match_ids:
            windows: list[dict[str, object]] = []
            for window_index in range(window_count):
                origin_id = f"period_1/sample_{25 + window_index}"
                scene_records = []
                for scene_index, scene_id in enumerate(("home", "away")):
                    target_ids = [
                        str(player_id)
                        for player_id in range(1 + scene_index * 100, 8 + scene_index * 100)
                    ]
                    truth = (
                        truth_for(match_id, window_index, scene_index) if truth_for else _truth()
                    )
                    all_truths[(match_id, window_index, scene_index)] = truth
                    scene_records.append(
                        {
                            "scene_id": scene_id,
                            "player_ids": target_ids,
                            "absolute_xy_truth_sha256": truth_sha256(
                                truth, target_representation="absolute_xy"
                            ),
                            "displacement_truth_sha256": truth_sha256(
                                truth, target_representation="origin_relative_displacement"
                            ),
                            "truth_mask_sha256": truth_mask_sha256(truth),
                        }
                    )
                windows.append(
                    {
                        "window_id": prospective_window_id(match_id, origin_id),
                        "origin_sample_id": origin_id,
                        "eligibility_result_sha256": _sha(
                            f"eligibility/{match_id}/{origin_id}".encode()
                        ),
                        "scenes": scene_records,
                    }
                )
            match_documents.append({"role": role, "match_id": match_id, "windows": windows})

    document: dict[str, object] = {
        "schema_id": "fpdbench.prospective-evaluation-population",
        "schema_version": "1.1.0",
        "population_id": "skillcorner.prospective.conditional_motion.population",
        "source_release_hash": EXPECTED_SOURCE_RELEASE_HASH,
        "source_population_hash": EXPECTED_SOURCE_POPULATION_HASH,
        "measurement_state_hash": EXPECTED_MEASUREMENT_STATE_HASH,
        "eligibility_policy_hash": EXPECTED_ELIGIBILITY_POLICY_HASH,
        "protocol_sha256": PROTOCOL_SHA256,
        "plan_sha256": empirical_experiment_plan.load_empirical_experiment_plan()["plan_sha256"],
        "candidate_window_count": len(match_documents) * window_count,
        "eligible_window_count": len(match_documents) * window_count,
        "candidate_origin_population_sha256": _sha(b"synthetic exhaustive origin enumeration"),
        "matches": match_documents,
        "membership_sha256": "0" * 64,
        "manifest_sha256": "0" * 64,
    }
    _seal(document)
    authority = validate_evaluation_population_authority_document(document)
    output_matches: dict[str, tuple[PopulationBoundWindow, ...]] = {}
    for match in authority.matches_for_role(scoring_role):
        result_windows = []
        for window_index, membership in enumerate(match.windows):
            result_scenes = []
            for scene_index, scene_membership in enumerate(membership.scenes):
                error = error_for(match.match_id, window_index, scene_index) if error_for else 0.0
                result_scenes.append(
                    PopulationBoundScene(
                        scene_membership.scene_id,
                        scene_membership.player_ids,
                        _prediction(error, len(scene_membership.player_ids)),
                        all_truths[(match.match_id, window_index, scene_index)],
                    )
                )
            result_windows.append(
                PopulationBoundWindow(
                    membership.window_id, membership.origin_sample_id, tuple(result_scenes)
                )
            )
        output_matches[match.match_id] = tuple(result_windows)
    output = EvaluationPopulationOutput(
        authority.manifest_sha256, output_matches, target_representation
    )
    return document, output


def _score(document: dict[str, object], output: EvaluationPopulationOutput):
    authority = validate_evaluation_population_authority_document(document)
    return evaluate_prospective_trajectories(
        output, authority, cell_id="origin_persistence_v1|history_only|absolute_xy"
    )


def test_population_bound_score_keeps_no_final_target_scene_excluded_from_all_metrics() -> None:
    document, output = _fixture(
        window_count=1,
        error_for=lambda match, _window, scene: (
            1.0 if match == EVALUATION_MATCH_IDS[0] and scene == 0 else 0.0
        ),
        truth_for=lambda match, _window, scene: (
            _truth(final_target=False)
            if match == EVALUATION_MATCH_IDS[0] and scene == 1
            else _truth()
        ),
    )

    result = _score(document, output)
    first_window = result.matches[0].windows[0]

    assert first_window.scenes[1].metrics is None
    assert first_window.scenes[1].reason == "NO_FINAL_TARGET"
    assert first_window.metrics is not None
    assert first_window.metrics.ade_m == pytest.approx(1.0)
    assert result.matches[0].metrics is not None
    assert result.matches[0].metrics.ade_m == pytest.approx(1.0)
    assert result.population_authority_sha256 == document["manifest_sha256"]


def test_scene_window_and_match_aggregation_are_equal_weighted() -> None:
    document, output = _fixture(
        error_for=lambda match, window, scene: (
            0.0
            if match != EVALUATION_MATCH_IDS[0] or window == 0 and scene == 0
            else 6.0
            if match == EVALUATION_MATCH_IDS[0] and window == 0
            else 10.0
        )
    )

    result = _score(document, output)

    assert result.matches[0].windows[0].metrics is not None
    assert result.matches[0].windows[0].metrics.ade_m == pytest.approx(3.0)
    assert result.matches[0].metrics is not None
    assert result.matches[0].metrics.ade_m == pytest.approx(6.5)
    assert result.metrics is not None
    assert result.metrics.ade_m == pytest.approx(1.625)
    assert result.matches[0].windows[0].scenes[1].metrics is not None
    assert result.matches[0].windows[0].scenes[1].metrics.scored_points == 105


def test_unscoreable_evaluation_match_makes_population_mean_null() -> None:
    document, output = _fixture(
        window_count=1,
        truth_for=lambda match, _window, _scene: (
            _truth(final_target=False) if match == EVALUATION_MATCH_IDS[-1] else _truth()
        ),
    )

    result = _score(document, output)

    assert result.matches[3].metrics is None
    assert result.metrics is None


def test_nonfinite_prediction_fails_even_when_truth_is_null() -> None:
    document, output = _fixture(
        window_count=1,
        truth_for=lambda match, _window, scene: (
            _truth(final_target=False)
            if match == EVALUATION_MATCH_IDS[0] and scene == 0
            else _truth()
        ),
    )
    match_id = EVALUATION_MATCH_IDS[0]
    match_windows = list(output.matches[match_id])
    window = match_windows[0]
    scenes = list(window.scenes)
    prediction = [list(sample) for sample in scenes[0].prediction]
    prediction[0][0] = (math.nan, 0.0)
    scenes[0] = PopulationBoundScene(
        scenes[0].scene_id,
        scenes[0].player_ids,
        tuple(tuple(sample) for sample in prediction),
        scenes[0].truth,
    )
    match_windows[0] = PopulationBoundWindow(
        window.window_id, window.origin_sample_id, tuple(scenes)
    )
    matches = dict(output.matches)
    matches[match_id] = tuple(match_windows)

    with pytest.raises(ValueError, match="predictions must contain finite XY pairs"):
        _score(
            document,
            EvaluationPopulationOutput(output.population_authority_sha256, matches, "absolute_xy"),
        )


def test_partial_truth_xy_is_invalid() -> None:
    document, output = _fixture(window_count=1)
    match_id = EVALUATION_MATCH_IDS[0]
    match_windows = list(output.matches[match_id])
    window = match_windows[0]
    scenes = list(window.scenes)
    invalid_truth = list(scenes[0].truth)
    invalid_truth[0] = ((0.0, math.nan), *invalid_truth[0][1:])
    scenes[0] = PopulationBoundScene(
        scenes[0].scene_id,
        scenes[0].player_ids,
        scenes[0].prediction,
        tuple(invalid_truth),
    )
    match_windows[0] = PopulationBoundWindow(
        window.window_id, window.origin_sample_id, tuple(scenes)
    )
    matches = dict(output.matches)
    matches[match_id] = tuple(match_windows)

    with pytest.raises(ValueError, match="truth positions must be finite XY pairs"):
        _score(
            document,
            EvaluationPopulationOutput(output.population_authority_sha256, matches, "absolute_xy"),
        )


def test_gate_rejects_missing_or_reordered_windows_and_wrong_population_digest() -> None:
    document, output = _fixture(window_count=2)
    match_id = EVALUATION_MATCH_IDS[0]
    windows = output.matches[match_id]
    missing = dict(output.matches)
    missing[match_id] = windows[:1]
    with pytest.raises(ValueError, match="missing or adding windows"):
        _score(
            document,
            EvaluationPopulationOutput(output.population_authority_sha256, missing, "absolute_xy"),
        )

    reordered = dict(output.matches)
    reordered[match_id] = tuple(reversed(windows))
    with pytest.raises(ValueError, match="order or origin identity drift"):
        _score(
            document,
            EvaluationPopulationOutput(
                output.population_authority_sha256, reordered, "absolute_xy"
            ),
        )

    with pytest.raises(ValueError, match="different population authority"):
        _score(document, EvaluationPopulationOutput("0" * 64, output.matches, "absolute_xy"))


def test_gate_rejects_player_identity_drift_and_model_dependent_masking() -> None:
    document, output = _fixture(window_count=1)
    match_id = EVALUATION_MATCH_IDS[0]
    windows = list(output.matches[match_id])
    window = windows[0]
    scenes = list(window.scenes)
    scene = scenes[0]
    scenes[0] = PopulationBoundScene(
        scene.scene_id,
        tuple(reversed(scene.player_ids)),
        scene.prediction,
        scene.truth,
    )
    windows[0] = PopulationBoundWindow(window.window_id, window.origin_sample_id, tuple(scenes))
    changed = dict(output.matches)
    changed[match_id] = tuple(windows)
    with pytest.raises(ValueError, match="player IDs or order"):
        _score(
            document,
            EvaluationPopulationOutput(output.population_authority_sha256, changed, "absolute_xy"),
        )

    document, output = _fixture(window_count=1)
    matches = cast(list[dict[str, object]], document["matches"])
    evaluation_match = next(item for item in matches if item["match_id"] == match_id)
    windows_doc = cast(list[dict[str, object]], evaluation_match["windows"])
    scenes_doc = cast(list[dict[str, object]], windows_doc[0]["scenes"])
    scenes_doc[0]["truth_mask_sha256"] = "0" * 64
    _seal(document)
    authority = validate_evaluation_population_authority_document(document)
    with pytest.raises(ValueError, match="target masking"):
        evaluate_prospective_trajectories(
            EvaluationPopulationOutput(authority.manifest_sha256, output.matches, "absolute_xy"),
            authority,
            cell_id="origin_persistence_v1|history_only|absolute_xy",
        )


def test_authority_rejects_invalid_origin_and_player_identities_even_if_resealed() -> None:
    document, _ = _fixture(window_count=1)
    matches = cast(list[dict[str, object]], document["matches"])
    first_windows = cast(list[dict[str, object]], matches[0]["windows"])
    first_windows[0]["origin_sample_id"] = "period_0/sample_24"
    _seal(document)
    with pytest.raises(ValueError, match="origin_sample_id is invalid"):
        validate_evaluation_population_authority_document(document)

    document, _ = _fixture(window_count=1)
    matches = cast(list[dict[str, object]], document["matches"])
    first_windows = cast(list[dict[str, object]], matches[0]["windows"])
    scenes = cast(list[dict[str, object]], first_windows[0]["scenes"])
    scenes[0]["player_ids"] = ["0", "2", "3", "4", "5", "6", "7"]
    _seal(document)
    with pytest.raises(ValueError, match="positive canonical decimal strings"):
        validate_evaluation_population_authority_document(document)


def test_population_authority_hashes_and_eligibility_membership_are_fail_closed(
    tmp_path: Path,
) -> None:
    document, _ = _fixture(window_count=1)
    path = tmp_path / "synthetic-population.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    authority = load_evaluation_population_authority(path)
    assert authority.eligible_window_count == 20

    document["eligible_window_count"] = 19
    _seal(document)
    with pytest.raises(ValueError, match="eligible_window_count"):
        validate_evaluation_population_authority_document(document)


def test_population_schema_is_versioned_and_contains_no_population_instance() -> None:
    schema_path = (
        ROOT
        / "src"
        / "fpdbench"
        / "benchmarks"
        / "conditional_multi_agent_motion_prediction"
        / "evaluation_population_authority_v1.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    assert schema["$id"] == "fpdbench.prospective-evaluation-population/1.1.0"
    assert schema["properties"]["matches"]["maxItems"] == 20
    assert validate_evaluation_population_schema(ROOT) == ()


@pytest.mark.parametrize("regime", ["history_only", "future_ball", "future_opponent_plus_ball"])
def test_nonzero_origins_seal_both_representations_with_identical_physical_errors(regime) -> None:
    masked_truth = tuple(
        tuple(None if time == 0 and player == 0 else (0.0, 0.0) for player in range(7))
        for time in range(15)
    )
    document, output = _fixture(
        window_count=1, error_for=lambda *_: 3.0, truth_for=lambda *_: masked_truth
    )
    absolute_matches = {}
    displacement_matches = {}
    for match_id, windows in output.matches.items():
        absolute_windows = []
        displacement_windows = []
        for window in windows:
            absolute_scenes = []
            displacement_scenes = []
            for scene in window.scenes:
                origins = tuple((100.0 + index, -40.0 - index) for index in range(7))
                absolute_truth = tuple(
                    tuple(
                        origins[index] if pair is not None else None
                        for index, pair in enumerate(row)
                    )
                    for row in scene.truth
                )
                absolute_prediction = tuple(
                    tuple((x + 3.0, y) for x, y in origins) for _ in range(15)
                )
                absolute_scenes.append(
                    replace(scene, truth=absolute_truth, prediction=absolute_prediction)
                )
                displacement_scenes.append(scene)
                matches = cast(list[dict[str, object]], document["matches"])
                match_doc = next(m for m in matches if m["match_id"] == match_id)
                window_doc = cast(list[dict[str, object]], match_doc["windows"])[0]
                scene_doc = next(
                    s
                    for s in cast(list[dict[str, object]], window_doc["scenes"])
                    if s["scene_id"] == scene.scene_id
                )
                scene_doc["absolute_xy_truth_sha256"] = truth_sha256(
                    absolute_truth, target_representation="absolute_xy"
                )
                assert (
                    scene_doc["absolute_xy_truth_sha256"] != scene_doc["displacement_truth_sha256"]
                )
            absolute_windows.append(replace(window, scenes=tuple(absolute_scenes)))
            displacement_windows.append(replace(window, scenes=tuple(displacement_scenes)))
        absolute_matches[match_id] = tuple(absolute_windows)
        displacement_matches[match_id] = tuple(displacement_windows)
    _seal(document)
    authority = validate_evaluation_population_authority_document(document)
    absolute = EvaluationPopulationOutput(
        authority.manifest_sha256, absolute_matches, "absolute_xy"
    )
    displacement = EvaluationPopulationOutput(
        authority.manifest_sha256, displacement_matches, "origin_relative_displacement"
    )
    a = evaluate_prospective_trajectories(
        absolute, authority, cell_id=f"origin_persistence_v1|{regime}|absolute_xy"
    )
    d = evaluate_prospective_trajectories(
        displacement,
        authority,
        cell_id=f"origin_persistence_v1|{regime}|origin_relative_displacement",
    )
    assert a == d
    assert a.metrics is not None and a.metrics.ade_m == 3.0
    with pytest.raises(ValueError, match="target representation"):
        evaluate_prospective_trajectories(
            displacement, authority, cell_id=f"origin_persistence_v1|{regime}|absolute_xy"
        )
    with pytest.raises(ValueError, match="target truth differs"):
        evaluate_prospective_trajectories(
            replace(absolute, target_representation="origin_relative_displacement"),
            authority,
            cell_id=f"origin_persistence_v1|{regime}|origin_relative_displacement",
        )


@pytest.mark.parametrize("role", ["validation", "lomo"])
@pytest.mark.parametrize(
    "drift", ["digest", "match", "window", "player", "truth", "mask", "prediction"]
)
def test_validation_and_lomo_receive_the_full_population_gate(role: str, drift: str) -> None:
    document, output = _fixture(scoring_role="validation" if role == "validation" else "training")
    authority = validate_evaluation_population_authority_document(document)
    if role == "lomo":
        first_match = next(iter(output.matches))
        output = replace(output, matches={first_match: output.matches[first_match]})
    kwargs = {"cell_id": "origin_persistence_v1|history_only|absolute_xy", "role": role}
    if role == "lomo":
        kwargs["lomo_fold_id"] = "fold-01"
    assert evaluate_prospective_trajectories(output, authority, **kwargs).metrics is not None
    matches = dict(output.matches)
    match_id = next(iter(matches))
    windows = list(matches[match_id])
    if drift == "digest":
        output = replace(output, population_authority_sha256="0" * 64)
    elif drift == "match":
        matches.pop(match_id)
    elif drift == "window":
        matches[match_id] = tuple(reversed(windows))
    else:
        scene = windows[0].scenes[0]
        if drift == "player":
            scene = replace(scene, player_ids=tuple(reversed(scene.player_ids)))
        elif drift in {"truth", "mask"}:
            truth = [list(row) for row in scene.truth]
            truth[0][0] = (10.0, 2.0) if drift == "truth" else None
            scene = replace(scene, truth=tuple(tuple(row) for row in truth))
        else:
            prediction = [list(row) for row in scene.prediction]
            prediction[0][0] = (math.nan, 0.0)
            scene = replace(scene, prediction=tuple(tuple(row) for row in prediction))
        windows[0] = replace(windows[0], scenes=(scene, windows[0].scenes[1]))
        matches[match_id] = tuple(windows)
    with pytest.raises(ValueError):
        evaluate_prospective_trajectories(replace(output, matches=matches), authority, **kwargs)


def _result_fixture(role: str = "final_train", status: str = "completed"):
    document, _ = _fixture(window_count=1)
    population = validate_evaluation_population_authority_document(document)
    plan = empirical_experiment_plan.load_empirical_experiment_plan()
    learned = role != "baseline"
    target = "absolute_xy"
    model = "per_target_context_deepsets_mlp_v1" if learned else "origin_persistence_v1"
    cell = f"{model}|history_only|{target}"
    roles = dict(_roles())
    held_out = roles["training"][0] if role == "lomo" else None
    fold = "fold-01" if role == "lomo" else None
    seed = 1729 if learned else None
    train = [m for m in roles["training"] if m != held_out] if learned else []
    scopes = [("validation_match", roles["validation"])]
    if role != "lomo":
        scopes.append(("evaluation_match", roles["evaluation"]))
    if role == "lomo":
        scopes.append(("lomo_held_out_match", (held_out,)))
    elif role == "baseline":
        scopes.append(("lomo_held_out_match", roles["training"]))
    value = {
        k: plan[k]
        for k in (
            "plan_id",
            "plan_version",
            "plan_sha256",
            "protocol_id",
            "protocol_version",
            "protocol_sha256",
        )
    }
    value.update(
        {
            "schema_id": "fpdbench.prospective-experiment-result",
            "schema_version": "1.1.0",
            "cell_id": cell,
            "model_class_id": model,
            "information_regime": "history_only",
            "target_representation": target,
            "fit_role": role,
            "lomo_fold_id": fold,
            "held_out_match_id": held_out,
            "seed": seed,
            "run_id": f"{cell}|{role}|{fold or 'final'}|{seed if learned else 'deterministic'}",
            "train_match_ids": train,
            "validation_match_ids": list(roles["validation"]),
            "population_authority_sha256": population.manifest_sha256,
            "configuration_sha256": "1" * 64,
            "environment_sha256": "2" * 64,
            "checkpoint_sha256": "3" * 64 if learned and status == "completed" else None,
            "selected_step": 100 if learned and status == "completed" else None,
            "status": status,
            "stopping_reason": ("early_stopping" if learned else "baseline_complete")
            if status == "completed"
            else {
                "failed_infrastructure": "external_worker_interruption",
                "failed_model": "out_of_memory",
                "failed_validation": "invalid_population",
                "incomplete": "campaign_incomplete",
            }[status],
            "output_artifacts": [],
            "metrics": [
                {
                    "scope": scope,
                    "match_id": match,
                    "metric_id": metric,
                    "value": 1.0,
                    "unit": "metres",
                }
                for scope, ids in scopes
                for match in ids
                for metric in ("ade_m", "fde_m", "xy_rmse_m")
            ]
            if status == "completed"
            else [],
        }
    )
    _seal_result(value)
    return value, population


def _seal_result(value):
    value["manifest_sha256"] = _sha(
        canonical_bytes({key: item for key, item in value.items() if key != "manifest_sha256"})
    )


@pytest.mark.parametrize("role", ["final_train", "lomo", "baseline"])
@pytest.mark.parametrize(
    "status",
    ["completed", "failed_infrastructure", "failed_model", "failed_validation", "incomplete"],
)
def test_result_validator_accepts_exact_frozen_runs(role, status):
    from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
        validate_prospective_result_document,
    )

    value, population = _result_fixture(role, status)
    validate_prospective_result_document(value, population)


@pytest.mark.parametrize(
    ("field", "contradiction"),
    [
        ("cell_id", "origin_persistence_v1|history_only|absolute_xy"),
        ("model_class_id", "origin_persistence_v1"),
        ("information_regime", "future_ball"),
        ("target_representation", "origin_relative_displacement"),
        ("fit_role", "baseline"),
        ("train_match_ids", []),
        ("validation_match_ids", ["1874553", "1925299", "2006229", "2010085"]),
        ("seed", 2719),
        ("seed", True),
        ("run_id", "unbound-run"),
        ("checkpoint_sha256", None),
        ("selected_step", 101),
        ("population_authority_sha256", "0" * 64),
        ("plan_sha256", "0" * 64),
        ("status", "failed_model"),
        ("metrics", []),
        ("stopping_reason", "out_of_memory"),
    ],
)
def test_result_validator_rejects_resealed_cross_field_contradictions(field, contradiction):
    from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
        validate_prospective_result_document,
    )

    value, population = _result_fixture()
    value[field] = contradiction
    _seal_result(value)
    with pytest.raises(ValueError):
        validate_prospective_result_document(value, population)


@pytest.mark.parametrize(
    "drift",
    [
        "fold",
        "held_out",
        "train",
        "scope",
        "match",
        "duplicate",
        "nonfinite",
        "negative",
        "unit",
        "digest",
    ],
)
def test_lomo_result_validator_rejects_fold_metric_and_digest_contradictions(drift):
    from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
        validate_prospective_result_document,
    )

    value, population = _result_fixture("lomo")
    if drift == "fold":
        value["lomo_fold_id"] = "fold-02"
    elif drift == "held_out":
        value["held_out_match_id"] = "1899585"
    elif drift == "train":
        value["train_match_ids"] = list(dict(_roles())["training"])
    elif drift == "duplicate":
        value["metrics"].append(value["metrics"][0])
    elif drift != "digest":
        metric = value["metrics"][-1]
        field, item = {
            "scope": ("scope", "evaluation_match"),
            "match": ("match_id", "1899585"),
            "nonfinite": ("value", math.inf),
            "negative": ("value", -1.0),
            "unit": ("unit", "yards"),
        }[drift]
        metric[field] = item
    if drift not in {"digest", "nonfinite"}:
        _seal_result(value)
    else:
        value["manifest_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        validate_prospective_result_document(value, population)


def test_all_frozen_cells_seeds_and_lomo_folds_accept_exact_result_membership():
    from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
        validate_prospective_result_document,
    )

    plan = empirical_experiment_plan.load_empirical_experiment_plan()
    for cell in plan["factorial"]["cells"]:
        learned = cell["model_class_id"] == "per_target_context_deepsets_mlp_v1"
        for seed in plan["seeds"]["stochastic_seed_ids"] if learned else [None]:
            value, population = _result_fixture("final_train" if learned else "baseline")
            value.update(cell)
            value["seed"] = seed
            value["run_id"] = (
                f"{cell['cell_id']}|{value['fit_role']}|final|"
                f"{seed if learned else 'deterministic'}"
            )
            _seal_result(value)
            validate_prospective_result_document(value, population)
    for index, held_out in enumerate(dict(_roles())["training"], 1):
        value, population = _result_fixture("lomo")
        value["lomo_fold_id"] = f"fold-{index:02d}"
        value["held_out_match_id"] = held_out
        value["train_match_ids"] = [m for m in dict(_roles())["training"] if m != held_out]
        value["run_id"] = f"{value['cell_id']}|lomo|{value['lomo_fold_id']}|1729"
        for metric in value["metrics"]:
            if metric["scope"] == "lomo_held_out_match":
                metric["match_id"] = held_out
        _seal_result(value)
        validate_prospective_result_document(value, population)


def test_result_loader_rejects_duplicate_json_keys_and_failed_record_metrics(tmp_path):
    from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
        load_prospective_result,
        validate_prospective_result_document,
    )

    value, population = _result_fixture()
    path = tmp_path / "synthetic-result.json"
    path.write_text(json.dumps(value))
    assert load_prospective_result(path, population) == value
    path.write_text('{"status":"completed",' + json.dumps(value)[1:])
    with pytest.raises(ValueError, match="duplicate JSON key"):
        load_prospective_result(path, population)
    failed, _ = _result_fixture(status="failed_model")
    failed["metrics"] = value["metrics"]
    _seal_result(failed)
    with pytest.raises(ValueError, match="no metrics on failure"):
        validate_prospective_result_document(failed, population)
