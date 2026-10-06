"""Model and checkpoint identities, independent of benchmark releases."""

import re
from dataclasses import dataclass

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class ModelCheckpoint:
    model_id: str
    checkpoint_sha256: str
    training_config_sha256: str

    def __post_init__(self) -> None:
        if not self.model_id:
            raise ValueError("model identity is required")
        if not _SHA256.fullmatch(self.checkpoint_sha256):
            raise ValueError("checkpoint digest must be lowercase SHA-256")
        if not _SHA256.fullmatch(self.training_config_sha256):
            raise ValueError("training config digest must be lowercase SHA-256")
