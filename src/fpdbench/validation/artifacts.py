"""Guard against restricted data, credentials, checkpoints, and oversized files."""

import re
import subprocess
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
_GENERATED_SITE_DIRS = frozenset(
    {
        ("site", "node_modules"),
        ("site", "dist"),
        ("site", "qa"),
        ("site", ".vercel"),
    }
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


def ignored_generated_site_dirs(root: Path) -> frozenset[tuple[str, str]]:
    """Ignore untracked frontend output, but never files force-added to Git.

    A missing Git index or a failed Git check means no exclusions (fail closed).
    Site dependencies are not a public release artifact or part of source validation.
    """
    if not (root / ".git").exists():
        return frozenset()
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "ls-files",
                "--cached",
                "-z",
                "--",
                "site/node_modules",
                "site/dist",
                "site/qa",
                "site/.vercel",
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return frozenset()
    tracked_roots: set[tuple[str, str]] = set()
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        parts = Path(raw.decode("utf-8", errors="surrogateescape")).parts
        if len(parts) >= 2:
            tracked_roots.add((parts[0], parts[1]))
    return _GENERATED_SITE_DIRS.difference(tracked_roots)


def ignored_generated_site_path(
    relative: Path, ignored_roots: frozenset[tuple[str, str]]
) -> bool:
    """Only an exact generated site subtree may be excluded from scanning."""
    return len(relative.parts) >= 2 and relative.parts[:2] in ignored_roots


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
    ignored_site_dirs = ignored_generated_site_dirs(root)
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        display = relative.as_posix()
        if any(part in _IGNORED_PARTS for part in relative.parts):
            continue
        if ignored_generated_site_path(relative, ignored_site_dirs) and (
            len(relative.parts) > 2 or not path.is_symlink()
        ):
            continue
        if path.is_symlink():
            errors.append(f"symlink is not allowed in the bootstrap repository: {display}")
            continue
        if not path.is_file():
            continue
        name = path.name.casefold()
        if _restricted_data_path(relative):
            errors.append(f"SkillCorner source or derived data is not allowed here: {display}")
        if _git_lfs_pointer(path):
            errors.append(f"Git LFS dataset pointer is not allowed: {display}")
        if path.suffix.casefold() in _FORBIDDEN_SUFFIXES:
            errors.append(f"data or checkpoint artifact is not allowed: {display}")
        if path.suffix.casefold() == ".pb" and _model_binary_path(relative):
            errors.append(f"model protobuf artifact is not allowed: {display}")
        if path.suffix.casefold() == ".bin" and _model_binary_path(relative):
            errors.append(f"model or checkpoint binary is not allowed: {display}")
        if name in _SECRET_NAMES or path.suffix.casefold() in {".key", ".pem"}:
            errors.append(f"secret-like file is not allowed: {display}")
        if any(part.casefold() in _FORBIDDEN_NAME_PARTS for part in relative.parts):
            errors.append(f"private or challenge artifact path is not allowed: {display}")
        if path.stat().st_size > max_file_bytes:
            errors.append(f"file exceeds {max_file_bytes} bytes: {display}")
    return tuple(sorted(set(errors)))
