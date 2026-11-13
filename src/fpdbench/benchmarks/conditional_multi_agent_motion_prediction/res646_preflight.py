"""Non-consuming research admission metadata checks; never opens source rows or models."""

from __future__ import annotations

import hashlib
import json
import re
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
    raw, _ = paths.read_regular_file(path, max_bytes=16 * 1024 * 1024, require_private=True)
    return _validate_admission(source.parse_json(raw), ADMISSION_SHA256)


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
