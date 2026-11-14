# RES646 execution boundary

The existing RES635 supervisor now runs `RealWorkload` through the existing source-stream,
checkpoint, scoring and verification interfaces. Production remains dormant without a separately
signed owner approval verified against the protected, out-of-repository owner Ed25519 trust file.
No production key or GO is created by this change. Fixture keys authenticate only the distinct
`RES646-SYNTHETIC-v1` namespace and invented inputs.

`CampaignPlan` describes metadata and scope without granting access. `Campaign` verifies canonical
approval bytes, the frozen authorization schema, expiry, signer fingerprint, code/runtime,
source inventory, checkpoint manifest, admission, four matches, resource ceilings, ledger and
output directory identities. Real source/checkpoint opens require the reserved supervisor's
single claimed worker. Start, worker, supervise, continuation, verify and status share that check.
The stable owner-private ledger is outside the output tree and its directory identity is signed.
The ledger's exclusive-create reservation survives crashes. HMACs in output are integrity aids;
the protected owner key and separately bound ledger provide authority.

Each source match undergoes its identity/drift pass before inference. Real source and population
lock hashes must match the signed inventory. A second, independent raw reader derives eligibility,
truth, masks, player order and quality. Independent features are compared before the one forward
call per window/cell. Separate metric arithmetic audits those same predictions. The receipt binds
all 18 records, denominators, provenance and audit. The supervisor records four ordered receipt
seals in the trusted ledger, verifies all 72 records and recomputes aggregates before completion.
Verification and signed-campaign continuation never call a learned model again. Legacy unsigned
RES643/RES645 fixture behavior is retained for its existing parity tests.

The supervisor charges launcher/setup, decoding, model loading, inference, independent verification
and final sealing against cumulative CPU/wall/RSS/disk ceilings. It rejects resource exhaustion
permanently. Only one predeclared, outcome-blind continuation at a verified match boundary is
possible, using the existing independent interruption evidence policy. Unknown, scientific and
integrity failures are terminal. The owner UID and operating-system protections of the ledger
remain the local process trust boundary; this does not sandbox arbitrary malicious Python code.

The signed local configuration uses schema `fpdbench.res646.campaign/1`. Synthetic qualification
uses `fixture_bundle`; real configuration uses the four ordered `matches` (match ID, directory,
separate locked path, eligible count and four source-file hashes), `checkpoint_directory`,
`receipt_directory` and `admission`. Both bind `namespace`, `ledger_root`, `output` and
`independent_report_sha256`. Ledger/output directories must already exist privately so their
device/inode identities can be frozen. Approval files beside `campaign.json` are
`campaign.approval.json` and `campaign.approval.sig`. Only synthetic mode reads
`campaign.synthetic-signers`; production obtains its signers exclusively from protected system
trust. None of these owner-local files belongs in the repository.

The separate metadata-only command is:

```console
python -m fpdbench.benchmarks.conditional_multi_agent_motion_prediction.res646_preflight \
  --owner-config <private-config> --evidence <existing-private-evidence> --report <private-report>
```

It preserves prior readback evidence without reopening source rows, deserializing checkpoints or
reserving a scope. Missing config and target resource attestations remain explicit blockers.
An old text report is never promoted into a new attestation. Production key provisioning is
separately deferred until independent review; it is not needed to qualify synthetic execution.

A complete run returns `RES646_GATE5_READY_FOR_INDEPENDENT_REVIEW` and exit 0; missing
configuration returns `MISSING_OWNER_LOCAL_CONFIG`, and failed or incomplete qualification
returns `RES646_GATE5_BLOCKED` (both exit 2). Readiness requests independent review, and does
not assert its acceptance. The CLI prints only disposition and missing field names. The complete
report, including diagnostic paths, must be written into an existing owner-private directory.

The prior metadata evidence must use `fpdbench.res646.gate5-evidence/1`. It identifies its verifier,
method, current UTC observation time, frozen identities, exact code/runtime, and approved read
scope. `GATE5_READ_SCOPE` is the canonical SHA-256 of that scope: the six configured paths,
source root, independent source metadata, intended four scoring match specifications, resource report, and `metadata-only-no-source-or-model-bytes` policy. Inventory
bytes must match the frozen admission's inventory hash. Evidence retains independently verified
hashes and contemporaneous device/inode/size/mtime/ctime identities for all 81 source files,
18 frozen checkpoints and 18 verified fit receipts. Current metadata must match those identities;
new stat observations cannot retroactively establish unchanged bytes after an old readback.
The metadata-only preflight now records current inode/stat observations separately and
preserves prior SHA-256 results as historical expected-content evidence. Missing old stat
bindings are disclosed, not manufactured. The separately signed Gate 6 source/checkpoint
read boundary must hash and compare the actual permitted bytes before the first learned
forward pass; any mismatch remains terminal.
Checkpoint and receipt paths use an exact signed digest-to-existing-filename mapping.
The loader accepts only one unique bare-hash or verified prefixed name for each of the
18 checkpoints and 18 completed-fit receipts. The checkpoint directory has no extra
files; the receipts directory may retain unrelated auxiliary records. No originals
are moved, renamed, hard-linked, or reselected. The map is frozen in the signed
campaign configuration and the actual bytes are verified again at authorized use.
The four intended scoring matches additionally require 16 independently verified normalized
input/lock identities. Their metadata/tracking hashes match the original source inventory;
normalized phases match the independent source report pinned by admission, and lock hashes match
both admitted producer/verifier artifacts. Only `O_PATH` inode inspection touches these 133 data,
checkpoint and receipt files; no contents are opened. Exact checkpoint/receipt directory entries
must match the loader as well. The successful report emits the concrete campaign configuration;
constructing `CampaignPlan` from it produces the same identities and proposed execution scope.

Qualification also checks empty ledger/output directories with the executor-required exact 0700
mode, writable filesystems, tree/inode isolation, cgroup
ancestor limits, CPU affinity, actual filesystem capacity and inode availability, and current
independent quota evidence bound to UID, device and mount-table identity. Missing quota evidence
fails closed. The final-code signed synthetic resource report is read by its exact hash. Its
largest population supplies a linear estimate and a 2x sensitivity scenario against the unchanged
14,400 CPU-second, 21,600 wall-second and 2 GiB RSS/transient limits. This scenario is not a proven
bound on unseen real bytes. The owner-private report retains every assumption and Gate 6 condition.
See `test_res646_preflight_qualification.py` for the complete invented evidence contract.

## Approval expiry and archival verification

Every fresh reservation, supervisor attempt, continuation, and worker entry requires an unexpired
signed approval. Each reservation and continuation records its authorization time in the
independently MAC-authenticated ledger. A running worker checks expiry at every scoring check;
expiry raises an integrity failure at the next existing check and is permanently terminal.
An in-flight window can finish; the next window cannot start. This is a check-boundary policy,
not a wall-clock interrupt of a tensor operation.
It neither adds a grace period nor extends continuation rights or cumulative limits.

Historical verification authenticates the original signature and checks those ledger times fall
inside the signed validity interval, in chronological order and no later than the verification
clock. It also checks the existing seals, accounting, frozen identities and scientific audit.
The current clock may be later than approval expiry. Constructing or inspecting a historical
Campaign grants no permission to reserve, resume, open scoring inputs, or perform inference.
