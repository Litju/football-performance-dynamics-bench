"""Supported full-row RMSE behavior for the invalidated 10 Hz formulation."""

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
from fpdbench.evaluation.evaluators import (
    SignedTangentialAccelerationEvaluation as _SignedTangentialAccelerationEvaluation,
)
from fpdbench.evaluation.evaluators import (
    evaluate_signed_tangential_acceleration as _evaluate_signed_tangential_acceleration,
)

RESEARCH_OBJECT_ID = "workload_performance_state/signed_tangential_acceleration_estimation"
SignedTangentialAccelerationEvaluation = _SignedTangentialAccelerationEvaluation
evaluate_signed_tangential_acceleration = _evaluate_signed_tangential_acceleration
DOCUMENTED_RMSE_INTERVAL_M_S2 = (0.04, 0.075)
DIAGNOSTIC_MODEL_BINDINGS = (
    "sha256:024f04e1cdb385916a431a84658bc0507a843c43bcdb10d3c0c8ff1d96789258",
    "sha256:c26cc227531d035e4c2e7f1203e29c6cd70b19c2f6d5f5c42a330db69a47886e",
    "sha256:e3061e7e0c7b4af2166bbd8156432c491566968c374db4b15b64fe93f1c95646",
    "sha256:807817dbeaf6bae32c193b09206b543238749e5c4f8c5e77a6108f2b8cf425a7",
    "sha256:b4ec06f3f317cc9eb1b0b7d60f930ad6e670e3dd856c9c53db4b14c7828a6ac0",
    "sha256:d1cbc6aa31455da0694a96fe021770720e9abee951fb48b98e5cdcfba1ddea62",
    "sha256:679b3a6026f33912c6e9d4c3b69d6989594ae674f6904749f6f4a4e0ef2855e5",
)


_TASK = TechnicalTaskContract(
    inputs=("causal GNSS and inertial sensor history", "public player-session context"),
    targets=("signed horizontal tangential acceleration in metres per second squared",),
    temporal=TemporalContract(target_hz=10.0),
    information_boundary=InformationBoundary(
        available_inputs=("causal sensor history", "public player-session context"),
        withheld_targets=("clean signed tangential acceleration at the scored sample",),
        forbidden_information=("future sensor observations",),
    ),
    population_semantics="Grouped synthetic exposures; exact target population unresolved.",
    data_state_binding=None,
    split_protocol_binding=None,
    evaluator_binding="global full-row RMSE, no normalization",
    execution_status=ExecutionStatus.PARTIAL,
    scientific_maturity=ScientificMaturity.INVALIDATED,
    reconstruction_blockers=(
        "The exact feature whitelist and data binding are partial.",
        "A split identifier crosswalk remains unresolved.",
        "The historical B5 raw single-channel submetric formula and aggregation are lost.",
    ),
    non_claims=(
        "The recovered RMSE does not restore the invalidated benchmark formulation.",
        "No unrecovered single-channel submetric is supplied.",
    ),
)

RESEARCH_OBJECT = ResearchObjectDefinition(
    identity=ResearchObjectIdentity(
        scientific_id=RESEARCH_OBJECT_ID,
        family_id="workload_performance_state",
        task_id="signed_tangential_acceleration_estimation",
    ),
    descriptor=ScientificDescriptor.from_task(
        _TASK,
        public_name="Signed tangential-acceleration formulation",
        technical_name="signed_tangential_acceleration_estimation",
        research_question=UNKNOWN,
        scientific_task_type=ScientificTaskType.ESTIMATION,
        prediction_or_inference_target=(
            "Signed horizontal tangential acceleration in metres per second squared."
        ),
        input_modalities=("GNSS", "inertial measurement"),
        conditioning_information=(
            "causal GNSS and inertial sensor history",
            "public player-session context",
        ),
        target_representation="One signed scalar per scored 10 Hz sample.",
        reference_frame="Horizontal trajectory tangent; exact sign convention is unresolved.",
        history_interpretation=UNKNOWN,
        horizon_interpretation=UNKNOWN,
        source_sampling_hz=UNKNOWN,
        unit_of_evaluation="Scored acceleration sample.",
        causal_status=CausalStatus.CAUSAL,
        scientific_metric_family=("global full-row RMSE",),
        research_object_type=ResearchObjectType.INVALIDATED_FORMULATION,
    ),
    task=_TASK,
    direct_model_bindings=DIAGNOSTIC_MODEL_BINDINGS,
)
