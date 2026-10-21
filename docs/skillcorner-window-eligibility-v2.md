# SkillCorner prospective window eligibility v2

**Identity:** `skillcorner_window_v2` 2.0.0
**Schema:** `fpdbench.skillcorner-window-eligibility` 2.0.0
**Policy SHA-256:** `ed1cdc20ca7a93040fd4aabc91655819c5c4b8c58021c6540c6aaea325dafa11`

V2 evaluates windows over `skillcorner_5hz_v2`. A candidate has 41 expected slots: 25 history intervals, the origin, and 15 future intervals. At least 39 slots must have both finite ball coordinates, and the origin must have finite XY. Source-false finite positions count toward positional coverage. A partial XY pair is not a 2D position and produces `BALL_COORDINATES_PARTIAL`; origin and the unchanged 39-of-41 threshold decide eligibility.

Position and detection attribution use separate counts. Position coverage is both-finite XY divided by 41 expected slots. Detection counts are over all 41 slots, including absent objects and source-sample gaps. Known-flag coverage is `(true + false) / 41`; it is zero when no Boolean flag is observed and null when the support span is unavailable. Detected share is `true / (true + false)` and is null with no known flags. No false flag is described as extrapolated.

The quality payload reports counts by flag state and coordinate state. Coordinate states are `both_finite`, `x_only`, `y_only`, `both_null`, `object_absent`, and `source_sample_missing`. Flag states are true, false, null, absent-object/N/A, and missing-source/N/A. The cross-tab reconciles to 41 expected slots. Zero numerators with a defined denominator produce zero; zero or unavailable denominators produce null.

Any retained v2 sample with null detection and finite XY triggers the source-specific population-wide `BALL_NULL_FLAG_WITH_FINITE_XY_UNAPPROVED` stop. Preserve canonical samples and restricted aggregate diagnostics, then stop before eligible membership or model masks. Do not filter only affected windows or continue qualification.

`validate_ball_population_drift_v2` returns untrusted scan diagnostics only. Seeing all 20 match IDs, even with the expected total count, cannot prove exhaustive retained-frame coverage, immutable input identity, or independent replay. `evaluate_skillcorner_window_v2` rejects these diagnostics and all caller-constructed objects. It remains blocked until the separate qualification task implements an independent verifier for exhaustive protected receipts. Synthetic tests and installed-package checks use the public candidate diagnostic without creating qualification evidence.

All eight window-quality dimensions remain unchanged: player detection exposure, ball detection exposure, player completeness, ball completeness, temporal continuity, identity transition exposure, source-quality uncertainty, and play context. Player floors, participation, identity transitions, pitch and temporal rules, positive phase coverage, warnings, and the information firewall retain their frozen v1 semantics. Detection, quality, eligibility reasons, future target values, and target masks are not model features.

Verify with `fpdbench eligibility verify skillcorner_window_v2`. V2 candidate counts and match scoreability remain unknown until the separate protected population qualification passes.

## Public candidate diagnostics

`fpdbench.eligibility.diagnose_skillcorner_window_v2(samples, *, history_intervals=25, future_intervals=15, match_metadata=..., phase_intervals=..., policy_manifest=None)` runs the production v2 policy and returns `CandidateWindowDiagnosticV2`. Its fixed `status` is `UNQUALIFIED`, including when `candidate_rules_pass` is true. It reports candidate-level exclusions, warnings, descriptive quality, and pinned policy/source/measurement bindings. It is distinct from `WindowEligibilityResult` and the untrusted scan diagnostics; it has no `eligible` flag. Exact 25/15 horizons and policy validation are mandatory.

A null-flag/finite-XY observation still raises `BallPopulationQualificationStop` at any support offset. Diagnostics emit no population membership or model masks and cannot authorize training, checkpoint selection, LOMO, or scoring. Passing a diagnostic as `population_qualification` to `evaluate_skillcorner_window_v2` is rejected, just like forged counts or incomplete receipts. No protected verifier is implemented here.

## Possession accounting

V2 `quality.play_context.possession_denominator_samples` remains 41. The mutually exclusive `possession_home_samples`, `possession_away_samples`, `possession_unknown_samples`, `possession_missing_samples`, and `possession_invalid_samples` sum to all expected slots. Explicit null possession or a valid observed null group counts as unknown. A missing source slot (including unread support in a truncated candidate) counts as missing, separately from observed unknown possession. A missing required possession key, malformed possession, or sample that fails before possession can be classified counts as invalid. No state is coerced to known or observed unknown possession.

Each category fraction uses 41 when the support span is defined; fractions are null when the span is unavailable. `possession_support_span_available`, `possession_classified_samples`, and `possession_counts_reconcile_to_expected_support` make reconciliation inspectable. Gapped candidates retain `TEMPORAL_GAP`; incomplete or malformed support retains its existing exclusions. Possession stays descriptive and never becomes a hard gate. V1 output and accounting are unchanged. These corrections implement the existing denominator and unknown-handling rules; they change no scientific authority, threshold, or hash.
