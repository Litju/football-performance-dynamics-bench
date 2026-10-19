# Prospective SkillCorner benchmark protocol v2

**Identity:** `skillcorner.prospective_conditional_motion` 2.0.0
**Protocol SHA-256:** `9d0b0fcc5cb072dda8f4f6b6418d4455dc86bef521e8f711a0f4cd2a2f30df3e`

The protocol binds the pinned SkillCorner release and source population to `skillcorner_5hz_v2` and `skillcorner_window_v2`. The source release and source-population hashes are unchanged. The two benchmark IDs retain their names and advance to version 2.0.0 under this successor protocol.

The frozen 20-match population and exact 12 training / 4 validation / 4 evaluation roles remain unchanged, as do the 12 LOMO folds, 5-second history, 3-second horizon, target panel, metrics, and four descriptive contrasts. Target truth masks and window membership must be common across all information regimes and both target representations.

The authorized regimes remain:

- `history_only`: history target-team, opponent-team, and ball XY with their observation masks.
- `future_ball`: the same history plus future ball XY and its observation mask.
- `future_opponent_plus_ball`: the same history plus future ball and opponent XY with their observation masks.

Ball position masks equal one only for both-finite XY and are independent of detection attribution. An unobserved null-flag/finite-XY source state stops population qualification before a future-context mask can be emitted. Future target truth, target masks, target membership, eligibility, phase, detection, quality, numeric IDs, and row order remain forbidden learned features.

Protocol v2 is a design and implementation authority. It does not qualify the real 20-match population or authorize model training, checkpoint selection, LOMO, or empirical scoring. See the [protected population gate](prospective-population-qualification-v2.md).
