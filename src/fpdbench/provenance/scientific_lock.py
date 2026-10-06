"""Deterministic scientific-lock hashing over result-bearing state only."""

import hashlib
import json
import re
from collections.abc import Mapping
from typing import cast

type JsonObject = dict[str, object]

LOCK_SCHEMA_VERSION = "fpdbench-scientific-lock.v1"
SCIENTIFIC_FIELDS = (
    "lock_schema_version",
    "benchmark_id",
    "benchmark_definition_hash",
    "data_release_id",
    "data_release_version",
    "data_manifest_hash",
    "data_state_id",
    "split_protocol_id",
    "split_protocol_version",
    "split_protocol_hash",
    "evaluator_id",
    "evaluator_version",
    "evaluator_hash",
    "schema_version",
    "schema_hash",
    "fixture_manifest_hash",
    "scientific_provenance_snapshot",
    "supersedes_scientific_lock_hash",
)
REQUIRED_FIELDS = frozenset(SCIENTIFIC_FIELDS[:-1])
_HASH_FIELDS = frozenset(
    {
        "benchmark_definition_hash",
        "data_manifest_hash",
        "split_protocol_hash",
        "evaluator_hash",
        "schema_hash",
        "fixture_manifest_hash",
    }
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
GOVERNANCE_FIELDS = frozenset(
    {
        "legal_status",
        "license_status",
        "license_clearance_snapshot",
        "publication_status",
        "public_release_authority",
        "historical_authority_role",
        "public_release_version",
        "release_status",
        "artifact_availability",
        "artifact_references",
        "hosting_provider",
        "provider_urls",
        "artifact_download_locations",
        "release_timestamp",
        "created_at",
        "publication_timestamps",
        "deprecation_metadata",
        "deprecation_timestamps",
        "supersession_governance_metadata",
        "withdrawal_metadata",
        "withdrawal_timestamps",
        "citation_metadata",
        "documentation_metadata",
        "runtime_clock_values",
    }
)


def _validate_string_tree(value: object) -> None:
    if isinstance(value, str):
        if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
            raise ValueError("unpaired Unicode surrogates are not valid UTF-8 lock values")
        return
    if isinstance(value, list):
        for item in cast(list[object], value):
            _validate_string_tree(item)
        return
    if isinstance(value, dict):
        typed_value = cast(dict[object, object], value)
        if any(not isinstance(key, str) for key in typed_value):
            raise ValueError("lock object keys must be strings")
        for key, item in typed_value.items():
            _validate_string_tree(key)
            _validate_string_tree(item)
        return
    raise ValueError("scientific lock values must contain only strings, objects, and arrays")


def _canonical_value(value: object) -> bytes:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if isinstance(value, list):
        items = cast(list[object], value)
        return b"[" + b",".join(_canonical_value(item) for item in items) + b"]"
    if isinstance(value, dict):
        items = cast(dict[str, object], value)
        ordered_keys = sorted(items, key=lambda key: key.encode("utf-16-be"))
        pairs = (
            _canonical_value(key) + b":" + _canonical_value(items[key]) for key in ordered_keys
        )
        return b"{" + b",".join(pairs) + b"}"
    raise ValueError("scientific lock values must contain only strings, objects, and arrays")


def canonical_scientific_bytes(value: object) -> bytes:
    """RFC 8785 JCS bytes for the lock schema's string-only scientific value tree.

    The lock schema admits only string leaves. Object keys are ordered as UTF-16
    code units and strings use JSON's UTF-8 representation, matching JCS exactly.
    """
    _validate_string_tree(value)
    return _canonical_value(value)


def _scientific_payload(lock: Mapping[str, object]) -> JsonObject:
    unknown = set(lock) - set(SCIENTIFIC_FIELDS) - GOVERNANCE_FIELDS - {"scientific_lock_hash"}
    if unknown:
        raise ValueError(f"unknown scientific-lock fields: {', '.join(sorted(unknown))}")
    missing = REQUIRED_FIELDS - set(lock)
    if missing:
        raise ValueError(f"missing scientific-lock fields: {', '.join(sorted(missing))}")
    if lock.get("lock_schema_version") != LOCK_SCHEMA_VERSION:
        raise ValueError("unsupported scientific lock schema version")
    payload = {key: lock[key] for key in SCIENTIFIC_FIELDS if key in lock}
    snapshot = payload.get("scientific_provenance_snapshot")
    if not isinstance(snapshot, dict):
        raise ValueError("scientific provenance snapshot has an invalid shape")
    typed_snapshot = cast(dict[str, object], snapshot)
    if set(typed_snapshot) != {"snapshot_id", "snapshot_hash", "citations"}:
        raise ValueError("scientific provenance snapshot has an invalid shape")
    if not isinstance(typed_snapshot["snapshot_id"], str) or not isinstance(
        typed_snapshot["snapshot_hash"], str
    ):
        raise ValueError("scientific provenance snapshot identifiers must be strings")
    citations = typed_snapshot["citations"]
    if not isinstance(citations, list) or not all(
        isinstance(item, str) for item in cast(list[object], citations)
    ):
        raise ValueError("scientific provenance citations must be an array of strings")
    string_fields = REQUIRED_FIELDS - {"scientific_provenance_snapshot"}
    if not all(isinstance(payload[key], str) for key in string_fields):
        raise ValueError("scientific lock identity fields must be strings")
    if any(not cast(str, payload[key]) for key in string_fields):
        raise ValueError("scientific lock identity fields must not be empty")
    if any(not _SHA256.fullmatch(cast(str, payload[key])) for key in _HASH_FIELDS):
        raise ValueError("scientific lock digest fields must be lowercase SHA-256")
    if not _SHA256.fullmatch(typed_snapshot["snapshot_hash"]):
        raise ValueError("scientific provenance snapshot hash must be lowercase SHA-256")
    if not all(
        _SEMVER.fullmatch(cast(str, payload[field]))
        for field in ("data_release_version", "split_protocol_version", "evaluator_version")
    ):
        raise ValueError("data, split, and evaluator versions must use semantic versioning")
    if "supersedes_scientific_lock_hash" in payload and (
        not isinstance(payload["supersedes_scientific_lock_hash"], str)
        or not _SHA256.fullmatch(payload["supersedes_scientific_lock_hash"])
    ):
        raise ValueError("superseded scientific lock hash must be lowercase SHA-256")
    return payload


def compute_scientific_lock_hash(lock: Mapping[str, object]) -> str:
    payload = _scientific_payload(lock)
    return hashlib.sha256(canonical_scientific_bytes(payload)).hexdigest()


def build_scientific_lock(scientific_state: Mapping[str, object]) -> JsonObject:
    payload = dict(_scientific_payload(scientific_state))
    payload["scientific_lock_hash"] = hashlib.sha256(
        canonical_scientific_bytes({key: value for key, value in payload.items()})
    ).hexdigest()
    return payload


def verify_scientific_lock(lock: Mapping[str, object]) -> bool:
    expected = lock.get("scientific_lock_hash")
    return isinstance(expected, str) and expected == compute_scientific_lock_hash(lock)
