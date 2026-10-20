"""First population producer: synthetic, immutable, and never empirical authority."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal, cast

from fpdbench.data_sources.skillcorner import canonical_bytes
from fpdbench.data_sources.skillcorner import load_manifest as load_source_manifest
from fpdbench.data_states.skillcorner import iter_skillcorner_5hz_v2
from fpdbench.eligibility.skillcorner import (
    PhaseInterval,
    diagnose_skillcorner_window_v2,
    skillcorner_period_ranges,
    validate_ball_population_drift_v2,
)

from .empirical_experiment_plan import PLAN_V2_SHA256, protocol_split_v2
from .evaluation_population import (
    prospective_window_id_v2,
    truth_mask_sha256,
    truth_sha256,
    validate_evaluation_population_authority_v2_document,
)
from .prospective_protocol import (
    EXPECTED_ELIGIBILITY_POLICY_V2_HASH,
    EXPECTED_MEASUREMENT_STATE_V2_HASH,
    EXPECTED_SOURCE_POPULATION_HASH,
    EXPECTED_SOURCE_RELEASE_HASH,
    PROTOCOL_V2_SHA256,
)

PRODUCER_VERSION = "res501-population-producer/2"
type Pair = tuple[float, float]
type Panel = tuple[tuple[Pair | None, ...], ...]


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _digest(value: object) -> str:
    return _sha(canonical_bytes(value))


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast(dict[str, object], value)


def _list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a JSON array")
    return cast(list[object], value)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _json(payload: bytes) -> object:
    def reject_constant(_: str) -> object:
        raise ValueError("nonfinite JSON constant")

    return json.loads(payload, object_pairs_hook=_unique_object, parse_constant=reject_constant)


@dataclass(frozen=True, slots=True)
class PopulationMatchInputV2:
    """Immutable input snapshots; phase JSON is normalized, not a source CSV receipt."""

    match_id: str
    metadata_json: bytes
    tracking_jsonl: bytes
    phase_intervals_json: bytes


@dataclass(frozen=True, slots=True)
class PopulationVerificationSubmissionV2:
    """Restricted wire interface for a separately authored verifier; no PASS field."""

    manifest_json: bytes
    candidates_jsonl: bytes
    truth_jsonl: bytes
    receipt_json: bytes
    diagnostic_census_jsonl: bytes = b""
    status: Literal["UNQUALIFIED"] = field(default="UNQUALIFIED", init=False)

    def require_empirical_qualification(self) -> None:
        raise ValueError("independent protected verification required; producer is UNQUALIFIED")


class IncompletePopulationV2(ValueError):
    """No draft authority returned for an incomplete or unscoreable required cohort."""

    def __init__(self, receipt_json: bytes) -> None:
        self.receipt_json = receipt_json
        super().__init__("incomplete population; every required match needs a scoreable window")


def _roles() -> tuple[tuple[str, str], ...]:
    roles = _mapping(protocol_split_v2()["roles"], "protocol roles")
    return tuple(
        (role, cast(str, match))
        for role in ("training", "validation", "evaluation")
        for match in _list(roles[role], "role matches")
    )


def _players(sample: Mapping[str, object]) -> dict[int, Mapping[str, object]]:
    return {
        cast(int, player["player_id"]): player
        for value in _list(sample["players"], "players")
        for player in [_mapping(value, "player")]
    }


def _pair(player: Mapping[str, object] | None) -> Pair | None:
    if player is None or player["x_m"] is None or player["y_m"] is None:
        return None
    # The canonical parser validates numeric types and finite coordinates.
    return float(cast(float, player["x_m"])), float(cast(float, player["y_m"]))


def _scene(
    support: Sequence[Mapping[str, object] | None],
    side: str,
) -> tuple[dict[str, object], dict[str, object], bool]:
    origin = support[25]
    assert origin is not None
    targets = [
        (player_id, cast(Pair, _pair(player)))
        for player_id, player in sorted(_players(origin).items())
        if player["group"] == side and _pair(player) is not None
    ]
    absolute: list[tuple[Pair | None, ...]] = []
    displacement: list[tuple[Pair | None, ...]] = []
    for sample in support[26:]:
        assert sample is not None
        players = _players(sample)
        row = tuple(_pair(players.get(player_id)) for player_id, _ in targets)
        absolute.append(row)
        displacement.append(
            tuple(
                None if xy is None else (xy[0] - anchor[0], xy[1] - anchor[1])
                for xy, (_, anchor) in zip(row, targets, strict=True)
            )
        )
    xy_panel: Panel = tuple(absolute)
    delta_panel: Panel = tuple(displacement)
    mask_digest = truth_mask_sha256(xy_panel)
    assert truth_mask_sha256(delta_panel) == mask_digest
    membership: dict[str, object] = {
        "scene_id": side,
        "player_ids": [str(player_id) for player_id, _ in targets],
        "absolute_xy_truth_sha256": truth_sha256(xy_panel, target_representation="absolute_xy"),
        "displacement_truth_sha256": truth_sha256(
            delta_panel, target_representation="origin_relative_displacement"
        ),
        "truth_mask_sha256": mask_digest,
    }
    scoreable = any(pair is not None for pair in xy_panel[-1])
    truth: dict[str, object] = {
        **membership,
        "origin_xy": [anchor for _, anchor in targets],
        "absolute_xy": xy_panel,
        "origin_relative_displacement": delta_panel,
        "truth_mask": [[pair is not None for pair in row] for row in xy_panel],
        "scoreable": scoreable,
        "unscoreable_reason": None if scoreable else "NO_FINAL_TARGET",
    }
    return membership, truth, scoreable


def produce_population_draft_v2(
    inputs: Sequence[PopulationMatchInputV2],
    *,
    input_kind: Literal["synthetic"],
) -> PopulationVerificationSubmissionV2:
    """Enumerate the whole fixture cohort; never accept or authenticate real-source data.

    No filesystem reader/writer or empirical gate is installed. The restricted
    adapter must later verify all 81 pinned files and independently checked coverage.
    """
    if input_kind != "synthetic":
        raise ValueError("restricted real-source processing is not authorized")
    roles = _roles()
    release_id = cast(str, load_source_manifest()["source_release_id"])
    expected_ids = {match for _, match in roles}
    if len(inputs) != 20 or {item.match_id for item in inputs} != expected_ids:
        raise ValueError("incomplete population: require exactly the pinned 20 matches")
    by_match = {item.match_id: item for item in inputs}
    # shortcut: hold fixtures in memory, add restricted streaming before real runs.
    prepared: dict[
        str,
        tuple[
            Mapping[str, object],
            tuple[dict[str, object], ...],
            tuple[PhaseInterval, ...],
            dict[int, tuple[int, int]],
        ],
    ] = {}
    input_receipts: list[dict[str, object]] = []
    for _, match_id in roles:
        item = by_match[match_id]
        if any(
            not isinstance(cast(object, payload), bytes)
            for payload in (item.metadata_json, item.tracking_jsonl, item.phase_intervals_json)
        ):
            raise ValueError("input snapshots must be immutable bytes")
        metadata = _mapping(_json(item.metadata_json), "match metadata")
        if type(metadata.get("id")) is not int or str(metadata["id"]) != match_id:
            raise ValueError("input match identity drift")
        periods, issues = skillcorner_period_ranges(metadata)
        if issues or not periods or any(period not in {1, 2} for period in periods):
            raise ValueError("invalid or unavailable period bounds")
        frames = tuple(
            _mapping(_json(line), "tracking frame") for line in item.tracking_jsonl.splitlines()
        )
        if not frames:
            raise ValueError("incomplete population: empty tracking payload")
        samples = tuple(iter_skillcorner_5hz_v2(frames, metadata, source_release_id=release_id))
        parsed_phases: list[PhaseInterval] = []
        for value in _list(_json(item.phase_intervals_json), "normalized phase intervals"):
            phase = _mapping(value, "phase")
            if set(phase) != {"period", "frame_start", "frame_end"} or any(
                type(phase[key]) is not int for key in phase
            ):
                raise ValueError("invalid normalized phase interval")
            parsed_phases.append(
                PhaseInterval(
                    release_id,
                    int(match_id),
                    cast(int, phase["period"]),
                    cast(int, phase["frame_start"]),
                    cast(int, phase["frame_end"]),
                )
            )
        prepared[match_id] = metadata, samples, tuple(parsed_phases), periods
        input_receipts.append(
            {
                "match_id": match_id,
                "inputs": {
                    name: {"sha256": _sha(payload), "byte_size": len(payload)}
                    for name, payload in (
                        ("metadata_json", item.metadata_json),
                        ("tracking_jsonl", item.tracking_jsonl),
                        ("normalized_phase_intervals_json", item.phase_intervals_json),
                    )
                },
                "source_frame_count": len(frames),
                "retained_sample_count": len(samples),
                "retained_samples_sha256": _digest(samples),
            }
        )
    # This scan precedes every candidate decision, retained membership and truth mask.
    scan = validate_ball_population_drift_v2(
        sample for _, match_id in roles for sample in prepared[match_id][1]
    )
    candidates: list[dict[str, object]] = []
    diagnostic_census: list[dict[str, object]] = []
    origins: list[dict[str, str]] = []
    diagnostic_origins: list[dict[str, str]] = []
    truths: list[dict[str, object]] = []
    matches: list[dict[str, object]] = []
    counts: list[dict[str, object]] = []
    for role, match_id in roles:
        metadata, samples, phases, periods = prepared[match_id]
        indexed = {cast(int, sample["source_frame"]): sample for sample in samples}
        windows: list[dict[str, object]] = []
        candidate_origins: list[dict[str, str]] = []
        match_diagnostic_origins: list[dict[str, str]] = []
        candidate_count = diagnostic_count = scoreable_windows = scoreable_scenes = 0
        candidate_exclusions: dict[str, int] = {}
        candidate_warnings: dict[str, int] = {}
        diagnostic_exclusions: dict[str, int] = {}
        diagnostic_warnings: dict[str, int] = {}
        for period, (start, end) in sorted(periods.items()):
            for frame in range(start + start % 2, end, 2):
                origin_id = f"period_{period}/sample_{frame // 2}"
                identity = {"match_id": match_id, "origin_sample_id": origin_id}
                diagnostic_origins.append(identity)
                match_diagnostic_origins.append(identity)
                diagnostic_count += 1
                support = tuple(indexed.get(frame + offset * 2) for offset in range(-25, 16))
                diagnostic = diagnose_skillcorner_window_v2(
                    support,
                    history_intervals=25,
                    future_intervals=15,
                    match_metadata=metadata,
                    phase_intervals=phases,
                )
                decision = asdict(diagnostic)
                decision_hash = _digest(decision)
                row = {
                    **identity,
                    "diagnostic": decision,
                    "eligibility_result_sha256": decision_hash,
                }
                diagnostic_census.append(row)
                for issues, totals in (
                    (diagnostic.exclusion_reasons, diagnostic_exclusions),
                    (diagnostic.warnings, diagnostic_warnings),
                ):
                    for code in {issue.code for issue in issues}:
                        totals[code] = totals.get(code, 0) + 1
                complete_support = indexed.get(frame) is not None and all(
                    sample is not None for sample in support
                )
                if complete_support:
                    origins.append(identity)
                    candidate_origins.append(identity)
                    candidate_count += 1
                    candidates.append(row)
                    for issues, totals in (
                        (diagnostic.exclusion_reasons, candidate_exclusions),
                        (diagnostic.warnings, candidate_warnings),
                    ):
                        for code in {issue.code for issue in issues}:
                            totals[code] = totals.get(code, 0) + 1
                if not complete_support or not diagnostic.candidate_rules_pass:
                    continue
                window_id = prospective_window_id_v2(match_id, origin_id)
                scenes: list[dict[str, object]] = []
                window_scoreable = False
                for side in ("home", "away"):
                    membership, truth, scoreable = _scene(support, side)
                    scenes.append(membership)
                    truths.append({**identity, "window_id": window_id, **truth})
                    scoreable_scenes += int(scoreable)
                    window_scoreable |= scoreable
                scoreable_windows += int(window_scoreable)
                windows.append(
                    {
                        "window_id": window_id,
                        "origin_sample_id": origin_id,
                        "eligibility_result_sha256": decision_hash,
                        "scenes": scenes,
                    }
                )
        matches.append({"role": role, "match_id": match_id, "windows": windows})
        counts.append(
            {
                "role": role,
                "match_id": match_id,
                "candidate_origin_population_sha256": _digest(candidate_origins),
                "candidate_window_count": candidate_count,
                "eligible_window_count": len(windows),
                "excluded_window_count": candidate_count - len(windows),
                "diagnostic_origin_count": diagnostic_count,
                "diagnostic_origin_census_sha256": _digest(match_diagnostic_origins),
                "diagnostic_excluded_window_count": diagnostic_count - len(windows),
                "directed_scene_count": len(windows) * 2,
                "scoreable_scene_count": scoreable_scenes,
                "scoreable_window_count": scoreable_windows,
                "exclusion_window_counts": candidate_exclusions,
                "warning_window_counts": candidate_warnings,
                "diagnostic_exclusion_window_counts": diagnostic_exclusions,
                "diagnostic_warning_window_counts": diagnostic_warnings,
            }
        )
    candidate_bytes = b"".join(canonical_bytes(row) + b"\n" for row in candidates)
    diagnostic_census_bytes = b"".join(
        canonical_bytes(row) + b"\n" for row in diagnostic_census
    )
    receipt: dict[str, object] = {
        "schema_id": "fpdbench.population-producer-receipt",
        "schema_version": "1.0.0",
        "status": "UNQUALIFIED",
        "input_kind": input_kind,
        "producer_version": PRODUCER_VERSION,
        "producer_code_sha256": _sha(Path(__file__).read_bytes()),
        "authority_bindings": {
            "source_release_hash": EXPECTED_SOURCE_RELEASE_HASH,
            "source_population_hash": EXPECTED_SOURCE_POPULATION_HASH,
            "measurement_state_hash": EXPECTED_MEASUREMENT_STATE_V2_HASH,
            "eligibility_policy_hash": EXPECTED_ELIGIBILITY_POLICY_V2_HASH,
            "protocol_sha256": PROTOCOL_V2_SHA256,
            "plan_sha256": PLAN_V2_SHA256,
        },
        "source_byte_qualified": False,
        "independent_verification": "NOT_PERFORMED",
        "input_receipts": input_receipts,
        "match_counts": counts,
        "candidate_origin_population_sha256": _digest(origins),
        "diagnostic_origin_census_count": len(diagnostic_origins),
        "diagnostic_origin_census_sha256": _digest(diagnostic_origins),
        "candidates_jsonl_sha256": _sha(candidate_bytes),
        "diagnostic_census_jsonl_sha256": _sha(diagnostic_census_bytes),
        "drift_scan": asdict(scan),
    }
    if any(cast(int, count["scoreable_window_count"]) == 0 for count in counts):
        receipt["status"] = "INCOMPLETE"
        receipt["receipt_sha256"] = _digest(receipt)
        raise IncompletePopulationV2(canonical_bytes(receipt))
    manifest: dict[str, object] = {
        "schema_id": "fpdbench.prospective-evaluation-population",
        "schema_version": "2.0.0",
        "population_id": "skillcorner.prospective.conditional_motion.population_v2",
        "source_release_id": "skillcorner_open_data_v1",
        "source_release_version": "1.0.0",
        "source_release_hash": EXPECTED_SOURCE_RELEASE_HASH,
        "source_population_hash": EXPECTED_SOURCE_POPULATION_HASH,
        "measurement_state_id": "skillcorner_5hz_v2",
        "measurement_state_version": "2.0.0",
        "measurement_state_hash": EXPECTED_MEASUREMENT_STATE_V2_HASH,
        "eligibility_policy_id": "skillcorner_window_v2",
        "eligibility_policy_version": "2.0.0",
        "eligibility_policy_hash": EXPECTED_ELIGIBILITY_POLICY_V2_HASH,
        "protocol_id": "skillcorner.prospective_conditional_motion",
        "protocol_version": "2.0.0",
        "protocol_sha256": PROTOCOL_V2_SHA256,
        "plan_id": "skillcorner.prospective_conditional_motion.execution",
        "plan_version": "2.0.0",
        "plan_sha256": PLAN_V2_SHA256,
        "ball_null_flag_finite_xy_count": 0,
        "candidate_window_count": len(origins),
        "eligible_window_count": sum(cast(int, count["eligible_window_count"]) for count in counts),
        "candidate_origin_population_sha256": _digest(origins),
        "matches": matches,
        "membership_sha256": _digest(matches),
    }
    manifest["manifest_sha256"] = _digest(manifest)
    validate_evaluation_population_authority_v2_document(manifest)
    truth_bytes = b"".join(canonical_bytes(row) + b"\n" for row in truths)
    receipt.update(
        population_manifest_sha256=manifest["manifest_sha256"],
        truth_jsonl_sha256=_sha(truth_bytes),
    )
    receipt["receipt_sha256"] = _digest(receipt)
    return PopulationVerificationSubmissionV2(
        canonical_bytes(manifest),
        candidate_bytes,
        truth_bytes,
        canonical_bytes(receipt),
        diagnostic_census_bytes,
    )
