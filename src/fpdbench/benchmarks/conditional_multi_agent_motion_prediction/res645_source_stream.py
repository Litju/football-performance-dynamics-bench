# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportPrivateUsage=false
"""Read-only adapter from the canonical SkillCorner source contract to ordered scientific windows.

One forward pass over a match's tracking JSONL (after a first identity/drift pass) yields, per
eligible origin, the frozen 25-history + origin + 15-future support, directed home/away scenes,
physical XY metres, per-player per-step truth masks and quality/missingness categories. Only a
bounded deque of 41 canonical samples and the current locked row are resident.

Qualification in RES645 is synthetic only: ``mode="synthetic"`` demands an invented-fixture marker
and refuses every protocol evaluation match identity. ``mode="frozen"`` raises until a separate
owner decision (RES646) supplies an authorization this module does not know how to create.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, cast

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.evaluation_population import (
    prospective_window_id_v2,
)
from fpdbench.data_sources.skillcorner import canonical_bytes
from fpdbench.data_sources.skillcorner import load_manifest as load_source_manifest
from fpdbench.data_states.skillcorner import iter_skillcorner_5hz_v2
from fpdbench.eligibility.skillcorner import (
    BallPopulationQualificationStop,
    PhaseInterval,
    diagnose_skillcorner_window_v2,
    skillcorner_period_ranges,
    validate_ball_population_drift_v2,
)

from . import res645_paths as paths
from .empirical_experiment_plan import protocol_split_v2
from .streaming_population_producer_v1 import _population_events, _scene

SOURCE_MARKER = "RES645-SYNTHETIC-SOURCE-FIXTURE-v1"
MAX_ROW_BYTES = 1024 * 1024
MAX_SMALL_BYTES = 16 * 1024 * 1024
MAX_TRACKING_BYTES = 8 * 1024**3
type Document = dict[str, Any]
type Mode = Literal["synthetic", "frozen"]


@dataclass(frozen=True, slots=True)
class SourceMatchSpec:
    """Match inputs with an optional separately stored population lock."""

    label: str
    match_id: str
    directory: Path
    role: str = "evaluation"
    locked_path: Path | None = None


def evaluation_match_ids() -> frozenset[str]:
    roles = cast(Mapping[str, Sequence[str]], protocol_split_v2()["roles"])
    return frozenset(roles["evaluation"])


def authorize(spec: SourceMatchSpec, mode: Mode) -> None:
    """Gate every open. No real held-out access can be granted from this module."""
    if mode == "frozen":
        raise PermissionError(
            "real source access requires the separate RES646 owner decision; not authorized"
        )
    if mode != "synthetic":
        raise PermissionError("unknown source mode")
    if spec.role != "evaluation":
        raise ValueError("source role must be evaluation")
    paths.reject_unsafe_path(spec.directory)
    if not spec.label.startswith("synthetic-match-") or spec.match_id in evaluation_match_ids():
        raise PermissionError("synthetic fixtures cannot carry a held-out evaluation identity")
    raw, _ = paths.read_regular_file(spec.directory / "fixture.json", max_bytes=4096)
    marker = json.loads(raw)
    if marker != {"synthetic_source_fixture": SOURCE_MARKER, "match_id": spec.match_id}:
        raise PermissionError("source directory is not an invented RES645 fixture")
    if spec.locked_path is not None:
        raw, _ = paths.read_regular_file(spec.locked_path.parent / "fixture.json", max_bytes=4096)
        if json.loads(raw) != marker:
            raise PermissionError("separate lock directory is not the same synthetic fixture")


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def parse_json(payload: bytes) -> object:
    def reject(_: str) -> object:
        raise ValueError("nonfinite JSON constant")

    return json.loads(payload, object_pairs_hook=_unique, parse_constant=reject)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return cast(Mapping[str, object], value)


def roster(metadata: Mapping[str, object]) -> tuple[list[int], list[int]]:
    home = cast(int, _mapping(metadata["home_team"], "home team")["id"])
    away = cast(int, _mapping(metadata["away_team"], "away team")["id"])
    home_ids: list[int] = []
    away_ids: list[int] = []
    for raw in cast(list[object], metadata.get("players")):
        player = _mapping(raw, "roster player")
        pid, team = player.get("id"), player.get("team_id")
        if type(pid) is not int or type(team) is not int:
            raise ValueError("roster identities must be integers")
        if team == home:
            home_ids.append(pid)
        elif team == away:
            away_ids.append(pid)
        else:
            raise ValueError("roster player outside the frozen teams")
    if not home_ids or not away_ids or set(home_ids) & set(away_ids):
        raise ValueError("two disjoint nonempty rosters required")
    return sorted(home_ids), sorted(away_ids)


@dataclass(slots=True)
class _Pass:
    bytes_read: int = 0
    frames: int = 0
    samples: int = 0
    raw: Any = None
    canonical: Any = None


class SourceMatch:
    """Opened, validated match. ``prepare`` is the mandatory first pass; ``windows`` the second."""

    def __init__(self, spec: SourceMatchSpec, mode: Mode) -> None:
        authorize(spec, mode)
        self.spec = spec
        meta_bytes, self.metadata_identity = paths.read_regular_file(
            spec.directory / "metadata.json", max_bytes=MAX_SMALL_BYTES
        )
        phase_bytes, self.phase_identity = paths.read_regular_file(
            spec.directory / "phases.json", max_bytes=MAX_SMALL_BYTES
        )
        self.metadata = _mapping(parse_json(meta_bytes), "match metadata")
        if type(self.metadata.get("id")) is not int or str(self.metadata["id"]) != spec.match_id:
            raise ValueError("source match identity differs from the requested identity")
        self.periods, issues = skillcorner_period_ranges(self.metadata)
        if issues or not self.periods or any(p not in {1, 2} for p in self.periods):
            raise ValueError("invalid or unavailable period bounds")
        self.release_id = cast(str, load_source_manifest()["source_release_id"])
        phases = parse_json(phase_bytes)
        if not isinstance(phases, list):
            raise ValueError("phase intervals must be an array")
        self.phases: tuple[PhaseInterval, ...] = tuple(
            PhaseInterval(
                self.release_id,
                int(spec.match_id),
                cast(int, p["period"]),
                cast(int, p["frame_start"]),
                cast(int, p["frame_end"]),
            )
            for p in (_mapping(v, "phase") for v in cast(list[object], phases))
            if set(p) == {"period", "frame_start", "frame_end"}
            and all(type(p[k]) is int for k in p)
        )
        if len(self.phases) != len(cast(list[object], phases)):
            raise ValueError("invalid normalized phase interval")
        self.home_ids, self.away_ids = roster(self.metadata)
        self.tracking_identity: paths.FileIdentity | None = None
        self.source_sha256: str | None = None
        self.samples_checked = 0
        self.tracking_raw_sha256: str | None = None
        self.locked_sha256: str | None = None

    # -- streamed tracking rows -------------------------------------------------------------
    def _samples(self, state: _Pass) -> Iterator[dict[str, object]]:
        fd = paths.open_regular_fd(self.spec.directory / "tracking.jsonl")
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            paths.check_regular(before, max_bytes=MAX_TRACKING_BYTES, require_private=False)
            state.raw, state.canonical = hashlib.sha256(), hashlib.sha256()

            def frames() -> Iterator[Mapping[str, object]]:
                while line := stream.readline(MAX_ROW_BYTES + 1):
                    if len(line) > MAX_ROW_BYTES or not line.strip():
                        raise ValueError("oversized or empty tracking JSONL row")
                    state.raw.update(line)
                    state.bytes_read += len(line)
                    state.frames += 1
                    yield _mapping(parse_json(line), "tracking frame")

            for sample in iter_skillcorner_5hz_v2(
                frames(), self.metadata, source_release_id=self.release_id
            ):
                state.canonical.update(canonical_bytes(sample) + b"\n")
                state.samples += 1
                yield sample
            after = os.fstat(stream.fileno())
        if paths.stat_key(before) != paths.stat_key(after) or state.bytes_read != after.st_size:
            raise ValueError("tracking input changed while being read")

    def prepare(self, check: Callable[[], None] = lambda: None) -> None:
        """Pass 1: pinned-source/drift sentinel, identity digest and stream-size accounting."""
        state = _Pass()

        def watched() -> Iterator[dict[str, object]]:
            for sample in self._samples(state):
                check()
                yield sample

        try:
            scan = validate_ball_population_drift_v2(watched())
        except BallPopulationQualificationStop as exc:
            raise ValueError("ball null-flag/finite-XY drift sentinel observed") from exc
        if scan.null_flag_finite_xy_count or state.frames == 0:
            raise ValueError("incomplete or drifting source population")
        self.samples_checked = state.samples
        self.tracking_raw_sha256 = cast(str, state.raw.hexdigest())
        self.source_sha256 = hashlib.sha256(
            canonical_bytes(
                {
                    "tracking_raw_sha256": state.raw.hexdigest(),
                    "canonical_samples_sha256": state.canonical.hexdigest(),
                    "metadata_sha256": self.metadata_identity.sha256,
                    "phases_sha256": self.phase_identity.sha256,
                    "frames": state.frames,
                    "samples": state.samples,
                }
            )
        ).hexdigest()
        self._expected_canonical = state.canonical.hexdigest()

    # -- ordered scientific windows ---------------------------------------------------------
    def windows(
        self, check: Callable[[], None] = lambda: None, limit: int | None = None
    ) -> Iterator[Document]:
        if self.source_sha256 is None:
            raise ValueError("prepare() is mandatory before windows()")
        locked_fd = paths.open_regular_fd(
            self.spec.locked_path or self.spec.directory / "locked.jsonl"
        )
        state = _Pass()
        eligible = 0
        locked_hash = hashlib.sha256()
        with os.fdopen(locked_fd, "rb") as locked:
            paths.check_regular(
                os.fstat(locked.fileno()), max_bytes=MAX_TRACKING_BYTES, require_private=False
            )
            for (period, frame, origin_id), support in _population_events(
                self._samples(state), self.periods
            ):
                check()
                line = locked.readline(MAX_ROW_BYTES + 1)
                if not line or len(line) > MAX_ROW_BYTES:
                    raise ValueError("locked population ended before its source")
                locked_hash.update(line)
                row = _mapping(parse_json(line), "locked population row")
                if (
                    row.get("match_id"),
                    row.get("role"),
                    row.get("period"),
                    row.get("source_frame"),
                    row.get("origin_sample_id"),
                ) != (self.spec.match_id, self.spec.role, period, frame, origin_id):
                    raise ValueError("source origin differs from the frozen population stream")
                complete = len(support) == 41 and all(s is not None for s in support)
                diagnostic = diagnose_skillcorner_window_v2(
                    support,
                    history_intervals=25,
                    future_intervals=15,
                    match_metadata=self.metadata,
                    phase_intervals=self.phases,
                )
                locked_id = row.get("window_id")
                is_eligible = complete and diagnostic.candidate_rules_pass
                if (locked_id is not None) != is_eligible:
                    raise ValueError("eligibility differs from the frozen population stream")
                if not is_eligible:
                    continue
                window_id = prospective_window_id_v2(self.spec.match_id, origin_id)
                if locked_id != window_id:
                    raise ValueError("window identity differs from original v2")
                yield self._window(row, support, diagnostic, eligible, window_id, origin_id)
                eligible += 1
                if limit is not None and eligible >= limit:
                    return
            if limit is None:
                if locked.readline():
                    raise ValueError("locked population has rows beyond the source")
                if state.canonical.hexdigest() != self._expected_canonical:
                    raise ValueError("tracking content differs between passes")
                self.locked_sha256 = locked_hash.hexdigest()

    def source_document(self) -> Document:
        """Source identities for the receipt; complete only after a full ``windows()`` pass."""
        return {
            "tracking_raw_sha256": self.tracking_raw_sha256,
            "metadata_sha256": self.metadata_identity.sha256,
            "phases_sha256": self.phase_identity.sha256,
            "locked_sha256": self.locked_sha256,
            "source_sha256": self.source_sha256,
            "canonical_samples": self.samples_checked,
        }

    def _window(
        self,
        row: Mapping[str, object],
        support: Sequence[Mapping[str, object] | None],
        diagnostic: Any,
        ordinal: int,
        window_id: str,
        origin_id: str,
    ) -> Document:
        complete = cast(Sequence[Mapping[str, object]], support)
        locked_scenes = cast(list[object], row.get("scenes"))
        if len(locked_scenes) != 2:
            raise ValueError("locked row must carry home and away scenes")
        scenes: list[Document] = []
        for side, locked in zip(("home", "away"), locked_scenes, strict=True):
            _, truth, scoreable = _scene(support, side)
            if canonical_bytes(truth) != canonical_bytes(locked):
                raise ValueError("source truth or mask differs from the frozen population")
            player_ids = [int(v) for v in cast(list[str], truth["player_ids"])]
            scene: Document = {
                "scene_id": side,
                "player_ids": player_ids,
                "origin_xy": [list(p) for p in cast(list[Any], truth["origin_xy"])],
                "absolute_xy": [
                    [None if p is None else list(p) for p in step]
                    for step in cast(list[Any], truth["absolute_xy"])
                ],
                "origin_relative_displacement": [
                    [None if p is None else list(p) for p in step]
                    for step in cast(list[Any], truth["origin_relative_displacement"])
                ],
                "truth_mask": truth["truth_mask"],
                "scoreable": scoreable,
                "truth_mask_sha256": truth["truth_mask_sha256"],
            }
            scene["quality"], scene["missingness"] = quality_and_missingness(complete, player_ids)
            scenes.append(scene)
        return {
            "match": self.spec.label,
            "match_id": self.spec.match_id,
            "role": self.spec.role,
            "index": ordinal,
            "origin_sample_id": origin_id,
            "period": row["period"],
            "source_frame": row["source_frame"],
            "window_id": window_id,
            "support": list(complete),
            "home_player_ids": self.home_ids,
            "away_player_ids": self.away_ids,
            "scenes": scenes,
            "eligibility": {
                "result_sha256": hashlib.sha256(canonical_bytes(asdict(diagnostic))).hexdigest(),
                "warnings": [w.code for w in diagnostic.warnings],
            },
        }


def quality_and_missingness(
    support: Sequence[Mapping[str, object]], player_ids: Sequence[int]
) -> tuple[str, Document]:
    """Frozen target-quality stratum plus explicit missingness categories (future steps only)."""
    counts = {
        "observed_detected": 0,
        "provider_extrapolated": 0,
        "flag_missing": 0,
        "missing_xy": 0,
    }
    for sample in support[26:]:
        players = {
            cast(int, p["player_id"]): p
            for p in cast(list[Mapping[str, object]], sample["players"])
        }
        for pid in player_ids:
            player = players.get(pid)
            if player is None or player.get("x_m") is None or player.get("y_m") is None:
                counts["missing_xy"] += 1
                continue
            flag = player.get("is_detected")
            if flag is True:
                counts["observed_detected"] += 1
            elif flag is False:
                counts["provider_extrapolated"] += 1
            elif flag is None:
                counts["flag_missing"] += 1
            else:
                raise ValueError("source quality flags must be Boolean or null")
    if counts["provider_extrapolated"]:
        return "with_provider_extrapolation", counts
    if not counts["observed_detected"] or counts["flag_missing"]:
        return "unclassified", counts
    return "detected_only", counts
