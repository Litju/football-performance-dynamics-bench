"""Non-consuming research admission metadata checks; never opens source rows or models."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
from pathlib import Path
from typing import Any, cast

from . import res645_paths as paths
from . import res645_source_stream as source
from .empirical_experiment_plan import protocol_split_v2

ADMISSION_SHA256 = "a8c82bfa09ac792d6c4ae779d4b28158c33ed3c2500f8548f3e94d48197f4fd1"
CONSUMED_SCOPE = "d359751e969767f30ed6e90c65b13d0eec49f11c9e33e1d2319b19530d28f2e0"


def _validate_admission(document: object, expected_sha256: str) -> dict[str, int]:
    if not isinstance(document, dict):
        raise ValueError("admission must be an object")
    document = cast(dict[str, Any], document)
    encoded = json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()
    if hashlib.sha256(encoded).hexdigest() != expected_sha256:
        raise ValueError("research admission identity differs")
    if (
        document.get("status") != "RESEARCH_RECONCILED"
        or document.get("protected_status") != "NOT_QUALIFIED"
        or document.get("source_release_hash")
        != "e92c417b7640b27399451134ee3fce4b1961b0c0dfc2e01175a8f3c906a9ae07"
        or document.get("source_population_hash")
        != "e9054b7ddc2dfeff4dd8425ea61a23ed0b326076a08899e47502484228fdbdf4"
    ):
        raise ValueError("research admission provenance differs")
    roles = cast(dict[str, list[str]], protocol_split_v2()["roles"])
    raw_matches: object = document.get("per_match")
    if not isinstance(raw_matches, dict):
        raise ValueError("research admission match inventory differs")
    matches = cast(dict[str, Any], raw_matches)
    if set(matches) != {mid for members in roles.values() for mid in members}:
        raise ValueError("research admission match inventory differs")
    for role, members in roles.items():
        if any(
            not isinstance(matches[mid], dict) or matches[mid].get("role") != role
            for mid in members
        ):
            raise ValueError("research admission match role differs")
    counts: dict[str, int] = {}
    for mid in roles["evaluation"]:
        match_counts: object = matches[mid].get("counts")
        if not isinstance(match_counts, dict):
            raise ValueError("evaluation scoreable-window count missing")
        count: object = cast(dict[str, object], match_counts).get("scoreable_windows")
        if type(count) is not int or count <= 0:
            raise ValueError("evaluation scoreable-window count missing")
        counts[mid] = count
    return counts


def verify_admission(path: Path) -> dict[str, int]:
    """Verify the pinned admission and declared evaluation counts without reading truth."""
    raw = _read_admission(path)
    return _validate_admission(source.parse_json(raw), ADMISSION_SHA256)


def _read_admission(path: Path) -> bytes:
    if (
        not path.is_absolute()
        or ".." in path.parts
        or path.name != "research-admission.json"
        or any(part in str(path).lower() for part in ("res594", "heldout", "held-out"))
    ):
        raise PermissionError("unsafe research admission path")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in path.parts[1:-1]:
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd
            )
            os.close(fd)
            fd = child
        parent = os.fstat(fd)
        if parent.st_uid != os.geteuid() or parent.st_mode & 0o077:
            raise PermissionError("research admission directory must be owner-private")
        child = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    finally:
        os.close(fd)
    with os.fdopen(child, "rb") as stream:
        before = os.fstat(stream.fileno())
        paths.check_regular(before, max_bytes=16 * 1024 * 1024, require_private=True)
        data = stream.read(16 * 1024 * 1024 + 1)
        after = os.fstat(stream.fileno())
    if len(data) != before.st_size or paths.stat_key(before) != paths.stat_key(after):
        raise ValueError("research admission changed while reading")
    return data


def proposed_scope(identities: dict[str, str]) -> str:
    """Hash prospective bindings only; this cannot authorize or reserve a campaign."""
    required = {
        "source_sha256",
        "scorer_sha256",
        "verifier_sha256",
        "runtime_sha256",
        "ledger_sha256",
        "output_sha256",
        "independent_report_sha256",
    }
    if set(identities) != required or any(
        re.fullmatch(r"[0-9a-f]{64}", value) is None or value == CONSUMED_SCOPE
        for value in identities.values()
    ):
        raise ValueError("incomplete or forbidden scope bindings")
    if identities["ledger_sha256"] == identities["output_sha256"]:
        raise ValueError("ledger and output identities must differ")
    body = {
        "study": "fpdbench.public-skillcorner-post-failure-descriptive-heldout/1.0.0",
        "protocol_sha256": "ac931391ecb0afcb68974e1765f65fbff17071ade2bcaab93bdadd22f84a0305",
        "manifest_sha256": "770f1d9bbca3020237992181a56e4f5be4adaae7aab07f5f1313aa699d8693e0",
        "admission_sha256": ADMISSION_SHA256,
        "matches": ["1874553", "1925299", "2006229", "2010085"],
        "cpu_seconds": 14400,
        "wall_seconds": 21600,
        "rss_bytes": 2147483648,
        "disk_bytes": 2147483648,
        "identities": identities,
    }
    data = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    digest = hashlib.sha256(data).hexdigest()
    if digest == CONSUMED_SCOPE:
        raise ValueError("historical scope is permanently forbidden")
    return digest


TRUST_DIRECTORY = Path("/etc/fpdbench/protected-executor")
TRUST_FILES = ("res646-owner-signers", "res646-ledger-key")


def production_trust_status() -> dict[str, Any]:
    """Existence-only probe of the protected trust files; never reads key material."""
    present = {name: (TRUST_DIRECTORY / name).is_file() for name in TRUST_FILES}
    return {
        "status": "PROVISIONED_UNVERIFIED"
        if all(present.values())
        else "PRODUCTION_TRUST_KEY_NOT_YET_PROVISIONED",
        "files_present": present,
        "policy": "real execution fails closed until both are provisioned and verified (Gate 6)",
    }


def private_preflight(owner_config: Path, evidence: Path) -> dict[str, Any]:
    """Reconcile existing owner-local evidence without source/model opens or reservation.

    Old textual readback evidence is retained as evidence, not promoted to a new attestation.
    Missing local bindings and target quotas remain blockers regardless of old hash checks.
    """
    raw, _ = paths.read_regular_file(owner_config, max_bytes=65536, require_private=True)
    prior, prior_identity = paths.read_regular_file(
        evidence,
        max_bytes=1 << 20,
        require_private=True,
    )
    names = {
        "SOURCE_INVENTORY",
        "CHECKPOINT_DIRECTORY",
        "FIT_RECEIPTS_DIRECTORY",
        "RESEARCH_ADMISSION",
        "LEDGER_ROOT",
        "OUTPUT_DIRECTORY",
        "GATE5_READ_SCOPE",
    }
    values: dict[str, str] = {}
    for line in raw.decode().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or key not in names or key in values:
            raise ValueError("invalid or duplicate owner-local configuration field")
        parsed = shlex.split(value, comments=True)
        if len(parsed) > 1:
            raise ValueError("owner-local values must be single literal paths or scope IDs")
        values[key] = parsed[0] if parsed else ""
    missing = sorted(name for name in names if not values.get(name))
    return {
        "schema": "fpdbench.res646.nonconsuming-preflight/1",
        "status": "MISSING_OWNER_LOCAL_CONFIG" if missing else "INDEPENDENT_PREFLIGHT_REQUIRED",
        "missing_fields": missing,
        "prior_evidence_sha256": prior_identity.sha256,
        "prior_evidence_bytes": len(prior),
        "prior_evidence_policy": "preserved; no repeated source or checkpoint byte readback",
        "protocol_sha256": "ac931391ecb0afcb68974e1765f65fbff17071ade2bcaab93bdadd22f84a0305",
        "manifest_sha256": "770f1d9bbca3020237992181a56e4f5be4adaae7aab07f5f1313aa699d8693e0",
        "admission_sha256": ADMISSION_SHA256,
        "production_trust": production_trust_status(),
        "source_rows_opened": False,
        "models_loaded": False,
        "scope_consumed": False,
        "target_resource_qualification": "not established by prior host free-space observations",
        "separate_owner_go": "not requested or provisioned",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="RES646 metadata-only, non-consuming preflight")
    parser.add_argument("--owner-config", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = private_preflight(args.owner_config, args.evidence)
    from .res635_execution import atomic

    atomic(args.report, result)
    print(json.dumps({"status": result["status"], "missing_fields": result["missing_fields"]}))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
