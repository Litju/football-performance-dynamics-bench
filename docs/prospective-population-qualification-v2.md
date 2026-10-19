# Protected prospective population qualification v2

The v2 population manifest is a restricted runtime artifact, not a checked-in dataset. Its schema is `fpdbench.prospective-evaluation-population` 2.0.0. Each population and result manifest must bind the pinned source release and source population, measurement v2, eligibility v2, protocol v2, and plan v2.

The authority requires all 20 protocol matches in canonical order with their exact training, validation, and evaluation roles; candidate and eligible counts; ordered window membership; two directed scenes per window; origin-player panels; representation-specific truth hashes; common truth-mask hashes; and canonical membership and manifest digests. `ball_null_flag_finite_xy_count` must equal zero. A nonzero count fails the entire population with `BALL_NULL_FLAG_WITH_FINITE_XY_UNAPPROVED`.

Before any empirical run, two independent enumerators must reconcile every candidate origin, expected 41-slot support, exclusion, warning, eligible window, target mask, and scene. Every required match must have scoreable windows, and windows, scenes, player panels, and truth masks must agree across the three regimes and both target representations. No partial cohort, match omission, or row filtering may substitute for the complete population.

This repository contains only synthetic acceptance fixtures. No real-source population, restricted receipt, source row, row-level derivative, truth digest, or model result was produced or committed. The separate protected-population qualification task remains open; training, checkpoint selection, LOMO, and scoring remain blocked until it passes.
