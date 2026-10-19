# SkillCorner prospective window eligibility v2

**Identity:** `skillcorner_window_v2` 2.0.0
**Schema:** `fpdbench.skillcorner-window-eligibility` 2.0.0
**Policy SHA-256:** `ed1cdc20ca7a93040fd4aabc91655819c5c4b8c58021c6540c6aaea325dafa11`

V2 evaluates windows over `skillcorner_5hz_v2`. A candidate has 41 expected slots: 25 history intervals, the origin, and 15 future intervals. At least 39 slots must have both finite ball coordinates, and the origin must have finite XY. Source-false finite positions count toward positional coverage. A partial XY pair is not a 2D position and produces `BALL_COORDINATES_PARTIAL`; origin and the unchanged 39-of-41 threshold decide eligibility.

Position and detection attribution use separate counts. Position coverage is both-finite XY divided by 41 expected slots. Detection counts are over all 41 slots, including absent objects and source-sample gaps. Known-flag coverage is `(true + false) / 41`; it is zero when no Boolean flag is observed and null when the support span is unavailable. Detected share is `true / (true + false)` and is null with no known flags. No false flag is described as extrapolated.

The quality payload reports counts by flag state and coordinate state. Coordinate states are `both_finite`, `x_only`, `y_only`, `both_null`, `object_absent`, and `source_sample_missing`. Flag states are true, false, null, absent-object/N/A, and missing-source/N/A. The cross-tab reconciles to 41 expected slots. Zero numerators with a defined denominator produce zero; zero or unavailable denominators produce null.

Any retained v2 sample with null detection and finite XY triggers the source-specific population-wide `BALL_NULL_FLAG_WITH_FINITE_XY_UNAPPROVED` stop. Preserve canonical samples and restricted aggregate diagnostics, then stop before eligible membership or model masks. Do not filter only affected windows or continue qualification.

`validate_ball_population_drift_v2` returns untrusted scan diagnostics only. Seeing all 20 match IDs, even with the expected total count, cannot prove exhaustive retained-frame coverage, immutable input identity, or independent replay. `evaluate_skillcorner_window_v2` rejects these diagnostics and all caller-constructed objects. It remains blocked until the separate qualification task implements an independent verifier for exhaustive protected receipts. Synthetic tests exercise the private candidate mechanics without creating qualification evidence.

All eight window-quality dimensions remain unchanged: player detection exposure, ball detection exposure, player completeness, ball completeness, temporal continuity, identity transition exposure, source-quality uncertainty, and play context. Player floors, participation, identity transitions, pitch and temporal rules, positive phase coverage, warnings, and the information firewall retain their frozen v1 semantics. Detection, quality, eligibility reasons, future target values, and target masks are not model features.

Verify with `fpdbench eligibility verify skillcorner_window_v2`. V2 candidate counts and match scoreability remain unknown until the separate protected population qualification passes.
