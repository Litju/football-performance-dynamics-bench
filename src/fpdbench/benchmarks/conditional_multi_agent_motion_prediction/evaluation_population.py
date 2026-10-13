"""Provenance-bound, fail-closed membership gate for prospective scoring."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from fpdbench.data_sources.skillcorner import canonical_bytes

from .empirical_experiment_plan import load_empirical_experiment_plan
from .prospective_protocol import (
    EXPECTED_ELIGIBILITY_POLICY_HASH,
    EXPECTED_MEASUREMENT_STATE_HASH,
    EXPECTED_SOURCE_POPULATION_HASH,
    EXPECTED_SOURCE_RELEASE_HASH,
    PROTOCOL_SHA256,
    load_prospective_protocol,
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_ORIGIN_ID = re.compile(r"period_([1-5])/sample_(0|[1-9][0-9]*)\Z")
_PLAYER_ID = re.compile(r"[1-9][0-9]*\Z")
_SCHEMA_ID = "fpdbench.prospective-evaluation-population"
_SCHEMA_VERSION = "1.0.0"
POPULATION_SCHEMA_FILE = "evaluation_population_authority_v1.schema.json"
_POPULATION_ID = "skillcorner.prospective.conditional_motion.population"

type XY = Sequence[float]
type TruthXY = XY | None
type ScenePrediction = Sequence[Sequence[XY]]
type SceneTruth = Sequence[Sequence[TruthXY]]


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    typed_value = cast(Mapping[object, object], value)
    if not all(isinstance(key, str) for key in typed_value):
        raise ValueError(f"{label} must have string keys")
    return cast(Mapping[str, object], value)


def _list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return cast(list[object], value)


def _keys(value: Mapping[str, object], required: set[str], label: str) -> None:
    if set(value) != required:
        raise ValueError(f"{label} fields must be exactly {sorted(required)}")


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _digest(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def prospective_window_id(match_id: str, origin_sample_id: str) -> str:
    """Return the stable opaque ID for one match-scoped forecast origin."""
    return _digest(
        {
            "schema_id": "fpdbench.prospective-window",
            "schema_version": "1.0.0",
            "match_id": match_id,
            "origin_sample_id": origin_sample_id,
            "source_release_hash": EXPECTED_SOURCE_RELEASE_HASH,
            "measurement_state_hash": EXPECTED_MEASUREMENT_STATE_HASH,
            "eligibility_policy_hash": EXPECTED_ELIGIBILITY_POLICY_HASH,
            "protocol_sha256": PROTOCOL_SHA256,
        }
    )


@dataclass(frozen=True, slots=True)
class SceneMembership:
    scene_id: str
    player_ids: tuple[str, ...]
    truth_sha256: str
    truth_mask_sha256: str


@dataclass(frozen=True, slots=True)
class WindowMembership:
    window_id: str
    origin_sample_id: str
    eligibility_result_sha256: str
    scenes: tuple[SceneMembership, SceneMembership]


@dataclass(frozen=True, slots=True)
class MatchMembership:
    role: str
    match_id: str
    windows: tuple[WindowMembership, ...]


@dataclass(frozen=True, slots=True)
class EvaluationPopulationAuthority:
    candidate_window_count: int
    eligible_window_count: int
    candidate_origin_population_sha256: str
    matches: tuple[MatchMembership, ...]
    membership_sha256: str
    manifest_sha256: str

    def match_ids(self, role: str) -> tuple[str, ...]:
        return tuple(match.match_id for match in self.matches if match.role == role)

    def matches_for_role(self, role: str) -> tuple[MatchMembership, ...]:
        return tuple(match for match in self.matches if match.role == role)


@dataclass(frozen=True, slots=True)
class PopulationBoundScene:
    scene_id: str
    player_ids: tuple[str, ...]
    prediction: ScenePrediction
    truth: SceneTruth


@dataclass(frozen=True, slots=True)
class PopulationBoundWindow:
    window_id: str
    origin_sample_id: str
    scenes: tuple[PopulationBoundScene, ...]


@dataclass(frozen=True, slots=True)
class EvaluationPopulationOutput:
    population_authority_sha256: str
    matches: Mapping[str, Sequence[PopulationBoundWindow]]


def _protocol_roles() -> tuple[tuple[str, tuple[str, ...]], ...]:
    protocol = _mapping(load_prospective_protocol(), "protocol")
    state = _mapping(protocol.get("scientific_state"), "protocol scientific_state")
    split = _mapping(state.get("split"), "protocol split")
    roles = _mapping(split.get("roles"), "protocol match roles")
    result: list[tuple[str, tuple[str, ...]]] = []
    for role in ("training", "validation", "evaluation"):
        ids = _list(roles.get(role), f"protocol {role} match IDs")
        if not all(isinstance(value, str) and value.isdecimal() for value in ids):
            raise ValueError(f"protocol {role} match IDs are invalid")
        result.append((role, tuple(cast(str, value) for value in ids)))
    return tuple(result)


def validate_evaluation_population_authority_document(
    document: Mapping[str, object],
) -> EvaluationPopulationAuthority:
    """Validate and bind the restricted population manifest to protocol and plan hashes."""
    value = _mapping(document, "population authority")
    _keys(
        value,
        {
            "schema_id",
            "schema_version",
            "population_id",
            "source_release_hash",
            "source_population_hash",
            "measurement_state_hash",
            "eligibility_policy_hash",
            "protocol_sha256",
            "plan_sha256",
            "candidate_window_count",
            "eligible_window_count",
            "candidate_origin_population_sha256",
            "matches",
            "membership_sha256",
            "manifest_sha256",
        },
        "population authority",
    )
    for field, expected in (
        ("schema_id", _SCHEMA_ID),
        ("schema_version", _SCHEMA_VERSION),
        ("population_id", _POPULATION_ID),
        ("source_release_hash", EXPECTED_SOURCE_RELEASE_HASH),
        ("source_population_hash", EXPECTED_SOURCE_POPULATION_HASH),
        ("measurement_state_hash", EXPECTED_MEASUREMENT_STATE_HASH),
        ("eligibility_policy_hash", EXPECTED_ELIGIBILITY_POLICY_HASH),
        ("protocol_sha256", PROTOCOL_SHA256),
        ("plan_sha256", load_empirical_experiment_plan()["plan_sha256"]),
    ):
        if value.get(field) != expected:
            raise ValueError(f"population authority {field} differs from its pinned authority")

    candidate_count = value.get("candidate_window_count")
    eligible_count = value.get("eligible_window_count")
    if (
        isinstance(candidate_count, bool)
        or not isinstance(candidate_count, int)
        or candidate_count < 0
        or isinstance(eligible_count, bool)
        or not isinstance(eligible_count, int)
        or eligible_count < 0
        or eligible_count > candidate_count
    ):
        raise ValueError("population candidate and eligible-window counts are invalid")
    candidate_digest = _sha256(
        value.get("candidate_origin_population_sha256"), "candidate origin population digest"
    )
    raw_matches = _list(value.get("matches"), "population matches")
    expected_roles = tuple(
        (role, match_id) for role, match_ids in _protocol_roles() for match_id in match_ids
    )
    if len(raw_matches) != len(expected_roles):
        raise ValueError("population authority must contain every protocol match exactly once")
    matches: list[MatchMembership] = []
    total_eligible = 0
    seen_match_ids: set[str] = set()
    for raw_match, (expected_role, expected_match_id) in zip(
        raw_matches, expected_roles, strict=True
    ):
        match = _mapping(raw_match, "population match")
        _keys(match, {"role", "match_id", "windows"}, "population match")
        role = match.get("role")
        match_id = match.get("match_id")
        if role != expected_role or match_id != expected_match_id or match_id in seen_match_ids:
            raise ValueError("population match role, identity, or canonical order drift")
        seen_match_ids.add(cast(str, match_id))
        windows: list[WindowMembership] = []
        prior_origin: tuple[int, int] | None = None
        seen_windows: set[str] = set()
        raw_windows = _list(match.get("windows"), "eligible windows")
        for raw_window in raw_windows:
            window = _mapping(raw_window, "eligible window")
            _keys(
                window,
                {"window_id", "origin_sample_id", "eligibility_result_sha256", "scenes"},
                "eligible window",
            )
            origin_id = window.get("origin_sample_id")
            if not isinstance(origin_id, str):
                raise ValueError("origin_sample_id must be a canonical string")
            parsed_origin = _ORIGIN_ID.fullmatch(origin_id)
            if parsed_origin is None or int(parsed_origin.group(2)) < 25:
                raise ValueError("origin_sample_id is invalid or lacks full history support")
            origin_key = (int(parsed_origin.group(1)), int(parsed_origin.group(2)))
            if prior_origin is not None and origin_key <= prior_origin:
                raise ValueError("eligible windows must be unique and ordered by period and origin")
            prior_origin = origin_key
            expected_window_id = prospective_window_id(cast(str, match_id), origin_id)
            window_id = _sha256(window.get("window_id"), "window_id")
            if window_id != expected_window_id or window_id in seen_windows:
                raise ValueError("window identity is invalid or duplicated")
            seen_windows.add(window_id)
            eligibility_digest = _sha256(
                window.get("eligibility_result_sha256"), "eligibility result digest"
            )
            raw_scenes = _list(window.get("scenes"), "directed scenes")
            if len(raw_scenes) != 2:
                raise ValueError("each physical window must have exactly two directed scenes")
            scenes: list[SceneMembership] = []
            for raw_scene, expected_scene_id in zip(raw_scenes, ("home", "away"), strict=True):
                scene = _mapping(raw_scene, "directed scene membership")
                _keys(
                    scene,
                    {"scene_id", "player_ids", "truth_sha256", "truth_mask_sha256"},
                    "directed scene membership",
                )
                if scene.get("scene_id") != expected_scene_id:
                    raise ValueError("directed scenes must be ordered home then away")
                raw_player_ids = _list(scene.get("player_ids"), "origin player IDs")
                if not all(
                    isinstance(player_id, str) and _PLAYER_ID.fullmatch(player_id)
                    for player_id in raw_player_ids
                ):
                    raise ValueError("origin player IDs must be positive canonical decimal strings")
                player_ids = tuple(cast(str, player_id) for player_id in raw_player_ids)
                if len(player_ids) < 7 or tuple(sorted(player_ids, key=int)) != player_ids:
                    raise ValueError(
                        "origin player IDs must contain at least seven sorted identities"
                    )
                if len(player_ids) != len(set(player_ids)):
                    raise ValueError("origin player IDs must be unique")
                scenes.append(
                    SceneMembership(
                        expected_scene_id,
                        player_ids,
                        _sha256(scene.get("truth_sha256"), "target truth digest"),
                        _sha256(scene.get("truth_mask_sha256"), "target truth-mask digest"),
                    )
                )
            windows.append(
                WindowMembership(
                    window_id,
                    origin_id,
                    eligibility_digest,
                    (scenes[0], scenes[1]),
                )
            )
        total_eligible += len(windows)
        matches.append(MatchMembership(cast(str, role), cast(str, match_id), tuple(windows)))
    if total_eligible != eligible_count:
        raise ValueError("eligible_window_count does not equal the complete retained membership")

    membership_digest = _sha256(value.get("membership_sha256"), "membership_sha256")
    if membership_digest != _digest(raw_matches):
        raise ValueError("population membership SHA-256 mismatch")
    manifest_digest = _sha256(value.get("manifest_sha256"), "manifest_sha256")
    payload = {key: item for key, item in value.items() if key != "manifest_sha256"}
    if manifest_digest != _digest(payload):
        raise ValueError("population authority manifest SHA-256 mismatch")
    return EvaluationPopulationAuthority(
        candidate_count,
        eligible_count,
        candidate_digest,
        tuple(matches),
        membership_digest,
        manifest_digest,
    )


def load_evaluation_population_authority(path: Path) -> EvaluationPopulationAuthority:
    """Load a restricted runtime population manifest; no default artifact is checked in."""
    document = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    return validate_evaluation_population_authority_document(
        _mapping(document, "population authority")
    )


def validate_evaluation_population_schema(root: Path) -> tuple[str, ...]:
    """Validate the checked-in JSON Schema used for restricted population instances."""
    path = (
        root
        / "src"
        / "fpdbench"
        / "benchmarks"
        / "conditional_multi_agent_motion_prediction"
        / POPULATION_SCHEMA_FILE
    )
    try:
        schema = _mapping(
            json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object),
            path.name,
        )
        plan_authority = _mapping(
            load_empirical_experiment_plan().get("population_authority"),
            "plan population authority",
        )
        properties = _mapping(schema.get("properties"), "population schema properties")
        matches = _mapping(properties.get("matches"), "population schema matches")
        match_definition = _mapping(
            _mapping(schema.get("$defs"), "population schema definitions").get("match"),
            "population schema match",
        )
        if (
            schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema"
            or schema.get("$id") != f"{_SCHEMA_ID}/{_SCHEMA_VERSION}"
            or plan_authority.get("schema_file") != path.name
            or plan_authority.get("schema_sha256") != hashlib.sha256(path.read_bytes()).hexdigest()
            or schema.get("additionalProperties") is not False
            or schema.get("required")
            != [
                "schema_id",
                "schema_version",
                "population_id",
                "source_release_hash",
                "source_population_hash",
                "measurement_state_hash",
                "eligibility_policy_hash",
                "protocol_sha256",
                "plan_sha256",
                "candidate_window_count",
                "eligible_window_count",
                "candidate_origin_population_sha256",
                "matches",
                "membership_sha256",
                "manifest_sha256",
            ]
            or properties.get("schema_id") != {"const": _SCHEMA_ID}
            or properties.get("schema_version") != {"const": _SCHEMA_VERSION}
            or matches.get("minItems") != 20
            or matches.get("maxItems") != 20
            or match_definition.get("additionalProperties") is not False
        ):
            return ("prospective population JSON Schema differs from its frozen contract",)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return (f"prospective population JSON Schema: {exc}",)
    return ()


def truth_sha256(truth: SceneTruth) -> str:
    """Hash an ordered physical truth panel without serializing it into the manifest."""
    return _digest(
        {
            "schema_id": "fpdbench.prospective-truth-panel",
            "schema_version": "1.0.0",
            "samples": _truth_rows(truth),
        }
    )


def truth_mask_sha256(truth: SceneTruth) -> str:
    """Hash the locked all-or-null XY mask for a directed truth panel."""
    rows = _truth_rows(truth)
    return _digest(
        {
            "schema_id": "fpdbench.prospective-truth-mask",
            "schema_version": "1.0.0",
            "samples": [[value is not None for value in row] for row in rows],
        }
    )


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, str | bytes)


def _truth_rows(truth: SceneTruth) -> list[list[list[str] | None]]:
    if len(truth) != 15:
        raise ValueError("each directed scene truth must contain exactly 15 future samples")
    rows: list[list[list[str] | None]] = []
    target_count: int | None = None
    for sample in cast(Sequence[object], truth):
        if not _is_sequence(sample):
            raise ValueError("truth samples must be target arrays")
        sample_values = cast(Sequence[object], sample)
        if target_count is None:
            target_count = len(sample_values)
        elif len(sample_values) != target_count:
            raise ValueError("truth target count must stay fixed for all 15 samples")
        row: list[list[str] | None] = []
        for pair in sample_values:
            if pair is None:
                row.append(None)
                continue
            if (
                not _is_sequence(pair)
                or len(cast(Sequence[object], pair)) != 2
                or any(
                    isinstance(coordinate, bool)
                    or not isinstance(coordinate, int | float)
                    or not math.isfinite(float(coordinate))
                    for coordinate in cast(Sequence[object], pair)
                )
            ):
                raise ValueError("truth positions must be finite XY pairs or a null XY mask")
            pair_values = cast(Sequence[object], pair)
            row.append(
                [
                    float(cast(int | float, pair_values[0])).hex(),
                    float(cast(int | float, pair_values[1])).hex(),
                ]
            )
        rows.append(row)
    return rows


def _validate_predictions(prediction: ScenePrediction, target_count: int) -> None:
    if len(prediction) != 15:
        raise ValueError("each directed scene prediction must contain exactly 15 future samples")
    for sample in cast(Sequence[object], prediction):
        if not _is_sequence(sample):
            raise ValueError("prediction samples must be target arrays")
        sample_values = cast(Sequence[object], sample)
        if len(sample_values) != target_count:
            raise ValueError("prediction must contain every origin target in every future sample")
        for pair in sample_values:
            if (
                not _is_sequence(pair)
                or len(cast(Sequence[object], pair)) != 2
                or any(
                    isinstance(coordinate, bool)
                    or not isinstance(coordinate, int | float)
                    or not math.isfinite(float(coordinate))
                    for coordinate in cast(Sequence[object], pair)
                )
            ):
                raise ValueError("predictions must contain finite XY pairs for every origin target")


def validate_population_bound_evaluation(
    authority: EvaluationPopulationAuthority, output: EvaluationPopulationOutput
) -> None:
    """Reject population drift, masking, identity changes, or reordered scorer inputs."""
    if output.population_authority_sha256 != authority.manifest_sha256:
        raise ValueError("evaluation output uses a different population authority")
    expected_matches = authority.matches_for_role("evaluation")
    if tuple(output.matches) != tuple(match.match_id for match in expected_matches):
        raise ValueError("evaluation output must contain all four matches in protocol order")
    for match, match_id in zip(expected_matches, output.matches, strict=True):
        actual_windows = output.matches[match_id]
        if len(actual_windows) != len(match.windows):
            raise ValueError(f"evaluation output is missing or adding windows for match {match_id}")
        for expected_window, actual_window in zip(match.windows, actual_windows, strict=True):
            if (
                actual_window.window_id != expected_window.window_id
                or actual_window.origin_sample_id != expected_window.origin_sample_id
            ):
                raise ValueError(
                    f"evaluation window order or origin identity drift in match {match_id}"
                )
            if len(actual_window.scenes) != 2:
                raise ValueError("each physical window must contain home and away scenes")
            for expected_scene, actual_scene in zip(
                expected_window.scenes, actual_window.scenes, strict=True
            ):
                if actual_scene.scene_id != expected_scene.scene_id:
                    raise ValueError("directed scene order must be home then away")
                if actual_scene.player_ids != expected_scene.player_ids:
                    raise ValueError("evaluation target player IDs or order differ from authority")
                if len(actual_scene.player_ids) != len(set(actual_scene.player_ids)):
                    raise ValueError("evaluation target player IDs must be unique")
                truth_digest = truth_sha256(actual_scene.truth)
                mask_digest = truth_mask_sha256(actual_scene.truth)
                if truth_digest != expected_scene.truth_sha256:
                    raise ValueError(
                        "evaluation target truth differs from the population authority"
                    )
                if mask_digest != expected_scene.truth_mask_sha256:
                    raise ValueError("model-dependent target masking is not allowed")
                _validate_predictions(actual_scene.prediction, len(expected_scene.player_ids))


__all__ = [
    "EvaluationPopulationAuthority",
    "EvaluationPopulationOutput",
    "MatchMembership",
    "POPULATION_SCHEMA_FILE",
    "PopulationBoundScene",
    "PopulationBoundWindow",
    "SceneMembership",
    "WindowMembership",
    "load_evaluation_population_authority",
    "prospective_window_id",
    "truth_mask_sha256",
    "truth_sha256",
    "validate_evaluation_population_authority_document",
    "validate_evaluation_population_schema",
    "validate_population_bound_evaluation",
]
