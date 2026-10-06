import json
from pathlib import Path

from fpdbench.cli import main
from fpdbench.provenance.scientific_lock import LOCK_SCHEMA_VERSION


def _state() -> dict[str, object]:
    digest = "a" * 64
    return {
        "lock_schema_version": LOCK_SCHEMA_VERSION,
        "benchmark_id": "conditional_multi_agent_motion_prediction/absolute_position_prediction",
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
    benchmark_lines = capsys.readouterr().out.splitlines()  # type: ignore[attr-defined]
    assert len(benchmark_lines) == 2
    assert all("conditional_multi_agent_motion_prediction/" in line for line in benchmark_lines)

    assert main(["families", "list"]) == 0
    assert len(capsys.readouterr().out.splitlines()) == 4  # type: ignore[attr-defined]

    assert main(["research-objects", "list"]) == 0
    object_lines = capsys.readouterr().out.splitlines()  # type: ignore[attr-defined]
    assert len(object_lines) == 6
    assert any("\tresearch_family\tunrecoverable" in line for line in object_lines)

    assert main(["research-objects", "describe", "future_response_forecasting"]) == 0
    assert '"research_object_type": "research_family"' in capsys.readouterr().out  # type: ignore[attr-defined]
    assert (
        main(
            [
                "benchmarks",
                "describe",
                "conditional_multi_agent_motion_prediction/origin_relative_displacement_prediction",
            ]
        )
        == 0
    )
    assert "origin_relative_displacement_prediction" in capsys.readouterr().out  # type: ignore[attr-defined]
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
