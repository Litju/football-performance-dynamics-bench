# Research-only final fits

## Frozen scope

This campaign completed the `per_target_context_deepsets_mlp_v1` cell from the
frozen v2 plan: three information regimes, two target representations, and seeds
1729, 2718, and 31415, for exactly 18 final-role fits. Each fit trained on the
same 12 training matches and selected its checkpoint using only the equal-match
mean physical ADE on the same four validation matches. Evaluation-role data,
labels, and predictions were not staged or scored. No learned LOMO or held-out
evaluation was run.

The model, exact features, masks, information boundaries, AdamW settings,
batch-size-128 sampling distribution, masked ADE loss, 100-step validation
cadence, earliest-checkpoint tie rule, patience of 10, and 5,000-step maximum
were unchanged. The selected step and stopping reason for every fit are listed
below.

## Prospective GPU amendment

The original v2 execution plan remains unchanged and CPU-only. A separate,
prospective research-only amendment authorized this private Colab GPU execution
before the first fit. All 18 fits used an NVIDIA A100-SXM4-40GB with CUDA 12.4,
driver 580.82.07, Python 3.12.8, NumPy 2.2.4, and PyTorch 2.6.0+cu124.
Deterministic CUDA settings were enabled, TF32 and mixed precision were disabled,
and synthetic CPU/GPU agreement and deterministic replay qualifications passed.
The GPU run is not claimed to be bitwise equivalent to the original CPU plan.

Private tracking and feature caches, checkpoints, receipts, and validation-match
metrics remain in owner-only Google Drive storage. Public output here is limited
to fit-level aggregates; it contains no match identifiers, rows, targets,
predictions, or checkpoints. The private research-data-handling amendment
permits this owner-authorized, access-controlled computation and temporary
staging while retaining attribution and the ban on public raw or row-level
distribution. It does not assert new upstream redistribution rights.

## Equal-match validation results

Each seed value is the arithmetic mean of its four validation-match ADE values
in metres. Cell mean and SD summarize the three frozen seeds; SD is the sample
standard deviation and is descriptive, not an inferential interval.

| Information regime | Target representation | Seed 1729 | Seed 2718 | Seed 31415 | Mean ± SD across seeds |
|---|---|---:|---:|---:|---:|
| `history_only` | `absolute_xy` | 2.176 | 2.125 | 2.281 | 2.194 ± 0.080 |
| `history_only` | `origin_relative_displacement` | 1.737 | 1.729 | 1.730 | 1.732 ± 0.004 |
| `future_ball` | `absolute_xy` | 1.814 | 1.924 | 1.948 | 1.895 ± 0.072 |
| `future_ball` | `origin_relative_displacement` | 1.465 | 1.483 | 1.481 | 1.476 ± 0.010 |
| `future_opponent_plus_ball` | `absolute_xy` | 1.691 | 1.883 | 1.755 | 1.776 ± 0.098 |
| `future_opponent_plus_ball` | `origin_relative_displacement` | 1.351 | 1.341 | 1.342 | 1.345 ± 0.005 |

## Fit matrix

| Information regime | Target representation | Seed | Validation ADE (m) | Selected step | Optimizer steps | Stopping reason |
|---|---|---:|---:|---:|---:|---|
| `history_only` | `absolute_xy` | 1729 | 2.176 | 2,100 | 3,100 | patience 10 |
| `history_only` | `absolute_xy` | 2718 | 2.125 | 3,900 | 4,900 | patience 10 |
| `history_only` | `absolute_xy` | 31415 | 2.281 | 1,300 | 2,300 | patience 10 |
| `future_ball` | `absolute_xy` | 1729 | 1.814 | 5,000 | 5,000 | maximum steps |
| `future_ball` | `absolute_xy` | 2718 | 1.924 | 3,100 | 4,100 | patience 10 |
| `future_ball` | `absolute_xy` | 31415 | 1.948 | 2,300 | 3,300 | patience 10 |
| `future_opponent_plus_ball` | `absolute_xy` | 1729 | 1.691 | 4,800 | 5,000 | maximum steps |
| `future_opponent_plus_ball` | `absolute_xy` | 2718 | 1.883 | 2,100 | 3,100 | patience 10 |
| `future_opponent_plus_ball` | `absolute_xy` | 31415 | 1.755 | 3,700 | 4,700 | patience 10 |
| `history_only` | `origin_relative_displacement` | 1729 | 1.737 | 4,900 | 5,000 | maximum steps |
| `history_only` | `origin_relative_displacement` | 2718 | 1.729 | 4,600 | 5,000 | maximum steps |
| `history_only` | `origin_relative_displacement` | 31415 | 1.730 | 4,500 | 5,000 | maximum steps |
| `future_ball` | `origin_relative_displacement` | 1729 | 1.465 | 5,000 | 5,000 | maximum steps |
| `future_ball` | `origin_relative_displacement` | 2718 | 1.483 | 4,500 | 5,000 | maximum steps |
| `future_ball` | `origin_relative_displacement` | 31415 | 1.481 | 4,600 | 5,000 | maximum steps |
| `future_opponent_plus_ball` | `origin_relative_displacement` | 1729 | 1.351 | 4,700 | 5,000 | maximum steps |
| `future_opponent_plus_ball` | `origin_relative_displacement` | 2718 | 1.341 | 4,700 | 5,000 | maximum steps |
| `future_opponent_plus_ball` | `origin_relative_displacement` | 31415 | 1.342 | 4,600 | 5,000 | maximum steps |

## Verification and limits

All 18 selected checkpoints and all 18 completed-fit receipts were uploaded to
private Drive storage using content-addressed filenames, then downloaded and
SHA-256 verified against their local bytes. The content-addressed progress index
records 18 `COMPLETED_AND_VERIFIED` fits, zero failed fits, zero pending fits,
and zero retry-eligible fits. The aggregate validation report and full
match-level evidence are stored privately.

Receipts bind each fit to the frozen research-population manifest, plan,
protocol, feature-mask identity, configuration, runtime environment, A100
session, checkpoint hash, and the exact four-match validation metrics. Total
optimizer steps were 80,500 and summed per-fit GPU wall time was about 3.14
hours. Session interruptions were recovered without changing fit configuration
or counting an incomplete fit as complete.

These are validation-only development results for the one frozen learned-model
cell. They do not qualify the protected population, establish held-out
performance, authorize deployment, or provide a CPU/GPU bitwise-equivalence
claim. The protected population remains `NOT_QUALIFIED`.
