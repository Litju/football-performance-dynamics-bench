"""RES614 synthetic-only performance qualification harness.

Everything here is invented: artificial tracking observations and randomly initialised model
weights. The module never touches the RES594 scorer entrypoint, protected-source processing,
real checkpoints, held-out labels or the historical campaign directory. It exists to measure the
computational *structure* of the frozen scorer (materialise -> hash -> reread -> features ->
18 CPU forward calls -> metrics -> result serialisation) under an explicit resource budget.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import resource
import statistics
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

import torch  # noqa: E402

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (  # noqa: E402
    learned_deepsets as lds,
)

SCHEMA_ID = "fpdbench.res614.synthetic-benchmark"
SYNTHETIC_SEED = 614
HISTORICAL_WINDOWS = 51_713
HISTORICAL_FORWARD_CALLS = 930_834
HISTORICAL_SNAPSHOT_BYTES = 6_815_838_287  # public size metadata recorded in RES594/RES614
FORBIDDEN_PATH_FRAGMENT = "fpdbench-private"

# Bounded diagnostic budget (RES614): cumulative CPU, RSS, temporary storage.
DEFAULT_CPU_BUDGET_S = 600.0
DEFAULT_RSS_BUDGET_BYTES = 2 * 1024**3
DEFAULT_DISK_BUDGET_BYTES = 1 * 1024**3

STAGES = (
    "synthesize_window",
    "materialize_row",
    "reread_parse_row",
    "feature_construction",
    "model_inference",
    "metric_aggregation",
)


class BudgetExceeded(RuntimeError):
    """Raised when the bounded diagnostic budget would be exceeded."""


@dataclass
class Budget:
    cpu_seconds: float = DEFAULT_CPU_BUDGET_S
    rss_bytes: int = DEFAULT_RSS_BUDGET_BYTES
    disk_bytes: int = DEFAULT_DISK_BUDGET_BYTES
    cpu_used_offset: float = 0.0
    disk_used: int = 0
    _start_cpu: float = field(default_factory=time.process_time)

    def cpu_used(self) -> float:
        return self.cpu_used_offset + (time.process_time() - self._start_cpu)

    @staticmethod
    def rss_peak_bytes() -> int:
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024

    def charge_disk(self, nbytes: int) -> None:
        self.disk_used += nbytes
        self.check()

    def release_disk(self, nbytes: int) -> None:
        self.disk_used = max(0, self.disk_used - nbytes)

    def check(self) -> None:
        if self.cpu_used() > self.cpu_seconds:
            raise BudgetExceeded("cumulative CPU-second budget exceeded")
        if self.rss_peak_bytes() > self.rss_bytes:
            raise BudgetExceeded("RSS budget exceeded")
        if self.disk_used > self.disk_bytes:
            raise BudgetExceeded("temporary-storage budget exceeded")


@dataclass(frozen=True)
class Scenario:
    """Workload-shape knobs. Defaults describe the nominal synthetic mix."""

    name: str
    roster_per_team: int = 14
    player_frame_missing_p: float = 0.02
    ball_missing_p: float = 0.01
    scoreable_scenes: int = 2
    truth_mask_p: float = 0.95
    extra_fields_per_player: int = 2


SCENARIOS = (
    Scenario("nominal"),
    Scenario("heavy_missingness", player_frame_missing_p=0.15, ball_missing_p=0.10),
    Scenario("single_scene", scoreable_scenes=1),
    Scenario("large_roster", roster_per_team=23),
)


def assert_synthetic_path(path: Path) -> None:
    """Refuse any path that could alias the private historical evidence area."""
    resolved = str(path.resolve())
    if FORBIDDEN_PATH_FRAGMENT in resolved or "res594" in resolved.lower():
        raise PermissionError("synthetic harness refuses historical/private campaign paths")


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def synthesize_window(rng: np.random.Generator, scenario: Scenario, index: int) -> dict[str, Any]:
    """Invent one 41-sample window (26 history + 15 future) with two directed scenes."""
    roster = scenario.roster_per_team
    home_ids = list(range(1, roster + 1))
    away_ids = list(range(101, 101 + roster))
    n = len(home_ids) + len(away_ids)
    positions = np.empty((41, n, 2))
    positions[0] = rng.uniform((-50.0, -32.0), (50.0, 32.0), size=(n, 2))
    steps = rng.normal(0.0, 0.35, size=(40, n, 2))
    positions[1:] = positions[0] + np.cumsum(steps, axis=0)
    ball = rng.uniform((-50.0, -32.0), (50.0, 32.0), size=(1, 2)) + np.cumsum(
        rng.normal(0.0, 1.0, size=(41, 2)), axis=0
    )
    present = rng.random((41, n)) >= scenario.player_frame_missing_p
    ball_present = rng.random(41) >= scenario.ball_missing_p
    all_ids = home_ids + away_ids
    support: list[dict[str, Any]] = []
    for t in range(41):
        players = []
        for j, player_id in enumerate(all_ids):
            if not present[t, j]:
                continue
            player: dict[str, Any] = {
                "player_id": player_id,
                "x_m": round(float(positions[t, j, 0]), 4),
                "y_m": round(float(positions[t, j, 1]), 4),
            }
            for k in range(scenario.extra_fields_per_player):
                player[f"provider_field_{k}"] = round(float(rng.normal()), 6)
            players.append(player)
        support.append(
            {
                "period": 1,
                "source_frame": 2 * (index * 41 + t),
                "players": players,
                "ball": (
                    {"x_m": round(float(ball[t, 0]), 4), "y_m": round(float(ball[t, 1]), 4)}
                    if ball_present[t]
                    else None
                ),
            }
        )
    scenes = []
    for side, ids in (("home", home_ids), ("away", away_ids)):
        panel = ids[: lds.TARGET_PLAYERS]
        columns = [all_ids.index(p) for p in panel]
        absolute = positions[26:, columns, :].transpose(1, 0, 2)
        mask = rng.random((lds.TARGET_PLAYERS, lds.FUTURE_SAMPLES)) < scenario.truth_mask_p
        mask[0, -1] = True  # at least one scoreable final target
        scenes.append(
            {
                "scene_id": side,
                "player_ids": panel,
                "origin_xy": positions[25, columns, :].round(4).tolist(),
                "absolute": absolute.round(4).tolist(),
                "mask": mask.tolist(),
                "quality": "detected_only" if rng.random() < 0.7 else "with_provider_extrapolation",
            }
        )
    return {
        "kind": "window",
        "window_id": f"synthetic-{index:08d}",
        "support": support,
        "home_player_ids": home_ids,
        "away_player_ids": away_ids,
        "scenes": scenes[: max(1, scenario.scoreable_scenes)],
    }


def build_random_models(
    seed_offset: int = 0,
) -> dict[tuple[str, str, int], lds.PerTargetContextDeepSetsMLP]:
    """18 randomly initialised models (3 regimes x 2 representations x 3 seeds)."""
    models: dict[tuple[str, str, int], lds.PerTargetContextDeepSetsMLP] = {}
    for regime in lds.INFORMATION_REGIMES:
        for representation in lds.TARGET_REPRESENTATIONS:
            for seed in lds.SEEDS:
                torch.manual_seed(SYNTHETIC_SEED + seed_offset + seed)
                model = lds.PerTargetContextDeepSetsMLP(regime).eval()
                models[(regime, representation, seed)] = model
    return models


def configure_cpu() -> None:
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def summarize(values: list[float]) -> dict[str, float]:
    return {
        "n": float(len(values)),
        "mean_s": statistics.fmean(values) if values else float("nan"),
        "median_s": _percentile(values, 0.5),
        "p95_s": _percentile(values, 0.95),
        "total_s": float(sum(values)),
    }


def process_window(
    row: dict[str, Any],
    models: dict[tuple[str, str, int], lds.PerTargetContextDeepSetsMLP],
    timers: dict[str, list[float]],
    digest: Any,
    *,
    inference_by_cell: dict[str, list[float]] | None = None,
) -> int:
    """Run feature construction, 18 forward calls and metrics for one parsed row."""
    support = row["support"]
    home_ids, away_ids = row["home_player_ids"], row["away_player_ids"]
    scenes = row["scenes"]
    forward_calls = 0
    feature_s = inference_s = metric_s = 0.0
    feature_c = inference_c = metric_c = 0.0
    for regime in lds.INFORMATION_REGIMES:
        t0 = time.perf_counter()
        c0 = time.thread_time()
        payloads = [
            lds.build_scene_feature_payload(
                support,
                target_side=scene["scene_id"],
                target_player_ids=scene["player_ids"],
                home_player_ids=home_ids,
                away_player_ids=away_ids,
                regime=regime,
            )
            for scene in scenes
        ]
        for payload in payloads:
            lds.validate_feature_payload(payload, regime)
        inputs = lds.collate_feature_payloads(payloads, regime)
        feature_s += time.perf_counter() - t0
        feature_c += time.thread_time() - c0
        for representation in lds.TARGET_REPRESENTATIONS:
            for seed in lds.SEEDS:
                model = models[(regime, representation, seed)]
                t1 = time.perf_counter()
                c1 = time.thread_time()
                with torch.inference_mode():
                    outputs = model(inputs).cpu().numpy().astype(np.float64)
                call_s = time.perf_counter() - t1
                inference_c += time.thread_time() - c1
                inference_s += call_s
                forward_calls += 1
                if inference_by_cell is not None:
                    inference_by_cell.setdefault(f"{regime}/{representation}/{seed}", []).append(
                        call_s
                    )
                t2 = time.perf_counter()
                c2 = time.thread_time()
                if not np.isfinite(outputs).all():
                    raise FloatingPointError("synthetic model emitted a non-finite prediction")
                for batch_index, scene in enumerate(scenes):
                    origin = np.asarray(scene["origin_xy"], dtype=np.float64)
                    physical = outputs[batch_index]
                    if representation == "origin_relative_displacement":
                        physical = physical + origin[:, None, :]
                    truth = np.asarray(scene["absolute"], dtype=np.float64)
                    mask = np.asarray(scene["mask"], dtype=np.bool_)
                    metrics = lds.physical_metrics(physical, truth, mask)
                    distances = np.hypot(*(physical - truth).transpose(2, 0, 1))
                    for start, stop in ((0, 5), (5, 10), (10, 15)):
                        window_mask = mask[:, start:stop]
                        if window_mask.any():
                            float(distances[:, start:stop][window_mask].mean())
                    digest.update(f"{metrics['ade_m']:.9f}|".encode())
                metric_s += time.perf_counter() - t2
                metric_c += time.thread_time() - c2
    timers["feature_construction"].append(feature_s)
    timers["model_inference"].append(inference_s)
    timers["metric_aggregation"].append(metric_s)
    timers["feature_construction__cpu"].append(feature_c)
    timers["model_inference__cpu"].append(inference_c)
    timers["metric_aggregation__cpu"].append(metric_c)
    return forward_calls


@dataclass
class ScenarioResult:
    scenario: Scenario
    windows: int
    timers: dict[str, list[float]]
    forward_calls: int
    row_bytes: list[int]
    inference_by_cell: dict[str, list[float]]
    cpu_seconds: float
    peak_rss_bytes: int
    deterministic_digest: str
    io: dict[str, float]


def run_scenario(
    scenario: Scenario,
    windows: int,
    work_dir: Path,
    budget: Budget,
    models: dict[tuple[str, str, int], lds.PerTargetContextDeepSetsMLP],
    *,
    progress: Callable[[str], None] | None = None,
) -> ScenarioResult:
    assert_synthetic_path(work_dir)
    name_seed = int.from_bytes(hashlib.sha256(scenario.name.encode()).digest()[:4], "big")
    rng = np.random.default_rng([SYNTHETIC_SEED, name_seed])
    timers: dict[str, list[float]] = {stage: [] for stage in STAGES}
    timers.update({f"{stage}__cpu": [] for stage in STAGES})
    snapshot = work_dir / f"{scenario.name}.synthetic.jsonl"
    row_bytes: list[int] = []
    cpu_start = time.process_time()

    # Stage 1+2: synthesise rows, materialise them to a bounded synthetic snapshot.
    write_s = 0.0
    with snapshot.open("wb") as stream:
        for index in range(windows):
            t0 = time.perf_counter()
            c0 = time.thread_time()
            row = synthesize_window(rng, scenario, index)
            timers["synthesize_window"].append(time.perf_counter() - t0)
            timers["synthesize_window__cpu"].append(time.thread_time() - c0)
            t1 = time.perf_counter()
            c1 = time.thread_time()
            payload = _canonical(row) + b"\n"
            stream.write(payload)
            elapsed = time.perf_counter() - t1
            timers["materialize_row"].append(elapsed)
            timers["materialize_row__cpu"].append(time.thread_time() - c1)
            write_s += elapsed
            row_bytes.append(len(payload))
            budget.charge_disk(len(payload))
        t_sync = time.perf_counter()
        stream.flush()
        os.fsync(stream.fileno())
        fsync_s = time.perf_counter() - t_sync
    snapshot_bytes = snapshot.stat().st_size

    # Stage 3: SHA-256 readback (mirrors the frozen scorer's secure hash of its snapshot).
    t_hash = time.perf_counter()
    sha = hashlib.sha256()
    with snapshot.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            sha.update(chunk)
    hash_s = time.perf_counter() - t_hash

    # Stage 4+: sequential reread, features, inference, metrics.
    digest = hashlib.sha256()
    inference_by_cell: dict[str, list[float]] = {}
    forward_calls = 0
    t_reread_total = 0.0
    with snapshot.open("rb") as stream:
        for line in stream:
            t0 = time.perf_counter()
            c0 = time.thread_time()
            row = json.loads(line)
            parse_s = time.perf_counter() - t0
            timers["reread_parse_row__cpu"].append(time.thread_time() - c0)
            timers["reread_parse_row"].append(parse_s)
            t_reread_total += parse_s
            forward_calls += process_window(
                row, models, timers, digest, inference_by_cell=inference_by_cell
            )
            budget.check()
    # Stage: result serialisation + durable commit of 72 small receipts (one JSONL, fsynced).
    receipts = work_dir / f"{scenario.name}.receipts.jsonl"
    t_commit = time.perf_counter()
    with receipts.open("wb") as stream:
        for index in range(72):
            stream.write(_canonical({"record": index, "digest": digest.hexdigest()}) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    commit_s = time.perf_counter() - t_commit
    receipts_bytes = receipts.stat().st_size
    budget.charge_disk(receipts_bytes)
    cpu_seconds = time.process_time() - cpu_start
    snapshot.unlink()
    receipts.unlink()
    budget.release_disk(snapshot_bytes + receipts_bytes)
    if progress:
        progress(f"{scenario.name}: {windows} windows, {cpu_seconds:.1f} cpu-s")
    total_read_s = hash_s
    return ScenarioResult(
        scenario=scenario,
        windows=windows,
        timers=timers,
        forward_calls=forward_calls,
        row_bytes=row_bytes,
        inference_by_cell=inference_by_cell,
        cpu_seconds=cpu_seconds,
        peak_rss_bytes=budget.rss_peak_bytes(),
        deterministic_digest=digest.hexdigest(),
        io={
            "snapshot_bytes": float(snapshot_bytes),
            "write_seconds": write_s,
            "fsync_seconds": fsync_s,
            "write_mib_per_s": snapshot_bytes / 2**20 / max(write_s, 1e-9),
            "hash_readback_seconds": total_read_s,
            "hash_readback_mib_per_s": snapshot_bytes / 2**20 / max(hash_s, 1e-9),
            "reread_parse_mib_per_s": snapshot_bytes / 2**20 / max(t_reread_total, 1e-9),
            "result_commit_seconds": commit_s,
            "result_commit_bytes": float(receipts_bytes),
        },
    )


def bootstrap_mean_ci(
    values: list[float], *, resamples: int = 2000, seed: int = SYNTHETIC_SEED
) -> tuple[float, float, float]:
    """Mean and 95% bootstrap interval of the per-window mean."""
    if not values:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    data = np.asarray(values)
    means = rng.choice(data, size=(resamples, len(data)), replace=True).mean(axis=1)
    return float(data.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def project_workload(
    result: ScenarioResult, windows: int = HISTORICAL_WINDOWS, *, clock: str = "wall"
) -> dict[str, Any]:
    """Per-stage projection of the historical workload for one scenario, with a 95% interval."""
    stages: dict[str, Any] = {}
    total_mean = total_lo = total_hi = 0.0
    for stage in STAGES:
        if stage == "synthesize_window":
            continue  # synthetic-only cost; the real scorer streams real rows instead
        values = result.timers[stage if clock == "wall" else f"{stage}__cpu"]
        mean, lo, hi = bootstrap_mean_ci(values)
        stages[stage] = {
            "per_window_mean_s": mean,
            "projected_total_s": mean * windows,
            "projected_total_ci95_s": [lo * windows, hi * windows],
        }
        total_mean += mean * windows
        total_lo += lo * windows
        total_hi += hi * windows
    hash_total = result.io["hash_readback_seconds"] / result.windows * windows
    stages["sha256_readback"] = {"projected_total_s": hash_total}
    total_mean += hash_total
    total_lo += hash_total
    total_hi += hash_total
    return {
        "clock": clock,
        "stages": stages,
        "projected_scoring_path_total_s": total_mean,
        "projected_scoring_path_total_ci95_s": [total_lo, total_hi],
        "excludes": [
            "pinned source verification and research-population reconciliation",
            "real tracking-file decode and producer-stream replay during materialisation",
            "checkpoint loading",
        ],
    }


def to_report(
    results: list[ScenarioResult], budget: Budget, *, started_at: float, completed: bool
) -> dict[str, Any]:
    per_scenario: dict[str, Any] = {}
    for result in results:
        sample_forward = result.forward_calls / max(result.windows, 1)
        mean_row = statistics.fmean(result.row_bytes)
        per_scenario[result.scenario.name] = {
            "shape": {
                "roster_per_team": result.scenario.roster_per_team,
                "player_frame_missing_p": result.scenario.player_frame_missing_p,
                "ball_missing_p": result.scenario.ball_missing_p,
                "scoreable_scenes": result.scenario.scoreable_scenes,
            },
            "windows": result.windows,
            "forward_calls": result.forward_calls,
            "forward_calls_per_window": sample_forward,
            "mean_row_bytes": mean_row,
            "mean_row_bytes_vs_historical_mean": mean_row
            / (HISTORICAL_SNAPSHOT_BYTES / HISTORICAL_WINDOWS),
            "stage_latency": {stage: summarize(v) for stage, v in result.timers.items()},
            "inference_by_cell_median_s": {
                key: _percentile(v, 0.5) for key, v in sorted(result.inference_by_cell.items())
            },
            "inference_by_regime_mean_s": {
                regime: statistics.fmean(
                    [
                        statistics.fmean(v)
                        for key, v in result.inference_by_cell.items()
                        if key.startswith(regime)
                    ]
                )
                for regime in lds.INFORMATION_REGIMES
            },
            "cpu_seconds": result.cpu_seconds,
            "cpu_utilisation_hint": (
                result.cpu_seconds
                / max(
                    sum(sum(v) for k, v in result.timers.items() if not k.endswith("__cpu"))
                    + result.io["hash_readback_seconds"]
                    + result.io["fsync_seconds"]
                    + result.io["result_commit_seconds"],
                    1e-9,
                )
            ),
            "io": result.io,
            "deterministic_digest": result.deterministic_digest,
            "projection_to_historical_workload": project_workload(result),
            "projection_cpu_time_basis": project_workload(result, clock="cpu"),
        }
    totals = [
        s["projection_cpu_time_basis"]["projected_scoring_path_total_s"]
        for s in per_scenario.values()
    ]
    return {
        "schema_id": SCHEMA_ID,
        "synthetic_only": True,
        "completed": completed,
        "issue": "RES614",
        "historical_workload": {
            "eligible_windows": HISTORICAL_WINDOWS,
            "forward_calls": HISTORICAL_FORWARD_CALLS,
            "snapshot_bytes": HISTORICAL_SNAPSHOT_BYTES,
        },
        "runtime": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "torch": torch.__version__,
            "threads": torch.get_num_threads(),
            "deterministic_algorithms": torch.are_deterministic_algorithms_enabled(),
            "cpu_count": os.cpu_count(),
            "gpu_used": False,
        },
        "budget": {
            "cpu_seconds_limit": budget.cpu_seconds,
            "cpu_seconds_used": budget.cpu_used(),
            "rss_bytes_limit": budget.rss_bytes,
            "peak_rss_bytes": budget.rss_peak_bytes(),
            "disk_bytes_limit": budget.disk_bytes,
            "wall_seconds": time.time() - started_at,
        },
        "host_loadavg_at_report": list(os.getloadavg()),
        "scenarios": per_scenario,
        "scenario_sensitivity": {
            "projected_total_s_min": min(totals) if totals else None,
            "projected_total_s_max": max(totals) if totals else None,
        },
        "deterministic_digest": hashlib.sha256(
            "|".join(r.deterministic_digest for r in results).encode()
        ).hexdigest(),
        "limitations": [
            "Random weights share the real models' FLOP count but not their activation values.",
            "Synthetic rows imitate shape and byte size only; real content differs.",
            "Per-window times are extrapolated linearly to 51,713 windows; cache, thermal and "
            "contention effects over a ~30-60 minute run are not observed.",
            "The 6.8 GB real snapshot exceeds the sampled snapshots; page-cache behaviour for "
            "the full file is not measured.",
            "Source verification, tracking decode and producer replay are not benchmarked.",
        ],
    }


def run_benchmark(
    out: Path,
    work_dir: Path,
    *,
    windows: int,
    repeats: int,
    budget: Budget,
    scenarios: tuple[Scenario, ...] = SCENARIOS,
) -> dict[str, Any]:
    assert_synthetic_path(work_dir)
    assert_synthetic_path(out)
    work_dir.mkdir(parents=True, exist_ok=True)
    configure_cpu()
    started = time.time()
    models = build_random_models()
    results: list[ScenarioResult] = []
    completed = True
    try:
        # Untimed warm-up (counts against the budget) so lazy initialisation is excluded.
        run_scenario(Scenario("warmup"), 3, work_dir, budget, models)
        for _ in range(repeats):
            for scenario in scenarios:
                results.append(run_scenario(scenario, windows, work_dir, budget, models))
    except BudgetExceeded as exc:
        completed = False
        print(f"STOPPED: {exc}", file=sys.stderr)
    # Merge repeats of the same scenario into one result (concatenate samples).
    merged: dict[str, ScenarioResult] = {}
    for result in results:
        key = result.scenario.name
        if key not in merged:
            merged[key] = result
            continue
        base = merged[key]
        for stage, values in result.timers.items():
            base.timers[stage].extend(values)
        base.windows += result.windows
        base.forward_calls += result.forward_calls
        base.row_bytes.extend(result.row_bytes)
        base.cpu_seconds += result.cpu_seconds
        for cell, values in result.inference_by_cell.items():
            base.inference_by_cell.setdefault(cell, []).extend(values)
        for io_key in (
            "snapshot_bytes",
            "write_seconds",
            "fsync_seconds",
            "hash_readback_seconds",
            "result_commit_seconds",
        ):
            base.io[io_key] += result.io[io_key]
        base.deterministic_digest = hashlib.sha256(
            (base.deterministic_digest + result.deterministic_digest).encode()
        ).hexdigest()
    report = to_report(list(merged.values()), budget, started_at=started, completed=completed)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RES614 synthetic-only benchmark")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--windows", type=int, default=150)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--cpu-budget-s", type=float, default=DEFAULT_CPU_BUDGET_S)
    args = parser.parse_args(argv)
    report = run_benchmark(
        args.output,
        args.work_dir,
        windows=args.windows,
        repeats=args.repeats,
        budget=Budget(cpu_seconds=args.cpu_budget_s),
    )
    print(
        json.dumps(
            {
                "completed": report["completed"],
                "cpu_seconds_used": report["budget"]["cpu_seconds_used"],
                "peak_rss_bytes": report["budget"]["peak_rss_bytes"],
                "scenario_sensitivity": report["scenario_sensitivity"],
            },
            indent=2,
        )
    )
    return 0 if report["completed"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
