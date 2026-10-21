"""Synthetic source snapshots only; never read the real SkillCorner checkout."""

import copy
import hashlib
import json
import os
import runpy
import subprocess
from pathlib import Path

import pytest

from fpdbench.data_sources import protected_skillcorner as adapter
from fpdbench.data_sources.skillcorner import canonical_bytes, git_blob_sha


@pytest.fixture
def snapshot(tmp_path, monkeypatch):
    source = tmp_path / "source"
    receipts = tmp_path / "receipts"
    source.mkdir(mode=0o700)
    receipts.mkdir(mode=0o700)
    fixture = runpy.run_path(
        str(Path(__file__).with_name("test_independent_population_verifier_v2.py"))
    )
    rows = fixture["_fixture"]()
    manifest = copy.deepcopy(adapter._authority())
    contents = {"data/matches.json": canonical_bytes([{"id": int(row.match_id)} for row in rows])}
    for row in rows:
        prefix = f"data/matches/{row.match_id}/{row.match_id}"
        contents.update(
            {
                prefix + "_match.json": row.metadata_json,
                prefix + "_tracking_extrapolated.jsonl": row.tracking_jsonl,
                prefix + "_phases_of_play.csv": b"frame_start,frame_end,duration\n100,186,8.6\n",
                prefix + "_dynamic_events.csv": b"synthetic\n",
            }
        )
    records = adapter._records(manifest)
    for record in records:
        payload = contents[record["repository_path"]]
        if record["identity_type"] == "git_lfs_pointer":
            record["lfs_oid_sha256"] = hashlib.sha256(payload).hexdigest()
            record["lfs_payload_size"] = len(payload)
            blob = (
                f"version https://git-lfs.github.com/spec/v1\n"
                f"oid sha256:{record['lfs_oid_sha256']}\nsize {len(payload)}\n"
            ).encode()
        else:
            blob = payload
        record["byte_size"] = len(blob)
        record["git_blob_sha"] = git_blob_sha(blob)
        if "raw_sha256" in record:
            record["raw_sha256"] = hashlib.sha256(blob).hexdigest()
        path = source / record["repository_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        path.chmod(0o600)
    for path in source.rglob("*"):
        if path.is_dir():
            path.chmod(0o700)
    monkeypatch.setattr(adapter, "_authority", lambda: manifest)
    return source, receipts, manifest


def test_two_pass_preflight(snapshot):
    source, receipts, _ = snapshot
    adapter.source_preflight(source, receipts)
    receipt = json.loads((receipts / "source-preflight.json").read_bytes())
    assert receipt["status"] == "SOURCE_PREFLIGHT"
    assert receipt["qualification_status"] == "NOT_QUALIFIED"
    assert len(receipt["inputs"]) == 81
    assert len(receipt["normalized_phases"]) == 20
    assert sum(row["source_rows"] for row in receipt["scan"]) == 1720
    assert sum(row["retained_rows"] for row in receipt["scan"]) == 860
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in receipts.iterdir())
    before = {path.name: path.read_bytes() for path in receipts.iterdir()}
    with pytest.raises(ValueError, match="fresh empty"):
        adapter.source_preflight(source, receipts)
    assert before == {path.name: path.read_bytes() for path in receipts.iterdir()}


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "extra",
        "truncated",
        "changed",
        "pointer",
        "symlink",
        "hardlink",
        "mode",
        "directory_symlink",
        "fifo",
    ],
)
def test_source_adversaries_fail_before_scan(snapshot, monkeypatch, fault):
    source, receipts, manifest = snapshot
    record = next(r for r in adapter._records(manifest) if r["identity_type"] == "git_lfs_pointer")
    path = source / record["repository_path"]
    if fault == "missing":
        path.unlink()
    elif fault == "extra":
        (source / "extra").write_bytes(b"x")
    elif fault == "truncated":
        path.write_bytes(path.read_bytes()[:-1])
    elif fault == "changed":
        data = path.read_bytes()
        path.write_bytes(b"!" + data[1:])
    elif fault == "pointer":
        path.write_bytes(b"version https://git-lfs.github.com/spec/v1\n")
    elif fault == "symlink":
        path.unlink()
        path.symlink_to("/etc/passwd")
    elif fault == "hardlink":
        os.link(path, source.parent / "external-link")
    elif fault == "mode":
        path.chmod(0o644)
    elif fault == "directory_symlink":
        original = source / "data"
        original.rename(source.parent / "outside")
        original.symlink_to(source.parent / "outside")
    elif fault == "fifo":
        path.unlink()
        os.mkfifo(path, 0o600)
    monkeypatch.setattr(adapter, "_scan", lambda *_: pytest.fail("unverified source reached scan"))
    with pytest.raises(ValueError, match="INCOMPLETE"):
        adapter.source_preflight(source, receipts)
    assert not (receipts / "source-preflight.json").exists()
    assert not list(receipts.glob("phases-*"))


def test_drift_in_last_match_prevents_all_second_pass_work(snapshot, monkeypatch):
    source, receipts, manifest = snapshot
    match_id = manifest["selected_source_matches"][-1]
    path = f"data/matches/{match_id}/{match_id}_tracking_extrapolated.jsonl"
    rows = [json.loads(line) for line in (source / path).read_bytes().splitlines()]
    rows[-2]["ball_data"]["is_detected"] = None
    (source / path).write_bytes(b"".join(canonical_bytes(row) + b"\n" for row in rows))
    original = adapter._verify_sources
    # Supply a synthetic authenticated byte identity for the altered synthetic fixture only.
    entry = next(r for r in adapter._records(manifest) if r["repository_path"] == path)
    payload = (source / path).read_bytes()
    entry["lfs_payload_size"] = len(payload)
    entry["lfs_oid_sha256"] = hashlib.sha256(payload).hexdigest()
    pointer = (
        f"version https://git-lfs.github.com/spec/v1\n"
        f"oid sha256:{entry['lfs_oid_sha256']}\nsize {len(payload)}\n"
    ).encode()
    entry.update(byte_size=len(pointer), git_blob_sha=git_blob_sha(pointer))
    scans = []

    def checked(*args):
        scans.append(True)
        return original(*args)

    monkeypatch.setattr(adapter, "_verify_sources", checked)
    monkeypatch.setattr(adapter, "normalize_phases", lambda *_: pytest.fail("second pass began"))
    with pytest.raises(ValueError, match="INCOMPLETE"):
        adapter.source_preflight(source, receipts)
    assert scans == [True]
    assert not list(receipts.glob("phases-*"))


def test_change_between_passes_is_rejected(snapshot, monkeypatch):
    source, receipts, _ = snapshot
    original = adapter._scan

    def changed(*args):
        result = original(*args)
        (source / "data/matches.json").write_bytes(b"changed")
        return result

    monkeypatch.setattr(adapter, "_scan", changed)
    with pytest.raises(ValueError, match="INCOMPLETE"):
        adapter.source_preflight(source, receipts)
    assert not (receipts / "source-preflight.json").exists()


@pytest.mark.parametrize(
    "fault",
    [
        "overlap",
        "ancestor_symlink",
        "git",
        "linked_git",
        "mode",
        "writable_parent",
        "mnt",
        "escape",
    ],
)
def test_storage_boundary(tmp_path, fault):
    source, output = tmp_path / "source", tmp_path / "output"
    source.mkdir(mode=0o700)
    output.mkdir(mode=0o700)
    if fault == "overlap":
        output = source
    elif fault == "ancestor_symlink":
        link = tmp_path / "link"
        link.symlink_to(source)
        source = link
    elif fault == "git":
        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    elif fault == "linked_git":
        (source / ".git").write_text("gitdir: /nonexistent\n")
    elif fault == "mode":
        source.chmod(0o755)
    elif fault == "writable_parent":
        tmp_path.chmod(0o777)
    elif fault == "mnt":
        source = Path("/mnt/c/synthetic-never-opened")
    elif fault == "escape":
        source = source / ".." / "source"
    with pytest.raises((ValueError, OSError)):
        adapter.source_preflight(source, output)
    assert not list(output.glob("*.json"))


def test_exclusive_receipts_and_safe_failure(snapshot, monkeypatch):
    source, receipts, _ = snapshot
    original = adapter.write_private
    calls = []

    def fail(fd, name, data):
        calls.append(name)
        if name != "started.json":
            raise OSError("PRIVATE PATH MUST NOT LEAK")
        original(fd, name, data)

    monkeypatch.setattr(adapter, "write_private", fail)
    with pytest.raises(ValueError) as caught:
        adapter.source_preflight(source, receipts)
    assert "PRIVATE" not in str(caught.value)
    assert "failure.json" in calls
    assert not (receipts / "source-preflight.json").exists()
    with adapter.private_directory(receipts) as fd:
        with pytest.raises(FileExistsError):
            original(fd, "started.json", b"overwrite")


@pytest.mark.parametrize(
    "csv",
    [
        b"frame_start,frame_start\n100,101\n",
        b"frame_start,frame_end\n100,100\n",
        b"frame_start,frame_end\n99,105\n",
        b"frame_start,frame_end\n180,190\n",
        b"frame_start,frame_end\n100.0,105\n",
        b"frame_start,frame_end\n100,105,extra\n",
        b"frame_start,frame_end,period\n100,105,2\n",
        b"frame_start,frame_end,duration\n100,105,NaN\n",
        b"frame_start,frame_end,duration\n100,105,1\n",
        b"frame_start,frame_end\n",
    ],
)
def test_phase_parse_fail_closed(csv):
    with pytest.raises(ValueError):
        adapter.normalize_phases(
            csv, {"match_periods": [{"period": 1, "start_frame": 100, "end_frame": 186}]}
        )


def test_phase_determinism_and_half_open_boundaries():
    metadata = {
        "match_periods": [
            {"period": 1, "start_frame": 100, "end_frame": 186},
            {"period": 2, "start_frame": 186, "end_frame": 200},
        ]
    }
    header = b"frame_start,frame_end,duration\n"
    first, second = b"100,186,8.6\n", b"186,200,1.4\n"
    assert adapter.normalize_phases(header + second + first, metadata) == (
        adapter.normalize_phases(header + first + second, metadata)
    )
    assert json.loads(adapter.normalize_phases(header + second, metadata))[0]["period"] == 2


def test_bounded_rows_and_duplicate_keys(tmp_path):
    path = tmp_path / "tracking"
    path.write_bytes(b"x" * (adapter.MAX_ROW + 1))
    path.chmod(0o600)
    with adapter.private_directory(tmp_path) as root:
        with pytest.raises(ValueError, match="oversized"):
            list(adapter._rows(root, "tracking", {}))
    with pytest.raises(ValueError, match="duplicate"):
        adapter._json(b'{"a":1,"a":2}')


def test_independent_signature_and_provenance(snapshot, tmp_path):
    source, receipts, _ = snapshot
    adapter.source_preflight(source, receipts)
    receipt = (receipts / "source-preflight.json").read_bytes()
    key = tmp_path / "reviewer"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
    trusted = tmp_path / "allowed_signers"
    trusted.write_text("res501-source " + key.with_suffix(".pub").read_text())
    trusted.chmod(0o600)
    signature = tmp_path / "receipt.sig"
    signed = subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", str(key), "-n", adapter.NAMESPACE],
        input=receipt,
        capture_output=True,
        check=True,
    )
    signature.write_bytes(signed.stdout)
    signature.chmod(0o600)
    kwargs = {
        "trusted_signers_sha256": hashlib.sha256(trusted.read_bytes()).hexdigest(),
        "expected_package_sha256": hashlib.sha256(
            canonical_bytes(json.loads(receipt)["adapter_package"])
        ).hexdigest(),
    }
    result = adapter.authenticate_receipt(receipt, signature, trusted, **kwargs)
    assert result["qualification_status"] == "NOT_QUALIFIED"
    with pytest.raises(ValueError, match="signature"):
        adapter.authenticate_receipt(receipt + b" ", signature, trusted, **kwargs)
    with pytest.raises(ValueError, match="provenance"):
        adapter.authenticate_receipt(
            receipt, signature, trusted, **{**kwargs, "expected_package_sha256": "0" * 64}
        )
    with pytest.raises(ValueError, match="signer"):
        adapter.authenticate_receipt(
            receipt, signature, trusted, **{**kwargs, "trusted_signers_sha256": "0" * 64}
        )


def test_manifest_pin_and_cardinality(monkeypatch, tmp_path):
    path = tmp_path / "manifest.json"
    path.write_bytes(b"{}")
    monkeypatch.setattr(adapter, "MANIFEST_PATH", path)
    with pytest.raises(ValueError, match="unreviewed"):
        adapter._authority()
    with pytest.raises(ValueError, match="81"):
        adapter._records({"available_matches": [], "source_index": {"repository_path": "x"}})


def test_raw_stream_memory_is_bounded(tmp_path):
    import tracemalloc

    path = tmp_path / "tracking"
    with path.open("wb") as stream:
        for frame in range(20_000):
            stream.write(canonical_bytes({"frame": frame}) + b"\n")
    path.chmod(0o600)
    counts = {}
    tracemalloc.start()
    try:
        with adapter.private_directory(tmp_path) as root:
            for _ in adapter._rows(root, "tracking", counts):
                pass
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert counts["source_rows"] == 20_000
    assert counts["even_source_rows"] == 10_000
    assert peak < 4 * adapter.MAX_ROW


def test_dropped_retained_frame_fails_closed(snapshot, monkeypatch):
    source, receipts, _ = snapshot
    original = adapter.iter_skillcorner_5hz_v2

    def dropped(*args, **kwargs):
        for index, sample in enumerate(original(*args, **kwargs)):
            if index:
                yield sample

    monkeypatch.setattr(adapter, "iter_skillcorner_5hz_v2", dropped)
    with pytest.raises(ValueError, match="INCOMPLETE"):
        adapter.source_preflight(source, receipts)
    assert not list(receipts.glob("phases-*"))


def test_foreign_file_owner_is_rejected(snapshot, monkeypatch):
    source, receipts, _ = snapshot
    original = adapter.os.fstat

    def foreign(fd):
        info = original(fd)
        if adapter.stat.S_ISREG(info.st_mode):
            values = list(info)
            values[4] = os.getuid() + 1
            return os.stat_result(values)
        return info

    monkeypatch.setattr(adapter.os, "fstat", foreign)
    with pytest.raises(ValueError, match="INCOMPLETE"):
        adapter.source_preflight(source, receipts)
    assert not (receipts / "source-preflight.json").exists()


def test_source_mutation_during_scan(snapshot, monkeypatch):
    source, receipts, manifest = snapshot
    original = adapter._scan

    def changed(*args):
        match_id = manifest["selected_source_matches"][0]
        path = source / f"data/matches/{match_id}/{match_id}_tracking_extrapolated.jsonl"
        path.write_bytes(path.read_bytes().replace(b'"z":null', b'"z":0.00'))
        return original(*args)

    monkeypatch.setattr(adapter, "_scan", changed)
    with pytest.raises(ValueError, match="INCOMPLETE"):
        adapter.source_preflight(source, receipts)
    assert not list(receipts.glob("phases-*"))


@pytest.mark.parametrize("path", ["../escape", "/absolute", "a//b", "a/./b", "a\\b"])
def test_relative_path_escape(path):
    with pytest.raises(ValueError, match="unsafe"):
        adapter._parts(path)
