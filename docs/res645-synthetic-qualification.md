# RES645 source/checkpoint integration — synthetic engineering qualification

This change implements the RES645 source-streaming and frozen-checkpoint contracts on the
RES643 executor. Its evidence uses invented tracking rows, artificial untrained CPU weights
and a separate synthetic ledger namespace. It does not authorize a private preflight or an
evaluation. Gate 4 remains an owner decision after independent review; RES646 holds the
separate later decisions.

## Scope and frozen identities

The base is `1f04b16b7a9b56a61034791e5a0fdde3e0d1c6c7`, on the existing
`codex/res645-source-checkpoint-integration` branch. Existing interrupted changes were retained.
The ratified RES635 JSON is unchanged, including its historical `PROPOSED_UNRATIFIED` field.

| Authority | SHA-256 |
| --- | --- |
| RES635 protocol | `ac931391ecb0afcb68974e1765f65fbff17071ade2bcaab93bdadd22f84a0305` |
| RES593 checkpoint manifest | `770f1d9bbca3020237992181a56e4f5be4adaae7aab07f5f1313aa699d8693e0` |
| Research admission | `a8c82bfa09ac792d6c4ae779d4b28158c33ed3c2500f8548f3e94d48197f4fd1` |
| Permanently consumed RES594 scope | `d359751e969767f30ed6e90c65b13d0eec49f11c9e33e1d2319b19530d28f2e0` |

The scientific matrix remains 3 information regimes × 2 representations × 3 seeds, four
frozen evaluation-role identities (1874553, 1925299, 2006229, 2010085), 25 history intervals
plus origin and 15 future samples at 0.2 seconds. No frozen protocol or authority bytes changed.
Conditional realized-future channels remain conditional descriptions, not ex-ante forecasts.
RES594 remains canceled and its old private snapshot stays out of bounds; RES501 remains
NOT_QUALIFIED, LOMO deferred, and RES440 blocked.

## Implementation and independent checks

`res645_source_stream` uses the common public canonicalizer and eligibility contract. It performs
a source identity/drift pass followed by a bounded 41-sample window pass, checks every ordered
origin against the locked population, and preserves physical truth, masks and provider flags.
The synthetic entry point refuses real evaluation IDs, historical paths and unmarked inputs;
frozen source mode raises before opening data. Invented fixtures use pinned-release training-role
IDs solely because the public canonicalizer requires release membership. They contain no provider
research rows. Every emitted scene still has the evaluation role in the synthetic namespace.

`res645_checkpoints` requires exactly 18 cells, complete manifest/fit-receipt bindings, selected
steps, configuration hashes and checkpoint hashes. It reads the hashed bytes once for tensors-only
CPU loading, checks keys/shapes/dtypes/finite values, refuses alias paths and optimizer state, and
checks that weights and evaluation mode remain unchanged. All exercised weights and receipts are
artificial. The packaged public manifest is used only as a frozen identity reference.

`res645_independent` reconstructs windows from raw JSONL, independently decides membership before
comparing the lock, constructs feature tensors separately, and computes metrics with separate
NumPy arithmetic. It uses no production canonicalizer, eligibility diagnostic, feature builder,
checkpoint loader or scoring accumulator. Independent raw eligibility covers support, periods,
timestamps, continuous phase coverage, active-player minima, coordinate bounds and ball coverage.
Warning-only extrapolation and partial coordinates retain their frozen meaning. Public window
identity construction and the network class are shared. The independent verifier is a synthetic
engineering oracle; it does not provide a real-input authorization boundary.

The complete campaign produces four sealed receipts and 72 match-cell records. For every
information regime the report checks raw-derived feature tensors exactly against the public
feature path, then compares independent ADE, FDE and scalar-coordinate XY RMSE. RMSE divides
squared XY error by `2 * N_masked_player_steps`. Scene means precede window means, seed means
are within match, and matches have equal weight. A separate array calculation checks all four
paired C1/C2 contrasts. These values measure invented fixtures, not model quality on football data.

## Execution and failure contract

The existing detached supervisor drives either the RES643 generator or the RES645 fixture
workload. A stable owner-private ledger binds source, code, runtime, scope and receipt seals.
`status` independently verifies a completed bundle; its ledger flag alone cannot establish success.
CPU/wall budgets are cumulative, disk and RSS are monitored, and verification is charged too.

Cgroup-v2 `oom_kill` counters identify no victim PID. An increase concurrent with worker SIGKILL
is diagnostic only and **always fails permanently**. No trusted victim-specific host channel is
implemented. SIGKILL, supervisor loss, host reboot and unattributed failures cannot authorize a
continuation. The supported continuation is the existing predeclared supervisor timeout with
sender-verified SIGTERM, an intact sealed boundary, no scientific failure or outcome access,
sufficient remaining cumulative budget, and at most one continuation. Production-path receipts
are compared byte-for-byte with an uninterrupted artificial campaign.

Adversarial tests exercise forged membership, role/identity changes, missing final targets,
mask/truth forgery, repeated or reordered windows, future-channel leakage, representation
reconstruction, checkpoint substitutions/configurations, fit-receipt corruption, model mutation,
symlinks/hard links, naked SIGKILL, unrelated shared-cgroup OOM activity, forged attestations,
receipt removal/tampering, repeated continuation, budget exhaustion and supervisor death.
No real OOM, reboot, real authorization record or evaluation-scope consumption is simulated as
having been qualified.

## Reproduction and evidence

Use Python 3.12 with the locked development/research dependencies (`uv sync --locked --all-groups`).
The existing runtime-attestation tests also require the public PR #25 package pinned in
`.github/workflows/ci.yml`; use the workflow's extraction and runtime capture steps locally.
The qualification report generator requires passing JUnit evidence, preserving individual fault
case names, durations and the source XML hash:

```sh
uv run pytest --junitxml=/tmp/res645-tests.xml
uv run python tools/res645_qualification.py report --pytest-junit /tmp/res645-tests.xml
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run fpdbench validate-naming
uv run fpdbench validate
uv run fpdbench evidence validate
uv run fpdbench reproducibility check
uv build
uv run python tools/wheel_smoke.py dist/*.whl dist/*.tar.gz
uv run python tools/res643_package_smoke.py dist/*.whl dist/*.tar.gz
uv run python tools/res645_package_smoke.py dist/*.whl dist/*.tar.gz
```

The adjacent machine-readable report records exact implementation/runtime hashes, the 72-record
independent matrix and contrasts, source/mask/truth identities, feature parity counts, sealed
receipt hashes, CPU/wall/RSS/disk measurements, and increasing-stream memory results. Traced
allocations start after fixture generation and model loading; process high-water RSS includes
those costs. Temporary artificial inputs are deleted after measurement. Stream sizes bound only
the tested workload, not a full private match. Code hashes are the measurement authority; the
report is committed afterward, so its measurement HEAD precedes the documentation commit.

The local validation environments reuse the installed locked dependencies. The uv-managed
relocatable Python could not create copied-interpreter virtual environments (missing `libpython`).
System Python 3.12 passes packaging, but its symlinked standard library is correctly refused by
runtime attestation. Whole-suite validation therefore uses a separate local copy of system Python
with dereferenced standard-library files and its local extension-directory configuration relocated.
Both runtime capture and copied-interpreter virtual-environment creation pass there. Hosted CI
uses the workflow's setup-python environment. No security check, dependency or project configuration
was changed to accommodate the local environment.

The source/checkpoint gate passed 87 tests and the execution/RES643 gate passed 55 tests before
their respective commits. The final suite contains 1,083 tests; exact-head whole-suite and hosted
workflow outcomes are recorded on the draft PR and in RES645. The report's JUnit inventory covers
the 55 execution and fault-injection tests. Ruff, strict Pyright, naming, registry, evidence and
reproducibility checks, plus all three isolated package smoke tools, are required for final readiness.

Private source, actual frozen checkpoint bytes, real held-out inference, real host OOM/reboot,
training, LOMO and paid compute were not accessed or executed. Synthetic parity is not full
real-data qualification. No Gate 5/6 approval or Gate 6 GO is issued by this change.
