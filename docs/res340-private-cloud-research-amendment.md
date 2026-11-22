# RES340 proposed private-cloud research handling amendment

**Status: proposed; not ratified.** The owner-authorized RES338 exception covers
only its 18 final-role fits. It does not authorize RES340 source/cache staging,
training, checkpoint storage, held-out scoring, or reporting. No RES340 private
Drive tree is created or written during preparation.

## Proposed scope

This amendment would permit the owner to use the existing owner-controlled Google
Colab A100 account and an owner-only Google Drive folder for the frozen RES340
research-only LOMO campaign. It binds the v2 experiment plan
`a59fee6ee8e9fb03f4f0ccdae1933458af2bbf2375db7e6cd2bdf10962e42b62`, the v2
protocol `3d7bdc46300b966a4da274579d21ac4c8219e1ef897719d6b7a308596e9f1d9f`, the
research-only population `a8c82bfa09ac792d6c4ae779d4b28158c33ed3c2500f8548f3e94d48197f4fd1`,
the exact fit matrix in `res340-lomo-fit-matrix.json`, and the exact owner-approved
RES340 code commit.

The scope would cover only the 12 training-role folds and four validation-role
matches. The four evaluation-role matches, their files, labels, predictions, and
scores are excluded from cache staging, training, and LOMO scoring. RES501 remains
protected `NOT_QUALIFIED`. This amendment does not alter upstream data terms or
create a public redistribution right.

## Existing identities to reuse

The verified RES338 training/validation reference is
`836827a9603c6408e35d8127b9a508442b46aab7e4858a97454b3cd78499651a`. Its frozen
campaign cache manifest is
`9554e03de5ca4ab0ef6143ef8320a266dc71af368a2695030f5264d1c68886c2`; its completed
18-fit progress index is
`073a474769f1d22d3bdadeef2353eed30760ad2e5e792083a8384ea94cc7d721`. The
all-cache archive index, chunk index, and verified readback are respectively
`5bdf3a6d46ebd974279796146f8ad8a26bb35b66513a1c8e384449385c0354a7`,
`5d5a55ede46cac65cacd7d052e657493430d16d9dc927b03728453710ae83f8a`, and
`922156ca828eafe54fd2475c6c7b92080d33f881af97bbccdcbcce24cf56e0ea`. These
identities bind 16 caches, 106 chunks, and 6,687,918,080 verified bytes. RES340
must stage and verify those caches as-is. A missing or mismatched cache is a hard
stop; no feature-cache regeneration from raw source is allowed.

The freeze also binds the exact original SkillCorner source release, source
population, producer/verifier identities, and `NOT_QUALIFIED` protected status.
New raw or row-level Drive uploads are not permitted. Any local cache, checkpoint,
receipt, score, attempt history, or report must remain on the Colab VM or in the
owner-only RES340 Drive tree described below.

## Separate Drive tree

After explicit owner approval, create a new owner-only folder named
`FPD-Bench-RES340-Colab`; do not reuse or modify `FPD-Bench-RES338-Colab`.

```text
FPD-Bench-RES340-Colab/
  amendments/
  identity-manifests/
  fold-manifests/
  frozen-configurations/
  cache-references/
  runtime-manifests/
  checkpoints/                 # content-addressed, one per LOMO fit
  receipts/                    # fit receipts and content-addressed attempt history
  progress-indexes/            # immutable hash-linked progress versions
  fold-scoped-evaluation/      # held-out scores, only after scoring GO
  resource-ledgers/
  final-private-reports/
```

Before any write, verify that the root and every child are owner-only (`shared =
false`) and record the actual Drive folder ID in the approval record. Never create
public or link-shared files. Use the existing verified 64 MiB chunk transfer and
readback process for large cache archives. Every new checkpoint, receipt,
progress index, score, and final report must be content-addressed and read back
before it is marked verified. Before each Colab job, stage the latest verified
progress-index version with its hash. The worker compares its next fit and attempt
against the local LOMO ledger before it starts. After each fit, persist the
content-addressed campaign ledger version and attempt history in addition to the
selected checkpoint and receipt. Read all of them back before marking the progress
entry complete. If the Colab VM is lost, restore the last verified campaign ledger
and all completed run receipts/checkpoints named by the progress index before
resuming.

## Data separation and retention

- Training receives only its 11 training caches. The fold's held-out training
  cache is omitted from that worker's input map. Checkpoint selection receives the
  four validation caches only.
- LOMO scores are stored separately from validation history and checkpoint
  selection. No held-out errors may stop, select, tune, or rerun a fit.
- Evaluation-role matches never enter these workers or their caches.
- Do not upload raw source or row-level material to Drive or GitHub. The existing
  RES338 cache objects remain unchanged and are read-only inputs.
- Retain every fit attempt, retry classification, resource snapshot, failure,
  missing fit ID, and score result. Do not drop failures to produce a complete
  looking aggregate.
- Public GitHub content is limited to code, public protocol identities, source
  references, non-sensitive hashes, and aggregate resource calculations. No
  checkpoints, private cache artifacts, predictions, truth arrays, per-match
  metrics, or match-level result files may enter GitHub.

## Required owner authorization record

The separate execution authorization must be owner-supplied after review. It must
bind the approved GPU and private-cloud amendment hashes, exact PR/merge code SHA,
fit-matrix SHA, RES338 cache manifest and completed progress-index SHAs, cache
archive/chunk/readback SHAs, owner-only Drive root ID, current compute-unit balance
and A100 rate, and the fixed 2,400 CU spend cap. It must explicitly state
`evaluation_role_access: false` and `heldout_scoring: false`.

The separate scoring authorization must be issued only after the exact 234
checkpoint manifests (18 final plus 216 LOMO) are frozen and readback verified. It
must bind those manifests and permit only fold-scoped LOMO scoring on the matching
held-out training match. Evaluation-role scoring remains a separate gate.
