# Licensing, attribution, and citation governance

## License decision

Original FPD Bench software and project-written documentation are licensed under Apache License 2.0. Apache-2.0 is an OSI-approved permissive license with an express patent grant and contribution terms; it suits reusable research software without imposing a reciprocal source-distribution requirement. The complete official license is in the root [LICENSE](../LICENSE), and package metadata uses the SPDX identifier `Apache-2.0`. See the [Apache license text](https://www.apache.org/licenses/LICENSE-2.0.txt) and [OSI license entry](https://opensource.org/licenses/Apache-2.0).

The grant covers only material for which FPD contributors have authority to license. It does not license third-party material or SkillCorner data. In particular, the FPD code license must never be interpreted as licensing SkillCorner’s core tracking, events, phase data, aggregates, or row-level derivatives.

## Provenance and rights audit

This repository review was made on 2026-10-12 and considered tracked source, documentation, package metadata, dependencies, bundled assets, and Git history.

- The prior project metadata said `UNLICENSED`; the README said licensing was not finalized. No root `LICENSE`, `NOTICE`, or `CITATION.cff` existed.
- The visible Git history records commits under Julio Rodriguez only. No source copyright headers or imported source-code notices were found. Git authorship is evidence of commit provenance, not proof of copyright ownership or authority to license.
- There are no runtime dependencies. Hatchling is the build backend; pytest, Ruff, and Pyright are development tools. No dependency source code is vendored into the repository or package.
- The package contains project code and machine-readable source, measurement, and eligibility manifests plus a Croissant/RAI draft. These metadata files identify upstream sources and contracts; they do not contain SkillCorner tracking, event, phase, aggregate rows, or model weights. No image, font, media, model, or raw dataset payload is bundled.
- The existing [SkillCorner rights audit](data-rights.md) records **CONDITIONAL GO** for local public research use and retains a release gate on redistribution of core source files and row-level derivatives. It also distinguishes public open-data evidence from SkillCorner’s separate commercial/customer terms. This license decision does not change that result.

Repository evidence does not establish whether Julio Rodriguez owns or is authorized to license every original contribution, whether any employer or institution has rights in the work, or whether any unrecorded draft or source was incorporated. Before a public release or package publication, the maintainer must confirm those points and resolve any third-party provenance that cannot be established from the repository. No copyright holder or institutional affiliation is asserted here.

## Copyright, contributions, and notices

- Copyright remains with each verified rightsholder. Do not infer copyright ownership from a Git author, repository owner, organization name, or email domain. Add a copyright notice only when its holder, scope, and year are verified.
- Contributors retain their copyright and grant FPD Bench and downstream users the Apache-2.0 rights needed for accepted contributions. A contribution may be accepted only when its author confirms authority to submit it under Apache-2.0 and records whether it is original or identifies its upstream source, exact version/files, license, and required notices. No copyright assignment is required.
- Do not copy third-party code, documentation, or assets into the project unless their provenance, license compatibility, redistribution rights, and required notices have been checked. The root license does not replace those terms. Preserve upstream notices and identify modifications as required by the applicable license.
- No `NOTICE` file is added: the audited tree contains no vendored third-party component or asset with an upstream NOTICE or other project-level notice requirement. If such material is added later, preserve its required notices and add the applicable notice material to distributions.
- Cite SkillCorner as the data provider and identify the pinned source revision and selected matches when reporting work that uses its public data. Acknowledge PySport as the collaborating initiative, following the wording in the [source card](skillcorner-source-card.md). Do not copy source rows into attribution examples or treat attribution as permission to redistribute them.

## Contributor and publication roles

Git commit authorship records who made or signed a commit. It is not a publication-author list, a copyright determination, or evidence of institutional affiliation. Scientific authorship, acknowledgments, and affiliations are separate decisions.

Before a paper, release note, or citation record names a person as an author or assigns a publication role, keep a verifiable contribution record and obtain that person’s explicit approval of the role and its description. Obtain approval before naming someone in acknowledgments. Verify each institutional affiliation with the person and obtain their explicit approval; never infer an affiliation from an email domain or commit metadata. Do not imply institutional endorsement. Do not publish names, roles, acknowledgments, or affiliations that have not been verified and approved.

## `CITATION.cff` requirements

Use the [Citation File Format 1.2.0 schema guide](https://github.com/citation-file-format/citation-file-format/blob/main/schema-guide.md). A valid file requires `cff-version`, `message`, `title`, and `authors`. For a released software citation, also set the verified release `version`, `repository-code`, and `license: Apache-2.0`; include `preferred-citation` only when its bibliographic metadata and publication roles have been approved. Add a DOI or future archive identifier only after verifying it against the issuing archive. When available, distinguish the concept DOI from a version DOI and record other archival identifiers such as a Software Heritage identifier only when the archive has issued them.

No `CITATION.cff` is created in this change: the repository does not contain an explicitly approved scientific author list or a preferred publication citation. The current package version `0.1.0.dev0` is a development version, not a release citation. The designated final-release task retains final citation, DOI, and archive authority; it must supply approved authorship and verified release identifiers before the CFF is created.

## Distribution checks

`pyproject.toml` declares `Apache-2.0` using SPDX syntax and names the root `LICENSE` for packaging. The public-reproducibility workflow builds both wheel and sdist; its artifact smoke verifies the wheel’s SPDX metadata and bundled license and checks the sdist license and `PKG-INFO` metadata.
