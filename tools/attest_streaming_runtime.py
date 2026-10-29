"""Synthetic pre-import runtime gate; never an authority for protected execution."""

from __future__ import annotations

import sys

# -B alone still reads caches. /dev/null makes prefixed cache paths unusable on Linux.
if not (
    sys.platform == "linux"
    and sys.flags.isolated
    and sys.flags.no_site
    and sys.flags.dont_write_bytecode
    and sys.pycache_prefix == "/dev/null"
):
    raise SystemExit("require Python -I -S -B -X pycache_prefix=/dev/null")

import argparse
import ctypes  # noqa: F401 - pin ctypes/libffi in the bootstrap native mappings.
import hashlib
import importlib.abc
import importlib.machinery
import importlib.util
import io
import json
import os
import stat
import sysconfig
from pathlib import Path

STARTUP_PATH = list(sys.path)
sys.path[:] = [str(Path(entry).resolve()) for entry in sys.path]

SCHEMA = "fpdbench.synthetic-streaming-runtime/1"
PREFIX = "fpdbench.benchmarks.conditional_multi_agent_motion_prediction."
WORKERS = {
    "producer": PREFIX + "streaming_population_producer_v1",
    "verifier": PREFIX + "streaming_population_verifier_v1",
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def read_regular(path):
    """Open every component without following links, then read one stable regular file."""
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("require absolute paths without traversal")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parts[1:-1]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        leaf = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(leaf, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise ValueError("runtime entries must be regular files")
            payload = stream.read()
            after = os.fstat(stream.fileno())
            fields = ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns")
            if any(getattr(before, key) != getattr(after, key) for key in fields):
                raise ValueError("runtime file changed while reading")
            return payload
    finally:
        os.close(fd)


def tree(root, *, stdlib=False):
    def fail(error):
        raise error

    files = {}
    for directory, directories, names in os.walk(root, followlinks=False, onerror=fail):
        directories[:] = sorted(
            name
            for name in directories
            if name != "__pycache__" and not (stdlib and name in {"site-packages", "dist-packages"})
        )
        for name in directories:
            if (Path(directory) / name).is_symlink():
                raise ValueError("symlinked runtime directory")
        for name in sorted(names):
            path = Path(directory) / name
            if path.suffix in {".pyc", ".pyo"}:
                raise ValueError("sourceless bytecode is forbidden")
            files[str(path)] = digest(read_regular(path))
    if not files:
        raise ValueError("empty runtime inventory")
    return files


def native_files():
    paths = set()
    for line in Path("/proc/self/maps").read_text().splitlines():
        fields = line.split(maxsplit=5)
        if len(fields) == 6 and fields[5].startswith("/"):
            if fields[5].endswith(" (deleted)"):
                raise ValueError("deleted native mapping")
            paths.add(fields[5])
        elif "x" in fields[1] and (len(fields) < 6 or fields[5] != "[vdso]"):
            # This fixed kernel pseudo-map is not a file-backed native executable.
            if os.uname().machine == "x86_64" and fields == [
                "ffffffffff600000-ffffffffff601000",
                "--xp",
                "00000000",
                "00:00",
                "0",
                "[vsyscall]",
            ]:
                continue
            # Report only fixed classifications and canonical-field checks, never raw mappings.
            classification = {
                "kind": (
                    "vsyscall"
                    if len(fields) == 6 and fields[5] == "[vsyscall]"
                    else "anonymous"
                    if len(fields) < 6
                    else "unknown"
                ),
                "permissions": fields[1]
                if len(fields[1]) == 4 and all(c in "rwxps-" for c in fields[1])
                else "invalid",
                "x86_64": os.uname().machine == "x86_64",
                "fixed_address": fields[0] == "ffffffffff600000-ffffffffff601000",
                "zero_offset": fields[2] == "00000000",
                "zero_device": fields[3] == "00:00",
                "zero_inode": fields[4] == "0",
            }
            raise ValueError(
                "unidentified executable mapping: " + canonical(classification).decode()
            )
    return {path: digest(read_regular(path)) for path in sorted(paths)}


def environment():
    # Capture provenance without writing arbitrary environment values (possibly credentials).
    allowed = {"PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ"}
    unexpected = set(os.environ) - allowed
    if unexpected:
        raise ValueError(
            "use an empty environment; unexpected names: " + ",".join(sorted(unexpected))
        )
    return dict(sorted(os.environ.items()))


def snapshot(package_root):
    stdlib = Path(sysconfig.get_path("stdlib")).resolve(strict=True)
    extension_root = Path(sysconfig.get_config_var("DESTSHARED")).resolve(strict=True)
    roots = {str(stdlib), str(extension_root)}
    # Python may advertise an absent standard-library zip; an existing zip is never accepted.
    for entry in sys.path:
        if entry not in roots and (not entry.endswith(".zip") or Path(entry).exists()):
            raise ValueError("unexpected executable import path: " + entry)
    executable = Path(sys.executable).resolve(strict=True)
    if not os.path.samefile(executable, "/proc/self/exe"):
        raise ValueError("invoked interpreter differs from running executable")
    files = tree(stdlib, stdlib=True)
    if not extension_root.is_relative_to(stdlib):
        files.update(tree(extension_root))
    files.update(tree(package_root))
    files[str(executable)] = digest(read_regular(executable))
    for configuration in ("/etc/ld.so.cache", "/etc/ld.so.preload"):
        if Path(configuration).exists():
            files[configuration] = digest(read_regular(configuration))
    files[str(Path(__file__).absolute())] = digest(read_regular(Path(__file__).absolute()))
    bootstrap = {}
    for name, module in BOOTSTRAP_MODULES:
        origin = getattr(getattr(module, "__spec__", None), "origin", None)
        if origin in {None, "built-in", "frozen"}:
            bootstrap[name] = origin
        else:
            resolved = str(Path(origin).resolve(strict=True))
            if resolved not in files:
                raise ValueError("bootstrap module outside inventory: " + name)
            bootstrap[name] = resolved
    return {
        "schema": SCHEMA,
        "authority": "SYNTHETIC_CALLER_PIN_ONLY",
        "package_root": str(package_root),
        "interpreter": {
            "invoked_path": sys.executable,
            "resolved_path": str(executable),
            "version": sys.version,
            "implementation": sys.implementation.name,
            "cache_tag": sys.implementation.cache_tag,
            "soabi": sysconfig.get_config_var("SOABI"),
            "prefix": sys.prefix,
            "base_prefix": sys.base_prefix,
        },
        "bootstrap_modules": bootstrap,
        "kernel": {
            key: getattr(os.uname(), key) for key in ("sysname", "release", "version", "machine")
        },
        "python_flags": {
            key: getattr(sys.flags, key)
            for key in (
                "isolated",
                "no_site",
                "ignore_environment",
                "safe_path",
                "dont_write_bytecode",
                "optimize",
                "debug",
                "utf8_mode",
                "hash_randomization",
                "dev_mode",
            )
        },
        "python_xoptions": dict(sys._xoptions),
        "cwd": os.getcwd(),
        "sys_path": list(sys.path),
        "startup_path": STARTUP_PATH,
        "environment": environment(),
        "files": dict(sorted(files.items())),
        "native_files": native_files(),
        "third_party_dependencies": [],
        "bytecode_policy": "COMPILE_VERIFIED_SOURCE;NO_CACHE_READS_OR_WRITES",
    }


class VerifiedSource(importlib.abc.Loader):
    def __init__(self, path, expected, files):
        self.path = path
        self.expected = expected
        self.inventory = files

    def get_resource_reader(self, fullname):
        return self

    def open_resource(self, resource):
        if Path(resource).name != resource:
            raise ValueError("invalid resource name")
        path = str(Path(self.path).parent / resource)
        payload = read_regular(path)
        if digest(payload) != self.inventory.get(path):
            raise ValueError("resource changed before read: " + path)
        return io.BytesIO(payload)

    def resource_path(self, resource):
        raise FileNotFoundError("resources must be read through verified bytes")

    def is_resource(self, name):
        return str(Path(self.path).parent / name) in self.inventory

    def contents(self):
        return [entry.name for entry in Path(self.path).parent.iterdir()]

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        payload = read_regular(self.path)
        if digest(payload) != self.expected:
            raise ValueError("source changed before compilation: " + self.path)
        module.__file__ = self.path
        exec(compile(payload, self.path, "exec", dont_inherit=True), module.__dict__)


class VerifiedImports(importlib.abc.MetaPathFinder):
    def __init__(self, files):
        self.files = files
        self.imported = {}

    def find_spec(self, fullname, path=None, target=None):
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or spec.origin not in self.files:
            raise ImportError("import outside runtime inventory: " + fullname)
        self.imported[fullname] = spec.origin
        if isinstance(spec.loader, importlib.machinery.SourceFileLoader):
            spec.loader = VerifiedSource(spec.origin, self.files[spec.origin], self.files)
            spec.cached = None
        elif not isinstance(spec.loader, importlib.machinery.ExtensionFileLoader):
            raise ImportError("unsupported runtime loader: " + fullname)
        elif digest(read_regular(spec.origin)) != self.files[spec.origin]:
            raise ImportError("native extension changed before import: " + fullname)
        return spec


def load_worker(kind, root, finder):
    if any(name == "fpdbench" or name.startswith("fpdbench.") for name in sys.modules):
        raise ValueError("worker package imported before attestation")
    if kind == "producer":
        return __import__(WORKERS[kind], fromlist=["produce_streaming_population_draft_v1"])
    # The independent verifier needs no package initializers or producer imports.
    path = str(
        root
        / "benchmarks/conditional_multi_agent_motion_prediction/"
        / ("streaming_population_verifier_v1.py")
    )
    loader = VerifiedSource(path, finder.files[path], finder.files)
    spec = importlib.util.spec_from_file_location(
        "_attested_streaming_verifier", path, loader=loader
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    finder.imported[spec.name] = path
    loader.exec_module(module)
    return module


def execute(kind, worker, request):
    if kind == "producer":
        if set(request) != {"inputs", "output_directory"}:
            raise ValueError("producer request requires inputs and output_directory")
        inputs = [
            worker.StreamingPopulationMatchInputV1(
                match_id=row["match_id"],
                metadata_path=Path(row["metadata_path"]),
                tracking_jsonl_path=Path(row["tracking_jsonl_path"]),
                phase_intervals_path=Path(row["phase_intervals_path"]),
            )
            for row in request["inputs"]
        ]
        return worker.produce_streaming_population_draft_v1(
            inputs, Path(request["output_directory"])
        ).status
    if set(request) != {"input_root", "artifact_root", "producer_package_root", "report"}:
        raise ValueError("invalid verifier request fields")
    return worker.verify_population(
        *(
            Path(request[key])
            for key in ("input_root", "artifact_root", "producer_package_root", "report")
        )
    )["status"]


def write_new(path, value):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(canonical(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("capture", "run"))
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--package-root", required=True, type=Path)
    parser.add_argument("--expected-sha256")
    parser.add_argument("--worker", choices=WORKERS)
    parser.add_argument("--request", type=Path)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    root = args.package_root
    if root.name != "fpdbench" or not root.is_absolute():
        parser.error("package-root must be an absolute fpdbench directory")
    if args.mode == "capture":
        value = snapshot(root)
        write_new(args.manifest, value)
        print(digest(canonical(value)))
        return 0
    if not all((args.expected_sha256, args.worker, args.request, args.evidence)):
        parser.error("run requires expected-sha256, worker, request and evidence")
    evidence = {
        "schema": SCHEMA,
        "status": "REJECTED",
        "runtime_gate": "BLOCKED",
        "qualification": "NOT_PERFORMED",
        "authority": "SYNTHETIC_CALLER_PIN_ONLY",
        "worker": args.worker,
        "worker_import_started": False,
        "worker_execution_started": False,
    }
    try:
        manifest_bytes = read_regular(args.manifest)
        manifest = json.loads(manifest_bytes)
        if digest(canonical(manifest)) != args.expected_sha256:
            raise ValueError("manifest pin mismatch")
        actual = snapshot(root)
        if actual != manifest:
            raise ValueError("pre-import runtime manifest mismatch")
        evidence["manifest_sha256"] = args.expected_sha256
        request_bytes = read_regular(args.request)
        evidence["request_sha256"] = digest(request_bytes)
        finder = VerifiedImports(manifest["files"])
        sys.path[:] = [str(root.parent), *sys.path]
        sys.meta_path[:] = [
            importlib.machinery.BuiltinImporter,
            importlib.machinery.FrozenImporter,
            finder,
        ]
        evidence["worker_import_started"] = True
        worker = load_worker(args.worker, root, finder)
        evidence["worker_execution_started"] = True
        evidence["worker_status"] = execute(args.worker, worker, json.loads(request_bytes))
        # Remove only our package search path for the identical post-execution snapshot.
        sys.path.remove(str(root.parent))
        if snapshot(root) != manifest:
            raise ValueError("post-execution runtime manifest mismatch")
        evidence["imports"] = finder.imported
        evidence["status"] = "SYNTHETIC_RUNTIME_CONSISTENT"
    except Exception as exc:
        evidence["error"] = str(exc)
    write_new(args.evidence, evidence)
    return 0 if evidence["status"] == "SYNTHETIC_RUNTIME_CONSISTENT" else 1


BOOTSTRAP_MODULES = sorted(sys.modules.items())


if __name__ == "__main__":
    raise SystemExit(main())
