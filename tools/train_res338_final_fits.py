"""Run only the frozen research-only final-role DeepSets fits."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import resource
import shutil
import stat
import subprocess
import sys
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import numpy as np
import research_baseline_v1 as research_run
import research_population_v1 as research
import torch
from numpy.typing import NDArray
from res338_colab_gpu_probe import gpu_memory_fingerprint
from torch import Tensor

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    empirical_experiment_plan as experiment_plan,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    streaming_population_producer_v1 as population,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.evaluation_population import (
    truth_mask_sha256,
    truth_sha256,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.learned_deepsets import (
    FUTURE_SAMPLES,
    HEAD_FEATURE_LAYOUT,
    INFORMATION_REGIMES,
    INPUT_DIMS,
    SEEDS,
    TARGET_PLAYERS,
    TARGET_REPRESENTATIONS,
    TRACK_POOLING,
    CheckpointSelection,
    InformationRegime,
    ModelInputs,
    PerTargetContextDeepSetsMLP,
    TargetRepresentation,
    build_scene_feature_payload,
    collate_feature_payloads,
    configure_deterministic_cpu,
    equal_match_mean,
    fit_failure_category,
    load_checkpoint_verified,
    make_optimizer,
    masked_scene_ade_loss,
    physical_metrics,
    retry_allowed,
    sample_scene_index,
    save_checkpoint_atomically,
    seed_training,
    validate_feature_payload,
    validate_truth_scene,
    validation_due,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction.prospective_protocol import (
    load_prospective_protocol_v2,
)
from fpdbench.data_sources import protected_skillcorner as source
from fpdbench.data_states.skillcorner import (
    iter_skillcorner_5hz_v2,
)
from fpdbench.data_states.skillcorner import (
    load_manifest_v2 as load_data_state_v2,
)
from fpdbench.eligibility.skillcorner import (
    load_manifest_v2 as load_eligibility_v2,
)
from fpdbench.eligibility.skillcorner import (
    skillcorner_period_ranges,
)

RESEARCH_MANIFEST_SHA256 = research_run.MANIFEST
RESEARCH_SCHEMA = research.SCHEMA
RESEARCH_VERSION = research.VERSION
MODEL_ID = "per_target_context_deepsets_mlp_v1"
BATCH_SIZE = 128
VALIDATION_CADENCE = 100
MAX_STEPS = 5000
PATIENCE = 10
FIT_CPU_BUDGET_SECONDS = 3600.0
CAMPAIGN_PREPARATION_CPU_BUDGET_SECONDS = 19.5 * 3600
CAMPAIGN_CPU_BUDGET_SECONDS = 292.5 * 3600
CAMPAIGN_WALL_BUDGET_SECONDS = 336 * 3600
MAX_WORKER_RSS_BYTES = 16 * 1024**3
GPU_FIT_WALL_BUDGET_SECONDS = 3600.0
GPU_RETRY_WALL_BUDGET_SECONDS = 0.25 * 3600
GPU_CAMPAIGN_BUDGET_SECONDS = 22.5 * 3600
MAX_GPU_ALLOCATED_BYTES = 8 * 1024**3
DEFAULT_PRIVATE_DISK_RESERVE_BYTES = 1024**3
GPU_PRIVATE_DISK_RESERVE_BYTES = 8 * 1024**3
GPU_TORCH_VERSION = "2.6.0+cu124"
GPU_CUDA_VERSION = "12.4"
REPO = Path(__file__).resolve().parents[1]
SOURCE_ROOT_DEFAULT = Path("/srv/fpdbench-private/source/skillcorner-v1")
RESEARCH_ROOT_DEFAULT = Path("/srv/fpdbench-private/evidence/research-population-v1-e9850a7")
TOY_PREFLIGHT_PATH = Path(
    "/srv/fpdbench-private/evidence/res338-toy-preflight-v2/toy-preflight.json"
)
GPU_EXECUTION_AMENDMENT = REPO / "docs/res338-colab-gpu-execution-amendment.md"
PRIVATE_CLOUD_AMENDMENT = REPO / "docs/res338-private-cloud-research-amendment.md"

_FEATURE_ARRAYS = (
    "target_history",
    "history_team_tracks",
    "history_team_mask",
    "history_ball",
    "target_side",
    "future_ball",
    "future_opponent_tracks",
    "future_opponent_mask",
)
_LABEL_ARRAYS = ("target_absolute_xy", "target_displacement", "target_mask", "scoreable")


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _training_environment_sha256(runtime: Mapping[str, object]) -> str:
    stable = dict(runtime)
    stable["cpu_affinity"] = len(cast(list[int], runtime["cpu_affinity"]))
    accelerator = runtime.get("accelerator")
    if isinstance(accelerator, Mapping):
        stable_accelerator = dict(accelerator)
        stable_accelerator.pop("available_memory_bytes_at_start", None)
        stable_accelerator.pop("available_memory_bytes", None)
        stable_accelerator.pop("torch_available_memory_bytes", None)
        stable["accelerator"] = stable_accelerator
    return hashlib.sha256(_canonical(stable)).hexdigest()


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError("content identity requires an exclusive regular file")
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
        after = os.fstat(stream.fileno())
        if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise ValueError("file changed while computing its content identity")
    return digest.hexdigest()


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_write(path: Path, payload: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    _fsync_directory(path.parent)


def _atomic_json(path: Path, value: object) -> None:
    _atomic_write(path, _canonical(value))


def _read_pinned_manifest(research_root: Path) -> dict[str, object]:
    payload = read_private_file(research_root / "research-admission.json", RESEARCH_MANIFEST_SHA256)
    if hashlib.sha256(payload).hexdigest() != RESEARCH_MANIFEST_SHA256:
        raise ValueError("private research manifest SHA-256 mismatch")
    manifest = json.loads(payload, object_pairs_hook=_unique_json_object)
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_id") != RESEARCH_SCHEMA
        or manifest.get("schema_version") != RESEARCH_VERSION
        or manifest.get("status") != "RESEARCH_RECONCILED"
        or manifest.get("protected_status") != "NOT_QUALIFIED"
    ):
        raise ValueError("research-only admission contract or status differs")
    return cast(dict[str, object], manifest)


def _read_private_bytes(path: Path) -> bytes:
    with source.private_directory(path.parent) as root_fd:
        with source._open_file(root_fd, path.name) as stream:
            return stream.read()


def read_private_file(path: Path, expected_sha256: str) -> bytes:
    """Read one exclusive 0600 file under a 0700, non-Git private directory."""
    payload = _read_private_bytes(path)
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise ValueError("private file SHA-256 mismatch")
    return payload


def _read_private_json(path: Path) -> dict[str, object]:
    value = json.loads(_read_private_bytes(path), object_pairs_hook=_unique_json_object)
    if not isinstance(value, dict):
        raise ValueError("private record must be a JSON object")
    return cast(dict[str, object], value)


def _cgroup_oom_kill_count() -> int | None:
    try:
        cgroup_path = next(
            row.split(":", maxsplit=2)[2]
            for row in Path("/proc/self/cgroup").read_text(encoding="ascii").splitlines()
            if row.startswith("0::")
        )
        parts = Path(cgroup_path.lstrip("/")).parts
        if any(part in {"", ".", ".."} for part in parts):
            return None
        events_path = Path("/sys/fs/cgroup").joinpath(*parts) / "memory.events"
        for line in events_path.read_text(encoding="ascii").splitlines():
            key, raw = line.split()
            if key == "oom_kill":
                return int(raw)
    except (OSError, ValueError):
        return None
    return None


def _frozen_split_and_authorities() -> tuple[
    dict[str, object], dict[str, object], dict[str, list[str]]
]:
    plan = experiment_plan.load_empirical_experiment_plan_v2()
    protocol = load_prospective_protocol_v2()
    experiment_plan.validate_empirical_experiment_plan_v2_document(plan, protocol)
    split = cast(dict[str, object], experiment_plan.protocol_split_v2()["roles"])
    roles = {
        role: sorted(cast(list[str], split[role]))
        for role in ("training", "validation", "evaluation")
    }
    state = load_data_state_v2()
    eligibility = load_eligibility_v2()
    if (
        state["data_state_hash"]
        != "1ecf355b3e6e2f04967e8363c1fdecc7f40707a7dda9966ebee1b3d90e97e671"
        or eligibility["policy_hash"]
        != "ed1cdc20ca7a93040fd4aabc91655819c5c4b8c58021c6540c6aaea325dafa11"
    ):
        raise ValueError("v2 measurement or eligibility identity differs")
    return plan, protocol, roles


def verify_research_population(
    research_root: Path,
    source_root: Path,
    plan: Mapping[str, object],
    roles: Mapping[str, Sequence[str]],
) -> tuple[dict[str, object], dict[str, object]]:
    pinned = _read_pinned_manifest(research_root)
    # This existing independent reconciliation rehashes both 20-match outputs and
    # all 81 pinned source files; it never constructs learned-model features.
    reconciled = research_run.verify(research_root, source_root)
    if hashlib.sha256((research_root / "research-admission.json").read_bytes()).hexdigest() != (
        RESEARCH_MANIFEST_SHA256
    ):
        raise ValueError("research manifest changed during reconciliation")
    if reconciled != pinned:
        raise ValueError("research manifest changed during reconciliation")
    source_inventory = cast(
        list[dict[str, object]],
        json.loads(
            read_private_file(
                research_root / "source-inventory.json",
                str(reconciled["source_inventory_sha256"]),
            ),
            object_pairs_hook=_unique_json_object,
        ),
    )
    independent_source = cast(
        dict[str, object],
        json.loads(
            read_private_file(
                research_root / "independent-source.json",
                str(reconciled["independent_source_sha256"]),
            ),
            object_pairs_hook=_unique_json_object,
        ),
    )
    independent_files = cast(list[dict[str, object]], independent_source["source_files"])
    source_rows = {
        (str(item["path"]), int(item["bytes"]), str(item["sha256"])) for item in source_inventory
    }
    independent_rows = {
        (str(item["path"]), int(item["bytes"]), str(item["sha256"])) for item in independent_files
    }
    if len(source_rows) != 81 or source_rows != independent_rows:
        raise ValueError("independent source inventory does not match the pinned 81-file set")
    artifacts = cast(dict[str, dict[str, object]], reconciled["artifacts"])
    if len(artifacts) != 20 or any(
        item["producer_sha256"] != item["verifier_sha256"]
        or item["producer_summary_sha256"] != item["verifier_summary_sha256"]
        for item in artifacts.values()
    ):
        raise ValueError("the two independent 20-match outputs have mismatches")
    actual_roles = {
        role: sorted(
            match_id
            for match_id, item in cast(
                dict[str, dict[str, object]], reconciled["per_match"]
            ).items()
            if item["role"] == role
        )
        for role in ("training", "validation", "evaluation")
    }
    if actual_roles != {role: sorted(values) for role, values in roles.items()}:
        raise ValueError("research population roles differ from the frozen v2 split")
    if (
        len(actual_roles["training"]) != 12
        or len(actual_roles["validation"]) != 4
        or len(actual_roles["evaluation"]) != 4
    ):
        raise ValueError("research population does not contain the exact frozen 12/4/4 roles")
    if reconciled["source_release_hash"] != plan["population_authority"]["source_release_hash"]:
        raise ValueError("source release identity differs from the v2 plan")
    if (
        reconciled["source_population_hash"]
        != plan["population_authority"]["source_population_hash"]
    ):
        raise ValueError("source population identity differs from the v2 plan")
    return reconciled, {
        "source_files_rehashed": len(source_rows),
        "independent_source_files_rehashed": len(independent_rows),
        "producer_outputs_rehashed": len(artifacts),
        "verifier_outputs_rehashed": len(artifacts),
        "producer_verifier_mismatches": 0,
        "exact_role_assignment_match": True,
        "role_counts": {role: len(matches) for role, matches in actual_roles.items()},
    }


def verify_training_validation_population(
    research_root: Path,
    source_root: Path,
    reference_path: Path,
    reference_sha256: str,
    plan: Mapping[str, object],
    roles: Mapping[str, Sequence[str]],
) -> tuple[dict[str, object], dict[str, object]]:
    reference_bytes = read_private_file(reference_path, reference_sha256)
    reference = cast(
        dict[str, object],
        json.loads(reference_bytes, object_pairs_hook=_unique_json_object),
    )
    expected_roles = {role: sorted(roles[role]) for role in ("training", "validation")}
    matches = cast(list[str], reference["source_match_order"])
    selected = set(expected_roles["training"]) | set(expected_roles["validation"])
    preloaded_cache_identities = cast(
        dict[str, dict[str, object]], reference.get("preloaded_cache_identities", {})
    )
    if (
        reference.get("schema_id") != "fpdbench.res338.training-validation-reference"
        or reference.get("parent_research_manifest_sha256") != RESEARCH_MANIFEST_SHA256
        or reference.get("source_release_hash")
        != plan["population_authority"]["source_release_hash"]
        or reference.get("source_population_hash")
        != plan["population_authority"]["source_population_hash"]
        or reference.get("roles") != expected_roles
        or set(matches) != selected
        or len(matches) != 16
        or len(preloaded_cache_identities) != 6
        or not set(preloaded_cache_identities).issubset(set(expected_roles["training"]))
        or set(reference) & {"evaluation", "evaluation_matches", "evaluation_labels"}
    ):
        raise ValueError("training-validation reference differs from the ratified 12/4 scope")
    reference_sha = hashlib.sha256(reference_bytes).hexdigest()

    source_authority = source._authority()
    if (
        reference.get("source_commit")
        != cast(dict[str, object], source_authority["upstream"])["pinned_commit"]
    ):
        raise ValueError("training-validation source commit differs from the pinned release")
    source_paths = {
        str(record["repository_path"])
        for record in cast(list[dict[str, object]], reference["source_manifest"])
    }
    if (
        len(source_paths) != 64
        or source_paths
        != {str(item["path"]) for item in cast(list[dict[str, object]], reference["source_files"])}
        or any(
            len(Path(path).parts) != 4 or Path(path).parts[2] not in selected
            for path in source_paths
        )
        or reference.get("source_commit")
        != cast(dict[str, object], source_authority["upstream"])["pinned_commit"]
    ):
        raise ValueError("training-validation source projection includes an unexpected source")
    records = [
        record
        for record in source._records(source_authority)
        if any(
            str(record["repository_path"]).startswith(f"data/matches/{match}/")
            for match in selected
        )
    ]
    if len(records) != 64:
        raise ValueError("Colab source authority must contain only 64 training/validation files")
    with source.private_directory(source_root) as root_fd:
        source_inventory = source._verify_sources(root_fd, records)
    if source_inventory != reference["source_files"]:
        raise ValueError("Colab-pinned source bytes differ from the projected source identity")

    admission_bytes = _read_private_bytes(research_root / "research-admission.json")
    admission_sha = hashlib.sha256(admission_bytes).hexdigest()
    admission = cast(
        dict[str, object],
        json.loads(admission_bytes, object_pairs_hook=_unique_json_object),
    )
    if (
        admission.get("schema_id") != RESEARCH_SCHEMA
        or admission.get("schema_version") != RESEARCH_VERSION
        or admission.get("status") != "RESEARCH_RECONCILED"
        or admission.get("protected_status") != "NOT_QUALIFIED"
        or admission.get("execution_scope") != "training-validation"
        or admission.get("parent_research_manifest_sha256") != RESEARCH_MANIFEST_SHA256
        or admission.get("source_release_hash") != reference["source_release_hash"]
        or admission.get("source_population_hash") != reference["source_population_hash"]
        or set(cast(dict[str, object], admission["per_match"])) != selected
        or set(cast(dict[str, object], admission["artifacts"])) != selected
        or admission.get("source_match_order") != matches
        or "evaluation" in cast(dict[str, object], admission["roles"])
    ):
        raise ValueError("Colab research admission is outside the training/validation scope")
    expected_role_names = {f"{match}.jsonl" for match in selected} | {
        f"{match}.summary.json" for match in selected
    }
    for directory_name in ("producer", "verifier"):
        directory = research_root / directory_name
        if {item.name for item in directory.iterdir()} != expected_role_names:
            raise ValueError("Colab population outputs contain missing or out-of-scope matches")
    if {item.name for item in (research_root / "inputs").iterdir()} != selected:
        raise ValueError("Colab canonical inputs contain missing or out-of-scope matches")
    if {
        item.name.removesuffix("-lineage.json")
        for item in (research_root / "normalization").iterdir()
    } != selected:
        raise ValueError("Colab normalization inputs contain missing or out-of-scope matches")

    inventory_bytes = read_private_file(
        research_root / "source-inventory.json", str(admission["source_inventory_sha256"])
    )
    if (
        json.loads(inventory_bytes, object_pairs_hook=_unique_json_object)
        != reference["source_files"]
    ):
        raise ValueError("Colab research source inventory differs from its reference")
    independent_bytes = read_private_file(
        research_root / "independent-source.json", str(admission["independent_source_sha256"])
    )
    independent = cast(
        dict[str, object],
        json.loads(independent_bytes, object_pairs_hook=_unique_json_object),
    )
    reference_independent = cast(dict[str, object], reference["independent_source"])
    if (
        independent.get("scope") != "training-validation"
        or set(cast(list[str], independent["match_ids"])) != selected
        or independent.get("source_files") != reference_independent["source_files"]
        or sorted(
            cast(list[dict[str, object]], independent["normalization_receipts"]),
            key=lambda item: str(item["match_id"]),
        )
        != sorted(
            cast(list[dict[str, object]], reference_independent["normalization_receipts"]),
            key=lambda item: str(item["match_id"]),
        )
    ):
        raise ValueError("Colab source or phase normalization differs from the private reference")

    source_matches = cast(list[dict[str, object]], source_authority["available_matches"])
    tracking_hashes = {
        str(item["match_id"]): str(
            next(file["lfs_oid_sha256"] for file in item["files"] if "lfs_oid_sha256" in file)
        )
        for item in source_matches
        if str(item["match_id"]) in selected
    }
    if set(tracking_hashes) != selected:
        raise ValueError("pinned tracking identities do not cover the training/validation scope")
    reconciled = research.reconcile(
        research_root / "producer", research_root / "verifier", matches, tracking_hashes
    )
    if (
        reconciled["per_match"] != reference["per_match"]
        or reconciled["artifacts"] != reference["artifacts"]
        or admission["per_match"] != reconciled["per_match"]
        or admission["artifacts"] != reconciled["artifacts"]
    ):
        raise ValueError(
            "Colab producer/verifier outputs differ from the frozen 16-match projection"
        )
    admission["preloaded_cache_identities"] = reference.get("preloaded_cache_identities", {})

    return admission, {
        "source_files_rehashed": len(source_inventory),
        "independent_source_files_rehashed": len(source_inventory),
        "producer_outputs_rehashed": len(matches),
        "verifier_outputs_rehashed": len(matches),
        "producer_verifier_mismatches": 0,
        "exact_role_assignment_match": True,
        "scope": "training-validation",
        "role_counts": {role: len(values) for role, values in expected_roles.items()},
        "reference_manifest_sha256": reference_sha,
        "projected_research_admission_sha256": admission_sha,
    }


def _colab_session_identity() -> dict[str, str | None]:
    return {
        "session_name": os.environ.get("RES338_COLAB_SESSION_NAME"),
        "session_id": os.environ.get("RES338_COLAB_SESSION_ID"),
        "colab_release_tag": os.environ.get("COLAB_RELEASE_TAG"),
    }


def _validate_training_runtime(device: str = "cpu") -> dict[str, object]:
    if sys.version_info[:3] != (3, 12, 8):
        raise RuntimeError(f"required Python 3.12.8, found {sys.version.split()[0]}")
    if np.__version__ != "2.2.4":
        raise RuntimeError(f"required NumPy 2.2.4, found {np.__version__}")
    if platform.machine().lower() not in {"x86_64", "amd64"}:
        raise RuntimeError("the frozen worker requires x86_64")
    if len(os.sched_getaffinity(0)) != 1:
        raise RuntimeError("launch the frozen worker on exactly one CPU core")
    if device == "cuda" and os.environ.get("CUBLAS_WORKSPACE_CONFIG") != ":4096:8":
        raise RuntimeError("CUBLAS_WORKSPACE_CONFIG must be set before importing PyTorch")
    configure_deterministic_cpu()
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.set_float32_matmul_precision("highest")
    if (
        torch.get_num_threads() != 1
        or torch.get_num_interop_threads() != 1
        or not torch.are_deterministic_algorithms_enabled()
        or torch.backends.cudnn.benchmark
        or not torch.backends.cudnn.deterministic
        or torch.backends.cuda.matmul.allow_tf32
        or torch.backends.cudnn.allow_tf32
        or torch.get_float32_matmul_precision() != "highest"
        or torch.get_default_dtype() is not torch.float32
    ):
        raise RuntimeError("the frozen deterministic numerical settings could not be established")
    runtime: dict[str, object] = {
        "python": sys.version,
        "python_executable_sha256": _sha256_file(Path(sys.executable).resolve()),
        "numpy": np.__version__,
        "torch": torch.__version__,
        "torch_cuda": torch.version.cuda,
        "torch_num_threads": torch.get_num_threads(),
        "torch_num_interop_threads": torch.get_num_interop_threads(),
        "deterministic_algorithms": torch.are_deterministic_algorithms_enabled(),
        "cpu_affinity": sorted(os.sched_getaffinity(0)),
        "machine": platform.machine(),
        "platform": platform.platform(),
        "torch_build": torch.__config__.show(),
        "cublas_workspace_config": os.environ.get("CUBLAS_WORKSPACE_CONFIG"),
        "cudnn_deterministic": torch.backends.cudnn.deterministic,
        "cudnn_benchmark": torch.backends.cudnn.benchmark,
        "matmul_tf32": torch.backends.cuda.matmul.allow_tf32,
        "cudnn_tf32": torch.backends.cudnn.allow_tf32,
        "float32_matmul_precision": torch.get_float32_matmul_precision(),
        "default_dtype": str(torch.get_default_dtype()),
        "device": device,
        "packages": sorted(
            (distribution.metadata["Name"], distribution.version)
            for distribution in importlib.metadata.distributions()
        ),
    }
    if device == "cpu":
        if torch.__version__ != "2.6.0+cpu" or torch.version.cuda is not None:
            raise RuntimeError(f"required PyTorch 2.6.0+cpu, found {torch.__version__}")
        if torch.cuda.is_available():
            raise RuntimeError("CPU execution refuses an available CUDA device")
        runtime["accelerator"] = None
    elif device == "cuda":
        session_identity = _colab_session_identity()
        if not session_identity["session_name"] or not session_identity["session_id"]:
            raise RuntimeError("Colab session name and assigned session ID must be recorded")
        if torch.__version__ != GPU_TORCH_VERSION or torch.version.cuda != GPU_CUDA_VERSION:
            raise RuntimeError(
                f"required PyTorch {GPU_TORCH_VERSION} with CUDA {GPU_CUDA_VERSION}, "
                f"found {torch.__version__} with CUDA {torch.version.cuda}"
            )
        if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
            raise RuntimeError("CUDA execution requires exactly one visible NVIDIA GPU")
        if shutil.which("nvidia-smi") is None:
            raise RuntimeError("nvidia-smi is required to record the NVIDIA driver")
        torch.cuda.init()
        gpu_name = torch.cuda.get_device_name(0)
        properties = torch.cuda.get_device_properties(0)
        free_bytes, total_bytes = torch.cuda.mem_get_info(0)
        rows = (
            subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total,memory.free,driver_version",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
                timeout=10,
            )
            .strip()
            .splitlines()
        )
        if len(rows) != 1:
            raise RuntimeError("the Colab worker must see exactly one NVIDIA GPU")
        reported_name, memory_mib, free_mib, driver_version = (
            item.strip() for item in rows[0].split(",")
        )
        if reported_name != gpu_name or total_bytes != int(properties.total_memory):
            raise RuntimeError("nvidia-smi and PyTorch disagree on the assigned GPU")
        runtime["accelerator"] = {
            "name": gpu_name,
            "capability": list(torch.cuda.get_device_capability(0)),
            **gpu_memory_fingerprint(
                int(properties.total_memory), int(free_bytes), int(memory_mib), int(free_mib)
            ),
            "available_memory_bytes_at_start": int(free_bytes),
            "driver_version": driver_version,
            "peak_allocated_budget_bytes": MAX_GPU_ALLOCATED_BYTES,
        }
    else:
        raise ValueError("device must be cpu or cuda")
    return runtime


def _available_memory() -> tuple[int, int]:
    values: dict[str, int] = {}
    with Path("/proc/meminfo").open(encoding="ascii") as stream:
        for line in stream:
            name, raw = line.split(":", maxsplit=1)
            if name in {"MemTotal", "MemAvailable"}:
                values[name] = int(raw.split()[0]) * 1024
    return values["MemTotal"], values["MemAvailable"]


def _resource_fingerprint(output_root: Path) -> dict[str, int | str | None]:
    total, available = _available_memory()
    disk = shutil.disk_usage(output_root)
    cpu_model = "unknown"
    with Path("/proc/cpuinfo").open(encoding="ascii") as stream:
        for line in stream:
            if line.startswith("model name"):
                cpu_model = line.split(":", maxsplit=1)[1].strip()
                break
    cgroup_limit = None
    cgroup_path = next(
        (
            row.split(":", maxsplit=2)[2]
            for row in Path("/proc/self/cgroup").read_text(encoding="ascii").splitlines()
            if row.startswith("0::")
        ),
        None,
    )
    if cgroup_path is not None:
        limit_path = Path("/sys/fs/cgroup") / cgroup_path.lstrip("/") / "memory.max"
        try:
            raw_limit = limit_path.read_text(encoding="ascii").strip()
            cgroup_limit = None if raw_limit == "max" else int(raw_limit)
        except (OSError, ValueError):
            cgroup_limit = None
    return {
        "cpu_count_logical": os.cpu_count() or 0,
        "cpu_model": cpu_model,
        "memory_total_bytes": total,
        "memory_available_bytes": available,
        "cgroup_memory_limit_bytes": cgroup_limit,
        "worker_memory_budget_bytes": MAX_WORKER_RSS_BYTES,
        "effective_worker_memory_limit_bytes": min(MAX_WORKER_RSS_BYTES, available),
        "disk_total_bytes": disk.total,
        "disk_available_bytes": disk.free,
        "disk_filesystem": subprocess.check_output(
            ["/usr/bin/stat", "-f", "-c", "%T", str(output_root)], text=True
        ).strip(),
    }


def _current_rss_bytes() -> int:
    with Path("/proc/self/status").open(encoding="ascii") as stream:
        for line in stream:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    raise RuntimeError("worker RSS is unavailable")


def _refresh_resource_totals(
    ledger: dict[str, object],
    freeze: Mapping[str, object],
    campaign_wall_start: float,
    campaign_cpu_start: float,
) -> None:
    runs = cast(list[dict[str, object]], ledger["runs"])
    attempts = cast(dict[str, list[dict[str, object]]], ledger["attempt_history"])
    prep_cpu = float(freeze["preparation_cpu_seconds"]) + float(
        ledger.get("resume_preparation_cpu_seconds", 0.0)
    )
    fit_cpu = math.fsum(float(item["fit_cpu_seconds"]) for item in runs)
    fit_gpu_wall = math.fsum(float(item.get("gpu_wall_seconds") or 0.0) for item in runs)
    fit_gpu_wall = math.fsum(float(item.get("gpu_wall_seconds") or 0.0) for item in runs)
    unknown_attempts = sum(
        entry.get("cpu_seconds") == "not_observable_after_worker_interruption"
        for entries in attempts.values()
        for entry in entries
    )
    ledger["recorded_preparation_cpu_seconds"] = prep_cpu
    ledger["recorded_fit_cpu_seconds"] = fit_cpu
    ledger["recorded_total_cpu_seconds"] = prep_cpu + fit_cpu
    ledger["recorded_gpu_wall_seconds"] = fit_gpu_wall
    gpu_started_at = ledger.get("gpu_training_started_at_utc")
    if gpu_started_at:
        ledger["campaign_gpu_elapsed_wall_seconds"] = round(
            max(
                0.0,
                (datetime.now(UTC) - datetime.fromisoformat(str(gpu_started_at))).total_seconds(),
            ),
            6,
        )
    ledger["recorded_gpu_wall_seconds"] = fit_gpu_wall
    gpu_started_at = ledger.get("gpu_training_started_at_utc")
    if gpu_started_at:
        ledger["campaign_gpu_elapsed_wall_seconds"] = round(
            max(
                0.0,
                (datetime.now(UTC) - datetime.fromisoformat(str(gpu_started_at))).total_seconds(),
            ),
            6,
        )
    ledger["interrupted_attempt_cpu_unknown_count"] = unknown_attempts
    ledger["campaign_cpu_seconds_this_process"] = round(time.process_time() - campaign_cpu_start, 6)
    ledger["campaign_wall_seconds"] = round(time.monotonic() - campaign_wall_start, 6)


def _metadata_rosters(metadata: Mapping[str, object]) -> tuple[list[int], list[int]]:
    home = cast(Mapping[str, object], metadata["home_team"])
    away = cast(Mapping[str, object], metadata["away_team"])
    home_id, away_id = int(home["id"]), int(away["id"])
    home_players: list[int] = []
    away_players: list[int] = []
    for value in cast(list[Mapping[str, object]], metadata["players"]):
        player_id, team_id = int(value["id"]), int(value["team_id"])
        if team_id == home_id:
            home_players.append(player_id)
        elif team_id == away_id:
            away_players.append(player_id)
        else:
            raise ValueError("match metadata contains a player outside the two frozen teams")
    if not home_players or not away_players:
        raise ValueError("match metadata must contain both player rosters")
    return sorted(home_players), sorted(away_players)


def _create_array(
    directory: Path, name: str, dtype: np.dtype[object], shape: tuple[int, ...]
) -> np.memmap:
    return np.lib.format.open_memmap(directory / f"{name}.npy", mode="w+", dtype=dtype, shape=shape)


def _close_arrays(arrays: Mapping[str, np.memmap]) -> None:
    for array in arrays.values():
        array.flush()
        mmap = getattr(array, "_mmap", None)
        if mmap is not None:
            mmap.close()


def _truth_identity(scene: Mapping[str, object]) -> dict[str, object]:
    absolute = cast(list[list[object]], scene["absolute_xy"])
    displacement = cast(list[list[object]], scene["origin_relative_displacement"])
    if (
        truth_sha256(absolute, target_representation="absolute_xy")
        != scene["absolute_xy_truth_sha256"]
    ):
        raise ValueError("absolute target digest differs from the locked research panel")
    if (
        truth_sha256(displacement, target_representation="origin_relative_displacement")
        != scene["displacement_truth_sha256"]
    ):
        raise ValueError("displacement target digest differs from the locked research panel")
    if (
        truth_mask_sha256(absolute) != scene["truth_mask_sha256"]
        or truth_mask_sha256(displacement) != scene["truth_mask_sha256"]
    ):
        raise ValueError("the two target representations do not share the locked mask")
    return {
        "scene_id": scene["scene_id"],
        "player_ids": scene["player_ids"],
        "absolute_xy_truth_sha256": scene["absolute_xy_truth_sha256"],
        "displacement_truth_sha256": scene["displacement_truth_sha256"],
        "truth_mask_sha256": scene["truth_mask_sha256"],
    }


def _write_target_labels(
    arrays: Mapping[str, np.memmap], index: int, lane: int, scene: Mapping[str, object]
) -> None:
    absolute, displacement, mask = validate_truth_scene(scene)
    cast(np.memmap, arrays["target_absolute_xy"])[index, lane] = absolute
    cast(np.memmap, arrays["target_displacement"])[index, lane] = displacement
    cast(np.memmap, arrays["target_mask"])[index, lane] = mask
    cast(np.memmap, arrays["scoreable"])[index, lane] = bool(scene["scoreable"])


def _build_match_cache(
    research_root: Path,
    cache_root: Path,
    match_id: str,
    role: str,
    research_manifest: Mapping[str, object],
    disk_reserve_bytes: int = DEFAULT_PRIVATE_DISK_RESERVE_BYTES,
) -> dict[str, object]:
    match_counts = cast(dict[str, object], research_manifest["per_match"])[match_id]
    expected_windows = int(cast(dict[str, object], match_counts["counts"])["scoreable_windows"])
    if expected_windows <= 0:
        raise ValueError("every training and validation match needs scoreable windows")
    input_dir = research_root / "inputs" / match_id
    metadata_path = input_dir / "metadata.json"
    receipt_bytes = read_private_file(
        research_root / "independent-source.json",
        str(research_manifest["independent_source_sha256"]),
    )
    receipt = cast(
        dict[str, object], json.loads(receipt_bytes, object_pairs_hook=_unique_json_object)
    )
    normalization = cast(list[dict[str, object]], receipt["normalization_receipts"])
    metadata_identity = next(item for item in normalization if item["match_id"] == match_id)
    metadata_bytes = read_private_file(metadata_path, str(metadata_identity["metadata_sha256"]))
    metadata = cast(
        dict[str, object], json.loads(metadata_bytes, object_pairs_hook=_unique_json_object)
    )
    home_players, away_players = _metadata_rosters(metadata)
    pool_size = max(len(home_players), len(away_players))
    bounds, errors = skillcorner_period_ranges(metadata)
    if errors:
        raise ValueError("frozen match period bounds are invalid")

    role_directory = cache_root / role
    role_directory.mkdir(mode=0o700, exist_ok=True)
    directory = role_directory / match_id
    directory.mkdir(mode=0o700)
    estimated_bytes_per_window = (
        2 * pool_size * 78 * 4
        + 2 * pool_size * 45 * 4
        + 2 * TARGET_PLAYERS * 78 * 4
        + 2 * 2 * FUTURE_SAMPLES * TARGET_PLAYERS * 2 * 8
        + 2 * FUTURE_SAMPLES * TARGET_PLAYERS
        + 4096
    )
    estimated_cache_bytes = expected_windows * estimated_bytes_per_window
    if shutil.disk_usage(cache_root).free < estimated_cache_bytes + disk_reserve_bytes:
        raise OSError("insufficient private disk for the complete frozen feature cache")

    shapes: dict[str, tuple[int, ...]] = {
        "target_history": (expected_windows, 2, TARGET_PLAYERS, 78),
        "history_team_tracks": (expected_windows, 2, pool_size, 78),
        "history_team_mask": (expected_windows, 2, pool_size),
        "history_ball": (expected_windows, 78),
        "target_side": (expected_windows, 2),
        "future_ball": (expected_windows, 45),
        "future_opponent_tracks": (expected_windows, 2, pool_size, 45),
        "future_opponent_mask": (expected_windows, 2, pool_size),
        "target_absolute_xy": (expected_windows, 2, TARGET_PLAYERS, FUTURE_SAMPLES, 2),
        "target_displacement": (expected_windows, 2, TARGET_PLAYERS, FUTURE_SAMPLES, 2),
        "target_mask": (expected_windows, 2, TARGET_PLAYERS, FUTURE_SAMPLES),
        "scoreable": (expected_windows, 2),
    }
    dtypes: dict[str, np.dtype[object]] = {
        **{
            name: np.dtype(np.float32)
            for name in _FEATURE_ARRAYS
            if name not in {"history_team_mask", "future_opponent_mask"}
        },
        "history_team_mask": np.dtype(np.bool_),
        "future_opponent_mask": np.dtype(np.bool_),
        "target_absolute_xy": np.dtype(np.float64),
        "target_displacement": np.dtype(np.float64),
        "target_mask": np.dtype(np.bool_),
        "scoreable": np.dtype(np.bool_),
    }
    arrays = {
        name: _create_array(directory, name, dtypes[name], shape) for name, shape in shapes.items()
    }
    roles = cast(dict[str, dict[str, object]], research_manifest["per_match"])
    if roles[match_id]["role"] != role:
        raise ValueError("match cache role differs from the frozen research manifest")

    summary_identity = cast(dict[str, object], research_manifest["artifacts"])[match_id]
    summary_bytes = read_private_file(
        research_root / "producer" / f"{match_id}.summary.json",
        str(summary_identity["producer_summary_sha256"]),
    )
    summary = cast(
        dict[str, object], json.loads(summary_bytes, object_pairs_hook=_unique_json_object)
    )
    expected_tracking_sha256 = str(summary["tracking_sha256"])
    population_digest = hashlib.sha256()
    target_identity_digest = hashlib.sha256()
    window_identity_digest = hashlib.sha256()
    feature_window_count = scoreable_scene_count = eligible_window_count = 0
    row_counts: dict[str, object] = {}
    source_release = str(source._authority()["source_release_id"])
    with (
        source.private_directory(research_root / "producer") as producer_fd,
        source._open_file(producer_fd, f"{match_id}.jsonl") as population_stream,
        source.private_directory(input_dir) as input_fd,
    ):
        samples = iter_skillcorner_5hz_v2(
            source._rows(input_fd, "tracking.jsonl", row_counts),
            metadata,
            source_release_id=source_release,
        )
        for (period, frame, origin), support in population._population_events(samples, bounds):
            line = population_stream.readline()
            if not line:
                raise ValueError("research population stream ended before source origins")
            population_digest.update(line)
            row = cast(dict[str, object], json.loads(line, object_pairs_hook=_unique_json_object))
            if (
                row["match_id"],
                row["role"],
                row["period"],
                row["source_frame"],
                row["origin_sample_id"],
            ) != (match_id, role, period, frame, origin):
                raise ValueError("research origin identity differs from canonical source order")
            window_id = row["window_id"]
            if not window_id:
                continue
            if window_id != population.prospective_window_id_v2(match_id, origin):
                raise ValueError("research window identity differs")
            eligible_window_count += 1
            window_identity_digest.update(_canonical({"window_id": window_id}) + b"\n")
            locked_scenes = cast(list[dict[str, object]], row["scenes"])
            if len(locked_scenes) != 2:
                raise ValueError("eligible research windows must contain both directed scenes")
            actual_scenes: list[dict[str, object]] = []
            scoreable = np.zeros(2, dtype=np.bool_)
            for lane, side in enumerate(("home", "away")):
                _, actual, _ = population._scene(support, side)
                locked = locked_scenes[lane]
                if research.canonical(actual) != research.canonical(locked):
                    raise ValueError(
                        "source targets or masks differ from the locked research scene"
                    )
                _truth_identity(locked)
                target_identity_digest.update(
                    _canonical(
                        {
                            "window_id": window_id,
                            **_truth_identity(locked),
                        }
                    )
                    + b"\n"
                )
                actual_scenes.append(locked)
                scoreable[lane] = bool(locked["scoreable"])

            if not scoreable.any():
                continue
            if feature_window_count >= expected_windows:
                raise ValueError("research match has more scoreable windows than its manifest")
            index = feature_window_count
            cast(np.memmap, arrays["scoreable"])[index] = scoreable
            for lane, scene in enumerate(actual_scenes):
                _write_target_labels(arrays, index, lane, scene)
            for lane, side in enumerate(("home", "away")):
                if not scoreable[lane]:
                    continue
                target_ids = [
                    int(value) for value in cast(list[str], actual_scenes[lane]["player_ids"])
                ]
                payload = build_scene_feature_payload(
                    support,
                    target_side=side,
                    target_player_ids=target_ids,
                    home_player_ids=home_players,
                    away_player_ids=away_players,
                    regime="future_opponent_plus_ball",
                )
                if lane == 0 or not scoreable[0]:
                    cast(np.memmap, arrays["history_team_tracks"])[index] = payload[
                        "history_team_tracks"
                    ]
                    cast(np.memmap, arrays["history_team_mask"])[index] = payload[
                        "history_team_mask"
                    ]
                    cast(np.memmap, arrays["history_ball"])[index] = payload["history_ball"]
                    cast(np.memmap, arrays["future_ball"])[index] = payload["future_ball"]
                cast(np.memmap, arrays["target_history"])[index, lane] = payload["target_history"]
                cast(np.memmap, arrays["target_side"])[index, lane] = payload["target_side"]
                future_tracks = cast(NDArray[np.float32], payload["future_opponent_tracks"])
                future_mask = cast(NDArray[np.bool_], payload["future_opponent_mask"])
                cast(np.memmap, arrays["future_opponent_tracks"])[
                    index, lane, : len(future_mask)
                ] = future_tracks
                cast(np.memmap, arrays["future_opponent_mask"])[index, lane, : len(future_mask)] = (
                    future_mask
                )
                scoreable_scene_count += 1
            feature_window_count += 1

        if population_stream.read(1):
            raise ValueError("research population stream has extra origins")
    _close_arrays(arrays)
    expected_summary = cast(dict[str, object], research_manifest["artifacts"])[match_id]
    if population_digest.hexdigest() != expected_summary["producer_sha256"]:
        raise ValueError("research population changed during feature extraction")
    if row_counts.get("tracking_sha256") != expected_tracking_sha256:
        raise ValueError("staged tracking source changed during feature extraction")
    expected_counts = cast(dict[str, object], roles[match_id]["counts"])
    if (
        feature_window_count != expected_windows
        or scoreable_scene_count != expected_counts["home_scenes"] + expected_counts["away_scenes"]
    ):
        raise ValueError("feature cache coverage differs from the locked research population")
    array_sha256: dict[str, str] = {}
    for name in shapes:
        array_path = directory / f"{name}.npy"
        os.chmod(array_path, 0o400)
        array_sha256[array_path.name] = _sha256_file(array_path)
    cache_identity = {
        "schema_id": "fpdbench.res338-feature-cache",
        "schema_version": "1.0.0",
        "match_id": match_id,
        "role": role,
        "window_count": feature_window_count,
        "scoreable_scene_count": scoreable_scene_count,
        "pool_size": pool_size,
        "population_stream_sha256": population_digest.hexdigest(),
        "tracking_sha256": expected_tracking_sha256,
        "window_identity_sha256": window_identity_digest.hexdigest(),
        "target_mask_identity_sha256": target_identity_digest.hexdigest(),
        "arrays": array_sha256,
    }
    _atomic_json(directory / "cache.json", cache_identity)
    return {
        **cache_identity,
        "cache_metadata_sha256": _sha256_file(directory / "cache.json"),
    }


@dataclass(slots=True)
class MatchCache:
    match_id: str
    role: str
    directory: Path
    arrays: dict[str, NDArray[np.generic]]


def _open_match_cache(directory: Path, match_id: str, role: str) -> MatchCache:
    arrays: dict[str, NDArray[np.generic]] = {
        name: np.load(directory / f"{name}.npy", mmap_mode="r", allow_pickle=False)
        for name in (*_FEATURE_ARRAYS, *_LABEL_ARRAYS)
    }
    return MatchCache(match_id, role, directory, arrays)


def _model_inputs_to_device(inputs: ModelInputs, device: torch.device) -> ModelInputs:
    values = {
        field.name: (value.to(device) if value is not None else None)
        for field in fields(inputs)
        if (value := getattr(inputs, field.name)) is not None
    }
    return ModelInputs(**values)


def _scene_payload(
    cache: MatchCache, window_index: int, lane: int, regime: InformationRegime
) -> dict[str, NDArray[np.generic]]:
    arrays = cache.arrays
    payload: dict[str, NDArray[np.generic]] = {
        "target_history": arrays["target_history"][window_index, lane],
        "history_team_tracks": arrays["history_team_tracks"][window_index],
        "history_team_mask": arrays["history_team_mask"][window_index],
        "history_ball": arrays["history_ball"][window_index],
        "target_side": arrays["target_side"][window_index, lane],
    }
    if regime != "history_only":
        payload["future_ball"] = arrays["future_ball"][window_index]
    if regime == "future_opponent_plus_ball":
        payload["future_opponent_tracks"] = arrays["future_opponent_tracks"][window_index, lane]
        payload["future_opponent_mask"] = arrays["future_opponent_mask"][window_index, lane]
    validate_feature_payload(payload, regime)
    return payload


def _fit_match_metrics(
    model: PerTargetContextDeepSetsMLP,
    cache: MatchCache,
    regime: InformationRegime,
    representation: TargetRepresentation,
    *,
    fit_cpu_deadline: float,
    fit_gpu_wall_deadline: float | None,
    campaign_cpu_deadline: float,
    campaign_wall_deadline: float,
    campaign_gpu_wall_deadline: float | None,
    worker_memory_limit_bytes: int,
) -> dict[str, float | int]:
    selected = np.argwhere(cast(NDArray[np.bool_], cache.arrays["scoreable"]))
    if not len(selected):
        raise ValueError("validation match has no scoreable directed scenes")
    prediction = np.empty((len(selected), TARGET_PLAYERS, FUTURE_SAMPLES, 2), dtype=np.float32)
    for start in range(0, len(selected), BATCH_SIZE):
        if time.process_time() >= fit_cpu_deadline:
            raise TimeoutError("per_fit_cpu_budget_exceeded")
        if time.process_time() >= campaign_cpu_deadline:
            raise TimeoutError("campaign_training_cpu_budget_exceeded")
        if time.monotonic() >= campaign_wall_deadline:
            raise TimeoutError("campaign_wall_budget_exceeded")
        if fit_gpu_wall_deadline is not None and time.monotonic() >= fit_gpu_wall_deadline:
            raise TimeoutError("per_fit_gpu_wall_budget_exceeded")
        if (
            campaign_gpu_wall_deadline is not None
            and time.monotonic() >= campaign_gpu_wall_deadline
        ):
            raise TimeoutError("campaign_gpu_wall_budget_exceeded")
        if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024 > worker_memory_limit_bytes:
            raise MemoryError("16GiB_worker_memory_budget_exceeded")
        batch_ids = selected[start : start + BATCH_SIZE]
        payloads = [
            _scene_payload(cache, int(window), int(lane), regime) for window, lane in batch_ids
        ]
        inputs = _model_inputs_to_device(
            collate_feature_payloads(payloads, regime), next(model.parameters()).device
        )
        with torch.inference_mode():
            batch_prediction = model(inputs).cpu().numpy()
        if not np.isfinite(batch_prediction).all():
            raise FloatingPointError("validation produced a non-finite prediction")
        prediction[start : start + len(batch_ids)] = batch_prediction
    panel_name = "target_absolute_xy" if representation == "absolute_xy" else "target_displacement"
    truth = np.stack(
        [cache.arrays[panel_name][int(window), int(lane)] for window, lane in selected]
    )
    mask = np.stack(
        [cache.arrays["target_mask"][int(window), int(lane)] for window, lane in selected]
    )
    return physical_metrics(prediction, truth, mask)


def _per_fit_config(
    regime: InformationRegime,
    representation: TargetRepresentation,
    seed: int,
    train_matches: Sequence[str],
    validation_matches: Sequence[str],
    plan_sha256: str,
    protocol_sha256: str,
    device: str = "cpu",
) -> dict[str, object]:
    return {
        "model_id": MODEL_ID,
        "input_dim": INPUT_DIMS[regime],
        "information_regime": regime,
        "target_representation": representation,
        "seed": seed,
        "training_device": device,
        "plan_sha256": plan_sha256,
        "protocol_sha256": protocol_sha256,
        "train_match_ids": list(train_matches),
        "validation_match_ids": list(validation_matches),
        "batch_size_directed_scenes": BATCH_SIZE,
        "batch_sampling": (
            "uniform_match_then_uniform_scoreable_window_then_uniform_scoreable_scene_"
            "with_replacement"
        ),
        "optimizer": "AdamW",
        "learning_rate": 0.001,
        "betas": [0.9, 0.999],
        "epsilon": 1e-8,
        "weight_decay": 0.0001,
        "scheduler": None,
        "gradient_clipping": None,
        "validation_cadence_steps": VALIDATION_CADENCE,
        "patience_checks": PATIENCE,
        "maximum_steps": MAX_STEPS,
        "validation_aggregation": "equal_mean_of_four_validation_match_ADE_m",
    }


def _fit_one(
    *,
    run_root: Path,
    cache_by_match: Mapping[str, MatchCache],
    train_matches: Sequence[str],
    validation_matches: Sequence[str],
    regime: InformationRegime,
    representation: TargetRepresentation,
    seed: int,
    plan_sha256: str,
    protocol_sha256: str,
    population_sha256: str,
    target_mask_identity_sha256: str,
    environment_sha256: str,
    campaign_cpu_start: float,
    campaign_wall_start: float,
    campaign_gpu_start: float | None = None,
    device: str = "cpu",
    accelerator: Mapping[str, object] | None = None,
    attempt_number: int = 1,
    fit_cpu_budget_seconds: float = FIT_CPU_BUDGET_SECONDS,
    fit_gpu_wall_budget_seconds: float = GPU_FIT_WALL_BUDGET_SECONDS,
    worker_memory_limit_bytes: int = MAX_WORKER_RSS_BYTES,
) -> dict[str, object]:
    cell_id = f"{MODEL_ID}|{regime}|{representation}"
    run_id = f"{cell_id}|final_train|final|{seed}"
    slug = run_id.replace("|", "--")
    partial = run_root / "runs" / f".{slug}.{uuid.uuid4().hex}.partial"
    partial.mkdir(mode=0o700)
    final_dir = run_root / "runs" / slug
    config = _per_fit_config(
        regime,
        representation,
        seed,
        train_matches,
        validation_matches,
        plan_sha256,
        protocol_sha256,
        device,
    )
    config_sha256 = hashlib.sha256(_canonical(config)).hexdigest()
    rng = np.random.default_rng(seed)
    scoreable_by_match = [
        cast(NDArray[np.bool_], cache_by_match[mid].arrays["scoreable"]) for mid in train_matches
    ]
    selection = CheckpointSelection()
    validation_history: list[dict[str, object]] = []
    selected_metrics: dict[str, dict[str, float | int]] | None = None
    checkpoint_sha256: str | None = None
    model: PerTargetContextDeepSetsMLP | None = None
    optimizer: torch.optim.AdamW | None = None
    torch_device = torch.device(device)
    step = 0
    last_training_loss_m: float | None = None
    start_wall, start_cpu = time.monotonic(), time.process_time()
    fit_cpu_deadline = start_cpu + fit_cpu_budget_seconds
    fit_gpu_wall_deadline = start_wall + fit_gpu_wall_budget_seconds
    campaign_cpu_deadline = campaign_cpu_start + CAMPAIGN_CPU_BUDGET_SECONDS
    campaign_wall_deadline = campaign_wall_start + CAMPAIGN_WALL_BUDGET_SECONDS
    campaign_gpu_wall_deadline = (
        campaign_gpu_start if campaign_gpu_start is not None else campaign_wall_start
    ) + GPU_CAMPAIGN_BUDGET_SECONDS
    fit_peak_rss_bytes = _current_rss_bytes()
    fit_peak_gpu_bytes = 0
    failure: str | None = None
    stopping_reason = "max_optimizer_steps"
    try:
        if (start_cpu - campaign_cpu_start) > CAMPAIGN_CPU_BUDGET_SECONDS:
            raise RuntimeError("campaign_training_cpu_budget_exceeded")
        if device == "cuda":
            torch.cuda.reset_peak_memory_stats(torch_device)
        seed_training(seed)
        model = PerTargetContextDeepSetsMLP(regime).to(torch_device)
        optimizer = make_optimizer(model)
        for step in range(1, MAX_STEPS + 1):
            elapsed_cpu = time.process_time() - start_cpu
            if elapsed_cpu >= fit_cpu_budget_seconds:
                raise TimeoutError("per_fit_cpu_budget_exceeded")
            if time.process_time() >= campaign_cpu_deadline:
                raise TimeoutError("campaign_training_cpu_budget_exceeded")
            if time.monotonic() >= campaign_wall_deadline:
                raise TimeoutError("campaign_wall_budget_exceeded")
            if device == "cuda" and time.monotonic() >= fit_gpu_wall_deadline:
                raise TimeoutError("per_fit_gpu_wall_budget_exceeded")
            if device == "cuda" and time.monotonic() >= campaign_gpu_wall_deadline:
                raise TimeoutError("campaign_gpu_wall_budget_exceeded")
            if (
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
                > worker_memory_limit_bytes
            ):
                raise MemoryError("16GiB_worker_memory_budget_exceeded")
            sampled = [sample_scene_index(scoreable_by_match, rng) for _ in range(BATCH_SIZE)]
            payloads = [
                _scene_payload(
                    cache_by_match[train_matches[match_index]], window_index, lane, regime
                )
                for match_index, window_index, lane in sampled
            ]
            inputs: ModelInputs = _model_inputs_to_device(
                collate_feature_payloads(payloads, regime), torch_device
            )
            panel_name = (
                "target_absolute_xy" if representation == "absolute_xy" else "target_displacement"
            )
            truth = torch.from_numpy(
                np.stack(
                    [
                        cache_by_match[train_matches[match_index]].arrays[panel_name][
                            window_index, lane
                        ]
                        for match_index, window_index, lane in sampled
                    ]
                ).astype(np.float32)
            ).to(torch_device)
            mask = torch.from_numpy(
                np.stack(
                    [
                        cache_by_match[train_matches[match_index]].arrays["target_mask"][
                            window_index, lane
                        ]
                        for match_index, window_index, lane in sampled
                    ]
                )
            ).to(torch_device)
            model.train()
            optimizer.zero_grad(set_to_none=True)
            predictions = model(inputs)
            loss = masked_scene_ade_loss(predictions, truth, mask)
            if not torch.isfinite(loss):
                raise FloatingPointError("non_finite_training_loss")
            last_training_loss_m = float(loss.detach().cpu())
            loss.backward()
            if any(
                parameter.grad is not None and not torch.isfinite(parameter.grad).all()
                for parameter in model.parameters()
            ):
                raise FloatingPointError("non_finite_gradient")
            optimizer.step()
            fit_peak_rss_bytes = max(fit_peak_rss_bytes, _current_rss_bytes())
            if fit_peak_rss_bytes > worker_memory_limit_bytes:
                raise MemoryError("16GiB_worker_memory_budget_exceeded")
            if device == "cuda":
                fit_peak_gpu_bytes = max(
                    fit_peak_gpu_bytes, int(torch.cuda.max_memory_allocated(torch_device))
                )
                if fit_peak_gpu_bytes > MAX_GPU_ALLOCATED_BYTES:
                    raise MemoryError("8GiB_GPU_memory_budget_exceeded")
            if not validation_due(step):
                continue

            model.eval()
            match_metrics: dict[str, dict[str, float | int]] = {}
            for match_id in validation_matches:
                match_metrics[match_id] = _fit_match_metrics(
                    model,
                    cache_by_match[match_id],
                    regime,
                    representation,
                    fit_cpu_deadline=fit_cpu_deadline,
                    fit_gpu_wall_deadline=(fit_gpu_wall_deadline if device == "cuda" else None),
                    campaign_cpu_deadline=campaign_cpu_deadline,
                    campaign_wall_deadline=campaign_wall_deadline,
                    campaign_gpu_wall_deadline=(
                        campaign_gpu_wall_deadline if device == "cuda" else None
                    ),
                    worker_memory_limit_bytes=worker_memory_limit_bytes,
                )
                fit_peak_rss_bytes = max(fit_peak_rss_bytes, _current_rss_bytes())
                if fit_peak_rss_bytes > worker_memory_limit_bytes:
                    raise MemoryError("16GiB_worker_memory_budget_exceeded")
                if device == "cuda":
                    fit_peak_gpu_bytes = max(
                        fit_peak_gpu_bytes, int(torch.cuda.max_memory_allocated(torch_device))
                    )
                    if fit_peak_gpu_bytes > MAX_GPU_ALLOCATED_BYTES:
                        raise MemoryError("8GiB_GPU_memory_budget_exceeded")
            match_ade = {
                match_id: float(metrics["ade_m"]) for match_id, metrics in match_metrics.items()
            }
            validation_mean = equal_match_mean(match_ade, validation_matches)
            improved = selection.observe(step, validation_mean)
            validation_history.append(
                {
                    "step": step,
                    "match_metrics": match_metrics,
                    "equal_match_ade_m": validation_mean,
                    "improved": improved,
                }
            )
            if improved:
                selected_metrics = match_metrics
                checkpoint_sha256 = save_checkpoint_atomically(
                    partial / "checkpoint.pt",
                    {
                        "metadata": {
                            "run_id": run_id,
                            "configuration_sha256": config_sha256,
                            "selected_step": step,
                            "attempt_number": attempt_number,
                        },
                        "state_dict": {
                            key: value.detach().cpu() if device == "cuda" else value
                            for key, value in model.state_dict().items()
                        },
                    },
                )
            if selection.should_stop:
                stopping_reason = "10_consecutive_nonimproving_validation_checks"
                break
        if (
            model is None
            or selection.best_step is None
            or selected_metrics is None
            or not checkpoint_sha256
        ):
            raise RuntimeError("no valid validation checkpoint was selected")
        selected = load_checkpoint_verified(partial / "checkpoint.pt", checkpoint_sha256)
        if (
            cast(dict[str, object], selected["metadata"]).get("selected_step")
            != selection.best_step
        ):
            raise ValueError("selected checkpoint step differs from validation selection")
        if device == "cuda":
            torch.cuda.synchronize(torch_device)
            fit_peak_gpu_bytes = max(
                fit_peak_gpu_bytes, int(torch.cuda.max_memory_allocated(torch_device))
            )
        selected_state = cast(dict[str, Tensor], selected["state_dict"])
        if any(not torch.isfinite(value).all() for value in selected_state.values()):
            raise FloatingPointError("selected checkpoint contains non-finite parameters")
        PerTargetContextDeepSetsMLP(regime).load_state_dict(selected_state, strict=True)
        receipt: dict[str, object] = {
            "schema_id": "fpdbench.res338-research-final-fit",
            "schema_version": "1.0.0",
            "run_id": run_id,
            "cell_id": cell_id,
            "model_id": MODEL_ID,
            "information_regime": regime,
            "target_representation": representation,
            "seed": seed,
            "attempt_number": attempt_number,
            "execution_device": device,
            "session_identity": _colab_session_identity(),
            "accelerator": dict(accelerator) if accelerator is not None else None,
            "status": "completed",
            "fit_role": "final_train",
            "train_match_ids": list(train_matches),
            "validation_match_ids": list(validation_matches),
            "population_manifest_sha256": population_sha256,
            "target_mask_identity_sha256": target_mask_identity_sha256,
            "plan_sha256": plan_sha256,
            "protocol_sha256": protocol_sha256,
            "configuration_sha256": config_sha256,
            "environment_sha256": environment_sha256,
            "checkpoint_sha256": checkpoint_sha256,
            "selected_step": selection.best_step,
            "stopping_reason": stopping_reason,
            "validation_equal_match_ade_m": selection.best_metric,
            "validation_match_metrics": selected_metrics,
            "validation_history": validation_history,
            "last_training_loss_m": last_training_loss_m,
            "optimizer_steps": step,
            "fit_cpu_seconds": round(time.process_time() - start_cpu, 6),
            "fit_wall_seconds": round(time.monotonic() - start_wall, 6),
            "peak_rss_bytes": fit_peak_rss_bytes,
            "peak_rss_measurement": (
                "sampled process RSS after optimizer steps and validation matches"
            ),
            "fit_cpu_budget_seconds": fit_cpu_budget_seconds,
            "worker_memory_limit_bytes": worker_memory_limit_bytes,
            "fit_gpu_wall_budget_seconds": fit_gpu_wall_budget_seconds
            if device == "cuda"
            else None,
            "peak_gpu_memory_allocated_bytes": fit_peak_gpu_bytes if device == "cuda" else None,
        }
        _atomic_json(partial / "receipt.json", receipt)
        if final_dir.exists():
            raise FileExistsError("fit output already committed")
        os.rename(partial, final_dir)
        _fsync_directory(final_dir.parent)
        return receipt
    except Exception as exc:
        if isinstance(exc, TimeoutError):
            failure = str(exc)
        else:
            failure = fit_failure_category(exc)
        checkpoint = partial / "checkpoint.pt"
        if checkpoint.exists():
            checkpoint.unlink()
        failed = {
            "schema_id": "fpdbench.res338-research-final-fit",
            "schema_version": "1.0.0",
            "run_id": run_id,
            "cell_id": cell_id,
            "model_id": MODEL_ID,
            "information_regime": regime,
            "target_representation": representation,
            "seed": seed,
            "attempt_number": attempt_number,
            "execution_device": device,
            "session_identity": _colab_session_identity(),
            "accelerator": dict(accelerator) if accelerator is not None else None,
            "status": "failed",
            "fit_role": "final_train",
            "train_match_ids": list(train_matches),
            "validation_match_ids": list(validation_matches),
            "population_manifest_sha256": population_sha256,
            "plan_sha256": plan_sha256,
            "protocol_sha256": protocol_sha256,
            "configuration_sha256": config_sha256,
            "environment_sha256": environment_sha256,
            "checkpoint_sha256": None,
            "selected_step": None,
            "stopping_reason": failure,
            "failure_type": type(exc).__name__,
            "failure_message": str(exc)[:1000],
            "optimizer_steps": step - 1,
            "last_training_loss_m": last_training_loss_m,
            "fit_cpu_seconds": round(time.process_time() - start_cpu, 6),
            "fit_wall_seconds": round(time.monotonic() - start_wall, 6),
            "peak_rss_bytes": fit_peak_rss_bytes,
            "peak_rss_measurement": (
                "sampled process RSS after optimizer steps and validation matches"
            ),
            "fit_cpu_budget_seconds": fit_cpu_budget_seconds,
            "worker_memory_limit_bytes": worker_memory_limit_bytes,
            "fit_gpu_wall_budget_seconds": fit_gpu_wall_budget_seconds
            if device == "cuda"
            else None,
            "peak_gpu_memory_allocated_bytes": fit_peak_gpu_bytes if device == "cuda" else None,
        }
        if not final_dir.exists():
            _atomic_json(partial / "receipt.json", failed)
            os.rename(partial, final_dir)
            _fsync_directory(final_dir.parent)
        return failed


def _fit_order(
    train_matches: Sequence[str], validation_matches: Sequence[str]
) -> list[dict[str, object]]:
    return [
        {
            "information_regime": regime,
            "target_representation": representation,
            "seed": seed,
            "train_match_ids": list(train_matches),
            "validation_match_ids": list(validation_matches),
        }
        for representation in TARGET_REPRESENTATIONS
        for regime in INFORMATION_REGIMES
        for seed in SEEDS
    ]


def _six_frozen_configurations(plan_sha256: str, protocol_sha256: str) -> list[dict[str, object]]:
    return [
        {
            "cell_id": f"{MODEL_ID}|{regime}|{representation}",
            "model_id": MODEL_ID,
            "information_regime": regime,
            "target_representation": representation,
            "input_dim": INPUT_DIMS[regime],
            "configuration_sha256": hashlib.sha256(
                _canonical(
                    {
                        "model_id": MODEL_ID,
                        "information_regime": regime,
                        "target_representation": representation,
                        "input_dim": INPUT_DIMS[regime],
                        "plan_sha256": plan_sha256,
                        "protocol_sha256": protocol_sha256,
                    }
                )
            ).hexdigest(),
        }
        for representation in TARGET_REPRESENTATIONS
        for regime in INFORMATION_REGIMES
    ]


def _implementation_fingerprint() -> dict[str, str]:
    paths = (
        REPO
        / "src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction/learned_deepsets.py",
        Path(__file__).resolve(),
        REPO / "tools/res338_toy_preflight.py",
        REPO / "tools/res338_cuda_qualification.py",
        REPO / "tools/res338_build_reference_manifest.py",
        REPO / "tools/res338_colab_prepare.py",
        REPO / "tools/res338_colab_setup.py",
        REPO / "tools/res338_colab_gpu_requirements.txt",
        REPO / "tools/res338_colab_worker.py",
        REPO / "tools/res338_colab_job.py",
        REPO / "tools/res338_colab_gpu_probe.py",
        REPO / "tools/res338_cache_archive.py",
        REPO / "tools/res338_colab_progress.py",
        REPO / "tools/res338_drive_readback.py",
        REPO / "tools/research_population_v1.py",
        REPO / "tools/research_population_verifier_v1.py",
        REPO / "pyproject.toml",
        REPO / "uv.lock",
        GPU_EXECUTION_AMENDMENT,
        PRIVATE_CLOUD_AMENDMENT,
    )
    return {path.relative_to(REPO).as_posix(): _sha256_file(path) for path in paths}


def _fit_run_id(fit: Mapping[str, object]) -> str:
    return (
        f"{MODEL_ID}|{fit['information_regime']}|{fit['target_representation']}"
        f"|final_train|final|{fit['seed']}"
    )


def _verify_cached_inputs(output_root: Path, cache_receipts: Mapping[str, object]) -> None:
    for match_id, raw_receipt in cache_receipts.items():
        receipt = cast(dict[str, object], raw_receipt)
        directory = output_root / "feature-cache" / str(receipt["role"]) / match_id
        cache_bytes = read_private_file(
            directory / "cache.json", str(receipt["cache_metadata_sha256"])
        )
        cache = json.loads(cache_bytes, object_pairs_hook=_unique_json_object)
        expected_cache = {
            key: value for key, value in receipt.items() if key != "cache_metadata_sha256"
        }
        if cache != expected_cache:
            raise ValueError("private feature-cache manifest differs from its frozen identity")
        arrays = cast(dict[str, str], receipt["arrays"])
        for name, expected_sha in arrays.items():
            if _sha256_file(directory / name) != expected_sha:
                raise ValueError("private feature-cache array identity mismatch")


def _verified_preloaded_cache(
    directory: Path, match_id: str, role: str, expected: Mapping[str, object]
) -> dict[str, object]:
    expected_metadata_sha = str(expected["cache_metadata_sha256"])
    payload = read_private_file(directory / "cache.json", expected_metadata_sha)
    cache = cast(dict[str, object], json.loads(payload, object_pairs_hook=_unique_json_object))
    identity = {key: value for key, value in expected.items() if key != "cache_metadata_sha256"}
    if cache != identity or cache.get("match_id") != match_id or cache.get("role") != role:
        raise ValueError("preloaded cache identity differs from its frozen private reference")
    arrays = cast(dict[str, str], cache["arrays"])
    expected_arrays = {f"{name}.npy" for name in (*_FEATURE_ARRAYS, *_LABEL_ARRAYS)}
    if set(arrays) != expected_arrays:
        raise ValueError("preloaded cache has missing or unexpected arrays")
    members = {item.name for item in directory.iterdir()}
    if members != expected_arrays | {"cache.json"}:
        raise ValueError("preloaded cache directory has missing or unexpected files")
    for name, expected_sha in arrays.items():
        if _sha256_file(directory / name) != expected_sha:
            raise ValueError("preloaded cache array hash differs")
    return {**cache, "cache_metadata_sha256": expected_metadata_sha}


def _verify_toy_preflight(
    path: Path,
    *,
    plan_sha256: str,
    protocol_sha256: str,
    code_sha: str,
    runtime_sha256: str,
    device: str = "cpu",
) -> tuple[bytes, dict[str, object], str]:
    payload = _read_private_bytes(path)
    report = cast(dict[str, object], json.loads(payload, object_pairs_hook=_unique_json_object))
    digest = hashlib.sha256(payload).hexdigest()
    if device == "cuda":
        qualification = cast(dict[str, object], report.get("cuda_qualification", {}))
        tolerances = cast(dict[str, object], qualification.get("numerical_tolerances", {}))
        if (
            report.get("schema_id") != "fpdbench.res338-cuda-qualification"
            or report.get("schema_version") != "1.0.0"
            or report.get("status") != "PASSED"
            or report.get("synthetic_only") is not True
            or report.get("real_fit_count") != 0
            or report.get("real_evaluation_metrics") != 0
            or report.get("evaluation_match_features") != 0
            or report.get("real_tracking_rows_read_for_features") != 0
            or report.get("research_manifest_sha256") != RESEARCH_MANIFEST_SHA256
            or report.get("plan_sha256") != plan_sha256
            or report.get("protocol_sha256") != protocol_sha256
            or report.get("code_sha") != code_sha
            or report.get("runtime_sha256") != runtime_sha256
            or report.get("device") != "cuda"
            or qualification.get("numerical_agreement") != "PASSED"
            or qualification.get("deterministic_replay") != "BITWISE_EQUAL"
            or set(cast(dict[str, object], qualification.get("per_regime", {})))
            != set(INFORMATION_REGIMES)
            or tolerances
            != {
                "prediction_and_masked_ade": {"rtol": 1e-4, "atol": 1e-5},
                "gradient_and_adamw_update": {"rtol": 1e-3, "atol": 1e-5},
            }
            or report.get("synthetic_optimization_steps") != MAX_STEPS
            or report.get("synthetic_validation_checks") != MAX_STEPS // VALIDATION_CADENCE
            or report.get("synthetic_full_cadence_forced") is not True
            or float(report.get("synthetic_fit_cpu_seconds", math.inf)) > FIT_CPU_BUDGET_SECONDS
            or float(report.get("synthetic_fit_wall_seconds", math.inf))
            > GPU_FIT_WALL_BUDGET_SECONDS
            or int(report.get("synthetic_peak_rss_bytes", MAX_WORKER_RSS_BYTES + 1))
            > MAX_WORKER_RSS_BYTES
            or int(report.get("synthetic_peak_cuda_memory_bytes", MAX_GPU_ALLOCATED_BYTES + 1))
            > MAX_GPU_ALLOCATED_BYTES
            or int(report.get("available_disk_bytes", 0))
            < int(report.get("estimated_private_cache_bytes_with_32_tracks_per_team", 0))
            + GPU_PRIVATE_DISK_RESERVE_BYTES
        ):
            raise ValueError("synthetic CUDA qualification did not pass the frozen limits")
        return payload, report, digest

    rehash = cast(dict[str, object], report.get("population_rehash", {}))
    if (
        report.get("schema_id") != "fpdbench.res338-toy-preflight"
        or report.get("schema_version") != "1.0.0"
        or report.get("status") != "PASSED"
        or report.get("synthetic_only") is not True
        or report.get("real_fit_count") != 0
        or report.get("real_evaluation_metrics") != 0
        or report.get("evaluation_match_features") != 0
        or report.get("real_tracking_rows_read_for_features") != 0
        or report.get("research_manifest_sha256") != RESEARCH_MANIFEST_SHA256
        or rehash.get("source_files_rehashed") != 81
        or rehash.get("independent_source_files_rehashed") != 81
        or rehash.get("producer_outputs_rehashed") != 20
        or rehash.get("verifier_outputs_rehashed") != 20
        or rehash.get("producer_verifier_mismatches") != 0
        or rehash.get("exact_role_assignment_match") is not True
        or report.get("plan_sha256") != plan_sha256
        or report.get("protocol_sha256") != protocol_sha256
        or report.get("code_sha") != code_sha
        or report.get("runtime_sha256") != runtime_sha256
        or report.get("synthetic_optimization_steps") != MAX_STEPS
        or report.get("synthetic_validation_checks") != MAX_STEPS // VALIDATION_CADENCE
        or report.get("synthetic_full_cadence_forced") is not True
        or float(report.get("synthetic_fit_cpu_seconds", math.inf)) > FIT_CPU_BUDGET_SECONDS
        or int(report.get("synthetic_peak_rss_bytes", MAX_WORKER_RSS_BYTES + 1))
        > int(report.get("effective_worker_memory_limit_bytes", MAX_WORKER_RSS_BYTES))
        or int(report.get("estimated_private_cache_bytes_with_32_tracks_per_team", 0))
        + DEFAULT_PRIVATE_DISK_RESERVE_BYTES
        > int(report.get("available_disk_bytes", 0))
    ):
        raise ValueError("toy-only CPU and disk preflight did not pass the frozen limits")
    return payload, report, digest


def _verify_committed_run(
    output_root: Path,
    ledger_item: Mapping[str, object],
    fit: Mapping[str, object],
    environment_sha256: str,
    train_matches: Sequence[str],
    validation_matches: Sequence[str],
    plan_sha256: str,
    protocol_sha256: str,
    device: str = "cpu",
) -> None:
    run_id = _fit_run_id(fit)
    if ledger_item.get("run_id") != run_id or ledger_item.get("status") != "completed":
        raise ValueError("campaign ledger contains a noncompleted or out-of-order fit")
    run_dir = output_root / "runs" / run_id.replace("|", "--")
    receipt_bytes = read_private_file(run_dir / "receipt.json", str(ledger_item["receipt_sha256"]))
    receipt = cast(
        dict[str, object], json.loads(receipt_bytes, object_pairs_hook=_unique_json_object)
    )
    config = _per_fit_config(
        cast(InformationRegime, fit["information_regime"]),
        cast(TargetRepresentation, fit["target_representation"]),
        int(fit["seed"]),
        train_matches,
        validation_matches,
        plan_sha256,
        protocol_sha256,
        device,
    )
    expected_config_sha256 = hashlib.sha256(_canonical(config)).hexdigest()
    if (
        receipt.get("run_id") != run_id
        or receipt.get("status") != "completed"
        or receipt.get("configuration_sha256") != expected_config_sha256
        or receipt.get("environment_sha256") != environment_sha256
        or receipt.get("execution_device") != device
        or receipt.get("checkpoint_sha256") != ledger_item.get("checkpoint_sha256")
    ):
        raise ValueError("committed run receipt differs from the frozen configuration")
    if device == "cuda":
        accelerator = cast(dict[str, object] | None, receipt.get("accelerator"))
        session = cast(dict[str, object], receipt.get("session_identity", {}))
        if (
            not accelerator
            or not accelerator.get("name")
            or not accelerator.get("driver_version")
            or not session.get("session_name")
            or not session.get("session_id")
            or int(receipt.get("peak_gpu_memory_allocated_bytes", MAX_GPU_ALLOCATED_BYTES + 1))
            > MAX_GPU_ALLOCATED_BYTES
        ):
            raise ValueError("GPU runtime identity or memory receipt is incomplete")
    checkpoint = run_dir / "checkpoint.pt"
    loaded = load_checkpoint_verified(checkpoint, str(receipt["checkpoint_sha256"]))
    metadata = cast(dict[str, object], loaded["metadata"])
    if (
        metadata.get("run_id") != run_id
        or metadata.get("configuration_sha256") != expected_config_sha256
        or metadata.get("attempt_number") != receipt.get("attempt_number")
    ):
        raise ValueError("checkpoint metadata differs from the frozen run")
    model = PerTargetContextDeepSetsMLP(cast(InformationRegime, fit["information_regime"]))
    state_dict = cast(dict[str, Tensor], loaded["state_dict"])
    model.load_state_dict(state_dict, strict=True)
    if any(not torch.isfinite(tensor).all() for tensor in state_dict.values()):
        raise ValueError("checkpoint contains non-finite parameters")
    if set(cast(dict[str, object], receipt["validation_match_metrics"])) != set(validation_matches):
        raise ValueError("completed checkpoint is missing a validation-match metric")
    selected_step = receipt.get("selected_step")
    if (
        not isinstance(selected_step, int)
        or selected_step < 100
        or selected_step > MAX_STEPS
        or selected_step % VALIDATION_CADENCE
    ):
        raise ValueError("checkpoint selected step differs from the frozen cadence")


def run_campaign(
    research_root: Path,
    source_root: Path,
    output_root: Path,
    *,
    resume: bool = False,
    retry_interrupted_run: str | None = None,
    device: str = "cpu",
    research_scope: str = "full",
    reference_manifest_path: Path | None = None,
    reference_manifest_sha256: str | None = None,
    preloaded_cache_root: Path | None = None,
    toy_preflight_path: Path | None = None,
    max_new_fits: int | None = None,
    prepare_only: bool = False,
) -> dict[str, object]:
    os.umask(0o077)
    if device not in {"cpu", "cuda"}:
        raise ValueError("device must be cpu or cuda")
    if research_scope not in {"full", "training-validation"}:
        raise ValueError("unknown research scope")
    if device == "cuda" and research_scope != "training-validation":
        raise ValueError("GPU final fits must use the training/validation-only scope")
    if research_scope == "training-validation" and reference_manifest_path is None:
        raise ValueError("training-validation scope requires its projected reference manifest")
    if preloaded_cache_root is not None and research_scope != "training-validation":
        raise ValueError("preloaded research caches require the training-validation scope")
    if max_new_fits is not None and max_new_fits <= 0:
        raise ValueError("max_new_fits must be a positive integer")
    if prepare_only and (resume or retry_interrupted_run is not None or max_new_fits is not None):
        raise ValueError(
            "prepare-only mode is fresh and cannot be combined with resume or fit limits"
        )
    if device == "cuda":
        affinity = os.sched_getaffinity(0)
        if not affinity:
            raise RuntimeError("the GPU worker has no CPU affinity")
        os.sched_setaffinity(0, {min(affinity)})
        if not GPU_EXECUTION_AMENDMENT.is_file() or not PRIVATE_CLOUD_AMENDMENT.is_file():
            raise FileNotFoundError("the frozen GPU and private-cloud amendments are required")
    required_disk_reserve_bytes = (
        GPU_PRIVATE_DISK_RESERVE_BYTES if device == "cuda" else DEFAULT_PRIVATE_DISK_RESERVE_BYTES
    )
    if reference_manifest_path is not None:
        if reference_manifest_sha256 is None or _sha256_file(reference_manifest_path) != (
            reference_manifest_sha256
        ):
            raise ValueError("training-validation reference hash differs")
    toy_preflight_path = toy_preflight_path or TOY_PREFLIGHT_PATH
    gpu_amendment_sha256 = _sha256_file(GPU_EXECUTION_AMENDMENT) if device == "cuda" else None
    cloud_amendment_sha256 = _sha256_file(PRIVATE_CLOUD_AMENDMENT) if device == "cuda" else None
    if not output_root.is_absolute():
        raise ValueError("private evidence output must use an absolute path")
    fresh = not output_root.exists()
    if fresh and (resume or retry_interrupted_run is not None):
        raise ValueError("an interrupted campaign can only resume from its existing private root")
    if not fresh and not resume:
        raise FileExistsError("evidence output exists; use the frozen resume path")
    with source.private_directory(output_root.parent):
        pass
    if fresh:
        output_root.mkdir(mode=0o700)
        (output_root / "feature-cache").mkdir(mode=0o700)
        (output_root / "runs").mkdir(mode=0o700)
    with source.private_directory(output_root):
        pass
    if not fresh:
        with (
            source.private_directory(output_root / "feature-cache"),
            source.private_directory(output_root / "runs"),
        ):
            pass
    preparation_cpu_start: float | None = None
    lock_fd = os.open(output_root / "campaign.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        os.close(lock_fd)
        raise RuntimeError("another training worker holds the campaign lock") from exc

    try:
        prior_ledger: dict[str, object] | None = None
        freeze: dict[str, object] | None = None
        if fresh:
            campaign_wall_start = time.monotonic()
            campaign_started_at = datetime.now(UTC).isoformat()
            preparation_cpu_start = time.process_time()
        else:
            prior_ledger = _read_private_json(output_root / "campaign.json")
            frozen_sha = str(prior_ledger["frozen_manifest_sha256"])
            freeze = cast(
                dict[str, object],
                json.loads(
                    read_private_file(output_root / "reproducibility-manifest.json", frozen_sha),
                    object_pairs_hook=_unique_json_object,
                ),
            )
            started_at = datetime.fromisoformat(str(freeze["campaign_started_at_utc"]))
            elapsed_wall = max(0.0, (datetime.now(UTC) - started_at).total_seconds())
            campaign_wall_start = time.monotonic() - elapsed_wall
            campaign_started_at = str(freeze["campaign_started_at_utc"])
            preparation_cpu_start = time.process_time()

        runtime = _validate_training_runtime(device)
        plan, protocol, roles = _frozen_split_and_authorities()
        if research_scope == "full":
            research_manifest, population_rehash = verify_research_population(
                research_root, source_root, plan, roles
            )
        else:
            assert reference_manifest_path is not None and reference_manifest_sha256 is not None
            research_manifest, population_rehash = verify_training_validation_population(
                research_root,
                source_root,
                reference_manifest_path,
                reference_manifest_sha256,
                plan,
                roles,
            )
            roles = {role: roles[role] for role in ("training", "validation")}
        train_matches, validation_matches = roles["training"], roles["validation"]
        if set(train_matches) & set(validation_matches):
            raise ValueError("training and validation match roles must be disjoint")
        configs = _fit_order(train_matches, validation_matches)
        plan_sha256 = str(plan["plan_sha256"])
        protocol_sha256 = str(protocol["protocol_sha256"])
        six_configs = _six_frozen_configurations(plan_sha256, protocol_sha256)
        runtime_sha256 = _training_environment_sha256(runtime)
        implementation = _implementation_fingerprint()
        code_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
        ).strip()
        toy_payload, toy_report, toy_preflight_sha256 = _verify_toy_preflight(
            toy_preflight_path,
            plan_sha256=plan_sha256,
            protocol_sha256=protocol_sha256,
            code_sha=code_sha,
            runtime_sha256=runtime_sha256,
            device=device,
        )
        if time.monotonic() - campaign_wall_start >= CAMPAIGN_WALL_BUDGET_SECONDS:
            raise TimeoutError("campaign_wall_budget_exceeded")

        if fresh:
            resource_state = _resource_fingerprint(output_root)
            cache_receipts: dict[str, dict[str, object]] = {}
            preloaded_identities = cast(
                dict[str, dict[str, object]],
                research_manifest.get("preloaded_cache_identities", {}),
            )
            preloaded_matches = set(preloaded_identities)
            if device == "cuda" and len(preloaded_matches) != 6:
                raise ValueError("the GPU preparation reference must bind all six completed caches")
            if preloaded_matches:
                if preloaded_cache_root is None:
                    raise ValueError(
                        "frozen preloaded caches must be staged before cache preparation"
                    )
                with source.private_directory(preloaded_cache_root):
                    pass
                if {item.name for item in preloaded_cache_root.iterdir()} != {"training"}:
                    raise ValueError("staged cache root contains a nontraining cache role")
                training_root = preloaded_cache_root / "training"
                if {item.name for item in training_root.iterdir()} != preloaded_matches:
                    raise ValueError("staged cache set differs from the six frozen training caches")
            for role, matches in (("training", train_matches), ("validation", validation_matches)):
                for match_id in matches:
                    if time.process_time() - preparation_cpu_start >= (
                        CAMPAIGN_PREPARATION_CPU_BUDGET_SECONDS
                    ):
                        raise TimeoutError("campaign_preparation_cpu_budget_exceeded")
                    if time.monotonic() - campaign_wall_start >= CAMPAIGN_WALL_BUDGET_SECONDS:
                        raise TimeoutError("campaign_wall_budget_exceeded")
                    if match_id in preloaded_matches:
                        identity = _verified_preloaded_cache(
                            preloaded_cache_root / role / match_id,
                            match_id,
                            role,
                            preloaded_identities[match_id],
                        )
                        target = output_root / "feature-cache" / role / match_id
                        target.parent.mkdir(mode=0o700, exist_ok=True)
                        shutil.copytree(preloaded_cache_root / role / match_id, target)
                        cache_receipts[match_id] = identity
                    else:
                        cache_receipts[match_id] = _build_match_cache(
                            research_root,
                            output_root / "feature-cache",
                            match_id,
                            role,
                            research_manifest,
                            required_disk_reserve_bytes,
                        )
            target_mask_identity = hashlib.sha256(
                _canonical(
                    {
                        mid: cache_receipts[mid]["target_mask_identity_sha256"]
                        for mid in sorted(cache_receipts)
                    }
                )
            ).hexdigest()
            fit_resource_state = _resource_fingerprint(output_root)
            worker_memory_limit = int(fit_resource_state["effective_worker_memory_limit_bytes"])
            feature_cache_bytes = sum(
                path.stat().st_size
                for path in (output_root / "feature-cache").rglob("*")
                if path.is_file()
            )
            if int(fit_resource_state["disk_available_bytes"]) < required_disk_reserve_bytes:
                raise OSError("frozen private disk reserve is required before training")
            if _current_rss_bytes() > worker_memory_limit:
                raise MemoryError("worker RSS exceeds available host memory before fitting")
            preparation_cpu_seconds = round(time.process_time() - preparation_cpu_start, 6)
            preparation_wall_seconds = round(time.monotonic() - campaign_wall_start, 6)
            if preparation_cpu_seconds > CAMPAIGN_PREPARATION_CPU_BUDGET_SECONDS:
                raise TimeoutError("campaign_preparation_cpu_budget_exceeded")
            factorial = cast(dict[str, object], plan["factorial"])
            model_spec = next(
                cast(dict[str, object], item)
                for item in cast(list[object], factorial["model_classes"])
                if cast(dict[str, object], item).get("class_id") == MODEL_ID
            )
            population_authority = cast(dict[str, object], plan["population_authority"])
            freeze = {
                "schema_id": "fpdbench.res338-research-final-fit-campaign",
                "schema_version": "1.0.0",
                "status": "FROZEN",
                "campaign_started_at_utc": campaign_started_at,
                "owner_authorization": {
                    "scope_comment_id": "8021405d-5508-46a2-accd-66095869ea85",
                    "manifest_sha256": RESEARCH_MANIFEST_SHA256,
                    "scope": (
                        "owner-authorized 18 research-only final-role fits; no evaluation "
                        "scoring or learned LOMO"
                    ),
                },
                "research_contract": f"{RESEARCH_SCHEMA}/{RESEARCH_VERSION}",
                "research_manifest_sha256": RESEARCH_MANIFEST_SHA256,
                "research_scope": research_scope,
                "research_projection_sha256": population_rehash.get(
                    "projected_research_admission_sha256"
                ),
                "reference_manifest_sha256": reference_manifest_sha256,
                "source_release_hash": research_manifest["source_release_hash"],
                "source_population_hash": research_manifest["source_population_hash"],
                "source_inventory_sha256": research_manifest["source_inventory_sha256"],
                "independent_source_sha256": research_manifest["independent_source_sha256"],
                "source_reconciliation_status": research_manifest["status"],
                "protected_status": research_manifest["protected_status"],
                "population_rehash": population_rehash,
                "research_roles": roles,
                "plan_sha256": plan_sha256,
                "protocol_sha256": protocol_sha256,
                "measurement_state_hash": population_authority["measurement_state_hash"],
                "eligibility_policy_hash": population_authority["eligibility_policy_hash"],
                "model_id": MODEL_ID,
                "training_device": device,
                "gpu_execution_amendment_sha256": gpu_amendment_sha256,
                "private_cloud_amendment_sha256": cloud_amendment_sha256,
                "session_identity_at_freeze": _colab_session_identity(),
                "architecture": model_spec["architecture"],
                "head_feature_layout": HEAD_FEATURE_LAYOUT,
                "track_pooling": TRACK_POOLING,
                "observation_features": {
                    "sample_grid": (
                        "26 history samples from -5.0 through 0.0 seconds; 15 future "
                        "samples from 0.2 through 3.0 seconds"
                    ),
                    "coordinates": (
                        "finite physical XY in metres; missing pairs filled with (0,0) and "
                        "a zero presence bit; no pitch normalization"
                    ),
                    "presence": (
                        "one iff both XY coordinates are finite; source detection flags are "
                        "not model features"
                    ),
                    "target_features": (
                        "target-player history and pooled historical team context only; "
                        "future target positions, masks, and availability are labels only"
                    ),
                },
                "input_dimensions": INPUT_DIMS,
                "six_frozen_configurations": six_configs,
                "toy_preflight_sha256": toy_preflight_sha256,
                "toy_preflight_summary": {
                    key: toy_report[key]
                    for key in (
                        "synthetic_optimization_steps",
                        "synthetic_validation_checks",
                        "synthetic_full_cadence_forced",
                        "synthetic_fit_cpu_seconds",
                        "synthetic_fit_wall_seconds",
                        "synthetic_peak_rss_bytes",
                        "synthetic_peak_cuda_memory_bytes",
                        "effective_worker_memory_limit_bytes",
                        "estimated_private_cache_bytes_with_32_tracks_per_team",
                        "available_disk_bytes",
                    )
                    if key in toy_report
                },
                "seeds": list(SEEDS),
                "fit_order": configs,
                "fit_count_required": 18,
                "training_and_selection": {
                    "batch_size_directed_scenes": BATCH_SIZE,
                    "sampling": (
                        "uniform_match_then_uniform_scoreable_window_then_"
                        "uniform_scoreable_scene_with_replacement"
                    ),
                    "optimizer": "AdamW",
                    "learning_rate": 0.001,
                    "betas": [0.9, 0.999],
                    "epsilon": 1e-8,
                    "weight_decay": 0.0001,
                    "scheduler": None,
                    "gradient_clipping": None,
                    "validation_cadence_steps": VALIDATION_CADENCE,
                    "validation_aggregation": (
                        "equal mean of the four validation-match physical XY ADE values"
                    ),
                    "strict_improvement": True,
                    "tie_break": "earliest optimizer step",
                    "patience_checks": PATIENCE,
                    "maximum_steps": MAX_STEPS,
                    "per_fit_cpu_seconds": FIT_CPU_BUDGET_SECONDS,
                    "per_fit_retry_cpu_seconds": 0.25 * 3600,
                    "per_fit_gpu_wall_seconds": (
                        GPU_FIT_WALL_BUDGET_SECONDS if device == "cuda" else None
                    ),
                    "per_fit_gpu_retry_wall_seconds": (
                        GPU_RETRY_WALL_BUDGET_SECONDS if device == "cuda" else None
                    ),
                    "campaign_gpu_wall_seconds": (
                        GPU_CAMPAIGN_BUDGET_SECONDS if device == "cuda" else None
                    ),
                    "maximum_gpu_memory_allocated_bytes": (
                        MAX_GPU_ALLOCATED_BYTES if device == "cuda" else None
                    ),
                    "campaign_training_cpu_seconds": CAMPAIGN_CPU_BUDGET_SECONDS,
                    "campaign_preparation_cpu_seconds": CAMPAIGN_PREPARATION_CPU_BUDGET_SECONDS,
                    "campaign_wall_seconds": CAMPAIGN_WALL_BUDGET_SECONDS,
                },
                "preparation_cpu_seconds": preparation_cpu_seconds,
                "preparation_wall_seconds": preparation_wall_seconds,
                "target_mask_identity_sha256": target_mask_identity,
                "feature_cache": cache_receipts,
                "feature_cache_total_bytes": feature_cache_bytes,
                "private_disk_reserve_before_fit_bytes": required_disk_reserve_bytes,
                "runtime": runtime,
                "runtime_sha256": runtime_sha256,
                "host_resources_before_cache": resource_state,
                "host_resources_before_fit": fit_resource_state,
                "worker_memory_limit_bytes": worker_memory_limit,
                "code_sha": code_sha,
                "implementation_files": implementation,
                "research_admission_amendment_sha256": _sha256_file(
                    REPO / "docs/research-population-admission-v1.md"
                ),
                "research_private_cloud_amendment_sha256": cloud_amendment_sha256,
                "research_gpu_execution_amendment_sha256": gpu_amendment_sha256,
                "data_rights_policy_sha256": _sha256_file(REPO / "docs/data-rights.md"),
                "configuration_sha256": hashlib.sha256(_canonical(configs)).hexdigest(),
                "environment_sha256": runtime_sha256,
                "artifacts_policy": (
                    "training/validation row-level caches, receipts, and checkpoints remain "
                    "owner-private; no evaluation-role files or labels are loaded"
                ),
                "evaluation_scoring": "not run",
                "learned_lomo": "not run",
            }
            _atomic_json(output_root / "reproducibility-manifest.json", freeze)
            _atomic_write(output_root / "toy-preflight.json", toy_payload)
            freeze_sha256 = _sha256_file(output_root / "reproducibility-manifest.json")
            ledger: dict[str, object] = {
                "schema_id": "fpdbench.res338-research-final-fit-ledger",
                "schema_version": "1.0.0",
                "status": "RUNNING",
                "frozen_manifest_sha256": freeze_sha256,
                "required_fit_count": 18,
                "completed_fit_count": 0,
                "failed_fit_count": 0,
                "reserved_training_cpu_seconds": 0.0,
                "reserved_gpu_wall_seconds": 0.0,
                "recorded_gpu_wall_seconds": 0.0,
                "gpu_training_started_at_utc": None,
                "current_run_id": None,
                "current_attempt": None,
                "current_configuration_sha256": None,
                "runs": [],
                "attempt_history": {},
            }
            _atomic_json(output_root / "campaign.json", ledger)
        else:
            assert freeze is not None and prior_ledger is not None
            if (
                freeze.get("schema_id") != "fpdbench.res338-research-final-fit-campaign"
                or freeze.get("research_manifest_sha256") != RESEARCH_MANIFEST_SHA256
                or freeze.get("research_scope") != research_scope
                or freeze.get("research_projection_sha256")
                != population_rehash.get("projected_research_admission_sha256")
                or freeze.get("reference_manifest_sha256") != reference_manifest_sha256
                or freeze.get("source_release_hash") != research_manifest["source_release_hash"]
                or freeze.get("source_population_hash")
                != research_manifest["source_population_hash"]
                or freeze.get("plan_sha256") != plan_sha256
                or freeze.get("protocol_sha256") != protocol_sha256
                or freeze.get("research_roles") != roles
                or freeze.get("runtime_sha256") != runtime_sha256
                or freeze.get("training_device") != device
                or freeze.get("gpu_execution_amendment_sha256") != gpu_amendment_sha256
                or freeze.get("private_cloud_amendment_sha256") != cloud_amendment_sha256
                or freeze.get("code_sha") != code_sha
                or freeze.get("implementation_files") != implementation
                or freeze.get("toy_preflight_sha256") != toy_preflight_sha256
            ):
                raise ValueError(
                    "resume rejected because the frozen code, environment, or source changed"
                )
            read_private_file(output_root / "toy-preflight.json", toy_preflight_sha256)
            cache_receipts = cast(dict[str, dict[str, object]], freeze["feature_cache"])
            _verify_cached_inputs(output_root, cache_receipts)
            fit_resource_state = _resource_fingerprint(output_root)
            worker_memory_limit = int(freeze["worker_memory_limit_bytes"])
            if int(fit_resource_state["memory_available_bytes"]) < worker_memory_limit:
                raise RuntimeError("available host memory is below the frozen worker limit")
            if int(fit_resource_state["disk_available_bytes"]) < int(
                freeze.get(
                    "private_disk_reserve_before_fit_bytes",
                    DEFAULT_PRIVATE_DISK_RESERVE_BYTES,
                )
            ):
                raise RuntimeError("available private disk is below the frozen reserve")
            if _current_rss_bytes() > worker_memory_limit:
                raise MemoryError("worker RSS exceeds available host memory before fitting")
            ledger = prior_ledger
            if ledger.get("frozen_manifest_sha256") != _sha256_file(
                output_root / "reproducibility-manifest.json"
            ):
                raise ValueError("campaign ledger does not bind the reproducibility manifest")
            target_mask_identity = str(freeze["target_mask_identity_sha256"])
            repeated_preparation_cpu = time.process_time() - preparation_cpu_start
            total_preparation_cpu = (
                float(freeze["preparation_cpu_seconds"])
                + float(ledger.get("resume_preparation_cpu_seconds", 0.0))
                + repeated_preparation_cpu
            )
            if total_preparation_cpu > CAMPAIGN_PREPARATION_CPU_BUDGET_SECONDS:
                raise TimeoutError("campaign_preparation_cpu_budget_exceeded")
            ledger["resume_preparation_cpu_seconds"] = round(
                float(ledger.get("resume_preparation_cpu_seconds", 0.0)) + repeated_preparation_cpu,
                6,
            )
            _atomic_json(output_root / "campaign.json", ledger)

        cache_by_match = {
            match_id: _open_match_cache(
                output_root / "feature-cache" / cast(str, receipt["role"]) / match_id,
                match_id,
                cast(str, receipt["role"]),
            )
            for match_id, receipt in cache_receipts.items()
        }
        if (
            hashlib.sha256(
                _canonical(
                    {
                        mid: cache_receipts[mid]["target_mask_identity_sha256"]
                        for mid in sorted(cache_receipts)
                    }
                )
            ).hexdigest()
            != target_mask_identity
        ):
            raise ValueError("target or mask identities changed in the private feature cache")

        freeze_sha256 = str(ledger["frozen_manifest_sha256"])
        prior_runs = cast(list[dict[str, object]], ledger["runs"])
        completed_ids: set[str] = set()
        for item in prior_runs:
            run_id = str(item["run_id"])
            fit = next(
                (candidate for candidate in configs if _fit_run_id(candidate) == run_id), None
            )
            if fit is None:
                raise ValueError("campaign ledger contains a run outside the frozen fit schedule")
            _verify_committed_run(
                output_root,
                item,
                fit,
                runtime_sha256,
                train_matches,
                validation_matches,
                plan_sha256,
                protocol_sha256,
                device,
            )
            completed_ids.add(run_id)
        if int(ledger["completed_fit_count"]) != len(completed_ids):
            raise ValueError("campaign coverage count differs from committed fit receipts")
        if int(ledger["failed_fit_count"]):
            raise RuntimeError("failed scientific fits are terminal and cannot be retried")
        if prepare_only:
            if not fresh or completed_ids:
                raise RuntimeError(
                    "prepare-only mode requires a fresh campaign with zero real fits"
                )
            ledger["status"] = "PREPARED"
            _atomic_json(output_root / "campaign.json", ledger)
            return ledger

        current_run_id = cast(str | None, ledger.get("current_run_id"))
        retry_id: str | None = None
        if current_run_id is not None:
            if not resume:
                raise RuntimeError(
                    "an interrupted campaign requires --resume; existing evidence is preserved"
                )
            fit = next(
                (candidate for candidate in configs if _fit_run_id(candidate) == current_run_id),
                None,
            )
            if fit is None or current_run_id in completed_ids:
                raise ValueError("uncommitted run is outside the frozen schedule")
            config = _per_fit_config(
                cast(InformationRegime, fit["information_regime"]),
                cast(TargetRepresentation, fit["target_representation"]),
                int(fit["seed"]),
                train_matches,
                validation_matches,
                plan_sha256,
                protocol_sha256,
                device,
            )
            current_config_sha256 = hashlib.sha256(_canonical(config)).hexdigest()
            if current_config_sha256 != ledger.get("current_configuration_sha256"):
                raise RuntimeError("the retry configuration differs from the interrupted fit")
            run_dir = output_root / "runs" / current_run_id.replace("|", "--")
            if run_dir.exists():
                receipt = _read_private_json(run_dir / "receipt.json")
                if (
                    receipt.get("run_id") != current_run_id
                    or receipt.get("configuration_sha256") != current_config_sha256
                    or receipt.get("environment_sha256") != runtime_sha256
                ):
                    raise ValueError("atomic fit output differs from its frozen configuration")
                committed_item = {
                    "run_id": current_run_id,
                    "status": receipt["status"],
                    "receipt_sha256": _sha256_file(run_dir / "receipt.json"),
                    "checkpoint_sha256": receipt["checkpoint_sha256"],
                    "optimizer_steps": receipt["optimizer_steps"],
                    "fit_cpu_seconds": receipt["fit_cpu_seconds"],
                    "fit_wall_seconds": receipt["fit_wall_seconds"],
                    "gpu_wall_seconds": (receipt["fit_wall_seconds"] if device == "cuda" else 0.0),
                    "peak_rss_bytes": receipt["peak_rss_bytes"],
                    "stopping_reason": receipt["stopping_reason"],
                }
                if receipt["status"] == "completed":
                    _verify_committed_run(
                        output_root,
                        committed_item,
                        fit,
                        runtime_sha256,
                        train_matches,
                        validation_matches,
                        plan_sha256,
                        protocol_sha256,
                        device,
                    )
                    completed_ids.add(current_run_id)
                    ledger["completed_fit_count"] = int(ledger["completed_fit_count"]) + 1
                else:
                    ledger["failed_fit_count"] = int(ledger["failed_fit_count"]) + 1
                    ledger["status"] = "INCOMPLETE"
                attempt_history = cast(
                    dict[str, list[dict[str, object]]], ledger["attempt_history"]
                )
                attempt_history[current_run_id][-1].update(
                    status=(
                        "completed_output_commit_recovered"
                        if receipt["status"] == "completed"
                        else "failed_output_commit_recovered"
                    ),
                    receipt_sha256=committed_item["receipt_sha256"],
                    checkpoint_sha256=committed_item["checkpoint_sha256"],
                )
                cast(list[dict[str, object]], ledger["runs"]).append(committed_item)
                ledger["current_run_id"] = None
                ledger["current_attempt"] = None
                ledger["current_configuration_sha256"] = None
                _atomic_json(output_root / "campaign.json", ledger)
                if receipt["status"] != "completed":
                    return ledger
                current_run_id = None
            if current_run_id is not None and retry_interrupted_run != current_run_id:
                raise RuntimeError(
                    "retry requires --resume and the exact --retry-interrupted-run ID"
                )
            if current_run_id is not None and ledger.get("current_attempt") != 1:
                raise RuntimeError("the frozen retry allowance has already been used")
        if current_run_id is not None:
            attempt_history = cast(dict[str, list[dict[str, object]]], ledger["attempt_history"])
            previous = attempt_history[current_run_id][-1]
            oom_before = previous.get("oom_kill_count_before")
            oom_after = _cgroup_oom_kill_count()
            if oom_before is None or oom_after is None or oom_after > int(oom_before):
                raise RuntimeError("retry denied because OOM interruption cannot be excluded")
            if not retry_allowed("uncommitted", "external_worker_interruption", 1, True):
                raise RuntimeError("the frozen infrastructure retry conditions are not met")
            previous.update(
                status="external_worker_interruption_confirmed",
                confirmed_at_utc=datetime.now(UTC).isoformat(),
                cpu_seconds="not_observable_after_worker_interruption",
                oom_kill_count_after=oom_after,
            )
            interrupted = output_root / "runs" / "interrupted"
            interrupted.mkdir(mode=0o700, exist_ok=True)
            for partial in (output_root / "runs").glob(
                f".{current_run_id.replace('|', '--')}.*.partial"
            ):
                if partial.is_symlink():
                    raise ValueError("interrupted fit path cannot be a symlink")
                os.rename(partial, interrupted / f"{partial.name}.preserved")
            _fsync_directory(interrupted)
            retry_id = current_run_id
            ledger["current_run_id"] = None
            ledger["current_attempt"] = None
            ledger["current_configuration_sha256"] = None
            _atomic_json(output_root / "campaign.json", ledger)
        if current_run_id is None and retry_interrupted_run is not None:
            raise ValueError("retry ID does not match an uncommitted fit")

        if not fresh and ledger["status"] == "RES338_RESEARCH_FINAL_FITS_COMPLETE":
            return ledger
        if not fresh and ledger["status"] == "INCOMPLETE":
            raise RuntimeError("incomplete scientific campaign cannot be resumed")

        campaign_cpu_start = time.process_time()
        campaign_gpu_start: float | None = None
        if device == "cuda":
            gpu_started_at = cast(str | None, ledger.get("gpu_training_started_at_utc"))
            if gpu_started_at is None:
                gpu_started_at = datetime.now(UTC).isoformat()
                ledger["gpu_training_started_at_utc"] = gpu_started_at
                _atomic_json(output_root / "campaign.json", ledger)
            elapsed_gpu = max(
                0.0,
                (datetime.now(UTC) - datetime.fromisoformat(gpu_started_at)).total_seconds(),
            )
            campaign_gpu_start = time.monotonic() - elapsed_gpu
        newly_completed = 0
        for fit in configs:
            run_id = _fit_run_id(fit)
            if run_id in completed_ids:
                continue
            _verify_cached_inputs(output_root, cast(dict[str, object], cache_receipts))
            if hashlib.sha256(_canonical(configs)).hexdigest() != freeze.get(
                "configuration_sha256"
            ):
                raise ValueError("fit schedule changed after the frozen campaign manifest")
            attempt_number = 2 if run_id == retry_id else 1
            fit_cpu_budget = 0.25 * 3600 if attempt_number == 2 else FIT_CPU_BUDGET_SECONDS
            fit_gpu_wall_budget = (
                (
                    GPU_RETRY_WALL_BUDGET_SECONDS
                    if attempt_number == 2
                    else GPU_FIT_WALL_BUDGET_SECONDS
                )
                if device == "cuda"
                else 0.0
            )
            if time.monotonic() >= campaign_wall_start + CAMPAIGN_WALL_BUDGET_SECONDS:
                ledger["status"] = "INCOMPLETE"
                ledger["campaign_stop_reason"] = "campaign_wall_budget_exceeded"
                _refresh_resource_totals(ledger, freeze, campaign_wall_start, campaign_cpu_start)
                _atomic_json(output_root / "campaign.json", ledger)
                return ledger
            reserved = float(ledger["reserved_training_cpu_seconds"]) + fit_cpu_budget
            if reserved > CAMPAIGN_CPU_BUDGET_SECONDS:
                ledger["status"] = "INCOMPLETE"
                ledger["campaign_stop_reason"] = "campaign_training_cpu_budget_exceeded"
                _refresh_resource_totals(ledger, freeze, campaign_wall_start, campaign_cpu_start)
                _atomic_json(output_root / "campaign.json", ledger)
                return ledger
            reserved_gpu = float(ledger.get("reserved_gpu_wall_seconds", 0.0)) + fit_gpu_wall_budget
            if device == "cuda" and reserved_gpu > GPU_CAMPAIGN_BUDGET_SECONDS:
                ledger["status"] = "INCOMPLETE"
                ledger["campaign_stop_reason"] = "campaign_gpu_wall_budget_exceeded"
                _refresh_resource_totals(ledger, freeze, campaign_wall_start, campaign_cpu_start)
                _atomic_json(output_root / "campaign.json", ledger)
                return ledger
            config = _per_fit_config(
                cast(InformationRegime, fit["information_regime"]),
                cast(TargetRepresentation, fit["target_representation"]),
                int(fit["seed"]),
                train_matches,
                validation_matches,
                plan_sha256,
                protocol_sha256,
                device,
            )
            config_sha256 = hashlib.sha256(_canonical(config)).hexdigest()
            attempt_log = cast(dict[str, list[dict[str, object]]], ledger["attempt_history"])
            entries = attempt_log.setdefault(run_id, [])
            if len(entries) + 1 != attempt_number:
                raise ValueError("fit attempt count differs from the frozen retry policy")
            oom_count = _cgroup_oom_kill_count()
            entry = {
                "attempt_number": attempt_number,
                "status": "running",
                "started_at_utc": datetime.now(UTC).isoformat(),
                "cpu_budget_seconds": fit_cpu_budget,
                "gpu_wall_budget_seconds": fit_gpu_wall_budget if device == "cuda" else None,
                "oom_kill_count_before": oom_count,
                "configuration_sha256": config_sha256,
            }
            entries.append(entry)
            ledger["status"] = "RUNNING"
            ledger["current_run_id"] = run_id
            ledger["current_attempt"] = attempt_number
            ledger["current_configuration_sha256"] = config_sha256
            ledger["reserved_training_cpu_seconds"] = reserved
            ledger["reserved_gpu_wall_seconds"] = reserved_gpu
            _atomic_json(output_root / "campaign.json", ledger)

            receipt = _fit_one(
                run_root=output_root,
                cache_by_match=cache_by_match,
                train_matches=train_matches,
                validation_matches=validation_matches,
                regime=cast(InformationRegime, fit["information_regime"]),
                representation=cast(TargetRepresentation, fit["target_representation"]),
                seed=int(fit["seed"]),
                plan_sha256=plan_sha256,
                protocol_sha256=protocol_sha256,
                population_sha256=RESEARCH_MANIFEST_SHA256,
                target_mask_identity_sha256=target_mask_identity,
                environment_sha256=runtime_sha256,
                campaign_cpu_start=campaign_cpu_start,
                campaign_wall_start=campaign_wall_start,
                campaign_gpu_start=campaign_gpu_start,
                device=device,
                accelerator=cast(dict[str, object] | None, runtime.get("accelerator")),
                attempt_number=attempt_number,
                fit_cpu_budget_seconds=fit_cpu_budget,
                fit_gpu_wall_budget_seconds=(
                    fit_gpu_wall_budget if device == "cuda" else GPU_FIT_WALL_BUDGET_SECONDS
                ),
                worker_memory_limit_bytes=worker_memory_limit,
            )
            run_receipt_path = output_root / "runs" / run_id.replace("|", "--") / "receipt.json"
            entry.update(
                status=receipt["status"],
                fit_cpu_seconds=receipt["fit_cpu_seconds"],
                fit_wall_seconds=receipt["fit_wall_seconds"],
                peak_rss_bytes=receipt["peak_rss_bytes"],
                peak_gpu_memory_allocated_bytes=receipt.get("peak_gpu_memory_allocated_bytes"),
                gpu_wall_seconds=receipt.get("fit_wall_seconds") if device == "cuda" else None,
                stopping_reason=receipt["stopping_reason"],
                finished_at_utc=datetime.now(UTC).isoformat(),
            )
            ledger_runs = cast(list[dict[str, object]], ledger["runs"])
            ledger_runs.append(
                {
                    "run_id": run_id,
                    "status": receipt["status"],
                    "receipt_sha256": _sha256_file(run_receipt_path),
                    "checkpoint_sha256": receipt["checkpoint_sha256"],
                    "optimizer_steps": receipt["optimizer_steps"],
                    "fit_cpu_seconds": receipt["fit_cpu_seconds"],
                    "fit_wall_seconds": receipt["fit_wall_seconds"],
                    "peak_rss_bytes": receipt["peak_rss_bytes"],
                    "execution_device": receipt.get("execution_device", device),
                    "peak_gpu_memory_allocated_bytes": receipt.get(
                        "peak_gpu_memory_allocated_bytes"
                    ),
                    "stopping_reason": receipt["stopping_reason"],
                }
            )
            ledger["current_run_id"] = None
            ledger["current_attempt"] = None
            ledger["current_configuration_sha256"] = None
            _refresh_resource_totals(ledger, freeze, campaign_wall_start, campaign_cpu_start)
            if receipt["status"] == "completed":
                ledger["completed_fit_count"] = int(ledger["completed_fit_count"]) + 1
                completed_ids.add(run_id)
                newly_completed += 1
            else:
                ledger["failed_fit_count"] = int(ledger["failed_fit_count"]) + 1
                ledger["status"] = "INCOMPLETE"
                _atomic_json(output_root / "campaign.json", ledger)
                return ledger
            _atomic_json(output_root / "campaign.json", ledger)
            if max_new_fits is not None and newly_completed >= max_new_fits:
                if len(completed_ids) == 18:
                    ledger["status"] = "RES338_RESEARCH_FINAL_FITS_COMPLETE"
                    _refresh_resource_totals(
                        ledger, freeze, campaign_wall_start, campaign_cpu_start
                    )
                    ledger["fit_coverage"] = [str(item["run_id"]) for item in ledger["runs"]]
                    _atomic_json(output_root / "campaign.json", ledger)
                return ledger

        if len(completed_ids) != 18:
            ledger["status"] = "INCOMPLETE"
            _atomic_json(output_root / "campaign.json", ledger)
            return ledger
        ledger["status"] = "RES338_RESEARCH_FINAL_FITS_COMPLETE"
        _refresh_resource_totals(ledger, freeze, campaign_wall_start, campaign_cpu_start)
        ledger["fit_coverage"] = [str(item["run_id"]) for item in ledger["runs"]]
        _atomic_json(output_root / "campaign.json", ledger)
        return ledger
    except Exception as exc:
        if (
            fresh
            and output_root.exists()
            and not (output_root / "reproducibility-manifest.json").exists()
        ):
            failure: dict[str, object] = {
                "schema_id": "fpdbench.res338-preparation-failure",
                "schema_version": "1.0.0",
                "status": "INCOMPLETE",
                "failure_type": type(exc).__name__,
                "failure_message": str(exc)[:1000],
                "research_manifest_sha256": RESEARCH_MANIFEST_SHA256,
                "training_fit_count": 0,
            }
            if preparation_cpu_start is not None:
                failure["preparation_cpu_seconds"] = round(
                    time.process_time() - preparation_cpu_start, 6
                )
            try:
                _atomic_json(output_root / "preparation-failure.json", failure)
            except OSError:
                pass
        raise
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("research_root", type=Path, nargs="?", default=RESEARCH_ROOT_DEFAULT)
    parser.add_argument("source_root", type=Path, nargs="?", default=SOURCE_ROOT_DEFAULT)
    parser.add_argument(
        "output_root",
        type=Path,
        nargs="?",
        default=Path("/srv/fpdbench-private/evidence/res338-final-fits-v1"),
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--retry-interrupted-run")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--research-scope", choices=("full", "training-validation"), default="full")
    parser.add_argument("--reference-manifest", type=Path)
    parser.add_argument("--reference-manifest-sha256")
    parser.add_argument("--preloaded-cache-root", type=Path)
    parser.add_argument("--toy-preflight", type=Path)
    parser.add_argument("--max-new-fits", type=int)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    if args.retry_interrupted_run and not args.resume:
        parser.error("--retry-interrupted-run requires --resume")
    result = run_campaign(
        args.research_root,
        args.source_root,
        args.output_root,
        resume=args.resume,
        retry_interrupted_run=args.retry_interrupted_run,
        device=args.device,
        research_scope=args.research_scope,
        reference_manifest_path=args.reference_manifest,
        reference_manifest_sha256=args.reference_manifest_sha256,
        preloaded_cache_root=args.preloaded_cache_root,
        toy_preflight_path=args.toy_preflight,
        max_new_fits=args.max_new_fits,
        prepare_only=args.prepare_only,
    )
    print(json.dumps(result, sort_keys=True))
    if (
        result["status"] != "RES338_RESEARCH_FINAL_FITS_COMPLETE"
        and not (args.prepare_only and result["status"] == "PREPARED")
        and not (args.max_new_fits is not None and result["status"] == "RUNNING")
    ):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
