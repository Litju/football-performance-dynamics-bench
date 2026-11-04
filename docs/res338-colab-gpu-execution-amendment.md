# RES338 prospective GPU execution amendment

**Status:** frozen prospectively before the first GPU fit on 2026-11-04.
**Owner authorization:** the owner-directed Colab execution request.
**Scientific plan:** the original v2 JSON plan and protocol remain unchanged.

This amendment changes the execution hardware for the research-only final fits.
It does not change population membership, targets, model, features, sampling,
optimizer, validation, checkpoint selection, retry rules, or protected status. It
does not claim bitwise equivalence between CPU and GPU results.

## Frozen campaign

- Model: `per_target_context_deepsets_mlp_v1`.
- Exactly six information-regime/target-representation configurations, crossed
  with seeds 1729, 2718, and 31415: exactly 18 final-role fits.
- Train only on the frozen twelve training matches. Validate only on the frozen
  four validation matches. Do not stage or read evaluation-role files or labels.
- Keep the frozen feature dimensions, information boundaries, masks, target
  representations, sampling distribution, AdamW values, batch size 128, masked
  physical ADE, 100-step validation cadence, patience 10, maximum 5,000 steps,
  equal-weight validation-match selection, and earliest-step tie rule.
- Keep one active training worker. Failed scientific fits remain terminal. Apply
  only the frozen infrastructure retry allowance.

## Runtime and deterministic execution

- Request an A100 first. Use another authorized NVIDIA GPU only after the GPU
  identity, available VRAM, driver, CUDA, and the qualification below are verified.
  CPU fallback is forbidden.
- Pin Python 3.12.8, NumPy 2.2.4, and PyTorch 2.6.0+cu124 with CUDA 12.4. Record
  the actual driver, runtime build, device model and memory, available system RAM,
  local disk, Colab session ID, and CLI version before a fit.
- Use FP32 only and set PyTorch float32 matmul precision to highest. Disable
  TF32 and mixed precision. Set
  `CUBLAS_WORKSPACE_CONFIG=:4096:8`, deterministic PyTorch algorithms, deterministic
  cuDNN, no cuDNN benchmarking, one Torch intra-op and inter-op CPU thread, and
  one CPU core for the worker. Seed Python, NumPy, and PyTorch from the frozen
  per-fit seed.
- Synthetic CPU/GPU qualification must pass before any real fit. For every
  information regime, compare fixed synthetic predictions and masked ADE at
  `rtol=1e-4, atol=1e-5`; compare gradients and one AdamW update at
  `rtol=1e-3, atol=1e-5`. Two 100-step replays on the same GPU runtime and seed
  must produce byte-identical model state and prediction arrays.
- Maximum GPU allocated memory per worker is 8 GiB. Record the peak for each fit.
- Colab local disk must retain at least an 8 GiB reserve after staging source,
  generating the paired producer/verifier outputs, and building all sixteen caches.

## Resource and failure limits

Preserve the original 3,600 CPU-second per-fit limit, 900-second retry CPU limit,
16 GiB worker-RSS limit, 19.5-hour preparation CPU limit, 292.5-hour campaign CPU
limit, and 336-hour campaign wall limit. Add a GPU-time ceiling of 3,600 seconds
per fit and 900 seconds for an allowed infrastructure retry, for a maximum total
of 22.5 GPU-hours across eighteen fits and their original retry allowance. These
are stop limits; they do not authorize extra seeds or extensions.

The CLI reported 256.78 existing compute units before allocation on 2026-11-04.
That balance is the hard campaign spend cap. Spend only those currently available
units; do not purchase, top up, or authorize additional charges. Recheck usage
before allocating and during the campaign. Stop before a fit if the remaining
balance cannot cover its frozen resource budget.

## Evidence

Bind every fit to the SHA-256 of this amendment, the original v2 plan and protocol,
the research-admission identity, the training/validation-only source and feature
manifests, the exact code commit, and the observed runtime manifest. Commit each
checkpoint and receipt to private Drive, then read back and verify their content
hashes before counting a fit as complete. The private cloud handling scope is
defined separately in `res338-private-cloud-research-amendment.md`.
