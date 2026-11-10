# RES614 frozen-scorer runtime audit and governance assessment

Audited at the frozen commit `7acc2c4e1174935efbe561e072f68c349af5e05f`
(`amended_heldout_evaluation.py`, sha256 `d14567a6...ceeb5bf`). The scorer, its entrypoint shim,
the amendment, the checkpoint manifest and the authorization schema are unchanged by this work
(`tests/unit/test_res614_frozen_integrity.py` enforces this). Line numbers refer to that file.

## Phase order and where time goes

| # | Phase | Code | Observed / projected cost | Interruption consequence |
|---|---|---|---|---|
| 1 | Authorization check, scope consumption, campaign reservation | `authorize_owner_execution`, `_consume_owner_authorization`, `_reserve_campaign` (2277 - 2335) | about 10 s with imports (observed) | Scope is consumed before any work, so a failure here still spends the one-shot GO |
| 2 | Load 18 checkpoints | `load_frozen_models` (1234) | with source verification, about 2.4 min before the snapshot appeared (observed) | Nothing durable lost |
| 3 | Source verification and research-population reconciliation | `baseline_runner.verify`, producer digests, `_prepare_verified_research_input` head (863 - 975) | within the 2.4 min | Nothing durable lost |
| 4 | Materialise 4 evaluation matches into one private JSONL | `_prepare_verified_research_input` (1049 - 1150) | about 9.5 min, 6.82 GB (observed) | Python exceptions unlink the file; a signal leaves a partial or complete 6.8 GB private file |
| 5 | SHA-256 readback of the snapshot | `_secure_sha256` (1176, called at 2562) | about 0.1 min at ~1 GiB/s (synthetic) | none |
| 6 | Sequential reread, per-window validation, features, 18 forward calls, metrics | `_score_authorized_snapshot` (2366 - 2420), `_score_window` (1577) | projected about 32 - 64 min (synthetic); the run had spent 18.8 min here | **All in-memory accumulators lost** |
| 7 | Build 72 records, aggregate, write receipts and campaign result | 2447 - 2512 | seconds | The only commit boundary in the design |

## Dominant operations (synthetic CPU basis, nominal scenario, 60 min total scoring path)

feature construction 37% (22 min), model inference 32% (19 min; 18 batch-of-two calls per window,
about 1 ms each, dispatch-bound), metrics 18% (11 min), JSON parse and write 13% (8 min), hashing
under 1%. Per-regime inference cost differs by about 25% (future-opponent regime highest). Feature
construction is pure Python over player-by-frame dictionaries; it scales with roster size and
number of scoreable scenes (35.7 - 69.7 min across scenarios).

## Memory and resources

Accumulators are small (per-seed, per-match, per-stratum aggregates), so RSS stayed near 164 MiB
(observed) versus an 8 GiB cap; the synthetic harness peaked at 250 MiB including its own
generator. Disk: the 6.82 GB snapshot is 83% of the 8 GiB input ceiling and fully duplicates data
that is re-derivable from the verified source. CPU ceilings (4 h) and wall ceilings (6 h) were
roughly four times the synthetic projection and were never the binding constraint.

## Failure boundaries

| Boundary | Behaviour in frozen code | Consequence |
|---|---|---|
| Python exception | `except BaseException` writes `.failed.json` and unlinks the snapshot (2584 - 2590) | clean, auditable stop |
| Resource breach | `_check_resource_limits` raises per window (2353) | clean stop with marker |
| SIGTERM, SIGINT, SIGHUP | no handler (zero references to `signal`) | immediate termination, no marker, snapshot survives |
| SIGKILL, OOM, power loss | unobservable by design | same as above |
| Partial progress | none persisted; no per-match receipt or telemetry | everything computed is lost |
| Duplicate execution | ledger in the parent directory, consumed before work | prevents reruns but also makes any infrastructure failure irreversible |
| Progress telemetry | none; stdout was empty for 30 min | stalls and slow progress are indistinguishable |

## Audit conclusions

1. The workload is modest. About one CPU-hour of scoring against a 4 h ceiling means the scientific
   design is feasible on this hardware; the failure was in execution architecture, not in scale.
2. The unrecoverable pieces were created by design choices: a single commit boundary, no signal
   handling, consuming the one-shot GO before any durable progress, and no telemetry.
3. The 6.8 GB intermediate snapshot adds I/O risk and a private-data artefact without being
   needed for correctness; streaming with per-match digests would avoid it.

## Scientific-governance assessment

What this work does **not** do: it does not reopen RES594, reuse its GO, recover or reconstruct any
learned result, or authorise retry. RES594 stays Canceled; RES593 stays Done; RES501 stays
`NOT_QUALIFIED`; RES340 stays deferred. The retained private snapshot is not a result. Re-scoring
it, or computing on it, would be a new access to held-out material that the consumed scope does not
cover.

Relationship to the tracked requirements: RES594 asked that any unavoidable interrupted or partial
run have explicit, predeclared fail-close handling. The frozen scorer's fail-close (the
`.failed.json` marker) only runs for Python exceptions, so a signal bypassed it. That is a gap in
the execution contract, not an unrecorded scientific decision, and it produced no outcome that
could steer analysis choices. RES440 (the downstream match-level result package) depends on 72
learned result records that do not exist, so it has nothing to consume; its state is not changed
here. Its inputs would come only from a future, separately authorised campaign.

What an independently approved future held-out study would need:

1. **A new amendment and protocol identity**, not an edit of RES593. It must declare that matches
   and aggregate baselines were already observed, that the first campaign's termination is
   disclosed, and that no learned held-out outcome from it exists. State that the first attempt
   produced no result so there is no outcome-dependent choice, and explain why that does not make
   the second attempt a free rerun (the 18 checkpoints, baselines and eligible population are
   unchanged, but the analyst has now seen the full workload shape).
2. **A new owner scope hash and fresh GO**, bound to the new scorer-code identity. The historical
   scope `d359751e...` must remain unusable; the runner denies it explicitly.
3. **A ratified execution contract**: detached supervision, signal attribution, per-match sealed
   receipts, streaming input, fsynced telemetry, and a defined treatment of interruption. The
   crucial decision is whether sealed per-match results may be reused after an infrastructure
   interruption. That is a scientific choice (it must not be conditioned on partial outcomes), so
   it must be fixed before data access: either (a) any interruption voids the run and requires a new
   owner GO, or (b) per-match scoring is a pure function of frozen inputs and a resumed match is
   bitwise identical to an uninterrupted one, so resumption cannot depend on observed values. Only
   (b) may be considered, and it needs its own synthetic equivalence qualification.
4. **Independent verification** of the new scorer against synthetic fixtures with bitwise replay
   (same runtime), reviewed by someone other than the implementer, with the frozen source and
   entrypoint of RES594 preserved byte-for-byte.
5. **Unchanged guardrails**: protected-population status stays `NOT_QUALIFIED`; no publication of
   private artifacts, reconstructive trajectories or checkpoints; zero paid compute unless a new
   amendment says otherwise.

## Recommendation

**NO-GO** on any real-data scoring now. **GO** to draft a new, separate study design that adopts the
qualified execution architecture, because the synthetic evidence shows the computation is feasible
and the architecture removes the identified loss mechanisms. Neither statement authorises
execution.
