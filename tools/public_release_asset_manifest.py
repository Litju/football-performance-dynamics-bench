"""Generate a candidate-only SHA-256 manifest for already-public aggregate-safe assets.

This program does not publish, redistribute, archive, sign or qualify any scientific data.
No raw provider rows, checkpoints, predictions, private receipts or protected truth are read.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ASSETS = (
    ("docs/res440/findings.json", "public_non_reconstructive_aggregate"),
    ("docs/res440/results.md", "public_scientific_report"),
    ("docs/res440/tables.md", "public_aggregate_tables"),
    ("docs/res440/errors.svg", "public_non_reconstructive_figure"),
    ("docs/res440/contrasts.svg", "public_non_reconstructive_figure"),
    ("docs/res440/horizon.svg", "public_non_reconstructive_figure"),
    ("docs/res440/errors.pdf", "public_non_reconstructive_figure"),
    ("docs/res440/contrasts.pdf", "public_non_reconstructive_figure"),
    ("docs/res440/horizon.pdf", "public_non_reconstructive_figure"),
    ("docs/res440/errors.png", "public_non_reconstructive_figure"),
    ("docs/res440/contrasts.png", "public_non_reconstructive_figure"),
    ("docs/res440/horizon.png", "public_non_reconstructive_figure"),
)
FORBIDDEN_SUFFIXES = {".ckpt", ".pt", ".pth", ".npy", ".npz", ".parquet", ".csv", ".jsonl"}
RIGHTS = {
    "project_original_code": "Apache-2.0, conditional on rightsholder approval for formal release",
    "skillcorner_core_data": "NO_REDISTRIBUTION_WITHOUT_WRITTEN_CLEARANCE",
    "row_level_derivatives": "NO_REDISTRIBUTION_WITHOUT_WRITTEN_CLEARANCE",
    "private_checkpoints_and_receipts": "NOT_INCLUDED_NO_PUBLIC_GRANT",
    "aggregate_safe_existing_public_artifacts": "CANDIDATE_UNDER_EXISTING_PUBLIC_POLICY",
}


def git(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout


def safe_path(root: Path, relative: str) -> Path:
    """Forbid path traversal, links, unexpected locations and sensitive extensions."""
    part = Path(relative)
    if part.is_absolute() or ".." in part.parts or len(part.parts) < 3:
        raise ValueError("invalid public artifact path")
    if part.parts[:2] != ("docs", "res440") or part.suffix.lower() in FORBIDDEN_SUFFIXES:
        raise ValueError("non-public or restricted artifact path")
    root = root.resolve(strict=True)
    target = root / part
    if not target.is_file():
        raise ValueError("missing public artifact")
    if any(p.is_symlink() for p in (target, *target.parents) if p != root):
        raise ValueError("artifact symlink is not allowed")
    if not target.resolve(strict=True).is_relative_to(root):
        raise ValueError("artifact escapes checkout")
    return target


def generate(root: Path = ROOT) -> dict[str, Any]:
    """Bind named public aggregates to bytes in a clean Git checkout; never upload them."""
    root = root.resolve(strict=True)
    head = git(root, "rev-parse", "HEAD").decode().strip()
    if len(head) != 40 or any(ch not in "0123456789abcdef" for ch in head):
        raise ValueError("invalid Git source SHA")
    tracked = {
        path.decode("utf-8", errors="surrogateescape")
        for path in git(root, "ls-files", "-z", "--", "docs/res440").split(b"\0")
        if path
    }
    entries: list[dict[str, object]] = []
    for relative, category in ASSETS:
        if relative not in tracked:
            raise ValueError(f"candidate asset is not tracked: {relative}")
        target = safe_path(root, relative)
        if git(root, "diff", "--name-only", "HEAD", "--", relative):
            raise ValueError(f"candidate asset differs from the source commit: {relative}")
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        entries.append(
            {
                "path": relative,
                "rights_class": category,
                "bytes": target.stat().st_size,
                "sha256": digest,
            }
        )
    entries.sort(key=lambda value: str(value["path"]))
    canonical = "\n".join(
        json.dumps(entry, sort_keys=True, separators=(",", ":")) for entry in entries
    ).encode() + b"\n"
    return {
        "schema": "fpdbench.public-release-asset-candidate/1",
        "status": "CANDIDATE_ONLY_NOT_PUBLISHED",
        "release_authorized": False,
        "protected_population": "NOT_QUALIFIED",
        "source_commit": head,
        "data_provider": "SkillCorner Open Data (SkillCorner / PySport)",
        "source_revision": "4340d274572876239c154c90bc507a9b3250a656",
        "rights": RIGHTS,
        "entries_sha256": hashlib.sha256(canonical).hexdigest(),
        "entries": entries,
    }


def main() -> int:
    print(json.dumps(generate(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
