# SkillCorner 5 Hz measurement data state

- **Data state:** `skillcorner_5hz_v1` (`1.0.0`)
- **Source:** [`skillcorner_open_data_v1`](skillcorner-source-authority.md), release `skillcorner_open_data_v1:sha256:e92c417b7640b27399451134ee3fce4b1961b0c0dfc2e01175a8f3c906a9ae07`
- **Data-state hash:** `4c29471c7fccc037dcfafd30222991e06d150e0887c0b667918bfa374262c6c3`
- **Schema/identity manifest:** [`skillcorner_5hz_v1.json`](../src/fpdbench/data_states/skillcorner_5hz_v1.json)
- **Transform:** [`skillcorner.py`](../src/fpdbench/data_states/skillcorner.py)

This is a prospective measurement-state definition. It does not define benchmark window eligibility, quality thresholds, event/dead-ball filters, targets, information boundaries, splits, evaluators, or model training. Those decisions remain downstream. The source rights policy permits local research processing but does not permit FPD to commit source rows or row-level derivatives while the core data-license scope remains unresolved.

## Pinned source semantics

The transform is tied to `SkillCorner/opendata@4340d274572876239c154c90bc507a9b3250a656`; it does not follow a moving branch. SkillCorner's [pinned README](https://github.com/SkillCorner/opendata/blob/4340d274572876239c154c90bc507a9b3250a656/README.md) describes tracking as video frames at 10 fps, match-clock timestamps with 0.1-second precision, period labels, player and ball data, and coordinates in meters centered on the pitch. It defines x along the pitch's long side and y along its short side. The per-match metadata carries pitch dimensions and the home/away roster IDs. The README's “10 matches” prose is stale; source population and identity come from the pinned source authority's index/tree.

The pinned tracking records use `frame`, `timestamp`, `period`, `player_data`, `ball_data`, `possession`, and `image_corners_projection`. Player records carry `player_id`, x/y, and `is_detected`; the per-match roster maps those player IDs through `players[].id` to `team_id`. The tracking `frame` is a video-frame number and is not reset at period boundaries. Timestamp strings are represented as `HH:MM:SS.cc`; only values on the documented 100 ms source clock are accepted. The source documentation does not specify positive x/y sign directions, so the transform preserves their provider values without interpreting the signs.

The tracking schema was cross-checked against the pinned match metadata and a bounded byte range from one pinned tracking file. No complete match payload was acquired, and no source rows are checked in; tests use FPD-authored synthetic frames only.

## Spatial and temporal contract

- Player and ball x/y remain physical meters with the provider pitch-center origin and length/width axes. Pitch dimensions are carried per match in meters. Coordinates are not normalized, clamped, rotated, or attack-direction-normalized.
- Keep source frames with `source_frame % 2 == 0`. The parity anchor is the absolute provider video-frame number, not the first row or the current period. There is no interpolation, smoothing, or averaging.
- `canonical_sample_index = source_frame // 2`. This is a global 5 Hz video-grid index; it does not reset at a period boundary. A period change restarts timestamp-continuity validation, while the provider period and timestamp values are preserved.
- Source frame numbers must be nonnegative and strictly increasing across the match. Duplicate or decreasing frame numbers fail. Missing source frames create gaps in the canonical index; no row is synthesized. Within adjacent source rows with the same non-null period and non-null timestamps, the decisecond timestamp difference must equal the source-frame difference. Inconsistency fails without repair.
- The source match clock is converted exactly to integer `timestamp_deciseconds`; null source period/time values remain null. No sample time is inferred from another row.

## Entities and missingness

Each emitted record contains the data-state/source identities, match ID, source period/frame, canonical index and timestamp, provider home/away team IDs, match pitch dimensions, players, ball, and possession.

- A player appears only if present in that source frame. Player IDs remain match-scoped provider IDs; there is no cross-match athlete identity. Team ID and `home`/`away` group come from that match's provider roster mapping. Player records are sorted by player ID for deterministic serialization.
- Preserve x/y values and `is_detected`, including extrapolated source observations with `is_detected=false`. No detection filtering is applied.
- A null source ball remains JSON null. For a ball object, x/y and `is_detected` are kept; the undocumented z coordinate is excluded. Explicit null x/y values stay null.
- A null possession object remains null; otherwise its source group (`home team` or `away team`) and player ID are retained exactly as auxiliary context, including a null player ID. Other group values are rejected. Possession is not interpreted as an eligibility rule or future information boundary.
- NaN and infinity fail. No absent player, ball, coordinate, or possession value is imputed or forward-filled.

## Source field contract

| Source field | Classification | Canonical treatment |
| --- | --- | --- |
| `tracking.frame`, `period`, `timestamp` | Canonical measurement/index values | Frame copied; period copied; timestamp converted to integer deciseconds or null. |
| `tracking.player_data[].player_id`, `x`, `y`, `is_detected` | Canonical measurement values | Preserve ID, metric x/y and detection flag; add match-scoped team ID/group from roster metadata. |
| `tracking.ball_data.x`, `y`, `is_detected` | Canonical measurement values | Preserve metric x/y and source flag; preserve null ball/coordinates. |
| `tracking.possession.group`, `player_id` | Retained auxiliary/context metadata | Copy current source value, including nulls. |
| `match.id`, `home_team.id`, `away_team.id`, `pitch_length`, `pitch_width` | Canonical match metadata | Carry provider IDs and match-specific metric pitch dimensions. |
| `match.players[].id`, `team_id` | Retained auxiliary/context metadata | Used only to map current frame player IDs to their match team/group. Names and identities do not leave the match scope. |
| `match.match_periods` | Provenance-only metadata | Records source period/frame boundary definitions; not used to select samples or define eligibility. |
| `tracking.image_corners_projection`, `tracking.ball_data.z` | Excluded | Not emitted. The source docs do not define the ball z unit/reference. |
| `dynamic_events.csv`, `phases_of_play.csv` | Excluded | Neither file is read by this transform; no event or phase label is attached to a measurement sample. |
| Other match metadata fields, including names, scores, dates, lineups, kits, coaches, roles, cards, status, and `home_team_side` | Excluded | They do not enter canonical samples or orient the coordinates. |
| Pinned source release IDs and immutable source file identities | Provenance-only | Bind the input authority; source rows and file paths are not copied into the data-state manifest. |

## Numeric identity and serialization

Coordinates and pitch dimensions are Python binary64 floats in meters. The transform converts source JSON integers/floats to binary64 without rounding; Python's shortest round-trip decimal form is used when serialized. IDs, frame numbers, canonical indices, periods, and integer decisecond timestamps serialize as JSON integers. Explicit missing values serialize as `null`; NaN and infinity are rejected.

Each sample serializes as UTF-8 JSON without a BOM or trailing newline, with sorted object keys, compact separators, `ensure_ascii=false`, and `allow_nan=false`. Player arrays are sorted by `player_id`. The `data_state_hash` is SHA-256 over canonical compact JSON of the manifest's `scientific_state` object only. Descriptive wording, local paths, hostnames, and timestamps are outside that object and do not change the identity.

Verify the offline manifest with `uv run fpdbench data-states verify`; list and inspect it with `uv run fpdbench data-states list` and `uv run fpdbench data-states describe skillcorner_5hz_v1`. The transform accepts source-frame iterables and one match metadata object, yields samples incrementally, and performs no network access.

No source or derived row payloads are committed. Tests use FPD-authored synthetic frames only. The historical R0–R3 reproducibility snapshot and identities remain unchanged.
