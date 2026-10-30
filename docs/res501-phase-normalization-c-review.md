# Phase normalization C review candidate

`fpdbench.skillcorner.phase-period-intersection` version `1.0.0` is an isolated
normalizer, not an activated source-preflight contract. Each valid explicitly labeled
row intersects only its labeled metadata period, using half-open bounds. Unlabeled
rows must be wholly contained in exactly one period. The normalized output is sorted;
lineage retains source row order and multiplicity, original and normalized bounds,
empty intersections, and SHA-256 identities of the original CSV, metadata, and
normalized bytes. Lineage is private and must not be committed or published.
The separately labeled B sensitivity output drops each noncontained row entirely;
it is not a membership or model-selection authority.

## Required downstream decision before activation

Ratify a new source-preflight receipt schema and signature namespace that bind the
normalizer identity and version, each pinned raw CSV and metadata digest, normalized
bytes digest, and private lineage digest. Specify canonical serialization, lineage
storage and retention, empty-intersection diagnostics, and independent rederivation
of both artifacts during snapshot verification. Require exact schema/version matching
and reject historical receipts relabeled as the successor. Ratify the changed adapter
package inventory and any corresponding root-owned protected trust policy and reviewer
signature bindings; preserve the existing source inventory, global scan, independent
verification and `SOURCE_PREFLIGHT / NOT_QUALIFIED` gates. Determine and ratify any
scientific authority or population provenance binding needed to identify the changed
mapping before any production activation. Existing signatures and receipts cannot be
reinterpreted as this successor. This document does not amend those authorities.

The handoff's public-source census (17 boundary conflicts in 20 matches, 406 added
source frames and 146 theoretical phase-only origins for C relative to B) is historical
non-authoritative evidence, not a qualification or scoreability result.

## Reproduction and verification

Ordinary pytest uses synthetic inputs and requires no network. Its interval-union
and 25/15 support arithmetic test is synthetic; it is not the public-source census.
To replay the public census, run `uv run python tools/replay_phase_c_census.py
--source-root /path/to/upstream/tree` against an approved local source tree, or use
`--fetch-public` to fetch only the pinned metadata and phase CSV files. The tool
checks each file's pinned Git blob and size, prints only aggregate results, and
compares them to the recorded 20-match, 17/3 conflict, 406-frame and 128/0/18
role-level theoretical-origin expectations. No tracking files are read or downloaded.
Neither these counts nor this tool qualify population membership or scoreability.

`verify_phases_c` accepts independently supplied original CSV and metadata bytes and
compares both normalized output and lineage byte-for-byte with a fresh derivation.
It is an isolated consistency check, not an authentication mechanism: callers must
independently establish source identities and protect the inputs. It does not alter
or invoke the historical source receipt verifier. Tests cover changed source bytes,
lineage rows and identities, output substitution, and self-consistently forged output.
