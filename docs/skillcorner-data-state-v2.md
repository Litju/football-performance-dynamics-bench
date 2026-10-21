# SkillCorner 5 Hz measurement data state v2

**Identity:** `skillcorner_5hz_v2` 2.0.0
**Schema:** `fpdbench.skillcorner-data-state` 2.0.0
**Scientific-state SHA-256:** `1ecf355b3e6e2f04967e8363c1fdecc7f40707a7dda9966ebee1b3d90e97e671`

V2 is an additive successor to [the frozen v1 measurement](skillcorner-data-state.md). It selects the same globally even source frames at 5 Hz and retains the same match, player, possession, timing, coordinate, and serialization rules. The nested sampling transform remains `skillcorner_source_frame_even_10hz_to_5hz` 1.0.0.

For each retained row, `ball_data` must be present. A JSON `null` value emits canonical `ball: null`. A present object retains `x_m`, `y_m`, and the exact source detection state. Detection `true`, `false`, and `null` remain distinct; null means unknown and is never coerced to false. The provider's meaning for a null ball flag remains undocumented.

Every present ball object must contain exactly `x`, `y`, `z`, and `is_detected`. Validate `z` as null or a finite non-Boolean number even though it is excluded from output. Missing or unexpected keys, missing or invalid flags, nonnumeric coordinates, and nonfinite coordinates fail closed. Explicit coordinate nulls remain null.

| Source state | Canonical representation | Consequence |
| --- | --- | --- |
| `ball_data` is JSON null | `ball: null` | Absent object; no finite XY position |
| Present object, Boolean flag, finite XY | Preserve both coordinates and the exact flag | One position, independent of true/false attribution |
| Present object, null flag, XY unavailable or partial | Preserve object, null flag, and each coordinate state | Unknown detection; no position for partial or null XY |
| Present object, null flag, finite XY | Preserve the finite pair and null flag | Stop source-specific population qualification with `BALL_NULL_FLAG_WITH_FINITE_XY_UNAPPROVED` before membership or model masks |
| Missing `ball_data`, invalid flag/key/value, nonnumeric or nonfinite coordinate | No completed canonical transform | Fail closed; no coercion or repair |

V2 does not interpolate, impute, smooth, or drop source rows to resolve ball missingness. `fpdbench data-states verify skillcorner_5hz_v2` validates this authority without reading restricted source rows.
