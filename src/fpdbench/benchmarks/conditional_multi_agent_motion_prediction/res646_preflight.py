"""Non-consuming research admission metadata checks; never opens source rows or models."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

from . import res645_paths as paths
from . import res645_source_stream as source
from .empirical_experiment_plan import protocol_split_v2

ADMISSION_SHA256 = "a8c82bfa09ac792d6c4ae779d4b28158c33ed3c2500f8548f3e94d48197f4fd1"


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
