# Public asset inventory and rights-scoped publication decision

**Disposition: CANDIDATE ONLY — no artifact was published or licensed by this document.**

The project has a public, non-reconstructive aggregate scientific package and separately retained private source/checkpoint/receipt evidence. This page identifies the **twelve existing** science-report/figure files that may be *considered* for an aggregate-safe software research release and the negative boundaries on all other scientific assets. It does not create a new data license, independent result validation or public archive.

## Candidate manifest generation

Run from a clean Git checkout whose source revision you intend to review:

```bash
uv sync --locked --python 3.12
uv run fpdbench validate
uv run python tools/public_release_asset_manifest.py > /tmp/fpd-public-assets-candidate.json
```

The standard-library manifest tool hashes **exact committed bytes** of the fixed public results file, reported tables and nine figure files (three concepts × SVG/PDF/PNG) using SHA-256. It also records the exact source commit SHA, byte count and a deterministic hash of the ordered file inventory. It rejects missing/untracked/modified files, unsafe paths and symlinks.

The generated object is marked `CANDIDATE_ONLY_NOT_PUBLISHED` and `release_authorized: false` regardless of test success. The output is **not** an uploaded GitHub asset, archival DOI record, digitally signed authority, rights certificate or validation against raw SkillCorner data. Run the manifest again on the **final tagged** release SHA if and only if the separately approved release gates are satisfied; do not copy a stale hash into a release description.

## Allowed source classes and restrictions

| Asset class | Existing public availability | Release disposition |
| --- | --- | --- |
| Aggregate research JSON and tables | Source-controlled, non-reconstructive match/configuration aggregates | Candidate; verify SHA-256, attribution and non-reconstruction |
| Error, paired-contrast and horizon figures | Source-controlled public SVG/PDF/PNG rendered from aggregate JSON | Candidate; verify as independent files and preserve limitations |
| Pinned source-revision metadata and measurement/protocol/eligibility contracts | Public code, schema and reproducibility metadata | Candidate as original software/docs; **not** a license for source rows |
| Scientific manuscript and supplement in repository | Public review-preparation materials; paper is not recorded as accepted/published | Present in source tree; no DOI/peer-review claim; publication rights require owner verification |
| SkillCorner core raw match/tracking/event/phase data | External provider files, **not distributed by FPD** | **NO-GO** pending written clarification of rights |
| Row-level derivative tracking, masks, target truth, per-window prediction packages | Private or unavailable | **NO-GO** under current source policy |
| Learned model checkpoints/weights, fit receipts and restricted ledger | Owner-only content; hashes only in public authority | **NO-GO** without an independent rights, reconstruction/confidentiality and owner review; no implied checkpoint downloads |
| Historical protected qualification truth | Forbidden private scientific evidence | **NEVER distribute or open under public reproducibility** |

The current [rights audit](data-rights.md) allows local research processing under conditions and publication of **non-reconstructive aggregates and source metadata** with appropriate attribution. It retains the raw/row-level redistribution gate. The source names SkillCorner as provider with PySport as a collaborating initiative. This is not an assertion that SkillCorner has approved new model-weight distribution.

## What the public report proves and does not prove

The published [four-match report](res440/results.md) and [full-precision aggregate JSON](res440/findings.json) describe 18 frozen DeepSets checkpoints in six configurations over four independent evaluation matches, paired with history-only deterministic references. A file hash proves a **byte identity for a checked file at one commit**. It does not prove that the underlying source tracking was independently measured, that private inference can be repeated from public artifacts, that a model generalizes, or that the source provider granted redistribution rights.

The public checker `tools/inspect_public_findings.py` reconciles public match-first aggregates and C1/C2 contrasts; it does **not** access underlying private results, checkpoint tensors or raw observation windows. The protected population remains `NOT_QUALIFIED`. The original 234-fit campaign is incomplete and 216 training LOMO fits have not run.

## Independent publication gates still pending

1. Confirm the software and documentation rightsholder/author attribution and independent third-party notice requirements for the *actual* intended GitHub source archives.
2. Review each proposed additional distribution asset and the final source tree for restricted rows, private receipts, identifying trajectories, credentials, unintended binaries or reconstructive information.
3. Validate the exact tagged source SHA, Python version, all applicable CI jobs, package artifacts, and asset manifest's SHA-256 values.
4. Obtain explicit approval for whether a separate archival DOI/Zenodo record is warranted, the approved author list and the exact materials deposited. Do not describe a draft manuscript as published.
5. Mark the protected scientific qualification and deferred original experiment as *unfulfilled* even after a software/source-only publication.

This inventory is deliberately narrower than the full stable-software release's approval authority. Read the [software release gates](software-release-gates.md), [public reproduction walkthrough](public-reproduction-walkthrough.md), [public model cards](public-data-and-model-cards.md) and [governance policy](licensing-and-governance.md) before publishing.
