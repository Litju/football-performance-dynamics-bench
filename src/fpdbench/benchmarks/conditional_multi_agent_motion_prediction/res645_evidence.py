"""Independent infrastructure-cause evidence for a worker that died by SIGKILL.

A cgroup-v2 counter identifies no victim PID. Shared-cgroup OOM activity and an
unrelated kill can coincide, so these snapshots are diagnostic only. Without an
independent trusted victim/cause channel, every SIGKILL fails permanently. Only
the existing supervised, sender-verified SIGTERM boundary permits continuation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

CGROUP_ROOT = Path("/sys/fs/cgroup")
BOOT_ID = Path("/proc/sys/kernel/random/boot_id")
KIND = "cgroup_oom_kill"
type Snapshot = dict[str, Any]


def _events(path: Path) -> dict[str, int]:
    result: dict[str, int] = {}
    for line in path.read_text().splitlines():
        name, _, value = line.partition(" ")
        if value.isdigit():
            result[name] = int(value)
    return result


class CgroupEvidence:
    """Kernel cgroup-v2 evidence source. ``root``/``cgroup`` are injectable only to build tests."""

    def __init__(self, root: Path = CGROUP_ROOT, cgroup: str | None = None) -> None:
        self.root, self.cgroup = root, cgroup

    def _relative(self, pid: int) -> str:
        if self.cgroup is not None:
            return self.cgroup
        for line in Path(f"/proc/{pid}/cgroup").read_text().splitlines():
            hierarchy, _, rest = line.partition(":")
            if hierarchy == "0":
                return rest.partition(":")[2]
        raise OSError("no cgroup-v2 membership")

    def snapshot(self, pid: int, cgroup: str | None = None) -> Snapshot:
        """Return an unavailable snapshot rather than guessing when the kernel gives no counter."""
        try:
            relative = cgroup if cgroup is not None else self._relative(pid)
            events = _events(self.root / relative.lstrip("/") / "memory.events")
            return {
                "available": True,
                "cgroup": relative,
                "oom_kill": events["oom_kill"],
                "boot_id": BOOT_ID.read_text().strip(),
            }
        except (OSError, KeyError, ValueError, IndexError):
            return {"available": False}


def assess(
    before: Snapshot,
    after: Snapshot,
    *,
    wait_returncode: int,
    supervisor_signals: int,
    worker_cpu_s: float,
    cpu_ceiling_s: float,
) -> Snapshot | None:
    """Counters cannot attribute a kill to this worker; fail closed on every platform."""
    return None


def valid_attestation(evidence: object) -> bool:
    """No victim-specific trusted host channel is implemented; reject recorded OOM claims."""
    return False
