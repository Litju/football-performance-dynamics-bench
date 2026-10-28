"""Only synthetic inputs and caller pins; no production trust or protected data."""

from __future__ import annotations

import hashlib
import json
import os
import py_compile
import shutil
import subprocess
import sys
import sysconfig
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).parents[2]
LAUNCHER = REPO / "tools/attest_streaming_runtime.py"
FLAGS = ["-I", "-S", "-B", "-X", "pycache_prefix=/dev/null"]
WORKER = "benchmarks/conditional_multi_agent_motion_prediction/streaming_population_verifier_v1.py"


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _command(*args, env=None, flags=FLAGS):
    return subprocess.run(
        [sys.executable, *flags, str(LAUNCHER), *map(str, args)],
        env={} if env is None else env,
        capture_output=True,
        text=True,
        timeout=180,
    )


@pytest.fixture
def runtime(tmp_path):
    root = tmp_path / "fpdbench"
    shutil.copytree(REPO / "src/fpdbench", root, ignore=shutil.ignore_patterns("__pycache__"))
    manifest = tmp_path / "runtime.json"
    result = _command("capture", "--manifest", manifest, "--package-root", root)
    assert result.returncode == 0, result.stderr
    return root, manifest, result.stdout.strip()


@pytest.fixture(scope="module")
def synthetic(tmp_path_factory):
    root = tmp_path_factory.mktemp("runtime-synthetic")
    with zipfile.ZipFile(
        REPO / "tests/fixtures/streaming-verifier-v1/pr25-synthetic-fixtures.zip"
    ) as archive:
        for name in archive.namelist():
            if name.startswith("complete_10hz/"):
                archive.extract(name, root)
    return root / "complete_10hz"


def _run(runtime, tmp_path, request, *, kind="verifier", env=None):
    root, manifest, pin = runtime
    request_path = tmp_path / "request.json"
    request_path.write_bytes(_canonical(request))
    evidence = tmp_path / "evidence.json"
    result = _command(
        "run",
        "--manifest",
        manifest,
        "--package-root",
        root,
        "--expected-sha256",
        pin,
        "--worker",
        kind,
        "--request",
        request_path,
        "--evidence",
        evidence,
        env=env,
    )
    assert evidence.exists(), result.stderr
    report = json.loads(evidence.read_bytes())
    assert report["runtime_gate"] == "BLOCKED"
    assert report["qualification"] == "NOT_PERFORMED"
    return result, report


def _verifier_request(synthetic, root, tmp_path):
    return {
        "input_root": str(synthetic / "inputs"),
        "artifact_root": str(synthetic / "artifacts"),
        "producer_package_root": str(root),
        "report": str(tmp_path / "verification.json"),
    }


@pytest.mark.parametrize("kind", ["producer", "verifier"])
def test_integrated_workers(runtime, synthetic, tmp_path, kind):
    root, manifest, _ = runtime
    if kind == "producer":
        request = {
            "inputs": [
                {
                    "match_id": directory.name,
                    "metadata_path": str(directory / "metadata.json"),
                    "tracking_jsonl_path": str(directory / "tracking.jsonl"),
                    "phase_intervals_path": str(directory / "phases.json"),
                }
                for directory in sorted((synthetic / "inputs").iterdir())
            ],
            "output_directory": str(tmp_path / "population"),
        }
    else:
        request = _verifier_request(synthetic, root, tmp_path)
    result, report = _run(runtime, tmp_path, request, kind=kind)
    assert result.returncode == 0, (result.stderr, report)
    assert report["status"] == "SYNTHETIC_RUNTIME_CONSISTENT"
    expected = "UNQUALIFIED" if kind == "producer" else "RECONCILED_NON_AUTHORITATIVE"
    assert report["worker_status"] == expected
    inventory = json.loads(manifest.read_bytes())
    assert inventory["third_party_dependencies"] == []
    assert inventory["interpreter"]["resolved_path"] in inventory["files"]
    if kind == "verifier":
        assert not any(name.startswith("fpdbench") for name in report["imports"])
        verification = json.loads((tmp_path / "verification.json").read_bytes())
        assert verification["runtime_gate"] == "BLOCKED"
    else:
        for filename in (
            "manifest.json",
            "candidates.jsonl",
            "diagnostic-census.jsonl",
            "truth.jsonl",
        ):
            assert (tmp_path / "population" / filename).read_bytes() == (
                synthetic / "artifacts" / filename
            ).read_bytes()


@pytest.mark.parametrize("field", ["interpreter", "files", "native_files", "environment"])
def test_runtime_pin_mismatch_rejected_before_import(runtime, tmp_path, field):
    root, manifest, _ = runtime
    value = json.loads(manifest.read_bytes())
    if field == "interpreter":
        value[field]["version"] = "forged"
    elif field == "environment":
        value[field]["TZ"] = "forged"
    else:
        value[field][next(iter(value[field]))] = "0" * 64
    manifest.write_bytes(_canonical(value))
    # Even a recalculated caller pin cannot make the observed runtime match forged evidence.
    runtime = root, manifest, hashlib.sha256(_canonical(value)).hexdigest()
    result, report = _run(runtime, tmp_path, {})
    assert result.returncode == 1
    assert not report["worker_import_started"]
    assert "pre-import" in report["error"]


@pytest.mark.parametrize(
    "mutation", ["source", "initializer", "resource", "extra", "symlink", "pyc"]
)
def test_package_changes_rejected_before_import(runtime, tmp_path, mutation):
    root, _, _ = runtime
    if mutation == "source":
        (root / WORKER).write_text("raise RuntimeError('MUST NOT EXECUTE')")
    elif mutation == "initializer":
        (root / "__init__.py").write_text("raise RuntimeError('MUST NOT EXECUTE')")
    elif mutation == "resource":
        (root / "data_states/skillcorner_5hz_v2.json").write_text("{}")
    elif mutation == "extra":
        (root / "unexpected.py").write_text("raise RuntimeError('MUST NOT EXECUTE')")
    elif mutation == "symlink":
        target = root / WORKER
        target.unlink()
        target.symlink_to(REPO / "src/fpdbench" / WORKER)
    else:
        (root / "unexpected.pyc").write_bytes(b"not bytecode")
    result, report = _run(runtime, tmp_path, {})
    assert result.returncode == 1
    assert not report["worker_import_started"]


def test_poisoned_cache_is_never_executed(runtime, synthetic, tmp_path):
    root, _, _ = runtime
    source = root / WORKER
    original = source.read_bytes()
    timestamp = source.stat().st_mtime_ns
    # A valid timestamp cache with the same size and mtime would be accepted by Python normally.
    poison = b"raise RuntimeError('POISONED CACHE EXECUTED')\n"
    source.write_bytes(poison + b" " * (len(original) - len(poison)))
    os.utime(source, ns=(timestamp, timestamp))
    py_compile.compile(str(source), doraise=True)
    source.write_bytes(original)
    os.utime(source, ns=(timestamp, timestamp))
    control = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-c",
            "import importlib.util,sys; "
            "s=importlib.util.spec_from_file_location('poison_control',sys.argv[1]); "
            "s.loader.exec_module(importlib.util.module_from_spec(s))",
            str(source),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert control.returncode != 0 and "POISONED CACHE EXECUTED" in control.stderr
    result, report = _run(runtime, tmp_path, _verifier_request(synthetic, root, tmp_path))
    assert result.returncode == 0, (result.stderr, report)
    assert report["worker_status"] == "RECONCILED_NON_AUTHORITATIVE"


@pytest.mark.parametrize("variable", ["PYTHONPATH", "LD_LIBRARY_PATH", "OPENSSL_CONF"])
def test_environment_injection_rejected_before_import(runtime, tmp_path, variable):
    result, report = _run(runtime, tmp_path, {}, env={variable: str(tmp_path)})
    assert result.returncode == 1
    assert not report["worker_import_started"]
    assert "unexpected names" in report["error"]


def test_startup_flags_required(tmp_path):
    result = _command("capture", flags=["-I", "-S", "-B"])
    assert result.returncode != 0
    assert "require Python" in result.stderr


def test_evidence_is_private_from_creation(tmp_path):
    script = """
import os, runpy, stat, sys
from pathlib import Path
module = runpy.run_path(sys.argv[1])
original = os.fchmod
def check_creation_mode(fd, mode):
    assert stat.S_IMODE(os.fstat(fd).st_mode) == 0o600
    original(fd, mode)
os.fchmod = check_creation_mode
os.umask(0)
path = Path(sys.argv[2])
module['write_new'](path, {'synthetic': True})
assert stat.S_IMODE(path.stat().st_mode) == 0o600
try:
    module['write_new'](path, {})
except FileExistsError:
    pass
else:
    raise AssertionError('existing evidence overwritten')
"""
    result = subprocess.run(
        [sys.executable, *FLAGS, "-c", script, str(LAUNCHER), str(tmp_path / "evidence.json")],
        env={},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "probe", ["post_mutation", "import_mutation", "escape", "native_mapping", "worker_error"]
)
def test_execution_failures_never_emit_success(runtime, tmp_path, probe):
    root, manifest, _ = runtime
    marker = tmp_path / "must-not-execute"
    helper = root / "late_helper.py"
    helper.write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\n")
    if probe == "post_mutation":
        body = f"Path({str(helper)!r}).write_text('changed')\n    return {{'status': 'PROBE'}}"
    elif probe == "import_mutation":
        body = f"Path({str(helper)!r}).write_text('changed')\n    import fpdbench.late_helper"
    elif probe == "escape":
        (root.parent / "outside_inventory.py").write_text(
            f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
        )
        body = "import outside_inventory"
    elif probe == "native_mapping":
        library = Path("/lib") / sysconfig.get_config_var("MULTIARCH") / "libuuid.so.1"
        if not library.exists():
            pytest.skip("native-mapping probe requires the system libuuid")
        body = (
            f"import ctypes\n    ctypes.CDLL({str(library.resolve())!r})"
            "\n    return {'status': 'PROBE'}"
        )
    else:
        body = "raise RuntimeError('synthetic worker failure')"
    (root / WORKER).write_text(
        "from pathlib import Path\ndef verify_population(*args):\n    " + body + "\n"
    )
    manifest.unlink()
    captured = _command("capture", "--manifest", manifest, "--package-root", root)
    assert captured.returncode == 0, captured.stderr
    runtime = root, manifest, captured.stdout.strip()
    request = {
        key: str(tmp_path)
        for key in ("input_root", "artifact_root", "producer_package_root", "report")
    }
    result, report = _run(runtime, tmp_path, request)
    assert result.returncode == 1
    assert report["status"] == "REJECTED"
    assert report["worker_execution_started"]
    assert not marker.exists()
    expected = {
        "post_mutation": "post-execution runtime manifest mismatch",
        "import_mutation": "source changed before compilation",
        "escape": "import outside runtime inventory",
        "native_mapping": "post-execution runtime manifest mismatch",
        "worker_error": "synthetic worker failure",
    }
    assert expected[probe] in report["error"]


def test_manifest_self_hash_is_not_enough(runtime, tmp_path):
    root, manifest, pin = runtime
    value = json.loads(manifest.read_bytes())
    value["authority"] = "PRODUCTION"
    manifest.write_bytes(_canonical(value))
    result, report = _run((root, manifest, pin), tmp_path, {})
    assert result.returncode == 1
    assert not report["worker_import_started"]
    assert report["error"] == "manifest pin mismatch"


@pytest.mark.parametrize("tree", ["input_root", "artifact_root", "producer_package_root"])
def test_launcher_rejects_report_inside_evidence(runtime, synthetic, tmp_path, tree):
    root, _, _ = runtime
    request = _verifier_request(synthetic, root, tmp_path)
    protected = Path(request[tree])
    target = next(path for path in protected.rglob("*") if path.is_file())
    before = target.read_bytes()
    request["report"] = str(target)
    result, evidence = _run(runtime, tmp_path, request)
    assert result.returncode == 1
    assert evidence["status"] == "REJECTED"
    assert "outside all evidence trees" in evidence["error"]
    assert target.read_bytes() == before
