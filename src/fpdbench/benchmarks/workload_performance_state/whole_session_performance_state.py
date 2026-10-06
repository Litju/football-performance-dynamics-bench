"""Partial historical whole-session target family; execution is unavailable."""

from fpdbench.benchmarks.base import (
    UNKNOWN,
    CausalStatus,
    ExecutionStatus,
    InformationBoundary,
    ResearchObjectDefinition,
    ResearchObjectIdentity,
    ResearchObjectType,
    ScientificDescriptor,
    ScientificMaturity,
    ScientificTaskType,
    TechnicalTaskContract,
    TemporalContract,
)

RESEARCH_OBJECT_ID = "workload_performance_state/whole_session_performance_state"

_TASK = TechnicalTaskContract(
    inputs=("synthetic exposure context", "session or player-week context"),
    targets=(
        "distance",
        "distance per minute",
        "peak speed",
        "high-speed running and sprint distance",
        "acceleration and event counts",
        "inertial sensor rate",
        "session rating of perceived exertion",
        "heart-rate-derived training impulse",
        "acute and chronic workload",
        "training monotony and strain",
    ),
    temporal=TemporalContract(),
    information_boundary=InformationBoundary(
        available_inputs=("session or player-week context",),
        withheld_targets=("whole-session performance outcomes",),
    ),
    population_semantics="Synthetic player-week grouped exposures; exact population unknown.",
    data_state_binding=None,
    split_protocol_binding=None,
    evaluator_binding=None,
    execution_status=ExecutionStatus.NON_EXECUTABLE,
    scientific_maturity=ScientificMaturity.PARTIAL,
    reconstruction_blockers=(
        "Original feature schema and exposure generator are unavailable.",
        "Target units, formulas, causal boundary, horizon, and population are unresolved.",
        "No independent evaluator or executable benchmark identity was recovered.",
        "No direct model binding survives.",
    ),
    non_claims=(
        "The task does not establish a separate causal future-response benchmark.",
        "Signed tangential-acceleration models are not whole-session experts.",
    ),
)

RESEARCH_OBJECT = ResearchObjectDefinition(
    identity=ResearchObjectIdentity(
        scientific_id=RESEARCH_OBJECT_ID,
        family_id="workload_performance_state",
        task_id="whole_session_performance_state",
    ),
    descriptor=ScientificDescriptor.from_task(
        _TASK,
        public_name="Whole-session performance-state study",
        technical_name="whole_session_performance_state",
        research_question=UNKNOWN,
        scientific_task_type=ScientificTaskType.ESTIMATION,
        prediction_or_inference_target=(
            "Whole-session performance outcomes; exact formulas and units are unresolved."
        ),
        input_modalities=UNKNOWN,
        conditioning_information=("session or player-week context",),
        target_representation=UNKNOWN,
        reference_frame=UNKNOWN,
        history_interpretation=UNKNOWN,
        horizon_interpretation=UNKNOWN,
        source_sampling_hz=UNKNOWN,
        unit_of_evaluation=UNKNOWN,
        causal_status=CausalStatus.UNKNOWN,
        scientific_metric_family=UNKNOWN,
        research_object_type=ResearchObjectType.HISTORICAL_STUDY,
    ),
    task=_TASK,
    direct_model_bindings=(),
)
