# RES-646 execution boundary

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
An old text report is never promoted into a newly signed success. The existing owner-local
configuration currently leaves all seven fields empty. Production key provisioning is separately
deferred until independent review; it is not needed to qualify synthetic execution.
