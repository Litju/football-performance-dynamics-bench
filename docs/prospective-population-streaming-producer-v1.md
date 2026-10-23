# Streaming population producer v1

**State: synthetic-only, UNQUALIFIED.** This worker is separately versioned
from the in-memory PR #20 producer. It does not authenticate a source receipt,
call the protected executor, qualify a population, or open an empirical gate.
The independent streaming verifier remains a separate implementation task.

## Inputs and pass order

streaming_population_producer_v1.produce_streaming_population_draft_v1 accepts
exactly the pinned 20 match IDs as paths to metadata JSON, complete tracking
JSONL, and already-normalized phase interval JSON. It orders matches by the
frozen 12/4/4 protocol. Metadata and phase JSON are strict UTF-8 JSON with
duplicate keys and nonfinite constants rejected. Each document is limited to
16 MiB; normalized phases are limited to 100,000 intervals. Tracking is parsed
with bounded readline calls capped at 1 MiB per row.

The first complete pass parses every match through the frozen v2 10 Hz to 5 Hz
canonicalizer and completes the nullable-ball drift scan over every retained
sample. No candidate, membership, or truth output is constructed before this
population-wide scan finishes. The worker records raw input hashes, byte sizes,
frame counts, retained-sample counts, and canonical retained-sample digests.
Detected drift writes an INCOMPLETE receipt and leaves the output marker in
place.

The construction pass parses each tracking file again. A deque retains at most
41 canonical samples. It enumerates every absolute even-frame origin in each
half-open metadata period and evaluates the exact offsets -25 through +15.
Missing origins and incomplete support stay in the diagnostic census; only
complete-support candidates enter the candidate JSONL. Eligibility, warnings,
exclusions, player ordering, truth masks, displacement arithmetic, scoreability,
and digests use the frozen v2 helpers and constants.

After construction, a third streaming hash pass checks all input files against
the first-pass snapshots. A mutation, malformed row, interrupted write, or
artifact digest mismatch leaves INCOMPLETE present and no usable success
receipt. A complete run writes an UNQUALIFIED receipt only after all artifacts
have been flushed and checked.

## Bounded storage

The worker holds one match's bounded metadata and phase documents, no more than
41 canonical samples, one candidate/window and its scene truth at a time, and
fixed 20-match receipt/count summaries. Candidate rows, diagnostic rows, truth
rows, and match membership are written as they are produced. The potentially
large manifest matches/windows array is spooled to a private file and copied
in chunks into the canonical manifest. The manifest self-digest is patched into
a fixed-width placeholder. Receipt JSON is emitted with the standard-library
incremental JSON encoder.

Input paths must be absolute and have no symlinked path components. Inputs and
outputs use separate directory trees. The output directory must be a new
absolute Linux path outside a Git worktree and /mnt. Its parent path is opened
component by component without following symlinks; ancestors must be root or
current-user owned and cannot be shared-writable except for root-owned sticky
directories such as /tmp. The new directory is created relative to that open
parent descriptor, then checked as current-user owned with mode 0700. Output
operations remain anchored to its open directory descriptor. Artifact files
are exclusively created, set to mode 0600, and checked for ownership and mode.
The worker hashes output streams, calls fsync on files and the directory, and
keeps INCOMPLETE until the receipt has been written and synced. A failed output
directory is never reused.

The receipt records the directory's filesystem type from its open descriptor,
but labels storage as `SYNTHETIC_ONLY_NOT_TRUSTED_FOR_PROTECTED_DATA` on every
filesystem. These permissions and path checks do not authenticate protected
inputs or establish production trusted storage. The synthetic CI temporary
filesystem is not a protected-storage qualification. Any future protected
executor needs a distinct reviewed storage gate that verifies its approved
mount identity and filesystem policy before it can route protected inputs.

The test suite measures Python peak allocations and peak process RSS in separate
worker processes without loading full output artifacts into those workers. It
scans **1,720 to 17,200 tracking rows** (10×), enumerates **60 to 1,300
candidate origins**, and writes **7,748,751 to 38,746,237 output bytes**. Peak
Python allocations are **17,390,409 to 17,512,598 bytes**; peak process RSS is
**48,492,544 bytes for both runs**. The larger input contains period-null
synthetic rows beyond its bounded candidate period to increase source scanning
without expanding the candidate time range. This is not a real-source resource
certification or a complete RSS/runtime attestation.

## Identity and parity

The receipt identifies
res544-streaming-population-producer/1.0.0 with a separately versioned
source-package identity. Its inventory covers the worker module, its enumerated
scientific helper sources, and frozen v2 authorities. The identity explicitly
states executable_runtime_attestation: NOT_PROVIDED; it does not authenticate
bytecode, Python, installed dependencies, or the complete runtime. Historical
PR #20/#21 fingerprints remain provenance only and are not reused as this
worker's executable identity.

The bound scientific authorities remain unchanged:

| Authority | SHA-256 |
| --- | --- |
| Source release | e92c417b7640b27399451134ee3fce4b1961b0c0dfc2e01175a8f3c906a9ae07 |
| Source population | e9054b7ddc2dfeff4dd8425ea61a23ed0b326076a08899e47502484228fdbdf4 |
| Measurement v2 | 1ecf355b3e6e2f04967e8363c1fdecc7f40707a7dda9966ebee1b3d90e97e671 |
| Eligibility v2 | ed1cdc20ca7a93040fd4aabc91655819c5c4b8c58021c6540c6aaea325dafa11 |
| Protocol v2 | 3d7bdc46300b966a4da274579d21ac4c8219e1ef897719d6b7a308596e9f1d9f |
| Plan v2 | a59fee6ee8e9fb03f4f0ccdae1933458af2bbf2375db7e6cd2bdf10962e42b62 |
| Population schema bytes | 27da86b7355c311a65c68ab9b2bd3ae86e27779ed48641c23181ffe2f9adc224 |
| Result schema bytes | d0d7dbf4a14cade66d1e0ce7282441d8f035a68de8a192ad8e4d70210be18f7f |

Synthetic tests compare the manifest, candidates JSONL, diagnostic census
JSONL, and truth JSONL byte for byte against the unchanged historical producer.
The complete 10 Hz case retains exactly **43 samples from 86 source rows** per
match and produces identical scientific artifacts. New worker provenance is
expected to differ explicitly in the receipt.

Adversarial tests cover missing matches, odd and even frames, sparse support,
period boundaries, missing origins, 39-of-41 and 38-of-41 eligibility,
warnings, nonzero displacement anchors, truth masks, incomplete populations,
malformed and duplicate-key JSON, nonfinite and unsupported records, late
nullable-ball drift outside every candidate support, source mutation after the
scan, interrupted writes, corrupted artifacts, exclusive output creation,
symlinked input/output ancestors, shared-writable output parents, input/output
tree separation, and increased frame/candidate/output volume.

## Remaining blockers

- No independent streaming verifier exists for this worker. Synthetic parity
  and producer-generated hashes are not independent verification.
- The existing source-only adapter inventory does not authenticate executed
  bytecode or the complete runtime. A separately controlled pre-import runtime
  and dependency attestation is still required.
- No external root-signed trust policy or independent reviewer keys are
  provisioned.
- No real SkillCorner input was read or processed. This worker's successful
  receipt remains UNQUALIFIED; no qualification PASS, training, scoring,
  or empirical gate activation is possible.
