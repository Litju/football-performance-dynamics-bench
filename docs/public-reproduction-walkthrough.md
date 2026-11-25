# Reproducing the public football-motion research

This is a **clean-checkout, public-only** usage and verification path for FPD Bench. It requires no private registry, raw tracking data, model weights, held-out truth, checkpoint deserialization, empirical scoring or training. It **cannot** reproduce the underlying private learned-model execution, validate the protected 20-match population, or turn the four-match descriptive study into an independent experiment.

Use **CPython 3.12** for the supported full dependency group. The public smoke commands work without the separate PR #25 synthetic worker package; the *complete CI test suite* requires the separately pinned public package listed in [test prerequisites](reproducibility.md#test-prerequisites).

## 1. Install and discover what is executable

From a fresh clone of [the public repository](https://github.com/Litju/football-performance-dynamics-bench):

```bash
uv sync --locked --python 3.12
uv run fpdbench families list
uv run fpdbench benchmarks list
uv run fpdbench research-objects list
uv run fpdbench validate
uv run fpdbench data-states verify skillcorner_5hz_v2
uv run fpdbench eligibility verify skillcorner_window_v2
uv run fpdbench reproducibility check
```

`families list` includes research intents that do **not** have an executable benchmark. `benchmarks list` and `research-objects list` are different discovery paths. For details about one **historical reconstructed** benchmark (not the prospective SkillCorner v2 result), inspect:

```bash
uv run fpdbench benchmarks describe conditional_multi_agent_motion_prediction/absolute_position_prediction
uv run fpdbench benchmarks describe conditional_multi_agent_motion_prediction/origin_relative_displacement_prediction
```

The complete prospective scientific target definitions are in [the public benchmark cards](public-benchmark-cards.md) and the [versioned protocol](prospective-skillcorner-protocol-v2.md). **Verification of a protocol JSON does not imply qualification of its real population.**

## 2. Compute one physical trajectory metric on invented data

The public `fpdbench.evaluation` module uses no private data or learned model. This toy example has a single target, two time steps and distances of one metre in each step; it exercises the *metric kernel*, not the actual 15-step forecast protocol:

```bash
uv run python - <<'PY'
from fpdbench.evaluation.metrics.trajectory import masked_physical_trajectory_metrics

prediction = [[[[0.0, 0.0]], [[2.0, 0.0]]]]
truth = [[[[1.0, 0.0]], [[2.0, 1.0]]]]
metric = masked_physical_trajectory_metrics(prediction, truth, scale_xy_m=(1.0, 1.0))
print(f"ADE={metric.ade_m:.4f} FDE={metric.fde_m:.4f} XY_RMSE={metric.xy_rmse_m:.4f}")
assert round(metric.ade_m, 4) == 1.0
assert round(metric.fde_m, 4) == 1.0
assert round(metric.xy_rmse_m, 4) == 0.7071
PY
```

A deterministic origin-persistence baseline predicts the **observed origin position at each future step**. The one-second constant-velocity baseline estimates velocity from target-player history. Their published four-match results are **public metadata/aggregates**, not a rerun on withheld source data: [baseline results](res337-deterministic-research-results.md). In the completed study, displacement predictions were converted back to **physical absolute XY** before computing ADE/FDE/scalar-coordinate RMSE.

## 3. Independently reconcile published match-level aggregates

The repository includes the public, non-reconstructive [`findings.json`](res440/findings.json): six configuration means, 24 seed-averaged match means, four C1/C2 paired contrasts, baseline comparisons, seed-sensitivity summaries and denominators. Run the **read-only, standard-library-only** checker:

```bash
uv run python tools/inspect_public_findings.py
uv run pytest -q tests/unit/test_public_findings.py
```

The checker independently verifies the *public aggregate arithmetic*:
- exactly four independent evaluation-match entries and 51,713 overlapping windows (103,426 directed scenes);
- exactly six regimes × representations, one 18-checkpoint/four-match design with 72 learned match/seed records;
- each published ADE, FDE and XY-RMSE configuration mean against the **equal-weight four-match mean** of the available per-match, seed-averaged values;
- each C1 and C2 public match-paired ADE contrast against the public per-match configuration values and its equal-match mean;
- history-only persistence/constant-velocity published comparison summaries and their arithmetic, without predicting on unseen source rows.

Output consists of aggregate tables in stdout. The checker does **not** infer any model's seed-level predictions, recover private receipts, manufacture row-level evidence, or certify frozen training or population rights. It requires the source status to remain `research-only NOT_QUALIFIED` and fails when public aggregates disagree.

The source [scientific report](res440/results.md) explains each metric, the 3-second horizon, four-match uncertainty boundaries, and why realized future ball/opponent settings are **conditional** rather than ex-ante predictions. The 51,713 overlapping windows and 72 learned records are **not** independent match replicates.

## 4. Rebuild public figures from the public aggregates

The checked-in rendering script reads *only* `docs/res440/findings.json` and writes the existing `errors`, `contrasts` and `horizon` figure triplets (PNG, SVG, PDF) into `docs/res440`.

It needs Matplotlib **only for rendering**; it is not a benchmark runtime dependency:

```bash
uv run --python 3.12 --with matplotlib==3.11.2 python tools/plot_res440.py
```

Run it on a **disposable clean checkout** if you wish to compare generated files, because the plot command writes to tracked figure paths. Output is a recreation of public figures from the public aggregate JSON; it is **not** a recomputation of model scores from protected input bytes. Rendering engines/fonts may differ across environments. See [figure explanations](res440/results.md) and [Paper A figures/evidence](paper-a-evidence.md).

## 5. Understand external source verification (optional; not a download instruction)

The [source card](skillcorner-source-card.md) and [source authority](skillcorner-source-authority.md) identify SkillCorner Open Data, the pinned upstream revision, per-match filenames and LFS payload identities. If you already hold an **independently permitted external** checkout and want to check its identity, use:

```bash
uv run fpdbench sources verify --local-root /path/outside/this-repository
```

This checks local file identities; it does not fetch, distribute or copy source bytes. The optional `sources verify --live` checks public upstream metadata for drift, not model quality or legal clearance. **Do not place source tracking, derived rows, restricted receipts or checkpoint bytes in this Git checkout.** Source acquisition must follow the original provider's terms and the repository [rights policy](data-rights.md).

## 6. Understand LOMO without implying it was executed

The prospective v2 protocol retains **12 intended training leave-one-match-out folds** and frozen 12/4/4 source-match roles. The **216 planned learned LOMO fits were never run**. The completed learned study instead scored 18 final-role DeepSets checkpoints on four separate evaluation-role matches under the reviewed post-failure descriptive route.

The repository also contains an *unrelated historical recovered* five-training-match LOMO protocol for its earlier fixed-array benchmark. Those five folds are **not** the prospective SkillCorner program and do not substitute for its missing experiments. See [protocol v2](prospective-skillcorner-protocol-v2.md), [original experiment plan](prospective-experiment-plan-v2.md), [historical split distinctions](reproducibility.md#canonical-conditional-motion-split-protocols), and [study deviations](res440/results.md#methods-provenance-and-reuse).

## 7. Verify public packaging and evidence identities

With the separately pinned **public synthetic PR #25 source package** configured according to the [full-suite prerequisite](reproducibility.md#test-prerequisites), run:

```bash
uv sync --locked --all-groups --python 3.12
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
uv run fpdbench validate-naming
uv run fpdbench validate
uv run fpdbench evidence validate
uv run fpdbench reproducibility check
uv build
uv run python tools/wheel_smoke.py dist/*.whl dist/*.tar.gz
uv run python tools/res643_package_smoke.py dist/*.whl dist/*.tar.gz
uv run python tools/res645_package_smoke.py dist/*.whl dist/*.tar.gz
```

A successful public verification establishes package/test/documentation integrity for those exact sources and fixtures. It does **not** establish a completed original 234-fit experiment, owner-approved citation, dataset redistribution rights, archival DOI, or protected real-population qualification. A non-public local registry can be checked only if explicitly supplied by its authorized owner, outside the public workflow.

## 8. What a released result manifest can and cannot prove

- The [public aggregate findings](res440/findings.json) bind the descriptive result to protocol, execution, scope, result file and checkpoint/source hashes; they disclose **no private result bodies**.
- Source/checkpoint digests describe **identity assertions**; they cannot substitute for public checkpoint bytes or independent access to original source rows. The existing private readback was separately authenticated; the public checker cannot repeat that protected operation.
- Result summaries refer to exactly **four independent evaluation matches**, not 51,713 independent samples.
- Rights, authorship, citation and publication remain their own independent release-authority decisions, separate from scientific state hashes.

For the authoritative public capability classes, see [reproducibility.md](reproducibility.md#public-reproducibility-boundary) and the [source/model cards](public-data-and-model-cards.md).
