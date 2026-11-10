# RES614 incident report: the 2026-11-07 RES594 termination (exit 143)

**Disposition: `SIGTERM_CAUSE_UNDETERMINED`.** The sender of SIGTERM is not identifiable from any
retained log. Several candidate causes are excluded by direct evidence; one candidate class (the
agent runner that hosted the process) remains the leading but unproven hypothesis.

Scope: execution metadata and logs only. The retained private snapshot was examined with
`stat(2)` metadata only. It was not opened, read, hashed, copied or parsed. No checkpoint,
prediction, label or protected source was read, and the original campaign directory and
authorization ledger were left unchanged (the directory still lists exactly `.started.json` and
`evaluation-input.private.jsonl`). Evidence hashes are in `docs/res614/incident_evidence_index.json`.
All times are UTC.

## Demonstrated facts

| Time (UTC) | Fact | Source |
|---|---|---|
| 05:04:35 | Scorer started by the agent runner as `exec_command` (`yield_time_ms=1000`) under `/bin/bash -lc`, then polled every 30 s with `write_stdin`. No `nohup`, `setsid`, `systemd-run`, `timeout` or `trap`. | E1 |
| 05:04:46.54 | Authorization consumed and `.started.json` written | E6 |
| 05:07:09.75 | Snapshot file created (about 2.4 min of model loading, source verification and producer digesting) | E7 |
| 05:16:37.76 | Last write to the snapshot (about 9.5 min of materialisation). The directory has no later entry. | E7 |
| 05:16:38.49 | First read of the snapshot, 0.73 s after the last write (atime under `relatime`) | E7 |
| 05:35:03.44 | `ps` shows PID 770696 alive: elapsed 30:27, CPU 00:29:54, RSS 167,636 KiB, 98.1% CPU, state `Rsl` | E1 |
| 05:35:25.28 | The exec session reports exit code 143, duration 1,849.32 s | E1 |
| 05:35:56 | `ps` shows PID 770696 gone | E1 |

The figures previously quoted as "CPU 29m54s, wall 30m27s, about 05:33/05:35" are the 05:35:03
sample, which was up to 22 s before the process ended. The process was alive for 1,827 s at that
sample and the session ended at 1,849.3 s. Neither is 1,800 s. The agent's remark at 05:35:51 that
"the scorer process is still alive" reflected that stale sample; by then it was gone.

## The five questions

**1. Who or what issued SIGTERM?** Not identifiable. Exit code 143 shows the hosting session
ended with SIGTERM semantics; it does not name a sender. Python without a signal handler records
nothing, the frozen scorer contains no signal handling at all (`grep -c signal` returns 0), and the
runner's own logs have no kill, terminate or prune record for that thread (E2).

**2. Does ~30 min correspond to an execution or tool limit?** No evidence for it, and evidence
against. Across 47,510 recorded runner command executions since 2026-09-24, 21 sessions that ran at
least 1,800 s exited 0, the longest at 11,679 s, and seven did so between 2026-11-04 and 2026-11-07
(1,820 to 6,036 s). Exit 143 occurs 82 times at durations from 21 s to 19,068 s, with no common
threshold, often in same-second batches. Also, the process was still running at 1,827 s, after any
1,800 s limit should have fired. A hidden limit that is not 1,800 s cannot be excluded, but nothing
supports it.

**3. Was the scorer still preparing the input?** No, with high confidence. The snapshot stopped
growing at 05:16:37.76 and was first read 0.73 s later. In the frozen code the only reader is the
scorer's own SHA-256 readback (`_secure_sha256`, line 2562), which follows materialisation. The run
therefore spent about 18.8 min after materialisation in hashing, rereading and scoring. The
synthetic projection (performance report) puts the scoring path at roughly 32 - 64 min, so the run
was probably between 30% and 59% through scoring. This is inference; scoring progress is not
observable.

**4. Did an OS, container, resource policy or the scorer's own limits cause it?** Excluded:
- *OOM*: RSS was 164 MiB of a 20 GB VM, the kernel log has no OOM event, and an OOM kill is
  SIGKILL (137), not 143.
- *WSL VM restart or shutdown*: `last -x` shows no boot after 2026-11-05 01:20:27; kernel log has no
  shutdown, panic or Hyper-V event in 05:00 - 05:45; the runner's app-server process kept one
  `process_uuid` through the window.
- *Scorer ceilings* (CPU 14,400 s, wall 21,600 s, RSS 8 GiB): not reached, and a breach raises an
  exception that would have written `.failed.json`.
- *`RLIMIT_CPU`*: would deliver SIGXCPU (exit 152), not SIGTERM.
- *Agent or user kill*: the rollout contains no kill command, and no user turn occurred between
  launch and exit; the same agent turn continued afterwards.
- *Concurrent-session pruning*: only one live exec session existed in that thread.
Not excluded: the runner or app-server ending its own child session (for reasons unrecorded), or
another process on the host sending SIGTERM. The WSL guest clock was being stepped around 04:00 -
04:30 and at 05:17:06; no causal link to the signal was found.

**5. Why was there no committed result or failure receipt?** This follows from the frozen code
path, independent of the cause. `.failed.json` is written only in an `except BaseException` block
(lines 2584 - 2590), which runs for Python exceptions. SIGTERM with the default disposition ends the
interpreter without running it, so no failure marker was written and the snapshot cleanup in the
same block (line 2587) also did not run. That is why the 6.8 GB snapshot survived. The 72 result
records and `campaign-result.json` are produced only after the entire snapshot has been scored
(lines 2447 - 2512), so every window computed in memory was lost with the process. There is no
per-match receipt anywhere in the design. This is an execution-architecture loss, not a scientific
or metric failure.

## Root-cause confidence matrix

| Hypothesis | Verdict | Basis |
|---|---|---|
| Runner/app-server ended its child session for an unrecorded reason | Leading, unproven | Process was a direct child of the runner session; 143 is common in that environment; nothing else fits |
| Fixed 30-minute command or session TTL | Not supported | 21 longer sessions completed; death at 1,849 s with the process alive at 1,827 s |
| OOM kill | Excluded | RSS, kernel log, signal number |
| WSL VM or host shutdown | Excluded | `last -x`, kernel log, app-server continuity |
| Scorer resource ceiling | Excluded | Not reached; would write `.failed.json` |
| Agent-issued kill | Excluded | No kill command, no user turn |
| User interrupt in the terminal | Unlikely | The same turn continued; a turn abort was not recorded |
| Other host process sent SIGTERM | Not excluded | No process accounting or auditd records |

## Limits of this forensics

No auditd or process accounting, systemd journal retention before 2026-11-09, runner-side signal
logs or stderr capture existed. The execution worktree `/tmp/fpdbench-res594-exec-7acc2c4` has been
removed. The runner's log level may not record a kill. Absence of a log row is therefore weak
evidence. The sender could only have been established by a process that recorded signal origin when
it was received, which is what the RES614 resilient-runner prototype does.

## Prioritised engineering changes

1. *Process/session defect*: detached supervision in its own session, recorded outcome, signal
   sender attribution, bounded graceful shutdown (demonstrated on synthetic units).
2. *Loss of outputs on interruption*: per-match sealed, hash-chained receipts with fsync and atomic
   rename; fsynced progress telemetry; snapshot-free streaming.
3. *Governance*: a new, separately ratified protocol and fresh owner approvals for any further
   real-data scoring. See `docs/res614-runtime-audit-and-governance.md`.
