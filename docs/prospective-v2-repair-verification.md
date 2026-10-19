# Nullable-ball v2 independent-review repair verification

Reviewed starting HEAD: `3c42b83859d41378afa74c665f258977835ae73f`. Implementation commit: `3f94795effd759121608ad2047732ab531c26d1e`. Work stayed on the existing draft PR [#19](https://github.com/Litju/football-performance-dynamics-bench/pull/19), addressing [review 5566183987](https://github.com/Litju/football-performance-dynamics-bench/pull/19#pullrequestreview-5566183987). Final push HEAD and exact-head CI are reported with the delivery response.

## Changed successor hashes

Acyclic regeneration order: unchanged source and measurement authorities → eligibility → protocol (including benchmark digest verification) → population/result schema bytes → execution plan. Schema bytes bind upstream science; the plan pins schema bytes. No schema embeds its downstream plan digest.

| Authority | SHA-256 |
| --- | --- |
| Eligibility v2 | `ed1cdc20ca7a93040fd4aabc91655819c5c4b8c58021c6540c6aaea325dafa11` |
| Protocol v2 | `3d7bdc46300b966a4da274579d21ac4c8219e1ef897719d6b7a308596e9f1d9f` |
| Population schema v2 bytes | `27da86b7355c311a65c68ab9b2bd3ae86e27779ed48641c23181ffe2f9adc224` |
| Result schema v2 bytes | `d0d7dbf4a14cade66d1e0ce7282441d8f035a68de8a192ad8e4d70210be18f7f` |
| Plan v2 | `a59fee6ee8e9fb03f4f0ccdae1933458af2bbf2375db7e6cd2bdf10962e42b62` |

Measurement v2 remains `1ecf355b3e6e2f04967e8363c1fdecc7f40707a7dda9966ebee1b3d90e97e671`.

## Adversarial synthetic evidence

- The horizon tests reject 24/16 and 26/14 despite their 41-slot total, plus truncated alternatives. The only supported pair is 25 history / 15 future intervals.
- The drift-boundary tests reject a truncated scan, one record per pinned match, a manually constructed object claiming all 622,414 retained samples and all 20 matches, and an incomplete caller-supplied receipt. Scans return diagnostics only; none authenticate exhaustive source coverage.
- AT-07 checks an otherwise structurally valid manifest, one empty required match, all empty matches, arbitrary resealed truth hashes, a changed resealed mask, an arbitrary candidate digest, and an injected receipt. None can become empirically qualified or authorize a completed result. Unknown receipt fields fail structural validation.
- AT-05 exercises the production absolute target and displacement target/inverse functions with nonzero origins. All three regimes share physical truth and mask identities across both representations; changing a mask changes its digest. Even physically consistent synthetic panels cannot authorize empirical scoring without independent source verification.
- A finite-XY origin with false detection remains eligible in synthetic candidate mechanics. The unapproved detection-at-origin exclusion is absent. The separate null-flag/finite-XY global sentinel still stops synthetic candidate processing.

No protected receipt verifier or qualification PASS is implemented or simulated as valid authority. The public v2 eligibility gate rejects every unverified object. Structural population objects expose `empirically_qualified == False`; the qualification boundary rejects empty required matches and otherwise blocks pending independent protected verification. Failed-validation result documents remain structurally inspectable.

## Validation

- Full pytest: **415 passed**, including the 19 new adversarial/parity parameter instances.
- Ruff lint and format: passed. Strict Pyright: **0 errors, 0 warnings**.
- Naming, repository and evidence validation: passed (232 evidence references / 63 digests).
- Reproducibility check: passed; snapshot SHA-256 `a22f93f11cf428b7f326a93714fbcc798c99e5d0dbcab5122edb48d050b4a873`.
- `uv build` and `tools/wheel_smoke.py`: passed. Wheel and wheel rebuilt from sdist were installed in separate fresh environments and tested from empty working directories with isolated Python; both include and validate all v2 authorities.

## Preserved historical hashes

The following scientific values and frozen byte hashes match the reviewed starting HEAD. No v1 authority, schema, lock, or snapshot file was edited; the full existing test suite preserves the v1 API and scientific behavior.

| Historical authority | SHA-256 |
| --- | --- |
| Source release | `e92c417b7640b27399451134ee3fce4b1961b0c0dfc2e01175a8f3c906a9ae07` |
| Source population | `e9054b7ddc2dfeff4dd8425ea61a23ed0b326076a08899e47502484228fdbdf4` |
| Measurement v1 | `4c29471c7fccc037dcfafd30222991e06d150e0887c0b667918bfa374262c6c3` |
| Eligibility v1 | `f0e1186f765cc7ce19c95152d8d6eacc66382f7e7f5a9ad1aa11c88c8a12f70b` |
| Protocol v1 | `865601662f4462178eaf7e1049075668176a9bd35f3bf4b1b6b8aa370de1d26c` |
| Plan v1 | `0446649e1ad049880cf6f8a76b4f3e03421d8bd7a1f7a2c562b5770461527775` |

All 12 tracked v1/lock/snapshot JSON files were also compared byte-for-byte against the starting HEAD:

| File | Byte SHA-256 |
| --- | --- |
| `benchmarks/conditional_multi_agent_motion_prediction/lomo_raw_displacement_scientific_lock.json` | `d3fa4e56b1d4c7c93b424960e0440217f2c45252ceab85f0fc516eb26a3fd621` |
| `benchmarks/conditional_multi_agent_motion_prediction/public_validation_physical_diagnostic_scientific_lock.json` | `ba2c5016cf31e9af43377cf14a72ab9f481f9715a17643c7ee8e486358f9b1ac` |
| `benchmarks/conditional_multi_agent_motion_prediction/public_validation_raw_displacement_scientific_lock.json` | `1f0254c5d687aa6a383d8ce6b53fe825473a6f23cbd7f9bbf7c787a362fa1171` |
| `benchmarks/reproducibility_snapshot.json` | `a22f93f11cf428b7f326a93714fbcc798c99e5d0dbcab5122edb48d050b4a873` |
| `src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction/empirical_experiment_plan_v1.json` | `636b50ee1f4c1c218d6d9f9348da695e9250502039629d304ef42c313d9eccc3` |
| `src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction/evaluation_population_authority_v1.schema.json` | `13cc71c618972cd2614b29ed1028172866bd68de7bf1df61058523c1cc2b8cde` |
| `src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction/prospective_experiment_result_v1.schema.json` | `7c81ea13d5c8accdeb1e900217abbfd7c84409955fd49388dea0eaaac49ae527` |
| `src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction/prospective_skillcorner_protocol_v1.json` | `34c43661edb44f656d6b1b064b79886044935cf1f2df6cc395b3ed0ef330fd3c` |
| `src/fpdbench/data_sources/skillcorner_open_data_v1.json` | `938cded522ee08f5de539976752fde51b2e858709574f3f63380bd72dd1af7fc` |
| `src/fpdbench/data_states/skillcorner_5hz_v1.json` | `e8380ea517ba71058186ac7f30f86a1d2854007081db7534801d6164c9f87b56` |
| `src/fpdbench/eligibility/skillcorner_window_v1.json` | `303169a799568020cc5c458025fa759b403d9031348ce78cd383ae59e4caf698` |
| `src/fpdbench/evaluation/absolute_xy_calibration_lock.json` | `f3b4155899c5d8e9632e9cab7a25e471411c62c4a9a7489c58c1edb16180ce94` |

Restricted data processing, real population qualification, GPU training, checkpoint selection, LOMO, scoring, and unrelated merges were not performed. Empirical v2 work remains blocked pending the separate independent protected-population verifier and qualification.
