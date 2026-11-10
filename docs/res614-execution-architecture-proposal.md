# RES614 execution architecture proposal (synthetic-qualified, not authorised for real data)

**Status: PROPOSAL for a future, separately ratified protocol.** Nothing here modifies, resumes,
retries or reinterprets the consumed RES594 authorization (scope
`d359751e969767f30ed6e90c65b13d0eec49f11c9e33e1d2319b19530d28f2e0`, `CONSUMED_IRREVERSIBLY`,
`retry_allowed=false`). The prototype in `tools/res614_resilient_runner.py` handles artificial
per-match units only and imports no scorer, model, checkpoint or protected-source code.

## Design goals mapped to the failures observed

| Observed failure (RES594) | Architectural answer | Demonstrated by synthetic test |
|---|---|---|
| Scorer was a direct child of an interactive agent exec session; the session ended with exit 143 and nobody recorded who sent SIGTERM | Detached supervisor in its own session; worker in its own process group; supervisor records worker exit status, signal and who ended it | `test_detached_launch_survives_launcher_exit_and_new_session`, `test_supervisor_survives_sighup_of_its_session` |
| SIGTERM sender unknown | Worker dequeues SIGTERM/SIGINT/SIGHUP with `sigwaitinfo` and records sender PID, UID, parent PID and command line | `test_sigterm_is_graceful_attributed_and_leaves_sealed_prefix` (sender equals test PID), `test_supervisor_enforces_hard_timeout_and_records_the_sender` |
| No `.failed.json`: default SIGTERM disposition kills Python without running `except` blocks | Signals are blocked and handled by a watcher thread; a terminal record is written atomically on every controlled exit | same tests; `.interrupted.json` / `.failed.json` always present for controlled stops |
| Shutdown behaviour undefined | Cooperative stop at window boundaries plus a bounded watchdog that records and force-exits after the grace period | `test_bounded_shutdown_forces_exit_when_window_overruns_grace` |
| Hung worker would never be reclaimed | Supervisor SIGTERM, grace, then SIGKILL of the process group, and it records which | `test_supervisor_sigkills_a_worker_that_ignores_sigterm` |
| 6.8 GB private snapshot materialised, hashed, re-read | Stream windows from the verified source straight into the scoring loop; bind the input by per-match streaming digests instead of a second full copy | prototype is streaming by construction; real-data equivalence is a protocol question |
| All 72 records committed only after a full pass | Seal one receipt per match when the match completes; commit the campaign result only when every match is sealed | `test_sigkill_leaves_no_false_completion_and_is_classified`, `test_tampered_receipt_chain_is_detected` |
| No progress visibility | Fsynced periodic telemetry (windows, wall, CPU, RSS, sealed count) | `test_injected_crash_between_windows_keeps_durable_telemetry` |
| Duplicate execution only guarded by a ledger file next to the output | Ledger outside the campaign directory, created with `O_EXCL`; survives deleting the campaign; concurrent starts allow exactly one | `test_duplicate_scope_is_refused_even_after_directory_removal`, `test_concurrent_starts_allow_exactly_one_execution` |

## Components

1. **Launcher.** Starts the supervisor with `start_new_session=True`, stdio redirected to files, and
   returns. The launching agent session may end at any time. In production this would be a systemd
   unit (`KillMode=mixed`, `TimeoutStopSec`, `Restart=no`, `MemoryMax`, `CPUQuota`) or an
   equivalent sandboxed job; the prototype uses plain sessions so it is testable anywhere.
2. **Supervisor.** Owns timeouts and the only authority to terminate the worker. It writes a
   `supervisor.json` outcome record (worker PID, return code, signal, `terminated_by`). It ignores
   SIGHUP.
3. **Worker.** Single-threaded compute with one extra signal-watcher thread. Checks stop flag,
   wall, CPU and RSS ceilings at every window. Performs no retry and no resume.
4. **Durable store.** Every committed file uses write-to-temp, `fsync(file)`, `rename`,
   `fsync(directory)`. Appends (telemetry) are `O_APPEND` + `fsync`. A temp file is never read as
   a result and is reported by `inspect` as evidence of an unclean stop.
5. **Sealed per-match receipts.** Each receipt carries its content SHA-256 and the previous
   receipt's hash, so removal, reorder, edit or truncation of the middle is detectable
   (`classify` reports `CORRUPT` or a `missing_matches` gap).
6. **Final commit and verification.** `campaign-result.json` is written once, after every receipt is
   sealed. A result file never implies completion. `verify_campaign` fails closed unless the
   hash-bound campaign metadata agrees with the independent one-shot ledger, exactly the frozen
   number of ordered, chained, correctly sized receipts exist on disk, and the result's scope,
   counts, receipt index and final chain equal them. Zero or negative work is refused at start.
   Supervisor exit status is zero only for a verified completion (distinct nonzero codes for
   timeout, crash, kill, worker refusal and unverifiable completion), and `status` re-verifies the
   campaign rather than trusting the recorded outcome. `launch` only reports that supervision began.
7. **State classifier.** `inspect` (read-only) returns exactly one of NOT_STARTED, COMPLETED,
   FAILED, INTERRUPTED, CRASHED_OR_KILLED, CORRUPT and lists sealed versus missing matches. Partial
   results are always flagged `partial_results_are_scientifically_usable: false`.

## What is and is not restartable (synthetic prototype)

| Situation | Outcome | Restart behaviour |
|---|---|---|
| Completed | `campaign-result.json` verified | Nothing to do; a new run is refused. |
| SIGTERM / budget stop | Terminal record and sealed prefix | Refused. The scope is consumed. |
| SIGKILL / power loss | No terminal record; sealed prefix intact; possible stray temp file | Refused. Classified `CRASHED_OR_KILLED`. |
| Torn write | Temp file never promoted | Refused. Reported as stray temp. |

The prototype deliberately contains **no resume path**. Resuming from sealed match receipts is
technically straightforward (receipts are independent per match and chained), but whether sealed
partial computation may be reused is a scientific-governance decision. See the governance
assessment. It cannot be applied to RES594, whose scorer never produced a sealed receipt.

## Performance changes worth evaluating in a future protocol (not applied anywhere)

From the synthetic benchmark (nominal scenario, CPU basis): features 22 min, inference 19 min,
metrics 11 min, JSON I/O 8 min of a ~60 min scoring path. Candidate changes, each of which would
alter code paths and therefore need fresh synthetic equivalence qualification and ratification:

- Vectorise `build_scene_feature_payload` (dictionary lookups per player-frame dominate).
- Share feature tensors across the six models of a regime (already shared) and batch several
  windows per forward call. Batch-size changes can change floating-point summation order, so any
  bitwise-equality claim would need to be re-established.
- Drop the intermediate JSONL snapshot and pre-hash: stream and digest per match.
- Run the four matches in four worker processes (one thread each). Output order and per-match
  receipts make this safe; CPU contention must be measured.

Whether any of these is needed depends on end-to-end real-data measurement, which this work did not
perform. The synthetic nominal scoring path is about one hour of CPU versus a 4 hour ceiling, a
conditional estimate only.

## Prototype limits

- Compute is a deterministic stand-in, not model inference. Resource enforcement and failure
  semantics are exercised, not model correctness.
- Sender attribution relies on Linux `sigwaitinfo`. It reports `si_pid` for signals sent by
  `kill(2)`; kernel-generated signals (for example some OOM or cgroup paths) may report PID 0, which
  is itself informative.
- Windows hosts, WSL VM suspension and container runtimes are not simulated.
