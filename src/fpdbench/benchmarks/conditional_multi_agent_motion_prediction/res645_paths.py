"""Read-only, alias-resistant file access shared by the RES645 source and checkpoint adapters.

Every path component is opened with ``O_NOFOLLOW`` relative to its parent descriptor, so a
symbolic link, ``..`` component or hard-linked alias is refused instead of followed.
Nothing here writes, renames or creates files.
"""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .res646_authorization import Campaign

# "checkpoint" is deliberately absent: checkpoint directories are legitimate inputs.
FORBIDDEN_FRAGMENTS = ("res594", "fpdbench-private", "owner-go", "heldout", "held-out")


@dataclass(frozen=True, slots=True)
class FileIdentity:
    device: int
    inode: int
    size: int
    mtime_ns: int
    ctime_ns: int
    sha256: str


def reject_unsafe_path(path: Path, *, campaign: Campaign | None = None) -> Path:
    """Return an absolute, lexically normal path or refuse aliases and historical scopes."""
    text = str(path)
    if "\x00" in text or not path.is_absolute():
        raise PermissionError("input paths must be absolute")
    if ".." in path.parts or "." in path.parts[1:]:
        raise PermissionError("path traversal components refused")
    lowered = text.lower()
    if campaign is not None:
        from .res646_authorization import require_campaign

        campaign = require_campaign(campaign)
        campaign.allow_input(path)
    if any(
        fragment in lowered
        for fragment in FORBIDDEN_FRAGMENTS
        if campaign is None or fragment != "fpdbench-private"
    ):
        raise PermissionError("historical or held-out path refused")
    return path


def _open_parent(path: Path, campaign: Campaign | None = None) -> tuple[int, str]:
    reject_unsafe_path(path, campaign=campaign)
    parts = path.parts
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in parts[1:-1]:
            try:
                child = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd
                )
            except OSError as exc:
                raise PermissionError(f"unsafe or missing directory component: {part}") from exc
            os.close(fd)
            fd = child
    except BaseException:
        os.close(fd)
        raise
    return fd, parts[-1]


def open_directory_fd(
    path: Path, *, require_private: bool, campaign: Campaign | None = None
) -> int:
    parent, name = _open_parent(path, campaign)
    try:
        fd = os.open(
            name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent
        )
    except OSError as exc:
        raise PermissionError("directory missing or aliased") from exc
    finally:
        os.close(parent)
    info = os.fstat(fd)
    if require_private and (info.st_uid != os.geteuid() or info.st_mode & 0o077):
        os.close(fd)
        raise PermissionError("directory must be owner-private with no group/other access")
    return fd


def list_directory(
    path: Path, *, require_private: bool, campaign: Campaign | None = None
) -> list[str]:
    fd = open_directory_fd(path, require_private=require_private, campaign=campaign)
    try:
        return sorted(os.listdir(fd))
    finally:
        os.close(fd)


def open_regular_fd(
    path: Path, *, require_private: bool = False, campaign: Campaign | None = None
) -> int:
    parent, name = _open_parent(path, campaign)
    try:
        fd = os.open(
            name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent
        )
        try:
            info = os.fstat(fd)
            check_regular(info, max_bytes=info.st_size, require_private=require_private)
        except BaseException:
            os.close(fd)
            raise
        return fd
    except OSError as exc:
        raise PermissionError("input file missing or aliased") from exc
    finally:
        os.close(parent)


def check_regular(info: os.stat_result, *, max_bytes: int, require_private: bool) -> None:
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_size > max_bytes
        or (require_private and (info.st_uid != os.geteuid() or info.st_mode & 0o077))
    ):
        raise PermissionError("input must be an exclusive, bounded, regular file")


def stat_key(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def read_regular_file(
    path: Path, *, max_bytes: int, require_private: bool = False, campaign: Campaign | None = None
) -> tuple[bytes, FileIdentity]:
    """Read one exclusive regular file once; identity is taken before and after the read."""
    fd = open_regular_fd(path, campaign=campaign)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        check_regular(before, max_bytes=max_bytes, require_private=require_private)
        data = stream.read(max_bytes + 1)
        after = os.fstat(stream.fileno())
    if len(data) != before.st_size or stat_key(before) != stat_key(after):
        raise ValueError("input changed while it was read")
    return data, FileIdentity(*stat_key(before), hashlib.sha256(data).hexdigest())


def same_identity(path: Path, expected: FileIdentity, *, max_bytes: int) -> bool:
    """Re-read and compare, to prove an input was not substituted during a streamed pass."""
    try:
        _, now = read_regular_file(path, max_bytes=max_bytes)
    except (OSError, ValueError):
        return False
    return now == expected
