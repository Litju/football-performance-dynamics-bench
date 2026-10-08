from pathlib import Path

from fpdbench.cli import main
from fpdbench.reproducibility import (
    ARTIFACT_AVAILABILITY,
    CAPABILITY_MATRIX,
    SNAPSHOT_RELATIVE_PATH,
    build_reproducibility_snapshot,
    check_reproducibility,
    render_reproducibility_snapshot,
)


def test_public_reproducibility_snapshot_and_capability_boundary(capsys: object) -> None:
    root = Path(__file__).resolve().parents[2]
    first = render_reproducibility_snapshot(root)
    second = render_reproducibility_snapshot(root)
    snapshot = build_reproducibility_snapshot(root)

    assert first == second == (root / SNAPSHOT_RELATIVE_PATH).read_bytes()
    assert snapshot["schema_id"] == "fpdbench.reproducibility-snapshot"
    assert snapshot["schema_version"] == "1.0.0"
    assert len(snapshot["historical_results"]) == 19  # type: ignore[arg-type]
    assert snapshot["private_result_records_count"] == 0
    assert dict(CAPABILITY_MATRIX)["historical_source_to_full_fixture_regeneration"] == (
        "UNAVAILABLE_PUBLIC_ARTIFACT"
    )
    assert dict(CAPABILITY_MATRIX)["j03wmx_private_qualification_truth_evaluation"] == (
        "FORBIDDEN_PRIVATE_TRUTH"
    )
    assert dict(ARTIFACT_AVAILABILITY)["historical_learned_checkpoint_bytes"] == (
        "UNAVAILABLE_PUBLIC_ARTIFACT"
    )
    assert check_reproducibility(root) == ()

    assert main(["reproducibility", "check"]) == 0
    assert '"status": "passed"' in capsys.readouterr().out  # type: ignore[attr-defined]
