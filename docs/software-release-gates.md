# Public research-software release gates

**Status:** preparation only. No tagged stable `v1.0.0` release, published archival DOI, author-approved software citation, protected-population qualification or newly authorized artifact distribution is established by this document. The current Python distribution is `0.1.0.dev0`.

This page separates **software reproducibility**, **scientific result validity**, **rights**, **authorship**, and **archive publication**. No single passing workflow can substitute for another authority.

## Planned release scope

| Material | Intended action and disposition | Required authority |
| --- | --- | --- |
| Original Apache-2.0 source, typed schemas, deterministic evaluators and verification tools | Candidate public software package and source tag, subject to owner rightsholder/copyright provenance approval | Existing [license and governance audit](licensing-and-governance.md), build and repository checks |
| Public benchmark/protocol/model/source cards and responsible-use limitations | Candidate public documentation, without a protected-production claim | Frozen [benchmark cards](public-benchmark-cards.md), [model/data cards](public-data-and-model-cards.md) and scientific authorities |
| Existing non-reconstructive four-match results and figures | Candidate referenced public aggregate evidence; existing published repository evidence must retain `research-only NOT_QUALIFIED` | [Scientific results](res440/results.md), [rights policy](data-rights.md), source and figure provenance |
| Source names, pinned upstream source commit, metadata and file digests | Safe as source/identity documentation, **not** a right to host the upstream bytes | [Source card](skillcorner-source-card.md), [source authority](skillcorner-source-authority.md) |
| Small explicitly MIT-licensed Body Pose sample, if ever proposed as a release asset | Separate asset-specific attribution/notice and redistribution check; **do not automatically include** | Distinct Body Pose rights record in [rights audit](data-rights.md) |
| Raw SkillCorner tracking, events, phase CSVs and row-level derivatives | **NO-GO for FPD redistribution** pending written clarification; not a software-release asset | [SkillCorner rights audit](data-rights.md) |
| Private checkpoint/receipt/ledger/prediction or protected truth bytes | **NO-GO** unless separate exact-asset rights, data-reconstruction, confidentiality and owner authorizations exist | Explicit artifact-release review; private scientific/trust boundary |
| Public scientific code/package with claim of fully reproducible learned inference | **NO-GO**: original model bytes and source rows are not provided | [Reproducibility matrix](reproducibility.md#public-reproducibility-boundary) |
| Scientific paper or accepted/peer-reviewed result | **NO-GO for such a claim**; Paper A is ready for final owner review, not documented as submitted/accepted | [Paper A submission readiness](paper-a/submission-readiness.md) |

**Scope policy:** unresolved rights for **SkillCorner row-level data** do not automatically prohibit a **source-only software** release, but they do prohibit packaging the uncleared data with it. Each asset must be reviewed on its own rights and reconstructability. Do not collapse code, aggregates, metadata, upstream samples and private checkpoint bytes into one permission decision.

## Gates for a versioned source-code release

1. **Scientific claims and cards:** benchmark, data, model and limitation cards cover both prospective targets, frozen information regimes, masks, scoring, four-match independent unit and historical task boundaries. No implied completed training LOMO, source qualification or deployable realized-future forecast.
2. **Public reproduction:** a third party can run the quickstart and public aggregate checker without private data, and follow the documented *synthetic-only* full test prerequisite. Wheel and sdist smokes, reproducibility locks, scientific reference and site content checks pass on exact release head.
3. **Artifact hygiene:** inspect `git ls-files` and the actual would-be release payload (not just the diff); no raw upstream tracking, source-derived rows, private truth, ledgers, receipts, keys, model weights or unintended URLs/paths are distributed. Verify all allowlisted public files and checksums independently; the public source-only GitHub auto-generated archive is distinct from optional uploaded assets.
4. **Rights and attribution:** project maintainer explicitly attests authority to distribute every original contribution under Apache-2.0; third-party notices/source credits and any permissions for proposed *additional* assets are recorded. Do not manufacture ownership from a Git author.
5. **Authorship and citation:** obtain approved author names, order, roles/affiliations and consent before creating a valid `CITATION.cff`. Confirm who can license the manuscript/metadata if included. Do not guess email, ORCID, funding, institutions or DOI.
6. **Version consistency:** only once gates pass, advance `pyproject.toml` from `0.1.0.dev0` to the approved stable software version, update changelog/release notes, bind release file checksums and rerun exact-head CI. Record a frozen Git SHA and use a history-preserving merge.
7. **Archive:** create and verify the permanent archive record **only after** author/rightsholder approval and exact version/tag verification; distinguish *concept* and *version-specific* DOIs. No fake Zenodo accession, fabricated DOI or publication date.
8. **Integration:** cut a signed-off GitHub source release and archive only with exact-head quality/reproducibility evidence, complete metadata and appropriate owner sign-off. Note any missing external grants without changing protected status.

## Authorship/citation approval record — not yet completed

This repository intentionally has **no** `CITATION.cff` until required fields are verified and approved. A schema-valid citation needs `cff-version`, `message`, `title`, and **approved authors**. The final release may add `version`, `repository-code`, `license: Apache-2.0`, verified release date and DOI once assigned. A `preferred-citation` for Paper A must remain absent unless the paper's exact bibliographic state and author order are approved.

| Owner question | Required evidence | Current status |
| --- | --- | --- |
| Who are the software's rights-holders and release approvers? | Explicit authority statement covering original contributions and applicable employer/institution obligations | **UNCONFIRMED** |
| What is the final software author list and order? | Each named person's approval of attribution/role; affiliations only with confirmation | **UNCONFIRMED** |
| Which third-party materials need notices or separate grants? | Audited source/asset inventory and any required upstream notices | **PENDING FINAL PAYLOAD REVIEW** |
| Is a software-only release approved without private assets? | Owner approval of exactly which binaries/source archives/public aggregates will appear | **PENDING** |
| What version/tag and archive identifiers actually exist? | Verified final Git SHA/version/tag, registered DOI or archive permalink | **UNISSUED** |
| Is Paper A an accepted publication? | Journal record, not a manuscript draft | **NO ACCEPTANCE CLAIM** |

## Immutable release manifest — requirements

A final human/machine-readable manifest must separately bind: repository URL, exact tagged Git SHA, Python package version, license decision, checked asset paths/bytes/SHA-256, upstream source revision and rights class, scientific protocol and result identities, exact-run CI evidence, archive identifier if issued, and the explicit `NOT_QUALIFIED` research/production separation. Do not generate the manifest from an unverified tag or arbitrary private paths. A placeholder or receipt self-hash is not an independent authorization.

For current source and result identities, consult the immutable [source authority](skillcorner-source-authority.md), [prospective v2 protocol](prospective-skillcorner-protocol-v2.md), [public aggregate evidence](res440/findings.json) and [reproducibility model](reproducibility.md).

## Owner-controlled publication decision

Until the separate decisions above are documented, **NO-GO for stable v1.0.0 and archival deposit**, regardless of successful Python/site CI. This is compatible with continuing to publish and improve the already-public *development* source and non-reconstructive scientific description. Finishing this checklist is not itself a publication or rights grant.
