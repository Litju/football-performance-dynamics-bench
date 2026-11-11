# RES635 proposed protocol — post-failure descriptive held-out study v1

**Status: PROPOSED / UNRATIFIED / NOT AUTHORIZED FOR EXECUTION.**
**Study ID:** `fpdbench.public-skillcorner-post-failure-descriptive-heldout/1.0.0`
**Protocol schema:** `fpdbench.res635.post-failure-descriptive-protocol/1.0.0`
**Machine-readable protocol:** `res635_post_failure_descriptive_protocol_v1.json`
**Protocol file SHA-256:** `ac931391ecb0afcb68974e1765f65fbff17071ade2bcaab93bdadd22f84a0305`
**Decision:** `DESIGN_GO_FOR_OWNER_REVIEW` (ticket) / `RES635_READY_FOR_FINAL_SCIENTIFIC_RATIFICATION_REVIEW` (review)
**Review:** `RES635_SCIENTIFICALLY_ADMISSIBLE_CONDITIONAL_REPAIRS`; the three precision corrections are applied.
**Execution GO:** **not granted.**

This is a separately versioned proposal for a new, descriptive, research-only study. It is not the original v2 protocol, not the RES593 amendment, not a retry or reuse of the RES594 consumed authorization, and not a completion of either the original 234-fit study or the deferred 216-fit LOMO campaign. It has no owner ratification and no execution authorization.

## 1. Historical authorities and non-modification

The following authorities are immutable for this proposal:

| Authority | Identity |
|---|---|
| Original v2 plan | `a59fee6ee8e9fb03f4f0ccdae1933458af2bbf2375db7e6cd2bdf10962e42b62` |
| Original v2 protocol | `3d7bdc46300b966a4da274579d21ac4c8219e1ef897719d6b7a308596e9f1d9f` |
| Research admission | `a8c82bfa09ac792d6c4ae779d4b28158c33ed3c2500f8548f3e94d48197f4fd1` |
| RES593 amendment | `e54f067a07479b81c4625428e49e5a5b907c49987d4c5bd7982138e270e66913` |
| RES593 frozen main | `7acc2c4e1174935efbe561e072f68c349af5e05f` |
| 18-checkpoint manifest | `770f1d9bbca3020237992181a56e4f5be4adaae7aab07f5f1313aa699d8693e0` |
| Baseline reference | `21b19a2370d5b4a45652a6ce132cb3e78a4abe2027a096a71f383b1191ea9b36` |
| Private baseline index | `8962fd40437c4aca50b86c8f918b653c35e2aa4277010fe10cbd19ffe8d32d4e` |
| Deterministic results document | `c98d8d29254c674e1011bb4b05912c5d12921c550a133eb8cdecc328c9263a68` |
| RES594 one-shot scope | `d359751e969767f30ed6e90c65b13d0eec49f11c9e33e1d2319b19530d28f2e0` |
| RES594 authorization record | `bad96973cf6f0759386544d24bc17de3368a578546e07826769bc9f727361868` |
| RES614 merged main | `cc3f1587e6837dd3c060a24b01236df8139b5c14` |
| RES614 incident evidence | `ce0c280fd6e95f8cf12b46d26df675b962c13d6f5b068836e6a280d22f869b17` |
| RES614 execution architecture | `4b3b761860ca4e118d032e341a03cf944f2d4ed5e92f597e32fed117cef272e7` |

The proposal does not modify the RES593 amendment, the 18-checkpoint manifest, the historical scorer, the RES594 entrypoint, the RES594 ledger or the RES614 evidence. The existing `tests/unit/test_res614_frozen_integrity.py` continues to enforce the frozen scorer and manifest identities.

The old scope is permanently closed. This proposal does not reuse the RES594 scope, authorization record, GO phrase, ledger, output directory or retained private snapshot. A new authorization hash alone is not the admissibility basis; the scientific conditions in `docs/res635-admissibility-decision.md` are.

## 2. Study classification and rationale

| Attribute | Value |
|---|---|
| Study type | Descriptive, fixed-population, fixed-model measurement |
| Timing | Post-failure, pre-observation of learned held-out outcomes |
| Prior attempt entered scoring phase | Yes (snapshot materialized; hashing/scoring began) |
| Learned result bundle committed/recovered/observed | No |
| Original preregistration | No |
| Confirmatory | No |
| Owner ratified | No |
| Execution authorized | No |
| New fits | 0 |
| New evaluation cohort | No |
| Original v2 completion | No |
| LOMO completion | No |
| Protected population | `NOT_QUALIFIED` |

The study exists because the RES594 measurement was not consummated in a committed result. The campaign consumed its one-shot scope, materialized its private snapshot and entered the hashing/scoring phase; some in-memory learned forward passes may have occurred. It then terminated with exit 143. No learned result bundle was committed, recovered or observed by the scientific analyst, and no 72-record result, campaign result or report exists. The proposed study is therefore **post-failure and pre-observation of learned held-out outcomes**: it is a re-execution of an unconsummated measurement, not a rerun after an observed result.

The execution was interrupted by an unexplained SIGTERM; RES614 reports `SIGTERM_CAUSE_UNDETERMINED`. OOM, host shutdown, scorer resource ceilings and agent kill were excluded by the available evidence, but the signal sender and underlying trigger were not proven. No scientific or methodological error was recorded and no scientific failure was demonstrated; this protocol does not claim the termination cause was established. The loss mechanisms were architectural: one commit boundary, no signal handling and no telemetry. This proposal adopts the synthetic-qualified detached supervisor, streaming input, sealed per-match receipts, fsynced telemetry and independent completion verification described in the RES614 architecture proposal. Those are engineering changes, not scientific changes.

## 3. Population and dependence

The study uses exactly the four frozen evaluation-role matches:

`1874553`, `1925299`, `2006229`, `2010085`.

The "held-out" label refers to these four matches being held out from the 18 models' training and validation; it does not mean a new cohort or a new generalization sample.

The population contract is unchanged:

* original research-only admission;
* original v2 candidate rules and window identity;
* 25 history intervals plus the origin, 15 future observations at 0.2-second spacing, 3.0-second horizon, 41 support slots;
* canonical 5 Hz source frames;
* source pitch XY in metres, no scene reflection;
* the original per-player, per-step finite physical truth mask;
* absolute and origin-relative displacement targets evaluated against the same absolute physical truth;
* equal scene weighting within a window and equal window weighting within a match;
* exactly four independent match units.

The 51,713 eligible windows and 103,426 directed scenes are a computational census, not independent observations. Windows overlap in time and share players and possessions. The three seeds are repeated fits on the same training data, not independent matches. The effective inferential unit is the match, \(n=4\). No claim in this study treats windows or seeds as independent.

Training and validation matches are not scored. The research root may contain the full 20-match population for producer/verifier reconciliation, but only the four evaluation-role windows enter the learned scorer. The scorer must verify the role, match identity, ordered player panel, window identity and truth mask before scoring.

No provider mixing is allowed. A different provider would require a new rights review, measurement contract, eligibility contract and role split; it is not a drop-in extension of this study.

## 4. Model matrix

The study uses the exact 18 final-fit checkpoints from the frozen 18-checkpoint manifest:

* one `per_target_context_deepsets_mlp_v1` model;
* three information regimes: `history_only`, `future_ball`, `future_opponent_plus_ball`;
* two target representations: `absolute_xy`, `origin_relative_displacement`;
* three seeds: 1729, 2718, 31415;
* 18 checkpoint configurations and 72 match-scoped result records.

| Regime | Representation | Seed | Checkpoint SHA-256 (prefix) | Selected step |
|---|---|---:|---|---:|
| `history_only` | `absolute_xy` | 1729 | `19b2ca2b6ef1` | 2,100 |
| `history_only` | `absolute_xy` | 2718 | `e7bd90aebf3d` | 3,900 |
| `history_only` | `absolute_xy` | 31415 | `65340e506b16` | 1,300 |
| `history_only` | `origin_relative_displacement` | 1729 | `0d61bec05776` | 4,900 |
| `history_only` | `origin_relative_displacement` | 2718 | `111783338265` | 4,600 |
| `history_only` | `origin_relative_displacement` | 31415 | `b82ced8285e1` | 4,500 |
| `future_ball` | `absolute_xy` | 1729 | `d79c52eeb17d` | 5,000 |
| `future_ball` | `absolute_xy` | 2718 | `2c9196571908` | 3,100 |
| `future_ball` | `absolute_xy` | 31415 | `72836aeb07a5` | 2,300 |
| `future_ball` | `origin_relative_displacement` | 1729 | `e8cc3dbf83a0` | 5,000 |
| `future_ball` | `origin_relative_displacement` | 2718 | `7d1fa53a644f` | 4,500 |
| `future_ball` | `origin_relative_displacement` | 31415 | `b177d305ac03` | 4,600 |
| `future_opponent_plus_ball` | `absolute_xy` | 1729 | `74f427d8e70e` | 4,800 |
| `future_opponent_plus_ball` | `absolute_xy` | 2718 | `bc9461a95b0e` | 2,100 |
| `future_opponent_plus_ball` | `absolute_xy` | 31415 | `0f4cac13fc85` | 3,700 |
| `future_opponent_plus_ball` | `origin_relative_displacement` | 1729 | `cb0442a96092` | 4,700 |
| `future_opponent_plus_ball` | `origin_relative_displacement` | 2718 | `b580e08670f3` | 4,700 |
| `future_opponent_plus_ball` | `origin_relative_displacement` | 31415 | `720571f53a0e` | 4,600 |

The exact full hashes, configuration hashes and receipt hashes are in the machine-readable protocol and are checked against the frozen manifest by `tests/unit/test_res635_protocol.py`.

The study performs zero new fits, warm starts, checkpoint reselection, checkpoint substitution, hyperparameter searches or optimizer steps. The checkpoints are loaded read-only from owner-private storage by their frozen SHA-256 filenames. No checkpoint bytes enter the repository or any public output.

## 5. Endpoints and measurement validity

| Endpoint | Definition | Unit | Role |
|---|---|---|---|
| Physical XY ADE | Mean Euclidean distance between predicted and true XY over scoreable player-steps | metres | Primary |
| Physical XY FDE | Euclidean distance at the final future step | metres | Secondary |
| Coordinate XY RMSE | Scalar-coordinate RMSE in metres: `sqrt(sum(dx^2 + dy^2) / (2 * N_masked_points))` over scoreable player-steps; metric ID `trajectory.xy_rmse_m.v1` | metres | Secondary |

The truth frame is absolute source XY in metres. Origin-relative displacement predictions are reconstructed by adding each target player's frozen origin XY before scoring. Both representations use the same frozen per-player, per-step physical truth mask. Missing truth is not imputed. Predicted points outside the mask are not scored.

The metric core is the frozen implementation. The new scorer must reuse it or prove numerical parity on synthetic fixtures. No new metric definition, normalization, coordinate frame or eligibility rule is allowed.

The frozen metric `trajectory.xy_rmse_m.v1` is **scalar-coordinate** RMSE, not root mean squared Euclidean displacement: it computes `sqrt(sum(dx^2 + dy^2) / (2 * N_masked_points))`, where `N_masked_points` is the number of scoreable player-steps and the denominator counts the two scalar coordinates per point. The protocol does not change this implementation, its denominator or any historical value. ADE remains the mean Euclidean distance; FDE remains the Euclidean distance at the final future step.

History-only is an ex-ante forecast setting. Future-ball and future-opponent-plus-ball condition on realized future observations. The study measures apparent predictability under added realized context, not deployable forecasting skill.

## 6. Aggregation and contrasts

For each model cell and evaluation match:

1. Score each eligible window with the frozen masked physical trajectory metric core.
2. Average scoreable directed scene metrics equally within the window.
3. Average scoreable windows equally within the match.
4. Preserve the per-match denominator, mask identity and missingness accounting.

For each regime/representation:

1. Average the three seed values within each match first.
2. Average the four match means equally.
3. Preserve all 72 seed-by-match records.

Do not pool overlapping windows as independent observations. Do not compute significance tests, p-values or confidence intervals.

The four frozen contrasts are:

* **C1, `absolute_xy`:** `history_only` ADE − `future_ball` ADE.
* **C1, `origin_relative_displacement`:** `history_only` ADE − `future_ball` ADE.
* **C2, `absolute_xy`:** `future_ball` ADE − `future_opponent_plus_ball` ADE.
* **C2, `origin_relative_displacement`:** `future_ball` ADE − `future_opponent_plus_ball` ADE.

Compute matched seed averages within each match before each match-level contrast. Report all four match-level values and their equal-match mean. Positive values mean lower ADE with the added realized context. These are descriptive paired contrasts, not causal effects.

## 7. Deterministic reference comparability

The deterministic baselines were already scored on the four evaluation matches. Their published values are:

| Model | ADE (m) | FDE (m) | XY RMSE (m) |
|---|---:|---:|---:|
| `origin_persistence_v1` | 3.5219 | 6.3739 | 3.0952 |
| `constant_velocity_1s_v1` | 2.2433 | 4.9257 | 2.2384 |

The published precision is four decimal places; the rounding bound is at most 0.00005 m. The study reads the pinned aggregate reference and never reruns or silently recomputes the historical baselines. Baseline comparisons are secondary descriptive results. The primary C1/C2 contrasts use only learned-model ADE and are independent of baseline metric rounding.

The fact that these values were observed before the RES593 amendment is disclosed. It may have influenced analysis choices; the protocol does not claim outcome-blind design. It does claim that no learned result bundle was committed, recovered or observed by the scientific analyst.

## 8. Prior information exposure and outcome-dependence controls

| Information | Observed before this proposal? | Treatment |
|---|---|---|
| Six regime/representation validation means | Yes | Disclosed; used for checkpoint selection; no reselection. |
| Deterministic evaluation baselines | Yes | Disclosed; secondary descriptive comparison only. |
| Learned evaluation metrics on the four matches | No | Primary estimand remains unobserved. |
| RES594 result bundle | No | No 72 records, no campaign result, no report. |
| RES594 partial in-memory work | No | Lost with the process; not recovered or reconstructed. |
| Workload shape (51,713 windows, ~930,834 forward calls, 6.82 GB snapshot) | Yes | Engineering context only; not a scientific outcome. |

The analysis plan is inherited from the pre-failure authority. The post-failure changes are limited to execution, provenance, verification and interruption rules. The machine-readable protocol records `post_failure_analysis_plan_changes: []`.

The following controls are mandatory:

* All four matches and all 18 cells are reported, including negative or null findings.
* No cell or match may be dropped because of its result.
* No interim learned result may be inspected by the scientific analyst.
* No early stopping based on results; only predeclared resource or integrity failures may stop the run.
* No post-hoc endpoint, match, cell or contrast changes.
* No post-hoc stratum promotion; the horizon and target-quality strata are predeclared and descriptive.
* No model reselection, checkpoint substitution, warm start, new fit or hyperparameter search.
* No use of the RES594 snapshot, partial progress, scope, GO phrase or ledger.
* If the study fails, the failure is reported and the design is closed; a further attempt requires a new scientific rationale and a new owner decision.

## 9. Execution architecture

The study requires a new scorer and a new entrypoint. The historical RES594 scorer and entrypoint remain byte-identical and are not reused.

| Component | Requirement |
|---|---|
| Input | Streaming from the verified source; no full private JSONL snapshot. |
| Memory | Bounded; one match at a time; no full-corpus materialization. |
| Models | 18 frozen checkpoints, read-only, SHA-256 verified before inference. |
| Forward calls | Up to 930,834 (18 models × 51,713 windows); CPU FP32, one thread. |
| Telemetry | Fsynced periodic progress: windows, wall, CPU, RSS, sealed count. |
| Receipts | One sealed receipt per match, content SHA-256 and previous-receipt hash. |
| Final commit | Written once after all four receipts are sealed and verified. |
| Verification | Worker re-verifies its bundle; supervisor independently re-verifies every zero-exit worker; `status` re-verifies again. |
| Failure records | Terminal record written atomically on every controlled exit. Sudden SIGKILL, OOM or power loss may leave no worker record; §12 requires independent postmortem attestation instead. |
| Partial results | Never scientifically usable. |

The new scorer must not import or invoke the RES594 scorer, entrypoint, authorization or ledger. The new entrypoint is proposed as `fpdbench-res635`; the module is proposed as `fpdbench.benchmarks.conditional_multi_agent_motion_prediction.res635_post_failure_evaluation`. Neither is implemented by this protocol.

## 10. Durable execution supervision

The real study must run under a detached supervisor, not a transient agent session:

* launcher starts the supervisor with `start_new_session=True` and returns;
* supervisor owns a dedicated process group and the only authority to terminate the worker;
* worker blocks SIGTERM/SIGINT/SIGHUP and records sender PID, UID, parent PID and command line;
* supervisor records worker PID, return code, signal and `terminated_by`;
* supervisor ignores SIGHUP;
* graceful stop at window boundaries, bounded watchdog, then SIGKILL of the process group if needed;
* hard wall timeout and resource ceilings enforced by the supervisor;
* supervisor exit status is zero only for a verified completion, with distinct nonzero codes for timeout, crash, kill, worker refusal and unverifiable completion;
* `status` re-verifies the campaign rather than trusting the recorded outcome.

A systemd unit with `KillMode=mixed`, `TimeoutStopSec`, `Restart=no`, `MemoryMax` and `CPUQuota` is the production target, or an equivalent sandboxed job. The RES614 prototype is synthetic-only; real-data qualification is a separate gate.

## 11. Sealed receipts and final commit

Each match produces one sealed receipt containing:

* study ID, protocol SHA-256, scope SHA-256 and campaign identity;
* match ID and role;
* checkpoint manifest SHA-256 and scorer code SHA-256;
* runtime identity and host identity;
* eligible window count, scoreable scene count, scored-point and final-target denominators;
* per-cell ADE/FDE/XY RMSE for the 18 cells;
* per-cell seed values and match-level aggregates;
* missingness and mask identity;
* content SHA-256 and previous-receipt hash.

Receipts are written to a temporary file, fsynced, atomically renamed and directory-fsynced. A receipt is never read as a result until it is sealed. Removal, reorder, edit or truncation of the chain is detectable as `CORRUPT` or a missing-match gap.

The final `campaign-result.json` is written once, after every receipt is sealed. It contains the 72 records, the four match-level aggregates, the C1/C2 contrasts, the provenance chain and the verification status. A result file never implies completion. The worker returns success only after re-running the full completion verifier over its own bundle; the supervisor repeats the verification; `status` repeats it again.

## 12. Predeclared infrastructure-interruption policy

**Mode:** `FAIL_CLOSED_WITH_ONE_PREAPPROVED_OUTCOME_BLIND_CONTINUATION` (fail-closed for scientific, integrity, unknown and untrustworthy causes).

| Situation | Worker terminal record | Required independent evidence | Continuation |
|---|---|---|---|
| Scientific or integrity failure | Required if the worker is alive to write it | Supervisor outcome record and failure classification | No |
| Unknown or untrustworthy cause | Not sufficient by itself | None sufficient | No |
| Supervisor per-attempt timeout with remaining cumulative budget | Required if the worker is alive | Supervisor `waitpid` status, sender, fsynced telemetry, cumulative budget and a verified match boundary | Yes, at most one |
| Worker SIGTERM from an external process | Required if the worker handles it; not guaranteed | Supervisor `waitpid` status; sender PID/UID if available; host audit or journal if available | Only if the independent evidence establishes a predeclared cause and the match boundary |
| SIGKILL | Not required; the worker cannot write one | Supervisor `waitpid` status with signal 9; if the supervisor is also lost, host attestation | Only if the independent evidence establishes a predeclared cause and the match boundary |
| OOM kill | Not required | Supervisor record plus cgroup `memory.events` OOM count and kernel log with cgroup and PID | Only if the independent evidence establishes a predeclared cause and the match boundary |
| Power loss or host reboot | Not required | Host boot ID change, systemd journal shutdown/reboot record, supervisor last fsynced telemetry and sealed receipt chain | Only if the independent evidence establishes a predeclared cause and the match boundary |
| Filesystem I/O failure | Not required | Supervisor record plus kernel or filesystem error evidence from the host | Only if the independent evidence establishes a predeclared cause and the match boundary |
| Completed | Verified result | Independent completion verification | No |
| Torn write | Not a terminal record | Stray temp file and sealed prefix inspection | Only under the same conditions |

A continuation is permitted only when all of the following hold:

* the cause is a predeclared infrastructure cause, established by evidence produced outside the worker process;
* the evidence is trustworthy and independent: it comes from the supervisor's `waitpid` or outcome record, supervisor fsynced telemetry, host boot identity, systemd journal, kernel log, cgroup `memory.events`, or an independent host attestation bundle;
* the evidence binds the study protocol, scope, campaign and worker identity, and includes the worker wait status, the sealed receipt prefix, the cumulative CPU and wall consumed, and the remaining budget;
* the interruption occurred at a verified match boundary: every match in the sealed prefix is complete, no partial match receipt exists, and the next match has not started;
* the continuation uses the same new RES635 scope, same protocol, same checkpoint manifest, same research admission and same scorer code;
* the continuation is a `CONTINUATION_READY_SAME_SCOPE` state, not a new run, new scope or new authorization;
* the deterministic sealed-receipt parity was proven on synthetic fixtures before the GO; the resumed match is bitwise identical to an uninterrupted match under the same runtime;
* the supervisor may verify receipt existence, match identity and hash-chain integrity, but must not read or use metric values for the continuation decision;
* no human accesses interim metric values for the continuation decision;
* the continuation decision is automatic and outcome-blind;
* at most one continuation is allowed;
* cumulative CPU and wall time across the original attempt and the continuation stay within 14,400 CPU-seconds and 21,600 wall-seconds;
* the continuation is refused if the cumulative budget is exhausted or if the remaining budget is insufficient for the next match under the predeclared per-match budget;
* no new scope is created for a continuation; the scope remains the same;
* the historical consumed RES594 scope is never reused.

If trustworthy evidence is unavailable, the default is permanent failure. A missing worker terminal record after a sudden SIGKILL, OOM kill, power loss or reboot is not itself a reason to refuse a continuation if independent postmortem attestation satisfies the conditions above; it is a reason to refuse if that attestation is absent, incomplete or untrusted. Partial results are never scientifically usable.

## 13. Independent scorer validation

The scorer implementer and the scorer verifier must be different people or independent roles. Before any real input:

* the scorer is qualified on synthetic fixtures from the existing synthetic input generator;
* same-runtime prediction replay is bitwise equal (`rtol=0`, `atol=0`);
* truth-origin reconstruction uses absolute tolerance `1e-12`;
* the frozen metric core and the new scorer agree on masks, denominators, scene weighting, window weighting, representation parity and final targets, including the scalar-coordinate `trajectory.xy_rmse_m.v1` formula and its `2 * N_masked_points` denominator;
* adversarial cases cover wrong match/role, mask identity mismatch, scoreable count mismatch, representation parity failure, duplicate reads, incomplete 18-cell matrix, missing final target, non-finite prediction/truth, overlapping-window independence misuse, and receipt removal/reorder/edit/truncation;
* an independent aggregate calculator recomputes the 72 records, the four match-level aggregates and the C1/C2 contrasts from the sealed receipts;
* the deterministic sealed-receipt parity required for any continuation is proven on synthetic fixtures, including the match-boundary prefix and the resumed match;
* the verification report is frozen and hash-bound before the owner GO;
* real-data verification is limited to aggregate and provenance verification; it is not a second learned evaluation.

A failure at this gate is a NO-GO. It is not a reason to weaken the gate or to run real data first.

## 14. Provenance, ledger and retention

The study requires:

* a new study ID and new protocol SHA-256;
* a clear separation between the top-level RES635 study protocol SHA-256 and the frozen original v2 input protocol SHA-256 `3d7bdc46300b966a4da274579d21ac4c8219e1ef897719d6b7a308596e9f1d9f`; the nested evaluation-input identity uses the original v2 input protocol, not the RES635 study protocol;
* a new scope SHA-256 derived from the new study/protocol/manifest/admission/scorer/runtime/limits;
* an explicit prohibition on the historical consumed RES594 scope SHA-256 `d359751e969767f30ed6e90c65b13d0eec49f11c9e33e1d2319b19530d28f2e0`; the authorization schema rejects that value and the later executor must enforce the same rejection;
* a new, distinct owner authorization record;
* a new owner-private ledger root, independent of the campaign output path;
* a single authoritative ledger root preserved across sessions; no copying, renaming or deletion;
* a ledger record keyed by the exact new scope; `CONSUMED_IRREVERSIBLY` after consumption; `retry_allowed=false`;
* SHA-256 readback of the checkpoint manifest, source release/population, research admission, scorer code, runtime and host identity;
* per-match receipt SHA-256 and final result SHA-256;
* independent verifier readback of the complete bundle;
* an owner-private retention policy for raw predictions (if retained), checkpoints, source data, ledger and receipts;
* a public output limited to aggregate tables, non-reconstructive figures, hashes, provenance and limitations.

The new ledger must not be the RES594 ledger. The new authorization must not be the RES594 authorization. The new scope must not be the RES594 scope, and the new study protocol must not be the original v2 input protocol. The new GO phrase template is:

`RES635-OWNER-GO:<protocol-sha256>:<checkpoint-manifest-sha256>:<research-admission-sha256>:<scorer-code-sha256>`

The template is not a GO. No owner authorization exists for this proposal.

## 15. Resource budgets

| Resource | Ceiling |
|---|---:|
| Device | CPU only |
| Precision | FP32 |
| Threads | 1 |
| Python | 3.12.8 |
| NumPy | 2.2.4 |
| PyTorch | 2.6.0+cpu |
| CPU seconds | 14,400 |
| Wall seconds | 21,600 |
| Budget scope | Cumulative across the one campaign and at most one continuation |
| Continuation budget check | Refused if cumulative budget exhausted or remaining budget insufficient |
| Peak RSS | 2 GiB |
| Private working disk | 2 GiB |
| Full private snapshot | 0 bytes (streaming) |
| Paid compute units | 0 |
| Paid cost | USD 0 |
| GPU | None |
| Training | None |
| LOMO fits | 0 |
| Checkpoint loads | 18 |
| Forward-call estimate | 930,834 |
| Telemetry interval | 60 seconds |

The budgets are engineering ceilings, not scientific endpoints. They are set from the synthetic qualification and conservative margins, not from the interrupted attempt's partial progress. The private working-disk ceiling excludes the read-only verified source tree; it bounds transient buffers, receipts and telemetry. A resource breach is a controlled terminal stop and is reported; it is not a scientific result.

## 16. Gates

The study proceeds only in this order:

1. **Proposed scientific protocol** — this document and the machine-readable protocol. No execution.
2. **Independent scientific review** — a reviewer independent of the author checks the protocol and the admissibility memo. No execution.
3. **Express owner ratification** — the owner ratifies the study identity, claims matrix, resource budget and gate sequence. No execution.
4. **Separately approved synthetic-only engineering qualification** — the new scorer, supervisor, receipts and interruption policy are qualified on synthetic data. No real input.
5. **Private non-consuming preflight** — metadata-only verification of the pinned runtime, checkpoint manifest, research admission, source identity, ledger root and free space. No evaluation truth, no inference, no output reservation.
6. **New and distinct express owner GO** — bound to the new study/protocol/manifest/admission/scorer/runtime/limits. This is the only gate that authorizes real execution.
7. **One controlled real study** — one campaign, four matches, 18 cells, 72 records, sealed receipts, durable supervision.
8. **Independent private 72-result verification** — aggregate calculator and provenance verification; no second learned evaluation.
9. **Public-safe reporting** — aggregate tables, non-reconstructive figures, hashes, provenance, limitations and required disclosures.

No gate may be skipped. PR approval, CI success or issue closure does not grant owner ratification or execution GO.

## 17. Claims matrix

**Allowed claims:**

* descriptive physical ADE, FDE and XY RMSE for the 18 frozen checkpoints on the four fixed evaluation matches;
* descriptive within-match paired C1 and C2 contrasts, with all four match values and the equal-match mean;
* descriptive seed variation, match heterogeneity, denominators and masks;
* descriptive comparison with the previously observed deterministic baselines under the documented rounding bound;
* descriptive evaluation-match deletion sensitivity;
* descriptive predeclared horizon and target-quality strata;
* statements bounded to the four fixed matches and the 18 fixed checkpoints;
* statements that future-ball and future-opponent-plus-ball use realized future observations and are conditional, not deployable forecasts.

**Forbidden claims:**

* statistical significance, p-values, confidence intervals or population-level inference from four matches;
* generalization to other matches, leagues, seasons, teams or providers;
* deployment readiness or ex-ante forecasting skill for the realized-future regimes;
* completion of the original v2 234-fit prospective study;
* completion of the 216-fit training LOMO campaign;
* protected population qualification;
* treating the aborted RES594 run as a result or a scientific failure;
* claiming that a new authorization hash alone justifies the study;
* claiming the four evaluation matches are untouched by all study activity;
* confirmatory or original-preregistration status for this post-failure protocol;
* retrying or reusing the consumed RES594 scope.

## 18. Publication and rights boundary

Public outputs are limited to aggregate tables, non-reconstructive figures, hashes, provenance and limitations. Raw positions, target masks, source rows, reconstructive trajectories, checkpoints, optimizer state and row-level predictions remain owner-private. SkillCorner attribution and the pinned source revision are required. The protected population remains `NOT_QUALIFIED`.

Required disclosures for any Paper B use:

* the original v2 234-fit study is incomplete and the 216-fit LOMO remains deferred;
* the four evaluation matches were already used by deterministic baselines;
* validation means were observed before the RES593 amendment and used for checkpoint selection;
* the RES594 campaign was consumed and entered the scoring phase, but no learned result bundle was committed, recovered or observed, and the SIGTERM cause remains undetermined;
* the four matches are the only independent evaluation units; overlapping windows are not independent;
* future-ball and future-opponent-plus-ball use realized future observations and are conditional;
* the protected population remains `NOT_QUALIFIED`;
* no statistical significance or population generalization is claimed.

## 19. Prohibitions

This protocol prohibits:

* opening, hashing, parsing or executing the retained RES594 private snapshot;
* reusing the RES594 consumed scope, authorization record, GO phrase or ledger;
* scoring training or validation matches;
* new model fits, warm starts, checkpoint reselection or hyperparameter search;
* LOMO fits;
* GPU or paid compute;
* real evaluation input access before the separate owner GO;
* interim learned result access by the scientific analyst;
* post-hoc endpoint, match, cell or contrast changes;
* raw or row-level public release;
* claims of original v2 completion, LOMO completion or protected qualification.

## 20. Residual risks and missing evidence

| Risk / gap | Status | Consequence |
|---|---|---|
| No verified new rights-cleared cohort | Open | Option 1 cannot be claimed; this descriptive study is the only current route. |
| Four matches only; overlapping windows | Irreducible | Descriptive only; no significance, CIs or population inference. |
| Validation means and deterministic baselines observed | Disclosed | Possible influence on analysis choices; primary learned contrasts are inherited and baseline-independent. |
| Aborted RES594 attempt | Disclosed | Entered the scoring phase; no learned result bundle committed, recovered or observed; old snapshot and scope are not used. |
| Workload shape known | Disclosed | Engineering budgets set from synthetic qualification and conservative margins. |
| New scorer not implemented | Open | Synthetic qualification and independent validation are mandatory before real input. |
| New supervisor not implemented for real data | Open | Durable execution qualification is mandatory before real input. |
| Continuation evidence | Open | A continuation requires independent postmortem attestation; absent, incomplete or untrusted evidence is terminal. |
| n=4 representativeness | Irreducible | No generalization to other matches, leagues, seasons, teams or providers. |
| Original v2 LOMO incomplete | Preserved | The study is not v2 completion and does not qualify the protected population. |

## 21. References

* `docs/res635-admissibility-decision.md`
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
