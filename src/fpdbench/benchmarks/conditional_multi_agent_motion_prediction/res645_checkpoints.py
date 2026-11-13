# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""Strictly read-only frozen-checkpoint contract for the 18 DeepSets configurations.

``mode="synthetic"`` qualifies the contract on artificial CPU checkpoints and a synthetic
manifest. ``mode="frozen"`` inventory checks demand the pinned RES593 manifest identity;
deserialization remains disabled until authenticated owner authorization is integrated. A
synthetic manifest can never validate as the frozen one, nor the reverse.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

if TYPE_CHECKING:
    from .res646_authorization import Campaign

import torch
from torch import Tensor

from . import learned_deepsets as lds
from . import res645_paths as paths

FROZEN_MANIFEST_SHA256 = "770f1d9bbca3020237992181a56e4f5be4adaae7aab07f5f1313aa699d8693e0"
MODEL_ID = "per_target_context_deepsets_mlp_v1"
SYNTHETIC_MARKER = "RES645-SYNTHETIC-CHECKPOINT-FIXTURE-v1"
MAX_CHECKPOINT_BYTES = 8 * 1024 * 1024
_HEX = re.compile(r"[0-9a-f]{64}")
type Cell = tuple[lds.InformationRegime, lds.TargetRepresentation, int]
type Mode = Literal["synthetic", "frozen"]

EXPECTED_CELLS: tuple[Cell, ...] = tuple(
    (regime, representation, seed)
    for regime in lds.INFORMATION_REGIMES
    for representation in lds.TARGET_REPRESENTATIONS
    for seed in lds.SEEDS
)


class CheckpointContractError(ValueError):
    """Any violation of the frozen checkpoint contract; never recoverable by substitution."""


@dataclass(frozen=True, slots=True)
class Binding:
    cell: Cell
    checkpoint_sha256: str
    configuration_sha256: str
    selected_step: int
    state_sha256: str

    def document(self) -> dict[str, Any]:
        return {
            "cell": list(self.cell),
            "checkpoint_sha256": self.checkpoint_sha256,
            "configuration_sha256": self.configuration_sha256,
            "selected_step": self.selected_step,
            "state_sha256": self.state_sha256,
        }


@dataclass(frozen=True, slots=True)
class FrozenModelSet:
    manifest_sha256: str
    models: dict[Cell, lds.PerTargetContextDeepSetsMLP]
    bindings: tuple[Binding, ...]

    def assert_unchanged(self) -> None:
        """Detect any parameter or buffer mutation, or a model left in training mode."""
        for binding in self.bindings:
            model = self.models[binding.cell]
            if model.training or state_sha256(model) != binding.state_sha256:
                raise CheckpointContractError("frozen model changed after loading")


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def run_id(cell: Cell) -> str:
    regime, representation, seed = cell
    return f"{MODEL_ID}|{regime}|{representation}|final_train|final|{seed}"


def state_sha256(model: torch.nn.Module) -> str:
    digest = hashlib.sha256()
    for name, tensor in sorted(model.state_dict().items()):
        digest.update(name.encode() + b"\0" + str(tuple(tensor.shape)).encode() + b"\0")
        digest.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return digest.hexdigest()


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not _HEX.fullmatch(value):
        raise CheckpointContractError(f"{label} must be a lowercase SHA-256")
    return value


def record_cell(record: Mapping[str, object]) -> Cell:
    regime, representation, seed = (
        record.get("information_regime"),
        record.get("target_representation"),
        record.get("seed"),
    )
    if (
        record.get("model_id") != MODEL_ID
        or regime not in lds.INFORMATION_REGIMES
        or representation not in lds.TARGET_REPRESENTATIONS
        or type(seed) is not int
        or seed not in lds.SEEDS
    ):
        raise CheckpointContractError("manifest record names an unexpected model cell")
    return cast(Cell, (regime, representation, seed))


def validate_records(manifest: Mapping[str, object]) -> dict[Cell, Mapping[str, object]]:
    records = manifest.get("checkpoints")
    if not isinstance(records, list):
        raise CheckpointContractError("manifest checkpoints must be an array")
    by_cell: dict[Cell, Mapping[str, object]] = {}
    unique: dict[str, set[str]] = {k: set() for k in ("checkpoint", "configuration", "receipt")}
    for raw in cast(list[object], records):
        if not isinstance(raw, dict):
            raise CheckpointContractError("manifest record must be an object")
        record = cast(dict[str, object], raw)
        cell = record_cell(record)
        if cell in by_cell:
            raise CheckpointContractError("manifest duplicates a model cell")
        if record.get("fit_role") != "final_train" or record.get("attempt_number") != 1:
            raise CheckpointContractError("manifest includes a nonfinal or retried fit")
        step, steps = record.get("selected_step"), record.get("optimizer_steps")
        if (
            type(step) is not int
            or type(steps) is not int
            or not 100 <= step <= steps
            or step > 5000
            or step % 100
        ):
            raise CheckpointContractError("selected step violates the frozen cadence")
        for name in RECEIPT_COPIED_FIELDS[7:11]:
            _sha(record.get(name), name)
        for field, group in (
            ("checkpoint_sha256", "checkpoint"),
            ("configuration_sha256", "configuration"),
            ("receipt_sha256", "receipt"),
        ):
            value = _sha(record.get(field), field)
            if value in unique[group]:
                raise CheckpointContractError(f"manifest duplicates a {group} digest")
            unique[group].add(value)
        by_cell[cell] = record
    if set(by_cell) != set(EXPECTED_CELLS) or len(records) != 18:
        raise CheckpointContractError("manifest must contain the exact 18 frozen cells once")
    return by_cell


def frozen_manifest() -> dict[str, object]:
    """The packaged, pinned RES593 manifest. Reading it never touches a checkpoint file."""
    root = resources.files("fpdbench.benchmarks.conditional_multi_agent_motion_prediction")
    payload = root.joinpath("res593_checkpoint_manifest_v1.json").read_bytes()
    if hashlib.sha256(payload).hexdigest() != FROZEN_MANIFEST_SHA256:
        raise CheckpointContractError("frozen checkpoint manifest identity differs")
    return cast(dict[str, object], json.loads(payload))


def validate_manifest(manifest: Mapping[str, object], mode: Mode) -> str:
    """Return the manifest identity after mode-specific validation."""
    by_cell = validate_records(manifest)
    frozen = frozen_manifest()
    if mode == "frozen":
        if manifest != frozen or "synthetic_fixture" in manifest:
            raise CheckpointContractError("manifest is not the pinned frozen manifest")
        return FROZEN_MANIFEST_SHA256
    frozen_hashes = {cast(dict[str, str], r)["checkpoint_sha256"] for r in frozen["checkpoints"]}  # type: ignore[attr-defined]
    used = {cast(str, r["checkpoint_sha256"]) for r in by_cell.values()}
    if (
        manifest.get("synthetic_fixture") != SYNTHETIC_MARKER
        or manifest.get("study_id") != "synthetic-res645"
        or used & frozen_hashes
    ):
        raise CheckpointContractError("synthetic fixture cannot masquerade as frozen checkpoints")
    return hashlib.sha256(canonical(manifest)).hexdigest()


RECEIPT_COPIED_FIELDS = (
    "information_regime",
    "target_representation",
    "seed",
    "selected_step",
    "optimizer_steps",
    "checkpoint_sha256",
    "configuration_sha256",
    "environment_sha256",
    "population_manifest_sha256",
    "target_mask_identity_sha256",
    "plan_sha256",
    "protocol_sha256",
    "train_match_ids",
    "validation_match_ids",
)


def verify_fit_receipt(
    directory: Path, record: Mapping[str, object], cell: Cell, *, campaign: Campaign | None = None
) -> None:
    """The owner-private completed-fit receipt must hash to, and agree with, its manifest record."""
    data, identity = paths.read_regular_file(
        directory / f"{record['receipt_sha256']}.json",
        max_bytes=1 << 20,
        require_private=True,
        campaign=campaign,
    )
    if identity.sha256 != record["receipt_sha256"]:
        raise CheckpointContractError("completed-fit receipt SHA-256 mismatch")
    receipt = json.loads(data)
    expected = {
        "status": "completed",
        "fit_role": "final_train",
        "run_id": run_id(cell),
        "model_id": MODEL_ID,
        "attempt_number": 1,
        **{name: record.get(name) for name in RECEIPT_COPIED_FIELDS},
    }
    if not isinstance(receipt, dict) or any(
        receipt.get(key) != value for key, value in expected.items()
    ):
        raise CheckpointContractError("fit receipt differs from the checkpoint manifest")


def verify_inventory(
    manifest: Mapping[str, object], directory: Path, receipts: Path, mode: Mode
) -> str:
    """Verify bytes and fit bindings without deserializing checkpoints or loading models."""
    manifest_sha = validate_manifest(manifest, mode)
    records = validate_records(manifest)
    if paths.list_directory(directory, require_private=True) != sorted(
        f"{r['checkpoint_sha256']}.pt" for r in records.values()
    ):
        raise CheckpointContractError("checkpoint directory differs from the manifest files")
    if paths.list_directory(receipts, require_private=True) != sorted(
        f"{r['receipt_sha256']}.json" for r in records.values()
    ):
        raise CheckpointContractError("receipt directory differs from the manifest receipts")
    for cell, record in records.items():
        verify_fit_receipt(receipts, record, cell)
        fd = paths.open_regular_fd(directory / f"{record['checkpoint_sha256']}.pt")
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            paths.check_regular(before, max_bytes=MAX_CHECKPOINT_BYTES, require_private=True)
            digest = hashlib.sha256()
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
            if paths.stat_key(before) != paths.stat_key(os.fstat(stream.fileno())):
                raise CheckpointContractError("checkpoint changed while hashing")
        if digest.hexdigest() != record["checkpoint_sha256"]:
            raise CheckpointContractError("checkpoint SHA-256 mismatch")
    return manifest_sha


def _expected_shapes(regime: lds.InformationRegime) -> dict[str, tuple[int, ...]]:
    return {
        k: tuple(v.shape) for k, v in lds.PerTargetContextDeepSetsMLP(regime).state_dict().items()
    }


def load_checkpoint(
    path: Path, record: Mapping[str, object], cell: Cell, *, campaign: Campaign | None = None
) -> tuple[Any, str]:
    """Hash and deserialize the *same* bytes; tensors-only unpickling; exact cell binding."""
    frozen_hashes = {
        cast(dict[str, str], item)["checkpoint_sha256"]
        for item in cast(list[object], frozen_manifest()["checkpoints"])
    }
    if record.get("checkpoint_sha256") in frozen_hashes:
        if campaign is None:
            raise CheckpointContractError(
                "frozen inference requires authenticated owner authorization"
            )
        campaign.allow_models(frozen_manifest(), path.parent, campaign.receipts)
        if record != validate_records(frozen_manifest())[cell]:
            raise CheckpointContractError("checkpoint record differs from frozen manifest")
    data, identity = paths.read_regular_file(
        path, max_bytes=MAX_CHECKPOINT_BYTES, require_private=True, campaign=campaign
    )
    if identity.sha256 in frozen_hashes and campaign is None:
        raise CheckpointContractError("frozen inference requires authenticated owner authorization")
    if identity.sha256 != record["checkpoint_sha256"]:
        raise CheckpointContractError("checkpoint SHA-256 mismatch")
    try:
        payload = torch.load(io.BytesIO(data), map_location="cpu", weights_only=True)
    except Exception as exc:  # unpickling errors are heterogeneous
        raise CheckpointContractError("checkpoint is not a tensors-only payload") from exc
    if not isinstance(payload, dict) or set(payload) != {"metadata", "state_dict"}:
        raise CheckpointContractError("checkpoint cannot contain optimizer or extra state")
    metadata = payload["metadata"]
    expected_metadata = {
        "run_id": run_id(cell),
        "configuration_sha256": record["configuration_sha256"],
        "selected_step": record["selected_step"],
        "attempt_number": 1,
    }
    if metadata != expected_metadata:
        raise CheckpointContractError("checkpoint metadata differs from its manifest binding")
    state = payload["state_dict"]
    shapes = _expected_shapes(cell[0])
    if not isinstance(state, dict) or set(state) != set(shapes):
        raise CheckpointContractError("checkpoint tensors differ from the frozen structure")
    for name, tensor in cast(dict[str, object], state).items():
        if (
            not isinstance(tensor, Tensor)
            or tuple(tensor.shape) != shapes[name]
            or tensor.dtype != torch.float32
            or tensor.device.type != "cpu"
            or not bool(torch.isfinite(tensor).all())
        ):
            raise CheckpointContractError("unexpected tensor shape, dtype or non-finite value")
    return state, identity.sha256


def load_models(
    manifest: Mapping[str, object],
    directory: Path,
    mode: Mode,
    receipts: Path,
    *,
    campaign: Campaign | None = None,
) -> FrozenModelSet:
    """Load exactly the 18 listed checkpoints as frozen float32 CPU models, read-only."""
    manifest_sha = validate_manifest(manifest, mode)
    if mode == "frozen":
        if campaign is None:
            raise CheckpointContractError(
                "frozen inference requires authenticated owner authorization"
            )
        campaign.allow_models(manifest, directory, receipts)
    else:
        campaign = None
    lds.configure_deterministic_cpu()
    by_cell = validate_records(manifest)
    try:
        present = paths.list_directory(directory, require_private=True, campaign=campaign)
    except PermissionError as exc:
        raise CheckpointContractError(str(exc)) from exc
    wanted = sorted(f"{r['checkpoint_sha256']}.pt" for r in by_cell.values())
    if present != wanted:
        raise CheckpointContractError("checkpoint directory differs from the manifest files")
    try:
        listed = paths.list_directory(receipts, require_private=True, campaign=campaign)
    except PermissionError as exc:
        raise CheckpointContractError(str(exc)) from exc
    if listed != sorted(f"{r['receipt_sha256']}.json" for r in by_cell.values()):
        raise CheckpointContractError("receipt directory differs from the manifest receipts")
    models: dict[Cell, lds.PerTargetContextDeepSetsMLP] = {}
    bindings: list[Binding] = []
    for cell in EXPECTED_CELLS:
        record = by_cell[cell]
        try:
            verify_fit_receipt(receipts, record, cell, campaign=campaign)
            state, digest = load_checkpoint(
                directory / f"{record['checkpoint_sha256']}.pt", record, cell, campaign=campaign
            )
        except (PermissionError, OSError, ValueError) as exc:
            if isinstance(exc, CheckpointContractError):
                raise
            raise CheckpointContractError(f"checkpoint unreadable or aliased: {exc}") from exc
        model = lds.PerTargetContextDeepSetsMLP(cell[0])
        model.load_state_dict(cast(dict[str, Tensor], state), strict=True)
        model.eval().requires_grad_(False)
        models[cell] = model
        bindings.append(
            Binding(
                cell,
                digest,
                cast(str, record["configuration_sha256"]),
                cast(int, record["selected_step"]),
                state_sha256(model),
            )
        )
    result = FrozenModelSet(manifest_sha, models, tuple(bindings))
    result.assert_unchanged()
    return result
