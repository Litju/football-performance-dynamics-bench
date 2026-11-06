"""Research-only one-pass held-out scorer; requires a separate exact owner GO."""

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    amended_heldout_evaluation as scorer,
)

if __name__ == "__main__":
    raise SystemExit(scorer.main())
