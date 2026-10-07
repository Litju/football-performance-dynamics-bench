import hashlib
import json
import os
from pathlib import Path

import pytest

from fpdbench.provenance.registry_digest import registry_content_digest


def test_registry_digest_normalizes_paths_excludes_git_and_hashes_symlinks(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "ignored").write_bytes(b"ignored")
    (tmp_path / ".hidden").write_bytes(b"hidden")
    (tmp_path / "visible").write_bytes(b"evidence")
    (tmp_path / "e\u0301.txt").write_bytes(b"unicode")
    os.symlink("visible", tmp_path / "link")

    digest, count = registry_content_digest(tmp_path)
    records = [
        {
            "kind": "file",
            "path": ".hidden",
            "sha256": hashlib.sha256(b"hidden").hexdigest(),
        },
        {
            "kind": "symlink",
            "path": "link",
            "sha256": hashlib.sha256(b"visible").hexdigest(),
        },
        {
            "kind": "file",
            "path": "visible",
            "sha256": hashlib.sha256(b"evidence").hexdigest(),
        },
        {
            "kind": "file",
            "path": "\u00e9.txt",
            "sha256": hashlib.sha256(b"unicode").hexdigest(),
        },
    ]
    records.sort(key=lambda record: record["path"].encode("utf-8"))
    manifest = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for record in records
    ).encode("utf-8")

    assert count == 4
    assert digest == hashlib.sha256(manifest).hexdigest()


def test_registry_root_must_not_be_a_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    root_link = tmp_path / "root-link"
    os.symlink(target, root_link, target_is_directory=True)

    with pytest.raises(ValueError, match="must not be a symlink"):
        registry_content_digest(root_link)
