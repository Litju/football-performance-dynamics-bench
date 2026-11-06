# Proposed amended held-out evaluation protocol

**Status: PROPOSED / UNRATIFIED.** This is a versioned, post-validation and pre-learned-evaluation amendment. It is not an original preregistration. It may proceed only after a separate owner scientific ratification and a separate exact-input execution GO.

Machine-readable amendment identity SHA-256: 577731350e77d8d57d3651d31c0c5a4b8e07e12f2bf79487e33fba4d80f33a31. The exact 18-checkpoint manifest SHA-256 is 770f1d9bbca3020237992181a56e4f5be4adaae7aab07f5f1313aa699d8693e0.

## Historical authorities and disclosure

The original v2 plan (a59fee6ee8e9fb03f4f0ccdae1933458af2bbf2375db7e6cd2bdf10962e42b62), protocol (3d7bdc46300b966a4da274579d21ac4c8219e1ef897719d6b7a308596e9f1d9f), and research-only admission (a8c82bfa09ac792d6c4ae779d4b28158c33ed3c2500f8548f3e94d48197f4fd1) remain unchanged.

Original v2 required 18 final fits plus 216 training-match LOMO fits, for 234 learned fits. It required all 234 checkpoint manifests to be frozen before its prescribed evaluation stage. That complete requirement was not fulfilled: the 18 final fits are complete; the 216-fit matrix remains preserved and deferred under the original LOMO plan. None of the 216 LOMO fits ran. The amended 18-checkpoint study cannot be described as completion of the original prospective v2 study.

The 18 final training fits completed before this amendment. The six regime/representation validation means were observed before this amendment and were used for checkpoint selection. Deterministic baselines had also already been scored on the four evaluation-role matches and their results were known before this amendment. In the published deterministic evaluation summary, persistence was 3.5219 / 6.3739 / 3.0952 m (ADE/FDE/XY-RMSE) and constant velocity was 2.2433 / 4.9257 / 2.2384 m. These prior outcomes may have influenced the analysis choices recorded here. No learned-model result on an evaluation-role match had been observed as part of this amendment.

The measured 18-fit final campaign used 55.34 Colab compute units and 11,304.44 GPU fit-wall seconds. This amendment avoids additional training because the selected final checkpoints already exist. It does not authorize paid compute units.

## Original v2 and amended study differences

| Element | Original v2 authority | Amended study treatment |
|---|---|---|
| 18 final DeepSets fits | Required | Retained; exact owner-Drive checkpoint and receipt hashes frozen in the 18-checkpoint manifest. |
| 216 training-match LOMO fits | Required as 12 folds × 6 configurations × 3 seeds | Deferred, not completed or deleted; original LOMO matrix and implementation remain preserved. |
| 234 checkpoint manifests before scoring | Required before the prescribed scoring stage | Replaced for this amended study with exactly the 18 verified final-fit checkpoints. |
| Four validation matches | Select final checkpoints by equal-match ADE | Retained; the results and selected checkpoints predate this amendment. |
| Four evaluation-role matches | Learned evaluation was downstream of all 234 original manifests | Retained as the learned held-out evaluation set. Deterministic deterministic baselines had already scored these matches. |
| Model, seeds, targets, information regimes | Frozen v2 definitions | Retained without architecture, weight, seed, or training changes. |
| Primary and secondary endpoints | Physical trajectory metrics | Retained as physical XY ADE, FDE, and XY RMSE in metres under the same truth masks. |
| C1 and C2 contrasts | Frozen four contrasts | Retained exactly; no post-hoc contrast changes. |
| Inference and spending | Existing GPU training amendments applied to training | Amended to CPU-only FP32 inference; zero optimizer steps and zero paid compute units. |
| Exploratory analysis | No post-outcome analysis | Only the horizon and quality strata listed below are planned. Any additional analysis after learned results is exploratory. |
| Scientific claim | Full original v2 study | Results are a separately amended research-only study and do not complete original prospective v2. |

## Frozen population, model matrix, and endpoints

The learned evaluator is limited to evaluation-role match IDs 1874553, 1925299, 2006229, and 2010085, from the original research-only admission. The evaluator must use the original eligibility rules, v2 window identity, ordered player panels, truth masks, physical units, and source orientation. Coordinates remain source pitch XY in metres; no scene reflection or changed source is allowed.

The target has 25 history intervals plus the origin, then 15 future observations at 0.2-second spacing, for a 3.0-second horizon. The 18 cells are one frozen per_target_context_deepsets_mlp_v1 model × three information regimes × two target representations × seeds 1729, 2718, and 31415. All checkpoint bytes remain owner-private. The committed manifest contains hashes and configuration identities only.

The endpoints are physical XY ADE (primary), FDE, and coordinate XY RMSE (secondary), all in metres. Absolute and origin-relative displacement predictions are evaluated against the same absolute physical truth. A displacement prediction is converted by adding each target player's frozen origin XY before scoring. Both representations use the same frozen per-player, per-step physical truth mask.

History-only is an ex-ante forecast setting. Future-ball and future-opponent-plus-ball use privileged realized future observations. Conditional prediction with realized future information is not equivalent to deployable future forecasting.

## Aggregation and contrasts

For each seed and match, score each eligible window with the existing masked physical trajectory metric core. Average the scoreable directed scene metrics equally within a window, then average windows equally within that match, matching the deterministic baseline contract. Preserve the per-match denominators and mask identity.

For each regime/representation, average the three seed values within each match first. Then average the four match means equally. Preserve all 72 seed-by-match records. Do not pool overlapping windows as independent observations.

The contrasts are:

- C1 for each representation: history_only ADE minus future_ball ADE.
- C2 for each representation: future_ball ADE minus future_opponent_plus_ball ADE.

Compute matched seed averages within each evaluation match before each match-level contrast. Report all four match-level values and their equal-match mean. Positive values mean lower ADE with the added realized context. No significance tests or confidence intervals are planned.

Planned descriptive strata are early (0.2–1.0 s), middle (1.2–2.0 s), and late (2.2–3.0 s) horizons, plus detected-only and provider-extrapolated target-quality groups using the source observation flag. Scenes with unavailable quality flags are reported as unclassified missingness and are not silently assigned to either group. These strata do not change eligibility, masks, or the primary score. The leave-one-out diagnostic is named **evaluation-match deletion sensitivity**; it is not training LOMO.

## Deterministic baseline evidence

The published deterministic report records match-scoped persistence and constant-velocity ADE/FDE/XY-RMSE values for the same four evaluation matches, with the same 15-step physical truth, scoreable-window population, equal scene-within-window and equal window-within-match weighting. Its public report records 51,713 windows and 103,426 directed scenes. The aggregate-safe values are mirrored in the versioned baseline reference file and are bound to the published report SHA-256.

The exact original private deterministic-baseline per-cell result manifest bytes were not found in the connected owner-only Drive or Linear evidence during this preparation. The published match summary is enough to prepare paired descriptive comparisons under the documented metric contract, but it is not a substitute for the immutable private cell manifests. Final scientific ratification requires the owner to accept this bounded baseline evidence or supply those manifests; the evaluator never reruns or silently recomputes the historical baselines.

## Inference plan and hard authorization gate

The subsequent one-pass evaluation uses Python 3.12.8, NumPy 2.2.4, PyTorch 2.6.0+cpu, CPU-only FP32 inference, one CPU thread, and deterministic algorithms. Same-runtime synthetic prediction replay uses rtol=0, atol=0 and must be bitwise equal; truth origin reconstruction uses absolute tolerance 1e-12. No CPU/GPU bitwise equivalence or cross-device tolerance is claimed. The model and metric logic are qualified on synthetic fixtures from the existing GPU qualification input generator and frozen scoring semantics.

One authorized run has a 14,400 CPU-second ceiling, 21,600 wall-second ceiling, 8 GiB RSS ceiling, 8 GiB private evaluation-input ceiling, zero paid compute units, and a USD $0 paid-compute ceiling. It loads no optimizer state and performs no optimizer step. If it fails or is interrupted, its output directory remains sealed and the run cannot be repeated without a new owner GO.

The executable requires an owner-only authorization JSON bound to the exact amendment SHA-256, checkpoint-manifest SHA-256, original research-admission SHA-256, and scorer-code SHA-256. The operator must also pass the exact phrase RES594-OWNER-GO:<amendment-sha256>:<checkpoint-manifest-sha256>:a8c82bfa09ac792d6c4ae779d4b28158c33ed3c2500f8548f3e94d48197f4fd1:<scorer-code-sha256>. Authorization is checked before the source or evaluation files are opened. The authorized process first verifies the pinned source and independent research population, then streams the four evaluation matches through the frozen window producer and scorer. The generated input identity is recorded in the result receipts. The authorization is limited to the separate research-only path and explicitly records protected population status NOT_QUALIFIED. Its exact fields and fixed resource values are defined in the packaged authorization JSON Schema.

The one-run command is:

    uv run --group research-training fpdbench-res594 score --owner-authorization OWNER_AUTH.json --owner-go RES594-OWNER-GO:AMENDMENT_SHA:CHECKPOINT_MANIFEST_SHA:RESEARCH_ADMISSION_SHA:SCORER_CODE_SHA --checkpoint-directory PRIVATE_CHECKPOINTS_BY_SHA --receipt-directory PRIVATE_RECEIPTS_BY_SHA --research-root VERIFIED_FULL_RESEARCH_ROOT --source-root PINNED_SOURCE_ROOT --output-directory NEW_PRIVATE_CAMPAIGN_DIR

Checkpoint filenames are their frozen lowercase SHA-256 values followed by .pt; receipt filenames are their frozen receipt SHA-256 values followed by .json. Each file remains owner-private. The research root must be the full verified original 20-match research-only population so its independent producer/verifier and source hashes can be checked; only the four evaluation-role windows enter the learned scorer.

From the canonical checkout, run the packaged command through the pinned CPU research environment with the owner-only checkpoint and receipt directories, the verified 20-match research root, the pinned source root, the owner authorization JSON, and the exact GO phrase. The executable creates a single private one-shot campaign directory, verifies the admission and producer streams, and scores each eligible evaluation window as it is streamed. The research root may be reused from the prior authorized deterministic-baseline run. If it must be prepared, stage it only after the same owner GO. No evaluation-label bundle is required before the GO.

## Reporting and rights boundary

The report generator emits a six-cell ADE/FDE/RMSE comparison, four-match records, seed variation, match heterogeneity, paired deterministic comparisons, C1/C2 contrasts, evaluation-match deletion sensitivity, provenance, original-v2 deviations, limitations, and negative findings. Figures are generated only from validated result receipts. Validation outcomes and held-out learned outcomes are labeled separately.

Only non-reconstructive aggregates and hashes may be published. Raw positions, target masks, source rows, reconstructive trajectories, checkpoints, and optimizer state remain owner-private. The protected population remains NOT_QUALIFIED; this scorer does not import or invoke the protected scoring gate.
