"""Reject historical administrative identifiers outside structured provenance values."""

import ast
import re
from pathlib import Path

FORBIDDEN_PATH_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"ALI[-_]?[0-9]+",
        r"BM[-_]?[0-9]+",
        r"SB[-_]?R0(?:[-_][A-Z0-9]+)*",
        r"SC[-_]?R0(?:[-_][A-Z0-9]+)*",
        r"H[0-9]+F[0-9]+",
        "R7" + "D",
        "R7" + "E",
        r"RES-[0-9]+",
        "soccer-trainingload-" + "bmcb",
    )
)
_OBSOLETE_IDENTITIES = ("Dynamis " + "Soccer", "Association Football " + "Performance Modeling")
_IGNORED_PARTS = frozenset(
    {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".pyright"}
)


def _ignored(path: Path) -> bool:
    return any(part in _IGNORED_PARTS for part in path.parts)


def _python_provenance_value_spans(source: str) -> tuple[tuple[int, int], ...]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ()
    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))

    def absolute(line_number: int, byte_column: int) -> int:
        line = lines[line_number - 1]
        prefix = line.encode("utf-8")[:byte_column].decode("utf-8")
        return offsets[line_number - 1] + len(prefix)

    spans: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function_name = (
            node.func.id
            if isinstance(node.func, ast.Name)
            else node.func.attr
            if isinstance(node.func, ast.Attribute)
            else ""
        )
        if function_name != "HistoricalAlias":
            continue
        for keyword in node.keywords:
            value = keyword.value
            if (
                keyword.arg == "value"
                and isinstance(value, ast.Constant)
                and isinstance(value.value, str)
                and value.end_lineno is not None
                and value.end_col_offset is not None
            ):
                spans.append(
                    (
                        absolute(value.lineno, value.col_offset),
                        absolute(value.end_lineno, value.end_col_offset),
                    )
                )
    return tuple(spans)


def validate_naming(root: Path) -> tuple[str, ...]:
    errors: list[str] = []
    if any(pattern.search(root.name) for pattern in FORBIDDEN_PATH_PATTERNS):
        errors.append(f"forbidden canonical path component: {root.name}")
    for path in root.rglob("*"):
        if _ignored(path):
            continue
        relative = path.relative_to(root)
        if any(pattern.search(path.name) for pattern in FORBIDDEN_PATH_PATTERNS):
            errors.append(f"forbidden canonical path component: {relative}")
        if not path.is_file():
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        provenance_spans = (
            _python_provenance_value_spans(source) if path.suffix.casefold() == ".py" else ()
        )
        lowered_source = source.casefold()
        if any(identity.casefold() in lowered_source for identity in _OBSOLETE_IDENTITIES):
            errors.append(f"obsolete project identity in canonical content: {relative}")
        for pattern in FORBIDDEN_PATH_PATTERNS:
            for match in pattern.finditer(source):
                if not any(
                    start <= match.start() and match.end() <= end for start, end in provenance_spans
                ):
                    errors.append(
                        f"historical identifier outside structured provenance value in "
                        f"{relative}: {match.group()}"
                    )
    return tuple(sorted(set(errors)))
