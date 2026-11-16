# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""RES643 synthetic-only preparation for the unratified RES635 protocol.

No file-based inputs, authorizations, checkpoints, or real match identifiers are accepted.
"""

from __future__ import annotations

import hashlib
import json
import platform
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Any

import numpy as np
import torch

from . import learned_deepsets as lds

PROTOCOL_SHA256 = "ac931391ecb0afcb68974e1765f65fbff17071ade2bcaab93bdadd22f84a0305"
MATCHES = tuple(f"synthetic-match-{i}" for i in range(4))
CELLS: tuple[tuple[lds.InformationRegime, lds.TargetRepresentation, int], ...] = tuple(
    (regime, representation, seed)
    for regime in lds.INFORMATION_REGIMES
    for representation in lds.TARGET_REPRESENTATIONS
    for seed in lds.SEEDS
)
METRICS = ("ade_m", "fde_m", "xy_rmse_m")
STRATA = (
    "all",
    "early",
    "middle",
    "late",
    "detected_only",
    "with_provider_extrapolation",
    "unclassified",
)
type Document = dict[str, Any]
type Models = dict[
    tuple[lds.InformationRegime, lds.TargetRepresentation, int], lds.PerTargetContextDeepSetsMLP
]


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def runtime() -> Document:
    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "torch": str(torch.__version__),
        "device": "cpu",
        "threads": 1,
        "precision": "float32",
    }


def provenance() -> Document:
    root = Path(__file__).parent
    files = (
        Path(__file__),
        root / "learned_deepsets.py",
        root / "information.py",
        root / "res635_execution.py",
        root / "res635_verification.py",
        root.parents[1] / "evaluation" / "metrics" / "trajectory.py",
    )
    protocol = root / "res635_post_failure_descriptive_protocol_v1.json"
    if hashlib.sha256(protocol.read_bytes()).hexdigest() != PROTOCOL_SHA256:
        raise ValueError("frozen protocol changed")
    return {
        "protocol_sha256": PROTOCOL_SHA256,
        "runtime": runtime(),
        "code_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        "synthetic_only": True,
        "weights": "random initialization; no optimizer or checkpoint",
    }


def models() -> Models:
    lds.configure_deterministic_cpu()
    result: Models = {}
    for regime, representation, seed in CELLS:
        torch.manual_seed(seed)
        result[regime, representation, seed] = lds.PerTargetContextDeepSetsMLP(regime).eval()
    return result


def window(match: str, index: int) -> Document:
    """Invent source XY first; derive truth, masks and origins from that same source."""
    if match not in MATCHES or type(index) is not int or index < 0:
        raise ValueError("only artificial ordered match windows are accepted")
    rng = np.random.default_rng(np.random.SeedSequence([643, MATCHES.index(match), index]))
    positions = rng.uniform(-20, 20, (1, 22, 2)) + np.cumsum(
        rng.normal(0, 0.2, (41, 22, 2)), axis=0
    )
    present = rng.random((41, 22)) > 0.08
    present[25] = True
    # Include one-scene and completely unscoreable windows without changing the truth rule.
    if index % 3 == 1:
        present[-1, 11:] = False
    if index % 7 == 6:
        present[-1] = False
    support = [
        {
            "period": 1,
            "source_frame": 2 * (index * 41 + t),
            "players": [
                {
                    "player_id": p + 1,
                    "x_m": float(positions[t, p, 0]),
                    "y_m": float(positions[t, p, 1]),
                }
                for p in range(22)
                if present[t, p]
            ],
            "ball": {"x_m": float(t / 5), "y_m": float(index % 11)},
        }
        for t in range(41)
    ]
    scenes: list[Document] = []
    for side, start in (("home", 0), ("away", 11)):
        absolute = [
            [positions[t, p].tolist() if present[t, p] else None for p in range(start, start + 11)]
            for t in range(26, 41)
        ]
        displacement = [
            [
                (positions[t, p] - positions[25, p]).tolist() if present[t, p] else None
                for p in range(start, start + 11)
            ]
            for t in range(26, 41)
        ]
        scenes.append(
            {
                "scene_id": side,
                "player_ids": list(range(start + 1, start + 12)),
                "origin_xy": positions[25, start : start + 11].tolist(),
                "absolute_xy": absolute,
                "origin_relative_displacement": displacement,
                "truth_mask": present[26:, start : start + 11].tolist(),
                "scoreable": bool(present[-1, start : start + 11].any()),
                "quality": ("detected_only", "with_provider_extrapolation", "unclassified")[
                    index % 3
                ],
            }
        )
    return {
        "match": match,
        "index": index,
        "window_id": f"{match}:{index:08d}",
        "support": support,
        "scenes": scenes,
    }


def windows(match: str, count: int) -> Iterator[Document]:
    for index in range(count):
        yield window(match, index)


class StreamIdentity:
    """Contiguous canonical order detects duplicates without an unbounded seen-ID set."""

    def __init__(self, match: str) -> None:
        if match not in MATCHES:
            raise ValueError("non-synthetic match")
        self.match = match
        self.count = self.points = self.finals = self.scenes = self.scoreable_windows = 0
        self.source = hashlib.sha256()
        self.masks = hashlib.sha256()

    def observe(self, row: Document) -> None:
        if (row["match"], row["index"], row["window_id"]) != (
            self.match,
            self.count,
            f"{self.match}:{self.count:08d}",
        ):
            raise ValueError("duplicate or out-of-order source window")
        if len(row["support"]) != 41 or [s["scene_id"] for s in row["scenes"]] != ["home", "away"]:
            raise ValueError("support or directed scene order differs")
        for t, sample in enumerate(row["support"]):
            if (sample["period"], sample["source_frame"]) != (1, 2 * (self.count * 41 + t)):
                raise ValueError("source frame order differs")
        expected = window(self.match, self.count)
        # Synthetic trust boundary: reject invented caller modifications, including forged masks.
        if row != expected:
            raise ValueError("synthetic source, mask, or origin identity mismatch")
        scoreable = 0
        for scene in row["scenes"]:
            _, _, mask = lds.validate_truth_scene(scene)
            self.masks.update(canonical(scene["truth_mask"]) + b"\n")
            if scene["scoreable"]:
                scoreable += 1
                self.points += int(mask.sum())
                self.finals += int(mask[:, -1].sum())
        self.scenes += scoreable
        self.scoreable_windows += bool(scoreable)
        self.source.update(canonical(row) + b"\n")
        self.count += 1

    def result(self) -> Document:
        return {
            "windows": self.count,
            "scoreable_windows": self.scoreable_windows,
            "scoreable_scenes": self.scenes,
            "scored_points": self.points,
            "final_targets": self.finals,
            "scalar_coordinates": 2 * self.points,
            "input_sha256": self.source.hexdigest(),
            "mask_sha256": self.masks.hexdigest(),
        }


def predictions(row: Document, random_models: Models) -> Iterator[tuple[int, Document, Any]]:
    """One window, two scenes, one model forward per cell; no retained prediction rows."""
    scenes = row["scenes"]
    with torch.inference_mode():
        for regime in lds.INFORMATION_REGIMES:
            payloads = [
                lds.build_scene_feature_payload(
                    row["support"],
                    target_side=s["scene_id"],
                    target_player_ids=s["player_ids"],
                    home_player_ids=range(1, 12),
                    away_player_ids=range(12, 23),
                    regime=regime,
                )
                for s in scenes
            ]
            inputs = lds.collate_feature_payloads(payloads, regime)
            for representation in lds.TARGET_REPRESENTATIONS:
                for seed in lds.SEEDS:
                    cell = (regime, representation, seed)
                    output = random_models[cell](inputs).numpy()
                    for i, scene in enumerate(scenes):
                        prediction = output[i].astype(np.float64)
                        if representation == "origin_relative_displacement":
                            prediction += np.asarray(scene["origin_xy"], dtype=np.float64)[
                                :, None, :
                            ]
                        yield CELLS.index(cell), scene, prediction


def scene_metrics(prediction: Any, scene: Document, stratum: str) -> dict[str, float] | None:
    truth, _, mask = lds.validate_truth_scene(scene)
    return validated_scene_metrics(prediction, scene, stratum, truth, mask)


def validated_scene_metrics(
    prediction: Any, scene: Document, stratum: str, truth: Any, mask: Any
) -> dict[str, float] | None:
    if not scene["scoreable"] or (stratum in STRATA[4:] and scene["quality"] != stratum):
        return None
    if stratum in ("early", "middle", "late"):
        start = {"early": 0, "middle": 5, "late": 10}[stratum]
        prediction, truth, mask = (p[:, start : start + 5] for p in (prediction, truth, mask))
    if not mask.any() or not mask[:, -1].any():
        return None
    if not np.isfinite(prediction).all():
        raise ValueError("non-finite prediction")
    delta = prediction - truth
    distances = np.hypot(delta[..., 0], delta[..., 1])
    return {
        "ade_m": float(distances[mask].mean()),
        "fde_m": float(distances[:, -1][mask[:, -1]].mean()),
        "xy_rmse_m": float(np.sqrt(np.square(delta[mask]).sum() / (2 * mask.sum()))),
    }


def score_match(
    match: str,
    count: int,
    random_models: Models,
    check: Callable[[], None] = lambda: None,
    source: Iterable[Document] | None = None,
) -> Document:
    if type(count) is not int or not 1 <= count <= 64:
        raise ValueError("inference preparation is limited to 1..64 windows per artificial match")
    identity = StreamIdentity(match)
    totals = np.zeros((18, len(STRATA), 3), dtype=np.float64)
    denominators = np.zeros((18, len(STRATA)), dtype=np.int64)
    for row in windows(match, count) if source is None else source:
        check()
        identity.observe(row)
        sums = np.zeros_like(totals)
        scenes = np.zeros_like(denominators)
        for cell, scene, prediction in predictions(row, random_models):
            for j, stratum in enumerate(STRATA):
                measured = scene_metrics(prediction, scene, stratum)
                if measured is not None:
                    sums[cell, j] += [measured[m] for m in METRICS]
                    scenes[cell, j] += 1
        present = scenes > 0
        totals[present] += sums[present] / scenes[present, None]
        denominators += present
    if identity.count != count or not denominators[:, 0].all():
        raise ValueError("incomplete or unscoreable match")
    records = []
    for i, cell in enumerate(CELLS):
        strata = {
            s: {
                "windows": int(denominators[i, j]),
                "metrics": {
                    m: float(totals[i, j, k] / denominators[i, j]) for k, m in enumerate(METRICS)
                }
                if denominators[i, j]
                else None,
            }
            for j, s in enumerate(STRATA)
        }
        records.append({"cell": list(cell), "strata": strata})
    return {
        "match": match,
        "identity": identity.result(),
        "records": records,
        "provenance": provenance(),
    }
