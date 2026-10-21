# Protected source adapter — synthetic delivery

Status: **READY_FOR_INDEPENDENT_SOURCE_ADAPTER_REVIEW / NOT_QUALIFIED**.
This implements source preparation, not protected population execution. No real
SkillCorner files were opened, acquired, normalized or qualified for this delivery.
No population qualification token is created. Empirical execution remains blocked.

## Integration preflight

Canonical checkout: `/home/litju/football-performance-dynamics-bench`.
Clean isolated WSL worktree:
`/home/litju/football-performance-dynamics-bench-res501-adapter`.
Local platform: Linux `6.18.33.2-microsoft-standard-WSL2`, CPython 3.14.5.

GitHub API and `git ls-remote` both matched these exact open draft heads:

| PR | Pinned head |
| --- | --- |
| #18 | `10014dcd5821faae8aa402abf4fc2022f1e14ea0` |
| #19 | `666578e0d4e6475724755ab38e8c4c565e0eadf2` |
| #20 | `6644dba8c945ca86be72b54792db30cbe488e5d0` |
| #21 | `ef1a22583cdd52bb63509a13bfc480a313ea69d4` |

Rehearsed #18 → #19 → #20 → #21 from official main
`c38218e76a9dff72a127ba57ca8b4354cadc06de`, ending at rehearsal commit
`986e54f`. No merge conflicts; inspected the automatic wheel-smoke combination
and retained both producer and independent verifier checks. Existing PRs, refs,
thread states and main were not changed. The new draft targets a separate
integration rehearsal branch at this rehearsal commit so the adapter
has a focused review diff. That base is an integration experiment, not approved main.

Main branch protection was inspected: strict `quality` and
`public-reproducibility` checks, admin enforcement, no force pushes/deletions,
zero required approving reviews, conversation resolution not required by GitHub.
The owner/handoff review gates still apply; scoped COMMENT acceptance is not an
APPROVE event. All 20 scientific JSON files (16 package authorities and four
benchmark locks/snapshot) remain byte-identical to #19.

### Six unresolved #19 review threads

All six remain unresolved on GitHub; no thread was marked resolved by this task.
The following is code/test disposition evidence for owner review, not a substitute
for deliberate thread resolution or independent review.

| Thread suffix / location | Finding | Current evidence |
| --- | --- | --- |
| `6tw2rn`, outdated | Wrong 24/16 or 26/14 horizon | Exact `(25, 15)` guard; `test_v2_rejects_changed_horizon_even_when_support_total_is_41`. |
| `6tw2rp`, outdated | Twenty observations mistaken for exhaustive source qualification | Scan returns diagnostics; empirical gate still rejects unverified counts/objects. Protected adapter adds byte and raw-even/retained identity checks but no membership authorization. |
| `6tw2rr`, current | Empty matches and resealed truth/masks | AT-07 `test_at07_structural_manifests_cannot_be_promoted_to_res501_qualification`: empty/all-empty, truth/mask/candidate changes and injected receipts cannot authorize empirical results. Structural validity deliberately remains distinct from qualification. |
| `6tw2rs`, outdated | Unapproved detection-origin exclusion | Removed from frozen successor authority; `test_v2_false_detection_at_origin_keeps_finite_xy_eligible`; global null-flag/finite-XY sentinel remains. |
| `6uHul0`, current | Public v2 evaluator unusable for diagnostics | Exported `diagnose_skillcorner_window_v2`; `test_public_v2_diagnostic_is_distinct_and_always_unqualified`; empirical gate remains closed. |
| `6uHul6`, current | Missing-slot possession denominator | Missing/invalid/unknown categories reconcile over 41; `test_v2_possession_distinguishes_missing_slots_and_observed_unknowns` and invalid-support reconciliation cases. |

## Frozen artifact compatibility

`uv run python tools/rehearse_population_artifacts.py` builds the exact #20 and
#21 revisions into separate wheels and installs them in separate temporary Python
environments. Workers run with `python -I` from an empty external directory; they
exchange only synthetic source and wire artifact bytes. The existing independently
authored verifier fixture supplies inputs; no production expected answers are
invented by the harness.

Observed: **RECONCILED**, 60 candidates; altered/self-rehashed, mixed-package and
unpinned-revision controls rejected. Both results remain NOT_QUALIFIED.

| Artifact | Wheel SHA-256 in this rehearsal |
| --- | --- |
| Producer #20 | `e98f7afa72490cc3edcb17a6f5a908e9f9a3998e859da1f542cc8ed6ce0100fa` |
| Verifier #21 | `8d6a475d3726738065a118f33b9ddd1228dad761000d584182f6f0046a98fd2e` |

Build-container hashes can vary with build tooling; the reviewed 79-file producer
package contract remains exactly
`153bc67c532b8eddba90a98994d60f656526e71961f17c9d1f2454a72dd2e1a4`.
Its verifier pin was not edited. Integrated wheel smoke explicitly verifies that
the combined package cannot authenticate as that producer. The integrated wheel
includes the source adapter but must never be substituted for the frozen producer.

## Source snapshot contract

Module: `fpdbench.data_sources.protected_skillcorner`.
`source_preflight(source, destination)` accepts an already staged, user-owned
snapshot outside **every** Git worktree, not an upstream working checkout. It does
not fetch or copy restricted sources. A later rights-authorized acquisition stage
must export only the exact 81 files, preserve resolved LFS bytes, and use private
permissions. An arbitrary revision label or local Git HEAD is not trusted: the
adapter pins the entire existing source-authority file SHA-256, its revision
`4340d274572876239c154c90bc507a9b3250a656`, each ordinary Git blob/size, raw SHA-256
where present, and all 20 LFS payload SHA-256/size identities. It reconstructs each
canonical LFS pointer and verifies its pinned Git blob identity; pointer text is
never accepted in place of the payload. This avoids placing protected receipts
or the staged source in a Git checkout. Missing, extra, duplicate-authority and
unsafe paths fail closed.

Tracking verification uses 1 MiB chunks; JSONL reads are limited to 1 MiB per row.
Metadata/phase documents have a hard 16 MiB bound. Exceeding a bound fails rather
than truncating. No complete tracking payload, match or population is buffered.
Raw even-frame count and ordered frame-ID digest are computed independently of
the streaming **v2** canonicalizer, then compared with its retained output. Raw
tracking hashes must match the initial byte inventory. Metadata and phase inputs
are checked against the same inventory before use; all 81 files are reverified
before writing a completion receipt.

Pass one finishes the global nullable-ball drift scan across all 20 sources.
Only then does pass two normalize phase CSVs. No membership or truth construction
is implemented or callable through this adapter. A future protected executor must
use the authenticated complete source scan and repeat immutable input validation
before constructing either. Normalization maps integer `frame_start/frame_end` to
half-open metadata period bounds, requires a unique containing period, checks a
supplied period and duration, rejects duplicate headers/ragged rows/parse errors,
and sorts by period/start/end. Overlapping opposing-team annotations and duplicate
interval multiplicity are preserved; gaps are never filled or called dead ball.
Receipt lineage binds raw CSV, metadata and normalized byte SHA-256 separately.

## POSIX and recovery evidence

PR #16 `d1978a55dfda9894767fc96e643adbf08f078bbb` was read for security logic only.
Its no-symlink, private-directory, source/output separation and exclusive-write
principles are retained. Its v1 canonicalizer and whole-payload reader were not
copied. The adapter strengthens these checks with directory descriptors,
component-wise `O_NOFOLLOW`, checked owner/mode/type, no hardlinked source files,
nonblocking opens (FIFOs cannot hang), safe ancestors, sanitized Git discovery,
Windows/network filesystem rejection, lexical and inode-based root separation,
and an exact bounded inventory walk.

All source directories must be user-owned 0700 and files regular user-owned 0600.
Receipt files are exclusive 0600 creations, flushed and fsynced; existing files
are never replaced. A fresh output directory is mandatory. `started.json` marks
an attempt INCOMPLETE; failures leave only protected partial evidence plus a
best-effort generic failure marker. A final `source-preflight.json` is written
last, with SOURCE_PREFLIGHT and NOT_QUALIFIED. Consumers must require that final
receipt and authenticate it; partial phase files are never completion evidence.
Recovery uses a new empty directory, preserving the failed attempt. Errors during
processing and emergency writes surface generic text, not source rows or traces.

Permissions protect against other users, not a compromised owner/root. Exclusive
creation is not a filesystem immutable flag. Signed receipt verification detects
post-signature edits; later execution must recheck its source snapshot. No test
or receipt claims resistance to a hostile kernel or compromised reviewer key.

## Independent, versioned provenance

The adapter introduces `fpdbench.protected-source-preflight` **1.0.0**, separate
from the frozen producer fingerprint contract. Its receipt contains an ordered
inventory of the installed adapter package's Python/JSON contents, the pinned
source-authority digest/revision, all 81 source digests, retained-frame evidence
and normalization lineage. A self-hash is deliberately insufficient.

An independent reviewer must inspect the evidence, pin the reviewed package
inventory digest and a trusted SSH allowed-signers file **outside the receipt**,
and sign the exact receipt bytes using namespace `fpdbench-res501-source-v1` and
principal `res501-source`. `authenticate_receipt` requires that detached signature,
the independently provisioned signer-file digest and reviewed package-inventory
digest; it rejects wrong signatures, edited receipts, untrusted signers, package
drift and wrong schema/revision/status. Trust/signature files use the same private
storage controls and are snapshotted before verification. No private signing key
is generated, stored or used by production adapter code. Tests use ephemeral
synthetic Ed25519 keys only.

**Provenance blocker:** no production reviewer trust anchor or independent approval
of this new contract/package inventory exists yet. Authenticating a source receipt
would prove only source-preflight provenance, never population qualification. The
frozen producer/verifier interfaces remain synthetic-only and buffer bytes; a
separately reviewed protected streaming execution contract is still required.
This delivery does not relabel protected inputs as synthetic, add a restricted
producer bypass, or infer authority from the successful synthetic key test.

## Validation

Synthetic adversarial tests cover 81-file/20-LFS checks, late global drift,
raw-even/retained coverage mismatch, between-pass and during-scan mutation,
source/receipt overlap, unsafe parents, foreign ownership, modes, symlinks,
hardlinks, FIFOs, Git and linked-worktree markers, path escapes, exclusive writes,
emergency-write failure, deterministic phase boundaries, malformed CSV/JSON,
streaming memory bounds and detached-signature/provenance failures.

Local validation: **528 pytest tests passed**, including **45 adapter cases**;
Ruff lint/format and strict Pyright passed (zero errors/warnings). Naming,
repository validation, evidence validation, reproducibility and isolated
wheel/sdist smoke passed. The CLI checks were repeated after the final guide edit. Evidence remains 232 references / 63 digests; snapshot remains
`a22f93f11cf428b7f326a93714fbcc798c99e5d0dbcab5122edb48d050b4a873`.
Final test counts, exact delivery HEAD and exact-head CI links are recorded in the
draft PR and protected-population workstream handoff comment.
