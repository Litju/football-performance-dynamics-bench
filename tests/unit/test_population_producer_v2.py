"""Synthetic raw frames only. No restricted source fixtures or second verifier."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    empirical_experiment_plan as plan,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    population_producer_v2 as p,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.evaluation_population import (
    truth_mask_sha256,
    truth_sha256,
    validate_evaluation_population_authority_v2_document,
)
from fpdbench.data_sources.skillcorner import canonical_bytes
from fpdbench.eligibility.skillcorner import BallPopulationQualificationStop


def synthetic_sources() -> tuple[p.PopulationMatchInputV2, ...]:
    """Wire fixtures are generated without invoking producer enumeration/eligibility."""
    sources = []
    for ids in plan.protocol_split_v2()["roles"].values():
        for match_id in ids:
            metadata = {
                "id": int(match_id),
                "home_team": {"id": 101},
                "away_team": {"id": 202},
                "pitch_length": 100,
                "pitch_width": 60,
                "match_periods": [{"period": 1, "start_frame": 100, "end_frame": 186}],
                "players": [
                    {
                        "id": player_id,
                        "team_id": 101 if player_id < 1009 else 202,
                        "playing_time": {
                            "by_period": [
                                {"name": "period_1", "start_frame": 100, "end_frame": 186}
                            ]
                        },
                    }
                    for player_id in range(1001, 1017)
                ],
            }
            frames = [
                {
                    "frame": frame,
                    "timestamp": f"00:00:{frame // 10:02d}.{frame % 10}0",
                    "period": 1,
                    "ball_data": {"x": 0, "y": 0, "z": None, "is_detected": True},
                    "possession": None,
                    "image_corners_projection": {"synthetic": True},
                    "player_data": [
                        {
                            "player_id": player_id,
                            "x": player_id % 20 + offset / 100,
                            "y": player_id % 10 - 5.0,
                            "is_detected": True,
                        }
                        for player_id in range(1001, 1017)
                    ],
                }
                for offset, frame in enumerate(range(100, 186, 2))
            ]
            sources.append(
                p.PopulationMatchInputV2(
                    match_id,
                    canonical_bytes(metadata),
                    _lines(frames),
                    canonical_bytes([{"period": 1, "frame_start": 100, "frame_end": 186}]),
                )
            )
    return tuple(sources)


def complete_10hz_sources(
    sources: tuple[p.PopulationMatchInputV2, ...],
) -> tuple[p.PopulationMatchInputV2, ...]:
    complete = []
    for source in sources:
        frames = _rows(source.tracking_jsonl)
        raw_frames = []
        for frame in frames:
            raw_frames.append(frame)
            odd_frame = copy.deepcopy(frame)
            odd_frame["frame"] += 1
            odd_frame["timestamp"] = (
                f"00:00:{odd_frame['frame'] // 10:02d}.{odd_frame['frame'] % 10}0"
            )
            odd_frame["ball_data"]["x"] = 777.0
            for player in odd_frame["player_data"]:
                player["x"] = 777.0
            raw_frames.append(odd_frame)
        complete.append(replace(source, tracking_jsonl=_lines(raw_frames)))
    return tuple(complete)


def _lines(values) -> bytes:
    return b"".join(canonical_bytes(value) + b"\n" for value in values)


def _rows(payload):
    return [json.loads(line) for line in payload.splitlines()]


def _changed(sources, frames):
    return (replace(sources[0], tracking_jsonl=_lines(frames)), *sources[1:])


@pytest.fixture(scope="module")
def sources():
    return synthetic_sources()


@pytest.fixture(scope="module")
def submission(sources):
    return p.produce_population_draft_v2(sources, input_kind="synthetic")


@pytest.fixture(scope="module")
def raw_10hz_sources(sources):
    return complete_10hz_sources(sources)


@pytest.fixture(scope="module")
def raw_10hz_submission(raw_10hz_sources):
    return p.produce_population_draft_v2(raw_10hz_sources, input_kind="synthetic")


def test_complete_census_and_canonical_order(sources, submission):
    manifest = json.loads(submission.manifest_json)
    receipt = json.loads(submission.receipt_json)
    assert manifest["candidate_window_count"] == 20 * 3
    assert manifest["eligible_window_count"] == 20 * 3
    roles = plan.protocol_split_v2()["roles"]
    match_ids = [match_id for ids in roles.values() for match_id in ids]
    assert [match["match_id"] for match in manifest["matches"]] == match_ids
    assert [count["role"] for count in receipt["match_counts"]].count("training") == 12
    assert [count["role"] for count in receipt["match_counts"]].count("validation") == 4
    assert [count["role"] for count in receipt["match_counts"]].count("evaluation") == 4
    for count in receipt["match_counts"]:
        assert count["candidate_window_count"] == 3
        assert count["eligible_window_count"] == count["scoreable_window_count"] == 3
        assert count["excluded_window_count"] == 0
        assert count["diagnostic_origin_count"] == 43
        assert count["diagnostic_excluded_window_count"] == 40
        assert count["scoreable_scene_count"] == count["directed_scene_count"] == 6
    for match in manifest["matches"]:
        assert [w["origin_sample_id"] for w in match["windows"]] == [
            "period_1/sample_75",
            "period_1/sample_76",
            "period_1/sample_77",
        ]
    reversed_submission = p.produce_population_draft_v2(
        tuple(reversed(sources)), input_kind="synthetic"
    )
    assert reversed_submission == submission
    candidates = _rows(submission.candidates_jsonl)
    diagnostics = _rows(submission.diagnostic_census_jsonl)
    assert len(candidates) == manifest["candidate_window_count"] == 60
    assert len(diagnostics) == receipt["diagnostic_origin_census_count"] == 20 * 43
    assert [row["origin_sample_id"] for row in candidates[:3]] == [
        "period_1/sample_75",
        "period_1/sample_76",
        "period_1/sample_77",
    ]
    assert [row["origin_sample_id"] for row in diagnostics[:43]][::42] == [
        "period_1/sample_50",
        "period_1/sample_92",
    ]
    assert not diagnostics[0]["diagnostic"]["candidate_rules_pass"]
    assert not diagnostics[42]["diagnostic"]["candidate_rules_pass"]
    expected_origins = [
        {"match_id": match_id, "origin_sample_id": f"period_1/sample_{sample}"}
        for match_id in match_ids
        for sample in (75, 76, 77)
    ]
    actual_origins = [
        {"match_id": row["match_id"], "origin_sample_id": row["origin_sample_id"]}
        for row in candidates
    ]
    assert actual_origins == expected_origins
    digest = hashlib.sha256(canonical_bytes(expected_origins)).hexdigest()
    assert manifest["candidate_origin_population_sha256"] == digest
    assert receipt["candidate_origin_population_sha256"] == digest
    for count, match_id in zip(receipt["match_counts"], match_ids, strict=True):
        match_origins = [origin for origin in expected_origins if origin["match_id"] == match_id]
        assert count["candidate_origin_population_sha256"] == hashlib.sha256(
            canonical_bytes(match_origins)
        ).hexdigest()
        match_diagnostics = [
            row for row in diagnostics if row["match_id"] == match_id
        ]
        diagnostic_origins = [
            {"match_id": match_id, "origin_sample_id": f"period_1/sample_{sample}"}
            for sample in range(50, 93)
        ]
        assert [
            {"match_id": row["match_id"], "origin_sample_id": row["origin_sample_id"]}
            for row in match_diagnostics
        ] == diagnostic_origins
        assert count["diagnostic_origin_census_sha256"] == hashlib.sha256(
            canonical_bytes(diagnostic_origins)
        ).hexdigest()
    assert receipt["diagnostic_origin_census_sha256"] == hashlib.sha256(
        canonical_bytes(
            [
                {"match_id": row["match_id"], "origin_sample_id": row["origin_sample_id"]}
                for row in diagnostics
            ]
        )
    ).hexdigest()


def test_full_10hz_stream_retains_global_even_frames_and_exact_counts(
    sources, submission, raw_10hz_sources, raw_10hz_submission
):
    source_frames = _rows(raw_10hz_sources[0].tracking_jsonl)
    assert [frame["frame"] for frame in source_frames] == list(range(100, 186))
    assert all(frame["ball_data"]["x"] == 777.0 for frame in source_frames if frame["frame"] % 2)
    assert raw_10hz_submission.manifest_json == submission.manifest_json
    assert raw_10hz_submission.candidates_jsonl == submission.candidates_jsonl
    assert raw_10hz_submission.truth_jsonl == submission.truth_jsonl
    full_receipt = json.loads(raw_10hz_submission.receipt_json)
    retained_only_receipt = json.loads(submission.receipt_json)
    for actual, expected in zip(
        full_receipt["input_receipts"],
        retained_only_receipt["input_receipts"],
        strict=True,
    ):
        assert actual["source_frame_count"] == 86
        assert actual["retained_sample_count"] == 43
        assert actual["retained_samples_sha256"] == expected["retained_samples_sha256"]


def test_raw_frame_gaps_preserve_or_block_exactly(raw_10hz_sources, raw_10hz_submission):
    full_receipt = json.loads(raw_10hz_submission.receipt_json)
    odd_gap = [
        frame
        for frame in _rows(raw_10hz_sources[0].tracking_jsonl)
        if frame["frame"] != 101
    ]
    odd_gap_submission = p.produce_population_draft_v2(
        _changed(raw_10hz_sources, odd_gap), input_kind="synthetic"
    )
    odd_gap_receipt = json.loads(odd_gap_submission.receipt_json)
    odd_gap_input = odd_gap_receipt["input_receipts"][0]
    assert odd_gap_input["source_frame_count"] == 85
    assert odd_gap_input["retained_sample_count"] == 43
    assert odd_gap_input["retained_samples_sha256"] == full_receipt["input_receipts"][0][
        "retained_samples_sha256"
    ]
    assert odd_gap_submission.manifest_json == raw_10hz_submission.manifest_json
    assert odd_gap_submission.candidates_jsonl == raw_10hz_submission.candidates_jsonl
    assert odd_gap_submission.truth_jsonl == raw_10hz_submission.truth_jsonl

    even_gap = [
        frame
        for frame in _rows(raw_10hz_sources[0].tracking_jsonl)
        if frame["frame"] != 160
    ]
    with pytest.raises(p.IncompletePopulationV2) as error:
        p.produce_population_draft_v2(_changed(raw_10hz_sources, even_gap), input_kind="synthetic")
    incomplete = json.loads(error.value.receipt_json)
    first_match = incomplete["match_counts"][0]
    first_input = incomplete["input_receipts"][0]
    assert first_input["source_frame_count"] == 85
    assert first_input["retained_sample_count"] == 42
    assert first_match["candidate_window_count"] == 0
    assert first_match["diagnostic_origin_count"] == 43
    assert incomplete["status"] == "INCOMPLETE"
    assert incomplete["source_byte_qualified"] is False
    assert "population_manifest_sha256" not in incomplete


@pytest.mark.parametrize("mutation", ["duplicate", "timestamp"])
def test_raw_odd_frame_integrity_errors_fail_closed(raw_10hz_sources, mutation):
    frames = _rows(raw_10hz_sources[0].tracking_jsonl)
    if mutation == "duplicate":
        duplicate_index = next(index for index, frame in enumerate(frames) if frame["frame"] == 121)
        frames.insert(duplicate_index + 1, copy.deepcopy(frames[duplicate_index]))
    else:
        odd_frame = next(frame for frame in frames if frame["frame"] == 121)
        odd_frame["timestamp"] = "00:00:12.20"
    with pytest.raises(ValueError):
        p.produce_population_draft_v2(
            _changed(raw_10hz_sources, frames), input_kind="synthetic"
        )


def test_nonzero_physical_truth_fixed_panels_common_masks_and_bindings(submission):
    manifest = json.loads(submission.manifest_json)
    authority = validate_evaluation_population_authority_v2_document(manifest)
    assert not authority.empirically_qualified
    for truth in _rows(submission.truth_jsonl):
        assert len(truth["absolute_xy"]) == len(truth["origin_relative_displacement"]) == 15
        assert len(truth["player_ids"]) == 8
        assert truth["player_ids"] == sorted(truth["player_ids"], key=int)
        assert all(len(row) == 8 for row in truth["absolute_xy"])
        assert truth["origin_xy"][0] != [0, 0]
        for xy_row, delta_row, mask in zip(
            truth["absolute_xy"],
            truth["origin_relative_displacement"],
            truth["truth_mask"],
            strict=True,
        ):
            for xy, delta, anchor, valid in zip(
                xy_row,
                delta_row,
                truth["origin_xy"],
                mask,
                strict=True,
            ):
                assert valid == (xy is not None) == (delta is not None)
                if valid:
                    assert all(
                        math.isclose(d + o, x) for d, o, x in zip(delta, anchor, xy, strict=True)
                    )
        assert truth["absolute_xy_truth_sha256"] == truth_sha256(
            truth["absolute_xy"], target_representation="absolute_xy"
        )
        assert truth["displacement_truth_sha256"] == truth_sha256(
            truth["origin_relative_displacement"],
            target_representation="origin_relative_displacement",
        )
        assert truth_mask_sha256(truth["absolute_xy"]) == truth["truth_mask_sha256"]
        assert (
            truth_mask_sha256(truth["origin_relative_displacement"]) == truth["truth_mask_sha256"]
        )
    receipt = json.loads(submission.receipt_json)
    digest = receipt.pop("receipt_sha256")
    assert digest == hashlib.sha256(canonical_bytes(receipt)).hexdigest()
    assert (
        receipt["candidates_jsonl_sha256"]
        == hashlib.sha256(submission.candidates_jsonl).hexdigest()
    )
    assert receipt["diagnostic_census_jsonl_sha256"] == hashlib.sha256(
        submission.diagnostic_census_jsonl
    ).hexdigest()
    assert receipt["truth_jsonl_sha256"] == hashlib.sha256(submission.truth_jsonl).hexdigest()
    assert receipt["source_byte_qualified"] is False
    assert receipt["independent_verification"] == "NOT_PERFORMED"
    assert submission.status == "UNQUALIFIED"
    with pytest.raises(FrozenInstanceError):
        submission.manifest_json = b"fake"
    with pytest.raises(ValueError, match="independent"):
        submission.require_empirical_qualification()
    with pytest.raises(ValueError, match="independently verified"):
        authority.require_empirical_qualification()


def test_receipt_fingerprints_every_production_package_file(submission):
    receipt = json.loads(submission.receipt_json)
    fingerprint = receipt["producer_executable_fingerprint"]
    package_root = Path(p.__file__).resolve().parents[2]
    expected_files = [
        {
            "path": path.relative_to(package_root).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in sorted(
            (
                path
                for path in package_root.rglob("*")
                if path.is_file() and path.suffix in {".py", ".json"}
            ),
            key=lambda path: path.relative_to(package_root).as_posix(),
        )
    ]
    assert fingerprint["schema_id"] == "fpdbench.production-package-fingerprint"
    assert fingerprint["files"] == expected_files
    fingerprint_content = dict(fingerprint)
    fingerprint_digest = fingerprint_content.pop("sha256")
    assert fingerprint_digest == hashlib.sha256(canonical_bytes(fingerprint_content)).hexdigest()
    assert "producer_code_sha256" not in receipt
    receipt_digest = receipt.pop("receipt_sha256")
    assert receipt_digest == hashlib.sha256(canonical_bytes(receipt)).hexdigest()


@pytest.mark.parametrize("missing,eligible", [(2, 3), (3, 2)])
def test_exact_39_of_41_coverage(sources, missing, eligible):
    frames = _rows(sources[0].tracking_jsonl)
    for frame in frames[:missing]:
        frame["ball_data"] = {"x": None, "y": None, "z": None, "is_detected": None}
    result = p.produce_population_draft_v2(_changed(sources, frames), input_kind="synthetic")
    receipt = json.loads(result.receipt_json)
    assert receipt["match_counts"][0]["eligible_window_count"] == eligible
    decision = _rows(result.diagnostic_census_jsonl)[25]["diagnostic"]
    assert decision["candidate_rules_pass"] == (missing == 2)
    assert decision["quality"]["ball_observations"]["valid_position_count"] == 41 - missing


def test_null_origin_excludes_without_dropping_other_candidates(sources):
    frames = _rows(sources[0].tracking_jsonl)
    frames[25]["ball_data"] = {"x": None, "y": None, "z": None, "is_detected": None}
    result = p.produce_population_draft_v2(_changed(sources, frames), input_kind="synthetic")
    assert json.loads(result.receipt_json)["match_counts"][0]["eligible_window_count"] == 2
    first = _rows(result.diagnostic_census_jsonl)[25]["diagnostic"]
    assert "BALL_MISSING_AT_ORIGIN" in {r["code"] for r in first["exclusion_reasons"]}


def test_drift_outside_every_candidate_support_stops_before_decisions(sources, monkeypatch):
    frames = _rows(sources[-1].tracking_jsonl)
    outside = copy.deepcopy(frames[0])
    outside.update(frame=0, timestamp="00:00:00.00", period=None)
    outside["ball_data"]["is_detected"] = None
    changed = (*sources[:-1], replace(sources[-1], tracking_jsonl=_lines([outside, *frames])))

    def forbidden(*args, **kwargs):
        pytest.fail("candidate evaluation happened before the source-wide drift stop")

    monkeypatch.setattr(p, "diagnose_skillcorner_window_v2", forbidden)
    with pytest.raises(BallPopulationQualificationStop):
        p.produce_population_draft_v2(changed, input_kind="synthetic")


def test_missing_origin_keeps_full_candidate_grid_and_fails_incomplete(sources):
    frames = _rows(sources[0].tracking_jsonl)
    del frames[25]
    with pytest.raises(p.IncompletePopulationV2) as error:
        p.produce_population_draft_v2(_changed(sources, frames), input_kind="synthetic")
    receipt = json.loads(error.value.receipt_json)
    first = receipt["match_counts"][0]
    assert first["candidate_window_count"] == 0
    assert first["diagnostic_origin_count"] == 43
    assert first["eligible_window_count"] == first["scoreable_window_count"] == 0
    assert first["exclusion_window_counts"] == {}
    assert first["diagnostic_exclusion_window_counts"]["TEMPORAL_GAP"] > 0
    assert receipt["diagnostic_origin_census_count"] == 20 * 43
    match_ids = [match_id for ids in plan.protocol_split_v2()["roles"].values() for match_id in ids]
    expected_origins = [
        {"match_id": match_id, "origin_sample_id": f"period_1/sample_{sample}"}
        for match_id in match_ids[1:]
        for sample in (75, 76, 77)
    ]
    assert receipt["candidate_origin_population_sha256"] == hashlib.sha256(
        canonical_bytes(expected_origins)
    ).hexdigest()
    assert receipt["status"] == "INCOMPLETE"
    assert "population_manifest_sha256" not in receipt


def test_incomplete_support_stays_in_diagnostic_census(sources):
    frames = _rows(sources[0].tracking_jsonl)
    del frames[0]
    result = p.produce_population_draft_v2(_changed(sources, frames), input_kind="synthetic")
    receipt = json.loads(result.receipt_json)
    first = receipt["match_counts"][0]
    assert first["candidate_window_count"] == 2
    assert first["eligible_window_count"] == 2
    assert first["diagnostic_origin_count"] == 43
    assert first["diagnostic_excluded_window_count"] == 41
    candidates = [
        row
        for row in _rows(result.candidates_jsonl)
        if row["match_id"] == sources[0].match_id
    ]
    diagnostics = [
        row
        for row in _rows(result.diagnostic_census_jsonl)
        if row["match_id"] == sources[0].match_id
    ]
    assert [row["origin_sample_id"] for row in candidates] == [
        "period_1/sample_76",
        "period_1/sample_77",
    ]
    assert diagnostics[0]["origin_sample_id"] == "period_1/sample_50"
    assert not diagnostics[0]["diagnostic"]["candidate_rules_pass"]


def test_partial_truth_false_detection_and_no_future_entrant(sources):
    frames = _rows(sources[0].tracking_jsonl)
    # One future target has a partial coordinate; remaining targets keep the scene scoreable.
    frames[40]["player_data"][0]["x"] = None
    for frame in frames:
        frame["player_data"][1]["is_detected"] = False
    result = p.produce_population_draft_v2(_changed(sources, frames), input_kind="synthetic")
    home = _rows(result.truth_jsonl)[0]
    assert home["absolute_xy"][-1][0] is None
    assert home["origin_relative_displacement"][-1][0] is None
    assert home["truth_mask"][-1][0] is False
    assert home["absolute_xy"][-1][1] is not None
    assert home["scoreable"] is True


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_match",
        "duplicate_match",
        "empty",
        "pointer",
        "duplicate_json",
        "bad_phase",
        "wrong_id",
        "nonfinite",
    ],
)
def test_incomplete_or_malformed_input_fails_closed(sources, mutation):
    changed = sources
    if mutation == "missing_match":
        changed = sources[:-1]
    elif mutation == "duplicate_match":
        changed = (sources[0], *sources[:-1])
    elif mutation == "empty":
        changed = (replace(sources[0], tracking_jsonl=b""), *sources[1:])
    elif mutation == "pointer":
        changed = (
            replace(sources[0], tracking_jsonl=b"version https://git-lfs.github.com/spec/v1"),
            *sources[1:],
        )
    elif mutation == "duplicate_json":
        changed = (replace(sources[0], metadata_json=b'{"id":1,"id":2}'), *sources[1:])
    elif mutation == "bad_phase":
        changed = (replace(sources[0], phase_intervals_json=b'[{"period":true}]'), *sources[1:])
    elif mutation == "wrong_id":
        changed = (replace(sources[0], metadata_json=b'{"id":1}'), *sources[1:])
    elif mutation == "nonfinite":
        changed = (replace(sources[0], metadata_json=b'{"id":NaN}'), *sources[1:])
    with pytest.raises(ValueError):
        p.produce_population_draft_v2(changed, input_kind="synthetic")


def test_real_domain_rejected_before_parsing(sources):
    with pytest.raises(ValueError, match="not authorized"):
        p.produce_population_draft_v2(sources, input_kind="restricted")


@pytest.mark.parametrize("replace_away", [False, True])
def test_future_replacements_never_join_origin_panels_and_scoreability_is_explicit(
    sources, replace_away
):
    metadata = json.loads(sources[0].metadata_json)
    frames = _rows(sources[0].tracking_jsonl)
    old_players = copy.deepcopy(metadata["players"])
    replaced_ids = {
        player["id"] for player in old_players if replace_away or player["team_id"] == 101
    }
    for player in metadata["players"]:
        if player["id"] in replaced_ids:
            player["playing_time"]["by_period"][0]["end_frame"] = 179
    for player in old_players:
        if player["id"] in replaced_ids:
            player["id"] += 1000
            player["playing_time"]["by_period"][0]["start_frame"] = 180
            metadata["players"].append(player)
    for frame in frames[40:]:
        for player in frame["player_data"]:
            if player["player_id"] in replaced_ids:
                player["player_id"] += 1000
    changed = (
        replace(sources[0], metadata_json=canonical_bytes(metadata), tracking_jsonl=_lines(frames)),
        *sources[1:],
    )
    if replace_away:
        with pytest.raises(p.IncompletePopulationV2) as error:
            p.produce_population_draft_v2(changed, input_kind="synthetic")
        count = json.loads(error.value.receipt_json)["match_counts"][0]
        assert count["eligible_window_count"] == 3
        assert count["scoreable_window_count"] == count["scoreable_scene_count"] == 0
    else:
        result = p.produce_population_draft_v2(changed, input_kind="synthetic")
        first_count = json.loads(result.receipt_json)["match_counts"][0]
        assert first_count["eligible_window_count"] == first_count["scoreable_window_count"] == 3
        assert first_count["scoreable_scene_count"] == 3
        home = _rows(result.truth_jsonl)[0]
        assert home["player_ids"] == [str(i) for i in range(1001, 1009)]
        assert home["absolute_xy"][-1] == [None] * 8
        assert home["unscoreable_reason"] == "NO_FINAL_TARGET"


def test_two_periods_enumerated_without_cross_period_eligible_windows(sources):
    metadata = json.loads(sources[0].metadata_json)
    second_period = {"period": 2, "start_frame": 300, "end_frame": 386}
    metadata["match_periods"].append(second_period)
    for player in metadata["players"]:
        player["playing_time"]["by_period"].append(
            {"name": "period_2", "start_frame": 300, "end_frame": 386}
        )
    frames = _rows(sources[0].tracking_jsonl)
    second = copy.deepcopy(frames)
    for frame in second:
        frame["frame"] += 200
        frame["period"] = 2
        frame["timestamp"] = f"00:00:{frame['frame'] // 10:02d}.{frame['frame'] % 10}0"
    changed = (
        replace(
            sources[0],
            metadata_json=canonical_bytes(metadata),
            tracking_jsonl=_lines(frames + second),
            phase_intervals_json=canonical_bytes(
                [
                    {"period": 1, "frame_start": 100, "frame_end": 186},
                    {"period": 2, "frame_start": 300, "frame_end": 386},
                ]
            ),
        ),
        *sources[1:],
    )
    result = p.produce_population_draft_v2(changed, input_kind="synthetic")
    first = json.loads(result.manifest_json)["matches"][0]
    assert [w["origin_sample_id"] for w in first["windows"]] == [
        "period_1/sample_75",
        "period_1/sample_76",
        "period_1/sample_77",
        "period_2/sample_175",
        "period_2/sample_176",
        "period_2/sample_177",
    ]
    first_count = json.loads(result.receipt_json)["match_counts"][0]
    assert first_count["candidate_window_count"] == 6
    assert first_count["diagnostic_origin_count"] == 86
