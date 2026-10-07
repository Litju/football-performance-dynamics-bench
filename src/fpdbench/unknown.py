"""Shared sentinel for facts that have not been recovered."""

from enum import StrEnum


class UnknownValue(StrEnum):
    UNKNOWN = "UNKNOWN"


UNKNOWN = UnknownValue.UNKNOWN
