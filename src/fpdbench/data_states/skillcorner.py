"""Canonical streaming SkillCorner 10 Hz to 5 Hz measurement transform."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import cast

from fpdbench.data_sources.skillcorner import (
    canonical_bytes,
)
from fpdbench.data_sources.skillcorner import (
    load_manifest as load_source_manifest,
)

MANIFEST_PATH = Path(__file__).with_name("skillcorner_5hz_v1.json")
_TIMESTAMP = re.compile(r"([0-9]+):([0-5][0-9]):([0-5][0-9])\.([0-9]{2})\Z")
_STATE_SECTION_TYPES: dict[str, dict[str, type[object]]] = {
    "entity_schema": dict.fromkeys(
        {"match", "period", "sample", "player", "ball", "possession", "team_orientation"},
        str,
    ),
    "field_contract": dict.fromkeys(
        {
            "canonical_measurement_values",
            "provenance_only",
            "retained_auxiliary_context",
            "excluded",
        },
        list,
    ),
    "identity": dict.fromkeys(
        {"schema_id", "schema_version", "data_state_id", "data_state_version"}, str
    ),
    "missing_values": dict.fromkeys(
        {"absent_player", "ball", "coordinates", "possession", "source_extrapolation"}, str
    ),
    "no_future_leakage": {
        "current_sample_only": str,
        "forbidden": list,
        "scope": str,
    },
    "numeric_representation": dict.fromkeys(
        {
            "coordinates_and_pitch_dimensions",
            "identifiers_and_indices",
            "timestamp",
            "z_coordinate",
        },
        str,
    ),
    "serialization": dict.fromkeys({"encoding", "hash", "json"}, str),
    "source": dict.fromkeys({"source_id", "source_release_id", "source_release_hash"}, str),
    "spatial_semantics": dict.fromkeys(
        {
            "attack_direction_normalization",
            "coordinate_units",
            "origin",
            "pitch_dimensions",
            "positive_axis_signs",
            "x_axis",
            "y_axis",
        },
        str,
    ),
    "temporal_sampling": {
        "canonical_frequency_hz": int,
        "canonical_sample_index": str,
        "duplicate_or_non_monotonic_frames": str,
        "frame_timestamp_consistency": str,
        "missing_source_frames": str,
        "parity_anchor": str,
        "period_boundary": str,
        "sampling_frame_modulus": int,
        "sampling_frame_remainder": int,
        "source_frame_resets_by_period": bool,
        "source_frequency_hz": int,
        "timestamp": str,
        "transform": str,
    },
    "transform": dict.fromkeys({"transform_id", "transform_version"}, str),
}
_SUPPORTED_FIELD_ITEMS: dict[str, frozenset[str]] = {
    "canonical_measurement_values": frozenset(
        {
            "tracking.frame -> source_frame",
            "tracking.period -> period",
            "tracking.timestamp -> timestamp_deciseconds",
            "tracking.player_data[].player_id -> players[].player_id",
            "tracking.player_data[].x/y -> players[].x_m/y_m",
            "tracking.player_data[].is_detected -> players[].is_detected",
            "tracking.ball_data.x/y -> ball.x_m/y_m",
            "tracking.ball_data.is_detected -> ball.is_detected",
            "match.id -> match_id",
            "match.pitch_length/pitch_width -> pitch_length_m/pitch_width_m",
            "match.home_team.id/match.away_team.id -> home_team_id/away_team_id",
        }
    ),
    "excluded": frozenset(
        {
            (
                "tracking.ball_data.z (the pinned source documentation does not establish "
                "its unit/reference)"
            ),
            "tracking.image_corners_projection payload",
            "dynamic_events.csv and phases_of_play.csv, including all event/phase labels",
            "all source fields not listed as canonical, auxiliary, or provenance-only",
        }
    ),
    "provenance_only": frozenset(
        {
            "pinned source release ID/hash",
            (
                "match.match_periods boundary metadata (not used to sample or select "
                "benchmark windows)"
            ),
            "source file paths and immutable byte identities bound by the source release",
        }
    ),
    "retained_auxiliary_context": frozenset(
        {
            "tracking.possession.group/player_id",
            "match.players[].id/team_id roster crosswalk used to assign canonical team/group",
        }
    ),
}
_SUPPORTED_STATE_VALUES: dict[str, dict[str, object]] = {
    "missing_values": {
        "absent_player": (
            "Remain absent from that sample; do not pad from the roster or forward-fill."
        ),
        "ball": (
            "Source null remains JSON null; an object with null coordinates remains an object "
            "with null coordinates."
        ),
        "coordinates": (
            "Explicit source null is preserved component-wise; NaN and infinity are rejected."
        ),
        "possession": "Source null remains JSON null; null player_id remains null.",
        "source_extrapolation": (
            "Preserve is_detected=false with the provider x/y values; do not filter or relabel it."
        ),
    },
    "no_future_leakage": {
        "current_sample_only": (
            "Every emitted positional, detection, ball, and possession value comes from that "
            "same retained source frame; static match metadata supplies only IDs and pitch "
            "dimensions."
        ),
        "forbidden": frozenset(
            {
                "future interpolation or smoothing",
                "FPD forward-fill or imputation",
                "event/phase labels attached to tracking samples",
                "future targets, opponent positions, or ball context",
            }
        ),
        "scope": (
            "Future conditional context and benchmark information boundaries are downstream "
            "decisions."
        ),
    },
    "numeric_representation": {
        "coordinates_and_pitch_dimensions": (
            "Python binary64 floats in meters, converted from source JSON numbers without "
            "rounding or normalization; finite values only, explicit null allowed where the "
            "source is null."
        ),
        "identifiers_and_indices": (
            "Nonnegative/positive provider identifiers and frame indices remain JSON "
            "integers; booleans are not accepted as integers."
        ),
        "timestamp": (
            "Parse HH:MM:SS.cc source strings to integer deciseconds; accept only source "
            "100 ms ticks; preserve null as null."
        ),
        "z_coordinate": (
            "Excluded because the pinned source documentation does not define its unit/reference."
        ),
    },
    "serialization": {
        "encoding": "UTF-8 without BOM or trailing newline.",
        "hash": (
            "SHA-256 over UTF-8 canonical JSON of scientific_state with sorted keys and "
            "compact separators; descriptive manifest fields are excluded."
        ),
        "json": (
            "Python JSON serialization with recursively sorted object keys, compact "
            "separators, ensure_ascii=false, allow_nan=false; players sorted by player_id; "
            "binary64 floats use Python's shortest round-trip decimal representation."
        ),
    },
    "spatial_semantics": {
        "attack_direction_normalization": "none; provider orientation is preserved",
        "coordinate_units": "meters (SI)",
        "origin": "pitch center",
        "pitch_dimensions": (
            "preserve match-specific pitch_length and pitch_width as metadata in meters"
        ),
        "positive_axis_signs": (
            "not specified by the pinned source documentation; preserve provider values unchanged"
        ),
        "x_axis": "pitch length axis",
        "y_axis": "pitch width axis",
    },
    "temporal_sampling": {
        "canonical_frequency_hz": 5,
        "canonical_sample_index": "source_frame // 2, on the global provider video-frame index",
        "duplicate_or_non_monotonic_frames": (
            "fail; source frame numbers must increase strictly across the match"
        ),
        "frame_timestamp_consistency": (
            "Within consecutive source rows with the same non-null period and non-null "
            "timestamps, timestamp_deciseconds delta must equal source_frame delta "
            "(one decisecond per 10 Hz source frame)."
        ),
        "missing_source_frames": (
            "Emit no synthetic sample; retain only observed even-numbered frames, leaving "
            "canonical_sample_index gaps where frames are absent."
        ),
        "parity_anchor": (
            "absolute source frame number; retain source_frame % 2 == 0. Parity does not "
            "restart at a period boundary."
        ),
        "period_boundary": (
            "Copy the source period. The global source frame and canonical index do not "
            "reset; timestamp continuity validation restarts at a period change."
        ),
        "sampling_frame_modulus": 2,
        "sampling_frame_remainder": 0,
        "source_frame_resets_by_period": False,
        "source_frequency_hz": 10,
        "timestamp": (
            "Copy the corresponding source row's match-clock time exactly as integer "
            "deciseconds; do not derive time from a neighboring sample."
        ),
        "transform": (
            "Direct selection of the source observation on even frames; no interpolation, "
            "smoothing, or averaging."
        ),
    },
    "transform": {
        "transform_id": "skillcorner_source_frame_even_10hz_to_5hz",
        "transform_version": "1.0.0",
    },
}


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object with string keys")
    typed_value = cast(Mapping[object, object], value)
    if not all(isinstance(key, str) for key in typed_value):
        raise ValueError(f"{label} must be an object with string keys")
    return cast(Mapping[str, object], typed_value)


def _exact_keys(value: Mapping[str, object], expected: set[str], label: str) -> None:
    if set(value) != expected:
        missing = sorted(expected - set(value))
        unexpected = sorted(set(value) - expected)
        raise ValueError(f"{label} fields differ from the pinned schema: {missing=}, {unexpected=}")


def _state_section(
    state: Mapping[str, object], name: str, errors: list[str]
) -> Mapping[str, object] | None:
    label = f"scientific_state.{name}"
    try:
        section = _mapping(state.get(name), label)
        _exact_keys(section, set(_STATE_SECTION_TYPES[name]), label)
    except ValueError as exc:
        errors.append(str(exc))
        return None
    for key, expected_type in _STATE_SECTION_TYPES[name].items():
        value = section.get(key)
        valid_type = type(value) is expected_type
        if valid_type and expected_type is list:
            valid_type = all(isinstance(item, str) for item in cast(list[object], value))
        if not valid_type:
            errors.append(f"{label}.{key} has an unsupported type")
        elif expected_type is str and not value:
            errors.append(f"{label}.{key} must not be empty")
    return section


def _validate_supported_values(
    sections: Mapping[str, Mapping[str, object]], errors: list[str]
) -> None:
    for key, expected_items in _SUPPORTED_FIELD_ITEMS.items():
        values = sections.get("field_contract", {}).get(key)
        valid = isinstance(values, list) and all(
            isinstance(value, str) for value in cast(list[object], values)
        )
        if valid:
            string_values = cast(list[str], values)
            valid = (
                len(string_values) == len(expected_items)
                and frozenset(string_values) == expected_items
            )
        if not valid:
            errors.append(f"unsupported scientific_state.field_contract.{key}")
    for section_name, expected_values in _SUPPORTED_STATE_VALUES.items():
        section = sections.get(section_name, {})
        for key, expected in expected_values.items():
            actual = section.get(key)
            if isinstance(expected, frozenset):
                valid = isinstance(actual, list) and all(
                    isinstance(value, str) for value in cast(list[object], actual)
                )
                if valid:
                    string_values = cast(list[str], actual)
                    expected_strings = cast(frozenset[str], expected)
                    valid = (
                        len(string_values) == len(expected_strings)
                        and frozenset(string_values) == expected_strings
                    )
            else:
                valid = actual == expected
            if not valid:
                errors.append(f"unsupported scientific_state.{section_name}.{key}")


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _finite_number(value: object, label: str, *, nullable: bool = False) -> float | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{label} must be a finite number" + (" or null" if nullable else ""))
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _timestamp_deciseconds(value: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("timestamp must be a string or null")
    match = _TIMESTAMP.fullmatch(value)
    if match is None:
        raise ValueError("timestamp must use HH:MM:SS.cc source format")
    hours, minutes, seconds, centiseconds = (int(part) for part in match.groups())
    if centiseconds % 10:
        raise ValueError("timestamp must have the source's 100 ms precision")
    return ((hours * 60 + minutes) * 60 + seconds) * 10 + centiseconds // 10


def compute_data_state_hash(scientific_state: Mapping[str, object]) -> str:
    """Hash only the canonical, load-bearing state definition."""
    return hashlib.sha256(canonical_bytes(dict(scientific_state))).hexdigest()


def load_manifest() -> dict[str, object]:
    value = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("data-state manifest must be a JSON object with string keys")
    typed_value = cast(dict[object, object], value)
    if not all(isinstance(key, str) for key in typed_value):
        raise ValueError("data-state manifest must be a JSON object with string keys")
    return cast(dict[str, object], typed_value)


def validate_manifest(manifest: Mapping[str, object]) -> tuple[str, ...]:
    errors: list[str] = []
    if manifest.get("schema_id") != "fpdbench.skillcorner-data-state":
        errors.append("unexpected data-state schema_id")
    if manifest.get("schema_version") != "1.0.0":
        errors.append("unsupported data-state schema_version")
    if manifest.get("data_state_id") != "skillcorner_5hz_v1":
        errors.append("unexpected data_state_id")
    if manifest.get("data_state_version") != "1.0.0":
        errors.append("unsupported data_state_version")

    source: Mapping[str, object] | None = None
    try:
        source = _mapping(load_source_manifest(), "pinned source authority")
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        errors.append(f"could not verify pinned source authority: {exc}")
    if source is not None:
        for field in ("source_id", "source_release_id", "source_release_hash"):
            if manifest.get(field) != source.get(field):
                errors.append(f"data-state {field} does not match the pinned source authority")

    sections: dict[str, Mapping[str, object]] = {}
    try:
        state = _mapping(manifest.get("scientific_state"), "scientific_state")
    except (ValueError, TypeError):
        errors.append("scientific_state must be an object with string keys")
        return tuple(errors)

    try:
        _exact_keys(state, set(_STATE_SECTION_TYPES), "scientific_state")
    except ValueError as exc:
        errors.append(str(exc))
    for section_name in _STATE_SECTION_TYPES:
        section = _state_section(state, section_name, errors)
        if section is not None:
            sections[section_name] = section

    _validate_supported_values(sections, errors)
    identity = sections.get("identity")
    if identity is not None:
        for field in ("schema_id", "schema_version", "data_state_id", "data_state_version"):
            if identity.get(field) != manifest.get(field):
                errors.append(f"scientific_state {field} does not match manifest")
    source_state = sections.get("source")
    if source_state is not None:
        for field in ("source_id", "source_release_id", "source_release_hash"):
            if source_state.get(field) != manifest.get(field):
                errors.append(f"scientific_state {field} does not match manifest")
    try:
        expected_hash = compute_data_state_hash(state)
    except (TypeError, ValueError):
        errors.append("scientific_state cannot be canonically serialized")
    else:
        if manifest.get("data_state_hash") != expected_hash:
            errors.append("data_state_hash does not match scientific_state")
    return tuple(errors)


def _match_context(
    metadata: Mapping[str, object],
) -> tuple[int, int, int, float, float, dict[int, int]]:
    match_id = _positive_int(metadata.get("id"), "match metadata id")
    home = _mapping(metadata.get("home_team"), "home_team")
    away = _mapping(metadata.get("away_team"), "away_team")
    home_team_id = _positive_int(home.get("id"), "home_team.id")
    away_team_id = _positive_int(away.get("id"), "away_team.id")
    if home_team_id == away_team_id:
        raise ValueError("home and away team IDs must differ")
    pitch_length = _finite_number(metadata.get("pitch_length"), "pitch_length")
    pitch_width = _finite_number(metadata.get("pitch_width"), "pitch_width")
    assert pitch_length is not None and pitch_width is not None
    if pitch_length <= 0 or pitch_width <= 0:
        raise ValueError("pitch dimensions must be positive")

    roster = metadata.get("players")
    if not isinstance(roster, list):
        raise ValueError("match metadata players must be an array")
    team_by_player: dict[int, int] = {}
    for value in cast(list[object], roster):
        player = _mapping(value, "match metadata player")
        player_id = _positive_int(player.get("id"), "match metadata player id")
        team_id = _positive_int(player.get("team_id"), "match metadata player team_id")
        if team_id not in {home_team_id, away_team_id}:
            raise ValueError(f"player {player_id} has a team outside the match")
        if player_id in team_by_player:
            raise ValueError(f"duplicate match metadata player id: {player_id}")
        team_by_player[player_id] = team_id
    return match_id, home_team_id, away_team_id, pitch_length, pitch_width, team_by_player


def _canonical_player(
    value: object,
    team_by_player: Mapping[int, int],
    home_team_id: int,
    away_team_id: int,
) -> dict[str, object]:
    player = _mapping(value, "player_data entry")
    _exact_keys(player, {"player_id", "x", "y", "is_detected"}, "player_data entry")
    player_id = _positive_int(player.get("player_id"), "player_id")
    team_id = team_by_player.get(player_id)
    if team_id is None:
        raise ValueError(f"player_id {player_id} is absent from the match roster")
    if team_id not in {home_team_id, away_team_id}:
        raise ValueError(f"player_id {player_id} maps to an unknown team")
    is_detected = player.get("is_detected")
    if not isinstance(is_detected, bool):
        raise ValueError("player is_detected must be boolean")
    return {
        "player_id": player_id,
        "team_id": team_id,
        "group": "home" if team_id == home_team_id else "away",
        "x_m": _finite_number(player.get("x"), "player x", nullable=True),
        "y_m": _finite_number(player.get("y"), "player y", nullable=True),
        "is_detected": is_detected,
    }


def _canonical_ball(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    ball = _mapping(value, "ball_data")
    _exact_keys(ball, {"x", "y", "z", "is_detected"}, "ball_data")
    is_detected = ball.get("is_detected")
    if not isinstance(is_detected, bool):
        raise ValueError("ball is_detected must be boolean")
    _finite_number(ball.get("z"), "ball z", nullable=True)
    return {
        "x_m": _finite_number(ball.get("x"), "ball x", nullable=True),
        "y_m": _finite_number(ball.get("y"), "ball y", nullable=True),
        "is_detected": is_detected,
    }


def _canonical_possession(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    possession = _mapping(value, "possession")
    _exact_keys(possession, {"group", "player_id"}, "possession")
    group = possession.get("group")
    player_id = possession.get("player_id")
    if group is not None and (
        not isinstance(group, str) or group not in {"home team", "away team"}
    ):
        raise ValueError("possession group must be 'home team', 'away team', or null")
    if player_id is not None:
        player_id = _positive_int(player_id, "possession player_id")
    return {"group": group, "player_id": player_id}


def iter_skillcorner_5hz(
    source_frames: Iterable[Mapping[str, object]],
    match_metadata: Mapping[str, object],
    *,
    source_release_id: str,
) -> Iterator[dict[str, object]]:
    """Yield the even-numbered source frames, validating in one forward pass."""
    manifest = load_manifest()
    errors = validate_manifest(manifest)
    if errors:
        raise ValueError("invalid SkillCorner data-state manifest: " + "; ".join(errors))
    if source_release_id != manifest.get("source_release_id"):
        raise ValueError("source release identity does not match skillcorner_5hz_v1")
    temporal = _mapping(
        _mapping(manifest["scientific_state"], "scientific_state")["temporal_sampling"],
        "temporal_sampling",
    )
    source_rate = temporal.get("source_frequency_hz")
    canonical_rate = temporal.get("canonical_frequency_hz")
    frame_modulus = temporal.get("sampling_frame_modulus")
    frame_remainder = temporal.get("sampling_frame_remainder")
    if (
        source_rate != 10
        or canonical_rate != 5
        or frame_modulus != 2
        or isinstance(frame_remainder, bool)
        or not isinstance(frame_remainder, int)
        or frame_remainder not in {0, 1}
    ):
        raise ValueError("unsupported SkillCorner 10 Hz to 5 Hz sampling rule")

    match_id, home_team_id, away_team_id, pitch_length, pitch_width, team_by_player = (
        _match_context(match_metadata)
    )
    source = load_source_manifest()
    selected_matches = source.get("selected_source_matches")
    if not isinstance(selected_matches, list) or match_id not in selected_matches:
        raise ValueError(f"match_id {match_id} is not in the pinned source release")

    previous_frame: int | None = None
    previous_period: int | None = None
    previous_timestamp: int | None = None
    for source_value in source_frames:
        frame = _mapping(source_value, "source frame")
        _exact_keys(
            frame,
            {
                "frame",
                "timestamp",
                "period",
                "ball_data",
                "possession",
                "image_corners_projection",
                "player_data",
            },
            "source frame",
        )
        source_frame = frame.get("frame")
        if isinstance(source_frame, bool) or not isinstance(source_frame, int) or source_frame < 0:
            raise ValueError("source frame number must be a nonnegative integer")
        if previous_frame is not None and source_frame <= previous_frame:
            reason = "duplicate" if source_frame == previous_frame else "non-monotonic"
            raise ValueError(f"{reason} source frame: {source_frame}")

        period_value = frame.get("period")
        if period_value is not None and (
            isinstance(period_value, bool)
            or not isinstance(period_value, int)
            or period_value not in {1, 2}
        ):
            raise ValueError("period must be 1, 2, or null")
        period = period_value
        timestamp = _timestamp_deciseconds(frame.get("timestamp"))
        if (
            period is not None
            and period == previous_period
            and previous_frame is not None
            and timestamp is not None
            and previous_timestamp is not None
            and timestamp - previous_timestamp != source_frame - previous_frame
        ):
            raise ValueError(f"frame/timestamp mismatch at source frame {source_frame}")

        if source_frame % 2 == frame_remainder:
            players_value = frame.get("player_data")
            if not isinstance(players_value, list):
                raise ValueError("player_data must be an array")
            players = [
                _canonical_player(value, team_by_player, home_team_id, away_team_id)
                for value in cast(list[object], players_value)
            ]
            player_ids = [cast(int, player["player_id"]) for player in players]
            if len(player_ids) != len(set(player_ids)):
                raise ValueError(f"duplicate player_id in source frame {source_frame}")
            players.sort(key=lambda player: cast(int, player["player_id"]))
            yield {
                "data_state_id": manifest["data_state_id"],
                "data_state_hash": manifest["data_state_hash"],
                "source_release_id": manifest["source_release_id"],
                "source_release_hash": manifest["source_release_hash"],
                "match_id": match_id,
                "period": period,
                "source_frame": source_frame,
                "canonical_sample_index": source_frame // 2,
                "timestamp_deciseconds": timestamp,
                "home_team_id": home_team_id,
                "away_team_id": away_team_id,
                "pitch_length_m": pitch_length,
                "pitch_width_m": pitch_width,
                "players": players,
                "ball": _canonical_ball(frame["ball_data"]),
                "possession": _canonical_possession(frame["possession"]),
            }
        previous_frame = source_frame
        previous_period = period
        previous_timestamp = timestamp


def serialize_sample(sample: Mapping[str, object]) -> bytes:
    """Serialize one canonical sample as sorted, compact UTF-8 JSON."""
    return json.dumps(
        dict(sample),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
