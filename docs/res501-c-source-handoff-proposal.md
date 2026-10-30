# C source handoff successor proposal

The frozen v2 scientific JSONs remain byte-identical. The production admission gate
remains closed until the independently authenticated, reconciled population exists.
The 400-origin exploratory exclusion matrix is a diagnostic, not membership.

## Exact receipt and policy changes proposed

Retain the historical `fpdbench.protected-source-preflight` 1.0.0 and its verifier
unchanged. A distinct `fpdbench.protected-source-preflight-c` 1.0.0 receipt must
retain its historical status, source inventory, global drift scan, adapter inventory
and frozen authority bindings and add:

* `normalizer: {id: "fpdbench.skillcorner.phase-period-intersection", version: "1.0.0"}`;
* for each match, existing phase path/output SHA-256/source CSV SHA-256/metadata
  SHA-256, plus `lineage_path`, `lineage_sha256` and normalized/lineage byte sizes;
* a distinct detached reviewer signature namespace `fpdbench-res501-source-c-v1`.

The successor root-signed policy must use a distinct schema version and signature
namespace, bind the exact successor receipt and normalizer identities, source adapter
inventory, separately pinned producer/verifier/runtime identities, frozen authority
bindings and authorized reviewer namespace. It must not accept v1 receipts or v1
policy signatures as the C successor. No real keys, trust policy or source data are
created here. Source signatures authenticate the receipt, not eligibility or scoring.

Verification must authenticate that policy and receipt from the independently
controlled trust root; verify the pinned full source inventory and global drift scan;
rederive each C phase and ordered lineage from source CSV and metadata bytes; compare
both exact private artifacts, their sizes and digests, and recheck the inventory. The
C normalizer currently imports private helpers from the historical adapter; integration
must import C only after the adapter is initialized or extract a neutral helper without
changing v1 behavior, to avoid a circular import.

The existing streaming launcher accepts caller-selected paths and is explicitly
synthetic-only. A successor handoff must construct every input path exclusively from
the authenticated selected-match inventory and C receipt, bind the worker's recorded
metadata, tracking and phase hashes and sizes to that receipt, verify the immutable
snapshot immediately before and after the run, and keep output `UNQUALIFIED`. A
path-only preflight check does not establish immutability during consumption. An
independently controlled runtime/immutable storage boundary and separately pinned
worker are needed to make that binding authoritative. The verifier remains separately
authored, and its reconciliation must bind the same snapshot and final artifact digests.
A separately authenticated sidecar can bind receipt and output digests without changing
the existing frozen population JSON schema; no source, measurement, eligibility,
protocol, target, role or scoring authority changes are proposed.

## Synthetic successor implemented

`protected_skillcorner_c` adds the distinct C receipt and `policy-c.json` /
`policy-c.sig`. The policy uses `fpdbench.protected-execution-trust-policy` version
`2.0.0`, root signature namespace `fpdbench-res544-trust-policy-c-v2`, and exactly
the old policy fields plus `normalizer` and `receipt_schema`. Its reviewer namespace
is `fpdbench-res501-source-c-v1`. The old producer/verifier pins, adapter inventory,
frozen authority bindings, generation, revocations and signer checks remain required;
this candidate does not add a trusted runtime manifest to the policy. Changing to the
C policy and provisioning its signatures are external trust decisions, not a rewrite
of the old policy or any scientific authority.

`source_preflight_c` emits the unsigned C receipt and private phase and lineage files;
`verify_source_snapshot_c` authenticates it, rescans the full pinned source, and
rederives and compares both artifacts. `produce_from_snapshot_c` derives input paths
from that receipt, checks the snapshot before and after the synthetic worker, and
compares all worker-recorded input hashes and sizes with the authenticated inventory.
It returns only an `UNQUALIFIED` worker output. A forged worker receipt or compromised
runtime can lie about its inputs: this candidate's same-process check is synthetic
consistency evidence, not a production-authenticated handoff. The existing independent
verifier and empirical gates are unchanged. Before a formal run, the trusted runtime
and immutable handoff must be independently established and the reconciled output
bound to the C receipt; this candidate does not claim to do that.

## Independent synthetic handoff

`synthetic_c_handoff.reconcile_from_snapshot_c` requires the signed C policy to
include `synthetic_runtime` with exactly `launcher_sha256`,
`producer_manifest_sha256`, and `verifier_manifest_sha256`. The field is optional
for standalone C preflight but mandatory for this handoff. It verifies the complete
20-match verifier input tree against the authenticated C receipt and frozen role
order, then launches the pinned historical streaming producer and separately authored
verifier in isolated processes via the existing synthetic runtime launcher. It checks
producer input identities and scan counts against the C receipt, independently hashes
the output artifacts, requires the independent verifier to reconcile every artifact,
and compares the source, input, output, receipt, signed policy, runtime manifests and
launcher identities again after execution. The private `c-handoff.json` records these
bindings with `RECONCILED_NON_AUTHORITATIVE`, `NOT_PERFORMED` and `BLOCKED` statuses.

The preflight and producer use different retained-sample digest serializations, so
those hashes are not compared as though they were the same encoding. Source bytes and
counts are bound to the signed C inventory; the independent verifier derives and
compares its own retained-sample identity and producer receipt. This path uses
synthetic caller-pinned runtime evidence and test-only signatures. It does not establish
an independently trusted production runtime, immutable storage, source rights, or a
qualified 20-match population. The historical production entrypoints and independent
scientific derivation remain unchanged.

Before reading tracking data, the synthetic handoff authenticates the C receipt and
rejects any inventory containing an exact frozen real tracking payload digest. This
prevents this synthetic path from operating on the pinned real cohort; it does not
prove that arbitrary nonmatching data are synthetic. A trusted production runtime and
reviewed storage boundary remain separate requirements, and neither launcher evidence
nor the unsigned synthetic handoff file is a production authenticity claim.
