# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""Production-path scorer: source windows -> frozen features -> frozen models -> metrics.

Source-agnostic. The RES643 synthetic generator and the RES645 source-stream adapter both feed
``score_stream``; the metric, aggregation, stratum and sealing contracts are RES643's, unchanged.
"""

from __future__ import annotations

import hashlib
import platform
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Any

import numpy as np
import torch

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.evaluation_population import (
    truth_mask_sha256,
)

from . import learned_deepsets as lds
from . import res635_post_failure_evaluation as s
from .information import validate_information_boundary
from .res645_checkpoints import Binding, FrozenModelSet

type Document = dict[str, Any]

CODE_FILES = (
    "res645_pipeline.py",
    "res645_independent.py",
    "res645_evidence.py",
    "res635_execution.py",
    "res645_source_stream.py",
    "res645_checkpoints.py",
    "res645_paths.py",
    "res645_fixtures.py",
    "res645_workloads.py",
    "learned_deepsets.py",
    "information.py",
    "res635_post_failure_evaluation.py",
    "res635_verification.py",
)


def provenance(bindings: Iterable[Binding], manifest_sha256: str) -> Document:
    root = Path(__file__).parent
    protocol = root / "res635_post_failure_descriptive_protocol_v1.json"
    if hashlib.sha256(protocol.read_bytes()).hexdigest() != s.PROTOCOL_SHA256:
        raise ValueError("frozen protocol changed")
    return {
        "protocol_sha256": s.PROTOCOL_SHA256,
        "runtime": {**s.runtime(), "python": platform.python_version()},
        "code_sha256": {n: hashlib.sha256((root / n).read_bytes()).hexdigest() for n in CODE_FILES},
        "synthetic_only": True,
        "weights": "artificial CPU checkpoints from a synthetic manifest",
        "checkpoint_manifest_sha256": manifest_sha256,
        "checkpoint_bindings": [b.document() for b in bindings],
    }


class SourceIdentity:
    """Ordered, bounded-state identity and denominator accounting for one streamed match."""

    def __init__(self, label: str, match_id: str) -> None:
        if label not in s.MATCHES:
            raise ValueError("unexpected match label")
        self.label, self.match_id = label, match_id
        self.count = self.scoreable_windows = self.scenes = self.points = self.finals = 0
        self.previous: tuple[int, int] | None = None
        self.ids, self.masks, self.truth, self.inputs = (hashlib.sha256() for _ in range(4))
        self.quality = {"detected_only": 0, "with_provider_extrapolation": 0, "unclassified": 0}
        self.missingness = {
            "observed_detected": 0,
            "provider_extrapolated": 0,
            "flag_missing": 0,
            "missing_xy": 0,
        }

    def observe(self, w: Document) -> None:
        if (w["match"], w["match_id"], w["index"]) != (self.label, self.match_id, self.count):
            raise ValueError("wrong match, missing window or duplicate window")
        origin = (w["period"], w["source_frame"])
        if self.previous is not None and origin <= self.previous:
            raise ValueError("duplicate or out-of-order source window")
        self.previous = origin
        support = w["support"]
        if len(support) != 41 or [c["scene_id"] for c in w["scenes"]] != ["home", "away"]:
            raise ValueError("support or directed scene order differs")
        for k, sample in enumerate(support):
            validate_information_boundary(sample.keys())
            for player in sample["players"]:
                validate_information_boundary(player.keys())
            if (sample["period"], sample["source_frame"]) != (origin[0], origin[1] + 2 * (k - 25)):
                raise ValueError("source frame order differs")
        home, away = set(w["home_player_ids"]), set(w["away_player_ids"])
        if not home or not away or home & away:
            raise ValueError("home and away rosters must be disjoint and nonempty")
        origin_players = {p["player_id"]: p for p in support[25]["players"]}
        scoreable = 0
        for scene in w["scenes"]:
            absolute, _, mask = lds.validate_truth_scene(scene)
            ids = scene["player_ids"]
            team = home if scene["scene_id"] == "home" else away
            if not set(ids) <= team:
                raise ValueError("scene players are outside their directed team")
            # Truth, origin and mask must be exactly reproducible from the support itself.
            for p, pid in enumerate(ids):
                row = origin_players.get(pid)
                if row is None or row["x_m"] is None or row["y_m"] is None:
                    raise ValueError("scene player is not observed at the forecast origin")
                if [row["x_m"], row["y_m"]] != list(scene["origin_xy"][p]):
                    raise ValueError("scene origin differs from the source origin")
                for t in range(lds.FUTURE_SAMPLES):
                    cell = {q["player_id"]: q for q in support[26 + t]["players"]}.get(pid)
                    observed = (
                        cell is not None and cell["x_m"] is not None and cell["y_m"] is not None
                    )
                    if observed != bool(mask[p, t]) or (
                        cell is not None
                        and observed
                        and [cell["x_m"], cell["y_m"]] != absolute[p, t].tolist()
                    ):
                        raise ValueError("scene truth or mask differs from the source support")
            if scene["truth_mask_sha256"] != truth_mask_sha256(
                tuple(
                    tuple(None if v is None else tuple(v) for v in step)
                    for step in scene["absolute_xy"]
                )
            ):
                raise ValueError("mask identity mismatch")
            if bool(mask[:, -1].any()) != scene["scoreable"]:
                raise ValueError("scoreable flag differs from final-target validity")
            self.masks.update(s.canonical(scene["truth_mask"]) + b"\n")
            self.truth.update(s.canonical(scene["absolute_xy"]) + b"\n")
            if scene["scoreable"]:
                scoreable += 1
                self.points += int(mask.sum())
                self.finals += int(mask[:, -1].sum())
                self.quality[scene["quality"]] += 1
                for key, value in scene["missingness"].items():
                    self.missingness[key] += value
        self.ids.update(w["window_id"].encode() + b"\n")
        self.inputs.update(
            s.canonical({"support": support, "eligibility": w["eligibility"]}) + b"\n"
        )
        self.scenes += scoreable
        self.scoreable_windows += bool(scoreable)
        self.count += 1

    def result(self) -> Document:
        return {
            "windows": self.count,
            "scoreable_windows": self.scoreable_windows,
            "scoreable_scenes": self.scenes,
            "scored_points": self.points,
            "final_targets": self.finals,
            "scalar_coordinates": 2 * self.points,
            "window_ids_sha256": self.ids.hexdigest(),
            "mask_sha256": self.masks.hexdigest(),
            "truth_sha256": self.truth.hexdigest(),
            "input_sha256": self.inputs.hexdigest(),
            "scoreable_scene_quality": self.quality,
            "future_target_missingness": self.missingness,
        }


def predictions(
    w: Document, frozen: FrozenModelSet
) -> Iterator[tuple[int, Document, np.ndarray[Any, Any]]]:
    """One window, two scenes, one forward per cell; physical absolute-XY reconstruction."""
    scenes = [c for c in w["scenes"]]
    with torch.inference_mode():
        for regime in lds.INFORMATION_REGIMES:
            payloads = [
                lds.build_scene_feature_payload(
                    w["support"],
                    target_side=c["scene_id"],
                    target_player_ids=c["player_ids"],
                    home_player_ids=w["home_player_ids"],
                    away_player_ids=w["away_player_ids"],
                    regime=regime,
                )
                for c in scenes
            ]
            inputs = lds.collate_feature_payloads(payloads, regime)
            for representation in lds.TARGET_REPRESENTATIONS:
                for seed in lds.SEEDS:
                    cell = (regime, representation, seed)
                    output = frozen.models[cell](inputs).numpy().astype(np.float64)
                    for i, scene in enumerate(scenes):
                        prediction = output[i]
                        if representation == "origin_relative_displacement":
                            prediction = (
                                prediction + np.asarray(scene["origin_xy"], np.float64)[:, None, :]
                            )
                        yield s.CELLS.index(cell), scene, prediction


def score_stream(
    label: str,
    match_id: str,
    windows: Iterable[Document],
    frozen: FrozenModelSet,
    expected_windows: int,
    check: Callable[[], None] = lambda: None,
) -> Document:
    identity = SourceIdentity(label, match_id)
    totals = np.zeros((18, len(s.STRATA), 3), dtype=np.float64)
    denominators = np.zeros((18, len(s.STRATA)), dtype=np.int64)
    for w in windows:
        check()
        identity.observe(w)
        sums, scenes = np.zeros_like(totals), np.zeros_like(denominators)
        for cell, scene, prediction in predictions(w, frozen):
            for j, stratum in enumerate(s.STRATA):
                measured = s.scene_metrics(prediction, scene, stratum)
                if measured is not None:
                    sums[cell, j] += [measured[m] for m in s.METRICS]
                    scenes[cell, j] += 1
        present = scenes > 0
        totals[present] += sums[present] / scenes[present, None]
        denominators += present
    frozen.assert_unchanged()
    if identity.count != expected_windows or not denominators[:, 0].all():
        raise ValueError("incomplete or unscoreable match")
    records = []
    for i, cell in enumerate(s.CELLS):
        strata = {
            name: {
                "windows": int(denominators[i, j]),
                "metrics": {
                    m: float(totals[i, j, k] / denominators[i, j]) for k, m in enumerate(s.METRICS)
                }
                if denominators[i, j]
                else None,
            }
            for j, name in enumerate(s.STRATA)
        }
        records.append({"cell": list(cell), "strata": strata})
    return {
        "match": label,
        "identity": identity.result(),
        "records": records,
        "provenance": provenance(frozen.bindings, frozen.manifest_sha256),
    }
