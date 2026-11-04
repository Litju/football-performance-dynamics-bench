"""Qualify deterministic CUDA math and the frozen worker on synthetic inputs only."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import cast

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import numpy as np
import torch
import train_res338_final_fits as trainer
from torch import Tensor

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.learned_deepsets import (
    FUTURE_SAMPLES,
    INFORMATION_REGIMES,
    TARGET_PLAYERS,
    ModelInputs,
    PerTargetContextDeepSetsMLP,
    collate_feature_payloads,
    make_optimizer,
    masked_scene_ade_loss,
)

SEED = 1729
REPLAY_STEPS = 100
OUTPUT_DEFAULT = Path("/content/res338/cuda-qualification.json")
RTOL_OUTPUT = 1e-4
ATOL_OUTPUT = 1e-5
RTOL_UPDATE = 1e-3
ATOL_UPDATE = 1e-5
SYNTHETIC_POOL_SIZE = 32
MAX_STEPS = trainer.MAX_STEPS
VALIDATION_CADENCE = trainer.VALIDATION_CADENCE


def _inputs(rng: np.random.Generator, batch_size: int, regime: str) -> ModelInputs:
    payloads = []
    for scene_index in range(batch_size):
        payload: dict[str, np.ndarray] = {
            "target_history": rng.normal(0, 4, (TARGET_PLAYERS, 78)).astype(np.float32),
            "history_team_tracks": rng.normal(0, 4, (2, SYNTHETIC_POOL_SIZE, 78)).astype(
                np.float32
            ),
            "history_team_mask": np.ones((2, SYNTHETIC_POOL_SIZE), dtype=np.bool_),
            "history_ball": rng.normal(0, 4, 78).astype(np.float32),
            "target_side": np.asarray(1.0 if scene_index % 2 == 0 else -1.0, dtype=np.float32),
        }
        if regime != "history_only":
            payload["future_ball"] = rng.normal(0, 4, 45).astype(np.float32)
        if regime == "future_opponent_plus_ball":
            payload["future_opponent_tracks"] = rng.normal(0, 4, (SYNTHETIC_POOL_SIZE, 45)).astype(
                np.float32
            )
            payload["future_opponent_mask"] = np.ones(SYNTHETIC_POOL_SIZE, dtype=np.bool_)
        payloads.append(payload)
    return collate_feature_payloads(payloads, cast(trainer.InformationRegime, regime))


def _truth_and_mask(rng: np.random.Generator, batch_size: int) -> tuple[Tensor, Tensor]:
    truth = torch.from_numpy(
        rng.normal(0, 10, (batch_size, TARGET_PLAYERS, FUTURE_SAMPLES, 2)).astype(np.float32)
    )
    mask = torch.from_numpy(
        (rng.random((batch_size, TARGET_PLAYERS, FUTURE_SAMPLES)) > 0.05).astype(np.bool_)
    )
    mask[..., -1] = True
    return truth, mask


def _compare_cpu_gpu(regime: str) -> dict[str, float]:
    rng = np.random.default_rng(SEED)
    inputs_cpu = _inputs(rng, 4, regime)
    inputs_gpu = trainer._model_inputs_to_device(inputs_cpu, torch.device("cuda:0"))
    truth, mask = _truth_and_mask(rng, 4)

    trainer.seed_training(SEED)
    cpu_model = PerTargetContextDeepSetsMLP(cast(trainer.InformationRegime, regime))
    gpu_model = PerTargetContextDeepSetsMLP(cast(trainer.InformationRegime, regime)).cuda()
    gpu_model.load_state_dict(cpu_model.state_dict(), strict=True)
    cpu_model.eval()
    gpu_model.eval()
    with torch.inference_mode():
        cpu_prediction = cpu_model(inputs_cpu)
        gpu_prediction = gpu_model(inputs_gpu).cpu()
    torch.testing.assert_close(gpu_prediction, cpu_prediction, rtol=RTOL_OUTPUT, atol=ATOL_OUTPUT)
    cpu_loss = masked_scene_ade_loss(cpu_prediction, truth, mask)
    gpu_loss = masked_scene_ade_loss(
        gpu_prediction.to("cuda:0"), truth.to("cuda:0"), mask.to("cuda:0")
    ).cpu()
    torch.testing.assert_close(gpu_loss, cpu_loss, rtol=RTOL_OUTPUT, atol=ATOL_OUTPUT)

    # Compare backend math with dropout disabled; replay below tests training-mode dropout.
    cpu_optimizer = make_optimizer(cpu_model)
    gpu_optimizer = make_optimizer(gpu_model)
    cpu_optimizer.zero_grad(set_to_none=True)
    gpu_optimizer.zero_grad(set_to_none=True)
    masked_scene_ade_loss(cpu_model(inputs_cpu), truth, mask).backward()
    masked_scene_ade_loss(gpu_model(inputs_gpu), truth.to("cuda:0"), mask.to("cuda:0")).backward()
    max_gradient_error = 0.0
    for cpu_parameter, gpu_parameter in zip(
        cpu_model.parameters(), gpu_model.parameters(), strict=True
    ):
        assert cpu_parameter.grad is not None and gpu_parameter.grad is not None
        gpu_grad = gpu_parameter.grad.detach().cpu()
        torch.testing.assert_close(gpu_grad, cpu_parameter.grad, rtol=RTOL_UPDATE, atol=ATOL_UPDATE)
        max_gradient_error = max(
            max_gradient_error,
            float((gpu_grad - cpu_parameter.grad).abs().max()),
        )
    cpu_optimizer.step()
    gpu_optimizer.step()
    max_parameter_error = 0.0
    for cpu_parameter, gpu_parameter in zip(
        cpu_model.parameters(), gpu_model.parameters(), strict=True
    ):
        gpu_value = gpu_parameter.detach().cpu()
        torch.testing.assert_close(
            gpu_value, cpu_parameter.detach(), rtol=RTOL_UPDATE, atol=ATOL_UPDATE
        )
        max_parameter_error = max(
            max_parameter_error,
            float((gpu_value - cpu_parameter.detach()).abs().max()),
        )
    torch.cuda.synchronize()
    return {
        "max_prediction_abs_error": float((gpu_prediction - cpu_prediction).abs().max()),
        "loss_abs_error": float((gpu_loss - cpu_loss).abs()),
        "max_gradient_abs_error": max_gradient_error,
        "max_parameter_abs_error_after_adamw": max_parameter_error,
    }


def _deterministic_replay() -> dict[str, object]:
    def run_once() -> tuple[dict[str, Tensor], Tensor]:
        rng = np.random.default_rng(SEED)
        trainer.seed_training(SEED)
        model = PerTargetContextDeepSetsMLP("future_opponent_plus_ball").cuda()
        optimizer = make_optimizer(model)
        for _ in range(REPLAY_STEPS):
            inputs = trainer._model_inputs_to_device(
                _inputs(rng, 4, "future_opponent_plus_ball"), torch.device("cuda:0")
            )
            truth, mask = _truth_and_mask(rng, 4)
            optimizer.zero_grad(set_to_none=True)
            loss = masked_scene_ade_loss(model(inputs), truth.to("cuda:0"), mask.to("cuda:0"))
            loss.backward()
            optimizer.step()
        torch.cuda.synchronize()
        final_inputs = trainer._model_inputs_to_device(
            _inputs(rng, 4, "future_opponent_plus_ball"), torch.device("cuda:0")
        )
        with torch.inference_mode():
            prediction = model(final_inputs).cpu()
        return (
            {name: value.detach().cpu().clone() for name, value in model.state_dict().items()},
            prediction,
        )

    first_state, first_prediction = run_once()
    second_state, second_prediction = run_once()
    exact_state = all(torch.equal(first_state[key], second_state[key]) for key in first_state)
    exact_prediction = torch.equal(first_prediction, second_prediction)
    if not exact_state or not exact_prediction:
        raise RuntimeError("same-runtime deterministic GPU replay differs bitwise")
    return {
        "steps": REPLAY_STEPS,
        "state_bitwise_equal": exact_state,
        "prediction_bitwise_equal": exact_prediction,
    }


def _synthetic_caches(
    root: Path,
) -> tuple[dict[str, trainer.MatchCache], tuple[str, ...], tuple[str, ...]]:
    rng = np.random.default_rng(SEED)
    train = tuple(f"synthetic-training-{i:02d}" for i in range(12))
    validation = tuple(f"synthetic-validation-{i:02d}" for i in range(4))
    caches: dict[str, trainer.MatchCache] = {}
    for role, match_ids in (("training", train), ("validation", validation)):
        for match_id in match_ids:
            arrays = {
                "target_history": rng.normal(size=(1, 2, TARGET_PLAYERS, 78)).astype(np.float32),
                "history_team_tracks": rng.normal(size=(1, 2, SYNTHETIC_POOL_SIZE, 78)).astype(
                    np.float32
                ),
                "history_team_mask": np.ones((1, 2, SYNTHETIC_POOL_SIZE), dtype=np.bool_),
                "history_ball": rng.normal(size=(1, 78)).astype(np.float32),
                "target_side": np.asarray([[1.0, -1.0]], dtype=np.float32),
                "future_ball": rng.normal(size=(1, 45)).astype(np.float32),
                "future_opponent_tracks": rng.normal(size=(1, 2, SYNTHETIC_POOL_SIZE, 45)).astype(
                    np.float32
                ),
                "future_opponent_mask": np.ones((1, 2, SYNTHETIC_POOL_SIZE), dtype=np.bool_),
                "target_absolute_xy": rng.normal(
                    size=(1, 2, TARGET_PLAYERS, FUTURE_SAMPLES, 2)
                ).astype(np.float64),
                "target_displacement": rng.normal(
                    size=(1, 2, TARGET_PLAYERS, FUTURE_SAMPLES, 2)
                ).astype(np.float64),
                "target_mask": np.ones((1, 2, TARGET_PLAYERS, FUTURE_SAMPLES), dtype=np.bool_),
                "scoreable": np.ones((1, 2), dtype=np.bool_),
            }
            caches[match_id] = trainer.MatchCache(match_id, role, root, arrays)
    return caches, train, validation


def _force_full_validation_cadence() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="res338-cuda-toy-") as temporary:
        root = Path(temporary)
        (root / "runs").mkdir(mode=0o700)
        caches, train, validation = _synthetic_caches(root)
        original = trainer._fit_match_metrics
        validation_calls = 0

        def improving_metric(*args: object, **kwargs: object) -> dict[str, float | int]:
            nonlocal validation_calls
            metric = original(*args, **kwargs)
            check_index = validation_calls // len(validation)
            validation_calls += 1
            metric["ade_m"] = (
                float(metric["ade_m"])
                + (MAX_STEPS // VALIDATION_CADENCE - check_index) * 1_000_000.0
            )
            return metric

        trainer._fit_match_metrics = improving_metric  # type: ignore[assignment]
        try:
            cpu_start, wall_start = time.process_time(), time.monotonic()
            fit = trainer._fit_one(
                run_root=root,
                cache_by_match=caches,
                train_matches=train,
                validation_matches=validation,
                regime="future_opponent_plus_ball",
                representation="absolute_xy",
                seed=SEED,
                plan_sha256="1" * 64,
                protocol_sha256="2" * 64,
                population_sha256=trainer.RESEARCH_MANIFEST_SHA256,
                target_mask_identity_sha256="3" * 64,
                environment_sha256="4" * 64,
                campaign_cpu_start=cpu_start,
                campaign_wall_start=wall_start,
                campaign_gpu_start=wall_start,
                device="cuda",
                accelerator=trainer._validate_training_runtime("cuda")["accelerator"],
                fit_cpu_budget_seconds=trainer.FIT_CPU_BUDGET_SECONDS,
                fit_gpu_wall_budget_seconds=trainer.GPU_FIT_WALL_BUDGET_SECONDS,
                worker_memory_limit_bytes=trainer.MAX_WORKER_RSS_BYTES,
            )
        finally:
            trainer._fit_match_metrics = original  # type: ignore[assignment]
        if (
            fit["status"] != "completed"
            or fit["optimizer_steps"] != MAX_STEPS
            or len(cast(list[object], fit["validation_history"])) != MAX_STEPS // VALIDATION_CADENCE
        ):
            raise RuntimeError("synthetic CUDA worker did not complete the frozen cadence")
        return {
            "optimizer_steps": fit["optimizer_steps"],
            "validation_checks": len(cast(list[object], fit["validation_history"])),
            "fit_cpu_seconds": fit["fit_cpu_seconds"],
            "fit_gpu_wall_seconds": fit["fit_wall_seconds"],
            "peak_rss_bytes": fit["peak_rss_bytes"],
            "peak_cuda_memory_bytes": fit["peak_gpu_memory_allocated_bytes"],
        }


def run(output: Path = OUTPUT_DEFAULT) -> dict[str, object]:
    os.umask(0o077)
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    output.parent.chmod(0o700)
    affinity = os.sched_getaffinity(0)
    if not affinity:
        raise RuntimeError("CUDA qualification requires a CPU affinity")
    os.sched_setaffinity(0, {min(affinity)})
    runtime = trainer._validate_training_runtime("cuda")
    plan, protocol, _ = trainer._frozen_split_and_authorities()
    environment_sha256 = trainer._training_environment_sha256(runtime)
    resources = trainer._resource_fingerprint(output.parent)
    expected_cache_bytes = 16 * (
        2 * SYNTHETIC_POOL_SIZE * 78 * 4
        + 2 * SYNTHETIC_POOL_SIZE * 45 * 4
        + 2 * TARGET_PLAYERS * 78 * 4
        + 2 * 2 * FUTURE_SAMPLES * TARGET_PLAYERS * 2 * 8
        + 2 * FUTURE_SAMPLES * TARGET_PLAYERS
        + 4096
    )
    numerical = {regime: _compare_cpu_gpu(regime) for regime in INFORMATION_REGIMES}
    replay = _deterministic_replay()
    full_fit = _force_full_validation_cadence()
    report: dict[str, object] = {
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
        "code_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=trainer.REPO, text=True
        ).strip(),
        "runtime": runtime,
        "runtime_sha256": environment_sha256,
        "device": "cuda",
        "cuda_qualification": {
            "numerical_agreement": "PASSED",
            "deterministic_replay": "BITWISE_EQUAL",
            "numerical_tolerances": {
                "prediction_and_masked_ade": {"rtol": RTOL_OUTPUT, "atol": ATOL_OUTPUT},
                "gradient_and_adamw_update": {"rtol": RTOL_UPDATE, "atol": ATOL_UPDATE},
            },
            "per_regime": numerical,
            "replay": replay,
        },
        "synthetic_optimization_steps": full_fit["optimizer_steps"],
        "synthetic_validation_checks": full_fit["validation_checks"],
        "synthetic_full_cadence_forced": True,
        "synthetic_fit_cpu_seconds": full_fit["fit_cpu_seconds"],
        "synthetic_fit_wall_seconds": full_fit["fit_gpu_wall_seconds"],
        "synthetic_peak_rss_bytes": full_fit["peak_rss_bytes"],
        "synthetic_peak_cuda_memory_bytes": full_fit["peak_cuda_memory_bytes"],
        "effective_worker_memory_limit_bytes": resources["effective_worker_memory_limit_bytes"],
        "estimated_private_cache_bytes_with_32_tracks_per_team": expected_cache_bytes,
        "available_disk_bytes": resources["disk_available_bytes"],
        "host_resources": resources,
    }
    trainer._atomic_json(output, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "runtime_sha256": environment_sha256,
                "report": str(output),
            }
        )
    )
    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT_DEFAULT)
    args = parser.parse_args()
    run(args.output)
