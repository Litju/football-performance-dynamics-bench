from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
from res338_colab_gpu_probe import gpu_memory_fingerprint, parse_probe_args  # noqa: E402


def test_probe_args_accept_only_the_colab_kernel_argument(tmp_path: Path) -> None:
    kernel = tmp_path / "kernel-session.json"
    kernel.write_text("{}")

    args = parse_probe_args(["--output", "probe.json", "-f", str(kernel)])

    assert args.output == Path("probe.json")
    with pytest.raises(SystemExit):
        parse_probe_args(["--unsupported"])


def test_gpu_memory_fingerprint_allows_only_driver_reserved_total_gap() -> None:
    physical_total = 40 * 1024**3
    visible_total = physical_total - 519 * 1024**2
    free = 40014 * 1024**2
    result = gpu_memory_fingerprint(visible_total, free - 589_824, 40960, 40014)

    assert result["total_memory_bytes"] == physical_total
    assert result["torch_visible_total_memory_bytes"] == visible_total
    assert result["driver_reserved_memory_bytes"] == 519 * 1024**2
    with pytest.raises(RuntimeError, match="available GPU memory"):
        gpu_memory_fingerprint(visible_total, free - 2 * 1024**2, 40960, 40014)
