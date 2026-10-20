# Independent prospective population verifier v2

This module independently derives synthetic expected results for the frozen
SkillCorner v2 population contract, then compares five producer wire payloads:
the manifest, candidate JSONL, diagnostic census JSONL, truth JSONL, and receipt.
It is a review tool. Its reports always carry `authoritative: false` and
`qualification_status: NOT_QUALIFIED`; reconciliation cannot open an empirical
gate.

## Frozen inputs

The verifier reads the source, measurement, eligibility, protocol, plan, and
population/result schema JSON files directly. It checks their pinned hashes
before processing inputs. The source population is exactly these 20 IDs:

`1874553, 1886347, 1899585, 1925299, 1927964, 1953632, 1959846, 1986691,
1996435, 1996436, 2006229, 2006363, 2007448, 2007721, 2010085, 2011166,
2013725, 2015213, 2016236, 2017461`.

It recomputes role ranking from SHA-256 of
`FPDBench prospective/v1/match/<decimal match_id>`, assigns 12/4/4, sorts IDs
within each role, and rejects a mismatch with the protocol's frozen role lists.
The active authority hashes are source release
`e92c417b7640b27399451134ee3fce4b1961b0c0dfc2e01175a8f3c906a9ae07`, source
population `e9054b7ddc2dfeff4dd8425ea61a23ed0b326076a08899e47502484228fdbdf4`,
measurement `1ecf355b3e6e2f04967e8363c1fdecc7f40707a7dda9966ebee1b3d90e97e671`,
eligibility `ed1cdc20ca7a93040fd4aabc91655819c5c4b8c58021c6540c6aaea325dafa11`,
protocol `3d7bdc46300b966a4da274579d21ac4c8219e1ef897719d6b7a308596e9f1d9f`,
and plan `a59fee6ee8e9fb03f4f0ccdae1933458af2bbf2375db7e6cd2bdf10962e42b62`.

## Independent derivation

`MatchSourceBytesV2` accepts in-memory match metadata JSON, raw tracking JSONL,
and normalized phase-interval JSON. Parsing rejects duplicate JSON keys, invalid
UTF-8, non-finite numbers, malformed timestamps, duplicate/non-monotonic source
frames, and any raw 10 Hz frame whose top-level keys differ from the frozen source
schema. It checks nested player, ball, and possession fields only on retained even
frames. Retained player fields must be exact, IDs unique, and every observed ID
present in the match roster. Sampling selects absolute even source frames only and
assigns `canonical_sample_index = frame // 2`; period changes do not reset parity
or the canonical index.
Each match's retained-sample digest is SHA-256 over the canonical compact JSON
array of its independently reconstructed retained sample records in source order.

The complete diagnostic census enumerates every even source-frame grid slot in
each half-open metadata period. Protocol candidates are the subset with an observed
origin and all 41 expected canonical sample positions present. The eligibility
rules then use the fixed offsets -25 through +15, 39/41 finite ball XY coverage,
finite origin ball XY, seven finite players per team per support sample, verified
period bounds, continuous positive phase coverage across every 10 Hz frame in the
support span, and the frozen coordinate, temporal, warning, and quality rules.
Every census slot receives its own independently calculated diagnostic, including
missing-source support slots; only complete-support rows enter candidate membership.
The null-detection/finite-ball-XY scan covers every retained sample in every input
before candidate enumeration. Any occurrence returns `STOPPED` with
`BALL_NULL_FLAG_WITH_FINITE_XY_UNAPPROVED` and no candidate, membership, or truth
output.

For each rule-passing candidate, target panels are the numerically sorted players
with finite XY at the origin, fixed for all 15 future samples. Finite false-flag
positions remain in physical truth. An absent player or partial future XY pair
produces one null XY pair in both target representations and a shared Boolean mask.
Displacement is computed from the same future XY minus the observed nonzero origin
XY. A directed scene is scoreable when any origin player has truth at future sample
15; a window is scoreable when at least one of its two scenes is scoreable. The
derivation is incomplete if any required match has no scoreable window.

## Comparison and mismatch report

`PopulationSubmissionV2` is read-only bytes for the five wire artifacts. Comparison
checks ordered candidate and census rows, diagnostic exclusions and warnings,
membership and roles, origin players, physical truth values, masks, scoreability,
all manifest/candidate/truth/output digests, input and retained-sample snapshots,
source-wide scan counts, producer provenance, and the receipt self-digest. Each
warning and exclusion occurrence retains its canonical sample index, multiplicity,
and producer order; only message prose is treated as presentation text.
Artifact values are checked against the independent replay, so resealing changed
membership, truth, or masks cannot make them reconcile.

The comparison API does not accept a caller-supplied fingerprint. It requires the
exact producer revision and validates the receipt's complete, sorted inventory of
79 package-relative `.py`/`.json` paths and SHA-256 values, its self-hash, and the
fingerprint digest pinned from that immutable Git tree. A missing, altered,
incomplete, or self-rehashed forged inventory cannot yield `RECONCILED`.

`AuditReportV2` contains no source rows or truth panels. It records SHA-256 and byte
length snapshots for the authority documents, inputs, retained samples, and
submitted artifacts; the verifier source hash; Python version; exact role and
per-match counts; stop status; and mismatch paths with expected/actual value hashes.
Canonical report bytes include `report_sha256`, computed over the report without
that field. Reports have no runtime timestamp and do not emit a qualification PASS.

## Frozen PR #20 synthetic reconciliation

The repaired verifier implementation was frozen at commit
`b9aaed295f0a22f4845ab6eb1cad3dcfaee65dce` with source SHA-256
`09d12139e858accc7cb96e5e2c4b5fbcccb61e0046943418cc921391136e7593` before any
new producer comparison outputs were generated. The producer ran in a separate
process from the immutable PR #20 revision
`6644dba8c945ca86be72b54792db30cbe488e5d0`; no producer eligibility code is
imported or called by the verifier.

All six valid synthetic cases reconciled the five wire artifacts with zero
mismatches: a clean baseline, multiple nullable detection flags with missing and
partial XY, an absent ball object, repeated player warnings with a missing active
record, a phase gap at a support edge, and malformed nested data on an odd frame.
The clean baseline contains 60 candidates, 60 eligible windows, 860 diagnostic
census slots, and 60 scoreable windows. Seven malformed-source controls were
rejected by both implementations: extra top-level fields on odd and even frames,
an extra retained-player field, duplicate and unknown retained-player IDs, and
malformed retained ball and possession schemas.

The pinned digest commits to all 79 sorted package paths and file digests at the
producer revision: SHA-256
`153bc67c532b8eddba90a98994d60f656526e71961f17c9d1f2454a72dd2e1a4`. The refreshed
clean-baseline report is
[`prospective-population-verifier-v2-reconciliation.json`](prospective-population-verifier-v2-reconciliation.json),
with report SHA-256 `624db3c7ebb96b1759871d4f07f1ec06e1db3fc202009ee7d31a02742b82f7a0`.
The suite records six per-case audit-report hashes, output snapshots, and the
negative-source outcomes in
[`prospective-population-verifier-v2-adversarial-reconciliation.json`](prospective-population-verifier-v2-adversarial-reconciliation.json),
with suite SHA-256 `1f53f7710f8187ecb1f9fb306c911dab9a75b9e03e111ae510aeca63a18abb66`.
Every report records `RECONCILED`, `authoritative: false`, and
`qualification_status: NOT_QUALIFIED`; the producer receipts remain
`UNQUALIFIED` and say `independent_verification: NOT_PERFORMED`.

## Independence and limits

The verifier imports only Python standard-library modules. It does not import or
call `population_producer_v2.py`, its private helpers, production sampling or
eligibility code, or production population validators. An AST test guards this
boundary. Expected 5 Hz samples, candidates, eligibility, targets, masks, and
physical truths are recomputed from the synthetic raw bytes. Shared sorted-key,
compact UTF-8 JSON and the frozen representation-tagged hash contract are used
only for wire serialization.

The fixtures use synthetic numbers only. The normalized phase bytes are the
producer's documented synthetic interface, not byte-qualified source CSV. This
module does not authenticate the 81 pinned files or LFS payloads, prove real-source
coverage, check data rights or Windows ACLs, write restricted receipts, or accept
a protected attestation. It must not be used to qualify real data. A separate
Windows-native protected adapter, independent source-byte verification, owner
authorization, protected receipt authentication, and subsequent scientific and
repository reviews remain required by the active protected-population acceptance
task.
