import copy
from collections.abc import Mapping
from typing import cast

import pytest

from fpdbench.data_sources.skillcorner import load_manifest as load_source_manifest
from fpdbench.data_states.skillcorner import load_manifest as load_data_state_manifest
from fpdbench.eligibility.skillcorner import (
    EligibilityIssue,
    PhaseInterval,
    WindowEligibilityResult,
    evaluate_skillcorner_window,
    load_manifest,
    policy_hash,
    validate_manifest,
)


def _metadata() -> dict[str, object]:
    players: list[dict[str, object]] = []
    for player_id in range(1001, 1017):
        team_id = 101 if player_id < 1009 else 202
        players.append(
            {
                "id": player_id,
                "team_id": team_id,
                "playing_time": {
                    "by_period": [
                        {"name": "period_1", "start_frame": 100, "end_frame": 200},
                        {"name": "period_2", "start_frame": 300, "end_frame": 400},
                    ]
                },
            }
        )
    return {
        "id": 2017461,
        "home_team": {"id": 101},
        "away_team": {"id": 202},
        "pitch_length": 100.0,
        "pitch_width": 60.0,
        "match_periods": [
            {"period": 1, "start_frame": 100, "end_frame": 200},
            {"period": 2, "start_frame": 300, "end_frame": 400},
        ],
        "players": players,
    }


def _frame(offset: int) -> dict[str, object]:
    source = load_source_manifest()
    state = load_data_state_manifest()
    players = [
        {
            "player_id": player_id,
            "team_id": 101 if player_id < 1009 else 202,
            "group": "home" if player_id < 1009 else "away",
            "x_m": float(player_id % 20),
            "y_m": float((player_id % 10) - 5),
            "is_detected": player_id != 1001 or offset == 0,
        }
        for player_id in range(1001, 1017)
    ]
    return {
        "data_state_id": state["data_state_id"],
        "data_state_hash": state["data_state_hash"],
        "source_release_id": source["source_release_id"],
        "source_release_hash": source["source_release_hash"],
        "match_id": 2017461,
        "period": 1,
        "source_frame": 100 + 2 * offset,
        "canonical_sample_index": 50 + offset,
        "timestamp_deciseconds": 100 + 2 * offset,
        "home_team_id": 101,
        "away_team_id": 202,
        "pitch_length_m": 100.0,
        "pitch_width_m": 60.0,
        "players": players,
        "ball": {"x_m": 0.0, "y_m": 0.0, "is_detected": True},
        "possession": None,
    }


def _window(
    samples: list[dict[str, object]] | None = None,
    *,
    metadata: dict[str, object] | None = None,
    phases: list[PhaseInterval] | None = None,
    policy: Mapping[str, object] | None = None,
):
    return evaluate_skillcorner_window(
        samples if samples is not None else [_frame(index) for index in range(5)],
        history_intervals=2,
        future_intervals=2,
        match_metadata=metadata if metadata is not None else _metadata(),
        phase_intervals=phases if phases is not None else [_phase(1, 100, 200)],
        policy_manifest=policy,
    )


def _phase(period: int, start: int, end: int) -> PhaseInterval:
    return PhaseInterval(
        cast(str, load_source_manifest()["source_release_id"]), 2017461, period, start, end
    )


def _reason_codes(result: WindowEligibilityResult) -> set[str]:
    reasons = cast(tuple[EligibilityIssue, ...], result.exclusion_reasons)
    return {reason.code for reason in reasons}


def _warning_codes(result: WindowEligibilityResult) -> set[str]:
    warnings = cast(tuple[EligibilityIssue, ...], result.warnings)
    return {warning.code for warning in warnings}


def test_policy_manifest_binds_pinned_source_and_state_and_hashes_semantics() -> None:
    manifest = load_manifest()
    assert validate_manifest(manifest) == ()
    assert manifest["source_release_id"] == load_source_manifest()["source_release_id"]
    assert manifest["data_state_hash"] == load_data_state_manifest()["data_state_hash"]

    description_only = copy.deepcopy(manifest)
    description_only["description"] = "local descriptive wording"
    description_only["local_path"] = "/tmp/source"
    description_only["hostname"] = "synthetic-host"
    description_only["retrieved_at"] = "2099-01-01T00:00:00Z"
    assert validate_manifest(description_only) == ()
    assert description_only["policy_hash"] == manifest["policy_hash"]

    changed = copy.deepcopy(manifest)
    policy = cast(dict[str, object], changed["scientific_policy"])
    player_rules = cast(dict[str, object], policy["player_observations"])
    player_rules["minimum_valid_per_team_per_sample"] = 6
    changed["policy_hash"] = policy_hash(policy)
    assert changed["policy_hash"] != manifest["policy_hash"]
    assert validate_manifest(changed) == ()

    wrong_state = copy.deepcopy(manifest)
    wrong_state["data_state_hash"] = "0" * 64
    assert any("data_state_hash" in error for error in validate_manifest(wrong_state))


def test_complete_window_is_deterministic_and_returns_composable_quality() -> None:
    first = _window()
    second = _window()
    assert first == second
    assert first.eligible
    assert not first.exclusion_reasons
    assert first.quality["strata"] == {
        "detection_exposure": "mixed",
        "ball_detection_exposure": "all_detected",
        "player_completeness": "complete",
        "ball_completeness": "complete",
        "temporal_continuity": "continuous",
        "identity_transition_exposure": "none_observed",
        "source_quality_uncertainty": "unknown_per_observation",
        "phase_context": "all_in_play",
    }
    assert first.quality["player_observations"]["expected_active_player_frames"] == 80  # type: ignore[index]
    assert first.quality["player_observations"]["extrapolated_position_count"] == 4  # type: ignore[index]
    assert first.quality["player_observations"]["extrapolation_fraction"] == 0.05  # type: ignore[index]
    assert first.quality["player_observations"]["displacement_pair_denominator"] == 64  # type: ignore[index]
    assert first.quality["ball_observations"]["denominator_sample_count"] == 5  # type: ignore[index]
    assert first.quality["play_context"]["possession_unknown_fraction"] == 1.0  # type: ignore[index]
    assert first.quality["temporal"]["continuous_intervals"] == 4  # type: ignore[index]
    assert first.quality["temporal"]["continuity_fraction"] == 1.0  # type: ignore[index]
    assert "SOURCE_QUALITY_UNKNOWN" in _warning_codes(first)


def test_absent_and_explicit_null_players_remain_distinct() -> None:
    samples = [_frame(index) for index in range(5)]
    players = cast(list[dict[str, object]], samples[0]["players"])
    players.pop(0)  # Absent active player: a record-completeness failure.
    nullable = cast(dict[str, object], cast(list[dict[str, object]], samples[1]["players"])[0])
    nullable["x_m"] = None  # Explicit record, but not a valid coordinate.
    result = _window(samples)
    assert result.eligible  # Seven home players remain, meeting the frozen floor.
    assert "PLAYER_OBSERVATION_MISSING" in _warning_codes(result)
    assert "PLAYER_COORDINATES_MISSING" in _warning_codes(result)
    quality = cast(Mapping[str, object], result.quality["player_observations"])
    assert quality["observed_record_count"] == 79
    assert quality["null_coordinate_records"] == 1
    assert quality["missing_active_record_fraction"] == 1 / 80
    assert quality["completeness_fraction"] == 78 / 80


def test_null_ball_fails_coverage_without_imputation() -> None:
    samples = [_frame(index) for index in range(5)]
    samples[2]["ball"] = None
    result = _window(samples)
    assert not result.eligible
    assert {"BALL_MISSING_AT_ORIGIN", "BALL_COVERAGE_BELOW_MINIMUM"} <= _reason_codes(result)
    assert result.quality["ball_observations"]["valid_position_count"] == 4  # type: ignore[index]
    assert result.quality["ball_observations"]["completeness_fraction"] == 0.8  # type: ignore[index]


def test_extrapolated_ball_counts_toward_coverage_and_is_stratified() -> None:
    samples = [_frame(index) for index in range(5)]
    cast(dict[str, object], samples[0]["ball"])["is_detected"] = False
    result = _window(samples)
    assert result.eligible
    assert result.quality["strata"]["ball_detection_exposure"] == "mixed"  # type: ignore[index]
    assert result.quality["ball_observations"]["extrapolated_position_count"] == 1  # type: ignore[index]


def test_extrapolated_positions_count_but_substitution_is_a_warning_stratum() -> None:
    samples = [_frame(index) for index in range(5)]
    metadata = _metadata()
    roster = cast(list[dict[str, object]], metadata["players"])
    roster.append(
        {
            "id": 1017,
            "team_id": 101,
            "playing_time": {
                "by_period": [
                    {"name": "period_1", "start_frame": 106, "end_frame": 200},
                    {"name": "period_2", "start_frame": 300, "end_frame": 400},
                ]
            },
        }
    )
    old_entry = cast(dict[str, object], roster[7]["playing_time"])
    old_period = cast(list[dict[str, object]], old_entry["by_period"])[0]
    old_period["end_frame"] = 104
    for sample in samples[3:]:
        sample_players = cast(list[dict[str, object]], sample["players"])
        sample_players[:] = [player for player in sample_players if player["player_id"] != 1008]
        sample_players.append(
            {
                "player_id": 1017,
                "team_id": 101,
                "group": "home",
                "x_m": 17.0,
                "y_m": 1.0,
                "is_detected": False,
            }
        )
    result = _window(samples, metadata=metadata)
    assert result.eligible
    assert "IDENTITY_TRANSITION_EXPOSURE" in _warning_codes(result)
    assert result.quality["strata"]["identity_transition_exposure"] == "exposed"  # type: ignore[index]
    assert result.quality["temporal"]["active_roster_transition_intervals"] == 1  # type: ignore[index]
    assert result.quality["temporal"]["active_roster_transition_fraction"] == 0.25  # type: ignore[index]


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("gap", "TEMPORAL_GAP"),
        ("duplicate", "DUPLICATE_SAMPLE"),
        ("timestamp", "TIMESTAMP_DISCONTINUITY"),
        ("period", "PERIOD_BOUNDARY_CROSSED"),
    ],
)
def test_gaps_duplicates_timestamp_discontinuity_and_period_boundary(
    mutation: str, reason: str
) -> None:
    samples = [_frame(index) for index in range(5)]
    phases = [_phase(1, 100, 200), _phase(2, 300, 400)]
    if mutation == "gap":
        samples[3]["source_frame"] = 108
        samples[3]["canonical_sample_index"] = 54
        samples[3]["timestamp_deciseconds"] = 108
    elif mutation == "duplicate":
        samples[3]["source_frame"] = samples[2]["source_frame"]
        samples[3]["canonical_sample_index"] = samples[2]["canonical_sample_index"]
        samples[3]["timestamp_deciseconds"] = samples[2]["timestamp_deciseconds"]
    elif mutation == "timestamp":
        samples[3]["timestamp_deciseconds"] = 107
    else:
        for offset, frame in ((3, 300), (4, 302)):
            samples[offset]["period"] = 2
            samples[offset]["source_frame"] = frame
            samples[offset]["canonical_sample_index"] = frame // 2
            samples[offset]["timestamp_deciseconds"] = 2 * (offset - 3)
    result = _window(samples, phases=phases)
    assert reason in _reason_codes(result)


def test_missing_phase_is_out_of_play_or_unknown_and_possession_is_not_a_gate() -> None:
    samples = [_frame(index) for index in range(5)]
    for sample in samples:
        sample["possession"] = {"group": None, "player_id": None}
    result = _window(samples, phases=[_phase(1, 100, 104)])
    assert not result.eligible
    assert "PHASE_NOT_IN_PLAY_OR_UNKNOWN" in _reason_codes(result)
    assert result.quality["play_context"]["possession_unknown_samples"] == 5  # type: ignore[index]


def test_phase_intervals_must_bind_to_the_pinned_source_release() -> None:
    wrong_source = PhaseInterval("wrong-release", 2017461, 1, 100, 200)
    result = _window(phases=[wrong_source])
    assert "PHASE_SOURCE_IDENTITY_MISMATCH" in _reason_codes(result)


def test_coordinate_anomalies_and_fast_displacements_are_auditable() -> None:
    samples = [_frame(index) for index in range(5)]
    first_player = cast(dict[str, object], cast(list[object], samples[0]["players"])[0])
    first_player["x_m"] = 101.0
    result = _window(samples)
    assert "COORDINATE_IMPLAUSIBLE" in _reason_codes(result)

    samples = [_frame(index) for index in range(5)]
    player0 = cast(dict[str, object], cast(list[object], samples[0]["players"])[0])
    player1 = cast(dict[str, object], cast(list[object], samples[1]["players"])[0])
    player0["x_m"] = 0.0
    player1["x_m"] = 5.0
    result = _window(samples)
    assert result.eligible
    assert "PLAYER_DISPLACEMENT_OUTLIER" in _warning_codes(result)

    samples = [_frame(index) for index in range(5)]
    player = cast(dict[str, object], cast(list[object], samples[0]["players"])[0])
    player["x_m"] = 51.0
    result = _window(samples)
    assert result.eligible
    assert "PLAYER_POSITION_OUTSIDE_PITCH" in _warning_codes(result)

    samples = [_frame(index) for index in range(5)]
    player = cast(dict[str, object], cast(list[object], samples[0]["players"])[0])
    player["x_m"] = float("nan")
    result = _window(samples)
    assert "NONFINITE_COORDINATE" in _reason_codes(result)


def test_non_null_entity_shapes_must_match_the_measurement_contract() -> None:
    samples = [_frame(index) for index in range(5)]
    samples[0].pop("ball")
    result = _window(samples)
    assert "INVALID_SAMPLE_SCHEMA" in _reason_codes(result)

    samples = [_frame(index) for index in range(5)]
    player = cast(dict[str, object], cast(list[object], samples[0]["players"])[0])
    player.pop("group")
    result = _window(samples)
    assert "INVALID_SAMPLE_SCHEMA" in _reason_codes(result)


def test_incomplete_roster_metadata_keeps_quality_unknown_not_poor() -> None:
    metadata = _metadata()
    roster = cast(list[dict[str, object]], metadata["players"])
    del roster[0]["playing_time"]
    result = _window(metadata=metadata)
    assert result.eligible
    assert result.quality["strata"]["player_completeness"] == "unknown"  # type: ignore[index]
    assert result.quality["strata"]["identity_transition_exposure"] == "unknown"  # type: ignore[index]
    assert result.quality["player_observations"]["completeness_fraction"] is None  # type: ignore[index]


@pytest.mark.parametrize(
    ("sample_count", "reason"),
    [(2, "INSUFFICIENT_HISTORY_SUPPORT"), (4, "INSUFFICIENT_FUTURE_SUPPORT")],
)
def test_candidate_support_requires_history_origin_and_future_samples(
    sample_count: int, reason: str
) -> None:
    result = _window([_frame(index) for index in range(sample_count)])
    assert reason in _reason_codes(result)
    assert result.quality["strata"]["temporal_continuity"] == "unknown"  # type: ignore[index]
