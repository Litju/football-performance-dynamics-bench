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

    try:
        source = load_source_manifest()
        if manifest.get("source_id") != source.get("source_id"):
            errors.append("data-state source_id does not match the pinned source authority")
        if manifest.get("source_release_id") != source.get("source_release_id"):
            errors.append("data-state source_release_id does not match the pinned source authority")
        if manifest.get("source_release_hash") != source.get("source_release_hash"):
            errors.append(
                "data-state source_release_hash does not match the pinned source authority"
            )
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        errors.append(f"could not verify pinned source authority: {exc}")

    try:
        state = _mapping(manifest.get("scientific_state"), "scientific_state")
        identity = _mapping(state.get("identity"), "scientific_state.identity")
        source_state = _mapping(state.get("source"), "scientific_state.source")
        if identity.get("schema_id") != manifest.get("schema_id"):
            errors.append("scientific_state schema_id does not match manifest")
        if identity.get("schema_version") != manifest.get("schema_version"):
            errors.append("scientific_state schema_version does not match manifest")
        if identity.get("data_state_id") != manifest.get("data_state_id"):
            errors.append("scientific_state data_state_id does not match manifest")
        if identity.get("data_state_version") != manifest.get("data_state_version"):
            errors.append("scientific_state data_state_version does not match manifest")
        for field in ("source_id", "source_release_id", "source_release_hash"):
            if source_state.get(field) != manifest.get(field):
                errors.append(f"scientific_state {field} does not match manifest")
        expected_hash = compute_data_state_hash(state)
        if manifest.get("data_state_hash") != expected_hash:
            errors.append("data_state_hash does not match scientific_state")
    except (ValueError, TypeError):
        errors.append("scientific_state cannot be canonically serialized")
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
    if group is not None and (not isinstance(group, str) or group not in {"home", "away"}):
        raise ValueError("possession group must be home, away, or null")
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
