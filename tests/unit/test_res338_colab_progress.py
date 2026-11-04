from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
from res338_colab_progress import advance, initialize, verify  # noqa: E402


def test_progress_requires_drive_readback_before_completion(tmp_path: Path) -> None:
    index_path, _ = initialize(
        tmp_path / "progress",
        reference_sha256="1" * 64,
        runtime_sha256="2" * 64,
        amendment_sha256="3" * 64,
        accelerator={"name": "synthetic"},
        compute_unit_balance=256.78,
    )
    initial = verify(index_path)
    assert initial["completed_fit_count"] == 0

    import json

    index = json.loads(index_path.read_text())
    run_id = index["fits"][0]["run_id"]
    running_path, _ = advance(
        index_path,
        tmp_path / "progress",
        run_id,
        "RUNNING",
        attempt_number=1,
        compute_unit_balance=256.78,
        compute_unit_rate_per_hour=10.0,
    )
    with pytest.raises(ValueError, match="readbacks"):
        advance(
            running_path,
            tmp_path / "progress",
            run_id,
            "COMPLETED_AND_VERIFIED",
            attempt_number=1,
            checkpoint_drive_file_id="checkpoint-id",
            receipt_drive_file_id="receipt-id",
        )
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(mode=0o700)
    checkpoint = artifacts / "checkpoint.pt"
    receipt = artifacts / "receipt.json"
    checkpoint_readback = artifacts / "checkpoint.readback.pt"
    receipt_readback = artifacts / "receipt.readback.json"
    checkpoint.write_bytes(b"synthetic checkpoint")
    receipt.write_bytes(b"synthetic receipt")
    checkpoint_readback.write_bytes(checkpoint.read_bytes())
    receipt_readback.write_bytes(receipt.read_bytes())
    for path in (checkpoint, receipt, checkpoint_readback, receipt_readback):
        path.chmod(0o600)
    completed_path, _ = advance(
        running_path,
        tmp_path / "progress",
        run_id,
        "COMPLETED_AND_VERIFIED",
        attempt_number=1,
        checkpoint_path=checkpoint,
        receipt_path=receipt,
        checkpoint_readback_path=checkpoint_readback,
        receipt_readback_path=receipt_readback,
        checkpoint_drive_file_id="checkpoint-id",
        receipt_drive_file_id="receipt-id",
    )
    assert verify(completed_path)["completed_fit_count"] == 1


def test_retry_requires_confirmed_infrastructure_and_excluded_oom(tmp_path: Path) -> None:
    index_path, _ = initialize(
        tmp_path / "progress",
        reference_sha256="1" * 64,
        runtime_sha256="2" * 64,
        amendment_sha256="3" * 64,
        accelerator={"name": "synthetic"},
        compute_unit_balance=256.78,
    )
    import json

    run_id = json.loads(index_path.read_text())["fits"][0]["run_id"]
    running_path, _ = advance(
        index_path,
        tmp_path / "progress",
        run_id,
        "RUNNING",
        attempt_number=1,
        compute_unit_balance=256.78,
        compute_unit_rate_per_hour=10.0,
    )
    with pytest.raises(ValueError, match="OOM exclusion"):
        advance(
            running_path,
            tmp_path / "progress",
            run_id,
            "INTERRUPTED_RETRY_ELIGIBLE",
            attempt_number=1,
            infrastructure_confirmed=True,
            oom_excluded=False,
            reason="runtime lost",
        )
    retry_path, _ = advance(
        running_path,
        tmp_path / "progress",
        run_id,
        "INTERRUPTED_RETRY_ELIGIBLE",
        attempt_number=1,
        infrastructure_confirmed=True,
        oom_excluded=True,
        reason="Colab session ended and CLI confirmed session absence",
    )
    second_attempt, _ = advance(
        retry_path,
        tmp_path / "progress",
        run_id,
        "RUNNING",
        attempt_number=2,
        compute_unit_balance=250.0,
        compute_unit_rate_per_hour=10.0,
    )
    with pytest.raises(ValueError, match="invalid progress transition"):
        advance(
            second_attempt,
            tmp_path / "progress",
            run_id,
            "RUNNING",
            attempt_number=3,
        )
