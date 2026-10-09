# SkillCorner Open Data source authority

**Verified:** 2026-10-09. This is the immutable upstream source authority for the prospective SkillCorner-backed FPD Bench v1 program. It does not define a benchmark data-state transform, windows, targets, quality rules, information boundaries, splits, evaluator, or training.

## Pinned source release

The official [SkillCorner/opendata repository](https://github.com/SkillCorner/opendata) uses default branch `master`. At verification, `master` pointed to commit [`4340d274572876239c154c90bc507a9b3250a656`](https://github.com/SkillCorner/opendata/commit/4340d274572876239c154c90bc507a9b3250a656), the selected canonical release. Its pinned recursive Git tree had 181 entries and was not truncated. The root `LICENSE`, `README.md`, `.gitattributes`, `data/matches.json`, all match directories, `data/aggregates/`, and `data/bodypose/` were inspected.

The `README.md` still says ten matches, as does SkillCorner's September 2, 2026 [Open Data article](https://www.skillcorner.com/us/articles/skillcorner-open-data-5-visualising-football-tracking-data). The pinned `data/matches.json` and its tree contain twenty matches and twenty corresponding directories. The mismatch is documentation drift; the pinned index and tree define the population. A match listed as `not_started` is still selected because all four expected source files exist and no source-level evidence justifies exclusion. Downstream semantic and quality decisions remain open.

## Source population

All twenty available matches are selected. No source matches are excluded. Selection requires the pinned index entry, match directory, match metadata, tracking path, dynamic-events file, and phases-of-play file to be present. It does not imply that any frame or window is eligible for a future benchmark.

Selected match IDs, sorted for display:

```text
1874553, 1886347, 1899585, 1925299, 1927964,
1953632, 1959846, 1986691, 1996435, 1996436,
2006229, 2006363, 2007448, 2007721, 2010085,
2011166, 2013725, 2015213, 2016236, 2017461
```

`data/matches.json` preserves the upstream order separately. The source-population hash treats membership as a set, so a reordered index does not change population or source-release identity.

## File identity and acquisition

The machine-readable authority is [`src/fpdbench/data_sources/skillcorner_open_data_v1.json`](../src/fpdbench/data_sources/skillcorner_open_data_v1.json), schema `fpdbench.skillcorner-source-authority` version `1.0.0`.

- Ordinary Git files record the repository path, pinned raw URL, Git blob SHA-1, and byte size. The index and match-metadata files also record raw-byte SHA-256 values because those bytes were inspected. Dynamic-event and phases-of-play CSVs are identified by their Git blobs; their row bytes were not fetched for this audit.
- Tracking files are Git LFS pointers. Their Git blob SHA-1 identifies the pointer only; the pointer's `oid sha256` and declared size identify the tracking payload. No tracking payload was downloaded.
- The index lists 20 IDs and the recursive tree has exactly the 20 corresponding directories and 80 expected per-match files. The three season-aggregate CSVs are recorded as observed repository artifacts but are outside this motion-source population.
- The core source release hash covers the repository, pinned commit, selected match IDs, and each selected per-match file identity. The source-population hash covers selected IDs. The acquisition-manifest SHA-256 covers the deterministic complete manifest, including descriptive and optional-source metadata. No local paths, hostnames, or runtime timestamps enter source-release identity.

The official rebuild path is GitHub at the full pinned commit, never a branch name:

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone --no-checkout https://github.com/SkillCorner/opendata.git /path/outside/fpdbench
GIT_LFS_SKIP_SMUDGE=1 git -C /path/outside/fpdbench checkout --detach 4340d274572876239c154c90bc507a9b3250a656
uv run fpdbench sources verify --local-root /path/outside/fpdbench
```

That check validates the exact `matches.json` population, refuses missing or unexpected match directories/files, checks ordinary files by their Git blob SHA-1 and recorded raw SHA-256 where present, and validates LFS pointers. If tracking payloads have separately been acquired into that external checkout, it hashes each payload against the pinned LFS OID and size. It does not download, copy, or write source files. The optional live check is `uv run fpdbench sources verify --live`; it reads the pinned commit/tree and small index, metadata, and LFS pointer objects from official hosts, then reports failure on default-branch, file, index, pointer, or external Body Pose revision drift. It never updates this manifest or substitutes a new head.

The regular `uv run fpdbench sources verify` is offline and checks the checked-in authority only. CI therefore does not depend on SkillCorner or Hugging Face availability.

## Rights and separate Body Pose source

This authority follows the [rights policy](data-rights.md). Core SkillCorner tracking, events, phases, and aggregates may be acquired and processed locally for public research, but FPD must not commit or host their raw bytes or row-level derivatives until the unresolved data-license scope is confirmed in writing. This repository contains no SkillCorner tracking, event, phase, or aggregate payloads, and no derived row-level fixtures. Attribution and the rights gate remain in effect.

Body Pose is optional and is not part of this core source-release hash. The authority records the GitHub manifest/sample identities and pins the public [SkillCorner/opendata-bodypose](https://huggingface.co/datasets/SkillCorner/opendata-bodypose) dataset at revision `a62e1ec1e3b82952042a7f7fa9dafd77c0e0822a`, rather than the GitHub manifest's mutable `main` reference. The pinned official manifest records two archives:

| Match | Archive SHA-256 | Bytes |
| --- | --- | ---: |
| 1925299 | `0415665098d594fb5681815000f7a6312037788a3237910a9f41bb8de5c336a0` | 623,408,231 |
| 1996435 | `64bcab2be9776172d062521d9a97e0e6f391fc9cacb331f9e42a6fe88cf8434b` | 644,327,811 |

The pinned Hugging Face dataset card explicitly states MIT and requests SkillCorner credit; its notice and attribution remain required. Live verification detects if the Hugging Face `main` head moves away from the pinned revision.

## Boundaries and handoff

The source release identity is upstream provenance only. It is not a canonical 5 Hz `data_state_id`, benchmark scientific lock, target schema, fixture manifest, split, evaluator binding, or training identity. Those decisions are deferred to downstream transform and quality work. Neither downstream issue is executed here. The historical R0–R3 reproducibility snapshot is unchanged.

Manifest identities:

- Source population hash: `e9054b7ddc2dfeff4dd8425ea61a23ed0b326076a08899e47502484228fdbdf4`
- Source release hash: `e92c417b7640b27399451134ee3fce4b1961b0c0dfc2e01175a8f3c906a9ae07`
- Manifest SHA-256: `8b44740efaea01051e3dadfc0111bed284d1d71807266ebe3c1280b408e54107`
