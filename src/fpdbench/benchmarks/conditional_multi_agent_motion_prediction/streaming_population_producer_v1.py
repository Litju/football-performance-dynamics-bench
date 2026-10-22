"""Bounded-memory synthetic population producer, separate from the historical v2 API."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
from collections import deque
from collections.abc import Iterator, Mapping, Sequence
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import BinaryIO, Literal, cast

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.evaluation_population import (
    prospective_window_id_v2,
    truth_mask_sha256,
    truth_sha256,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.prospective_protocol import (
    EXPECTED_ELIGIBILITY_POLICY_V2_HASH,
    EXPECTED_MEASUREMENT_STATE_V2_HASH,
    EXPECTED_SOURCE_POPULATION_HASH,
    EXPECTED_SOURCE_RELEASE_HASH,
    PROTOCOL_V2_SHA256,
)
from fpdbench.data_sources.skillcorner import canonical_bytes
from fpdbench.data_sources.skillcorner import (
    load_manifest as load_source_manifest,
)
from fpdbench.data_states.skillcorner import (
    iter_skillcorner_5hz_v2,
)
from fpdbench.data_states.skillcorner import (
    load_manifest_v2 as load_data_state_manifest_v2,
)
from fpdbench.eligibility.skillcorner import (
    BallPopulationQualificationStop,
    BallPopulationQualificationV2,
    EligibilityIssue,
    PhaseInterval,
    diagnose_skillcorner_window_v2,
    skillcorner_period_ranges,
    validate_ball_population_drift_v2,
)

from .empirical_experiment_plan import PLAN_V2_SHA256, protocol_split_v2

WORKER_VERSION = "res544-streaming-population-producer/1.0.0"
MAX_DOCUMENT_BYTES = 16 * 1024 * 1024
MAX_TRACKING_ROW_BYTES = 1024 * 1024
MAX_PHASE_INTERVALS = 100_000
_WINDOW_SLOTS = 41
_SUPPORT_FIRST = -25
_SUPPORT_LAST = 15
_FILES = {
    "manifest": "manifest.json",
    "candidates": "candidates.jsonl",
    "diagnostic_census": "diagnostic-census.jsonl",
    "truth": "truth.jsonl",
    "receipt": "receipt.json",
}

type Pair = tuple[float, float]


@dataclass(frozen=True, slots=True)
class StreamingPopulationMatchInputV1:
    """Paths to one synthetic match's metadata, tracking JSONL, and normalized phases."""

    match_id: str
    metadata_path: Path
    tracking_jsonl_path: Path
    phase_intervals_path: Path


@dataclass(frozen=True, slots=True)
class StreamingPopulationResultV1:
    output_directory: Path
    status: Literal["UNQUALIFIED"] = "UNQUALIFIED"

    def require_empirical_qualification(self) -> None:
        raise ValueError("independent protected verification required; worker is UNQUALIFIED")


class IncompleteStreamingPopulationV1(ValueError):
    """Complete inputs whose required matches do not all contain a scoreable window."""

    def __init__(self, receipt_path: Path) -> None:
        self.receipt_path = receipt_path
        super().__init__("incomplete population; every required match needs a scoreable window")


@dataclass(frozen=True, slots=True)
class _FileSnapshot:
    device: int
    inode: int
    mode: int
    size: int
    modified_ns: int
    changed_ns: int
    sha256: str


@dataclass(frozen=True, slots=True)
class _MatchSnapshot:
    metadata: _FileSnapshot
    tracking: _FileSnapshot
    phases: _FileSnapshot
    source_frame_count: int
    retained_sample_count: int
    retained_samples_sha256: str


class _ArrayDigest:
    def __init__(self) -> None:
        self._hash = hashlib.sha256()
        self._hash.update(b"[")
        self._first = True

    def append(self, value: object) -> None:
        if not self._first:
            self._hash.update(b",")
        self._hash.update(canonical_bytes(value))
        self._first = False

    def hexdigest(self) -> str:
        result = self._hash.copy()
        result.update(b"]")
        return result.hexdigest()


class _ArtifactWriter:
    def __init__(self, stream: BinaryIO) -> None:
        self.stream = stream
        self.hash = hashlib.sha256()

    def write(self, payload: bytes) -> None:
        view = memoryview(payload)
        while view:
            count = self.stream.write(view)
            if count <= 0:
                raise OSError("short write to private population artifact")
            view = view[count:]
        self.hash.update(payload)


def _worker_package_identity() -> dict[str, object]:
    root = Path(__file__).resolve().parents[2]
    sources = (
        "benchmarks/conditional_multi_agent_motion_prediction/streaming_population_producer_v1.py",
        "benchmarks/conditional_multi_agent_motion_prediction/empirical_experiment_plan.py",
        "benchmarks/conditional_multi_agent_motion_prediction/evaluation_population.py",
        "benchmarks/conditional_multi_agent_motion_prediction/prospective_protocol.py",
        "benchmarks/conditional_multi_agent_motion_prediction/prospective_skillcorner_protocol_v2.json",
        "data_sources/skillcorner.py",
        "data_sources/skillcorner_open_data_v1.json",
        "data_states/skillcorner.py",
        "data_states/skillcorner_5hz_v2.json",
        "eligibility/skillcorner.py",
        "eligibility/skillcorner_window_v2.json",
        "benchmarks/conditional_multi_agent_motion_prediction/empirical_experiment_plan_v2.json",
        "benchmarks/conditional_multi_agent_motion_prediction/evaluation_population_authority_v2.schema.json",
    )
    files = [
        {
            "path": path,
            "sha256": _hash_file(root / path),
        }
        for path in sorted(sources)
    ]
    identity: dict[str, object] = {
        "schema_id": "fpdbench.streaming-worker-package-identity",
        "schema_version": "1.0.0",
        "package": (
            "fpdbench.benchmarks.conditional_multi_agent_motion_prediction."
            "streaming_population_producer_v1"
        ),
        "worker_version": WORKER_VERSION,
        "hash_algorithm": "sha256",
        "source_inventory_scope": "listed Python and frozen authority files only",
        "executable_runtime_attestation": "NOT_PROVIDED",
        "files": files,
    }
    identity["sha256"] = _digest(identity)
    return identity


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _digest(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object with string keys")
    typed = cast(dict[object, object], value)
    if not all(isinstance(key, str) for key in typed):
        raise ValueError(f"{label} must be an object with string keys")
    return cast(dict[str, object], value)


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

    return json.loads(
        payload,
        object_pairs_hook=_unique_object,
        parse_constant=reject_constant,
    )


def _json_chunks(value: object) -> Iterator[bytes]:
    encoder = json.JSONEncoder(
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    for chunk in encoder.iterencode(value):
        yield chunk.encode("utf-8")


def _roles() -> tuple[tuple[str, str], ...]:
    roles = _mapping(protocol_split_v2()["roles"], "protocol roles")
    output: list[tuple[str, str]] = []
    for role in ("training", "validation", "evaluation"):
        values = roles.get(role)
        if not isinstance(values, list):
            raise ValueError("protocol role match IDs are invalid")
        entries = cast(list[object], values)
        if not all(isinstance(value, str) for value in entries):
            raise ValueError("protocol role match IDs are invalid")
        output.extend((role, cast(str, value)) for value in entries)
    return tuple(output)


def _input_map(
    inputs: Sequence[StreamingPopulationMatchInputV1],
    roles: Sequence[tuple[str, str]],
) -> dict[str, StreamingPopulationMatchInputV1]:
    expected = {match_id for _, match_id in roles}
    by_match: dict[str, StreamingPopulationMatchInputV1] = {}
    for item in inputs:
        if item.match_id in by_match:
            raise ValueError("duplicate population match input")
        by_match[item.match_id] = item
    if len(inputs) != 20 or set(by_match) != expected:
        raise ValueError("incomplete population: require exactly the pinned 20 matches")
    return by_match


def _open_regular(path: Path) -> tuple[int, _FileSnapshot]:
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode):
        os.close(fd)
        raise ValueError("population input must be a regular file")
    return fd, _file_snapshot(info, "")


def _file_snapshot(info: os.stat_result, sha256: str) -> _FileSnapshot:
    return _FileSnapshot(
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
        sha256,
    )


def _same_file(left: _FileSnapshot, right: _FileSnapshot) -> bool:
    return (
        left.device,
        left.inode,
        left.mode,
        left.size,
        left.modified_ns,
        left.changed_ns,
    ) == (
        right.device,
        right.inode,
        right.mode,
        right.size,
        right.modified_ns,
        right.changed_ns,
    )


def _same_snapshot(left: _FileSnapshot, right: _FileSnapshot) -> bool:
    return _same_file(left, right) and left.sha256 == right.sha256


def _read_document(path: Path) -> tuple[bytes, _FileSnapshot]:
    fd, initial = _open_regular(path)
    digest = hashlib.sha256()
    try:
        with os.fdopen(fd, "rb") as stream:
            payload = stream.read(MAX_DOCUMENT_BYTES + 1)
            if len(payload) > MAX_DOCUMENT_BYTES:
                raise ValueError("metadata or normalized phase document exceeds memory bound")
            digest.update(payload)
            final = _file_snapshot(os.fstat(stream.fileno()), digest.hexdigest())
        if not _same_file(initial, final) or len(payload) != final.size:
            raise ValueError("population input changed while being read")
        final_path = _file_snapshot(path.stat(follow_symlinks=False), "")
        if not _same_file(final, final_path):
            raise ValueError("population input path changed while being read")
        return payload, final
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        raise


def _metadata_and_phases(
    item: StreamingPopulationMatchInputV1,
    release_id: str,
) -> tuple[
    Mapping[str, object],
    tuple[PhaseInterval, ...],
    dict[int, tuple[int, int]],
    _FileSnapshot,
    _FileSnapshot,
]:
    metadata_bytes, metadata_snapshot = _read_document(item.metadata_path)
    phase_bytes, phase_snapshot = _read_document(item.phase_intervals_path)
    metadata = _mapping(_json(metadata_bytes), "match metadata")
    if type(metadata.get("id")) is not int or str(metadata["id"]) != item.match_id:
        raise ValueError("input match identity drift")
    periods, issues = skillcorner_period_ranges(metadata)
    if issues or not periods or any(period not in {1, 2} for period in periods):
        raise ValueError("invalid or unavailable period bounds")

    raw_phases = _json(phase_bytes)
    if not isinstance(raw_phases, list):
        raise ValueError("normalized phase intervals exceed the supported bound")
    phase_values = cast(list[object], raw_phases)
    if len(phase_values) > MAX_PHASE_INTERVALS:
        raise ValueError("normalized phase intervals exceed the supported bound")
    parsed: list[PhaseInterval] = []
    for value in phase_values:
        phase = _mapping(value, "phase")
        if set(phase) != {"period", "frame_start", "frame_end"} or any(
            type(phase[key]) is not int for key in phase
        ):
            raise ValueError("invalid normalized phase interval")
        parsed.append(
            PhaseInterval(
                release_id,
                int(item.match_id),
                cast(int, phase["period"]),
                cast(int, phase["frame_start"]),
                cast(int, phase["frame_end"]),
            )
        )
    return metadata, tuple(parsed), periods, metadata_snapshot, phase_snapshot


@dataclass(slots=True)
class _TrackingStats:
    byte_count: int = 0
    source_frame_count: int = 0
    retained_sample_count: int = 0
    raw_sha256: str = ""
    retained_samples_sha256: str = ""
    snapshot: _FileSnapshot | None = None


def _tracking_samples(
    path: Path,
    metadata: Mapping[str, object],
    release_id: str,
    stats: _TrackingStats,
) -> Iterator[dict[str, object]]:
    fd, initial = _open_regular(path)
    raw_hash = hashlib.sha256()
    samples_hash = _ArrayDigest()
    try:
        with os.fdopen(fd, "rb") as stream:

            def raw_frames() -> Iterator[Mapping[str, object]]:
                while line := stream.readline(MAX_TRACKING_ROW_BYTES + 1):
                    if len(line) > MAX_TRACKING_ROW_BYTES or not line.strip():
                        raise ValueError("oversized or empty tracking JSONL row")
                    raw_hash.update(line)
                    stats.byte_count += len(line)
                    stats.source_frame_count += 1
                    yield _mapping(_json(line), "tracking frame")

            for sample in iter_skillcorner_5hz_v2(
                raw_frames(),
                metadata,
                source_release_id=release_id,
            ):
                samples_hash.append(sample)
                stats.retained_sample_count += 1
                yield sample
            final = _file_snapshot(os.fstat(stream.fileno()), raw_hash.hexdigest())
        if (
            not _same_file(initial, final)
            or stats.byte_count != final.size
            or not _same_file(final, _file_snapshot(path.stat(follow_symlinks=False), ""))
        ):
            raise ValueError("tracking input changed while being read")
        stats.raw_sha256 = raw_hash.hexdigest()
        stats.retained_samples_sha256 = samples_hash.hexdigest()
        stats.snapshot = final
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        raise


def _snapshots_and_drift(
    inputs: Mapping[str, StreamingPopulationMatchInputV1],
    roles: Sequence[tuple[str, str]],
    release_id: str,
) -> tuple[dict[str, _MatchSnapshot], BallPopulationQualificationV2]:
    snapshots: dict[str, _MatchSnapshot] = {}
    seen_matches: set[str] = set()
    checked_samples = 0

    def samples() -> Iterator[Mapping[str, object]]:
        nonlocal checked_samples
        for _, match_id in roles:
            item = inputs[match_id]
            metadata, _, _, metadata_snapshot, phase_snapshot = _metadata_and_phases(
                item,
                release_id,
            )
            stats = _TrackingStats()
            for sample in _tracking_samples(item.tracking_jsonl_path, metadata, release_id, stats):
                seen_matches.add(match_id)
                checked_samples += 1
                yield sample
            if stats.source_frame_count == 0:
                raise ValueError("incomplete population: empty tracking payload")
            if stats.snapshot is None:
                raise ValueError("tracking input scan did not complete")
            snapshots[match_id] = _MatchSnapshot(
                metadata_snapshot,
                stats.snapshot,
                phase_snapshot,
                stats.source_frame_count,
                stats.retained_sample_count,
                stats.retained_samples_sha256,
            )

    try:
        scan = validate_ball_population_drift_v2(samples())
    except BallPopulationQualificationStop as exc:
        data_state = load_data_state_manifest_v2()
        scan = BallPopulationQualificationV2(
            EXPECTED_SOURCE_RELEASE_HASH,
            cast(str, data_state["data_state_hash"]),
            checked_samples,
            len(seen_matches),
            exc.count,
        )
    return snapshots, scan


def _verify_file_unchanged(path: Path, expected: _FileSnapshot, *, limit: int | None) -> None:
    fd, initial = _open_regular(path)
    digest = hashlib.sha256()
    size = 0
    try:
        with os.fdopen(fd, "rb") as stream:
            chunk_size = 1024 * 1024 if limit is None else min(1024 * 1024, limit + 1 - size)
            while chunk := stream.read(chunk_size):
                size += len(chunk)
                if limit is not None and size > limit:
                    raise ValueError("metadata or phase input exceeds memory bound")
                digest.update(chunk)
            final = _file_snapshot(os.fstat(stream.fileno()), digest.hexdigest())
        if (
            not _same_file(expected, initial)
            or not _same_file(expected, final)
            or size != expected.size
            or digest.hexdigest() != expected.sha256
            or not _same_file(expected, _file_snapshot(path.stat(follow_symlinks=False), ""))
        ):
            raise ValueError("population input mutated after the mandatory drift scan")
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        raise


def _verify_snapshots_unchanged(
    inputs: Mapping[str, StreamingPopulationMatchInputV1],
    snapshots: Mapping[str, _MatchSnapshot],
    roles: Sequence[tuple[str, str]],
) -> None:
    for _, match_id in roles:
        item = inputs[match_id]
        snapshot = snapshots[match_id]
        _verify_file_unchanged(item.metadata_path, snapshot.metadata, limit=MAX_DOCUMENT_BYTES)
        _verify_file_unchanged(
            item.tracking_jsonl_path,
            snapshot.tracking,
            limit=None,
        )
        _verify_file_unchanged(item.phase_intervals_path, snapshot.phases, limit=MAX_DOCUMENT_BYTES)


def _private_output_directory(path: Path) -> None:
    if (
        sys.platform != "linux"
        or not path.is_absolute()
        or ".." in path.parts
        or path == Path("/mnt")
        or Path("/mnt") in path.parents
    ):
        raise ValueError("absolute Linux private output path required")
    resolved_parent = path.parent.resolve()
    if any((parent / ".git").exists() for parent in (resolved_parent, *resolved_parent.parents)):
        raise ValueError("population output must be outside a Git worktree")
    path.mkdir(mode=0o700)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
        raise ValueError("population output directory must be a user-owned directory")
    path.chmod(0o700)
    if stat.S_IMODE(path.stat().st_mode) != 0o700:
        raise ValueError("population output directory must be mode 0700")
    _sync_directory(resolved_parent)


def _create_writer(stack: ExitStack, path: Path) -> _ArtifactWriter:
    fd = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o600,
    )
    stream = os.fdopen(fd, "wb", buffering=0)
    stack.callback(stream.close)
    return _ArtifactWriter(stream)


def _sync_file(writer: _ArtifactWriter) -> None:
    writer.stream.flush()
    os.fsync(writer.stream.fileno())


def _sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _verify_output_digest(path: Path, expected: str) -> str:
    actual = _hash_file(path)
    if actual != expected:
        raise ValueError(f"population artifact changed while being written: {path.name}")
    return actual


def _manifest_artifact_hash(
    values: Mapping[str, object],
    matches_path: Path,
    manifest_sha256: str,
) -> str:
    digest = hashlib.sha256()
    digest.update(b"{")
    for index, key in enumerate(sorted(values)):
        if index:
            digest.update(b",")
        digest.update(canonical_bytes(key) + b":")
        if key == "matches":
            with matches_path.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
        elif key == "manifest_sha256":
            digest.update(canonical_bytes(manifest_sha256))
        else:
            digest.update(canonical_bytes(values[key]))
    digest.update(b"}")
    return digest.hexdigest()


def _write_receipt(path: Path, receipt: dict[str, object]) -> None:
    digest = hashlib.sha256()
    for chunk in _json_chunks(receipt):
        digest.update(chunk)
    receipt["receipt_sha256"] = digest.hexdigest()
    fd = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o600,
    )
    with os.fdopen(fd, "wb", buffering=0) as stream:
        writer = _ArtifactWriter(stream)
        for chunk in _json_chunks(receipt):
            writer.write(chunk)
        stream.flush()
        os.fsync(stream.fileno())
    _sync_directory(path.parent)


def _base_receipt(
    *,
    status: Literal["UNQUALIFIED", "INCOMPLETE"],
    worker_identity: Mapping[str, object],
    input_receipts: list[dict[str, object]],
    scan: BallPopulationQualificationV2,
) -> dict[str, object]:
    return {
        "schema_id": "fpdbench.streaming-population-producer-receipt",
        "schema_version": "1.0.0",
        "status": status,
        "worker_version": WORKER_VERSION,
        "worker_package_identity": worker_identity,
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
        "drift_scan": asdict(scan),
    }


def _input_receipts(
    roles: Sequence[tuple[str, str]],
    snapshots: Mapping[str, _MatchSnapshot],
) -> list[dict[str, object]]:
    receipts: list[dict[str, object]] = []
    for _, match_id in roles:
        snapshot = snapshots[match_id]
        receipts.append(
            {
                "match_id": match_id,
                "inputs": {
                    "metadata_json": {
                        "sha256": snapshot.metadata.sha256,
                        "byte_size": snapshot.metadata.size,
                    },
                    "tracking_jsonl": {
                        "sha256": snapshot.tracking.sha256,
                        "byte_size": snapshot.tracking.size,
                    },
                    "normalized_phase_intervals_json": {
                        "sha256": snapshot.phases.sha256,
                        "byte_size": snapshot.phases.size,
                    },
                },
                "source_frame_count": snapshot.source_frame_count,
                "retained_sample_count": snapshot.retained_sample_count,
                "retained_samples_sha256": snapshot.retained_samples_sha256,
            }
        )
    return receipts


def _player_map(sample: Mapping[str, object]) -> dict[int, Mapping[str, object]]:
    values = sample.get("players")
    if not isinstance(values, list):
        raise ValueError("canonical sample players must be an array")
    player_values = cast(list[object], values)
    result: dict[int, Mapping[str, object]] = {}
    for value in player_values:
        player = _mapping(value, "canonical player")
        player_id = player.get("player_id")
        if isinstance(player_id, bool) or not isinstance(player_id, int):
            raise ValueError("canonical player ID must be an integer")
        result[player_id] = player
    return result


def _pair(player: Mapping[str, object] | None) -> Pair | None:
    if player is None or player.get("x_m") is None or player.get("y_m") is None:
        return None
    return cast(float, player["x_m"]), cast(float, player["y_m"])


def _scene(
    support: Sequence[Mapping[str, object] | None],
    side: str,
) -> tuple[dict[str, object], dict[str, object], bool]:
    origin = support[25]
    assert origin is not None
    targets = [
        (player_id, cast(Pair, _pair(player)))
        for player_id, player in sorted(_player_map(origin).items())
        if player["group"] == side and _pair(player) is not None
    ]
    absolute: list[tuple[Pair | None, ...]] = []
    displacement: list[tuple[Pair | None, ...]] = []
    for sample in support[26:]:
        assert sample is not None
        players = _player_map(sample)
        row = tuple(_pair(players.get(player_id)) for player_id, _ in targets)
        absolute.append(row)
        displacement.append(
            tuple(
                None if xy is None else (xy[0] - anchor[0], xy[1] - anchor[1])
                for xy, (_, anchor) in zip(row, targets, strict=True)
            )
        )
    xy_panel = tuple(absolute)
    delta_panel = tuple(displacement)
    mask_digest = truth_mask_sha256(xy_panel)
    assert truth_mask_sha256(delta_panel) == mask_digest
    membership: dict[str, object] = {
        "scene_id": side,
        "player_ids": [str(player_id) for player_id, _ in targets],
        "absolute_xy_truth_sha256": truth_sha256(
            xy_panel,
            target_representation="absolute_xy",
        ),
        "displacement_truth_sha256": truth_sha256(
            delta_panel,
            target_representation="origin_relative_displacement",
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


def _origins(periods: Mapping[int, tuple[int, int]]) -> Iterator[tuple[int, int, str]]:
    for period, (start, end) in sorted(periods.items()):
        for frame in range(start + start % 2, end, 2):
            yield period, frame, f"period_{period}/sample_{frame // 2}"


def _support(
    recent: Sequence[Mapping[str, object]],
    origin_frame: int,
) -> tuple[Mapping[str, object] | None, ...]:
    indexed = {cast(int, sample["source_frame"]): sample for sample in recent}
    return tuple(
        indexed.get(origin_frame + offset * 2)
        for offset in range(_SUPPORT_FIRST, _SUPPORT_LAST + 1)
    )


def _population_events(
    samples: Iterator[dict[str, object]],
    periods: Mapping[int, tuple[int, int]],
) -> Iterator[
    tuple[
        tuple[int, int, str],
        tuple[Mapping[str, object] | None, ...],
    ]
]:
    recent: deque[Mapping[str, object]] = deque(maxlen=_WINDOW_SLOTS)
    origins = _origins(periods)
    origin = next(origins, None)
    for sample in samples:
        recent.append(sample)
        current_frame = cast(int, sample["source_frame"])
        while origin is not None and origin[1] + 30 <= current_frame:
            yield origin, _support(recent, origin[1])
            origin = next(origins, None)
    while origin is not None:
        yield origin, _support(recent, origin[1])
        origin = next(origins, None)


def _count_issues(
    issues: Sequence[EligibilityIssue],
    totals: dict[str, int],
) -> None:
    for code in {issue.code for issue in issues}:
        totals[code] = totals.get(code, 0) + 1


def _emit_manifest(
    directory: Path,
    values: dict[str, object],
    matches_path: Path,
) -> tuple[str, str]:
    """Stream the large matches array and patch its fixed-width self-digest."""
    manifest_path = directory / _FILES["manifest"]
    fd = os.open(
        manifest_path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o600,
    )
    digest = hashlib.sha256()
    matches_digest = hashlib.sha256()
    with os.fdopen(fd, "w+b", buffering=0) as stream:
        writer = _ArtifactWriter(stream)
        writer.write(b"{")
        digest.update(b"{")
        first_output = True
        first_base = True
        placeholder_offset = -1
        for key in sorted(values):
            if not first_output:
                writer.write(b",")
            first_output = False
            member_prefix = canonical_bytes(key) + b":"
            writer.write(member_prefix)
            if key == "manifest_sha256":
                placeholder_offset = stream.tell() + 1
                writer.write(b'"' + b"0" * 64 + b'"')
                continue
            if not first_base:
                digest.update(b",")
            first_base = False
            digest.update(member_prefix)
            if key == "matches":
                with matches_path.open("rb") as matches_stream:
                    while chunk := matches_stream.read(1024 * 1024):
                        writer.write(chunk)
                        digest.update(chunk)
                        matches_digest.update(chunk)
            else:
                encoded = canonical_bytes(values[key])
                writer.write(encoded)
                digest.update(encoded)
        writer.write(b"}")
        digest.update(b"}")
        if placeholder_offset < 0:
            raise ValueError("manifest self-digest placeholder missing")
        manifest_sha256 = digest.hexdigest()
        stream.seek(placeholder_offset)
        writer.write(manifest_sha256.encode("ascii"))
        stream.flush()
        os.fsync(stream.fileno())
    _sync_directory(directory)
    if matches_digest.hexdigest() != cast(str, values["membership_sha256"]):
        raise ValueError("population membership spool changed during manifest assembly")
    expected_artifact_hash = _manifest_artifact_hash(values, matches_path, manifest_sha256)
    return manifest_sha256, _verify_output_digest(manifest_path, expected_artifact_hash)


def _write_incomplete_marker(directory: Path) -> None:
    marker = directory / ".incomplete"
    fd = os.open(
        marker,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o600,
    )
    with os.fdopen(fd, "wb", buffering=0) as stream:
        stream.write(
            canonical_bytes(
                {
                    "schema_id": "fpdbench.streaming-population-output-state",
                    "schema_version": "1.0.0",
                    "status": "INCOMPLETE",
                    "worker_version": WORKER_VERSION,
                }
            )
        )
        stream.flush()
        os.fsync(stream.fileno())


def _scan_receipt(
    directory: Path,
    worker_identity: Mapping[str, object],
    input_receipts: list[dict[str, object]],
    scan: BallPopulationQualificationV2,
) -> None:
    receipt = _base_receipt(
        status="INCOMPLETE",
        worker_identity=worker_identity,
        input_receipts=input_receipts,
        scan=scan,
    )
    _write_receipt(directory / _FILES["receipt"], receipt)


def produce_streaming_population_draft_v1(
    inputs: Sequence[StreamingPopulationMatchInputV1],
    output_directory: Path,
) -> StreamingPopulationResultV1:
    """Stream a synthetic population draft without qualifying or authenticating inputs.

    Tracking JSONL is parsed in bounded rows on a mandatory full-population drift
    pass, then parsed again with a 41-sample rolling window for output construction.
    A final byte pass rejects sources that changed during construction.
    """
    roles = _roles()
    by_match = _input_map(inputs, roles)
    worker_identity = _worker_package_identity()
    _private_output_directory(output_directory)
    _write_incomplete_marker(output_directory)
    _sync_directory(output_directory)
    release_id = cast(str, load_source_manifest()["source_release_id"])

    snapshots, scan = _snapshots_and_drift(by_match, roles, release_id)
    input_receipts = _input_receipts(roles, snapshots)
    if scan.null_flag_finite_xy_count:
        _scan_receipt(output_directory, worker_identity, input_receipts, scan)
        raise IncompleteStreamingPopulationV1(output_directory / _FILES["receipt"])

    candidate_origins = _ArrayDigest()
    diagnostic_origins = _ArrayDigest()
    global_candidate_count = 0
    eligible_window_count = 0
    match_counts: list[dict[str, object]] = []
    total_diagnostic_count = 0

    with ExitStack() as stack:
        candidate_writer = _create_writer(
            stack,
            output_directory / _FILES["candidates"],
        )
        diagnostic_writer = _create_writer(
            stack,
            output_directory / _FILES["diagnostic_census"],
        )
        truth_writer = _create_writer(stack, output_directory / _FILES["truth"])
        matches_path = output_directory / ".matches.partial"
        matches_writer = _create_writer(stack, matches_path)
        matches_writer.write(b"[")

        for _, match_id in roles:
            item = by_match[match_id]
            snapshot = snapshots[match_id]
            metadata, phases, periods, metadata_now, phases_now = _metadata_and_phases(
                item,
                release_id,
            )
            if not _same_snapshot(snapshot.metadata, metadata_now) or not _same_snapshot(
                snapshot.phases, phases_now
            ):
                raise ValueError("metadata or phase input mutated after the mandatory drift scan")

            stats = _TrackingStats()
            match_candidate_hash = _ArrayDigest()
            match_diagnostic_hash = _ArrayDigest()
            candidate_count = diagnostic_count = 0
            scoreable_windows = scoreable_scenes = eligible_count = 0
            candidate_exclusions: dict[str, int] = {}
            candidate_warnings: dict[str, int] = {}
            diagnostic_exclusions: dict[str, int] = {}
            diagnostic_warnings: dict[str, int] = {}
            if match_counts:
                matches_writer.write(b",")
            matches_writer.write(b'{"match_id":')
            matches_writer.write(canonical_bytes(match_id))
            matches_writer.write(b',"role":')
            matches_writer.write(canonical_bytes(_role_for(roles, match_id)))
            matches_writer.write(b',"windows":[')
            first_window = True

            for (_, _, origin_id), support in _population_events(
                _tracking_samples(
                    item.tracking_jsonl_path,
                    metadata,
                    release_id,
                    stats,
                ),
                periods,
            ):
                identity = {"match_id": match_id, "origin_sample_id": origin_id}
                diagnostic_origins.append(identity)
                match_diagnostic_hash.append(identity)
                diagnostic_count += 1
                total_diagnostic_count += 1
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
                diagnostic_writer.write(canonical_bytes(row) + b"\n")
                _count_issues(diagnostic.exclusion_reasons, diagnostic_exclusions)
                _count_issues(diagnostic.warnings, diagnostic_warnings)
                complete_support = all(value is not None for value in support)
                if complete_support:
                    candidate_origins.append(identity)
                    match_candidate_hash.append(identity)
                    candidate_count += 1
                    global_candidate_count += 1
                    candidate_writer.write(canonical_bytes(row) + b"\n")
                    _count_issues(diagnostic.exclusion_reasons, candidate_exclusions)
                    _count_issues(diagnostic.warnings, candidate_warnings)
                if complete_support and diagnostic.candidate_rules_pass:
                    window_id = prospective_window_id_v2(match_id, origin_id)
                    scenes: list[dict[str, object]] = []
                    window_scoreable = False
                    for side in ("home", "away"):
                        membership, truth, scoreable = _scene(support, side)
                        scenes.append(membership)
                        truth_writer.write(
                            canonical_bytes(
                                {
                                    **identity,
                                    "window_id": window_id,
                                    **truth,
                                }
                            )
                            + b"\n"
                        )
                        scoreable_scenes += int(scoreable)
                        window_scoreable |= scoreable
                    window = {
                        "window_id": window_id,
                        "origin_sample_id": origin_id,
                        "eligibility_result_sha256": decision_hash,
                        "scenes": scenes,
                    }
                    if not first_window:
                        matches_writer.write(b",")
                    first_window = False
                    matches_writer.write(canonical_bytes(window))
                    eligible_count += 1
                    eligible_window_count += 1
                    scoreable_windows += int(window_scoreable)

            if (
                stats.source_frame_count != snapshot.source_frame_count
                or stats.retained_sample_count != snapshot.retained_sample_count
                or stats.snapshot is None
                or not _same_snapshot(stats.snapshot, snapshot.tracking)
                or stats.retained_samples_sha256 != snapshot.retained_samples_sha256
            ):
                raise ValueError("tracking input changed after the mandatory drift scan")
            matches_writer.write(b"]}")
            match_counts.append(
                {
                    "role": _role_for(roles, match_id),
                    "match_id": match_id,
                    "candidate_origin_population_sha256": match_candidate_hash.hexdigest(),
                    "candidate_window_count": candidate_count,
                    "eligible_window_count": eligible_count,
                    "excluded_window_count": candidate_count - eligible_count,
                    "diagnostic_origin_count": diagnostic_count,
                    "diagnostic_origin_census_sha256": match_diagnostic_hash.hexdigest(),
                    "diagnostic_excluded_window_count": diagnostic_count - eligible_count,
                    "directed_scene_count": eligible_count * 2,
                    "scoreable_scene_count": scoreable_scenes,
                    "scoreable_window_count": scoreable_windows,
                    "exclusion_window_counts": candidate_exclusions,
                    "warning_window_counts": candidate_warnings,
                    "diagnostic_exclusion_window_counts": diagnostic_exclusions,
                    "diagnostic_warning_window_counts": diagnostic_warnings,
                }
            )
        matches_writer.write(b"]")

        _sync_file(candidate_writer)
        _sync_file(diagnostic_writer)
        _sync_file(truth_writer)
        _sync_file(matches_writer)

        _verify_snapshots_unchanged(by_match, snapshots, roles)
        candidates_hash = _verify_output_digest(
            output_directory / _FILES["candidates"],
            candidate_writer.hash.hexdigest(),
        )
        diagnostic_hash = _verify_output_digest(
            output_directory / _FILES["diagnostic_census"],
            diagnostic_writer.hash.hexdigest(),
        )
        if any(cast(int, count["scoreable_window_count"]) == 0 for count in match_counts):
            (output_directory / _FILES["truth"]).unlink()
            matches_path.unlink()
            receipt = _base_receipt(
                status="INCOMPLETE",
                worker_identity=worker_identity,
                input_receipts=input_receipts,
                scan=scan,
            )
            receipt.update(
                match_counts=match_counts,
                candidate_origin_population_sha256=candidate_origins.hexdigest(),
                diagnostic_origin_census_count=total_diagnostic_count,
                diagnostic_origin_census_sha256=diagnostic_origins.hexdigest(),
                candidates_jsonl_sha256=candidates_hash,
                diagnostic_census_jsonl_sha256=diagnostic_hash,
            )
            _write_receipt(output_directory / _FILES["receipt"], receipt)
            raise IncompleteStreamingPopulationV1(output_directory / _FILES["receipt"])

        manifest_values: dict[str, object] = {
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
            "candidate_window_count": global_candidate_count,
            "eligible_window_count": eligible_window_count,
            "candidate_origin_population_sha256": candidate_origins.hexdigest(),
            "manifest_sha256": "",
            "matches": None,
            "membership_sha256": _hash_file(matches_path),
        }
        manifest_sha, manifest_artifact_hash = _emit_manifest(
            output_directory,
            manifest_values,
            matches_path,
        )
        matches_path.unlink()
        truth_hash = _verify_output_digest(
            output_directory / _FILES["truth"],
            truth_writer.hash.hexdigest(),
        )

        receipt = _base_receipt(
            status="UNQUALIFIED",
            worker_identity=worker_identity,
            input_receipts=input_receipts,
            scan=scan,
        )
        receipt.update(
            match_counts=match_counts,
            candidate_origin_population_sha256=candidate_origins.hexdigest(),
            diagnostic_origin_census_count=total_diagnostic_count,
            diagnostic_origin_census_sha256=diagnostic_origins.hexdigest(),
            candidates_jsonl_sha256=candidates_hash,
            diagnostic_census_jsonl_sha256=diagnostic_hash,
            population_manifest_sha256=manifest_sha,
            manifest_json_sha256=manifest_artifact_hash,
            truth_jsonl_sha256=truth_hash,
        )
        _write_receipt(output_directory / _FILES["receipt"], receipt)
        (output_directory / ".incomplete").unlink()
        _sync_directory(output_directory)
    return StreamingPopulationResultV1(output_directory)


def _role_for(roles: Sequence[tuple[str, str]], match_id: str) -> str:
    for role, candidate in roles:
        if candidate == match_id:
            return role
    raise ValueError("match is outside the pinned protocol")
