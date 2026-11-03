# Research-only final fits

This report covers only the frozen `per_target_context_deepsets_mlp_v1` cell from
the v2 plan. Its six regime/representation configurations are crossed with seeds
1729, 2718, and 31415 for 18 final-role fits. Training samples only the 12 frozen
training matches. The four frozen validation matches select checkpoints by the
equal mean of their physical XY ADE values.

The model uses shared history-player and future-opponent DeepSets encoders and
the frozen 128-128-30 per-target prediction head. Input construction uses finite
XY in metres, zero-filled missing coordinates with presence masks, and the
26-point history grid. `history_only` receives no future channels;
`future_ball` adds only the 15 permitted future ball samples;
`future_opponent_plus_ball` adds only permitted opposing-player tracks, including
substitutes. Future target positions, target masks, and target availability stay
labels for training and validation. Player IDs only group and order tracks.

The private execution checks the exact research-admission manifest, independently
rehashes the two 20-match reconciliation outputs and pinned source files, then
builds private feature caches for training and validation only. The research
admission remains a distinct local-processing contract. It does not qualify or
open the protected population gate, which remains In Progress / NOT_QUALIFIED.

The fit worker is pinned to Python 3.12.8, PyTorch 2.6.0+cpu, NumPy 2.2.4,
deterministic CPU algorithms, one thread, and one CPU core. The repository keeps
no tracking rows, feature caches, run receipts, or checkpoints. Checkpoints and
row-level evidence stay in private storage.

The pinned training packages are in the `research-training` dependency group;
they do not become default requirements of the published package. The isolated
worker environment is created with `uv sync --group research-training`.

## Results

Campaign status: pending. No real fits, evaluation-role scoring, learned LOMO, or
held-out evaluation claims are included in this report. Results will be added
here as validation-set-only aggregates after the frozen campaign completes.
The previously supplied descriptive evaluation references are not training
targets or checkpoint-selection criteria.
