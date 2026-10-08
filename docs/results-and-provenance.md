# Results and provenance

Scientific locks identify the benchmark, repaired data state, split, evaluator,
schema, fixture, and immutable source snapshot. `ScientificStateBinding`
references that verified lock in each experiment or result. A run manifest adds
the system, run configuration, model-selection declaration, environment, and
artifact references. A result manifest adds structured metrics, population,
validity, uncertainty, outputs, and evidence. Legal, publication, and hosting
state belongs in `PublicReleaseManifest` and never changes scientific identity.

## Run identity

`ExperimentManifest` (`fpdbench.experiment-manifest`, `1.0.0`) requires a
verified scientific binding, `SystemIdentity`, a SHA-256 run configuration
identity, an explicit selection declaration, environment fingerprint, artifact
declarations, and execution provenance. Learned systems can carry checkpoint,
architecture, and training-configuration digests; unknown historical
configuration stays absent. Historical model-selection use stays `UNKNOWN`.

`EnvironmentFingerprint` (`fpdbench.environment-fingerprint`, `1.0.0`) hashes
the runtime version, dependency-lock digest, source revision, and optional
source-tree digest, container digest, and platform/accelerator descriptor.
Run/environment identity excludes timestamps, hostnames, usernames, local
paths, CI URLs, and governance metadata. Artifact byte digests are identity;
artifact URIs are location metadata.

## Result identity

`ResultRecord` (`fpdbench.result-record`, `1.0.0`) requires a lowercase lock
SHA-256. Historical tuple metric keys remain available through `metrics` and
`metric_records`. New `ResultManifest` (`fpdbench.result-manifest`, `1.0.0`)
uses `ResultMetric(metric_id, value, unit)`; its hash encodes each finite value
with `float.hex()`. Output digests and evidence affect result identity, never
the consumed scientific lock.

Historical recovered records use `HISTORICAL_EVIDENCE_BOUND` and retain their
source evidence without fabricated run or environment data. New executed
records use `EXECUTION_MANIFEST_BOUND` and include a complete
`ExperimentManifest`.

## Uncertainty

`UncertaintyReport` (`fpdbench.uncertainty-report`, `1.0.0`) separates
descriptive dispersion, inferential uncertainty, and algorithmic sensitivity.
Its adapters accept the match and LOMO summary types without importing the
protocol module at runtime.

For public validation, one match gives a point estimate, `n_units=1`, and no
descriptive SD, inferential SE, or CI. For leave-one-match-out results,
`n_units=5` and descriptive held-out-match SD are available; inferential SE and
CI remain unavailable because training sets overlap and no dependence-aware
method is declared. Seed sensitivity is a separate summary.

The historical physical-trajectory diagnostics have their own public
validation scientific lock, using the historical match-grouped split and the
physical trajectory evaluator. This keeps ADE/FDE/XY-RMSE separate from the
raw PopulationSRE evaluator while reusing the same repaired data, schema, and
fixture state.
