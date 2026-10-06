"""Guard against private datasets, credentials, checkpoints, and oversized files."""

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
        ".parquet",
        ".pkl",
        ".pt",
        ".pth",
        ".sqlite",
        ".tsv",
    }
)
_FORBIDDEN_NAME_PARTS = frozenset({"challenge", "private", "truth_data"})
_IGNORED_PARTS = frozenset(
    {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".pyright"}
)
_SECRET_NAMES = frozenset({".env", "id_rsa", "credentials.json", "secrets.json"})


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
        if path.suffix.casefold() in _FORBIDDEN_SUFFIXES:
            errors.append(f"data or checkpoint artifact is not allowed: {relative}")
        if name in _SECRET_NAMES or path.suffix.casefold() in {".key", ".pem"}:
            errors.append(f"secret-like file is not allowed: {relative}")
        if any(part.casefold() in _FORBIDDEN_NAME_PARTS for part in relative.parts):
            errors.append(f"private or challenge artifact path is not allowed: {relative}")
        if path.stat().st_size > max_file_bytes:
            errors.append(f"file exceeds {max_file_bytes} bytes: {relative}")
    return tuple(sorted(set(errors)))
