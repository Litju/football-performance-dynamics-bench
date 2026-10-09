import copy
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest

from fpdbench.data_states.skillcorner import (
    compute_data_state_hash,
    iter_skillcorner_5hz,
    load_manifest,
    serialize_sample,
    validate_manifest,
)
from fpdbench.validation.artifacts import validate_artifacts


def _metadata() -> dict[str, object]:
    return {
        # Synthetic frames use an in-release match ID to exercise the release boundary.
        "id": 2017461,
        "home_team": {"id": 101},
        "away_team": {"id": 202},
        "pitch_length": 103.5,
        "pitch_width": 67.5,
        "players": [
            {"id": 1001, "team_id": 101},
            {"id": 2002, "team_id": 202},
        ],
    }


def _player(
    player_id: int = 1001,
    *,
    x: float = -23.75,
    y: float = 17.25,
    detected: bool = False,
) -> dict[str, object]:
    return {"player_id": player_id, "x": x, "y": y, "is_detected": detected}


def _frame(
    source_frame: int,
    timestamp: str | None,
    *,
    period: int | None = 1,
    players: list[dict[str, object]] | None = None,
    ball: dict[str, object] | None = None,
    possession: dict[str, object] | None = None,
) -> dict[str, object]:
    if ball is None and source_frame % 4 != 2:
        ball = {"x": 25.125, "y": -12.625, "z": 2.5, "is_detected": True}
    return {
        "frame": source_frame,
        "timestamp": timestamp,
        "period": period,
        "ball_data": ball,
        "possession": possession,
        "image_corners_projection": {"synthetic": True},
        "player_data": players if players is not None else [_player()],
    }


def _samples(
    frames: list[dict[str, object]], *, release_id: str | None = None
) -> list[dict[str, object]]:
    manifest = load_manifest()
    return list(
        iter_skillcorner_5hz(
            frames,
            _metadata(),
            source_release_id=release_id or cast(str, manifest["source_release_id"]),
        )
    )


def _rehash(manifest: dict[str, object]) -> None:
    state = cast(dict[str, object], manifest["scientific_state"])
    manifest["data_state_hash"] = compute_data_state_hash(state)


def test_pinned_manifest_hash_and_source_release_are_valid() -> None:
    manifest = load_manifest()
    assert validate_manifest(manifest) == ()
    original_hash = manifest["data_state_hash"]

    described_change = copy.deepcopy(manifest)
    described_change["description"] = "documentation-only wording change"
    described_change["local_path"] = "/tmp/skillcorner"
    described_change["retrieved_at"] = "2099-01-01T00:00:00Z"
    described_change["hostname"] = "synthetic-local-host"
    assert described_change["data_state_hash"] == original_hash
    assert validate_manifest(described_change) == ()

    wrong_source = copy.deepcopy(manifest)
    wrong_source["source_release_id"] = "skillcorner_open_data_v1:sha256:" + "0" * 64
    assert any("source_release_id" in error for error in validate_manifest(wrong_source))


@pytest.mark.parametrize("missing", ["section", "field_contract", "field_entry"])
def test_rehashed_manifest_with_missing_contract_fails(missing: str) -> None:
    changed = copy.deepcopy(load_manifest())
    state = cast(dict[str, object], changed["scientific_state"])
    if missing == "section":
        del state["no_future_leakage"]
    elif missing == "field_contract":
        del state["field_contract"]
    else:
        field_contract = cast(dict[str, object], state["field_contract"])
        canonical_values = cast(list[str], field_contract["canonical_measurement_values"])
        canonical_values.remove("tracking.player_data[].is_detected -> players[].is_detected")
    _rehash(changed)

    assert validate_manifest(changed)


def test_rehashed_manifest_with_wrong_section_type_fails() -> None:
    changed = copy.deepcopy(load_manifest())
    state = cast(dict[str, object], changed["scientific_state"])
    entity_schema = cast(dict[str, object], state["entity_schema"])
    entity_schema["player"] = ["unsupported shape"]
    _rehash(changed)

    assert any(
        "entity_schema.player has an unsupported type" in error
        for error in validate_manifest(changed)
    )


@pytest.mark.parametrize(
    ("section_name", "field", "value", "error"),
    [
        (
            "entity_schema",
            "player",
            "player_id is global across matches",
            "entity_schema.player",
        ),
        (
            "entity_schema",
            "possession",
            "discard possession",
            "entity_schema.possession",
        ),
        (
            "entity_schema",
            "team_orientation",
            "rotate each team to attack in +x",
            "entity_schema.team_orientation",
        ),
        ("spatial_semantics", "coordinate_units", "feet", "spatial_semantics.coordinate_units"),
        ("spatial_semantics", "origin", "southwest corner", "spatial_semantics.origin"),
        (
            "spatial_semantics",
            "attack_direction_normalization",
            "normalize each team to attack in +x",
            "spatial_semantics.attack_direction_normalization",
        ),
        ("temporal_sampling", "source_frequency_hz", 25, "temporal_sampling.source_frequency_hz"),
        (
            "temporal_sampling",
            "sampling_frame_remainder",
            1,
            "temporal_sampling.sampling_frame_remainder",
        ),
        ("transform", "transform_id", "unsupported_transform", "transform.transform_id"),
        (
            "transform",
            "transform_version",
            "2.0.0",
            "transform.transform_version",
        ),
        ("serialization", "json", "unordered noncanonical JSON", "serialization.json"),
    ],
)
def test_rehashed_manifest_with_unsupported_scientific_semantics_fails(
    section_name: str, field: str, value: object, error: str
) -> None:
    changed = copy.deepcopy(load_manifest())
    state = cast(dict[str, object], changed["scientific_state"])
    section = cast(dict[str, object], state[section_name])
    section[field] = value
    _rehash(changed)

    assert any(error in item for item in validate_manifest(changed))


def test_rehashed_source_release_mismatch_fails() -> None:
    changed = copy.deepcopy(load_manifest())
    wrong_hash = "0" * 64
    wrong_release_id = f"skillcorner_open_data_v1:sha256:{wrong_hash}"
    changed["source_release_id"] = wrong_release_id
    changed["source_release_hash"] = wrong_hash
    state = cast(dict[str, object], changed["scientific_state"])
    source = cast(dict[str, object], state["source"])
    source["source_release_id"] = wrong_release_id
    source["source_release_hash"] = wrong_hash
    _rehash(changed)

    assert any("pinned source authority" in error for error in validate_manifest(changed))


def test_exact_even_frame_sampling_period_boundary_and_metric_entities() -> None:
    frames = [
        _frame(
            100,
            "00:00:10.00",
            players=[_player(2002, x=31.625, y=-16.875, detected=True), _player()],
            possession={"group": None, "player_id": None},
        ),
        _frame(101, "00:00:10.10"),
        _frame(102, "00:00:10.20", players=[], ball=None, possession=None),
        _frame(201, "00:00:00.10", period=2),
        _frame(202, "00:00:00.20", period=2),
        _frame(203, "00:00:00.30", period=2),
    ]

    samples = _samples(frames)
    assert [sample["source_frame"] for sample in samples] == [100, 102, 202]
    assert [sample["canonical_sample_index"] for sample in samples] == [50, 51, 101]
    assert [sample["period"] for sample in samples] == [1, 1, 2]
    assert [sample["timestamp_deciseconds"] for sample in samples] == [100, 102, 2]
    assert samples[0]["pitch_length_m"] == 103.5
    assert samples[0]["pitch_width_m"] == 67.5

    players = cast(list[dict[str, object]], samples[0]["players"])
    assert [player["player_id"] for player in players] == [1001, 2002]
    assert players[0] == {
        "player_id": 1001,
        "team_id": 101,
        "group": "home",
        "x_m": -23.75,
        "y_m": 17.25,
        "is_detected": False,
    }
    assert players[1]["team_id"] == 202
    assert players[1]["group"] == "away"
    assert players[1]["x_m"] == 31.625
    assert players[1]["y_m"] == -16.875
    assert players[1]["is_detected"] is True
    assert samples[0]["possession"] == {"group": None, "player_id": None}
    assert samples[0]["ball"] == {
        "x_m": 25.125,
        "y_m": -12.625,
        "is_detected": True,
    }
    assert samples[1]["ball"] is None
    assert samples[1]["possession"] is None
    assert samples[1]["players"] == []


@pytest.mark.parametrize("group", ["home team", "away team"])
def test_possession_group_is_preserved_from_source(group: str) -> None:
    sample = _samples([_frame(100, "00:00:10.00", possession={"group": group, "player_id": 1001})])[
        0
    ]
    assert sample["possession"] == {"group": group, "player_id": 1001}


@pytest.mark.parametrize("group", ["home", "away", "unknown", 1])
def test_unsupported_possession_group_fails(group: object) -> None:
    with pytest.raises(ValueError, match="possession group"):
        _samples([_frame(100, "00:00:10.00", possession={"group": group, "player_id": None})])


@pytest.mark.parametrize("player_id", [0, -1, True])
def test_possession_player_id_remains_a_positive_integer(player_id: object) -> None:
    with pytest.raises(ValueError, match="possession player_id"):
        _samples(
            [
                _frame(
                    100,
                    "00:00:10.00",
                    possession={"group": "home team", "player_id": player_id},
                )
            ]
        )


def test_missing_frames_leave_index_gaps_without_synthesis() -> None:
    samples = _samples(
        [
            _frame(10, "00:00:01.00"),
            _frame(13, "00:00:01.30"),
            _frame(14, "00:00:01.40"),
        ]
    )
    assert [sample["source_frame"] for sample in samples] == [10, 14]
    assert [sample["canonical_sample_index"] for sample in samples] == [5, 7]


@pytest.mark.parametrize(
    ("frames", "message"),
    [
        ([_frame(10, "00:00:01.00"), _frame(10, "00:00:01.00")], "duplicate"),
        (
            [_frame(10, "00:00:01.00"), _frame(12, "00:00:01.20"), _frame(11, "00:00:01.10")],
            "non-monotonic",
        ),
        ([_frame(10, "00:00:01.00"), _frame(12, "00:00:01.30")], "frame/timestamp mismatch"),
    ],
)
def test_bad_source_frame_sequence_fails(frames: list[dict[str, object]], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _samples(frames)


def test_wrong_source_release_identity_fails_before_reading_frames() -> None:
    def unread() -> Iterator[dict[str, object]]:
        raise AssertionError("source frames must not be read")
        yield {}

    with pytest.raises(ValueError, match="source release identity"):
        list(iter_skillcorner_5hz(unread(), _metadata(), source_release_id="wrong-release"))


def test_transform_reads_no_future_sample_to_emit_current_sample() -> None:
    def one_then_fail() -> Iterator[dict[str, object]]:
        yield _frame(100, "00:00:10.00")
        raise AssertionError("transform read a future source frame")

    manifest = load_manifest()
    result = iter_skillcorner_5hz(
        one_then_fail(),
        _metadata(),
        source_release_id=cast(str, manifest["source_release_id"]),
    )
    assert next(result)["source_frame"] == 100


def test_serialization_is_deterministic_and_ignores_excluded_projection() -> None:
    first = _frame(
        100,
        "00:00:10.00",
        players=[_player(2002, detected=True), _player()],
    )
    second = copy.deepcopy(first)
    cast(list[dict[str, object]], second["player_data"]).reverse()
    second["image_corners_projection"] = {"different": [1, 2, 3]}
    assert serialize_sample(_samples([first])[0]) == serialize_sample(_samples([second])[0])


def test_unsupported_sampling_change_also_changes_the_identity_hash() -> None:
    manifest = load_manifest()
    baseline = cast(str, manifest["data_state_hash"])
    changed = copy.deepcopy(manifest)
    state = cast(dict[str, object], changed["scientific_state"])
    temporal = cast(dict[str, object], state["temporal_sampling"])
    temporal["sampling_frame_remainder"] = 1
    _rehash(changed)
    assert changed["data_state_hash"] != baseline
    assert validate_manifest(changed)


def test_artifact_guard_rejects_canonical_row_payloads(tmp_path: Path) -> None:
    sample = _samples([_frame(100, "00:00:10.00")])[0]
    payload = tmp_path / "src" / "fpdbench" / "data_states" / "synthetic_rows.jsonl"
    payload.parent.mkdir(parents=True)
    payload.write_bytes(serialize_sample(sample) + b"\n")
    assert any(
        "data or checkpoint artifact is not allowed" in error
        for error in validate_artifacts(tmp_path)
    )
