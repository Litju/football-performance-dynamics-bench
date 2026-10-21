"""Provenance-bound, fail-closed membership gate for prospective scoring."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from fpdbench.data_sources.skillcorner import canonical_bytes

from .empirical_experiment_plan import (
    PLAN_V2_SHA256,
    experiment_cell,
    load_empirical_experiment_plan,
    load_empirical_experiment_plan_v2,
    lomo_held_out_match,
    protocol_split,
    protocol_split_v2,
    validate_empirical_experiment_plan_v2_document,
)
from .prospective_protocol import (
    EXPECTED_ELIGIBILITY_POLICY_HASH,
    EXPECTED_ELIGIBILITY_POLICY_V2_HASH,
    EXPECTED_MEASUREMENT_STATE_HASH,
    EXPECTED_MEASUREMENT_STATE_V2_HASH,
    EXPECTED_SOURCE_POPULATION_HASH,
    EXPECTED_SOURCE_RELEASE_HASH,
    PROTOCOL_SHA256,
    PROTOCOL_V2_SHA256,
    load_prospective_protocol,
    load_prospective_protocol_v2,
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_ORIGIN_ID = re.compile(r"period_([1-5])/sample_(0|[1-9][0-9]*)\Z")
_PLAYER_ID = re.compile(r"[1-9][0-9]*\Z")
_SCHEMA_ID = "fpdbench.prospective-evaluation-population"
_SCHEMA_VERSION = "1.1.0"
POPULATION_SCHEMA_FILE = "evaluation_population_authority_v1.schema.json"
POPULATION_SCHEMA_V2_FILE = "evaluation_population_authority_v2.schema.json"
_POPULATION_ID = "skillcorner.prospective.conditional_motion.population"
_POPULATION_ID_V2 = "skillcorner.prospective.conditional_motion.population_v2"
_SCHEMA_VERSION_V2 = "2.0.0"

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


def prospective_window_id_v2(match_id: str, origin_sample_id: str) -> str:
    """Return the nullable-ball v2 identity for a match-scoped forecast origin."""
    return _digest(
        {
            "schema_id": "fpdbench.prospective-window",
            "schema_version": "2.0.0",
            "match_id": match_id,
            "origin_sample_id": origin_sample_id,
            "source_release_hash": EXPECTED_SOURCE_RELEASE_HASH,
            "measurement_state_hash": EXPECTED_MEASUREMENT_STATE_V2_HASH,
            "eligibility_policy_hash": EXPECTED_ELIGIBILITY_POLICY_V2_HASH,
            "protocol_sha256": PROTOCOL_V2_SHA256,
        }
    )


@dataclass(frozen=True, slots=True)
class SceneMembership:
    scene_id: str
    player_ids: tuple[str, ...]
    absolute_xy_truth_sha256: str
    displacement_truth_sha256: str
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
class EvaluationPopulationAuthorityV2:
    population_id: str
    source_release_id: str
    source_release_version: str
    source_release_hash: str
    source_population_hash: str
    measurement_state_id: str
    measurement_state_version: str
    measurement_state_hash: str
    eligibility_policy_id: str
    eligibility_policy_version: str
    eligibility_policy_hash: str
    protocol_id: str
    protocol_version: str
    protocol_sha256: str
    plan_id: str
    plan_version: str
    plan_sha256: str
    ball_null_flag_finite_xy_count: int
    candidate_window_count: int
    eligible_window_count: int
    candidate_origin_population_sha256: str
    matches: tuple[MatchMembership, ...]
    membership_sha256: str
    manifest_sha256: str

    @property
    def empirically_qualified(self) -> bool:
        """Structural validation never authenticates source-derived truth or masks."""
        return False

    def require_empirical_qualification(self) -> None:
        if any(not match.windows for match in self.matches) or len(self.matches) != 20:
            raise ValueError(
                "protected-population qualification requires scoreable windows in every match"
            )
        # The independent protected receipt verifier is a separate qualification task.
        raise ValueError(
            "independently verified protected-population receipt required; "
            "structural hashes do not qualify source membership, physical truth, or masks"
        )

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
    target_representation: str


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


def _protocol_roles_v2() -> tuple[tuple[str, tuple[str, ...]], ...]:
    protocol = _mapping(load_prospective_protocol_v2(), "v2 protocol")
    state = _mapping(protocol.get("scientific_state"), "v2 protocol scientific_state")
    split = _mapping(state.get("split"), "v2 protocol split")
    roles = _mapping(split.get("roles"), "v2 protocol match roles")
    result: list[tuple[str, tuple[str, ...]]] = []
    for role in ("training", "validation", "evaluation"):
        ids = _list(roles.get(role), f"v2 protocol {role} match IDs")
        if not all(isinstance(value, str) and value.isdecimal() for value in ids):
            raise ValueError(f"v2 protocol {role} match IDs are invalid")
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

    expected_roles = tuple(
        (role, match_id) for role, match_ids in _protocol_roles() for match_id in match_ids
    )
    return _validate_population_membership(
        value, expected_roles=expected_roles, window_id_fn=prospective_window_id
    )


def _validate_population_membership(
    value: Mapping[str, object],
    *,
    expected_roles: tuple[tuple[str, str], ...],
    window_id_fn: Callable[[str, str], str],
) -> EvaluationPopulationAuthority:
    """Validate canonical match/window membership independently of authority version."""
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
            expected_window_id = window_id_fn(cast(str, match_id), origin_id)
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
                    {
                        "scene_id",
                        "player_ids",
                        "absolute_xy_truth_sha256",
                        "displacement_truth_sha256",
                        "truth_mask_sha256",
                    },
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
                        _sha256(scene.get("absolute_xy_truth_sha256"), "absolute truth digest"),
                        _sha256(
                            scene.get("displacement_truth_sha256"), "displacement truth digest"
                        ),
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


def validate_evaluation_population_authority_v2_document(
    document: Mapping[str, object],
) -> EvaluationPopulationAuthorityV2:
    """Validate structure and hash bindings only; return an empirically unqualified manifest."""
    value = _mapping(document, "v2 population authority")
    plan = load_empirical_experiment_plan_v2()
    validate_empirical_experiment_plan_v2_document(plan)
    population_contract = _mapping(plan.get("population_authority"), "v2 population contract")
    required_fields = {
        "schema_id",
        "schema_version",
        "population_id",
        "source_release_id",
        "source_release_version",
        "source_release_hash",
        "source_population_hash",
        "measurement_state_id",
        "measurement_state_version",
        "measurement_state_hash",
        "eligibility_policy_id",
        "eligibility_policy_version",
        "eligibility_policy_hash",
        "protocol_id",
        "protocol_version",
        "protocol_sha256",
        "plan_id",
        "plan_version",
        "plan_sha256",
        "ball_null_flag_finite_xy_count",
        "candidate_window_count",
        "eligible_window_count",
        "candidate_origin_population_sha256",
        "matches",
        "membership_sha256",
        "manifest_sha256",
    }
    _keys(value, required_fields, "v2 population authority")
    expected_fields = (
        ("schema_id", _SCHEMA_ID),
        ("schema_version", _SCHEMA_VERSION_V2),
        ("population_id", _POPULATION_ID_V2),
        ("source_release_id", "skillcorner_open_data_v1"),
        ("source_release_version", "1.0.0"),
        ("source_release_hash", EXPECTED_SOURCE_RELEASE_HASH),
        ("source_population_hash", EXPECTED_SOURCE_POPULATION_HASH),
        ("measurement_state_id", "skillcorner_5hz_v2"),
        ("measurement_state_version", "2.0.0"),
        ("measurement_state_hash", EXPECTED_MEASUREMENT_STATE_V2_HASH),
        ("eligibility_policy_id", "skillcorner_window_v2"),
        ("eligibility_policy_version", "2.0.0"),
        ("eligibility_policy_hash", EXPECTED_ELIGIBILITY_POLICY_V2_HASH),
        ("protocol_id", "skillcorner.prospective_conditional_motion"),
        ("protocol_version", "2.0.0"),
        ("protocol_sha256", PROTOCOL_V2_SHA256),
        ("plan_id", plan.get("plan_id")),
        ("plan_version", "2.0.0"),
        ("plan_sha256", plan.get("plan_sha256")),
    )
    for field, expected in expected_fields:
        if value.get(field) != expected:
            raise ValueError(f"v2 population authority {field} differs from its pinned authority")
    drift_count = value.get("ball_null_flag_finite_xy_count")
    if type(drift_count) is not int or drift_count < 0:
        raise ValueError("v2 population drift-stop count must be a nonnegative integer")
    if drift_count != population_contract.get("ball_null_flag_finite_xy_count"):
        raise ValueError(
            "BALL_NULL_FLAG_WITH_FINITE_XY_UNAPPROVED: population authority is not qualified"
        )

    base = _validate_population_membership(
        value,
        expected_roles=tuple(
            (role, match_id) for role, match_ids in _protocol_roles_v2() for match_id in match_ids
        ),
        window_id_fn=prospective_window_id_v2,
    )
    return EvaluationPopulationAuthorityV2(
        _POPULATION_ID_V2,
        "skillcorner_open_data_v1",
        "1.0.0",
        EXPECTED_SOURCE_RELEASE_HASH,
        EXPECTED_SOURCE_POPULATION_HASH,
        "skillcorner_5hz_v2",
        "2.0.0",
        EXPECTED_MEASUREMENT_STATE_V2_HASH,
        "skillcorner_window_v2",
        "2.0.0",
        EXPECTED_ELIGIBILITY_POLICY_V2_HASH,
        "skillcorner.prospective_conditional_motion",
        "2.0.0",
        PROTOCOL_V2_SHA256,
        cast(str, plan["plan_id"]),
        "2.0.0",
        cast(str, plan["plan_sha256"]),
        0,
        base.candidate_window_count,
        base.eligible_window_count,
        base.candidate_origin_population_sha256,
        base.matches,
        base.membership_sha256,
        base.manifest_sha256,
    )


def load_evaluation_population_authority_v2(path: Path) -> EvaluationPopulationAuthorityV2:
    """Load and validate only an explicitly v2 restricted population manifest."""
    document = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    return validate_evaluation_population_authority_v2_document(
        _mapping(document, "v2 population authority")
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


def validate_evaluation_population_schema_v2(root: Path) -> tuple[str, ...]:
    """Validate both v2 schemas against their raw-byte hashes in the v2 plan."""
    from .empirical_experiment_plan import validate_empirical_experiment_plan_v2

    errors = list(validate_empirical_experiment_plan_v2(root))
    if errors:
        return tuple(errors)
    base = root / "src" / "fpdbench" / "benchmarks" / "conditional_multi_agent_motion_prediction"
    population_path = base / POPULATION_SCHEMA_V2_FILE
    result_path = base / "prospective_experiment_result_v2.schema.json"
    try:
        plan = _mapping(
            json.loads((base / "empirical_experiment_plan_v2.json").read_text(encoding="utf-8")),
            "v2 experiment plan",
        )
        population_contract = _mapping(plan.get("population_authority"), "v2 population contract")
        result_contract = _mapping(plan.get("result_manifest_schema"), "v2 result contract")
        population_schema = _mapping(
            json.loads(
                population_path.read_text(encoding="utf-8"),
                object_pairs_hook=_unique_object,
            ),
            population_path.name,
        )
        result_schema = _mapping(
            json.loads(result_path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object),
            result_path.name,
        )
        population_properties = _mapping(
            population_schema.get("properties"), "v2 population schema properties"
        )
        population_required = [
            "schema_id",
            "schema_version",
            "population_id",
            "source_release_id",
            "source_release_version",
            "source_release_hash",
            "source_population_hash",
            "measurement_state_id",
            "measurement_state_version",
            "measurement_state_hash",
            "eligibility_policy_id",
            "eligibility_policy_version",
            "eligibility_policy_hash",
            "protocol_id",
            "protocol_version",
            "protocol_sha256",
            "plan_id",
            "plan_version",
            "plan_sha256",
            "ball_null_flag_finite_xy_count",
            "candidate_window_count",
            "eligible_window_count",
            "candidate_origin_population_sha256",
            "matches",
            "membership_sha256",
            "manifest_sha256",
        ]
        population_matches = _mapping(
            population_properties.get("matches"), "v2 population matches schema"
        )
        result_properties = _mapping(result_schema.get("properties"), "v2 result schema properties")
        result_required = _list(result_contract.get("required_fields"), "v2 result required fields")
        result_schema_hash = hashlib.sha256(result_path.read_bytes()).hexdigest()
        if (
            population_schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema"
            or population_schema.get("$id") != f"{_SCHEMA_ID}/2.0.0"
            or population_contract.get("schema_file") != population_path.name
            or population_contract.get("schema_sha256")
            != hashlib.sha256(population_path.read_bytes()).hexdigest()
            or population_schema.get("additionalProperties") is not False
            or population_schema.get("required") != population_required
            or population_properties.get("schema_id") != {"const": _SCHEMA_ID}
            or population_properties.get("schema_version") != {"const": "2.0.0"}
            or population_properties.get("population_id") != {"const": _POPULATION_ID_V2}
            or population_properties.get("plan_sha256") != {"$ref": "#/$defs/sha256"}
            or population_properties.get("manifest_sha256") != {"$ref": "#/$defs/sha256"}
            or population_properties.get("ball_null_flag_finite_xy_count") != {"const": 0}
            or population_matches.get("minItems") != 20
            or population_matches.get("maxItems") != 20
            or result_schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema"
            or result_schema.get("$id") != "fpdbench.prospective-experiment-result/2.0.0"
            or result_contract.get("schema_file") != result_path.name
            or result_contract.get("schema_sha256") != result_schema_hash
            or result_schema.get("additionalProperties") is not False
            or result_schema.get("required") != result_required
            or result_properties.get("schema_id")
            != {"const": "fpdbench.prospective-experiment-result"}
            or result_properties.get("schema_version") != {"const": "2.0.0"}
            or result_properties.get("plan_sha256") != {"$ref": "#/$defs/sha256"}
            or result_properties.get("population_authority_sha256") != {"$ref": "#/$defs/sha256"}
        ):
            return ("v2 population or result JSON Schema differs from its frozen plan contract",)
        if "const" in _mapping(population_properties["plan_sha256"], "population plan hash schema"):
            return ("v2 population schema cannot contain the downstream plan hash",)
        if "const" in _mapping(result_properties["plan_sha256"], "result plan hash schema"):
            return ("v2 result schema cannot contain the downstream plan hash",)
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return (f"v2 population/result JSON Schema: {exc}",)
    return ()


def truth_sha256(truth: SceneTruth, *, target_representation: str) -> str:
    """Seal an ordered truth panel in its explicit metre-valued target frame."""
    if target_representation not in {"absolute_xy", "origin_relative_displacement"}:
        raise ValueError("unknown target representation")
    return _digest(
        {
            "schema_id": "fpdbench.prospective-truth-panel",
            "schema_version": "1.1.0",
            "target_representation": target_representation,
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
    authority: EvaluationPopulationAuthority,
    output: EvaluationPopulationOutput,
    *,
    cell_id: str,
    role: str = "evaluation",
    lomo_fold_id: str | None = None,
) -> None:
    """Reject population drift, masking, identity changes, or reordered scorer inputs."""
    if isinstance(authority, EvaluationPopulationAuthorityV2):
        authority.require_empirical_qualification()
    if output.population_authority_sha256 != authority.manifest_sha256:
        raise ValueError("evaluation output uses a different population authority")
    cell = experiment_cell(cell_id)
    if output.target_representation != cell["target_representation"]:
        raise ValueError("output target representation differs from frozen cell")
    if role == "lomo" and lomo_fold_id is not None:
        held_out = lomo_held_out_match(lomo_fold_id)
        expected_matches = tuple(
            match for match in authority.matches_for_role("training") if match.match_id == held_out
        )
    elif role in {"validation", "evaluation"} and lomo_fold_id is None:
        expected_matches = authority.matches_for_role(role)
    else:
        raise ValueError("scoring role and LOMO fold are incompatible")
    if not expected_matches:
        raise ValueError("population authority lacks the scoring role")
    if tuple(output.matches) != tuple(match.match_id for match in expected_matches):
        raise ValueError(
            "evaluation output must contain all scoring-role matches in protocol order"
        )
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
                truth_digest = truth_sha256(
                    actual_scene.truth, target_representation=output.target_representation
                )
                mask_digest = truth_mask_sha256(actual_scene.truth)
                expected_digest = (
                    expected_scene.absolute_xy_truth_sha256
                    if output.target_representation == "absolute_xy"
                    else expected_scene.displacement_truth_sha256
                )
                if truth_digest != expected_digest:
                    raise ValueError(
                        "evaluation target truth differs from the population authority"
                    )
                if mask_digest != expected_scene.truth_mask_sha256:
                    raise ValueError("model-dependent target masking is not allowed")
                if any(len(row) != len(expected_scene.player_ids) for row in actual_scene.truth):
                    raise ValueError("truth must contain every origin target")
                _validate_predictions(actual_scene.prediction, len(expected_scene.player_ids))


def validate_prospective_result_document(
    document: Mapping[str, object], population: EvaluationPopulationAuthority
) -> None:
    """Require exact run membership and complete match metrics, never partial success."""
    value = _mapping(document, "result manifest")
    plan = load_empirical_experiment_plan()
    contract = _mapping(plan["result_manifest_schema"], "result contract")
    required = _list(contract["required_fields"], "result fields")
    _keys(value, set(cast(list[str], required)), "result manifest")
    for field in (
        "plan_id",
        "plan_version",
        "plan_sha256",
        "protocol_id",
        "protocol_version",
        "protocol_sha256",
    ):
        if value[field] != plan[field]:
            raise ValueError(f"result {field} differs from frozen authority")
    if (
        value["schema_id"] != "fpdbench.prospective-experiment-result"
        or value["schema_version"] != "1.1.0"
    ):
        raise ValueError("unsupported result schema identity")
    if not isinstance(value["cell_id"], str):
        raise ValueError("result cell_id must be a string")
    cell = experiment_cell(value["cell_id"])
    if any(value[field] != cell[field] for field in cell):
        raise ValueError("result cell/model/regime/target contradiction")
    roles = _mapping(protocol_split()["roles"], "match roles")
    training = _list(roles["training"], "training matches")
    validation = _list(roles["validation"], "validation matches")
    evaluation = _list(roles["evaluation"], "evaluation matches")
    learned = value["model_class_id"] == "per_target_context_deepsets_mlp_v1"
    role = value["fit_role"]
    held_out: str | None = None
    if learned and role == "lomo" and isinstance(value["lomo_fold_id"], str):
        held_out = lomo_held_out_match(value["lomo_fold_id"])
        train = [match for match in training if match != held_out]
    elif (learned and role == "final_train") or (not learned and role == "baseline"):
        if value["lomo_fold_id"] is not None:
            raise ValueError("non-LOMO result cannot name a fold")
        train = training if learned else []
    else:
        raise ValueError("result model and fit role are incompatible")
    if value["held_out_match_id"] != held_out:
        raise ValueError("result held-out identity differs from frozen fold")
    if value["train_match_ids"] != train or value["validation_match_ids"] != validation:
        raise ValueError("result train/validation membership differs from protocol")
    seed = value["seed"]
    if learned:
        if type(seed) is not int or seed not in [1729, 2718, 31415]:
            raise ValueError("result seed differs from frozen schedule")
    elif seed is not None:
        raise ValueError("deterministic baseline cannot name a seed")
    fold_part = value["lomo_fold_id"] if held_out is not None else "final"
    seed_part = seed if learned else "deterministic"
    if value["run_id"] != f"{value['cell_id']}|{role}|{fold_part}|{seed_part}":
        raise ValueError("result run ID differs from canonical run identity")
    for field in (
        "population_authority_sha256",
        "configuration_sha256",
        "environment_sha256",
        "manifest_sha256",
    ):
        _sha256(value[field], field)
    if value["population_authority_sha256"] != population.manifest_sha256:
        raise ValueError("result uses a different population authority")
    # Also reject a caller-constructed authority with the wrong role membership.
    for population_role in ("training", "validation", "evaluation"):
        if list(population.match_ids(population_role)) != roles[population_role]:
            raise ValueError("result population roles differ from protocol")
    status = value["status"]
    contract = _mapping(plan["result_manifest_schema"], "result contract")
    if status not in _list(contract["status_values"], "statuses"):
        raise ValueError("unsupported result status")
    reasons = _mapping(contract["stopping_reasons_by_status"], "stopping reasons")
    if value["stopping_reason"] not in _list(reasons[cast(str, status)], "status reasons"):
        raise ValueError("result stopping reason contradicts status")
    completed = status == "completed"
    if completed and learned:
        _sha256(value["checkpoint_sha256"], "completed learned checkpoint")
        step = value["selected_step"]
        if type(step) is not int or not 100 <= step <= 5000 or step % 100:
            raise ValueError("selected checkpoint step differs from validation cadence")
        if value["stopping_reason"] == "baseline_complete":
            raise ValueError("learned result cannot use baseline stopping reason")
    else:
        if value["checkpoint_sha256"] is not None or value["selected_step"] is not None:
            raise ValueError("baseline or unsuccessful result cannot publish a checkpoint")
        if completed and value["stopping_reason"] != "baseline_complete":
            raise ValueError("baseline completion requires baseline stopping reason")
    artifacts = _list(value["output_artifacts"], "output artifacts")
    artifact_ids: set[str] = set()
    for item in artifacts:
        artifact = _mapping(item, "artifact")
        _keys(artifact, {"artifact_id", "sha256", "relation"}, "artifact")
        identity = artifact["artifact_id"]
        if not isinstance(identity, str) or not identity or identity in artifact_ids:
            raise ValueError("artifact IDs must be nonempty and unique")
        artifact_ids.add(identity)
        _sha256(artifact["sha256"], "artifact digest")
        if artifact["relation"] not in {"output", "diagnostic"}:
            raise ValueError("unsupported result artifact relation")
    metrics = _list(value["metrics"], "metrics")
    expected = {
        (scope, match, metric)
        for scope, matches in (
            ("validation_match", validation),
            ("evaluation_match", evaluation if role != "lomo" else []),
            (
                "lomo_held_out_match",
                [held_out] if role == "lomo" else training if role == "baseline" else [],
            ),
        )
        for match in matches
        for metric in ("ade_m", "fde_m", "xy_rmse_m")
    }
    actual: set[tuple[str, str, str]] = set()
    for item in metrics:
        metric = _mapping(item, "metric")
        _keys(metric, {"scope", "match_id", "metric_id", "value", "unit"}, "metric")
        identity_fields = (metric["scope"], metric["match_id"], metric["metric_id"])
        if not all(isinstance(part, str) for part in identity_fields):
            raise ValueError("metric identity fields must be strings")
        identity = cast(tuple[str, str, str], identity_fields)
        number = metric["value"]
        if (
            identity in actual
            or identity not in expected
            or metric["unit"] != "metres"
            or isinstance(number, bool)
            or not isinstance(number, int | float)
            or not math.isfinite(number)
            or number < 0
        ):
            raise ValueError("invalid, duplicate, or out-of-scope result metric")
        actual.add(identity)
    if (completed and actual != expected) or (not completed and metrics):
        raise ValueError("result status requires complete metrics or no metrics on failure")
    if value["manifest_sha256"] != _digest(
        {key: item for key, item in value.items() if key != "manifest_sha256"}
    ):
        raise ValueError("result canonical manifest SHA-256 mismatch")


def validate_prospective_result_document_v2(
    document: Mapping[str, object],
    population: EvaluationPopulationAuthorityV2,
) -> None:
    """Validate result structure; empirical results additionally require protected-population."""
    if document.get("status") != "failed_validation":
        population.require_empirical_qualification()
    value = _mapping(document, "v2 result manifest")
    plan = load_empirical_experiment_plan_v2()
    validate_empirical_experiment_plan_v2_document(plan)
    contract = _mapping(plan.get("result_manifest_schema"), "v2 result contract")
    required = _list(contract.get("required_fields"), "v2 result fields")
    _keys(value, set(cast(list[str], required)), "v2 result manifest")
    expected_bindings: dict[str, object] = {
        "schema_id": "fpdbench.prospective-experiment-result",
        "schema_version": "2.0.0",
        "source_release_id": population.source_release_id,
        "source_release_version": population.source_release_version,
        "source_release_hash": population.source_release_hash,
        "source_population_hash": population.source_population_hash,
        "measurement_state_id": population.measurement_state_id,
        "measurement_state_version": population.measurement_state_version,
        "measurement_state_hash": population.measurement_state_hash,
        "eligibility_policy_id": population.eligibility_policy_id,
        "eligibility_policy_version": population.eligibility_policy_version,
        "eligibility_policy_hash": population.eligibility_policy_hash,
        "protocol_id": population.protocol_id,
        "protocol_version": population.protocol_version,
        "protocol_sha256": population.protocol_sha256,
        "plan_id": population.plan_id,
        "plan_version": population.plan_version,
        "plan_sha256": population.plan_sha256,
        "population_id": population.population_id,
        "population_schema_id": _SCHEMA_ID,
        "population_schema_version": _SCHEMA_VERSION_V2,
        "population_authority_sha256": population.manifest_sha256,
    }
    for field, expected in expected_bindings.items():
        if value.get(field) != expected:
            raise ValueError(f"v2 result {field} differs from its bound authority")
    if (
        population.source_release_hash != EXPECTED_SOURCE_RELEASE_HASH
        or population.source_population_hash != EXPECTED_SOURCE_POPULATION_HASH
        or population.measurement_state_hash != EXPECTED_MEASUREMENT_STATE_V2_HASH
        or population.eligibility_policy_hash != EXPECTED_ELIGIBILITY_POLICY_V2_HASH
        or population.protocol_sha256 != PROTOCOL_V2_SHA256
        or population.plan_sha256 != PLAN_V2_SHA256
        or population.ball_null_flag_finite_xy_count != 0
    ):
        raise ValueError("v2 result population is not bound to the qualified authority chain")
    if value["manifest_sha256"] != _digest(
        {key: item for key, item in value.items() if key != "manifest_sha256"}
    ):
        raise ValueError("v2 result canonical manifest SHA-256 mismatch")

    v2_roles = _mapping(protocol_split_v2()["roles"], "v2 match roles")
    for role in ("training", "validation", "evaluation"):
        if list(population.match_ids(role)) != v2_roles[role]:
            raise ValueError("v2 population roles differ from the successor protocol")

    # Run the shared metric/run checks after validating every v2 identity above.
    v1_plan = load_empirical_experiment_plan()
    v1_protocol = load_prospective_protocol()
    v1_fields = _list(
        _mapping(v1_plan.get("result_manifest_schema"), "v1 result contract").get(
            "required_fields"
        ),
        "v1 result fields",
    )
    semantic_value = {field: value[field] for field in cast(list[str], v1_fields)}
    semantic_value.update(
        schema_version="1.1.0",
        plan_id=v1_plan["plan_id"],
        plan_version=v1_plan["plan_version"],
        plan_sha256=v1_plan["plan_sha256"],
        protocol_id=v1_protocol["protocol_id"],
        protocol_version=v1_protocol["protocol_version"],
        protocol_sha256=v1_protocol["protocol_sha256"],
    )
    semantic_value["manifest_sha256"] = _digest(
        {key: item for key, item in semantic_value.items() if key != "manifest_sha256"}
    )
    validate_prospective_result_document(
        semantic_value,
        cast(EvaluationPopulationAuthority, population),
    )


def load_prospective_result_v2(
    path: Path, population: EvaluationPopulationAuthorityV2
) -> dict[str, object]:
    """Read duplicate-key-safe restricted v2 result JSON and validate before use."""
    value = _mapping(
        json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object),
        "v2 result manifest",
    )
    validate_prospective_result_document_v2(value, population)
    return dict(value)


def load_prospective_result(
    path: Path, population: EvaluationPopulationAuthority
) -> dict[str, object]:
    """Read duplicate-key-safe restricted result JSON and validate it before use."""
    value = _mapping(
        json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object),
        "result manifest",
    )
    validate_prospective_result_document(value, population)
    return dict(value)


__all__ = [
    "EvaluationPopulationAuthority",
    "EvaluationPopulationAuthorityV2",
    "EvaluationPopulationOutput",
    "MatchMembership",
    "POPULATION_SCHEMA_FILE",
    "POPULATION_SCHEMA_V2_FILE",
    "PopulationBoundScene",
    "PopulationBoundWindow",
    "SceneMembership",
    "WindowMembership",
    "load_prospective_result",
    "load_prospective_result_v2",
    "validate_prospective_result_document",
    "validate_prospective_result_document_v2",
    "load_evaluation_population_authority",
    "load_evaluation_population_authority_v2",
    "prospective_window_id",
    "prospective_window_id_v2",
    "truth_mask_sha256",
    "truth_sha256",
    "validate_evaluation_population_authority_document",
    "validate_evaluation_population_authority_v2_document",
    "validate_evaluation_population_schema",
    "validate_evaluation_population_schema_v2",
    "validate_population_bound_evaluation",
]
