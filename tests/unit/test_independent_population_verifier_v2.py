"""Synthetic, independently authored population verifier cases; no source payloads."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    independent_population_verifier_v2 as verifier,
)

_PRODUCER_FINGERPRINT = json.loads(
    (Path(__file__).parents[1] / "fixtures/pr20-production-package-fingerprint-v2.json").read_text(
        encoding="utf-8"
    )
)


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


def _digest(value: object) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _match_ids() -> tuple[str, ...]:
    source = json.loads(
        (
            Path(__file__).parents[2] / "src/fpdbench/data_sources/skillcorner_open_data_v1.json"
        ).read_text(encoding="utf-8")
    )
    return tuple(str(match_id) for match_id in source["selected_source_matches"])


def _timestamp(frame: int) -> str:
    seconds, deciseconds = divmod(frame, 10)
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{deciseconds * 10:02d}"


def _fixture(*, players_per_team: int = 7) -> list[verifier.MatchSourceBytesV2]:
    result = []
    for match_number, match_id in enumerate(_match_ids()):
        home_team = 600_000 + match_number * 2
        away_team = home_team + 1
        home_players = [
            100_000 + match_number * 100 + index for index in range(1, players_per_team + 1)
        ]
        away_players = [
            200_000 + match_number * 100 + index for index in range(1, players_per_team + 1)
        ]
        roster = [
            {
                "id": player_id,
                "team_id": team_id,
                "playing_time": {
                    "by_period": [{"name": "period_1", "start_frame": 100, "end_frame": 185}]
                },
            }
            for team_id, players in ((home_team, home_players), (away_team, away_players))
            for player_id in players
        ]
        metadata = {
            "id": int(match_id),
            "home_team": {"id": home_team},
            "away_team": {"id": away_team},
            "pitch_length": 105.0,
            "pitch_width": 68.0,
            "match_periods": [
                {"period": 1, "start_frame": 100, "end_frame": 186, "duration_frames": 86}
            ],
            "players": roster,
        }
        rows = []
        for frame in range(100, 186):
            player_data = []
            for team_index, players in enumerate((home_players, away_players)):
                for player_index, player_id in enumerate(players):
                    player_data.append(
                        {
                            "player_id": player_id,
                            "x": (-20.0 if team_index == 0 else 20.0)
                            + player_index * 0.5
                            + (frame - 100) * 0.01,
                            "y": -12.0 + player_index * 3.0,
                            "is_detected": True,
                        }
                    )
            rows.append(
                {
                    "frame": frame,
                    "timestamp": _timestamp(frame),
                    "period": 1,
                    "player_data": player_data,
                    "ball_data": {
                        "x": -1.0 + (frame - 100) * 0.01,
                        "y": 2.0,
                        "z": None,
                        "is_detected": True,
                    },
                    "possession": {"group": "home team", "player_id": home_players[0]},
                    "image_corners_projection": None,
                }
            )
        result.append(
            verifier.MatchSourceBytesV2(
                match_id,
                _json_bytes(metadata),
                b"".join(_json_bytes(row) + b"\n" for row in rows),
                _json_bytes([{"period": 1, "frame_start": 100, "frame_end": 186}]),
            )
        )
    return result


def _read_rows(source: verifier.MatchSourceBytesV2) -> tuple[dict[str, object], ...]:
    return tuple(json.loads(line) for line in source.tracking_jsonl.splitlines())


def _with_rows(
    source: verifier.MatchSourceBytesV2, rows: list[dict[str, object]]
) -> verifier.MatchSourceBytesV2:
    return replace(
        source,
        tracking_jsonl=b"".join(_json_bytes(row) + b"\n" for row in rows),
    )


def _baseline_submission(
    inputs: list[verifier.MatchSourceBytesV2], derivation: verifier.DerivationV2
) -> verifier.PopulationSubmissionV2:
    fingerprint = copy.deepcopy(_PRODUCER_FINGERPRINT)
    assert derivation.expected_manifest is not None
    receipt = verifier._expected_producer_receipt(
        derivation,
        tuple(inputs),
        derivation.expected_manifest,
        derivation.expected_candidates,
        derivation.expected_census,
        derivation.expected_truth,
        fingerprint,
    )
    receipt["receipt_sha256"] = _digest(receipt)
    return verifier.PopulationSubmissionV2(
        _json_bytes(derivation.expected_manifest),
        derivation.expected_candidates,
        derivation.expected_census,
        derivation.expected_truth,
        _json_bytes(receipt),
    )


def _reseal_manifest(manifest: dict[str, object]) -> None:
    manifest["membership_sha256"] = _digest(manifest["matches"])
    manifest.pop("manifest_sha256", None)
    manifest["manifest_sha256"] = _digest(manifest)


def _reseal_manifest_receipt(
    submission: verifier.PopulationSubmissionV2, manifest: dict[str, object]
) -> verifier.PopulationSubmissionV2:
    _reseal_manifest(manifest)
    receipt = json.loads(submission.receipt_json)
    receipt["population_manifest_sha256"] = manifest["manifest_sha256"]
    return _submission_with(submission, manifest=manifest, receipt=receipt)


def _scene_digests(row: dict[str, object]) -> dict[str, str]:
    def samples(field: str) -> tuple[tuple[tuple[float, float] | None, ...], ...]:
        raw = row[field]
        return tuple(
            tuple(None if pair is None else (float(pair[0]), float(pair[1])) for pair in step)
            for step in raw
        )

    absolute = samples("absolute_xy")
    displacement = samples("origin_relative_displacement")
    mask = tuple(tuple(bool(value) for value in step) for step in row["truth_mask"])
    return {
        "absolute_xy_truth_sha256": verifier._truth_digest(absolute, "absolute_xy"),
        "displacement_truth_sha256": verifier._truth_digest(
            displacement, "origin_relative_displacement"
        ),
        "truth_mask_sha256": verifier._mask_digest(mask),
    }


def _submission_with(
    submission: verifier.PopulationSubmissionV2,
    *,
    manifest: dict[str, object] | None = None,
    candidates: list[dict[str, object]] | None = None,
    census: list[dict[str, object]] | None = None,
    truth: list[dict[str, object]] | None = None,
    receipt: dict[str, object] | None = None,
) -> verifier.PopulationSubmissionV2:
    actual_manifest = json.loads(submission.manifest_json) if manifest is None else manifest
    actual_candidates = (
        [json.loads(line) for line in submission.candidates_jsonl.splitlines()]
        if candidates is None
        else candidates
    )
    actual_census = (
        [json.loads(line) for line in submission.diagnostic_census_jsonl.splitlines()]
        if census is None
        else census
    )
    actual_truth = (
        [json.loads(line) for line in submission.truth_jsonl.splitlines()]
        if truth is None
        else truth
    )
    actual_receipt = json.loads(submission.receipt_json) if receipt is None else receipt
    manifest_bytes = _json_bytes(actual_manifest)
    candidate_bytes = b"".join(_json_bytes(row) + b"\n" for row in actual_candidates)
    census_bytes = b"".join(_json_bytes(row) + b"\n" for row in actual_census)
    truth_bytes = b"".join(_json_bytes(row) + b"\n" for row in actual_truth)
    actual_receipt["candidates_jsonl_sha256"] = hashlib.sha256(candidate_bytes).hexdigest()
    actual_receipt["diagnostic_census_jsonl_sha256"] = hashlib.sha256(census_bytes).hexdigest()
    actual_receipt["truth_jsonl_sha256"] = hashlib.sha256(truth_bytes).hexdigest()
    actual_receipt["population_manifest_sha256"] = actual_manifest["manifest_sha256"]
    actual_receipt.pop("receipt_sha256", None)
    actual_receipt["receipt_sha256"] = _digest(actual_receipt)
    return verifier.PopulationSubmissionV2(
        manifest_bytes,
        candidate_bytes,
        census_bytes,
        truth_bytes,
        _json_bytes(actual_receipt),
    )


def test_recomputes_authorities_roles_sampling_census_and_truth() -> None:
    inputs = _fixture()
    derivation = verifier._derive(tuple(inputs))
    report = verifier.derive_synthetic_population_v2(inputs)

    assert len(derivation.role_order) == 20
    roles = {
        role: tuple(match_id for item_role, match_id in derivation.role_order if item_role == role)
        for role in ("training", "validation", "evaluation")
    }
    assert roles == {
        "training": (
            "1886347",
            "1899585",
            "1927964",
            "1959846",
            "1986691",
            "1996436",
            "2006363",
            "2007448",
            "2007721",
            "2011166",
            "2013725",
            "2016236",
        ),
        "validation": ("1953632", "1996435", "2015213", "2017461"),
        "evaluation": ("1874553", "1925299", "2006229", "2010085"),
    }
    assert report.role_assignment_sha256 == (
        "923dc2721a05620716f23c3b4cb1814e73485f80052f00c5334ccce666b99d94"
    )
    assert derivation.candidate_count == 60
    assert derivation.eligible_count == 60
    assert derivation.diagnostic_grid_count == 860
    assert derivation.scoreable_window_count == 60
    assert all(len(candidate.origin.support) == 41 for candidate in derivation.candidates)
    assert all(candidate.included and candidate.scoreable for candidate in derivation.candidates)
    assert all(
        [
            candidate.origin.origin_sample_id
            for candidate in derivation.candidates
            if candidate.origin.match_id == match_id
        ]
        == ["period_1/sample_75", "period_1/sample_76", "period_1/sample_77"]
        for _, match_id in derivation.role_order
    )
    assert [
        int(row["origin_sample_id"].split("/sample_")[1]) for row in derivation.census_rows[:43]
    ] == list(range(50, 93))
    assert report.status == "DERIVED"
    assert report.qualification_status == "NOT_QUALIFIED"
    assert report.authoritative is False
    assert report.candidate_count == 60
    assert report.eligible_count == 60
    assert report.diagnostic_grid_count == 860
    assert report.scoreable_window_count == 60
    assert len(report.retained_sample_snapshots) == 20
    assert all(
        (
            item.raw_source_frames,
            item.even_source_frames,
            item.odd_source_frames,
            item.retained_samples,
        )
        == (86, 43, 43, 43)
        for item in report.retained_sample_snapshots
    )
    assert len(report.match_roles) == 20
    assert all(
        (
            item.diagnostic_grid_count,
            item.candidate_count,
            item.eligible_window_count,
            item.directed_scene_count,
            item.scoreable_window_count,
        )
        == (43, 3, 3, 6, 3)
        for item in report.match_counts
    )
    encoded = json.loads(report.to_json_bytes())
    unhashed = dict(encoded)
    report_hash = unhashed.pop("report_sha256")
    assert report_hash == _digest(unhashed)
    assert "truth" not in encoded and "rows" not in encoded


def test_exact_ball_support_threshold_and_missing_origin_are_independent() -> None:
    inputs = _fixture()
    first = inputs[0]
    rows = [dict(row) for row in _read_rows(first)]
    for frame in (102, 106):
        ball = dict(rows[frame - 100]["ball_data"])
        ball["x"] = None
        ball["y"] = None
        rows[frame - 100]["ball_data"] = ball
    inputs[0] = _with_rows(first, rows)
    exact_threshold = verifier._derive(tuple(inputs))
    at_75 = next(
        item
        for item in exact_threshold.candidates
        if item.origin.match_id == first.match_id and item.origin.sample_index == 75
    )
    assert at_75.diagnostic["quality"]["ball_observations"]["valid_position_count"] == 39
    assert at_75.included is True

    inputs = _fixture()
    first = inputs[0]
    rows = [dict(row) for row in _read_rows(first)]
    for frame in (102, 106, 108):
        ball = dict(rows[frame - 100]["ball_data"])
        ball["x"] = None
        ball["y"] = None
        rows[frame - 100]["ball_data"] = ball
    inputs[0] = _with_rows(first, rows)
    derivation = verifier._derive(tuple(inputs))
    at_75 = next(
        item
        for item in derivation.candidates
        if item.origin.match_id == first.match_id and item.origin.sample_index == 75
    )
    assert at_75.diagnostic["quality"]["ball_observations"]["valid_position_count"] == 38
    assert at_75.included is False
    assert {issue["code"] for issue in at_75.diagnostic["exclusion_reasons"]} == {
        "BALL_COVERAGE_BELOW_MINIMUM"
    }

    inputs = _fixture()
    first = inputs[0]
    rows = [dict(row) for row in _read_rows(first) if row["frame"] != 100]
    inputs[0] = _with_rows(first, rows)
    derivation = verifier._derive(tuple(inputs))
    census_row = next(
        row
        for row in derivation.census_rows
        if row["match_id"] == first.match_id and row["origin_sample_id"] == "period_1/sample_50"
    )
    assert census_row["diagnostic"]["candidate_rules_pass"] is False
    assert "BALL_MISSING_AT_ORIGIN" in {
        issue["code"] for issue in census_row["diagnostic"]["exclusion_reasons"]
    }
    assert sum(item.origin.match_id == first.match_id for item in derivation.candidates) == 2
    assert derivation.diagnostic_grid_count == 860

    inputs = _fixture()
    first = inputs[0]
    rows = [dict(row) for row in _read_rows(first)]
    rows[50]["ball_data"] = None
    inputs[0] = _with_rows(first, rows)
    derivation = verifier._derive(tuple(inputs))
    origin_missing_ball = next(
        item
        for item in derivation.candidates
        if item.origin.match_id == first.match_id and item.origin.sample_index == 75
    )
    assert "BALL_MISSING_AT_ORIGIN" in {
        issue["code"] for issue in origin_missing_ball.diagnostic["exclusion_reasons"]
    }


def test_null_flag_finite_ball_stops_before_candidate_or_truth_membership() -> None:
    inputs = _fixture()
    first = inputs[0]
    metadata = json.loads(first.metadata_json)
    metadata["match_periods"].append(
        {"period": 2, "start_frame": 300, "end_frame": 302, "duration_frames": 2}
    )
    for player in metadata["players"]:
        player["playing_time"]["by_period"].append(
            {"name": "period_2", "start_frame": 300, "end_frame": 300}
        )
    rows = [dict(row) for row in _read_rows(first)]
    drift = dict(rows[-1])
    drift["frame"] = 300
    drift["timestamp"] = "00:00:00.00"
    drift["period"] = 2
    drift["ball_data"] = {"x": 0.0, "y": 0.0, "z": None, "is_detected": None}
    rows.append(drift)
    phases = [
        {"period": 1, "frame_start": 100, "frame_end": 186},
        {"period": 2, "frame_start": 300, "frame_end": 301},
    ]
    inputs[0] = replace(
        first,
        metadata_json=_json_bytes(metadata),
        tracking_jsonl=b"".join(_json_bytes(row) + b"\n" for row in rows),
        phase_intervals_json=_json_bytes(phases),
    )

    report = verifier.derive_synthetic_population_v2(inputs)
    assert report.status == "STOPPED"
    assert report.stop_code == "BALL_NULL_FLAG_WITH_FINITE_XY_UNAPPROVED"
    assert report.ball_null_flag_finite_xy_count == 1
    assert report.candidate_count is None
    assert report.eligible_count is None
    assert report.scoreable_window_count is None
    assert report.qualification_status == "NOT_QUALIFIED"


def test_phase_gap_temporal_fault_and_strict_json_fail_closed() -> None:
    inputs = _fixture()
    first = inputs[0]
    inputs[0] = replace(
        first,
        phase_intervals_json=_json_bytes(
            [
                {"period": 1, "frame_start": 100, "frame_end": 150},
                {"period": 1, "frame_start": 151, "frame_end": 186},
            ]
        ),
    )
    derivation = verifier._derive(tuple(inputs))
    first_candidate = next(
        item for item in derivation.candidates if item.origin.match_id == first.match_id
    )
    assert "PHASE_NOT_IN_PLAY_OR_UNKNOWN" in {
        issue["code"] for issue in first_candidate.diagnostic["exclusion_reasons"]
    }

    inputs = _fixture()
    first = inputs[0]
    rows = [dict(row) for row in _read_rows(first)]
    rows[10]["timestamp"] = _timestamp(112)
    inputs[0] = _with_rows(first, rows)
    report = verifier.derive_synthetic_population_v2(inputs)
    assert report.status == "INVALID_INPUT"


def test_sampling_uses_absolute_even_frames_and_preserves_gaps() -> None:
    complete = _fixture()
    first = complete[0]
    odd_removed = [dict(row) for row in _read_rows(first) if row["frame"] != 101]
    complete[0] = _with_rows(first, odd_removed)
    odd_result = verifier._derive(tuple(complete))
    baseline = verifier._derive(tuple(_fixture()))
    assert odd_result.expected_manifest == baseline.expected_manifest
    assert odd_result.expected_candidates == baseline.expected_candidates
    assert odd_result.expected_truth == baseline.expected_truth
    changed_snapshot = next(item for item in odd_result.contexts if item.match_id == first.match_id)
    assert (changed_snapshot.raw_source_frames, changed_snapshot.retained_samples_sha256) == (
        85,
        next(
            item for item in baseline.contexts if item.match_id == first.match_id
        ).retained_samples_sha256,
    )

    complete = _fixture()
    first = complete[0]
    even_removed = [dict(row) for row in _read_rows(first) if row["frame"] != 102]
    complete[0] = _with_rows(first, even_removed)
    gap_result = verifier._derive(tuple(complete))
    assert gap_result.candidate_count == 58
    assert gap_result.diagnostic_grid_count == 860
    assert sum(item.origin.match_id == first.match_id for item in gap_result.candidates) == 1


@pytest.mark.parametrize("frame", [101, 102])
def test_parser_requires_exact_raw_frame_keys_on_both_parities(frame: int) -> None:
    source = _fixture()[0]
    rows = [dict(row) for row in _read_rows(source)]
    rows[frame - 100]["unexpected"] = None
    with pytest.raises(ValueError, match="source schema"):
        verifier._parse_match(_with_rows(source, rows))


def test_parser_validates_nested_source_fields_on_even_frames_only() -> None:
    source = _fixture()[0]
    rows = [dict(row) for row in _read_rows(source)]
    malformed_nested = {
        "player_data": [{"player_id": 1, "extra": True}],
        "ball_data": {"unexpected": True},
        "possession": {"unexpected": True},
    }
    odd_rows = [dict(row) for row in rows]
    odd_rows[1].update(malformed_nested)
    odd_context = verifier._parse_match(_with_rows(source, odd_rows))
    baseline_context = verifier._parse_match(source)
    assert odd_context.retained_samples_sha256 == baseline_context.retained_samples_sha256
    assert odd_context.raw_source_frames == baseline_context.raw_source_frames == 86

    even_rows = [dict(row) for row in rows]
    even_rows[2].update(malformed_nested)
    with pytest.raises(ValueError):
        verifier._parse_match(_with_rows(source, even_rows))


@pytest.mark.parametrize("malformation", ["extra_key", "duplicate", "unknown_identity"])
def test_parser_rejects_malformed_retained_player_schema_and_identity(
    malformation: str,
) -> None:
    source = _fixture()[0]
    rows = [dict(row) for row in _read_rows(source)]
    players = [dict(player) for player in rows[2]["player_data"]]
    if malformation == "extra_key":
        players[0]["extra"] = True
    elif malformation == "duplicate":
        players.append(dict(players[0]))
    else:
        players[0]["player_id"] = 999_999
    rows[2]["player_data"] = players
    with pytest.raises(ValueError):
        verifier._parse_match(_with_rows(source, rows))


def test_adjacent_period_support_is_a_candidate_then_fails_period_rule() -> None:
    inputs = _fixture()
    first = inputs[0]
    metadata = json.loads(first.metadata_json)
    metadata["match_periods"] = [
        {"period": 1, "start_frame": 100, "end_frame": 140, "duration_frames": 40},
        {"period": 2, "start_frame": 140, "end_frame": 186, "duration_frames": 46},
    ]
    for player in metadata["players"]:
        player["playing_time"]["by_period"] = [
            {"name": "period_1", "start_frame": 100, "end_frame": 139},
            {"name": "period_2", "start_frame": 140, "end_frame": 185},
        ]
    rows = [dict(row) for row in _read_rows(first)]
    for row in rows:
        frame = int(row["frame"])
        row["period"] = 1 if frame < 140 else 2
        row["timestamp"] = _timestamp(frame if frame < 140 else frame - 140)
    phases = [
        {"period": 1, "frame_start": 100, "frame_end": 140},
        {"period": 2, "frame_start": 140, "frame_end": 185},
    ]
    inputs[0] = replace(
        first,
        metadata_json=_json_bytes(metadata),
        tracking_jsonl=b"".join(_json_bytes(row) + b"\n" for row in rows),
        phase_intervals_json=_json_bytes(phases),
    )
    derivation = verifier._derive(tuple(inputs))
    candidates = [item for item in derivation.candidates if item.origin.match_id == first.match_id]
    assert [item.origin.sample_index for item in candidates] == [75, 76, 77]
    assert all(
        "PERIOD_BOUNDARY_CROSSED"
        in {issue["code"] for issue in item.diagnostic["exclusion_reasons"]}
        for item in candidates
    )
    assert derivation.diagnostic_grid_count == 860


def test_player_floor_and_non_gating_quality_warnings_are_replayed() -> None:
    inputs = _fixture()
    first = inputs[0]
    rows = [dict(row) for row in _read_rows(first)]
    rows[50]["player_data"] = rows[50]["player_data"][1:]
    ball = dict(rows[54]["ball_data"])
    ball["x"] = 60.0
    ball["is_detected"] = False
    rows[54]["ball_data"] = ball
    inputs[0] = _with_rows(first, rows)
    derivation = verifier._derive(tuple(inputs))
    candidate = next(
        item
        for item in derivation.candidates
        if item.origin.match_id == first.match_id and item.origin.sample_index == 75
    )
    reasons = {issue["code"] for issue in candidate.diagnostic["exclusion_reasons"]}
    warnings = {issue["code"] for issue in candidate.diagnostic["warnings"]}
    assert "PLAYER_COUNT_BELOW_TEAM_MINIMUM" in reasons
    assert "BALL_COVERAGE_BELOW_MINIMUM" not in reasons
    assert "BALL_OUTSIDE_PITCH" in warnings
    assert candidate.diagnostic["quality"]["ball_observations"]["valid_position_count"] == 41
    assert candidate.diagnostic["quality"]["ball_observations"]["flag_false_count"] == 1

    inputs = _fixture()
    first = inputs[0]
    duplicate_frame = dict(_read_rows(first)[0])
    raw = first.tracking_jsonl + _json_bytes(duplicate_frame) + b"\n"
    report = verifier.derive_synthetic_population_v2(
        [replace(first, tracking_jsonl=raw), *inputs[1:]]
    )
    assert report.status == "INVALID_INPUT"


def test_diagnostic_occurrences_keep_indices_multiplicity_and_order() -> None:
    inputs = _fixture()
    source = inputs[0]
    rows = [dict(row) for row in _read_rows(source)]
    rows[50]["player_data"][0]["x"] = None
    rows[50]["player_data"][1]["y"] = None
    rows[50]["ball_data"] = {"x": None, "y": 2.0, "z": None, "is_detected": None}
    rows[52]["ball_data"] = None
    rows[54]["player_data"] = rows[54]["player_data"][1:]
    rows[54]["ball_data"] = {"x": None, "y": None, "z": None, "is_detected": False}
    rows[56]["ball_data"] = {"x": None, "y": None, "z": None, "is_detected": True}
    phases = [
        {"period": 1, "frame_start": 100, "frame_end": 150},
        {"period": 1, "frame_start": 151, "frame_end": 186},
    ]
    inputs[0] = replace(
        source,
        tracking_jsonl=b"".join(_json_bytes(row) + b"\n" for row in rows),
        phase_intervals_json=_json_bytes(phases),
    )

    derivation = verifier._derive(tuple(inputs))
    diagnostic = next(
        item.diagnostic
        for item in derivation.candidates
        if item.origin.match_id == source.match_id and item.origin.sample_index == 75
    )
    warnings = [(item["code"], item["sample_index"]) for item in diagnostic["warnings"]]
    exclusions = [(item["code"], item["sample_index"]) for item in diagnostic["exclusion_reasons"]]

    assert warnings.count(("PLAYER_COORDINATES_MISSING", 75)) == 2
    assert ("BALL_DETECTION_UNKNOWN", 75) in warnings
    assert ("BALL_COORDINATES_PARTIAL", 75) in warnings
    assert ("BALL_OBJECT_ABSENT", 76) in warnings
    assert ("BALL_COORDINATES_MISSING", 77) in warnings
    assert ("PLAYER_OBSERVATION_MISSING", 77) in warnings
    assert exclusions.count(("PHASE_NOT_IN_PLAY_OR_UNKNOWN", 75)) == 1
    assert exclusions.count(("PLAYER_COUNT_BELOW_TEAM_MINIMUM", 77)) == 1
    assert warnings == sorted(
        warnings, key=lambda item: (-1 if item[1] is None else item[1], item[0])
    )
    assert exclusions == sorted(
        exclusions, key=lambda item: (-1 if item[1] is None else item[1], item[0])
    )


def test_required_match_without_any_scoreable_window_is_incomplete() -> None:
    inputs = _fixture()
    first = inputs[0]
    metadata = json.loads(first.metadata_json)
    home_ids = {
        player["id"]
        for player in metadata["players"]
        if player["team_id"] == metadata["home_team"]["id"]
    }
    away_ids = {
        player["id"]
        for player in metadata["players"]
        if player["team_id"] == metadata["away_team"]["id"]
    }
    replacements: dict[str, list[int]] = {"home": [], "away": []}
    for side, team_id in (
        ("home", metadata["home_team"]["id"]),
        ("away", metadata["away_team"]["id"]),
    ):
        base_id = 900_000 if side == "home" else 910_000
        for offset in range(7):
            player_id = base_id + offset
            replacements[side].append(player_id)
            metadata["players"].append(
                {
                    "id": player_id,
                    "team_id": team_id,
                    "playing_time": {
                        "by_period": [{"name": "period_1", "start_frame": 180, "end_frame": 185}]
                    },
                }
            )
    for player in metadata["players"]:
        if player["id"] in home_ids | away_ids:
            player["playing_time"]["by_period"][0]["end_frame"] = 179
    rows = [dict(row) for row in _read_rows(first)]
    for row in rows:
        if row["frame"] >= 180:
            row["player_data"] = [
                {
                    "player_id": player_id,
                    "x": (-15.0 if side == "home" else 15.0) + offset,
                    "y": float(offset),
                    "is_detected": True,
                }
                for side in ("home", "away")
                for offset, player_id in enumerate(replacements[side])
            ]
    inputs[0] = replace(first, metadata_json=_json_bytes(metadata))
    inputs[0] = _with_rows(inputs[0], rows)
    report = verifier.derive_synthetic_population_v2(inputs)
    assert report.status == "INCOMPLETE"
    assert report.eligible_count == 60
    assert report.scoreable_window_count == 57
    assert report.qualification_status == "NOT_QUALIFIED"


def test_target_panels_masks_false_detections_and_nonzero_anchors() -> None:
    inputs = _fixture()
    first = inputs[0]
    metadata = json.loads(first.metadata_json)
    newcomer = 999_001
    metadata["players"].append(
        {
            "id": newcomer,
            "team_id": metadata["home_team"]["id"],
            "playing_time": {
                "by_period": [{"name": "period_1", "start_frame": 152, "end_frame": 185}]
            },
        }
    )
    rows = [dict(row) for row in _read_rows(first)]
    for row in rows:
        if row["frame"] >= 152:
            player_data = list(row["player_data"])
            player_data.append({"player_id": newcomer, "x": -10.0, "y": 5.0, "is_detected": True})
            row["player_data"] = player_data
    origin_row = rows[50]
    origin_row["player_data"][0]["is_detected"] = False
    future_row = rows[52]
    future_row["player_data"][0]["x"] = None
    future_row["player_data"][0]["is_detected"] = False
    inputs[0] = replace(first, metadata_json=_json_bytes(metadata))
    inputs[0] = _with_rows(inputs[0], rows)
    derivation = verifier._derive(tuple(inputs))
    candidate = next(
        item
        for item in derivation.candidates
        if item.origin.match_id == first.match_id and item.origin.sample_index == 75
    )
    assert candidate.included is True
    assert candidate.scenes is not None
    home = candidate.scenes[0]
    assert len(home.player_ids) == 7
    assert newcomer not in home.player_ids
    assert home.origin_xy[0][0] != 0.0
    assert home.mask[0][0] is False
    assert home.absolute_xy[0][0] is None
    assert home.displacement_xy[0][0] is None
    assert home.mask_digest == verifier._mask_digest(home.mask)
    assert home.absolute_digest != home.displacement_digest
    assert len(home.absolute_xy) == 15
    assert len(home.displacement_xy) == 15
    for step, delta, mask in zip(home.absolute_xy, home.displacement_xy, home.mask, strict=True):
        for point, displacement, valid, anchor in zip(
            step, delta, mask, home.origin_xy, strict=True
        ):
            if valid:
                assert point is not None and displacement is not None
                assert point[0] == pytest.approx(displacement[0] + anchor[0], abs=1e-12)
                assert point[1] == pytest.approx(displacement[1] + anchor[1], abs=1e-12)


def test_read_only_comparator_detects_reordering_missing_rows_and_rehashed_fabrication() -> None:
    inputs = _fixture()
    derivation = verifier._derive(tuple(inputs))
    submission = _baseline_submission(inputs, derivation)
    report = verifier.compare_population_v2(
        inputs,
        submission,
        producer_revision=verifier.PRODUCER_REVISION,
    )
    assert report.status == "RECONCILED"
    assert not report.mismatches
    assert report.authoritative is False
    assert report.qualification_status == "NOT_QUALIFIED"

    candidate_rows = [json.loads(line) for line in submission.candidates_jsonl.splitlines()]
    reordered = _submission_with(submission, candidates=list(reversed(candidate_rows)))
    report = verifier.compare_population_v2(
        inputs, reordered, producer_revision=verifier.PRODUCER_REVISION
    )
    assert report.status == "MISMATCH"
    assert any(item.artifact == "candidates_jsonl" for item in report.mismatches)

    omitted = _submission_with(submission, candidates=candidate_rows[:-1])
    report = verifier.compare_population_v2(
        inputs, omitted, producer_revision=verifier.PRODUCER_REVISION
    )
    assert any(item.path.endswith("/length") for item in report.mismatches)

    altered_warnings = copy.deepcopy(candidate_rows)
    altered_warnings[0]["diagnostic"]["warnings"].append({"code": "BALL_OBJECT_ABSENT"})
    altered_digest = _digest(altered_warnings[0]["diagnostic"])
    altered_warnings[0]["eligibility_result_sha256"] = altered_digest
    warning_manifest = json.loads(submission.manifest_json)
    warning_match = next(
        item
        for item in warning_manifest["matches"]
        if item["match_id"] == altered_warnings[0]["match_id"]
    )
    warning_window = next(
        item
        for item in warning_match["windows"]
        if item["origin_sample_id"] == altered_warnings[0]["origin_sample_id"]
    )
    warning_window["eligibility_result_sha256"] = altered_digest
    _reseal_manifest(warning_manifest)
    warning_receipt = json.loads(submission.receipt_json)
    warning_receipt["population_manifest_sha256"] = warning_manifest["manifest_sha256"]
    fabricated_warning = _submission_with(
        submission,
        manifest=warning_manifest,
        candidates=altered_warnings,
        receipt=warning_receipt,
    )
    report = verifier.compare_population_v2(
        inputs, fabricated_warning, producer_revision=verifier.PRODUCER_REVISION
    )
    assert any(item.artifact == "candidates_jsonl" for item in report.mismatches)

    manifest = json.loads(submission.manifest_json)
    manifest["matches"][0]["role"] = "evaluation"
    fabricated = _reseal_manifest_receipt(submission, manifest)
    report = verifier.compare_population_v2(
        inputs, fabricated, producer_revision=verifier.PRODUCER_REVISION
    )
    assert any(item.artifact == "manifest_json" for item in report.mismatches)
    assert any(item.artifact == "receipt_json" for item in report.mismatches)

    altered_players = json.loads(submission.manifest_json)
    original_player_id = int(
        altered_players["matches"][0]["windows"][0]["scenes"][0]["player_ids"][0]
    )
    altered_players["matches"][0]["windows"][0]["scenes"][0]["player_ids"][0] = str(
        original_player_id - 1
    )
    forged_panel = _reseal_manifest_receipt(submission, altered_players)
    report = verifier.compare_population_v2(
        inputs, forged_panel, producer_revision=verifier.PRODUCER_REVISION
    )
    assert any("player_ids" in item.path for item in report.mismatches)

    truth_rows = [json.loads(line) for line in submission.truth_jsonl.splitlines()]
    changed = copy.deepcopy(truth_rows)
    changed[0]["absolute_xy"][0][0][0] += 100.0
    digests = _scene_digests(changed[0])
    changed[0].update(digests)
    changed_manifest = json.loads(submission.manifest_json)
    changed_match = next(
        item for item in changed_manifest["matches"] if item["match_id"] == changed[0]["match_id"]
    )
    changed_window = next(
        item for item in changed_match["windows"] if item["window_id"] == changed[0]["window_id"]
    )
    changed_scene = next(
        item for item in changed_window["scenes"] if item["scene_id"] == changed[0]["scene_id"]
    )
    changed_scene.update(digests)
    changed_submission = _reseal_manifest_receipt(submission, changed_manifest)
    fabricated_truth = _submission_with(changed_submission, truth=changed)
    report = verifier.compare_population_v2(
        inputs, fabricated_truth, producer_revision=verifier.PRODUCER_REVISION
    )
    assert any(item.artifact == "truth_jsonl" for item in report.mismatches)
    assert any(item.artifact == "manifest_json" for item in report.mismatches)

    changed_mask_rows = copy.deepcopy(truth_rows)
    changed_mask_rows[0]["absolute_xy"][0][0] = None
    changed_mask_rows[0]["origin_relative_displacement"][0][0] = None
    changed_mask_rows[0]["truth_mask"][0][0] = False
    mask_digests = _scene_digests(changed_mask_rows[0])
    changed_mask_rows[0].update(mask_digests)
    mask_manifest = json.loads(submission.manifest_json)
    mask_match = next(
        item
        for item in mask_manifest["matches"]
        if item["match_id"] == changed_mask_rows[0]["match_id"]
    )
    mask_window = next(
        item
        for item in mask_match["windows"]
        if item["window_id"] == changed_mask_rows[0]["window_id"]
    )
    mask_scene = next(
        item
        for item in mask_window["scenes"]
        if item["scene_id"] == changed_mask_rows[0]["scene_id"]
    )
    mask_scene.update(mask_digests)
    mask_submission = _reseal_manifest_receipt(submission, mask_manifest)
    fabricated_mask = _submission_with(mask_submission, truth=changed_mask_rows)
    report = verifier.compare_population_v2(
        inputs, fabricated_mask, producer_revision=verifier.PRODUCER_REVISION
    )
    assert any(item.artifact == "truth_jsonl" for item in report.mismatches)
    assert any("truth_mask_sha256" in item.path for item in report.mismatches)

    # A membership edit plus fresh membership, manifest, and receipt hashes still fails.
    forged_membership = json.loads(submission.manifest_json)
    forged_membership["matches"][0]["windows"].pop()
    forged_membership["eligible_window_count"] = 59
    membership_submission = _reseal_manifest_receipt(submission, forged_membership)
    report = verifier.compare_population_v2(
        inputs, membership_submission, producer_revision=verifier.PRODUCER_REVISION
    )
    assert any(item.artifact == "manifest_json" for item in report.mismatches)


def test_forged_receipt_digest_and_wrong_producer_fingerprint_do_not_reconcile() -> None:
    inputs = _fixture()
    derivation = verifier._derive(tuple(inputs))
    submission = _baseline_submission(inputs, derivation)
    receipt = json.loads(submission.receipt_json)
    receipt["match_counts"][0]["candidate_window_count"] += 1
    resealed = _submission_with(submission, receipt=receipt)
    report = verifier.compare_population_v2(
        inputs, resealed, producer_revision=verifier.PRODUCER_REVISION
    )
    assert any(item.artifact == "receipt_json" for item in report.mismatches)

    forged_fingerprint = copy.deepcopy(_PRODUCER_FINGERPRINT)
    forged_fingerprint["files"].pop()
    forged_fingerprint["sha256"] = _digest(
        {key: value for key, value in forged_fingerprint.items() if key != "sha256"}
    )
    forged_receipt = json.loads(submission.receipt_json)
    forged_receipt["producer_executable_fingerprint"] = forged_fingerprint
    forged_submission = _submission_with(submission, receipt=forged_receipt)
    report = verifier.compare_population_v2(
        inputs, forged_submission, producer_revision=verifier.PRODUCER_REVISION
    )
    assert report.status == "MISMATCH"
    assert any(item.artifact == "provenance" for item in report.mismatches)

    wrong_revision = verifier.compare_population_v2(inputs, submission, producer_revision="a" * 40)
    assert wrong_revision.status == "MISMATCH"
    assert any(item.path.endswith("producer_revision") for item in wrong_revision.mismatches)


def test_pinned_producer_fingerprint_rejects_forged_altered_and_incomplete_inventories() -> None:
    assert verifier._producer_fingerprint_is_verified(
        verifier.PRODUCER_REVISION, _PRODUCER_FINGERPRINT
    )
    assert not verifier._producer_fingerprint_is_verified("a" * 40, _PRODUCER_FINGERPRINT)

    altered = copy.deepcopy(_PRODUCER_FINGERPRINT)
    altered["files"][0]["sha256"] = "b" * 64
    altered["sha256"] = _digest({key: value for key, value in altered.items() if key != "sha256"})
    assert not verifier._producer_fingerprint_is_verified(verifier.PRODUCER_REVISION, altered)

    incomplete = copy.deepcopy(_PRODUCER_FINGERPRINT)
    incomplete["files"].pop()
    incomplete["sha256"] = _digest(
        {key: value for key, value in incomplete.items() if key != "sha256"}
    )
    assert not verifier._producer_fingerprint_is_verified(verifier.PRODUCER_REVISION, incomplete)

    self_hash_mismatch = copy.deepcopy(_PRODUCER_FINGERPRINT)
    self_hash_mismatch["files"][0]["sha256"] = "c" * 64
    assert not verifier._producer_fingerprint_is_verified(
        verifier.PRODUCER_REVISION, self_hash_mismatch
    )


def test_shuffled_inputs_preserve_canonical_order_and_missing_match_fails_closed() -> None:
    inputs = _fixture()
    baseline = verifier._derive(tuple(inputs))
    shuffled = verifier._derive(tuple(reversed(inputs)))
    assert shuffled.expected_manifest == baseline.expected_manifest
    assert shuffled.expected_candidates == baseline.expected_candidates
    assert shuffled.expected_census == baseline.expected_census
    assert shuffled.expected_truth == baseline.expected_truth
    assert verifier.derive_synthetic_population_v2(inputs[:-1]).status == "INVALID_INPUT"


def test_verifier_imports_no_producer_or_production_policy_modules() -> None:
    source_path = Path(verifier.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    assert all(not name.startswith("fpdbench.") for name in imports)
    assert not any(
        "population_producer_v2" in name
        or "eligibility.skillcorner" in name
        or "data_states.skillcorner" in name
        for name in imports
    )
