# Prospective SkillCorner experiment plan

**Plan:** `skillcorner.prospective_conditional_motion.execution` v1.1.0

**Plan SHA-256:** `0446649e1ad049880cf6f8a76b4f3e03421d8bd7a1f7a2c562b5770461527775`

**Scientific protocol:** `skillcorner.prospective_conditional_motion` v1.1.0
**Protocol SHA-256:** `865601662f4462178eaf7e1049075668176a9bd35f3bf4b1b6b8aa370de1d26c`

Machine authority: [`empirical_experiment_plan_v1.json`](../src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction/empirical_experiment_plan_v1.json). The scientific protocol file and digest are unchanged.

## Frozen matrix

Every information regime is crossed with both protocol target representations and all three model classes, for exactly 18 model/condition cells:

| Model class | Definition | Training |
| --- | --- | --- |
| `origin_persistence_v1` | Repeat origin XY; zero displacement | No |
| `constant_velocity_1s_v1` | Per-coordinate least-squares trend over the six history samples from -1.0 to 0.0 seconds; fallback to persistence when fewer than two finite distinct-time samples exist | No |
| `per_target_context_deepsets_mlp_v1` | Shared mask-aware DeepSets track encoders and a shared per-origin-player MLP prediction head | Yes; single primary class |

The three regimes and two representations retain the exact meanings in the frozen scientific protocol. Both baselines ignore added future context, so their predictions are identical across regimes. Their six regime/target cells remain in the matrix as controls. The learned class has six factorial cells and is the only primary class.

The learned architecture is fully fixed in the JSON authority. In brief, a shared `78→32→16` history track encoder mean-pools target and opponent players separately, a `45→32→16` encoder pools all opponent tracks over the future horizon including substitutes, and the prediction head is `input→128→128→30` with ReLU and dropout 0.1. Inputs use XY in metres, a presence bit for each XY pair, relative time offsets and home/away side. Missing coordinates are zero-filled with their mask. Player IDs align and order tracks only; they are not model features. Future target information and eligibility/quality outputs stay forbidden.

Training uses PyTorch 2.6.0 CPU, Python 3.12.8 and NumPy 2.2.4, one CPU thread, deterministic algorithms, and seeds 1729, 2718 and 31415. The model uses AdamW (learning rate 0.001, weight decay 0.0001), 128 directed scenes per batch, 5,000 maximum optimizer steps, and masked physical ADE loss. Batches sample a fit-role match, eligible window and scoreable directed scene uniformly at each level, with replacement. The remaining architecture, feature dimensions, optimizer values and initialization are in the machine authority.

## Fits, selection and compute

The 18 final fits are the six learned cells crossed with the three shared seeds. The protocol supplies 12 LOMO folds; fitting those same six cells and seeds gives 216 LOMO fits. The complete campaign has exactly 234 learned fits. LOMO is descriptive, uses the protocol training matches, selects checkpoints only on the four validation matches, and never selects or tunes the model.

Validate every 100 optimizer steps, beginning at step 100. Select the checkpoint with the minimum equal mean of the four validation-match ADE values; exact ties keep the earliest step. Stop after ten consecutive checks without a strict improvement, 5,000 steps, or the fit compute limit. There is no hyperparameter search. The evaluation matches are used once after every checkpoint is frozen.

Each fit gets at most 1 CPU-core-hour initially and one restart-from-scratch infrastructure retry of at most 0.25 CPU-core-hour, with identical seed and configuration. Other model failures, invalid populations, missing validation scores, non-finite values, and any evaluation-stage failure are not retried. The 234 fits therefore have a 292.5 CPU-core-hour maximum. Preparation and scoring have a 19.5 CPU-core-hour allocation; the full cap is 312 CPU-core-hours or 336 wall-clock hours. Hitting any ceiling stops the campaign; no budget extension is allowed.

Run order is: validate protocol/plan/runtime/population authorities; run deterministic baselines on validation; fit final learned cells by target, regime, seed; fit LOMO cells by protocol fold, target, regime, seed; freeze and verify all run manifests/checkpoints; score LOMO and evaluation outputs once; then write per-match results and descriptive summaries. A missing cell, seed, fold, match or population identity makes the campaign incomplete. No partial four-match contrast summary is reported.

## Result and contrast records

Each run manifest uses `fpdbench.prospective-experiment-result` v1.1.0, defined by [`prospective_experiment_result_v1.schema.json`](../src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction/prospective_experiment_result_v1.schema.json). Its required identity includes plan and protocol hashes, cell/model/target/regime, fit role and LOMO fold, seed, exact train/validation match IDs, population-authority digest, configuration/environment/checkpoint digests, selected step, stopping reason, status, output-artifact digests and match-scoped ADE/FDE/XY-RMSE values in metres. Aggregate manifests also bind their exact seed and match sets. The field list and allowed status/metric IDs are pinned in the experiment plan authority. `load_prospective_result(path, population)` and `validate_prospective_result_document(document, population)` enforce the cross-field contract before a result can be consumed. JSON Schema alone cannot verify canonical digests or population binding. Run IDs use `<cell_id>|<fit_role>|<fold_id-or-final>|<seed-or-deterministic>`; training memberships, held-out identity and seed must match that run exactly. Completed learned runs require a checkpoint and a selected validation step divisible by 100. Failed/incomplete runs publish no checkpoint, selected step or metrics; status-specific stopping reasons are frozen in the plan.

Completed final runs require all three metrics on all four validation and all four evaluation matches. Completed LOMO runs require all four validation matches and their one held-out training match. Deterministic baseline records have empty training membership and include validation, evaluation and all twelve held-out training controls. Duplicated, partial, non-finite, negative or out-of-scope metrics fail validation. Run outputs and predictions remain in restricted authorized storage.

Only the primary learned class contributes the four preregistered ADE contrasts:

1. `C1_ABSOLUTE_XY_FUTURE_BALL`: history-only ADE minus future-ball ADE.
2. `C1_DISPLACEMENT_FUTURE_BALL`: history-only ADE minus future-ball ADE.
3. `C2_ABSOLUTE_XY_FUTURE_OPPONENT`: future-ball ADE minus future-opponent-plus-ball ADE.
4. `C2_DISPLACEMENT_FUTURE_OPPONENT`: future-ball ADE minus future-opponent-plus-ball ADE.

Average the three seeds within each evaluation match first. Report all four match-level differences and their equal-match mean only when every required match pair is scoreable. Positive values mean lower ADE with added realized context. These remain descriptive: no p-values, confidence intervals, multiplicity corrections or significance claims. Other metrics and model-class comparisons are exploratory/descriptive.

## Population completeness gate and separate blocker

This plan owns the versioned gate and schema in [`evaluation_population_authority_v1.schema.json`](../src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction/evaluation_population_authority_v1.schema.json). The runtime manifest must bind all 20 protocol matches, source/release/measurement/eligibility hashes, the scientific protocol hash, this plan hash, exhaustive candidate-origin digest, exact retained eligible windows, each origin identity, home/away origin player IDs, and separate per-scene `absolute_xy_truth_sha256` and `displacement_truth_sha256` identities with one common mask digest. Each window also binds the eligibility-result digest. Match, window, scene and player ordering is canonical.

The scorer now requires that restricted authority. Before metric computation it rejects missing or reordered matches/windows/scenes/players, invalid identities, truth or mask drift, and incomplete/non-finite model predictions. Truth digests are explicitly tagged by representation and version. Both truth and prediction panels must use the cell's representation in metres: physical XY for `absolute_xy`, per-player origin-relative displacement for `origin_relative_displacement`. Each representation has its own sealed digest under the same window/player membership and mask. Translating both panels by the same observed origin preserves physical error distances; the scorer uses the selected sealed panel without an implicit frame conversion.

`evaluate_prospective_trajectories` requires `cell_id` and an output `target_representation`. The shared gate runs before metrics for `role="validation"` (all four validation matches), `role="lomo", lomo_fold_id="fold-XX"` (exactly that fold's held-out training match), or the default evaluation role (all four evaluation matches). All three paths enforce the same windows, origins, scenes, players, truth, mask and finite-prediction checks. Unknown cells/folds and incompatible roles fail closed. Without the external authority the scorer cannot run.

The repository does not contain SkillCorner payload rows, derived window identities, truth hashes or the exhaustive candidate-origin enumeration, so it does not contain a population-manifest instance. [The protected population qualification blocker](https://linear.app/alignerr-cmj/issue/fe554f95-1ae8-406c-9dd7-a73d91711e51), owned by Julio Rodriguez, remains the unresolved blocker for materializing and independently qualifying the restricted artifact from authorized source data. It must use the revised population schema v1.1.0 and current plan digest, independently verify that both representation-specific truth panels derive from identical physical truth and observed per-player origin XY (including nonzero origins), and verify their common masks and membership. The v1.0.0 population artifact and result records are not accepted by the revised APIs; filenames retain the v1 schema-family name. The validator ensures a supplied manifest matches the pinned identities and scorer payloads; it cannot prove an external producer enumerated every source candidate. That blocker must verify exhaustive enumeration before any training, validation selection, LOMO scoring or evaluation scoring.

No training, empirical scoring, private qualification truth inspection or row-level redistribution was performed to freeze this plan.
