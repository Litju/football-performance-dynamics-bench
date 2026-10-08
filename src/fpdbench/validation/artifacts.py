"""Guard against restricted data, credentials, checkpoints, and oversized files."""

import re
from pathlib import Path

MAX_ARTIFACT_BYTES = 10 * 1024 * 1024
_FORBIDDEN_SUFFIXES = frozenset(
    {
        ".arrow",
        ".ckpt",
        ".csv",
        ".feather",
        ".joblib",
        ".npy",
        ".npz",
        ".safetensors",
        ".onnx",
        ".parquet",
        ".pkl",
        ".pt",
        ".pth",
        ".h5",
        ".hdf5",
        ".keras",
        ".jsonl",
        ".sqlite",
        ".tsv",
    }
)
_FORBIDDEN_NAME_PARTS = frozenset({"challenge", "private", "truth_data"})
_IGNORED_PARTS = frozenset(
    {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".pyright"}
)
# This sample is explicitly MIT-licensed; the core data files have unresolved scope.
_ALLOWED_DATA_FILES = frozenset(
    {
        Path("data/bodypose/README.md"),
        Path("data/bodypose/MANIFEST.json"),
        Path("data/bodypose/sample_1925299_phase406.jsonl.gz"),
    }
)
_SECRET_NAMES = frozenset({".env", "id_rsa", "credentials.json", "secrets.json"})
_MODEL_PATH_PARTS = frozenset(
    {"model", "models", "checkpoint", "checkpoints", "weights", "saved_model"}
)
_MODEL_NAME = re.compile(r"(?:^|[._-])(?:model|checkpoint|weights|saved_model)(?:$|[._-])", re.I)


def _model_binary_path(relative: Path) -> bool:
    return any(
        part.casefold() in _MODEL_PATH_PARTS or _MODEL_NAME.search(part) is not None
        for part in relative.parts
    )


def _restricted_data_path(relative: Path) -> bool:
    return relative.parts[:1] == ("data",) and relative not in _ALLOWED_DATA_FILES


def _git_lfs_pointer(path: Path) -> bool:
    with path.open("rb") as stream:
        return stream.readline(128).startswith(b"version https://git-lfs.github.com/spec/v1")


def validate_artifacts(root: Path, *, max_file_bytes: int = MAX_ARTIFACT_BYTES) -> tuple[str, ...]:
    errors: list[str] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if any(part in _IGNORED_PARTS for part in relative.parts):
            continue
        if path.is_symlink():
            errors.append(f"symlink is not allowed in the bootstrap repository: {relative}")
            continue
        if not path.is_file():
            continue
        name = path.name.casefold()
        if _restricted_data_path(relative):
            errors.append(f"SkillCorner source or derived data is not allowed here: {relative}")
        if _git_lfs_pointer(path):
            errors.append(f"Git LFS dataset pointer is not allowed: {relative}")
        if path.suffix.casefold() in _FORBIDDEN_SUFFIXES:
            errors.append(f"data or checkpoint artifact is not allowed: {relative}")
        if path.suffix.casefold() == ".pb" and _model_binary_path(relative):
            errors.append(f"model protobuf artifact is not allowed: {relative}")
        if path.suffix.casefold() == ".bin" and _model_binary_path(relative):
            errors.append(f"model or checkpoint binary is not allowed: {relative}")
        if name in _SECRET_NAMES or path.suffix.casefold() in {".key", ".pem"}:
            errors.append(f"secret-like file is not allowed: {relative}")
        if any(part.casefold() in _FORBIDDEN_NAME_PARTS for part in relative.parts):
            errors.append(f"private or challenge artifact path is not allowed: {relative}")
        if path.stat().st_size > max_file_bytes:
            errors.append(f"file exceeds {max_file_bytes} bytes: {relative}")
    return tuple(sorted(set(errors)))
