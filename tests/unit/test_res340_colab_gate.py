from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import res340_colab_gate as gate  # noqa: E402


def test_read_only_colab_usage_parser_and_no_approval_gate() -> None:
    snapshot = gate.parse_usage_snapshot(
        "Current balance: 87.58 compute units\nUsage rate: 0.00/hr\nActive assignments: 0\n"
    )
    result = gate.validate_preflight(snapshot, None)

    assert snapshot == {
        "compute_unit_balance": 87.58,
        "compute_unit_rate_per_hour": 0.0,
        "active_assignments": 0,
    }
    assert result["status"] == "OWNER_APPROVAL_REQUIRED"
    assert result["allocation_started"] is False
    assert result["fit_execution_authorized"] is False


def test_active_a100_parser_ignores_cpu_sessions() -> None:
    sessions = gate.parse_active_a100_sessions(
        "[res338-fits] gpu-a100-id | Hardware: A100 | Shape: Standard | Variant: GPU\n"
        "[cpu-diagnostics] cpu-id | Hardware: CPU | Shape: Standard | Variant: CPU\n"
    )
    assert sessions == ["res338-fits"]
