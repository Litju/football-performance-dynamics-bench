"""Verify a private Drive file materialized locally against its frozen SHA-256."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import urllib.parse
import urllib.request
from pathlib import Path

SHA256 = re.compile(r"[0-9a-f]{64}")


def verify(path: Path, expected_sha256: str, expected_size: int) -> dict[str, object]:
    if SHA256.fullmatch(expected_sha256) is None or expected_size < 0:
        raise ValueError("readback requires a valid SHA-256 and byte size")
    digest = hashlib.sha256()
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError("Drive readback must be an exclusive regular file")
        count = 0
        while block := stream.read(1024 * 1024):
            count += len(block)
            if count > expected_size:
                raise ValueError("Drive readback exceeds the expected byte size")
            digest.update(block)
        after = os.fstat(stream.fileno())
        if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise ValueError("Drive readback changed while hashing")
    if count != expected_size or digest.hexdigest() != expected_sha256:
        raise ValueError("Drive readback SHA-256 or size differs from the committed local file")
    return {"status": "VERIFIED", "bytes": count, "sha256": digest.hexdigest()}


def fetch_and_verify(
    download_url: str, path: Path, expected_sha256: str, expected_size: int
) -> dict[str, object]:
    parsed = urllib.parse.urlparse(download_url)
    if parsed.scheme != "https" or not (parsed.hostname or "").endswith(".oaiusercontent.com"):
        raise ValueError(
            "readback URL is not an authenticated file reference: "
            f"{parsed.scheme} {parsed.hostname}"
        )
    if SHA256.fullmatch(expected_sha256) is None or expected_size < 0:
        raise ValueError("readback requires a valid SHA-256 and byte size")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.partial")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    digest = hashlib.sha256()
    count = 0
    try:
        request = urllib.request.Request(download_url)
        with os.fdopen(fd, "wb") as stream:
            with urllib.request.urlopen(request, timeout=300) as response:
                final_host = urllib.parse.urlparse(response.geturl()).hostname or ""
                if not final_host.endswith(".oaiusercontent.com"):
                    raise ValueError("readback redirected outside the authenticated file service")
                while block := response.read(1024 * 1024):
                    count += len(block)
                    if count > expected_size:
                        raise ValueError("Drive readback exceeds the expected byte size")
                    digest.update(block)
                    stream.write(block)
                stream.flush()
                os.fsync(stream.fileno())
        actual_sha256 = digest.hexdigest()
        if count != expected_size or actual_sha256 != expected_sha256:
            raise ValueError("Drive readback SHA-256 or size differs from the committed local file")
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return {"status": "VERIFIED", "bytes": count, "sha256": actual_sha256}
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    local = modes.add_parser("verify")
    local.add_argument("file", type=Path)
    local.add_argument("--sha256", required=True)
    local.add_argument("--size", required=True, type=int)
    fetch = modes.add_parser("fetch-and-verify")
    fetch.add_argument("file", type=Path)
    fetch.add_argument("--sha256", required=True)
    fetch.add_argument("--size", required=True, type=int)
    args = parser.parse_args()
    result = (
        verify(args.file, args.sha256, args.size)
        if args.mode == "verify"
        else fetch_and_verify(sys.stdin.readline().strip(), args.file, args.sha256, args.size)
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
