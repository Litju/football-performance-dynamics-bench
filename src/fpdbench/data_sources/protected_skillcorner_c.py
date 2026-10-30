"""Versioned C preflight candidate; never grants population qualification."""
# pyright: reportPrivateUsage=false

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import cast

from fpdbench.data_sources import protected_skillcorner as old
from fpdbench.data_sources.phase_normalization_c import (
    NORMALIZER_ID,
    NORMALIZER_VERSION,
    normalize_phases_c,
)
from fpdbench.data_sources.skillcorner import canonical_bytes

SCHEMA = "fpdbench.protected-source-preflight-c"
VERSION = "1.0.0"
NAMESPACE = "fpdbench-res501-source-c-v1"
POLICY_VERSION = "2.0.0"
POLICY_NAMESPACE = "fpdbench-res544-trust-policy-c-v2"
NORMALIZER = {"id": NORMALIZER_ID, "version": NORMALIZER_VERSION}


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def source_preflight_c(source: Path, destination: Path) -> None:
    """Create a new unsigned C preflight in a fresh private directory."""
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError("source and receipt directories must be disjoint")
    with old.private_directory(source) as root, old.private_directory(destination) as output:
        si, oi = os.fstat(root), os.fstat(output)
        if (si.st_dev, si.st_ino) in old._ancestor_identities(output) or (
            oi.st_dev,
            oi.st_ino,
        ) in old._ancestor_identities(root):
            raise ValueError("source and receipt filesystem identities overlap")
        if os.listdir(output):
            raise ValueError("fresh empty receipt directory required")
        old.write_private(output, "started.json", canonical_bytes({"status": "INCOMPLETE"}))
        try:
            manifest = old._authority()
            records = old._records(manifest)
            inventory = old._verify_sources(root, records)
            counts = old._scan(root, manifest)
            expected = {str(row["path"]): row["sha256"] for row in inventory}
            for count in counts:
                prefix = f"data/matches/{count['match_id']}/{count['match_id']}"
                if count["tracking_sha256"] != expected[prefix + "_tracking_extrapolated.jsonl"]:
                    raise ValueError("source changed during global scan")
            phases: list[dict[str, object]] = []
            for match in cast(list[int], manifest["selected_source_matches"]):
                prefix = f"data/matches/{match}/{match}"
                metadata = old._document(root, prefix + "_match.json")
                source_csv = old._document(root, prefix + "_phases_of_play.csv")
                if (
                    _sha(metadata) != expected[prefix + "_match.json"]
                    or _sha(source_csv) != expected[prefix + "_phases_of_play.csv"]
                ):
                    raise ValueError("phase source changed")
                normalized, lineage, _ = normalize_phases_c(source_csv, metadata)
                if len(normalized) > old.MAX_DOCUMENT or len(lineage) > old.MAX_DOCUMENT:
                    raise ValueError("C phase artifact exceeds memory bound")
                name, lineage_name = f"phases-{match}.json", f"lineage-{match}.json"
                old.write_private(output, name, normalized)
                old.write_private(output, lineage_name, lineage)
                phases.append(
                    {
                        "path": name,
                        "sha256": _sha(normalized),
                        "bytes": len(normalized),
                        "lineage_path": lineage_name,
                        "lineage_sha256": _sha(lineage),
                        "lineage_bytes": len(lineage),
                        "source_sha256": _sha(source_csv),
                        "metadata_sha256": _sha(metadata),
                    }
                )
            if old._verify_sources(root, records) != inventory:
                raise ValueError("source changed during preflight")
            receipt = {
                "schema_id": SCHEMA,
                "schema_version": VERSION,
                "status": "SOURCE_PREFLIGHT",
                "qualification_status": "NOT_QUALIFIED",
                "source_revision": old.REVISION,
                "authority_sha256": old.MANIFEST_SHA256,
                "normalizer": NORMALIZER,
                "inputs": inventory,
                "scan": counts,
                "normalized_phases": phases,
                "adapter_package": old.installed_adapter_inventory(),
                "authentication": "DETACHED_SSH_SIGNATURE_REQUIRED",
            }
            old.write_private(output, "source-preflight-c.json", canonical_bytes(receipt))
        except Exception:
            try:
                old.write_private(output, "failure.json", canonical_bytes({"status": "INCOMPLETE"}))
            except Exception:
                pass
            raise ValueError(
                "INCOMPLETE: C preflight failed; use a fresh receipt directory"
            ) from None


def _validate_receipt(payload: bytes, value: dict[str, object], policy: dict[str, object]) -> None:
    if (
        canonical_bytes(value) != payload
        or value.get("schema_id") != SCHEMA
        or value.get("schema_version") != VERSION
        or value.get("normalizer") != NORMALIZER
    ):
        raise ValueError("invalid C receipt identity")
    legacy = dict(value)
    legacy.pop("normalizer", None)
    legacy["schema_id"], legacy["schema_version"] = old.SCHEMA, old.VERSION
    raw = legacy.get("normalized_phases")
    if not isinstance(raw, list):
        raise ValueError("invalid C phases")
    entries: list[dict[str, object]] = []
    for match, item in zip(
        cast(list[int], old._authority()["selected_source_matches"]),
        cast(list[object], raw),
        strict=True,
    ):
        row = old._object(item)
        if set(row) != {
            "path",
            "sha256",
            "bytes",
            "lineage_path",
            "lineage_sha256",
            "lineage_bytes",
            "source_sha256",
            "metadata_sha256",
        }:
            raise ValueError("invalid C phase lineage shape")
        if row["lineage_path"] != f"lineage-{match}.json":
            raise ValueError("invalid C lineage path")
        old._hash(row["lineage_sha256"], "lineage digest")
        for key in ("bytes", "lineage_bytes"):
            if type(row[key]) is not int or not 0 < cast(int, row[key]) <= old.MAX_DOCUMENT:
                raise ValueError("invalid C artifact size")
        entries.append(
            {key: row[key] for key in ("path", "sha256", "source_sha256", "metadata_sha256")}
        )
    legacy["normalized_phases"] = entries
    old._validate_source_receipt(canonical_bytes(legacy), legacy, policy)


def _validate_policy(payload: bytes, reviewer_signers: bytes) -> dict[str, object]:
    policy = old._object(old._json(payload))
    if canonical_bytes(policy) != payload or policy.get("schema_version") != POLICY_VERSION:
        raise ValueError("invalid C trust policy")
    if policy.get("normalizer") != NORMALIZER or policy.get("receipt_schema") != {
        "id": SCHEMA,
        "version": VERSION,
    }:
        raise ValueError("C policy binding mismatch")
    legacy = dict(policy)
    legacy.pop("normalizer", None)
    legacy.pop("receipt_schema", None)
    runtime = legacy.pop("synthetic_runtime", None)
    if runtime is not None:
        binding = old._object(runtime)
        if set(binding) != {
            "launcher_sha256",
            "producer_manifest_sha256",
            "verifier_manifest_sha256",
        }:
            raise ValueError("invalid synthetic runtime binding")
        for digest in binding.values():
            old._hash(digest, "synthetic runtime digest")
    legacy["schema_version"] = old.TRUST_POLICY_VERSION
    reviewer = dict(old._object(legacy["reviewer"]))
    if reviewer.get("namespace") != NAMESPACE:
        raise ValueError("C reviewer namespace mismatch")
    reviewer["namespace"] = old.NAMESPACE
    legacy["reviewer"] = reviewer
    old._validate_trust_policy(canonical_bytes(legacy), reviewer_signers)
    return policy


def _load_policy_c() -> tuple[dict[str, object], bytes, str]:
    with old._trusted_directory() as root:
        policy_bytes = old._trusted_file(root, "policy-c.json")
        policy_sig = old._trusted_file(root, "policy-c.sig")
        root_signers = old._trusted_file(root, "root.allowed_signers")
        reviewer_signers = old._trusted_file(root, "reviewer.allowed_signers")
    old._signer_fingerprints(root_signers, old.TRUST_POLICY_PRINCIPAL)
    old._verify_ssh_signature(
        policy_bytes, policy_sig, root_signers, old.TRUST_POLICY_PRINCIPAL, POLICY_NAMESPACE
    )
    policy = _validate_policy(policy_bytes, reviewer_signers)
    return policy, reviewer_signers, _sha(policy_bytes)


def authenticate_receipt_c(payload: bytes, signature: bytes) -> dict[str, object]:
    """Authenticate a C receipt only through the separate root-signed C policy."""
    if len(payload) > old.MAX_DOCUMENT or len(signature) > old.MAX_DOCUMENT:
        raise ValueError("oversized C receipt or signature")
    policy, reviewer_signers, _ = _load_policy_c()
    reviewer = old._object(policy["reviewer"])
    old._verify_ssh_signature(
        payload, signature, reviewer_signers, cast(str, reviewer["principal"]), NAMESPACE
    )
    value = old._object(old._json(payload))
    _validate_receipt(payload, value, policy)
    return value


def verify_source_snapshot_c(source: Path, receipt_directory: Path) -> dict[str, object]:
    """Reauthenticate and independently rederive both C artifacts from source bytes."""
    with old.private_directory(source) as root, old.private_directory(receipt_directory) as output:
        si, oi = os.fstat(root), os.fstat(output)
        if (
            source == receipt_directory
            or source in receipt_directory.parents
            or receipt_directory in source.parents
            or (si.st_dev, si.st_ino) in old._ancestor_identities(output)
            or (oi.st_dev, oi.st_ino) in old._ancestor_identities(root)
        ):
            raise ValueError("overlapping source and receipt roots")
        payload = old._document(output, "source-preflight-c.json")
        signature = old._document(output, "source-preflight-c.sig")
        receipt = authenticate_receipt_c(payload, signature)
        manifest = old._authority()
        records = old._records(manifest)
        inventory = old._verify_sources(root, records)
        if inventory != receipt["inputs"] or old._scan(root, manifest) != receipt["scan"]:
            raise ValueError("C source inventory or scan changed")
        for match, raw in zip(
            cast(list[int], manifest["selected_source_matches"]),
            cast(list[object], receipt["normalized_phases"]),
            strict=True,
        ):
            row = old._object(raw)
            prefix = f"data/matches/{match}/{match}"
            metadata = old._document(root, prefix + "_match.json")
            source_csv = old._document(root, prefix + "_phases_of_play.csv")
            normalized, lineage, _ = normalize_phases_c(source_csv, metadata)
            if (
                _sha(metadata) != row["metadata_sha256"]
                or _sha(source_csv) != row["source_sha256"]
                or _sha(normalized) != row["sha256"]
                or len(normalized) != row["bytes"]
                or _sha(lineage) != row["lineage_sha256"]
                or len(lineage) != row["lineage_bytes"]
                or old._document(output, cast(str, row["path"])) != normalized
                or old._document(output, cast(str, row["lineage_path"])) != lineage
            ):
                raise ValueError("C normalized phase or lineage changed")
        if old._verify_sources(root, records) != inventory:
            raise ValueError("source changed during C verification")
        return receipt


def produce_from_snapshot_c(source: Path, receipt_directory: Path, output: Path) -> Path:
    """Run the synthetic worker against receipt-derived paths and check its input digests.

    The returned output remains UNQUALIFIED; this does not attest the runtime or storage.
    """
    from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
        streaming_population_producer_v1 as worker,
    )

    snapshot = verify_source_snapshot_c(source, receipt_directory)
    manifest = old._authority()
    inventory = {str(row["path"]): row for row in cast(list[dict[str, object]], snapshot["inputs"])}
    phase_rows = cast(list[dict[str, object]], snapshot["normalized_phases"])
    matches = cast(list[int], manifest["selected_source_matches"])
    expected: dict[str, dict[str, object]] = {}
    inputs: list[worker.StreamingPopulationMatchInputV1] = []
    for match, phase in zip(matches, phase_rows, strict=True):
        prefix = f"data/matches/{match}/{match}"
        metadata_path = prefix + "_match.json"
        tracking_path = prefix + "_tracking_extrapolated.jsonl"
        metadata, tracking = inventory[metadata_path], inventory[tracking_path]
        expected[str(match)] = {
            "metadata_json": {"sha256": metadata["sha256"], "byte_size": metadata["bytes"]},
            "tracking_jsonl": {"sha256": tracking["sha256"], "byte_size": tracking["bytes"]},
            "normalized_phase_intervals_json": {
                "sha256": phase["sha256"],
                "byte_size": phase["bytes"],
            },
        }
        inputs.append(
            worker.StreamingPopulationMatchInputV1(
                match_id=str(match),
                metadata_path=source / metadata_path,
                tracking_jsonl_path=source / tracking_path,
                phase_intervals_path=receipt_directory / cast(str, phase["path"]),
            )
        )
    result = worker.produce_streaming_population_draft_v1(inputs, output)
    if (
        result.status != "UNQUALIFIED"
        or result.output_directory != output
        or verify_source_snapshot_c(source, receipt_directory) != snapshot
    ):
        raise ValueError("C snapshot changed during producer execution")
    with old.private_directory(output) as root:
        produced = old._object(old._json(old._document(root, "receipt.json")))
    rows = produced.get("input_receipts")
    if produced.get("status") != "UNQUALIFIED" or not isinstance(rows, list):
        raise ValueError("producer receipt missing or qualified")
    seen: set[str] = set()
    for item in cast(list[object], rows):
        row = old._object(item)
        match_id = row.get("match_id")
        if (
            not isinstance(match_id, str)
            or match_id in seen
            or row.get("inputs") != expected.get(match_id)
        ):
            raise ValueError("producer inputs differ from authenticated C snapshot")
        seen.add(match_id)
    if seen != set(expected):
        raise ValueError("producer input coverage differs from authenticated C snapshot")
    return result.output_directory
