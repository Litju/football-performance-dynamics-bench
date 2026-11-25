# Public benchmark cards — football motion

**Status:** public research-software documentation for the prospective v2.0.0 task contracts and their separately authorized, descriptive four-match study. This is **not** a qualified protected benchmark release or a claim that every research family is executable.

## Scope and task identity

FPD Bench distinguishes a scientific **research family**, a typed **benchmark/task identity**, a data/measurement version, a population and split, an evaluator, a frozen experiment, and an empirical result. A change in target reference frame or in the information available at prediction time can change the scientific question, even if metrics share units. The [public benchmark registry](../src/fpdbench/benchmarks/registry.py), [benchmark transition record](benchmark-transitions.md) and [Paper A task matrix](paper-a-evidence.md#1-benchmark-and-task-matrix) are authoritative for these distinctions.

The active prospective study has **two versioned target tasks**, each evaluated in **three information regimes** under the pinned SkillCorner 20-match source and successor nullable-ball measurement/eligibility policies.

| Card | Prospective absolute position | Prospective origin-relative displacement |
| --- | --- | --- |
| Scientific family | `conditional_multi_agent_motion_prediction` | Same |
| Protocol | `skillcorner.prospective_conditional_motion` v2.0.0 | Same |
| Target | Target-team future pitch-centred **absolute XY** in metres | Each target-player future **p − o** displacement relative to the observed forecast-origin position `o`, in metres |
| Temporal grid | 26 history samples including origin at 5 Hz (5 s), followed by 15 scored future steps at 5 Hz (3 s) | Same |
| Population | Frozen source-match roles: 12 training, 4 validation, 4 evaluation; origin-player panel and missingness follow v2 eligibility | Exact same origin population, truth, eligibility, windows and target-valid masks |
| Authorized regimes | `history_only`; `future_ball`; `future_opponent_plus_ball` | Same |
| Primary endpoint | Physical ADE in metres, aggregated at match level | Physical ADE after origin displacement is reconstructed to absolute XY |
| Secondary endpoints | FDE at 3 s; physical scalar-coordinate XY RMSE, metres | Same physical XY endpoints after reconstruction |
| Evaluation status | Completed **four-match descriptive research-only** study; protected population `NOT_QUALIFIED` | Same |
| Execution claim | Public protocol/transform/evaluator verification is available; private fitted checkpoints and complete empirical source are **not** published | Same |

For the complete immutable task authorities, see [protocol v2](prospective-skillcorner-protocol-v2.md), [measurement v2](skillcorner-data-state-v2.md), [eligibility v2](skillcorner-window-eligibility-v2.md), [original frozen plan](prospective-experiment-plan-v2.md), and the [post-failure descriptive scientific contract](../src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction/res635_post_failure_descriptive_protocol_v1.json). The descriptive study **does not** replace the original v2 plan.

## Information boundary: what the model may see

| Regime | Available at the forecast origin? | Learned-model inputs | Correct interpretation |
| --- | --- | --- | --- |
| `history_only` | Yes | Observed target team, opponents and ball histories with input masks | **Ex-ante forecasting** from available history |
| `future_ball` | No, not as a realized trajectory | The same history plus **realized** future ball positions and masks | Conditional trajectory analysis; **not** an ex-ante deployment forecast |
| `future_opponent_plus_ball` | No, not as realized trajectories | History plus **realized** future opponents and ball positions and masks | Conditional multi-agent analysis; **not** an ex-ante deployment forecast |

The target team's future positions, target/truth masks, eligibility decisions, phase labels, provider detection attribution, quality/selection diagnostics, match clock and identity encodings are **not** authorized learned inputs. This information boundary is enforced in the [protocol](prospective-skillcorner-protocol-v2.md) and illustrated in [Paper A](paper-a-evidence.md#3-information-boundary). Comparing conditional regimes with history-only shows apparent predictability given information that is unavailable at deployment, not causal response or improvement in an operational forecasting system.

## Measurement and scoring

- Native SkillCorner tracking is 10 Hz and the canonical study grid is 5 Hz by deterministic selection, **without interpolation or imputation**. The v2 nullable-ball policy preserves absent versus present-but-coordinate-null ball states and true/false/unknown provider detection flags. It never converts undocumented provider flags into invented observations.
- A model's predicted target displacement must be inverted to physical absolute XY using the target player's actual **observed origin** before physical scoring. The same origin panel and future truth/mask apply across all six configurations.
- **ADE** = mean Euclidean distance over scored players and forecast steps; **FDE** uses the final step at +3 s; **XY RMSE** takes the square root of mean squared residuals across *scalar x and y coordinates*, not Euclidean RMSE. Units are metres for all three.
- The frozen hierarchy averages within directed scene/window/match, averages the three selected seeds **within each match**, then equally averages the four independent evaluation matches. Do not weight the match mean by the number of overlapping windows.
- Membership, truth and mask eligibility are not model features. Excluded origins/players are not characterized by valid scored-target counts.

For exact formulas, zero-variance/calibration distinctions, mask behavior and denominators, refer to [evaluation.md](evaluation.md), [Paper A evaluation design](paper-a-evidence.md#4-evaluation-design), and [scientific results](res440/results.md).

## The fixed completed demonstration

The public [results](res440/results.md) and [machine-readable aggregate findings](res440/findings.json) document **18 frozen DeepSets checkpoints** (one class × three regimes × two encodings × three seeds) scored as **72 match/seed records** on **four** evaluation matches. Those matches contributed **51,713 overlapping windows** and 103,426 directed scenes, **not** 51,713 independent statistical observations.

| Information regime | Absolute XY ADE (m) | Displacement ADE (m) |
| --- | ---: | ---: |
| History only | 2.1216 | 1.6680 |
| History + realized future ball | 1.8330 | 1.4298 |
| History + realized future ball and opponents | 1.7182 | 1.2958 |

The comparable history-only one-second constant-velocity reference has ADE **2.2433 m**; history-only displacement DeepSets had **25.6% lower** descriptive ADE on the four fixed matches. In every regime, displacement had a lower physical ADE than absolute XY for the frozen fitted models. The separate fitted checkpoint sets and validation selection prevent causal attribution of the error difference to a representation alone.

These are **descriptive n=4 observations**, with no inferential confidence interval, statistical-significance claim, broad-match generalization, causal interpretation or operational deployment evidence. The original **234-fit** prospective plan was not completed; its **216 training LOMO fits remain unexecuted**. The protected 20-match population remains `NOT_QUALIFIED`. The completed study followed a separately authorized post-failure descriptive route; no new training was performed during scoring. See [results interpretation and limitations](res440/results.md#interpretation-and-limitations).

## Historical tasks are not prospective v2 identities

| Historical/recovered object | What can be inspected in public code | What is **not** established |
| --- | --- | --- |
| Conditional absolute-position prediction | Recovered fixed-array contract, transforms, population-SRE evaluator, absolute calibration lock and scientific metadata | Historical learned-checkpoint inference or equivalence to the prospective SkillCorner cohort |
| Conditional origin-relative displacement | Recovered fixed-array contract, transformation/inverse, raw population SRE and corrected lineage metadata | Calibrated displacement reward or historical model/result parity |
| Whole-session performance state | Archival partial evidence, non-executable object | Recovered valid whole-session benchmark |
| Signed tangential acceleration | Diagnostic RMSE evaluator for an invalidated formulation | A valid physical task or accepted benchmark |
| Multimodal sensor-state reconstruction | Scoped negative synthetic pilot | Selected target family or qualified executable benchmark |
| Future-response forecasting | Research-family registry intent | A recovered benchmark, assigned scorer, target, horizon, or model |

Historical fixed-array conditional motion and the prospective variable-player-panel v2 protocol are **separate** research objects; a common metric name does not make their populations interchangeable. Refer to [the historical transition record](benchmark-transitions.md), [Paper A evidence](paper-a-evidence.md#1-benchmark-and-task-matrix), and the [public reproducibility boundary](reproducibility.md#public-reproducibility-boundary).

## Reuse and citation

The repository makes code, schemas, public scientific aggregates and restricted-artifact *metadata* available for scrutiny. It does not distribute the SkillCorner tracking rows, row-level transformations, private predictions/receipts, held-out truth, or model weights. SkillCorner is the upstream data provider in collaboration with PySport; the [rights policy](data-rights.md) governs reuse separately from the repository's Apache-2.0 software license. No DOI, author list or paper-publication status is asserted by this card.
