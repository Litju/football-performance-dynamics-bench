"""Review candidate for period-constrained phase normalization; not a receipt authority."""

from __future__ import annotations

import csv
import hashlib
import io
import re
from decimal import Decimal, InvalidOperation

from fpdbench.data_sources.protected_skillcorner import (  # pyright: ignore[reportPrivateUsage]
    MAX_DOCUMENT,
    _json,  # pyright: ignore[reportPrivateUsage]
    _object,  # pyright: ignore[reportPrivateUsage]
)
from fpdbench.data_sources.skillcorner import canonical_bytes
from fpdbench.eligibility.skillcorner import skillcorner_period_ranges

NORMALIZER_ID = "fpdbench.skillcorner.phase-period-intersection"
NORMALIZER_VERSION = "1.0.0"


def normalize_phases_c(payload: bytes, metadata_bytes: bytes) -> tuple[bytes, bytes, bytes]:
    """Return C intervals, private source-row lineage, and non-authoritative B intervals."""
    if len(payload) > MAX_DOCUMENT or len(metadata_bytes) > MAX_DOCUMENT:
        raise ValueError("phase source exceeds memory bound")
    metadata = _object(_json(metadata_bytes))
    bounds, issues = skillcorner_period_ranges(metadata)
    if issues or not bounds:
        raise ValueError("invalid phase period bounds")
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8"), newline=""), strict=True)
    try:
        headers = reader.fieldnames
    except csv.Error as exc:
        raise ValueError("malformed phase CSV") from exc
    if (
        not headers
        or len(headers) != len(set(headers))
        or not {"frame_start", "frame_end"} <= set(headers)
    ):
        raise ValueError("invalid phase CSV header")
    intervals: list[dict[str, int]] = []
    shadow: list[dict[str, int]] = []
    rows: list[dict[str, object]] = []
    try:
        for index, row in enumerate(reader, 1):
            if None in row or any(value is None for value in row.values()):
                raise ValueError("ragged phase CSV row")
            values = [row["frame_start"], row["frame_end"]]
            if any(not re.fullmatch(r"0|[1-9][0-9]*", value) for value in values):
                raise ValueError("invalid phase frames")
            start, end = map(int, values)
            if start >= end:
                raise ValueError("invalid phase interval")
            if "match_id" in row and str(metadata.get("id")) != row["match_id"]:
                raise ValueError("phase match identity disagrees with metadata")
            if "duration" in row:
                try:
                    duration = Decimal(row["duration"])
                    if not duration.is_finite() or duration != Decimal(end - start) / 10:
                        raise ValueError("phase duration disagrees with original interval")
                except InvalidOperation:
                    raise ValueError("invalid phase duration") from None
            if "period" in row:
                label = row["period"]
                if not re.fullmatch(r"[1-9][0-9]*", label) or int(label) not in bounds:
                    raise ValueError("invalid phase period")
                period = int(label)
            else:
                candidates = [
                    p for p, (left, right) in bounds.items() if left <= start < end <= right
                ]
                if len(candidates) != 1:
                    raise ValueError("phase interval requires a source period label")
                period = candidates[0]
            left, right = bounds[period]
            clipped_start, clipped_end = max(start, left), min(end, right)
            normalized = None
            if clipped_start < clipped_end:
                normalized = {
                    "period": period,
                    "frame_start": clipped_start,
                    "frame_end": clipped_end,
                }
                intervals.append(normalized)
                if left <= start < end <= right:
                    shadow.append(normalized)
            rows.append(
                {
                    "source_row": index,
                    "raw_start": start,
                    "raw_end": end,
                    "source_period": row.get("period"),
                    "period": period,
                    "normalized": normalized,
                    "disposition": "COVERED" if normalized else "EMPTY_INTERSECTION",
                }
            )
    except csv.Error as exc:
        raise ValueError("malformed phase CSV") from exc
    if not rows:
        raise ValueError("empty phase CSV")

    def key(row: dict[str, int]) -> tuple[int, int, int]:
        return row["period"], row["frame_start"], row["frame_end"]

    intervals.sort(key=key)
    shadow.sort(key=key)
    phases = canonical_bytes(intervals)
    lineage = canonical_bytes(
        {
            "normalizer_id": NORMALIZER_ID,
            "normalizer_version": NORMALIZER_VERSION,
            "source_sha256": hashlib.sha256(payload).hexdigest(),
            "metadata_sha256": hashlib.sha256(metadata_bytes).hexdigest(),
            "normalized_sha256": hashlib.sha256(phases).hexdigest(),
            "rows": rows,
        }
    )
    sensitivity = canonical_bytes(
        {"status": "NON_AUTHORITATIVE_SENSITIVITY", "option": "B", "intervals": shadow}
    )
    return phases, lineage, sensitivity


def verify_phases_c(source_csv: bytes, metadata: bytes, normalized: bytes, lineage: bytes) -> None:
    """Recompute the source-bound candidate, without authenticating a production receipt."""
    expected_normalized, expected_lineage, _ = normalize_phases_c(source_csv, metadata)
    if normalized != expected_normalized or lineage != expected_lineage:
        raise ValueError("phase normalization or lineage differs from source")
