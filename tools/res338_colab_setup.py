"""Clone the pinned development head and build its exact CUDA worker environment."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path("/content/res338")
REPOSITORY_URL = "https://github.com/Litju/football-performance-dynamics-bench.git"
PYPI_INDEX = "https://pypi.org/simple"
VENV_PYTHON = ROOT / "venv" / "bin" / "python"
REFERENCE = ROOT / "manifests" / "training-validation-reference.json"
RUNTIME_MANIFEST = ROOT / "runtime" / "gpu-runtime.json"


def _run(
    command: Sequence[str], *, env: dict[str, str] | None = None, cwd: Path | None = None
) -> str:
    result = subprocess.run(
        list(command),
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    return result.stdout.strip()


def _private_directory(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)


def setup() -> dict[str, object]:
    os.umask(0o077)
    code_sha = os.environ.get("RES338_CODE_SHA")
    reference_sha = os.environ.get("RES338_REFERENCE_SHA256")
    if not code_sha or not reference_sha or len(code_sha) != 40 or len(reference_sha) != 64:
        raise ValueError("pinned code and training-validation reference hashes are required")
    for path in (
        ROOT,
        ROOT / "manifests",
        ROOT / "runtime",
        ROOT / "logs",
        ROOT / "evidence",
        ROOT / "cache-archives",
        ROOT / "transfer" / "chunks",
        ROOT / "preloaded-cache",
    ):
        _private_directory(path)
    if (
        not REFERENCE.is_file()
        or hashlib.sha256(REFERENCE.read_bytes()).hexdigest() != reference_sha
    ):
        raise ValueError("staged training-validation reference does not match its SHA-256")
    REFERENCE.chmod(0o600)

    repo = ROOT / "repo"
    if repo.exists():
        current = _run(["git", "rev-parse", "HEAD"], cwd=repo)
        if current != code_sha:
            raise RuntimeError("existing Colab checkout differs from the pinned campaign head")
    else:
        _run(["git", "clone", "--no-checkout", REPOSITORY_URL, str(repo)])
        _run(["git", "fetch", "--no-tags", "origin", code_sha], cwd=repo)
        _run(["git", "checkout", "--detach", code_sha], cwd=repo)
    if _run(["git", "rev-parse", "HEAD"], cwd=repo) != code_sha:
        raise RuntimeError("Colab repository checkout did not reach the exact pinned head")

    uv = shutil.which("uv")
    if not uv:
        _run([sys.executable, "-m", "pip", "install", "--quiet", "uv"])
        uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("uv installation did not provide its command")
    env = os.environ.copy()
    env.update(
        UV_CACHE_DIR=str(ROOT / "uv-cache"),
        UV_PYTHON_INSTALL_DIR=str(ROOT / "python"),
        CUBLAS_WORKSPACE_CONFIG=":4096:8",
        RES338_COLAB_SESSION_NAME=os.environ.get("RES338_COLAB_SESSION_NAME", ""),
        RES338_COLAB_SESSION_ID=os.environ.get("RES338_COLAB_SESSION_ID", ""),
    )
    _private_directory(ROOT / "uv-cache")
    _private_directory(ROOT / "python")
    _run([uv, "python", "install", "3.12.8"], env=env)
    if not VENV_PYTHON.exists():
        _run([uv, "venv", "--python", "3.12.8", str(ROOT / "venv")], env=env)
    _run(
        [
            uv,
            "pip",
            "install",
            "--python",
            str(VENV_PYTHON),
            "--disable-pip-version-check",
            "--index-url",
            PYPI_INDEX,
            "-r",
            str(repo / "tools/res338_colab_gpu_requirements.txt"),
        ],
        env=env,
    )
    _run(
        [
            str(VENV_PYTHON),
            str(repo / "tools/res338_colab_gpu_probe.py"),
            "--output",
            str(RUNTIME_MANIFEST),
        ],
        env=env,
        cwd=repo,
    )
    runtime = json.loads(RUNTIME_MANIFEST.read_text())
    if (
        runtime.get("python") != "3.12.8"
        or runtime.get("numpy") != "2.2.4"
        or runtime.get("torch") != "2.6.0+cu124"
        or runtime.get("torch_cuda_runtime") != "12.4"
        or runtime.get("gpu_count") != 1
    ):
        raise RuntimeError("pinned Colab GPU environment failed verification")
    summary = {
        "status": "ENVIRONMENT_VERIFIED",
        "code_sha": code_sha,
        "reference_sha256": reference_sha,
        "python": runtime["python"],
        "numpy": runtime["numpy"],
        "torch": runtime["torch"],
        "cuda": runtime["torch_cuda_runtime"],
        "gpu": runtime["gpu"],
        "session": {
            "name": runtime["session_name"],
            "id": runtime["session_id"],
        },
        "runtime_manifest_sha256": hashlib.sha256(RUNTIME_MANIFEST.read_bytes()).hexdigest(),
    }
    print(json.dumps(summary, sort_keys=True))
    return summary


if __name__ == "__main__":
    setup()
