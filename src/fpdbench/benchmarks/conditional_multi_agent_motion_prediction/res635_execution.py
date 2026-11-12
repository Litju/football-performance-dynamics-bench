"""Detached, fail-closed synthetic campaigns; one explicit boundary continuation.

Linux only. The owner UID and stable ledger root are the trust boundary. No real-data
permissions exist here. The supervisor attests its own wait status, never a worker claim.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import hmac
import json
import math
import os
import resource
import signal
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, cast

from . import res635_post_failure_evaluation as s
from . import res635_verification as v

MODULE = "fpdbench.benchmarks.conditional_multi_agent_motion_prediction.res635_execution"
BUDGET = {"cpu_s": 600.0, "wall_s": 900.0, "rss_bytes": 2 * 1024**3, "disk_bytes": 64 * 1024**2}
EXIT_INTEGRITY, EXIT_BUDGET, EXIT_INTERRUPTED, EXIT_WORKER = 7, 5, 143, 6
FORBIDDEN = ("res594", "fpdbench-private", "owner-go", "heldout", "checkpoint")


def safe_path(path: Path) -> Path:
    if any(part in str(path.absolute()).lower() for part in FORBIDDEN):
        raise PermissionError("historical or private campaign path refused")
    resolved = path.resolve()
    if any(part in str(resolved).lower() for part in FORBIDDEN):
        raise PermissionError("historical or private campaign alias refused")
    for parent in (path.absolute(), *path.absolute().parents):
        if parent.is_symlink():
            raise PermissionError("symbolic campaign/ledger paths refused")
    return resolved


def fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic(path: Path, value: object) -> None:
    data = s.canonical(value)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    fsync_dir(path.parent)


def read(path: Path) -> s.Document:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 2_000_000:
            raise ValueError("invalid evidence file")
        value: Any = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("evidence must be an object")
    return cast(s.Document, value)


def private_root(root: Path, output: Path) -> Path:
    root, output = safe_path(root), safe_path(output)
    if root == output or root in output.parents or output in root.parents:
        raise PermissionError("stable ledger and output must be separate trees")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = root.stat()
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise PermissionError("ledger must be owner-private 0700")
    return root


def ledger_path(root: Path, count: int) -> Path:
    return root / f"{v.receipts_scope(count)}.json"


def signed(body: s.Document, key: str) -> s.Document:
    return {
        "body": body,
        "hmac_sha256": hmac.new(bytes.fromhex(key), s.canonical(body), hashlib.sha256).hexdigest(),
    }


def authenticated(path: Path, key: str) -> s.Document:
    record = read(path)
    if not hmac.compare_digest(record["hmac_sha256"], signed(record["body"], key)["hmac_sha256"]):
        raise ValueError("forged postmortem or manifest")
    return record["body"]


def telemetry(output: Path, value: s.Document) -> None:
    fd = os.open(
        output / "telemetry.jsonl", os.O_APPEND | os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600
    )
    try:
        data = s.canonical(value) + b"\n"
        if os.write(fd, data) != len(data):
            raise OSError("short telemetry write")
        os.fsync(fd)
    finally:
        os.close(fd)


def reserve(root: Path, output: Path, count: int, continuation: bool) -> s.Document:
    if type(count) is not int or not 1 <= count <= 64:
        raise ValueError("synthetic inference count must be 1..64")
    root = private_root(root, output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("output already populated")
    if output.exists() and (
        output.stat().st_uid != os.geteuid() or stat.S_IMODE(output.stat().st_mode) != 0o700
    ):
        raise PermissionError("output must be owner-private 0700")
    path = ledger_path(root, count)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    record: s.Document = {
        "namespace": "RES643-SYNTHETIC-ONLY-v1",
        "scope_sha256": v.receipts_scope(count),
        "output": str(output.resolve()),
        "count": count,
        "seals": [],
        "attempt": 0,
        "continuation_predeclared": continuation,
        "key": os.urandom(32).hex(),
        "cpu_used": 0.0,
        "wall_used": 0.0,
        "budget": BUDGET,
        "status": "RESERVED",
    }
    record["record_sha256"] = s.digest(record)
    with os.fdopen(fd, "wb") as stream:
        stream.write(s.canonical(record))
        stream.flush()
        os.fsync(stream.fileno())
    fsync_dir(root)
    output.mkdir(parents=True, mode=0o700, exist_ok=True)
    atomic(
        output / "campaign.json",
        {k: record[k] for k in ("namespace", "scope_sha256", "count", "budget")},
    )
    return record


def store_ledger(root: Path, count: int, record: s.Document) -> None:
    body = {k: value for k, value in record.items() if k != "record_sha256"}
    record["record_sha256"] = s.digest(body)
    atomic(ledger_path(root, count), record)


def bound_record(root: Path, output: Path, count: int) -> s.Document:
    private_root(root, output)
    path = ledger_path(root, count)
    info = path.stat()
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600:
        raise PermissionError("ledger record must be owner-private 0600")
    record = read(path)
    if record.get("record_sha256") != s.digest(
        {k: value for k, value in record.items() if k != "record_sha256"}
    ):
        raise ValueError("ledger record hash differs")
    if record["output"] != str(output.resolve()) or record["scope_sha256"] != v.receipts_scope(
        count
    ):
        raise ValueError("campaign/ledger identity differs")
    if record["status"] == "RUNNING" and (output / "processes.json").exists():
        processes = read(output / "processes.json")
        if processes["attempt"] != record["attempt"]:
            return record
        try:
            fields = (
                Path(f"/proc/{processes['supervisor_pid']}/stat")
                .read_text()
                .rsplit(")", 1)[1]
                .split()
            )
            alive = fields[0] != "Z" and fields[19] == processes["supervisor_start_ticks"]
        except (OSError, KeyError, IndexError):
            alive = False
        if not alive:
            record["status"] = "FAILED_PERMANENTLY"
            store_ledger(root, count, record)
    return record


def _child_limits(parent_pid: int, cpu: float) -> None:
    # The worker cannot outlive a lost supervisor, including before exec completes.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0 or os.getppid() != parent_pid:
        os._exit(EXIT_WORKER)
    signal.pthread_sigmask(signal.SIG_BLOCK, (signal.SIGTERM, signal.SIGINT, signal.SIGHUP))
    resource.setrlimit(resource.RLIMIT_CPU, (max(1, math.ceil(cpu)), max(2, math.ceil(cpu) + 1)))
    resource.setrlimit(
        resource.RLIMIT_FSIZE, (int(BUDGET["disk_bytes"]), int(BUDGET["disk_bytes"]))
    )
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def worker(output: Path, count: int, start: int, pause: int) -> int:
    stop = threading.Event()
    events: list[s.Document] = []
    signals = (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)
    signal.pthread_sigmask(signal.SIG_BLOCK, signals)

    def watch() -> None:
        info = signal.sigwaitinfo(signals)
        events.append(
            {"signal": info.si_signo, "sender_pid": info.si_pid, "sender_uid": info.si_uid}
        )
        stop.set()
        timer = threading.Timer(2, lambda: os._exit(EXIT_INTERRUPTED))
        timer.daemon = True
        timer.start()

    threading.Thread(target=watch, daemon=True).start()

    def check() -> None:
        if stop.is_set():
            raise InterruptedError("controlled worker termination")

    models = s.models()
    previous = s.digest(read(output / f"match-{start - 1}.json")) if start else "0" * 64
    try:
        for i in range(start, 4):
            check()
            body = s.score_match(s.MATCHES[i], count, models, check)
            receipt = {**body, "scope_sha256": v.receipts_scope(count), "previous_sha256": previous}
            atomic(output / f"match-{i}.json", receipt)
            previous = s.digest(receipt)
            # Explicit synthetic fault fixture, outside the scientific scope and measurements.
            if i == pause:
                atomic(output / "boundary.json", {"match": i, "pid": os.getpid()})
                while not stop.wait(0.02):
                    pass
                check()
        return 0
    except InterruptedError:
        atomic(output / "worker-terminal.json", {"signals": events, "status": "INTERRUPTED"})
        return EXIT_INTERRUPTED
    except Exception as exc:
        atomic(
            output / "worker-terminal.json",
            {"status": "SCIENTIFIC_OR_INTEGRITY_FAILURE", "error": type(exc).__name__},
        )
        return EXIT_INTEGRITY


def usage(pid: int) -> tuple[float, int]:
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    return (
        (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK"),
        int(fields[21]) * os.sysconf("SC_PAGE_SIZE"),
    )


def working_disk_bytes(output: Path) -> int:
    total = 0
    for path in output.iterdir():
        try:
            info = path.stat(follow_symlinks=False)
        except FileNotFoundError:
            # Atomic receipt renames can remove a temporary name between listing and stat.
            continue
        if stat.S_ISREG(info.st_mode):
            total += info.st_size
    return total


def supervise(
    root: Path, output: Path, count: int, pause: int = -1, wall_limit: float | None = None
) -> int:
    record = bound_record(root, output, count)
    if record["status"] not in ("RESERVED", "CONTINUATION_RESERVED"):
        raise ValueError("attempt not reserved")
    token = root / f"{record['scope_sha256']}.attempt-{record['attempt']}"
    fd = os.open(token, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    os.fsync(fd)
    os.close(fd)
    fsync_dir(root)
    record["status"] = "RUNNING"
    store_ledger(root, count, record)
    start = time.monotonic()
    initial_cpu, initial_wall = record["cpu_used"], record["wall_used"]
    remaining_cpu = record["budget"]["cpu_s"] - record["cpu_used"]
    remaining_wall = record["budget"]["wall_s"] - record["wall_used"]
    limit = min(remaining_wall, wall_limit if wall_limit is not None else remaining_wall)
    supervisor_pid = os.getpid()
    child = subprocess.Popen(
        [
            sys.executable,
            "-m",
            MODULE,
            "_worker",
            "--output",
            str(output),
            "--count",
            str(count),
            "--start",
            str(len(record["seals"])),
            "--pause",
            str(pause),
        ],
        start_new_session=True,
        preexec_fn=lambda: _child_limits(supervisor_pid, remaining_cpu),
    )
    atomic(
        output / "processes.json",
        {
            "supervisor_pid": supervisor_pid,
            "supervisor_start_ticks": Path(f"/proc/{supervisor_pid}/stat")
            .read_text()
            .rsplit(")", 1)[1]
            .split()[19],
            "worker_pid": child.pid,
            "attempt": record["attempt"],
        },
    )

    def hard_budget_stop() -> None:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        record["status"] = "FAILED_PERMANENTLY"
        try:
            store_ledger(root, count, record)
            atomic(
                output / "status.json", {"status": "FAILED_PERMANENTLY", "exit_code": EXIT_BUDGET}
            )
        finally:
            os._exit(EXIT_BUDGET)

    # Covers hung feature construction and independent verification, beyond the polling loop.
    watchdog = threading.Timer(max(0.01, remaining_wall) + 2.5, hard_budget_stop)
    watchdog.daemon = True
    watchdog.start()
    reason = "EXIT"
    peak_rss = 0
    sent_at: float | None = None
    last_telemetry = -1.0
    cpu = 0.0
    while True:
        waited, wait_status, child_usage = os.wait4(child.pid, os.WNOHANG)
        if waited:
            child.returncode = os.waitstatus_to_exitcode(wait_status)
            cpu = child_usage.ru_utime + child_usage.ru_stime
            peak_rss = max(peak_rss, child_usage.ru_maxrss * 1024)
            break
        wall = time.monotonic() - start
        try:
            cpu, rss = usage(child.pid)
        except (OSError, ValueError, IndexError):
            rss = 0
        _, supervisor_rss = usage(os.getpid())
        rss += supervisor_rss
        peak_rss = max(peak_rss, rss)
        disk = working_disk_bytes(output)
        if wall - last_telemetry >= 1:
            telemetry(
                output,
                {
                    "attempt": record["attempt"],
                    "wall_s": wall,
                    "cpu_s": cpu,
                    "rss_bytes": rss,
                    "disk_bytes": disk,
                    "worker_pid": child.pid,
                },
            )
            last_telemetry = wall
        budget_hit = (
            cpu >= remaining_cpu
            or rss > record["budget"]["rss_bytes"]
            or disk > record["budget"]["disk_bytes"]
            or wall >= remaining_wall
        )
        if sent_at is None and (wall >= limit or budget_hit):
            reason = "BUDGET" if budget_hit else "SUPERVISOR_TIMEOUT"
            os.killpg(child.pid, signal.SIGTERM)
            sent_at = wall
        elif sent_at is not None and wall - sent_at >= 2.5:
            os.killpg(child.pid, signal.SIGKILL)
        time.sleep(0.02)
    # wait4 supplies actual CPU accounting and kernel signal status, including sudden death.
    code = child.wait()
    record["cpu_used"] += cpu + time.process_time()
    record["wall_used"] += time.monotonic() - start
    seals = [
        s.digest(read(output / f"match-{i}.json"))
        for i in range(4)
        if (output / f"match-{i}.json").exists()
    ]
    attestation = {
        "scope_sha256": record["scope_sha256"],
        "output": record["output"],
        "protocol_sha256": s.PROTOCOL_SHA256,
        "attempt": record["attempt"],
        "wait_returncode": code,
        "reason": reason,
        "seals": seals,
        "cpu_used": record["cpu_used"],
        "wall_used": record["wall_used"],
        "supervisor_pid": supervisor_pid,
        "worker_pid": child.pid,
        "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "peak_rss_bytes": peak_rss,
        "outcome_accessed": False,
    }
    record["seals"] = seals
    record["status"] = "FAILED_PERMANENTLY"
    result_code = EXIT_BUDGET if reason == "BUDGET" else EXIT_WORKER
    try:
        receipts = v.verify_prefix(output, count, seals)
        terminal_path = output / "worker-terminal.json"
        if terminal_path.exists() and read(terminal_path)["status"] != "INTERRUPTED":
            raise ValueError("known scientific or integrity failure overrides signal status")
        if code == 0 and reason == "EXIT" and len(receipts) == 4:
            aggregate = v.aggregate(receipts)
            # Commit only after independent full readback and numerical recomputation.
            manifest = {
                "scope_sha256": record["scope_sha256"],
                "seals": seals,
                "aggregate": aggregate,
                "status": "COMPLETED_VERIFIED_SYNTHETIC_ONLY",
            }
            verify_cpu = time.process_time() + cpu
            if (
                initial_cpu + verify_cpu >= record["budget"]["cpu_s"]
                or initial_wall + time.monotonic() - start >= record["budget"]["wall_s"]
                or resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
                > record["budget"]["rss_bytes"]
            ):
                raise ValueError("verification resource ceiling exceeded")
            atomic(output / "result.json", signed(manifest, record["key"]))
            if authenticated(output / "result.json", record["key"]) != manifest:
                raise ValueError("final manifest readback failed")
            record["status"] = "COMPLETED_VERIFIED"
            result_code = 0
        elif reason == "SUPERVISOR_TIMEOUT" and code == EXIT_INTERRUPTED and 0 < len(seals) < 4:
            terminal = read(output / "worker-terminal.json")
            if (
                record["continuation_predeclared"]
                and record["attempt"] == 0
                and terminal["status"] == "INTERRUPTED"
                and terminal["signals"]
                and all(
                    e["sender_pid"] == supervisor_pid and e["signal"] == signal.SIGTERM
                    for e in terminal["signals"]
                )
            ):
                record["status"] = "CONTINUATION_READY_SAME_SCOPE"
                result_code = EXIT_INTERRUPTED
        elif code == -signal.SIGKILL and reason == "EXIT" and 0 < len(seals) < 4:
            if record["continuation_predeclared"] and record["attempt"] == 0:
                record["status"] = "CONTINUATION_READY_SAME_SCOPE"
                result_code = EXIT_INTERRUPTED
    except (ValueError, KeyError, OSError, TypeError, IndexError) as exc:
        print(f"INDEPENDENT_VERIFICATION_FAILED: {exc}", file=sys.stderr, flush=True)
        result_code = EXIT_INTEGRITY
    # Charge supervisor imports/verification and kernel-accounted worker CPU.
    record["cpu_used"] = initial_cpu + cpu + time.process_time()
    record["wall_used"] = initial_wall + time.monotonic() - start
    attestation.update(cpu_used=record["cpu_used"], wall_used=record["wall_used"])
    atomic(output / f"postmortem-{record['attempt']}.json", signed(attestation, record["key"]))
    atomic(output / "postmortem.json", signed(attestation, record["key"]))
    store_ledger(root, count, record)
    atomic(output / "status.json", {"status": record["status"], "exit_code": result_code})
    watchdog.cancel()
    return result_code


def continue_campaign(root: Path, output: Path, count: int) -> None:
    record = bound_record(root, output, count)
    if record["status"] != "CONTINUATION_READY_SAME_SCOPE":
        raise ValueError("campaign is not continuation ready")
    # Claim the one continuation before verification; a failed check consumes it permanently.
    fd = os.open(
        root / f"{record['scope_sha256']}.continuation",
        os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
        0o600,
    )
    os.fsync(fd)
    os.close(fd)
    fsync_dir(root)
    replay_start, replay_cpu = time.monotonic(), time.process_time()
    try:
        attestation = authenticated(output / "postmortem.json", record["key"])
        if (
            record["status"] != "CONTINUATION_READY_SAME_SCOPE"
            or record["attempt"] != 0
            or not record["continuation_predeclared"]
            or attestation["scope_sha256"] != record["scope_sha256"]
            or attestation["output"] != record["output"]
            or attestation["seals"] != record["seals"]
            or attestation["cpu_used"] != record["cpu_used"]
            or attestation["wall_used"] != record["wall_used"]
            or attestation["protocol_sha256"] != s.PROTOCOL_SHA256
            or attestation["attempt"] != 0
            or attestation["outcome_accessed"] is not False
            or not 0 < len(record["seals"]) < 4
        ):
            raise ValueError("missing trustworthy independent interruption evidence")
        if (attestation["reason"], attestation["wait_returncode"]) not in (
            ("SUPERVISOR_TIMEOUT", EXIT_INTERRUPTED),
            ("EXIT", -signal.SIGKILL),
        ):
            raise ValueError("noncontinuable cause")
        terminal_path = output / "worker-terminal.json"
        if terminal_path.exists() and read(terminal_path)["status"] != "INTERRUPTED":
            raise ValueError("known scientific or integrity failure is permanently terminal")
        # Conservative predeclared reserve; never choose budgets based on metric values.
        if any(
            record["budget"][k] - record[u] < 30 * (4 - len(record["seals"]))
            for k, u in (("cpu_s", "cpu_used"), ("wall_s", "wall_used"))
        ):
            raise ValueError("insufficient remaining cumulative budget")
        receipts = v.verify_prefix(output, count, record["seals"])
        random_models = s.models()
        for i, receipt in enumerate(receipts):
            expected = {
                **s.score_match(s.MATCHES[i], count, random_models),
                "scope_sha256": record["scope_sha256"],
                "previous_sha256": receipt["previous_sha256"],
            }
            if s.canonical(expected) != s.canonical(receipt):
                raise ValueError("sealed receipt bitwise parity failed")
        record["cpu_used"] += time.process_time() - replay_cpu
        record["wall_used"] += time.monotonic() - replay_start
        if any(
            record["budget"][k] - record[u] < 30 * (4 - len(receipts))
            for k, u in (("cpu_s", "cpu_used"), ("wall_s", "wall_used"))
        ):
            raise ValueError("insufficient remaining budget after parity verification")
        record.update(attempt=1, status="CONTINUATION_RESERVED")
        store_ledger(root, count, record)
    except Exception:
        record["status"] = "FAILED_PERMANENTLY"
        store_ledger(root, count, record)
        raise


def verify_complete(root: Path, output: Path, count: int) -> s.Document:
    record = bound_record(root, output, count)
    if record["status"] != "COMPLETED_VERIFIED":
        raise ValueError("campaign not complete")
    manifest = authenticated(output / "result.json", record["key"])
    receipts = v.verify_prefix(output, count, record["seals"])
    expected = {
        "scope_sha256": record["scope_sha256"],
        "seals": record["seals"],
        "aggregate": v.aggregate(receipts),
        "status": "COMPLETED_VERIFIED_SYNTHETIC_ONLY",
    }
    if manifest != expected:
        raise ValueError("final bundle differs")
    return manifest


def launch(
    root: Path,
    output: Path,
    count: int,
    *,
    continuation: bool = False,
    resume: bool = False,
    pause: int = -1,
    wall_limit: float | None = None,
) -> int:
    safe_path(output)
    if resume:
        continue_campaign(root, output, count)
        (output / "status.json").unlink(missing_ok=True)
        fsync_dir(output)
    else:
        reserve(root, output, count, continuation)
    command = [
        sys.executable,
        "-m",
        MODULE,
        "_supervise",
        "--output",
        str(output.resolve()),
        "--ledger-root",
        str(root.resolve()),
        "--count",
        str(count),
        "--pause",
        str(pause),
    ]
    if wall_limit is not None:
        if not math.isfinite(wall_limit) or wall_limit <= 0:
            raise ValueError("invalid per-attempt wall limit")
        command += ["--wall-limit", str(wall_limit)]
    with (output / "supervisor.log").open("ab", buffering=0) as log:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
            close_fds=True,
        )
    return process.pid


def main() -> int:
    parser = argparse.ArgumentParser(
        description="RES643 synthetic preparation only; no real authorization accepted"
    )
    parser.add_argument(
        "action", choices=("start", "continue", "verify", "status", "_worker", "_supervise")
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--ledger-root", type=Path)
    parser.add_argument("--count", type=int, default=2)
    parser.add_argument("--predeclare-continuation", action="store_true")
    parser.add_argument("--pause", type=int, default=-1, help="synthetic boundary fault fixture")
    parser.add_argument("--wall-limit", type=float)
    parser.add_argument("--start", type=int, default=0)
    args = parser.parse_args()
    try:
        safe_path(args.output)
        if args.action == "_worker":
            return worker(args.output, args.count, args.start, args.pause)
        if args.ledger_root is None:
            parser.error("--ledger-root is required and must remain stable across outputs")
        if args.action == "_supervise":
            return supervise(args.ledger_root, args.output, args.count, args.pause, args.wall_limit)
        if args.action in ("start", "continue"):
            pid = launch(
                args.ledger_root,
                args.output,
                args.count,
                continuation=args.predeclare_continuation,
                resume=args.action == "continue",
                pause=args.pause,
                wall_limit=args.wall_limit,
            )
            print(json.dumps({"supervisor_pid": pid, "synthetic_only": True}))
            return 0
        if args.action == "verify":
            manifest = verify_complete(args.ledger_root, args.output, args.count)
            print(json.dumps({"status": manifest["status"], "records": 72}))
            return 0
        record = bound_record(args.ledger_root, args.output, args.count)
        if record["status"] == "COMPLETED_VERIFIED":
            # Completion is a verified bundle state, never merely a ledger flag.
            verify_complete(args.ledger_root, args.output, args.count)
            print(json.dumps({"status": record["status"]}))
            return 0
        print(json.dumps({"status": record["status"]}))
        return EXIT_WORKER
    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        if (
            args.action == "_supervise"
            and args.ledger_root is not None
            and (
                not (args.output / "processes.json").exists()
                or read(args.output / "processes.json")["supervisor_pid"] == os.getpid()
            )
        ):
            record = bound_record(args.ledger_root, args.output, args.count)
            record["status"] = "FAILED_PERMANENTLY"
            store_ledger(args.ledger_root, args.count, record)
            atomic(
                args.output / "status.json",
                {"status": "FAILED_PERMANENTLY", "exit_code": EXIT_INTEGRITY},
            )
        print(f"REFUSED: {exc}", file=sys.stderr)
        return EXIT_INTEGRITY


if __name__ == "__main__":
    raise SystemExit(main())
