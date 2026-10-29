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


def test_independent_signature_and_provenance(snapshot, tmp_path, monkeypatch):
    source, receipts, _ = snapshot
    adapter.source_preflight(source, receipts)
    receipt = (receipts / "source-preflight.json").read_bytes()
    root_key = tmp_path / "policy-root"
    reviewer_key = tmp_path / "reviewer"
    for key in (root_key, reviewer_key):
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
    trust = tmp_path / "system-trust"
    trust.mkdir(mode=0o755)
    monkeypatch.setattr(adapter, "TRUST_DIRECTORY", trust)
    monkeypatch.setattr(adapter, "TRUST_OWNER_UID", os.getuid())

    def install_policy(key, *, generation=1, revoked=()):
        root_signers = b"fpdbench-policy-owner " + root_key.with_suffix(".pub").read_bytes()
        reviewer_signers = b"test-reviewer " + key.with_suffix(".pub").read_bytes()
        policy = {
            "schema_id": adapter.TRUST_POLICY_SCHEMA,
            "schema_version": adapter.TRUST_POLICY_VERSION,
            "generation": generation,
            "status": "ACTIVE",
            "reviewer": {
                "principal": "test-reviewer",
                "namespace": adapter.NAMESPACE,
                "allowed_signers_sha256": hashlib.sha256(reviewer_signers).hexdigest(),
            },
            "adapter_inventory_sha256": adapter._inventory_digest(
                adapter.installed_adapter_inventory()
            ),
            "producer": {
                "revision": adapter.PRODUCER_REVISION,
                "inventory_sha256": adapter.PRODUCER_INVENTORY_SHA256,
            },
            "verifier": {
                "revision": adapter.VERIFIER_REVISION,
                "inventory_sha256": adapter.VERIFIER_INVENTORY_SHA256,
            },
            "authority_bindings": adapter._authority_bindings(),
            "revoked_signer_key_fingerprints": sorted(revoked),
        }
        payload = canonical_bytes(policy)
        signature = subprocess.run(
            [
                "ssh-keygen",
                "-Y",
                "sign",
                "-f",
                str(root_key),
                "-n",
                adapter.TRUST_POLICY_NAMESPACE,
            ],
            input=payload,
            capture_output=True,
            check=True,
        ).stdout
        for name, value in (
            ("root.allowed_signers", root_signers),
            ("reviewer.allowed_signers", reviewer_signers),
            ("policy.json", payload),
            ("policy.sig", signature),
        ):
            (trust / name).write_bytes(value)
            (trust / name).chmod(0o644)

    def sign(key, payload):
        return subprocess.run(
            ["ssh-keygen", "-Y", "sign", "-f", str(key), "-n", adapter.NAMESPACE],
            input=payload,
            capture_output=True,
            check=True,
        ).stdout

    install_policy(reviewer_key)
    signature = sign(reviewer_key, receipt)
    result = adapter.authenticate_receipt(receipt, signature)
    assert result["qualification_status"] == "NOT_QUALIFIED"
    with pytest.raises(ValueError, match="signature"):
        adapter.authenticate_receipt(receipt + b" ", signature)
    with pytest.raises(TypeError):
        adapter.authenticate_receipt(
            receipt,
            signature,
            trusted_signers_sha256="0" * 64,
        )

    rotated_key = tmp_path / "reviewer-rotated"
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(rotated_key)], check=True
    )
    revoked = adapter._signer_fingerprints(
        b"test-reviewer " + reviewer_key.with_suffix(".pub").read_bytes(), "test-reviewer"
    )
    install_policy(rotated_key, generation=2, revoked=revoked)
    with pytest.raises(ValueError, match="signature"):
        adapter.authenticate_receipt(receipt, signature)
    assert adapter.authenticate_receipt(receipt, sign(rotated_key, receipt))["status"] == (
        "SOURCE_PREFLIGHT"
    )
    (receipts / "source-preflight.sig").write_bytes(sign(rotated_key, receipt))
    (receipts / "source-preflight.sig").chmod(0o600)
    adapter.verify_source_snapshot(source, receipts)
    tracking = next(source.glob("data/matches/*/*_tracking_extrapolated.jsonl"))
    tracking.write_bytes(tracking.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="INCOMPLETE"):
        adapter.verify_source_snapshot(source, receipts)

    trusted = trust / "reviewer.allowed_signers"
    attacker_key = tmp_path / "attacker"
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(attacker_key)], check=True
    )
    trusted.write_bytes(
        trusted.read_bytes() + b"test-reviewer " + attacker_key.with_suffix(".pub").read_bytes()
    )
    with pytest.raises(ValueError, match="policy"):
        adapter.authenticate_receipt(receipt, sign(rotated_key, receipt))
    trusted.write_bytes(b"test-reviewer " + rotated_key.with_suffix(".pub").read_bytes())
    policy = trust / "policy.json"
    original_policy = policy.read_bytes()
    policy.write_bytes(original_policy + b" ")
    with pytest.raises(ValueError, match="policy"):
        adapter.authenticate_receipt(receipt, sign(rotated_key, receipt))


@pytest.mark.parametrize("filesystem", ["9p", "drvfs", "cifs", "nfs", "fuseblk", "overlayfs"])
def test_system_trust_rejects_untrusted_backing_filesystems(monkeypatch, tmp_path, filesystem):
    trust = tmp_path / "system-trust"
    trust.mkdir(mode=0o755)
    monkeypatch.setattr(adapter, "TRUST_DIRECTORY", trust)
    monkeypatch.setattr(adapter, "TRUST_OWNER_UID", os.getuid())
    monkeypatch.setattr(adapter, "_filesystem_type", lambda _fd: filesystem)
    with pytest.raises(ValueError, match="unsupported protected trust filesystem"):
        with adapter._trusted_directory():
            pytest.fail("untrusted backing filesystem was accepted")


def test_system_trust_filesystem_probe_uses_open_directory_descriptor(monkeypatch, tmp_path):
    trust = tmp_path / "system-trust"
    trust.mkdir(mode=0o755)
    monkeypatch.setattr(adapter, "TRUST_DIRECTORY", trust)
    monkeypatch.setattr(adapter, "TRUST_OWNER_UID", os.getuid())
    seen = []

    def check_opened_fd(fd):
        seen.append(os.fstat(fd).st_ino)
        return "ext2/ext3"

    monkeypatch.setattr(adapter, "_filesystem_type", check_opened_fd)
    with adapter._trusted_directory() as fd:
        assert seen == [os.fstat(fd).st_ino]


@pytest.mark.parametrize(
    "entry_kind",
    ["file_symlink", "directory_symlink", "dangling_symlink", "fifo", "native_binary"],
)
def test_adapter_inventory_rejects_unreviewed_package_entries(monkeypatch, tmp_path, entry_kind):
    package_root = tmp_path / "mock-fpdbench"
    module_path = package_root / "data_sources" / "protected_skillcorner.py"
    module_path.parent.mkdir(parents=True)
    module_path.write_text("# synthetic installed source\\n", encoding="utf-8")
    monkeypatch.setattr(adapter, "__file__", str(module_path))
    baseline = adapter.installed_adapter_inventory()
    assert [entry["path"] for entry in baseline] == ["data_sources/protected_skillcorner.py"]
    if entry_kind == "file_symlink":
        (package_root / "injected.py").symlink_to(module_path)
    elif entry_kind == "directory_symlink":
        (package_root / "linked_sources").symlink_to(module_path.parent, target_is_directory=True)
    elif entry_kind == "dangling_symlink":
        (package_root / "missing.json").symlink_to(package_root / "absent.json")
    elif entry_kind == "fifo":
        os.mkfifo(package_root / "unexpected", 0o600)
    else:
        (package_root / "unreviewed.so").write_bytes(b"synthetic")
    with pytest.raises(ValueError, match="unreviewed installed package"):
        adapter.installed_adapter_inventory()


def test_adapter_inventory_includes_new_python_sources(monkeypatch, tmp_path):
    package_root = tmp_path / "mock-fpdbench"
    module_path = package_root / "data_sources" / "protected_skillcorner.py"
    module_path.parent.mkdir(parents=True)
    module_path.write_text("# synthetic source\\n", encoding="utf-8")
    monkeypatch.setattr(adapter, "__file__", str(module_path))
    original = adapter._inventory_digest(adapter.installed_adapter_inventory())
    (package_root / "unexpected.py").write_text("# unreviewed\\n", encoding="utf-8")
    updated = adapter.installed_adapter_inventory()
    assert {entry["path"] for entry in updated} == {
        "data_sources/protected_skillcorner.py",
        "unexpected.py",
    }
    assert adapter._inventory_digest(updated) != original


def test_system_trust_rejects_foreign_backed_policy_file(monkeypatch, tmp_path):
    trust = tmp_path / "system-trust"
    trust.mkdir(mode=0o755)
    signer_file = trust / "root.allowed_signers"
    signer_file.write_bytes(b"synthetic policy key")
    signer_file.chmod(0o644)
    monkeypatch.setattr(adapter, "TRUST_DIRECTORY", trust)
    monkeypatch.setattr(adapter, "TRUST_OWNER_UID", os.getuid())

    def filesystem_type(fd):
        return "9p" if adapter.stat.S_ISREG(os.fstat(fd).st_mode) else "ext2/ext3"

    monkeypatch.setattr(adapter, "_filesystem_type", filesystem_type)
    with adapter._trusted_directory() as directory:
        with pytest.raises(ValueError, match="untrusted system trust file filesystem"):
            adapter._trusted_file(directory, "root.allowed_signers")


def test_trusted_policy_is_required(monkeypatch, tmp_path):
    monkeypatch.setattr(adapter, "TRUST_DIRECTORY", tmp_path / "missing")
    with pytest.raises(ValueError, match="policy"):
        adapter._load_trusted_policy()


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
