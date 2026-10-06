import json
from pathlib import Path

from fpdbench.cli import main
from fpdbench.provenance.scientific_lock import LOCK_SCHEMA_VERSION


def _state() -> dict[str, object]:
    digest = "a" * 64
    return {
        "lock_schema_version": LOCK_SCHEMA_VERSION,
        "benchmark_id": "workload_performance_state/signed_tangential_acceleration_estimation",
        "benchmark_definition_hash": digest,
        "data_release_id": "synthetic-evidence-only",
        "data_release_version": "1.0.0",
        "data_manifest_hash": digest,
        "data_state_id": "neutral-data-state",
        "split_protocol_id": "grouped-validation",
        "split_protocol_version": "1.0.0",
        "split_protocol_hash": digest,
        "evaluator_id": "full_row_rmse",
        "evaluator_version": "1.0.0",
        "evaluator_hash": digest,
        "schema_version": "1.0.0",
        "schema_hash": digest,
        "fixture_manifest_hash": digest,
        "scientific_provenance_snapshot": {
            "snapshot_id": "test-fixture",
            "snapshot_hash": digest,
            "citations": [],
        },
    }


def test_cli_list_describe_and_validate(capsys: object) -> None:
    root = Path(__file__).resolve().parents[2]
    assert main(["benchmarks", "list"]) == 0
    assert "whole_session_performance_state" in capsys.readouterr().out  # type: ignore[attr-defined]
    assert main(["benchmarks", "describe", "future_response_forecasting"]) == 0
    assert "unrecoverable" in capsys.readouterr().out  # type: ignore[attr-defined]
    assert main(["validate-naming", "--root", str(root)]) == 0
    assert main(["validate", "--root", str(root)]) == 0


def test_cli_computes_and_verifies_scientific_lock(tmp_path: Path, capsys: object) -> None:
    source = tmp_path / "state.json"
    result = tmp_path / "lock.json"
    source.write_text(json.dumps(_state()))
    assert main(["lock", "compute", str(source), "--output", str(result)]) == 0
    lock = json.loads(result.read_text())
    assert lock["scientific_lock_hash"] != "a" * 64
    assert main(["lock", "verify", str(result)]) == 0
    assert "scientific lock valid" in capsys.readouterr().out  # type: ignore[attr-defined]
