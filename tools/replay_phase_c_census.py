"""Read-only, non-authoritative replay using pinned public metadata and phase CSV only."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path
from typing import Any

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    empirical_experiment_plan,
)
from fpdbench.data_sources.phase_normalization_c import normalize_phases_c
from fpdbench.data_sources.skillcorner import MANIFEST_PATH

REVISION = "4340d274572876239c154c90bc507a9b3250a656"
EXPECTED = {
    "matches": 20,
    "conflicting_matches": 17,
    "clean_matches": 3,
    "covered_frames_gain": 406,
    "theoretical_origins_gain": {"training": 128, "validation": 0, "evaluation": 18},
}


def coverage(intervals: list[dict[str, int]]) -> tuple[int, int]:
    """Count union coverage and complete 25/15 support origins on even source frames."""
    merged: list[tuple[int, int, int]] = []
    for row in sorted(intervals, key=lambda r: (r["period"], r["frame_start"], r["frame_end"])):
        period, start, end = row["period"], row["frame_start"], row["frame_end"]
        if merged and period == merged[-1][0] and start <= merged[-1][2]:
            p, left, right = merged[-1]
            merged[-1] = (p, left, max(right, end))
        else:
            merged.append((period, start, end))
    frames = sum(end - start for _, start, end in merged)
    origins = sum(max(0, (end - 31) // 2 - (start + 49) // 2) for _, start, end in merged)
    return frames, origins


def replay(local_root: Path | None) -> dict[str, Any]:
    manifest = json.loads(MANIFEST_PATH.read_bytes())
    roles = empirical_experiment_plan.protocol_split_v2()["roles"]
    role_by_match = {int(match): role for role, matches in roles.items() for match in matches}
    totals: dict[str, Any] = {
        "matches": 0,
        "conflicting_matches": 0,
        "clean_matches": 0,
        "covered_frames_gain": 0,
        "theoretical_origins_gain": {"training": 0, "validation": 0, "evaluation": 0},
    }
    for match in manifest["available_matches"]:
        match_id = match["match_id"]
        payloads = []
        for suffix in ("_match.json", "_phases_of_play.csv"):
            record = next(r for r in match["files"] if r["repository_path"].endswith(suffix))
            path = record["repository_path"]
            url = f"https://raw.githubusercontent.com/SkillCorner/opendata/{REVISION}/{path}"
            if record["pinned_source_url"] != url:
                raise ValueError("source revision or path mismatch")
            if local_root is None:
                with urllib.request.urlopen(url, timeout=45) as response:
                    payload = response.read()
            else:
                payload = (local_root / path).read_bytes()
            blob = hashlib.sha1(b"blob " + str(len(payload)).encode() + b"\0" + payload).hexdigest()
            if len(payload) != record["byte_size"] or blob != record["git_blob_sha"]:
                raise ValueError("public source identity mismatch")
            payloads.append(payload)
        phases, lineage, shadow = normalize_phases_c(payloads[1], payloads[0])
        rows = json.loads(lineage)["rows"]
        conflicts = [
            row
            for row in rows
            if row["normalized"] is None
            or row["raw_start"] != row["normalized"]["frame_start"]
            or row["raw_end"] != row["normalized"]["frame_end"]
        ]
        period_one_end = next(
            period["end_frame"]
            for period in json.loads(payloads[0])["match_periods"]
            if period["period"] == 1
        )
        if len(conflicts) not in (0, 1) or any(
            row["period"] != 1 or row["raw_end"] <= period_one_end for row in conflicts
        ):
            raise ValueError("unexpected conflict multiplicity")
        c_frames, c_origins = coverage(json.loads(phases))
        b_frames, b_origins = coverage(json.loads(shadow)["intervals"])
        totals["matches"] += 1
        totals["conflicting_matches" if conflicts else "clean_matches"] += 1
        totals["covered_frames_gain"] += c_frames - b_frames
        totals["theoretical_origins_gain"][role_by_match[match_id]] += c_origins - b_origins
    if totals != EXPECTED:
        raise ValueError(f"public census differs from expected aggregate: {totals}")
    return totals


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--source-root", type=Path, help="local upstream tree; read only")
    group.add_argument(
        "--fetch-public", action="store_true", help="fetch only public CSV and metadata"
    )
    args = parser.parse_args()
    print(json.dumps({"status": "NON_AUTHORITATIVE_SENSITIVITY", **replay(args.source_root)}))


if __name__ == "__main__":
    main()
