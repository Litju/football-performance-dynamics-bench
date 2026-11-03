# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""Frozen per-target DeepSets MLP and research-only fit primitives."""

from __future__ import annotations

import hashlib
import math
import os
import random
import stat
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

import numpy as np
import torch
from numpy.typing import NDArray
from torch import Tensor, nn

from .information import validate_information_boundary

InformationRegime = Literal["history_only", "future_ball", "future_opponent_plus_ball"]
TargetRepresentation = Literal["absolute_xy", "origin_relative_displacement"]

INFORMATION_REGIMES: tuple[InformationRegime, ...] = (
    "history_only",
    "future_ball",
    "future_opponent_plus_ball",
)
TARGET_REPRESENTATIONS: tuple[TargetRepresentation, ...] = (
    "absolute_xy",
    "origin_relative_displacement",
)
SEEDS = (1729, 2718, 31415)
INPUT_DIMS: dict[InformationRegime, int] = {
    "history_only": 215,
    "future_ball": 260,
    "future_opponent_plus_ball": 276,
}
HEAD_FEATURE_LAYOUT = (
    ("target_player_history_xy_presence", 78),
    ("target_team_history_mean_embedding", 16),
    ("opponent_team_history_mean_embedding", 16),
    ("history_ball_xy_presence", 78),
    ("relative_time_offsets_s", 26),
    ("target_team_home_away_side", 1),
    ("permitted_future_ball_xy_presence", 45),
    ("permitted_future_opponent_mean_embedding", 16),
)
TRACK_POOLING = {
    "history": (
        "mean of encoded provider-ID tracks with a source player row in the 26 history "
        "samples, separately for each team"
    ),
    "future_opponent": (
        "mean of encoded opposing-team provider-ID tracks with a source player row in the "
        "15-sample horizon, including substitutes"
    ),
    "player_ids": "grouping and ordering only; never numeric features",
}
HISTORY_SAMPLES = 26
FUTURE_SAMPLES = 15
TARGET_PLAYERS = 11
HISTORY_TRACK_FEATURES = HISTORY_SAMPLES * 3
FUTURE_TRACK_FEATURES = FUTURE_SAMPLES * 3

_BASE_FEATURE_KEYS = frozenset(
    {
        "target_history",
        "history_team_tracks",
        "history_team_mask",
        "history_ball",
        "target_side",
    }
)
_FEATURE_KEYS: dict[InformationRegime, frozenset[str]] = {
    "history_only": _BASE_FEATURE_KEYS,
    "future_ball": _BASE_FEATURE_KEYS | {"future_ball"},
    "future_opponent_plus_ball": _BASE_FEATURE_KEYS
    | {"future_ball", "future_opponent_tracks", "future_opponent_mask"},
}


@dataclass(frozen=True, slots=True)
class ModelInputs:
    """Model inputs only; labels and target masks are intentionally separate."""

    target_history: Tensor
    history_team_tracks: Tensor
    history_team_mask: Tensor
    history_ball: Tensor
    target_side: Tensor
    future_ball: Tensor | None = None
    future_opponent_tracks: Tensor | None = None
    future_opponent_mask: Tensor | None = None


def validate_feature_payload(payload: Mapping[str, object], regime: InformationRegime) -> None:
    """Require the exact input fields for a regime and reject unknown channels."""
    if frozenset(payload) != _FEATURE_KEYS[regime]:
        raise ValueError("feature payload fields do not match the frozen information regime")
    validate_information_boundary(payload)


def _player_map(sample: Mapping[str, object]) -> dict[int, Mapping[str, object]]:
    players = sample.get("players")
    if not isinstance(players, list):
        raise ValueError("canonical sample players must be an array")
    result: dict[int, Mapping[str, object]] = {}
    for value in players:
        if not isinstance(value, Mapping):
            raise ValueError("canonical player must be an object")
        player_id = value.get("player_id")
        if isinstance(player_id, bool) or not isinstance(player_id, int) or player_id in result:
            raise ValueError("canonical player IDs must be unique integers")
        result[player_id] = cast(Mapping[str, object], value)
    return result


def _position_features(value: object) -> tuple[float, float, float]:
    if value is None:
        return 0.0, 0.0, 0.0
    if not isinstance(value, Mapping):
        raise ValueError("canonical observation must be an object or null")
    x, y = value.get("x_m"), value.get("y_m")
    if x is None or y is None:
        return 0.0, 0.0, 0.0
    if (
        isinstance(x, bool)
        or isinstance(y, bool)
        or not isinstance(x, int | float)
        or not isinstance(y, int | float)
        or not math.isfinite(x)
        or not math.isfinite(y)
    ):
        raise ValueError("model coordinates must be finite")
    return float(x), float(y), 1.0


def _track_features(
    frames: Sequence[Mapping[int, Mapping[str, object]]], player_id: int
) -> tuple[NDArray[np.float32], bool]:
    values = np.zeros((len(frames), 3), dtype=np.float32)
    observed = False
    for index, frame in enumerate(frames):
        player = frame.get(player_id)
        if player is not None:
            observed = True
        values[index] = _position_features(player)
    return values.reshape(-1), observed


def build_scene_feature_payload(
    support: Sequence[Mapping[str, object] | None],
    *,
    target_side: Literal["home", "away"],
    target_player_ids: Sequence[int],
    home_player_ids: Sequence[int],
    away_player_ids: Sequence[int],
    regime: InformationRegime,
) -> dict[str, NDArray[np.generic]]:
    """Build one directed scene's allowed features from its 41 observed samples."""
    if len(support) != HISTORY_SAMPLES + FUTURE_SAMPLES or any(
        sample is None for sample in support
    ):
        raise ValueError("feature extraction requires complete 41-sample support")
    if len(target_player_ids) != TARGET_PLAYERS or len(set(target_player_ids)) != TARGET_PLAYERS:
        raise ValueError("the frozen target panel must contain eleven unique players")
    home_ids, away_ids = tuple(sorted(home_player_ids)), tuple(sorted(away_player_ids))
    target_ids = tuple(target_player_ids)
    team_ids = (home_ids, away_ids)
    target_team_index = 0 if target_side == "home" else 1
    opponent_team_index = 1 - target_team_index
    if not set(target_ids).issubset(team_ids[target_team_index]):
        raise ValueError("target players must belong to the directed target team")

    complete_support = cast(Sequence[Mapping[str, object]], support)
    history = [_player_map(sample) for sample in complete_support[:HISTORY_SAMPLES]]
    future = [_player_map(sample) for sample in complete_support[HISTORY_SAMPLES:]]
    pool_size = max(len(home_ids), len(away_ids))
    history_team_tracks = np.zeros((2, pool_size, HISTORY_TRACK_FEATURES), dtype=np.float32)
    history_team_mask = np.zeros((2, pool_size), dtype=np.bool_)
    for team_index, player_ids in enumerate(team_ids):
        for player_index, player_id in enumerate(player_ids):
            track, observed = _track_features(history, player_id)
            history_team_tracks[team_index, player_index] = track
            history_team_mask[team_index, player_index] = observed

    target_history = np.stack([_track_features(history, player_id)[0] for player_id in target_ids])
    history_ball = np.concatenate(
        [_position_features(sample.get("ball")) for sample in complete_support[:HISTORY_SAMPLES]]
    ).astype(np.float32, copy=False)
    payload: dict[str, NDArray[np.generic]] = {
        "target_history": target_history,
        "history_team_tracks": history_team_tracks,
        "history_team_mask": history_team_mask,
        "history_ball": history_ball,
        "target_side": np.asarray(1.0 if target_side == "home" else -1.0, dtype=np.float32),
    }
    if regime != "history_only":
        payload["future_ball"] = np.concatenate(
            [
                _position_features(sample.get("ball"))
                for sample in complete_support[HISTORY_SAMPLES:]
            ]
        ).astype(np.float32, copy=False)
    if regime == "future_opponent_plus_ball":
        opponent_ids = team_ids[opponent_team_index]
        future_tracks = np.zeros((len(opponent_ids), FUTURE_TRACK_FEATURES), dtype=np.float32)
        future_mask = np.zeros(len(opponent_ids), dtype=np.bool_)
        for player_index, player_id in enumerate(opponent_ids):
            track, observed = _track_features(future, player_id)
            future_tracks[player_index] = track
            future_mask[player_index] = observed
        payload["future_opponent_tracks"] = future_tracks
        payload["future_opponent_mask"] = future_mask
    validate_feature_payload(payload, regime)
    return payload


def validate_truth_scene(
    scene: Mapping[str, object],
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.bool_]]:
    """Validate both frozen target panels and return player-major labels/mask."""
    absolute_raw = cast(list[list[object]], scene["absolute_xy"])
    displacement_raw = cast(list[list[object]], scene["origin_relative_displacement"])
    origin_raw = cast(list[list[float]], scene["origin_xy"])
    mask_raw = cast(list[list[bool]], scene["truth_mask"])
    if (
        len(absolute_raw) != FUTURE_SAMPLES
        or len(displacement_raw) != FUTURE_SAMPLES
        or len(mask_raw) != FUTURE_SAMPLES
        or len(origin_raw) != TARGET_PLAYERS
    ):
        raise ValueError("locked target panel dimensions differ")
    absolute = np.zeros((TARGET_PLAYERS, FUTURE_SAMPLES, 2), dtype=np.float64)
    displacement = np.zeros_like(absolute)
    mask = np.zeros((TARGET_PLAYERS, FUTURE_SAMPLES), dtype=np.bool_)
    for timestep in range(FUTURE_SAMPLES):
        if any(
            len(panel[timestep]) != TARGET_PLAYERS
            for panel in (absolute_raw, displacement_raw, mask_raw)
        ):
            raise ValueError("locked target panel player order differs")
        for player_index in range(TARGET_PLAYERS):
            absolute_xy = absolute_raw[timestep][player_index]
            displacement_xy = displacement_raw[timestep][player_index]
            is_present = mask_raw[timestep][player_index]
            if type(is_present) is not bool:
                raise ValueError("locked target masks must be Boolean")
            if (absolute_xy is None) != (displacement_xy is None) or is_present != (
                absolute_xy is not None
            ):
                raise ValueError(
                    "absolute and displacement panels must share the locked truth mask"
                )
            if absolute_xy is None or displacement_xy is None:
                continue
            if (
                not isinstance(absolute_xy, Sequence)
                or isinstance(absolute_xy, str | bytes)
                or not isinstance(displacement_xy, Sequence)
                or isinstance(displacement_xy, str | bytes)
                or len(absolute_xy) != 2
                or len(displacement_xy) != 2
            ):
                raise ValueError("locked target values must be XY pairs")
            a = cast(list[float], absolute_xy)
            d = cast(list[float], displacement_xy)
            origin = origin_raw[player_index]
            if len(origin) != 2 or not all(
                math.isfinite(float(value)) for value in (*a, *d, *origin)
            ):
                raise ValueError("locked physical targets and origins must be finite XY")
            if not all(
                math.isclose(d[axis], a[axis] - origin[axis], rel_tol=0.0, abs_tol=1e-12)
                for axis in (0, 1)
            ):
                raise ValueError("target representations do not describe the same trajectory")
            absolute[player_index, timestep] = a
            displacement[player_index, timestep] = d
            mask[player_index, timestep] = True
    if type(scene["scoreable"]) is not bool or bool(mask[:, -1].any()) != scene["scoreable"]:
        raise ValueError("scoreability must reflect a final-slot truth observation")
    return absolute, displacement, mask


def collate_feature_payloads(
    payloads: Sequence[Mapping[str, NDArray[np.generic]]], regime: InformationRegime
) -> ModelInputs:
    """Pad variable track sets for one batch; padding never enters a pool."""
    if not payloads:
        raise ValueError("a model batch cannot be empty")
    for payload in payloads:
        validate_feature_payload(payload, regime)
    batch_size = len(payloads)
    history_players = max(p["history_team_tracks"].shape[1] for p in payloads)
    history_tracks = np.zeros(
        (batch_size, 2, history_players, HISTORY_TRACK_FEATURES), dtype=np.float32
    )
    history_mask = np.zeros((batch_size, 2, history_players), dtype=np.bool_)
    for index, payload in enumerate(payloads):
        tracks = cast(NDArray[np.float32], payload["history_team_tracks"])
        mask = cast(NDArray[np.bool_], payload["history_team_mask"])
        history_tracks[index, :, : tracks.shape[1]] = tracks
        history_mask[index, :, : mask.shape[1]] = mask

    future_ball = None
    future_opponent_tracks = None
    future_opponent_mask = None
    if regime != "history_only":
        future_ball = torch.from_numpy(
            np.stack([cast(NDArray[np.float32], p["future_ball"]) for p in payloads])
        )
    if regime == "future_opponent_plus_ball":
        opponent_players = max(p["future_opponent_tracks"].shape[0] for p in payloads)
        opponent_tracks = np.zeros(
            (batch_size, opponent_players, FUTURE_TRACK_FEATURES), dtype=np.float32
        )
        opponent_mask = np.zeros((batch_size, opponent_players), dtype=np.bool_)
        for index, payload in enumerate(payloads):
            tracks = cast(NDArray[np.float32], payload["future_opponent_tracks"])
            mask = cast(NDArray[np.bool_], payload["future_opponent_mask"])
            opponent_tracks[index, : tracks.shape[0]] = tracks
            opponent_mask[index, : mask.shape[0]] = mask
        future_opponent_tracks = torch.from_numpy(opponent_tracks)
        future_opponent_mask = torch.from_numpy(opponent_mask)

    return ModelInputs(
        target_history=torch.from_numpy(
            np.stack([cast(NDArray[np.float32], p["target_history"]) for p in payloads])
        ),
        history_team_tracks=torch.from_numpy(history_tracks),
        history_team_mask=torch.from_numpy(history_mask),
        history_ball=torch.from_numpy(
            np.stack([cast(NDArray[np.float32], p["history_ball"]) for p in payloads])
        ),
        target_side=torch.from_numpy(
            np.asarray([p["target_side"] for p in payloads], dtype=np.float32)
        ),
        future_ball=future_ball,
        future_opponent_tracks=future_opponent_tracks,
        future_opponent_mask=future_opponent_mask,
    )


class PerTargetContextDeepSetsMLP(nn.Module):
    """Shared per-player predictor with the exact v2 DeepSets MLP architecture."""

    def __init__(self, regime: InformationRegime) -> None:
        super().__init__()
        if regime not in INPUT_DIMS:
            raise ValueError("unknown frozen information regime")
        self.regime: InformationRegime = regime
        self.history_player_encoder = nn.Sequential(
            nn.Linear(HISTORY_TRACK_FEATURES, 32),
            nn.ReLU(),
            nn.Linear(32, 16),
            nn.ReLU(),
        )
        self.future_opponent_encoder: nn.Sequential | None = None
        if regime == "future_opponent_plus_ball":
            self.future_opponent_encoder = nn.Sequential(
                nn.Linear(FUTURE_TRACK_FEATURES, 32),
                nn.ReLU(),
                nn.Linear(32, 16),
                nn.ReLU(),
            )
        input_dim = INPUT_DIMS[regime]
        self.prediction_head = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(128, 128),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(128, FUTURE_SAMPLES * 2),
        )
        self.history_time_offsets_s: Tensor
        offsets = torch.arange(HISTORY_SAMPLES, dtype=torch.float32) * 0.2 - 5.0
        self.register_buffer("history_time_offsets_s", offsets, persistent=False)

    def forward(self, inputs: ModelInputs) -> Tensor:
        batch_size = inputs.target_history.shape[0]
        if (
            inputs.target_history.shape != (batch_size, TARGET_PLAYERS, HISTORY_TRACK_FEATURES)
            or inputs.history_team_tracks.ndim != 4
            or inputs.history_team_tracks.shape[0] != batch_size
            or inputs.history_team_tracks.shape[1] != 2
            or inputs.history_team_tracks.shape[3] != HISTORY_TRACK_FEATURES
            or inputs.history_team_mask.shape != inputs.history_team_tracks.shape[:3]
            or inputs.history_team_mask.dtype is not torch.bool
            or inputs.history_ball.shape != (batch_size, HISTORY_TRACK_FEATURES)
            or inputs.target_side.shape != (batch_size,)
        ):
            raise ValueError("history model-input dimensions differ from the frozen interface")
        if not torch.all((inputs.target_side == 1.0) | (inputs.target_side == -1.0)):
            raise ValueError("target side must be home +1 or away -1")
        tensors = [
            inputs.target_history,
            inputs.history_team_tracks,
            inputs.history_ball,
            inputs.target_side,
        ]
        if any(value.dtype != torch.float32 for value in tensors):
            raise ValueError("model inputs must use PyTorch's default float32 tensors")
        if (
            not torch.isfinite(inputs.target_history).all()
            or not torch.isfinite(inputs.history_team_tracks).all()
            or not torch.isfinite(inputs.history_ball).all()
        ):
            raise ValueError("model inputs must be finite")

        encoded_history = self.history_player_encoder(inputs.history_team_tracks)
        history_weights = inputs.history_team_mask.unsqueeze(-1).to(encoded_history.dtype)
        counts = history_weights.sum(dim=2).clamp_min(1.0)
        team_means = (encoded_history * history_weights).sum(dim=2) / counts
        home_target = inputs.target_side > 0
        target_team = torch.where(home_target[:, None], team_means[:, 0], team_means[:, 1])
        opponent_team = torch.where(home_target[:, None], team_means[:, 1], team_means[:, 0])

        pieces = [
            inputs.target_history,
            target_team[:, None, :].expand(-1, TARGET_PLAYERS, -1),
            opponent_team[:, None, :].expand(-1, TARGET_PLAYERS, -1),
            inputs.history_ball[:, None, :].expand(-1, TARGET_PLAYERS, -1),
            self.history_time_offsets_s[None, None, :].expand(batch_size, TARGET_PLAYERS, -1),
            inputs.target_side[:, None, None].expand(-1, TARGET_PLAYERS, -1),
        ]
        if self.regime != "history_only":
            if (
                inputs.future_ball is None
                or inputs.future_ball.shape
                != (
                    batch_size,
                    FUTURE_TRACK_FEATURES,
                )
                or inputs.future_ball.dtype != torch.float32
            ):
                raise ValueError("future_ball regime requires exactly fifteen ball samples")
            if not torch.isfinite(inputs.future_ball).all():
                raise ValueError("future ball features must be finite")
            pieces.append(inputs.future_ball[:, None, :].expand(-1, TARGET_PLAYERS, -1))
        elif inputs.future_ball is not None:
            raise ValueError("history_only cannot receive future ball observations")

        if self.regime == "future_opponent_plus_ball":
            if (
                self.future_opponent_encoder is None
                or inputs.future_opponent_tracks is None
                or inputs.future_opponent_mask is None
                or inputs.future_opponent_tracks.ndim != 3
                or inputs.future_opponent_tracks.shape[0] != batch_size
                or inputs.future_opponent_tracks.shape[2] != FUTURE_TRACK_FEATURES
                or inputs.future_opponent_mask.shape != inputs.future_opponent_tracks.shape[:2]
                or inputs.future_opponent_mask.dtype is not torch.bool
                or inputs.future_opponent_tracks.dtype != torch.float32
            ):
                raise ValueError("future-opponent regime requires masked fifteen-sample tracks")
            if not torch.isfinite(inputs.future_opponent_tracks).all():
                raise ValueError("future opponent features must be finite")
            encoded_future = self.future_opponent_encoder(inputs.future_opponent_tracks)
            future_weights = inputs.future_opponent_mask.unsqueeze(-1).to(encoded_future.dtype)
            future_counts = future_weights.sum(dim=1).clamp_min(1.0)
            future_mean = (encoded_future * future_weights).sum(dim=1) / future_counts
            pieces.append(future_mean[:, None, :].expand(-1, TARGET_PLAYERS, -1))
        elif inputs.future_opponent_tracks is not None or inputs.future_opponent_mask is not None:
            raise ValueError("this information regime cannot receive future opponent tracks")

        features = torch.cat(pieces, dim=-1)
        if features.shape[-1] != INPUT_DIMS[self.regime]:
            raise RuntimeError("constructed model input differs from the frozen dimension")
        output = self.prediction_head(features).reshape(
            batch_size, TARGET_PLAYERS, FUTURE_SAMPLES, 2
        )
        if not torch.isfinite(output).all():
            raise FloatingPointError("model produced a non-finite prediction")
        return output


def configure_deterministic_cpu() -> None:
    """Apply the pinned single-thread CPU numerical settings in a fresh worker."""
    torch.set_num_threads(1)
    if torch.get_num_interop_threads() != 1:
        torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark = False


def seed_training(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def make_optimizer(model: nn.Module) -> torch.optim.AdamW:
    return torch.optim.AdamW(
        model.parameters(),
        lr=0.001,
        betas=(0.9, 0.999),
        eps=1e-8,
        weight_decay=0.0001,
    )


def masked_scene_ade_loss(prediction: Tensor, truth: Tensor, mask: Tensor) -> Tensor:
    if prediction.shape != truth.shape or prediction.shape[-2:] != (FUTURE_SAMPLES, 2):
        raise ValueError("prediction and truth must be matching fifteen-step XY panels")
    if mask.shape != prediction.shape[:-1] or mask.dtype is not torch.bool:
        raise ValueError("only the locked Boolean target mask may control the loss")
    if not torch.isfinite(prediction).all() or not torch.isfinite(truth).all():
        raise FloatingPointError("training values must be finite")
    distances = torch.linalg.vector_norm(prediction - truth, dim=-1)
    weights = mask.to(distances.dtype)
    counts = weights.sum(dim=(1, 2))
    if torch.any(counts <= 0):
        raise ValueError("every sampled directed scene must be scoreable")
    return ((distances * weights).sum(dim=(1, 2)) / counts).mean()


def sample_scene_index(
    scoreable_windows: Sequence[NDArray[np.bool_]], rng: np.random.Generator
) -> tuple[int, int, int]:
    """Sample match, window, and scoreable directed scene uniformly at each level."""
    if not scoreable_windows:
        raise ValueError("each training match needs sampleable scoreable windows")
    match_index = int(rng.integers(len(scoreable_windows)))
    windows = scoreable_windows[match_index]
    if windows.ndim != 2 or windows.shape[1] != 2 or not len(windows):
        raise ValueError("training match windows must have two directed scene slots")
    window_index = int(rng.integers(len(windows)))
    scenes = np.flatnonzero(windows[window_index])
    if not len(scenes):
        raise ValueError("sampled window has no scoreable directed scene")
    scene_index = int(rng.choice(scenes))
    return match_index, window_index, scene_index


def equal_match_mean(values: Mapping[str, float], expected_matches: Sequence[str]) -> float:
    if set(values) != set(expected_matches) or not expected_matches:
        raise ValueError("validation must contain exactly all four frozen matches")
    metrics = [values[match] for match in expected_matches]
    if any(not math.isfinite(value) for value in metrics):
        raise FloatingPointError("validation metrics must be finite")
    return math.fsum(metrics) / len(metrics)


@dataclass(slots=True)
class CheckpointSelection:
    best_metric: float | None = None
    best_step: int | None = None
    checks_without_improvement: int = 0

    def observe(self, step: int, metric: float) -> bool:
        if step < 100 or step % 100 or not math.isfinite(metric):
            raise ValueError("checkpoint selection accepts finite 100-step validation checks")
        improved = self.best_metric is None or metric < self.best_metric
        if improved:
            self.best_metric = metric
            self.best_step = step
            self.checks_without_improvement = 0
        else:
            self.checks_without_improvement += 1
        return improved

    @property
    def should_stop(self) -> bool:
        return self.checks_without_improvement >= 10


def retry_allowed(status: str, cause: str, attempts: int, config_unchanged: bool) -> bool:
    return (
        status == "uncommitted"
        and cause == "external_worker_interruption"
        and attempts == 1
        and config_unchanged
    )


def validation_due(step: int) -> bool:
    return step >= 100 and step % 100 == 0


def fit_failure_category(error: BaseException) -> str:
    if isinstance(error, (MemoryError, torch.OutOfMemoryError)) or (
        isinstance(error, RuntimeError) and "out of memory" in str(error).casefold()
    ):
        return "out_of_memory"
    if isinstance(error, FloatingPointError):
        return "non_finite_fit"
    return "fit_failure"


def save_checkpoint_atomically(path: Path, payload: Mapping[str, object]) -> str:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        torch.save(dict(payload), stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return checkpoint_sha256(path)


def checkpoint_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError("checkpoint identity requires an exclusive regular file")
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
        after = os.fstat(stream.fileno())
        if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise ValueError("checkpoint changed while its identity was computed")
    return digest.hexdigest()


def load_checkpoint_verified(path: Path, expected_sha256: str) -> dict[str, object]:
    if checkpoint_sha256(path) != expected_sha256:
        raise ValueError("checkpoint SHA-256 mismatch")
    loaded = torch.load(path, map_location="cpu", weights_only=True)
    if not isinstance(loaded, dict) or not isinstance(loaded.get("state_dict"), dict):
        raise ValueError("checkpoint payload shape differs")
    return cast(dict[str, object], loaded)


def physical_metrics(
    prediction: NDArray[np.float32],
    truth: NDArray[np.float64],
    mask: NDArray[np.bool_],
) -> dict[str, float]:
    if prediction.shape != truth.shape or prediction.shape[-2:] != (FUTURE_SAMPLES, 2):
        raise ValueError("physical metrics require matching player-major XY panels")
    if mask.shape != prediction.shape[:-1] or not mask.any():
        raise ValueError("physical metrics require the locked nonempty target mask")
    if not np.isfinite(prediction).all() or not np.isfinite(truth).all():
        raise FloatingPointError("physical metrics require finite predictions and truth")
    delta = prediction.astype(np.float64) - truth
    distances = np.hypot(delta[..., 0], delta[..., 1])
    final_mask = mask[..., -1]
    if not final_mask.any():
        raise ValueError("a validation scene must have a scoreable final target")
    return {
        "ade_m": float(distances[mask].mean()),
        "fde_m": float(distances[..., -1][final_mask].mean()),
        "xy_rmse_m": float(np.sqrt(np.square(delta[mask]).sum() / (2 * mask.sum()))),
        "scored_points": int(mask.sum()),
        "final_targets": int(final_mask.sum()),
    }
