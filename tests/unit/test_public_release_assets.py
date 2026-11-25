"""A public manifest must bind exact committed aggregates, not local or protected inputs."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "tools/public_release_asset_manifest.py"
SPEC = importlib.util.spec_from_file_location("public_release_assets", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def fixture_repo(root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = root / "docs" / "res440" / "findings.json"
    target.parent.mkdir(parents=True)
    target.write_text('{"synthetic_only": true}\n', encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "docs/res440/findings.json"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Research Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "Synthetic public manifest fixture",
        ],
        check=True,
    )
    monkeypatch.setattr(
        module,
        "ASSETS",
        (("docs/res440/findings.json", "public_non_reconstructive_aggregate"),),
    )
    return target


def test_candidate_manifest_is_reproducible_and_never_authorizes_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture_repo(tmp_path, monkeypatch)
    first = module.generate(tmp_path)
    second = module.generate(tmp_path)
    assert first == second
    assert first["status"] == "CANDIDATE_ONLY_NOT_PUBLISHED"
    assert first["release_authorized"] is False
    assert first["protected_population"] == "NOT_QUALIFIED"
    assert len(first["entries"]) == 1
    assert len(first["entries"][0]["sha256"]) == 64
    assert len(first["entries_sha256"]) == 64


def test_mutated_tracked_public_asset_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = fixture_repo(tmp_path, monkeypatch)
    target.write_text('{"changed": true}\n')
    with pytest.raises(ValueError, match="differs from the source commit"):
        module.generate(tmp_path)


def test_untracked_candidate_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture_repo(tmp_path, monkeypatch)
    target = tmp_path / "docs" / "res440" / "untracked.svg"
    target.write_text("synthetic")
    monkeypatch.setattr(module, "ASSETS", (("docs/res440/untracked.svg", "public_figure"),))
    with pytest.raises(ValueError, match="not tracked"):
        module.generate(tmp_path)


@pytest.mark.parametrize(
    "filename", ["../upstream.csv", "docs/res440/checkpoint.pt", "/tmp/private.jsonl"]
)
def test_restricted_or_escaping_paths_fail(tmp_path: Path, filename: str) -> None:
    with pytest.raises(ValueError, match="invalid public artifact|restricted artifact"):
        module.safe_path(tmp_path, filename)


def test_public_asset_symlink_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture_repo(tmp_path, monkeypatch)
    source = tmp_path / "docs" / "res440" / "findings.json"
    source.rename(tmp_path / "separate.json")
    source.symlink_to(tmp_path / "separate.json")
    with pytest.raises(ValueError, match="symlink"):
        module.safe_path(tmp_path, "docs/res440/findings.json")


def test_real_repository_candidate_manifest_binds_existing_public_assets() -> None:
    """A release manifest must cover the actual public Git artifacts, not only toy fixtures."""
    root = Path(__file__).resolve().parents[2]
    if not (root / ".git").exists():
        pytest.skip("candidate release-manifest audit requires a Git checkout")
    manifest = module.generate(root)
    assert manifest["release_authorized"] is False
    assert manifest["status"] == "CANDIDATE_ONLY_NOT_PUBLISHED"
    assert manifest["protected_population"] == "NOT_QUALIFIED"
    assert len(manifest["entries"]) == 12
    actual_paths = {entry["path"] for entry in manifest["entries"]}
    expected_paths = {name for name, _ in module.ASSETS}
    assert actual_paths == expected_paths
    assert all(entry["bytes"] > 0 for entry in manifest["entries"])
    assert all(len(entry["sha256"]) == 64 for entry in manifest["entries"])
    assert manifest["source_commit"] == module.git(root, "rev-parse", "HEAD").decode().strip()
