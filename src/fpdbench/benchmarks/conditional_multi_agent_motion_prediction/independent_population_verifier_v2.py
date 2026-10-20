"""Independent, synthetic-only replay of the frozen SkillCorner v2 population contract.

This module deliberately imports no production parser, sampler, eligibility evaluator,
population producer, or population validator. It derives expected results from raw
in-memory synthetic inputs and compares those results with an external submission.
Every report is non-authoritative and cannot qualify a population.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

type JsonObject = dict[str, object]
type XY = tuple[float, float]

SOURCE_RELEASE_HASH = "e92c417b7640b27399451134ee3fce4b1961b0c0dfc2e01175a8f3c906a9ae07"
SOURCE_POPULATION_HASH = "e9054b7ddc2dfeff4dd8425ea61a23ed0b326076a08899e47502484228fdbdf4"
MEASUREMENT_HASH = "1ecf355b3e6e2f04967e8363c1fdecc7f40707a7dda9966ebee1b3d90e97e671"
ELIGIBILITY_HASH = "ed1cdc20ca7a93040fd4aabc91655819c5c4b8c58021c6540c6aaea325dafa11"
PROTOCOL_HASH = "3d7bdc46300b966a4da274579d21ac4c8219e1ef897719d6b7a308596e9f1d9f"
PLAN_HASH = "a59fee6ee8e9fb03f4f0ccdae1933458af2bbf2375db7e6cd2bdf10962e42b62"
POPULATION_SCHEMA_HASH = "27da86b7355c311a65c68ab9b2bd3ae86e27779ed48641c23181ffe2f9adc224"
RESULT_SCHEMA_HASH = "d0d7dbf4a14cade66d1e0ce7282441d8f035a68de8a192ad8e4d70210be18f7f"
DRIFT_STOP_CODE = "BALL_NULL_FLAG_WITH_FINITE_XY_UNAPPROVED"

_ROOT = Path(__file__).parents[2]
_SOURCE_AUTHORITY = _ROOT / "data_sources" / "skillcorner_open_data_v1.json"
_STATE_AUTHORITY = _ROOT / "data_states" / "skillcorner_5hz_v2.json"
_POLICY_AUTHORITY = _ROOT / "eligibility" / "skillcorner_window_v2.json"
_PROTOCOL_AUTHORITY = Path(__file__).with_name("prospective_skillcorner_protocol_v2.json")
_PLAN_AUTHORITY = Path(__file__).with_name("empirical_experiment_plan_v2.json")
_POPULATION_SCHEMA = Path(__file__).with_name("evaluation_population_authority_v2.schema.json")
_RESULT_SCHEMA = Path(__file__).with_name("prospective_experiment_result_v2.schema.json")
_TIMESTAMP = re.compile(r"([0-9]{2}):([0-5][0-9]):([0-5][0-9])\.([0-9]{2})\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_ORIGIN_ID = re.compile(r"period_([1-5])/sample_(0|[1-9][0-9]*)\Z")


@dataclass(frozen=True, slots=True)
class MatchSourceBytesV2:
    """Synthetic raw input bytes; phases use the producer wire's normalized intervals."""

    match_id: str
    metadata_json: bytes
    tracking_jsonl: bytes
    phase_intervals_json: bytes


@dataclass(frozen=True, slots=True)
class PopulationSubmissionV2:
    """Five producer wire payloads, supplied as bytes for read-only comparison."""

    manifest_json: bytes
    candidates_jsonl: bytes
    diagnostic_census_jsonl: bytes
    truth_jsonl: bytes
    receipt_json: bytes


@dataclass(frozen=True, slots=True)
class MismatchV2:
    artifact: str
    path: str
    expected_sha256: str | None
    actual_sha256: str | None


@dataclass(frozen=True, slots=True)
class InputSnapshotV2:
    match_id: str
    field: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class ArtifactSnapshotV2:
    artifact: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class RetainedSampleSnapshotV2:
    match_id: str
    raw_source_frames: int
    even_source_frames: int
    odd_source_frames: int
    retained_samples: int
    retained_samples_sha256: str


@dataclass(frozen=True, slots=True)
class MatchCountsV2:
    role: str
    match_id: str
    diagnostic_grid_count: int | None
    candidate_count: int | None
    eligible_window_count: int | None
    directed_scene_count: int | None
    scoreable_window_count: int | None


@dataclass(frozen=True, slots=True)
class AuditReportV2:
    """Hash-bound comparison result; reconciliation never means empirical qualification."""

    status: Literal["DERIVED", "RECONCILED", "MISMATCH", "INCOMPLETE", "STOPPED", "INVALID_INPUT"]
    qualification_status: Literal["NOT_QUALIFIED"]
    authoritative: Literal[False]
    producer_revision: str | None
    producer_executable_fingerprint: str | None
    verifier_source_sha256: str
    python_version: str
    source_release_hash: str
    source_population_hash: str
    role_assignment_sha256: str
    measurement_hash: str
    eligibility_hash: str
    protocol_hash: str
    plan_hash: str
    authority_snapshots: tuple[ArtifactSnapshotV2, ...]
    input_snapshots: tuple[InputSnapshotV2, ...]
    artifact_snapshots: tuple[ArtifactSnapshotV2, ...]
    retained_sample_snapshots: tuple[RetainedSampleSnapshotV2, ...]
    match_roles: tuple[tuple[str, str], ...]
    match_counts: tuple[MatchCountsV2, ...]
    candidate_count: int | None
    eligible_count: int | None
    diagnostic_grid_count: int | None
    scoreable_window_count: int | None
    ball_null_flag_finite_xy_count: int | None
    stop_code: str | None
    mismatches: tuple[MismatchV2, ...]
    report_sha256: str

    def content_without_digest(self) -> JsonObject:
        value: JsonObject = {
            "status": self.status,
            "qualification_status": self.qualification_status,
            "authoritative": self.authoritative,
            "producer_revision": self.producer_revision,
            "producer_executable_fingerprint": self.producer_executable_fingerprint,
            "verifier_source_sha256": self.verifier_source_sha256,
            "python_version": self.python_version,
            "authority_hashes": {
                "source_release": self.source_release_hash,
                "source_population": self.source_population_hash,
                "role_assignment": self.role_assignment_sha256,
                "measurement": self.measurement_hash,
                "eligibility": self.eligibility_hash,
                "protocol": self.protocol_hash,
                "plan": self.plan_hash,
            },
            "authority_document_snapshots": [
                {"artifact": item.artifact, "size_bytes": item.size_bytes, "sha256": item.sha256}
                for item in self.authority_snapshots
            ],
            "input_snapshots": [
                {
                    "match_id": item.match_id,
                    "field": item.field,
                    "size_bytes": item.size_bytes,
                    "sha256": item.sha256,
                }
                for item in self.input_snapshots
            ],
            "artifact_snapshots": [
                {"artifact": item.artifact, "size_bytes": item.size_bytes, "sha256": item.sha256}
                for item in self.artifact_snapshots
            ],
            "retained_sample_snapshots": [
                {
                    "match_id": item.match_id,
                    "raw_source_frames": item.raw_source_frames,
                    "even_source_frames": item.even_source_frames,
                    "odd_source_frames": item.odd_source_frames,
                    "retained_samples": item.retained_samples,
                    "retained_samples_sha256": item.retained_samples_sha256,
                }
                for item in self.retained_sample_snapshots
            ],
            "match_roles": [
                {"role": role, "match_id": match_id} for role, match_id in self.match_roles
            ],
            "match_counts": [
                {
                    "role": item.role,
                    "match_id": item.match_id,
                    "diagnostic_grid_count": item.diagnostic_grid_count,
                    "candidate_count": item.candidate_count,
                    "eligible_window_count": item.eligible_window_count,
                    "directed_scene_count": item.directed_scene_count,
                    "scoreable_window_count": item.scoreable_window_count,
                }
                for item in self.match_counts
            ],
            "counts": {
                "candidates": self.candidate_count,
                "eligible": self.eligible_count,
                "diagnostic_grid": self.diagnostic_grid_count,
                "scoreable_windows": self.scoreable_window_count,
                "ball_null_flag_finite_xy": self.ball_null_flag_finite_xy_count,
            },
            "stop_code": self.stop_code,
            "mismatches": [
                {
                    "artifact": item.artifact,
                    "path": item.path,
                    "expected_sha256": item.expected_sha256,
                    "actual_sha256": item.actual_sha256,
                }
                for item in self.mismatches
            ],
        }
        return value

    def to_json_bytes(self) -> bytes:
        """Return canonical, self-digested report bytes without source rows or truth values."""
        value = self.content_without_digest()
        value["report_sha256"] = self.report_sha256
        return _canonical_bytes(value)


@dataclass(frozen=True, slots=True)
class PeriodBounds:
    period: int
    start_frame: int
    end_frame: int


@dataclass(frozen=True, slots=True)
class PlayerObservation:
    player_id: int
    x: float | None
    y: float | None
    detected: bool
    team_id: int | None
    team: Literal["home", "away"] | None

    @property
    def xy(self) -> XY | None:
        if self.x is None or self.y is None:
            return None
        return (self.x, self.y)


@dataclass(frozen=True, slots=True)
class BallObservation:
    x: float | None
    y: float | None
    detected: bool | None

    @property
    def xy(self) -> XY | None:
        if self.x is None or self.y is None:
            return None
        return (self.x, self.y)


@dataclass(frozen=True, slots=True)
class PossessionObservation:
    group: str | None
    player_id: int | None


@dataclass(frozen=True, slots=True)
class CanonicalSample:
    source_frame: int
    canonical_sample_index: int
    period: int | None
    timestamp_deciseconds: int | None
    players: tuple[PlayerObservation, ...]
    ball: BallObservation | None
    possession: PossessionObservation | None


@dataclass(frozen=True, slots=True)
class RosterPlayer:
    player_id: int
    team_id: int
    team: Literal["home", "away"] | None
    intervals: tuple[tuple[int, int, int], ...] | None


@dataclass(frozen=True, slots=True)
class MatchContext:
    match_id: str
    home_team_id: int
    away_team_id: int
    pitch_length_m: float
    pitch_width_m: float
    periods: tuple[PeriodBounds, ...]
    roster: tuple[RosterPlayer, ...]
    roster_complete: bool
    roster_identity_conflict: bool
    phases: tuple[tuple[int, int, int], ...]
    samples: tuple[CanonicalSample, ...]
    raw_source_frames: int
    even_source_frames: int
    odd_source_frames: int
    retained_samples_sha256: str

    @property
    def samples_by_index(self) -> dict[int, CanonicalSample]:
        return {sample.canonical_sample_index: sample for sample in self.samples}

    @property
    def roster_by_id(self) -> dict[int, RosterPlayer]:
        return {player.player_id: player for player in self.roster}


@dataclass(frozen=True, slots=True)
class OriginCandidate:
    role: str
    match_id: str
    period: int
    sample_index: int
    support: tuple[CanonicalSample, ...]

    @property
    def origin_sample_id(self) -> str:
        return f"period_{self.period}/sample_{self.sample_index}"


@dataclass(frozen=True, slots=True)
class SceneTruthV2:
    scene_id: Literal["home", "away"]
    player_ids: tuple[int, ...]
    origin_xy: tuple[XY, ...]
    absolute_xy: tuple[tuple[XY | None, ...], ...]
    displacement_xy: tuple[tuple[XY | None, ...], ...]
    mask: tuple[tuple[bool, ...], ...]
    absolute_digest: str
    displacement_digest: str
    mask_digest: str
    scoreable: bool
    unscoreable_reason: str | None


@dataclass(frozen=True, slots=True)
class EvaluatedCandidate:
    origin: OriginCandidate
    diagnostic: JsonObject
    eligibility_digest: str
    included: bool
    scenes: tuple[SceneTruthV2, SceneTruthV2] | None
    scoreable: bool


@dataclass(frozen=True, slots=True)
class DerivationV2:
    role_order: tuple[tuple[str, str], ...]
    candidates: tuple[EvaluatedCandidate, ...]
    census_rows: tuple[JsonObject, ...]
    contexts: tuple[MatchContext, ...]
    expected_manifest: JsonObject | None
    expected_candidates: bytes
    expected_census: bytes
    expected_truth: bytes
    expected_receipt: JsonObject
    candidate_count: int
    eligible_count: int
    diagnostic_grid_count: int
    scoreable_window_count: int
    drift_count: int
    stop_code: str | None


class _InputError(ValueError):
    pass


def canonical_bytes(value: object) -> bytes:
    """The frozen authorities use sorted-key compact UTF-8 JSON for wire hashes."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _canonical_bytes(value: object) -> bytes:
    return canonical_bytes(value)


def _digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest(value: object) -> str:
    return _digest_bytes(canonical_bytes(value))


def _strict_object(pairs: list[tuple[str, object]]) -> JsonObject:
    result: JsonObject = {}
    for key, value in pairs:
        if key in result:
            raise _InputError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_constant(_: str) -> object:
    raise _InputError("non-finite JSON number")


def _parse_json(raw: bytes, label: str) -> object:
    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _InputError(f"{label} is invalid UTF-8 JSON") from exc


def _object(value: object, label: str) -> JsonObject:
    if not isinstance(value, dict):
        raise _InputError(f"{label} must be a JSON object")
    return cast(JsonObject, value)


def _array(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise _InputError(f"{label} must be a JSON array")
    return cast(list[object], value)


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise _InputError(f"{label} must be an integer >= {minimum}")
    return value


def _number(value: object, label: str, *, nullable: bool) -> float | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _InputError(f"{label} must be a finite number" + (" or null" if nullable else ""))
    result = float(value)
    if not math.isfinite(result):
        raise _InputError(f"{label} must be finite")
    return result


def _timestamp(value: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _InputError("timestamp must be a string or null")
    match = _TIMESTAMP.fullmatch(value)
    if match is None:
        raise _InputError("timestamp must use HH:MM:SS.cc on 100 ms ticks")
    hour, minute, second, centisecond = (int(part) for part in match.groups())
    if centisecond % 10:
        raise _InputError("timestamp is not on a 100 ms source tick")
    return ((hour * 60 + minute) * 60 + second) * 10 + centisecond // 10


def _period_number(value: object, label: str) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value in {1, 2}:
        return value
    if not isinstance(value, str):
        raise _InputError(f"{label} has an unsupported period label")
    normalized = re.sub(r"[^a-z0-9]", "", value.lower())
    aliases = {
        "1": 1,
        "1h": 1,
        "1sthalf": 1,
        "firsthalf": 1,
        "period1": 1,
        "2": 2,
        "2h": 2,
        "2ndhalf": 2,
        "secondhalf": 2,
        "period2": 2,
    }
    if normalized not in aliases:
        raise _InputError(f"{label} has an unsupported period label")
    return aliases[normalized]


def _authority_object(path: Path) -> JsonObject:
    return _object(_parse_json(path.read_bytes(), path.name), path.name)


def _load_contract() -> tuple[tuple[tuple[str, str], ...], JsonObject]:
    source = _authority_object(_SOURCE_AUTHORITY)
    state = _authority_object(_STATE_AUTHORITY)
    policy = _authority_object(_POLICY_AUTHORITY)
    protocol = _authority_object(_PROTOCOL_AUTHORITY)
    plan = _authority_object(_PLAN_AUTHORITY)
    population_schema_bytes = _POPULATION_SCHEMA.read_bytes()
    result_schema_bytes = _RESULT_SCHEMA.read_bytes()
    scientific_state = _object(state.get("scientific_state"), "measurement scientific_state")
    scientific_policy = _object(policy.get("scientific_policy"), "eligibility scientific_policy")
    protocol_state = _object(protocol.get("scientific_state"), "protocol scientific_state")
    expected_hashes = (
        ("source_release_hash", source.get("source_release_hash"), SOURCE_RELEASE_HASH),
        ("source_population_hash", source.get("source_population_hash"), SOURCE_POPULATION_HASH),
        ("measurement_hash", _digest(scientific_state), MEASUREMENT_HASH),
        ("eligibility_hash", _digest(scientific_policy), ELIGIBILITY_HASH),
        ("protocol_hash", _digest(protocol_state), PROTOCOL_HASH),
        ("plan_hash", plan.get("plan_sha256"), PLAN_HASH),
        ("population_schema_hash", _digest_bytes(population_schema_bytes), POPULATION_SCHEMA_HASH),
        ("result_schema_hash", _digest_bytes(result_schema_bytes), RESULT_SCHEMA_HASH),
    )
    for label, actual, expected in expected_hashes:
        if actual != expected:
            raise _InputError(f"frozen authority drift: {label}")
    plan_payload = {key: value for key, value in plan.items() if key != "plan_sha256"}
    if _digest(plan_payload) != PLAN_HASH:
        raise _InputError("frozen authority drift: plan bytes")

    source_ids = _array(source.get("selected_source_matches"), "selected source matches")
    if len(source_ids) != 20 or any(
        isinstance(value, bool) or not isinstance(value, int) for value in source_ids
    ):
        raise _InputError("frozen source authority does not contain the exact 20-match set")
    source_integer_ids = cast(list[int], source_ids)
    if _digest(sorted(source_integer_ids)) != SOURCE_POPULATION_HASH:
        raise _InputError("frozen source population hash does not match its 20 IDs")

    split = _object(protocol_state.get("split"), "protocol split")
    protocol_ids = _array(split.get("population_match_ids"), "protocol population IDs")
    if tuple(protocol_ids) != tuple(str(value) for value in source_integer_ids):
        raise _InputError("protocol and source authority match IDs differ")
    rank_order = sorted(
        (str(match_id) for match_id in source_integer_ids),
        key=lambda match_id: hashlib.sha256(
            f"FPDBench prospective/v1/match/{match_id}".encode()
        ).digest(),
    )
    role_ids = {
        "training": tuple(sorted(rank_order[:12], key=int)),
        "validation": tuple(sorted(rank_order[12:16], key=int)),
        "evaluation": tuple(sorted(rank_order[16:], key=int)),
    }
    declared_roles = _object(split.get("roles"), "protocol roles")
    for role, ids in role_ids.items():
        declared = _array(declared_roles.get(role), f"protocol {role} match IDs")
        if not all(isinstance(match_id, str) for match_id in declared):
            raise _InputError("frozen protocol roles must contain string match IDs")
        if tuple(cast(list[str], declared)) != ids:
            raise _InputError("recomputed 12/4/4 role assignment differs from frozen protocol")
    role_order = tuple((role, match_id) for role, ids in role_ids.items() for match_id in ids)
    return role_order, {
        "source": source,
        "measurement": state,
        "eligibility": policy,
        "protocol": protocol,
        "plan": plan,
        "population_schema_sha256": POPULATION_SCHEMA_HASH,
        "result_schema_sha256": RESULT_SCHEMA_HASH,
        "role_assignment_sha256": split.get("role_assignment_sha256"),
    }


def _parse_tracking(raw: bytes) -> tuple[JsonObject, ...]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _InputError("tracking JSONL is not UTF-8") from exc
    lines = text.splitlines()
    if not lines or any(not line.strip() for line in lines):
        raise _InputError("tracking JSONL must contain non-empty records only")
    result: list[JsonObject] = []
    prior_frame: int | None = None
    prior_period: int | None = None
    prior_time: int | None = None
    for line in lines:
        record = _object(_parse_json(line.encode("utf-8"), "tracking row"), "tracking row")
        frame = _integer(record.get("frame"), "tracking frame")
        period_raw = record.get("period")
        period = None if period_raw is None else _integer(period_raw, "tracking period", minimum=1)
        if period is not None and period not in {1, 2}:
            raise _InputError("tracking period must be 1, 2, or null")
        timestamp = _timestamp(record.get("timestamp"))
        if prior_frame is not None:
            if frame <= prior_frame:
                raise _InputError("tracking frames are duplicate or non-monotonic")
            if (
                period is not None
                and period == prior_period
                and timestamp is not None
                and prior_time is not None
            ):
                if timestamp - prior_time != frame - prior_frame:
                    raise _InputError("source frame and timestamp increments disagree")
        prior_frame, prior_period, prior_time = frame, period, timestamp
        result.append(record)
    return tuple(result)


def _parse_match(source: MatchSourceBytesV2) -> MatchContext:
    if not re.fullmatch(r"[1-9][0-9]*", source.match_id):
        raise _InputError("match input ID is not a positive decimal string")
    metadata = _object(_parse_json(source.metadata_json, "match metadata"), "match metadata")
    if str(metadata.get("id")) != source.match_id:
        raise _InputError("metadata match ID differs from the input identity")
    home_team = _object(metadata.get("home_team"), "home team")
    away_team = _object(metadata.get("away_team"), "away team")
    home_id = _integer(home_team.get("id"), "home team ID", minimum=1)
    away_id = _integer(away_team.get("id"), "away team ID", minimum=1)
    if home_id == away_id:
        raise _InputError("home and away team IDs must differ")
    length = _number(metadata.get("pitch_length"), "pitch length", nullable=False)
    width = _number(metadata.get("pitch_width"), "pitch width", nullable=False)
    assert length is not None and width is not None
    if length <= 0 or width <= 0:
        raise _InputError("pitch dimensions must be positive")

    period_rows = _array(metadata.get("match_periods"), "match_periods")
    periods: list[PeriodBounds] = []
    for item in period_rows:
        row = _object(item, "match period")
        period = _period_number(row.get("name"), "match period name")
        start = _integer(row.get("start_frame"), "period start frame")
        end = _integer(row.get("end_frame"), "period end frame")
        if start >= end:
            raise _InputError("period bounds must be non-empty half-open intervals")
        if (
            "duration_frames" in row
            and _integer(row["duration_frames"], "period duration") != end - start
        ):
            raise _InputError("period duration does not match its half-open bounds")
        periods.append(PeriodBounds(period, start, end))
    periods.sort(key=lambda value: (value.start_frame, value.period))
    if not periods or len({item.period for item in periods}) != len(periods):
        raise _InputError("period bounds are missing or duplicated")
    for left, right in zip(periods[:-1], periods[1:], strict=True):
        if right.start_frame < left.end_frame:
            raise _InputError("match period bounds overlap")

    roster_rows = _array(metadata.get("players"), "match roster")
    roster: list[RosterPlayer] = []
    roster_ids: set[int] = set()
    identity_conflict = False
    roster_complete = True
    for item in roster_rows:
        row = _object(item, "roster player")
        player_id = _integer(row.get("id"), "roster player ID", minimum=1)
        team_id = _integer(row.get("team_id"), "roster team ID", minimum=1)
        team: Literal["home", "away"] | None = (
            "home" if team_id == home_id else "away" if team_id == away_id else None
        )
        if player_id in roster_ids or team is None:
            identity_conflict = True
        roster_ids.add(player_id)
        playing = row.get("playing_time")
        playing_object = (
            _object(cast(object, playing), "playing_time") if isinstance(playing, dict) else None
        )
        raw_by_period = None if playing_object is None else playing_object.get("by_period")
        intervals: list[tuple[int, int, int]] = []
        if not isinstance(raw_by_period, list):
            roster_complete = False
            parsed_intervals: tuple[tuple[int, int, int], ...] | None = None
        else:
            parsed_intervals = ()
            for interval_value in cast(list[object], raw_by_period):
                interval = _object(interval_value, "player participation interval")
                try:
                    interval_period = _period_number(interval.get("name"), "participation period")
                    start = _integer(interval.get("start_frame"), "participation start")
                    end = _integer(interval.get("end_frame"), "participation end")
                except _InputError:
                    roster_complete = False
                    continue
                if end < start:
                    roster_complete = False
                    continue
                intervals.append((interval_period, start, end))
            parsed_intervals = tuple(intervals)
        roster.append(RosterPlayer(player_id, team_id, team, parsed_intervals))
    roster.sort(key=lambda value: value.player_id)

    phase_value = _array(
        _parse_json(source.phase_intervals_json, "phase intervals"), "phase intervals"
    )
    phases: list[tuple[int, int, int]] = []
    for item in phase_value:
        row = _object(item, "phase interval")
        if set(row) != {"period", "frame_start", "frame_end"}:
            raise _InputError("normalized phase interval fields are not canonical")
        phase = _integer(row.get("period"), "phase period", minimum=1)
        if phase not in {1, 2}:
            raise _InputError("normalized phase period must be 1 or 2")
        start = _integer(row.get("frame_start"), "phase start frame")
        end = _integer(row.get("frame_end"), "phase end frame")
        if start >= end:
            raise _InputError("phase intervals must be non-empty half-open spans")
        phases.append((phase, start, end))
    phases.sort()
    if len(set(phases)) != len(phases):
        raise _InputError("duplicate phase interval")
    for previous, current in zip(phases[:-1], phases[1:], strict=True):
        if current[0] == previous[0] and current[1] < previous[2]:
            raise _InputError("phase intervals overlap")

    records = _parse_tracking(source.tracking_jsonl)
    parsed_rows: list[
        tuple[
            int,
            int | None,
            int | None,
            tuple[PlayerObservation, ...],
            BallObservation | None,
            PossessionObservation | None,
        ]
    ] = []
    roster_by_id = {item.player_id: item for item in roster}
    for record in records:
        if not {"frame", "timestamp", "period", "player_data", "ball_data", "possession"} <= set(
            record
        ):
            raise _InputError("tracking row omits a required field")
        frame = _integer(record.get("frame"), "tracking frame")
        period_raw = record.get("period")
        period = None if period_raw is None else _integer(period_raw, "tracking period", minimum=1)
        if period is not None and period not in {1, 2}:
            raise _InputError("tracking period must be 1, 2, or null")
        timestamp = _timestamp(record.get("timestamp"))
        player_rows = _array(record.get("player_data"), "player_data")
        players: list[PlayerObservation] = []
        for raw_player in player_rows:
            player = _object(raw_player, "player observation")
            if not {"player_id", "x", "y", "is_detected"} <= set(player):
                raise _InputError("player observation omits a required field")
            player_id = _integer(player.get("player_id"), "observed player ID", minimum=1)
            x = _number(player.get("x"), "player x", nullable=True)
            y = _number(player.get("y"), "player y", nullable=True)
            detected = player.get("is_detected")
            if not isinstance(detected, bool):
                raise _InputError("player is_detected must be Boolean")
            roster_player = roster_by_id.get(player_id)
            players.append(
                PlayerObservation(
                    player_id,
                    x,
                    y,
                    detected,
                    None if roster_player is None else roster_player.team_id,
                    None if roster_player is None else roster_player.team,
                )
            )
        ball_raw = record.get("ball_data")
        ball: BallObservation | None
        if ball_raw is None:
            ball = None
        else:
            ball_obj = _object(ball_raw, "ball_data")
            if set(ball_obj) != {"x", "y", "z", "is_detected"}:
                raise _InputError("ball_data fields differ from the frozen measurement contract")
            x = _number(ball_obj.get("x"), "ball x", nullable=True)
            y = _number(ball_obj.get("y"), "ball y", nullable=True)
            _number(ball_obj.get("z"), "ball z", nullable=True)
            detected_raw = ball_obj.get("is_detected")
            if detected_raw is not None and not isinstance(detected_raw, bool):
                raise _InputError("ball is_detected must be true, false, or null")
            ball = BallObservation(x, y, detected_raw)
        possession_raw = record.get("possession")
        possession: PossessionObservation | None
        if possession_raw is None:
            possession = None
        else:
            possession_obj = _object(possession_raw, "possession")
            if set(possession_obj) != {"group", "player_id"}:
                raise _InputError("possession fields differ from the retained auxiliary contract")
            group_raw = possession_obj.get("group")
            if group_raw not in {"home team", "away team", None}:
                raise _InputError("possession group is not home, away, or null")
            possession_player = possession_obj.get("player_id")
            if possession_player is not None:
                possession_player = _integer(possession_player, "possession player ID", minimum=1)
            possession = PossessionObservation(cast(str | None, group_raw), possession_player)
        parsed_rows.append((frame, period, timestamp, tuple(players), ball, possession))

    # Sampling uses the absolute source-frame parity; period boundaries do not reset it.
    samples = tuple(
        CanonicalSample(frame, frame // 2, period, timestamp, players, ball, possession)
        for frame, period, timestamp, players, ball, possession in parsed_rows
        if frame % 2 == 0
    )
    retained_rows: list[JsonObject] = []
    for sample in samples:
        player_values = [
            {
                "player_id": player.player_id,
                "team_id": player.team_id,
                "team": player.team,
                "x_m": player.x,
                "y_m": player.y,
                "is_detected": player.detected,
            }
            for player in sorted(sample.players, key=lambda value: value.player_id)
        ]
        ball_value = (
            None
            if sample.ball is None
            else {
                "x_m": sample.ball.x,
                "y_m": sample.ball.y,
                "is_detected": sample.ball.detected,
            }
        )
        possession_value = (
            None
            if sample.possession is None
            else {
                "group": sample.possession.group,
                "player_id": sample.possession.player_id,
            }
        )
        retained_rows.append(
            {
                "match_id": source.match_id,
                "source_frame": sample.source_frame,
                "canonical_sample_index": sample.canonical_sample_index,
                "period": sample.period,
                "timestamp_deciseconds": sample.timestamp_deciseconds,
                "home_team_id": home_id,
                "away_team_id": away_id,
                "pitch_length_m": length,
                "pitch_width_m": width,
                "players": player_values,
                "ball": ball_value,
                "possession": possession_value,
            }
        )
    retained_samples_sha256 = _digest_bytes(
        b"".join(canonical_bytes(row) + b"\n" for row in retained_rows)
    )
    return MatchContext(
        source.match_id,
        home_id,
        away_id,
        length,
        width,
        tuple(periods),
        tuple(roster),
        roster_complete,
        identity_conflict,
        tuple(phases),
        samples,
        len(parsed_rows),
        sum(row[0] % 2 == 0 for row in parsed_rows),
        sum(row[0] % 2 == 1 for row in parsed_rows),
        retained_samples_sha256,
    )


def _active_roster(context: MatchContext, sample: CanonicalSample) -> frozenset[int] | None:
    if not context.roster_complete or sample.period is None:
        return None
    active: set[int] = set()
    for player in context.roster:
        if player.intervals is None:
            return None
        if any(
            period == sample.period and start <= sample.source_frame <= end
            for period, start, end in player.intervals
        ):
            active.add(player.player_id)
    return frozenset(active)


def _role_periods(context: MatchContext) -> tuple[PeriodBounds, ...]:
    return context.periods


def _enumerate(context: MatchContext, role: str) -> tuple[list[OriginCandidate], list[JsonObject]]:
    samples = context.samples_by_index
    candidates: list[OriginCandidate] = []
    census: list[JsonObject] = []
    for period_bounds in _role_periods(context):
        first_even = period_bounds.start_frame + period_bounds.start_frame % 2
        for frame in range(first_even, period_bounds.end_frame, 2):
            sample_index = frame // 2
            support_indices = range(sample_index - 25, sample_index + 16)
            observed_support = [samples.get(index) for index in support_indices]
            origin = samples.get(sample_index)
            support_complete = origin is not None and all(
                sample is not None for sample in observed_support
            )
            census.append(
                {
                    "role": role,
                    "match_id": context.match_id,
                    "period": period_bounds.period,
                    "canonical_sample_index": sample_index,
                    "origin_observed": origin is not None,
                    "support_complete": support_complete,
                    "candidate": support_complete,
                }
            )
            if support_complete:
                candidates.append(
                    OriginCandidate(
                        role,
                        context.match_id,
                        period_bounds.period,
                        sample_index,
                        cast(tuple[CanonicalSample, ...], tuple(observed_support)),
                    )
                )
    return candidates, census


def _covered(context: MatchContext, period: int, frame: int) -> bool:
    return any(
        interval_period == period and start <= frame < end
        for interval_period, start, end in context.phases
    )


def _within_pitch(x: float, y: float, length: float, width: float) -> bool:
    return abs(x) <= length / 2 and abs(y) <= width / 2


def _displacement_speed(left: XY, right: XY) -> float:
    return math.hypot(right[0] - left[0], right[1] - left[1]) / 0.2


def _issue_dict(codes: set[str]) -> list[JsonObject]:
    return [{"code": code} for code in sorted(codes)]


def _ball_state(ball: BallObservation | None) -> tuple[str, str]:
    if ball is None:
        return ("object_absent", "object_absent_not_applicable")
    if ball.x is not None and ball.y is not None:
        coordinate = "both_finite"
    elif ball.x is not None:
        coordinate = "x_only"
    elif ball.y is not None:
        coordinate = "y_only"
    else:
        coordinate = "both_null"
    flag = "null" if ball.detected is None else "true" if ball.detected else "false"
    return coordinate, flag


def _assess_candidate(context: MatchContext, origin: OriginCandidate) -> JsonObject:
    exclusions: set[str] = set()
    warnings: set[str] = {"SOURCE_QUALITY_UNKNOWN"}
    support = origin.support
    expected_indices = tuple(range(origin.sample_index - 25, origin.sample_index + 16))
    if len(support) != 41:
        exclusions.add("WINDOW_SUPPORT_LENGTH_MISMATCH")

    periods = {sample.period for sample in support}
    if None in periods or len(periods) != 1:
        exclusions.add("PERIOD_BOUNDARY_CROSSED")
    actual_period = next(iter(periods)) if len(periods) == 1 else None
    for sample, expected_index in zip(support, expected_indices, strict=True):
        if (
            sample.canonical_sample_index != expected_index
            or sample.source_frame != expected_index * 2
        ):
            exclusions.add("CANONICAL_FRAME_MISMATCH")
        if sample.period is None:
            exclusions.add("PERIOD_BOUNDS_MISSING")
            continue
        bound_matches = [item for item in context.periods if item.period == sample.period]
        if not bound_matches:
            exclusions.add("PERIOD_BOUNDS_MISSING")
        elif len(bound_matches) > 1:
            exclusions.add("PERIOD_BOUNDS_DUPLICATE")
        else:
            bounds = bound_matches[0]
            if bounds.start_frame >= bounds.end_frame:
                exclusions.add("PERIOD_BOUNDS_INVALID")
            if not bounds.start_frame <= sample.source_frame < bounds.end_frame:
                exclusions.add("OUTSIDE_PERIOD_BOUNDS")
    if actual_period is not None and actual_period != origin.period:
        exclusions.add("OUTSIDE_PERIOD_BOUNDS")
    period_frames = range(support[0].source_frame, support[-1].source_frame + 1)

    def phase_covers_frame(frame: int) -> bool:
        expected_period = next(
            (
                bounds.period
                for bounds in context.periods
                if bounds.start_frame <= frame < bounds.end_frame
            ),
            None,
        )
        return expected_period is not None and _covered(context, expected_period, frame)

    if any(not phase_covers_frame(frame) for frame in period_frames):
        exclusions.add("PHASE_NOT_IN_PLAY_OR_UNKNOWN")

    temporal_intervals = 0
    for left, right in zip(support[:-1], support[1:], strict=True):
        if left.period is not None and left.period == right.period:
            if (
                right.canonical_sample_index == left.canonical_sample_index + 1
                and right.source_frame == left.source_frame + 2
            ):
                if left.timestamp_deciseconds is None or right.timestamp_deciseconds is None:
                    exclusions.add("TIMESTAMP_MISSING")
                elif right.timestamp_deciseconds - left.timestamp_deciseconds != 2:
                    exclusions.add("TIMESTAMP_DISCONTINUITY")
                else:
                    temporal_intervals += 1
            else:
                exclusions.add("TEMPORAL_GAP")
        else:
            exclusions.add("PERIOD_BOUNDARY_CROSSED")
    if any(sample.timestamp_deciseconds is None for sample in support):
        exclusions.add("TIMESTAMP_MISSING")

    ball_coords = Counter[str]()
    ball_flags = Counter[str]()
    finite_ball: list[XY | None] = []
    ball_finite_count = 0
    ball_true = 0
    ball_false = 0
    ball_unknown = 0
    ball_absent = 0
    ball_partial = 0
    ball_missing = 0
    ball_outside = 0
    ball_outliers = 0
    for sample in support:
        coordinate_state, flag_state = _ball_state(sample.ball)
        ball_coords[coordinate_state] += 1
        ball_flags[flag_state] += 1
        if sample.ball is None:
            ball_absent += 1
            warnings.add("BALL_OBJECT_ABSENT")
            finite_ball.append(None)
            continue
        ball = sample.ball
        if ball.detected is True:
            ball_true += 1
        elif ball.detected is False:
            ball_false += 1
        else:
            ball_unknown += 1
            warnings.add("BALL_DETECTION_UNKNOWN")
        if ball.xy is None:
            finite_ball.append(None)
            if ball.x is None and ball.y is None:
                ball_missing += 1
                warnings.add("BALL_COORDINATES_MISSING")
            else:
                ball_partial += 1
                warnings.add("BALL_COORDINATES_PARTIAL")
            continue
        point = ball.xy
        finite_ball.append(point)
        ball_finite_count += 1
        if not _within_pitch(point[0], point[1], context.pitch_length_m, context.pitch_width_m):
            ball_outside += 1
            warnings.add("BALL_OUTSIDE_PITCH")
        if abs(point[0]) > 2 * context.pitch_length_m or abs(point[1]) > 2 * context.pitch_width_m:
            exclusions.add("COORDINATE_IMPLAUSIBLE")
    origin_ball = support[25].ball
    if origin_ball is None or origin_ball.xy is None:
        exclusions.add("BALL_MISSING_AT_ORIGIN")
    if ball_finite_count < 39:
        exclusions.add("BALL_COVERAGE_BELOW_MINIMUM")
    for left, right in zip(finite_ball[:-1], finite_ball[1:], strict=True):
        if left is not None and right is not None and _displacement_speed(left, right) > 50:
            ball_outliers += 1
            warnings.add("BALL_DISPLACEMENT_OUTLIER")

    player_detection = Counter[str]()
    player_coordinate_missing = 0
    player_observation_missing = 0
    player_outside = 0
    player_outliers = 0
    active_expected = 0
    active_finite = 0
    minimum_per_team = {"home": 41, "away": 41}
    player_points: list[dict[int, XY | None]] = []
    previous_active: frozenset[int] | None = None
    transition_count = 0
    null_coordinate_count = 0
    observed_player_count = 0
    if not context.roster_complete:
        warnings.add("PLAYER_APPEARANCE_METADATA_UNKNOWN")
    if context.roster_identity_conflict:
        exclusions.add("PLAYER_TEAM_IDENTITY_CONFLICT")
    for sample in support:
        active = _active_roster(context, sample)
        if active is None:
            active = None
        elif previous_active is not None and active != previous_active:
            transition_count += 1
            warnings.add("IDENTITY_TRANSITION_EXPOSURE")
        if active is not None:
            previous_active = active
            active_expected += len(active)
        present_ids = {player.player_id for player in sample.players}
        if active is not None and active - present_ids:
            player_observation_missing += len(active - present_ids)
            warnings.add("PLAYER_OBSERVATION_MISSING")
        points: dict[int, XY | None] = {}
        per_team: dict[str, set[int]] = {"home": set(), "away": set()}
        finite_active_ids: set[int] = set()
        for player in sample.players:
            observed_player_count += 1
            point = player.xy
            points[player.player_id] = point
            if point is None:
                null_coordinate_count += 1
                player_coordinate_missing += 1
                warnings.add("PLAYER_COORDINATES_MISSING")
            else:
                player_detection["detected" if player.detected else "extrapolated"] += 1
                if not _within_pitch(
                    point[0], point[1], context.pitch_length_m, context.pitch_width_m
                ):
                    player_outside += 1
                    warnings.add("PLAYER_POSITION_OUTSIDE_PITCH")
                if abs(point[0]) > context.pitch_length_m or abs(point[1]) > context.pitch_width_m:
                    exclusions.add("COORDINATE_IMPLAUSIBLE")
            roster_player = context.roster_by_id.get(player.player_id)
            if roster_player is None or roster_player.team is None:
                exclusions.add("PLAYER_TEAM_IDENTITY_CONFLICT")
                continue
            is_active = active is None or player.player_id in active
            if not is_active:
                warnings.add("PLAYER_OUTSIDE_APPEARANCE")
                continue
            if point is not None:
                per_team[roster_player.team].add(player.player_id)
                if active is not None:
                    finite_active_ids.add(player.player_id)
        if len(present_ids) != len(sample.players):
            exclusions.add("DUPLICATE_PLAYER_ID")
        for team_name in ("home", "away"):
            minimum_per_team[team_name] = min(minimum_per_team[team_name], len(per_team[team_name]))
            if len(per_team[team_name]) < 7:
                exclusions.add("PLAYER_COUNT_BELOW_TEAM_MINIMUM")
        active_finite += len(finite_active_ids)
        player_points.append(points)
    for left, right in zip(player_points[:-1], player_points[1:], strict=True):
        for player_id in left.keys() & right.keys():
            left_xy = left[player_id]
            right_xy = right[player_id]
            if (
                left_xy is not None
                and right_xy is not None
                and _displacement_speed(left_xy, right_xy) > 12
            ):
                player_outliers += 1
                warnings.add("PLAYER_DISPLACEMENT_OUTLIER")

    possession_counts = Counter[str]()
    possession_unknown = 0
    possession_unobserved = 0
    for sample in support:
        if sample.possession is None or sample.possession.group is None:
            possession_counts["unknown"] += 1
            possession_unknown += 1
            warnings.add("POSSESSION_CONTEXT_UNKNOWN")
            continue
        category = "home" if sample.possession.group == "home team" else "away"
        possession_counts[category] += 1
        if sample.possession.player_id is not None and sample.possession.player_id not in {
            player.player_id for player in sample.players
        }:
            possession_unobserved += 1
            warnings.add("POSSESSION_PLAYER_UNOBSERVED")

    known_ball_flags = ball_true + ball_false
    known_coverage = known_ball_flags / 41
    detected_share = ball_true / known_ball_flags if known_ball_flags else None
    finite_unknown_flag = any(
        sample.ball is not None and sample.ball.xy is not None and sample.ball.detected is None
        for sample in support
    )
    finite_ball_flags = [
        sample.ball.detected
        for sample in support
        if sample.ball is not None and sample.ball.xy is not None
    ]
    if not ball_finite_count or finite_unknown_flag:
        ball_exposure = "unknown"
    elif all(flag is True for flag in finite_ball_flags):
        ball_exposure = "all_detected"
    elif all(flag is False for flag in finite_ball_flags):
        ball_exposure = "all_false_flag"
    else:
        ball_exposure = "mixed"
    player_finite_count = sum(player_detection.values())
    if player_finite_count == 0:
        player_exposure = "unknown"
    elif player_detection["detected"] == player_finite_count:
        player_exposure = "all_detected"
    elif player_detection["extrapolated"] == player_finite_count:
        player_exposure = "all_extrapolated"
    else:
        player_exposure = "mixed"
    phase_frames = support[-1].source_frame - support[0].source_frame + 1
    phase_covered = sum(phase_covers_frame(frame) for frame in period_frames)
    completeness = active_finite / active_expected if active_expected else None
    possession_fraction = {key: possession_counts[key] / 41 for key in ("home", "away", "unknown")}
    quality: JsonObject = {
        "player_detection_exposure": {
            "state": player_exposure,
            "detected_positions": player_detection["detected"],
            "extrapolated_positions": player_detection["extrapolated"],
            "finite_positions": player_finite_count,
        },
        "ball_detection_exposure": {
            "state": ball_exposure,
            "true_flags": ball_true,
            "false_flags": ball_false,
            "unknown_flags": ball_unknown,
            "known_flag_coverage": known_coverage,
            "detected_share_among_known_flags": detected_share,
        },
        "player_completeness": {
            "state": "unknown"
            if completeness is None
            else "complete"
            if active_finite == active_expected
            else "partial",
            "finite_active_player_frames": active_finite,
            "expected_active_player_frames": active_expected if context.roster_complete else None,
            "fraction": completeness if context.roster_complete else None,
            "valid_minimum_per_team": minimum_per_team,
        },
        "ball_completeness": {
            "finite_positions": ball_finite_count,
            "expected_slots": 41,
            "fraction": ball_finite_count / 41,
            "coordinate_states": dict(sorted(ball_coords.items())),
            "flag_states": dict(sorted(ball_flags.items())),
        },
        "temporal_continuity": {
            "continuous_intervals": temporal_intervals,
            "expected_intervals": 40,
            "fraction": temporal_intervals / 40,
        },
        "identity_transition_exposure": {
            "transition_intervals": transition_count,
            "expected_intervals": 40 if context.roster_complete else None,
            "fraction": transition_count / 40 if context.roster_complete else None,
        },
        "source_quality_uncertainty": {"state": "unknown"},
        "play_context": {
            "phase_covered_source_frames": phase_covered,
            "phase_expected_source_frames": phase_frames,
            "phase_coverage_fraction": phase_covered / phase_frames,
            "possession_counts": dict(sorted(possession_counts.items())),
            "possession_fractions": possession_fraction,
            "possession_unknown_samples": possession_unknown,
            "possession_player_unobserved_samples": possession_unobserved,
        },
        "coordinate_quality": {
            "player_outside_pitch_positions": player_outside,
            "ball_outside_pitch_positions": ball_outside,
            "ball_displacement_outliers": ball_outliers,
            "player_displacement_outliers": player_outliers,
            "player_null_coordinate_records": null_coordinate_count,
            "player_observation_missing_active_frames": player_observation_missing,
            "player_null_coordinate_fraction": null_coordinate_count / observed_player_count
            if observed_player_count
            else None,
        },
    }
    result: JsonObject = {
        "status": "UNQUALIFIED",
        "candidate_rules_pass": not exclusions,
        "exclusions": _issue_dict(exclusions),
        "warnings": _issue_dict(warnings),
        "quality": quality,
        "eligibility_policy_hash": ELIGIBILITY_HASH,
        "measurement_state_hash": MEASUREMENT_HASH,
    }
    return result


def _window_id(match_id: str, origin_sample_id: str) -> str:
    return _digest(
        {
            "schema_id": "fpdbench.prospective-window",
            "schema_version": "2.0.0",
            "match_id": match_id,
            "origin_sample_id": origin_sample_id,
            "source_release_hash": SOURCE_RELEASE_HASH,
            "measurement_state_hash": MEASUREMENT_HASH,
            "eligibility_policy_hash": ELIGIBILITY_HASH,
            "protocol_sha256": PROTOCOL_HASH,
        }
    )


def _truth_rows(samples: tuple[tuple[XY | None, ...], ...]) -> list[list[list[str] | None]]:
    return [
        [
            None if point is None else [float(point[0]).hex(), float(point[1]).hex()]
            for point in step
        ]
        for step in samples
    ]


def _truth_digest(samples: tuple[tuple[XY | None, ...], ...], representation: str) -> str:
    return _digest(
        {
            "schema_id": "fpdbench.prospective-truth-panel",
            "schema_version": "1.1.0",
            "target_representation": representation,
            "samples": _truth_rows(samples),
        }
    )


def _mask_digest(mask: tuple[tuple[bool, ...], ...]) -> str:
    return _digest(
        {
            "schema_id": "fpdbench.prospective-truth-mask",
            "schema_version": "1.0.0",
            "samples": [list(step) for step in mask],
        }
    )


def _make_scene(
    context: MatchContext, candidate: OriginCandidate, side: Literal["home", "away"]
) -> SceneTruthV2:
    origin_sample = candidate.support[25]
    origin_players = sorted(
        (
            player
            for player in origin_sample.players
            if player.team == side and player.xy is not None
        ),
        key=lambda item: item.player_id,
    )
    player_ids = tuple(player.player_id for player in origin_players)
    origin_xy = tuple(cast(XY, player.xy) for player in origin_players)
    sample_map = context.samples_by_index
    absolute_steps: list[tuple[XY | None, ...]] = []
    displacement_steps: list[tuple[XY | None, ...]] = []
    masks: list[tuple[bool, ...]] = []
    for future_index in range(candidate.sample_index + 1, candidate.sample_index + 16):
        sample = sample_map[future_index]
        by_id = {player.player_id: player for player in sample.players}
        abs_step: list[XY | None] = []
        displacement_step: list[XY | None] = []
        mask_step: list[bool] = []
        for player_id, anchor in zip(player_ids, origin_xy, strict=True):
            future = by_id.get(player_id)
            point = None if future is None else future.xy
            abs_step.append(point)
            mask_step.append(point is not None)
            displacement_step.append(
                None if point is None else (point[0] - anchor[0], point[1] - anchor[1])
            )
        absolute_steps.append(tuple(abs_step))
        displacement_steps.append(tuple(displacement_step))
        masks.append(tuple(mask_step))
    absolute = tuple(absolute_steps)
    displacement = tuple(displacement_steps)
    mask = tuple(masks)
    for step, disp_step, mask_values in zip(absolute, displacement, mask, strict=True):
        for point, delta, valid, anchor in zip(
            step, disp_step, mask_values, origin_xy, strict=True
        ):
            if valid != (point is not None) or valid != (delta is not None):
                raise _InputError("independent truth representations have different masks")
            if valid and point is not None and delta is not None:
                if not (
                    math.isclose(point[0], delta[0] + anchor[0], rel_tol=0.0, abs_tol=1e-12)
                    and math.isclose(point[1], delta[1] + anchor[1], rel_tol=0.0, abs_tol=1e-12)
                ):
                    raise _InputError("absolute and displacement truth are physically inconsistent")
    scoreable = any(mask[-1]) if mask else False
    return SceneTruthV2(
        side,
        player_ids,
        origin_xy,
        absolute,
        displacement,
        mask,
        _truth_digest(absolute, "absolute_xy"),
        _truth_digest(displacement, "origin_relative_displacement"),
        _mask_digest(mask),
        scoreable,
        None if scoreable else "NO_FINAL_TARGET",
    )


def _scene_manifest(scene: SceneTruthV2) -> JsonObject:
    return {
        "scene_id": scene.scene_id,
        "player_ids": [str(player_id) for player_id in scene.player_ids],
        "absolute_xy_truth_sha256": scene.absolute_digest,
        "displacement_truth_sha256": scene.displacement_digest,
        "truth_mask_sha256": scene.mask_digest,
    }


def _truth_scene_row(
    match_id: str, candidate: EvaluatedCandidate, scene: SceneTruthV2
) -> JsonObject:
    return {
        "role": candidate.origin.role,
        "match_id": match_id,
        "window_id": _window_id(match_id, candidate.origin.origin_sample_id),
        "origin_sample_id": candidate.origin.origin_sample_id,
        "scene_id": scene.scene_id,
        "player_ids": [str(value) for value in scene.player_ids],
        "origin_xy_m": [list(pair) for pair in scene.origin_xy],
        "absolute_xy_truth_m": [
            [None if pair is None else list(pair) for pair in step] for step in scene.absolute_xy
        ],
        "displacement_truth_m": [
            [None if pair is None else list(pair) for pair in step]
            for step in scene.displacement_xy
        ],
        "truth_mask": [list(step) for step in scene.mask],
        "absolute_xy_truth_sha256": scene.absolute_digest,
        "displacement_truth_sha256": scene.displacement_digest,
        "truth_mask_sha256": scene.mask_digest,
        "scoreable": scene.scoreable,
        "unscoreable_reason": scene.unscoreable_reason,
    }


def _jsonl_bytes(rows: tuple[JsonObject, ...] | list[JsonObject]) -> bytes:
    return b"".join(canonical_bytes(row) + b"\n" for row in rows)


def _derive(inputs: tuple[MatchSourceBytesV2, ...]) -> DerivationV2:
    role_order, _ = _load_contract()
    role_by_match = {match_id: role for role, match_id in role_order}
    expected_ids = set(role_by_match)
    input_ids = [item.match_id for item in inputs]
    if len(set(input_ids)) != len(input_ids):
        raise _InputError("duplicate match input")
    if set(input_ids) != expected_ids:
        raise _InputError("input set must contain exactly the pinned 20 matches")
    by_id = {item.match_id: item for item in inputs}
    ordered_inputs = tuple(by_id[match_id] for _, match_id in role_order)
    contexts = tuple(_parse_match(item) for item in ordered_inputs)

    drift_count = sum(
        1
        for context in contexts
        for sample in context.samples
        if sample.ball is not None and sample.ball.detected is None and sample.ball.xy is not None
    )
    if drift_count:
        grid_count = sum(
            len(
                range(
                    period.start_frame + period.start_frame % 2,
                    period.end_frame,
                    2,
                )
            )
            for context in contexts
            for period in context.periods
        )
        return DerivationV2(
            role_order,
            (),
            (),
            contexts,
            None,
            b"",
            b"",
            b"",
            {"status": "STOPPED", "stop_code": DRIFT_STOP_CODE, "drift_count": drift_count},
            0,
            0,
            grid_count,
            0,
            drift_count,
            DRIFT_STOP_CODE,
        )

    census_rows: list[JsonObject] = []
    origins: list[OriginCandidate] = []
    for context in contexts:
        candidates, census = _enumerate(context, role_by_match[context.match_id])
        origins.extend(candidates)
        census_rows.extend(census)
    evaluated: list[EvaluatedCandidate] = []
    candidate_rows: list[JsonObject] = []
    truth_rows: list[JsonObject] = []
    scoreable_windows = 0
    for origin in origins:
        context = next(item for item in contexts if item.match_id == origin.match_id)
        diagnostic = _assess_candidate(context, origin)
        digest = _digest(diagnostic)
        included = diagnostic["candidate_rules_pass"] is True
        scenes = (
            (_make_scene(context, origin, "home"), _make_scene(context, origin, "away"))
            if included
            else None
        )
        scoreable = bool(scenes and any(scene.scoreable for scene in scenes))
        if scoreable:
            scoreable_windows += 1
        item = EvaluatedCandidate(origin, diagnostic, digest, included, scenes, scoreable)
        evaluated.append(item)
        candidate_rows.append(
            {
                "role": origin.role,
                "match_id": origin.match_id,
                "origin_sample_id": origin.origin_sample_id,
                "diagnostic": diagnostic,
                "eligibility_result_sha256": digest,
            }
        )
        if scenes:
            truth_rows.extend(_truth_scene_row(origin.match_id, item, scene) for scene in scenes)

    per_match: dict[str, list[EvaluatedCandidate]] = {match_id: [] for _, match_id in role_order}
    for item in evaluated:
        per_match[item.origin.match_id].append(item)
    no_scoreable_matches = [
        match_id
        for _, match_id in role_order
        if not any(item.included and item.scoreable for item in per_match[match_id])
    ]
    eligible_count = sum(item.included for item in evaluated)
    candidate_origin_rows = [
        {"match_id": item.origin.match_id, "origin_sample_id": item.origin.origin_sample_id}
        for item in evaluated
    ]
    candidate_origin_digest = _digest(candidate_origin_rows)
    manifest_matches: list[JsonObject] = []
    for role, match_id in role_order:
        windows: list[JsonObject] = []
        for item in per_match[match_id]:
            if not item.included or item.scenes is None:
                continue
            window_id = _window_id(match_id, item.origin.origin_sample_id)
            windows.append(
                {
                    "window_id": window_id,
                    "origin_sample_id": item.origin.origin_sample_id,
                    "eligibility_result_sha256": item.eligibility_digest,
                    "scenes": [_scene_manifest(scene) for scene in item.scenes],
                }
            )
        manifest_matches.append({"role": role, "match_id": match_id, "windows": windows})

    manifest: JsonObject = {
        "schema_id": "fpdbench.prospective-evaluation-population",
        "schema_version": "2.0.0",
        "population_id": "skillcorner.prospective.conditional_motion.population_v2",
        "source_release_id": "skillcorner_open_data_v1",
        "source_release_version": "1.0.0",
        "source_release_hash": SOURCE_RELEASE_HASH,
        "source_population_hash": SOURCE_POPULATION_HASH,
        "measurement_state_id": "skillcorner_5hz_v2",
        "measurement_state_version": "2.0.0",
        "measurement_state_hash": MEASUREMENT_HASH,
        "eligibility_policy_id": "skillcorner_window_v2",
        "eligibility_policy_version": "2.0.0",
        "eligibility_policy_hash": ELIGIBILITY_HASH,
        "protocol_id": "skillcorner.prospective_conditional_motion",
        "protocol_version": "2.0.0",
        "protocol_sha256": PROTOCOL_HASH,
        "plan_id": "skillcorner.prospective_conditional_motion.execution",
        "plan_version": "2.0.0",
        "plan_sha256": PLAN_HASH,
        "ball_null_flag_finite_xy_count": 0,
        "candidate_window_count": len(evaluated),
        "eligible_window_count": eligible_count,
        "candidate_origin_population_sha256": candidate_origin_digest,
        "matches": manifest_matches,
    }
    manifest["membership_sha256"] = _digest(manifest_matches)
    manifest["manifest_sha256"] = _digest(manifest)
    if no_scoreable_matches:
        manifest_result: JsonObject | None = None
        receipt: JsonObject = {
            "status": "INCOMPLETE",
            "code": "NO_SCOREABLE_WINDOW_IN_REQUIRED_MATCH",
            "matches_without_scoreable_window": no_scoreable_matches,
            "candidate_window_count": len(evaluated),
            "eligible_window_count": eligible_count,
            "diagnostic_census_count": len(census_rows),
        }
    else:
        manifest_result = manifest
        receipt = {
            "status": "UNQUALIFIED",
            "qualification_status": "NOT_QUALIFIED",
            "source_release_hash": SOURCE_RELEASE_HASH,
            "source_population_hash": SOURCE_POPULATION_HASH,
            "measurement_state_hash": MEASUREMENT_HASH,
            "eligibility_policy_hash": ELIGIBILITY_HASH,
            "protocol_sha256": PROTOCOL_HASH,
            "plan_sha256": PLAN_HASH,
            "candidate_window_count": len(evaluated),
            "eligible_window_count": eligible_count,
            "candidate_origin_population_sha256": candidate_origin_digest,
            "diagnostic_census_count": len(census_rows),
            "scoreable_window_count": scoreable_windows,
            "membership_sha256": manifest["membership_sha256"],
            "manifest_sha256": manifest["manifest_sha256"],
        }
    candidate_payload = _jsonl_bytes(candidate_rows)
    census_payload = _jsonl_bytes(census_rows)
    truth_payload = _jsonl_bytes(truth_rows)
    if manifest_result is not None:
        input_by_id = {item.match_id: item for item in inputs}
        receipt["input_snapshots"] = [
            {
                "match_id": match_id,
                "field": field,
                "size_bytes": len(raw),
                "sha256": _digest_bytes(raw),
            }
            for _, match_id in role_order
            for field, raw in (
                ("metadata_json", input_by_id[match_id].metadata_json),
                ("tracking_jsonl", input_by_id[match_id].tracking_jsonl),
                ("phase_intervals_json", input_by_id[match_id].phase_intervals_json),
            )
        ]
        receipt["retained_sample_snapshots"] = [
            {
                "match_id": context.match_id,
                "raw_source_frames": context.raw_source_frames,
                "even_source_frames": context.even_source_frames,
                "odd_source_frames": context.odd_source_frames,
                "retained_samples": len(context.samples),
                "retained_samples_sha256": context.retained_samples_sha256,
            }
            for context in contexts
        ]
        source_scan = Counter[str]()
        match_source_scan: list[JsonObject] = []
        for context in contexts:
            local = Counter[str]()
            for sample in context.samples:
                if sample.ball is None:
                    local["absent_object"] += 1
                    continue
                ball = sample.ball
                if ball.detected is True:
                    local["true_flags"] += 1
                elif ball.detected is False:
                    local["false_flags"] += 1
                else:
                    local["null_flags"] += 1
                if ball.xy is not None:
                    local["finite_xy"] += 1
                elif ball.x is not None or ball.y is not None:
                    local["partial_xy"] += 1
                else:
                    local["both_null_xy"] += 1
            source_scan.update(local)
            match_source_scan.append(
                {
                    "match_id": context.match_id,
                    "retained_samples": len(context.samples),
                    "ball_counts": dict(sorted(local.items())),
                }
            )
        receipt["source_wide_scan_counts"] = {
            "retained_sample_count": sum(len(context.samples) for context in contexts),
            "ball_counts": dict(sorted(source_scan.items())),
            "ball_null_flag_finite_xy_count": drift_count,
            "matches": match_source_scan,
        }
        receipt["match_counts"] = [
            {
                "role": role,
                "match_id": match_id,
                "diagnostic_grid_count": sum(row["match_id"] == match_id for row in census_rows),
                "candidate_count": len(per_match[match_id]),
                "eligible_window_count": sum(item.included for item in per_match[match_id]),
                "directed_scene_count": 2 * sum(item.included for item in per_match[match_id]),
                "scoreable_window_count": sum(
                    item.included and item.scoreable for item in per_match[match_id]
                ),
                "scoreable_scene_count": sum(
                    scene.scoreable
                    for item in per_match[match_id]
                    if item.included and item.scenes is not None
                    for scene in item.scenes
                ),
            }
            for role, match_id in role_order
        ]
        receipt["scoreable_scene_count"] = sum(
            scene.scoreable
            for item in evaluated
            if item.included and item.scenes is not None
            for scene in item.scenes
        )
        receipt["candidate_jsonl_sha256"] = _digest_bytes(candidate_payload)
        receipt["diagnostic_census_jsonl_sha256"] = _digest_bytes(census_payload)
        receipt["truth_jsonl_sha256"] = _digest_bytes(truth_payload)
        receipt["manifest_json_sha256"] = _digest_bytes(canonical_bytes(manifest))
        receipt["output_sha256"] = {
            "manifest_json": _digest_bytes(canonical_bytes(manifest)),
            "candidates_jsonl": _digest_bytes(candidate_payload),
            "diagnostic_census_jsonl": _digest_bytes(census_payload),
            "truth_jsonl": _digest_bytes(truth_payload),
        }
    return DerivationV2(
        role_order,
        tuple(evaluated),
        tuple(census_rows),
        contexts,
        manifest_result,
        candidate_payload,
        census_payload,
        truth_payload,
        receipt,
        len(evaluated),
        eligible_count,
        len(census_rows),
        scoreable_windows,
        drift_count,
        None,
    )


def _snapshot_inputs(
    inputs: tuple[MatchSourceBytesV2, ...], role_order: tuple[tuple[str, str], ...]
) -> tuple[InputSnapshotV2, ...]:
    by_id = {item.match_id: item for item in inputs}
    return tuple(
        InputSnapshotV2(match_id, field, len(raw), _digest_bytes(raw))
        for _, match_id in role_order
        for field, raw in (
            ("metadata_json", by_id[match_id].metadata_json),
            ("tracking_jsonl", by_id[match_id].tracking_jsonl),
            ("phase_intervals_json", by_id[match_id].phase_intervals_json),
        )
    )


def _submission_snapshots(
    submission: PopulationSubmissionV2 | None,
) -> tuple[ArtifactSnapshotV2, ...]:
    if submission is None:
        return ()
    return tuple(
        ArtifactSnapshotV2(name, len(raw), _digest_bytes(raw))
        for name, raw in (
            ("manifest_json", submission.manifest_json),
            ("candidates_jsonl", submission.candidates_jsonl),
            ("diagnostic_census_jsonl", submission.diagnostic_census_jsonl),
            ("truth_jsonl", submission.truth_jsonl),
            ("receipt_json", submission.receipt_json),
        )
    )


def _value_digest(value: object | None) -> str | None:
    return None if value is None else _digest(value)


def _jsonl_objects(raw: bytes, label: str) -> list[JsonObject]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _InputError(f"{label} is not UTF-8") from exc
    lines = text.splitlines()
    if not text.endswith("\n") or any(not line for line in lines):
        raise _InputError(f"{label} must contain one LF-terminated JSON object per line")
    return [_object(_parse_json(line.encode("utf-8"), label), label) for line in lines]


def _record_mismatches(
    artifact: str,
    expected: object,
    actual: object,
    path: str = "",
) -> list[MismatchV2]:
    if isinstance(expected, dict) and isinstance(actual, dict):
        expected_object = cast(JsonObject, expected)
        actual_object = cast(JsonObject, actual)
        errors: list[MismatchV2] = []
        for key in sorted(set(expected_object) | set(actual_object)):
            child = f"{path}/{key}"
            if key not in expected_object or key not in actual_object:
                errors.append(
                    MismatchV2(
                        artifact,
                        child,
                        _value_digest(expected_object.get(key)),
                        _value_digest(actual_object.get(key)),
                    )
                )
            else:
                errors.extend(
                    _record_mismatches(artifact, expected_object[key], actual_object[key], child)
                )
        return errors
    if isinstance(expected, list) and isinstance(actual, list):
        expected_list = cast(list[object], expected)
        actual_list = cast(list[object], actual)
        errors: list[MismatchV2] = []
        if len(expected_list) != len(actual_list):
            errors.append(
                MismatchV2(
                    artifact,
                    f"{path}/length",
                    _value_digest(len(expected_list)),
                    _value_digest(len(actual_list)),
                )
            )
            return errors
        for index, (left, right) in enumerate(zip(expected_list, actual_list, strict=True)):
            errors.extend(_record_mismatches(artifact, left, right, f"{path}/{index}"))
        return errors
    if expected != actual or type(cast(object, expected)) is not type(actual):
        return [
            MismatchV2(
                artifact,
                path or "/",
                _value_digest(cast(object, expected)),
                _value_digest(actual),
            )
        ]
    return []


def _report(
    status: Literal["DERIVED", "RECONCILED", "MISMATCH", "INCOMPLETE", "STOPPED", "INVALID_INPUT"],
    inputs: tuple[MatchSourceBytesV2, ...],
    submission: PopulationSubmissionV2 | None,
    *,
    producer_revision: str | None,
    producer_executable_fingerprint: str | None,
    derivation: DerivationV2 | None,
    mismatches: tuple[MismatchV2, ...] = (),
) -> AuditReportV2:
    role_order, authorities = _load_contract()
    source_hash = _digest_bytes(Path(__file__).read_bytes())
    inputs_snapshot = (
        _snapshot_inputs(inputs, role_order)
        if len(inputs) == len(role_order)
        and set(item.match_id for item in inputs) == {mid for _, mid in role_order}
        else ()
    )
    artifact_snapshot = _submission_snapshots(submission)
    authority_snapshot = tuple(
        ArtifactSnapshotV2(path.name, len(raw), _digest_bytes(raw))
        for path, raw in (
            (_SOURCE_AUTHORITY, _SOURCE_AUTHORITY.read_bytes()),
            (_STATE_AUTHORITY, _STATE_AUTHORITY.read_bytes()),
            (_POLICY_AUTHORITY, _POLICY_AUTHORITY.read_bytes()),
            (_PROTOCOL_AUTHORITY, _PROTOCOL_AUTHORITY.read_bytes()),
            (_PLAN_AUTHORITY, _PLAN_AUTHORITY.read_bytes()),
            (_POPULATION_SCHEMA, _POPULATION_SCHEMA.read_bytes()),
            (_RESULT_SCHEMA, _RESULT_SCHEMA.read_bytes()),
        )
    )
    retained_snapshots = (
        tuple(
            RetainedSampleSnapshotV2(
                context.match_id,
                context.raw_source_frames,
                context.even_source_frames,
                context.odd_source_frames,
                len(context.samples),
                context.retained_samples_sha256,
            )
            for context in derivation.contexts
        )
        if derivation is not None
        else ()
    )
    match_counts: list[MatchCountsV2] = []
    for role, match_id in role_order:
        if derivation is None:
            match_counts.append(MatchCountsV2(role, match_id, None, None, None, None, None))
            continue
        grid_count = sum(row["match_id"] == match_id for row in derivation.census_rows)
        if derivation.stop_code is not None:
            context = next(item for item in derivation.contexts if item.match_id == match_id)
            grid_count = sum(
                len(
                    range(
                        period.start_frame + period.start_frame % 2,
                        period.end_frame,
                        2,
                    )
                )
                for period in context.periods
            )
            match_counts.append(MatchCountsV2(role, match_id, grid_count, None, None, None, None))
            continue
        candidates = [item for item in derivation.candidates if item.origin.match_id == match_id]
        eligible = [item for item in candidates if item.included]
        match_counts.append(
            MatchCountsV2(
                role,
                match_id,
                grid_count,
                len(candidates),
                len(eligible),
                2 * len(eligible),
                sum(item.scoreable for item in eligible),
            )
        )
    report = AuditReportV2(
        status,
        "NOT_QUALIFIED",
        False,
        producer_revision,
        producer_executable_fingerprint,
        source_hash,
        ".".join(map(str, sys.version_info[:3])),
        SOURCE_RELEASE_HASH,
        SOURCE_POPULATION_HASH,
        cast(str, authorities["role_assignment_sha256"]),
        MEASUREMENT_HASH,
        ELIGIBILITY_HASH,
        PROTOCOL_HASH,
        PLAN_HASH,
        authority_snapshot,
        inputs_snapshot,
        artifact_snapshot,
        retained_snapshots,
        role_order,
        tuple(match_counts),
        None
        if derivation is None or derivation.stop_code is not None
        else derivation.candidate_count,
        None
        if derivation is None or derivation.stop_code is not None
        else derivation.eligible_count,
        None if derivation is None else derivation.diagnostic_grid_count,
        None
        if derivation is None or derivation.stop_code is not None
        else derivation.scoreable_window_count,
        None if derivation is None else derivation.drift_count,
        None if derivation is None else derivation.stop_code,
        mismatches,
        "0" * 64,
    )
    report_hash = _digest(report.content_without_digest())
    return AuditReportV2(
        report.status,
        report.qualification_status,
        report.authoritative,
        report.producer_revision,
        report.producer_executable_fingerprint,
        report.verifier_source_sha256,
        report.python_version,
        report.source_release_hash,
        report.source_population_hash,
        report.role_assignment_sha256,
        report.measurement_hash,
        report.eligibility_hash,
        report.protocol_hash,
        report.plan_hash,
        report.authority_snapshots,
        report.input_snapshots,
        report.artifact_snapshots,
        report.retained_sample_snapshots,
        report.match_roles,
        report.match_counts,
        report.candidate_count,
        report.eligible_count,
        report.diagnostic_grid_count,
        report.scoreable_window_count,
        report.ball_null_flag_finite_xy_count,
        report.stop_code,
        report.mismatches,
        report_hash,
    )


def compare_population_v2(
    inputs: tuple[MatchSourceBytesV2, ...] | list[MatchSourceBytesV2],
    submission: PopulationSubmissionV2,
    *,
    producer_revision: str | None = None,
    producer_executable_fingerprint: str | None = None,
) -> AuditReportV2:
    """Recompute expected synthetic outputs and compare all five producer wire payloads."""
    input_tuple = tuple(inputs)
    try:
        derivation = _derive(input_tuple)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        mismatch = MismatchV2("input", "/", None, _digest(str(exc)))
        return _report(
            "INVALID_INPUT",
            input_tuple,
            submission,
            producer_revision=producer_revision,
            producer_executable_fingerprint=producer_executable_fingerprint,
            derivation=None,
            mismatches=(mismatch,),
        )
    if derivation.stop_code is not None:
        mismatch = MismatchV2("population", "/stop_code", _digest(DRIFT_STOP_CODE), None)
        return _report(
            "STOPPED",
            input_tuple,
            submission,
            producer_revision=producer_revision,
            producer_executable_fingerprint=producer_executable_fingerprint,
            derivation=derivation,
            mismatches=(mismatch,),
        )
    if derivation.expected_manifest is None:
        mismatch = MismatchV2(
            "population", "/scoreable_windows", None, _digest(derivation.expected_receipt)
        )
        return _report(
            "INCOMPLETE",
            input_tuple,
            submission,
            producer_revision=producer_revision,
            producer_executable_fingerprint=producer_executable_fingerprint,
            derivation=derivation,
            mismatches=(mismatch,),
        )
    try:
        actual_manifest = _object(_parse_json(submission.manifest_json, "manifest"), "manifest")
        actual_candidates = _jsonl_objects(submission.candidates_jsonl, "candidates_jsonl")
        actual_census = _jsonl_objects(
            submission.diagnostic_census_jsonl, "diagnostic_census_jsonl"
        )
        actual_truth = _jsonl_objects(submission.truth_jsonl, "truth_jsonl")
        actual_receipt = _object(_parse_json(submission.receipt_json, "receipt"), "receipt")
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        mismatch = MismatchV2("submission", "/", None, _digest(str(exc)))
        return _report(
            "MISMATCH",
            input_tuple,
            submission,
            producer_revision=producer_revision,
            producer_executable_fingerprint=producer_executable_fingerprint,
            derivation=derivation,
            mismatches=(mismatch,),
        )
    expected_candidates = _jsonl_objects(derivation.expected_candidates, "independent candidates")
    expected_census = _jsonl_objects(derivation.expected_census, "independent census")
    expected_truth = _jsonl_objects(derivation.expected_truth, "independent truth")
    mismatches: list[MismatchV2] = []
    mismatches.extend(
        _record_mismatches("manifest_json", derivation.expected_manifest, actual_manifest)
    )
    mismatches.extend(
        _record_mismatches("candidates_jsonl", expected_candidates, actual_candidates)
    )
    mismatches.extend(_record_mismatches("diagnostic_census_jsonl", expected_census, actual_census))
    mismatches.extend(_record_mismatches("truth_jsonl", expected_truth, actual_truth))
    expected_receipt = dict(derivation.expected_receipt)
    expected_receipt["producer_executable_fingerprint"] = producer_executable_fingerprint
    expected_receipt["receipt_sha256"] = _digest(expected_receipt)
    mismatches.extend(_record_mismatches("receipt_json", expected_receipt, actual_receipt))
    mismatch_tuple = tuple(sorted(mismatches, key=lambda item: (item.artifact, item.path)))
    return _report(
        "RECONCILED" if not mismatch_tuple else "MISMATCH",
        input_tuple,
        submission,
        producer_revision=producer_revision,
        producer_executable_fingerprint=producer_executable_fingerprint,
        derivation=derivation,
        mismatches=mismatch_tuple,
    )


def derive_synthetic_population_v2(
    inputs: tuple[MatchSourceBytesV2, ...] | list[MatchSourceBytesV2],
) -> AuditReportV2:
    """Return hash-bound synthetic diagnostics only; this function does not emit qualification."""
    input_tuple = tuple(inputs)
    try:
        derivation = _derive(input_tuple)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return _report(
            "INVALID_INPUT",
            input_tuple,
            None,
            producer_revision=None,
            producer_executable_fingerprint=None,
            derivation=None,
            mismatches=(MismatchV2("input", "/", None, _digest(str(exc))),),
        )
    status: Literal["DERIVED", "RECONCILED", "MISMATCH", "INCOMPLETE", "STOPPED", "INVALID_INPUT"]
    if derivation.stop_code is not None:
        status = "STOPPED"
    elif derivation.expected_manifest is None:
        status = "INCOMPLETE"
    else:
        status = "DERIVED"
    return _report(
        status,
        input_tuple,
        None,
        producer_revision=None,
        producer_executable_fingerprint=None,
        derivation=derivation,
    )
