# Scientific evaluation library

The no-third-party-dependency `fpdbench.evaluation` package owns the shared metric kernels and the raw displacement scorer. Benchmark modules validate task-specific inputs and delegate score calculation to this library. Evaluator version/configuration and calibration metadata are separate from `BenchmarkDefinition` identity.

## Raw vector metrics

For `N > 0` scalar observations, RMSE is

`sqrt(sum((prediction - truth)²) / N)`.

Population standardized relative error is

`RMSE(prediction, truth) / sqrt(sum((truth - mean(truth))²) / N)`.

The denominator uses the evaluated population's truth values with `ddof=0`. SRE is dimensionless when variance is nonzero. The common SRE function defaults to an explicit error for constant truth; callers may select `zero_variance="rmse"` to return unnormalized RMSE. Inputs must be finite, nonempty, and the same length.

Stable raw metric IDs are `rmse.global.v1` and `sre.rmse_over_population_std.v1`; trajectory IDs are `trajectory.ade_m.v1`, `trajectory.fde_m.v1`, and `trajectory.xy_rmse_m.v1`.

## Absolute-position trajectories

The absolute-position benchmark delegates physical scoring to `physical_trajectory_metrics`. Pitch-normalized coordinate residuals are scaled by `(52.5 m, 34.0 m)` before scoring.

- ADE is the arithmetic mean Euclidean distance over every evaluated entity and forecast step, in metres.
- FDE is the arithmetic mean Euclidean distance over entities at the final forecast step, in metres.
- Physical XY-RMSE is the square root of the mean squared residual over all x and y scalar coordinates, in metres.

These physical diagnostics are separate from the historical calibrated scorer. The raw absolute-position evaluator returns 330 per-target SRE values, the progress transform applies the locked floors/weights, and the historical scorer maps aggregate progress through the locked clamped piecewise-linear curve.

The raw scorer uses evaluated-population truth (`ddof=0`) and RMSE fallback for zero variance. The calibration lock supplies each target's reference, raw floor, no-information ceiling, and weight. Per-target progress is `clamp(1 - SRE / min(raw_floor, no_information_ceiling), 0, 1)`, aggregated with equal `1/330` weights. The lock is bundled byte-for-byte with SHA-256 `f3b4155899c5d8e9632e9cab7a25e471411c62c4a9a7489c58c1edb16180ce94`; the R2 evaluator artifact is `41db5a6fb1d4a05db0bf2060b96336a2c3e86ec9ab25dfd7aaa16390e0c0defa`. The recovered `x_ref` is `0.9616270652419386`; curve knots are `(0,0)`, `(x_ref,0.5)`, and `(1,1)`. The reference vector scores `0.5`, perfect targets score `1`, and no-information targets score `0`.

## Origin-relative displacement raw score

Each evaluated row has `15 × 11 × 2 = 330` scalar displacement targets. For each target independently, the scorer computes RMSE divided by the population SD of truth across the evaluated rows (`ddof=0`). It gives every scalar target equal weight and returns their arithmetic mean. Raw values are not clipped. Lower is better; a perfect predictor scores `0`; a per-scalar population-mean predictor scores `1` when truth variance is nonzero.

If a scalar target has zero evaluated-population variance, its SRE falls back to that target's RMSE in normalized displacement units. This is the recovered raw evaluator behavior. It does not define a calibrated reward.

Calibration remains separate and UNKNOWN for the generated calibration lock, reference vector, no-information ceiling vector, `x_ref`, and calibrated reward. Unknown calibration cannot emit a reward. The generic piecewise-linear transform is only a utility and does not supply missing calibration.

## Benchmark bindings and research boundaries

- `conditional_multi_agent_motion_prediction/absolute_position_prediction` binds ADE metres, FDE metres, physical XY-RMSE metres, and the separate evidence-backed historical scorer above.
- `conditional_multi_agent_motion_prediction/origin_relative_displacement_prediction` binds the 330-target raw population-SRE scorer above; calibrated reward remains unavailable.

Scorer or calibration changes do not create a benchmark identity. Signed tangential acceleration uses global full-row RMSE in m/s² with no normalization; the lost B5 single-channel submetric remains unavailable, and the formulation remains invalidated. The sensor-state pilot uses per-channel population SRE (`ddof=0`), `q=clamp(1-SRE,0,1)`, equal-channel means, a fixed corruption-region mask with at least 256 selected rows/channel, and a public non-expert maximum-quality gate of `0.30`. It remains a scoped negative result: no target family was selected and no benchmark reward is emitted. Whole-session, signed acceleration, and sensor-state remain non-benchmark research objects. Future Response remains a family with no evaluator or benchmark identity.
