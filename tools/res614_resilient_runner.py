"""RES614 synthetic-only resilient execution runner (qualification prototype).

This is *not* a scorer and it is not a retry path for the consumed RES594 campaign. It
demonstrates, on artificial per-match units only, the execution properties the frozen scorer
lacked: durable supervision independent of an interactive session, SIGTERM sender attribution,
bounded graceful shutdown, atomic fsync'd commits, sealed per-match receipts with a hash chain,
partial-result classification, explicit timeout/resource enforcement and one-shot scope
consumption that survives crashes.

Hard refusals: paths containing the private evidence area, the historical RES594 scope hash,
and any authorisation that is not explicitly synthetic.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import resource
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_ID = "fpdbench.res614.synthetic-campaign"
HISTORICAL_SCOPE_SHA256 = "d359751e969767f30ed6e90c65b13d0eec49f11c9e33e1d2319b19530d28f2e0"
FORBIDDEN_FRAGMENTS = ("fpdbench-private", "res594")
MARKER = "SYNTHETIC_CAMPAIGN.json"

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_DUPLICATE = 3
EXIT_BAD_INPUT = 4
EXIT_INTERRUPTED = 143
EXIT_CRASH_INJECTED = 86
EXIT_WATCHDOG = 144


class DuplicateExecutionRefused(RuntimeError):
    """The one-shot scope was already consumed; no automatic retry exists."""


class Interrupted(RuntimeError):
    """A termination signal was received and the run is shutting down gracefully."""


class BudgetStop(RuntimeError):
    """A configured wall, CPU or RSS ceiling was exceeded."""


@dataclass(frozen=True)
class Config:
    matches: int = 4
    windows_per_match: int = 40
    seed: int = 614
    window_delay_s: float = 0.0
    wall_limit_s: float = 60.0
    cpu_limit_s: float = 60.0
    rss_limit_bytes: int = 1 << 30
    telemetry_every: int = 10
    grace_s: float = 2.0
    ignore_sigterm: bool = False  # fault injection: hung worker
    crash_after_windows: int = -1  # fault injection: hard exit without cleanup
    torn_write_at_match: int = -1  # fault injection: leave a partial .tmp, then crash

    def scope_sha256(self) -> str:
        body = {
            "schema": SCHEMA_ID,
            "matches": self.matches,
            "windows_per_match": self.windows_per_match,
            "seed": self.seed,
        }
        return hashlib.sha256(canonical(body)).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def assert_synthetic_location(path: Path) -> None:
    resolved = str(path.resolve()).lower()
    if any(fragment in resolved for fragment in FORBIDDEN_FRAGMENTS):
        raise PermissionError("refusing a path that could alias private or historical evidence")


def _fsync_dir(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write(path: Path, data: bytes) -> str:
    """Write-then-rename with file and directory fsync; returns the content SHA-256."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise
    _fsync_dir(path.parent)
    return hashlib.sha256(data).hexdigest()


def append_durable(path: Path, record: dict[str, Any]) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, canonical(record) + b"\n")
        os.fsync(fd)
    finally:
        os.close(fd)


def consume_scope(ledger_dir: Path, config: Config, campaign_dir: Path) -> Path:
    """One-shot consumption; O_EXCL refuses concurrent and repeated starts, even after a crash."""
    scope = config.scope_sha256()
    if scope == HISTORICAL_SCOPE_SHA256:
        raise PermissionError("the historical RES594 scope can never be consumed here")
    assert_synthetic_location(ledger_dir)
    ledger_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = ledger_dir / f".consumed-{scope}.json"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError as exc:
        raise DuplicateExecutionRefused(f"scope {scope[:12]} already consumed") from exc
    record = {
        "schema_id": SCHEMA_ID + ".ledger",
        "status": "CONSUMED_IRREVERSIBLY",
        "retry_allowed": False,
        "synthetic_only": True,
        "scope_sha256": scope,
        "campaign_directory": str(campaign_dir),
        "consumed_at_utc": utc_now(),
        "consumer_pid": os.getpid(),
    }
    with os.fdopen(fd, "wb") as stream:
        stream.write(canonical(record) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    _fsync_dir(ledger_dir)
    return path


def synthetic_window_score(seed: int, match: int, index: int) -> float:
    """Deterministic stand-in for a per-window metric. Not model output."""
    rng = random.Random(f"{seed}:{match}:{index}")
    return sum(rng.random() for _ in range(2_000)) / 2_000


class SignalWatcher:
    """Block SIGTERM/SIGINT/SIGHUP everywhere and dequeue them with sender attribution."""

    SIGNALS = (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)

    def __init__(
        self,
        ignore: bool = False,
        grace_s: float = 2.0,
        on_deadline: Callable[[], None] | None = None,
    ) -> None:
        self.stop = threading.Event()
        self.events: list[dict[str, Any]] = []
        self._ignore = ignore
        self._grace_s = grace_s
        self._on_deadline = on_deadline
        self._deadline_started = False
        signal.pthread_sigmask(signal.SIG_BLOCK, self.SIGNALS)
        self._thread = threading.Thread(target=self._loop, daemon=True, name="signal-watcher")
        self._thread.start()

    @staticmethod
    def _describe(pid: int) -> dict[str, Any]:
        info: dict[str, Any] = {"sender_pid": pid}
        try:
            info["sender_cmdline"] = (
                Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode()[:300]
            )
            stat = Path(f"/proc/{pid}/stat").read_text()
            info["sender_ppid"] = int(stat.rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            info["sender_exited_before_inspection"] = True
        return info

    def _loop(self) -> None:
        while True:
            siginfo = signal.sigwaitinfo(self.SIGNALS)
            event = {
                "signal": signal.Signals(siginfo.si_signo).name,
                "received_at_utc": utc_now(),
                "received_monotonic_s": time.monotonic(),
                "sender_uid": siginfo.si_uid,
                **self._describe(siginfo.si_pid),
            }
            self.events.append(event)
            if not self._ignore:
                self.stop.set()
                if self._on_deadline is not None and not self._deadline_started:
                    self._deadline_started = True
                    timer = threading.Timer(self._grace_s, self._on_deadline)
                    timer.daemon = True
                    timer.start()


def _rss_bytes() -> int:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024


def run_campaign(config: Config, campaign_dir: Path, ledger_dir: Path) -> int:
    assert_synthetic_location(campaign_dir)
    if campaign_dir.exists() and any(campaign_dir.iterdir()):
        raise DuplicateExecutionRefused("campaign directory already populated")
    consume_scope(ledger_dir, config, campaign_dir)
    campaign_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    receipts = campaign_dir / "receipts"
    receipts.mkdir(mode=0o700, exist_ok=True)
    marker = {
        "schema_id": SCHEMA_ID,
        "synthetic_only": True,
        "scope_sha256": config.scope_sha256(),
        "config": {
            "matches": config.matches,
            "windows_per_match": config.windows_per_match,
            "seed": config.seed,
        },
        "started_at_utc": utc_now(),
        "pid": os.getpid(),
    }
    atomic_write(campaign_dir / MARKER, canonical(marker) + b"\n")
    sealed: list[dict[str, Any]] = []
    windows_done = 0

    def force_exit() -> None:
        """Bounded shutdown: if graceful stop overruns the grace period, record and exit."""
        record = {
            "schema_id": SCHEMA_ID + ".terminal",
            "status": "INTERRUPTED",
            "reason": "grace period exceeded; forced exit",
            "watchdog_forced": True,
            "retry_allowed": False,
            "windows_done": windows_done,
            "sealed_matches": [item["match"] for item in sealed],
            "signal_events": watcher.events,
            "at_utc": utc_now(),
        }
        try:
            atomic_write(campaign_dir / ".interrupted.json", canonical(record) + b"\n")
        finally:
            os._exit(EXIT_WATCHDOG)

    watcher = SignalWatcher(
        ignore=config.ignore_sigterm, grace_s=config.grace_s, on_deadline=force_exit
    )
    start_wall, start_cpu = time.monotonic(), time.process_time()
    telemetry = campaign_dir / "telemetry.jsonl"
    chain = "0" * 64
    try:
        for match in range(config.matches):
            scores: list[float] = []
            for index in range(config.windows_per_match):
                if watcher.stop.is_set():
                    raise Interrupted("termination signal received")
                wall = time.monotonic() - start_wall
                cpu = time.process_time() - start_cpu
                if wall > config.wall_limit_s:
                    raise BudgetStop("wall-time ceiling exceeded")
                if cpu > config.cpu_limit_s:
                    raise BudgetStop("CPU-time ceiling exceeded")
                if _rss_bytes() > config.rss_limit_bytes:
                    raise BudgetStop("RSS ceiling exceeded")
                if config.window_delay_s:
                    time.sleep(config.window_delay_s)
                scores.append(synthetic_window_score(config.seed, match, index))
                windows_done += 1
                if windows_done == config.crash_after_windows:
                    os._exit(EXIT_CRASH_INJECTED)
                if windows_done % config.telemetry_every == 0:
                    append_durable(
                        telemetry,
                        {
                            "windows_done": windows_done,
                            "match": match,
                            "wall_s": round(wall, 3),
                            "cpu_s": round(cpu, 3),
                            "rss_bytes": _rss_bytes(),
                            "sealed_matches": len(sealed),
                        },
                    )
            if config.torn_write_at_match == match:
                torn = receipts / f".match-{match}.torn.tmp"
                torn.write_bytes(b'{"partial":')
                os._exit(EXIT_CRASH_INJECTED)
            body = {
                "schema_id": SCHEMA_ID + ".match-receipt",
                "match": match,
                "windows": len(scores),
                "mean_score": sum(scores) / len(scores),
                "previous_receipt_sha256": chain,
            }
            digest = hashlib.sha256(canonical(body)).hexdigest()
            atomic_write(receipts / f"match-{match}.json", canonical({**body, "sha256": digest}))
            chain = digest
            sealed.append({"match": match, "sha256": digest})
        result = {
            "schema_id": SCHEMA_ID + ".result",
            "status": "COMPLETED",
            "synthetic_only": True,
            "scope_sha256": config.scope_sha256(),
            "receipts": sealed,
            "final_chain_sha256": chain,
            "windows": windows_done,
        }
        result["result_sha256"] = hashlib.sha256(canonical(result)).hexdigest()
        atomic_write(campaign_dir / "campaign-result.json", canonical(result) + b"\n")
        return EXIT_OK
    except Interrupted:
        _write_terminal(campaign_dir, "INTERRUPTED", "signal", watcher, sealed, windows_done)
        return EXIT_INTERRUPTED
    except BudgetStop as exc:
        _write_terminal(campaign_dir, "FAILED", str(exc), watcher, sealed, windows_done)
        return EXIT_FAILED
    except BaseException as exc:
        _write_terminal(campaign_dir, "FAILED", type(exc).__name__, watcher, sealed, windows_done)
        raise


def _write_terminal(
    campaign_dir: Path,
    status: str,
    reason: str,
    watcher: SignalWatcher,
    sealed: list[dict[str, Any]],
    windows_done: int,
) -> None:
    name = ".interrupted.json" if status == "INTERRUPTED" else ".failed.json"
    record = {
        "schema_id": SCHEMA_ID + ".terminal",
        "status": status,
        "reason": reason,
        "retry_allowed": False,
        "windows_done": windows_done,
        "sealed_matches": [item["match"] for item in sealed],
        "signal_events": watcher.events,
        "at_utc": utc_now(),
    }
    atomic_write(campaign_dir / name, canonical(record) + b"\n")


def classify(campaign_dir: Path, expected_matches: int | None = None) -> dict[str, Any]:
    """Read-only state classification used for partial-result identification."""
    marker_path = campaign_dir / MARKER
    if not marker_path.exists():
        return {"state": "NOT_STARTED"}
    marker = json.loads(marker_path.read_text())
    matches = expected_matches if expected_matches is not None else marker["config"]["matches"]
    receipts_dir = campaign_dir / "receipts"
    sealed, problems = [], []
    chain = "0" * 64
    for match in range(matches):
        path = receipts_dir / f"match-{match}.json"
        if not path.exists():
            continue
        try:
            doc = json.loads(path.read_text())
            claimed = doc.pop("sha256")
            if hashlib.sha256(canonical(doc)).hexdigest() != claimed:
                problems.append(f"match-{match}: content hash mismatch")
            elif doc["previous_receipt_sha256"] != chain:
                problems.append(f"match-{match}: chain link mismatch")
            else:
                sealed.append(match)
                chain = claimed
        except (ValueError, KeyError):
            problems.append(f"match-{match}: unreadable receipt")
    strays = sorted(p.name for p in campaign_dir.rglob(".*.tmp"))
    state = "CRASHED_OR_KILLED"
    if (campaign_dir / "campaign-result.json").exists():
        state = "COMPLETED"
    elif (campaign_dir / ".failed.json").exists():
        state = "FAILED"
    elif (campaign_dir / ".interrupted.json").exists():
        state = "INTERRUPTED"
    if problems:
        state = "CORRUPT"
    return {
        "state": state,
        "sealed_matches": sealed,
        "missing_matches": [m for m in range(matches) if m not in sealed],
        "stray_tmp_files": strays,
        "problems": problems,
        "partial_results_are_scientifically_usable": False,
    }


def verify_completed(campaign_dir: Path) -> bool:
    result = json.loads((campaign_dir / "campaign-result.json").read_text())
    claimed = result.pop("result_sha256")
    if hashlib.sha256(canonical(result)).hexdigest() != claimed:
        return False
    info = classify(campaign_dir, len(result["receipts"]))
    return info["state"] == "COMPLETED" and not info["missing_matches"]


def _worker_args(config: Config, campaign: Path, ledger: Path) -> list[str]:
    args = [
        "--campaign-dir",
        str(campaign),
        "--ledger-dir",
        str(ledger),
        "--matches",
        str(config.matches),
        "--windows-per-match",
        str(config.windows_per_match),
        "--seed",
        str(config.seed),
        "--window-delay-s",
        str(config.window_delay_s),
        "--wall-limit-s",
        str(config.wall_limit_s),
        "--cpu-limit-s",
        str(config.cpu_limit_s),
        "--rss-limit-bytes",
        str(config.rss_limit_bytes),
        "--telemetry-every",
        str(config.telemetry_every),
        "--grace-s",
        str(config.grace_s),
        "--crash-after-windows",
        str(config.crash_after_windows),
        "--torn-write-at-match",
        str(config.torn_write_at_match),
    ]
    if config.ignore_sigterm:
        args.append("--ignore-sigterm")
    return args


def supervise(config: Config, campaign: Path, ledger: Path, hard_timeout_s: float) -> int:
    """Run the worker in its own session; enforce a hard timeout; record who ended it."""
    signal.signal(signal.SIGHUP, signal.SIG_IGN)  # terminal teardown must not kill supervision
    log_dir = campaign.parent / f"{campaign.name}.supervisor"
    log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    started = time.monotonic()
    with (log_dir / "worker.out").open("wb") as out:
        worker = subprocess.Popen(
            [
                sys.executable,
                os.fspath(Path(__file__)),
                "run",
                *_worker_args(config, campaign, ledger),
            ],
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
    terminated_by = "none"
    while worker.poll() is None:
        if time.monotonic() - started > hard_timeout_s:
            terminated_by = "supervisor_timeout_sigterm"
            os.killpg(worker.pid, signal.SIGTERM)
            try:
                worker.wait(timeout=config.grace_s)
            except subprocess.TimeoutExpired:
                terminated_by = "supervisor_timeout_sigkill_after_grace"
                os.killpg(worker.pid, signal.SIGKILL)
                worker.wait()
            break
        time.sleep(0.02)
    code = worker.returncode
    record = {
        "schema_id": SCHEMA_ID + ".supervisor",
        "supervisor_pid": os.getpid(),
        "worker_pid": worker.pid,
        "worker_returncode": code,
        "worker_signal": signal.Signals(-code).name if code is not None and code < 0 else None,
        "terminated_by": terminated_by,
        "hard_timeout_s": hard_timeout_s,
        "elapsed_s": round(time.monotonic() - started, 3),
        "ended_at_utc": utc_now(),
    }
    atomic_write(log_dir / "supervisor.json", canonical(record) + b"\n")
    return 0


def launch_detached(config: Config, campaign: Path, ledger: Path, hard_timeout_s: float) -> int:
    """Start the supervisor in a new session and return immediately (survives the caller)."""
    log_dir = campaign.parent / f"{campaign.name}.supervisor"
    log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (log_dir / "supervisor.out").open("wb") as out:
        proc = subprocess.Popen(
            [
                sys.executable,
                os.fspath(Path(__file__)),
                "supervise",
                *_worker_args(config, campaign, ledger),
                "--hard-timeout-s",
                str(hard_timeout_s),
            ],
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
    print(json.dumps({"supervisor_pid": proc.pid, "campaign_directory": str(campaign)}))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="RES614 synthetic-only resilient runner")
    parser.add_argument("command", choices=["run", "supervise", "launch", "inspect", "verify"])
    parser.add_argument("--campaign-dir", type=Path, required=True)
    parser.add_argument("--ledger-dir", type=Path)
    parser.add_argument("--matches", type=int, default=4)
    parser.add_argument("--windows-per-match", type=int, default=40)
    parser.add_argument("--seed", type=int, default=614)
    parser.add_argument("--window-delay-s", type=float, default=0.0)
    parser.add_argument("--wall-limit-s", type=float, default=60.0)
    parser.add_argument("--cpu-limit-s", type=float, default=60.0)
    parser.add_argument("--rss-limit-bytes", type=int, default=1 << 30)
    parser.add_argument("--telemetry-every", type=int, default=10)
    parser.add_argument("--grace-s", type=float, default=2.0)
    parser.add_argument("--hard-timeout-s", type=float, default=120.0)
    parser.add_argument("--ignore-sigterm", action="store_true")
    parser.add_argument("--crash-after-windows", type=int, default=-1)
    parser.add_argument("--torn-write-at-match", type=int, default=-1)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    campaign: Path = args.campaign_dir
    try:
        assert_synthetic_location(campaign)
    except PermissionError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return EXIT_BAD_INPUT
    if args.command == "inspect":
        print(json.dumps(classify(campaign), indent=2, sort_keys=True))
        return 0
    if args.command == "verify":
        ok = verify_completed(campaign)
        print(json.dumps({"verified": ok}))
        return 0 if ok else 1
    config = Config(
        matches=args.matches,
        windows_per_match=args.windows_per_match,
        seed=args.seed,
        window_delay_s=args.window_delay_s,
        wall_limit_s=args.wall_limit_s,
        cpu_limit_s=args.cpu_limit_s,
        rss_limit_bytes=args.rss_limit_bytes,
        telemetry_every=args.telemetry_every,
        grace_s=args.grace_s,
        ignore_sigterm=args.ignore_sigterm,
        crash_after_windows=args.crash_after_windows,
        torn_write_at_match=args.torn_write_at_match,
    )
    ledger: Path = args.ledger_dir or campaign.parent / f"{campaign.name}.ledger"
    try:
        if args.command == "run":
            return run_campaign(config, campaign, ledger)
        if args.command == "supervise":
            return supervise(config, campaign, ledger, args.hard_timeout_s)
        return launch_detached(config, campaign, ledger, args.hard_timeout_s)
    except DuplicateExecutionRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return EXIT_DUPLICATE
    except PermissionError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return EXIT_BAD_INPUT


if __name__ == "__main__":
    raise SystemExit(main())
