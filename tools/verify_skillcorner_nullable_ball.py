"""Independent streaming verifier for the nullable-ball audit."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Iterable

_ABSENT = object()
_FLAGS = ("true", "false", "null", "missing", "invalid")
_XY = ("both_finite", "partial", "both_missing", "invalid")
_COORDINATE_STATES = ("finite", "null", "missing", "nonfinite", "invalid")


def _flag(ball: object, presence: str) -> str:
    if presence == "absent":
        return "not_applicable"
    if presence == "missing_key":
        return "missing"
    if not isinstance(ball, dict):
        return "invalid"
    value = ball.get("is_detected", _ABSENT)
    if value is _ABSENT:
        return "missing"
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    return "invalid"


def _coordinate(value: object, exists: bool) -> str:
    if not exists:
        return "missing"
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "invalid"
    if isinstance(value, int | float):
        try:
            return "finite" if math.isfinite(value) else "nonfinite"
        except OverflowError:
            return "invalid"
    return "invalid"


def _matrix_cells(counts: Counter[tuple[str, str, str]]) -> list[dict[str, object]]:
    cells = [("absent", "not_applicable", "not_applicable")]
    cells.append(("missing_key", "missing", "invalid"))
    cells.extend(("present", flag, xy) for flag in _FLAGS for xy in _XY)
    return [
        {
            "object_presence": presence,
            "detection_flag": flag,
            "xy_availability": xy,
            "count": counts[(presence, flag, xy)],
        }
        for presence, flag, xy in cells
    ]


def _flag_xy_cells(counts: Counter[tuple[str, str, str, str]]) -> list[dict[str, object]]:
    cells = [("absent", "not_applicable", "not_applicable", "not_applicable")]
    cells.append(("missing_key", "missing", "missing", "missing"))
    cells.extend(
        ("present", flag, x_state, y_state)
        for flag in _FLAGS
        for x_state in _COORDINATE_STATES
        for y_state in _COORDINATE_STATES
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


def recompute(lines: Iterable[bytes]) -> dict[str, object]:
    """Reparse tracking bytes and independently recompute every retained-frame cell."""
    matrix: Counter[tuple[str, str, str]] = Counter()
    flag_xy: Counter[tuple[str, str, str, str]] = Counter()
    xy_details: Counter[str] = Counter()
    player_flags: Counter[str] = Counter()
    player_flags_all: Counter[str] = Counter()
    source_rows = even_rows = odd_rows = 0
    previous_frame = -1
    payload_hash = hashlib.sha256()
    payload_bytes = 0

    for raw in lines:
        payload_hash.update(raw)
        payload_bytes += len(raw)
        row = json.loads(raw)
        if not isinstance(row, dict):
            raise ValueError("source row must be an object")
        frame = row.get("frame")
        if type(frame) is not int or frame < 0 or frame <= previous_frame:
            raise ValueError("source frame sequence is invalid")
        previous_frame = frame
        source_rows += 1
        players = row.get("player_data")
        if isinstance(players, list):
            for player in players:
                value = (
                    player.get("is_detected", _ABSENT)
                    if isinstance(player, dict)
                    else "invalid-entry"
                )
                if value is True:
                    category = "true"
                elif value is False:
                    category = "false"
                elif value is _ABSENT:
                    category = "missing"
                elif value is None:
                    category = "null"
                else:
                    category = "invalid"
                player_flags_all[category] += 1
                if frame % 2 == 0:
                    player_flags[category] += 1
        if frame % 2:
            odd_rows += 1
            continue
        even_rows += 1

        if "ball_data" not in row:
            presence, ball = "missing_key", _ABSENT
            flag, xy_kind, x_state, y_state = "missing", "invalid", "missing", "missing"
        else:
            ball = row["ball_data"]
            presence = "absent" if ball is None else "present"
            if presence == "absent":
                flag, xy_kind = "not_applicable", "not_applicable"
                x_state = y_state = "not_applicable"
            elif not isinstance(ball, dict):
                flag, xy_kind = "invalid", "invalid"
                x_state = y_state = "invalid"
            else:
                x_state = _coordinate(ball.get("x"), "x" in ball)
                y_state = _coordinate(ball.get("y"), "y" in ball)
                if x_state == y_state == "finite":
                    xy_kind = "both_finite"
                elif (x_state == "finite" and y_state in ("null", "missing")) or (
                    y_state == "finite" and x_state in ("null", "missing")
                ):
                    xy_kind = "partial"
                elif x_state in ("null", "missing") and y_state in ("null", "missing"):
                    xy_kind = "both_missing"
                else:
                    xy_kind = "invalid"
                xy_details[f"{x_state}|{y_state}"] += 1
                flag = _flag(ball, presence)
        matrix[(presence, flag, xy_kind)] += 1
        flag_xy[(presence, flag, x_state, y_state)] += 1

    cells = _matrix_cells(matrix)
    detail_cells = [
        {"x_state": x, "y_state": y, "count": xy_details[f"{x}|{y}"]}
        for x in _COORDINATE_STATES
        for y in _COORDINATE_STATES
    ]
    return {
        "source_rows": source_rows,
        "odd_source_rows": odd_rows,
        "retained_even_rows": even_rows,
        "matrix": cells,
        "flag_xy_detail_matrix": _flag_xy_cells(flag_xy),
        "xy_detail_matrix": detail_cells,
        "player_detection_flag_counts": {key: player_flags[key] for key in _FLAGS},
        "player_detection_flag_counts_all_source_rows": {
            key: player_flags_all[key] for key in _FLAGS
        },
        "tracking_bytes": payload_bytes,
        "tracking_sha256": payload_hash.hexdigest(),
    }
