# Release-readiness evidence (R8 QA audit)

Status date: 2026-11-23. Baseline: `main` at `0feddee7e666771b1dcecfdd0bcf57db33a31964` (merge of PR #42). Scope: public documentation, reproducibility, rights and release metadata. This report is a QA gate. It is not a stable release, a citation or archival record, or a scientific qualification.

**Overall determination: NO_GO** for a stable release (R8 stable-release issue) and for any public artifact or archival step. The repository is acceptable as a documented, non-archival research-software **development** state, subject to the open items below. The repository does not record owner decisions for rights, citation, authorship or publication.

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
| Full pytest | `0feddee` | `pytest -q -rfE`, with `FPDBENCH_PR25_PACKAGE_ROOT` set | **FAIL** (1 of 1340) | 1339 passed, 1 failed, 1784 s. See F2. |
| Full pytest without PR #25 package | `0feddee` | same, env var unset, `node_modules` present | not a valid gate | 1303 passed, 7 failed, 30 errors. The 30 errors are the missing package (F3). The second run differed only by setting the package variable and removing `site/node_modules`, and those failures did not recur. The individual causes of the first run's remaining failures were not traced. Kept only as diagnostics. |
| CLI discovery | `0feddee` | `benchmarks list`, `families list`, `research-objects list` | PASS | exit 0 |
| Data state and eligibility | `0feddee` | `data-states verify`, `eligibility verify` | PASS | `status: passed` for `skillcorner_5hz_v1` and `skillcorner_window_v1` |
| Package build | `0feddee` | `uv build` | PASS | `football_performance_dynamics_bench-0.1.0.dev0` wheel and sdist |
| Wheel/sdist smoke | `0feddee` | `tools/wheel_smoke.py dist/*.whl dist/*.tar.gz` | PASS | exit 0 (Python 3.12 and 3.14 environments) |
| RES643 package parity | `0feddee` | `tools/res643_package_smoke.py` | PASS | exit 0 under Python 3.12, `--all-groups` (needs `numpy`) |
| RES645 package parity | `0feddee` | `tools/res645_package_smoke.py` | PASS | exit 0 under Python 3.12, `--all-groups` |
| Site install | `0feddee` | `npm ci` in `site/` | PASS | exit 0; `found 0 vulnerabilities` |
| Site build | `0feddee` | `npm run build` | PASS | exit 0 (`tsc --noEmit && vite build`) |
| Site content | `0feddee` | `npm run check:content` | PASS | "content checks passed" |
| Site browser (a11y, phone, reduced motion) | `0feddee` | `npm run check:browser` | **BLOCKED** | Playwright Chromium cannot start: `libnspr4.so: cannot open shared object file`. The system library is not installed on this host. Installing it needs system access, which this QA run did not use. |
| Relative links | `0feddee` | Python check over 59 Markdown files | PASS | 0 broken |
| External links | `0feddee` | HTTP status of 86 unique external URLs | PASS with notes | 83 HTTP 200; 2 DOI links return HTTP 403 to an automated client (unverified, not broken); `http://localhost:5173` is a development-server instruction, not a link |
| Live showcase reachability | n/a | `GET https://fpd-bench-showcase.vercel.app/` | PASS (reachability only) | HTTP 200. Deploy identity and content were not inspected through Vercel tooling. |
| Hosted CI on exact PR head | pending | `.github/workflows/ci.yml` | NOT_RUN | Requires the draft PR. Recorded in the PR body. |
| Independent review | pending | separate reviewer | NOT_RUN | Recorded in the PR body. |

Gates on the R8-QA commits (validators, then the doc-sensitive tests):

| Commit | Subject | Validators | Tests |
| --- | --- | --- | --- |
| `e7d98a6` | redact private checkout paths from public docs | PASS (naming, validate, evidence, reproducibility) | PASS (`test_reproducibility.py`, `test_validation.py`) |
| `2e86e5e` | add newcomer path and document test prerequisites | PASS (ruff check and format, pyright, naming, validate, evidence, reproducibility) | PASS (`test_reproducibility.py`, `test_validation.py`, `test_cli.py`, `test_res646_preflight_qualification.py`) |

## 3. Scientific claim audit

Each headline number was checked against `docs/res440/findings.json` (public, aggregate).

| Claim | Authority value | Where it appears | Result |
| --- | --- | --- | --- |
| History-only displacement ADE 1.6680 m | `summary` / `history_baseline_comparisons`: 1.6680180412 m | `results.md`, `paper-a-evidence.md`, `manuscript.tex`, `supplement.md`, `scientific-audit.md` | consistent |
| Constant velocity 2.2433 m | `history_baseline_comparisons` baseline 2.2433 | same | consistent |
| 25.6% reduction | `reduction_percent` 25.6444 | same | consistent |
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
| F2 | **blocker (open)** | One full-suite failure on `0feddee` with the PR #25 package: `tests/unit/test_res646_preflight_qualification.py::test_complete_configuration_qualifies_without_input_bytes_or_scope_consumption`, `KeyError: 'proposed_scope_sha256'` on the **second** `check()` call (test line 445). The test **passes** alone and the whole module passes (87/87), so the failure depends on test order or on leftover state. The cause was not established. | Open. Owner: R8-QA follow-up. The full-suite gate cannot be recorded as PASS until F2 is explained or fixed. |
| F3 | defect (documented) | 30 streaming-integration errors without `FPDBENCH_PR25_PACKAGE_ROOT`; the streaming tests and the artifact-size guard both depend on local layout (a local `site/node_modules` made the guard fail on an untracked 10 MB+ file). | Documented in `docs/reproducibility.md#test-prerequisites` (`2e86e5e`). |
| F4 | defect (fixed) | Private absolute checkout and registry paths (`/home/litju/...`) appeared in three public documents. No code depends on them. | Fixed in `e7d98a6`. A tracked-tree search after the fix finds no remaining `/home/litju` string. |
| F5 | defect (fixed) | The documented public command block omitted the CI sdist smoke and the RES643/RES645 package-parity steps. | Fixed in `2e86e5e`. |
| F6 | defect (fixed) | No newcomer entry point: the README did not state what is investigated, what runs publicly, the limitations, or how Paper A and the showcase relate to the evidence. | Fixed in `2e86e5e` (`Start here`). |
| F7 | blocker (owner decision) | Redistribution of SkillCorner-derived content is not cleared. `docs/data-rights.md` records **CONDITIONAL GO** for local public research use and a retained release gate for core source files and row-level derivatives. | Owner decision. Routed to the R8 artifact-publication issue and the data-rights record. Not waived. |
| F8 | blocker (metadata) | `CITATION.cff`, DOI and archive metadata are absent. The licensing record says these depend on verified rightsholders and affiliations. | Routed to the R8 citation and archive issue. Not created here, to avoid inventing authorship or identity. |
| F9 | blocker (release) | No stable version, tag, changelog or release notes. Package version is `0.1.0.dev0`. No tags exist locally or on the remote. | Routed to the R8 stable-release issue. |
| F10 | blocker (owner) | Author, affiliation and copyright attestations are not established by repository evidence (`docs/licensing-and-governance.md`). | Owner decision; routed to the R8 citation and archive issue. |
| F11 | open (environment) | Browser accessibility, phone and reduced-motion checks are BLOCKED on this host (missing `libnspr4`). | Re-run on a host with Chromium system libraries before a release determination. |
| F12 | note | The synthetic PR #25 fixture archive (`tests/fixtures/streaming-verifier-v1/pr25-synthetic-fixtures.zip`, 4 MB) is consistent with its README (synthetic team IDs 101/202, player IDs from 1001, 100 by 60 pitch). Its match-ID labels coincide with public match IDs in `findings.json`. A rights reviewer should confirm that the labels carry no real-data content. | Note for R8 artifact-publication issue. |
| F13 | note | Two DOI links return HTTP 403 to automated clients. | Note; verify manually. |
| F14 | note | Paper A readiness record states "ready for final owner review." It does not record a journal submission, peer review or publication. The repository does not claim one. | Consistent. No change. |

## 5. Public capability matrix (as documented in `docs/reproducibility.md`)

| Capability | Label |
| --- | --- |
| Target transforms, displacement inversion, information-boundary checks, raw evaluators, absolute-position calibration, physical diagnostics, canonical protocols, scientific-lock construction, result-manifest hashing, CLI discovery and validation | `PUBLIC_EXECUTABLE` |
| Historical result records, fixture manifests, population counts, output digests, checkpoint identifiers as public metadata | `PUBLIC_VERIFIABLE` |
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
| F2: order-dependent test failure | R8-QA follow-up (this branch's review) | RC determination |
| F7: SkillCorner redistribution and row-level derivative rights | R8 artifact-publication issue and data-rights owner | any artifact publication |
| F8, F10: citation, DOI, author and affiliation attestations | R8 citation and archive issue | archive and citation |
| F9: stable version, tag, changelog, release notes | R8 stable-release issue | stable release |
| Benchmark, data and model cards | R8 benchmark, data and model cards issue | research-software completeness |
| F11: browser checks on a host with Chromium libraries | environment owner | release determination |

## 8. Determination

**NO_GO** for a stable release and for any public artifact or archive. The determination is not **GO** for release-candidate status while F2 remains unexplained. Items F1, F3, F4, F5 and F6 are repaired or documented in this branch. Remaining items are listed above with their owners. No owner approval, authorship, affiliation, DOI, rights clearance or publication status was assumed.
