# RES338 owner-authorized private cloud research handling

**Status:** approved by the project owner for this campaign on 2026-11-04.
**Scope:** the frozen 18-fit `per_target_context_deepsets_mlp_v1` campaign only.

This amendment supersedes the FPD local-only handling rule in `data-rights.md`
only for private processing and storage by the owner in the owner's access-
controlled Google Colab and Google Drive accounts. It does not amend SkillCorner's
license, establish a redistribution right, or apply to other FPD work.

SkillCorner's [public Open Data documentation](https://skillcorner.github.io/opendata/)
describes the corpus as open sourced for research and links to Google Colab
tracking tutorials. The [pinned repository README](https://github.com/SkillCorner/opendata/blob/4340d274572876239c154c90bc507a9b3250a656/README.md)
describes a joint open-data release for researchers and asks users to credit
SkillCorner. The [pinned repository license](https://github.com/SkillCorner/opendata/blob/4340d274572876239c154c90bc507a9b3250a656/LICENSE)
is MIT but describes its subject as software and associated documentation; the
scope for core data files remains unresolved. The official pinned materials
reviewed contain no express prohibition on this specific private research
computation. This records the owner's authorization and FPD's controls without
claiming that upstream redistribution rights have been clarified.

## Permitted handling for this campaign

- Download only the pinned source files for the twelve frozen training matches
  and four validation matches directly from the official SkillCorner repository
  into the Colab VM's local `/content` disk. Verify every file against the pinned
  source manifest before use. Do not stage evaluation-match source files or labels.
- Build and use the frozen feature caches and validation labels in the private
  Colab VM. Do not print rows, labels, predictions, or tensor values to notebook
  output or logs.
- Persist content-addressed training/validation feature caches, environment and
  configuration manifests, checkpoints, receipts, progress indexes, and aggregate
  results in the owner's private Drive folder. The folder and all descendants must
  remain owner-only, with no link-based or public sharing.
- When a private cache archive exceeds the connected Drive file-transfer limit,
  split it into content-addressed 64 MiB chunks. Persist the ordered chunk manifest,
  verify each chunk by SHA-256 readback, and verify the reassembled archive hash.
- Keep downloaded raw source and temporary intermediate files on Colab local disk
  only while cache construction and verification require them. Remove them from
  the VM after verified cache construction. They are not copied from WSL to Drive.
- Retain the research-admission binding
  `a8c82bfa09ac792d6c4ae779d4b28158c33ed3c2500f8548f3e94d48197f4fd1`, source
  commit, per-file source SHA-256 values, scoped role manifest, and attribution to
  SkillCorner and PySport with the private evidence.

## Excluded uses

This amendment does not authorize public or third-party hosting, publication, or
redistribution of raw source files, row-level derived data, feature caches,
predictions, or checkpoints. Public GitHub, CI, Linear, and notebook output may
contain only code, source references and hashes, environment details that reveal
no credentials, and non-reconstructive aggregate validation results. No held-out
evaluation or learned LOMO data may enter the runtime. The protected population
gate remains unchanged.

The owner retains the Drive folder. The agent must confirm its private sharing
state before upload and after each evidence write. If the upstream source presents
an express term barring this private processing, stop before transferring the
affected bytes and record that source verbatim in the private recovery ledger.
