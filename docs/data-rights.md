# SkillCorner Open Data rights audit and release policy

**Audit snapshot:** 2026-10-08. Published pages were read on this date. Repository and dataset revisions are recorded below where available. This is a source-backed project policy, not a claim that every right in the underlying broadcast-derived material has been independently cleared.

## Operational decision

**CONDITIONAL GO** for FPD Bench v1 research use under an acquisition/rebuild architecture.

SkillCorner Open Data is publicly released for research and practical analysis. The official documentation demonstrates downloading, normalizing, joining, analyzing, and visualizing it. The public repository is marked MIT. However, its MIT text refers to “software and associated documentation files,” and neither the root license nor a data-specific license expressly identifies the tracking, dynamic-event, phases-of-play, or season-aggregate files as licensed data. The public-use intent and repository-level MIT marker are evidence that SkillCorner intended a broad open release, but the exact scope of the grant for those data files remains unresolved. ([S1](#s1-skillcorner-open-data-repository), [S2](#s2-skillcorner-license), [S3](#s3-skillcorner-open-data-guidance))

Until SkillCorner confirms that scope in writing, FPD Bench may acquire and process the public core corpus locally for research, including training and evaluation, but must not host or redistribute its raw files or row-level derivatives. FPD may publish aggregate results, non-reconstructive visualizations, and source metadata with attribution. This is a conservative **project release policy** for the unresolved scope; it is not a finding that the MIT license forbids those uses. If SkillCorner confirms that the core data files and row-level derivatives are covered, the policy can be revised to permit redistribution under the confirmed terms.

The separate Hugging Face Body Pose dataset card explicitly labels the full dataset MIT and requests credit to SkillCorner. Redistribution and derivative redistribution of the Body Pose sample or full files are therefore permitted under that stated MIT license, subject to keeping the license notice and credit. ([S5](#s5-body-pose-documents-and-hosting))

The MIT grant has no non-commercial restriction and expressly allows sale of covered copies. That includes commercial use of SkillCorner code and, for Body Pose, the files identified by its explicit MIT dataset card. For the core tracking/event/phase/aggregate files, commercial use remains conditional on confirmation that those files are within the MIT license's subject matter.

## Audit snapshot of the live source

The official GitHub API reported default branch `master`, repository license `MIT`, and head `4340d274572876239c154c90bc507a9b3250a656` (commit date 2026-09-14). The recursive tree was not truncated and contained 181 entries. The pinned `data/matches.json` has 20 IDs, there are 20 corresponding match directories, and each directory contains all four documented files: match metadata, tracking, dynamic events, and phases of play. ([S1](#s1-skillcorner-open-data-repository), [S4](#s4-live-population-and-file-hosting))

The 20 match IDs, in the order in `matches.json`, are:

```text
2017461, 2016236, 2015213, 2013725, 2011166,
2010085, 2007721, 2007448, 2006363, 2006229,
1996435, 1996436, 1986691, 1959846, 1953632,
1927964, 1925299, 1899585, 1886347, 1874553
```

The README, GitHub repository description, and SkillCorner’s September 2, 2026 Open Data article still say “10 matches”; that article lists ten of the IDs above. The current repository tree and `matches.json` contain ten additional match IDs. The Hugging Face Body Pose card independently describes the rest of the open dataset as covering 20 A-League matches. This is source-population drift, so the README or blog count is not a safe data identity. ([S1](#s1-skillcorner-open-data-repository), [S3](#s3-skillcorner-open-data-guidance), [S5](#s5-body-pose-documents-and-hosting))

Current file and hosting observations:

- `matches.json` and the match metadata JSON files are ordinary Git blobs.
- All 20 `*_tracking_extrapolated.jsonl` paths are governed by `.gitattributes` as Git LFS files; the Git tree contains only 133- or 134-byte pointer blobs. A pointer records the payload size and SHA-256 object ID. The tracking payloads were not fetched for this audit.
- Dynamic-event CSVs and phases-of-play CSVs are ordinary Git blobs. They are source data even though their bytes are in Git rather than LFS.
- The repository contains three ordinary Git CSVs of season aggregates.
- The repository includes one 1,926,895-byte compressed Body Pose phase sample, plus a manifest and documentation. The two full Body Pose zip files are hosted in the public, ungated Hugging Face dataset through Git LFS/Xet, not in the GitHub tree.
- The GitHub Body Pose manifest points at mutable Hugging Face `main`. At audit time the Hugging Face dataset revision was `a62e1ec1e3b82952042a7f7fa9dafd77c0e0822a`, last modified 2026-09-08. The manifest records archive SHA-256 values and sizes: `1925299` is 623,408,231 bytes (`0415665098d594fb5681815000f7a6312037788a3237910a9f41bb8de5c336a0`); `1996435` is 644,327,811 bytes (`64bcab2be9776172d062521d9a97e0e6f391fc9cacb331f9e42a6fe88cf8434b`).

Git hosting, Git LFS, and Hugging Face are acquisition mechanisms, not evidence of permission to mirror an asset. No tracking, event, phase, aggregate, or Body Pose payload was downloaded for this audit, and no SkillCorner asset was added to FPD Bench.

## Rights matrix

`YES`, `NO`, `CONDITIONAL`, `UNCLEAR`, and `NOT_APPLICABLE` describe the source evidence or current FPD policy stated in the cell. A project-policy `NO` is not a claim that source terms prohibit the act. “Publication” means a paper, supplement, archive, or benchmark release. Source IDs link to the evidence record below.

| Artifact | Source / authority | Research use | Local transformation | Redistribute source bytes | Redistribute derivatives | Publication / supplement | Attribution requirement | Decision / confidence |
|---|---|---:|---:|---:|---:|---:|---|---|
| FPD Bench code | FPD repository; `UNLICENSED` in project metadata | YES within project | YES within project | NO public grant finalized | NO public grant finalized | CONDITIONAL on project licensing | None from SkillCorner | CONDITIONAL; project license is intentionally unchanged |
| SkillCorner repository code | Root MIT; copyright SkillCorner, 2020 [S2] | YES | YES | YES, MIT notice | YES, MIT notice | YES | Preserve copyright and permission notice | YES; high confidence for code and docs |
| Raw tracking bytes | Repository `data/matches`; MIT scope unresolved [S1–S4] | YES, public research intent | YES | CONDITIONAL | CONDITIONAL | CONDITIONAL; aggregate results and non-reconstructive figures only under current policy | Credit SkillCorner; retain MIT notice if the license applies | CONDITIONAL; data scope unresolved |
| Dynamic events | Repository `data/matches`; no separate data license found [S1, S2] | YES, public research intent | YES | CONDITIONAL | CONDITIONAL | CONDITIONAL; no event-row tables/files | Credit SkillCorner; retain MIT notice if applicable | CONDITIONAL; same repository-license ambiguity |
| Phases of play | Repository `data/matches`; no separate data license found [S1, S2] | YES, public research intent | YES | CONDITIONAL | CONDITIONAL | CONDITIONAL; no phase-row tables/files | Credit SkillCorner; retain MIT notice if applicable | CONDITIONAL; same repository-license ambiguity |
| Season aggregates | Repository `data/aggregates`; no separate data license found [S1, S2] | YES | YES | CONDITIONAL for the source CSVs | CONDITIONAL for player-season rows | YES for non-reconstructive aggregate results; source-row supplements remain conditional | Credit SkillCorner; retain MIT notice if applicable | CONDITIONAL for source rows; aggregate outputs allowed by project policy |
| Core source-row example snippets | Tracking/events/phases; core data license scope unresolved [S1–S4] | YES locally | YES | CONDITIONAL | CONDITIONAL | NO under current FPD policy | Credit SkillCorner; include notice if MIT applies | CONDITIONAL legally; currently exclude source rows from releases |
| Body Pose sample | Sample in GitHub repo; dataset card says MIT [S5] | YES | YES | YES, MIT notice | YES, MIT notice | YES, MIT terms | Preserve MIT notice; credit SkillCorner | YES; explicit dataset-card statement, high confidence |
| Full Body Pose files | Public Hugging Face dataset card says MIT [S5] | YES | YES | YES, MIT notice | YES, MIT notice | YES, MIT terms | Preserve MIT notice; credit SkillCorner | YES; explicit dataset-card statement, high confidence |
| FPD canonical derived rows | Derived from core tracking/events/phases | YES locally | YES | NOT_APPLICABLE | NO under current project release policy | NO as row-level benchmark data or supplements | SkillCorner credit in associated study; source revision in manifest | CONDITIONAL legal scope; current release policy is NO |
| FPD windowed fixtures / tensors | Derived from core tracking/events | YES locally | YES | NOT_APPLICABLE | NO under current project release policy | NO as row-level fixtures, arrays, or archives | SkillCorner credit in associated study; source revision in manifest | CONDITIONAL legal scope; current release policy is NO |
| FPD synthetic fixtures | Independently authored, no source rows or values | YES | YES | CONDITIONAL on FPD’s own license | CONDITIONAL on FPD’s own license | CONDITIONAL on FPD’s own license | No SkillCorner attribution required unless used for context | CONDITIONAL; FPD’s public license is not finalized |
| Trained model checkpoints | Model trained on public core corpus; no source-specific model term found [S1–S4] | YES locally | YES | NOT_APPLICABLE | CONDITIONAL | CONDITIONAL after rights clarification and source-reconstruction review | Credit and pinned training-source manifest | CONDITIONAL; source is silent on weights, not a stated prohibition |
| Aggregate paper results | Computed summaries, not source rows [S3] | YES | YES | NOT_APPLICABLE | YES for non-reconstructive aggregates | YES | Cite SkillCorner and identify source revision/matches | YES; project interpretation supported by open-data research and sharing guidance |
| Paper figures / trajectory visualizations | Derived from tracking; SkillCorner demonstrates and encourages sharing visualizations [S3] | YES | YES | NOT_APPLICABLE | CONDITIONAL; no image/video that reconstructs source sequences | CONDITIONAL; selected non-reconstructive figures only under current policy | Credit SkillCorner and identify source | CONDITIONAL; official practice is supportive, but not an express row-data license |
| Supplementary result tables | Non-reconstructive metric/result summaries | YES | YES | NOT_APPLICABLE | YES for aggregate result tables; NO for source-row extracts under current policy | YES for aggregate results only | Cite SkillCorner and identify source revision/matches | YES for aggregate tables; NO for row-level data tables under current policy |
| Source manifests / checksums | FPD metadata pointing to public sources; Git SHA/LFS SHA-256/HF revision [S4–S5] | YES | NOT_APPLICABLE | NOT_APPLICABLE (not source data bytes) | NOT_APPLICABLE | YES; do not embed source rows | Include official source URL, revision, match IDs, and checksum algorithm | YES; metadata is not a data mirror |

### Matrix interpretation

- **Repository code:** the root MIT license grants broad use, copying, modification, publication, distribution, sublicensing, and sale rights, with the copyright and permission notice included in copies or substantial portions. The GitHub repository-level `MIT` classifier agrees. This is a clear result for SkillCorner code and documentation; the literal “Software” scope does not unambiguously settle separately identifiable datasets.
- **Commercial use:** there is no non-commercial carveout in MIT. If a file is within the grant, its use, modification, redistribution, and sale are permitted subject to the notice. That is clear for SkillCorner repository code and explicit for Body Pose; it remains conditional for the other data files because their license scope is not explicit.
- **Core public data:** the README calls the corpus open-sourced and its stated goal includes access for researchers. Official SkillCorner tutorials load and transform the files, and a SkillCorner article creates static and animated tracking visualizations and asks authors to cite SkillCorner. These facts support research acquisition, local processing, and non-reconstructive research outputs. They do not expressly grant bulk redistribution of the tracking/event/phase/aggregate rows or row-level derivatives.
- **Derived data:** if the MIT grant covers a core source file, its broad modification and distribution terms plausibly cover a modified dataset. Because that premise is unresolved, FPD policy holds row-level derived rows and fixtures until written clarification. This is not a claim that every feature tensor or model weight legally reproduces its source.
- **Models:** no SkillCorner source reviewed states a blanket prohibition on learned weights. Conversely, no source reviewed expressly grants checkpoint rights or addresses memorization. The release gate is a project safeguard: obtain the core-data clarification and check whether a checkpoint embeds or can materially reconstruct source rows. This is not stated as a source-imposed rule.
- **Papers:** aggregate statistics and selected visualizations are consistent with SkillCorner’s public research and sharing materials. Under current core-data policy, papers and supplements must not include source-row snippets, raw files, row extracts, row-level arrays, or sequences that reconstruct them. The Body Pose MIT card is a separate explicit license.
- **Citations:** the inspected repository has no `CITATION.cff` or DOI. The source asks users to credit SkillCorner; the repository describes the release as a joint SkillCorner/PySport initiative. FPD policy requires SkillCorner attribution and recommends acknowledging PySport.

## Open data versus commercial/customer data

The public corpus is served from a public GitHub repository and a public, ungated Hugging Face dataset. The official open-data materials describe it as free/open data for researchers and analysts. SkillCorner’s current Standard Terms, dated 1 May 2026, define the “Agreement” as a Work Order plus the terms. They define “Licensed Data” as data licensed to a **Partner** under that Agreement, grant the Partner a limited, non-transferable and non-sublicensable right to use it, and prohibit copying, modifying, or redistributing the contracted data except as the Agreement permits. These terms concern that paid Partner/Work Order regime; they do not automatically replace or expand the public repository’s terms. ([S3](#s3-skillcorner-open-data-guidance), [S5](#s5-body-pose-documents-and-hosting), [S7](#s7-commercial-standard-terms))

FPD must keep public open data separate from credential-gated API data, customer Work Order data, and other private SkillCorner material. The public MIT marker does not grant rights to those other regimes. This audit did not access commercial endpoints or private data.

## FPD Bench v1 release policy

1. Use an **acquisition/rebuild architecture** for the core tracking, dynamic-event, phases-of-play, and season-aggregate corpus. FPD publishes transformation code and source references; each user obtains the original files from SkillCorner’s official public source. FPD does not mirror the core raw files or row-level derivatives in repository fixtures, model/data artifacts, paper supplements, or archival releases until the data scope is confirmed in writing.
2. Local research processing, transformations, training, and evaluation are allowed for the public corpus. Store source bytes outside the FPD repository. Do not cross this authority to private API/customer files.
3. Any future experiment must record a pinned Git commit (not `master`), an explicit selected match list, exact upstream file paths, and source-byte SHA-256 hashes. For Git LFS assets, verify the downloaded payload against the pointer’s SHA-256 and byte count. For Body Pose, pin a Hugging Face commit rather than `main` and verify the archive hashes.
4. Public papers may include aggregate statistics, non-reconstructive plots, selected action visualizations, result tables, and non-sensitive source metadata, with SkillCorner attribution and reproducibility references. Do not put source rows or row-level derived tables/files in a supplement.
5. Body Pose has an explicit MIT dataset-card statement. It may be redistributed and transformed under that MIT license with its notice and SkillCorner credit. The current FPD repository still applies its general 10 MiB artifact limit; large Body Pose archives should be linked to their official host rather than added to this code repository.
6. Checkpoints trained on the core corpus require written confirmation of the source-data license scope and a review for embedded or materially reconstructible source rows before publication. The source does not itself state a blanket weights restriction.
7. FPD Bench’s own code remains marked `UNLICENSED`; this audit does not choose or change a project license.

## Clarification required before row-level redistribution

The ambiguity is material to a public benchmark because redistributing its canonical rows or fixtures is central to a downloadable dataset release. Obtain written confirmation from SkillCorner before FPD hosts or republishes raw core data, row-level derivatives, or a checkpoint that may materially reproduce those rows. Do not send this request as part of this audit.

Exact clarification questions:

1. **Does the MIT license in `SkillCorner/opendata` apply to the contents of `data/matches/` and `data/aggregates/` themselves—including tracking JSONL, dynamic-event CSV, phases-of-play CSV, match metadata, and season aggregates—or only to repository software and documentation?**
2. **If it applies to those data files, may users copy, modify, publish, redistribute, and commercially use the raw files and row-level modified or derived datasets (including downsampled rows, normalized coordinates, windows/tensors, and Parquet/JSON/NPZ equivalents), provided the MIT notice and SkillCorner credit are retained?**
3. **Does the same permission cover non-reconstructive trained model checkpoints and selected trajectory figures, and is any additional PySport acknowledgement required?**

Until answers to questions 1–2 are received, row-level redistribution is a release gate. The public research, local transformation, aggregate publication, and attribution policy above remains in effect.

## Attribution text for current public-core research

> Data source: SkillCorner Open Data, released by SkillCorner in a joint initiative with PySport. Retrieved from [SkillCorner/opendata](https://github.com/SkillCorner/opendata) at commit `4340d274572876239c154c90bc507a9b3250a656` on 2026-10-08. Selected match IDs: `<explicit IDs>`. SkillCorner is credited as the data provider. The source population and file hashes are recorded in the experiment manifest.

For Body Pose, additionally cite [SkillCorner/opendata-bodypose at revision `a62e1ec1e3b82952042a7f7fa9dafd77c0e0822a`](https://huggingface.co/datasets/SkillCorner/opendata-bodypose/blob/a62e1ec1e3b82952042a7f7fa9dafd77c0e0822a/README.md) and retain its MIT notice. If redistributing any material actually covered by SkillCorner’s MIT grant, include the unmodified SkillCorner copyright and MIT permission notice with those copies.

## Evidence record

Pages without a source revision were checked on 2026-10-08. A URL being public or technically downloadable was treated as evidence of acquisition mechanics, not as a license.

### S1 — SkillCorner Open Data repository

[Repository](https://github.com/SkillCorner/opendata) and pinned [README at `4340d274572876239c154c90bc507a9b3250a656`](https://github.com/SkillCorner/opendata/blob/4340d274572876239c154c90bc507a9b3250a656/README.md), retrieved 2026-10-08. The current repository metadata reports default branch `master`, GitHub SPDX license `MIT`, and the head recorded in this audit. The README says the repo contains open-sourced broadcast tracking, derived Dynamic Events, aggregates, and Body Pose and requests SkillCorner credit. Its prose says ten matches; the pinned tree’s live `matches.json` has twenty.

### S2 — SkillCorner repository license

[Root `LICENSE` at `4340d274572876239c154c90bc507a9b3250a656`](https://github.com/SkillCorner/opendata/blob/4340d274572876239c154c90bc507a9b3250a656/LICENSE), retrieved 2026-10-08. It is MIT, copyright “2020 SkillCorner,” and contains the ordinary broad permission grant and notice requirement. No separate license file or data-specific license was present in the inspected tree. **Inference:** root placement, repo-level MIT metadata, the README’s open-source statement, and the absence of exclusions suggest broad intent, but do not expressly define data files as part of “Software.”

### S3 — SkillCorner open-data guidance

[Analytics Cup](https://www.skillcorner.com/us/analytics-cup-2027), retrieved 2026-10-08, describes a SkillCorner/PySport initiative to open source data for research, new approaches, and shared work. SkillCorner’s [Open Data #5 article](https://www.skillcorner.com/us/articles/skillcorner-open-data-5-visualising-football-tracking-data), published 2026-09-02 and retrieved 2026-10-08, says the free 2024/25 release has ten matches, shows loading and transforming tracking, creating static and animated visualizations, and invites authors to share work while crediting SkillCorner. These are source facts about intent and examples, not express terms authorizing mirror copies of every row.

### S4 — Live population and file hosting

GitHub’s [repository API](https://api.github.com/repos/SkillCorner/opendata), default-branch ref, commit, and recursive tree were retrieved 2026-10-08. The `master` head was `4340d274572876239c154c90bc507a9b3250a656`, committed 2026-09-14. The pinned [matches index](https://raw.githubusercontent.com/SkillCorner/opendata/4340d274572876239c154c90bc507a9b3250a656/data/matches.json), [.gitattributes](https://github.com/SkillCorner/opendata/blob/4340d274572876239c154c90bc507a9b3250a656/.gitattributes), and [Body Pose README](https://github.com/SkillCorner/opendata/blob/4340d274572876239c154c90bc507a9b3250a656/data/bodypose/README.md) support the counts and hosting details above. The `.gitattributes` rule marks `*.jsonl` for Git LFS. **Method limit:** the LFS payloads were not downloaded or independently rehashed; tree pointers expose the LFS SHA-256 and size.

### S5 — Body Pose documents and hosting

The [pinned GitHub Body Pose README](https://github.com/SkillCorner/opendata/blob/4340d274572876239c154c90bc507a9b3250a656/data/bodypose/README.md) identifies two full files on Hugging Face and one committed phase sample. Its [manifest](https://github.com/SkillCorner/opendata/blob/4340d274572876239c154c90bc507a9b3250a656/data/bodypose/MANIFEST.json) records `hf_revision: main` plus archive sizes and SHA-256 values. The public [Hugging Face dataset card at revision `a62e1ec1e3b82952042a7f7fa9dafd77c0e0822a`](https://huggingface.co/datasets/SkillCorner/opendata-bodypose/blob/a62e1ec1e3b82952042a7f7fa9dafd77c0e0822a/README.md) explicitly says “MIT, matching the opendata repository” and asks users to credit SkillCorner. The Hugging Face API reported that revision (last modified 2026-09-08), `gated: false`, and two LFS/Xet archives, retrieved 2026-10-08. The card describes this as an initial two-match testing release.

### S6 — Live count disagreement

The pinned GitHub README, GitHub repository description, and SkillCorner [Open Data #5 article](https://www.skillcorner.com/us/articles/skillcorner-open-data-5-visualising-football-tracking-data) say ten matches. The [Hugging Face Body Pose card](https://huggingface.co/datasets/SkillCorner/opendata-bodypose) says the rest of the open dataset covers 20 matches, and the pinned `matches.json` plus live tree count 20. The file population, not stale prose count, is the source fact used here.

### S7 — Commercial Standard Terms

SkillCorner’s current official [Standard Terms and Conditions PDF](https://26560301.fs1.hubspotusercontent-eu1.net/hubfs/26560301/SkillCorner%20T%26Cs_.pdf), dated 1 May 2026 and retrieved 2026-10-08, defines the Agreement as the applicable Work Order plus the terms; defines Licensed Data as data licensed to the Partner under that Agreement and further specified by the Work Order; grants only a limited use license subject to fees; states SkillCorner retains rights; and prohibits the Partner from copying, modifying, or redistributing the contracted Data except as the Agreement expressly permits (§§1.1–1.2, 2.1, 3.2–3.3). It is used only to distinguish that customer-contract regime from the public repository/Hugging Face release, not to impose customer terms on public data.
