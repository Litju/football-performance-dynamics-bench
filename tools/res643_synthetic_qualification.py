"""Bounded synthetic census accounting; never opens input data or runs model inference.

The lightweight source identity covers synthetic window IDs, source-frame ranges and masks,
not the scorer's full invented-XY stream identity. Both are independently repeatable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import resource
import sys
import time
import tracemalloc
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (  # noqa: E402
    res635_post_failure_evaluation as s,
)


def census(total: int) -> dict[str, object]:
    if not 1 <= total <= 51_713:
        raise ValueError("synthetic census budget is 1..51713 windows")
    started, cpu = time.monotonic(), time.process_time()
    tracemalloc.start()
    identity, masks = hashlib.sha256(), hashlib.sha256()
    scenes = points = finals = scoreable_windows = 0
    for match in range(4):
        count = total // 4 + (match < total % 4)
        for index in range(count):
            rng = np.random.default_rng(np.random.SeedSequence([643, match, index]))
            rng.uniform(-20, 20, (1, 22, 2))
            rng.normal(0, 0.2, (41, 22, 2))
            present = rng.random((41, 22)) > 0.08
            if index % 3 == 1:
                present[-1, 11:] = False
            if index % 7 == 6:
                present[-1] = False
            mask = present[26:]
            window_scenes = 0
            for start in (0, 11):
                panel = mask[:, start : start + 11]
                if panel[-1].any():
                    window_scenes += 1
                    points += int(panel.sum())
                    finals += int(panel[-1].sum())
            scenes += window_scenes
            scoreable_windows += bool(window_scenes)
            identity.update(
                s.canonical([s.MATCHES[match], index, index * 82, index * 82 + 80]) + b"\n"
            )
            masks.update(np.packbits(mask).tobytes())
            if time.process_time() - cpu > 120:
                raise RuntimeError("census CPU budget exceeded")
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "windows": total,
        "directed_scene_slots": 2 * total,
        "scoreable_windows": scoreable_windows,
        "scoreable_scenes": scenes,
        "scored_points": points,
        "final_targets": finals,
        "scalar_coordinates": 2 * points,
        "identity_sha256": identity.hexdigest(),
        "mask_sha256": masks.hexdigest(),
        "traced_peak_bytes": peak,
        "rss_peak_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
        "cpu_s": time.process_time() - cpu,
        "wall_s": time.monotonic() - started,
        "snapshot_bytes": 0,
        "forward_calls": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--windows", type=int, default=51_713)
    args = parser.parse_args()
    print(json.dumps(census(args.windows), sort_keys=True))


if __name__ == "__main__":
    main()
