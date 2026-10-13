from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable
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
                            "truth_sha256": truth_sha256(truth),
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
        "schema_version": "1.0.0",
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
    for match in authority.matches_for_role("evaluation"):
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
    output = EvaluationPopulationOutput(authority.manifest_sha256, output_matches)
    return document, output


def _score(document: dict[str, object], output: EvaluationPopulationOutput):
    authority = validate_evaluation_population_authority_document(document)
    return evaluate_prospective_trajectories(output, authority)


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
        _score(document, EvaluationPopulationOutput(output.population_authority_sha256, matches))


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
        _score(document, EvaluationPopulationOutput(output.population_authority_sha256, matches))


def test_gate_rejects_missing_or_reordered_windows_and_wrong_population_digest() -> None:
    document, output = _fixture(window_count=2)
    match_id = EVALUATION_MATCH_IDS[0]
    windows = output.matches[match_id]
    missing = dict(output.matches)
    missing[match_id] = windows[:1]
    with pytest.raises(ValueError, match="missing or adding windows"):
        _score(document, EvaluationPopulationOutput(output.population_authority_sha256, missing))

    reordered = dict(output.matches)
    reordered[match_id] = tuple(reversed(windows))
    with pytest.raises(ValueError, match="order or origin identity drift"):
        _score(document, EvaluationPopulationOutput(output.population_authority_sha256, reordered))

    with pytest.raises(ValueError, match="different population authority"):
        _score(document, EvaluationPopulationOutput("0" * 64, output.matches))


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
        _score(document, EvaluationPopulationOutput(output.population_authority_sha256, changed))

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
            EvaluationPopulationOutput(authority.manifest_sha256, output.matches), authority
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

    assert schema["$id"] == "fpdbench.prospective-evaluation-population/1.0.0"
    assert schema["properties"]["matches"]["maxItems"] == 20
    assert validate_evaluation_population_schema(ROOT) == ()
