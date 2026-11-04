"""Research-only independent reconstruction; no producer or eligibility imports."""

from __future__ import annotations

import argparse
import csv
import dataclasses
import hashlib
import io
import json
import os
import stat
from collections.abc import Sequence
from pathlib import Path

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    streaming_population_verifier_v1 as v,
)


def normalize(source_csv: bytes, metadata_bytes: bytes) -> tuple[bytes, bytes]:
    """Independently reproduce C's period intersection and ordered row lineage."""
    metadata = json.loads(metadata_bytes)
    bounds = v._metadata_periods(metadata)
    intervals, rows = [], []
    for index, row in enumerate(csv.DictReader(io.StringIO(source_csv.decode())), 1):
        start, end = int(row["frame_start"]), int(row["frame_end"])
        if "period" in row:
            period = int(row["period"])
        else:
            candidates = [p for p, (a, b) in bounds.items() if a <= start < end <= b]
            if len(candidates) != 1:
                raise ValueError("ambiguous phase period")
            period = candidates[0]
        left, right = bounds[period]
        a, b = max(start, left), min(end, right)
        normalized = {"period": period, "frame_start": a, "frame_end": b} if a < b else None
        if normalized:
            intervals.append(normalized)
        rows.append(
            {
                "source_row": index,
                "raw_start": start,
                "raw_end": end,
                "source_period": row.get("period"),
                "period": period,
                "normalized": normalized,
                "disposition": "COVERED" if normalized else "EMPTY_INTERSECTION",
            }
        )
    phases = v.canonical_bytes(
        sorted(intervals, key=lambda r: (r["period"], r["frame_start"], r["frame_end"]))
    )
    lineage = v.canonical_bytes(
        {
            "normalizer_id": "fpdbench.skillcorner.phase-period-intersection",
            "normalizer_version": "1.0.0",
            "source_sha256": hashlib.sha256(source_csv).hexdigest(),
            "metadata_sha256": hashlib.sha256(metadata_bytes).hexdigest(),
            "normalized_sha256": hashlib.sha256(phases).hexdigest(),
            "rows": rows,
        }
    )
    return phases, lineage


def _scoped_authorities(scope: str):
    authorities = v.load_authorities()
    if scope == "full":
        return authorities
    if scope != "training-validation":
        raise ValueError("unknown research population scope")
    role_by_match = {match_id: role for role, match_id in authorities.roles}
    source_order = [
        str(match_id)
        for match_id in authorities.source["selected_source_matches"]
        if role_by_match[str(match_id)] in {"training", "validation"}
    ]
    roles = tuple((role_by_match[match_id], match_id) for match_id in source_order)
    source = dict(authorities.source)
    source["selected_source_matches"] = [int(match_id) for match_id in source_order]
    return dataclasses.replace(
        authorities,
        source=source,
        roles=roles,
        match_order=tuple(match_id for _, match_id in roles),
    )


def check_source(
    source: Path,
    inputs: Path,
    normalization: Path,
    *,
    scope: str = "full",
    match_ids: Sequence[str] | None = None,
) -> dict:
    """Independently bind all raw bytes and C inputs to frozen source identities."""
    authorities = _scoped_authorities(scope)
    authority = authorities.source
    selected = list(authorities.match_order)
    if match_ids is not None and list(match_ids) != selected:
        raise ValueError("source check match list differs from the frozen research roles")
    if scope == "full":
        records = [authority["source_index"]] + [
            r for m in authority["available_matches"] for r in m["files"]
        ]
    else:
        selected_set = set(selected)
        records = [
            record
            for match in authority["available_matches"]
            if str(match["match_id"]) in selected_set
            for record in match["files"]
        ]
    expected = {r["repository_path"] for r in records}
    expected_dirs = {str(p) for name in expected for p in Path(name).parents if str(p) != "."}
    actual = set()
    for path in source.rglob("*"):
        info = path.lstat()
        if path.is_symlink() or info.st_uid != os.getuid():
            raise ValueError("unsafe public source path")
        if stat.S_IMODE(info.st_mode) != (0o700 if path.is_dir() else 0o600):
            raise ValueError("unsafe source permissions")
        if path.is_file():
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError("unsafe source file")
            actual.add(path.relative_to(source).as_posix())
        elif not path.is_dir() or path.relative_to(source).as_posix() not in expected_dirs:
            raise ValueError("unexpected source path")
    expected_file_count = 81 if scope == "full" else 4 * len(selected)
    if actual != expected or len(expected) != expected_file_count:
        raise ValueError("source inventory differs")
    receipts = []
    for record in records:
        path = source / record["repository_path"]
        size = record.get("lfs_payload_size", record["byte_size"])
        blob = hashlib.sha1(b"blob " + str(size).encode() + b"\0")
        sha = hashlib.sha256()
        fd, before = v._open_regular_nofollow(path)
        with os.fdopen(fd, "rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                blob.update(chunk)
                sha.update(chunk)
            if v._stat_identity(before) != v._stat_identity(os.fstat(stream.fileno())):
                raise ValueError("source changed")
        if before.st_size != size:
            raise ValueError("source size differs")
        identity = sha.hexdigest() if "lfs_oid_sha256" in record else blob.hexdigest()
        if identity != record.get("lfs_oid_sha256", record["git_blob_sha"]):
            raise ValueError("source content identity differs")
        if "raw_sha256" in record and sha.hexdigest() != record["raw_sha256"]:
            raise ValueError("source SHA-256 differs")
        receipts.append(
            {"path": record["repository_path"], "sha256": sha.hexdigest(), "bytes": size}
        )
    normalization_receipts = []
    for match in selected:
        prefix = source / f"data/matches/{match}/{match}"
        metadata = v._read_bounded_document(
            prefix.with_name(prefix.name + "_match.json"), "metadata"
        )[0]
        csv_bytes = v._read_bounded_document(
            prefix.with_name(prefix.name + "_phases_of_play.csv"), "phase CSV"
        )[0]
        phases, lineage = normalize(csv_bytes, metadata)
        if (
            (inputs / str(match) / "metadata.json").read_bytes() != metadata
            or (inputs / str(match) / "phases.json").read_bytes() != phases
            or (normalization / f"{match}-lineage.json").read_bytes() != lineage
        ):
            raise ValueError("independent C normalization/lineage differs")
        normalization_receipts.append(
            {
                "match_id": str(match),
                "metadata_sha256": hashlib.sha256(metadata).hexdigest(),
                "raw_csv_sha256": hashlib.sha256(csv_bytes).hexdigest(),
                "phases_sha256": hashlib.sha256(phases).hexdigest(),
                "lineage_sha256": hashlib.sha256(lineage).hexdigest(),
            }
        )
    return {
        "scope": scope,
        "match_ids": selected,
        "source_files": receipts,
        "normalization": "INDEPENDENTLY_REDERIVED",
        "normalization_receipts": normalization_receipts,
    }


def derive(inputs: Path, match: str, output: Path, *, scope: str = "full") -> dict:
    authorities = _scoped_authorities(scope)
    if match not in authorities.match_order:
        raise ValueError("match is outside the selected research scope")
    contracts, snapshots = v.load_input_contracts(inputs, authorities)
    contract = contracts[match]
    stats: dict = {}
    counts: dict = {}
    digest = hashlib.sha256()
    partial = output.with_suffix(".partial")
    with partial.open("xb") as stream:

        def samples():
            for sample in v._read_tracking(
                inputs / match / "tracking.jsonl", contract, authorities, stats
            ):
                ball = sample["ball"]
                if (
                    ball
                    and ball["is_detected"] is None
                    and ball["x_m"] is not None
                    and ball["y_m"] is not None
                ):
                    raise ValueError("BALL_NULL_FLAG_WITH_FINITE_XY_UNAPPROVED")
                yield sample

        for origin, support in v._events(samples(), contract):
            complete = all(s is not None for s in support)
            diagnostic = v._diagnose_window(support, contract, authorities)
            scenes = []
            passing = complete and diagnostic["candidate_rules_pass"]
            window = v._window_id(match, origin.sample_id) if passing else None
            if passing:
                for side in ("home", "away"):
                    _, truth, _ = v._scene_truth(support, side)
                    scenes.append(truth)
            row = {
                "match_id": match,
                "role": contract.role,
                "period": origin.period,
                "source_frame": origin.source_frame,
                "origin_sample_id": origin.sample_id,
                "complete_support": complete,
                "diagnostic": diagnostic,
                "window_id": window,
                "scenes": scenes,
            }
            payload = v.canonical_bytes(row) + b"\n"
            stream.write(payload)
            digest.update(payload)
            c = counts.setdefault(
                str(origin.period),
                {
                    "theoretical": 0,
                    "complete_support": 0,
                    "rules_pass": 0,
                    "scoreable_windows": 0,
                    "home_scenes": 0,
                    "away_scenes": 0,
                },
            )
            c["theoretical"] += 1
            c["complete_support"] += complete
            c["rules_pass"] += passing
            c["scoreable_windows"] += any(s["scoreable"] for s in scenes)
            for s in scenes:
                c[s["scene_id"] + "_scenes"] += s["scoreable"]
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(partial, output)
    for period, (start, end) in contract.period_bounds.items():
        if counts[str(period)]["theoretical"] != len(range(start + start % 2, end, 2)):
            raise ValueError("independent origin coverage differs")
    v._validate_input_snapshots(inputs, authorities, snapshots, include_tracking=False)
    return {
        "match_id": match,
        "role": contract.role,
        "periods": counts,
        "artifact_sha256": digest.hexdigest(),
        "tracking_sha256": stats["raw_sha256"],
        "source_rows": stats["source_frame_count"],
        "retained_samples": stats["retained_sample_count"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    check = modes.add_parser("check-source")
    check.add_argument("source", type=Path)
    check.add_argument("inputs", type=Path)
    check.add_argument("normalization", type=Path)
    check.add_argument("output", type=Path)
    check.add_argument("--scope", choices=("full", "training-validation"), default="full")
    check.add_argument("--match-id", action="append")
    worker = modes.add_parser("derive")
    worker.add_argument("inputs", type=Path)
    worker.add_argument("match")
    worker.add_argument("output", type=Path)
    worker.add_argument("--scope", choices=("full", "training-validation"), default="full")
    args = parser.parse_args()
    os.umask(0o077)
    if args.mode == "check-source":
        result = check_source(
            args.source,
            args.inputs,
            args.normalization,
            scope=args.scope,
            match_ids=args.match_id,
        )
        args.output.write_bytes(v.canonical_bytes(result))
    else:
        result = derive(args.inputs, args.match, args.output, scope=args.scope)
        args.output.with_suffix(".summary.json").write_bytes(v.canonical_bytes(result))


if __name__ == "__main__":
    main()
