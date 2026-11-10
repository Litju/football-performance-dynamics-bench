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
import stat
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA_ID = "fpdbench.res614.synthetic-campaign"
HISTORICAL_SCOPE_SHA256 = "d359751e969767f30ed6e90c65b13d0eec49f11c9e33e1d2319b19530d28f2e0"
FORBIDDEN_FRAGMENTS = ("fpdbench-private", "res594")
MARKER = "SYNTHETIC_CAMPAIGN.json"
LEDGER_SCHEMA_ID = SCHEMA_ID + ".ledger"
LEDGER_STATUS = "CONSUMED_IRREVERSIBLY"

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_DUPLICATE = 3
EXIT_BAD_INPUT = 4
EXIT_INTERRUPTED = 143
EXIT_CRASH_INJECTED = 86
EXIT_WATCHDOG = 144
EXIT_UNVERIFIED = 7
EXIT_SUPERVISED_TIMEOUT = 5
EXIT_WORKER_FAILED = 6
EXIT_NOT_FINISHED = 8

STATUS_EXIT = {
    "COMPLETED_VERIFIED": EXIT_OK,
    "WORKER_TIMED_OUT": EXIT_SUPERVISED_TIMEOUT,
    "WORKER_FAILED": EXIT_WORKER_FAILED,
    "WORKER_KILLED": EXIT_WORKER_FAILED,
    "COMPLETION_UNVERIFIED": EXIT_UNVERIFIED,
}


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
    forge_empty_result: bool = False  # fault injection: commit a self-consistent empty result

    def __post_init__(self) -> None:
        for name in ("matches", "windows_per_match", "telemetry_every"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if type(self.seed) is not int:
            raise ValueError("seed must be an integer")
        for name in ("wall_limit_s", "cpu_limit_s", "grace_s", "window_delay_s"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must not be negative")

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


def _ledger_root_problem(ledger_dir: Path, campaign_dir: Path) -> str | None:
    """Describe why an existing ledger root is unusable, or return None when it is valid."""
    try:
        assert_synthetic_location(ledger_dir)
    except PermissionError as exc:
        return str(exc)
    ledger_root = ledger_dir.resolve()
    campaign_root = campaign_dir.resolve()
    if ledger_root == campaign_root or campaign_root in ledger_root.parents:
        return "the one-shot ledger root must be outside the campaign output directory"
    try:
        info = os.lstat(ledger_dir)
    except OSError:
        return "the one-shot ledger root is missing or unreadable"
    if stat.S_ISLNK(info.st_mode):
        return "the one-shot ledger root must not be a symbolic link"
    if not stat.S_ISDIR(info.st_mode):
        return "the one-shot ledger root must be a directory"
    if info.st_uid != os.geteuid():
        return "the one-shot ledger root must be owned by the current user"
    if stat.S_IMODE(info.st_mode) & 0o077:
        return "the one-shot ledger root must be owner-private (mode 0700)"
    return None


def _prepare_ledger_root(ledger_dir: Path, campaign_dir: Path) -> None:
    """Create and validate the explicit, stable, owner-private one-shot authority root."""
    ledger_root = ledger_dir.resolve()
    campaign_root = campaign_dir.resolve()
    if ledger_root == campaign_root or campaign_root in ledger_root.parents:
        raise PermissionError(
            "the one-shot ledger root must be outside the campaign output directory"
        )
    try:
        os.lstat(ledger_dir)
    except FileNotFoundError:
        ledger_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    problem = _ledger_root_problem(ledger_dir, campaign_dir)
    if problem is not None:
        raise PermissionError(problem)


def consume_scope(ledger_dir: Path, config: Config, campaign_dir: Path) -> Path:
    """One-shot consumption; O_EXCL refuses concurrent and repeated starts, even after a crash."""
    scope = config.scope_sha256()
    if scope == HISTORICAL_SCOPE_SHA256:
        raise PermissionError("the historical RES594 scope can never be consumed here")
    _prepare_ledger_root(ledger_dir, campaign_dir)
    path = ledger_dir / f".consumed-{scope}.json"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError as exc:
        raise DuplicateExecutionRefused(f"scope {scope[:12]} already consumed") from exc
    record = {
        "schema_id": LEDGER_SCHEMA_ID,
        "status": LEDGER_STATUS,
        "retry_allowed": False,
        "synthetic_only": True,
        "scope_sha256": scope,
        "config": {
            "matches": config.matches,
            "windows_per_match": config.windows_per_match,
            "seed": config.seed,
        },
        "campaign_directory": str(campaign_dir.resolve()),
        "consumed_at_utc": utc_now(),
        "consumer_pid": os.getpid(),
    }
    record["record_sha256"] = hashlib.sha256(canonical(record)).hexdigest()
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
    marker["metadata_sha256"] = hashlib.sha256(canonical(marker)).hexdigest()
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
            sealed.append({"match": match, "windows": len(scores), "sha256": digest})
        result = {
            "schema_id": SCHEMA_ID + ".result",
            "status": "COMPLETED",
            "synthetic_only": True,
            "scope_sha256": config.scope_sha256(),
            "matches": config.matches,
            "windows_per_match": config.windows_per_match,
            "receipts": sealed,
            "final_chain_sha256": chain,
            "windows": windows_done,
        }
        if config.forge_empty_result:
            result.update(receipts=[], final_chain_sha256="0" * 64, matches=0, windows=0)
        result["result_sha256"] = hashlib.sha256(canonical(result)).hexdigest()
        atomic_write(campaign_dir / "campaign-result.json", canonical(result) + b"\n")
        problems = verify_campaign(campaign_dir, ledger_dir)
        if problems:
            reason = "completion verification failed: " + "; ".join(problems)
            _write_terminal(campaign_dir, "FAILED", reason[:2000], watcher, sealed, windows_done)
            print(f"UNVERIFIED: {reason}", file=sys.stderr)
            return EXIT_UNVERIFIED
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


_RECEIPT_KEYS = {
    "schema_id",
    "match",
    "windows",
    "mean_score",
    "previous_receipt_sha256",
    "sha256",
}
_RESULT_KEYS = {
    "schema_id",
    "status",
    "synthetic_only",
    "scope_sha256",
    "matches",
    "windows_per_match",
    "receipts",
    "final_chain_sha256",
    "windows",
    "result_sha256",
}
_LEDGER_KEYS = {
    "schema_id",
    "status",
    "retry_allowed",
    "synthetic_only",
    "scope_sha256",
    "config",
    "campaign_directory",
    "consumed_at_utc",
    "consumer_pid",
    "record_sha256",
}


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        doc = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def _is_sha(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= set("0123456789abcdef")


def _ledger_file_problem(path: Path) -> str | None:
    """The ledger file must be a regular, owner-private file, never a link or shared inode."""
    try:
        info = os.lstat(path)
    except OSError:
        return "one-shot ledger missing or unreadable"
    if stat.S_ISLNK(info.st_mode):
        return "one-shot ledger must not be a symbolic link"
    if not stat.S_ISREG(info.st_mode):
        return "one-shot ledger must be a regular file"
    if info.st_uid != os.geteuid():
        return "one-shot ledger must be owned by the current user"
    if stat.S_IMODE(info.st_mode) & 0o077:
        return "one-shot ledger must be owner-private (mode 0600)"
    return None


def _ledger_record_problems(
    ledger: dict[str, Any], config: Config, campaign_dir: Path
) -> list[str]:
    """Validate the exact consumption record and its binding to this campaign."""
    if set(ledger) != _LEDGER_KEYS:
        return ["one-shot ledger schema invalid"]
    claimed = ledger["record_sha256"]
    body = {key: value for key, value in ledger.items() if key != "record_sha256"}
    if not _is_sha(claimed) or hashlib.sha256(canonical(body)).hexdigest() != claimed:
        return ["one-shot ledger hash mismatch"]
    scope = config.scope_sha256()
    problems: list[str] = []
    if ledger["schema_id"] != LEDGER_SCHEMA_ID:
        problems.append("one-shot ledger schema identity mismatch")
    if ledger["synthetic_only"] is not True:
        problems.append("one-shot ledger is not marked synthetic-only")
    if ledger["status"] != LEDGER_STATUS:
        problems.append("one-shot ledger status is not CONSUMED_IRREVERSIBLY")
    if ledger["retry_allowed"] is not False:
        problems.append("one-shot ledger permits retry")
    if ledger["scope_sha256"] != scope:
        problems.append("one-shot ledger scope mismatch")
    if ledger["config"] != {
        "matches": config.matches,
        "windows_per_match": config.windows_per_match,
        "seed": config.seed,
    }:
        problems.append("one-shot ledger configuration mismatch")
    if ledger["campaign_directory"] != str(campaign_dir.resolve()):
        problems.append("one-shot ledger is bound to a different campaign directory")
    if type(ledger["consumer_pid"]) is not int or ledger["consumer_pid"] < 1:
        problems.append("one-shot ledger consumer PID invalid")
    consumed_at = ledger["consumed_at_utc"]
    try:
        if not isinstance(consumed_at, str):
            raise ValueError("not a string")
        datetime.strptime(consumed_at, "%Y-%m-%dT%H:%M:%SZ")
        valid_timestamp = True
    except ValueError:
        valid_timestamp = False
    if not valid_timestamp:
        problems.append("one-shot ledger consumption timestamp invalid")
    return problems


def _frozen_campaign(
    campaign_dir: Path, ledger_dir: Path | None, problems: list[str]
) -> Config | None:
    """Return the independently frozen configuration, or record why it cannot be trusted."""
    marker = _load_json(campaign_dir / MARKER)
    if marker is None:
        problems.append("campaign metadata missing or unreadable")
        return None
    claimed = marker.pop("metadata_sha256", None)
    if claimed != hashlib.sha256(canonical(marker)).hexdigest():
        problems.append("campaign metadata hash mismatch")
        return None
    cfg = marker.get("config")
    try:
        assert isinstance(cfg, dict) and set(cfg) == {"matches", "windows_per_match", "seed"}
        config = Config(**cfg)
    except (AssertionError, TypeError, ValueError):
        problems.append("campaign metadata configuration invalid")
        return None
    if marker.get("synthetic_only") is not True or marker.get("scope_sha256") != (
        config.scope_sha256()
    ):
        problems.append("campaign metadata scope does not match its configuration")
        return None
    if ledger_dir is None:
        problems.append("one-shot ledger root not supplied; frozen scope cannot be confirmed")
        return None
    root_problem = _ledger_root_problem(ledger_dir, campaign_dir)
    if root_problem is not None:
        problems.append(root_problem)
        return None
    ledger_path = ledger_dir / f".consumed-{config.scope_sha256()}.json"
    file_problem = _ledger_file_problem(ledger_path)
    if file_problem is not None:
        problems.append(file_problem)
        return None
    ledger = _load_json(ledger_path)
    if ledger is None:
        problems.append("one-shot ledger missing, empty or malformed")
        return None
    ledger_problems = _ledger_record_problems(ledger, config, campaign_dir)
    if ledger_problems:
        problems.extend(ledger_problems)
        return None
    return config


def _check_receipts(
    campaign_dir: Path, config: Config, problems: list[str]
) -> list[dict[str, Any]]:
    """Validate the on-disk receipt chain against the frozen match count; return sealed receipts."""
    receipts_dir = campaign_dir / "receipts"
    expected_names = {f"match-{m}.json" for m in range(config.matches)}
    present = (
        {p.name for p in receipts_dir.glob("match-*.json")} if receipts_dir.is_dir() else set()
    )
    for extra in sorted(present - expected_names):
        problems.append(f"unexpected receipt file {extra}")
    sealed: list[dict[str, Any]] = []
    chain = "0" * 64
    for match in range(config.matches):
        doc = _load_json(receipts_dir / f"match-{match}.json")
        if doc is None:
            if f"match-{match}.json" in present:
                problems.append(f"match-{match}: unreadable receipt")
            break  # later receipts cannot be trusted without their predecessor
        claimed = doc.get("sha256")
        body = {k: v for k, v in doc.items() if k != "sha256"}
        if set(doc) != _RECEIPT_KEYS or doc.get("schema_id") != SCHEMA_ID + ".match-receipt":
            problems.append(f"match-{match}: receipt schema invalid")
        elif hashlib.sha256(canonical(body)).hexdigest() != claimed:
            problems.append(f"match-{match}: content hash mismatch")
        elif doc["previous_receipt_sha256"] != chain:
            problems.append(f"match-{match}: chain link mismatch")
        elif doc["match"] != match or doc["windows"] != config.windows_per_match:
            problems.append(f"match-{match}: receipt identity or window count mismatch")
        else:
            sealed.append({"match": match, "windows": doc["windows"], "sha256": claimed})
            chain = claimed
            continue
        break
    return sealed


def verify_campaign(campaign_dir: Path, ledger_dir: Path | None = None) -> list[str]:
    """Fail-closed completion verification; an empty list means fully verified COMPLETED."""
    problems: list[str] = []
    config = _frozen_campaign(campaign_dir, ledger_dir, problems)
    if config is None:
        return problems
    sealed = _check_receipts(campaign_dir, config, problems)
    if len(sealed) != config.matches:
        problems.append(f"only {len(sealed)} of {config.matches} frozen receipts are sealed")
    for terminal in (".failed.json", ".interrupted.json"):
        if (campaign_dir / terminal).exists():
            problems.append(f"terminal marker {terminal} coexists with a completion claim")
    if list(campaign_dir.rglob(".*.tmp")):
        problems.append("stray temporary files present")
    result = _load_json(campaign_dir / "campaign-result.json")
    if result is None:
        problems.append("final result missing, empty or malformed")
        return problems
    claimed = result.get("result_sha256")
    body = {k: v for k, v in result.items() if k != "result_sha256"}
    if set(result) != _RESULT_KEYS or hashlib.sha256(canonical(body)).hexdigest() != claimed:
        problems.append("final result schema or hash invalid")
        return problems
    expected = {
        "schema_id": SCHEMA_ID + ".result",
        "status": "COMPLETED",
        "synthetic_only": True,
        "scope_sha256": config.scope_sha256(),
        "matches": config.matches,
        "windows_per_match": config.windows_per_match,
        "windows": config.matches * config.windows_per_match,
        "receipts": sealed,
        "final_chain_sha256": sealed[-1]["sha256"] if sealed else None,
    }
    for key, value in expected.items():
        if result.get(key) != value:
            problems.append(f"final result field {key} differs from frozen campaign and receipts")
    return problems


def verify_completed(campaign_dir: Path, ledger_dir: Path | None = None) -> bool:
    return not verify_campaign(campaign_dir, ledger_dir)


def classify(campaign_dir: Path, ledger_dir: Path | None = None) -> dict[str, Any]:
    """Read-only state classification. COMPLETED only if verify_campaign finds no problem."""
    if not (campaign_dir / MARKER).exists():
        if any(campaign_dir.glob("campaign-result.json")):
            return {"state": "CORRUPT", "problems": ["result present without campaign metadata"]}
        return {"state": "NOT_STARTED"}
    framing: list[str] = []
    config = _frozen_campaign(campaign_dir, ledger_dir, framing)
    if config is None:
        return {
            "state": "CORRUPT",
            "problems": framing,
            "sealed_matches": [],
            "missing_matches": [],
            "stray_tmp_files": sorted(p.name for p in campaign_dir.rglob(".*.tmp")),
            "partial_results_are_scientifically_usable": False,
        }
    receipt_problems: list[str] = []
    sealed = [item["match"] for item in _check_receipts(campaign_dir, config, receipt_problems)]
    info: dict[str, Any] = {
        "sealed_matches": sealed,
        "missing_matches": [m for m in range(config.matches) if m not in sealed],
        "stray_tmp_files": sorted(p.name for p in campaign_dir.rglob(".*.tmp")),
        "problems": receipt_problems,
        "partial_results_are_scientifically_usable": False,
    }
    if (campaign_dir / "campaign-result.json").exists():
        full = verify_campaign(campaign_dir, ledger_dir)
        info["state"] = "COMPLETED" if not full else "CORRUPT"
        info["problems"] = full
    elif receipt_problems:
        info["state"] = "CORRUPT"
    elif (campaign_dir / ".failed.json").exists():
        info["state"] = "FAILED"
    elif (campaign_dir / ".interrupted.json").exists():
        info["state"] = "INTERRUPTED"
    else:
        info["state"] = "CRASHED_OR_KILLED"
    return info


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
    if config.forge_empty_result:
        args.append("--fault-forge-empty-result")
    return args


def _supervisor_outcome(
    campaign: Path, ledger: Path, worker_returncode: int | None, terminated_by: str
) -> tuple[str, list[str]]:
    """Map the observable worker outcome to an independently verified supervisor status."""
    if terminated_by != "none":
        return "WORKER_TIMED_OUT", []
    if worker_returncode is not None and worker_returncode < 0:
        return "WORKER_KILLED", []
    if worker_returncode == EXIT_UNVERIFIED:
        problems = verify_campaign(campaign, ledger)
        if not problems:
            problems = ["worker reported completion unverified"]
        return "COMPLETION_UNVERIFIED", problems
    if worker_returncode != 0:
        return "WORKER_FAILED", []
    problems = verify_campaign(campaign, ledger)
    if problems:
        return "COMPLETION_UNVERIFIED", problems
    return "COMPLETED_VERIFIED", []


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
    status, problems = _supervisor_outcome(campaign, ledger, code, terminated_by)
    record = {
        "schema_id": SCHEMA_ID + ".supervisor",
        "supervisor_status": status,
        "exit_code_returned": STATUS_EXIT[status],
        "verification_problems": problems,
        "supervisor_pid": os.getpid(),
        "worker_pid": worker.pid,
        "worker_returncode": code,
        "worker_signal": signal.Signals(-code).name if code is not None and code < 0 else None,
        "terminated_by": terminated_by,
        "hard_timeout_s": hard_timeout_s,
        "elapsed_s": round(time.monotonic() - started, 3),
        "ended_at_utc": utc_now(),
    }
    record["record_sha256"] = hashlib.sha256(canonical(record)).hexdigest()
    atomic_write(log_dir / "supervisor.json", canonical(record) + b"\n")
    return STATUS_EXIT[status]


def read_status(campaign: Path, ledger: Path | None = None) -> tuple[str, int]:
    """Fail-closed status for callers of a detached launch.

    Success requires an intact supervisor record AND independent re-verification of the campaign;
    the recorded status alone is never trusted.
    """
    record = _load_json(campaign.parent / f"{campaign.name}.supervisor" / "supervisor.json")
    if record is None:
        return "NOT_FINISHED_OR_NO_RECORD", EXIT_NOT_FINISHED
    claimed = record.pop("record_sha256", None)
    if claimed != hashlib.sha256(canonical(record)).hexdigest():
        return "SUPERVISOR_RECORD_INVALID", EXIT_UNVERIFIED
    status = record.get("supervisor_status")
    if status not in STATUS_EXIT:
        return "SUPERVISOR_RECORD_INVALID", EXIT_UNVERIFIED
    if status == "COMPLETED_VERIFIED" and verify_campaign(campaign, ledger):
        return "COMPLETION_UNVERIFIED", EXIT_UNVERIFIED
    return str(status), STATUS_EXIT[str(status)]


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
    print(
        json.dumps(
            {
                "supervisor_pid": proc.pid,
                "campaign_directory": str(campaign),
                "launched_only": True,
                "note": "exit 0 means launched; run the status command for the verified outcome",
            }
        )
    )
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="RES614 synthetic-only resilient runner")
    parser.add_argument(
        "command", choices=["run", "supervise", "launch", "inspect", "verify", "status"]
    )
    parser.add_argument("--campaign-dir", type=Path, required=True)
    parser.add_argument(
        "--ledger-dir",
        type=Path,
        help=(
            "required stable owner-private one-shot ledger root, independent of the "
            "campaign output path"
        ),
    )
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
    parser.add_argument("--fault-forge-empty-result", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    campaign: Path = args.campaign_dir
    try:
        assert_synthetic_location(campaign)
    except PermissionError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return EXIT_BAD_INPUT
    if args.ledger_dir is None:
        print(
            "REFUSED: --ledger-dir is required and must be a stable owner-private root "
            "independent of the campaign output path",
            file=sys.stderr,
        )
        return EXIT_BAD_INPUT
    if args.command == "inspect":
        print(json.dumps(classify(campaign, args.ledger_dir), indent=2, sort_keys=True))
        return 0
    if args.command == "verify":
        found = verify_campaign(campaign, args.ledger_dir)
        print(json.dumps({"verified": not found, "problems": found}))
        return 0 if not found else EXIT_UNVERIFIED
    if args.command == "status":
        label, code = read_status(campaign, args.ledger_dir)
        print(json.dumps({"status": label, "exit_code": code}))
        return code
    try:
        config = _config_from_args(args)
    except ValueError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return EXIT_BAD_INPUT
    return _dispatch(args, config, campaign)


def _config_from_args(args: argparse.Namespace) -> Config:
    return Config(
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
        forge_empty_result=args.fault_forge_empty_result,
    )


def _dispatch(args: argparse.Namespace, config: Config, campaign: Path) -> int:
    assert args.ledger_dir is not None
    ledger: Path = args.ledger_dir
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
