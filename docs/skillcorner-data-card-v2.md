# SkillCorner prospective data card v2

V2 measures the same pinned SkillCorner Open Data release and selected 20-match source population under a successor nullable-ball contract. The source release hash remains `e92c417b7640b27399451134ee3fce4b1961b0c0dfc2e01175a8f3c906a9ae07`; the source-population hash remains `e9054b7ddc2dfeff4dd8425ea61a23ed0b326076a08899e47502484228fdbdf4`.

`skillcorner_5hz_v2` preserves source ball detection as true, false, or unknown null and keeps absent ball objects distinct from present objects with null coordinates. Provider null-flag meaning is undocumented. The unobserved null-flag/finite-XY combination is a source-specific population qualification stop, not an asserted provider semantic.

The contract does not publish raw tracking, row-level derivatives, restricted receipts, per-match source detail, target panels, truth hashes, or model results. Public outputs remain limited by the [data rights policy](data-rights.md). The protected 20-match population has not been qualified; aggregate coordinate availability does not establish eligible or scoreable windows.

Machine-readable authorities and verification commands are listed in [the measurement state](skillcorner-data-state-v2.md), [the eligibility policy](skillcorner-window-eligibility-v2.md), [the protocol](prospective-skillcorner-protocol-v2.md), and [the execution plan](prospective-experiment-plan-v2.md).
