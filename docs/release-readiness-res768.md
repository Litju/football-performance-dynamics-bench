# Release-readiness evidence (R8 QA audit)

Status date: 2026-11-24. Original baseline: `main` at `0feddee7e666771b1dcecfdd0bcf57db33a31964` (merge of PR #42); code baseline for the RC verification: `ba2e79f` (bounded clock-skew repair). Scope: public documentation, reproducibility, rights and release metadata. This report is a QA gate. It is not a stable release, a citation or archival record, or a scientific qualification.

**Overall determination: NO_GO** for a stable release (R8 stable-release issue) and for any public artifact or archival step. The repository is acceptable as a documented, non-archival research-software **development** state, subject to the open items below. The repository does not record owner decisions for rights, citation, authorship or publication. The release-candidate recommendation is **GO** for the repaired code; exact-head CI and independent review are recorded below. Stable release remains **NO_GO**.

## 1. Environments

| Item | Value |
| --- | --- |
| Host | Ubuntu on WSL2, Linux `6.18.33.2-microsoft-standard-WSL2` |
| Python used for CI gates | CPython 3.12.13 (`uv sync --locked --all-groups --python 3.12`) |
| Python default on host | CPython 3.14.5 (dev group only; see §4 F1) |
| uv | 0.12.2 |
| Node / npm | v22.23.2 / 10.9.8 |
| Clean checkout | fresh `git clone` of the local repository, pinned to the exact commit under test |
| Pinned PR #25 source package | commit `aad8888eb6c7c046e4dfbce866886bf2ec8dd123`, extracted with `git archive FETCH_HEAD src/fpdbench` as in CI |
| Browser system libraries | `libnspr4`, `libnss3` and `libasound2t64` fetched with `apt-get download` and extracted to a user-local directory; `LD_LIBRARY_PATH` was set only for the site browser check. No system package was installed and no preflight/security behavior depends on this workaround. |
| Host clock | WSL2 wall clock stepped backward by 0.001–3.4 s (median ~1.6 s) roughly every 31 s, with forward corrections up to 2.5 s (measured against `time.monotonic_ns()`), while the monotonic clock advanced normally. This is the F2 trigger, not a repository-generated clock. |

Commands below are the ones run. Exit codes were recorded for each run.

## 2. Gate results

Status key: **PASS** (exit 0 on the stated commit), **FAIL** (non-zero exit, cause stated), **BLOCKED** (cannot run here, cause stated), **NOT_RUN** (not yet executed on the stated commit).

| Gate | Commit | Command | Status | Evidence |
| --- | --- | --- | --- | --- |
| Lint | `0feddee` | `uv run ruff check .` | PASS | exit 0 |
| Format | `0feddee` | `uv run ruff format --check .` | PASS | exit 0 |
| Types | `0feddee` | `uv run pyright` | PASS | exit 0 |
| Naming | `0feddee` | `uv run fpdbench validate-naming` | PASS | exit 0 |
| Repository | `0feddee` | `uv run fpdbench validate` | PASS | exit 0 |
| Evidence | `0feddee` | `uv run fpdbench evidence validate` | PASS | exit 0 |
| Reproducibility | `0feddee` | `uv run fpdbench reproducibility check` | PASS | exit 0 |
| Runtime attestation | `0feddee` | `tools/attest_streaming_runtime.py capture` (isolated `env -i`) | PASS | exit 0 |
| Full pytest | `ba2e79f` | `pytest -q -rfE`, with `FPDBENCH_PR25_PACKAGE_ROOT` set | **PASS** (1344) | 1344 passed in 1393.67 s (23:13) on CPython 3.12.13 in a fresh clone: the original 1,340 tests plus four clock-skew regression cases. This is the repaired code. |
| Full pytest baseline (pre-repair) | `0feddee` | same | **FAIL** (1 of 1340) | 1339 passed, 1 failed, 1784 s. The failure was the F2 `KeyError`; it is now explained and fixed. |
| F2 real-clock regression (pre-repair) | `0feddee` | target test repeated 40 times in one clean clone | **FAIL** (1 of 40) | Iteration 31 reproduced the exact `KeyError: 'proposed_scope_sha256'`. The clock monitor recorded backward steps (median ~1.6 s, max ~3.4 s) over the same interval. |
| F2 real-clock regression (post-repair) | `ba2e79f` | target test repeated 40 times | **PASS** (40/40) | 0 failures, including intervals containing host clock steps. |
| F2 deterministic regression | `ba2e79f` | 1 s and 4 s backward clock steps; 6 s and 1 h future-dated controls | **PASS** | The 1 s/4 s cases previously returned `RES646_GATE5_BLOCKED`; after the repair both consecutive checks return `RES646_GATE5_READY_FOR_INDEPENDENT_REVIEW` with identical scope identities. The 6 s/1 h controls remain blocked. |
| Full pytest without PR #25 package | `0feddee` | same, env var unset, `node_modules` present | not a valid gate | 1303 passed, 7 failed, 30 errors. The 30 errors are the missing package (F3). The second full run (the baseline row above) differed only by setting the package variable and removing `site/node_modules`. Kept only as diagnostics. |
| CLI discovery | `0feddee` | `benchmarks list`, `families list`, `research-objects list` | PASS | exit 0 |
| Data state and eligibility | `0feddee` | `data-states verify`, `eligibility verify` | PASS | `status: passed` for `skillcorner_5hz_v1` and `skillcorner_window_v1` |
| Package build | `ba2e79f` | `uv build` | PASS | `football_performance_dynamics_bench-0.1.0.dev0` wheel and sdist |
| Wheel/sdist smoke | `ba2e79f` | `tools/wheel_smoke.py dist/*.whl dist/*.tar.gz` | PASS | `isolated wheel smoke passed` under Python 3.12.13 |
| RES643 package parity | `ba2e79f` | `tools/res643_package_smoke.py` | PASS | `RES643 isolated wheel/sdist parity passed` |
| RES645 package parity | `ba2e79f` | `tools/res645_package_smoke.py` | PASS | `RES645 isolated wheel/sdist parity passed` |
| Site install | `0feddee` | `npm ci` in `site/` | PASS | exit 0; `found 0 vulnerabilities` |
| Site build | `0feddee` | `npm run build` | PASS | exit 0 (`tsc --noEmit && vite build`) |
| Site content | `0feddee` | `npm run check:content` | PASS | "content checks passed" |
| Site browser (a11y, phone, reduced motion) | `ba2e79f` | `npm run build && npx vite preview --port 4173`, then `npm run check:browser` | **PASS** | `browser checks passed`; desktop, phone and reduced-motion runs completed with no serious/critical axe violations, console errors or horizontal overflow. Chromium ran with the user-local libraries above. |
| Relative links | `0feddee` | Python check over 59 Markdown files | PASS | 0 broken |
| External links | `0feddee` | HTTP status of 86 unique external URLs | PASS with notes | 83 HTTP 200; 2 DOI links return HTTP 403 to an automated client (unverified, not broken); `http://localhost:5173` is a development-server instruction, not a link |
| Live showcase reachability | n/a | `GET https://fpd-bench-showcase.vercel.app/` | PASS (reachability only) | HTTP 200. Deploy identity and content were not inspected through Vercel tooling. |
| Hosted CI on code head | `4b7bc7c` | `.github/workflows/ci.yml` | **PASS** | Run [45414442244](https://github.com/Litju/football-performance-dynamics-bench/actions/runs/45414442244): `quality` and `public-reproducibility` both succeeded. The report-only follow-up is covered by the final docs-only CI run linked in the PR. |
| Independent review | `4b7bc7c` | separate read-only reviewer | **APPROVE** | Automated reviewer in a separate context approved the repair and evidence after changes; it is not a human owner approval or release authorization. |

Gates on the R8-QA commits (validators, then the doc-sensitive tests):

| Commit | Subject | Validators | Tests |
| --- | --- | --- | --- |
| `e7d98a6` | redact private checkout paths from public docs | PASS (naming, validate, evidence, reproducibility) | PASS (`test_reproducibility.py`, `test_validation.py`) |
| `2e86e5e` | add newcomer path and document test prerequisites | PASS (ruff check and format, pyright, naming, validate, evidence, reproducibility) | PASS (`test_reproducibility.py`, `test_validation.py`, `test_cli.py`, `test_res646_preflight_qualification.py`) |
| `218705a` | add release-readiness evidence report | PASS (ruff check and format, pyright, naming, validate, evidence, reproducibility) | PASS (`test_reproducibility.py`, `test_validation.py`) at this head; the report is the reviewed head, and the earlier amendment is superseded by the commit below |
| `ba2e79f` | bound future clock skew in RES646 preflight | PASS (ruff check and format, pyright, naming, validate, evidence, reproducibility, CLI discovery, data states, eligibility) | PASS (`test_res646_preflight_qualification.py`, 91 tests; 40/40 target repeats) |

### F2 root cause and repair

The failure was a **wall-clock synchronization race**, not a preflight data mutation or a test-order leak. In the clean CPython 3.12.13 environment, a monitor comparing `time.time_ns()` with `time.monotonic_ns()` recorded repeated backward wall-clock steps (median ~1.6 s, maximum ~3.4 s, roughly every 31 s) plus forward corrections up to ~2.5 s. The target fixture stamps `verified_at_utc` with `datetime.now(UTC)`, and `_qualify` rejects any evidence whose timestamp is even slightly in the future. If a host clock step landed between the fixture stamp and the second `check()`, the evidence appeared future-dated, the second report became `RES646_GATE5_BLOCKED`, and the test then raised `KeyError: 'proposed_scope_sha256'`.

The repair accepts only a bounded **five-second** future skew as clock jitter. Stale evidence (older than one day), clearly future-dated evidence (beyond five seconds), and all other fail-closed checks are unchanged. No exception is suppressed, no preflight step is skipped, and no input/model byte is opened. The regression tests use a fixed clock relative to the fixture timestamp: 1 s and 4 s backward steps (both blocked before the repair, both ready after) and 6 s and 1 h future-dated controls (both remain blocked). Repeating the unmodified target test 40 times reproduced the exact `KeyError` once at iteration 31; repeating the repaired test 40 times passed all runs while the host clock was still stepping.

`res646_preflight.py` is part of `res645_pipeline.CODE_FILES`, so the repair changes the code identity bound into Gate 5 evidence. Any pre-existing Gate 5 evidence must be regenerated and re-reviewed; this is fail-closed and no live evidence is committed to the public repository. The synthetic regression fixture computes its provenance after the change, so it exercises the new identity.

## 3. Scientific claim audit

Each headline number was checked against `docs/res440/findings.json` (public, aggregate).

| Claim | Authority value | Where it appears | Result |
| --- | --- | --- | --- |
| History-only displacement ADE 1.6680 m | `summary` / `history_baseline_comparisons`: 1.6680180412 m | `results.md`, `paper-a-evidence.md`, `manuscript.tex`, `supplement.md`, `scientific-audit.md` | consistent |
| Constant velocity 2.2433 m | `history_baseline_comparisons` baseline 2.2433 | same | consistent |
| 25.6% reduction | `reduction_percent` 25.6445 | same | consistent |
| History-only absolute XY ADE 2.1216 m (5.4%) | `summary` | `paper-a-evidence.md`, `results.md` | consistent |
| 51,713 windows; 72 match/seed records; 18 checkpoints; 4 independent units | `windows` 51713, `independent_units` 4 | `results.md`, `supplement.md` | consistent |
| `NOT_QUALIFIED` | `classification` = "research-only NOT_QUALIFIED" | README, `results.md`, showcase | consistent |
| Original 234-fit campaign incomplete; 216 training LOMO fits never run | `results.md` (stated in the results text) | `results.md`, README, showcase | consistent with the authority text |

No new scientific number was introduced. No result was recomputed from restricted data, and no model was run.

## 4. Findings

Severity: **blocker** = prevents a release-candidate or stable determination; **defect** = repaired in this branch or open with an owner; **note** = recorded, no action required for this gate.

| ID | Severity | Finding | Status |
| --- | --- | --- | --- |
| F1 | defect (fixed) | README quickstart did not state the Python constraint for the full CI environment. On CPython 3.14, `uv sync --all-groups` fails because `torch==2.6.0+cpu` (research-training group) has no cp314 wheels. Plain `uv sync` works on 3.14 and was verified. | Fixed in `2e86e5e` (README quickstart note). |
| F2 | defect (fixed) | One full-suite failure on `0feddee` with the PR #25 package: `tests/unit/test_res646_preflight_qualification.py::test_complete_configuration_qualifies_without_input_bytes_or_scope_consumption`, `KeyError: 'proposed_scope_sha256'` on the **second** `check()` call. Root cause: repeated backward wall-clock steps (median ~1.6 s, maximum ~3.4 s) on this WSL2 host made the fixture timestamp look future-dated. A 40-repeat real-clock run reproduced the exact `KeyError` once. | Fixed in `ba2e79f`: bounded five-second future clock-skew tolerance; 1 s/4 s regressions pass, 6 s/1 h future evidence still blocked. Full suite and real-clock repeats pass. |
| F3 | defect (documented) | 30 streaming-integration errors without `FPDBENCH_PR25_PACKAGE_ROOT`; the streaming tests and the artifact-size guard both depend on local layout (a local `site/node_modules` made the guard fail on an untracked 10 MB+ file). | Documented in `docs/reproducibility.md#test-prerequisites` (`2e86e5e`). |
| F4 | defect (fixed) | Private absolute checkout and registry paths (the maintainer's home directory) appeared in three public documents. No code depends on them. | Fixed in `e7d98a6`. A tracked-tree search after the fix finds no remaining checkout-path string outside this report's own description of F4. |
| F5 | defect (fixed) | The documented public command block omitted the CI sdist smoke and the RES643/RES645 package-parity steps. | Fixed in `2e86e5e`. |
| F6 | defect (fixed) | No newcomer entry point: the README did not state what is investigated, what runs publicly, the limitations, or how Paper A and the showcase relate to the evidence. | Fixed in `2e86e5e` (`Start here`). |
| F7 | blocker (owner decision) | Redistribution of SkillCorner-derived content is not cleared. `docs/data-rights.md` records **CONDITIONAL GO** for local public research use and a retained release gate for core source files and row-level derivatives. | Owner decision. Routed to the R8 artifact-publication issue and the data-rights record. Not waived. |
| F8 | blocker (metadata) | `CITATION.cff`, DOI and archive metadata are absent. The licensing record says these depend on verified rightsholders and affiliations. | Routed to the R8 citation and archive issue. Not created here, to avoid inventing authorship or identity. |
| F9 | blocker (release) | No stable version, tag, changelog or release notes. Package version is `0.1.0.dev0`. No tags exist locally or on the remote. | Routed to the R8 stable-release issue. |
| F10 | blocker (owner) | Author, affiliation and copyright attestations are not established by repository evidence (`docs/licensing-and-governance.md`). | Owner decision; routed to the R8 citation and archive issue. |
| F11 | defect (environment; verified) | Browser accessibility, phone and reduced-motion checks were blocked by missing Chromium system libraries (`libnspr4`, `libnss3`, `libasound2t64`). | Verified with user-local extracted libraries and `LD_LIBRARY_PATH`; `npm run check:browser` passes. No system package was installed and the repository is unchanged. |
| F12 | note | The synthetic PR #25 fixture archive (`tests/fixtures/streaming-verifier-v1/pr25-synthetic-fixtures.zip`, 4 MB) is consistent with its README (synthetic team IDs 101/202, player IDs from 1001, 100 by 60 pitch). Its match-ID labels coincide with public match IDs in `findings.json`. A rights reviewer should confirm that the labels carry no real-data content. | Note for R8 artifact-publication issue. |
| F13 | note | Two DOI links return HTTP 403 to automated clients. | Note; verify manually. |
| F14 | note | Paper A readiness record states "ready for final owner review." It does not record a journal submission, peer review or publication. The repository does not claim one. | Consistent. No change. |

## 5. Public capability matrix (as documented in `docs/reproducibility.md`)

| Capability | Label |
| --- | --- |
| Target transforms, displacement inversion, information-boundary checks, raw evaluators, absolute-position calibration, physical diagnostics, canonical protocols, scientific-lock construction, result-manifest hashing, CLI discovery and validation | `PUBLIC_EXECUTABLE` |
| Historical result records, fixture manifests, population counts, output digests, checkpoint identifiers as public metadata | `PUBLIC_VERIFIABLE` |
| Evidence pointers that resolve only against a supplied local registry (`evidence validate --registry-root`) | `LOCAL_EVIDENCE_VERIFIABLE` |
| Historical raw tracking bytes, learned checkpoints, historical source-to-fixture regeneration, learned-model inference | `UNAVAILABLE_PUBLIC_ARTIFACT` |
| J03WMX qualification truth | `FORBIDDEN_PRIVATE_TRUTH` (never read) |
| SkillCorner source data bytes and row-level derivatives | rights-restricted (F7); not in repository |
| Original 234-fit prospective campaign; deferred 216 training LOMO fits | incomplete / never run (no capability claimed) |
| Protected population status | `NOT_QUALIFIED` |

This matrix does not claim full experimental reproducibility.

## 6. Reproduction for a third party

```bash
git clone https://github.com/Litju/football-performance-dynamics-bench.git
cd football-performance-dynamics-bench
git checkout <commit>
uv sync --locked --all-groups --python 3.12
uv run ruff check . && uv run ruff format --check . && uv run pyright
uv run fpdbench validate-naming && uv run fpdbench validate
uv run fpdbench evidence validate && uv run fpdbench reproducibility check
# PR #25 package for the streaming tests: see docs/reproducibility.md#test-prerequisites
uv run pytest -q -rfE
uv build
uv run python tools/wheel_smoke.py dist/*.whl dist/*.tar.gz
uv run python tools/res643_package_smoke.py dist/*.whl dist/*.tar.gz
uv run python tools/res645_package_smoke.py dist/*.whl dist/*.tar.gz
# site: run in a separate directory after the Python gates
cd site && npm ci && npm run build && npm run check:content
```

## 7. Blockers and owners

| Item | Owner issue | Required for |
| --- | --- | --- |
| F7: SkillCorner redistribution and row-level derivative rights | R8 artifact-publication issue and data-rights owner | any artifact publication |
| F8, F10: citation, DOI, author and affiliation attestations | R8 citation and archive issue | archive and citation |
| F9: stable version, tag, changelog, release notes | R8 stable-release issue | stable release |
| Benchmark, data and model cards | R8 benchmark, data and model cards issue | research-software completeness |

F2 (clock-skew test failure) and F11 (browser system libraries) are closed by reproduced evidence in this branch and are no longer release gates.

## 8. Determination

**Release-candidate recommendation: GO.** The full suite (1,344 tests: 1,340 original plus four clock-skew regressions) passes on the repaired code in the documented CPython 3.12.13 clean-clone environment, the F2 real-clock and deterministic regressions pass, the validators, type checks, packaging smokes and site browser checks pass, and exact-head CI and independent review are recorded above. This recommendation covers **research-software release-candidate readiness** only; it is not owner approval or a stable-release authorization.

**Stable release and public artifact/archive: NO_GO.** The separate rights, citation, authorship, archival and stable-version gates (F7, F8, F10, F9 and the benchmark/data/model cards) remain open with their owners. No owner approval, authorship, affiliation, DOI, rights clearance or publication status was assumed. No tag, release, DOI deposit or deployment was created by this QA work.
