from __future__ import annotations

import hashlib
import io
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
from res338_drive_readback import fetch_and_verify, verify  # noqa: E402


def test_drive_readback_verifies_size_and_sha256(tmp_path: Path) -> None:
    path = tmp_path / "archive.bin"
    payload = b"private readback fixture"
    path.write_bytes(payload)
    os.chmod(path, 0o600)
    result = verify(path, hashlib.sha256(payload).hexdigest(), len(payload))
    assert result == {
        "status": "VERIFIED",
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def test_drive_readback_rejects_mismatched_content(tmp_path: Path) -> None:
    path = tmp_path / "archive.bin"
    path.write_bytes(b"changed")
    os.chmod(path, 0o600)
    with pytest.raises(ValueError, match="SHA-256 or size"):
        verify(path, hashlib.sha256(b"expected").hexdigest(), len(b"expected"))


def test_authenticated_drive_fetch_streams_and_verifies_without_returning_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b"streamed private archive bytes"

    class Response(io.BytesIO):
        status = 200

        def geturl(self) -> str:
            return "https://files.oaiusercontent.com/private-readback"

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout: Response(payload),
    )
    path = tmp_path / "readback" / "archive.bin"
    result = fetch_and_verify(
        "https://files.oaiusercontent.com/signed-token",
        path,
        hashlib.sha256(payload).hexdigest(),
        len(payload),
    )
    assert result["status"] == "VERIFIED"
    assert result["bytes"] == len(payload)
    assert path.read_bytes() == payload
