"""Evaluate candidate windows over the pinned SkillCorner 5 Hz data state."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from typing import cast

from fpdbench.data_sources.skillcorner import canonical_bytes
from fpdbench.data_sources.skillcorner import (
    load_manifest as load_source_manifest,
)
from fpdbench.data_states.skillcorner import (
    load_manifest as load_data_state_manifest,
)
from fpdbench.data_states.skillcorner import (
    validate_manifest as validate_data_state_manifest,
)

MANIFEST_PATH = Path(__file__).with_name("skillcorner_window_v1.json")
SUPPORTED_POLICY_ID = "skillcorner_window_v1"
SUPPORTED_POLICY_VERSION = "1.1.0"
SUPPORTED_POLICY_HASH = "f0e1186f765cc7ce19c95152d8d6eacc66382f7e7f5a9ad1aa11c88c8a12f70b"
_PERIOD_NAME = re.compile(r"period_([1-5])\Z")
_SAMPLE_FIELDS = frozenset(
    {
        "data_state_id",
        "data_state_hash",
        "source_release_id",
        "source_release_hash",
        "match_id",
        "period",
        "source_frame",
        "canonical_sample_index",
        "timestamp_deciseconds",
        "home_team_id",
        "away_team_id",
        "pitch_length_m",
        "pitch_width_m",
        "players",
        "ball",
        "possession",
    }
)
_PLAYER_FIELDS = frozenset({"player_id", "team_id", "group", "x_m", "y_m", "is_detected"})
_BALL_FIELDS = frozenset({"x_m", "y_m", "is_detected"})
_POSSESSION_FIELDS = frozenset({"group", "player_id"})


@dataclass(frozen=True)
class PhaseInterval:
    """A pinned in-play interval with an inclusive start and exclusive end frame."""

    source_release_id: str
    match_id: int
    period: int
    frame_start: int
    frame_end: int


@dataclass(frozen=True)
class EligibilityIssue:
    code: str
    message: str
    sample_index: int | None = None


@dataclass(frozen=True)
class WindowEligibilityResult:
    policy_id: str
    policy_version: str
    policy_hash: str
    source_release_id: str
    source_release_hash: str
    data_state_id: str
    data_state_version: str
    data_state_hash: str
    eligible: bool
    exclusion_reasons: tuple[EligibilityIssue, ...]
    warnings: tuple[EligibilityIssue, ...]
    quality: Mapping[str, object]


def policy_hash(scientific_policy: Mapping[str, object]) -> str:
    """Hash policy semantics only; descriptive manifest fields are excluded."""
    return hashlib.sha256(canonical_bytes(scientific_policy)).hexdigest()


def load_manifest() -> dict[str, object]:
    value = json.loads(MANIFEST_PATH.read_text())
    if not isinstance(value, dict):
        raise ValueError("window eligibility manifest must be a JSON object")
    typed_value = cast(dict[object, object], value)
    if not all(isinstance(key, str) for key in typed_value):
        raise ValueError("window eligibility manifest keys must be strings")
    return cast(dict[str, object], typed_value)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object with string keys")
    typed_value = cast(Mapping[object, object], value)
    if not all(isinstance(key, str) for key in typed_value):
        raise ValueError(f"{label} must be an object with string keys")
    return cast(Mapping[str, object], typed_value)


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _number(value: object, label: str, *, nullable: bool = False) -> float | None:
    if nullable and value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{label} must be a finite number" + (" or null" if nullable else ""))
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _section(policy: Mapping[str, object], name: str) -> Mapping[str, object]:
    return _mapping(policy.get(name), f"scientific_policy.{name}")


def validate_manifest(manifest: Mapping[str, object]) -> tuple[str, ...]:
    errors: list[str] = []
    try:
        source = load_source_manifest()
        state = load_data_state_manifest()
        errors.extend(validate_data_state_manifest(state))
        if manifest.get("schema_id") != "fpdbench.skillcorner-window-eligibility":
            errors.append("unexpected window eligibility schema_id")
        if manifest.get("schema_version") != "1.0.0":
            errors.append("unsupported window eligibility schema_version")
        if manifest.get("policy_id") != SUPPORTED_POLICY_ID:
            errors.append("unexpected eligibility policy_id")
        if manifest.get("policy_version") != SUPPORTED_POLICY_VERSION:
            errors.append("unsupported eligibility policy_version")
        bindings = {
            "source_release_id": source.get("source_release_id"),
            "source_release_hash": source.get("source_release_hash"),
            "data_state_id": state.get("data_state_id"),
            "data_state_version": state.get("data_state_version"),
            "data_state_hash": state.get("data_state_hash"),
        }
        for field, expected in bindings.items():
            if manifest.get(field) != expected:
                errors.append(f"{field} does not match its pinned authority")
        policy = _mapping(manifest.get("scientific_policy"), "scientific_policy")
        identity = _mapping(policy.get("identity"), "scientific_policy.identity")
        for field, expected in {
            "policy_id": manifest.get("policy_id"),
            "policy_version": manifest.get("policy_version"),
            **bindings,
        }.items():
            if identity.get(field) != expected:
                errors.append(f"scientific_policy.identity.{field} does not match manifest")
        # A self-reported digest cannot authorize a different scientific policy.
        calculated_policy_hash = policy_hash(policy)
        if manifest.get("policy_hash") != calculated_policy_hash:
            errors.append("window eligibility policy_hash mismatch")
        if calculated_policy_hash != SUPPORTED_POLICY_HASH:
            errors.append("scientific_policy does not match the frozen supported policy")

        players = _section(policy, "player_observations")
        minimum_players = _integer(
            players.get("minimum_valid_per_team_per_sample"),
            "minimum_valid_per_team_per_sample",
            minimum=1,
        )
        if minimum_players > 11:
            errors.append("minimum_valid_per_team_per_sample cannot exceed 11")
        ball = _section(policy, "ball_observations")
        ball_fraction = _number(ball.get("minimum_valid_fraction"), "minimum_valid_fraction")
        if ball_fraction is None or not 0.0 < ball_fraction <= 1.0:
            errors.append("minimum_valid_fraction must be in (0, 1]")
        support = _section(policy, "support")
        if _integer(support.get("sample_frequency_hz"), "sample_frequency_hz", minimum=1) != 5:
            errors.append("sample_frequency_hz must match skillcorner_5hz_v1")
        coordinates = _section(policy, "coordinate_checks")
        for field in (
            "player_gross_limit_pitch_dimension_multiple",
            "ball_gross_limit_pitch_dimension_multiple",
        ):
            multiple = _number(coordinates.get(field), field)
            if multiple is None or multiple <= 0.0:
                errors.append(f"{field} must be positive")
        for field in (
            "player_displacement_warning_mps",
            "ball_displacement_warning_mps",
        ):
            threshold = _number(coordinates.get(field), field)
            if threshold is None or threshold <= 0.0:
                errors.append(f"{field} must be positive")
        temporal = _section(policy, "temporal_continuity")
        state_policy = _mapping(state.get("scientific_state"), "data-state scientific_state")
        state_temporal = _mapping(
            state_policy.get("temporal_sampling"), "data-state temporal_sampling"
        )
        expected_temporal = {
            "source_frame_parity": state_temporal.get("sampling_frame_remainder"),
            "source_frame_step": state_temporal.get("sampling_frame_modulus"),
            "canonical_sample_step": 1,
            "timestamp_step_deciseconds": 2,
        }
        for field, expected in expected_temporal.items():
            if temporal.get(field) != expected:
                errors.append(f"temporal_continuity.{field} does not match the pinned data state")
        if support.get("sample_interval_deciseconds") != temporal.get("timestamp_step_deciseconds"):
            errors.append("support sample interval does not match timestamp continuity")
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        errors.append(f"invalid window eligibility manifest: {exc}")
    return tuple(errors)


def _issues(items: Iterable[EligibilityIssue]) -> tuple[EligibilityIssue, ...]:
    unique = {(item.code, item.message, item.sample_index): item for item in items}
    return tuple(
        unique[key]
        for key in sorted(
            unique, key=lambda item: (-1 if item[2] is None else item[2], item[0], item[1])
        )
    )


def _active_roster(
    metadata: Mapping[str, object],
) -> tuple[dict[int, int], dict[int, dict[int, list[tuple[int, int]]]], bool]:
    players = metadata.get("players")
    if not isinstance(players, list):
        return {}, {}, False
    teams: dict[int, int] = {}
    appearances: dict[int, dict[int, list[tuple[int, int]]]] = {}
    complete = True
    player_values = cast(list[object], players)
    for raw_player in player_values:
        try:
            player = _mapping(raw_player, "match player")
            player_id = _integer(player.get("id"), "match player id", minimum=1)
            team_id = _integer(player.get("team_id"), "match player team_id", minimum=1)
            if player_id in teams:
                complete = False
                continue
            teams[player_id] = team_id
            playing_time = _mapping(player.get("playing_time"), "player playing_time")
            by_period = playing_time.get("by_period")
            if not isinstance(by_period, list):
                complete = False
                continue
            player_periods: dict[int, list[tuple[int, int]]] = {}
            for raw_interval in cast(list[object], by_period):
                interval = _mapping(raw_interval, "player playing-time interval")
                name = interval.get("name")
                match = _PERIOD_NAME.fullmatch(name) if isinstance(name, str) else None
                if match is None:
                    complete = False
                    continue
                period = int(match.group(1))
                start = _integer(interval.get("start_frame"), "appearance start_frame")
                end = _integer(interval.get("end_frame"), "appearance end_frame")
                if start > end:
                    complete = False
                    continue
                player_periods.setdefault(period, []).append((start, end))
            appearances[player_id] = player_periods
        except (ValueError, TypeError):
            complete = False
    return teams, appearances, complete and len(teams) == len(player_values)


def _period_ranges(
    metadata: Mapping[str, object],
) -> tuple[dict[int, tuple[int, int]], tuple[EligibilityIssue, ...]]:
    result: dict[int, tuple[int, int]] = {}
    issues: list[EligibilityIssue] = []
    values = metadata.get("match_periods")
    if values is None:
        return result, (
            EligibilityIssue("PERIOD_BOUNDS_MISSING", "match period bounds are missing"),
        )
    if not isinstance(values, list):
        return result, (
            EligibilityIssue("PERIOD_BOUNDS_INVALID", "match_periods must be an array"),
        )
    if not values:
        return result, (
            EligibilityIssue("PERIOD_BOUNDS_MISSING", "match period bounds are missing"),
        )
    for offset, raw_period in enumerate(cast(list[object], values)):
        try:
            period_value = _mapping(raw_period, "match period")
            period = _integer(period_value.get("period"), "period", minimum=1)
            start = _integer(period_value.get("start_frame"), "period start_frame")
            end = _integer(period_value.get("end_frame"), "period end_frame")
            if start >= end:
                raise ValueError("period start_frame must be less than end_frame")
        except (ValueError, TypeError):
            issues.append(
                EligibilityIssue(
                    "PERIOD_BOUNDS_INVALID",
                    f"match period definition at index {offset} is malformed",
                )
            )
            continue
        previous = result.get(period)
        if previous is not None:
            code = (
                "PERIOD_BOUNDS_DUPLICATE" if previous == (start, end) else "PERIOD_BOUNDS_CONFLICT"
            )
            issues.append(
                EligibilityIssue(code, f"period {period} has multiple frame-bound definitions")
            )
            continue
        result[period] = (start, end)

    ordered_periods = sorted(result.items())
    for (previous_period, (_, previous_end)), (period, (start, _)) in zip(
        ordered_periods, ordered_periods[1:], strict=False
    ):
        if start < previous_end:
            issues.append(
                EligibilityIssue(
                    "PERIOD_BOUNDS_CONFLICT",
                    f"periods {previous_period} and {period} have overlapping frame bounds",
                )
            )
    return result, tuple(issues)


def evaluate_skillcorner_window(
    samples: Iterable[Mapping[str, object]],
    *,
    history_intervals: int,
    future_intervals: int,
    match_metadata: Mapping[str, object],
    phase_intervals: Iterable[PhaseInterval],
    policy_manifest: Mapping[str, object] | None = None,
) -> WindowEligibilityResult:
    """Evaluate exactly one candidate; memory use is bounded by its support length."""
    history_intervals = _integer(history_intervals, "history_intervals", minimum=1)
    future_intervals = _integer(future_intervals, "future_intervals", minimum=1)
    manifest = load_manifest() if policy_manifest is None else dict(policy_manifest)
    manifest_errors = validate_manifest(manifest)
    if manifest_errors:
        raise ValueError("invalid window eligibility manifest: " + "; ".join(manifest_errors))
    policy = _mapping(manifest["scientific_policy"], "scientific_policy")
    source = _mapping(load_source_manifest(), "source manifest")
    data_state = _mapping(load_data_state_manifest(), "data-state manifest")
    policy_id = cast(str, manifest["policy_id"])
    version = cast(str, manifest["policy_version"])
    digest = cast(str, manifest["policy_hash"])
    expected_count = history_intervals + future_intervals + 1
    values = list(islice(samples, expected_count + 1))
    candidate = values[:expected_count]

    exclusions: list[EligibilityIssue] = []
    warnings: list[EligibilityIssue] = []

    def exclude(code: str, message: str, sample_index: int | None = None) -> None:
        exclusions.append(EligibilityIssue(code, message, sample_index))

    def warn(code: str, message: str, sample_index: int | None = None) -> None:
        warnings.append(EligibilityIssue(code, message, sample_index))

    if len(candidate) < expected_count:
        reason = (
            "INSUFFICIENT_HISTORY_SUPPORT"
            if len(candidate) <= history_intervals
            else "INSUFFICIENT_FUTURE_SUPPORT"
        )
        exclude(reason, f"expected {expected_count} samples, received {len(candidate)}")
    elif len(values) > expected_count:
        exclude("WINDOW_SUPPORT_LENGTH_MISMATCH", f"expected exactly {expected_count} samples")

    try:
        match_id = _integer(match_metadata.get("id"), "match id", minimum=1)
        home_team = _mapping(match_metadata.get("home_team"), "home_team")
        away_team = _mapping(match_metadata.get("away_team"), "away_team")
        home_team_id = _integer(home_team.get("id"), "home_team.id", minimum=1)
        away_team_id = _integer(away_team.get("id"), "away_team.id", minimum=1)
        pitch_length = _number(match_metadata.get("pitch_length"), "pitch_length")
        pitch_width = _number(match_metadata.get("pitch_width"), "pitch_width")
        selected_matches = source.get("selected_source_matches")
        if (
            pitch_length is None
            or pitch_width is None
            or pitch_length <= 0.0
            or pitch_width <= 0.0
            or home_team_id == away_team_id
            or not isinstance(selected_matches, list)
            or match_id not in selected_matches
        ):
            raise ValueError("match id, teams, pitch dimensions, or source membership is invalid")
    except (ValueError, TypeError) as exc:
        match_id = 0
        home_team_id = 0
        away_team_id = 0
        pitch_length = 0.0
        pitch_width = 0.0
        exclude("INVALID_MATCH_METADATA", str(exc))

    team_by_player, appearances, roster_complete = _active_roster(match_metadata)
    if not roster_complete:
        warn(
            "PLAYER_APPEARANCE_METADATA_UNKNOWN",
            "active-player denominator or transitions are incomplete",
        )
    period_bounds, period_bound_issues = _period_ranges(match_metadata)
    exclusions.extend(period_bound_issues)
    phase_intervals_by_period: dict[int, list[tuple[int, int]]] = {}
    for interval in phase_intervals:
        try:
            if interval.source_release_id != source.get("source_release_id"):
                exclude(
                    "PHASE_SOURCE_IDENTITY_MISMATCH",
                    "phase interval source release does not match the pinned release",
                )
                continue
            interval_match = _integer(interval.match_id, "phase match_id", minimum=1)
            period = _integer(interval.period, "phase period", minimum=1)
            start = _integer(interval.frame_start, "phase frame_start")
            end = _integer(interval.frame_end, "phase frame_end")
            if start >= end:
                exclude(
                    "PHASE_INTERVAL_INVALID", "phase interval must have positive frame duration"
                )
                continue
            if interval_match != match_id:
                exclude("PHASE_MATCH_ID_MISMATCH", "phase interval belongs to another match")
                continue
            phase_intervals_by_period.setdefault(period, []).append((start, end))
        except (AttributeError, ValueError, TypeError):
            exclude("PHASE_INTERVAL_INVALID", "phase interval fields are invalid")
            continue

    player_rules = _section(policy, "player_observations")
    ball_rules = _section(policy, "ball_observations")
    coordinate_rules = _section(policy, "coordinate_checks")
    temporal_rules = _section(policy, "temporal_continuity")
    support_rules = _section(policy, "support")
    minimum_players = cast(int, player_rules["minimum_valid_per_team_per_sample"])
    minimum_ball_fraction = cast(float, ball_rules["minimum_valid_fraction"])
    player_multiple = cast(float, coordinate_rules["player_gross_limit_pitch_dimension_multiple"])
    ball_multiple = cast(float, coordinate_rules["ball_gross_limit_pitch_dimension_multiple"])
    player_limit = player_multiple * pitch_length
    player_y_limit = player_multiple * pitch_width
    ball_limit = ball_multiple * pitch_length
    ball_y_limit = ball_multiple * pitch_width
    player_speed_limit = cast(float, coordinate_rules["player_displacement_warning_mps"])
    ball_speed_limit = cast(float, coordinate_rules["ball_displacement_warning_mps"])
    source_frame_step = cast(int, temporal_rules["source_frame_step"])
    canonical_sample_step = cast(int, temporal_rules["canonical_sample_step"])
    timestamp_step = cast(int, temporal_rules["timestamp_step_deciseconds"])
    elapsed_seconds = cast(int, support_rules["sample_interval_deciseconds"]) / 10.0

    periods: list[int | None] = []
    sample_indexes: list[int | None] = []
    timestamps: list[int | None] = []
    source_frames: list[int | None] = []
    valid_player_positions = 0
    observed_player_records = 0
    detected_players = 0
    extrapolated_players = 0
    player_expected_frames = 0
    player_valid_active_positions = 0
    support_complete = len(candidate) == expected_count
    player_completeness_known = roster_complete and support_complete
    unknown_roster_samples = 0
    missing_active_records = 0
    null_player_positions = 0
    outside_pitch_players = 0
    player_outlier_count = 0
    player_displacement_pairs = 0
    valid_ball_positions = 0
    detected_balls = 0
    extrapolated_balls = 0
    outside_pitch_balls = 0
    ball_outlier_count = 0
    ball_displacement_pairs = 0
    possession_home = 0
    possession_away = 0
    possession_unknown = 0
    transition_intervals = 0
    transition_player_ids: set[int] = set()
    observed_identity_change_intervals = 0
    observed_identity_comparison_intervals = 0
    continuous_intervals = 0
    team_observation_counts: list[dict[int, int]] = []
    active_rosters: list[set[int] | None] = []
    player_positions_by_frame: list[dict[int, tuple[float, float]]] = []
    ball_positions_by_frame: list[tuple[float, float] | None] = []

    for offset, raw_sample in enumerate(candidate):
        source_frames.append(None)
        sample_indexes.append(None)
        periods.append(None)
        timestamps.append(None)
        active_rosters.append(None)
        team_observation_counts.append({})
        player_positions_by_frame.append({})
        ball_positions_by_frame.append(None)
        sample_index: int | None = None
        try:
            sample = _mapping(raw_sample, "canonical sample")
            sample_index = _integer(sample.get("canonical_sample_index"), "canonical_sample_index")
            source_frame = _integer(sample.get("source_frame"), "source_frame")
            period_value = sample.get("period")
            period = (
                _integer(period_value, "period", minimum=1) if period_value is not None else None
            )
            timestamp_value = sample.get("timestamp_deciseconds")
            timestamp = (
                _integer(timestamp_value, "timestamp_deciseconds")
                if timestamp_value is not None
                else None
            )
            source_frames[offset] = source_frame
            sample_indexes[offset] = sample_index
            periods[offset] = period
            timestamps[offset] = timestamp
            if sample.get("data_state_id") != data_state.get("data_state_id") or sample.get(
                "data_state_hash"
            ) != data_state.get("data_state_hash"):
                exclude(
                    "INVALID_SAMPLE_SCHEMA",
                    "sample data-state identity does not match pinned state",
                    sample_index,
                )
            if sample.get("source_release_id") != source.get("source_release_id") or sample.get(
                "source_release_hash"
            ) != source.get("source_release_hash"):
                exclude(
                    "INVALID_SAMPLE_SCHEMA",
                    "sample source identity does not match pinned release",
                    sample_index,
                )
            if sample.get("match_id") != match_id:
                exclude(
                    "INVALID_SAMPLE_SCHEMA",
                    "sample match_id differs from match metadata",
                    sample_index,
                )
            if (
                sample.get("home_team_id") != home_team_id
                or sample.get("away_team_id") != away_team_id
            ):
                exclude(
                    "INVALID_SAMPLE_SCHEMA",
                    "sample team IDs differ from match metadata",
                    sample_index,
                )
            sample_pitch_length = _number(sample.get("pitch_length_m"), "pitch_length_m")
            sample_pitch_width = _number(sample.get("pitch_width_m"), "pitch_width_m")
            if sample_pitch_length != pitch_length or sample_pitch_width != pitch_width:
                exclude(
                    "INVALID_SAMPLE_SCHEMA",
                    "sample pitch dimensions differ from match metadata",
                    sample_index,
                )
            if (
                source_frame % 2 != cast(int, temporal_rules["source_frame_parity"])
                or sample_index != source_frame // 2
            ):
                exclude(
                    "CANONICAL_FRAME_MISMATCH",
                    "source frame parity or canonical index is inconsistent",
                    sample_index,
                )
            if period is None:
                exclude("INVALID_SAMPLE_SCHEMA", "period is null", sample_index)
            elif period not in period_bounds:
                exclude(
                    "PERIOD_BOUNDS_MISSING",
                    "match metadata has no frame bounds for this sample period",
                    sample_index,
                )
            elif not (period_bounds[period][0] <= source_frame < period_bounds[period][1]):
                exclude(
                    "OUTSIDE_PERIOD_BOUNDS",
                    "sample falls outside match metadata period bounds",
                    sample_index,
                )

            raw_players = sample.get("players")
            if not isinstance(raw_players, list):
                exclude("INVALID_SAMPLE_SCHEMA", "players must be an array", sample_index)
                raw_players = []
            raw_ball = sample.get("ball")
            if frozenset(sample) != _SAMPLE_FIELDS:
                exclude(
                    "INVALID_SAMPLE_SCHEMA",
                    "canonical sample fields differ from the pinned measurement schema",
                    sample_index,
                )
            if timestamp is None:
                exclude("TIMESTAMP_MISSING", "timestamp_deciseconds is null", sample_index)

            active_ids: set[int] | None = None
            if roster_complete and period is not None:
                active_ids = {
                    player_id
                    for player_id, player_periods in appearances.items()
                    if any(
                        start <= source_frame <= end
                        for start, end in player_periods.get(period, [])
                    )
                }
                player_expected_frames += len(active_ids)
            else:
                player_completeness_known = False
                unknown_roster_samples += 1
            active_rosters[offset] = active_ids

            player_ids: set[int] = set()
            positions: dict[int, tuple[float, float]] = {}
            team_counts = {home_team_id: 0, away_team_id: 0}
            for raw_player in cast(list[object], raw_players):
                try:
                    player = _mapping(raw_player, "canonical player")
                    if frozenset(player) != _PLAYER_FIELDS:
                        raise ValueError(
                            "canonical player fields differ from the measurement schema"
                        )
                    player_id = _integer(player.get("player_id"), "player_id", minimum=1)
                    team_id = _integer(player.get("team_id"), "team_id", minimum=1)
                    if player_id in player_ids:
                        exclude(
                            "DUPLICATE_PLAYER_ID", f"duplicate player_id {player_id}", sample_index
                        )
                        continue
                    player_ids.add(player_id)
                    observed_player_records += 1
                    if (
                        team_id not in team_counts
                        or player_id not in team_by_player
                        or team_by_player[player_id] != team_id
                        or player.get("group") != ("home" if team_id == home_team_id else "away")
                    ):
                        exclude(
                            "PLAYER_TEAM_IDENTITY_CONFLICT",
                            f"player_id {player_id} has an inconsistent team",
                            sample_index,
                        )
                        continue
                    is_detected = player.get("is_detected")
                    if not isinstance(is_detected, bool):
                        exclude(
                            "INVALID_DETECTION_FLAG",
                            f"player_id {player_id} has a non-boolean is_detected",
                            sample_index,
                        )
                        continue
                    x = _number(player.get("x_m"), "player x_m", nullable=True)
                    y = _number(player.get("y_m"), "player y_m", nullable=True)
                    if x is None or y is None:
                        null_player_positions += 1
                        warn(
                            "PLAYER_COORDINATES_MISSING",
                            f"player_id {player_id} has a null coordinate",
                            sample_index,
                        )
                        continue
                    if abs(x) > player_limit or abs(y) > player_y_limit:
                        exclude(
                            "COORDINATE_IMPLAUSIBLE",
                            f"player_id {player_id} exceeds gross pitch-relative bounds",
                            sample_index,
                        )
                        continue
                    active = active_ids is None or player_id in active_ids
                    if not active:
                        warn(
                            "PLAYER_OUTSIDE_APPEARANCE",
                            f"player_id {player_id} is outside metadata playing-time intervals",
                            sample_index,
                        )
                        continue
                    positions[player_id] = (x, y)
                    valid_player_positions += 1
                    team_counts[team_id] += 1
                    if is_detected:
                        detected_players += 1
                    else:
                        extrapolated_players += 1
                    if abs(x) > pitch_length / 2.0 or abs(y) > pitch_width / 2.0:
                        outside_pitch_players += 1
                        warn(
                            "PLAYER_POSITION_OUTSIDE_PITCH",
                            f"player_id {player_id} is outside the pitch rectangle",
                            sample_index,
                        )
                    if active_ids is not None and player_id in active_ids:
                        player_valid_active_positions += 1
                except (ValueError, TypeError) as exc:
                    code = (
                        "NONFINITE_COORDINATE" if "finite" in str(exc) else "INVALID_SAMPLE_SCHEMA"
                    )
                    exclude(code, str(exc), sample_index)
            team_observation_counts[offset] = team_counts
            if (
                team_counts[home_team_id] < minimum_players
                or team_counts[away_team_id] < minimum_players
            ):
                count_message = (
                    f"valid active counts home={team_counts[home_team_id]}, "
                    f"away={team_counts[away_team_id]}; minimum={minimum_players} each"
                )
                exclude("PLAYER_COUNT_BELOW_TEAM_MINIMUM", count_message, sample_index)
            if active_ids is not None:
                missing_active_records += len(active_ids - player_ids)
                if active_ids - player_ids:
                    warn(
                        "PLAYER_OBSERVATION_MISSING",
                        f"{len(active_ids - player_ids)} active player records are absent",
                        sample_index,
                    )
            player_positions_by_frame[offset] = positions

            ball_position: tuple[float, float] | None = None
            if raw_ball is not None:
                try:
                    ball = _mapping(raw_ball, "canonical ball")
                    if frozenset(ball) != _BALL_FIELDS:
                        raise ValueError("canonical ball fields differ from the measurement schema")
                    detected = ball.get("is_detected")
                    if not isinstance(detected, bool):
                        exclude(
                            "INVALID_DETECTION_FLAG",
                            "ball has a non-boolean is_detected",
                            sample_index,
                        )
                    else:
                        x = _number(ball.get("x_m"), "ball x_m", nullable=True)
                        y = _number(ball.get("y_m"), "ball y_m", nullable=True)
                        if x is None or y is None:
                            warn(
                                "BALL_COORDINATES_MISSING",
                                "ball has a null coordinate",
                                sample_index,
                            )
                        elif abs(x) > ball_limit or abs(y) > ball_y_limit:
                            exclude(
                                "COORDINATE_IMPLAUSIBLE",
                                "ball exceeds gross pitch-relative bounds",
                                sample_index,
                            )
                        else:
                            ball_position = (x, y)
                            valid_ball_positions += 1
                            if detected:
                                detected_balls += 1
                            else:
                                extrapolated_balls += 1
                            if abs(x) > pitch_length / 2.0 or abs(y) > pitch_width / 2.0:
                                outside_pitch_balls += 1
                                warn(
                                    "BALL_OUTSIDE_PITCH",
                                    "ball is outside the pitch rectangle",
                                    sample_index,
                                )
                except (ValueError, TypeError) as exc:
                    code = (
                        "NONFINITE_COORDINATE" if "finite" in str(exc) else "INVALID_SAMPLE_SCHEMA"
                    )
                    exclude(code, str(exc), sample_index)
            else:
                warn("BALL_COORDINATES_MISSING", "ball observation is null", sample_index)
            ball_positions_by_frame[offset] = ball_position

            possession = sample.get("possession")
            if possession is not None:
                try:
                    context = _mapping(possession, "possession")
                    if frozenset(context) != _POSSESSION_FIELDS:
                        raise ValueError("possession fields differ from the measurement schema")
                    group = context.get("group")
                    possession_player = context.get("player_id")
                    if group == "home team":
                        possession_home += 1
                    elif group == "away team":
                        possession_away += 1
                    elif group is None:
                        possession_unknown += 1
                        warn(
                            "POSSESSION_CONTEXT_UNKNOWN",
                            "possession group is null",
                            sample_index,
                        )
                    else:
                        raise ValueError("possession group is not home team, away team, or null")
                    if possession_player is not None:
                        player_id = _integer(possession_player, "possession player_id", minimum=1)
                        if player_id not in player_ids:
                            warn(
                                "POSSESSION_PLAYER_UNOBSERVED",
                                "possession player is absent from this sample",
                                sample_index,
                            )
                except (ValueError, TypeError) as exc:
                    exclude("INVALID_SAMPLE_SCHEMA", str(exc), sample_index)
            if possession is None:
                possession_unknown += 1
                warn(
                    "POSSESSION_CONTEXT_UNKNOWN",
                    "possession observation is null",
                    sample_index,
                )
        except (ValueError, TypeError) as exc:
            exclude("INVALID_SAMPLE_SCHEMA", str(exc), sample_index)

    for offset in range(1, len(candidate)):
        before_index, current_index = sample_indexes[offset - 1], sample_indexes[offset]
        before_frame, current_frame = source_frames[offset - 1], source_frames[offset]
        before_period, current_period = periods[offset - 1], periods[offset]
        before_time, current_time = timestamps[offset - 1], timestamps[offset]
        issue_index = current_index
        if (
            before_period is not None
            and current_period is not None
            and before_period != current_period
        ):
            exclude("PERIOD_BOUNDARY_CROSSED", "window support crosses a match period", issue_index)
            continue
        if before_period is not None and before_period == current_period:
            observed_identity_comparison_intervals += 1
        if before_index is not None and current_index is not None:
            if current_index == before_index:
                exclude("DUPLICATE_SAMPLE", "canonical sample index is repeated", issue_index)
            elif current_index < before_index:
                exclude(
                    "NONMONOTONIC_SAMPLE_ORDER", "canonical sample order decreases", issue_index
                )
            elif current_index != before_index + canonical_sample_step:
                exclude("TEMPORAL_GAP", "canonical sample indices are not consecutive", issue_index)
        if (
            before_frame is not None
            and current_frame is not None
            and current_frame - before_frame != source_frame_step
        ):
            if current_frame == before_frame:
                exclude("DUPLICATE_SAMPLE", "source frame is repeated", issue_index)
            elif current_frame < before_frame:
                exclude("NONMONOTONIC_SAMPLE_ORDER", "source frame order decreases", issue_index)
            else:
                exclude(
                    "TEMPORAL_GAP", "source frames are not consecutive 5 Hz samples", issue_index
                )
        if before_period == current_period and before_time is not None and current_time is not None:
            if current_time - before_time != timestamp_step:
                exclude(
                    "TIMESTAMP_DISCONTINUITY",
                    "adjacent 5 Hz timestamps must differ by two deciseconds",
                    issue_index,
                )

        before_active, current_active = active_rosters[offset - 1], active_rosters[offset]
        if (
            before_active is not None
            and current_active is not None
            and before_active != current_active
        ):
            transition_intervals += 1
            transition_player_ids.update(before_active ^ current_active)
            warn(
                "IDENTITY_TRANSITION_EXPOSURE",
                "active player IDs change within support",
                issue_index,
            )
        before_observed = set(player_positions_by_frame[offset - 1])
        current_observed = set(player_positions_by_frame[offset])
        if before_observed != current_observed:
            observed_identity_change_intervals += 1

        if (
            current_index is not None
            and before_index is not None
            and current_index == before_index + canonical_sample_step
            and before_time is not None
            and current_time == before_time + timestamp_step
            and before_frame is not None
            and current_frame == before_frame + source_frame_step
            and before_period is not None
            and current_period == before_period
        ):
            continuous_intervals += 1
            for player_id in before_observed & current_observed:
                player_displacement_pairs += 1
                before_xy = player_positions_by_frame[offset - 1][player_id]
                current_xy = player_positions_by_frame[offset][player_id]
                if math.dist(before_xy, current_xy) / elapsed_seconds > player_speed_limit:
                    player_outlier_count += 1
                    warn(
                        "PLAYER_DISPLACEMENT_OUTLIER",
                        f"player_id {player_id} exceeds the advisory displacement speed",
                        issue_index,
                    )
            before_ball = ball_positions_by_frame[offset - 1]
            current_ball = ball_positions_by_frame[offset]
            if before_ball is not None and current_ball is not None:
                ball_displacement_pairs += 1
                if math.dist(before_ball, current_ball) / elapsed_seconds > ball_speed_limit:
                    ball_outlier_count += 1
                    warn(
                        "BALL_DISPLACEMENT_OUTLIER",
                        "ball exceeds the advisory displacement speed",
                        issue_index,
                    )

    phase_coverage_count: int | None = None
    phase_coverage_denominator: int | None = None
    first_uncovered_source_frame: int | None = None
    if (
        support_complete
        and source_frames
        and all(frame is not None for frame in source_frames)
        and periods[0] is not None
        and all(period == periods[0] for period in periods)
        and cast(int, source_frames[-1]) >= cast(int, source_frames[0])
    ):
        span_start = cast(int, source_frames[0])
        span_end = cast(int, source_frames[-1]) + 1
        phase_coverage_denominator = span_end - span_start
        cursor = span_start
        covered_frames = 0
        clipped_intervals = sorted(
            (
                max(start, span_start),
                min(end, span_end),
            )
            for start, end in phase_intervals_by_period.get(periods[0], [])
            if start < span_end and end > span_start
        )
        for start, end in clipped_intervals:
            if end <= cursor:
                continue
            if start > cursor and first_uncovered_source_frame is None:
                first_uncovered_source_frame = cursor
            covered_frames += end - max(start, cursor)
            cursor = max(cursor, end)
        if cursor < span_end and first_uncovered_source_frame is None:
            first_uncovered_source_frame = cursor
        phase_coverage_count = covered_frames
        if first_uncovered_source_frame is not None:
            sample_offset = next(
                (
                    offset
                    for offset, frame in enumerate(source_frames)
                    if frame == first_uncovered_source_frame
                ),
                None,
            )
            exclude(
                "PHASE_NOT_IN_PLAY_OR_UNKNOWN",
                f"source frame {first_uncovered_source_frame} lacks positive in-play coverage",
                sample_indexes[sample_offset] if sample_offset is not None else None,
            )

    support_count = len(candidate)
    expected_intervals = max(0, expected_count - 1)
    observed_intervals = max(0, support_count - 1)
    ball_fraction = valid_ball_positions / support_count if support_count else None
    if support_count > history_intervals and ball_positions_by_frame[history_intervals] is None:
        exclude(
            "BALL_MISSING_AT_ORIGIN",
            "ball position at candidate origin is unavailable",
            sample_indexes[history_intervals],
        )
    if ball_fraction is not None and ball_fraction < minimum_ball_fraction:
        exclude(
            "BALL_COVERAGE_BELOW_MINIMUM",
            f"valid ball fraction {ball_fraction:.6f} is below {minimum_ball_fraction:.6f}",
        )

    detection_denominator = detected_players + extrapolated_players
    player_completeness_fraction = (
        player_valid_active_positions / player_expected_frames
        if player_completeness_known and player_expected_frames
        else None
    )
    expected_player_frames = player_expected_frames if player_completeness_known else None
    temporal_discontinuous = support_count != expected_count or any(
        issue.code
        in {
            "DUPLICATE_SAMPLE",
            "NONMONOTONIC_SAMPLE_ORDER",
            "TEMPORAL_GAP",
            "TIMESTAMP_DISCONTINUITY",
            "TIMESTAMP_MISSING",
            "PERIOD_BOUNDARY_CROSSED",
        }
        for issue in exclusions
    )
    detection_stratum = (
        "unknown"
        if not support_complete or detection_denominator == 0
        else "all_detected"
        if extrapolated_players == 0
        else "all_extrapolated"
        if detected_players == 0
        else "mixed"
    )
    ball_detection_stratum = (
        "unknown"
        if not support_complete or valid_ball_positions == 0
        else "all_detected"
        if extrapolated_balls == 0
        else "all_extrapolated"
        if detected_balls == 0
        else "mixed"
    )
    player_completeness_stratum = (
        "unknown"
        if player_completeness_fraction is None
        else "complete"
        if player_completeness_fraction == 1.0
        else "none"
        if player_completeness_fraction == 0.0
        else "partial"
    )
    ball_completeness_stratum = (
        "unknown"
        if not support_complete or ball_fraction is None
        else "complete"
        if ball_fraction == 1.0
        else "none"
        if ball_fraction == 0.0
        else "partial"
    )
    strata = {
        "player_detection_exposure": detection_stratum,
        "ball_detection_exposure": ball_detection_stratum,
        "player_completeness": player_completeness_stratum,
        "ball_completeness": ball_completeness_stratum,
        "temporal_continuity": (
            "unknown"
            if support_count != expected_count
            else "discontinuous"
            if temporal_discontinuous
            else "continuous"
        ),
        "identity_transition_exposure": (
            "unknown"
            if not roster_complete or not support_complete
            else "exposed"
            if transition_intervals
            else "none_observed"
        ),
        "source_quality_uncertainty": "unknown_per_observation",
        "play_context": (
            "unknown"
            if phase_coverage_count is None or phase_coverage_denominator is None
            else "uncovered_or_unknown"
            if phase_coverage_count != phase_coverage_denominator
            else "all_in_play"
        ),
    }
    warn(
        "SOURCE_QUALITY_UNKNOWN",
        "no per-observation player-identity confidence is supplied by SkillCorner",
    )

    quality: dict[str, object] = {
        "support_sample_count": support_count,
        "origin_offset": history_intervals,
        "player_observations": {
            "valid_position_count": valid_player_positions,
            "observed_record_count": observed_player_records,
            "expected_active_player_frames": expected_player_frames,
            "active_position_count": player_valid_active_positions
            if player_completeness_known
            else None,
            "completeness_fraction": player_completeness_fraction,
            "missing_active_records": missing_active_records if player_completeness_known else None,
            "missing_active_record_fraction": (
                missing_active_records / expected_player_frames if expected_player_frames else None
            ),
            "unknown_roster_samples": unknown_roster_samples,
            "null_coordinate_records": null_player_positions,
            "null_coordinate_fraction": (
                null_player_positions / observed_player_records if observed_player_records else None
            ),
            "detected_position_count": detected_players,
            "extrapolated_position_count": extrapolated_players,
            "detection_denominator": detection_denominator,
            "extrapolation_fraction": (
                extrapolated_players / detection_denominator if detection_denominator else None
            ),
            "outside_pitch_count": outside_pitch_players,
            "outside_pitch_fraction": (
                outside_pitch_players / detection_denominator if detection_denominator else None
            ),
            "displacement_outlier_count": player_outlier_count,
            "displacement_pair_denominator": player_displacement_pairs,
            "displacement_outlier_fraction": (
                player_outlier_count / player_displacement_pairs
                if player_displacement_pairs
                else None
            ),
        },
        "ball_observations": {
            "valid_position_count": valid_ball_positions,
            "denominator_sample_count": support_count,
            "completeness_fraction": ball_fraction,
            "detected_position_count": detected_balls,
            "extrapolated_position_count": extrapolated_balls,
            "extrapolation_fraction": (
                extrapolated_balls / valid_ball_positions if valid_ball_positions else None
            ),
            "outside_pitch_count": outside_pitch_balls,
            "outside_pitch_fraction": (
                outside_pitch_balls / valid_ball_positions if valid_ball_positions else None
            ),
            "displacement_outlier_count": ball_outlier_count,
            "displacement_pair_denominator": ball_displacement_pairs,
            "displacement_outlier_fraction": (
                ball_outlier_count / ball_displacement_pairs if ball_displacement_pairs else None
            ),
        },
        "temporal": {
            "expected_intervals": expected_intervals,
            "observed_intervals": observed_intervals,
            "continuous_intervals": continuous_intervals,
            "continuity_fraction": (
                continuous_intervals / expected_intervals if support_complete else None
            ),
            "observed_identity_change_intervals": observed_identity_change_intervals,
            "identity_comparison_intervals": observed_identity_comparison_intervals,
            "observed_identity_change_fraction": (
                observed_identity_change_intervals / observed_identity_comparison_intervals
                if observed_identity_comparison_intervals
                else None
            ),
            "active_roster_transition_intervals": transition_intervals if roster_complete else None,
            "active_roster_transition_fraction": (
                transition_intervals / expected_intervals
                if roster_complete and support_complete and expected_intervals
                else None
            ),
            "changed_active_player_ids": len(transition_player_ids) if roster_complete else None,
        },
        "play_context": {
            "phase_covered_source_frames": phase_coverage_count,
            "phase_coverage_denominator_source_frames": phase_coverage_denominator,
            "uncovered_source_frames": (
                phase_coverage_denominator - phase_coverage_count
                if phase_coverage_count is not None and phase_coverage_denominator is not None
                else None
            ),
            "phase_coverage_fraction": (
                phase_coverage_count / phase_coverage_denominator
                if phase_coverage_count is not None and phase_coverage_denominator is not None
                else None
            ),
            "possession_home_samples": possession_home,
            "possession_away_samples": possession_away,
            "possession_unknown_samples": possession_unknown,
            "possession_denominator_samples": support_count,
            "possession_home_fraction": possession_home / support_count if support_count else None,
            "possession_away_fraction": possession_away / support_count if support_count else None,
            "possession_unknown_fraction": (
                possession_unknown / support_count if support_count else None
            ),
        },
        "strata": strata,
    }
    return WindowEligibilityResult(
        policy_id=policy_id,
        policy_version=version,
        policy_hash=digest,
        source_release_id=cast(str, manifest["source_release_id"]),
        source_release_hash=cast(str, manifest["source_release_hash"]),
        data_state_id=cast(str, manifest["data_state_id"]),
        data_state_version=cast(str, manifest["data_state_version"]),
        data_state_hash=cast(str, manifest["data_state_hash"]),
        eligible=not exclusions,
        exclusion_reasons=_issues(exclusions),
        warnings=_issues(warnings),
        quality=quality,
    )
