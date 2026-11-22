# RES340 prospective LOMO GPU execution amendment

**Status: proposed; not ratified.** This file does not authorize private cloud staging,
real fitting, held-out scoring, payment, or use of a Colab A100. The RES338 cloud
exception remains limited to its original 18 final fits.

## Frozen identities

- Starting repository commit: `8ed800853915b5789813718469c42c73d77c7841`.
- Previous learned-model implementation: `fd06e1b15eaf8982a1bef8708f3063c965ed801d`.
- Model: `per_target_context_deepsets_mlp_v1`.
- Experiment plan: `a59fee6ee8e9fb03f4f0ccdae1933458af2bbf2375db7e6cd2bdf10962e42b62`.
- Protocol: `3d7bdc46300b966a4da274579d21ac4c8219e1ef897719d6b7a308596e9f1d9f`.
- Research-only admission: `a8c82bfa09ac792d6c4ae779d4b28158c33ed3c2500f8548f3e94d48197f4fd1`.
- RES338 training/validation reference: `836827a9603c6408e35d8127b9a508442b46aab7e4858a97454b3cd78499651a`.
- RES338 cache freeze: `9554e03de5ca4ab0ef6143ef8320a266dc71af368a2695030f5264d1c68886c2`.
- RES338 completed progress index: `073a474769f1d22d3bdadeef2353eed30760ad2e5e792083a8384ea94cc7d721`.
- RES338 all-cache archive index: `5bdf3a6d46ebd974279796146f8ad8a26bb35b66513a1c8e384449385c0354a7`.
- RES338 all-cache chunk index: `5d5a55ede46cac65cacd7d052e657493430d16d9dc927b03728453710ae83f8a`.
- RES338 verified Drive readback: `922156ca828eafe54fd2475c6c7b92080d33f881af97bbccdcbcce24cf56e0ea`.
- Frozen RES340 fit matrix canonical SHA-256: `47450802e53dc5ed03b7108fb0a9592165ee3669847f6b061212f1002a67823a`.
- The exact RES340 code commit must be included in the owner's separate execution authorization. It must be the reviewed PR head or its owner-approved merge commit.

## Experiment and runtime

The schedule is exactly 12 protocol folds × 2 target representations × 3 information
regimes × 3 seeds = 216 unique fit IDs. Each fold excludes its one held-out training
match from optimization, trains on the other 11 training matches, and uses only the
four separately frozen validation matches for checkpoint selection. The fit worker
receives only those 15 caches. The held-out match is opened only by the separate
scorer after every learned checkpoint manifest is frozen.

Each fit starts with a fresh model and the frozen seed. The model, 26-sample input
history, 15 future samples at 0.2 seconds, feature rules, masks, absolute XY and
origin-relative displacement targets, 128-128-30 head, PyTorch default Linear
initialization, AdamW settings, batch size 128, match/window/scene sampling,
masked physical ADE loss, validation cadence, earliest-checkpoint tie rule,
patience, and maximum steps remain unchanged from RES338. No final-fit checkpoint
is a warm start, and its checkpoint hash is forbidden in the LOMO worker.

The runtime is Python 3.12.8, NumPy 2.2.4, PyTorch 2.6.0+cu124, CUDA 12.4, on an
NVIDIA A100-SXM4-40GB. Use deterministic algorithms and FP32; disable TF32 and mixed
precision. The RES338 numerical qualification remains applicable because the model
and optimizer math are unchanged. The new local synthetic checks qualify fold
selection, cache access, receipt binding, scoring, and match-level aggregation. No
paid synthetic CUDA run was used during preparation.

## Resource limits and stop rules

- One active GPU worker; deterministic protocol-fold, target, regime, seed order.
- Per fit: 3,600 GPU seconds. One infrastructure-only retry may use at most 900 GPU
  seconds. Scientific, data, numerical, and OOM failures are terminal.
- LOMO fit and retry ceiling: 270 GPU hours total. Preserve the 292.5 CPU-hour,
  19.5 preparation CPU-hour, and 336 wall-hour campaign ceilings.
- Proposed fixed Colab spend cap: **2,400 compute units**. At the last observed A100
  rate of 6.73 CU/hour, the 336-hour wall ceiling is 2,261.28 CU. Adding the 68.44
  CU historical preparation/staging allowance gives 2,329.72 CU; the cap leaves
  70.28 CU for rate rounding and reconnect overhead. The cap cannot be increased
  or reallocated to new fits after results are observed.
- Before cache staging or the first fit, the owner-authorized account balance must
  cover the whole cap. Before each later fit, the live balance must cover the
  remaining fixed cap and the remaining per-fit/retry ceiling. The live A100 rate
  must equal the rate in the authorization record; otherwise stop before a fit.
- Also stop on any source/cache or configuration mismatch, missing Drive readback,
  shared Drive permission, concurrent worker, evaluation-role access, unapproved
  operation, or spend/resource ceiling.

The current account does not meet the proposed cap. The fit-only expected cost is
about 253.60 CU; the evidence-based total expected cost is about 732.52 CU. The
current verified balance and detailed cost calculation are recorded in
[`res340-lomo-compute-budget.md`](res340-lomo-compute-budget.md). No purchase or
partial launch is authorized.

Before any owner-approved `colab new --gpu A100`, run the read-only
`tools/res340_colab_gate.py` preflight. It checks the complete fixed cap and the
exact code/matrix/amendment identities and never allocates a session. After
allocation, the worker checks the live A100 rate and the same remaining budget
before cache staging and every fit. It also blocks a second A100 assignment while
another A100 session is active. Create the progress index after the pinned
runtime check but before cache staging, binding the pre-allocation balance
snapshot from the owner approval so setup/staging spend counts against the cap.
Read back the 216-fit progress index in the owner-only Drive tree before staging; upload its current
content-addressed version to the Colab VM before every job. The worker checks that
the index's next fit ID and attempt number match its internal campaign ledger.

## Cache reuse and recovery

The owner-only RES338 archive contains all 16 training/validation feature caches:
12 training and four validation, 6,687,918,080 bytes in 106 chunks. All 106 chunk
readbacks and the reassembled cache identities were verified. RES340 stages that
exact archive into its separate Colab workspace, verifies all cache and array
hashes, then removes the temporary local chunks and archives to retain the frozen
8 GiB free-disk reserve. It does not regenerate the features from raw source. If
the archive is incomplete or any identity differs, stop before fitting.

After a Colab loss, verify the session is gone, read current usage, restore the same
content-addressed cache archive, and resume the existing RES340 ledger at its
next fit ID. Do not change a fit configuration or resume model/optimizer state.
Retry only a confirmed Colab infrastructure interruption with OOM excluded, once,
from fresh seeded initialization. Preserve partial artifacts and attempt history.

## Custody and scoring boundary

The additional private-cloud scope is defined separately in
[`res340-private-cloud-research-amendment.md`](res340-private-cloud-research-amendment.md).
Its Drive tree is separate from RES338. It is not approved by this proposal. The
owner must approve both amendments and provide an owner-only Drive root before
cache staging, checkpoint, receipt, or score uploads.

Every fit receipt binds the fold, held-out match, 11 optimization matches, four
validation matches, source/cache identities, regime, representation, seed, exact
configuration, environment, selected checkpoint, and retry number. The training
worker never receives its held-out match. The scorer separately binds that match,
ordered origin/window and player-panel identities, truth/mask identity, and exact
checkpoint hash. It uses the frozen physical ADE, FDE, and XY-RMSE semantics and
does not invoke the protected-only scoring interface.

Held-out scoring remains closed until a separate owner scoring authorization is
provided after all 18 final and 216 LOMO checkpoint manifests (234 total) are
frozen. Evaluation-role matches remain outside LOMO preparation, training, and
fold scoring. RES501 remains `NOT_QUALIFIED`. C1/C2 continue to use their original
four evaluation matches and primary ADE definitions; LOMO matched differences are
descriptive only, with no significance claims from overlapping windows or folds.
