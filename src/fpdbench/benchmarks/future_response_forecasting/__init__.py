"""Research family only; no historical executable benchmark was recovered."""

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

FAMILY_ID = "future_response_forecasting"
RESEARCH_OBJECT_ID = FAMILY_ID
RECONSTRUCTION_BLOCKERS = (
    "Causal history variables and modality whitelist are unrecovered.",
    "Ex-ante exposure definition and availability proof are unrecovered.",
    "Target, units, reference frame, horizon, cadence, and population are unrecovered.",
    "Dataset lineage, split, evaluator, viability evidence, and model lineage are unrecovered.",
)

_TASK = TechnicalTaskContract(
    inputs=(),
    targets=(),
    temporal=TemporalContract(),
    information_boundary=InformationBoundary(available_inputs=(), withheld_targets=()),
    population_semantics=UNKNOWN,
    data_state_binding=None,
    split_protocol_binding=None,
    evaluator_binding=None,
    execution_status=ExecutionStatus.UNRECOVERABLE,
    scientific_maturity=ScientificMaturity.UNRECOVERABLE,
    reconstruction_blockers=RECONSTRUCTION_BLOCKERS,
    non_claims=(
        (
            "Realized future opponent and ball paths are conditional response context, "
            "not ex-ante exposure."
        ),
        "No target, scorer, model, exposure, or horizon is assigned.",
    ),
)

RESEARCH_OBJECT = ResearchObjectDefinition(
    identity=ResearchObjectIdentity(
        scientific_id=RESEARCH_OBJECT_ID,
        family_id=FAMILY_ID,
        task_id=None,
    ),
    descriptor=ScientificDescriptor.from_task(
        _TASK,
        public_name="Future response forecasting research family",
        technical_name=FAMILY_ID,
        research_question=UNKNOWN,
        scientific_task_type=ScientificTaskType.FORECASTING,
        prediction_or_inference_target=UNKNOWN,
        input_modalities=UNKNOWN,
        conditioning_information=UNKNOWN,
        target_representation=UNKNOWN,
        reference_frame=UNKNOWN,
        history_interpretation=UNKNOWN,
        horizon_interpretation=UNKNOWN,
        source_sampling_hz=UNKNOWN,
        unit_of_evaluation=UNKNOWN,
        causal_status=CausalStatus.UNKNOWN,
        scientific_metric_family=UNKNOWN,
        research_object_type=ResearchObjectType.RESEARCH_FAMILY,
    ),
    task=_TASK,
)
