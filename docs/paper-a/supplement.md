# Paper A supplementary materials

This is the canonical repository companion to the manuscript and its reviewer appendix. It points to the frozen authorities and their public checks. The empirical scope is four fixed evaluation matches under the completed research-only, `NOT_QUALIFIED` study.

## Benchmark and task cards

The [benchmark/task matrix](../paper-a-evidence.md#1-benchmark-and-task-matrix) specifies each recovered object and both prospective targets, including inputs, units, horizon, evaluators and status. The [registry](../../src/fpdbench/benchmarks/registry.py) distinguishes executable contracts, scientific maturity and family scope.

| Card | Intended use | Comparison boundary |
| --- | --- | --- |
| Historical conditional absolute XY | Evaluate recovery of the fixed-array conditional task. Inspect normalized position targets and population SRE, or the locked absolute calibration on its bound population. | Requires realized future ball and opponent context. Bind the original or repaired measurement/membership state explicitly. |
| Historical conditional origin-relative displacement | Inspect the recovered target transform, inverse and raw displacement SRE. | Same conditioning, separate benchmark identity. The recovered raw evaluator supplies no calibrated displacement reward or full model parity. |
| Prospective SkillCorner v2 absolute XY and displacement | Forecast with authorized history or evaluate either realized-future conditioning regime. Use the same origin players, windows and masks for both encodings, and score in physical XY. | Variable origin panel, 26 history samples, 15 future steps at 5 Hz. ADE, FDE, scalar-coordinate XY RMSE. The reported learned study is research-only. |
| Other historical families | Inspect archival or negative evidence about whole-session state, signed acceleration, sensor-state reconstruction and future response. | The retained objects support different levels of recovery. None establishes an executable, valid benchmark for its family. |

The three Paper A schematics are available as [genealogy](genealogy.pdf), [information boundary](information-boundary.pdf), and [evaluation design](evaluation-design.pdf). SVG and PNG copies and captions are indexed in the [figure notes](../paper-a-evidence.md#2-benchmark-genealogy).

## Source, eligibility and frozen evaluation

- **Source and rights.** [Pinned SkillCorner Open Data release](https://github.com/SkillCorner/opendata/tree/4340d274572876239c154c90bc507a9b3250a656), [source authority](../skillcorner-source-authority.md), [v2 data card](../skillcorner-data-card-v2.md), [measurement state](../skillcorner-data-state-v2.md), and [rights policy](../data-rights.md). SkillCorner supplied the data in a joint initiative with PySport. The source authority gives match membership, acquisition references and checksums.
- **Membership and inputs.** [v2 eligibility](../skillcorner-window-eligibility-v2.md), [v2 protocol](../../src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction/prospective_skillcorner_protocol_v2.json), and [research admission](../research-population-admission-v1.md). Source presence and detection provenance are distinct. Membership rules can inspect support across the whole window. Truth, eligibility and quality audits stay outside learned inputs.
- **Scoring.** [Evaluator specification](../evaluation.md), [historical absolute calibration lock](../../src/fpdbench/evaluation/absolute_xy_calibration_lock.json), [historical scientific locks](../../benchmarks/conditional_multi_agent_motion_prediction/), and [prospective metrics and uncertainty](../prospective-skillcorner-protocol.md#metrics-and-uncertainty). Use the metrics, units and aggregation bound to each result. A physical XY RMSE uses the scalar-coordinate denominator and is averaged by the frozen hierarchy.
- **Fit and result provenance.** [Original plan](../../src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction/empirical_experiment_plan_v2.json), [pre-evaluation amendment](../res593-amended-heldout-evaluation-v1.md), [18-checkpoint manifest](../../src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction/res593_checkpoint_manifest_v1.json), [post-failure descriptive protocol](../../src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction/res635_post_failure_descriptive_protocol_v1.json), [frozen deterministic reference](../../src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction/res593_baseline_reference_v1.json), and [public findings and digests](../res440/findings.json). The published results describe the authenticated result and receipt readback. Public hashes identify the private inputs to that readback.

## Claims-to-evidence index

| Manuscript claim | Evidence and scope |
| --- | --- |
| Measurement repair can preserve task identity. A change of target/reference frame or authorized information can change the question. | [Typed identities](../../src/fpdbench/benchmarks/base.py), [historical transitions](../benchmark-transitions.md), [historical provenance](../results-and-provenance.md). |
| Future target truth is excluded from authorized input bundles. Realized future ball/opponent context changes the prediction setting. | [Information-boundary contract](../../src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction/information.py), [forecast origin](../../src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction/forecast_origin.py), and [prospective contract](../prospective-skillcorner-protocol-v2.md). This is evidence about the named contracts and feature checks. |
| Inversion preserves physical residuals given a shared origin. Evaluated-population standardization can still change scores. | [Target transforms](../../src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction/origin_relative_displacement_prediction.py), [metric definitions](../evaluation.md), and [synthetic round trip](../reproducibility.md#public-reproducibility-boundary). |
| The four-match demonstration has 18 frozen checkpoints, 72 verified learned match-scoped records and 51,713 overlapping windows. The history-only displacement ADE is 1.6680 m against 2.2433 m for constant velocity. | [Findings](../res440/findings.json) (`records`, `windows`, `independent_units`, `history_baseline_comparisons`) and [physical forecast comparators](../res440/tables.md#3-history-only-comparisons-with-frozen-deterministic-baselines). The comparison concerns the frozen systems and matches. |
| Public executability, public verifiability and private replay are different capabilities. | [Public snapshot](../../benchmarks/reproducibility_snapshot.json), [capability definitions](../reproducibility.md#public-reproducibility-boundary), [result release boundary](../res440/results.md#methods-provenance-and-reuse). |
| Negative, invalidated and missing outcomes constrain reconstruction. | [Record-level evidence pointers](../paper-a-related-work-and-claims.md#a6--negative-and-unrecoverable-historical-outcomes) and [sealed historical evidence](../paper-a-related-work-and-claims.md#a7--recorded-historical-performance-not-new-execution). |

## Negative, invalidated and unrecoverable outcomes

- The whole-session workload study lacks the complete original schema, target units, split, scorer and result-bearing binding. Future response forecasting survives as intent without a recovered task or scorer.
- The synthetic signed-acceleration formulation was invalidated. Its diagnostic RMSE and model bindings survive, while the exact invalidation trigger is unavailable. The separate synthetic multimodal sensor pilot selected no candidate target within its recorded gate.
- The original absolute-position experiment did not beat simple physical baselines in its recorded scope. Later repaired-state viability records have a different measurement and membership binding. No row-level crosswalk resolves the populations.
- The original displacement aggregate was invalidated by a tuple-order assignment error. The retained correction recombines sealed fold results without retraining. The generated displacement calibration and full historical model parity remain unrecovered.
- The initial learned held-out execution entered scoring and terminated without a committed, recovered or analyst-observed learned outcome. This is a historical non-result. The later, separately authorized descriptive execution is the source of the present demonstration. The original 234-fit design remains incomplete, including all 216 deferred training leave-one-match-out fits. The four-match deletion sensitivity in the canonical results recomputes means with one match omitted and fits no models.

## Reproduction and availability

From the repository root, with Python 3.12 and `uv`:

```sh
uv sync --locked --all-groups
uv run --locked fpdbench validate-naming
uv run --locked fpdbench validate
uv run --locked fpdbench evidence validate
uv run --locked fpdbench reproducibility check
uv run --locked fpdbench data-states verify skillcorner_5hz_v2
uv run --locked fpdbench eligibility verify skillcorner_window_v2
uv run --locked pytest -q tests/unit/test_benchmark_contracts.py tests/unit/test_prospective_trajectory_metrics.py tests/unit/test_paper_a_evidence.py tests/unit/test_res440_analysis.py
```

Regenerate drawings and plots in a disposable checkout or worktree, since the scripts write to the existing figure paths. This reads the tracked authorities and aggregate findings.

```sh
uv run --no-project --python 3.12 --with matplotlib==3.11.2 python tools/plot_paper_a_schematics.py
uv run --no-project --python 3.12 --with matplotlib==3.11.2 python tools/plot_res440.py
```

| Capability | Available evidence |
| --- | --- |
| Publicly executable | Synthetic target/evaluator and boundary checks, lock/snapshot regeneration, aggregate plotting and checks on reported values. |
| Publicly verifiable | Historical result and checkpoint identities, public fit/role accounting, descriptive results tables and aggregate-safe provenance. Upstream source acquisition is separate. |
| Registry-local | Strict hash resolution of archived evidence requires the canonical local registry and any referenced local bytes. See the [registry boundary](../reproducibility.md#evidence-registry-content-digest). |
| Owner-private | Learned checkpoints, the match/seed input bundle, receipt bodies, execution ledger, truth masks and predictions. The existing [analysis command](../res440/results.md#methods-provenance-and-reuse) requires the authorized result bundle. |
| Unavailable or forbidden | Public historical checkpoint replay and complete historical fixture regeneration are unavailable. Historical private qualification truth is forbidden. No protected qualification PASS or training LOMO result exists. |

Original project code and documentation carry [Apache-2.0](../../LICENSE). The code license grants no upstream data rights. The current [publication policy](../data-rights.md#fpd-bench-v1-release-policy) permits non-reconstructive aggregate outputs and provenance with attribution. Source rows, row-level derivatives, private truth and unapproved weights are excluded from the package.

## Canonical full campaign evidence

The following are repository references for provenance and owner review. The archival reviewer appendix carries the bounded Paper A demonstration. The detailed empirical matrix and figures belong to the Paper B analysis.

- [Complete results narrative](../res440/results.md), [tables including all match contrasts and denominators](../res440/tables.md), and [full-precision aggregates](../res440/findings.json).
- [Physical errors](../res440/errors.pdf), [paired contrasts](../res440/contrasts.pdf), and [horizon results](../res440/horizon.pdf). PNG and SVG variants are linked from the results narrative.
