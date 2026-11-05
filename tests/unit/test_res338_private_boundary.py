"""Synthetic rejection checks for private inputs and manifests."""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
from train_res338_final_fits import read_private_file  # noqa: E402


def test_private_manifest_requires_exact_digest_and_private_mode(tmp_path) -> None:
    manifest = tmp_path / "research-admission.json"
    manifest.write_bytes(b'{"status":"RESEARCH_RECONCILED"}')
    os.chmod(manifest, 0o600)
    expected = hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert read_private_file(manifest, expected) == manifest.read_bytes()
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        read_private_file(manifest, "0" * 64)

    os.chmod(manifest, 0o644)
    with pytest.raises(ValueError, match="0600"):
        read_private_file(manifest, expected)


def test_private_manifest_and_source_roots_reject_symlinks(tmp_path) -> None:
    from fpdbench.data_sources import protected_skillcorner as source

    target = tmp_path / "real"
    target.mkdir(mode=0o700)
    manifest = target / "manifest.json"
    manifest.write_bytes(b"{}")
    os.chmod(manifest, 0o600)
    link = tmp_path / "manifest-link.json"
    link.symlink_to(manifest)
    with pytest.raises(OSError):
        read_private_file(link, hashlib.sha256(b"{}").hexdigest())

    root_link = tmp_path / "source-link"
    root_link.symlink_to(target, target_is_directory=True)
    with pytest.raises(OSError):
        with source.private_directory(root_link):
            pass
