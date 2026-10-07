# Scientific evaluation library

The no-third-party-dependency `fpdbench.evaluation` package owns the shared metric kernels and the raw displacement scorer. Benchmark modules validate task-specific inputs and delegate score calculation to this library. Evaluator version/configuration and calibration metadata are separate from `BenchmarkDefinition` identity.

## Raw vector metrics

For `N > 0` scalar observations, RMSE is

`sqrt(sum((prediction - truth)²) / N)`.

Population standardized relative error is

`RMSE(prediction, truth) / sqrt(sum((truth - mean(truth))²) / N)`.

The denominator uses the evaluated population's truth values with `ddof=0`. SRE is dimensionless when variance is nonzero. The common SRE function defaults to an explicit error for constant truth; callers may select `zero_variance="rmse"` to return unnormalized RMSE. Inputs must be finite, nonempty, and the same length.

## Absolute-position trajectories

The absolute-position benchmark delegates physical scoring to `physical_trajectory_metrics`. Pitch-normalized coordinate residuals are scaled by `(52.5 m, 34.0 m)` before scoring.

- ADE is the arithmetic mean Euclidean distance over every evaluated entity and forecast step, in metres.
- FDE is the arithmetic mean Euclidean distance over entities at the final forecast step, in metres.
- Physical XY-RMSE is the square root of the mean squared residual over all x and y scalar coordinates, in metres.

These are the exposed evidence-supported physical metrics. Exact historical scorer-wrapper parity remains UNKNOWN; no historical calibrated reward is exposed.

## Origin-relative displacement raw score

Each evaluated row has `15 × 11 × 2 = 330` scalar displacement targets. For each target independently, the scorer computes RMSE divided by the population SD of truth across the evaluated rows (`ddof=0`). It gives every scalar target equal weight and returns their arithmetic mean. Raw values are not clipped. Lower is better; a perfect predictor scores `0`; a per-scalar population-mean predictor scores `1` when truth variance is nonzero.

If a scalar target has zero evaluated-population variance, its SRE falls back to that target's RMSE in normalized displacement units. This is the recovered raw evaluator behavior. Exact historical scorer-wrapper parity remains UNKNOWN, and this raw score is not a calibrated reward.

Calibration remains separate and UNKNOWN for the generated calibration lock, reference vector, no-information ceiling vector, `x_ref`, and calibrated reward. Unknown calibration cannot emit a reward. The generic piecewise-linear transform is only a utility and does not supply missing calibration.

## Benchmark bindings and research boundaries

- `conditional_multi_agent_motion_prediction/absolute_position_prediction` binds ADE metres, FDE metres, and physical XY-RMSE metres. It makes no exact historical wrapper-parity claim.
- `conditional_multi_agent_motion_prediction/origin_relative_displacement_prediction` binds the 330-target raw population-SRE scorer above; calibrated reward remains unavailable.

Scorer or calibration changes do not create a benchmark identity. Signed acceleration may reuse common RMSE; sensor-state may reuse common SRE, while its quality conversion and gate remain research-study logic. Whole-session, signed acceleration, and sensor-state remain non-benchmark research objects. Future Response remains a family with no evaluator or benchmark identity.
