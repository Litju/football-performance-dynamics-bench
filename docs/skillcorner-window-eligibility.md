# SkillCorner prospective window eligibility

- **Policy:** `skillcorner_window_v1` (`1.1.0`)
- **Policy manifest:** [`skillcorner_window_v1.json`](../src/fpdbench/eligibility/skillcorner_window_v1.json)
- **Evaluator:** [`skillcorner.py`](../src/fpdbench/eligibility/skillcorner.py)
- **Source release:** `skillcorner_open_data_v1:sha256:e92c417b7640b27399451134ee3fce4b1961b0c0dfc2e01175a8f3c906a9ae07`
- **Measurement state:** `skillcorner_5hz_v1` (`1.0.0`), hash `4c29471c7fccc037dcfafd30222991e06d150e0887c0b667918bfa374262c6c3`
- **Eligibility-policy hash:** `f0e1186f765cc7ce19c95152d8d6eacc66382f7e7f5a9ad1aa11c88c8a12f70b`.

This policy evaluates whether one candidate support sequence is eligible and returns reason codes, warning codes, provenance, quality measurements, and composable quality strata. It does not change or repair the 5 Hz state. It does not set benchmark targets, model inputs, evaluation splits, a final candidate-window population, or the intended history/horizon. Each call supplies positive integer history and future intervals at 5 Hz; support is `history_intervals + future_intervals + 1` samples, with the origin included in history.

## Source evidence and limits

The pinned SkillCorner README describes 10 Hz video-frame tracking, match timestamps, player and ball coordinates, and the binary player `is_detected` flag. It says that `is_detected=false` denotes extrapolation and warns that tracking points can be erroneous and player identities are not perfectly accurate. Its approximately 97% identity-accuracy statement is aggregate documentation, not an observation-level confidence score. No per-frame confidence, covariance, or identity-probability field is defined in the pinned schema. ([Pinned SkillCorner README](https://github.com/SkillCorner/opendata/blob/4340d274572876239c154c90bc507a9b3250a656/README.md))

The pinned match metadata contains `match_periods` frame bounds and player `playing_time.by_period` start/end frames. Its `match_periods.duration_frames` matches `end_frame - start_frame`, so period bounds use `[start_frame, end_frame)`. Player participation intervals do not carry that duration field; this policy keeps their frozen inclusive end convention. Missing, malformed, duplicate, conflicting, or overlapping match-period definitions hard-exclude a candidate, and each sample must have a verified bound for its period. The dynamic-event specification does not document a substitution event field, so entries and exits come only from participation intervals. ([Pinned match metadata schema/example](https://github.com/SkillCorner/opendata/blob/4340d274572876239c154c90bc507a9b3250a656/data/matches/2017461/2017461_match.json), [SkillCorner Dynamic Events CSV specification](https://26560301.fs1.hubspotusercontent-eu1.net/hubfs/26560301/Guides/Dynamic%20Events/20250216%20-%20Dynamic%20Events%20CSV%20Specifications.pdf))

SkillCorner's pinned README says phases are defined only while the ball is in play and that no phase is present while it is out of play. The specification defines `frame_start` and `frame_end` as frames associated with phase start and end; in the pinned CSV, `duration` reconciles with `(frame_end - frame_start) / 10`, and adjacent rows share boundaries. FPD therefore interprets intervals as half-open `[frame_start, frame_end)`. This positive-only format has no explicit dead-ball row, so a gap cannot distinguish confirmed out-of-play exposure from incomplete annotation. We label it `uncovered_or_unknown`, require coverage of every 10 Hz source frame from the first through the last retained sample, and hard-exclude any gap. No tolerance is allowed. Every annotated phase type, including `set_play` and `chaotic`, remains in play. ([Pinned SkillCorner README](https://github.com/SkillCorner/opendata/blob/4340d274572876239c154c90bc507a9b3250a656/README.md), [Phases of Play CSV specification](https://26560301.fs1.hubspotusercontent-eu1.net/hubfs/26560301/Guides/Phases%20of%20Play/20250216%20-%20Phases%20of%20Play%20CSV%20Specifications.pdf), [Pinned phases-of-play CSV](https://github.com/SkillCorner/opendata/blob/4340d274572876239c154c90bc507a9b3250a656/data/matches/2017461/2017461_phases_of_play.csv))

Dynamic-event and phase files are separate from `skillcorner_5hz_v1`; the canonical measurement-state contract excludes their row labels. The evaluator accepts phase frame intervals from the pinned phase file and player participation from pinned match metadata as membership-only annotations. It does not use event rows. This follows the [measurement-state contract](skillcorner-data-state.md) and the [source acquisition and rights contract](skillcorner-source-authority.md). The unresolved core-data redistribution restriction in [data-rights.md](data-rights.md) still applies; this repository contains no SkillCorner or derived row-level records.

## Frozen rules

### Support and time

- Candidate support must contain exactly `history_intervals + future_intervals + 1` canonical samples. Both lengths must be positive; no duration is hardcoded.
- All support must belong to one match and one non-null period, and every sample must lie within a unique, verified match-metadata period range `[start_frame, end_frame)`. Missing, malformed, duplicate, conflicting, or overlapping period definitions hard-exclude the candidate.
- The source frame must have the frozen even-frame parity, canonical indices must advance by one, source frames by two, and timestamps by two deciseconds (0.2 s). Duplicates, ordering errors, gaps, missing timestamps, and discontinuities exclude the candidate with separate codes. Period changes exclude the candidate; clocks are not compared across periods.
- No missing frame is synthesized and no timestamp is inferred.

### In-play and possession context

- A phase interval is identified by pinned source-release ID, match ID, period, `frame_start`, and `frame_end`, and covers `[frame_start, frame_end)`. An interval from another source/match or one with zero or negative duration is rejected.
- Every 10 Hz source frame from the first through the last retained 5 Hz sample must fall in at least one phase interval. A single uncovered source frame excludes the candidate as `PHASE_NOT_IN_PLAY_OR_UNKNOWN`, including a gap between retained 5 Hz samples. This continuous-span rule prevents a 10 Hz annotation gap from being hidden by 5 Hz downsampling. No dynamic-event, possession, score, restart, or event label is used to infer a phase.
- The pinned format has no explicit dead-ball annotation, so FPD cannot distinguish a confirmed dead-ball gap from incomplete phase annotation. Both remain uncovered/unknown; only positive phase coverage is evidence of in-play. The pinned file identity detects source drift, not annotation completeness.
- A source phase of `set_play` remains eligible because it is a ball-in-play phase. Other phase labels do not create extra filters.
- Tracking possession is never a hard gate. Home/away possession counts and unknown/null possession counts are reported descriptively. Null is unknown, not a third team or a negative label.

### Players, missingness, substitutions, and identity

- For every support sample, at least seven valid player positions from each team are required. This is an FPD policy floor, informed by the Laws of the Game minimum of seven players per team; it is not a SkillCorner quality threshold and does not define the final task's target set. The total minimum is consequently fourteen. ([IFAB Law 3, 2025/26](https://www.theifab.com/laws/2025-26/the-players/))
- A valid position has finite x and y values. A source player record with a null coordinate is present but has no valid position. A player absent from the sample is a missing record relative to the active roster. Neither condition is filled, forward-carried, or interpolated.
- Active-player expectations come from match metadata `players[].playing_time.by_period`. A finite extrapolated source position (`is_detected=false`) counts toward the seven-player floor and is counted separately from direct detections. This preserves the measurement state's source distinction without inventing confidence or silently discarding extrapolations.
- If metadata intervals are incomplete, active-player completeness and substitution exposure are `unknown`; they are not reported as poor. Observed coordinates remain eligible for the per-team floor.
- Entry/exit exposure is a change in the active match-scoped player-ID set across adjacent samples. It produces `IDENTITY_TRANSITION_EXPOSURE` and a transition stratum, but does not exclude a window. Source player IDs are never stitched, remapped, or treated as continuous across substitutions. A player record outside its metadata playing-time interval is a warning and is not counted toward the per-team floor.

### Ball and coordinate quality

- At least 95% of all support samples must have a finite ball x/y position, and the origin sample must have a valid ball position. This FPD threshold allows up to 5% missing ball samples while anchoring the candidate at the origin; it does not impute nulls. Extrapolated ball positions count as positions and have a separate exposure count.
- Positions outside the physical pitch rectangle are retained with warnings because players and the ball can be beyond the lines. A much wider corruption guard excludes a player only when `abs(x) > pitch_length` or `abs(y) > pitch_width`; for the ball the limits are twice those dimensions. These broad FPD bounds are sanity guards, not source confidence limits.
- Adjacent 5 Hz displacement above 12 m/s for a player or 50 m/s for the ball is retained with an outlier warning. The thresholds are advisory anomaly screens; no coordinate is smoothed, clamped, or deleted. Non-finite coordinates and positions beyond the gross bounds exclude the window with explicit reasons.

These thresholds are fixed before model results. Any change to decision behavior requires changing the scientific policy and its version, which changes the policy hash. Descriptive metadata and documentation edits do not change that hash.

### Quality strata and denominators

Strata are composable: each window gets one category for each dimension.

| Dimension | Strata | Measurement denominator |
| --- | --- | --- |
| `player_detection_exposure` | `all_detected`, `mixed`, `all_extrapolated`, `unknown` | Finite player positions. |
| `ball_detection_exposure` | `all_detected`, `mixed`, `all_extrapolated`, `unknown` | Finite ball positions. |
| `player_completeness` | `complete`, `partial`, `none`, `unknown` | Active player-frames from metadata; numerator is active records with finite coordinates, whether detected or extrapolated. Incomplete metadata yields unknown fraction. |
| `ball_completeness` | `complete`, `partial`, `none`, `unknown` | Every support sample, including the origin. |
| `temporal_continuity` | `continuous`, `discontinuous`, `unknown` | Numerator is consecutive same-period frame/index/timestamp intervals; denominator is expected history and future intervals. Incomplete support is unknown, while detected gaps or timestamp faults are discontinuous. |
| `identity_transition_exposure` | `exposed`, `none_observed`, `unknown` | Numerator is adjacent active-roster ID sets that change; denominator is all expected support intervals, when metadata and support are complete. |
| `source_quality_uncertainty` | `unknown_per_observation` | No per-frame confidence is supplied; this is always unknown, not poor. |
| `play_context` | `all_in_play`, `uncovered_or_unknown`, `unknown` | Every 10 Hz source-frame index from the first through the last retained sample, inclusive. |

The result reports numerator, denominator, and fraction for each derived measure where the denominator is known. Detection exposure uses finite positions; player completeness uses active player-frames from metadata; ball completeness and possession context use all support samples; phase coverage uses every 10 Hz source-frame index in the full retained-sample span; outside-pitch exposure uses finite entity positions; displacement outliers use adjacent same-entity pairs with valid positions and exact temporal continuity; null-coordinate frequency uses observed player records; substitution exposure uses expected adjacent support intervals with complete active-roster metadata. An unavailable denominator yields `null`, not zero. Missingness never becomes a numeric zero coordinate.

## Exclusions and warnings

Hard exclusions are explicit `EligibilityIssue` records with a code, sample index where available, and a stable explanation. They include insufficient history/future support, invalid sample or match metadata, source/data-state mismatch, wrong canonical parity, missing/invalid/duplicate/conflicting period bounds, period crossing/out-of-bounds samples, any uncovered source frame in the full phase span, fewer than seven valid players on either team, missing origin ball, ball coverage below 95%, non-finite/grossly implausible coordinates, duplicate player IDs, team identity conflicts, duplicate/non-monotonic samples, temporal gaps, missing timestamps, and timestamp discontinuities.

Warnings retain the candidate and record source uncertainty, missing/null player records, extrapolation through measurements, null possession, player appearance mismatch, substitution/identity transition exposure, outside-pitch coordinates, and advisory displacement outliers. Eligibility is true only when the exclusion list is empty; the list is never reduced to an opaque validity flag.

## Information boundary

Future positions, future phase coverage, and future quality are inspected only to decide evaluation membership and calculate these audit strata. The result object is evaluation metadata and must not be joined into prediction features. Prediction inputs may use only history and the separately frozen information boundary; the policy neither defines nor widens that boundary. Policy identity is distinct from source release, measurement state, benchmark identity, and future window-membership identity. This evaluator creates no membership digest or final fixture manifest.

Verify the policy offline with `uv run fpdbench eligibility verify`. Tests use only FPD-authored synthetic samples and metadata.
