# Prospective SkillCorner-backed FPD Bench data card

**Status:** R4 research and metadata draft. This card describes pinned source and scientific contracts, not a public row-level data release. No SkillCorner rows, reconstructed samples, eligible-window records, or derived fixtures are included in this repository or its wheel.

The Python wheel packages the JSON-LD draft and machine-readable source, measurement, and eligibility authority files as metadata. These metadata contracts are not distributions of tracking records or eligible windows.

## Dataset identity and authorities

| Layer | Repository authority | Frozen identity |
| --- | --- | --- |
| Upstream source | [Source authority](skillcorner-source-authority.md) and [machine-readable source manifest](../src/fpdbench/data_sources/skillcorner_open_data_v1.json) | skillcorner_open_data_v1; release hash e92c417b7640b27399451134ee3fce4b1961b0c0dfc2e01175a8f3c906a9ae07; upstream SkillCorner/opendata commit 4340d274572876239c154c90bc507a9b3250a656 |
| Canonical measurement | [5 Hz data-state contract](skillcorner-data-state.md) and [machine-readable data-state manifest](../src/fpdbench/data_states/skillcorner_5hz_v1.json) | skillcorner_5hz_v1 version 1.0.0; hash 4c29471c7fccc037dcfafd30222991e06d150e0887c0b667918bfa374262c6c3 |
| Window eligibility | [Eligibility contract](skillcorner-window-eligibility.md) and [machine-readable eligibility manifest](../src/fpdbench/eligibility/skillcorner_window_v1.json) | skillcorner_window_v1 version 1.1.0; hash f0e1186f765cc7ce19c95152d8d6eacc66382f7e7f5a9ad1aa11c88c8a12f70b |

These are separate identities. The source hash binds upstream population and file identities. The data-state hash binds the 10 Hz to 5 Hz measurement semantics. The eligibility hash binds the candidate-window rules. They must be read from their repository authorities and are cross-checked by tests. Eligibility does not change the measured state.

The Croissant JSON-LD draft is [skillcorner_croissant_rai_draft.json](../src/fpdbench/data_sources/skillcorner_croissant_rai_draft.json). Its metadata version is 0.1.0-draft; it is not an FPD content-release version. The dataset page URL currently points to the project repository. No public data download URL is asserted.

## Source-established facts

SkillCorner describes the upstream source as 10 Hz player and ball tracking generated from broadcast video using computer vision and machine learning. The provider README identifies a sample of 2024/2025 Australian A-League matches and a joint SkillCorner/PySport initiative. Its pinned match index and source inventory contain 20 selected matches. The README prose still says 10; FPD population identity follows the pinned index and inventory, not that stale count.

The pinned source population has 20 match IDs: 1874553, 1886347, 1899585, 1925299, 1927964, 1953632, 1959846, 1986691, 1996435, 1996436, 2006229, 2006363, 2007448, 2007721, 2010085, 2011166, 2013725, 2015213, 2016236, and 2017461. Every selected ID is backed by the source authority's match index, directory, match metadata, tracking path, dynamic-event file, and phase file. Inclusion indicates source-file availability only.

The manifest records one competition ID (61), one competition-edition ID (870), and one season ID (95). It records dates from 2024-11-23 through 2025-05-17 UTC and 13 distinct team names. Some provider match metadata is status not_started; those IDs remain selected because the required source files exist. These values describe source coverage, not complete tracking, eligible windows, or representativeness.

The three season-aggregate CSVs and optional 3D Body Pose source are separate materials and are excluded from this motion-source identity. No commercial/customer feed or credential-gated API data is included in these authorities.

## FPD measurement decisions

The canonical measurement applies a deterministic selection to the pinned source:

- Retain only provider source rows where the global frame number is even. The source frame is never reset at a period boundary; canonical_sample_index is source_frame // 2.
- Select source observations directly to reduce the documented 10 Hz frame grid to 5 Hz. Do not interpolate, smooth, average, or synthesize frames.
- Preserve source period and timestamp. Convert HH:MM:SS.cc to integer deciseconds only when the timestamp lies on the documented 100 ms clock. A null timestamp or period stays null.
- Keep provider x/y values as binary64 coordinates in meters, pitch-centered, with x along pitch length and y along pitch width. Do not round, rotate, or attack-direction normalize. The positive axis signs are not specified by the pinned provider documentation.
- Carry match-specific pitch length and width, provider home/away team IDs, and match ID. The ball z field is excluded because the source documentation does not establish its unit or reference.
- Preserve provider detection flags. false is extrapolation and remains distinguishable from missing coordinates.
- Preserve roster-mapped player team/group context and provider possession context. Do not attach event or phase labels to measurement records.
- Reject invalid source structure, non-finite coordinates, and malformed frame/time relationships rather than repairing them. Canonical serialization is deterministic UTF-8 JSON with sorted keys and no NaN or infinity.

### Source-to-canonical field map

| Upstream fields | Canonical field or treatment |
| --- | --- |
| tracking frame | source_frame, plus canonical_sample_index = source_frame // 2 |
| tracking period | period, provider value or null |
| tracking timestamp | timestamp_deciseconds, exact integer conversion or null |
| tracking player_data[].player_id, x, y, is_detected | players[].player_id, x_m, y_m, is_detected; roster adds team_id and home/away group |
| tracking ball_data x, y, is_detected | ball.x_m, ball.y_m, ball.is_detected; a null source ball remains null |
| tracking possession group, player_id | possession.group and possession.player_id, preserving nulls |
| match id, home_team.id, away_team.id | match_id, home_team_id, away_team_id |
| match pitch_length, pitch_width | pitch_length_m, pitch_width_m |
| match players[].id and team_id | Current-match roster crosswalk to assign each observed player to a provider team and home/away group |
| match match_periods | Provenance and downstream validation metadata; not used by the measurement transform to select samples |
| tracking image_corners_projection and ball_data.z | Excluded |
| dynamic_events.csv and phases_of_play.csv rows | Excluded from measurement records; phase intervals are used only by the separate eligibility gate |

### Canonical record fields and entities

One conceptual canonical record is one retained observation for a match and source frame. It carries the four frozen identities and hashes where specified by the data-state manifest, match and period context, the source frame, canonical sample index, match-clock timestamp, home/away team IDs, pitch dimensions, the observed player list, ball state, and possession state.

Player IDs are provider identifiers scoped to a match. A player is emitted only in frames where the source lists that player. No FPD cross-match athlete identity is created. Within a frame, players are sorted by player ID; team_id and home/away group come from the match metadata roster.

Player and ball x/y are metric coordinates. Explicit null x or y is preserved component-wise. A missing player row remains absent; it is not padded from the roster. A null ball object remains null. Possession can be null, and a null possession player remains null. These conditions are not interchangeable.

## Window eligibility contract

Eligibility version 1.1.0 evaluates a supplied candidate support sequence over the pinned 5 Hz state. It returns hard exclusion reasons, non-repairing warnings, quality measurements, and composable strata. It does not change observations, select a final benchmark population, define a fixed forecast history/horizon, or assign evaluation splits. Each call provides positive history and future interval counts; support contains history + future + origin samples at 0.2 seconds each. The origin is included in history.

Hard gates and thresholds:

- Every support sample must have at least seven finite-x/y player positions from each team. The seven-player floor is FPD policy, informed by the Laws of the Game; it is not a SkillCorner threshold. Finite provider extrapolations count toward this floor.
- The ball must have finite x/y at the origin and valid positions for at least 95% of support samples. A finite extrapolated ball position counts.
- Each sample must have a verified period range from pinned match metadata. Period ranges are half-open. The window must remain in one period and have exact canonical/source-frame and timestamp continuity; no gaps are tolerated.
- The full 10 Hz source-frame span from the first through last retained 5 Hz sample must be covered by positive phase intervals. Intervals are interpreted as half-open. Any uncovered source frame excludes as PHASE_NOT_IN_PLAY_OR_UNKNOWN because the format cannot distinguish dead ball from incomplete phase annotation.
- Every annotated phase type, including set_play, counts as in-play. Active-player expectations come from match metadata playing_time.by_period intervals with the frozen inclusive end convention; absent or null player positions are missing against the active roster. The dynamic-event file does not define the substitution signal used here, so player-ID changes remain warnings and are never stitched.
- Possession is not a hard gate. Null possession is reported as unknown.
- Player positions outside the pitch are retained with warnings. Player and ball coordinates beyond their gross limits cause exclusion: one pitch-dimension multiple for players and two for the ball. Displacement warnings use advisory thresholds of 12 m/s for players and 50 m/s for the ball; no positions are repaired.
- Identity changes retain a warning; IDs are not stitched. Unknown source-quality and incomplete appearance metadata remain unknown rather than being classified as poor.
- Future observations and future phase/quality information are membership-only. Eligibility outputs are not permitted as model inputs.

Hard-exclusion reason codes in the frozen policy:

BALL_COVERAGE_BELOW_MINIMUM, BALL_MISSING_AT_ORIGIN, CANONICAL_FRAME_MISMATCH, COORDINATE_IMPLAUSIBLE, DUPLICATE_PLAYER_ID, DUPLICATE_SAMPLE, INSUFFICIENT_FUTURE_SUPPORT, INSUFFICIENT_HISTORY_SUPPORT, INVALID_DETECTION_FLAG, INVALID_MATCH_METADATA, INVALID_SAMPLE_SCHEMA, NONFINITE_COORDINATE, NONMONOTONIC_SAMPLE_ORDER, OUTSIDE_PERIOD_BOUNDS, PERIOD_BOUNDARY_CROSSED, PHASE_INTERVAL_INVALID, PHASE_MATCH_ID_MISMATCH, PHASE_SOURCE_IDENTITY_MISMATCH, PHASE_NOT_IN_PLAY_OR_UNKNOWN, PERIOD_BOUNDS_CONFLICT, PERIOD_BOUNDS_DUPLICATE, PERIOD_BOUNDS_INVALID, PERIOD_BOUNDS_MISSING, PLAYER_COUNT_BELOW_TEAM_MINIMUM, PLAYER_TEAM_IDENTITY_CONFLICT, TEMPORAL_GAP, TIMESTAMP_DISCONTINUITY, TIMESTAMP_MISSING, WINDOW_SUPPORT_LENGTH_MISMATCH.

Warning codes in the frozen policy:

BALL_COORDINATES_MISSING, BALL_DISPLACEMENT_OUTLIER, BALL_OUTSIDE_PITCH, IDENTITY_TRANSITION_EXPOSURE, PLAYER_APPEARANCE_METADATA_UNKNOWN, PLAYER_COORDINATES_MISSING, PLAYER_DISPLACEMENT_OUTLIER, PLAYER_OBSERVATION_MISSING, PLAYER_OUTSIDE_APPEARANCE, PLAYER_POSITION_OUTSIDE_PITCH, POSSESSION_CONTEXT_UNKNOWN, POSSESSION_PLAYER_UNOBSERVED, SOURCE_QUALITY_UNKNOWN.

Composable quality-stratum dimensions are player detection exposure, ball detection exposure, player completeness, ball completeness, temporal continuity, identity-transition exposure, source-quality uncertainty, and play context. The denominators come from support positions, active-roster metadata, continuous intervals, phase frame coverage, or possession samples as documented in the policy manifest. Unknown is separate from poor.

No candidate windows have been enumerated from source payloads in this work. Eligible-window counts and observed quality distributions are therefore unknown.

## Source quality, missingness, and limitations

SkillCorner documents that some tracking points are erroneous and that player identities are not perfect. Its pinned README says around 97% of supplied player identities are accurate; the source does not define this as per-frame confidence. FPD has not independently assessed that aggregate provider statement. No observation-level confidence, identity probability, or covariance field is established in the tracking schema.

Potential missingness and measurement issues include absent player records, explicit null coordinates, null ball frames or ball coordinates, source extrapolations, timestamp or period gaps, annotation gaps, identity transitions, and camera-view or occlusion effects. These are preserved or surfaced under the contracts; this draft gives no rates for them. The provider suggests applying speed or acceleration smoothing/control for some downstream use, but FPD's canonical measurement does not add smoothing.

The 20 selected matches represent one provider release, competition edition, and season. They cannot establish generalization to other leagues, regions, playing levels, age groups, genders, teams, camera systems, or collection conditions. No performance results or model behavior are presented.

## Intended uses and non-uses

Recommended use is offline methodological research on football movement data, tracking-aware estimation and forecasting, measurement reproducibility, and quality-aware evaluation. The proposed FPD work is not a player-ranking product or an operational decision system.

FPD recommends against using this draft or any future benchmark derived from it for individual hiring, scouting, selection, compensation, contract, medical, betting, surveillance, law-enforcement, or live tactical decisions; demographic or sensitive-trait inference; or unsupported claims of a named player's skill, fitness, health, or future performance. These are governance non-uses and limits of validity, not a statement of SkillCorner's license terms.

## Population, privacy, and ethics

Known source population facts are the 20 selected match IDs, one competition/edition/season ID tuple, the source date span, and the 13 team names recorded by the authority. Unknown or uncomputed facts include source row counts, measured missingness and detection rates, eligible-window counts, demographic distributions, participant consent status, and empirical tracking accuracy.

Tracking trajectories concern real professional players. Provider IDs remain match-scoped, but trajectories plus public video, team sheets, team names, match IDs, and timing may permit re-identification. The canonical measurement omits player names and does not create cross-match identity; it does not guarantee anonymity.

The reviewed public materials do not establish a consent basis, ethics approval, data-protection impact assessment, or anonymization procedure. Demographic, age, gender, health, and other sensitive-trait fields are not established or inferred. No fairness estimate can be made from this draft.

## Rights, distribution, citation, and publication blockers

The current operational rights decision is **CONDITIONAL GO** for local acquisition and public-research processing using the public source. The repository-level MIT license covers SkillCorner software and documentation, but its treatment of core tracking, dynamic-event, phase, and aggregate data is unresolved. FPD policy therefore prohibits hosting or redistributing raw core rows and row-level derivatives, including canonical 5 Hz observations and windowed records, until SkillCorner confirms the scope in writing.

The source citation/attribution is the pinned SkillCorner Open Data repository and commit, with SkillCorner credited as provider and PySport acknowledged as collaborating initiative. The underlying code license is not represented as a dataset license. The future FPD code-license decision is separate from data rights. A separate R8 publication task owns final publication, approved creator/authorship details, formal citation, DOI, publication date, and archive metadata; none is invented here.

The JSON-LD declares Croissant 1.1 and Croissant RAI 1.0 and includes the source-population inventory, conceptual measurement schema, eligibility-contract metadata, PROV-O provenance, and supported RAI fields. It deliberately does not populate schema.org license, distribution, or datePublished:

- No FPD row-level data artifact is currently distributable, so no truthful Croissant FileObject/FileSet distribution can be declared. Official SkillCorner URLs identify upstream source files and are acquisition pointers, not FPD distribution URLs.
- The core source-data license scope is unresolved. The repository MIT code marker is not assigned as a dataset license.
- No FPD content release has been published, so there is no truthful dataset publication date.
- The variable conceptual observation fields have no field-level FileObject, FileSet, or DataSource. No distributable FPD file exists, and an upstream URL alone would not express the canonical downsampling and data-state rules as a supported Croissant extraction.

Croissant 1.1 requires license and distribution, requires dataset-level datePublished, and requires a source on operational fields. Their omission is an explicit R4 publication blocker. The metadata URL is the FPD project repository, not a data download URL. No DOI, citeAs entry, or fabricated citation is included.

## Responsible AI coverage

The JSON-LD uses the Croissant RAI 1.0 vocabulary for collection process and source, collection type, missing-data semantics, imputation, data manipulation, preprocessing, intended uses, limitations, biases, sensitive information, potential social impact, and release maintenance. It states when collection details, demographics, consent, quality measurements, and population counts are unknown. The full narrative cards distinguish provider-established facts, FPD policy choices, and unverified empirical properties.

### Validation record

The repository metadata test parses the JSON-LD document, checks the declared Croissant and RAI terms, field IDs, key/data references, types, and cross-bindings to the three repository authorities. The test passes. The official [mlcroissant 1.1.1 validator](https://github.com/mlcommons/croissant) was also run with:

    uvx --from mlcroissant mlcroissant validate --jsonld src/fpdbench/data_sources/skillcorner_croissant_rai_draft.json

It parsed and inspected the metadata but returned a nonzero result. It reported 13 conceptual observation fields without a supported source/value binding, including four fixed identity fields for which the JSON-LD provides cr:value declarations that this validator did not recognize. The remaining variable observation fields have no source because there is no row-level FPD file. It also reported four errors parsing the specification's array shape string (-1,). The validator's array-shape parser does not accept the Croissant 1.1 form. It warned that its built-in context differs by the keys path, replace, repeated, and samplingRate, and warned that license, datePublished, and citeAs are absent. The first two are deliberate publication blockers; citeAs is omitted because no final citation or DOI exists. The official Croissant 1.1 specification defines arrayShape (-1,) for a one-dimensional array, so the validator's array-shape errors are recorded as a validator limitation, not corrected by changing the metadata away from the specification.

The validator does not report distribution among its current findings, but Croissant 1.1 declares distribution required. It also treats datePublished as recommended, while the specification marks it required. The metadata is therefore not full Croissant 1.1 conformance and must not be presented as a downloadable release. The standards references are the [Croissant Format Specification 1.1](https://docs.mlcommons.org/croissant/docs/croissant-spec-1.1.html) and [Croissant RAI Specification 1.0](https://docs.mlcommons.org/croissant/docs/croissant-rai-spec.html).

## Related authorities

- [SkillCorner source card](skillcorner-source-card.md).
- [Rights audit and policy](data-rights.md).
- [Source acquisition and file identities](skillcorner-source-authority.md).
- [Canonical 5 Hz measurement contract](skillcorner-data-state.md).
- [Window eligibility contract](skillcorner-window-eligibility.md).
- [Results and provenance model](results-and-provenance.md).
