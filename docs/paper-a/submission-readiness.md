# Paper A submission readiness

**Ready for final owner review.** The research scope is benchmark methodology, historical reconstruction and one bounded descriptive demonstration. The package supports the four-match description under `NOT_QUALIFIED`. Independent protected qualification, additional matches and training LOMO are outside the claims of this manuscript.

| Item | Review artifact |
| --- | --- |
| Manuscript and reviewer appendix | [Anonymous PDF](manuscript.pdf), [LaTeX](manuscript.tex), [references](references.bib), [appendix source](appendix.tex) |
| Reproducibility and supporting assets | [Canonical supplement](supplement.md), including the three methodological schematics, release policy and public verification commands |
| Scientific and originality review | [Claim and A/B audit](scientific-audit.md), including result-level ownership and the evidence for the limited example |
| Submission text | [Cover letter and contribution statement](submission-text.md) |
| Venue decision | [Recovered venue strategy](../paper-a-venue-and-submission-strategy.md). Its October readiness assessment reflects the earlier evidence. This review uses the subsequently completed descriptive study and leaves protected status unchanged. |

## Format and build

Use Tectonic 0.17.0 from this directory. The two unmodified TMLR style files are pinned to [upstream revision `7bf90efe`](https://github.com/JmlrOrg/tmlr-style-file/tree/7bf90efe3a0debbba703c05c43f3ff7e4d4a2992) and include their [upstream license](tmlr-license.txt). The standard review header is supplied by the template.

```sh
cd docs/paper-a
SOURCE_DATE_EPOCH=1794960000 tectonic manuscript.tex
```

TMLR requires its LaTeX layout and double-blind submission via OpenReview. The formatted PDF includes the reviewer appendix after the references. The journal has no fixed page cap and allows optional anonymized PDF or ZIP supporting material up to 100 MB. Use the manuscript PDF as the review file. The repository supplement, recovered venue decision, overlap audit and cover letter contain owner/repository context for internal review. Any separately supplied review copy of code or artifacts must be anonymized with license and attribution notices preserved. [TMLR author guide](https://www.jmlr.org/tmlr/author-guide.html), [submission instructions](https://www.jmlr.org/tmlr/submissions.html)

## Owner decisions and external requirements

1. Approve the scientific text and A/B result allocation, attest that no overlapping archival version is published, accepted or under review elsewhere, and approve the anonymous PDF for submission. The title and project are already identifiable through the public repository, so the review PDF omits that repository URL, author information and issue links. Recheck supplementary upload choices and anonymity at the point of submission. Reapply the recorded partition to Paper B when an archival draft exists. [TMLR originality and review policies](https://www.jmlr.org/tmlr/editorial-policies.html)
2. Confirm the complete and final author list, roles, affiliations, permissions and acknowledgments. Confirm rightsholder authority to license the submitted material under CC BY 4.0 from submission, preserving existing third-party notices and SkillCorner attribution. Obtain author-approved human-subjects/IRB reporting, funding and competing-interest disclosures. The manuscript claims no institutional determination. [TMLR author guide](https://www.jmlr.org/tmlr/author-guide.html)
3. Verify active, complete OpenReview profiles and sufficient TMLR quota for every author. Complete conflict information and identify suitable unconflicted action editors. These are account- and author-specific. [TMLR editorial policies](https://www.jmlr.org/tmlr/editorial-policies.html), [OpenReview venue](https://openreview.net/group?id=TMLR)
4. Authorize the OpenReview submission and any separate public preprint upload. A preprint is optional and requires its own approval. TMLR permits preprints while requiring double-blind review materials to omit identified copy links. [TMLR author guide](https://www.jmlr.org/tmlr/author-guide.html)
