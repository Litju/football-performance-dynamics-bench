# Contributing to Football Performance Dynamics Bench

FPD Bench is research software for inspectable football-performance task definitions, evaluations and evidence. A contribution must preserve **scientific identity, reproducibility, protected-data boundaries and attribution**; a passing unit test alone does not authorize changing a frozen benchmark.

## Before proposing a change

Read the [README](README.md), [scientific reproducibility model](docs/reproducibility.md), [public benchmark cards](docs/public-benchmark-cards.md), [source/model and limitation cards](docs/public-data-and-model-cards.md), [licensing and authorship policy](docs/licensing-and-governance.md), and [SkillCorner data-rights audit](docs/data-rights.md).

The project separates code, protocol, data state, match membership, evaluator, result, and release identities. State which object you are changing and whether the proposed change is a scientific successor, code repair, public documentation improvement or new research. Never modify frozen scientific JSON or historical locked result artifacts merely to improve software ergonomics.

## Clean public developer workflow

Use Python 3.12 and `uv`. The public subset needs no data credentials:

```bash
uv sync --locked --python 3.12
uv run fpdbench benchmarks list
uv run fpdbench validate
uv run fpdbench evidence validate
uv run fpdbench reproducibility check
uv run python tools/inspect_public_findings.py
uv run pytest -q tests/unit/test_validation.py tests/unit/test_public_findings.py
```

For the **complete** Python test suite, install the pinned public synthetic PR #25 source-package fixture following [the exact prerequisites](docs/reproducibility.md#test-prerequisites). Use `uv sync --locked --all-groups --python 3.12`, then `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run pyright`, `uv run fpdbench validate-naming`, `uv run fpdbench validate`, `uv run fpdbench evidence validate`, and `uv run fpdbench reproducibility check`. Build/check wheel and sdist with the documented isolated smoke scripts. Do not claim an unrun check passed.

The independently versioned `site/` companion uses `npm ci`, `npm run build`, `npm run check:content` and, when Chromium is available, `npm run check:browser`. Site illustrations are schematic. All displayed measured numbers must derive from committed `docs/res440/findings.json` rather than retyping or inventing values.

## Code and documentation requirements

- Make one coherent scientific or software change per commit; for issue-linked repository work use **at least two meaningful atomic commits**, each referencing its exact issue ID in the **Git commit subject**, after scoped verification. Do not use fake checkpoint commits. Preserve reviewable commits with normal merges.
- New metrics must document input/target units, reference frame, mask/denominator and temporal semantics, expected behavior for missing values, aggregation hierarchy and zero variance.
- New data acquisition/measurement transformations need pinned upstream identities, exact file inventories and rights review; generic moving source URLs are not enough.
- New algorithms/evaluators must have synthetic deterministic tests, invalid-input and contamination/leakage tests, and clearly separated scientific versus runtime/packaging claims.
- Correct earlier scientific mistakes with explicit versioned transitions and evidence; never retroactively change a frozen claim without recording the disagreement.
- Public papers/results must keep *match* as the independent unit for the existing four-match study. Do not report windows/seeds as independent matches, inferential intervals without a declared dependence-aware method, or conditional realized-future analysis as ex-ante forecasting.
- Do not add tracker IDs, legacy administrative identifiers or obsolete internal project names to committed filenames/content where the naming policy forbids them. Use issue IDs in commit subjects and PR discussion, not in canonical scientific artifacts.
- Run the full applicable lint/type/test/evidence/packaging checks and attach exact-head CI evidence to a focused PR. Keep the branch draft until its acceptance criteria and independent review are complete.

## Security, data rights and protected artifacts

**Do not commit or post** source tracking rows, phase/event data, row-level derived trajectories, full hidden truth, fit checkpoint bytes, private receipts, secrets, home-directory paths, identifiable player timelines, keys, or confidential credentials. No real protected-source access, model fitting, or evaluation is authorized by a code contribution.

SkillCorner and PySport must receive the documented credit. The repository's Apache-2.0 license applies only to rights-cleared *original code and documentation*; it does not sublicense upstream data. Use the [source card](docs/skillcorner-source-card.md) and [rights policy](docs/data-rights.md) for the explicit local-research versus redistribution distinction.

Do not infer a person's rightsholder status, scientific authorship, institution, contributor role, or release approval from commit identity. Contributors must affirm they have the right to offer the material under the applicable terms and identify imported code/data/assets and their licenses. Publication authorship and citation require separate documented approval.

## Changes that require a separate decision

The following are **not** automatically authorized by passing CI: a new original experiment/LOMO training run, access to protected real-source or held-out truth, changes to scientific locks, sharing upstream data/model weights, publication of source-derived row-level outputs, assignment of paper authorship or affiliations, creating a stable version/tag, depositing a DOI, submitting a paper, or declaring the protected population qualified.

Review the [release gates](docs/software-release-gates.md) for a public code/software distribution decision. Contributions and support questions can be raised via the repository's [GitHub issues](https://github.com/Litju/football-performance-dynamics-bench/issues); do not upload private artifacts with a report.
