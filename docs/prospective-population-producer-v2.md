# Linear issue 501 v2 acceptance reconciliation and verifier handoff

This is an additive acceptance-contract proposal for Linear issue 501; preserve its original v1
description and earlier FAIL receipts as historical evidence. This document does not
edit Linear, approve a merge, or qualify a population.

## Exact acceptance reconciliation

Replace the **active** v1 policy 1.1.0 and population 1.1.0 requirements with
`skillcorner_window_v2` 2.0.0 and
`fpdbench.prospective-evaluation-population` 2.0.0, population identity
`skillcorner.prospective.conditional_motion.population_v2`.
Replace the active v1 measurement/protocol/plan bindings with the following
immutable authorities from reviewed Linear issue 531 HEAD
`666578e0d4e6475724755ab38e8c4c565e0eadf2`.
Do not rewrite v1 JSON, original issue history or the historical qualification FAIL.

| Authority | SHA-256 |
| --- | --- |
| Source release (unchanged) | e92c417b7640b27399451134ee3fce4b1961b0c0dfc2e01175a8f3c906a9ae07 |
| Source population (unchanged) | e9054b7ddc2dfeff4dd8425ea61a23ed0b326076a08899e47502484228fdbdf4 |
| Measurement v2 | 1ecf355b3e6e2f04967e8363c1fdecc7f40707a7dda9966ebee1b3d90e97e671 |
| Eligibility v2 | ed1cdc20ca7a93040fd4aabc91655819c5c4b8c58021c6540c6aaea325dafa11 |
| Protocol v2 | 3d7bdc46300b966a4da274579d21ac4c8219e1ef897719d6b7a308596e9f1d9f |
| Population schema bytes | 27da86b7355c311a65c68ab9b2bd3ae86e27779ed48641c23181ffe2f9adc224 |
| Result schema bytes | d0d7dbf4a14cade66d1e0ce7282441d8f035a68de8a192ad8e4d70210be18f7f |
| Plan v2 | a59fee6ee8e9fb03f4f0ccdae1933458af2bbf2375db7e6cd2bdf10962e42b62 |

The source-population digest is read from the unchanged protocol constant and bound
explicitly in each draft; it is not recomputed from a synthetic fixture.

Active acceptance text:

1. Enumerate all canonical 5 Hz forecast origins in each metadata period's half-open
   source-frame range in every one of the pinned 20 matches, including missing-origin
   and insufficient-support candidates. Advance one canonical sample. Sort matches
   by protocol role (training, validation, evaluation), then the pinned role order;
   sort origins by period and canonical sample index. Each origin has offsets
   -25 through +15, inclusive (41 slots), with absent slots represented explicitly.
2. Apply the unchanged approved v2 policy. Require finite origin ball XY and at
   least 39 finite ball pairs of 41. Preserve null detection as unknown, absent ball
   versus present-null ball, warning-only partial XY under origin/coverage gates,
   existing player/phase/temporal/pitch rules and eight quality dimensions.
   Before any retained membership or truth masks, scan **all retained source samples**
   in all matches, including samples outside candidate support, and stop the entire
   population on `BALL_NULL_FLAG_WITH_FINITE_XY_UNAPPROVED`. No window filtering,
   null-to-false conversion, interpolation or threshold relaxation is authorized.
3. Retain every and only rule-passing candidate in a draft manifest. Record every
   candidate identity, diagnostic digest, exclusions/warnings, exact candidate,
   eligible, directed-scene and scoreable-window counts per match and role.
   Scoreability follows the frozen protocol: a scene has a finite target at future
   slot 15; a window has at least one scoreable scene. No scoreable window in any
   required match is an incomplete population, never zero-filled or omitted.
4. Preserve exact 12/4/4 roles, source-release/population, measurement, eligibility,
   protocol, schema and plan bindings. For each home/away scene use the numerically
   sorted finite-origin player panel, fixed for all 15 future samples. Keep false
   detections with finite XY; represent an absent/partial future pair as one null.
   Derive physical XY and per-player displacement using the exact observed origin,
   with shared masks and no later entrants or identity stitching.
5. Independently replay from byte-qualified, authorized source inputs. The second
   verifier must independently derive candidates, eligibility, panels, physical
   truths and masks, reconcile every candidate and all counts/digests, and reject
   arbitrary self-consistent hashes. Neither a producer receipt, synthetic result,
   COMMENT review nor green CI is qualification.
6. Keep source bytes, row identities, truth, row digests, population manifests and
   full receipts outside Git in authorized immutable restricted storage. Before a
   real run require all 81 source files, actual LFS payload SHA-256/size, ordinary
   Git blob/size identities, rights authorization and independently verified
   complete retained-frame coverage. Missing, truncated, mismatched, unauthorized
   or pointer-only inputs fail closed. The current delivery permits synthetic
   in-memory execution only; it installs no real-data runner or receipt accepter.
7. Leave all empirical authorization APIs closed. Qualification requires separately
   reviewed independent verification and protected receipt authentication;
   training, selection, LOMO and scoring require their subsequent authorization.

V1 historical hashes remain measurement
`4c29471c7fccc037dcfafd30222991e06d150e0887c0b667918bfa374262c6c3`,
eligibility `f0e1186f765cc7ce19c95152d8d6eacc66382f7e7f5a9ad1aa11c88c8a12f70b`,
protocol `865601662f4462178eaf7e1049075668176a9bd35f3bf4b1b6b8aa370de1d26c`,
plan `0446649e1ad049880cf6f8a76b4f3e03421d8bd7a1f7a2c562b5770461527775`.
Snapshot bytes remain
`a22f93f11cf428b7f326a93714fbcc798c99e5d0dbcab5122edb48d050b4a873`.

## Integration-readiness observation, 2026-10-20 UTC

Read-only GitHub API checks found all four PRs OPEN, DRAFT and MERGEABLE/CLEAN.
No merge, retarget, approval submission or protection change was performed.

| PR | Exact HEAD | Base | Review / CI |
| --- | --- | --- | --- |
| #16 | d1978a55dfda9894767fc96e643adbf08f078bbb | main | No formal reviews; push/PR quality and public-reproducibility SUCCESS |
| #17 | 319f3540b67857293ca865744aad8798a9e1ee49 | #16 branch | No formal reviews; push/PR required checks SUCCESS |
| #18 | 10014dcd5821faae8aa402abf4fc2022f1e14ea0 | main | Scientific DESIGN PASS as COMMENT; push/PR required checks SUCCESS |
| #19 | 666578e0d4e6475724755ab38e8c4c565e0eadf2 | main | Scoped repair re-review PASS as COMMENT; push/PR required checks SUCCESS |

Main protection: enforce_admins=true, strict up-to-date checks
`quality` and `public-reproducibility` (GitHub Actions app 15368);
required approving count=0, no required code owners/last-push approval;
force pushes and deletions disabled; no additional rulesets returned.
PR #18 has no review threads. PR #19 has six unresolved threads (three marked
outdated); the latest exact-head COMMENT accepts the scoped repair, but those
threads still need deliberate disposition. Conversation resolution is not required
by current protection. There are **no APPROVED events** on these PRs. User-required review/authorization
gates still apply even though the configured minimum approval count is zero.

Sequence: deliberate integration of #18's scientific provenance first; then check
#19 against the resulting main, rerun integration CI, review and seek authorized
integration. Both remain DRAFT/unmerged. #16/#17 are a separate diagnostic/audit
stack: #16 precedes #17; after authorized #16 integration inspect #17's new base
and rerun CI/review. Their historical POSIX storage gate is not a Windows receipt
writer and must not be reused as one. The new producer branch is stacked directly
on reviewed #19, excludes #16/#17/#18, and must be reviewed against that base.

Sources: [Linear issue 501](https://linear.app/alignerr-cmj/issue/fe554f95-1ae8-406c-9dd7-a73d91711e51),
[Linear issue 520](https://linear.app/alignerr-cmj/issue/9e3a0b17-9211-4469-b39b-ef266134f707),
[Linear issue 531](https://github.com/Litju/football-performance-dynamics-bench/pull/19),
[PR #18](https://github.com/Litju/football-performance-dynamics-bench/pull/18),
[PR #19](https://github.com/Litju/football-performance-dynamics-bench/pull/19).

## Independent verification interface (separately tasked work)

Call `produce_population_draft_v2(inputs, input_kind="synthetic")` from
`fpdbench.benchmarks.conditional_multi_agent_motion_prediction.population_producer_v2`.
There is no source download, filesystem input/output command, real-data switch,
qualified token, verifier implementation or automatic empirical activation.

`PopulationMatchInputV2` is frozen and contains match_id plus immutable bytes for:
metadata JSON, complete tracking JSONL, and normalized phase-interval JSON
(array of exact integer period/frame_start/frame_end objects). The normalization
boundary is deliberately explicit: this is **not** byte-qualified source CSV.
The future authorized adapter must independently bind normalization to the exact
pinned phase CSV and account for index/events files, even when unused as features.

The frozen `PopulationVerificationSubmissionV2` contains five byte payloads:

| Field | Canonical content / verification responsibility |
| --- | --- |
| manifest_json | Existing population 2.0.0 schema; structural validation only |
| candidates_jsonl | One row per protocol candidate, ordered by split role, match, numeric period and sample; each row includes its complete public diagnostic and SHA-256 |
| diagnostic_census_jsonl | One row for every even metadata-period grid slot, including missing origins and incomplete support, in the same canonical order |
| truth_jsonl | One row per retained window/scene: identity, origin player IDs/XY, both 15-slot truth panels, common Boolean mask, representation digests, scoreability and NO_FINAL_TARGET reason |
| receipt_json | Versioned input SHA-256/size snapshots, retained-sample digests/counts, candidate and diagnostic census counts/digests, producer dependency fingerprint, full source-wide scan counts and output digests |

The frozen protocol defines origin candidates as canonical 5 Hz samples with
complete 41-sample support. We apply that wording directly: a candidate must
have an observed origin and all 41 expected canonical sample positions must be
present. Eligibility is evaluated after this population is formed. A metadata
grid slot with no observed origin or incomplete support remains in the
diagnostic census and is not assigned candidate membership. The census keeps
the grid identity (period and canonical sample index) for those diagnostic-only
slots. No frozen authority JSON or scientific eligibility rule changed.

All serialized objects use existing sorted-key compact UTF-8 canonical JSON.
JSONL has one LF after **every** row. `candidate_origin_population_sha256`
hashes the canonical JSON array of exactly the protocol candidate
{match_id, origin_sample_id} identities, including candidates excluded by
eligibility but excluding diagnostic-only grid slots without a complete
observed support. The receipt separately binds the full diagnostic census
count, ordered identities and JSONL bytes.

`producer_executable_fingerprint` lists every installed-package `.py` and
`.json` file by sorted package-relative path and SHA-256, then hashes that
manifest. It includes the producer, canonicalizer, period/eligibility code,
protocol split and truth/hash utilities, plus their packaged authorities. The
package declares no third-party runtime dependencies. The fingerprint contains
no checkout path, build timestamp or VCS metadata, so the wheel and sdist-built
wheel produce the same fingerprint and canonical receipt bytes.

`eligibility_result_sha256` hashes the complete dataclass diagnostic,
including UNQUALIFIED status. Existing representation-tagged truth and mask
hash functions specify the wire hashes;
their legacy serialization version labels remain unchanged. Input snapshots
are domain-separated by named field in the receipt. The receipt self-digest
hashes its canonical object with only receipt_sha256 omitted.

The same immutable truth/membership bundle applies to every regime and model;
the producer accepts no model/regime/masking parameter. Target masks and quality
are restricted verification data, never model-visible features. No predictions
or metrics are computed.

An incomplete required match raises `IncompletePopulationV2`, carries an immutable
INCOMPLETE diagnostic receipt, and returns no manifest/submission. Eligible but
unscoreable windows remain in eligible counts. Scoreability is determined before
qualification, using final-slot truth only. Malformed/partial input or drift raises
before any usable submission. All submissions remain UNQUALIFIED and all existing
empirical gates stay closed. A caller can construct bytes or hashes; that proves
nothing about authenticity. This first interface does **not** accept a verifier's
PASS or authenticate signatures.

Assign the second verifier to a different engineering task. It must:

1. Read the owner-approved specification and immutable authorities directly.
   Do not import/call this producer, its private helpers, the production candidate
   evaluator, its period-bound helper, or its eligibility logic to derive expected
   outcomes. Shared JSON/hash wire serialization and immutable authority documents
   are acceptable; self-consistency comparisons alone are insufficient.
2. Build a separate raw-source parser, period-grid enumerator, phase/player/ball/
   temporal eligibility implementation and physical-truth derivation. Reconcile
   exact input bytes and exhaustive source coverage before trusting any output.
3. Compare candidate-by-candidate decisions/exclusions/warnings, ordered membership,
   input/retained counts, exact role assignment, fixed panels, every physical value,
   displacement arithmetic including nonzero anchors, common masks, final-slot
   scoreability and all canonical digests. Verify the global drift gate over all
   retained source samples, not only eligible support.
4. Return a separate restricted mismatch report and provenance receipt binding its
   independently authored code/version, all input hashes, producer outputs and the
   exact population manifest. Design protected receipt authentication separately;
   do not make a caller-provided PASS sufficient to enable scoring.
5. Exercise the synthetic raw-frame generator in
   `tests/unit/test_population_producer_v2.py::synthetic_sources` and its adversarial
   transformations. These fixtures build raw frames without producer eligibility
   calls. The current tests are producer tests, **not** a second verifier.

Required adversarial verifier cases include a missing/duplicate match, shuffled
match input, missing origin with unchanged grid count, exact 39/41 versus 38/41,
missing origin ball, source drift outside all candidate windows, malformed/duplicate/
nonfinite JSON, pointer-only payload, period boundaries, partial future XY, finite
false detections, replacement players, a scene without final truth, a required
match with eligible but no scoreable windows, swapped player order, altered role,
one-axis truth edits, nonzero-origin displacement edits, model-dependent masks,
and a fully rehashed fabricated receipt/membership. Last cases must still fail
independent source comparison even when structural validators accept them.

Before authorized real qualification: integrate/review #18 then #19 deliberately,
review this producer, separately implement/review the verifier, add a Windows-native
restricted-storage/ACL and immutable write adapter, verify all pinned source bytes
and LFS payloads, obtain explicit real-source execution authorization, and reconcile
both exhaustive runs. Publish only approved non-reconstructive closeout aggregates.
