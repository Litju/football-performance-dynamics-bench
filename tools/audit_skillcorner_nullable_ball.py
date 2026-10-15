"""Audit nullable ball detection and coordinate states from pinned local source bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import subprocess
import traceback
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from qualify_skillcorner_source import (
    private_directory,
    source_preflight,
    validate_storage_boundary,
    write_private,
)
from verify_skillcorner_nullable_ball import recompute as independent_recompute

from fpdbench.data_sources.skillcorner import (
    canonical_bytes,
    manifest_hash,
    source_population_hash,
    source_release_hash,
)
from fpdbench.data_sources.skillcorner import (
    load_manifest as load_source_manifest,
)
from fpdbench.data_sources.skillcorner import (
    validate_manifest as validate_source_manifest,
)

_FRAME_FIELDS = {
    "frame",
    "timestamp",
    "period",
    "ball_data",
    "possession",
    "image_corners_projection",
    "player_data",
}
_PLAYER_FIELDS = {"player_id", "x", "y", "is_detected"}
_BALL_FIELDS = {"x", "y", "z", "is_detected"}
_POSSESSION_FIELDS = {"group", "player_id"}
_FLAGS = ("true", "false", "null", "missing", "invalid")
_XY = ("both_finite", "partial", "both_missing", "invalid")
_COORDINATE_STATES = ("finite", "null", "missing", "nonfinite", "invalid")
_TIMESTAMP = re.compile(r"[0-9]+:[0-5][0-9]:[0-5][0-9]\.([0-9]{2})\Z")


def coordinate_state(value: object, exists: bool) -> str:
    if not exists:
        return "missing"
    if value is None:
        return "null"
    if isinstance(value, bool) or not isinstance(value, int | float):
        return "invalid"
    try:
        return "finite" if math.isfinite(value) else "nonfinite"
    except OverflowError:
        return "invalid"


def flag_state(value: object, exists: bool) -> str:
    if not exists:
        return "missing"
    if value is None:
        return "null"
    if type(value) is bool:
        return "true" if value else "false"
    return "invalid"


def xy_availability(x: str, y: str) -> str:
    if x == y == "finite":
        return "both_finite"
    if (x == "finite" and y in {"null", "missing"}) or (y == "finite" and x in {"null", "missing"}):
        return "partial"
    if x in {"null", "missing"} and y in {"null", "missing"}:
        return "both_missing"
    return "invalid"


def _matrix_keys() -> list[tuple[str, str, str]]:
    return [
        ("absent", "not_applicable", "not_applicable"),
        ("missing_key", "missing", "invalid"),
        *(("present", flag, xy) for flag in _FLAGS for xy in _XY),
    ]


def _matrix_rows(counts: Counter[tuple[str, str, str]]) -> list[dict[str, object]]:
    return [
        {
            "object_presence": presence,
            "detection_flag": flag,
            "xy_availability": xy,
            "count": counts[(presence, flag, xy)],
        }
        for presence, flag, xy in _matrix_keys()
    ]


def _xy_rows(counts: Counter[tuple[str, str]]) -> list[dict[str, object]]:
    return [
        {"x_state": x, "y_state": y, "count": counts[(x, y)]}
        for x in _COORDINATE_STATES
        for y in _COORDINATE_STATES
    ]


def _flag_xy_rows(
    counts: Counter[tuple[str, str, str, str]],
) -> list[dict[str, object]]:
    cells = [("absent", "not_applicable", "not_applicable", "not_applicable")]
    cells.append(("missing_key", "missing", "missing", "missing"))
    cells.extend(
        ("present", flag, x, y)
        for flag in _FLAGS
        for x in _COORDINATE_STATES
        for y in _COORDINATE_STATES
    )
    return [
        {
            "object_presence": presence,
            "detection_flag": flag,
            "x_state": x,
            "y_state": y,
            "count": counts[(presence, flag, x, y)],
        }
        for presence, flag, x, y in cells
    ]


def scan_tracking_lines(lines: Iterable[bytes]) -> dict[str, object]:
    """Stream one JSONL payload and preserve every even-frame ball classification."""
    matrix: Counter[tuple[str, str, str]] = Counter()
    xy_details: Counter[tuple[str, str]] = Counter()
    flag_xy_details: Counter[tuple[str, str, str, str]] = Counter()
    player_flags: Counter[str] = Counter()
    player_flags_all: Counter[str] = Counter()
    anomaly_counts: Counter[str] = Counter()
    retained_anomaly_counts: Counter[str] = Counter()
    anomaly_records: list[dict[str, object]] = []
    row_observations: list[dict[str, object]] = []
    payload_hash = hashlib.sha256()
    payload_bytes = source_rows = odd_rows = even_rows = unclassified_rows = 0
    previous_frame: int | None = None

    def anomaly(
        kind: str,
        line_number: int,
        frame_number: int | None,
        retained: bool,
        *,
        field: str | None = None,
        value_type: str | None = None,
        player_index: int | None = None,
        player_id: object = None,
    ) -> None:
        anomaly_counts[kind] += 1
        if retained:
            retained_anomaly_counts[kind] += 1
        item: dict[str, object] = {
            "source_row": line_number,
            "source_frame": frame_number,
            "retained_even_frame": retained,
            "kind": kind,
            "field": field,
            "value_type": value_type,
        }
        if player_index is not None:
            item["player_index"] = player_index
        if type(player_id) is int:
            item["player_id"] = player_id
        anomaly_records.append(item)

    for line_number, raw in enumerate(lines, start=1):
        source_rows += 1
        payload_hash.update(raw)
        payload_bytes += len(raw)
        try:
            frame = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            anomaly("invalid_json_row", line_number, None, False)
            unclassified_rows += 1
            continue
        if not isinstance(frame, dict):
            anomaly("frame_not_object", line_number, None, False)
            unclassified_rows += 1
            continue

        frame_number_value = frame.get("frame")
        if type(frame_number_value) is not int:
            anomaly(
                "frame_number_invalid",
                line_number,
                None,
                False,
                field="frame",
                value_type=type(frame_number_value).__name__ if "frame" in frame else "missing",
            )
            unclassified_rows += 1
            continue
        frame_number = frame_number_value
        retained = frame_number % 2 == 0
        if frame_number < 0:
            anomaly("frame_number_negative", line_number, frame_number, retained, field="frame")
        if previous_frame is not None and frame_number <= previous_frame:
            anomaly("frame_order_invalid", line_number, frame_number, retained, field="frame")
        previous_frame = frame_number

        missing = sorted(_FRAME_FIELDS - set(frame))
        unexpected = sorted(set(frame) - _FRAME_FIELDS)
        for field in missing:
            anomaly("frame_field_missing", line_number, frame_number, retained, field=field)
        for field in unexpected:
            anomaly("frame_field_unexpected", line_number, frame_number, retained, field=field)

        timestamp = frame.get("timestamp")
        if timestamp is not None and (
            not isinstance(timestamp, str)
            or (match := _TIMESTAMP.fullmatch(timestamp)) is None
            or int(match.group(1)) % 10 != 0
        ):
            anomaly(
                "timestamp_invalid",
                line_number,
                frame_number,
                retained,
                field="timestamp",
                value_type=type(timestamp).__name__,
            )
        period = frame.get("period")
        if period is not None and (type(period) is not int or period not in {1, 2}):
            anomaly(
                "period_invalid",
                line_number,
                frame_number,
                retained,
                field="period",
                value_type=type(period).__name__,
            )
        if retained:
            even_rows += 1
        else:
            odd_rows += 1

        if "ball_data" not in frame:
            presence, flag, xy, x_state, y_state = (
                "missing_key",
                "missing",
                "invalid",
                "missing",
                "missing",
            )
            anomaly(
                "ball_object_key_missing", line_number, frame_number, retained, field="ball_data"
            )
        elif frame["ball_data"] is None:
            presence, flag, xy, x_state, y_state = (
                "absent",
                "not_applicable",
                "not_applicable",
                "not_applicable",
                "not_applicable",
            )
        else:
            presence = "present"
            ball = frame["ball_data"]
            if not isinstance(ball, dict):
                flag, xy, x_state, y_state = "invalid", "invalid", "invalid", "invalid"
                anomaly(
                    "ball_object_not_object",
                    line_number,
                    frame_number,
                    retained,
                    field="ball_data",
                    value_type=type(ball).__name__,
                )
            else:
                ball_missing = sorted(_BALL_FIELDS - set(ball))
                ball_unexpected = sorted(set(ball) - _BALL_FIELDS)
                for field in ball_missing:
                    anomaly("ball_field_missing", line_number, frame_number, retained, field=field)
                for field in ball_unexpected:
                    anomaly(
                        "ball_field_unexpected", line_number, frame_number, retained, field=field
                    )
                flag = flag_state(ball.get("is_detected"), "is_detected" in ball)
                if flag not in {"true", "false"}:
                    anomaly(
                        f"ball_detection_flag_{flag}",
                        line_number,
                        frame_number,
                        retained,
                        field="is_detected",
                        value_type=type(ball.get("is_detected")).__name__
                        if "is_detected" in ball
                        else "missing",
                    )
                x_state = coordinate_state(ball.get("x"), "x" in ball)
                y_state = coordinate_state(ball.get("y"), "y" in ball)
                xy = xy_availability(x_state, y_state)
                if retained:
                    xy_details[(x_state, y_state)] += 1
                for name, state in (("x", x_state), ("y", y_state)):
                    if state in {"nonfinite", "invalid"}:
                        anomaly(
                            "ball_coordinate_invalid",
                            line_number,
                            frame_number,
                            retained,
                            field=name,
                            value_type=state,
                        )
                z_state = coordinate_state(ball.get("z"), "z" in ball)
                if z_state in {"missing", "nonfinite", "invalid"}:
                    anomaly(
                        "ball_z_invalid",
                        line_number,
                        frame_number,
                        retained,
                        field="z",
                        value_type=z_state,
                    )

        if retained:
            matrix[(presence, flag, xy)] += 1
            flag_xy_details[(presence, flag, x_state, y_state)] += 1
            row_observations.append(
                {
                    "source_row": line_number,
                    "source_frame": frame_number,
                    "object_presence": presence,
                    "detection_flag": flag,
                    "xy_availability": xy,
                    "x_state": x_state,
                    "y_state": y_state,
                }
            )

        players = frame.get("player_data")
        if not isinstance(players, list):
            anomaly(
                "player_data_not_array",
                line_number,
                frame_number,
                retained,
                field="player_data",
                value_type=type(players).__name__ if "player_data" in frame else "missing",
            )
            players = []
        player_ids: set[int] = set()
        for player_index, player in enumerate(players):
            if not isinstance(player, dict):
                anomaly(
                    "player_entry_not_object",
                    line_number,
                    frame_number,
                    retained,
                    field="player_data",
                    value_type=type(player).__name__,
                    player_index=player_index,
                )
                player_flags_all["invalid"] += 1
                if retained:
                    player_flags["invalid"] += 1
                anomaly(
                    "player_detection_flag_invalid",
                    line_number,
                    frame_number,
                    retained,
                    field="is_detected",
                    value_type="invalid_player_entry",
                    player_index=player_index,
                )
                continue
            for field in sorted(_PLAYER_FIELDS - set(player)):
                anomaly("player_field_missing", line_number, frame_number, retained, field=field)
            for field in sorted(set(player) - _PLAYER_FIELDS):
                anomaly("player_field_unexpected", line_number, frame_number, retained, field=field)
            player_id = player.get("player_id")
            if type(player_id) is not int or player_id <= 0:
                anomaly(
                    "player_id_invalid",
                    line_number,
                    frame_number,
                    retained,
                    field="player_id",
                    value_type=type(player_id).__name__ if "player_id" in player else "missing",
                    player_index=player_index,
                )
            elif player_id in player_ids:
                anomaly(
                    "player_id_duplicate",
                    line_number,
                    frame_number,
                    retained,
                    field="player_id",
                    player_index=player_index,
                    player_id=player_id,
                )
            else:
                player_ids.add(player_id)

            player_flag = flag_state(player.get("is_detected"), "is_detected" in player)
            player_flags_all[player_flag] += 1
            if retained:
                player_flags[player_flag] += 1
            if player_flag not in {"true", "false"}:
                anomaly(
                    f"player_detection_flag_{player_flag}",
                    line_number,
                    frame_number,
                    retained,
                    field="is_detected",
                    value_type=type(player.get("is_detected")).__name__
                    if "is_detected" in player
                    else "missing",
                    player_index=player_index,
                    player_id=player_id,
                )
            for name in ("x", "y"):
                state = coordinate_state(player.get(name), name in player)
                if state in {"missing", "nonfinite", "invalid"}:
                    anomaly(
                        "player_coordinate_invalid",
                        line_number,
                        frame_number,
                        retained,
                        field=name,
                        value_type=state,
                        player_index=player_index,
                        player_id=player_id,
                    )

        possession = frame.get("possession")
        if possession is not None:
            if not isinstance(possession, dict):
                anomaly(
                    "possession_not_object",
                    line_number,
                    frame_number,
                    retained,
                    field="possession",
                    value_type=type(possession).__name__,
                )
            else:
                for field in sorted(_POSSESSION_FIELDS - set(possession)):
                    anomaly(
                        "possession_field_missing",
                        line_number,
                        frame_number,
                        retained,
                        field=field,
                    )
                for field in sorted(set(possession) - _POSSESSION_FIELDS):
                    anomaly(
                        "possession_field_unexpected",
                        line_number,
                        frame_number,
                        retained,
                        field=field,
                    )
                group = possession.get("group")
                if group is not None and (
                    not isinstance(group, str) or group not in {"home team", "away team"}
                ):
                    anomaly(
                        "possession_group_invalid",
                        line_number,
                        frame_number,
                        retained,
                        field="group",
                        value_type=type(group).__name__,
                    )
                owner = possession.get("player_id")
                if owner is not None and (type(owner) is not int or owner <= 0):
                    anomaly(
                        "possession_player_id_invalid",
                        line_number,
                        frame_number,
                        retained,
                        field="player_id",
                        value_type=type(owner).__name__,
                    )

    matrix_sum = sum(matrix.values())
    if matrix_sum != even_rows:
        anomaly_counts["even_frame_partition_mismatch"] += 1
    return {
        "source_rows": source_rows,
        "odd_source_rows": odd_rows,
        "retained_even_rows": even_rows,
        "unclassified_rows": unclassified_rows,
        "matrix": _matrix_rows(matrix),
        "xy_detail_matrix": _xy_rows(xy_details),
        "flag_xy_detail_matrix": _flag_xy_rows(flag_xy_details),
        "player_detection_flag_counts": {key: player_flags[key] for key in _FLAGS},
        "player_detection_flag_counts_all_source_rows": {
            key: player_flags_all[key] for key in _FLAGS
        },
        "schema_anomalies": {
            "counts_all_source_rows": dict(sorted(anomaly_counts.items())),
            "counts_retained_even_rows": dict(sorted(retained_anomaly_counts.items())),
            "records": anomaly_records,
        },
        "row_observations": row_observations,
        "tracking_bytes": payload_bytes,
        "tracking_sha256": payload_hash.hexdigest(),
    }


def _tracking_entry(manifest: dict[str, object], match_id: int) -> dict[str, object]:
    matches = manifest["available_matches"]
    if not isinstance(matches, list):
        raise ValueError("invalid source match inventory")
    for raw_match in matches:
        if not isinstance(raw_match, dict) or raw_match.get("match_id") != match_id:
            continue
        files = raw_match.get("files")
        if not isinstance(files, list):
            break
        for entry in files:
            if isinstance(entry, dict) and str(entry.get("repository_path", "")).endswith(
                "_tracking_extrapolated.jsonl"
            ):
                return entry
    raise ValueError("tracking identity missing from source authority")


def _source_provenance(root: Path) -> tuple[dict[str, object], list[int]]:
    manifest = load_source_manifest()
    errors = validate_source_manifest(manifest)
    if errors:
        raise ValueError("pinned source manifest is invalid")
    pinned = manifest["upstream"]["pinned_commit"]  # type: ignore[index]
    revision = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    if revision != pinned:
        raise ValueError("source revision mismatch")
    source_files = source_preflight(root)
    expected_release = source_release_hash(manifest)
    expected_population = source_population_hash(manifest["selected_source_matches"])
    expected_manifest = manifest_hash(manifest)
    if (
        expected_release != manifest.get("source_release_hash")
        or expected_population != manifest.get("source_population_hash")
        or expected_manifest != manifest.get("manifest_sha256")
    ):
        raise ValueError("source provenance digest mismatch")
    lfs_files = [item for item in source_files if "pointer_sha256" in item]
    selected = manifest["selected_source_matches"]
    if not isinstance(selected, list) or not all(type(match_id) is int for match_id in selected):
        raise ValueError("pinned source match inventory is invalid")
    provenance = {
        "schema_id": "fpdbench.skillcorner-nullable-ball-source-provenance",
        "schema_version": "1.0.0",
        "source_repository": manifest["upstream"]["repository"],  # type: ignore[index]
        "source_revision": revision,
        "source_release_id": manifest["source_release_id"],
        "source_release_hash": expected_release,
        "source_population_hash": expected_population,
        "source_manifest_sha256": expected_manifest,
        "source_file_count": len(source_files),
        "verified_lfs_payload_count": len(lfs_files),
        "verified_lfs_payload_bytes": sum(int(item["bytes"]) for item in lfs_files),
        "source_files": source_files,
    }
    if len(source_files) != 81 or len(lfs_files) != 20:
        raise ValueError("unexpected pinned source inventory size")
    return provenance, selected


def _cell_map(rows: list[dict[str, object]], fields: tuple[str, ...]) -> dict[tuple[str, ...], int]:
    return {tuple(str(row[field]) for field in fields): int(row["count"]) for row in rows}


def _compare(
    primary: dict[str, object], verifier: dict[str, object], match_id: int
) -> list[dict[str, object]]:
    mismatches: list[dict[str, object]] = []
    for field in (
        "source_rows",
        "odd_source_rows",
        "retained_even_rows",
        "tracking_bytes",
        "tracking_sha256",
    ):
        if primary[field] != verifier[field]:
            mismatches.append(
                {
                    "match_id": match_id,
                    "category": field,
                    "primary": primary[field],
                    "verifier": verifier[field],
                }
            )
    comparisons = (
        ("matrix", ("object_presence", "detection_flag", "xy_availability")),
        ("xy_detail_matrix", ("x_state", "y_state")),
        (
            "flag_xy_detail_matrix",
            ("object_presence", "detection_flag", "x_state", "y_state"),
        ),
    )
    for field, dimensions in comparisons:
        left = _cell_map(primary[field], dimensions)  # type: ignore[arg-type]
        right = _cell_map(verifier[field], dimensions)  # type: ignore[arg-type]
        for key in sorted(set(left) | set(right)):
            if left.get(key, 0) != right.get(key, 0):
                mismatches.append(
                    {
                        "match_id": match_id,
                        "category": field,
                        "cell": key,
                        "primary": left.get(key, 0),
                        "verifier": right.get(key, 0),
                    }
                )
    if primary["player_detection_flag_counts"] != verifier["player_detection_flag_counts"]:
        mismatches.append(
            {
                "match_id": match_id,
                "category": "player_detection_flag_counts",
                "primary": primary["player_detection_flag_counts"],
                "verifier": verifier["player_detection_flag_counts"],
            }
        )
    if (
        primary["player_detection_flag_counts_all_source_rows"]
        != verifier["player_detection_flag_counts_all_source_rows"]
    ):
        mismatches.append(
            {
                "match_id": match_id,
                "category": "player_detection_flag_counts_all_source_rows",
                "primary": primary["player_detection_flag_counts_all_source_rows"],
                "verifier": verifier["player_detection_flag_counts_all_source_rows"],
            }
        )
    return mismatches


def _sum_cells(
    results: list[dict[str, object]],
    section: str,
    field: str,
    dimensions: tuple[str, ...],
) -> list[dict[str, object]]:
    totals: Counter[tuple[str, ...]] = Counter()
    for result in results:
        rows = result[section][field]
        totals.update(
            {
                tuple(str(row[dimension]) for dimension in dimensions): int(row["count"])
                for row in rows  # type: ignore[union-attr]
            }
        )
    return [
        {**dict(zip(dimensions, key, strict=True)), "count": count}
        for key, count in sorted(totals.items())
    ]


def run_audit(root: Path, destination: Path) -> dict[str, object]:
    root = private_directory(root)
    destination = private_directory(destination)
    validate_storage_boundary(root, destination)
    if any(destination.iterdir()):
        raise ValueError("restricted receipt destination is not empty")

    provenance, match_ids = _source_provenance(root)
    manifest = load_source_manifest()
    write_private(destination / "source-provenance.json", provenance)
    audit_implementation_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    verifier_path = Path(__file__).with_name("verify_skillcorner_nullable_ball.py")
    verifier_implementation_sha = hashlib.sha256(verifier_path.read_bytes()).hexdigest()
    match_results: list[dict[str, object]] = []
    all_mismatches: list[dict[str, object]] = []
    expected_by_path = {
        str(item["path"]): item
        for item in provenance["source_files"]  # type: ignore[union-attr]
    }

    for index, match_id in enumerate(match_ids, start=1):
        entry = _tracking_entry(manifest, int(match_id))
        path = str(entry["repository_path"])
        expected = expected_by_path[path]
        tracking = root / path
        with tracking.open("rb") as stream:
            primary = scan_tracking_lines(stream)
        with tracking.open("rb") as stream:
            verifier = independent_recompute(stream)
        if (
            primary["tracking_sha256"] != expected["sha256"]
            or primary["tracking_bytes"] != expected["bytes"]
            or primary["tracking_sha256"] != entry["lfs_oid_sha256"]
            or primary["tracking_bytes"] != entry["lfs_payload_size"]
            or verifier["tracking_sha256"] != expected["sha256"]
            or verifier["tracking_bytes"] != expected["bytes"]
        ):
            raise ValueError("streamed payload identity mismatch")
        mismatches = _compare(primary, verifier, int(match_id))
        if primary["unclassified_rows"] != 0:
            mismatches.append(
                {
                    "match_id": int(match_id),
                    "category": "unclassified_rows",
                    "primary": primary["unclassified_rows"],
                    "verifier": 0,
                }
            )
        result = {
            "match_id": int(match_id),
            "tracking_path": path,
            "source_payload_sha256": expected["sha256"],
            "source_payload_bytes": expected["bytes"],
            "primary": primary,
            "independent_verifier": verifier,
            "mismatches": mismatches,
        }
        write_private(destination / f"match-{index:02}.json", result)
        match_results.append(result)
        all_mismatches.extend(mismatches)

    expected_even = sum(int(result["primary"]["retained_even_rows"]) for result in match_results)
    expected_rows = sum(int(result["primary"]["source_rows"]) for result in match_results)
    expected_odd = sum(int(result["primary"]["odd_source_rows"]) for result in match_results)
    matrix = _sum_cells(
        match_results,
        "primary",
        "matrix",
        ("object_presence", "detection_flag", "xy_availability"),
    )
    xy_details = _sum_cells(match_results, "primary", "xy_detail_matrix", ("x_state", "y_state"))
    flag_xy_details = _sum_cells(
        match_results,
        "primary",
        "flag_xy_detail_matrix",
        ("object_presence", "detection_flag", "x_state", "y_state"),
    )
    anomaly_counts: Counter[str] = Counter()
    retained_anomaly_counts: Counter[str] = Counter()
    player_flag_totals: Counter[str] = Counter()
    player_flag_totals_all: Counter[str] = Counter()
    for result in match_results:
        primary = result["primary"]
        anomalies = primary["schema_anomalies"]
        anomaly_counts.update(anomalies["counts_all_source_rows"])
        retained_anomaly_counts.update(anomalies["counts_retained_even_rows"])
        player_flag_totals.update(primary["player_detection_flag_counts"])
        player_flag_totals_all.update(primary["player_detection_flag_counts_all_source_rows"])

    matrix_total = sum(int(row["count"]) for row in matrix)
    null_finite = next(
        int(row["count"])
        for row in matrix
        if row["object_presence"] == "present"
        and row["detection_flag"] == "null"
        and row["xy_availability"] == "both_finite"
    )
    false_flag_any_explicit_null = sum(
        int(row["count"])
        for row in flag_xy_details
        if row["object_presence"] == "present"
        and row["detection_flag"] == "false"
        and "null" in {row["x_state"], row["y_state"]}
    )
    false_both_null = sum(
        int(row["count"])
        for row in flag_xy_details
        if row["object_presence"] == "present"
        and row["detection_flag"] == "false"
        and row["x_state"] == "null"
        and row["y_state"] == "null"
    )
    invariants = {
        "match_count_is_20": len(match_results) == 20,
        "all_rows_partition_even_and_odd": expected_rows == expected_even + expected_odd,
        "aggregate_matrix_equals_retained_even_rows": matrix_total == expected_even,
        "every_match_reconciled": all(
            result["primary"]["source_rows"]
            == result["primary"]["retained_even_rows"] + result["primary"]["odd_source_rows"]
            and sum(int(row["count"]) for row in result["primary"]["matrix"])
            == result["primary"]["retained_even_rows"]
            for result in match_results
        ),
        "all_independent_cells_agree": not all_mismatches,
        "source_file_count_is_81": provenance["source_file_count"] == 81,
        "lfs_payload_count_is_20": provenance["verified_lfs_payload_count"] == 20,
    }
    header_failures = {
        "invalid_json_row",
        "frame_not_object",
        "frame_number_invalid",
        "frame_number_negative",
        "frame_order_invalid",
        "frame_field_missing",
        "frame_field_unexpected",
        "timestamp_invalid",
        "period_invalid",
    }
    schema_failures = any(value > 0 for value in retained_anomaly_counts.values()) or any(
        anomaly_counts[key] > 0 for key in header_failures
    )
    receipt: dict[str, object] = {
        "schema_id": "fpdbench.skillcorner-nullable-ball-audit",
        "schema_version": "1.0.0",
        "audit_status": "PASS" if all(invariants.values()) else "FAIL",
        "source_integrity_status": "PASS",
        "independent_replication_status": "PASS" if not all_mismatches else "FAIL",
        "current_measurement_schema_conformity": "FAIL" if schema_failures else "PASS",
        "population_qualification": "NOT_ATTEMPTED",
        "audited_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "source_revision": provenance["source_revision"],
        "source_manifest_sha256": provenance["source_manifest_sha256"],
        "source_release_hash": provenance["source_release_hash"],
        "source_population_hash": provenance["source_population_hash"],
        "source_file_count": provenance["source_file_count"],
        "lfs_payload_count": provenance["verified_lfs_payload_count"],
        "lfs_payload_bytes": provenance["verified_lfs_payload_bytes"],
        "source_rows": expected_rows,
        "odd_source_rows": expected_odd,
        "retained_even_rows": expected_even,
        "aggregate_matrix": matrix,
        "aggregate_xy_detail_matrix": xy_details,
        "aggregate_flag_xy_detail_matrix": flag_xy_details,
        "null_flag_both_finite_xy": null_finite,
        "false_flag_any_explicit_null_xy_coordinate": false_flag_any_explicit_null,
        "false_flag_both_null_xy": false_both_null,
        "player_detection_flag_counts": {key: player_flag_totals[key] for key in _FLAGS},
        "player_detection_flag_counts_all_source_rows": {
            key: player_flag_totals_all[key] for key in _FLAGS
        },
        "schema_anomaly_counts_all_source_rows": dict(sorted(anomaly_counts.items())),
        "schema_anomaly_counts_retained_even_rows": dict(sorted(retained_anomaly_counts.items())),
        "invariants": invariants,
        "mismatch_count": len(all_mismatches),
        "mismatches": all_mismatches,
        "audit_implementation": {
            "id": "audit_skillcorner_nullable_ball.scan_tracking_lines/v1",
            "sha256": audit_implementation_sha,
        },
        "independent_verifier": {
            "id": "verify_skillcorner_nullable_ball.recompute/v1",
            "sha256": verifier_implementation_sha,
        },
        "source_preflight_implementation_sha256": hashlib.sha256(
            Path(__file__).with_name("qualify_skillcorner_source.py").read_bytes()
        ).hexdigest(),
        "source_verification_runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "implementation_git_revision": subprocess.check_output(
                [
                    "git",
                    "-C",
                    str(Path(__file__).resolve().parents[1]),
                    "rev-parse",
                    "HEAD",
                ],
                text=True,
            ).strip(),
        },
        "per_match_receipt_sha256": [
            hashlib.sha256(canonical_bytes(result)).hexdigest() for result in match_results
        ],
        "source_provenance_receipt_sha256": hashlib.sha256(canonical_bytes(provenance)).hexdigest(),
    }
    receipt["receipt_sha256"] = hashlib.sha256(canonical_bytes(receipt)).hexdigest()
    write_private(destination / "audit-receipt.json", receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--restricted-output", required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        receipt = run_audit(args.source_root, args.restricted_output)
    except Exception:
        try:
            destination = private_directory(args.restricted_output)
            if not any(destination.iterdir()):
                write_private(
                    destination / "failure.json",
                    {
                        "status": "INCONCLUSIVE",
                        "diagnostic": traceback.format_exc(),
                    },
                )
        except Exception:
            pass
        raise SystemExit(
            "INCONCLUSIVE: restricted audit failed; diagnostics remain private"
        ) from None
    if receipt["audit_status"] != "PASS":
        raise SystemExit("FAIL: independent audit did not reconcile; diagnostics remain private")
    print("PASS: pinned source integrity and independent audit replication verified")


if __name__ == "__main__":
    main()
