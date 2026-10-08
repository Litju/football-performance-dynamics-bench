# Reproducibility model

A benchmark identity defines the scientific task. A release, data state, dataset membership, split protocol, evaluator, model checkpoint, experiment, and result each have independent identities. Population semantics describe who or what a task applies to; dataset membership records which observations were used.

A scientific lock hashes only result-bearing benchmark, data, split, evaluator, schema, fixture, and scientific-provenance state. Legal, publication, hosting, artifact-location, and timestamp fields belong to a separate release manifest. Equal benchmark IDs alone do not establish comparable results.

A storage/source cadence change leaves benchmark identity and release compatibility unchanged when canonical values and interfaces remain identical. A canonical grid change can keep the same scientific identity when the target, information boundary, temporal interpretation, and population remain unchanged, but it makes the release incompatible and normally requires a major version. Changes to those scientific semantics may require a new benchmark identity. Conditional motion with realized future opponent and ball context is distinct from causal forecasting with ex-ante exposure information.

## Evidence registry content digest

`tools/registry_content_digest.py` defines the read-only registry digest. The root must be a real directory. It includes every regular file and symlink below the root, including hidden files, and excludes any path containing a `.git` component. It does not include directory entries or follow symlinks; a symlink record hashes the literal link-target bytes. Unsupported filesystem nodes and paths that collide after normalization fail closed.

Each relative path is rendered with `/` separators, normalized to Unicode NFC, and encoded as UTF-8. Records are ordered by normalized UTF-8 path bytes. A regular-file record contains the SHA-256 of its raw bytes. Each record is compact JSON with sorted keys (`kind`, `path`, `sha256`), UTF-8 encoded with `ensure_ascii=False`, followed by one LF byte. The aggregate is SHA-256 over the concatenated record lines.

The pre-reconstruction baseline for `/home/litju/Research-Benchmarks-Registry` is 793 paths and `539f453eedd2e11b5ee5c2346df4c5ee360a04f5daa55e66e0c0810ed7d20511`. Two earlier 793-file reports gave `16b8e3bd97dd155584688b0fcdcc9c326d3407eeb0e4bfa6de3f0f13dafef2b8` and `7bab728177acaba464e590b38e8c633d7f252e042311d3b9022f73cae435863d`. No per-file manifest or hashing procedure for either report survives in the registry or the earlier closeout comment. Six common aggregate serializations over the current path/hash list did not reproduce either value:

- Bare per-file SHA-256 hex values joined by LF: `6d8137eb8b901aa7f0a02d884da3b6a10e65a757bcbbefd3448524d71a0b09e7`.
- Standard `sha256sum` lines (`digest`, two spaces, path, LF): `f6ef03921d75b8fda2f9f1658ff3ae1fb69a6b7e4d551acbd3cb6103707eeb06`.
- Path, NUL, hex digest, LF: `78651f11333eec77d394fa2c3d459836cfd855b5a0c99782e50966442d0d4906`.
- Path, NUL, raw digest bytes, LF: `478f87cf3757c8980f573cc60b9c668cbaccff4f2a8cdf6ec7038a0f29db920c`.
- Compact JSON array of path/digest records: `c725e9617d12b1e2ed9792e00e8a6c372425d3d432e1b480857197b4521f7be2`.
- Canonical NDJSON defined above: `539f453eedd2e11b5ee5c2346df4c5ee360a04f5daa55e66e0c0810ed7d20511`.

The matching path count and aggregate claims alone cannot distinguish a serialization difference from changed bytes, so the earlier discrepancy remains unexplained; this baseline is the first reproducible canonical digest.

Origin-relative displacement raw results use separate public-validation and LOMO scientific locks. Each binds its own split protocol and fixture population, the repaired measurement state, displacement schemas, raw population-SRE semantics, and execution sources. Physical diagnostics and the missing generated-calibration instance/private reward remain outside both locks.

## Canonical conditional-motion split protocols

`fpdbench.protocols` defines the R3 role and LOMO protocols for absolute position and origin-relative displacement. Both benchmarks share the same match-role assignment:

| Role | Matches | Availability |
| --- | --- | --- |
| `PUBLIC_TRAIN` | J03WOH, J03WOY, J03WPY, J03WQQ, J03WR9 | Public |
| `PUBLIC_VALIDATION` | J03WN1 | Public |
| `HISTORICAL_PRIVATE_QUALIFICATION` | J03WMX | Metadata only; truth remains unopened |
| `PUBLIC_TEST` | None | Not defined |

J03WMX is not a public test set and is unavailable to public CI. The protocol exposes the absence of a public test population explicitly. Historical evaluation on J03WN1 is known, while historical model-selection use remains unknown; future experiment records declare model-selection use separately.

Role semantics are shared, while concrete fixture membership is benchmark-specific. The repaired absolute-position public membership has 17,386 training windows/34,772 directed rows and 215 validation windows/430 directed rows. Its original and repaired-state population snapshots have an unresolved row-level crosswalk, so they remain distinct. The displacement fixture has its own target representation, fixture manifest, and split manifest even though its public role counts match. Equal match roles do not imply byte-identical fixture membership.

The R3 protocol IDs are `conditional_motion.match_role_assignment.r3` and `conditional_motion.public_train_lomo.r3`, both version `1.0.0`. They describe future canonical semantics. They do not replace the historical recovered R2 split descriptors or rebind historical ResultRecords.

LOMO uses the five `PUBLIC_TRAIN` matches only and produces five deterministic folds. Each fold trains on the other four matches and evaluates the held-out match. J03WN1 and J03WMX are excluded from every fold. The LOMO split hash covers only fold IDs and held-out match IDs; training seeds and evaluator bindings are separate run/evaluation configuration.

The inferential experimental unit and cross-match aggregation unit are both the physical match. Overlapping windows and the two directed scenes from one physical window stay in the same match role or fold. Evaluators score the full declared match population; population-defined metrics are not recomputed by averaging arbitrary row scores.

Public validation contains one match, J03WN1. Its point estimate is available with `n_match=1`; between-match standard deviation, standard error, and confidence interval are unavailable. The 430 directed rows are measurement rows, not 430 independent matches. Confidence intervals remain absent until a method and population are explicitly declared.

For the historical three-seed by five-held-out-match LOMO table, first average repeated seed results within each held-out match. The primary generalization mean is the equal mean of those five match summaries, and between-match uncertainty uses `n_match=5`. Report seed sensitivity separately across the seed-level means. A balanced grand mean may equal the historical 15-cell arithmetic mean while the inferential match count remains five.

Absolute-position evaluation binds `absolute_position.population_sre_targets`, `absolute_position.per_target_progress`, `absolute_position.historical_continuous_pwl_v3`, and `physical_trajectory.ade_fde_xy_rmse`. Displacement binds `origin_relative_displacement_raw_population_sre` and `physical_trajectory.ade_fde_xy_rmse`; its calibrated scorer remains unavailable. Evaluator identities do not enter either split hash. The historical displacement scientific locks remain `d56ef8e1ff37276e258d516fa9ce26231403222e549296777ee27e5f38cfeedc` and `572e28bb5b4675a1fac91eb7c2c2c9cd4f00b28119aa447dd563c080a704cfd0`.
