# Protected population executor boundary

**State: BLOCKED / NOT_QUALIFIED.** This change hardens source-receipt trust and
snapshot revalidation and strengthens the synthetic producer/verifier package
rehearsal. It does not claim a complete protected population executor or qualify
any population.

## Trust root

Production receipt authentication reads a fixed bundle from
`/etc/fpdbench/protected-executor`; callers cannot supply expected hashes,
allowed-signers files, signer identities, or package pins. The directory and its
files must be root-owned, outside every Git worktree, and not group/other writable.
The opened trust-directory descriptor must also report a local Linux ext/btrfs/xfs
or tmpfs backing filesystem; Windows/9p, network, FUSE, and overlay mounts are
rejected even when bind-mounted beneath /etc. The check uses the opened directory
descriptor rather than trusting its pathname or reported owner alone.
Its files are:

| File | Authority |
| --- | --- |
| `root.allowed_signers` | Host administrator's trusted policy-signing public key(s), principal `fpdbench-policy-owner` |
| `policy.json` | Canonical root-signed execution policy |
| `policy.sig` | SSH detached signature of the exact policy bytes in namespace `fpdbench-res544-trust-policy-v1` |
| `reviewer.allowed_signers` | Reviewer public key(s), with the exact file digest pinned by the signed policy |

The signed policy pins the installed adapter inventory, reviewer principal and
receipt namespace, the PR #20 producer revision and 79-file inventory, the PR #21
verifier revision and 79-file inventory, the 81-file/20-LFS source authority, and
the frozen v2 measurement, eligibility, protocol, plan and schema hashes. It
always requires a signed `SOURCE_PREFLIGHT / NOT_QUALIFIED` receipt. Neither a
receipt self-hash nor a caller-provided digest can create authority.

To rotate or revoke a reviewer key, the host administrator updates
`reviewer.allowed_signers`, removes revoked public keys, increments the policy
generation, lists revoked key fingerprints, signs the canonical policy with the
root key, and atomically installs the bundle. Receipt authentication uses only
the currently installed root-owned bundle. Replacing the root trust key itself
requires a separate host trust-root change and is outside this package.

Tests generate temporary Ed25519 keys and synthetic receipts under temporary
directories only. They test policy and reviewer signatures, signer rotation,
revocation, injection, policy substitution, and source mutation. These keys and
digests are not production trust anchors. No production private key is generated
or stored by this repository.

## Immutable source handoff

The initial adapter checks the complete pinned source inventory, including all
20 resolved LFS payload identities, scans all retained samples for the frozen v2
nullable-ball stop before phase normalization, and emits an unsigned
`SOURCE_PREFLIGHT / NOT_QUALIFIED` receipt. An independent reviewer must sign the
exact receipt bytes. Before population work, `verify_source_snapshot` authenticates
that receipt from the fixed trust root and rechecks source bytes, the global
20-match scan, normalized phases, and the final source inventory. It fails closed
on any discrepancy and emits no population membership or qualification token.

All source and receipt files remain in user-owned 0700 Linux directories, with
exclusive 0600 files, outside Git and Windows mounts. The system trust bundle is
separate and root-owned. Public CI and repository files contain synthetic fixtures
and aggregate-safe contract evidence only.

## Producer and verifier provenance

The original synthetic producer remains pinned to PR #20
`6644dba8c945ca86be72b54792db30cbe488e5d0` with its historical 79-file inventory
digest `153bc67c532b8eddba90a98994d60f656526e71961f17c9d1f2454a72dd2e1a4`. The
independent verifier remains pinned to PR #21
`ef1a22583cdd52bb63509a13bfc480a313ea69d4` with inventory digest
`c61851dd0b930694a960d8cf79046258ea92a8c2cc19db60d33fdbb12f4b6b09`. The
rehearsal builds and runs each wheel in a separate isolated interpreter and now
checks each installed inventory before exchange. The merged monolithic package
is not accepted as the PR #20 producer.

The two pinned APIs still accept complete in-memory match-byte objects, retain
the whole cohort and return whole output artifacts. They are synthetic-only.
They do not satisfy the required bounded-memory per-match/streaming execution
contract, so the trusted boundary deliberately does not route a protected source
snapshot to them.

## Exact blockers

1. Implement separately versioned producer and verifier workers that consume the
   authenticated snapshot with bounded per-match/streaming memory, write protected
   output incrementally, and preserve independent code, protocol, and package
   attestations. The frozen PR #20 and #21 packages remain historical provenance;
   the merged public APIs cannot be relabeled or given a restricted-input bypass.
2. Provision the root-owned policy bundle and owner/reviewer public keys outside
   the repository. No production key, trust file, or protected source is present
   here, so production receipt authentication currently fails closed.
3. Independently review the exact DRAFT PR head and its trust/execution contract
   before any separately authorized real-source run.

No real SkillCorner processing, qualification PASS, training, checkpoint
selection, LOMO, scoring, or release was performed or authorized by this work.

## Synthetic validation

At the implementation head, the full suite passed **529 pytest tests**. Ruff,
format checking, strict Pyright, repository/naming validation, evidence validation,
and reproducibility passed; the public snapshot remains
`a22f93f11cf428b7f326a93714fbcc798c99e5d0dbcab5122edb48d050b4a873`. Wheel and
sdist builds passed the isolated installation smoke. The pinned producer/verifier
rehearsal reconciled **60 synthetic candidates** with three negative controls and
`NOT_QUALIFIED`. These synthetic results do not establish real-source coverage or
population qualification.
