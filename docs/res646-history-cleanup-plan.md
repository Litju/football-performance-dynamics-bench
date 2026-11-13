# RES646 history exception and optional cleanup

The existing commit `e01aca58caf05453f441c43e04c71569990d0a90` is retained unchanged.
Its subject (only the historical issue identifier) does not describe its 12-file integration, which combines independent
prediction auditing, signed campaign/worker integration, and private preflight reporting.
This is a documented governance exception, not an assertion that its subject or scope complies.
All remediation uses new commits on the existing draft PR #38. No history rewrite is authorized.

## Optional owner-approved plan (not executed)

1. Record the approval-time branch HEAD, remote HEAD, full tree hash, and a backup ref. The only
   affected branch is `codex/res646-private-preflight`; base main and all scientific authorities
   remain unchanged. Confirm no collaborator has advanced the branch before beginning.
2. Replace only `e01aca5` with these ordered commits, partitioning **hunks**, not whole shared files:
   - `RES646 audit captured predictions without a second learned forward pass`: independent
     prediction/source audit classes, pipeline audit callbacks, and their standalone parity tests.
   - `RES646 bind the real workload and supervised inputs to signed owner authority`: Campaign
     implementation, source/checkpoint/path authorization parameters and guards, RealWorkload,
     executor reservation/worker integration, and signed campaign/refusal tests. Keep this entire
     security boundary together; never leave an intermediate commit enabling unguarded real access.
   - `RES646 report non-consuming private preflight configuration and deferred production trust`:
     preflight reporting, its configuration test, and execution-boundary documentation.
   Validate each split's imports, focused tests, Ruff and strict Pyright before proceeding.
3. Replay every descendant, preserving its content and subject. The exact affected revision set is
   `e01aca58caf05453f441c43e04c71569990d0a90^..APPROVAL_TIME_HEAD`. Existing descendants include
   `680d6e6`, `4767a18`, `9010a75`, `adabd73`, `fdfe39a`, `9918a9b`, `90e877e`, `40b6dd1`, and the
   remediation commits `2e0147b`, `63a5616`, `c506dde`, `c2d267c`, plus subsequent qualification
   commits. All these descendant commit IDs necessarily change; their final source tree must not.
4. Compare the final tree with the recorded approval-time tree. Resolve only replay mechanics;
   any intended content change needs separate review. Rerun the signed synthetic qualification,
   full pytest, Ruff/format, strict Pyright, naming/repository/evidence/reproducibility checks,
   wheel/sdist builds and isolated installed-package smokes. Refresh commit provenance while
   preserving direct measurement data and exact code hashes.
5. Only after explicit owner approval, update this PR branch with `--force-with-lease` against the
   recorded remote HEAD. Run and inspect both push and pull_request workflows at the **new exact
   HEAD**, including every quality/reproducibility job. Publish new immutable evidence links and
   request independent re-review. Keep PR #38 draft and unmerged; no real GO follows from cleanup.

A simpler owner-approved alternative is to reword `e01aca5` alone with a meaningful integration
subject. That fixes the subject but leaves its multi-concern scope as an explicit exception; it
still changes every descendant ID and requires the same exact-head revalidation.
