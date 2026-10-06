"""Historical identifiers stored only as values in provenance records."""

from fpdbench.provenance import EvidenceReference, HistoricalAlias

HISTORICAL_ALIASES = (
    HistoricalAlias(
        value="SB-R0-BM-001",
        canonical_id="workload_performance_state/whole_session_performance_state",
        evidence=EvidenceReference("registry://r2/workload_performance_state"),
    ),
    HistoricalAlias(
        value="SB-R0-BM-002",
        canonical_id="workload_performance_state/signed_tangential_acceleration_estimation",
        evidence=EvidenceReference("registry://r2/workload_performance_state"),
    ),
    HistoricalAlias(
        value="SB-R0-BM-003",
        canonical_id="multimodal_state_estimation/multimodal_sensor_state_reconstruction",
        evidence=EvidenceReference("registry://r2/temporal_sensor_latent_state"),
    ),
    HistoricalAlias(
        value="SB-R0-BM-004",
        canonical_id="conditional_multi_agent_motion_prediction/absolute_position_prediction",
        evidence=EvidenceReference("registry://r2/conditional_team_response_absolute_position"),
    ),
    HistoricalAlias(
        value="SB-R0-BM-005",
        canonical_id="conditional_multi_agent_motion_prediction/absolute_position_prediction",
        evidence=EvidenceReference("registry://r2/conditional_team_response_absolute_position"),
    ),
)
