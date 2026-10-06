"""Information-boundary checks shared by conditional motion task inputs."""

from collections.abc import Iterable

_FORBIDDEN_FEATURES = frozenset(
    {
        "future_target_s",
        "future_target_a",
        "future_aggregates",
        "event_labels",
        "score",
        "absolute_timestamp",
        "file_identity",
        "row_order",
        "target_encoding",
        "numeric_player_id",
        "numeric_team_id",
        "numeric_match_id",
    }
)
_FORBIDDEN_NAME_FRAGMENTS = ("future_target", "target_future", "future_truth")


def validate_information_boundary(feature_names: Iterable[str]) -> None:
    """Reject withheld target truth, target-derived features, and identity leakage."""
    forbidden: list[str] = []
    for name in feature_names:
        normalized = name.casefold().replace("-", "_").replace(".", "_")
        if normalized in _FORBIDDEN_FEATURES or any(
            fragment in normalized for fragment in _FORBIDDEN_NAME_FRAGMENTS
        ):
            forbidden.append(name)
    if forbidden:
        raise ValueError(f"forbidden information-boundary features: {', '.join(sorted(forbidden))}")
