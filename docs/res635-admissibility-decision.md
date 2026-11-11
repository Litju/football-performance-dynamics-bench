# RES635 — Scientific admissibility of a post-failure held-out study

**Issue:** RES635 (Linear Research; the issue identifier is the administrative authority)
**Date:** 2026-11-11
**Status:** Proposed for independent scientific review. **No execution GO is granted.**
**Decision token:** `DESIGN_GO_FOR_OWNER_REVIEW` (ticket token) / `RES635_READY_FOR_INDEPENDENT_SCIENTIFIC_REVIEW` (review token)
**Machine-readable protocol:** `res635_post_failure_descriptive_protocol_v1.json`, file SHA-256 `525d2954bf3aed0215b5960262e0fce844fdd164bfcdd0e548a16a90315a72a0`

## Bottom line

The preferred route for a genuinely new held-out evaluation is a rights-cleared, compatible, prospectively locked evaluation-match cohort. **No such cohort is currently verified.** The only source in this repository is the 20-match SkillCorner Open Data cohort; its four evaluation-role matches are the same four already used by the deterministic baselines. A different provider would not be a drop-in replacement for the frozen 18-model matrix without a new measurement, admission and training contract. Option 1 is therefore **not qualified now**.

The conditional route — a separately ratified, post-failure **descriptive** study on the original four evaluation matches — is scientifically admissible **only in a narrow form**:

* the RES594 measurement produced no committed, recovered or observed learned result bundle, so the new attempt is not conditioned on a learned outcome;
* no learned result bundle was committed, recovered or observed for the four matches;
* the analysis plan, endpoints, model matrix, aggregation and C1/C2 contrasts are inherited unchanged from the pre-failure authority;
* the study is a new, separately versioned protocol and a new execution identity, not a retry or reuse of the consumed RES594 scope;
* the execution architecture is independently qualified on synthetic data and uses sealed per-match receipts, durable supervision and a fail-closed interruption policy;
* the claims are descriptive, bounded to the four fixed matches and the 18 fixed checkpoints, with no significance, confidence intervals, population generalization, deployment or ex-ante future-context claims.

Under those conditions, the recommended path is **Option 2, descriptive only**. It is not confirmatory, not a completion of original v2, not a substitute for a new cohort, and not evidence of protected-population qualification. If the owner's publication goal requires confirmatory or population-level inference, the correct decision is **Option 3 (no new evaluation)** until Option 1 becomes feasible.

## Evidence reviewed

| Evidence | Identity / location | Use in this decision |
|---|---|---|
| Original v2 plan | SHA-256 `a59fee6ee8e9fb03f4f0ccdae1933458af2bbf2375db7e6cd2bdf10962e42b62` | Original 234-fit prospective authority; preserved, not completed. |
| Original v2 protocol | SHA-256 `3d7bdc46300b966a4da274579d21ac4c8219e1ef897719d6b7a308596e9f1d9f` | Frozen endpoints, regimes, representations, seeds and aggregation. |
| Research admission | SHA-256 `a8c82bfa09ac792d6c4ae779d4b28158c33ed3c2500f8548f3e94d48197f4fd1` | Local public-data research authority; protected population remains separate and `NOT_QUALIFIED`. |
| RES593 amendment | SHA-256 `e54f067a07479b81c4625428e49e5a5b907c49987d4c5bd7982138e270e66913` at frozen main `7acc2c4e1174935efbe561e072f68c349af5e05f` | Disclosed post-validation/pre-learned-evaluation amendment; 18 final checkpoints; 216 LOMO fits deferred. |
| 18-checkpoint manifest | SHA-256 `770f1d9bbca3020237992181a56e4f5be4adaae7aab07f5f1313aa699d8693e0` | Exact model matrix and frozen checkpoint identities. |
| RES337 deterministic results | Document SHA-256 `c98d8d29254c674e1011bb4b05912c5d12921c550a133eb8cdecc328c9263a68`; implementation `f14537acc17f4381d0c95907f1f1a1654152410a`; execution identity `05f6e22566e6781d7465bce00ae5e32fb7c5f7d163ea9efbfed1ad4640c9fb1e` | Deterministic evaluation baselines already observed on the four matches. |
| Baseline reference | SHA-256 `21b19a2370d5b4a45652a6ce132cb3e78a4abe2027a096a71f383b1191ea9b36`; private index `8962fd40437c4aca50b86c8f918b653c35e2aa4277010fe10cbd19ffe8d32d4e` | Physical ADE/FDE/XY RMSE, masks, denominators and rounding bound. |
| RES594 campaign | Canceled; one-shot scope `d359751e969767f30ed6e90c65b13d0eec49f11c9e33e1d2319b19530d28f2e0`; `CONSUMED_IRREVERSIBLY`; `retry_allowed=false`; authorization record `bad96973cf6f0759386544d24bc17de3368a578546e07826769bc9f727361868` | Entered the scoring phase; no learned result bundle committed, recovered or observed; old scope permanently closed. |
| RES614 forensics | Incident evidence `ce0c280fd6e95f8cf12b46d26df675b962c13d6f5b068836e6a280d22f869b17`; report `f7deab64c6cc0010f601fe6c5034ce33781bd58c0a7d22c578b9157521dd9208`; architecture proposal `4b3b761860ca4e118d032e341a03cf944f2d4ed5e92f597e32fed117cef272e7`; governance `844e3f64f34173f169efd0f70908aa04c24c83b87b03ff02359e7070734b0b34` | `SIGTERM_CAUSE_UNDETERMINED`; synthetic-only supervision and receipt qualification; not a real-data scorer qualification. |
| RES614 synthetic performance | Report `1e63f40c02f88fac398bb9ab13dde397e463c0936267b4f71bba9f00c88c8ea1`; benchmark `42d23c51fae6779960f3ba6920167073e9e5f3eb1273e99d72903e6f32e997ae` | Conditional engineering estimate, not a scientific result or a feasibility proof. |
| R5 / Paper B requirements | RES310, RES440, RES312, RES347 | Claim matrix must distinguish original predeclared, amendment-pre-evaluation and post-result exploratory claims; no peeking at learned evaluation metrics. |

The review used public, hash-only and aggregate evidence. It did not open the retained RES594 private snapshot, score any evaluation match, load private learned truth, run inference, train models, run LOMO or consume any authorization.

## Historical facts that cannot change

1. RES593 was ratified at frozen main `7acc2c4e1174935efbe561e072f68c349af5e05f` as a disclosed post-validation, research-only amendment. It is **Done**. It is not an original preregistration.
2. Eighteen final checkpoints were trained; the 216 LOMO fits remain **deferred and unexecuted**. The original v2 234-fit requirement is **not complete**.
3. RES594 started after a distinct owner GO on 2026-11-07, consumed scope `d359751e...`, terminated with exit 143, and committed **no learned 72-record result bundle**. RES594 is **Canceled**, not Done and not successfully evaluated.
4. RES614 is **Done** with `SIGTERM_CAUSE_UNDETERMINED`; the forensic and runner work is synthetic-only and is **not** a qualified real-data scorer.
5. Validation configuration means and deterministic baseline evaluation values were already observed. The four evaluation matches were used by deterministic controls; the original study is not untouched by all study activity.
6. There are exactly **four independent evaluation matches**. Overlapping windows and three seeds are not independent matches.
7. History-only is an ex-ante forecast setting. Future-ball and future-opponent-plus-ball condition on **realized future observations** and are not deployable forecasts.
8. RES501 remains `NOT_QUALIFIED`; RES340 remains deferred; no GPU purchase or paid compute is authorized.

## Admissibility review

The review judges the three options on the dimensions the issue requires. The judgments are about scientific defensibility, not engineering convenience.

| Dimension | Option 1 — new rights-cleared cohort | Option 2 — same four, post-failure descriptive | Option 3 — no new evaluation |
|---|---|---|---|
| Prior information exposure | Low if the cohort is locked before access. Strongest option. | **Conditional.** Validation means and deterministic baselines are known; no learned result bundle was committed, recovered or observed. Primary C1/C2 contrasts are independent of baseline values. | No new exposure, but no new learned evidence. |
| Statistical independence | Match-level independence if the cohort is genuinely new and compatible. | **Four matches only.** Windows overlap; seeds are repeated fits. Effective inferential unit is the match, \(n=4\). Descriptive only. | No new data; existing deterministic evidence remains. |
| Dataset compatibility | **Not verified.** No compatible rights-cleared cohort exists in the repository. A different provider needs a new measurement/admission contract and may require retraining. | **Strong.** Exact same source, admission, eligibility, masks, units, horizon and window identity. | Not applicable. |
| Measurement validity | Depends on the new source's tracking quality, extrapolation, coordinate conventions and masks. Requires a new validation contract. | **Strong.** Same frozen physical ADE/FDE/XY RMSE, truth mask, metric core and representation parity. New scorer must prove parity. | Existing deterministic metrics remain valid; learned measurement remains absent. |
| Scientific estimand | Could support broader descriptive generalization if the cohort is representative and compatible. | **Fixed-population descriptive estimand:** equal-match mean over the four fixed matches for the 18 fixed checkpoints, plus paired C1/C2 contrasts. It answers "how do these frozen models behave on these four matches?", not "how well do they generalize?" | No new estimand; the aborted attempt remains a non-result. |
| Outcome-dependent selection risk | Low if prospective and locked. Cohort selection itself must not be outcome-dependent. | **Low but non-zero.** No learned result bundle was committed, recovered or observed. Risks are rerun-after-failure, analysis changes, interim peeking and selective reporting; the protocol closes each. | None, but risks under-reporting the learned question. |
| Claim boundaries and reproducibility | Can support broader descriptive claims if the cohort is representative; still not deployment. New provenance and rights required. | **Descriptive only.** No significance, CIs, population inference, deployment, ex-ante future-context, v2 completion, LOMO or protected qualification. Fully hash-bound and receipt-verified. | Claims limited to deterministic baselines and validation results; transparent but incomplete for Paper B's learned-model question. |
| Feasibility now | **Not qualified.** No verified cohort; rights and compatibility work outstanding. | **Feasible in principle** under the proposed gates; engineering qualification is still required. | Immediately feasible; no new compute. |

### Option 1 — genuinely new rights-cleared evaluation cohort

This is scientifically the best route for a new held-out generalization claim. It is not available on the current evidence:

* The repository contains one public tracking source, the 20-match SkillCorner Open Data cohort, with frozen 12/4/4 roles. The four evaluation matches are already the evaluation roles for the frozen models.
* The Body Pose data covers two matches, one of which (`1925299`) is already an evaluation match and one (`1996435`) is a validation match. It is pose data, not a compatible tracking cohort.
* No other rights-cleared, compatible provider is documented. A different provider would need a new rights review, a new measurement and eligibility contract, a new role split, and likely new training. Mixing providers without a documented validation contract would confound source, tracking quality and model performance.
* Claiming a new cohort exists without metadata-only/rights verification would be unsupported. This memo does not claim one.

**Judgment:** preferred in principle, **not qualified now**. It remains the correct path if a new cohort is independently verified. It is not a reason to delay a bounded descriptive study on the existing four matches.

### Option 2 — post-failure descriptive study on the same four matches

This is admissible only as a **descriptive, fixed-population, fixed-model measurement**. The "held-out" label refers to the four matches being held out from the 18 models' training and validation; it does not mean a new cohort or a new generalization sample. The study is post-failure and pre-observation of learned held-out outcomes. The scientific rationale is not "a new authorization hash exists." It is:

1. **The measurement was not consummated in a committed result.** RES594 materialized the private snapshot and entered the hashing/scoring phase; some in-memory learned forward passes may have occurred. It produced no learned result bundle, no 72 records and no report. No learned held-out outcome was available to condition on.
2. **No learned result bundle was committed, recovered or observed for the four matches.** The only committed prior evaluation activity on them was deterministic baselines, which are controls, not the learned estimand; the aborted learned attempt produced no committed result.
3. **The analysis plan predates the failure.** Endpoints, model matrix, aggregation, C1/C2 contrasts and planned strata are inherited from RES593 and the original v2 protocol. The new protocol adds execution and verification details, not new scientific choices.
4. **The execution was interrupted by an unexplained SIGTERM; no scientific failure was demonstrated.** RES614 reports `SIGTERM_CAUSE_UNDETERMINED` and excluded OOM, host shutdown, scorer ceilings and agent kill. The signal sender and underlying trigger were not proven. The loss mechanisms were architectural: one commit boundary, no signal handling, no telemetry. A new study with sealed per-match receipts and durable supervision addresses them.
5. **The new study is separately versioned and separately authorized.** It has a new study ID, new protocol, new scorer identity, new scope, new ledger root and new GO phrase. It does not reuse the old scope, old GO phrase, old ledger or old snapshot. The old scope remains permanently closed.
6. **The claims are bounded.** The study reports descriptive metrics on four fixed matches. It does not claim significance, generalization, deployment, ex-ante future-context skill, v2 completion, LOMO completion or protected qualification.

The residual risks are real and must be controlled:

* **Rerun-after-failure / success-conditioned reporting.** The study exists because the first attempt was interrupted without a committed result. The protocol must state that the decision is based on the unconsummated measurement, not on an observed outcome, and must commit to reporting the result regardless of direction. The new study is the final attempt under this design; a further attempt would require a new scientific rationale and a new owner decision.
* **Analysis flexibility.** Any post-failure change to endpoints, matches, cells, contrasts or aggregation would create outcome-dependent risk. The protocol forbids such changes. The only permitted additions are execution, provenance, verification and interruption rules.
* **Interim peeking.** The scientific analyst must not see interim learned results. Sealed receipts are for integrity verification, not scientific decision-making. The analyst sees only the final verified bundle.
* **Known baselines.** The deterministic values are known. The primary C1/C2 contrasts use only learned-model ADE and are independent of baseline rounding. Baseline comparisons are secondary, descriptive and disclose the prior observation.
* **n=4.** The study cannot support population inference. All claims are bounded to the four matches. The leave-one-match-out diagnostic is descriptive and is not training LOMO.
* **Engineering risk.** The new scorer and supervisor are not yet implemented. The protocol requires synthetic end-to-end qualification and independent scorer validation before any real input. A failure at that gate is a NO-GO, not a reason to weaken the gate.

**Judgment:** **conditionally admissible as descriptive only**, subject to the gates in the proposed protocol. **Not admissible** as confirmatory, generalization, v2 completion or a retry of the consumed scope.

### Option 3 — no new evaluation

This is the correct fallback if any of the Option 2 conditions cannot be met, or if the owner requires confirmatory/population-level inference. It preserves the aborted result as a non-result and pivots Paper B to validated deterministic baselines and validation evidence with narrowed claims. It is also the correct decision if the independent reviewer concludes that the four-match descriptive study is not worth the residual risk.

**Judgment:** scientifically defensible, but it leaves the learned held-out question unanswered. It is the fallback, not the recommendation, because a bounded descriptive measurement is feasible and scientifically useful.

## Why a new authorization hash is not sufficient

A new hash proves only that a new scope exists. It does not establish scientific admissibility. The following conditions are necessary and collectively sufficient for the recommended path:

1. No learned held-out result bundle was committed, recovered or observed from RES594, and the new protocol does not use the old snapshot or partial progress.
2. The analysis plan is inherited unchanged; no post-failure endpoint, match, cell, contrast or aggregation change.
3. The model matrix is exactly the frozen 18 checkpoints; zero new fits, zero reselection, zero substitution.
4. The population is exactly the four frozen evaluation matches; no training or validation scoring; no provider mixing.
5. The new scorer is independently validated on synthetic fixtures with bitwise replay and aggregate verification.
6. The execution architecture has detached supervision, signal attribution, sealed per-match receipts, fsynced telemetry and independent completion verification.
7. The interruption policy is fail-closed for scientific/integrity failures and unknown causes; infrastructure continuation is narrow, predeclared, bitwise-parity-proven and outcome-blind.
8. The claims are descriptive only and bounded to the four matches.
9. The new study is separately reviewed, separately ratified and separately authorized; the old scope remains closed.
10. No execution occurs until all gates, including a new distinct owner GO, are satisfied.

If any condition fails, the design is `DESIGN_NO_GO`.

## Recommended path and conditions

**Recommend Option 2, descriptive only**, under the separately versioned protocol in `docs/res635-post-failure-descriptive-protocol-v1.md` and `res635_post_failure_descriptive_protocol_v1.json`.

The recommendation is conditional on:

* independent scientific review of the protocol and this memo;
* express owner ratification of the new study identity, claims matrix and gate sequence;
* a separately approved synthetic-only engineering qualification of the new scorer and supervisor;
* a private non-consuming preflight;
* a new and distinct express owner GO bound to the new protocol, checkpoint manifest, research admission and scorer code;
* independent private verification of the 72 records and the aggregation;
* public-safe reporting with the required disclosures.

**No execution GO is granted by this memo, the protocol, the repository changes or any PR approval.** Owner scientific ratification and execution GO are separate acts.

## Residual risks and missing evidence

| Risk / gap | Status | Consequence |
|---|---|---|
| No verified new rights-cleared cohort | Open | Option 1 cannot be claimed; Option 2 remains the only current route. |
| Four matches only; overlapping windows | Irreducible | Descriptive only; no significance, CIs or population inference. |
| Validation means and deterministic baselines observed | Disclosed | Possible influence on analysis choices; primary learned contrasts are inherited and baseline-independent. |
| Aborted RES594 attempt | Disclosed | Entered scoring; no learned result bundle committed, recovered or observed; new protocol must not use the old snapshot or scope. |
| Workload shape known | Disclosed | Engineering budgets set from synthetic qualification and conservative margins, not from partial-run progress. |
| New scorer not implemented | Open | Synthetic qualification and independent validation are mandatory before real input. |
| New supervisor not implemented for real data | Open | Durable execution qualification is mandatory before real input. |
| n=4 representativeness | Irreducible | No generalization to other matches, leagues, seasons, teams or providers. |
| Original v2 LOMO incomplete | Preserved | The study is not v2 completion and does not qualify the protected population. |

## What is not authorized

This memo and the proposed protocol do **not** authorize:

* opening, hashing, parsing or executing the retained RES594 private snapshot;
* reusing the RES594 consumed scope, authorization record, GO phrase or ledger;
* scoring the four original evaluation matches with the learned models;
* loading private learned truth or generating real model predictions;
* training, warm starts, checkpoint reselection, hyperparameter search or LOMO;
* GPU or paid compute;
* changing RES594 to Done, RES593 to incomplete, RES614 to a real-data qualification, RES501 to qualified, or RES340 to executed;
* claiming that RES440 is unblocked by closing forensic issues;
* merging the draft PR or treating PR approval as scientific ratification or execution GO.

## Proposed subsequent issue sequence

1. **Independent scientific review** of this memo and the protocol — reviewer must be independent of the protocol author.
2. **Owner ratification** of the new study identity, claims matrix, resource budget and gate sequence.
3. **Synthetic-only engineering qualification** of the new scorer, supervisor, receipts and interruption policy.
4. **Independent scorer validation** with adversarial synthetic fixtures and bitwise replay.
5. **Private non-consuming preflight** over metadata, hashes, runtime and resource availability.
6. **New and distinct owner GO** bound to the new study, manifest, admission and scorer code.
7. **One controlled real study** with sealed per-match receipts and durable supervision.
8. **Independent private 72-result verification**.
9. **Public-safe reporting** for Paper B with the required disclosures.
10. **R5/RES440 dependency update**: record that the learned result package is still missing and that RES440 is not unblocked by forensic closure.

## References

* `docs/res593-amended-heldout-evaluation-v1.md`
* `docs/res614-sigterm-incident-report.md`
* `docs/res614-execution-architecture-proposal.md`
* `docs/res614-runtime-audit-and-governance.md`
* `docs/res614-synthetic-performance-report.md`
* `docs/res337-deterministic-research-results.md`
* `docs/res338-research-final-fits.md`
* `docs/data-rights.md`
* `docs/research-population-admission-v1.md`
* `docs/prospective-experiment-plan-v2.md`
* `docs/results-and-provenance.md`
* RES310, RES440, RES312, RES347 (Linear)
