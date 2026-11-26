"""A release bundle must contain only approved, unambiguous distribution archives."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FILE = ROOT / "tools" / "select_release_distributions.py"
SPEC = importlib.util.spec_from_file_location("release_distributions", FILE)
assert SPEC is not None and SPEC.loader is not None
selector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(selector)

WHEEL = "football_performance_dynamics_bench-1.0.0-py3-none-any.whl"
SDIST = "football_performance_dynamics_bench-1.0.0.tar.gz"


def make_distribution(tmp_path: Path) -> Path:
    directory = tmp_path / "dist"
    directory.mkdir()
    (directory / WHEEL).write_bytes(b"synthetic wheel")
    (directory / SDIST).write_bytes(b"synthetic sdist")
    return directory


def test_extra_non_distribution_entries_do_not_block_release(tmp_path: Path) -> None:
    """Reproduce the release failure: two archives plus incidental build output."""
    directory = make_distribution(tmp_path)
    (directory / ".gitignore").write_text("*\n")
    (directory / "other-build-output").mkdir()
    wheel, sdist = selector.select_distribution_artifacts(directory, version="1.0.0")
    assert [wheel.name, sdist.name] == [WHEEL, SDIST]
    assert wheel.is_file() and sdist.is_file()


def test_extra_old_version_archive_fails_closed(tmp_path: Path) -> None:
    directory = make_distribution(tmp_path)
    (directory / "football_performance_dynamics_bench-0.1.0-py3-none-any.whl").touch()
    with pytest.raises(ValueError, match="unexpected distribution archives"):
        selector.select_distribution_artifacts(directory, version="1.0.0")


def test_extra_other_package_archive_fails_closed(tmp_path: Path) -> None:
    directory = make_distribution(tmp_path)
    (directory / "other_package-1.0.0.tar.gz").touch()
    with pytest.raises(ValueError, match="unexpected distribution archives"):
        selector.select_distribution_artifacts(directory, version="1.0.0")


def test_multiple_matching_wheels_fail_closed(tmp_path: Path) -> None:
    directory = make_distribution(tmp_path)
    (directory / "football_performance_dynamics_bench-1.0.0-cp312-none-any.whl").touch()
    with pytest.raises(ValueError, match="expected one wheel"):
        selector.select_distribution_artifacts(directory, version="1.0.0")


def test_missing_distribution_fails_closed(tmp_path: Path) -> None:
    directory = make_distribution(tmp_path)
    (directory / SDIST).unlink()
    with pytest.raises(ValueError, match="sdists=0"):
        selector.select_distribution_artifacts(directory, version="1.0.0")


def test_invalid_version_and_directory_fail_closed(tmp_path: Path) -> None:
    directory = make_distribution(tmp_path)
    with pytest.raises(ValueError, match="numeric release"):
        selector.select_distribution_artifacts(directory, version="../1.0.0")
    with pytest.raises(ValueError, match="numeric release"):
        selector.select_distribution_artifacts(directory, version="")
    with pytest.raises(ValueError, match="real directory"):
        selector.select_distribution_artifacts(tmp_path / "absent", version="1.0.0")


def test_symlink_or_zero_byte_distribution_fails_closed(tmp_path: Path) -> None:
    directory = make_distribution(tmp_path)
    wheel = directory / WHEEL
    wheel.unlink()
    wheel.symlink_to(directory / SDIST)
    with pytest.raises(ValueError, match="invalid release artifact"):
        selector.select_distribution_artifacts(directory, version="1.0.0")
    wheel.unlink()
    wheel.touch()
    with pytest.raises(ValueError, match="invalid release artifact"):
        selector.select_distribution_artifacts(directory, version="1.0.0")
