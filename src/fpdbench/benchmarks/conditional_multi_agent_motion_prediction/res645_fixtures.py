# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportPrivateUsage=false
"""Invented source files, a locked population stream, and artificial CPU checkpoints.

Everything here is generated from seeded random numbers. No SkillCorner file, held-out match,
private checkpoint or real manifest is read. Fixture match files carry real *pinned-release*
training-role identifiers only because the production canonicalizer accepts nothing else; the
adapter refuses every evaluation-role identity in synthetic mode.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import torch

from fpdbench.data_sources.skillcorner import canonical_bytes
from fpdbench.data_sources.skillcorner import load_manifest as load_source_manifest
from fpdbench.data_states.skillcorner import iter_skillcorner_5hz_v2
from fpdbench.eligibility.skillcorner import (
    PhaseInterval,
    diagnose_skillcorner_window_v2,
    skillcorner_period_ranges,
)

from . import learned_deepsets as lds
from . import res645_checkpoints as ck
from . import res645_source_stream as src
from .evaluation_population import prospective_window_id_v2
from .streaming_population_producer_v1 import _population_events, _scene

BUNDLE_MARKER = "RES645-SYNTHETIC-BUNDLE-v1"
# Pinned-release training-role identifiers; never evaluation-role identifiers.
FIXTURE_MATCH_IDS = ("1886347", "1899585", "1927964", "1959846")
LABELS = tuple(f"synthetic-match-{i}" for i in range(4))
FIRST_FRAME = 100


def _write(path: Path, data: bytes, mode: int = 0o600) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _swapped(match_index: int, pid: int) -> bool:
    """Match 1: the away XI is replaced by substitutes at one slot; match 3: both teams."""
    return (match_index == 1 and pid >= 1012) or match_index == 3


def invented_frames(match_index: int, samples: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """10 Hz raw frames for 22 invented players and a ball; odd frames are decoys."""
    rng = np.random.default_rng(np.random.SeedSequence([645, match_index]))
    end = FIRST_FRAME + 2 * samples
    ids = list(range(1001, 1023))
    substitutes = list(range(1023, 1045))
    metadata: dict[str, Any] = {
        "id": int(FIXTURE_MATCH_IDS[match_index]),
        "home_team": {"id": 101},
        "away_team": {"id": 202},
        "pitch_length": 105,
        "pitch_width": 68,
        "match_periods": [{"period": 1, "start_frame": FIRST_FRAME, "end_frame": end}],
        "players": [
            {
                "id": pid,
                "team_id": 101 if pid < 1012 or 1023 <= pid < 1034 else 202,
                "playing_time": {
                    "by_period": [
                        {"name": "period_1", "start_frame": FIRST_FRAME, "end_frame": end}
                    ]
                },
            }
            for pid in ids + substitutes
        ],
    }
    base = rng.uniform([-30, -20], [30, 20], (22, 2))
    velocity = rng.normal(0, 1.2, (22, 2))
    ball_base = rng.uniform(-10, 10, 2)
    frames: list[dict[str, Any]] = []
    for step in range(samples):
        # Frames are 10 Hz; even frames are the canonical 5 Hz samples, odd ones are decoys.
        for sub in (0, 1):
            frame = FIRST_FRAME + 2 * step + sub
            t = (frame - FIRST_FRAME) / 10
            # Long qualification streams stay inside the invented pitch rather than drifting out.
            travel = 10 * np.sin(t / 10) if samples > 100 else t
            xy = base + velocity * travel + rng.normal(0, 0.05, (22, 2))
            players: list[dict[str, Any]] = []
            for i, pid in enumerate(ids):
                dropout = rng.random() < 0.06 and sub == 0
                if dropout and rng.random() < 0.5:
                    continue  # absent from the frame
                if sub == 0 and step == 40 and _swapped(match_index, pid):
                    continue  # original player absent from this one slot
                late = step >= 43 and (pid < 1012) == (match_index % 2 == 0)
                players.append(
                    {
                        "player_id": pid,
                        "x": None if dropout else float(xy[i, 0] if sub == 0 else 777.0),
                        "y": None if dropout else float(xy[i, 1] if sub == 0 else 777.0),
                        "is_detected": not (late and rng.random() < 0.5),
                    }
                )
            if sub == 0 and step == 40 and match_index in (1, 3):
                players += [
                    {"player_id": pid, "x": float(pid % 11), "y": -3.0, "is_detected": True}
                    for pid in substitutes
                    if match_index == 3 or pid >= 1034
                ]
            seconds, tenth = divmod(frame, 10)
            hours, seconds = divmod(seconds, 3600)
            minutes, seconds = divmod(seconds, 60)
            frames.append(
                {
                    "frame": frame,
                    "timestamp": f"{hours:02d}:{minutes:02d}:{seconds:02d}.{tenth}0",
                    "period": 1,
                    "ball_data": {
                        "x": float(ball_base[0] + 0.5 * travel),
                        "y": float(ball_base[1]),
                        "z": None,
                        "is_detected": bool(rng.random() > 0.1),
                    },
                    "possession": None,
                    "image_corners_projection": {"synthetic": True},
                    "player_data": players,
                }
            )
    return metadata, frames


def _fix_origins(frames: list[dict[str, Any]], samples: int) -> None:
    """Every window origin keeps all 22 players observed so the frozen 11-player panels exist."""
    for step in range(25, samples - 15):
        frame = frames[2 * step]
        frame["player_data"] = [p for p in frame["player_data"] if 1001 <= p["player_id"] <= 1022]
        present = {p["player_id"]: p for p in frame["player_data"]}
        for pid in range(1001, 1023):
            player = present.get(pid)
            if player is None:
                player = {"player_id": pid, "x": 0.0, "y": 0.0, "is_detected": True}
                frame["player_data"].append(player)
            if player["x"] is None:
                player["x"], player["y"], player["is_detected"] = float(pid % 7), 1.0, True


def lock_pass(
    metadata: dict[str, Any], frames: list[dict[str, Any]], match_id: str, first: int, end: int
) -> tuple[bytes, int]:
    """Production eligibility and truth builders over invented samples: the locked stream."""
    release_id = str(load_source_manifest()["source_release_id"])
    periods, _ = skillcorner_period_ranges(metadata)
    phases = (PhaseInterval(release_id, int(match_id), 1, first, end),)
    rows: list[bytes] = []
    eligible = 0
    for (period, frame, origin_id), support in _population_events(
        iter_skillcorner_5hz_v2(frames, metadata, source_release_id=release_id), periods
    ):
        complete = all(s is not None for s in support)
        diagnostic = diagnose_skillcorner_window_v2(
            support,
            history_intervals=25,
            future_intervals=15,
            match_metadata=metadata,
            phase_intervals=phases,
        )
        row: dict[str, Any] = {
            "match_id": match_id,
            "role": "evaluation",
            "period": period,
            "source_frame": frame,
            "origin_sample_id": origin_id,
            "window_id": None,
        }
        if complete and diagnostic.candidate_rules_pass:
            row["window_id"] = prospective_window_id_v2(match_id, origin_id)
            row["scenes"] = [_scene(support, side)[1] for side in ("home", "away")]
            eligible += 1
        rows.append(canonical_bytes(row) + b"\n")
    return b"".join(rows), eligible


def build_match(directory: Path, match_index: int, samples: int) -> dict[str, Any]:
    """Write one match directory including the lock pass that mirrors the producer stream."""
    directory.mkdir(mode=0o700)
    metadata, frames = invented_frames(match_index, samples)
    _fix_origins(frames, samples)
    match_id = FIXTURE_MATCH_IDS[match_index]
    _write(
        directory / "fixture.json",
        canonical_bytes({"synthetic_source_fixture": src.SOURCE_MARKER, "match_id": match_id}),
    )
    _write(directory / "metadata.json", canonical_bytes(metadata))
    _write(
        directory / "phases.json",
        canonical_bytes(
            [{"period": 1, "frame_start": FIRST_FRAME, "frame_end": FIRST_FRAME + 2 * samples}]
        ),
    )
    _write(directory / "tracking.jsonl", b"".join(canonical_bytes(f) + b"\n" for f in frames))
    locked, eligible = lock_pass(metadata, frames, match_id, FIRST_FRAME, FIRST_FRAME + 2 * samples)
    _write(directory / "locked.jsonl", locked)
    return {
        "label": LABELS[match_index],
        "match_id": match_id,
        "directory": f"match-{match_index}",
        "eligible_windows": eligible,
    }


def build_checkpoints(directory: Path, receipts: Path | None = None) -> dict[str, Any]:
    """Eighteen artificial CPU checkpoints (random weights), fit receipts and a manifest."""
    directory.mkdir(mode=0o700)
    receipts = receipts or directory.with_name("receipts")
    receipts.mkdir(mode=0o700)
    records: list[dict[str, Any]] = []
    for number, cell in enumerate(ck.EXPECTED_CELLS):
        torch.manual_seed(645_000 + number)
        model = lds.PerTargetContextDeepSetsMLP(cell[0])
        step = 100 * (1 + number)
        config = hashlib.sha256(f"synthetic-config|{number}|{cell}".encode()).hexdigest()
        temporary = directory / f"pending-{number}.pt"
        digest = lds.save_checkpoint_atomically(
            temporary,
            {
                "metadata": {
                    "run_id": ck.run_id(cell),
                    "configuration_sha256": config,
                    "selected_step": step,
                    "attempt_number": 1,
                },
                "state_dict": {k: v.detach().clone() for k, v in model.state_dict().items()},
            },
        )
        os.rename(temporary, directory / f"{digest}.pt")
        fields: dict[str, Any] = {
            "information_regime": cell[0],
            "target_representation": cell[1],
            "seed": cell[2],
            "selected_step": step,
            "optimizer_steps": step + 1000,
            "checkpoint_sha256": digest,
            "configuration_sha256": config,
            **{
                name: hashlib.sha256(f"synthetic-{name}|{number}".encode()).hexdigest()
                for name in (
                    "environment_sha256",
                    "population_manifest_sha256",
                    "target_mask_identity_sha256",
                    "plan_sha256",
                    "protocol_sha256",
                )
            },
            "train_match_ids": ["synthetic-train-a", "synthetic-train-b"],
            "validation_match_ids": ["synthetic-validation"],
        }
        receipt = canonical_bytes(
            {
                "status": "completed",
                "fit_role": "final_train",
                "run_id": ck.run_id(cell),
                "model_id": ck.MODEL_ID,
                "attempt_number": 1,
                **fields,
            }
        )
        receipt_sha = hashlib.sha256(receipt).hexdigest()
        _write(receipts / f"{receipt_sha}.json", receipt)
        records.append(
            {
                **fields,
                "attempt_number": 1,
                "fit_role": "final_train",
                "model_id": ck.MODEL_ID,
                "receipt_sha256": receipt_sha,
            }
        )
    return {
        "synthetic_fixture": ck.SYNTHETIC_MARKER,
        "study_id": "synthetic-res645",
        "checkpoints": records,
    }


def build_bundle(root: Path, samples: int = 46) -> Path:
    """One fixture bundle: 4 invented matches + 18 artificial checkpoints + synthetic manifest."""
    root.mkdir(mode=0o700)
    matches = [build_match(root / f"match-{i}", i, samples) for i in range(4)]
    manifest = build_checkpoints(root / "checkpoints")
    _write(root / "manifest.json", canonical_bytes(manifest))
    _write(root / "bundle.json", canonical_bytes({"bundle": BUNDLE_MARKER, "matches": matches}))
    return root


def read_bundle(
    root: Path,
) -> tuple[
    list[src.SourceMatchSpec], dict[str, Any], Path
]:  # checkpoints; receipts at root/'receipts'
    """Validate and parse a bundle; refuses anything lacking the invented-fixture markers."""
    from . import res645_paths as paths

    raw, _ = paths.read_regular_file(root / "bundle.json", max_bytes=1 << 20)
    bundle = json.loads(raw)
    if bundle.get("bundle") != BUNDLE_MARKER or [m["label"] for m in bundle["matches"]] != list(
        LABELS
    ):
        raise PermissionError("not an invented RES645 fixture bundle")
    specs = [
        src.SourceMatchSpec(m["label"], m["match_id"], root / m["directory"])
        for m in bundle["matches"]
    ]
    manifest_raw, _ = paths.read_regular_file(root / "manifest.json", max_bytes=1 << 20)
    return specs, json.loads(manifest_raw), root / "checkpoints"
