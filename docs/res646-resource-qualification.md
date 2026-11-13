# RES646 synthetic resource qualification

Public-safe. Every input is invented (artificial fixtures, artificial DeepSets checkpoints,
ephemeral test signing keys). No real source, checkpoint, owner key or authorization was used.
Raw numbers: `docs/res646-synthetic-resource-report.json`, produced by
`tools/res646_qualification.py` at commit `adabd73` (execution-path files are unchanged since).

Runtime: Python 3.12.8, NumPy 2.2.4, PyTorch 2.6.0+cpu, CPU only, one thread, zero paid compute.
Each point is a complete signed campaign through the detached supervisor: launcher, setup, model
load, source identity pass, decoding, inference, independent feature/truth/metric audit, receipt
sealing, ledger operations, final verification. Fixture generation is outside the campaign.

| samples/match | eligible windows | records | CPU s | wall s | peak combined RSS | transient disk |
|---:|---:|---:|---:|---:|---:|---:|
| 60 | 80 | 72 | 21.1 | 22.4 | 435 MiB | 174 KB |
| 240 | 800 | 72 | 90.2 | 93.0 | 436 MiB | 183 KB |
| 1040 | 4,000 | 72 | 437.4 | 449.7 | 437 MiB | 226 KB |

Marginal cost between 800 and 4,000 windows is 0.108 CPU s/window (fixed cost ≈ 3.7 s); wall/CPU
is 1.03. RSS and transient disk are flat (they depend on receipts, not window count).

## Extrapolation to the frozen study (51,713 windows, ~930,834 forward calls)

| limit | frozen ceiling | point estimate | conservative bound | verdict |
|---|---:|---:|---:|---|
| cumulative CPU | 14,400 s | ≈ 5.6k s (39%) | ≈ 12k s (83%) | within, margin unproven on real bytes |
| cumulative wall | 21,600 s | ≈ 5.8k s (27%) | ≈ 12.4k s (57%) | within |
| combined RSS | 2 GiB | ≈ 0.44 GiB | same | within |
| transient disk | 2 GiB | < 1 MB | same | within |

The point estimate is a linear scaling of the 4,000-window run. The conservative bound exists
because the fixture has ~2.1 source frames per window while a real match at 10 Hz has roughly
4–5; source decoding costs ≈ 0.029 CPU s/window here (≈ 26% of the total, measured separately),
so the bound doubles *all* per-window cost. Real tracking-file density and player counts were
not measured, and cannot be before the separate owner GO.

## Assessment

Feasible within the frozen limits on all measured evidence. **Not demonstrated on real bytes.**
The remaining uncertainty is real-source decode cost; the worst case considered still fits
CPU with ~17% margin. Resource exhaustion is a permanent terminal failure of the one-shot scope,
so the first real run carries that risk by design. No budget, model, device or compute purchase
was changed. No resource blocker is raised.
