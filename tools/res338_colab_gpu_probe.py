"""Record and require one real Colab CUDA GPU without emitting private data."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import torch

OUTPUT = Path("/content/res338/runtime/gpu-probe.json")


def _memory_info() -> dict[str, int]:
    values: dict[str, int] = {}
    with Path("/proc/meminfo").open(encoding="ascii") as stream:
        for line in stream:
            name, raw = line.split(":", maxsplit=1)
            if name in {"MemTotal", "MemAvailable"}:
                values[name] = int(raw.split()[0]) * 1024
    return {
        "total_bytes": values["MemTotal"],
        "available_bytes": values["MemAvailable"],
    }


def probe(output: Path = OUTPUT) -> dict[str, object]:
    os.umask(0o077)
    root = Path("/content/res338")
    for directory in (
        root,
        root / "manifests",
        root / "logs",
        root / "evidence",
        root / "cache-archives",
        root / "preloaded-cache",
    ):
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        directory.chmod(0o700)
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        raise RuntimeError("nvidia-smi is unavailable; refusing a CPU fallback")
    rows = (
        subprocess.check_output(
            [
                nvidia_smi,
                "--query-gpu=index,name,memory.total,memory.free,driver_version",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=10,
        )
        .strip()
        .splitlines()
    )
    if len(rows) != 1 or not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise RuntimeError("this campaign requires exactly one available Colab NVIDIA GPU")
    index, name, memory_total_mib, memory_free_mib, driver = (
        item.strip() for item in rows[0].split(",")
    )
    if index != "0" or torch.cuda.get_device_name(0) != name:
        raise RuntimeError("nvidia-smi and PyTorch disagree on the assigned GPU")
    free_bytes, total_bytes = torch.cuda.mem_get_info(0)
    if total_bytes != int(memory_total_mib) * 1024**2:
        raise RuntimeError("PyTorch and nvidia-smi disagree on total GPU memory")
    probe_result = {
        "schema_id": "fpdbench.res338.colab-gpu-probe",
        "schema_version": "1.0.0",
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "status": "GPU_ALLOCATED",
        "session_name": os.environ.get("RES338_COLAB_SESSION_NAME"),
        "session_id": os.environ.get("RES338_COLAB_SESSION_ID"),
        "colab_release_tag": os.environ.get("COLAB_RELEASE_TAG"),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "torch": torch.__version__,
        "torch_cuda_runtime": torch.version.cuda,
        "cuda_available": torch.cuda.is_available(),
        "gpu_count": torch.cuda.device_count(),
        "gpu": {
            "index": int(index),
            "name": name,
            "driver_version": driver,
            "total_memory_bytes": total_bytes,
            "available_memory_bytes": free_bytes,
            "capability": list(torch.cuda.get_device_capability(0)),
        },
        "system_memory": _memory_info(),
        "local_disk": {
            "total_bytes": shutil.disk_usage("/content").total,
            "available_bytes": shutil.disk_usage("/content").free,
            "filesystem": subprocess.check_output(
                ["/usr/bin/stat", "-f", "-c", "%T", "/content"], text=True, timeout=10
            ).strip(),
        },
        "cpu_affinity": sorted(os.sched_getaffinity(0)),
    }
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    output.parent.chmod(0o700)
    payload = json.dumps(probe_result, sort_keys=True, separators=(",", ":")).encode()
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps(probe_result, sort_keys=True))
    return probe_result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    probe(args.output)
