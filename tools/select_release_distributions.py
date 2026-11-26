"""Select the two version-pinned Python archives for a source-only software release.

A build output directory may contain non-distribution entries. Such entries are never
included in a release bundle. Extra, old-version or ambiguous distribution archives
still fail closed rather than being silently uploaded.
"""

from __future__ import annotations

from pathlib import Path

DISTRIBUTION_STEM = "football_performance_dynamics_bench"


def select_distribution_artifacts(directory: Path, *, version: str) -> tuple[Path, Path]:
    """Return the single matching wheel and sdist, excluding unrelated build files."""
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError("distribution directory must be a real directory")
    if not version or any(char not in "0123456789." for char in version):
        raise ValueError("software version must be an explicit numeric release")
    entries = sorted(directory.iterdir(), key=lambda item: item.name)
    wheel_prefix = f"{DISTRIBUTION_STEM}-{version}-"
    sdist_name = f"{DISTRIBUTION_STEM}-{version}.tar.gz"
    wheels = [
        item
        for item in entries
        if item.name.startswith(wheel_prefix) and item.name.endswith(".whl")
    ]
    sdists = [item for item in entries if item.name == sdist_name]
    release_files = [*wheels, *sdists]

    # Never silently accept a second distribution from another release or package.
    unexpected_archives = [
        item.name
        for item in entries
        if (item.name.endswith(".whl") or item.name.endswith(".tar.gz"))
        and item not in release_files
    ]
    if unexpected_archives:
        raise ValueError(f"unexpected distribution archives: {unexpected_archives}")
    if len(wheels) != 1 or len(sdists) != 1:
        raise ValueError(
            f"expected one wheel and one sdist for {version}; "
            f"found wheels={len(wheels)}, sdists={len(sdists)}; "
            f"directory entries={[item.name for item in entries]}"
        )
    for artifact in release_files:
        if artifact.is_symlink() or not artifact.is_file() or artifact.stat().st_size == 0:
            raise ValueError(f"invalid release artifact: {artifact.name}")
    return wheels[0], sdists[0]
