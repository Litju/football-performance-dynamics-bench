# Nullable-ball v2 measurement and eligibility decision

**Status: READY FOR INDEPENDENT SCIENTIFIC APPROVAL. Not approved or frozen; keep PR #18 in DRAFT until approval.**

This document specifies a model-result-blind successor proposal. It does not authorize source-population construction, training, checkpoint selection, empirical scoring, or source-data/result publication. It leaves the v1 authorities and their bytes unchanged.

## Evidence and authority boundary

- [nullable-ball source audit](https://linear.app/alignerr-cmj/issue/3ea6850d-aba2-4513-9eea-9497ea54380d) reports agreement between two implementations, match by match, over 622,414 retained even-frame rows: 352,369 present-ball / `true` / finite-XY, 87,095 present-ball / `false` / finite-XY, and 182,950 present-ball / `null` / XY unavailable. Other retained ball/XY cells were reported as zero.
- The public matrix's “both null or missing” label is a coarsened XY-availability bucket. A read-only check of the existing restricted aggregate receipts for the [nullable-ball source audit](https://linear.app/alignerr-cmj/issue/3ea6850d-aba2-4513-9eea-9497ea54380d) reconciled it: the retained present-ball / null-flag cell has 182,950 rows with `x_state=null` and `y_state=null`; no row in that cell has a missing coordinate key. The receipt schema and audit parser classify explicit JSON null separately from a missing key. The checked receipts' stored digests and pinned source identities matched; source integrity, independent replication, all aggregate invariants, and zero mismatches were recorded as PASS. Only aggregate cells were inspected; no source payload, row identity, per-match detail, or row-level receipt was opened or copied into this document.
- The all-source-frame count of 365,951 null ball flags remains a single-path report: the independent retained-frame verifier did not replicate odd-frame counts or the scanner's full schema-anomaly taxonomy. That count and the implied 183,001 odd-frame count are not used to choose v2 semantics.
- PR [#16](https://github.com/Litju/football-performance-dynamics-bench/pull/16) is a draft source-preflight diagnostic; PR [#17](https://github.com/Litju/football-performance-dynamics-bench/pull/17) is a draft retained-frame audit stacked on #16. Their code and synthetic tests are not frozen scientific authorities. This proposal does not include either PR's code.
- The provider's meaning for a null ball detection flag is undocumented. The pinned source pattern establishes a nullable value, not what that value means. `false` remains the exact source flag; v2 makes no claim that a false ball flag means extrapolation.
- The research comment triangulates the pinned [SkillCorner README](https://github.com/SkillCorner/opendata/blob/4340d274572876239c154c90bc507a9b3250a656/README.md), [tracking tutorial](https://github.com/SkillCorner/opendata/blob/4340d274572876239c154c90bc507a9b3250a656/notebooks/tutorials/03_Basics_of_Tracking/Open_Data_Tracking_Tutorial.ipynb), and [toolkit](https://github.com/SkillCorner/skillcorner-toolkit/blob/3389bf6cc9d472c347db17be6c104fcc90287b4a/event_synchronization/with_tracking/formatted_data_manager.py). These support preserving missing ball coordinates but do not define null-flag provenance; the observed pinned corpus remains the primary authority.
- [frozen measurement authority](https://linear.app/alignerr-cmj/issue/058676e3-d791-4e68-ab3a-a5acded3e4dd) freezes the 10 Hz to 5 Hz measurement transform and source-field boundary. [frozen eligibility authority](https://linear.app/alignerr-cmj/issue/3618f0ec-bc2e-4350-9699-5ef188619aad) freezes the window, phase, player, coordinate, and quality rules. Their v1 authorities remain immutable.
- [frozen benchmark protocol](https://linear.app/alignerr-cmj/issue/2882e2c6-f2b6-48a8-b724-b0caac415235) and [frozen experiment plan](https://linear.app/alignerr-cmj/issue/1ae916a8-7380-48dc-96c2-57353c52d954) lock the study question, targets, masks, time grid, match split, regimes, metrics, and execution plan. The experiment-plan issue remains In Progress because the protected-population gate is open.
- [nullable-ball decision issue](https://linear.app/alignerr-cmj/issue/9e3a0b17-9211-4469-b39b-ef266134f707) is In Review. The latest independent review on that issue conditionally accepts drafting only; it rejects freezing until the state table, partial-coordinate behavior, denominator/stratum rules, and migration contract receive independent review.

The local v1 identities are: source release `skillcorner_open_data_v1` SHA-256 `e92c417b7640b27399451134ee3fce4b1961b0c0dfc2e01175a8f3c906a9ae07`; source population SHA-256 `e9054b7ddc2dfeff4dd8425ea61a23ed0b326076a08899e47502484228fdbdf4`; measurement `skillcorner_5hz_v1` 1.0.0 SHA-256 `4c29471c7fccc037dcfafd30222991e06d150e0887c0b667918bfa374262c6c3`; eligibility `skillcorner_window_v1` 1.1.0 SHA-256 `f0e1186f765cc7ce19c95152d8d6eacc66382f7e7f5a9ad1aa11c88c8a12f70b`; protocol 1.1.0 SHA-256 `865601662f4462178eaf7e1049075668176a9bd35f3bf4b1b6b8aa370de1d26c`; and plan 1.1.0 SHA-256 `0446649e1ad049880cf6f8a76b4f3e03421d8bd7a1f7a2c562b5770461527775`.

This review did not read source payload bytes or inspect row-level/per-match receipts, row-level derivatives, private historical qualification truth, model outputs/checkpoints, or empirical scores. It inspected only aggregate fields in the existing restricted receipts for the [nullable-ball source audit](https://linear.app/alignerr-cmj/issue/3ea6850d-aba2-4513-9eea-9497ea54380d) to settle explicit-null versus missing-key status. This read-only receipt check is not independent scientific approval or an external source replay.

## Proposed v2 measurement contract

### Sampling and preservation

Keep the pinned source release and source-population hashes. Select the same globally even-numbered source frames at 5 Hz. Preserve the source frame, canonical index, timestamp, period, coordinates, player records, team orientation, and existing auxiliary fields exactly as v1 specifies. Do not synthesize samples, infer timestamps, interpolate, smooth, or drop any retained even-frame row to handle nullable ball state.

The v1 nested sampling sub-transform remains `transform_id=skillcorner_source_frame_even_10hz_to_5hz`, `transform_version=1.0.0`. Its scope is the unchanged global even-source-frame selection and 10 Hz to 5 Hz sampling algorithm. The measurement state and schema advance to `skillcorner_5hz_v2` / `fpdbench.skillcorner-data-state` 2.0.0 because the canonical ball contract changes; retaining the sampling sub-transform at 1.0.0 does not reuse or preserve the v1 measurement-state hash.

For each retained sample, emit `ball: null` only when the required source `ball_data` field is present and null. A missing `ball_data` field is `INVALID_SAMPLE_SCHEMA`, not an absent ball. If `ball_data` is an object, require exactly the v1 source keys (`x`, `y`, `z`, `is_detected`); missing or unexpected keys fail closed. Validate `z` as in v1 even though it is excluded from canonical output: JSON null is allowed, otherwise it must be a finite JSON number; reject Booleans, nonnumeric values, NaN, and infinity. These exact-key and `z` checks apply to every present-object row and are not relaxed by the XY/flag decision table. Preserve `x`, `y`, and `is_detected` as `x_m`, `y_m`, and `is_detected`, including explicit JSON nulls, under the source-state rules below. Do not turn a present object into an absent ball. All other v1 source-schema and measurement checks remain fail-closed unless explicitly changed here. A structural source error must stop canonical output publication; a partially written artifact must not be accepted as a complete transform.

### Source-state decision table

`finite XY` means both coordinates are finite JSON numbers; Boolean coordinate values are invalid. `x-only` and `y-only` mean the other coordinate is explicitly null. Missing coordinate keys are not null values. A flag is valid only when its JSON value is exactly `true`, `false`, or `null`; do not accept integers such as `0` or `1` as Booleans. The matrix covers each present-object combination; the separate absent-object row covers the only valid absent state.

| Source `ball_data` state | Flag / XY state | Canonical output | Position and eligibility outcome |
| --- | --- | --- | --- |
| Required key present with JSON null | Flag and XY not applicable | `ball: null`; absent-object count +1 | Mask 0; `BALL_OBJECT_ABSENT`; position count +0; origin and 39-of-41 rules apply |
| Required key missing, or value is neither null nor an object | Not applicable | Reject complete transform | `INVALID_SAMPLE_SCHEMA`; do not treat as absent ball |

| Present-object flag state | Both finite | X-only | Y-only | Both explicitly null | Either coordinate key missing | Any coordinate value nonnumeric | Any coordinate value nonfinite |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `true` | Preserve object; mask 1; position count +1; known-true count +1 | Preserve values; mask 0; `BALL_COORDINATES_PARTIAL`; position count +0 | Preserve values; mask 0; `BALL_COORDINATES_PARTIAL`; position count +0 | Preserve nulls; mask 0; `BALL_COORDINATES_MISSING`; position count +0 | Reject transform: `INVALID_SAMPLE_SCHEMA` | Reject transform: `INVALID_SAMPLE_SCHEMA` | Reject transform: `NONFINITE_COORDINATE` |
| `false` | Preserve object; mask 1; position count +1; known-false count +1; do not label the position extrapolated | Preserve values; mask 0; `BALL_COORDINATES_PARTIAL`; position count +0 | Preserve values; mask 0; `BALL_COORDINATES_PARTIAL`; position count +0 | Preserve nulls; mask 0; `BALL_COORDINATES_MISSING`; position count +0 | Reject transform: `INVALID_SAMPLE_SCHEMA` | Reject transform: `INVALID_SAMPLE_SCHEMA` | Reject transform: `NONFINITE_COORDINATE` |
| `null` | Preserve finite XY and null flag; `BALL_DETECTION_UNKNOWN`; count in null-flag × finite-XY diagnostics; stop population qualification with `BALL_NULL_FLAG_WITH_FINITE_XY_UNAPPROVED`; emit no eligible population or model mask | Preserve values; mask 0; `BALL_DETECTION_UNKNOWN` + `BALL_COORDINATES_PARTIAL`; position count +0 | Preserve values; mask 0; `BALL_DETECTION_UNKNOWN` + `BALL_COORDINATES_PARTIAL`; position count +0 | Preserve nulls; mask 0; `BALL_DETECTION_UNKNOWN` + `BALL_COORDINATES_MISSING`; position count +0 | Reject transform: `INVALID_SAMPLE_SCHEMA` | Reject transform: `INVALID_SAMPLE_SCHEMA` | Reject transform: `NONFINITE_COORDINATE` |
| Key missing | Reject transform: `INVALID_DETECTION_FLAG` | Reject transform: `INVALID_DETECTION_FLAG` | Reject transform: `INVALID_DETECTION_FLAG` | Reject transform: `INVALID_DETECTION_FLAG` | Reject transform: `INVALID_DETECTION_FLAG` + `INVALID_SAMPLE_SCHEMA` | Reject transform: `INVALID_DETECTION_FLAG` + `INVALID_SAMPLE_SCHEMA` | Reject transform: `INVALID_DETECTION_FLAG` + `NONFINITE_COORDINATE` |
| Value invalid (any non-Boolean, non-null type) | Reject transform: `INVALID_DETECTION_FLAG` | Reject transform: `INVALID_DETECTION_FLAG` | Reject transform: `INVALID_DETECTION_FLAG` | Reject transform: `INVALID_DETECTION_FLAG` | Reject transform: `INVALID_DETECTION_FLAG` + `INVALID_SAMPLE_SCHEMA` | Reject transform: `INVALID_DETECTION_FLAG` + `INVALID_SAMPLE_SCHEMA` | Reject transform: `INVALID_DETECTION_FLAG` + `NONFINITE_COORDINATE` |

If more than one defect is present, report every applicable reason code and publish no canonical artifact; validation order must not hide a second defect. A missing or unexpected key in the source sample or ball object is `INVALID_SAMPLE_SCHEMA`. An absent ball's flag and coordinates are not applicable and do not increment the null-flag count.

For every valid present object, count `true`, `false`, and `null` flags in their own source-state count regardless of XY state; these counts are independent of position counts. A missing or invalid flag is a schema failure and has no accepted state count.

For any supported state with no finite pair, emit mask 0 and count no position. Add `BALL_MISSING_AT_ORIGIN` when the origin lacks a finite XY pair and `BALL_COVERAGE_BELOW_MINIMUM` when fewer than 39 of 41 expected slots have finite XY; both exclusions may apply. A partial pair away from the origin is warning-only if the origin is finite and the 39-of-41 threshold passes. A null-flag/finite-XY row is a population-level contract-drift stop, not a per-window exclusion or an ordinary missing-position case. The pinned retained-frame audit reports no absent ball objects, partial/invalid XY, missing or invalid flags, or null-flag/finite-XY rows; these prospective cases remain synthetic-test requirements.

### Ball position coverage and origin

- Keep exactly 41 expected support slots: 25 history intervals plus origin plus 15 future intervals at 5 Hz. Offsets are `-25..0` for history and `1..15` for future; origin is support index 25.
- For each origin candidate with a defined 41-slot span, `ball_position_coverage_numerator` is the number of slots with both finite XY, regardless of detection flag; `ball_position_coverage_denominator` is always 41, including a missing source sample slot. Partial pairs, null pairs, absent ball objects, and missing source slots contribute zero. A null-flag/finite-XY sample counts as finite XY in diagnostics but stops population qualification before eligible membership or model masks are produced.
- A window passes the ball rule only when coverage is at least 0.95 and the origin has both finite XY. With 41 slots, that means at least 39 finite pairs; 39/41 passes and 38/41 fails. A finite pair with source flag `false` counts; no position is imputed for any null.
- If the 41-slot span cannot be defined, report coverage fraction as null and exclude for insufficient history/future support. If a slot is absent within a defined span, keep it in the denominator, report the temporal gap, and exclude for the applicable continuity reason. Do not shrink the denominator to the number of rows that happened to be read.
- The origin gate checks a finite XY pair, independently of detection attribution. Null flag plus finite pair is intercepted by the global drift gate before membership construction. Do not add a separate known-detection-at-origin gate.

## Eligibility decisions

All v1 rules remain unless this document explicitly changes the nullable-ball handling. Eligibility is membership-only and model-result-blind.

The approved downstream invariants remain: 5-second history (26 samples including origin), 3-second horizon (15 future samples), 41 support slots; absolute XY and origin-relative displacement targets; the three information regimes below; 18 cells across the three existing model classes; seeds `1729`, `2718`, and `31415`; 12 match-held-out LOMO folds; primary ADE and secondary FDE/XY-RMSE in metres; descriptive directional contrasts without confirmatory p-values or confidence intervals. Preserve the existing model definitions, optimizer/training rules, validation selection, stopping, failure/retry, and compute rules verbatim: validation selects by the equal mean of four validation-match ADE values, minimizing with earliest-step tie break, checks every 100 steps, caps at 5,000 steps with patience 10, and uses no hyperparameter search; the campaign ceiling stays 312 CPU-core-hours and 336 wall-clock hours. The exact role membership remains:

| Role | Match IDs |
| --- | --- |
| Training (12) | `1886347`, `1899585`, `1927964`, `1959846`, `1986691`, `1996436`, `2006363`, `2007448`, `2007721`, `2011166`, `2013725`, `2016236` |
| Validation (4) | `1953632`, `1996435`, `2015213`, `2017461` |
| Evaluation (4) | `1874553`, `1925299`, `2006229`, `2010085` |

The 12 LOMO folds hold out each training match once in ascending training-match ID order. The role-assignment SHA-256 remains `923dc2721a05620716f23c3b4cb1814e73485f80052f00c5334ccce666b99d94`; the v1 role arrays and LOMO identities are copied unchanged into the successor protocol.

### Hard exclusions and global stop

Preserve these v1 hard-exclusion codes: `BALL_COVERAGE_BELOW_MINIMUM`, `BALL_MISSING_AT_ORIGIN`, `CANONICAL_FRAME_MISMATCH`, `COORDINATE_IMPLAUSIBLE`, `DUPLICATE_PLAYER_ID`, `DUPLICATE_SAMPLE`, `INSUFFICIENT_FUTURE_SUPPORT`, `INSUFFICIENT_HISTORY_SUPPORT`, `INVALID_DETECTION_FLAG`, `INVALID_MATCH_METADATA`, `INVALID_SAMPLE_SCHEMA`, `NONFINITE_COORDINATE`, `NONMONOTONIC_SAMPLE_ORDER`, `OUTSIDE_PERIOD_BOUNDS`, `PERIOD_BOUNDARY_CROSSED`, `PHASE_INTERVAL_INVALID`, `PHASE_MATCH_ID_MISMATCH`, `PHASE_SOURCE_IDENTITY_MISMATCH`, `PHASE_NOT_IN_PLAY_OR_UNKNOWN`, `PERIOD_BOUNDS_CONFLICT`, `PERIOD_BOUNDS_DUPLICATE`, `PERIOD_BOUNDS_INVALID`, `PERIOD_BOUNDS_MISSING`, `PLAYER_COUNT_BELOW_TEAM_MINIMUM`, `PLAYER_TEAM_IDENTITY_CONFLICT`, `TEMPORAL_GAP`, `TIMESTAMP_DISCONTINUITY`, `TIMESTAMP_MISSING`, and `WINDOW_SUPPORT_LENGTH_MISMATCH`.

For the ball, retain `BALL_MISSING_AT_ORIGIN`, `BALL_COVERAGE_BELOW_MINIMUM`, `INVALID_DETECTION_FLAG`, `NONFINITE_COORDINATE`, `INVALID_SAMPLE_SCHEMA`, and `COORDINATE_IMPLAUSIBLE` with v2 meanings from the table. Add `BALL_NULL_FLAG_WITH_FINITE_XY_UNAPPROVED` as a **population-level hard stop**: preserve all source/canonical samples, report aggregate diagnostics in restricted storage, and do not issue an eligible-window population or continue by filtering only affected windows. It is not a warning and not an ordinary per-window exclusion, because the contract meaning is unapproved.

`BALL_COORDINATES_PARTIAL` is a warning, not a new blanket exclusion. The finite-origin gate and the unchanged 0.95 threshold determine whether partial/missing coordinates make a particular window ineligible. Gross-bound violations remain hard exclusions; outside-pitch positions and advisory speed outliers remain warnings without repair.

### Warnings and unchanged rules

Add or retain these ball warnings: `BALL_OBJECT_ABSENT`, `BALL_DETECTION_UNKNOWN`, `BALL_COORDINATES_MISSING`, `BALL_COORDINATES_PARTIAL`, `BALL_OUTSIDE_PITCH`, and `BALL_DISPLACEMENT_OUTLIER`. They preserve evidence and do not independently exclude a window. Preserve the other v1 warning codes: `IDENTITY_TRANSITION_EXPOSURE`, `PLAYER_APPEARANCE_METADATA_UNKNOWN`, `PLAYER_COORDINATES_MISSING`, `PLAYER_DISPLACEMENT_OUTLIER`, `PLAYER_OBSERVATION_MISSING`, `PLAYER_OUTSIDE_APPEARANCE`, `PLAYER_POSITION_OUTSIDE_PITCH`, `POSSESSION_CONTEXT_UNKNOWN`, `POSSESSION_PLAYER_UNOBSERVED`, and `SOURCE_QUALITY_UNKNOWN`.

Keep the seven-player-per-team floor, participation intervals, identity transitions, gross coordinate limits, advisory speed limits, and phase policy unchanged. Every 10 Hz frame from the first through last retained 5 Hz frame must still have positive phase coverage; any gap remains uncovered-or-unknown and excludes. All annotated in-play phase types remain included. Possession remains descriptive, never a hard gate.

## Detection attribution, quality strata, and zero denominators

Keep the eight composable v1 dimensions: `player_detection_exposure`, `ball_detection_exposure`, `player_completeness`, `ball_completeness`, `temporal_continuity`, `identity_transition_exposure`, `source_quality_uncertainty`, and `play_context`. Unknown is distinct from poor quality. Add ball-state counts and cross-tabs inside `quality.ball_observations`; do not make them model features or add a ninth window-level stratum.

For each complete expected 41-slot support, report:

| Output | Numerator | Denominator | Zero/unknown handling |
| --- | --- | --- | --- |
| `valid_position_count`, `position_coverage_fraction` | both-finite XY, independent of flag | 41 expected support slots | zero numerator gives `0/41 = 0.0`; support span unavailable gives null fraction |
| `flag_true_count`, `flag_false_count`, `flag_null_count` | slots in each source state | 41 | counts are zero when known; invalid/missing flag stops qualification |
| `absent_object_count` | `ball_data` null slots | 41 | separate from `flag_null_count` |
| `missing_source_sample_count` | expected support slots with no source row | 41 | count as missing position and retain the applicable temporal exclusion |
| `known_flag_count`, `known_flag_coverage_fraction` | true + false flags, regardless of XY | 41 when span is defined | known coverage is `0.0` if there are no Boolean flags; null if the support span is unavailable |
| `detected_share_among_known_flags` | true flags | true + false flags | null when there are no known flags or the denominator is unavailable; otherwise true / (true + false) |
| `flag_by_coordinate_state_counts`, `finite_xy_by_flag` | full flag-state × coordinate-state cells; the finite-XY summary is derived from the both-finite cells | 41 support slots | includes separate absent-object and missing-source-slot cells; null-flag/finite-XY is diagnostic and triggers the global stop |
| outside-pitch fraction | finite positions outside pitch rectangle | finite positions | null when there are no finite positions |
| displacement-outlier fraction | same-ball adjacent valid pairs above 50 m/s | continuous adjacent valid pairs | null when there are no such pairs |

Coordinate states are `both_finite`, `x_only`, `y_only`, `both_null`, `object_absent`, and `source_sample_missing`; flag states are true, false, null, absent-object/N/A, and missing-source-slot/N/A. The full cross-tab must reconcile to 41 for valid complete input. Missing flag keys, missing coordinate keys, unexpected keys, and invalid values are source-schema failures, not missingness buckets. Window-level `ball_detection_exposure` is `all_detected`, `mixed`, `all_false_flag`, or `unknown`; it is computed over finite XY positions, with `unknown` when support is incomplete, no finite position exists, or any finite position has a null flag. The counts above retain null/absent attribution even when that stratum is `unknown`.

Preserve the v1 denominator definitions for the other quality measures: finite player positions for player detection exposure; active roster player-frames for player completeness; 41 support slots for ball completeness and possession; 40 expected intervals for temporal continuity and, when roster metadata is complete, identity transitions; every 10 Hz source frame in the inclusive retained-sample span for phase coverage; finite entity positions for outside-pitch exposure; continuous adjacent same-entity pairs for displacement outliers; observed player records for null player-coordinate frequency. If a denominator is unavailable or zero for a ratio, emit null, not zero. A known denominator with zero numerator yields zero. Never turn an unavailable measurement into a zero coordinate.

## Future-context masks and target invariants

The protocol retains the approved three regimes and exact feature boundary:

- `history_only`: history target-team, opponent-team, and ball XY plus their masks.
- `future_ball`: the same history plus future ball XY and `future.ball.observation_mask`.
- `future_opponent_plus_ball`: the same history plus future ball XY/mask and future opponent XY/mask.

For ball context, the position mask is 1 exactly when that sample has both finite XY, independent of flag attribution; it is 0 for absent ball objects, null XY, and partial XY. A source null-flag/finite-XY state stops population qualification before a population mask is emitted, so it cannot silently become visible future context. Player context masks are 1 exactly for finite XY pairs, including source-false player positions as already approved. Missing XY may use the existing masked tensor encoding `(0, 0)` with mask 0; this is an input sentinel only. Canonical source values remain null and no zero is a measured or imputed position.

Target-player identity is fixed from the finite origin target panel under the frozen protocol. Future target positions and their model-independent truth masks remain evaluation-only. The mask is finite future target XY for the fixed origin target IDs; it is identical across target representations, models, seeds, and information regimes. Future eligibility reasons, phase/possession labels, quality fields, detection flags, target masks, and target membership are forbidden model features. Future opponent/ball masks describe only those context positions that the regime is authorized to observe; they never change eligible membership or target scoring masks.

## Successor identities, hashes, and migration bindings

These are the exact proposed identities and schema versions; they are **proposals, not frozen identities**. Every v2 digest remains unfrozen until independent review accepts the decisions below and the canonical files exist.

| Authority | Exact proposed ID and version | Schema ID and version | File | Digest input |
| --- | --- | --- | --- | --- |
| Source release | `skillcorner_open_data_v1`; pinned source/population hashes unchanged | Existing source-authority schema, unchanged | Existing v1 source authority | Existing source-release and source-population rules |
| Measurement | `skillcorner_5hz_v2` 2.0.0 | `fpdbench.skillcorner-data-state` 2.0.0 | `data_states/skillcorner_5hz_v2.json` | SHA-256 of canonical `scientific_state` only |
| Nested sampling sub-transform | `skillcorner_source_frame_even_10hz_to_5hz` 1.0.0, unchanged | No separate schema; nested in `scientific_state.transform` | Same measurement JSON | Included in the v2 measurement-state hash; identifies unchanged sampling only |
| Eligibility | `skillcorner_window_v2` 2.0.0 | `fpdbench.skillcorner-window-eligibility` 2.0.0 | `eligibility/skillcorner_window_v2.json` | SHA-256 of canonical `scientific_policy` only |
| Protocol | `skillcorner.prospective_conditional_motion` 2.0.0 | `fpdbench.prospective-benchmark-protocol` 2.0.0 | `prospective_skillcorner_protocol_v2.json` | SHA-256 of canonical `scientific_state` only |
| Experiment plan | `skillcorner.prospective_conditional_motion.execution` 2.0.0 | `fpdbench.prospective-experiment-plan` 2.0.0 | `empirical_experiment_plan_v2.json` | SHA-256 of canonical plan JSON excluding `plan_sha256` |
| Population | `skillcorner.prospective.conditional_motion.population_v2` | `fpdbench.prospective-evaluation-population` 2.0.0 | `evaluation_population_authority_v2.schema.json` | Schema SHA-256 over exact file bytes; manifest SHA-256 over canonical manifest fields excluding `manifest_sha256` |
| Window ID | SHA-256 opaque ID; `match_id` + origin sample ID | `fpdbench.prospective-window` 2.0.0 | Defined in v2 population API | SHA-256 of canonical identity payload described below |
| Result manifest | No separate result ID; schema ID is the identity | `fpdbench.prospective-experiment-result` 2.0.0 | `prospective_experiment_result_v2.schema.json` | Schema SHA-256 over exact file bytes; manifest SHA-256 over canonical manifest fields excluding `manifest_sha256` |
| Benchmarks | `skillcorner.prospective.conditional_motion.absolute_xy`; `skillcorner.prospective.conditional_motion.origin_relative_displacement` | Each `benchmark_version` 2.0.0 in protocol v2 | Protocol v2 | SHA-256 of canonical benchmark object excluding `benchmark_sha256`; protocol hash binds both IDs and benchmark digests |

Canonical JSON means UTF-8 bytes with recursively sorted keys, compact separators, `ensure_ascii=false`, `allow_nan=false`, and no trailing newline, using the existing canonical-byte helper. Bind and hash the v2 authorities in this order:

1. Hash the canonical measurement `scientific_state` and eligibility `scientific_policy`.
2. Bind those IDs, versions, and hashes into the protocol, then hash its canonical `scientific_state`.
3. Finalize the population and result JSON Schema files using their schema IDs, versions, and structural constraints. Compute each schema SHA-256 over exact file bytes. Neither schema may hard-code a `plan_sha256` or any population/result manifest digest; it may define those manifest fields with a generic SHA-256 shape.
4. Bind the protocol ID/version/hash and both schema IDs/versions/exact-byte hashes into the experiment plan, then compute `plan_sha256` from canonical plan JSON excluding the `plan_sha256` field.
5. Build the restricted population manifest with the source, measurement, eligibility, protocol, plan IDs/versions/hashes, schema identity, and exact 20-match roles. Compute its `manifest_sha256` from canonical manifest fields excluding `manifest_sha256`.
6. Bind the population-manifest digest and all upstream authority IDs/versions/hashes into each result manifest, then compute its `manifest_sha256` excluding that field.

The dependency graph is therefore: unchanged source release/population → measurement v2 and eligibility v2 → protocol v2 → schema-file byte hashes → plan v2 → population manifest → result manifests. Schemas define field shapes and IDs/versions; validators enforce digest equality by recomputing schema-file hashes against the plan, checking the population's `plan_sha256` against the verified plan, and checking result manifests against both verified plan and population. This keeps the schema-to-plan-to-population bindings acyclic while retaining fail-closed equality checks. Each result manifest directly binds source release/population, measurement, eligibility, protocol, plan, and population IDs/versions/hashes.

Each window ID hashes this canonical object: `schema_id=fpdbench.prospective-window`, `schema_version=2.0.0`, match ID, origin sample ID, source-release hash, measurement-state hash, eligibility-policy hash, and protocol SHA-256. It intentionally does not include the plan hash; its containing population manifest does. No old digest is reused or edited in place.

Keep the existing source release and source-population hashes unchanged. Preserve the frozen protocol 20-match set, 12/4/4 role membership and LOMO assignment, 5 s / 3 s time grid, 18 factorial cells, seeds, model and compute rules, descriptive contrasts, target definitions, and evaluator semantics. The two benchmark IDs above remain stable but are bound only under protocol v2.0.0. Recompute every v2 digest only after review; do not guess or pre-freeze hashes in this draft.

Migration creates new v2 authority, population, window, and result artifacts; it never rewrites or relabels a v1 record. Keep explicit v1 loaders/validators and their accepted schemas/hashes unchanged, including the existing population identity and `evaluation_population_authority_v1.schema.json` 1.1.0 and `prospective_experiment_result_v1.schema.json` 1.1.0; v1 code must not fall back to v2 and v2 code must not reinterpret v1 records. Re-enumerate and independently qualify the full 20-match population under v2 before any v2 empirical API can run.

Do not modify any v1 authority/schema bytes or historical locks. This includes the three files `benchmarks/conditional_multi_agent_motion_prediction/lomo_raw_displacement_scientific_lock.json`, `benchmarks/conditional_multi_agent_motion_prediction/public_validation_physical_diagnostic_scientific_lock.json`, and `benchmarks/conditional_multi_agent_motion_prediction/public_validation_raw_displacement_scientific_lock.json`, plus `src/fpdbench/evaluation/absolute_xy_calibration_lock.json`. Keep `benchmarks/reproducibility_snapshot.json` byte-for-byte unchanged at SHA-256 `a22f93f11cf428b7f326a93714fbcc798c99e5d0dbcab5122edb48d050b4a873`; do not regenerate it for v2.

## Required population gate before any empirical run

After independent review and approval of the v2 decision, but before any training, validation checkpoint selection, baseline scoring, LOMO, or final evaluation, independently verify the complete eligible-window population for **all 20 matches** and exact **12 training / 4 validation / 4 evaluation** roles. The protected population build must:

1. Verify pinned source identities and independently enumerate every candidate origin in canonical order, every expected 41-slot support, all exclusions/warnings, and every eligible window. Reconcile two independently authored implementations and stop on any mismatch or unapproved null-flag/finite-XY state.
2. Seal all match-role assignments, candidate and eligible counts, ordered origin IDs, window IDs, eligibility-result digests, both directed scenes, origin player panels, representation-specific truth hashes, and the common truth-mask hash under the v2 authorities.
3. Verify complete source-derived eligible and scoreable populations for every match; the 12/4/4 populations must be complete, and each required match must have scoreable windows. No partial cohort or match omission is accepted.
4. Verify the same windows, scenes, players, and truth masks across all three information regimes and both target representations. Verify future-context masks are deterministic and regime-specific features contain no forbidden target or eligibility data.
5. Independently attest population completeness and rights-safe aggregate reporting. Keep raw bytes, row-level derivatives, per-match restricted receipts, and truth/mask digests outside Git/public artifacts.

If any check fails or a required match has no scoreable window, stop before every empirical run. Aggregate source coverage (including the 70.6064% finite-ball figure) is not evidence of contiguous eligible-window support.

## Exact post-review implementation-file plan

This draft itself is the only proposed repository change for this task. After scientific approval, the v2 authority/parser/eligibility implementation has this exact inventory. The protected population producer and two independently authored enumeration implementations are a separate protected-population gate after the authorities are frozen; no such run or source-derived artifact is included here.

| File | Required change |
| --- | --- |
| `src/fpdbench/data_states/skillcorner_5hz_v2.json` | Add measurement ID/version 2.0.0 and its scientific-state hash. |
| `src/fpdbench/data_states/skillcorner.py` | Add a v2 canonical ball parser and explicit v2 iterator; leave `_canonical_ball` and `iter_skillcorner_5hz` v1 semantics unchanged. Preserve null flag and present-object distinction. |
| `src/fpdbench/data_states/__init__.py` | Export explicit v2 loader/iterator names without changing v1 exports. |
| `src/fpdbench/eligibility/skillcorner_window_v2.json` | Add policy ID/version 2.0.0, exact support/coverage/strata rules, and new reason/warning codes. |
| `src/fpdbench/eligibility/skillcorner.py` | Add v2 manifest validation and evaluator path; leave v1 manifest hash, evaluator, and outputs unchanged. |
| `src/fpdbench/eligibility/__init__.py` | Export explicit v2 API names. |
| `src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction/prospective_skillcorner_protocol_v2.json` | Add protocol v2.0.0 bound to source, measurement v2, and eligibility v2; retain the frozen protocol factors. |
| `src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction/empirical_experiment_plan_v2.json` | Add plan v2.0.0 and bind it to protocol v2; preserve approved execution choices. |
| `src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction/evaluation_population_authority_v2.schema.json` | Require all v2 authority hashes, 20 matches, exact roles, masks, truth-panel digests, and v2 population identity. |
| `src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction/prospective_experiment_result_v2.schema.json` | Require v2 source, measurement, eligibility, protocol, plan, and population bindings; preserve existing semantic result validation. |
| `src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction/prospective_protocol.py` | Add explicit v2 protocol loader/validator and constants; retain v1 loader/hash. |
| `src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction/empirical_experiment_plan.py` | Add explicit v2 plan validation and schema bindings; retain v1 constants and checks. |
| `src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction/evaluation_population.py` | Add v2 population/window/result identities and validators; require complete role-aware population authority before any empirical API can run. |
| `src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction/__init__.py` | Export new v2 validation/loading APIs. |
| `src/fpdbench/validation/repository.py` | Validate the added v2 authority chain while continuing to check historical v1 locks. |
| `pyproject.toml` | Package all six new versioned JSON authority/schema files in wheel and sdist. |
| `docs/skillcorner-data-state-v2.md` | Document v2 field preservation, null semantics, and source-state table without rewriting the v1 contract. |
| `docs/skillcorner-window-eligibility-v2.md` | Document 41-slot eligibility, denominators, warning/exclusion rules, and the eight quality dimensions. |
| `docs/prospective-skillcorner-protocol-v2.md` | Document v2 identities, information regimes, target/mask invariants, and gates. |
| `docs/prospective-experiment-plan-v2.md` | Record the v2-bound frozen execution plan without modifying its v1 authority. |
| `docs/prospective-population-qualification-v2.md` | Specify the separate protected-population qualification record format and stop conditions; never claim a population PASS before evidence exists. |
| `docs/skillcorner-data-card-v2.md` | State v2 authority identity and publication limits without implying row-level data release. |
| `docs/reproducibility.md` | Add the v2 authority path while documenting that the historical v1 snapshot stays unchanged. |
| `README.md` | Link to the additive v2 documentation while retaining the existing v1 authority links. |
| `tests/unit/test_skillcorner_data_state.py` | Add synthetic v2 state-table tests, frame-preservation assertions, and no-null-coercion cases. |
| `tests/unit/test_skillcorner_window_eligibility.py` | Add synthetic coverage/origin/partial-pair/drift/zero-denominator/stratum tests. |
| `tests/unit/test_prospective_protocol.py` | Test v2 authority bindings and unchanged v1 protocol digest. |
| `tests/unit/test_empirical_experiment_plan.py` | Test plan v2 binding and preserved frozen execution-plan factors. |
| `tests/unit/test_experiment_schemas.py` | Test v2 population/result schemas and fail-closed cross-bindings. |
| `tests/unit/test_prospective_population_qualification_v2.py` | Add synthetic completeness, role-assignment, and independent-enumerator parity tests for the separate protected-population gate. |
| `tests/unit/test_prospective_trajectory_metrics.py` | Test that regime-specific future context masks do not change target identity, truth masks, or membership. |
| `tests/unit/test_reproducibility.py` | Assert historical v1 lock/snapshot files and scientific authority bytes remain unchanged; do not regenerate the v1 snapshot. |
| `tests/unit/test_validation.py` | Verify repository validation accepts the complete v2 authority graph and rejects missing/mismatched successor files. |
| `tests/integration/test_cli.py` | Exercise installed-package loading of the six v2 JSON files alongside unchanged v1 APIs. |

The existing `skillcorner_croissant_rai_draft.json` remains explicitly v1; a v2 Croissant/RAI publication artifact is a separate metadata-authority decision and is not implied by this proposal. Add no real-source fixture, row-level derivative, source payload, private truth, model, or empirical score.

The exact later protected-population qualification files are `tools/build_prospective_population_v2.py` (first candidate/window enumerator), `tools/verify_prospective_population_v2.py` (independently authored second enumerator and reconciliation), and the synthetic test above. They run only after v2 authority approval and use restricted external storage for any real-source receipts. They are a separate task and must not depend on unmerged PR #16/#17 code.

## Acceptance-test matrix for the separate implementation

All automated source/eligibility cases use synthetic, source-free input. These tests are proposed acceptance criteria; they are not run or implemented in this documentation-only review.

| ID | Acceptance cases | Required pass result | Test location |
| --- | --- | --- | --- |
| AT-01 | Absent ball; present object with exact keys; z null/finite/invalid; each of true/false/null/missing/invalid flag crossed with both-finite, x-only, y-only, both-null, missing-coordinate-key, nonnumeric, and nonfinite XY | Exact canonical value, mask/count, warning, and error/global-stop outcome matches the decision table; z is validated as nullable/finite before exclusion from output; missing/unexpected keys fail; present-null remains distinct from absent; null is never coerced; simultaneous defects report every applicable code | `tests/unit/test_skillcorner_data_state.py`, `tests/unit/test_skillcorner_window_eligibility.py` |
| AT-02 | 41-slot support at 39/41 and 38/41; finite/missing/partial origin; source-false finite positions; one or two partial/nonfinite states | 39/41 passes and 38/41 fails; origin must have finite XY; source-false finite XY counts; partial XY away from origin is warning-only when thresholds pass; partial origin fails with `BALL_MISSING_AT_ORIGIN` | `tests/unit/test_skillcorner_window_eligibility.py` |
| AT-03 | Complete and gapped support; zero known flags; no finite XY; absent objects; true/false/null cross-tabs; zero or unavailable denominators | Position and known-flag coverage use 41 expected slots; support holes count zero and retain separate temporal exclusions; zero known flags yield known coverage 0 and detected share null; unknown denominator yields null; cross-tabs reconcile and the eight quality dimensions remain unchanged | `tests/unit/test_skillcorner_window_eligibility.py` |
| AT-04 | Null-flag/finite-XY in any support position, including origin and future context | Diagnostic position coverage counts finite XY independently of flag, but the global drift gate stops population construction before membership or model masks; no affected-window filtering or fallback behavior | `tests/unit/test_skillcorner_window_eligibility.py`, `tests/unit/test_experiment_schemas.py` |
| AT-05 | Each of the three information regimes, both target representations, missing future context, and fixed target panels | Future-context masks are deterministic and regime-specific; target IDs, truth masks, and membership are common across regimes and representations; no interpolation, imputation, or forbidden target/eligibility/quality leakage | `tests/unit/test_prospective_protocol.py`, `tests/unit/test_prospective_trajectory_metrics.py`, `tests/unit/test_experiment_schemas.py` |
| AT-06 | Every v2 authority/schema ID, version, file digest, and dependency edge; nested sampling transform identity/version; one-field mutations; v1 artifacts and APIs | Canonical authority hashes and raw schema-byte hashes verify in the specified acyclic order; nested sampling transform stays `skillcorner_source_frame_even_10hz_to_5hz` 1.0.0 with global source-frame parity modulus/remainder 2/0 while measurement state is v2.0.0; any mismatch fails closed; no v1 authority JSON byte, hash, API behavior, lock, or snapshot changes; no v1/v2 fallback or relabeling | `tests/unit/test_skillcorner_data_state.py`, `tests/unit/test_skillcorner_window_eligibility.py`, `tests/unit/test_prospective_protocol.py`, `tests/unit/test_empirical_experiment_plan.py`, `tests/unit/test_experiment_schemas.py`, `tests/unit/test_reproducibility.py` |
| AT-07 | Synthetic 20-match manifest with exact 12/4/4 roles and 12 LOMO folds; one missing required match, wrong role, incomplete fold membership, unequal truth masks, or independent-enumerator mismatch | Only a complete, reconciled 20-match population with exact roles and all required matches scoreable passes; every mismatch blocks; aggregate ball availability never substitutes for candidate/window enumeration | `tests/unit/test_experiment_schemas.py`, `tests/unit/test_prospective_population_qualification_v2.py`; real qualification is a separate restricted population-qualification operation |
| AT-08 | Wheel/sdist and repository validation | All six v2 JSON files are packaged; repository checks validate both v2 bindings and unchanged v1 locks; no source rows, restricted receipts, or model artifacts enter the repository | `tests/integration/test_cli.py`, `tests/unit/test_validation.py` |

## Decision disposition for independent approval

| Decision | Proposed v2 determination | Evidence and status |
| --- | --- | --- |
| 182,950 null-flag coordinate states | Both coordinate keys were present and each value was JSON `null`; the public “both null or missing” cell combines those distinct states. | Restricted receipts for the [nullable-ball source audit](https://linear.app/alignerr-cmj/issue/3ea6850d-aba2-4513-9eea-9497ea54380d) separate `x_state` and `y_state`; read-only receipt-digest/source-identity checks passed, with source-integrity and independent-replication PASS, zero mismatches, and all recorded invariants true. This resolves key presence for the reported retained rows; it does not establish provider semantics. |
| Nullable ball detection | Map source `is_detected: null` to unknown, never false. Preserve true, false, and null distinctly. Do not claim that false means extrapolated for ball detections. | The pinned source audit observed 182,950 null flags and zero null-flag/finite-XY rows. Provider documentation does not define the ball-null meaning. Unknown is the conservative measurement state; approval remains pending. |
| Absent versus present-null ball | Preserve `ball_data: null` as an absent object and a present object with null coordinates as present. Do not collapse, impute, or synthesize either state. | Explicitly represented in the source-state table. The 182,950 observed null-flag rows are present objects with explicit null coordinates. |
| Support, origin, and position coverage | Keep 41 expected slots, including gaps when the span is defined; require a finite XY origin and at least 39 finite XY pairs (0.95 × 41). Count both-finite XY independently of detection attribution. | Frozen v1 protocol retains the 41-sample support; the [independent review of this amendment](https://linear.app/alignerr-cmj/issue/9e3a0b17-9211-4469-b39b-ef266134f707) requires the existing 0.95 threshold and valid origin. Exact window eligibility still requires future population qualification. |
| Partial XY | One finite axis with the other explicitly null is not a 2D position and gets `BALL_COORDINATES_PARTIAL`. It is warning-only unless the finite-origin or 39-of-41 rule excludes the window. A missing coordinate key remains `INVALID_SAMPLE_SCHEMA`. | No partial XY was observed in the pinned retained corpus. The warning/origin/coverage treatment is a prospective rule and requires approval; it does not remove a whole window solely for a partial pair. |
| Null flag with finite XY | Count the finite pair in positional diagnostics, while retaining unknown detection attribution. For this source-locked v2, any such row stops population qualification with `BALL_NULL_FLAG_WITH_FINITE_XY_UNAPPROVED` before eligible membership or model masks are emitted. | The state was unobserved (aggregate count 0). The stop is an explicit conservative scientific choice, not a source fact; independent scientific approval is required. |
| Quality dimensions and denominators | Preserve the eight v1 dimensions. Put flag/coordinate cross-tabs inside `quality.ball_observations`; do not add a ninth window-level dimension. For ratios, a defined denominator with zero numerator yields zero; a zero or unavailable denominator yields null. Apply the exact per-output behavior in the preceding table. | The proposal spells out each numerator, denominator, and zero/unknown case, including position coverage, known-flag coverage/share, outside-pitch fraction, and displacement outliers. `all_false_flag` and `unknown` remain descriptive strata, not provider-semantic claims. Approval remains pending. |
| Future information and leakage | Keep origin target IDs and truth masks common across regimes/representations. Future target truth, masks, membership, eligibility outputs, phase, detection, and quality data are evaluation-only and forbidden model features; future-context masks expose only authorized raw XY availability. | Frozen protocol feature boundary and target contract; the proposal preserves those boundaries under the successor protocol. No empirical data or model results were inspected. |
| Successor identity and migration | Use the exact candidate IDs, schema versions, digest inputs, and binding graph in the identity table. Keep all v1 authorities, historical hashes, locks, APIs, and the reproducibility snapshot byte-for-byte unchanged. | The identity table binds measurement, eligibility, protocol, plan, population, windows, and results. Candidate v2 hashes are intentionally uncomputed until approval and canonical authority files exist. |
| Population sufficiency | Do not infer eligible or scoreable window counts from aggregate XY availability. After v2 approval, independently enumerate all 20 matches with exact 12/4/4 roles and stop if any required match is unscoreable or the independent enumerations disagree. | The restricted population artifact for the [protected population gate](https://linear.app/alignerr-cmj/issue/fe554f95-1ae8-406c-9dd7-a73d91711e51) has not been built or independently qualified; candidate counts and scoreable-window counts remain unknown. This is a separate pre-training gate, not evidence supplied by this proposal. |

## Facts and gates that remain unresolved

- **Independent approval is outstanding.** No independent scientific approval has been submitted for PR #18 or this exact proposal. The fail-closed null-flag/finite-XY stop, partial-XY rule, denominators/strata, and successor identity graph are concrete proposals for that review. Keep PR #18 in DRAFT.
- **Provider meaning remains undocumented.** The source evidence establishes the nullable value and its observed co-occurrence, not what a null ball flag means. The proposal preserves unknown and does not assign extrapolation semantics to false.
- **Null-flag/finite-XY remains unobserved.** Its source count is zero; the population-wide stop is deliberately conservative and requires explicit scientific approval before implementation.
- **The all-source-frame 365,951 null-flag count remains single-path evidence.** The odd-frame count and complete all-frame anomaly taxonomy were not independently replicated; neither is used by this decision.
- **Successor digests do not exist yet.** Compute them only from approved canonical authorities; do not fill the proposed identity table with guessed hashes.
- **Population membership and scoreability remain unknown.** The [protected population gate](https://linear.app/alignerr-cmj/issue/fe554f95-1ae8-406c-9dd7-a73d91711e51) must independently qualify the full v2 population after approval and before training, checkpoint selection, LOMO, or scoring. This PR does not start that work.

## Independent approval checklist

- [ ] Independent reviewer confirms the receipt-backed explicit-null versus missing-key reconciliation without requesting or publishing row-level details.
- [ ] Reviewer approves the complete source-state table, unknown-null treatment, absent-object distinction, partial-XY warning, finite-origin/39-of-41 rule, and the fail-closed null-flag/finite-XY population stop.
- [ ] Reviewer confirms the eight quality dimensions, each exact denominator/zero-denominator rule, and the proposed `all_false_flag`/`unknown` labels.
- [ ] Reviewer verifies the target, eligibility, and quality leakage boundaries and the successor identity/hash dependency graph against frozen v1 authorities.
- [ ] Record independent reviewer identity, date, and exact reviewed HEAD. No source-derived row data, restricted receipts, private historical truth, or model results may be published.
- [ ] Keep PR #18 in DRAFT until approval. After approval, implement the versioned authorities in a separate change without rewriting v1; complete the independent [protected population gate](https://linear.app/alignerr-cmj/issue/fe554f95-1ae8-406c-9dd7-a73d91711e51) before any empirical run.
