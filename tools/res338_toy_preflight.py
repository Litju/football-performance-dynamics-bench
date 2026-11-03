"""Measure the frozen worker on synthetic inputs before private model fitting."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import cast

import numpy as np
import train_res338_final_fits as trainer

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.learned_deepsets import (
    FUTURE_SAMPLES,
    TARGET_PLAYERS,
)

RESEARCH_ROOT = trainer.RESEARCH_ROOT_DEFAULT
SOURCE_ROOT = trainer.SOURCE_ROOT_DEFAULT
OUTPUT_ROOT = Path("/srv/fpdbench-private/evidence/res338-toy-preflight-v1")
TOY_POOL_SIZE = 32
DISK_PROBE_BYTES = 64 * 1024**2


def _broadcast(base: np.ndarray, windows: int) -> np.ndarray:
    return np.broadcast_to(base, (windows, *base.shape[1:]))


def _toy_cache(match_id: str, role: str, windows: int, scenes: int) -> trainer.MatchCache:
    if windows <= 0 or not windows <= scenes <= 2 * windows:
        raise ValueError("synthetic match counts do not satisfy the frozen scene/window grain")
    scoreable = np.zeros((windows, 2), dtype=np.bool_)
    scoreable[:, 0] = True
    scoreable[: scenes - windows, 1] = True
    bases = {
        "target_history": np.zeros((1, 2, TARGET_PLAYERS, 78), dtype=np.float32),
        "history_team_tracks": np.zeros((1, 2, TOY_POOL_SIZE, 78), dtype=np.float32),
        "history_team_mask": np.ones((1, 2, TOY_POOL_SIZE), dtype=np.bool_),
        "history_ball": np.zeros((1, 78), dtype=np.float32),
        "target_side": np.asarray([[1.0, -1.0]], dtype=np.float32),
        "future_ball": np.zeros((1, 45), dtype=np.float32),
        "future_opponent_tracks": np.zeros((1, 2, TOY_POOL_SIZE, 45), dtype=np.float32),
        "future_opponent_mask": np.ones((1, 2, TOY_POOL_SIZE), dtype=np.bool_),
        "target_absolute_xy": np.full(
            (1, 2, TARGET_PLAYERS, FUTURE_SAMPLES, 2), 10.0, dtype=np.float64
        ),
        "target_displacement": np.zeros(
            (1, 2, TARGET_PLAYERS, FUTURE_SAMPLES, 2), dtype=np.float64
        ),
        "target_mask": np.ones((1, 2, TARGET_PLAYERS, FUTURE_SAMPLES), dtype=np.bool_),
    }
    arrays = {name: _broadcast(value, windows) for name, value in bases.items()}
    arrays["scoreable"] = scoreable
    return trainer.MatchCache(match_id, role, OUTPUT_ROOT, arrays)


def _disk_probe(directory: Path) -> tuple[int, float]:
    path = directory / "toy-disk-probe.bin"
    start = time.monotonic()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        block = bytes(1024 * 1024)
        for _ in range(DISK_PROBE_BYTES // len(block)):
            stream.write(block)
        stream.flush()
        os.fsync(stream.fileno())
    elapsed = time.monotonic() - start
    path.unlink()
    trainer._fsync_directory(directory)
    return DISK_PROBE_BYTES, elapsed


def run() -> dict[str, object]:
    os.umask(0o077)
    if OUTPUT_ROOT.exists():
        raise FileExistsError("toy preflight output already exists; it is never overwritten")
    OUTPUT_ROOT.mkdir(mode=0o700)
    pinned = trainer._read_pinned_manifest(RESEARCH_ROOT)
    plan, protocol, roles = trainer._frozen_split_and_authorities()
    reconciled, population_rehash = trainer.verify_research_population(
        RESEARCH_ROOT, SOURCE_ROOT, plan, roles
    )
    if reconciled != pinned:
        raise ValueError("toy preflight population identity changed")
    runtime = trainer._validate_training_runtime()
    if len(os.sched_getaffinity(0)) != 1:
        raise RuntimeError("toy preflight must use one CPU core")
    available_disk = shutil.disk_usage(OUTPUT_ROOT).free
    estimated_cache_bytes = 0
    validation_caches: dict[str, trainer.MatchCache] = {}
    training_caches: dict[str, trainer.MatchCache] = {}
    for role, match_ids, cache in (
        ("training", roles["training"], training_caches),
        ("validation", roles["validation"], validation_caches),
    ):
        for index, match_id in enumerate(match_ids):
            summary = cast(dict[str, object], reconciled["per_match"])[match_id]
            counts = cast(dict[str, object], summary["counts"])
            windows = int(counts["scoreable_windows"])
            scenes = int(counts["home_scenes"]) + int(counts["away_scenes"])
            estimated_cache_bytes += windows * (
                2 * TOY_POOL_SIZE * 78 * 4
                + 2 * TOY_POOL_SIZE * 45 * 4
                + 2 * TARGET_PLAYERS * 78 * 4
                + 2 * 2 * FUTURE_SAMPLES * TARGET_PLAYERS * 2 * 8
                + 2 * FUTURE_SAMPLES * TARGET_PLAYERS
                + 4096
            )
            cache[f"{role}-{index:02d}"] = _toy_cache(f"{role}-{index:02d}", role, windows, scenes)
    if available_disk < estimated_cache_bytes + 1024**3:
        raise OSError("toy cache estimate plus reserve exceeds available disk")
    disk_probe_bytes, disk_probe_seconds = _disk_probe(OUTPUT_ROOT)

    train_ids = tuple(training_caches)
    validation_ids = tuple(validation_caches)
    original_metrics = trainer._fit_match_metrics
    validation_calls = 0
    host_before_fit = trainer._resource_fingerprint(OUTPUT_ROOT)
    toy_memory_limit = int(host_before_fit["effective_worker_memory_limit_bytes"])

    def worst_case_validation(*args: object, **kwargs: object) -> dict[str, float | int]:
        nonlocal validation_calls
        metric = original_metrics(*args, **kwargs)
        check_index = validation_calls // len(validation_ids)
        validation_calls += 1
        metric["ade_m"] = float(metric["ade_m"]) - (check_index + 1) * 1e-9
        return metric

    trainer._fit_match_metrics = worst_case_validation  # type: ignore[assignment]
    start_cpu, start_wall = time.process_time(), time.monotonic()
    with tempfile.TemporaryDirectory(prefix="res338-toy-fit-", dir=OUTPUT_ROOT) as temporary:
        root = Path(temporary)
        (root / "runs").mkdir(mode=0o700)
        fit = trainer._fit_one(
            run_root=root,
            cache_by_match={**training_caches, **validation_caches},
            train_matches=train_ids,
            validation_matches=validation_ids,
            regime="future_opponent_plus_ball",
            representation="absolute_xy",
            seed=1729,
            plan_sha256=str(plan["plan_sha256"]),
            protocol_sha256=str(protocol["protocol_sha256"]),
            population_sha256=trainer.RESEARCH_MANIFEST_SHA256,
            target_mask_identity_sha256="0" * 64,
            environment_sha256=hashlib.sha256(trainer._canonical(runtime)).hexdigest(),
            campaign_cpu_start=start_cpu,
            campaign_wall_start=start_wall,
            worker_memory_limit_bytes=toy_memory_limit,
        )
    trainer._fit_match_metrics = original_metrics  # type: ignore[assignment]
    if fit["status"] != "completed":
        raise RuntimeError(f"synthetic worker feasibility fit failed: {fit['stopping_reason']}")
    report = {
        "schema_id": "fpdbench.res338-toy-preflight",
        "schema_version": "1.0.0",
        "status": "PASSED",
        "synthetic_only": True,
        "real_fit_count": 0,
        "real_evaluation_metrics": 0,
        "evaluation_match_features": 0,
        "real_tracking_rows_read_for_features": 0,
        "research_manifest_sha256": trainer.RESEARCH_MANIFEST_SHA256,
        "source_release_hash": reconciled["source_release_hash"],
        "source_population_hash": reconciled["source_population_hash"],
        "population_rehash": population_rehash,
        "plan_sha256": plan["plan_sha256"],
        "protocol_sha256": protocol["protocol_sha256"],
        "python": runtime["python"].split()[0],
        "torch": runtime["torch"],
        "numpy": runtime["numpy"],
        "cpu_affinity": runtime["cpu_affinity"],
        "input_dimensions": trainer.INPUT_DIMS,
        "synthetic_track_pool_size_per_team": TOY_POOL_SIZE,
        "synthetic_training_window_count": sum(
            int(
                cast(
                    dict[str, object],
                    cast(dict[str, object], reconciled["per_match"])[mid]["counts"],
                )["scoreable_windows"]
            )
            for mid in roles["training"]
        ),
        "synthetic_validation_scene_count": sum(
            int(
                cast(
                    dict[str, object],
                    cast(dict[str, object], reconciled["per_match"])[mid]["counts"],
                )["home_scenes"]
            )
            + int(
                cast(
                    dict[str, object],
                    cast(dict[str, object], reconciled["per_match"])[mid]["counts"],
                )["away_scenes"]
            )
            for mid in roles["validation"]
        ),
        "synthetic_optimization_steps": fit["optimizer_steps"],
        "synthetic_validation_checks": len(cast(list[object], fit["validation_history"])),
        "synthetic_fit_cpu_seconds": fit["fit_cpu_seconds"],
        "synthetic_fit_wall_seconds": fit["fit_wall_seconds"],
        "synthetic_peak_rss_bytes": fit["peak_rss_bytes"],
        "effective_worker_memory_limit_bytes": toy_memory_limit,
        "runtime_sha256": hashlib.sha256(trainer._canonical(runtime)).hexdigest(),
        "per_fit_cpu_budget_seconds": trainer.FIT_CPU_BUDGET_SECONDS,
        "estimated_private_cache_bytes_with_32_tracks_per_team": estimated_cache_bytes,
        "available_disk_bytes": available_disk,
        "synthetic_disk_probe_bytes": disk_probe_bytes,
        "synthetic_disk_probe_seconds": round(disk_probe_seconds, 6),
        "host_resources": trainer._resource_fingerprint(OUTPUT_ROOT),
        "selection_metric_outputs": (
            "discarded with the temporary synthetic fit; not research results"
        ),
        "code_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=trainer.REPO, text=True
        ).strip(),
    }
    trainer._atomic_json(OUTPUT_ROOT / "toy-preflight.json", report)
    return report


if __name__ == "__main__":
    created = not OUTPUT_ROOT.exists()
    try:
        print(json.dumps(run(), sort_keys=True))
    except Exception as exc:
        if created and OUTPUT_ROOT.exists() and not (OUTPUT_ROOT / "toy-preflight.json").exists():
            trainer._atomic_json(
                OUTPUT_ROOT / "toy-preflight-failure.json",
                {
                    "schema_id": "fpdbench.res338-toy-preflight",
                    "schema_version": "1.0.0",
                    "status": "INCOMPLETE",
                    "synthetic_only": True,
                    "real_fit_count": 0,
                    "failure_type": type(exc).__name__,
                    "failure_message": str(exc)[:1000],
                },
            )
        raise
