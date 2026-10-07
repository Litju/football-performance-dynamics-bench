"""Versioned evaluator identity, independent of benchmark and model identity."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256

from fpdbench.provenance import canonical_scientific_bytes

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class EvaluatorConfiguration:
    evaluator_id: str
    version: str
    scientific_config_sha256: str
    calibration_sha256: str | None = None
    description: str | None = None
    provenance: tuple[str, ...] = ()

    @classmethod
    def from_state(
        cls,
        evaluator_id: str,
        version: str,
        scientific_state: Mapping[str, str],
        *,
        calibration_sha256: str | None = None,
        description: str | None = None,
        provenance: tuple[str, ...] = (),
    ) -> EvaluatorConfiguration:
        digest = sha256(canonical_scientific_bytes(dict(scientific_state))).hexdigest()
        return cls(
            evaluator_id,
            version,
            digest,
            calibration_sha256,
            description,
            provenance,
        )

    def __post_init__(self) -> None:
        if not self.evaluator_id or not self.version:
            raise ValueError("evaluator identity and version are required")
        if not _SHA256.fullmatch(self.scientific_config_sha256):
            raise ValueError("evaluator config must use a lowercase SHA-256 digest")
        if self.calibration_sha256 is not None and not _SHA256.fullmatch(self.calibration_sha256):
            raise ValueError("calibration must use a lowercase SHA-256 digest")
        if not all(self.provenance):
            raise ValueError("evaluator provenance values must not be empty")
