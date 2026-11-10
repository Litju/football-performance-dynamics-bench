# RES614 synthetic-only performance report

**Status: diagnostic engineering evidence. Not a scientific result.** Every number below comes from
invented tracking observations and randomly initialised model weights. Nothing here estimates model
quality, reproduces or substitutes for any of the 72 consumed RES594 result records, or touches the
retained private evaluation snapshot, checkpoints, labels or protected source data.

Harness: `tools/res614_synthetic_workload.py` (tests: `tests/unit/test_res614_synthetic_workload.py`).
Raw measurements: `docs/res614/synthetic_benchmark_v1.json` (final, CPU-time series) and
`docs/res614/synthetic_benchmark_run1_wall_only.json` (earlier run, wall-clock series only; kept
because its CPU spend counts against the budget).

## What was built

For each synthetic window the harness runs the same stage structure as the frozen scorer:

| Stage | Frozen scorer analogue | Synthetic stand-in |
|---|---|---|
| synthesize_window | producer/source decode (not measured for the real scorer) | NumPy random-walk players and ball, 41 samples, two directed scenes |
| materialize_row | `_prepare_verified_research_input` canonical JSONL write + fsync | canonical JSON write + fsync to a synthetic file |
| sha256 readback | `_secure_sha256(snapshot)` | SHA-256 over the synthetic file |
| reread_parse_row | `_read_json_lines` | `json.loads` per line |
| feature_construction | `build_scene_feature_payload` / `validate_feature_payload` / `collate_feature_payloads`, per regime | the same library functions, called per regime |
| model_inference | 18 `PerTargetContextDeepSetsMLP` forward calls per window | the same class, 18 randomly initialised models (3 regimes x 2 representations x 3 seeds), CPU FP32, one thread |
| metric_aggregation | `physical_metrics` plus horizon strata | the same `physical_metrics` plus horizon-stratum ADE |
| result commit | 72 receipts + campaign result, fsynced | 72 small JSONL lines, fsynced |

Row size was calibrated against the public historical mean of 6,815,838,287 B / 51,713 windows =
131,805 B per window. The nominal scenario produces 123.9 KiB (0.96x of that mean).

Scenarios (all reported; none is claimed to be the real mix):

| Scenario | Roster/team | Player-frame missing | Ball missing | Scoreable scenes | Row bytes vs historical mean |
|---|---|---|---|---|---|
| nominal | 14 | 2% | 1% | 2 | 0.96x |
| heavy_missingness | 14 | 15% | 10% | 2 | 0.85x |
| single_scene | 14 | 2% | 1% | 1 | 0.93x |
| large_roster | 23 | 2% | 1% | 2 | 1.53x |

## Budget compliance

| Resource | Limit | Used |
|---|---|---|
| Cumulative CPU | 600 s | run 1: 283.3 s; final run: 90.1 s; smoke runs and unit tests: small (a few tens of s). Estimated total ~ 410 s (including tests). The Budget class enforces the per-invocation limit and is unit tested. |
| Peak RSS | 2 GiB | 265.5 MB (run 1), 249.6 MB (final) |
| Temporary storage | 1 GiB | peak footprint of one synthetic snapshot <= 0.16 GB (run 1, large_roster); every snapshot is deleted before the next scenario. Cumulative bytes written: 0.79 GiB (run 1) + 0.32 GiB (final), well under any simultaneous footprint. |
| GPU / paid compute | 0 | 0 (`gpu_used: false`) |

No limit was exceeded and no run was stopped by the budget guard.

## Per-stage CPU time per window (final run, thread CPU time, ms; median / p95)

| Stage | nominal | heavy_missingness | single_scene | large_roster |
|---|---|---|---|---|
| reread_parse_row | 3.3 / 5.2 | 2.8 / 4.1 | 2.9 / 4.3 | 4.7 / 7.5 |
| feature_construction | 25.0 / 36.3 | 20.4 / 30.3 | 11.5 / 17.2 | 34.8 / 52.3 |
| model_inference (18 calls) | 21.1 / 34.4 | 18.5 / 29.0 | 16.0 / 28.1 | 19.4 / 32.2 |
| metric_aggregation | 11.9 / 19.2 | 10.5 / 16.7 | 5.7 / 9.8 | 10.5 / 17.1 |
| materialize_row (write) | 4.8 / 9.4 | 4.1 / 6.3 | 4.0 / 5.9 | 5.9 / 14.2 |

Model inference per forward call (mean over the nominal scenario): history_only 1.05 ms,
future_ball 1.12 ms, future_opponent_plus_ball 1.31 ms; absolute_xy vs origin_relative_displacement
and the three seeds differ by less than 0.7 ms and show no systematic pattern beyond first-model
warm-up. Calls are batch size <= 2, so cost is dominated by PyTorch dispatch overhead and the
Python feature path rather than FLOPs. The inference cost of the future-opponent regime is about
25% above history-only.

I/O (nominal, final run): canonical JSON write 17 MiB/s (CPU-bound serialisation, not the disk),
SHA-256 readback about 1.0 GiB/s, JSON reread/parse 36 MiB/s, fsync of a ~95 MB file about 0.04 s,
72-receipt commit about 5 ms. Hashing the entire historical snapshot would therefore cost minutes of
page-cache-assisted I/O at most; parse and serialise cost dominate, not hashing.

## Projection to the historical workload (51,713 windows, 930,834 forward calls)

Projection method: bootstrap (2,000 resamples) of the per-window mean for each stage, multiplied
by 51,713, summed over reread, features, inference and metrics (and materialise-write and hashing
for the full scoring path). Intervals are the 95% bootstrap interval of the *sampling* uncertainty of
the per-window mean only. They do not cover the model error from extrapolating synthetic content,
host-load changes or real-data distribution differences.

| Scenario | Scoring path, CPU-time basis (min) | 95% interval (min) | Wall-time basis (min) |
|---|---|---|---|
| nominal | 60.2 | 57.9 - 63.0 | 55.9 |
| heavy_missingness | 51.1 | 49.2 - 53.6 | 47.1 |
| single_scene | 35.7 | 34.4 - 37.0 | 32.6 |
| large_roster | 69.7 | 66.7 - 73.2 | 64.8 |

The nominal CPU-time stage breakdown is: features 22.1 min, inference 19.4 min, metrics 10.6 min,
materialise-write 4.8 min, reread 3.2 min, hashing 0.1 min.

Sensitivity: scene count is the largest driver (one versus two scoreable scenes changes the total
by about 40%), then roster size (feature path scales with players x frames), then missingness
(fewer players present means less to encode, so the heavy-missingness scenario is faster, not
slower). The scenario range 35.7 - 69.7 min brackets any plausible real mix; the real scene mix was
not observed.

**Reading against the historical run (inference, not demonstrated).** From file metadata (see
the incident report) the real snapshot stopped growing at 05:16:37 UTC and the run ended at
05:35:25 UTC, so about 18.8 minutes were spent after materialisation. The synthetic scoring-only
cost (reread + features + inference + metrics) is about 55 minutes in the nominal scenario (range
roughly 32 - 64 minutes across scenarios). Under this extrapolation the scorer had likely completed
about a third of its scoring pass (plausible range roughly 30% - 59%) when it ended, i.e. it was not
close to finishing, and a successful completion would have needed on the order of another 35 - 40
minutes in the nominal case. Even the pessimistic projection (~70 min plus materialisation and
source verification) is far below the authorised 14,400 CPU-second (4 h) and 21,600 wall-second (6 h)
ceilings, so the resource caps were not the binding constraint.

## Limitations (explicit)

1. Random weights have the real FLOP count but not real activation values; branch-free MLP timing
   should transfer, but this was not verified against real checkpoints (forbidden).
2. Synthetic rows imitate shape and size only. Real JSON content (key mix, float formatting,
   nulls) changes parse and serialise cost.
3. Linear extrapolation from 100-window samples (x3 repeats) to 51,713 windows ignores cache,
   thermal and contention effects over a 1 - 4 hour run.
4. The host was shared and heavily loaded (load average 4 - 11 on 8 logical CPUs during the
   runs, recorded in the JSON). Contention inflates the wall series and, to a lesser degree, CPU time;
   run 1's nominal wall-clock series shows a 6x median/p95 spread that the CPU-time series removes.
   Projections are therefore more likely pessimistic than optimistic.
5. Source verification, research-population reconciliation, tracking decode, producer replay and
   checkpoint loading were not measured; they preceded the snapshot in the historical run
   (about 2.4 minutes before the snapshot file was created and about 9.5 minutes of materialisation).
6. The 6.8 GB real snapshot was not recreated; page-cache effects for a file that size were not
   measured. WSL had 20 GB of memory, so it likely stayed cached.

## Reproducibility

`uv run python tools/res614_synthetic_workload.py --output OUT.json --work-dir DIR --windows 100 --repeats 3 --cpu-budget-s 200`
reproduces the measurement structure. All synthetic content and model weights are seeded (seed 614
plus scenario hash); the `deterministic_digest` field is bitwise stable across runs (unit test
`test_run_is_deterministic`), while timing fields vary with host load.
