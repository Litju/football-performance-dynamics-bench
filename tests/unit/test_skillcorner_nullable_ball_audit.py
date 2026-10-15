"""Synthetic only; real source rows and receipts stay outside tests and Git."""

import json
import runpy
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2] / "tools"


def _modules():
    tool_path = str(TOOLS)
    sys.path.insert(0, tool_path)
    try:
        audit = runpy.run_path(str(TOOLS / "audit_skillcorner_nullable_ball.py"))
        verifier = runpy.run_path(str(TOOLS / "verify_skillcorner_nullable_ball.py"))
        return audit, verifier
    finally:
        sys.path.remove(tool_path)


def _frame(number, ball, players=None):
    return {
        "frame": number,
        "timestamp": f"00:00:{number // 10:02}.00",
        "period": 1,
        "ball_data": ball,
        "possession": None,
        "image_corners_projection": None,
        "player_data": players or [],
    }


def _lines():
    frames = [
        _frame(0, None),
        _frame(
            1,
            {"x": None, "y": None, "is_detected": None},
            [{"player_id": 4, "x": 0, "y": 0, "is_detected": None}],
        ),
        _frame(2, {"x": 1, "y": 2, "z": None, "is_detected": True}),
        _frame(
            4,
            {"x": 3, "y": None, "z": None, "is_detected": None},
            [
                {"player_id": 1, "x": 1, "y": 1, "is_detected": 1},
                {"player_id": 2, "x": None, "y": None},
            ],
        ),
        _frame(6, {"x": None, "y": None, "z": None}),
        _frame(8, {"x": None, "y": None, "z": None, "is_detected": False}),
        _frame(10, {"x": float("inf"), "y": "bad", "z": None, "is_detected": 0}),
        _frame(12, None),
        _frame(14, None, [{"player_id": 3, "x": 0, "y": 0, "is_detected": None}]),
        _frame(16, {"x": None, "y": 4, "z": None, "is_detected": True}),
        _frame(18, {"x": 5, "y": None, "z": None, "is_detected": False}),
        _frame(20, {"x": 5, "y": 6, "z": None, "is_detected": None}),
    ]
    frames[7].pop("ball_data")
    return [json.dumps(frame).encode() + b"\n" for frame in frames]


def _count(matrix, presence, flag, xy):
    return next(
        cell["count"]
        for cell in matrix
        if cell["object_presence"] == presence
        and cell["detection_flag"] == flag
        and cell["xy_availability"] == xy
    )


def test_streamed_matrix_and_independent_verifier_agree_on_every_category():
    audit, verifier_module = _modules()
    primary = audit["scan_tracking_lines"](_lines())
    verifier = verifier_module["recompute"](_lines())

    assert audit["_compare"](primary, verifier, 0) == []
    assert primary["source_rows"] == 12
    assert primary["odd_source_rows"] == 1
    assert primary["retained_even_rows"] == 11
    assert sum(row["count"] for row in primary["matrix"]) == 11
    assert len(primary["matrix"]) == 22
    assert _count(primary["matrix"], "absent", "not_applicable", "not_applicable") == 2
    assert _count(primary["matrix"], "missing_key", "missing", "invalid") == 1
    assert _count(primary["matrix"], "present", "null", "both_finite") == 1
    assert _count(primary["matrix"], "present", "null", "partial") == 1
    assert _count(primary["matrix"], "present", "missing", "both_missing") == 1
    assert _count(primary["matrix"], "present", "false", "both_missing") == 1
    assert _count(primary["matrix"], "present", "false", "partial") == 1
    assert _count(primary["matrix"], "present", "invalid", "invalid") == 1
    assert len(primary["flag_xy_detail_matrix"]) == 127
    assert len(primary["xy_detail_matrix"]) == 25
    assert primary["player_detection_flag_counts"] == {
        "true": 0,
        "false": 0,
        "null": 1,
        "missing": 1,
        "invalid": 1,
    }
    assert primary["player_detection_flag_counts_all_source_rows"]["null"] == 2
    assert (
        primary["schema_anomalies"]["counts_retained_even_rows"]["player_detection_flag_null"] == 1
    )
    assert (
        primary["schema_anomalies"]["counts_retained_even_rows"]["player_detection_flag_missing"]
        == 1
    )
    assert (
        primary["schema_anomalies"]["counts_retained_even_rows"]["player_detection_flag_invalid"]
        == 1
    )
    assert primary["schema_anomalies"]["counts_all_source_rows"]["player_detection_flag_null"] == 2
    assert any(
        row["source_frame"] == 20
        and row["detection_flag"] == "null"
        and row["xy_availability"] == "both_finite"
        for row in primary["row_observations"]
    )


def test_coordinate_states_distinguish_partial_null_and_invalid_values():
    audit, _ = _modules()
    assert audit["coordinate_state"](1, True) == "finite"
    assert audit["coordinate_state"](None, True) == "null"
    assert audit["coordinate_state"](None, False) == "missing"
    assert audit["coordinate_state"](float("inf"), True) == "nonfinite"
    assert audit["coordinate_state"]("1", True) == "invalid"
    assert audit["coordinate_state"](True, True) == "invalid"
    assert audit["xy_availability"]("finite", "null") == "partial"
    assert audit["xy_availability"]("null", "missing") == "both_missing"
    assert audit["xy_availability"]("finite", "invalid") == "invalid"
