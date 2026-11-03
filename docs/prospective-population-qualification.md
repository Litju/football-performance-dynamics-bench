# Restricted prospective population qualification

**Qualification: FAIL (2026-10-14). No population authority was sealed.**

The pinned source bytes are available, but the frozen measurement transform rejects
them. Construction cannot continue under the current scientific identities. The
[population construction issue](https://linear.app/alignerr-cmj/issue/fe554f95-1ae8-406c-9dd7-a73d91711e51)
remains open for independent scientific review and continues to block the experiment
plan's completion. No empirical execution is authorized.

## Evidence and blocker

The external source checkout was pinned to
`4340d274572876239c154c90bc507a9b3250a656`. All 81 required files (the index and
four files for each of 20 matches) passed source-byte verification. All 20 Git LFS
tracking objects were resolved to actual payloads: 1,823,448,331 bytes in total,
with exact pinned SHA-256 values and sizes. The pinned Git pointer objects were
verified separately. No source bytes were substituted or repaired.

An independent streaming scan of all tracking bytes inspected 1,244,814 source
rows, including 622,414 even-frame rows. It found 182,950 even-frame ball objects
whose `is_detected` is null and whose coordinate pair is missing. Separately,
replaying the existing `iter_skillcorner_5hz` transform against each match failed
with `ball is_detected must be boolean` in **all 20 matches**.

The transform accepts an absent ball object and null coordinates, but requires
a boolean detection flag whenever a ball object is present. Converting these
source objects to null balls, coercing the flag, or skipping their frames would
change the frozen measurement semantics. This implementation does none of those.
The mismatch requires scientific review of the measurement contract before
construction can resume; it is not an acquisition/checksum failure.

The source release, source population, measurement state, eligibility policy,
protocol and experiment plan identities remain unchanged. In particular, the
plan remains v1.1.0, SHA-256
`0446649e1ad049880cf6f8a76b4f3e03421d8bd7a1f7a2c562b5770461527775`, and the
protocol remains SHA-256
`865601662f4462178eaf7e1049075668176a9bd35f3bf4b1b6b8aa370de1d26c`.

## Restricted replay tool

[`qualify_skillcorner_source.py`](../tools/qualify_skillcorner_source.py) strengthens
the existing pointer-or-payload acquisition check by requiring complete tracking
payloads and the pinned checkout revision. It runs an independent raw-schema scan
and the frozen canonicalizer separately for every selected match, rechecks source
identities after processing, and writes receipts only to an empty, user-owned
0700 directory outside the FPD repository, source checkout, and every Git worktree.
The resolved source and receipt roots must not overlap, and receipt paths cannot
contain symlinks or unprotected group/other-writable parents. Files are created
with mode 0600 and never overwritten. CLI output contains only a safe status;
detailed failures stay in restricted receipts.

Run locally with an authorized source checkout and an empty restricted destination:

```bash
uv run python tools/qualify_skillcorner_source.py \
  --source-root /restricted/source-checkout \
  --restricted-output /restricted/empty-qualification-directory
```

The tool returns nonzero on missing/corrupt/truncated assets, unresolved LFS
pointers, a revision mismatch, a changed source, unsafe storage, or a frozen
measurement failure. A source-preflight PASS would authorize only the next
construction step, not training or scoring.

Receipts bind all source SHA-256 values and sizes, pointer identities, verifier
and canonicalizer code digests, implementation Git revision, Python version,
frozen authority hashes, per-match discrepancies and receipt digests. Candidate
and eligible-window counts and the final population digest are explicitly null:
they are **unknown**, not zero. The raw retained-row support upper bounds in the
restricted diagnostics are not scientific candidate counts.

## Limits and review handoff

This change is a source qualification preflight, not the complete population
producer or an independent eligibility verifier. No canonical candidate
enumeration, eligibility replay, truth panels, membership manifest, LOMO scoring,
checkpoint selection, model training or historical private truth inspection was
performed. Representation arithmetic and population compatibility remain
unqualified on real data. Existing synthetic population-gate tests still check
the fail-closed validation, LOMO and evaluation contracts.

The repository contains only original code, synthetic tests and this aggregate
failure finding. Raw data, row identities and detailed receipts stay outside Git,
CI and redistributable artifacts under the existing CONDITIONAL GO rights policy.
The PR must remain unmerged pending independent scientific review. Resolving this
blocker requires an explicitly reviewed measurement-authority decision, followed
by full construction and a separately evidenced eligibility/truth replay.
