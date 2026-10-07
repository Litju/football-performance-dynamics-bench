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
