# Public source, model and limitation cards

**Release scope:** this is documentation for the public FPD Bench research-software checkout and public aggregate evidence. It is **not** a downloadable tracking dataset, model-weight release, or protected evaluation qualification. Scientific task definitions and their four-match research demonstration are described in the companion [benchmark cards](public-benchmark-cards.md).

## Data and source card

| Attribute | Documented state |
| --- | --- |
| Provider | **SkillCorner Open Data**, published by SkillCorner jointly with PySport |
| External source | [SkillCorner/opendata](https://github.com/SkillCorner/opendata), pinned commit `4340d274572876239c154c90bc507a9b3250a656` |
| FPD source population | 20 source-match file inventories in one competition edition; 12 training, 4 validation, 4 evaluation roles in the prospective protocol |
| Source cadence | Provider tracking at 10 Hz; selected canonical 5 Hz samples without interpolation or imputation |
| Source measurements | Pitch-centred player and ball XY in metres; match/period and provider flags as separate provenance and quality variables |
| Successor measurement | `skillcorner_5hz_v2`, preserving absent vs present-null ball states and nullable detection flags |
| Successor eligibility | `skillcorner_window_v2`: 25 prior history intervals, origin and 15 future intervals; finite ball XY in at least 39 of 41 expected samples, and at origin; additional participation/phase/player/quality requirements |
| Source rights | **CONDITIONAL GO** for local public-source research processing; **NO FPD redistribution** of core tracking, events, phases, row-level derived data pending written rights clarification |
| Available release content | External acquisition/verification contracts, source/schema metadata, synthetic checks, non-reconstructive scientific aggregates and figures |
| Not included | Raw tracking/events/phases, full row-level windows, player histories, match-scoped predictions, private receipt bodies, truth masks, private checkpoints |
| Protected population | `NOT_QUALIFIED`, including the frozen 20-match protected gate |

**Source inventory is not benchmark eligibility.** Twenty match directories and complete expected provider filenames do not prove that every frame/window can be scored. Candidate diagnostics that pass their local rules remain `UNQUALIFIED` until the separate authenticated population qualification succeeds. Source quality and admission in the independently authorized descriptive research study are distinct from the unqualified protected-production gate.

The v2 eligibility policy explicitly refuses an observed null ball detection flag paired with finite ball XY, because that unobserved source combination has no approved interpretation. Provider detection flags, coordinate availability, missingness and quality are not interchangeable and must not be silently repaired. The source is based on broadcast-derived tracking; provider extrapolation, occlusion, identity errors, incomplete phase coverage and camera selection remain limitations.

Detailed authority: [source card](skillcorner-source-card.md), [source pin and checksums](skillcorner-source-authority.md), [data card v2](skillcorner-data-card-v2.md), [eligibility policy v2](skillcorner-window-eligibility-v2.md), [rights audit](data-rights.md) and [reproducibility model](reproducibility.md). This documentation does not independently prove data rights or participant consent.

## Baseline card: origin persistence

| Attribute | Description |
| --- | --- |
| Identifier | `origin_persistence_v1` |
| Information used | Observed target-player origin position only (history available at `t=0`) |
| Prediction | Hold the origin position through the 15 future forecast steps |
| Status | Deterministic reference; published four-match research-only descriptive scores |
| Evaluation ADE / FDE / XY RMSE | **3.5219 / 6.3739 / 3.0952 m** |
| Interpretation | A no-motion physical-space reference, not a tactical or learned forecasting system |

The physical prediction is the same under either target encoding or conditioning label; the baseline does **not** consume realized future ball or opponent context. Other role-level metrics and per-match scores are in [the deterministic results](res337-deterministic-research-results.md).

## Baseline card: one-second constant velocity

| Attribute | Description |
| --- | --- |
| Identifier | `constant_velocity_1s_v1` |
| Information used | Observed target-player positions in the preceding second |
| Prediction | Extend recent target-player velocity over the three-second horizon |
| Status | Deterministic reference; same research-only cohort, mask, forecast horizon and scoring hierarchy as learned history-only cells |
| Evaluation ADE / FDE / XY RMSE | **2.2433 / 4.9257 / 2.2384 m** |
| Interpretation | A target-history-only kinematic reference; not conditioned on future ball/opponents |

The reference is **comparable to history-only** learned forecasting at the full-system level, not a controlled architecture-only ablation. Frozen learned systems can use broader historical context. Evaluation outputs are public aggregates only; [detailed baselines](res337-deterministic-research-results.md).

## Model card: frozen per-target context DeepSets MLP

| Attribute | State |
| --- | --- |
| Identifier | `per_target_context_deepsets_mlp_v1` |
| Architecture class | Per-target-context DeepSets / MLP; the completed empirical study contains one learned architecture class, not the original proposed ladder |
| Factorial study | 3 information regimes × 2 target encodings × 3 seeds = **18** separately trained and validation-selected final-role checkpoints |
| Frozen seeds | 1729, 2718 and 31415 |
| Training membership | Twelve fixed source matches |
| Checkpoint selection | Four *validation* matches; validation ADE equal-averaged by match, with frozen checkpoint selection/stopping rules |
| Training environment | Owner-controlled Colab A100 GPU under a separately approved private-compute amendment; the original CPU experiment plan was not altered or satisfied as written |
| Validation reference | [Public final-fit validation summary](res338-research-final-fits.md); selected hashes/steps in the frozen [checkpoint manifest](../src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction/res593_checkpoint_manifest_v1.json) |
| Completed evaluation | Four fixed evaluation matches under the separately authorized post-failure **descriptive-only** research route; 72 learned match/seed result records |
| Deployment | **Not demonstrated or authorized** |
| Weights and inference | **No weights, checkpoint bytes, trained inference or row-level prediction artifacts are distributed** |
| Population classification | Protected population remains `NOT_QUALIFIED` |

The public [scientific results](res440/results.md) contain all six configuration-level physical ADE/FDE/XY-RMSE summaries, matched baseline comparisons, seed/match variation and descriptive context contrasts. Lower ADE with *realized future* ball/opponent observations is not evidence of better ex-ante forecasts. A smaller result for origin-relative displacement does not establish an intrinsic superiority independent of fitting and checkpoint selection. Neither model nor benchmark is medically, tactically or commercially deployment-qualified.

The trained checkpoints and research receipts were retained privately. Their cryptographic identifiers support provenance references, **not** public rerunning of the fitted models. There is no public checkpoint download under this card. Original 234-fit planning and 216 unexecuted training-LOMO fits must not be reported as completed.

## Scientific limitations and responsible-use guidance

1. **Independent unit is match, n=4.** Overlapping windows (51,713) and seed records (72) are not independent replications. No independent-match inferential standard error, confidence interval, p-value, or generalization claim is supported by this study.
2. **Incomplete original experimental program.** The completed study is an amended/post-failure descriptive demonstration on frozen checkpoints. The original 234-fit prospective matrix and the 216-fit training LOMO campaign are not complete. Deleting one evaluation match from an aggregate is descriptive sensitivity, **not** training LOMO.
3. **Source extrapolation.** Among 17,065,290 counted scored player-time observations (with overlap), **6,008,819 (35.2%)** are provider-extrapolated. Only 1,343 of 103,426 directed scenes were detected-only. This is *not* validation against independent positional ground truth, nor a model bias estimate for the entire source.
4. **Information availability.** Only `history_only` is an ex-ante forecast setting. The other two regimes consume realized future context unavailable at the origin and have no validated upstream ball/opponent prediction-error propagation.
5. **Scope and selection.** One professional competition edition/season, four evaluation matches, provider-derived tracking and validation-selected checkpoints. No support is established for other leagues, age groups, countries, levels, providers, match distributions or new seasons.
6. **Data ethics and personal inference.** Professional-player movement traces can remain re-identifiable when linked to video or lineup context. The public cards do not establish consent or ethics approval. Do **not** use these findings for individual ability profiling, recruitment/selection, compensation, medical decisions, betting, surveillance or live tactical automation.
7. **Scientific availability.** Public transforms, evaluator and synthetic verification are executable. Historical private truth is forbidden. Private source rows, learned weights and inference remain unavailable public artifacts. Reproducibility of public aggregates from private result bytes is not equivalent to independently reproducing private learned inference.

## Public capability/reuse matrix

| Capability | Published status |
| --- | --- |
| Benchmarks, public metadata and CLI discovery; target transforms, inverse displacement, scientific evaluation; synthetic and reproducibility checks | `PUBLIC_EXECUTABLE` |
| Public records, immutable schema/manifest/aggregate digests and four-match summary values | `PUBLIC_VERIFIABLE` (metadata and aggregate inspection only) |
| Registry-bound forensic evidence that requires a user-supplied local verified registry | `LOCAL_EVIDENCE_VERIFIABLE` |
| Historical tracking/checkpoint bytes, private fitted weights, trained inference or historical full-fixture regeneration | `UNAVAILABLE_PUBLIC_ARTIFACT` |
| Historical protected qualification truth | `FORBIDDEN_PRIVATE_TRUTH`; never read or distributed |
| SkillCorner core tracking/events/phases or row-level derivatives | **Rights-restricted**; external-source retrieval and local research only under applicable source terms |
| Protected 20-match population | **`NOT_QUALIFIED`**, no qualified production or generalization claim |

The machine-readable five-label reproducibility taxonomy is in [reproducibility.md](reproducibility.md#public-reproducibility-boundary). SkillCorner's data rights and attribution are distinct from this repository's Apache-2.0 **original code/documentation** license. Only rights-cleared, non-reconstructive material may be distributed. A formal citation, author/affiliation metadata, DOI and tagged software release remain subject to separate author/rights and release decisions.

## Source-of-truth and evidence

- [Paper A benchmark and reproducibility matrix](paper-a-evidence.md#1-benchmark-and-task-matrix)
- [Four-match descriptive scientific results](res440/results.md), [full-precision aggregates](res440/findings.json) and [scientific tables](res440/tables.md)
- [Frozen deterministic controls](res337-deterministic-research-results.md) and [learned-fit validation summary](res338-research-final-fits.md)
- [Pinned source card](skillcorner-source-card.md), [v2 data/quality card](skillcorner-data-card-v2.md), [rights policy](data-rights.md)
- [Scientific evaluation formulas](evaluation.md), [prospective protocol v2](prospective-skillcorner-protocol-v2.md) and [reproducibility policy](reproducibility.md)
