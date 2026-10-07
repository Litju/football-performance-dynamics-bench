"""Historical identifiers stored only as values in provenance records."""

from fpdbench.provenance import EvidenceReference, HistoricalAlias

DISPLACEMENT_HISTORICAL_ALIASES = (
    HistoricalAlias(
        value="ALI475",
        canonical_id="conditional_multi_agent_motion_prediction/origin_relative_displacement_prediction",
        evidence=EvidenceReference(
            "registry://sha256/fe8c6644d24644cfb4b99fe2b8acfde28621e013ab69735228a94086a1970a59",
            description="synthetic runtime preflight with no quality-bearing result",
        ),
    ),
    HistoricalAlias(
        value="ALI476",
        canonical_id="conditional_multi_agent_motion_prediction/origin_relative_displacement_prediction",
        evidence=EvidenceReference(
            "registry://sha256/8daaa00acd1a6b8477c5a9bf9daac9703b8671165641a584fe0c2408d2eaee1f",
            description="five-fold public training-match campaign manifest",
        ),
    ),
    HistoricalAlias(
        value="ALI477",
        canonical_id="conditional_multi_agent_motion_prediction/origin_relative_displacement_prediction",
        evidence=EvidenceReference(
            "registry://sha256/6bf6416609942c0b32af290fec94c36fef3e0362afee92981ff053950d45a2a2",
            description="ten-fold campaign with invalidated original aggregation",
        ),
    ),
    HistoricalAlias(
        value="ALI478",
        canonical_id="conditional_multi_agent_motion_prediction/origin_relative_displacement_prediction",
        evidence=EvidenceReference(
            "registry://sha256/13a92c677cc9a11b2e492a8efe7ae81bb3b744b54195a096da19ff7c2380ed62",
            description="frozen historical model checkpoint metadata",
        ),
    ),
    HistoricalAlias(
        value="ALI514",
        canonical_id="conditional_multi_agent_motion_prediction/origin_relative_displacement_prediction",
        evidence=EvidenceReference(
            "registry://sha256/eb83130616d3d77c6d0d49c7d9ebe89ed8099741fa5c6163b295a084d73ac527",
            description="corrected aggregation over preserved fold outputs",
        ),
    ),
    HistoricalAlias(
        value="ALI503",
        canonical_id="conditional_multi_agent_motion_prediction/origin_relative_displacement_prediction",
        evidence=EvidenceReference(
            "registry://sha256/03a492e8dded161344cb979d8f194a6bbcd1978ae0a49fe600098126b2146b7e",
            description="preflight checkpoint classified without a quality result",
        ),
    ),
    HistoricalAlias(
        value="ALI534",
        canonical_id="conditional_multi_agent_motion_prediction/origin_relative_displacement_prediction",
        evidence=EvidenceReference(
            "registry://sha256/c2fa14ec4e8e424825e57d6dca0f80c32d6b9ba4ce642809668e3d317ba38a56",
            description="release engineering handoff index",
        ),
    ),
)

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
    *DISPLACEMENT_HISTORICAL_ALIASES,
)
