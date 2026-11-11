# RES643 synthetic scoring preparation

This implementation prepares the proposed RES635 study on invented observations and randomly initialized CPU models only. It does not ratify RES635 or complete formal Gate 4. Gate 3 owner ratification and separate Gate 4 approval remain pending. Gates 5 and 6 were not entered. RES594 remains closed; its scorer, entrypoint, scope, private snapshot and historical artifacts are unchanged.

The immutable scientific authority is `res635_post_failure_descriptive_protocol_v1.json`, SHA-256 `ac931391ecb0afcb68974e1765f65fbff17071ade2bcaab93bdadd22f84a0305`. The implementation starts from main `30d3fc279735bd06aa4265493a9627602e1580fc`.

## Synthetic execution

The installed `fpdbench-res635` entrypoint accepts generated synthetic inputs exclusively. It has no source, snapshot, checkpoint, authorization or real scope arguments. The four identities are `synthetic-match-0` through `synthetic-match-3`. Exactly 18 random model configurations use the frozen three regimes, two representations and seeds 1729, 2718 and 31415. No training, checkpoint deserialization, GPU, dataset acquisition or paid compute occurs.

Choose one stable, explicitly named owner-private ledger root and keep using it across output directories. These example paths must be new synthetic locations:

```sh
uv run fpdbench-res635 start --ledger-root /owner/synthetic-ledger --output /owner/synthetic-output --count 2 --predeclare-continuation
uv run fpdbench-res635 status --ledger-root /owner/synthetic-ledger --output /owner/synthetic-output --count 2
uv run fpdbench-res635 verify --ledger-root /owner/synthetic-ledger --output /owner/synthetic-output --count 2
```

`start` reports a detached supervisor PID, not scientific success. `status` returns nonzero until independently verified completion. `verify` performs another complete receipt and aggregate readback and reports only the synthetic status and record count. Receipts, postmortems, telemetry and keys remain in owner-private directories; intermediate metrics have no public CLI. Changing the configured ledger root would change the trust authority and is outside the one-shot guarantee.

A campaign allows 1–64 windows per artificial match. Its declared cumulative budget is 600 CPU seconds, 900 wall seconds, 2 GiB combined monitored worker/supervisor RSS and 64 MiB output storage. Worker CPU and file-size limits, sampled RSS/disk checks, and a hard wall watchdog bound execution. The supervisor charges kernel-accounted worker CPU plus its own imports and independent verification. Continuation additionally charges receipt replay and reserves 30 CPU and wall seconds per remaining match. These synthetic ceilings are stricter than the proposed real campaign's 14,400/21,600-second limits and do not authorize that campaign.

## Measurement and streaming contracts

Each generated source window contains 41 samples: 25 history intervals plus origin and 15 future observations at 0.2-second spacing. Truth, origin-relative truth and finite truth masks derive from the same source XY observations. The generator includes missing intermediate observations, absent final targets, single-scoreable-scene windows, unscoreable windows and three quality categories, including unclassified scenes.

The public frozen DeepSets feature builder, information-boundary validation and model architecture are reused. Features exclude labels and respect regime-specific future channels. Random model outputs are converted to float64 for physical reconstruction and scoring; origin-relative predictions add each player's origin before measurement. Scalar-coordinate XY RMSE uses `sqrt(sum(dx²+dy²)/(2*N))`. Equal scoreable-scene means form window scores, equal scoreable-window means form match scores, three seed scores form configuration-within-match means, and four matches receive equal weight. All four C1/C2 contrasts retain four paired match values and their equal-match mean. Horizon and quality strata do not alter primary scores.

The scorer retains a bounded window, feature/prediction panels, 18 fixed model instances and fixed-size accumulators. It retains no list of windows, predictions or window scores. Strict contiguous source order and canonical IDs detect duplicate reads with a single expected index. Streamed input and mask SHA-256 digests, scene/window denominators, masked point counts, final target counts and scalar-coordinate denominators accompany each match receipt. The synthetic trust boundary independently regenerates each invented source window to reject altered coordinates, origin panels or masks.

`tools/res643_synthetic_qualification.py` separately enumerates 51,713 invented window identities and masks without inference. Its lightweight digest covers source-frame ranges, IDs and masks; it is explicitly distinct from the full invented-XY stream digest. A test compares its mask digest and all denominators with the full generator. The measured 517 versus 51,713-window results are recorded in the companion JSON report; no evaluation snapshot is created.

## Sealing and independent verification

The worker writes one complete receipt per artificial match with all 18 cells, every stratum, denominators, source/mask identities, code/runtime/protocol provenance, scope and the previous receipt hash. Writes use owner-private temporary files, file fsync, atomic rename and directory fsync. Four ordered receipts produce exactly 72 cell-match records. Partial temporary files, missing receipts, reordered matches, duplicate cells, forged hashes, changed masks, numerical changes and provenance differences fail verification.

`res635_verification.py` uses a separate scalar public-metric calculation and separate scene/window accumulation. It independently recomputes synthetic model measurements, checks them to absolute tolerance 1e-12, and calculates seed means, equal-match means and C1/C2 from the 72 verified records. It does not trust a scorer-supplied campaign aggregate. The supervisor performs this verification before committing `result.json`, then authenticates its readback. Receipt seals and postmortem/manifest HMACs bind the private ledger authority. The owner UID and the chosen stable ledger root are the security boundary, not protection against a malicious process running as that same UID.

The independent calculator is a separate code path written within this implementation. An independent scientific reviewer, distinct from the implementer, must still review the contracts and evidence before formal qualification.

## Interruption policy

The launcher exits independently of the supervisor. The supervisor starts an isolated worker process group and records actual kernel `wait4` exit/signal and CPU information. Linux parent-death signaling kills a worker if its supervisor disappears. Termination signals are blocked before worker exec so all model-library threads inherit the mask; `sigwaitinfo` records sender PID/UID. Controlled termination allows bounded cleanup and a worker terminal record. A supervisor watchdog covers hung scoring and verification. Persistent rate-limited telemetry is fsynced. Exit codes distinguish verified success (0), resource stop (5), worker/unknown failure (6), integrity/refusal (7) and continuation-ready interruption (143).

Only a predeclared campaign may request one explicit `continue` under the same ledger scope and output. No automatic retries exist. The original supervisor must authenticate a supported timeout SIGTERM or observed worker SIGKILL, and a nonempty proper prefix of match receipts must pass independent numerical verification and byte-exact deterministic replay. Controlled SIGTERM also requires the worker terminal record with the supervisor as sender. A sudden SIGKILL does not require an impossible worker terminal record. The exclusive continuation token is durable before replay; failed validation consumes the opportunity permanently. The CLI does not expose intermediate metrics or accept outcome-dependent continuation parameters.

Unknown SIGTERM, scientific/integrity failures, missing or forged postmortems, outcome-access flags, incomplete or changed receipts, exhausted budgets and insufficient remaining budget fail permanently. Supervisor loss has no trustworthy surviving supervisor attestation and is terminal. Simulated OOM and host-loss claims without trusted host evidence are rejected; this preparation does not fabricate a host attestation service or claim actual kernel OOM/reboot qualification. There is no fallback to a new scope or output directory.

Tests compare all four scientific receipt files and independently calculated aggregate payloads byte for byte between continued and uninterrupted synthetic campaigns on the pinned runtime. Private authentication envelopes, process IDs, telemetry, elapsed resource counters and launcher paths intentionally describe the actual attempts and therefore differ.

## Acceptance boundary

The accompanying evidence records targeted and full tests, metric parity, resource accounting, independent 72-record aggregation and Git/CI identities. The DRAFT PR is reviewable and must not be merged automatically.

Remaining work before formal Gate 4 acceptance: express owner scientific ratification, separate approval of synthetic qualification, and review by a verifier independent of this implementation. Real source streaming, private checkpoint/runtime/source preflight, real-data throughput, a trusted host-level attestation service, actual OOM/reboot behavior and real learned metrics remain unqualified. No real owner authorization was created, no real execution scope was consumed, and no held-out inference was performed.

## Measured preparation evidence

The [machine-readable report](res643-synthetic-preparation-report.json) records the final 8-window-per-match synthetic campaign: 72 independently verified cell-match records, 24.1763 cumulative CPU seconds including supervisor verification, 21.3788 wall seconds, 449,413,120 bytes peak combined monitored RSS, and 80,943 bytes of output. The independent scalar calculator differed from the vectorized scorer by at most `8.881784197001252e-15` metres, below the frozen `1e-12` absolute tolerance. All receipts share the frozen protocol and exact code/runtime fingerprints in the report.

The census grew from 517 to 51,713 windows while traced peak allocation changed from 597,185 to 597,239 bytes. Peak process RSS changed from 217,874,432 to 217,628,672 bytes. The large census accounted for 103,426 directed scene slots, 73,880 scoreable scenes, 44,328 scoreable windows, 11,216,027 masked points, 747,783 final targets and 22,432,054 scalar coordinates. It used 32.7948 CPU seconds and 54.8343 wall seconds, zero model forward calls and zero snapshot bytes. These are invented mask populations, not the real census's scoreability denominators.

Reproduce the allocation comparison in separate processes:

```sh
uv run python tools/res643_synthetic_qualification.py --windows 517
uv run python tools/res643_synthetic_qualification.py --windows 51713
uv run pytest -q tests/unit/test_res643_scorer.py tests/unit/test_res643_execution.py
uv build
uv run python tools/res643_package_smoke.py dist/*.whl dist/*.tar.gz
```

The extracted wheel and sdist execute identical synthetic parity checks outside the checkout, using the installed pinned research dependencies. Their scientific receipt SHA-256 was `d78de30d9bd19734041450e2cd4c1ee56f705e2508cc3635fe00d473df20089e`. The dependency-free core wheel/sdist smoke also passed. Locally that existing smoke required system Python 3.12.3 because copied virtual-environment executables from this host's uv Python could not locate `libpython`; scientific measurements and extracted-package parity used Python 3.12.8 throughout. Hosted CI runs the standard repository smoke plus the new synthetic package check.
