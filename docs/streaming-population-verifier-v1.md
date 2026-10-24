# Independent streaming population verifier v1

`streaming_population_verifier_v1.py` is an independently authored verifier for
the synthetic population artifacts from PR #25. It is versioned separately as
`res544-streaming-population-verifier/1.0.0`. Its implementation imports only
Python standard-library modules and reads the frozen source, measurement,
eligibility, protocol, plan, and population-schema JSON authorities directly.
It pins their file and scientific hashes and verifies the protocol's exact 12/4/4
match roles.

The verifier authenticates the synthetic producer source package against 13
code-pinned file digests and the identity
`c3a81aa35599608711be85e3eacd9946bdd762937ef1bd08431a88ba415d20fc`. The
producer receipt is treated as untrusted evidence: recalculating its own hash
cannot change that identity. Executable-runtime attestation remains a separate
mandatory gate and is `NOT_PROVIDED`; the report always keeps the runtime gate
`BLOCKED`.

Before reconciling membership or truth, the verifier reads every raw 10 Hz
tracking row for all 20 pinned matches, reconstructs retained 5 Hz samples, and
checks the global nullable-ball-flag finite-coordinate drift gate. It then
enumerates each period grid and replays exact support offsets `-25` through
`+15`, the frozen eligibility policy, warnings, physical truth, displacement,
masks, and scoreability.

Candidate, diagnostic, and truth expectations are written as temporary JSONL
streams. The manifest parser retains one match or window token at a time and
compares the five output artifacts without loading full JSONL files or the
cohort. Mismatch reports retain at most 1,000 record entries while preserving
the complete total and per-category counts. Each record report includes its
identity and expected/actual digests where those sides exist.

Metadata, normalized phases, and tracking inputs are pinned by descriptor-backed
SHA-256 and file identity snapshots. Metadata and phases are rechecked after
the global drift scan, tracking identity is checked before its replay pass, and
all 60 files are rehashed after artifact comparison immediately before the
report is written. Replacement or in-place mutation fails closed with
`INPUT_SNAPSHOT_MISMATCH`.

The fixtures are in
[`tests/fixtures/streaming-verifier-v1`](../tests/fixtures/streaming-verifier-v1/README.md).
CI fetches PR #25's pinned commit, exposes its source package to the tests, and
checks that the branch has not moved. Results are
`RECONCILED_NON_AUTHORITATIVE` only for synthetic reconciliation. This worker
does not produce an empirical qualification PASS and does not authorize
protected-population execution.

## Memory scaling

The measured workers were separate Python processes. `tracemalloc` started
before importing the verifier, RSS used Linux `ru_maxrss`, and each process
received only input/output paths and wrote a small report. It did not load the
artifacts into the measurement harness.

| Synthetic case | Raw source rows | Candidate rows | Five output artifact bytes | Traced peak bytes | Peak RSS bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| `complete_10hz` | 1,720 | 60 | 7,748,751 | 28,601,304 | 45,809,664 |
| `resource_scale` | 17,200 | 1,300 | 38,746,237 | 28,619,610 | 46,215,168 |

The larger case increased raw rows by 10×, candidate rows by 21.7×, and output
bytes by 5×. Traced peak changed by 18,306 bytes and peak RSS by 405,504 bytes.
These figures describe the synthetic CI fixture and this Linux worker; they are
not a protected-population capacity guarantee.

Run locally after making the exact PR #25 package available:

```bash
FPDBENCH_PR25_PACKAGE_ROOT=/path/to/pr25/src/fpdbench uv run pytest
```
