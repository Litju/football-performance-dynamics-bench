# Public research-software release gates

**Status:** candidate version `1.0.0` for an explicitly **software/source-only GitHub release**. The maintainer approved the Apache-2.0 license authority for original code/documentation and the sole software author in [AUTHORS.md](../AUTHORS.md) and [CITATION.cff](../CITATION.cff). **Neither the source tree nor a green CI job alone proves a GitHub tag/release exists.** A separate DOI/archival deposit, private model/data redistribution and protected-population qualification remain unapproved. Check [GitHub Releases](https://github.com/Litju/football-performance-dynamics-bench/releases) for actual publication.

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
6. **Version consistency:** the proposed `1.0.0` version must agree across `pyproject.toml`, `uv.lock`, `CITATION.cff`, source-only release notes, build distribution metadata and final tag. Run exact-head tests and package checks after all version changes and preserve history in a non-squash merge.
7. **Archive:** create and verify the permanent archive record **only after** author/rightsholder approval and exact version/tag verification; distinguish *concept* and *version-specific* DOIs. No fake Zenodo accession, fabricated DOI or publication date.
8. **Integration:** the GitHub **source-only** release may be issued via the guarded owner-dispatched workflow only after full exact-head checks, signed-off original-code scope, public aggregate asset audit, CFF, release version and notes are verified. Any later Zenodo/DOI **archival** release is a separate approval/action; never imply DOI assignment from a GitHub tag. Note unresolved external rights without changing protected status.

## Authorship/citation approval record — partially completed

The root [CITATION.cff](../CITATION.cff) records **Julio Rodriguez** as the sole explicitly approved **software** author and declares the **candidate version 1.0.0** with code repository and Apache-2.0 license. The version alone does not establish that a tag or GitHub Release was issued; verify those externally. No DOI, institutional affiliation, paper author list or publication date is asserted. Add an archival DOI only after its independent issuance; a `preferred-citation` for Paper A remains out of scope without distinct author/publication approval.

| Owner question | Required evidence | Current status |
| --- | --- | --- |
| Who may license the original project code/docs? | Maintainer approval to release rights-controlled original contributions under Apache-2.0; additional third-party rights remain separate | **OWNER ATTESTED** for original software and project-written documentation; final source payload still requires inspection |
| What is the software author list and order? | Explicit contributor approval of the software citation role | **APPROVED:** Julio Rodriguez, sole software author; no affiliation/ORCID asserted |
| Which third-party materials need notices or separate grants? | Audited source/asset inventory and any required upstream notices | **PENDING FINAL PAYLOAD REVIEW** |
| Is a software-only release approved without private assets? | Owner request for a source-only release, plus final exact-payload safety/rights check | **OWNER REQUESTED** for software/source and public aggregates; final exact-payload review still pending |
| What version/tag and archive identifiers actually exist? | Exact checked release SHA, source-only GitHub tag, distinct DOI issuance | **v1.0.0 SOURCE CANDIDATE**; no tag or DOI is asserted until independently verified |
| Is Paper A an accepted publication? | Journal record, not a manuscript draft | **NO ACCEPTANCE CLAIM** |

## Separate release workflow and archival decision

The repository provides a **manual-only** GitHub Actions workflow, `.github/workflows/publish-source-release.yml`. Only the repository owner may dispatch it from `main` with the exact source-only confirmation token. It repeats the complete public test/validation and packaging gates, verifies software citation/version, audits committed public aggregate file bytes, builds and hashes the wheel and source distribution, refuses an existing tag, then creates an annotated `v1.0.0` tag and publishes a GitHub Release with source-only assets and immutable build checksums. If any step fails before tagging, **no release must be claimed**. If GitHub rejects tag creation or publishing, report the failure and leave the relevant release step incomplete.

That GitHub release is **not** equivalent to an archival DOI. A future Zenodo/other archival deposit needs an actual provider connection, verified archive contents, metadata, version and separately recorded authority. The scope of the existing research results does not change with software versioning.

## Immutable release manifest — requirements

A final human/machine-readable manifest must separately bind: repository URL, exact tagged Git SHA, Python package version, license decision, checked asset paths/bytes/SHA-256, upstream source revision and rights class, scientific protocol and result identities, exact-run CI evidence, archive identifier if issued, and the explicit `NOT_QUALIFIED` research/production separation. Do not generate the manifest from an unverified tag or arbitrary private paths. A placeholder or receipt self-hash is not an independent authorization.

For current source and result identities, consult the immutable [source authority](skillcorner-source-authority.md), [prospective v2 protocol](prospective-skillcorner-protocol-v2.md), [public aggregate evidence](res440/findings.json) and [reproducibility model](reproducibility.md).

## Owner-controlled publication decision

**Conditional GO for an owner-dispatched, verified source-only GitHub v1.0.0 software release:** original-code authority and sole software authorship are approved; final head, package and public aggregate payload checks must still succeed, and the maintainer must explicitly initiate the guarded workflow. **NO-GO remains for DOI/Zenodo deposit, unapproved third-party row-level data, private checkpoint distribution, protected population qualification and any journal-publication claim.** Completion of this document alone is not publication.
