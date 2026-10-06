"""Versioned evaluator identity, independent of benchmark and model identity."""

from dataclasses import dataclass
import re

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class EvaluatorConfiguration:
    evaluator_id: str
    version: str
    scientific_config_sha256: str
    calibration_sha256: str | None = None

    def __post_init__(self) -> None:
        if not self.evaluator_id or not self.version:
            raise ValueError("evaluator identity and version are required")
        if not _SHA256.fullmatch(self.scientific_config_sha256):
            raise ValueError("evaluator config must use a lowercase SHA-256 digest")
        if self.calibration_sha256 is not None and not _SHA256.fullmatch(self.calibration_sha256):
            raise ValueError("calibration must use a lowercase SHA-256 digest")
