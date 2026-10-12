# SkillCorner Open Data source card

**Status:** pinned external source authority for prospective FPD Bench research. This card describes what SkillCorner publishes and how FPD identifies it. It does not grant a right to redistribute SkillCorner files.

## Source identity and attribution

- Provider and source: SkillCorner Open Data, repository [SkillCorner/opendata](https://github.com/SkillCorner/opendata).
- Pinned upstream revision: commit [4340d274572876239c154c90bc507a9b3250a656](https://github.com/SkillCorner/opendata/commit/4340d274572876239c154c90bc507a9b3250a656), requested from upstream master.
- FPD source ID: skillcorner_open_data_v1.
- Source-release SHA-256: e92c417b7640b27399451134ee3fce4b1961b0c0dfc2e01175a8f3c906a9ae07.
- Selected-population SHA-256: e9054b7ddc2dfeff4dd8425ea61a23ed0b326076a08899e47502484228fdbdf4.
- Complete authority-manifest SHA-256: 8b44740efaea01051e3dadfc0111bed284d1d71807266ebe3c1280b408e54107.
- Upstream names SkillCorner as the tracking provider and describes the release as a joint initiative with PySport. Credit SkillCorner as the data provider and acknowledge PySport as the collaborating initiative. Named dataset authors and a formal source citation record are not specified here.

Suggested attribution for research using the public source:

> Data source: SkillCorner Open Data, released by SkillCorner in a joint initiative with PySport. Retrieved from SkillCorner/opendata at commit 4340d274572876239c154c90bc507a9b3250a656. Selected match IDs and file identities are recorded in the FPD Bench source authority. Credit SkillCorner as the data provider and acknowledge PySport as the collaborating initiative.

The repository root is marked MIT, but the license text covers software and associated documentation and does not clearly identify the core tracking, event, phase, and season-aggregate files as licensed data. The current FPD rights decision is **CONDITIONAL GO** for local acquisition and public research processing, with no FPD hosting or redistribution of core source bytes or row-level derivatives pending written clarification. Read [the full rights audit](data-rights.md) for the evidence and artifact-specific policy. Commercial/customer data and credential-gated APIs are outside this public source authority.

## Population and coverage

The pinned source authority selects all 20 indexed matches for which it records the match directory and all four expected files. It excludes no source matches. This membership rule does not claim that any frame or candidate window is eligible for a benchmark.

Selected provider match IDs, sorted for display:

1874553, 1886347, 1899585, 1925299, 1927964, 1953632, 1959846, 1986691, 1996435, 1996436, 2006229, 2006363, 2007448, 2007721, 2010085, 2011166, 2013725, 2015213, 2016236, 2017461.

The authority records competition ID 61, competition-edition ID 870, and season ID 95 for each selected match. The pinned provider README describes a sample of 2024/2025 Australian A-League matches. Recorded match dates span 2024-11-23 through 2025-05-17 UTC, and 13 distinct team names occur in the authority manifest. The source README's prose still says “10 matches”; the pinned match index and file inventory establish the 20-match population used by FPD. The README count is treated as stale documentation.

All 20 matches have match metadata, tracking, dynamic-event, and phase file paths in the pinned tree. The source authority also records some matches with status not_started; they remain selected because all required source files are present. This is source-file coverage, not a claim about tracked duration, complete observations, in-play coverage, or benchmark eligibility.

The three season-aggregate CSVs, optional Body Pose release, and any customer or API data are outside this motion-source population. Body Pose has its own source and rights authority and is not part of this card's source-release hash.

## Source files and fields

| Upstream file | Documented content | FPD treatment |
| --- | --- | --- |
| data/matches.json | Match index and provider match IDs. | Defines the pinned source population together with the per-match inventory. |
| {id}_match.json | Match metadata including lineup, playing time, referee, pitch dimensions, period boundaries, home/away teams, and player roster identifiers. | Supplies match/team IDs, pitch dimensions, player-to-team mapping, participation intervals, and period metadata to downstream validation. Names and other metadata are not copied into the canonical 5 Hz observation schema. |
| {id}_tracking_extrapolated.jsonl | One record per video frame at 10 Hz. Top-level fields: frame, timestamp, period, ball_data, possession, image_corners_projection, player_data. Each player entry has x, y, player_id, and is_detected. Ball entries provide x, y, z, and is_detected. | The 5 Hz measurement uses only the fields documented in the [measurement card](skillcorner-data-card.md). Projection payload and ball z are excluded. |
| {id}_dynamic_events.csv | Provider game-intelligence event rows, including event IDs unique within a game; the provider documents event categories, event coordinates, expected-possession-value measures, and pressure/difficulty measures. | Excluded from the canonical measurement. No event labels are attached to tracking samples or used by window eligibility. |
| {id}_phases_of_play.csv | Phase rows with phase start/end frame information and in-possession/out-of-possession context. The provider says phases are defined while the ball is in play and absent while out of play. | Excluded from the canonical measurement. The separate eligibility policy uses pinned phase intervals as membership-only evidence; uncovered frames mean unknown or uncovered, not confirmed dead ball. |

SkillCorner's pinned README describes tracking as computer-vision and machine-learning tracking from broadcast video. It documents a 10 Hz frame grid, match-clock timestamps at 0.1-second precision, coordinates in meters centered on the pitch, x along the pitch's long side and y along its short side. It does not establish the positive x/y sign directions or a unit/reference for ball z. The measurement preserves provider coordinates and excludes z.

## Acquisition, integrity, and drift

The machine-readable authority is [skillcorner_open_data_v1.json](../src/fpdbench/data_sources/skillcorner_open_data_v1.json). Its acquisition contract requires the full pinned upstream commit, the exact 20-match set, four expected files per match, no missing or unexpected files, and no replacement of the pinned revision with a moving branch.

Integrity checks distinguish the Git tree object from file payloads:

- Ordinary Git files are identified by Git blob SHA-1 and byte size. Raw-byte SHA-256 is also recorded for files inspected during the source audit.
- Each tracking JSONL path is a Git LFS pointer. Its Git blob SHA-1 identifies only that pointer; the pointer's LFS SHA-256 and declared byte size identify the tracking payload.
- Dynamic-event and phase CSVs are ordinary Git blobs. Their payload rows were not fetched for the source-authority audit.
- The 20 tracking payloads were not fully downloaded during the source-authority audit. Their payload integrity is checked only when they are acquired locally and verified against the recorded LFS object ID and size.

Use the source tool to verify an external checkout:

    uv run fpdbench sources verify --local-root /path/outside/fpdbench

This checks the exact inventory and local file identities; it does not download or copy files. The optional live check,

    uv run fpdbench sources verify --live

checks the pinned tree, index, blobs, LFS pointers, default-branch drift, and the separate Body Pose revision. Drift is reported; the pin is never silently advanced. Regular verification of the checked-in authority is offline.

## Quality caveats and unknowns

SkillCorner documents erroneous tracking points and imperfect player identities, and asks users to apply speed or acceleration smoothing/control where appropriate. Its README gives an approximate “around 97%” player-identity accuracy statement. This is a provider-level statement with no defined observation-level confidence or uncertainty field; FPD has not independently measured source accuracy and does not treat that value as a per-player or per-frame score.

The public tracking schema does not provide per-observation identity probabilities or covariance. Provider extrapolations are marked with is_detected=false. Occlusion, camera-view variation, confusing player appearances, absent records, null coordinates, and phase-annotation gaps can affect downstream completeness and interpretation.

Known from the pinned source authority: 20 match IDs, expected per-match file presence, competition and season identifiers, match-date range, provider-described competition context, and file identities. Not measured in the checked-in repository: total source frame counts, observed missingness rates, player/ball detection proportions, complete phase coverage, eligible-window counts, demographic representation, or empirical tracking errors. No such counts or rates are inferred from file presence.

## Intended and unsupported uses

The source is intended by SkillCorner to support research and sports analytics. FPD's prospective use is offline research on movement representation, tracking-aware estimation or forecasting methods, and reproducibility of the pinned transformation.

These data are not validated for individual player grading, recruitment, selection, compensation, contract, medical, betting, surveillance, law-enforcement, or live tactical decisions. They do not support sensitive-trait inference or claims of individual ability from this draft. These are FPD research-governance non-uses; they do not purport to add terms to SkillCorner's license.

The 20-match sample comes from one competition edition and season and is subject to provider availability, team, league, geographic, camera, and tracking-coverage selection. Generalization to other competitions, levels, regions, genders, age groups, or operating conditions has not been established.

## Privacy and ethics

Player trajectories describe identifiable people in a specific professional-sport context. A match-scoped provider ID is not a cross-match FPD athlete identity, but trajectories may be re-identified by linking them with public video, team sheets, or other match context. FPD does not claim that the source is anonymous or that re-identification is impossible.

The reviewed public source does not establish participant consent, an ethics review, a data-protection impact assessment, retention rules, or a demographic profile. Their status remains unknown; no consent or ethics approval is asserted by this card.

## Evidence

- Pinned [SkillCorner README](https://github.com/SkillCorner/opendata/blob/4340d274572876239c154c90bc507a9b3250a656/README.md).
- Pinned [SkillCorner source commit](https://github.com/SkillCorner/opendata/commit/4340d274572876239c154c90bc507a9b3250a656).
- [FPD immutable source authority](skillcorner-source-authority.md).
- [FPD rights audit and release policy](data-rights.md).
- [FPD 5 Hz measurement and eligibility card](skillcorner-data-card.md).
