"""Independent bounded-memory reconciliation for the frozen SkillCorner v2 population.

This worker deliberately imports no FPD producer, canonicalizer, eligibility,
population, or historical-verifier module. It reads frozen JSON authorities as
data and derives its own raw-frame, window, diagnostic, membership, and truth
streams. Every result is a non-authoritative reconciliation; the executable
runtime gate remains BLOCKED.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import tempfile
from collections import Counter, deque
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, TextIO, cast

VERIFIER_VERSION = "res544-streaming-population-verifier/1.0.0"
PRODUCER_VERSION = "res544-streaming-population-producer/1.0.0"
PRODUCER_COMMIT = "aad8888eb6c7c046e4dfbce866886bf2ec8dd123"
PRODUCER_IDENTITY_SHA256 = "c3a81aa35599608711be85e3eacd9946bdd762937ef1bd08431a88ba415d20fc"
SOURCE_RELEASE_HASH = "e92c417b7640b27399451134ee3fce4b1961b0c0dfc2e01175a8f3c906a9ae07"
SOURCE_POPULATION_HASH = "e9054b7ddc2dfeff4dd8425ea61a23ed0b326076a08899e47502484228fdbdf4"
MEASUREMENT_HASH = "1ecf355b3e6e2f04967e8363c1fdecc7f40707a7dda9966ebee1b3d90e97e671"
ELIGIBILITY_HASH = "ed1cdc20ca7a93040fd4aabc91655819c5c4b8c58021c6540c6aaea325dafa11"
PROTOCOL_HASH = "3d7bdc46300b966a4da274579d21ac4c8219e1ef897719d6b7a308596e9f1d9f"
PLAN_HASH = "a59fee6ee8e9fb03f4f0ccdae1933458af2bbf2375db7e6cd2bdf10962e42b62"
POPULATION_SCHEMA_HASH = "27da86b7355c311a65c68ab9b2bd3ae86e27779ed48641c23181ffe2f9adc224"
SOURCE_MANIFEST_HASH = "938cded522ee08f5de539976752fde51b2e858709574f3f63380bd72dd1af7fc"
DATA_STATE_FILE_HASH = "b23fee5040b1b55756ddb2891270c3041355d0e73d2ec90347c759d184b121b4"
ELIGIBILITY_FILE_HASH = "7f767c34bdf15acf56e196a8875ad2379091a1e7c11307582bf6fb2ebe68c8cd"
PROTOCOL_FILE_HASH = "6e0ddd6dd0718d6f039cde5ef2f94c99089cfe30ba322d0daa4a27b2af2a3100"
PLAN_FILE_HASH = "f094f0397c09c58035aeaf3d6ee5445bafe36c51ee2a07a711fba94a92973e15"
HISTORY = 25
FUTURE = 15
SLOTS = 41
MAX_DOCUMENT_BYTES = 16 * 1024 * 1024
MAX_TRACKING_ROW_BYTES = 1024 * 1024
MAX_REPORT_ENTRIES = 1000
MAX_REPORT_DETAIL_BYTES = 256 * 1024
MAX_REPORT_IDENTITY_FIELDS = 16
MAX_REPORT_IDENTITY_FIELD_BYTES = 128
MAX_MANIFEST_TOKEN_BYTES = 16 * 1024 * 1024
FILES = {
    "manifest.json",
    "candidates.jsonl",
    "diagnostic-census.jsonl",
    "truth.jsonl",
    "receipt.json",
}
_TIMESTAMP = re.compile(r"^(\d+):([0-5]\d):([0-5]\d)\.(\d{2})$")
_PERIOD_NAME = re.compile(r"^period_([1-5])$")

PRODUCER_SOURCE_HASHES: tuple[tuple[str, str], ...] = (
    (
        "benchmarks/conditional_multi_agent_motion_prediction/empirical_experiment_plan.py",
        "d048b5fc9c8d89f3b3dcb6ad50cc9ac1e765a036618d0e54551ed2ab58c367d4",
    ),
    (
        "benchmarks/conditional_multi_agent_motion_prediction/empirical_experiment_plan_v2.json",
        "f094f0397c09c58035aeaf3d6ee5445bafe36c51ee2a07a711fba94a92973e15",
    ),
    (
        "benchmarks/conditional_multi_agent_motion_prediction/evaluation_population.py",
        "e05a654d0d2cf37d5f148bd23f2db2ec0ef328febbd02c8f9986e7b36d78390b",
    ),
    (
        "benchmarks/conditional_multi_agent_motion_prediction/evaluation_population_authority_v2.schema.json",
        "27da86b7355c311a65c68ab9b2bd3ae86e27779ed48641c23181ffe2f9adc224",
    ),
    (
        "benchmarks/conditional_multi_agent_motion_prediction/prospective_protocol.py",
        "7c8aac440aa5920cf59a486643a81072b976eb7797fa525d669e59c015f41ae2",
    ),
    (
        "benchmarks/conditional_multi_agent_motion_prediction/prospective_skillcorner_protocol_v2.json",
        "6e0ddd6dd0718d6f039cde5ef2f94c99089cfe30ba322d0daa4a27b2af2a3100",
    ),
    (
        "benchmarks/conditional_multi_agent_motion_prediction/streaming_population_producer_v1.py",
        "45e053d5937ff49ac275c76672cc9f5fb5c6db30faaf4844d419d7779fb85e06",
    ),
    (
        "data_sources/skillcorner.py",
        "598e681c894cd9f890fb1e77f6a083a4c566c14c4c1119950ba0dff99eeb8e1b",
    ),
    (
        "data_sources/skillcorner_open_data_v1.json",
        SOURCE_MANIFEST_HASH,
    ),
    (
        "data_states/skillcorner.py",
        "e214a810fc1a364e48e0015048b0da076678cddd369fd410000f3dfe72a6fa66",
    ),
    ("data_states/skillcorner_5hz_v2.json", DATA_STATE_FILE_HASH),
    (
        "eligibility/skillcorner.py",
        "ccedb9ac76f5ca64bb857d53474a555c9e8f47b680fba3de383204da57db37c5",
    ),
    ("eligibility/skillcorner_window_v2.json", ELIGIBILITY_FILE_HASH),
)

PROTOCOL_FILE = (
    "benchmarks/conditional_multi_agent_motion_prediction/prospective_skillcorner_protocol_v2.json"
)
PLAN_FILE = "benchmarks/conditional_multi_agent_motion_prediction/empirical_experiment_plan_v2.json"
POPULATION_SCHEMA_FILE = (
    "benchmarks/conditional_multi_agent_motion_prediction/"
    "evaluation_population_authority_v2.schema.json"
)
AUTHORITY_FILE_HASHES = {
    "data_sources/skillcorner_open_data_v1.json": SOURCE_MANIFEST_HASH,
    "data_states/skillcorner_5hz_v2.json": DATA_STATE_FILE_HASH,
    "eligibility/skillcorner_window_v2.json": ELIGIBILITY_FILE_HASH,
    PROTOCOL_FILE: PROTOCOL_FILE_HASH,
    PLAN_FILE: PLAN_FILE_HASH,
    POPULATION_SCHEMA_FILE: POPULATION_SCHEMA_HASH,
}


class VerificationInputError(ValueError):
    """An input or authority could not be safely interpreted under the frozen contract."""


class InputSnapshotChanged(VerificationInputError):
    """A pinned source file changed identity or bytes during verification."""


class CanonicalArrayDigest:
    """Incremental SHA-256 for the canonical JSON array used by the v2 wire format."""

    def __init__(self) -> None:
        self._hash = hashlib.sha256(b"[")
        self._first = True

    def append(self, value: object) -> None:
        if not self._first:
            self._hash.update(b",")
        self._hash.update(canonical_bytes(value))
        self._first = False

    def hexdigest(self) -> str:
        digest = self._hash.copy()
        digest.update(b"]")
        return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class InputPaths:
    match_id: str
    metadata: Path
    tracking: Path
    phases: Path


@dataclass(frozen=True, slots=True)
class InputFileSnapshot:
    sha256: str
    byte_size: int
    device: int
    inode: int
    mode: int
    mtime_ns: int
    ctime_ns: int

    def matches_stat(self, info: os.stat_result) -> bool:
        return (
            self.device,
            self.inode,
            self.mode,
            self.byte_size,
            self.mtime_ns,
            self.ctime_ns,
        ) == (
            info.st_dev,
            info.st_ino,
            info.st_mode,
            info.st_size,
            info.st_mtime_ns,
            info.st_ctime_ns,
        )


@dataclass(slots=True)
class MatchInputSnapshots:
    metadata: InputFileSnapshot
    phases: InputFileSnapshot
    tracking: InputFileSnapshot | None = None


@dataclass(frozen=True, slots=True)
class MatchContract:
    match_id: str
    role: str
    metadata: dict[str, object]
    phases: tuple[dict[str, int], ...]
    period_bounds: dict[int, tuple[int, int]]
    team_by_player: dict[int, int]
    appearances: dict[int, dict[int, tuple[tuple[int, int], ...]]]
    roster_complete: bool
    home_team_id: int
    away_team_id: int
    pitch_length: float
    pitch_width: float


@dataclass(frozen=True, slots=True)
class SourceReceipt:
    match_id: str
    metadata_sha256: str
    metadata_bytes: int
    tracking_sha256: str
    tracking_bytes: int
    phase_sha256: str
    phase_bytes: int
    source_frame_count: int
    retained_sample_count: int
    retained_samples_sha256: str

    def to_wire(self) -> dict[str, object]:
        return {
            "match_id": self.match_id,
            "inputs": {
                "metadata_json": {"sha256": self.metadata_sha256, "byte_size": self.metadata_bytes},
                "tracking_jsonl": {
                    "sha256": self.tracking_sha256,
                    "byte_size": self.tracking_bytes,
                },
                "normalized_phase_intervals_json": {
                    "sha256": self.phase_sha256,
                    "byte_size": self.phase_bytes,
                },
            },
            "source_frame_count": self.source_frame_count,
            "retained_sample_count": self.retained_sample_count,
            "retained_samples_sha256": self.retained_samples_sha256,
        }


@dataclass(frozen=True, slots=True)
class Origin:
    match_id: str
    role: str
    period: int
    source_frame: int
    sample_id: str

    @property
    def identity(self) -> dict[str, str]:
        return {"match_id": self.match_id, "origin_sample_id": self.sample_id}


class MismatchCollector:
    """Bounded mismatch details with complete category totals and mismatch counts."""

    def __init__(
        self,
        limit: int = MAX_REPORT_ENTRIES,
        detail_byte_limit: int = MAX_REPORT_DETAIL_BYTES,
    ) -> None:
        self.limit = limit
        self.detail_byte_limit = detail_byte_limit
        self.total = 0
        self.by_category: Counter[str] = Counter()
        self.entries: list[dict[str, object]] = []
        self.detail_bytes = 2
        self.detail_limit_reached = False

    def add(
        self,
        category: str,
        identity: Mapping[str, object],
        expected: object,
        actual: object,
        *,
        expected_sha256: str | None = None,
        actual_sha256: str | None = None,
    ) -> None:
        self.total += 1
        self.by_category[category] += 1
        if len(self.entries) >= self.limit or self.detail_limit_reached:
            return
        entry: dict[str, object] = {
            "category": category,
            "identity": _bounded_report_identity(identity),
            "expected_sha256": expected_sha256
            or (None if expected is None else value_sha256(expected)),
            "actual_sha256": actual_sha256 or (None if actual is None else value_sha256(actual)),
        }
        entry_bytes = len(canonical_bytes(entry)) + bool(self.entries)
        if self.detail_bytes + entry_bytes > self.detail_byte_limit:
            self.detail_limit_reached = True
            return
        self.entries.append(entry)
        self.detail_bytes += entry_bytes

    def report_fields(self) -> dict[str, object]:
        return {
            "mismatch_count": self.total,
            "mismatch_counts_by_category": dict(sorted(self.by_category.items())),
            "reported_mismatch_count": len(self.entries),
            "suppressed_mismatch_count": self.total - len(self.entries),
            "reported_mismatch_detail_bytes": self.detail_bytes,
            "maximum_mismatch_detail_bytes": self.detail_byte_limit,
            "mismatches": self.entries,
        }


def _streaming_json_sha256(value: object) -> str:
    digest = hashlib.sha256()
    encoder = json.JSONEncoder(
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    for part in encoder.iterencode(value):
        for offset in range(0, len(part), 1024):
            digest.update(part[offset : offset + 1024].encode("utf-8"))
    return digest.hexdigest()


def _bounded_report_text(value: str) -> str | dict[str, object]:
    digest = hashlib.sha256()
    byte_size = 0
    for offset in range(0, len(value), 1024):
        block = value[offset : offset + 1024].encode("utf-8")
        byte_size += len(block)
        digest.update(block)
    if byte_size <= MAX_REPORT_IDENTITY_FIELD_BYTES:
        return value
    return {"prefix": value[:32], "sha256": digest.hexdigest(), "truncated": True}


def _bounded_report_identity(identity: Mapping[str, object]) -> dict[str, object]:
    bounded: dict[str, object] = {}
    for index, (key, value) in enumerate(identity.items()):
        if index >= MAX_REPORT_IDENTITY_FIELDS:
            bounded["_omitted_identity_fields"] = len(identity) - index
            break
        safe_key = key if len(key) <= 64 else f"field_{_streaming_json_sha256(key)}"
        if isinstance(value, str):
            bounded[safe_key] = _bounded_report_text(value)
        elif type(value) is int and value.bit_length() > 256:
            bounded[safe_key] = _bounded_report_text(str(value))
        elif value is None or type(value) in (bool, int, float):
            bounded[safe_key] = value
        elif isinstance(value, dict):
            bounded[safe_key] = {
                "type": "object",
                "sha256": _streaming_json_sha256(cast(dict[str, object], value)),
            }
        elif isinstance(value, list):
            bounded[safe_key] = {
                "type": "array",
                "sha256": _streaming_json_sha256(cast(list[object], value)),
            }
        else:
            bounded[safe_key] = {"type": type(value).__name__}
    return bounded


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def value_sha256(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise VerificationInputError(f"duplicate JSON member {key!r}")
        value[key] = item
    return value


def strict_json_bytes(payload: bytes, label: str, limit: int = MAX_DOCUMENT_BYTES) -> object:
    if len(payload) > limit:
        raise VerificationInputError(f"{label} exceeds the {limit}-byte document limit")
    try:
        text = payload.decode("utf-8", errors="strict")
        return json.loads(
            text,
            object_pairs_hook=_json_object,
            parse_constant=lambda value: (_ for _ in ()).throw(
                VerificationInputError(f"nonfinite JSON constant {value}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationInputError(f"{label} is not strict UTF-8 JSON: {exc}") from exc


def _absolute_parts(path: Path) -> tuple[str, ...]:
    if not path.is_absolute() or ".." in path.parts:
        raise VerificationInputError("worker file paths must be absolute and cannot contain '..'")
    return path.parts[1:]


def _open_directory_nofollow(path: Path) -> int:
    parts = _absolute_parts(path)
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        for part in parts:
            child = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
                dir_fd=fd,
            )
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _open_regular_nofollow(path: Path) -> tuple[int, os.stat_result]:
    parts = _absolute_parts(path)
    if not parts:
        raise VerificationInputError("expected a file path")
    parent_fd = _open_directory_nofollow(path.parent)
    try:
        fd = os.open(
            parts[-1],
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=parent_fd,
        )
    finally:
        os.close(parent_fd)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode):
        os.close(fd)
        raise VerificationInputError("worker input must be a regular file")
    return fd, info


def _stat_identity(info: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _snapshot_from_stat(digest: str, byte_size: int, info: os.stat_result) -> InputFileSnapshot:
    return InputFileSnapshot(
        digest,
        byte_size,
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _read_bounded_document(path: Path, label: str) -> tuple[bytes, os.stat_result]:
    fd, before = _open_regular_nofollow(path)
    try:
        with os.fdopen(fd, "rb") as stream:
            payload = stream.read(MAX_DOCUMENT_BYTES + 1)
            after = os.fstat(stream.fileno())
        if len(payload) > MAX_DOCUMENT_BYTES:
            raise VerificationInputError(f"{label} exceeds the {MAX_DOCUMENT_BYTES}-byte limit")
        if _stat_identity(before) != _stat_identity(after) or len(payload) != after.st_size:
            raise InputSnapshotChanged(f"{label} changed while being read")
        return payload, after
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


def _file_snapshot(
    path: Path,
    expected_snapshot: InputFileSnapshot | None = None,
) -> InputFileSnapshot:
    fd, before = _open_regular_nofollow(path)
    digest = hashlib.sha256()
    size = 0
    try:
        if expected_snapshot is not None and not expected_snapshot.matches_stat(before):
            raise InputSnapshotChanged("worker input identity changed since its first scan")
        with os.fdopen(fd, "rb") as stream:
            while block := stream.read(1024 * 1024):
                size += len(block)
                digest.update(block)
            after = os.fstat(stream.fileno())
        if _stat_identity(before) != _stat_identity(after) or size != after.st_size:
            raise InputSnapshotChanged("worker input changed while being hashed")
        return _snapshot_from_stat(digest.hexdigest(), size, after)
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


def _sha256_file(path: Path) -> tuple[str, int]:
    snapshot = _file_snapshot(path)
    return snapshot.sha256, snapshot.byte_size


def _authority_root() -> Path:
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True, slots=True)
class Authorities:
    source: dict[str, object]
    measurement: dict[str, object]
    eligibility: dict[str, object]
    protocol: dict[str, object]
    plan: dict[str, object]
    population_schema: dict[str, object]
    roles: tuple[tuple[str, str], ...]
    match_order: tuple[str, ...]


def load_authorities() -> Authorities:
    package_root = _authority_root()
    documents: dict[str, dict[str, object]] = {}
    for relative, expected_sha in AUTHORITY_FILE_HASHES.items():
        raw = (package_root / relative).read_bytes()
        actual_sha = hashlib.sha256(raw).hexdigest()
        if actual_sha != expected_sha:
            raise VerificationInputError(f"frozen authority bytes changed: {relative}")
        parsed = strict_json_bytes(raw, relative)
        if not isinstance(parsed, dict):
            raise VerificationInputError(f"frozen authority {relative} must be a JSON object")
        documents[relative] = cast(dict[str, object], parsed)

    state = documents["data_states/skillcorner_5hz_v2.json"]
    eligibility = documents["eligibility/skillcorner_window_v2.json"]
    protocol = documents[
        "benchmarks/conditional_multi_agent_motion_prediction/prospective_skillcorner_protocol_v2.json"
    ]
    plan = documents[
        "benchmarks/conditional_multi_agent_motion_prediction/empirical_experiment_plan_v2.json"
    ]
    source = documents["data_sources/skillcorner_open_data_v1.json"]
    schema = documents[
        "benchmarks/conditional_multi_agent_motion_prediction/evaluation_population_authority_v2.schema.json"
    ]
    state_hash = value_sha256(state["scientific_state"])
    eligibility_hash = value_sha256(eligibility["scientific_policy"])
    protocol_hash = value_sha256(protocol["scientific_state"])
    plan_payload = {key: value for key, value in plan.items() if key != "plan_sha256"}
    plan_hash = value_sha256(plan_payload)
    checks = (
        (state_hash, MEASUREMENT_HASH, "measurement state"),
        (eligibility_hash, ELIGIBILITY_HASH, "eligibility policy"),
        (protocol_hash, PROTOCOL_HASH, "protocol"),
        (plan_hash, PLAN_HASH, "experiment plan"),
        (state.get("data_state_hash"), MEASUREMENT_HASH, "measurement state identifier"),
        (eligibility.get("policy_hash"), ELIGIBILITY_HASH, "eligibility policy identifier"),
        (protocol.get("protocol_sha256"), PROTOCOL_HASH, "protocol identifier"),
        (plan.get("plan_sha256"), PLAN_HASH, "experiment plan identifier"),
        (source.get("source_release_hash"), SOURCE_RELEASE_HASH, "source release"),
        (source.get("source_population_hash"), SOURCE_POPULATION_HASH, "source population"),
    )
    for actual, expected, name in checks:
        if actual != expected:
            raise VerificationInputError(f"frozen {name} binding differs from the verifier pin")

    protocol_state = _as_mapping(protocol.get("scientific_state"), "protocol scientific_state")
    split = _as_mapping(protocol_state.get("split"), "protocol split")
    roles_value = _as_mapping(split.get("roles"), "protocol roles")
    role_rows: list[tuple[str, str]] = []
    for role in ("training", "validation", "evaluation"):
        ids = _as_sequence(roles_value.get(role), f"frozen {role} role")
        if not all(isinstance(item, str) for item in ids):
            raise VerificationInputError(f"frozen {role} role is not a string array")
        role_rows.extend((role, cast(str, match_id)) for match_id in ids)
    match_order = tuple(match_id for _, match_id in role_rows)
    selected = _as_sequence(source.get("selected_source_matches"), "selected source matches")
    selected_ids = tuple(str(item) for item in selected)
    if (
        len(role_rows) != 20
        or [
            sum(role == name for role, _ in role_rows)
            for name in ("training", "validation", "evaluation")
        ]
        != [12, 4, 4]
        or len(set(match_order)) != 20
        or set(match_order) != set(selected_ids)
    ):
        raise VerificationInputError(
            "frozen role assignment is not the exact selected 12/4/4 population"
        )
    return Authorities(
        source=source,
        measurement=state,
        eligibility=eligibility,
        protocol=protocol,
        plan=plan,
        population_schema=schema,
        roles=tuple(role_rows),
        match_order=match_order,
    )


def _as_mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise VerificationInputError(f"{label} must be an object with string keys")
    raw = cast(dict[object, object], value)
    if not all(isinstance(key, str) for key in raw):
        raise VerificationInputError(f"{label} must be an object with string keys")
    return cast(dict[str, object], raw)


def _as_sequence(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise VerificationInputError(f"{label} must be an array")
    return cast(list[object], value)


def _normalize_json_value(value: object) -> object:
    if isinstance(value, dict):
        return cast(dict[str, object], value)
    if isinstance(value, list):
        return cast(list[object], value)
    return value


def _int(value: object, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise VerificationInputError(f"{label} must be an integer >= {minimum}")
    return value


def _number(value: object, label: str, *, nullable: bool = False) -> float | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise VerificationInputError(f"{label} must be a finite JSON number")
    result = float(value)
    if not math.isfinite(result):
        raise VerificationInputError(f"{label} must be a finite JSON number")
    return result


def verify_producer_source_package(package_root: Path) -> dict[str, object]:
    """Authenticate the reviewed source inventory against code-pinned file digests."""
    actual_files: list[dict[str, str]] = []
    for relative, expected_digest in PRODUCER_SOURCE_HASHES:
        digest, _ = _sha256_file(package_root / relative)
        if digest != expected_digest:
            raise VerificationInputError(f"pinned PR #25 source differs: {relative}")
        actual_files.append({"path": relative, "sha256": digest})
    identity: dict[str, object] = {
        "schema_id": "fpdbench.streaming-worker-package-identity",
        "schema_version": "1.0.0",
        "package": (
            "fpdbench.benchmarks.conditional_multi_agent_motion_prediction."
            "streaming_population_producer_v1"
        ),
        "worker_version": PRODUCER_VERSION,
        "hash_algorithm": "sha256",
        "source_inventory_scope": "listed Python and frozen authority files only",
        "executable_runtime_attestation": "NOT_PROVIDED",
        "files": actual_files,
    }
    identity_digest = value_sha256(identity)
    if identity_digest != PRODUCER_IDENTITY_SHA256:
        raise VerificationInputError("pinned PR #25 source-package identity differs")
    identity["sha256"] = identity_digest
    return identity


def _timestamp_deciseconds(value: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise VerificationInputError("source timestamp must be a string or null")
    match = _TIMESTAMP.fullmatch(value)
    if match is None:
        raise VerificationInputError("source timestamp is not HH:MM:SS.cc")
    hours, minutes, seconds, centiseconds = (int(part) for part in match.groups())
    if centiseconds % 10:
        raise VerificationInputError("source timestamps must use exact 100 ms ticks")
    return ((hours * 60 + minutes) * 60 + seconds) * 10 + centiseconds // 10


def _canonical_ball(raw: object) -> dict[str, object] | None:
    if raw is None:
        return None
    ball = _as_mapping(raw, "ball_data")
    if set(ball) != {"x", "y", "z", "is_detected"}:
        raise VerificationInputError("raw ball_data fields differ from the pinned state")
    z = _number(ball["z"], "ball z", nullable=True)
    del z
    detected = ball["is_detected"]
    if detected is not None and not isinstance(detected, bool):
        raise VerificationInputError("ball detection flag must be boolean or null")
    return {
        "x_m": _number(ball["x"], "ball x", nullable=True),
        "y_m": _number(ball["y"], "ball y", nullable=True),
        "is_detected": detected,
    }


def _canonical_possession(raw: object) -> dict[str, object] | None:
    if raw is None:
        return None
    possession = _as_mapping(raw, "possession")
    if set(possession) != {"group", "player_id"}:
        raise VerificationInputError("raw possession fields differ from the pinned state")
    group = possession["group"]
    player_id = possession["player_id"]
    if group is not None and group not in {"home team", "away team"}:
        raise VerificationInputError("possession group is not a pinned home/away value")
    if player_id is not None:
        _int(player_id, "possession player_id", minimum=1)
    return {"group": group, "player_id": player_id}


def _canonical_sample(
    row: dict[str, object],
    contract: MatchContract,
    authorities: Authorities,
    frame: int,
    timestamp: int | None,
    period: int | None,
) -> dict[str, object]:
    raw_players = _as_sequence(row["player_data"], "player_data")
    players: list[dict[str, object]] = []
    seen: set[int] = set()
    for raw in raw_players:
        player = _as_mapping(raw, "player_data entry")
        if set(player) != {"player_id", "x", "y", "is_detected"}:
            raise VerificationInputError("raw player fields differ from the pinned state")
        player_id = _int(player["player_id"], "player_id", minimum=1)
        team_id = contract.team_by_player.get(player_id)
        if team_id is None:
            raise VerificationInputError("source player is absent from its match roster")
        if player_id in seen:
            raise VerificationInputError("duplicate source player_id in one frame")
        seen.add(player_id)
        detected = player["is_detected"]
        if not isinstance(detected, bool):
            raise VerificationInputError("player detection flag must be boolean")
        players.append(
            {
                "player_id": player_id,
                "team_id": team_id,
                "group": "home" if team_id == contract.home_team_id else "away",
                "x_m": _number(player["x"], "player x", nullable=True),
                "y_m": _number(player["y"], "player y", nullable=True),
                "is_detected": detected,
            }
        )
    players.sort(key=lambda item: cast(int, item["player_id"]))
    return {
        "data_state_id": "skillcorner_5hz_v2",
        "data_state_hash": MEASUREMENT_HASH,
        "source_release_id": cast(str, authorities.source["source_release_id"]),
        "source_release_hash": SOURCE_RELEASE_HASH,
        "match_id": int(contract.match_id),
        "period": period,
        "source_frame": frame,
        "canonical_sample_index": frame // 2,
        "timestamp_deciseconds": timestamp,
        "home_team_id": contract.home_team_id,
        "away_team_id": contract.away_team_id,
        "pitch_length_m": contract.pitch_length,
        "pitch_width_m": contract.pitch_width,
        "players": players,
        "ball": _canonical_ball(row["ball_data"]),
        "possession": _canonical_possession(row["possession"]),
    }


def _read_tracking(
    path: Path,
    contract: MatchContract,
    authorities: Authorities,
    stats: dict[str, object],
    expected_snapshot: InputFileSnapshot | None = None,
) -> Iterator[dict[str, object]]:
    try:
        fd, before = _open_regular_nofollow(path)
    except OSError as exc:
        if expected_snapshot is not None:
            raise InputSnapshotChanged("tracking input disappeared between scans") from exc
        raise
    raw_digest = hashlib.sha256()
    retained_digest = CanonicalArrayDigest()
    byte_count = frame_count = retained_count = 0
    previous_frame: int | None = None
    previous_period: int | None = None
    previous_time: int | None = None
    try:
        if expected_snapshot is not None and not expected_snapshot.matches_stat(before):
            raise InputSnapshotChanged("tracking input identity changed between scans")
        with os.fdopen(fd, "rb") as stream:
            while line := stream.readline(MAX_TRACKING_ROW_BYTES + 1):
                if len(line) > MAX_TRACKING_ROW_BYTES or not line.strip():
                    raise VerificationInputError("tracking row is blank or exceeds the row limit")
                raw_digest.update(line)
                byte_count += len(line)
                frame_value = strict_json_bytes(line, "tracking row", MAX_TRACKING_ROW_BYTES)
                row = _as_mapping(frame_value, "tracking row")
                required = {
                    "frame",
                    "timestamp",
                    "period",
                    "ball_data",
                    "possession",
                    "image_corners_projection",
                    "player_data",
                }
                if set(row) != required:
                    raise VerificationInputError("tracking row fields differ from the pinned state")
                frame = _int(row["frame"], "source frame")
                if previous_frame is not None and frame <= previous_frame:
                    raise VerificationInputError("source frame numbers must increase strictly")
                period_value = row["period"]
                period = (
                    None if period_value is None else _int(period_value, "source period", minimum=1)
                )
                if period not in {None, 1, 2}:
                    raise VerificationInputError("source period must be 1, 2, or null")
                timestamp = _timestamp_deciseconds(row["timestamp"])
                if (
                    period is not None
                    and period == previous_period
                    and previous_frame is not None
                    and previous_time is not None
                    and timestamp is not None
                    and timestamp - previous_time != frame - previous_frame
                ):
                    raise VerificationInputError("source frame/timestamp intervals disagree")
                frame_count += 1
                if frame % 2 == 0:
                    sample = _canonical_sample(row, contract, authorities, frame, timestamp, period)
                    retained_digest.append(sample)
                    retained_count += 1
                    yield sample
                previous_frame = frame
                previous_period = period
                previous_time = timestamp
            after = os.fstat(stream.fileno())
        if _stat_identity(before) != _stat_identity(after) or after.st_size != byte_count:
            raise InputSnapshotChanged("tracking input changed during the scan")
        snapshot = _snapshot_from_stat(raw_digest.hexdigest(), byte_count, after)
        if expected_snapshot is not None and snapshot != expected_snapshot:
            raise InputSnapshotChanged("tracking input changed between scans")
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
    stats.update(
        source_frame_count=frame_count,
        retained_sample_count=retained_count,
        raw_byte_count=byte_count,
        raw_sha256=raw_digest.hexdigest(),
        retained_samples_sha256=retained_digest.hexdigest(),
        file_snapshot=snapshot,
    )


def _read_input_document(path: Path, label: str) -> tuple[bytes, object, InputFileSnapshot]:
    payload, info = _read_bounded_document(path, label)
    digest = hashlib.sha256(payload).hexdigest()
    snapshot = _snapshot_from_stat(digest, len(payload), info)
    return payload, strict_json_bytes(payload, label), snapshot


def _metadata_periods(metadata: dict[str, object]) -> dict[int, tuple[int, int]]:
    raw_periods = _as_sequence(metadata.get("match_periods"), "match_periods")
    if not raw_periods:
        raise VerificationInputError("match metadata must define at least one period bound")
    periods: dict[int, tuple[int, int]] = {}
    for offset, raw in enumerate(raw_periods):
        item = _as_mapping(raw, f"match_periods[{offset}]")
        period = _int(item.get("period"), "period", minimum=1)
        start = _int(item.get("start_frame"), "period start_frame")
        end = _int(item.get("end_frame"), "period end_frame")
        if period not in {1, 2} or start >= end:
            raise VerificationInputError("match period has unsupported identity or empty bounds")
        if period in periods:
            raise VerificationInputError("match metadata defines a period more than once")
        periods[period] = (start, end)
    ordered = sorted(periods.items())
    for (prior_period, (_, prior_end)), (period, (start, _)) in zip(
        ordered, ordered[1:], strict=False
    ):
        if start < prior_end:
            raise VerificationInputError(
                f"period bounds for periods {prior_period} and {period} overlap"
            )
    return periods


def _appearance_metadata(
    metadata: dict[str, object],
    team_by_player: dict[int, int],
) -> tuple[dict[int, dict[int, tuple[tuple[int, int], ...]]], bool]:
    roster = metadata.get("players")
    if not isinstance(roster, list):
        return {}, False
    roster_values = cast(list[object], roster)
    appearances: dict[int, dict[int, tuple[tuple[int, int], ...]]] = {}
    complete = True
    for offset, raw_player in enumerate(roster_values):
        player = _as_mapping(raw_player, f"players[{offset}]")
        player_id = _int(player.get("id"), "roster player id", minimum=1)
        playing = player.get("playing_time")
        if not isinstance(playing, dict):
            complete = False
            continue
        playing_value = cast(dict[str, object], playing)
        raw_by_period_value = playing_value.get("by_period")
        if not isinstance(raw_by_period_value, list):
            complete = False
            continue
        raw_by_period = cast(list[object], raw_by_period_value)
        by_period: dict[int, list[tuple[int, int]]] = {}
        for raw_interval in raw_by_period:
            if not isinstance(raw_interval, dict):
                complete = False
                continue
            interval = cast(dict[str, object], raw_interval)
            name = interval.get("name")
            match = _PERIOD_NAME.fullmatch(name) if isinstance(name, str) else None
            if match is None:
                complete = False
                continue
            period = int(match.group(1))
            start = interval.get("start_frame")
            end = interval.get("end_frame")
            if (
                isinstance(start, bool)
                or not isinstance(start, int)
                or isinstance(end, bool)
                or not isinstance(end, int)
                or start > end
            ):
                complete = False
                continue
            by_period.setdefault(period, []).append((start, end))
        appearances[player_id] = {
            period: tuple(intervals) for period, intervals in by_period.items()
        }
    return appearances, complete and len(appearances) == len(team_by_player)


def load_input_contracts(
    input_root: Path,
    authorities: Authorities,
) -> tuple[dict[str, MatchContract], dict[str, MatchInputSnapshots]]:
    _open_root_fd = _open_directory_nofollow(input_root)
    os.close(_open_root_fd)
    match_ids = authorities.match_order
    seen: set[str] = set()
    try:
        for entry in input_root.iterdir():
            if entry.is_symlink() or not entry.is_dir():
                raise VerificationInputError(
                    "input root may contain only regular match directories"
                )
            seen.add(entry.name)
    except OSError as exc:
        raise VerificationInputError(f"cannot enumerate input root: {exc}") from exc
    if seen != set(match_ids):
        raise VerificationInputError(
            "input root must contain exactly the pinned 20 match directories"
        )

    contracts: dict[str, MatchContract] = {}
    input_snapshots: dict[str, MatchInputSnapshots] = {}
    for role, match_id in authorities.roles:
        directory = input_root / match_id
        metadata_path = directory / "metadata.json"
        phase_path = directory / "phases.json"
        _, metadata_value, metadata_snapshot = _read_input_document(
            metadata_path, f"metadata for {match_id}"
        )
        _, phase_value, phase_snapshot = _read_input_document(
            phase_path, f"phase intervals for {match_id}"
        )
        metadata = _as_mapping(metadata_value, "match metadata")
        if type(metadata.get("id")) is not int or str(metadata["id"]) != match_id:
            raise VerificationInputError(f"metadata identity differs for match {match_id}")
        home = _as_mapping(metadata.get("home_team"), "home_team")
        away = _as_mapping(metadata.get("away_team"), "away_team")
        home_id = _int(home.get("id"), "home_team.id", minimum=1)
        away_id = _int(away.get("id"), "away_team.id", minimum=1)
        if home_id == away_id:
            raise VerificationInputError("home and away team IDs must differ")
        pitch_length = _number(metadata.get("pitch_length"), "pitch_length")
        pitch_width = _number(metadata.get("pitch_width"), "pitch_width")
        if pitch_length is None or pitch_width is None or pitch_length <= 0 or pitch_width <= 0:
            raise VerificationInputError("match pitch dimensions must be positive finite values")
        if int(match_id) not in cast(list[object], authorities.source["selected_source_matches"]):
            raise VerificationInputError("match ID is outside the pinned source release")
        periods = _metadata_periods(metadata)

        raw_roster = _as_sequence(metadata.get("players"), "match metadata players")
        team_by_player: dict[int, int] = {}
        for offset, raw in enumerate(raw_roster):
            player = _as_mapping(raw, f"players[{offset}]")
            player_id = _int(player.get("id"), "roster player id", minimum=1)
            team_id = _int(player.get("team_id"), "roster player team_id", minimum=1)
            if team_id not in {home_id, away_id} or player_id in team_by_player:
                raise VerificationInputError("roster identity is duplicate or outside match teams")
            team_by_player[player_id] = team_id
        appearances, roster_complete = _appearance_metadata(metadata, team_by_player)

        raw_phases = _as_sequence(phase_value, "normalized phase intervals")
        phases: list[dict[str, int]] = []
        for offset, raw in enumerate(raw_phases):
            phase = _as_mapping(raw, f"phase_intervals[{offset}]")
            if set(phase) != {"period", "frame_start", "frame_end"}:
                raise VerificationInputError(
                    "phase interval fields differ from the normalized contract"
                )
            period = _int(phase["period"], "phase period", minimum=1)
            start = _int(phase["frame_start"], "phase frame_start")
            end = _int(phase["frame_end"], "phase frame_end")
            phases.append({"period": period, "frame_start": start, "frame_end": end})

        contracts[match_id] = MatchContract(
            match_id=match_id,
            role=role,
            metadata=metadata,
            phases=tuple(phases),
            period_bounds=periods,
            team_by_player=team_by_player,
            appearances=appearances,
            roster_complete=roster_complete,
            home_team_id=home_id,
            away_team_id=away_id,
            pitch_length=pitch_length,
            pitch_width=pitch_width,
        )
        input_snapshots[match_id] = MatchInputSnapshots(metadata_snapshot, phase_snapshot)
    return contracts, input_snapshots


def _global_drift_scan(
    contracts: Mapping[str, MatchContract],
    input_snapshots: dict[str, MatchInputSnapshots],
    input_root: Path,
    authorities: Authorities,
) -> tuple[dict[str, SourceReceipt], dict[str, object], int]:
    source_receipts: dict[str, SourceReceipt] = {}
    checked_sample_count = 0
    checked_matches: set[str] = set()
    drift_count = 0
    for _, match_id in authorities.roles:
        contract = contracts[match_id]
        stats: dict[str, object] = {}
        sample_count = 0
        for sample in _read_tracking(
            input_root / match_id / "tracking.jsonl", contract, authorities, stats
        ):
            sample_count += 1
            checked_sample_count += 1
            checked_matches.add(match_id)
            ball_value = sample["ball"]
            if isinstance(ball_value, dict):
                ball = cast(dict[str, object], ball_value)
                if (
                    ball.get("is_detected") is None
                    and ball.get("x_m") is not None
                    and ball.get("y_m") is not None
                ):
                    drift_count += 1
        snapshots = input_snapshots[match_id]
        tracking_snapshot = cast(InputFileSnapshot, stats["file_snapshot"])
        snapshots.tracking = tracking_snapshot
        raw_sha256 = cast(str, stats["raw_sha256"])
        source_receipts[match_id] = SourceReceipt(
            match_id=match_id,
            metadata_sha256=snapshots.metadata.sha256,
            metadata_bytes=snapshots.metadata.byte_size,
            tracking_sha256=raw_sha256,
            tracking_bytes=cast(int, stats["raw_byte_count"]),
            phase_sha256=snapshots.phases.sha256,
            phase_bytes=snapshots.phases.byte_size,
            source_frame_count=cast(int, stats["source_frame_count"]),
            retained_sample_count=cast(int, stats["retained_sample_count"]),
            retained_samples_sha256=cast(str, stats["retained_samples_sha256"]),
        )
        if sample_count == 0:
            raise VerificationInputError(f"match {match_id} has no retained 5 Hz samples")
    drift_scan: dict[str, object] = {
        "checked_match_count": len(checked_matches),
        "checked_sample_count": checked_sample_count,
        "data_state_hash": MEASUREMENT_HASH,
        "null_flag_finite_xy_count": drift_count,
        "source_release_hash": SOURCE_RELEASE_HASH,
    }
    return source_receipts, drift_scan, drift_count


def _validate_input_snapshots(
    input_root: Path,
    authorities: Authorities,
    input_snapshots: Mapping[str, MatchInputSnapshots],
    *,
    include_tracking: bool,
) -> None:
    for _, match_id in authorities.roles:
        snapshots = input_snapshots[match_id]
        paths = (
            ("metadata.json", snapshots.metadata),
            ("phases.json", snapshots.phases),
        )
        for filename, expected in paths:
            try:
                actual = _file_snapshot(input_root / match_id / filename, expected)
            except OSError as exc:
                raise InputSnapshotChanged(
                    f"{filename} became unavailable for match {match_id}"
                ) from exc
            if actual != expected:
                raise InputSnapshotChanged(f"{filename} changed for match {match_id}")
        if include_tracking:
            expected_tracking = snapshots.tracking
            if expected_tracking is None:
                raise InputSnapshotChanged(f"tracking snapshot missing for match {match_id}")
            try:
                actual_tracking = _file_snapshot(
                    input_root / match_id / "tracking.jsonl", expected_tracking
                )
            except OSError as exc:
                raise InputSnapshotChanged(
                    f"tracking.jsonl became unavailable for match {match_id}"
                ) from exc
            if actual_tracking != expected_tracking:
                raise InputSnapshotChanged(f"tracking.jsonl changed for match {match_id}")


def _active_player_ids(contract: MatchContract, period: int, source_frame: int) -> set[int]:
    return {
        player_id
        for player_id, by_period in contract.appearances.items()
        if any(start <= source_frame <= end for start, end in by_period.get(period, ()))
    }


def _sorted_issues(items: list[dict[str, object]]) -> list[dict[str, object]]:
    unique = {
        (
            cast(str, item["code"]),
            cast(str, item["message"]),
            cast(int | None, item["sample_index"]),
        ): item
        for item in items
    }
    return [
        unique[key]
        for key in sorted(
            unique,
            key=lambda value: (
                -1 if value[2] is None else value[2],
                value[0],
                value[1],
            ),
        )
    ]


def _diagnose_window(
    support: Sequence[dict[str, object] | None],
    contract: MatchContract,
    authorities: Authorities,
) -> dict[str, object]:
    """Derive one v2 decision and quality record from frozen policy values."""
    policy = _as_mapping(authorities.eligibility["scientific_policy"], "eligibility policy")
    players_policy = _as_mapping(policy["player_observations"], "player policy")
    ball_policy = _as_mapping(policy["ball_observations"], "ball policy")
    coordinate_policy = _as_mapping(policy["coordinate_checks"], "coordinate policy")
    temporal_policy = _as_mapping(policy["temporal_continuity"], "temporal policy")
    sample_policy = _as_mapping(policy["support"], "support policy")
    expected_count = _int(ball_policy["expected_support_slots"], "support slot count", minimum=1)
    if len(support) != expected_count:
        raise VerificationInputError("verifier support does not contain the frozen slot count")

    reasons: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []

    def reject(code: str, message: str, sample_index: int | None = None) -> None:
        reasons.append({"code": code, "message": message, "sample_index": sample_index})

    def warn(code: str, message: str, sample_index: int | None = None) -> None:
        warnings.append({"code": code, "message": message, "sample_index": sample_index})

    support_complete = all(sample is not None for sample in support)
    support_span_available = len(support) == expected_count
    missing_source_sample_count = sum(sample is None for sample in support)
    periods: list[int | None] = [None] * expected_count
    sample_indexes: list[int | None] = [None] * expected_count
    source_frames: list[int | None] = [None] * expected_count
    timestamps: list[int | None] = [None] * expected_count
    active_rosters: list[set[int] | None] = [None] * expected_count
    player_positions: list[dict[int, tuple[float, float]]] = [{} for _ in range(expected_count)]
    ball_positions: list[tuple[float, float] | None] = [None] * expected_count

    minimum_team_players = _int(
        players_policy["minimum_valid_per_team_per_sample"],
        "minimum valid players per team",
        minimum=1,
    )
    minimum_ball_fraction = cast(float, ball_policy["minimum_valid_fraction"])
    player_gross_x = cast(float, coordinate_policy["player_gross_limit_pitch_dimension_multiple"])
    player_gross_y = player_gross_x
    ball_gross_x = cast(float, coordinate_policy["ball_gross_limit_pitch_dimension_multiple"])
    ball_gross_y = ball_gross_x
    player_speed_limit = cast(float, coordinate_policy["player_displacement_warning_mps"])
    ball_speed_limit = cast(float, coordinate_policy["ball_displacement_warning_mps"])
    source_frame_step = _int(temporal_policy["source_frame_step"], "source frame step", minimum=1)
    sample_index_step = _int(
        temporal_policy["canonical_sample_step"], "canonical sample step", minimum=1
    )
    timestamp_step = _int(
        temporal_policy["timestamp_step_deciseconds"], "timestamp step", minimum=1
    )
    elapsed_seconds = cast(float, sample_policy["sample_interval_deciseconds"]) / 10.0

    active_player_frames = 0
    valid_active_player_positions = 0
    unknown_roster_samples = 0
    missing_active_records = 0
    valid_player_positions = 0
    observed_player_records = 0
    detected_players = 0
    extrapolated_players = 0
    null_player_positions = 0
    outside_pitch_players = 0
    player_displacement_pairs = 0
    player_outliers = 0

    valid_ball_positions = 0
    detected_balls = 0
    extrapolated_balls = 0
    unknown_ball_positions = 0
    true_flags = 0
    false_flags = 0
    null_flags = 0
    absent_ball_objects = 0
    outside_pitch_balls = 0
    ball_displacement_pairs = 0
    ball_outliers = 0

    coordinate_states = (
        "both_finite",
        "x_only",
        "y_only",
        "both_null",
        "object_absent",
        "source_sample_missing",
    )
    flag_states = (
        "true",
        "false",
        "null",
        "object_absent_not_applicable",
        "source_sample_missing_not_applicable",
    )
    cross_tab: dict[str, dict[str, int]] = {
        flag: {coordinate: 0 for coordinate in coordinate_states} for flag in flag_states
    }
    cross_tab["source_sample_missing_not_applicable"]["source_sample_missing"] = (
        missing_source_sample_count
    )
    if missing_source_sample_count:
        reject("TEMPORAL_GAP", "expected source sample is missing")

    team_observations: list[dict[int, int]] = []
    possession_categories: list[object] = ["missing"] * expected_count
    possession_home = possession_away = possession_unknown = 0
    active_transitions = 0
    changed_active_ids: set[int] = set()
    observed_identity_changes = 0
    identity_comparisons = 0
    continuous_intervals = 0

    for offset, sample in enumerate(support):
        team_counts = {contract.home_team_id: 0, contract.away_team_id: 0}
        team_observations.append(team_counts)
        if sample is None:
            continue
        sample_index = _int(sample.get("canonical_sample_index"), "canonical sample index")
        source_frame = _int(sample.get("source_frame"), "canonical source frame")
        period_value = sample.get("period")
        period = None if period_value is None else _int(period_value, "canonical period", minimum=1)
        timestamp_value = sample.get("timestamp_deciseconds")
        timestamp = (
            None if timestamp_value is None else _int(timestamp_value, "canonical timestamp")
        )
        sample_indexes[offset] = sample_index
        source_frames[offset] = source_frame
        periods[offset] = period
        timestamps[offset] = timestamp

        if (
            sample.get("data_state_id") != "skillcorner_5hz_v2"
            or sample.get("data_state_hash") != MEASUREMENT_HASH
            or sample.get("source_release_id") != authorities.source.get("source_release_id")
            or sample.get("source_release_hash") != SOURCE_RELEASE_HASH
            or sample.get("match_id") != int(contract.match_id)
            or sample.get("home_team_id") != contract.home_team_id
            or sample.get("away_team_id") != contract.away_team_id
            or sample.get("pitch_length_m") != contract.pitch_length
            or sample.get("pitch_width_m") != contract.pitch_width
        ):
            reject(
                "INVALID_SAMPLE_SCHEMA",
                "canonical sample binding differs from metadata",
                sample_index,
            )
        if source_frame % 2 != 0 or sample_index != source_frame // 2:
            reject(
                "CANONICAL_FRAME_MISMATCH",
                "source frame or canonical index is inconsistent",
                sample_index,
            )
        if period is None:
            reject("INVALID_SAMPLE_SCHEMA", "period is null", sample_index)
        elif period not in contract.period_bounds:
            reject(
                "PERIOD_BOUNDS_MISSING",
                "match metadata has no frame bounds for this sample period",
                sample_index,
            )
        elif not (
            contract.period_bounds[period][0] <= source_frame < contract.period_bounds[period][1]
        ):
            reject(
                "OUTSIDE_PERIOD_BOUNDS",
                "sample falls outside match metadata period bounds",
                sample_index,
            )
        if timestamp is None:
            reject("TIMESTAMP_MISSING", "timestamp_deciseconds is null", sample_index)
        if set(sample) != {
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
        }:
            reject(
                "INVALID_SAMPLE_SCHEMA",
                "canonical sample fields differ from the measurement state",
                sample_index,
            )

        active_ids: set[int] | None = None
        if contract.roster_complete and period is not None:
            active_ids = _active_player_ids(contract, period, source_frame)
            active_player_frames += len(active_ids)
        else:
            unknown_roster_samples += 1
        active_rosters[offset] = active_ids

        raw_players = sample.get("players")
        if not isinstance(raw_players, list):
            reject("INVALID_SAMPLE_SCHEMA", "players must be an array", sample_index)
            raw_players = []
        seen_player_ids: set[int] = set()
        valid_positions: dict[int, tuple[float, float]] = {}
        for raw_player in cast(list[object], raw_players):
            player = _as_mapping(raw_player, "canonical player")
            if set(player) != {"player_id", "team_id", "group", "x_m", "y_m", "is_detected"}:
                reject(
                    "INVALID_SAMPLE_SCHEMA",
                    "canonical player fields differ from the measurement state",
                    sample_index,
                )
                continue
            player_id = _int(player.get("player_id"), "player_id", minimum=1)
            team_id = _int(player.get("team_id"), "player team_id", minimum=1)
            if player_id in seen_player_ids:
                reject("DUPLICATE_PLAYER_ID", f"duplicate player_id {player_id}", sample_index)
                continue
            seen_player_ids.add(player_id)
            observed_player_records += 1
            expected_group = "home" if team_id == contract.home_team_id else "away"
            if (
                team_id not in team_counts
                or contract.team_by_player.get(player_id) != team_id
                or player.get("group") != expected_group
            ):
                reject(
                    "PLAYER_TEAM_IDENTITY_CONFLICT",
                    f"player_id {player_id} has an inconsistent team",
                    sample_index,
                )
                continue
            detected = player.get("is_detected")
            if not isinstance(detected, bool):
                reject(
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
            if (
                abs(x) > player_gross_x * contract.pitch_length
                or abs(y) > player_gross_y * contract.pitch_width
            ):
                reject(
                    "COORDINATE_IMPLAUSIBLE",
                    f"player_id {player_id} exceeds gross pitch-relative bounds",
                    sample_index,
                )
                continue
            if active_ids is not None and player_id not in active_ids:
                warn(
                    "PLAYER_OUTSIDE_APPEARANCE",
                    f"player_id {player_id} is outside metadata playing-time intervals",
                    sample_index,
                )
                continue
            valid_positions[player_id] = (x, y)
            valid_player_positions += 1
            team_counts[team_id] += 1
            if detected:
                detected_players += 1
            else:
                extrapolated_players += 1
            if abs(x) > contract.pitch_length / 2.0 or abs(y) > contract.pitch_width / 2.0:
                outside_pitch_players += 1
                warn(
                    "PLAYER_POSITION_OUTSIDE_PITCH",
                    f"player_id {player_id} is outside the pitch rectangle",
                    sample_index,
                )
            if active_ids is not None and player_id in active_ids:
                valid_active_player_positions += 1
        player_positions[offset] = valid_positions
        if (
            team_counts[contract.home_team_id] < minimum_team_players
            or team_counts[contract.away_team_id] < minimum_team_players
        ):
            reject(
                "PLAYER_COUNT_BELOW_TEAM_MINIMUM",
                f"valid active counts home={team_counts[contract.home_team_id]}, "
                f"away={team_counts[contract.away_team_id]}; minimum={minimum_team_players} each",
                sample_index,
            )
        if active_ids is not None:
            missing = active_ids - seen_player_ids
            missing_active_records += len(missing)
            if missing:
                warn(
                    "PLAYER_OBSERVATION_MISSING",
                    f"{len(missing)} active player records are absent",
                    sample_index,
                )

        ball_value = sample.get("ball")
        ball_position: tuple[float, float] | None = None
        if ball_value is None:
            absent_ball_objects += 1
            cross_tab["object_absent_not_applicable"]["object_absent"] += 1
            warn("BALL_OBJECT_ABSENT", "ball_data is absent", sample_index)
        else:
            ball = _as_mapping(ball_value, "canonical ball")
            if set(ball) != {"x_m", "y_m", "is_detected"}:
                reject(
                    "INVALID_SAMPLE_SCHEMA",
                    "canonical ball fields differ from the measurement state",
                    sample_index,
                )
            else:
                detected = ball.get("is_detected")
                if detected is not None and not isinstance(detected, bool):
                    reject(
                        "INVALID_DETECTION_FLAG",
                        "ball is_detected must be boolean or null",
                        sample_index,
                    )
                else:
                    x = _number(ball.get("x_m"), "ball x_m", nullable=True)
                    y = _number(ball.get("y_m"), "ball y_m", nullable=True)
                    flag_state = (
                        "true" if detected is True else "false" if detected is False else "null"
                    )
                    coordinate_state = (
                        "both_finite"
                        if x is not None and y is not None
                        else "x_only"
                        if x is not None
                        else "y_only"
                        if y is not None
                        else "both_null"
                    )
                    cross_tab[flag_state][coordinate_state] += 1
                    if detected is True:
                        true_flags += 1
                    elif detected is False:
                        false_flags += 1
                    else:
                        null_flags += 1
                        warn("BALL_DETECTION_UNKNOWN", "ball detection flag is null", sample_index)
                    if x is not None and y is not None:
                        valid_ball_positions += 1
                        if detected is None:
                            unknown_ball_positions += 1
                        if (
                            abs(x) > ball_gross_x * contract.pitch_length
                            or abs(y) > ball_gross_y * contract.pitch_width
                        ):
                            reject(
                                "COORDINATE_IMPLAUSIBLE",
                                "ball exceeds gross pitch-relative bounds",
                                sample_index,
                            )
                        else:
                            ball_position = (x, y)
                            if detected is True:
                                detected_balls += 1
                            elif detected is False:
                                extrapolated_balls += 1
                            if (
                                abs(x) > contract.pitch_length / 2.0
                                or abs(y) > contract.pitch_width / 2.0
                            ):
                                outside_pitch_balls += 1
                                warn(
                                    "BALL_OUTSIDE_PITCH",
                                    "ball is outside the pitch rectangle",
                                    sample_index,
                                )
                    elif x is not None or y is not None:
                        warn(
                            "BALL_COORDINATES_PARTIAL",
                            "ball has only one finite coordinate",
                            sample_index,
                        )
                    else:
                        warn(
                            "BALL_COORDINATES_MISSING",
                            "ball has no finite XY coordinates",
                            sample_index,
                        )
        ball_positions[offset] = ball_position

        possession = sample.get("possession")
        possession_categories[offset] = "invalid"
        if possession is None:
            possession_categories[offset] = None
            possession_unknown += 1
            warn("POSSESSION_CONTEXT_UNKNOWN", "possession observation is null", sample_index)
        else:
            possession_value = _as_mapping(possession, "canonical possession")
            if set(possession_value) != {"group", "player_id"}:
                reject(
                    "INVALID_SAMPLE_SCHEMA",
                    "possession fields differ from the measurement state",
                    sample_index,
                )
            else:
                group = possession_value.get("group")
                possession_player = possession_value.get("player_id")
                if group == "home team":
                    possession_home += 1
                elif group == "away team":
                    possession_away += 1
                elif group is None:
                    possession_unknown += 1
                    warn("POSSESSION_CONTEXT_UNKNOWN", "possession group is null", sample_index)
                else:
                    reject(
                        "INVALID_SAMPLE_SCHEMA",
                        "possession group is not home team, away team, or null",
                        sample_index,
                    )
                possession_categories[offset] = group
                if possession_player is not None:
                    player_id = _int(possession_player, "possession player_id", minimum=1)
                    if player_id not in seen_player_ids:
                        warn(
                            "POSSESSION_PLAYER_UNOBSERVED",
                            "possession player is absent from this sample",
                            sample_index,
                        )

    expected_intervals = max(0, expected_count - 1)
    for offset in range(1, expected_count):
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
            reject("PERIOD_BOUNDARY_CROSSED", "window support crosses a match period", issue_index)
            continue
        if before_period is not None and before_period == current_period:
            identity_comparisons += 1
        if before_index is not None and current_index is not None:
            if current_index == before_index:
                reject("DUPLICATE_SAMPLE", "canonical sample index is repeated", issue_index)
            elif current_index < before_index:
                reject("NONMONOTONIC_SAMPLE_ORDER", "canonical sample order decreases", issue_index)
            elif current_index != before_index + sample_index_step:
                reject("TEMPORAL_GAP", "canonical sample indices are not consecutive", issue_index)
        if (
            before_frame is not None
            and current_frame is not None
            and current_frame - before_frame != source_frame_step
        ):
            if current_frame == before_frame:
                reject("DUPLICATE_SAMPLE", "source frame is repeated", issue_index)
            elif current_frame < before_frame:
                reject("NONMONOTONIC_SAMPLE_ORDER", "source frame order decreases", issue_index)
            else:
                reject(
                    "TEMPORAL_GAP", "source frames are not consecutive 5 Hz samples", issue_index
                )
        if before_period == current_period and before_time is not None and current_time is not None:
            if current_time - before_time != timestamp_step:
                reject(
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
            active_transitions += 1
            changed_active_ids.update(before_active ^ current_active)
            warn(
                "IDENTITY_TRANSITION_EXPOSURE",
                "active player IDs change within support",
                issue_index,
            )
        before_observed = set(player_positions[offset - 1])
        current_observed = set(player_positions[offset])
        if before_observed != current_observed:
            observed_identity_changes += 1

        if (
            before_index is not None
            and current_index == before_index + sample_index_step
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
                if (
                    math.dist(
                        player_positions[offset - 1][player_id], player_positions[offset][player_id]
                    )
                    / elapsed_seconds
                    > player_speed_limit
                ):
                    player_outliers += 1
                    warn(
                        "PLAYER_DISPLACEMENT_OUTLIER",
                        f"player_id {player_id} exceeds the advisory displacement speed",
                        issue_index,
                    )
            before_ball, current_ball = ball_positions[offset - 1], ball_positions[offset]
            if before_ball is not None and current_ball is not None:
                ball_displacement_pairs += 1
                if math.dist(before_ball, current_ball) / elapsed_seconds > ball_speed_limit:
                    ball_outliers += 1
                    warn(
                        "BALL_DISPLACEMENT_OUTLIER",
                        "ball exceeds the advisory displacement speed",
                        issue_index,
                    )

    phase_covered: int | None = None
    phase_denominator: int | None = None
    first_uncovered: int | None = None
    if (
        support_complete
        and all(frame is not None for frame in source_frames)
        and periods[0] is not None
        and all(period == periods[0] for period in periods)
        and cast(int, source_frames[-1]) >= cast(int, source_frames[0])
    ):
        span_start = cast(int, source_frames[0])
        span_end = cast(int, source_frames[-1]) + 1
        phase_denominator = span_end - span_start
        cursor = span_start
        covered = 0
        intervals = sorted(
            (
                max(int(phase["frame_start"]), span_start),
                min(int(phase["frame_end"]), span_end),
            )
            for phase in contract.phases
            if phase["period"] == periods[0]
            and int(phase["frame_start"]) < span_end
            and int(phase["frame_end"]) > span_start
        )
        for start, end in intervals:
            if end <= cursor:
                continue
            if start > cursor and first_uncovered is None:
                first_uncovered = cursor
            covered += end - max(start, cursor)
            cursor = max(cursor, end)
        if cursor < span_end and first_uncovered is None:
            first_uncovered = cursor
        phase_covered = covered
        if first_uncovered is not None:
            affected_index = next(
                (
                    sample_indexes[i]
                    for i, frame in enumerate(source_frames)
                    if frame == first_uncovered
                ),
                None,
            )
            reject(
                "PHASE_NOT_IN_PLAY_OR_UNKNOWN",
                f"source frame {first_uncovered} lacks positive in-play coverage",
                affected_index,
            )

    support_count = len(support)
    ball_fraction = valid_ball_positions / expected_count if support_span_available else None
    if support_count > HISTORY and ball_positions[HISTORY] is None:
        reject(
            "BALL_MISSING_AT_ORIGIN",
            "ball position at candidate origin is unavailable",
            sample_indexes[HISTORY],
        )
    if ball_fraction is not None and ball_fraction < minimum_ball_fraction:
        reject(
            "BALL_COVERAGE_BELOW_MINIMUM",
            f"valid ball fraction {ball_fraction:.6f} is below {minimum_ball_fraction:.6f}",
        )

    detection_denominator = detected_players + extrapolated_players
    player_completeness_known = (
        contract.roster_complete
        and support_complete
        and all(period is not None for period in periods)
    )
    player_completeness = (
        valid_active_player_positions / active_player_frames
        if player_completeness_known and active_player_frames
        else None
    )
    expected_active_frames = active_player_frames if player_completeness_known else None
    temporal_discontinuous = (
        any(
            item["code"]
            in {
                "DUPLICATE_SAMPLE",
                "NONMONOTONIC_SAMPLE_ORDER",
                "TEMPORAL_GAP",
                "TIMESTAMP_DISCONTINUITY",
                "TIMESTAMP_MISSING",
                "PERIOD_BOUNDARY_CROSSED",
            }
            for item in reasons
        )
        or support_count != expected_count
    )
    player_detection_stratum = (
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
        if not support_complete or valid_ball_positions == 0 or unknown_ball_positions > 0
        else "all_detected"
        if extrapolated_balls == 0
        else "all_false_flag"
        if detected_balls == 0
        else "mixed"
    )
    player_completeness_stratum = (
        "unknown"
        if player_completeness is None
        else "complete"
        if player_completeness == 1.0
        else "none"
        if player_completeness == 0.0
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
        "player_detection_exposure": player_detection_stratum,
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
            if not contract.roster_complete or not support_complete
            else "exposed"
            if active_transitions
            else "none_observed"
        ),
        "source_quality_uncertainty": "unknown_per_observation",
        "play_context": (
            "unknown"
            if phase_covered is None or phase_denominator is None
            else "uncovered_or_unknown"
            if phase_covered != phase_denominator
            else "all_in_play"
        ),
    }
    warn(
        "SOURCE_QUALITY_UNKNOWN",
        "no per-observation player-identity confidence is supplied by SkillCorner",
    )

    known_flags = true_flags + false_flags
    cross_tab_slot_count = sum(sum(row.values()) for row in cross_tab.values())
    ball_quality: dict[str, object] = {
        "valid_position_count": valid_ball_positions,
        "denominator_sample_count": expected_count,
        "completeness_fraction": ball_fraction,
        "detected_position_count": detected_balls,
        "outside_pitch_count": outside_pitch_balls,
        "outside_pitch_fraction": outside_pitch_balls / valid_ball_positions
        if valid_ball_positions
        else None,
        "displacement_outlier_count": ball_outliers,
        "displacement_pair_denominator": ball_displacement_pairs,
        "displacement_outlier_fraction": ball_outliers / ball_displacement_pairs
        if ball_displacement_pairs
        else None,
        "expected_support_slot_count": expected_count,
        "position_coverage_fraction": ball_fraction,
        "flag_true_count": true_flags,
        "flag_false_count": false_flags,
        "flag_null_count": null_flags,
        "absent_object_count": absent_ball_objects,
        "missing_source_sample_count": missing_source_sample_count,
        "known_flag_count": known_flags,
        "known_flag_coverage_fraction": known_flags / expected_count
        if support_span_available
        else None,
        "detected_share_among_known_flags": true_flags / known_flags if known_flags else None,
        "flag_by_coordinate_state_counts": cross_tab,
        "finite_xy_by_flag": {
            "true": cross_tab["true"]["both_finite"],
            "false": cross_tab["false"]["both_finite"],
            "null": cross_tab["null"]["both_finite"],
        },
        "cross_tab_slot_count": cross_tab_slot_count,
        "cross_tab_reconciles_to_expected_support": cross_tab_slot_count == expected_count,
        "false_flag_position_count": extrapolated_balls,
    }
    possession_classified = sum(
        possession_categories.count(state)
        for state in ("home team", "away team", None, "missing", "invalid")
    )
    phase_uncovered = (
        phase_denominator - phase_covered
        if phase_denominator is not None and phase_covered is not None
        else None
    )
    quality: dict[str, object] = {
        "support_sample_count": support_count,
        "origin_offset": HISTORY,
        "player_observations": {
            "valid_position_count": valid_player_positions,
            "observed_record_count": observed_player_records,
            "expected_active_player_frames": expected_active_frames,
            "active_position_count": valid_active_player_positions
            if player_completeness_known
            else None,
            "completeness_fraction": player_completeness,
            "missing_active_records": missing_active_records if player_completeness_known else None,
            "missing_active_record_fraction": missing_active_records / expected_active_frames
            if expected_active_frames
            else None,
            "unknown_roster_samples": unknown_roster_samples,
            "null_coordinate_records": null_player_positions,
            "null_coordinate_fraction": null_player_positions / observed_player_records
            if observed_player_records
            else None,
            "detected_position_count": detected_players,
            "extrapolated_position_count": extrapolated_players,
            "detection_denominator": detection_denominator,
            "extrapolation_fraction": extrapolated_players / detection_denominator
            if detection_denominator
            else None,
            "outside_pitch_count": outside_pitch_players,
            "outside_pitch_fraction": outside_pitch_players / detection_denominator
            if detection_denominator
            else None,
            "displacement_outlier_count": player_outliers,
            "displacement_pair_denominator": player_displacement_pairs,
            "displacement_outlier_fraction": player_outliers / player_displacement_pairs
            if player_displacement_pairs
            else None,
        },
        "ball_observations": ball_quality,
        "temporal": {
            "expected_intervals": expected_intervals,
            "observed_intervals": max(0, support_count - 1),
            "continuous_intervals": continuous_intervals,
            "continuity_fraction": continuous_intervals / expected_intervals
            if support_complete and expected_intervals
            else None,
            "observed_identity_change_intervals": observed_identity_changes,
            "identity_comparison_intervals": identity_comparisons,
            "observed_identity_change_fraction": observed_identity_changes / identity_comparisons
            if identity_comparisons
            else None,
            "active_roster_transition_intervals": active_transitions
            if contract.roster_complete
            else None,
            "active_roster_transition_fraction": active_transitions / expected_intervals
            if contract.roster_complete and support_complete and expected_intervals
            else None,
            "changed_active_player_ids": len(changed_active_ids)
            if contract.roster_complete
            else None,
        },
        "play_context": {
            "phase_covered_source_frames": phase_covered,
            "phase_coverage_denominator_source_frames": phase_denominator,
            "uncovered_source_frames": phase_uncovered,
            "phase_coverage_fraction": phase_covered / phase_denominator
            if phase_covered is not None and phase_denominator
            else None,
            "possession_home_samples": possession_home,
            "possession_away_samples": possession_away,
            "possession_unknown_samples": possession_unknown,
            "possession_denominator_samples": support_count,
            "possession_home_fraction": possession_home / support_count if support_count else None,
            "possession_away_fraction": possession_away / support_count if support_count else None,
            "possession_unknown_fraction": possession_unknown / support_count
            if support_count
            else None,
            "possession_support_span_available": support_span_available,
            "possession_classified_samples": possession_classified,
            "possession_counts_reconcile_to_expected_support": possession_classified
            == expected_count,
            "possession_invalid_samples": possession_categories.count("invalid"),
            "possession_invalid_fraction": possession_categories.count("invalid") / expected_count
            if support_span_available
            else None,
            "possession_missing_samples": possession_categories.count("missing"),
            "possession_missing_fraction": possession_categories.count("missing") / expected_count
            if support_span_available
            else None,
        },
        "strata": strata,
    }
    diagnostic: dict[str, object] = {
        "candidate_rules_pass": not reasons,
        "data_state_hash": MEASUREMENT_HASH,
        "data_state_id": "skillcorner_5hz_v2",
        "data_state_version": "2.0.0",
        "exclusion_reasons": _sorted_issues(reasons),
        "policy_hash": ELIGIBILITY_HASH,
        "policy_id": "skillcorner_window_v2",
        "policy_version": "2.0.0",
        "quality": quality,
        "source_release_hash": SOURCE_RELEASE_HASH,
        "source_release_id": cast(str, authorities.source["source_release_id"]),
        "status": "UNQUALIFIED",
        "warnings": _sorted_issues(warnings),
    }
    return diagnostic


class ArtifactWriter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.stream: BinaryIO = path.open("wb")
        self.digest = hashlib.sha256()

    def write(self, value: bytes) -> None:
        self.stream.write(value)
        self.digest.update(value)

    def close(self) -> None:
        self.stream.flush()
        self.stream.close()

    @property
    def sha256(self) -> str:
        return self.digest.hexdigest()


def _hash_stream(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _count_issue_codes(issues: Sequence[dict[str, object]], totals: Counter[str]) -> None:
    for code in {cast(str, item["code"]) for item in issues}:
        totals[code] += 1


def _sample_pair(player: Mapping[str, object] | None) -> tuple[float, float] | None:
    if player is None or player.get("x_m") is None or player.get("y_m") is None:
        return None
    return cast(float, player["x_m"]), cast(float, player["y_m"])


def _player_lookup(sample: Mapping[str, object]) -> dict[int, dict[str, object]]:
    values = _as_sequence(sample.get("players"), "canonical sample players")
    return {
        cast(int, player["player_id"]): player
        for player in (_as_mapping(value, "canonical player") for value in values)
    }


def _truth_rows(panel: Sequence[Sequence[tuple[float, float] | None]]) -> list[list[object]]:
    return [
        [None if pair is None else [float(pair[0]).hex(), float(pair[1]).hex()] for pair in row]
        for row in panel
    ]


def _truth_digest(
    panel: Sequence[Sequence[tuple[float, float] | None]], representation: str
) -> str:
    return value_sha256(
        {
            "schema_id": "fpdbench.prospective-truth-panel",
            "schema_version": "1.1.0",
            "target_representation": representation,
            "samples": _truth_rows(panel),
        }
    )


def _mask_digest(panel: Sequence[Sequence[tuple[float, float] | None]]) -> str:
    return value_sha256(
        {
            "schema_id": "fpdbench.prospective-truth-mask",
            "schema_version": "1.0.0",
            "samples": [[pair is not None for pair in row] for row in panel],
        }
    )


def _scene_truth(
    support: Sequence[dict[str, object]],
    side: str,
) -> tuple[dict[str, object], dict[str, object], bool]:
    origin = support[HISTORY]
    origin_players = _player_lookup(origin)
    targets = [
        (player_id, pair)
        for player_id, player in sorted(origin_players.items())
        if player["group"] == side and (pair := _sample_pair(player)) is not None
    ]
    absolute: list[list[tuple[float, float] | None]] = []
    displacement: list[list[tuple[float, float] | None]] = []
    for sample in support[HISTORY + 1 :]:
        current_players = _player_lookup(sample)
        row = [_sample_pair(current_players.get(player_id)) for player_id, _ in targets]
        absolute.append(row)
        displacement.append(
            [
                None if pair is None else (pair[0] - anchor[0], pair[1] - anchor[1])
                for pair, (_, anchor) in zip(row, targets, strict=True)
            ]
        )
    truth_mask = _mask_digest(absolute)
    membership: dict[str, object] = {
        "scene_id": side,
        "player_ids": [str(player_id) for player_id, _ in targets],
        "absolute_xy_truth_sha256": _truth_digest(absolute, "absolute_xy"),
        "displacement_truth_sha256": _truth_digest(displacement, "origin_relative_displacement"),
        "truth_mask_sha256": truth_mask,
    }
    final_row = absolute[-1]
    scoreable = any(pair is not None for pair in final_row)
    truth: dict[str, object] = {
        **membership,
        "origin_xy": [anchor for _, anchor in targets],
        "absolute_xy": absolute,
        "origin_relative_displacement": displacement,
        "truth_mask": [[pair is not None for pair in row] for row in absolute],
        "scoreable": scoreable,
        "unscoreable_reason": None if scoreable else "NO_FINAL_TARGET",
    }
    return membership, truth, scoreable


def _window_id(match_id: str, origin_sample_id: str) -> str:
    return value_sha256(
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


def _origin_grid(contract: MatchContract) -> Iterator[Origin]:
    for period, (start, end) in sorted(contract.period_bounds.items()):
        first = start + start % 2
        for frame in range(first, end, 2):
            yield Origin(
                contract.match_id,
                contract.role,
                period,
                frame,
                f"period_{period}/sample_{frame // 2}",
            )


def _support_from_recent(
    recent: Sequence[dict[str, object]],
    origin_frame: int,
) -> tuple[dict[str, object] | None, ...]:
    indexed = {cast(int, sample["source_frame"]): sample for sample in recent}
    return tuple(indexed.get(origin_frame + offset * 2) for offset in range(-HISTORY, FUTURE + 1))


def _write_line(writer: ArtifactWriter, row: object) -> None:
    writer.write(canonical_bytes(row) + b"\n")


def _write_array_object(
    stream: BinaryIO,
    digest: Any,
    values: Mapping[str, object],
    membership_spool: Path,
) -> str:
    """Stream a canonical manifest, splicing the already streamed matches array."""
    manifest_sha = hashlib.sha256()
    manifest_sha.update(b"{")
    digest_started = False
    base_keys = [key for key in sorted(values) if key != "manifest_sha256"]
    for key in base_keys:
        if digest_started:
            manifest_sha.update(b",")
        digest_started = True
        member = canonical_bytes(key) + b":"
        manifest_sha.update(member)
        if key == "matches":
            with membership_spool.open("rb") as matches:
                while block := matches.read(1024 * 1024):
                    manifest_sha.update(block)
        else:
            manifest_sha.update(canonical_bytes(values[key]))
    manifest_sha.update(b"}")
    manifest_sha256 = manifest_sha.hexdigest()

    stream.write(b"{")
    digest.update(b"{")
    for index, key in enumerate(sorted(values)):
        if index:
            stream.write(b",")
            digest.update(b",")
        member = canonical_bytes(key) + b":"
        stream.write(member)
        digest.update(member)
        if key == "matches":
            with membership_spool.open("rb") as matches:
                while block := matches.read(1024 * 1024):
                    stream.write(block)
                    digest.update(block)
        elif key == "manifest_sha256":
            encoded = canonical_bytes(manifest_sha256)
            stream.write(encoded)
            digest.update(encoded)
        else:
            encoded = canonical_bytes(values[key])
            stream.write(encoded)
            digest.update(encoded)
    stream.write(b"}")
    digest.update(b"}")
    return manifest_sha256


def _input_receipt_rows(
    authorities: Authorities,
    source_receipts: Mapping[str, SourceReceipt],
) -> list[dict[str, object]]:
    return [source_receipts[match_id].to_wire() for _, match_id in authorities.roles]


def _base_receipt(
    status: str,
    producer_identity: Mapping[str, object],
    input_receipts: list[dict[str, object]],
    drift_scan: Mapping[str, object],
) -> dict[str, object]:
    return {
        "schema_id": "fpdbench.streaming-population-producer-receipt",
        "schema_version": "1.0.0",
        "status": status,
        "worker_version": PRODUCER_VERSION,
        "worker_package_identity": dict(producer_identity),
        "authority_bindings": {
            "source_release_hash": SOURCE_RELEASE_HASH,
            "source_population_hash": SOURCE_POPULATION_HASH,
            "measurement_state_hash": MEASUREMENT_HASH,
            "eligibility_policy_hash": ELIGIBILITY_HASH,
            "protocol_sha256": PROTOCOL_HASH,
            "plan_sha256": PLAN_HASH,
        },
        "source_byte_qualified": False,
        "independent_verification": "NOT_PERFORMED",
        "storage_boundary": {
            "trust": "SYNTHETIC_ONLY_NOT_TRUSTED_FOR_PROTECTED_DATA",
        },
        "input_receipts": input_receipts,
        "drift_scan": dict(drift_scan),
    }


def _emit_manifest(
    path: Path,
    values: dict[str, object],
    matches_spool: Path,
) -> tuple[str, str]:
    digest = hashlib.sha256()
    with path.open("wb") as stream:
        manifest_hash = _write_array_object(stream, digest, values, matches_spool)
    return manifest_hash, digest.hexdigest()


def _write_json_file(path: Path, value: object) -> str:
    payload = canonical_bytes(value)
    with path.open("wb") as stream:
        stream.write(payload)
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class ExpectedPopulation:
    files: dict[str, Path]
    hashes: dict[str, str]
    receipt: dict[str, object]
    counts: tuple[dict[str, object], ...]
    eligible_window_count: int
    candidate_window_count: int
    diagnostic_origin_count: int
    complete: bool
    membership_records: Path
    manifest_values: dict[str, object] | None


def _events(
    samples: Iterator[dict[str, object]],
    contract: MatchContract,
) -> Iterator[tuple[Origin, tuple[dict[str, object] | None, ...]]]:
    recent: deque[dict[str, object]] = deque(maxlen=SLOTS)
    origins = iter(_origin_grid(contract))
    origin = next(origins, None)
    for sample in samples:
        recent.append(sample)
        current_frame = cast(int, sample["source_frame"])
        while origin is not None and origin.source_frame + FUTURE * 2 <= current_frame:
            yield origin, _support_from_recent(recent, origin.source_frame)
            origin = next(origins, None)
    while origin is not None:
        yield origin, _support_from_recent(recent, origin.source_frame)
        origin = next(origins, None)


def _expected_manifest_values(
    candidate_window_count: int,
    eligible_window_count: int,
    origin_hash: str,
    membership_hash: str,
) -> dict[str, object]:
    return {
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
        "candidate_window_count": candidate_window_count,
        "eligible_window_count": eligible_window_count,
        "candidate_origin_population_sha256": origin_hash,
        "manifest_sha256": "",
        "matches": None,
        "membership_sha256": membership_hash,
    }


def _build_expected_population(
    input_root: Path,
    contracts: Mapping[str, MatchContract],
    authorities: Authorities,
    source_receipts: Mapping[str, SourceReceipt],
    input_snapshots: Mapping[str, MatchInputSnapshots],
    drift_scan: Mapping[str, object],
    producer_identity: Mapping[str, object],
    expected_root: Path,
) -> ExpectedPopulation:
    expected_root.mkdir(mode=0o700)
    candidates = ArtifactWriter(expected_root / "candidates.jsonl")
    diagnostics = ArtifactWriter(expected_root / "diagnostic-census.jsonl")
    truth = ArtifactWriter(expected_root / "truth.jsonl")
    match_spool_path = expected_root / ".matches.partial"
    membership_records_path = expected_root / "membership-records.jsonl"
    matches_digest = hashlib.sha256()
    membership_records = membership_records_path.open("wb")
    candidate_origins = CanonicalArrayDigest()
    diagnostic_origins = CanonicalArrayDigest()
    global_candidate_count = 0
    global_eligible_count = 0
    diagnostic_count = 0
    match_counts: list[dict[str, object]] = []

    with match_spool_path.open("wb") as matches:
        matches.write(b"[")
        matches_digest.update(b"[")
        for match_offset, (role, match_id) in enumerate(authorities.roles):
            contract = contracts[match_id]
            membership_records.write(
                canonical_bytes({"kind": "match", "match_id": match_id, "role": role}) + b"\n"
            )
            if match_offset:
                matches.write(b",")
                matches_digest.update(b",")
            matches.write(b'{"match_id":')
            matches_digest.update(b'{"match_id":')
            encoded_match_id = canonical_bytes(match_id)
            matches.write(encoded_match_id)
            matches_digest.update(encoded_match_id)
            matches.write(b',"role":')
            matches_digest.update(b',"role":')
            encoded_role = canonical_bytes(role)
            matches.write(encoded_role)
            matches_digest.update(encoded_role)
            matches.write(b',"windows":[')
            matches_digest.update(b',"windows":[')

            match_candidate_origins = CanonicalArrayDigest()
            match_diagnostic_origins = CanonicalArrayDigest()
            candidate_count = diagnostic_origin_count = 0
            eligible_count = scoreable_scenes = scoreable_windows = 0
            candidate_exclusions: Counter[str] = Counter()
            candidate_warnings: Counter[str] = Counter()
            diagnostic_exclusions: Counter[str] = Counter()
            diagnostic_warnings: Counter[str] = Counter()
            first_window = True
            second_pass_stats: dict[str, object] = {}
            tracking_snapshot = input_snapshots[match_id].tracking
            if tracking_snapshot is None:
                raise InputSnapshotChanged(f"tracking snapshot missing for match {match_id}")

            sample_iter = _read_tracking(
                input_root / match_id / "tracking.jsonl",
                contract,
                authorities,
                second_pass_stats,
                expected_snapshot=tracking_snapshot,
            )
            for origin, support in _events(sample_iter, contract):
                identity = origin.identity
                diagnostic_origins.append(identity)
                match_diagnostic_origins.append(identity)
                diagnostic_origin_count += 1
                diagnostic_count += 1
                diagnostic_value = _diagnose_window(support, contract, authorities)
                diagnostic_hash = value_sha256(diagnostic_value)
                row: dict[str, object] = {
                    **identity,
                    "diagnostic": diagnostic_value,
                    "eligibility_result_sha256": diagnostic_hash,
                }
                _write_line(diagnostics, row)
                _count_issue_codes(
                    cast(list[dict[str, object]], diagnostic_value["exclusion_reasons"]),
                    diagnostic_exclusions,
                )
                _count_issue_codes(
                    cast(list[dict[str, object]], diagnostic_value["warnings"]),
                    diagnostic_warnings,
                )

                complete_support = all(sample is not None for sample in support)
                if complete_support:
                    candidate_origins.append(identity)
                    match_candidate_origins.append(identity)
                    candidate_count += 1
                    global_candidate_count += 1
                    _write_line(candidates, row)
                    _count_issue_codes(
                        cast(list[dict[str, object]], diagnostic_value["exclusion_reasons"]),
                        candidate_exclusions,
                    )
                    _count_issue_codes(
                        cast(list[dict[str, object]], diagnostic_value["warnings"]),
                        candidate_warnings,
                    )

                if complete_support and diagnostic_value["candidate_rules_pass"]:
                    complete_support_samples = cast(tuple[dict[str, object], ...], support)
                    window_id = _window_id(match_id, origin.sample_id)
                    scenes: list[dict[str, object]] = []
                    window_scoreable = False
                    for side in ("home", "away"):
                        scene_membership, scene_truth, scoreable = _scene_truth(
                            complete_support_samples,
                            side,
                        )
                        scenes.append(scene_membership)
                        truth_row = {
                            **identity,
                            "window_id": window_id,
                            **scene_truth,
                        }
                        _write_line(truth, truth_row)
                        scoreable_scenes += int(scoreable)
                        window_scoreable = window_scoreable or scoreable
                    window = {
                        "window_id": window_id,
                        "origin_sample_id": origin.sample_id,
                        "eligibility_result_sha256": diagnostic_hash,
                        "scenes": scenes,
                    }
                    if not first_window:
                        matches.write(b",")
                        matches_digest.update(b",")
                    first_window = False
                    encoded_window = canonical_bytes(window)
                    matches.write(encoded_window)
                    matches_digest.update(encoded_window)
                    membership_records.write(
                        canonical_bytes(
                            {
                                "kind": "window",
                                "match_id": match_id,
                                "role": role,
                                "origin_sample_id": origin.sample_id,
                                "window": window,
                            }
                        )
                        + b"\n"
                    )
                    eligible_count += 1
                    global_eligible_count += 1
                    scoreable_windows += int(window_scoreable)

            if (
                cast(int, second_pass_stats.get("source_frame_count", -1))
                != source_receipts[match_id].source_frame_count
                or cast(int, second_pass_stats.get("retained_sample_count", -1))
                != source_receipts[match_id].retained_sample_count
                or second_pass_stats.get("raw_sha256") != source_receipts[match_id].tracking_sha256
                or second_pass_stats.get("retained_samples_sha256")
                != source_receipts[match_id].retained_samples_sha256
                or second_pass_stats.get("file_snapshot") != tracking_snapshot
            ):
                raise InputSnapshotChanged(f"tracking input changed between passes for {match_id}")

            matches.write(b"]}")
            matches_digest.update(b"]}")
            match_counts.append(
                {
                    "role": role,
                    "match_id": match_id,
                    "candidate_origin_population_sha256": match_candidate_origins.hexdigest(),
                    "candidate_window_count": candidate_count,
                    "eligible_window_count": eligible_count,
                    "excluded_window_count": candidate_count - eligible_count,
                    "diagnostic_origin_count": diagnostic_origin_count,
                    "diagnostic_origin_census_sha256": match_diagnostic_origins.hexdigest(),
                    "diagnostic_excluded_window_count": diagnostic_origin_count - eligible_count,
                    "directed_scene_count": eligible_count * 2,
                    "scoreable_scene_count": scoreable_scenes,
                    "scoreable_window_count": scoreable_windows,
                    "exclusion_window_counts": dict(sorted(candidate_exclusions.items())),
                    "warning_window_counts": dict(sorted(candidate_warnings.items())),
                    "diagnostic_exclusion_window_counts": dict(
                        sorted(diagnostic_exclusions.items())
                    ),
                    "diagnostic_warning_window_counts": dict(sorted(diagnostic_warnings.items())),
                }
            )
            membership_records.write(
                canonical_bytes({"kind": "end_match", "match_id": match_id, "role": role}) + b"\n"
            )
        matches.write(b"]")
        matches_digest.update(b"]")
    membership_records.close()
    candidates.close()
    diagnostics.close()
    truth.close()

    files = {
        "candidates.jsonl": expected_root / "candidates.jsonl",
        "diagnostic-census.jsonl": expected_root / "diagnostic-census.jsonl",
    }
    hashes = {
        "candidates.jsonl": _hash_stream(files["candidates.jsonl"]),
        "diagnostic-census.jsonl": _hash_stream(files["diagnostic-census.jsonl"]),
    }
    complete_population = all(
        cast(int, count["scoreable_window_count"]) > 0 for count in match_counts
    )
    input_receipt_rows = _input_receipt_rows(authorities, source_receipts)

    if complete_population:
        manifest_values = _expected_manifest_values(
            global_candidate_count,
            global_eligible_count,
            candidate_origins.hexdigest(),
            matches_digest.hexdigest(),
        )
        manifest_path = expected_root / "manifest.json"
        manifest_hash, manifest_file_hash = _emit_manifest(
            manifest_path,
            manifest_values,
            match_spool_path,
        )
        manifest_values["manifest_sha256"] = manifest_hash
        truth_path = expected_root / "truth.jsonl"
        truth_hash = _hash_stream(truth_path)
        files["manifest.json"] = manifest_path
        files["truth.jsonl"] = truth_path
        hashes["manifest.json"] = manifest_file_hash
        hashes["truth.jsonl"] = truth_hash
        receipt = _base_receipt(
            "UNQUALIFIED",
            producer_identity,
            input_receipt_rows,
            drift_scan,
        )
        receipt.update(
            match_counts=match_counts,
            candidate_origin_population_sha256=candidate_origins.hexdigest(),
            diagnostic_origin_census_count=diagnostic_count,
            diagnostic_origin_census_sha256=diagnostic_origins.hexdigest(),
            candidates_jsonl_sha256=hashes["candidates.jsonl"],
            diagnostic_census_jsonl_sha256=hashes["diagnostic-census.jsonl"],
            population_manifest_sha256=manifest_hash,
            manifest_json_sha256=manifest_file_hash,
            truth_jsonl_sha256=truth_hash,
        )
        files["receipt.json"] = expected_root / "receipt.json"
        _write_receipt_expected(files["receipt.json"], receipt)
    else:
        manifest_values = None
        (expected_root / "truth.jsonl").unlink(missing_ok=True)
        match_spool_path.unlink(missing_ok=True)
        membership_records_path.unlink(missing_ok=True)
        receipt = _base_receipt(
            "INCOMPLETE",
            producer_identity,
            input_receipt_rows,
            drift_scan,
        )
        receipt.update(
            match_counts=match_counts,
            candidate_origin_population_sha256=candidate_origins.hexdigest(),
            diagnostic_origin_census_count=diagnostic_count,
            diagnostic_origin_census_sha256=diagnostic_origins.hexdigest(),
            candidates_jsonl_sha256=hashes["candidates.jsonl"],
            diagnostic_census_jsonl_sha256=hashes["diagnostic-census.jsonl"],
        )
        files[".incomplete"] = expected_root / ".incomplete"
        _write_json_file(
            files[".incomplete"],
            {
                "schema_id": "fpdbench.streaming-population-output-state",
                "schema_version": "1.0.0",
                "status": "INCOMPLETE",
                "worker_version": PRODUCER_VERSION,
            },
        )
        files["receipt.json"] = expected_root / "receipt.json"
        _write_receipt_expected(files["receipt.json"], receipt)

    match_spool_path.unlink(missing_ok=True)
    if ".incomplete" in files:
        hashes[".incomplete"] = _hash_stream(files[".incomplete"])
    return ExpectedPopulation(
        files=files,
        hashes=hashes,
        receipt=receipt,
        counts=tuple(match_counts),
        eligible_window_count=global_eligible_count,
        candidate_window_count=global_candidate_count,
        diagnostic_origin_count=diagnostic_count,
        complete=complete_population,
        membership_records=membership_records_path,
        manifest_values=manifest_values,
    )


def _write_receipt_expected(path: Path, receipt: dict[str, object]) -> str:
    receipt["receipt_sha256"] = value_sha256(receipt)
    payload = canonical_bytes(receipt)
    with path.open("wb") as stream:
        stream.write(payload)
    return hashlib.sha256(payload).hexdigest()


class _MembershipEventReader:
    def __init__(self, path: Path) -> None:
        self.stream = path.open("rb")
        self._pending: dict[str, object] | None = None

    def peek(self) -> dict[str, object] | None:
        if self._pending is None:
            line = self.stream.readline(MAX_MANIFEST_TOKEN_BYTES + 1)
            if not line:
                return None
            if len(line) > MAX_MANIFEST_TOKEN_BYTES:
                raise VerificationInputError("expected membership record exceeds the row limit")
            self._pending = _as_mapping(
                strict_json_bytes(line, "expected membership record"), "expected membership record"
            )
        return self._pending

    def pop(self) -> dict[str, object] | None:
        value = self.peek()
        self._pending = None
        return value

    def close(self) -> None:
        self.stream.close()


class _JsonStreamReader:
    """Decode one JSON value at a time while bounding the retained text buffer."""

    def __init__(self, path: Path) -> None:
        fd, _ = _open_regular_nofollow(path)
        self.stream: TextIO = os.fdopen(fd, "r", encoding="utf-8", errors="strict", newline="")
        self.buffer = ""
        self.position = 0
        self.eof = False
        self.decoder = json.JSONDecoder(
            object_pairs_hook=_json_object,
            parse_constant=lambda value: (_ for _ in ()).throw(
                VerificationInputError(f"nonfinite manifest number {value}")
            ),
        )

    def _fill(self) -> bool:
        if self.eof:
            return False
        if self.position:
            self.buffer = self.buffer[self.position :]
            self.position = 0
        chunk = self.stream.read(64 * 1024)
        if not chunk:
            self.eof = True
            return False
        self.buffer += chunk
        if len(self.buffer) > MAX_MANIFEST_TOKEN_BYTES and self.position == 0:
            raise VerificationInputError("manifest token exceeds the verifier's bounded token size")
        return True

    def _space(self) -> None:
        while True:
            while self.position < len(self.buffer) and self.buffer[self.position] in " \t\r\n":
                self.position += 1
            if self.position < len(self.buffer) or not self._fill():
                return

    def peek(self) -> str:
        self._space()
        if self.position >= len(self.buffer):
            raise VerificationInputError("manifest ended unexpectedly")
        return self.buffer[self.position]

    def expect(self, token: str) -> None:
        actual = self.peek()
        if actual != token:
            raise VerificationInputError(f"manifest expected {token!r}, found {actual!r}")
        self.position += 1

    def _decode_value(self) -> object:
        self._space()
        start = self.position
        while True:
            try:
                value, end = self.decoder.raw_decode(self.buffer, self.position)
                if end == len(self.buffer) and not self.eof:
                    if len(self.buffer) - start > MAX_MANIFEST_TOKEN_BYTES:
                        raise VerificationInputError(
                            "manifest value exceeds the bounded token size"
                        )
                    self._fill()
                    continue
                if end - start > MAX_MANIFEST_TOKEN_BYTES:
                    raise VerificationInputError("manifest value exceeds the bounded token size")
                self.position = end
                return value
            except json.JSONDecodeError as exc:
                if len(self.buffer) - start > MAX_MANIFEST_TOKEN_BYTES or not self._fill():
                    raise VerificationInputError(f"malformed manifest JSON: {exc}") from exc

    def string(self) -> str:
        value = self._decode_value()
        if not isinstance(value, str):
            raise VerificationInputError("manifest object key must be a string")
        return value

    def value(self) -> object:
        return self._decode_value()

    def finish(self) -> None:
        self._space()
        if self.position < len(self.buffer) or self._fill():
            self._space()
            if self.position < len(self.buffer):
                raise VerificationInputError("extra content follows the manifest object")

    def close(self) -> None:
        self.stream.close()


def _field_category(path: str, artifact: str) -> str:
    if artifact == "receipt.json":
        if path.startswith("/worker_package_identity"):
            return "PRODUCER_PROVENANCE_MISMATCH"
        if path.startswith("/match_counts"):
            return "RECEIPT_MATCH_COUNT_MISMATCH"
        if path.startswith("/input_receipts"):
            return "INPUT_RECEIPT_MISMATCH"
        if path.startswith("/authority_bindings"):
            return "RECEIPT_AUTHORITY_MISMATCH"
        if path.startswith("/drift_scan"):
            return "DRIFT_SCAN_RECEIPT_MISMATCH"
        return "RECEIPT_FIELD_MISMATCH"
    if artifact == "manifest.json":
        if path.endswith("/role") or path.endswith("/match_id"):
            return "MANIFEST_MATCH_IDENTITY_MISMATCH"
        if path.endswith("/truth_mask_sha256") or "/truth_mask" in path:
            return "MANIFEST_TRUTH_MASK_MISMATCH"
        if "/scenes/" in path or path.endswith("/scenes"):
            return "MANIFEST_SCENE_MEMBERSHIP_MISMATCH"
        if "/windows/" in path or path.endswith("/windows"):
            return "MANIFEST_WINDOW_MISMATCH"
        return "MANIFEST_FIELD_MISMATCH"
    return "JSON_FIELD_MISMATCH"


def _compare_values(
    expected: object,
    actual: object,
    path: str,
    artifact: str,
    identity: Mapping[str, object],
    mismatches: MismatchCollector,
) -> None:
    if isinstance(expected, dict) and isinstance(actual, dict):
        expected_map = cast(dict[str, object], expected)
        actual_map = cast(dict[str, object], actual)
        expected_keys: set[str] = set(expected_map)
        actual_keys: set[str] = set(actual_map)
        for key in sorted(expected_keys | actual_keys):
            child_path = f"{path}/{key}"
            if key not in expected_map:
                mismatches.add(
                    _field_category(child_path, artifact),
                    {**identity, "field": child_path},
                    None,
                    actual_map[key],
                )
            elif key not in actual_map:
                mismatches.add(
                    _field_category(child_path, artifact),
                    {**identity, "field": child_path},
                    expected_map[key],
                    None,
                )
            else:
                _compare_values(
                    expected_map[key],
                    actual_map[key],
                    child_path,
                    artifact,
                    identity,
                    mismatches,
                )
        return
    if isinstance(expected, list) and isinstance(actual, list):
        expected_list = cast(list[object], expected)
        actual_list = cast(list[object], actual)
        if len(expected_list) != len(actual_list):
            mismatches.add(
                _field_category(path, artifact),
                {**identity, "field": path},
                {"length": len(expected_list)},
                {"length": len(actual_list)},
            )
        for index, (expected_item, actual_item) in enumerate(
            zip(expected_list, actual_list, strict=False)
        ):
            _compare_values(
                expected_item, actual_item, f"{path}/{index}", artifact, identity, mismatches
            )
        return
    if expected != actual:
        expected_value = _normalize_json_value(cast(object, expected))
        actual_value = _normalize_json_value(actual)
        mismatches.add(
            _field_category(path, artifact),
            {**identity, "field": path},
            expected_value,
            actual_value,
        )


def _expected_membership_event(events: _MembershipEventReader) -> dict[str, object] | None:
    return events.pop()


def _compare_window_value(
    expected_event: Mapping[str, object],
    actual_window: object,
    match_id: str,
    role: str,
    mismatches: MismatchCollector,
) -> None:
    expected_window = expected_event.get("window")
    expected_window_object = _normalize_json_value(expected_window)
    actual_window_object = _normalize_json_value(actual_window)
    identity = {
        "match_id": match_id,
        "role": role,
        "origin_sample_id": expected_event.get("origin_sample_id"),
    }
    if not isinstance(expected_window, dict) or not isinstance(actual_window, dict):
        mismatches.add(
            "MANIFEST_WINDOW_MISMATCH",
            identity,
            expected_window_object,
            actual_window_object,
        )
        return
    expected_window_value = cast(dict[str, object], expected_window)
    actual_window_value = cast(dict[str, object], actual_window)
    actual_origin = actual_window_value.get("origin_sample_id")
    if actual_origin != expected_event.get("origin_sample_id"):
        identity["actual_origin_sample_id"] = actual_origin
        mismatches.add(
            "MANIFEST_WINDOW_ORDER_MISMATCH",
            identity,
            expected_event.get("origin_sample_id"),
            actual_origin,
        )
        return
    _compare_values(
        expected_window_value,
        actual_window_value,
        "/matches/windows",
        "manifest.json",
        identity,
        mismatches,
    )


def _parse_manifest_match(
    reader: _JsonStreamReader,
    events: _MembershipEventReader,
    match_index: int,
    mismatches: MismatchCollector,
) -> None:
    reader.expect("{")
    header = _expected_membership_event(events)
    if header is None or header.get("kind") != "match":
        mismatches.add(
            "MANIFEST_EXTRA_MATCH",
            {"artifact": "manifest.json", "match_index": match_index},
            None,
            {"match_index": match_index},
        )
        header = {"match_id": None, "role": None}
    expected_match_id = header.get("match_id")
    expected_role = header.get("role")
    actual_match_id: object = None
    actual_role: object = None
    seen: set[str] = set()
    if reader.peek() != "}":
        while True:
            key = reader.string()
            if key in seen:
                raise VerificationInputError("manifest match object repeats a member")
            seen.add(key)
            reader.expect(":")
            if key == "windows":
                reader.expect("[")
                actual_window_index = 0
                if reader.peek() != "]":
                    while True:
                        actual_window = reader.value()
                        next_event = events.peek()
                        if next_event is not None and next_event.get("kind") == "window":
                            popped = events.pop()
                            if popped is not None:
                                _compare_window_value(
                                    popped,
                                    actual_window,
                                    cast(str, expected_match_id),
                                    cast(str, expected_role),
                                    mismatches,
                                )
                        else:
                            actual_window_value = (
                                cast(dict[str, object], actual_window)
                                if isinstance(actual_window, dict)
                                else None
                            )
                            actual_origin = (
                                actual_window_value.get("origin_sample_id")
                                if actual_window_value is not None
                                else None
                            )
                            mismatches.add(
                                "MANIFEST_EXTRA_WINDOW",
                                {
                                    "artifact": "manifest.json",
                                    "match_id": actual_match_id or expected_match_id,
                                    "origin_sample_id": actual_origin,
                                    "window_index": actual_window_index,
                                },
                                None,
                                cast(object, actual_window),
                            )
                        actual_window_index += 1
                        if reader.peek() == ",":
                            reader.expect(",")
                            continue
                        break
                reader.expect("]")
            else:
                value = reader.value()
                if key == "match_id":
                    actual_match_id = value
                elif key == "role":
                    actual_role = value
                else:
                    mismatches.add(
                        "MANIFEST_MATCH_FIELD_MISMATCH",
                        {
                            "artifact": "manifest.json",
                            "match_id": expected_match_id,
                            "field": f"/matches/{key}",
                        },
                        None,
                        value,
                    )
            if reader.peek() == ",":
                reader.expect(",")
                continue
            break
    reader.expect("}")
    if actual_match_id != expected_match_id:
        mismatches.add(
            "MANIFEST_MATCH_IDENTITY_MISMATCH",
            {
                "artifact": "manifest.json",
                "match_id": expected_match_id,
                "actual_match_id": actual_match_id,
            },
            expected_match_id,
            actual_match_id,
        )
    if actual_role != expected_role:
        mismatches.add(
            "MANIFEST_MATCH_ROLE_MISMATCH",
            {"artifact": "manifest.json", "match_id": expected_match_id, "role": expected_role},
            expected_role,
            actual_role,
        )
    while True:
        event = events.peek()
        if event is None:
            break
        if event.get("kind") == "window" and event.get("match_id") == expected_match_id:
            missing = events.pop()
            if missing is not None:
                mismatches.add(
                    "MANIFEST_MISSING_WINDOW",
                    {
                        "artifact": "manifest.json",
                        "match_id": expected_match_id,
                        "origin_sample_id": missing.get("origin_sample_id"),
                    },
                    missing.get("window"),
                    None,
                )
            continue
        if event.get("kind") == "end_match" and event.get("match_id") == expected_match_id:
            events.pop()
        break


def _compare_manifest_structure(
    actual_path: Path,
    expected: ExpectedPopulation,
    mismatches: MismatchCollector,
) -> None:
    manifest_values = expected.manifest_values
    if manifest_values is None:
        return
    events = _MembershipEventReader(expected.membership_records)
    reader = _JsonStreamReader(actual_path)
    actual_static: dict[str, object] = {}
    actual_match_index = 0
    seen_top: set[str] = set()
    try:
        reader.expect("{")
        if reader.peek() != "}":
            while True:
                key = reader.string()
                if key in seen_top:
                    raise VerificationInputError("manifest repeats a top-level member")
                seen_top.add(key)
                reader.expect(":")
                if key == "matches":
                    reader.expect("[")
                    if reader.peek() != "]":
                        while True:
                            _parse_manifest_match(reader, events, actual_match_index, mismatches)
                            actual_match_index += 1
                            if reader.peek() == ",":
                                reader.expect(",")
                                continue
                            break
                    reader.expect("]")
                elif key in manifest_values and key != "matches":
                    actual_static[key] = reader.value()
                else:
                    value = reader.value()
                    mismatches.add(
                        "MANIFEST_EXTRA_FIELD",
                        {"artifact": "manifest.json", "field": f"/{key}"},
                        None,
                        value,
                    )
                if reader.peek() == ",":
                    reader.expect(",")
                    continue
                break
        reader.expect("}")
        reader.finish()
        if actual_match_index != 20:
            mismatches.add(
                "MANIFEST_MATCH_COUNT_MISMATCH",
                {"artifact": "manifest.json"},
                20,
                actual_match_index,
            )
        expected_static = {key: value for key, value in manifest_values.items() if key != "matches"}
        _compare_values(
            expected_static,
            actual_static,
            "",
            "manifest.json",
            {"artifact": "manifest.json"},
            mismatches,
        )
        while (event := events.pop()) is not None:
            if event.get("kind") == "window":
                identity = {
                    "artifact": "manifest.json",
                    "match_id": event.get("match_id"),
                    "origin_sample_id": event.get("origin_sample_id"),
                }
                mismatches.add("MANIFEST_MISSING_WINDOW", identity, event.get("window"), None)
            elif event.get("kind") == "match":
                mismatches.add(
                    "MANIFEST_MISSING_MATCH",
                    {
                        "artifact": "manifest.json",
                        "match_id": event.get("match_id"),
                        "role": event.get("role"),
                    },
                    event,
                    None,
                )
    except (VerificationInputError, UnicodeDecodeError) as exc:
        mismatches.add(
            "MALFORMED_MANIFEST",
            {"artifact": "manifest.json"},
            "strict canonical v2 population manifest",
            str(exc),
        )
    finally:
        events.close()
        reader.close()


def _record_identity(value: object, artifact: str, index: int) -> dict[str, object]:
    identity: dict[str, object] = {"artifact": artifact, "record_index": index}
    if isinstance(value, dict):
        record = cast(dict[str, object], value)
        for key in ("match_id", "origin_sample_id", "window_id", "scene_id"):
            if key in record:
                identity[key] = record[key]
    return identity


def _jsonl_category(artifact: str, expected: object, actual: object) -> str:
    if artifact == "truth.jsonl" and isinstance(expected, dict) and isinstance(actual, dict):
        expected_row = cast(dict[str, object], expected)
        actual_row = cast(dict[str, object], actual)
        if expected_row.get("truth_mask") != actual_row.get("truth_mask"):
            return "TRUTH_MASK_MISMATCH"
        if any(
            expected_row.get(key) != actual_row.get(key)
            for key in ("absolute_xy", "origin_relative_displacement", "origin_xy")
        ):
            return "PHYSICAL_TRUTH_MISMATCH"
        return "TRUTH_RECORD_MISMATCH"
    if artifact == "diagnostic-census.jsonl":
        return "ELIGIBILITY_DIAGNOSTIC_MISMATCH"
    if artifact == "candidates.jsonl":
        return "CANDIDATE_RECORD_MISMATCH"
    return "JSONL_RECORD_MISMATCH"


def _read_line_bounded(stream: BinaryIO, digest: Any) -> tuple[bytes, bool]:
    line = stream.readline(MAX_MANIFEST_TOKEN_BYTES + 1)
    digest.update(line)
    if len(line) <= MAX_MANIFEST_TOKEN_BYTES:
        return line, False
    while line and not line.endswith(b"\n"):
        line = stream.readline(MAX_MANIFEST_TOKEN_BYTES + 1)
        digest.update(line)
    return b"", True


def _compare_jsonl(
    expected_path: Path,
    actual_path: Path,
    artifact: str,
    mismatches: MismatchCollector,
) -> tuple[str, str]:
    expected_digest = hashlib.sha256()
    actual_digest = hashlib.sha256()
    actual_fd, _ = _open_regular_nofollow(actual_path)
    with expected_path.open("rb") as expected_stream, os.fdopen(actual_fd, "rb") as actual_stream:
        index = 0
        while True:
            expected_line, expected_large = _read_line_bounded(expected_stream, expected_digest)
            actual_line, actual_large = _read_line_bounded(actual_stream, actual_digest)
            if not expected_line and not actual_line and not expected_large and not actual_large:
                break
            expected_value: object | None = None
            actual_value: object | None = None
            expected_valid = bool(expected_line) and not expected_large
            actual_valid = bool(actual_line) and not actual_large
            if expected_valid:
                try:
                    expected_value = strict_json_bytes(
                        expected_line, f"expected {artifact} record", MAX_MANIFEST_TOKEN_BYTES
                    )
                except VerificationInputError as exc:
                    mismatches.add(
                        "VERIFIER_EXPECTED_ARTIFACT_INVALID",
                        {"artifact": artifact, "record_index": index},
                        "strict JSON record",
                        str(exc),
                        expected_sha256=hashlib.sha256(expected_line).hexdigest(),
                    )
            if actual_valid:
                try:
                    actual_value = strict_json_bytes(
                        actual_line, f"actual {artifact} record", MAX_MANIFEST_TOKEN_BYTES
                    )
                except VerificationInputError:
                    actual_valid = False
            expected_normalized: object = _normalize_json_value(expected_value)
            actual_normalized: object = _normalize_json_value(actual_value)
            if expected_large:
                mismatches.add(
                    "EXPECTED_RECORD_EXCEEDS_BOUND",
                    {"artifact": artifact, "record_index": index},
                    MAX_MANIFEST_TOKEN_BYTES,
                    len(expected_line),
                )
            elif actual_large:
                mismatches.add(
                    "ACTUAL_RECORD_EXCEEDS_BOUND",
                    {"artifact": artifact, "record_index": index},
                    len(expected_line),
                    MAX_MANIFEST_TOKEN_BYTES,
                )
            elif expected_line and not actual_line:
                mismatches.add(
                    "MISSING_RECORD",
                    _record_identity(expected_value, artifact, index),
                    expected_value,
                    None,
                    expected_sha256=hashlib.sha256(expected_line).hexdigest(),
                )
            elif actual_line and not expected_line:
                mismatches.add(
                    "EXTRA_RECORD",
                    _record_identity(actual_value, artifact, index),
                    None,
                    actual_value,
                    actual_sha256=hashlib.sha256(actual_line).hexdigest(),
                )
            elif expected_line != actual_line:
                if not actual_valid:
                    category = "MALFORMED_ARTIFACT_RECORD"
                else:
                    expected_record = (
                        cast(dict[str, object], expected_value)
                        if isinstance(expected_value, dict)
                        else None
                    )
                    actual_record = (
                        cast(dict[str, object], actual_value)
                        if isinstance(actual_value, dict)
                        else None
                    )
                    if (
                        expected_record is not None
                        and actual_record is not None
                        and any(
                            expected_record.get(key) != actual_record.get(key)
                            for key in ("match_id", "origin_sample_id", "scene_id")
                        )
                    ):
                        category = "RECORD_ORDER_OR_IDENTITY_MISMATCH"
                    else:
                        category = _jsonl_category(artifact, expected_normalized, actual_normalized)
                identity = _record_identity(expected_normalized, artifact, index)
                if isinstance(actual_normalized, dict):
                    actual_record = cast(dict[str, object], actual_normalized)
                    for key in ("match_id", "origin_sample_id", "scene_id"):
                        if key in actual_record:
                            identity[f"actual_{key}"] = actual_record[key]
                mismatches.add(
                    category,
                    identity,
                    expected_normalized if actual_valid else expected_line,
                    cast(object, actual_normalized) if actual_valid else actual_line,
                    expected_sha256=hashlib.sha256(expected_line).hexdigest(),
                    actual_sha256=hashlib.sha256(actual_line).hexdigest(),
                )
            index += 1
    return expected_digest.hexdigest(), actual_digest.hexdigest()


def _read_small_actual_receipt(path: Path) -> dict[str, object] | None:
    try:
        payload, _ = _read_bounded_document(path, "producer receipt")
        return _as_mapping(strict_json_bytes(payload, "producer receipt"), "producer receipt")
    except (OSError, VerificationInputError):
        return None


def _receipt_comparison_view(receipt: dict[str, object]) -> dict[str, object]:
    comparison = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    boundary = comparison.get("storage_boundary")
    if isinstance(boundary, dict):
        boundary_value = cast(dict[str, object], boundary)
        comparison["storage_boundary"] = {
            key: value for key, value in boundary_value.items() if key != "filesystem_type"
        }
    return comparison


def _compare_receipt(
    actual_path: Path,
    expected_value: dict[str, object],
    mismatches: MismatchCollector,
) -> None:
    actual_value = _read_small_actual_receipt(actual_path)
    if actual_value is None:
        mismatches.add(
            "MALFORMED_OR_MISSING_RECEIPT",
            {"artifact": "receipt.json"},
            "valid receipt matching independently checked fields",
            None,
        )
        return
    actual_self_hash = actual_value.get("receipt_sha256")
    actual_payload = {key: value for key, value in actual_value.items() if key != "receipt_sha256"}
    computed_self_hash = value_sha256(actual_payload)
    if actual_self_hash != computed_self_hash:
        mismatches.add(
            "RECEIPT_SELF_HASH_INVALID",
            {"artifact": "receipt.json", "field": "/receipt_sha256"},
            computed_self_hash,
            actual_self_hash,
        )
    _compare_values(
        _receipt_comparison_view(expected_value),
        _receipt_comparison_view(actual_value),
        "",
        "receipt.json",
        {"artifact": "receipt.json"},
        mismatches,
    )


def _compare_file_bytes(
    expected_path: Path,
    actual_path: Path,
    artifact: str,
    category: str,
    mismatches: MismatchCollector,
) -> tuple[str, str]:
    expected_digest = hashlib.sha256()
    actual_digest = hashlib.sha256()
    equal = True
    actual_fd, _ = _open_regular_nofollow(actual_path)
    with expected_path.open("rb") as left, os.fdopen(actual_fd, "rb") as right:
        while True:
            left_block = left.read(1024 * 1024)
            right_block = right.read(1024 * 1024)
            if left_block != right_block:
                equal = False
            if not left_block and not right_block:
                break
            expected_digest.update(left_block)
            actual_digest.update(right_block)
    expected_sha = expected_digest.hexdigest()
    actual_sha = actual_digest.hexdigest()
    if not equal:
        mismatches.add(
            category,
            {"artifact": artifact},
            expected_sha,
            actual_sha,
            expected_sha256=expected_sha,
            actual_sha256=actual_sha,
        )
    return expected_sha, actual_sha


def _compare_output_set(
    actual_root: Path,
    expected: ExpectedPopulation,
    mismatches: MismatchCollector,
) -> dict[str, str]:
    try:
        root_fd = _open_directory_nofollow(actual_root)
    except (OSError, VerificationInputError) as exc:
        mismatches.add(
            "OUTPUT_DIRECTORY_UNREADABLE",
            {"artifact": str(actual_root)},
            "readable directory",
            str(exc),
        )
        return {}
    try:
        actual_names: set[str] = set()
        actual_regular_names: set[str] = set()
        for name in os.listdir(root_fd):
            info = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode):
                mismatches.add(
                    "UNEXPECTED_OUTPUT_ENTRY_TYPE",
                    {"artifact": name},
                    "regular file",
                    stat.filemode(info.st_mode),
                )
            else:
                actual_regular_names.add(name)
            actual_names.add(name)
    except OSError as exc:
        mismatches.add(
            "OUTPUT_DIRECTORY_UNREADABLE",
            {"artifact": str(actual_root)},
            "readable directory",
            str(exc),
        )
        return {}
    finally:
        os.close(root_fd)
    expected_names = set(expected.files)
    for missing in sorted(expected_names - actual_regular_names):
        mismatches.add("MISSING_ARTIFACT", {"artifact": missing}, "present", None)
    for extra in sorted(actual_names - expected_names):
        mismatches.add("UNEXPECTED_ARTIFACT", {"artifact": extra}, None, "present")

    actual_hashes: dict[str, str] = {}
    for name in sorted(expected_names & actual_regular_names):
        expected_path = expected.files[name]
        actual_path = actual_root / name
        try:
            if name in {"candidates.jsonl", "diagnostic-census.jsonl", "truth.jsonl"}:
                expected_sha, actual_sha = _compare_jsonl(
                    expected_path,
                    actual_path,
                    name,
                    mismatches,
                )
                actual_hashes[name] = actual_sha
                if expected_sha != actual_sha:
                    mismatches.add(
                        "ARTIFACT_DIGEST_MISMATCH",
                        {"artifact": name},
                        expected_sha,
                        actual_sha,
                        expected_sha256=expected_sha,
                        actual_sha256=actual_sha,
                    )
            elif name == "receipt.json":
                _compare_receipt(actual_path, expected.receipt, mismatches)
                actual_hashes[name] = _hash_stream(actual_path)
            elif name == "manifest.json":
                _compare_manifest_structure(actual_path, expected, mismatches)
                expected_sha, actual_sha = _compare_file_bytes(
                    expected_path,
                    actual_path,
                    name,
                    "MANIFEST_BYTE_MISMATCH",
                    mismatches,
                )
                actual_hashes[name] = actual_sha
            else:
                expected_sha, actual_sha = _compare_file_bytes(
                    expected_path,
                    actual_path,
                    name,
                    "INCOMPLETE_MARKER_MISMATCH",
                    mismatches,
                )
                actual_hashes[name] = actual_sha
        except (OSError, VerificationInputError) as exc:
            mismatches.add("ARTIFACT_READ_ERROR", {"artifact": name}, "readable artifact", str(exc))
    return actual_hashes


def _receipt_verification_scope() -> dict[str, object]:
    return {
        "unverified_external_metadata": [
            {"artifact": "receipt.json", "field": "/storage_boundary/filesystem_type"}
        ],
        "receipt_byte_identity": "NOT_VERIFIED",
    }


def _empty_report(mismatches: MismatchCollector) -> dict[str, object]:
    return {
        "schema_id": "fpdbench.streaming-population-verification-report",
        "schema_version": "1.0.0",
        "verifier_version": VERIFIER_VERSION,
        "status": "INVALID_INPUT",
        "authority": "NON_AUTHORITATIVE_RECONCILIATION_ONLY",
        "qualification": "NOT_PERFORMED",
        "runtime_attestation": "NOT_PROVIDED",
        "runtime_gate": "BLOCKED",
        "membership_verification_started": False,
        "producer_package_identity_sha256": PRODUCER_IDENTITY_SHA256,
        **_receipt_verification_scope(),
        **mismatches.report_fields(),
    }


def _validate_report_destination(path: Path, protected_roots: tuple[Path, ...]) -> None:
    destinations = (path.absolute(), path.resolve())
    for root in protected_roots:
        if any(
            destination.is_relative_to(protected)
            for destination in destinations
            for protected in (root.absolute(), root.resolve())
        ):
            raise VerificationInputError("report destination must be outside all evidence trees")


def _write_report(path: Path, report: dict[str, object], protected_roots: tuple[Path, ...]) -> None:
    _validate_report_destination(path, protected_roots)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_bytes(report)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".verify-report-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _authority_pin_report(error: BaseException) -> dict[str, object]:
    collector = MismatchCollector()
    collector.add(
        "FROZEN_AUTHORITY_MISMATCH",
        {"artifact": "frozen-v2-authorities"},
        {
            "measurement_state_hash": MEASUREMENT_HASH,
            "eligibility_policy_hash": ELIGIBILITY_HASH,
            "protocol_sha256": PROTOCOL_HASH,
            "plan_sha256": PLAN_HASH,
        },
        str(error),
    )
    report = _empty_report(collector)
    report["status"] = "AUTHORITY_MISMATCH"
    return report


def _input_snapshot_report(
    mismatches: MismatchCollector,
    error: InputSnapshotChanged,
    *,
    membership_started: bool,
    drift_scan: Mapping[str, object] | None = None,
) -> dict[str, object]:
    mismatches.add(
        "INPUT_SNAPSHOT_MISMATCH",
        {"scope": "all-pinned-source-files"},
        "unchanged descriptor-backed file identities and SHA-256 digests",
        str(error),
    )
    report = _empty_report(mismatches)
    report.update(
        status="INPUT_SNAPSHOT_MISMATCH",
        producer_source_package_verified=True,
        membership_verification_started=membership_started,
    )
    if drift_scan is not None:
        report["global_drift_scan"] = dict(drift_scan)
    return report


def verify_population(
    input_root: Path,
    artifact_root: Path,
    producer_package_root: Path,
    report_path: Path,
) -> dict[str, object]:
    """Reconstruct and reconcile PR #25 outputs without importing its code."""
    protected_roots = (input_root, artifact_root, producer_package_root)
    _validate_report_destination(report_path, protected_roots)
    mismatches = MismatchCollector()
    try:
        authorities = load_authorities()
    except (OSError, VerificationInputError) as exc:
        report = _authority_pin_report(exc)
        _write_report(report_path, report, protected_roots)
        return report

    try:
        producer_identity = verify_producer_source_package(producer_package_root)
    except (OSError, VerificationInputError) as exc:
        mismatches.add(
            "PRODUCER_SOURCE_PACKAGE_MISMATCH",
            {"producer_commit": PRODUCER_COMMIT},
            PRODUCER_IDENTITY_SHA256,
            str(exc),
        )
        report = _empty_report(mismatches)
        report["status"] = "PRODUCER_PROVENANCE_MISMATCH"
        report["producer_source_package_verified"] = False
        _write_report(report_path, report, protected_roots)
        return report

    try:
        contracts, input_snapshots = load_input_contracts(input_root, authorities)
        source_receipts, drift_scan, drift_count = _global_drift_scan(
            contracts,
            input_snapshots,
            input_root,
            authorities,
        )
    except InputSnapshotChanged as exc:
        report = _input_snapshot_report(mismatches, exc, membership_started=False)
        _write_report(report_path, report, protected_roots)
        return report
    except (OSError, VerificationInputError) as exc:
        mismatches.add(
            "INVALID_SYNTHETIC_INPUT",
            {"input_root": str(input_root)},
            "complete, valid synthetic 20-match source tree",
            str(exc),
        )
        report = _empty_report(mismatches)
        report["status"] = "INVALID_INPUT"
        report["producer_source_package_verified"] = True
        _write_report(report_path, report, protected_roots)
        return report

    try:
        _validate_input_snapshots(
            input_root,
            authorities,
            input_snapshots,
            include_tracking=drift_count > 0,
        )
    except InputSnapshotChanged as exc:
        report = _input_snapshot_report(
            mismatches,
            exc,
            membership_started=False,
            drift_scan=drift_scan,
        )
        _write_report(report_path, report, protected_roots)
        return report

    if drift_count:
        mismatches.add(
            "GLOBAL_NULL_FLAG_FINITE_XY_DRIFT",
            {"scope": "all-retained-v2-samples"},
            0,
            drift_count,
        )
        report = _empty_report(mismatches)
        report.update(
            status="GLOBAL_DRIFT_STOP",
            producer_source_package_verified=True,
            drift_scan=drift_scan,
            membership_verification_started=False,
        )
        _write_report(report_path, report, protected_roots)
        return report

    with tempfile.TemporaryDirectory(prefix="fpdbench-streaming-verifier-") as temporary:
        try:
            expected = _build_expected_population(
                input_root,
                contracts,
                authorities,
                source_receipts,
                input_snapshots,
                drift_scan,
                producer_identity,
                Path(temporary) / "expected",
            )
        except InputSnapshotChanged as exc:
            report = _input_snapshot_report(
                mismatches,
                exc,
                membership_started=True,
                drift_scan=drift_scan,
            )
            _write_report(report_path, report, protected_roots)
            return report
        except (OSError, VerificationInputError, ValueError, TypeError) as exc:
            mismatches.add(
                "INDEPENDENT_DERIVATION_FAILED",
                {"scope": "synthetic-population"},
                "complete frozen v2 independent derivation",
                str(exc),
            )
            report = _empty_report(mismatches)
            report.update(
                status="DERIVATION_ERROR",
                producer_source_package_verified=True,
                drift_scan=drift_scan,
                membership_verification_started=True,
            )
            _write_report(report_path, report, protected_roots)
            return report

        actual_hashes = _compare_output_set(artifact_root, expected, mismatches)
        try:
            _validate_input_snapshots(
                input_root, authorities, input_snapshots, include_tracking=True
            )
        except InputSnapshotChanged as exc:
            report = _input_snapshot_report(
                mismatches,
                exc,
                membership_started=True,
                drift_scan=drift_scan,
            )
            _write_report(report_path, report, protected_roots)
            return report

    status = "RECONCILED_NON_AUTHORITATIVE" if mismatches.total == 0 else "MISMATCH"
    report = {
        "schema_id": "fpdbench.streaming-population-verification-report",
        "schema_version": "1.0.0",
        "verifier_version": VERIFIER_VERSION,
        "producer_commit": PRODUCER_COMMIT,
        "producer_package_identity_sha256": PRODUCER_IDENTITY_SHA256,
        "producer_source_package_verified": True,
        "producer_runtime_attestation": "NOT_PROVIDED",
        "runtime_gate": "BLOCKED",
        "status": status,
        "authority": "NON_AUTHORITATIVE_RECONCILIATION_ONLY",
        "qualification": "NOT_PERFORMED",
        "population_status": "UNQUALIFIED",
        "membership_verification_started": True,
        "global_drift_scan": drift_scan,
        "candidate_window_count": expected.candidate_window_count,
        "eligible_window_count": expected.eligible_window_count,
        "diagnostic_origin_count": expected.diagnostic_origin_count,
        "expected_artifact_sha256": dict(sorted(expected.hashes.items())),
        "actual_artifact_sha256": dict(sorted(actual_hashes.items())),
        "storage_boundary": "SYNTHETIC_ONLY_NOT_TRUSTED_FOR_PROTECTED_DATA",
        **_receipt_verification_scope(),
        **mismatches.report_fields(),
    }
    _write_report(report_path, report, protected_roots)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Independently reconcile the synthetic PR #25 streaming population artifacts."
    )
    parser.add_argument("--input-root", required=True, type=Path)
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument("--producer-package-root", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)
    protected_roots = (args.input_root, args.artifact_root, args.producer_package_root)
    try:
        _validate_report_destination(args.report, protected_roots)
    except (OSError, VerificationInputError, ValueError) as exc:
        parser.error(str(exc))
    try:
        report = verify_population(
            args.input_root,
            args.artifact_root,
            args.producer_package_root,
            args.report,
        )
    except (OSError, VerificationInputError, ValueError, TypeError) as exc:
        collector = MismatchCollector()
        collector.add(
            "VERIFIER_RUNTIME_ERROR",
            {"scope": "worker"},
            "bounded non-authoritative verifier result",
            str(exc),
        )
        report = _empty_report(collector)
        report["status"] = "VERIFIER_ERROR"
        _write_report(args.report, report, protected_roots)
    print(
        json.dumps(
            {
                "status": report["status"],
                "qualification": report["qualification"],
                "mismatch_count": report["mismatch_count"],
                "report": str(args.report),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0 if report["status"] == "RECONCILED_NON_AUTHORITATIVE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
