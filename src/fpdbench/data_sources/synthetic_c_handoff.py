"""Synthetic-only C snapshot handoff through the isolated streaming workers."""
# pyright: reportPrivateUsage=false

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    empirical_experiment_plan,
)
from fpdbench.data_sources import protected_skillcorner as old
from fpdbench.data_sources import protected_skillcorner_c as source_c
from fpdbench.data_sources.skillcorner import canonical_bytes


def _digest_file(root: int, name: str) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with old._open_file(root, name) as stream:
        while chunk := stream.read(old.MAX_ROW):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _input_identities(
    input_root: Path, snapshot: dict[str, object]
) -> tuple[list[str], dict[str, dict[str, object]]]:
    roles = old._object(empirical_experiment_plan.protocol_split_v2()["roles"])
    ordered = [
        str(item)
        for role in ("training", "validation", "evaluation")
        for item in cast(list[object], roles[role])
    ]
    matches = cast(list[int], old._authority()["selected_source_matches"])
    if len(ordered) != 20 or len(set(ordered)) != 20 or set(ordered) != {str(x) for x in matches}:
        raise ValueError("C handoff cohort or roles differ from frozen authority")
    phases = dict(
        zip(
            (str(x) for x in matches),
            cast(list[dict[str, object]], snapshot["normalized_phases"]),
            strict=True,
        )
    )
    inputs = {str(row["path"]): row for row in cast(list[dict[str, object]], snapshot["inputs"])}
    expected: dict[str, dict[str, object]] = {}
    paths = [
        f"{match}/{name}"
        for match in ordered
        for name in ("metadata.json", "tracking.jsonl", "phases.json")
    ]
    with old.private_directory(input_root) as root:
        old._inventory(root, paths)
        for match in ordered:
            prefix = f"data/matches/{match}/{match}"
            metadata = inputs[prefix + "_match.json"]
            tracking = inputs[prefix + "_tracking_extrapolated.jsonl"]
            phase = phases[match]
            values = {
                "metadata.json": (metadata["sha256"], metadata["bytes"]),
                "tracking.jsonl": (tracking["sha256"], tracking["bytes"]),
                "phases.json": (phase["sha256"], phase["bytes"]),
            }
            for name, identity in values.items():
                if _digest_file(root, f"{match}/{name}") != identity:
                    raise ValueError("verifier input differs from authenticated C snapshot")
            expected[match] = {
                "metadata_json": {"sha256": metadata["sha256"], "byte_size": metadata["bytes"]},
                "tracking_jsonl": {"sha256": tracking["sha256"], "byte_size": tracking["bytes"]},
                "normalized_phase_intervals_json": {
                    "sha256": phase["sha256"],
                    "byte_size": phase["bytes"],
                },
            }
    return ordered, expected


def _output_hashes(output: Path) -> dict[str, str]:
    names = (
        "candidates.jsonl",
        "diagnostic-census.jsonl",
        "manifest.json",
        "receipt.json",
        "truth.jsonl",
    )
    with old.private_directory(output) as root:
        old._inventory(root, list(names))
        return {name: _digest_file(root, name)[0] for name in names}


def _reject_pinned_real_sources(snapshot: dict[str, object]) -> None:
    payload = old.MANIFEST_PATH.read_bytes()
    if source_c._sha(payload) != old.MANIFEST_SHA256:
        raise ValueError("frozen source authority differs")
    pinned = old._object(old._json(payload))
    actual_tracking = {
        str(item["repository_path"]): item["lfs_oid_sha256"]
        for item in old._records(pinned)
        if item["identity_type"] == "git_lfs_pointer"
    }
    for raw in cast(list[object], snapshot["inputs"]):
        row = old._object(raw)
        if (
            row.get("path") in actual_tracking
            and row.get("sha256") == actual_tracking[str(row["path"])]
        ):
            raise ValueError("synthetic handoff rejects pinned real tracking payloads")


def _runtime_manifest(path: Path) -> str:
    payload = path.read_bytes()
    value = old._json(payload)
    return source_c._sha(canonical_bytes(value))


def reconcile_from_snapshot_c(
    source: Path,
    receipt_directory: Path,
    input_root: Path,
    output: Path,
    launcher: Path,
    producer_root: Path,
    producer_manifest: Path,
    verifier_root: Path,
    verifier_manifest: Path,
    evidence_directory: Path,
) -> dict[str, object]:
    """Reconcile in separate pinned synthetic processes; never qualifies a population."""
    with old.private_directory(receipt_directory) as root:
        initial_receipt = old._document(root, "source-preflight-c.json")
        initial_signature = old._document(root, "source-preflight-c.sig")
    snapshot = source_c.authenticate_receipt_c(initial_receipt, initial_signature)
    _reject_pinned_real_sources(snapshot)
    if source_c.verify_source_snapshot_c(source, receipt_directory) != snapshot:
        raise ValueError("C snapshot changed during authentication")
    policy, _, policy_digest = source_c._load_policy_c()
    runtime = old._object(policy.get("synthetic_runtime"))
    pins = {
        "launcher_sha256": source_c._sha(launcher.read_bytes()),
        "producer_manifest_sha256": _runtime_manifest(producer_manifest),
        "verifier_manifest_sha256": _runtime_manifest(verifier_manifest),
    }
    if runtime != pins:
        raise ValueError("signed synthetic runtime binding mismatch")
    with old.private_directory(receipt_directory) as root:
        receipt_digest = source_c._sha(old._document(root, "source-preflight-c.json"))
    order, expected = _input_identities(input_root, snapshot)
    with old.private_directory(evidence_directory) as evidence:
        if os.listdir(evidence):
            raise ValueError("fresh evidence directory required")
        request = {
            "inputs": [
                {
                    "match_id": match,
                    "metadata_path": str(input_root / match / "metadata.json"),
                    "tracking_jsonl_path": str(input_root / match / "tracking.jsonl"),
                    "phase_intervals_path": str(input_root / match / "phases.json"),
                }
                for match in order
            ],
            "output_directory": str(output),
        }
        old.write_private(evidence, "producer-request.json", canonical_bytes(request))

    def launch(kind: str, package: Path, manifest: Path, pin: str) -> dict[str, object]:
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-S",
                "-B",
                "-X",
                "pycache_prefix=/dev/null",
                str(launcher),
                "run",
                "--manifest",
                str(manifest),
                "--package-root",
                str(package),
                "--expected-sha256",
                pin,
                "--worker",
                kind,
                "--request",
                str(evidence_directory / f"{kind}-request.json"),
                "--evidence",
                str(evidence_directory / f"{kind}-runtime.json"),
            ],
            env={},
            capture_output=True,
            check=False,
        )
        if result.returncode:
            raise ValueError(f"isolated {kind} failed")
        with old.private_directory(evidence_directory) as root:
            status = old._object(old._json(old._document(root, f"{kind}-runtime.json")))
        required = "UNQUALIFIED" if kind == "producer" else "RECONCILED_NON_AUTHORITATIVE"
        if (
            status.get("status") != "SYNTHETIC_RUNTIME_CONSISTENT"
            or status.get("worker_status") != required
            or status.get("runtime_gate") != "BLOCKED"
            or status.get("qualification") != "NOT_PERFORMED"
            or status.get("authority") != "SYNTHETIC_CALLER_PIN_ONLY"
            or status.get("manifest_sha256") != pin
            or status.get("worker_import_started") is not True
            or status.get("worker_execution_started") is not True
        ):
            raise ValueError(f"isolated {kind} evidence is invalid")
        return status

    launch("producer", producer_root, producer_manifest, pins["producer_manifest_sha256"])
    if source_c.verify_source_snapshot_c(
        source, receipt_directory
    ) != snapshot or _input_identities(input_root, snapshot) != (order, expected):
        raise ValueError("C input changed during producer execution")
    before = _output_hashes(output)
    with old.private_directory(output) as root:
        producer_receipt = old._object(old._json(old._document(root, "receipt.json")))
    raw_rows = producer_receipt.get("input_receipts")
    if (
        not isinstance(raw_rows, list)
        or producer_receipt.get("status") != "UNQUALIFIED"
        or producer_receipt.get("source_byte_qualified") is not False
        or producer_receipt.get("independent_verification") != "NOT_PERFORMED"
    ):
        raise ValueError("invalid producer receipt")
    rows = [old._object(item) for item in cast(list[object], raw_rows)]
    if [row.get("match_id") for row in rows] != order or any(
        row.get("inputs") != expected[str(row["match_id"])] for row in rows
    ):
        raise ValueError("producer input receipt differs from authenticated C snapshot")
    scan = {str(row["match_id"]): row for row in cast(list[dict[str, object]], snapshot["scan"])}
    for row in rows:
        expected_scan = scan[str(row["match_id"])]
        if (
            row.get("source_frame_count") != expected_scan["source_rows"]
            or row.get("retained_sample_count") != expected_scan["retained_rows"]
        ):
            raise ValueError("producer global scan differs from authenticated C snapshot")
    with old.private_directory(evidence_directory) as evidence:
        old.write_private(
            evidence,
            "verifier-request.json",
            canonical_bytes(
                {
                    "input_root": str(input_root),
                    "artifact_root": str(output),
                    "producer_package_root": str(producer_root),
                    "report": str(evidence_directory / "verification.json"),
                }
            ),
        )
    launch("verifier", verifier_root, verifier_manifest, pins["verifier_manifest_sha256"])
    with old.private_directory(evidence_directory) as evidence:
        report = old._object(old._json(old._document(evidence, "verification.json")))
    if (
        report.get("status") != "RECONCILED_NON_AUTHORITATIVE"
        or report.get("qualification") != "NOT_PERFORMED"
        or report.get("runtime_gate") != "BLOCKED"
        or report.get("population_status") != "UNQUALIFIED"
        or report.get("authority") != "NON_AUTHORITATIVE_RECONCILIATION_ONLY"
        or report.get("producer_source_package_verified") is not True
        or report.get("mismatch_count") != 0
        or report.get("actual_artifact_sha256") != before
        or report.get("expected_artifact_sha256")
        != {k: v for k, v in before.items() if k != "receipt.json"}
    ):
        raise ValueError("independent verifier reconciliation differs from producer artifacts")
    drift = old._object(report.get("global_drift_scan"))
    if (
        drift.get("checked_match_count") != 20
        or drift.get("checked_sample_count")
        != sum(cast(int, row["retained_rows"]) for row in scan.values())
        or drift.get("null_flag_finite_xy_count") != 0
        or drift.get("source_release_hash") != old.EXPECTED_SOURCE_RELEASE_HASH
        or drift.get("data_state_hash") != old.EXPECTED_MEASUREMENT_STATE_V2_HASH
    ):
        raise ValueError("independent global drift scan differs from authenticated snapshot")
    after_policy, _, after_digest = source_c._load_policy_c()
    with old.private_directory(receipt_directory) as root:
        after_receipt_digest = source_c._sha(old._document(root, "source-preflight-c.json"))
    if (
        after_policy != policy
        or after_digest != policy_digest
        or after_receipt_digest != receipt_digest
        or source_c.verify_source_snapshot_c(source, receipt_directory) != snapshot
        or _input_identities(input_root, snapshot) != (order, expected)
        or _output_hashes(output) != before
        or source_c._sha(launcher.read_bytes()) != pins["launcher_sha256"]
        or _runtime_manifest(producer_manifest) != pins["producer_manifest_sha256"]
        or _runtime_manifest(verifier_manifest) != pins["verifier_manifest_sha256"]
    ):
        raise ValueError("C handoff identity changed during independent verification")
    binding: dict[str, object] = {
        "schema_id": "fpdbench.synthetic-c-handoff",
        "schema_version": "1.0.0",
        "status": "RECONCILED_NON_AUTHORITATIVE",
        "qualification": "NOT_PERFORMED",
        "runtime_gate": "BLOCKED",
        "source_receipt_sha256": receipt_digest,
        "source_receipt_schema": {"id": source_c.SCHEMA, "version": source_c.VERSION},
        "normalizer": source_c.NORMALIZER,
        "policy_identity": {
            "id": old.TRUST_POLICY_SCHEMA,
            "version": source_c.POLICY_VERSION,
            "signature_namespace": source_c.POLICY_NAMESPACE,
        },
        "authenticated_source_inventory_sha256": source_c._sha(canonical_bytes(snapshot["inputs"])),
        "verifier_input_identities_sha256": source_c._sha(canonical_bytes(expected)),
        "global_drift_scan": drift,
        "policy_sha256": policy_digest,
        "policy_generation": policy["generation"],
        "ordered_roles_sha256": source_c._sha(
            canonical_bytes(empirical_experiment_plan.protocol_split_v2()["roles"])
        ),
        "artifact_sha256": before,
        "runtime_manifest_sha256": pins,
        "verifier_report_sha256": source_c._sha(canonical_bytes(report)),
    }
    with old.private_directory(evidence_directory) as evidence:
        old.write_private(evidence, "c-handoff.json", canonical_bytes(binding))
    return binding
