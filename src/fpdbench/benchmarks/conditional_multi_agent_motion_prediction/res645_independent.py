# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""Genuinely separate verification calculation for source-fed match receipts.

Shares public identities and the frozen network class; metrics use separate NumPy arithmetic.
It does NOT use the source adapter, the production producer, the canonicalizer, the feature
builder, the checkpoint loader, the scorer's accumulators or its truth panels. Windows come
directly from raw 10 Hz JSONL frames; eligibility is re-derived before checking the lock.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
from collections import deque
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .res646_authorization import Campaign

import numpy as np
import torch

from . import learned_deepsets as lds
from . import res635_post_failure_evaluation as s
from . import res645_checkpoints as checkpoints_contract
from . import res645_paths as paths
from . import res645_source_stream as source
from .evaluation_population import prospective_window_id_v2

type Document = dict[str, Any]
MAX = 8 * 1024**3


class PredictionAudit:
    """Recalculate match metrics as predictions pass, without calling any model."""

    def __init__(self) -> None:
        self.sums = [[[0.0] * 3 for _ in s.STRATA] for _ in s.CELLS]
        self.counts = [[0] * len(s.STRATA) for _ in s.CELLS]
        self.values: dict[tuple[int, int], list[list[float]]] = {}
        self.truth: dict[str, tuple[Any, Any]] = {}

    def begin(self, scenes: list[Document]) -> None:
        self.values = {}
        self.truth = {}
        for scene in scenes:
            panel = scene["absolute_xy"]
            mask = np.asarray([[point is not None for point in row] for row in panel]).T
            truth = np.asarray(
                [[point if point is not None else [0.0, 0.0] for point in row] for row in panel],
                dtype=np.float64,
            ).transpose(1, 0, 2)
            if mask.tolist() != np.asarray(scene["truth_mask"]).T.tolist():
                raise ValueError("independent truth mask differs")
            self.truth[scene["scene_id"]] = truth, mask

    def observe(self, cell: int, scene: Document, prediction: Any) -> None:
        if not scene["scoreable"]:
            return
        truth, full_mask = self.truth[scene["scene_id"]]
        for j, stratum in enumerate(s.STRATA):
            if j >= 4 and scene["quality"] != stratum:
                continue
            start, end = {"early": (0, 5), "middle": (5, 10), "late": (10, 15)}.get(
                stratum, (0, 15)
            )
            mask = full_mask[:, start:end]
            if not mask[:, -1].any():
                continue
            squared = np.square(prediction[:, start:end] - truth[:, start:end]).sum(axis=-1)
            distances = np.sqrt(squared)
            self.values.setdefault((cell, j), []).append(
                [
                    float(distances[mask].mean()),
                    float(distances[:, -1][mask[:, -1]].mean()),
                    float(np.sqrt(squared[mask].sum() / (2 * mask.sum()))),
                ]
            )

    def end(self) -> None:
        for (cell, j), rows in self.values.items():
            for k in range(3):
                self.sums[cell][j][k] += sum(row[k] for row in rows) / len(rows)
            self.counts[cell][j] += 1

    def records(self) -> list[Document]:
        return [
            {
                "cell": list(cell),
                "strata": {
                    name: {
                        "windows": self.counts[i][j],
                        "metrics": {
                            metric: self.sums[i][j][k] / self.counts[i][j]
                            for k, metric in enumerate(s.METRICS)
                        }
                        if self.counts[i][j]
                        else None,
                    }
                    for j, name in enumerate(s.STRATA)
                },
            }
            for i, cell in enumerate(s.CELLS)
        ]


class SourcePredictionAudit(PredictionAudit):
    """Independent raw eligibility/truth readback, sharing the one prediction pass only."""

    def __init__(
        self,
        directory: Path,
        label: str,
        locked_path: Path | None,
        campaign: Campaign | None = None,
    ) -> None:
        super().__init__()
        self.windows = raw_windows(
            directory,
            label,
            locked_path,
            campaign,
            mode="frozen" if campaign is not None else "synthetic",
        )
        self.ids, self.masks, self.truths = (hashlib.sha256() for _ in range(3))
        self.count = self.scoreable = self.scenes = self.points = self.finals = 0
        self.missingness = dict.fromkeys(
            (
                "observed_detected",
                "provider_extrapolated",
                "flag_missing",
                "missing_xy",
            ),
            0,
        )
        self.quality = dict.fromkeys(
            ("detected_only", "with_provider_extrapolation", "unclassified"), 0
        )

    def begin_source(self, window: Document) -> None:
        raw = next(self.windows, None)
        if raw is None or (raw["index"], raw["window_id"]) != (
            window["index"],
            window["window_id"],
        ):
            raise ValueError("independent source window inventory differs")
        self.current = raw
        self.ids.update(raw["window_id"].encode() + b"\n")
        scenes = []
        scoreable = False
        for actual, expected in zip(window["scenes"], raw["scenes"], strict=True):
            panel = [
                [
                    None if np.isnan(p[0]) else [float(p[0]), float(p[1])]
                    for p in expected["absolute"][:, t]
                ]
                for t in range(15)
            ]
            mask = expected["mask"].T.tolist()
            if any(
                actual[k] != value
                for k, value in {
                    "scene_id": expected["scene_id"],
                    "player_ids": expected["player_ids"],
                    "origin_xy": expected["origin"].tolist(),
                    "absolute_xy": panel,
                    "truth_mask": mask,
                    "scoreable": expected["scoreable"],
                    "quality": expected["quality"],
                }.items()
            ):
                raise ValueError("independent source truth, origin, mask or quality differs")
            scenes.append({**actual, "absolute_xy": panel, "truth_mask": mask})
            self.masks.update(_digest(mask) + b"\n")
            self.truths.update(_digest(panel) + b"\n")
            if expected["scoreable"]:
                scoreable = True
                self.scenes += 1
                self.points += int(expected["mask"].sum())
                self.finals += int(expected["mask"][:, -1].sum())
                self.quality[expected["quality"]] += 1
                for frame in raw["support"][26:]:
                    for pid in expected["player_ids"]:
                        point = _xy(frame, pid)
                        category = (
                            "missing_xy"
                            if point is None
                            else (
                                "observed_detected"
                                if point[2] is True
                                else "provider_extrapolated"
                                if point[2] is False
                                else "flag_missing"
                            )
                        )
                        self.missingness[category] += 1
        self.count += 1
        self.scoreable += scoreable
        self.begin(scenes)

    def result(self) -> Document:
        if next(self.windows, None) is not None:
            raise ValueError("independent source has missing scored windows")
        return {
            "windows": self.count,
            "scoreable_windows": self.scoreable,
            "scoreable_scenes": self.scenes,
            "scored_points": self.points,
            "final_targets": self.finals,
            "scalar_coordinates": 2 * self.points,
            "window_ids_sha256": self.ids.hexdigest(),
            "mask_sha256": self.masks.hexdigest(),
            "truth_sha256": self.truths.hexdigest(),
            "scoreable_scene_quality": self.quality,
            "future_target_missingness": self.missingness,
        }


def _digest(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def raw_eligible(support: list[Any], meta: Document, phases: list[Document]) -> bool:
    """Re-derive frozen-v2 membership on invented raw frames, without lock decisions.

    Extrapolation, identity transitions and partial XY are warnings, not exclusions.
    """
    if len(support) != 41 or any(f is None for f in support):
        return False
    period = support[25]["period"]
    bounds = [p for p in meta["match_periods"] if p["period"] == period]
    if len(bounds) != 1 or period not in (1, 2):
        return False
    start, end = bounds[0]["start_frame"], bounds[0]["end_frame"]
    first, last = support[0]["frame"], support[-1]["frame"]
    if not all(
        any(p["period"] == period and p["frame_start"] <= f < p["frame_end"] for p in phases)
        for f in range(first, last + 1)
    ):
        return False
    teams = (meta["home_team"]["id"], meta["away_team"]["id"])
    roster = {p["id"]: p for p in meta["players"]}
    ball_count = 0
    previous_time = None
    for i, frame in enumerate(support):
        f = frame["frame"]
        if frame["period"] != period or f != first + 2 * i or not start <= f < end:
            return False
        stamp = frame["timestamp"]
        if not isinstance(stamp, str):
            return False
        h, m, sec = stamp.split(":")
        clock = 36000 * int(h) + 600 * int(m) + float(sec) * 10
        if previous_time is not None and not math.isclose(clock - previous_time, 2):
            return False
        previous_time = clock
        counts = dict.fromkeys(teams, 0)
        seen = set()
        for player in frame["player_data"]:
            pid = player["player_id"]
            if (
                pid in seen
                or pid not in roster
                or (player["is_detected"] is not None and type(player["is_detected"]) is not bool)
            ):
                return False
            seen.add(pid)
            person = roster[pid]
            xy = (player["x"], player["y"])
            if any(
                v is not None and (type(v) not in (int, float) or not math.isfinite(v)) for v in xy
            ):
                return False
            if None in xy:
                continue
            if abs(xy[0]) > meta["pitch_length"] or abs(xy[1]) > meta["pitch_width"]:
                return False
            active = any(
                a["name"] == f"period_{period}" and a["start_frame"] <= f <= a["end_frame"]
                for a in person["playing_time"]["by_period"]
            )
            if active:
                counts[person["team_id"]] += 1
        if min(counts.values()) < 7:
            return False
        ball = frame["ball_data"]
        valid = False
        if ball is not None:
            xy = (ball["x"], ball["y"])
            if any(
                v is not None and (type(v) not in (int, float) or not math.isfinite(v)) for v in xy
            ):
                return False
            if ball["is_detected"] is not None and type(ball["is_detected"]) is not bool:
                return False
            valid = None not in xy
            if valid:
                if ball["is_detected"] is None:
                    raise ValueError("independent global ball qualification stop")
                if abs(xy[0]) > 2 * meta["pitch_length"] or abs(xy[1]) > 2 * meta["pitch_width"]:
                    return False
        if i == 25 and not valid:
            return False
        ball_count += valid
    return ball_count >= 39


def raw_windows(
    directory: Path,
    label: str,
    locked_path: Path | None = None,
    campaign: Campaign | None = None,
    *,
    mode: source.Mode = "synthetic",
) -> Iterator[Document]:
    """Stream eligible windows straight from raw frames; no canonicalizer, no producer."""
    if mode == "frozen":
        from .res646_authorization import require_campaign

        campaign = require_campaign(campaign)
        campaign.require_worker()
        specs = [
            spec
            for spec in campaign.specs
            if (spec.directory, spec.label, spec.locked_path) == (directory, label, locked_path)
        ]
        if len(specs) != 1:
            raise PermissionError("source is outside signed campaign")
        spec = specs[0]
    else:
        if campaign is not None or mode != "synthetic":
            raise PermissionError("explicit real source mode required")
        marker, _ = paths.read_regular_file(directory / "fixture.json", max_bytes=4096)
        spec = source.SourceMatchSpec(
            label, json.loads(marker)["match_id"], directory, locked_path=locked_path
        )
    source.authorize(spec, mode, campaign)
    meta_bytes, _ = paths.read_regular_file(
        directory / "metadata.json", max_bytes=16 << 20, campaign=campaign
    )
    meta = json.loads(meta_bytes)
    if str(meta["id"]) != spec.match_id:
        raise PermissionError("source match identity differs from authorized fixture or campaign")
    team_of = {p["id"]: p["team_id"] for p in meta["players"]}
    home_team = meta["home_team"]["id"]
    home_ids = sorted(i for i, t in team_of.items() if t == home_team)
    away_ids = sorted(i for i, t in team_of.items() if t != home_team)
    phase_bytes, _ = paths.read_regular_file(
        directory / "phases.json", max_bytes=16 << 20, campaign=campaign
    )
    phases = json.loads(phase_bytes)
    origins = (
        (p["period"], f)
        for p in sorted(meta["match_periods"], key=lambda q: q["period"])
        for f in range(p["start_frame"] + p["start_frame"] % 2, p["end_frame"], 2)
    )
    locked = os.fdopen(
        paths.open_regular_fd(locked_path or directory / "locked.jsonl", campaign=campaign), "rb"
    )
    tracking = os.fdopen(
        paths.open_regular_fd(directory / "tracking.jsonl", campaign=campaign), "rb"
    )
    ordinal = 0
    try:
        recent: deque[dict[str, Any]] = deque(maxlen=41)
        pending = iter(origins)
        current = next(pending, None)

        def emit(origin: tuple[int, int]) -> Document | None:
            nonlocal ordinal
            line = locked.readline(1024 * 1024 + 1)
            if len(line) > 1024 * 1024:
                raise ValueError("oversized independent lock row")
            row = json.loads(line)
            period, frame = origin
            if (row["period"], row["source_frame"], row["match_id"], row["role"]) != (
                period,
                frame,
                str(meta["id"]),
                "evaluation",
            ):
                raise ValueError("locked row differs from the raw origin grid")
            by_frame = {f["frame"]: f for f in recent if f["period"] == period}
            support = [by_frame.get(frame + 2 * k) for k in range(-25, 16)]
            eligible = raw_eligible(support, meta, phases)
            origin_id = f"period_{period}/sample_{frame // 2}"
            expected_id = prospective_window_id_v2(str(meta["id"]), origin_id) if eligible else None
            if row["window_id"] != expected_id:
                raise ValueError("independent raw eligibility differs from locked stream")
            if not eligible:
                return None
            window = _build(
                label, ordinal, row["window_id"], support, home_ids, away_ids, team_of, home_team
            )
            ordinal += 1
            return window

        for line in iter(lambda: tracking.readline(1024 * 1024 + 1), b""):
            if len(line) > 1024 * 1024:
                raise ValueError("oversized independent tracking row")
            frame = json.loads(line)
            if frame["frame"] % 2:
                continue
            if recent and frame["frame"] <= recent[-1]["frame"]:
                raise ValueError("independent duplicate or reordered raw frame")
            ball = frame["ball_data"]
            if (
                ball is not None
                and ball["is_detected"] is None
                and all(ball[k] is not None for k in ("x", "y"))
            ):
                raise ValueError("independent global ball qualification stop")
            recent.append(frame)
            while current is not None and current[1] + 30 <= frame["frame"]:
                window = emit(current)
                current = next(pending, None)
                if window is not None:
                    yield window
        while current is not None:
            window = emit(current)
            current = next(pending, None)
            if window is not None:
                yield window
        if locked.readline():
            raise ValueError("locked stream has rows beyond the raw origin grid")
    finally:
        locked.close()
        tracking.close()


def _xy(frame: dict[str, Any], pid: int) -> tuple[float, float, bool | None] | None:
    for p in frame["player_data"]:
        if p["player_id"] == pid and p["x"] is not None and p["y"] is not None:
            return float(p["x"]), float(p["y"]), p["is_detected"]
    return None


def _build(
    label: str,
    ordinal: int,
    window_id: str,
    support: list[Any],
    home_ids: list[int],
    away_ids: list[int],
    team_of: dict[int, int],
    home_team: int,
) -> Document:
    scenes = []
    for side, roster in (("home", home_ids), ("away", away_ids)):
        targets = [pid for pid in roster if _xy(support[25], pid) is not None]
        absolute = np.full((11, 15, 2), np.nan)
        flags: list[bool | None] = []
        for p, pid in enumerate(targets[:11]):
            for t in range(15):
                got = _xy(support[26 + t], pid)
                if got is not None:
                    absolute[p, t] = got[:2]
                    flags.append(got[2])
        origin = np.array([_xy(support[25], pid)[:2] for pid in targets[:11]])  # type: ignore[index]
        mask = ~np.isnan(absolute[..., 0])
        quality = (
            "with_provider_extrapolation"
            if any(f is False for f in flags)
            else "unclassified"
            if not flags or any(f is None for f in flags)
            else "detected_only"
        )
        scenes.append(
            {
                "scene_id": side,
                "player_ids": targets,
                "origin": origin,
                "absolute": absolute,
                "mask": mask,
                "scoreable": bool(mask[:, -1].any()),
                "quality": quality,
            }
        )
    return {
        "match": label,
        "index": ordinal,
        "window_id": window_id,
        "support": support,
        "home_ids": home_ids,
        "away_ids": away_ids,
        "scenes": scenes,
    }


def _track(frames: list[Any], pid: int) -> tuple[np.ndarray[Any, Any], bool]:
    out = np.zeros((len(frames), 3), np.float32)
    seen = False
    for i, frame in enumerate(frames):
        if any(p["player_id"] == pid for p in frame["player_data"]):
            seen = True
        got = _xy(frame, pid)
        if got is not None:
            out[i] = (got[0], got[1], 1.0)
    return out.reshape(-1), seen


def _ball(frames: list[Any]) -> np.ndarray[Any, Any]:
    out = np.zeros((len(frames), 3), np.float32)
    for i, frame in enumerate(frames):
        b = frame["ball_data"]
        if b is not None and b["x"] is not None and b["y"] is not None:
            out[i] = (b["x"], b["y"], 1.0)
    return out.reshape(-1)


def model_inputs(w: Document, regime: str) -> lds.ModelInputs:
    """Independent feature construction straight from raw frames, batched over both scenes."""
    history, future = w["support"][:26], w["support"][26:]
    pool = max(len(w["home_ids"]), len(w["away_ids"]))
    n = len(w["scenes"])
    target = np.zeros((n, 11, 78), np.float32)
    tracks = np.zeros((n, 2, pool, 78), np.float32)
    tmask = np.zeros((n, 2, pool), bool)
    for b, scene in enumerate(w["scenes"]):
        for p, pid in enumerate(scene["player_ids"][:11]):
            target[b, p] = _track(history, pid)[0]
        for team, ids in enumerate((w["home_ids"], w["away_ids"])):
            for p, pid in enumerate(ids):
                tracks[b, team, p], tmask[b, team, p] = _track(history, pid)
    side = np.array([1.0 if sc["scene_id"] == "home" else -1.0 for sc in w["scenes"]], np.float32)
    kwargs: dict[str, Any] = {}
    if regime != "history_only":
        kwargs["future_ball"] = torch.from_numpy(np.tile(_ball(future), (n, 1)))
    if regime == "future_opponent_plus_ball":
        opp = max(len(w["home_ids"]), len(w["away_ids"]))
        ft = np.zeros((n, opp, 45), np.float32)
        fm = np.zeros((n, opp), bool)
        for b, scene in enumerate(w["scenes"]):
            ids = w["away_ids"] if scene["scene_id"] == "home" else w["home_ids"]
            for p, pid in enumerate(ids):
                ft[b, p], fm[b, p] = _track(future, pid)
        kwargs["future_opponent_tracks"] = torch.from_numpy(ft)
        kwargs["future_opponent_mask"] = torch.from_numpy(fm)
    return lds.ModelInputs(
        target_history=torch.from_numpy(target),
        history_team_tracks=torch.from_numpy(tracks),
        history_team_mask=torch.from_numpy(tmask),
        history_ball=torch.from_numpy(np.tile(_ball(history), (n, 1))),
        target_side=torch.from_numpy(side),
        **kwargs,
    )


def load_models(
    manifest: Document,
    directory: Path,
    receipts: Path,
    *,
    mode: checkpoints_contract.Mode = "synthetic",
    campaign: Campaign | None = None,
) -> tuple[dict[tuple[str, str, int], lds.PerTargetContextDeepSetsMLP], list[Document]]:
    """Independent loader: reads the manifest-named bytes itself and checks the hash."""
    checkpoints_contract.validate_manifest(manifest, mode)
    if mode == "frozen":
        from .res646_authorization import require_campaign

        campaign = require_campaign(campaign)
        campaign.allow_models(manifest, directory, receipts)
    elif campaign is not None:
        raise PermissionError("explicit real checkpoint mode required")
    models: dict[tuple[str, str, int], lds.PerTargetContextDeepSetsMLP] = {}
    bindings: list[Document] = []
    for rec in manifest["checkpoints"]:
        fit, fit_id = paths.read_regular_file(
            receipts / f"{rec['receipt_sha256']}.json",
            max_bytes=1 << 20,
            require_private=True,
            campaign=campaign,
        )
        if (
            fit_id.sha256 != rec["receipt_sha256"]
            or json.loads(fit)["checkpoint_sha256"] != (rec["checkpoint_sha256"])
        ):
            raise ValueError("independent fit receipt mismatch")
        data, ident = paths.read_regular_file(
            directory / f"{rec['checkpoint_sha256']}.pt",
            max_bytes=1 << 26,
            require_private=True,
            campaign=campaign,
        )
        if ident.sha256 != rec["checkpoint_sha256"]:
            raise ValueError("independent checkpoint hash mismatch")
        payload = torch.load(io.BytesIO(data), map_location="cpu", weights_only=True)
        model = lds.PerTargetContextDeepSetsMLP(rec["information_regime"])
        model.load_state_dict(payload["state_dict"], strict=True)
        model.eval()
        key = (rec["information_regime"], rec["target_representation"], rec["seed"])
        models[key] = model
        h = hashlib.sha256()
        for name, tensor in sorted(model.state_dict().items()):
            h.update(name.encode() + b"\0" + str(tuple(tensor.shape)).encode() + b"\0")
            h.update(tensor.detach().numpy().tobytes())
        bindings.append(
            {
                "cell": list(key),
                "checkpoint_sha256": ident.sha256,
                "configuration_sha256": rec["configuration_sha256"],
                "selected_step": rec["selected_step"],
                "state_sha256": h.hexdigest(),
            }
        )
    ordered = [next(b for b in bindings if tuple(b["cell"]) == c) for c in s.CELLS]
    return models, ordered


def match_body(
    directory: Path,
    label: str,
    manifest: Document,
    checkpoints: Path,
    receipts: Path,
    *,
    mode: source.Mode = "synthetic",
    campaign: Campaign | None = None,
) -> Document:
    # Real verification audits captured predictions; it must never replay learned inference.
    if mode != "synthetic" or campaign is not None:
        raise PermissionError("match_body is invented-fixture verification only")
    models, bindings = load_models(manifest, checkpoints, receipts, mode=mode)
    sums = [[[0.0] * 3 for _ in s.STRATA] for _ in s.CELLS]
    counts = [[0] * len(s.STRATA) for _ in s.CELLS]
    ids, masks, truths = hashlib.sha256(), hashlib.sha256(), hashlib.sha256()
    windows = scoreable_windows = scenes_n = points = finals = 0
    quality = {"detected_only": 0, "with_provider_extrapolation": 0, "unclassified": 0}
    for w in raw_windows(directory, label):
        windows += 1
        ids.update(w["window_id"].encode() + b"\n")
        any_scoreable = False
        for sc in w["scenes"]:
            truth = [
                [
                    None if np.isnan(v[0]) else [float(v[0]), float(v[1])]
                    for v in sc["absolute"][:, t]
                ]
                for t in range(15)
            ]
            masks.update(_digest([[bool(m) for m in sc["mask"][:, t]] for t in range(15)]) + b"\n")
            truths.update(_digest(truth) + b"\n")
            if sc["scoreable"]:
                any_scoreable = True
                scenes_n += 1
                points += int(sc["mask"].sum())
                finals += int(sc["mask"][:, -1].sum())
                quality[sc["quality"]] += 1
        scoreable_windows += any_scoreable
        values: dict[tuple[int, int], list[list[float]]] = {}
        with torch.inference_mode():
            for regime in lds.INFORMATION_REGIMES:
                inputs = model_inputs(w, regime)
                for rep in lds.TARGET_REPRESENTATIONS:
                    for seed in lds.SEEDS:
                        cell = s.CELLS.index((regime, rep, seed))
                        out = models[(regime, rep, seed)](inputs).numpy().astype(np.float64)
                        for b, sc in enumerate(w["scenes"]):
                            if not sc["scoreable"]:
                                continue
                            pred = out[b] + (
                                sc["origin"][:, None, :] if rep != "absolute_xy" else 0.0
                            )
                            for j, stratum in enumerate(s.STRATA):
                                if j >= 4 and sc["quality"] != stratum:
                                    continue
                                a, z = {"early": (0, 5), "middle": (5, 10), "late": (10, 15)}.get(
                                    stratum, (0, 15)
                                )
                                mask = sc["mask"][:, a:z]
                                if not mask[:, -1].any():
                                    continue
                                squared = np.square(pred[:, a:z] - sc["absolute"][:, a:z]).sum(
                                    axis=-1
                                )
                                distances = np.sqrt(squared)
                                values.setdefault((cell, j), []).append(
                                    [
                                        float(distances[mask].mean()),
                                        float(distances[:, -1][mask[:, -1]].mean()),
                                        float(np.sqrt(squared[mask].sum() / (2 * mask.sum()))),
                                    ]
                                )
        for (cell, j), rows in values.items():
            for k in range(3):
                sums[cell][j][k] += sum(r[k] for r in rows) / len(rows)
            counts[cell][j] += 1
    records = [
        {
            "cell": list(c),
            "strata": {
                name: {
                    "windows": counts[i][j],
                    "metrics": {m: sums[i][j][k] / counts[i][j] for k, m in enumerate(s.METRICS)}
                    if counts[i][j]
                    else None,
                }
                for j, name in enumerate(s.STRATA)
            },
        }
        for i, c in enumerate(s.CELLS)
    ]
    return {
        "match": label,
        "identity": {
            "windows": windows,
            "scoreable_windows": scoreable_windows,
            "scoreable_scenes": scenes_n,
            "scored_points": points,
            "final_targets": finals,
            "scalar_coordinates": 2 * points,
            "window_ids_sha256": ids.hexdigest(),
            "mask_sha256": masks.hexdigest(),
            "truth_sha256": truths.hexdigest(),
            "scoreable_scene_quality": quality,
        },
        "records": records,
        "bindings": bindings,
        "raw_sha256": {
            key: _file_sha(directory / name)
            for key, name in (
                ("tracking_raw_sha256", "tracking.jsonl"),
                ("metadata_sha256", "metadata.json"),
                ("phases_sha256", "phases.json"),
                ("locked_sha256", "locked.jsonl"),
            )
        },
    }


def _file_sha(path: Path) -> str:
    with os.fdopen(paths.open_regular_fd(path), "rb") as stream:
        paths.check_regular(os.fstat(stream.fileno()), max_bytes=MAX, require_private=False)
        return hashlib.file_digest(stream, "sha256").hexdigest()
