from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
import train_res338_final_fits as trainer  # noqa: E402
from res338_cuda_qualification import (  # noqa: E402
    INFORMATION_REGIMES,
    TARGET_PLAYERS,
    _inputs,
    _truth_and_mask,
)


def test_cuda_qualification_uses_one_directed_scene_panel() -> None:
    for regime in INFORMATION_REGIMES:
        inputs = _inputs(np.random.default_rng(1729), 4, regime)
        assert inputs.target_history.shape == (4, TARGET_PLAYERS, 78)
        assert inputs.target_side.shape == (4,)

    truth, mask = _truth_and_mask(np.random.default_rng(2718), 4)
    assert truth.shape == (4, TARGET_PLAYERS, 15, 2)
    assert mask.shape == (4, TARGET_PLAYERS, 15)


def test_cuda_preflight_verifies_the_recorded_gpu_wall_budget(tmp_path: Path) -> None:
    plan, protocol, _ = trainer._frozen_split_and_authorities()
    report = {
        "schema_id": "fpdbench.res338-cuda-qualification",
        "schema_version": "1.0.0",
        "status": "PASSED",
        "synthetic_only": True,
        "real_fit_count": 0,
        "real_evaluation_metrics": 0,
        "evaluation_match_features": 0,
        "real_tracking_rows_read_for_features": 0,
        "research_manifest_sha256": trainer.RESEARCH_MANIFEST_SHA256,
        "plan_sha256": plan["plan_sha256"],
        "protocol_sha256": protocol["protocol_sha256"],
        "code_sha": "a" * 40,
        "runtime_sha256": "b" * 64,
        "device": "cuda",
        "cuda_qualification": {
            "numerical_agreement": "PASSED",
            "deterministic_replay": "BITWISE_EQUAL",
            "numerical_tolerances": {
                "prediction_and_masked_ade": {"rtol": 1e-4, "atol": 1e-5},
                "gradient_and_adamw_update": {"rtol": 1e-3, "atol": 1e-5},
            },
            "per_regime": {regime: {} for regime in INFORMATION_REGIMES},
        },
        "synthetic_optimization_steps": trainer.MAX_STEPS,
        "synthetic_validation_checks": trainer.MAX_STEPS // trainer.VALIDATION_CADENCE,
        "synthetic_full_cadence_forced": True,
        "synthetic_fit_cpu_seconds": 1.0,
        "synthetic_fit_wall_seconds": 1.0,
        "synthetic_peak_rss_bytes": 1,
        "synthetic_peak_cuda_memory_bytes": 1,
        "effective_worker_memory_limit_bytes": trainer.MAX_WORKER_RSS_BYTES,
        "estimated_private_cache_bytes_with_32_tracks_per_team": 1,
        "available_disk_bytes": trainer.GPU_PRIVATE_DISK_RESERVE_BYTES + 1,
    }
    path = tmp_path / "cuda-qualification.json"
    path.write_bytes(trainer._canonical(report))
    path.chmod(0o600)

    _, verified, _ = trainer._verify_toy_preflight(
        path,
        plan_sha256=str(plan["plan_sha256"]),
        protocol_sha256=str(protocol["protocol_sha256"]),
        code_sha="a" * 40,
        runtime_sha256="b" * 64,
        device="cuda",
    )
    assert verified["synthetic_fit_wall_seconds"] == 1.0
    report["synthetic_fit_wall_seconds"] = trainer.GPU_FIT_WALL_BUDGET_SECONDS + 1
    path.write_bytes(trainer._canonical(report))
    with pytest.raises(ValueError, match="synthetic CUDA qualification"):
        trainer._verify_toy_preflight(
            path,
            plan_sha256=str(plan["plan_sha256"]),
            protocol_sha256=str(protocol["protocol_sha256"]),
            code_sha="a" * 40,
            runtime_sha256="b" * 64,
            device="cuda",
        )
