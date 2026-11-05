from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import train_res338_final_fits as trainer  # noqa: E402
from res338_colab_progress import advance, initialize, verify  # noqa: E402

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.learned_deepsets import (  # noqa: E402
    PerTargetContextDeepSetsMLP,
)


def _initialize(directory: Path, *, balance: float = 2400.0) -> Path:
    accelerator = directory.parent / "accelerator.json"
    accelerator.write_text('{"name":"synthetic A100"}')
    accelerator.chmod(0o600)
    path, _ = initialize(
        directory,
        reference_sha256="1" * 64,
        runtime_sha256="2" * 64,
        amendment_sha256="3" * 64,
        accelerator=json.loads(accelerator.read_text()),
        compute_unit_balance=balance,
        fit_role="lomo",
        compute_unit_spend_cap=2400.0,
        compute_unit_rate_per_hour=6.73,
        owner_authorization_sha256="4" * 64,
        final_checkpoint_sha256s=[f"{index + 100:064x}" for index in range(18)],
        lomo_cache_manifest_sha256="5" * 64,
        lomo_cache_ledger_sha256="6" * 64,
        compute_unit_balance_at_start=2400.0,
    )
    return path


def test_lomo_progress_refuses_to_initialize_without_full_budget(tmp_path: Path) -> None:
    progress_root = tmp_path / "progress"
    with pytest.raises(ValueError, match="fixed campaign cap"):
        _initialize(progress_root, balance=94.31)
    assert not progress_root.exists()


def test_lomo_progress_freezes_all_ids_and_reserves_full_remaining_campaign(
    tmp_path: Path,
) -> None:
    progress_root = tmp_path / "progress"
    initial = _initialize(progress_root)
    report = verify(initial)
    index = json.loads(initial.read_bytes())
    run_id = index["fits"][0]["run_id"]

    assert report["required_fit_count"] == 216
    assert report["completed_fit_count"] == 0
    assert index["fit_matrix_sha256"]
    assert len(index["fits"]) == 216
    assert all(fit["status"] == "NOT_STARTED" for fit in index["fits"])

    with pytest.raises(ValueError, match="remaining balance cannot cover"):
        advance(
            initial,
            progress_root,
            run_id,
            "RUNNING",
            attempt_number=1,
            compute_unit_balance=1800.0,
            compute_unit_rate_per_hour=6.73,
        )
    assert hashlib.sha256(initial.read_bytes()).hexdigest() == initial.stem.removeprefix(
        "progress-index-"
    )

    running, _ = advance(
        initial,
        progress_root,
        run_id,
        "RUNNING",
        attempt_number=1,
        compute_unit_balance=2400.0,
        compute_unit_rate_per_hour=6.73,
    )
    assert verify(running)["completed_fit_count"] == 0


def test_lomo_retry_keeps_same_fit_identity_and_requires_infrastructure_proof(
    tmp_path: Path,
) -> None:
    progress_root = tmp_path / "progress"
    initial = _initialize(progress_root)
    run_id = json.loads(initial.read_bytes())["fits"][0]["run_id"]
    running, _ = advance(
        initial,
        progress_root,
        run_id,
        "RUNNING",
        attempt_number=1,
        compute_unit_balance=2400.0,
        compute_unit_rate_per_hour=6.73,
    )
    with pytest.raises(ValueError, match="OOM exclusion"):
        advance(
            running,
            progress_root,
            run_id,
            "INTERRUPTED_RETRY_ELIGIBLE",
            attempt_number=1,
            infrastructure_confirmed=True,
            oom_excluded=False,
            reason="synthetic interruption",
        )
    retryable, _ = advance(
        running,
        progress_root,
        run_id,
        "INTERRUPTED_RETRY_ELIGIBLE",
        attempt_number=1,
        infrastructure_confirmed=True,
        oom_excluded=True,
        reason="synthetic Colab session interruption; OOM excluded",
    )
    retry, _ = advance(
        retryable,
        progress_root,
        run_id,
        "RUNNING",
        attempt_number=2,
        compute_unit_balance=2299.0,
        compute_unit_rate_per_hour=6.73,
    )
    current = json.loads(retry.read_bytes())
    assert current["fits"][0]["run_id"] == run_id
    assert current["fits"][0]["attempt_count"] == 2
    assert current["fits"][0]["attempts"][0]["reason"] == (
        "synthetic Colab session interruption; OOM excluded"
    )


def test_progress_requires_receipt_checkpoint_identity_and_drive_readback(
    tmp_path: Path,
) -> None:
    progress_root = tmp_path / "progress"
    initial = _initialize(progress_root)
    index = json.loads(initial.read_bytes())
    fit = index["fits"][0]
    run_id = fit["run_id"]
    running, _ = advance(
        initial,
        progress_root,
        run_id,
        "RUNNING",
        attempt_number=1,
        compute_unit_balance=2400.0,
        compute_unit_rate_per_hour=6.73,
    )
    artifacts = tmp_path / "private-artifacts"
    artifacts.mkdir(mode=0o700)
    train_ids = fit["train_match_ids"]
    validation_ids = fit["validation_match_ids"]
    model = PerTargetContextDeepSetsMLP(str(fit["information_regime"]))
    checkpoint = artifacts / "checkpoint.pt"
    checkpoint_sha = trainer.save_checkpoint_atomically(
        checkpoint,
        {
            "metadata": {
                "run_id": run_id,
                "configuration_sha256": fit["configuration_sha256"],
                "selected_step": 100,
                "attempt_number": 1,
            },
            "state_dict": model.state_dict(),
        },
    )
    receipt_path = artifacts / "receipt.json"
    receipt = {
        "run_id": run_id,
        "status": "completed",
        "fit_role": "lomo",
        "lomo_fold_id": fit["lomo_fold_id"],
        "lomo_held_out_match_id": fit["lomo_held_out_match_id"],
        "information_regime": fit["information_regime"],
        "target_representation": fit["target_representation"],
        "seed": fit["seed"],
        "train_match_ids": train_ids,
        "validation_match_ids": validation_ids,
        "plan_sha256": index["plan_sha256"],
        "protocol_sha256": index["protocol_sha256"],
        "population_manifest_sha256": trainer.RESEARCH_MANIFEST_SHA256,
        "configuration_sha256": fit["configuration_sha256"],
        "checkpoint_sha256": checkpoint_sha,
        "attempt_number": 1,
    }
    trainer._atomic_json(receipt_path, receipt)
    checkpoint_readback = artifacts / "checkpoint-readback.pt"
    receipt_readback = artifacts / "receipt-readback.json"
    checkpoint_readback.write_bytes(checkpoint.read_bytes())
    receipt_readback.write_bytes(receipt_path.read_bytes())
    for path in (checkpoint_readback, receipt_readback):
        path.chmod(0o600)

    with pytest.raises(ValueError, match="Drive readbacks"):
        advance(
            running,
            progress_root,
            run_id,
            "COMPLETED_AND_VERIFIED",
            attempt_number=1,
            checkpoint_path=checkpoint,
            receipt_path=receipt_path,
        )
    completed, _ = advance(
        running,
        progress_root,
        run_id,
        "COMPLETED_AND_VERIFIED",
        attempt_number=1,
        checkpoint_path=checkpoint,
        receipt_path=receipt_path,
        checkpoint_readback_path=checkpoint_readback,
        receipt_readback_path=receipt_readback,
        checkpoint_drive_file_id="synthetic-checkpoint-file",
        receipt_drive_file_id="synthetic-receipt-file",
    )

    assert verify(completed)["completed_fit_count"] == 1
