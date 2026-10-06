"""Reject administrative history labels from canonical paths and source modules."""

import re
from pathlib import Path

FORBIDDEN_PATH_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"ALI[-_]?[0-9]+",
        r"BM[-_]?[0-9]+",
        r"SB[-_]?R0",
        r"SC[-_]?R0",
        r"H[0-9]+F[0-9]+",
        r"R7D",
        r"R7E",
        r"RES-[0-9]+",
        r"soccer-trainingload-bmcb",
    )
)
_OBSOLETE_NAMES = (
    "Dynamis " + "Soccer",
    "Association Football " + "Performance Modeling",
    "soccer-trainingload-" + "bmcb",
)
_IGNORED_PARTS = frozenset(
    {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".pyright"}
)


def _ignored(path: Path) -> bool:
    return any(part in _IGNORED_PARTS for part in path.parts)


def validate_naming(root: Path) -> tuple[str, ...]:
    errors: list[str] = []
    for path in root.rglob("*"):
        if _ignored(path):
            continue
        relative = path.relative_to(root)
        for component in relative.parts:
            if any(pattern.search(component) for pattern in FORBIDDEN_PATH_PATTERNS):
                errors.append(f"forbidden canonical path component: {relative}")
                break
        if not path.is_file() or path.suffix != ".py":
            continue
        if relative.parts[:2] != ("src", "fpdbench"):
            continue
        if "provenance" in relative.parts or relative.as_posix().endswith("validation/naming.py"):
            continue
        source = path.read_text(errors="replace").casefold()
        if any(name.casefold() in source for name in _OBSOLETE_NAMES):
            errors.append(f"obsolete project identity in canonical source: {relative}")
    return tuple(sorted(set(errors)))
