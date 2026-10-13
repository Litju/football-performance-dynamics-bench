# Prospective SkillCorner benchmark protocol

**Protocol:** `skillcorner.prospective_conditional_motion` v1.1.0

**Protocol SHA-256:** `865601662f4462178eaf7e1049075668176a9bd35f3bf4b1b6b8aa370de1d26c`

**Machine authority:** [`prospective_skillcorner_protocol_v1.json`](../src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction/prospective_skillcorner_protocol_v1.json)

This is the hard pre-training lock for the prospective 20-match SkillCorner study. It creates new prospective identities for absolute pitch XY and origin-relative displacement. It does not version or repair the historical reconstructed benchmarks. Historical J03 match roles, fixtures, private qualification truth, results, and scientific locks remain separate; `J03WMX` is not prospective evaluation data.

The lock binds the pinned source population hash `e9054b7ddc2dfeff4dd8425ea61a23ed0b326076a08899e47502484228fdbdf4`, source release hash `e92c417b7640b27399451134ee3fce4b1961b0c0dfc2e01175a8f3c906a9ae07`, measurement state hash `4c29471c7fccc037dcfafd30222991e06d150e0887c0b667918bfa374262c6c3`, and eligibility policy hash `f0e1186f765cc7ce19c95152d8d6eacc66382f7e7f5a9ad1aa11c88c8a12f70b`. Validation compares these values with the checked-in authorities and verifies that the split covers exactly their 20 match IDs. No row-level payload or derived observation is included.

## Task and temporal support

The research question is whether conditioning multi-agent player-position prediction on realized future ball and opponent trajectories changes three-second prediction error, under two target representations.

The 5 Hz grid has 0.2-second intervals. A five-second history is **25 intervals and 26 samples**, with the forecast-origin sample shared as the last history sample. The three-second horizon is **15 future intervals and 15 samples** after the origin. Each complete window therefore has 41 support samples: 26 history/origin plus 15 future. The origin is sample index 25 in the support. Origins advance by one canonical sample, within a single period. Every origin passing the pinned eligibility policy is retained. No window counts or quality statistics are asserted because payload rows are unavailable here.

This interval-based definition follows Linear issue 437's `history + future + origin` support rule. The historical reconstruction's fixed-11-player array with 25 history samples is not reused for this prospective task.

## Information available to each model

Every regime receives the same 26-sample history: target-team XY, opponent-team XY, ball XY, their source-presence masks, relative time offsets, and home/away side. The three regimes then receive:

- **History only:** no future observations.
- **Future ball:** realized ball XY and its source-presence mask at all 15 future samples.
- **Future opponent plus ball:** the future-ball inputs plus realized opponent-team XY and its source-presence masks at all 15 future samples, including substitute players appearing during the horizon.

Player IDs preserve within-match ordering and continuity but are not numeric model features or joined across matches. Future context is explicitly ex-post oracle information; this is conditional prediction, not an ex-ante causal forecast.

Future target-team positions, target masks, eligibility outputs, phase/event/possession labels, quality-audit fields, absolute match clock, file identity, row order, and cross-match player identities are forbidden model inputs. History and future-context masks indicate only whether the corresponding raw XY pair is available; source `is_detected` flags and computed quality strata are not features. Eligibility, phases, target truth, and quality audits may determine evaluation membership or scoring masks only.

## Targets, identity, and missing positions

Each physical window produces home-target and away-target directed scenes. A scene's target set is the player records with finite XY in that side's forecast-origin sample, ordered by ascending provider player ID. Cardinality is variable and fixed per scene for its 15 outputs; there is no eleven-player cap or cardinality guarantee. The seven-player Linear issue 437 eligibility floor is not treated as a guarantee of eleven targets or of a complete target trajectory.

Absolute targets are provider pitch-centered XY in metres, without pitch normalization, rotation, or attack-direction transformation. Displacement targets are each same player's future XY minus its observed origin XY, also in metres; adding the origin XY reconstructs physical position.

The target panel keeps origin IDs for the full horizon and never stitches identities or adds later entrants. A finite extrapolated source position (`is_detected=false`) remains a target value and retains its quality stratum. An absent record or a position with a missing coordinate becomes one null XY pair in the truth array. There is no interpolation, carry-forward, replacement target, or model prediction mask. Each model must emit a finite XY prediction for every origin target at every future sample. Truth masks are used only by the evaluator.

## Match assignment and LOMO

The 20 pinned match IDs are ranked by ascending SHA-256 of UTF-8 `FPDBench prospective/v1/match/<decimal match_id>`. The first 12 form training, the next 4 validation, and the last 4 evaluation; IDs are then sorted within each role. This yields deterministic roles without using dates, team outcomes, eligibility counts, or model results.

| Role | Match IDs |
| --- | --- |
| Training (12) | 1886347, 1899585, 1927964, 1959846, 1986691, 1996436, 2006363, 2007448, 2007721, 2011166, 2013725, 2016236 |
| Validation (4) | 1953632, 1996435, 2015213, 2017461 |
| Evaluation (4) | 1874553, 1925299, 2006229, 2010085 |

The 12 LOMO folds each hold out one training-role match and train on the other 11. Validation and evaluation matches appear in no LOMO training set. All windows and both directed scenes from a match stay together. LOMO is descriptive and cannot select or tune a model. Its overlapping training sets do not support iid match-level confidence intervals or hypothesis tests. The evaluation role is used once for final scoring and never for model selection.

Digests: role assignment `923dc2721a05620716f23c3b4cb1814e73485f80052f00c5334ccce666b99d94`; LOMO held-out assignment `8eba816cd1521aea8156c0da21b10321a29476f41ffe4b089382d0b9de4d9240`; combined split `63c517001ce505525b48cf6a49ab48ed336ddf32c2d6ea24cd2ba950feff3a32`.

## Metrics and uncertainty

The primary metric is physical XY **ADE in metres**. Secondary metrics are physical XY **FDE in metres** and **XY-RMSE in metres**. The mask-aware metric kernel treats a null truth XY pair as the sole missing-target mask; predictions must be finite. Coordinates are already in metres, so both XY scale factors are 1.0. No calibrated reward or population SRE is produced for this protocol.

A directed scene must have at least one valid target at future sample 15 to be scoreable; the same scene population is used for all metrics. A scene with no final target has null metrics and reason `NO_FINAL_TARGET`, and is excluded from every metric. A physical window with no scoreable scene has a null window score and is excluded from that match's mean. A match with no scoreable window has a null match score; keep it in the four-match population and do not report an across-match summary if any match lacks a score. Invalid or missing model predictions fail that model cell, including predictions at null-truth positions.

Aggregation is fixed: compute a metric over valid target/time labels within each directed scene; average scoreable home/away scenes equally within a physical window; average eligible windows with at least one scoreable scene equally within each match; average the four evaluation-match scores equally only when all four have a score. Multiple seeds are averaged within each match first. Frames, windows, scenes, and seeds are not independent generalization units.

The four preregistered directional ADE contrasts are descriptive: report each evaluation match's control ADE minus context ADE and their equal-match mean. Positive values mean lower ADE with added realized context. Do not report p-values, confidence intervals, multiplicity corrections, or significance claims. Do not drop a match to repair a missing comparison. LOMO inference remains unavailable because its training folds overlap.

Robustness results use only the eight composable strata defined in Linear issue 437: player detection exposure, ball detection exposure, player completeness, ball completeness, temporal continuity, identity-transition exposure, source-quality uncertainty, and play context. Report stratum and match counts descriptively, keep the policy's thresholds, and do not add post hoc bins or confirmatory tests.

## Preregistered descriptive directional ADE contrasts

All four contrasts use ADE and preregister the expected direction of lower error with added realized context. They apply to the single primary model class that Linear issue 339 must designate before training:

1. Future ball versus history only for absolute XY.
2. Future ball versus history only for origin-relative displacement.
3. Future opponent plus ball versus future ball for absolute XY.
4. Future opponent plus ball versus future ball for origin-relative displacement.

FDE and XY-RMSE contrasts, all other model-class comparisons, interactions, horizon slices, and stratum comparisons are exploratory/descriptive. Linear issue 439 owns any later team-coherence or team-plausibility metric decision; those metrics are outside this lock.

## Selection and pre-training gate

Final fits use training matches only. Validation matches may select checkpoints and control early stopping using the equal mean of the four validation-match ADE values; minimize it and break checkpoint ties by choosing the earliest step. Any other validation-tuned parameter must be explicitly declared by Linear issue 339. Evaluation matches cannot be used for tuning, early stopping, retries, or threshold changes.

Stochastic cells use at least three distinct seeds, shared across comparable cells; exact seed IDs/count and seed-dependent run cells are owned by Linear issue 339. Report seed sensitivity separately, not as match uncertainty. Linear issue 339 must also freeze the exact experiment matrix, primary model class, compute ceilings, early-stopping patience/maximum steps, retry count, run order, and result manifest before training. No extra cells, seeds, compute, or retries may be added in response to outcomes.

**Training remains blocked** until Linear issue 336 receives independent scientific review and is complete, and Linear issue 339 freezes every delegated execution decision. This protocol alone does not authorize training. No learned-model training, empirical campaign, private truth inspection, or model-result-driven protocol change was performed to create this lock.

The machine authority is validated by `fpdbench validate` and its canonical digest covers the complete result-bearing scientific state. Changes before training require an explicit versioned amendment and new review; changes after observing a model outcome are forbidden.
