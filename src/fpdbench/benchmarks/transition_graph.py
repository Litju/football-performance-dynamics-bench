"""The evidence-backed R2 transition and non-transition classifications."""

from __future__ import annotations

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import PREDECESSOR_PARITY
from fpdbench.benchmarks.transitions import (
    IdentityConsequence,
    ScientificTransition,
    TransitionEndpoint,
    TransitionKind,
    TransitionStatus,
    identity_consequence_for_kind,
)
from fpdbench.provenance import EvidenceReference, validate_evidence_reference_shape

WHOLE_SESSION = "workload_performance_state/whole_session_performance_state"
SIGNED_ACCELERATION = "workload_performance_state/signed_tangential_acceleration_estimation"
SENSOR_STATE = "multimodal_state_estimation/multimodal_sensor_state_reconstruction"
FUTURE_RESPONSE = "future_response_forecasting"
CONDITIONAL_MOTION = "conditional_multi_agent_motion_prediction"
ABSOLUTE_POSITION = "conditional_multi_agent_motion_prediction/absolute_position_prediction"
DISPLACEMENT = "conditional_multi_agent_motion_prediction/origin_relative_displacement_prediction"


def _evidence(digest: str, description: str) -> EvidenceReference:
    return EvidenceReference(f"registry://sha256/{digest}", digest, description)


_R1_TAXONOMY = _evidence(
    "96968c239c4758845b87ce8b88db09eb465c81771fdf0b056f9317187325a79e",
    "R1 canonical research-family and object distinctions",
)
_R1_PROGRAM = _evidence(
    "51b9d9c270c885bd95c2aebb0d5e612ee392467daf961e8e6cf87fce0eba6904",
    "R1 research-program lineage summary",
)
_R1_QUESTION_MATRIX = _evidence(
    "0687bea89c7f32ed7c0484918e1e0d544a4d8294f5dede642e8789e3d52207e5",
    "R1 research-question and task-transition records",
)
_R1_TRANSITIONS = _evidence(
    "4acadf8e48a37bcbc4a6eb8664bed472d874d49f33cc7de5364c25bc751b339e",
    "R1 source-backed task transitions",
)
_R2_WORKLOAD = _evidence(
    "90e1da32e077e424f71b2d0fb862cea542301cdfa599302fab7ae00184cc6b53",
    "R2 workload reconstruction outcome",
)
_R2_SENSOR = _evidence(
    "4c22e6f09cfbbc411b1cc364b3ac73a1f39b8ece3f533827144d0ddb857a949e",
    "R2 sensor-state pilot reconstruction outcome",
)
_R2_SENSOR_LINEAGE = _evidence(
    "28a5b701e7d0fad86d38c19baebd1c2bb1f64442354995a3b6fd54a878037260",
    "R2 sensor-state world-lineage record",
)
_R2_FUTURE = _evidence(
    "11e791303212fd1647b6e387d1c409f3611bd8aa250f382a207c2a04bd83b37a",
    "R2 Future Response reconstruction outcome",
)
_R2_FUTURE_LINEAGE = _evidence(
    "e830c7b9b4a3c5e9b8a86e16b9d467b3036a03574b5759c12366b1e0684740bb",
    "R2 Future Response model-lineage investigation",
)
_R2_REPAIR = _evidence(
    "66b5002fcb1be240e90528f01961bfa526d92deee0f1073fe5be4762e5448a98",
    "repaired absolute-position measurement authority",
)
_R2_DATA_STATES = _evidence(
    "a13db1d01e70f4d4b1aece6b5ea3e578eba7bbb473dcb231fea2ea40f1dd6ec7",
    "original and repaired absolute-position data states",
)
_ABSOLUTE_CONTRACT = _evidence(
    "a6892d5158b424db5f8a4903fc5c01b687429246c24056d7a5b03007f9dec23a",
    "absolute-position scientific task contract",
)
_R0_GENEALOGY = _evidence(
    "955882f09af833c8e30458c2f756c479a8feba08f58054e0ab60c12ce77b4bdc",
    "historical benchmark and evaluator genealogy",
)


def _absolute_repair_parity(layer: str, explanation: str) -> ScientificTransition:
    return ScientificTransition(
        transition_id=f"absolute_position_repair:parity:{layer}",
        transition_group_id="absolute_position_measurement_repair",
        source=TransitionEndpoint(ABSOLUTE_POSITION, "original_position_measurement_state"),
        target=TransitionEndpoint(ABSOLUTE_POSITION, "repaired_position_measurement_state"),
        transition_kind=TransitionKind.DATA_STATE_REPAIR,
        layer=layer,
        status=TransitionStatus.SAME,
        explanation=explanation,
        evidence=(_ABSOLUTE_CONTRACT, _R2_DATA_STATES, _R2_REPAIR),
        identity_consequence=IdentityConsequence.SAME_BENCHMARK_IDENTITY,
        data_state_consequence=TransitionStatus.CHANGED,
    )


ABSOLUTE_POSITION_REPAIR = (
    ScientificTransition(
        transition_id="absolute_position_measurement_repair",
        transition_group_id="absolute_position_measurement_repair",
        source=TransitionEndpoint(ABSOLUTE_POSITION, "original_position_measurement_state"),
        target=TransitionEndpoint(ABSOLUTE_POSITION, "repaired_position_measurement_state"),
        transition_kind=TransitionKind.DATA_STATE_REPAIR,
        layer="measurement_data_state",
        status=TransitionStatus.CHANGED,
        explanation=(
            "The measurement state changed while the absolute-position benchmark identity and "
            "its 5 s history, 3 s horizon, 5 Hz grid, absolute XY target, 11 target players, "
            "realized future opponent and ball context, and withheld future target-team XY stayed "
            "the same."
        ),
        evidence=(_ABSOLUTE_CONTRACT, _R2_DATA_STATES, _R2_REPAIR),
        identity_consequence=IdentityConsequence.SAME_BENCHMARK_IDENTITY,
        data_state_consequence=TransitionStatus.CHANGED,
    ),
    _absolute_repair_parity(
        "benchmark_identity", "The measurement repair retains the absolute-position benchmark ID."
    ),
    _absolute_repair_parity(
        "history_contract", "Five seconds of observed scene history are unchanged."
    ),
    _absolute_repair_parity("horizon_contract", "The three-second target horizon is unchanged."),
    _absolute_repair_parity(
        "sampling_grid", "The history and target remain on the five-hertz grid."
    ),
    _absolute_repair_parity("target_representation", "The target remains absolute pitch XY."),
    _absolute_repair_parity("target_entities", "The target remains XY for 11 target-team players."),
    _absolute_repair_parity(
        "conditional_future_context", "Realized future opponent and ball XY remain supplied."
    ),
    _absolute_repair_parity(
        "information_boundary", "Future target-team XY remains withheld from inputs."
    ),
    _absolute_repair_parity(
        "population_roles", "Train, public-validation, and held-out roles are unchanged."
    ),
    ScientificTransition(
        transition_id="absolute_position_dataset_membership_change",
        transition_group_id="absolute_position_measurement_repair",
        source=TransitionEndpoint(ABSOLUTE_POSITION, "original_dataset_membership"),
        target=TransitionEndpoint(ABSOLUTE_POSITION, "repaired_dataset_membership"),
        transition_kind=TransitionKind.DATASET_MEMBERSHIP_CHANGE,
        layer="dataset_membership",
        status=TransitionStatus.CHANGED,
        explanation=(
            "Repair eligibility changes fixture membership while preserving source population "
            "and split roles; an exact row-level crosswalk remains unknown."
        ),
        evidence=(_R2_REPAIR, _R2_DATA_STATES, _ABSOLUTE_CONTRACT),
        identity_consequence=IdentityConsequence.SAME_BENCHMARK_IDENTITY,
        data_state_consequence=TransitionStatus.CHANGED,
    ),
)


RESEARCH_LINEAGE = (
    ScientificTransition(
        transition_id="whole_session_to_signed_acceleration_research_lineage",
        transition_group_id="workload_performance_branch",
        source=TransitionEndpoint(WHOLE_SESSION, "historical partial study"),
        target=TransitionEndpoint(SIGNED_ACCELERATION, "invalidated synthetic formulation"),
        transition_kind=TransitionKind.RESEARCH_LINEAGE,
        layer="research_question",
        status=TransitionStatus.CHANGED,
        explanation=(
            "The evidence records a task-design shift from aggregate session outcomes to "
            "samplewise acceleration; this conveys no benchmark identity or model binding."
        ),
        evidence=(_R1_QUESTION_MATRIX, _R1_TRANSITIONS, _R2_WORKLOAD),
        identity_consequence=IdentityConsequence.NON_BENCHMARK_RESEARCH_LINEAGE,
        research_lineage_consequence=TransitionStatus.CHANGED,
    ),
    ScientificTransition(
        transition_id="signed_acceleration_to_sensor_state_research_lineage",
        transition_group_id="signed_acceleration_to_sensor_state",
        source=TransitionEndpoint(SIGNED_ACCELERATION, "synthetic 10 Hz formulation"),
        target=TransitionEndpoint(SENSOR_STATE, "multimodal sensor-state pilot"),
        transition_kind=TransitionKind.RESEARCH_LINEAGE,
        layer="research_task_lineage",
        status=TransitionStatus.CHANGED,
        explanation=(
            "The source-backed sequence links two distinct synthetic research tasks; it does not "
            "establish a benchmark release or version transition."
        ),
        evidence=(_R1_PROGRAM, _R1_QUESTION_MATRIX, _R1_TRANSITIONS, _R2_SENSOR),
        identity_consequence=IdentityConsequence.NON_BENCHMARK_RESEARCH_LINEAGE,
        research_lineage_consequence=TransitionStatus.CHANGED,
    ),
    ScientificTransition(
        transition_id="signed_acceleration_to_sensor_state_simulator_identity",
        transition_group_id="signed_acceleration_to_sensor_state",
        source=TransitionEndpoint(SIGNED_ACCELERATION, "synthetic 10 Hz formulation"),
        target=TransitionEndpoint(SENSOR_STATE, "multimodal sensor-state pilot"),
        transition_kind=TransitionKind.RESEARCH_LINEAGE,
        layer="exact_simulator_identity",
        status=TransitionStatus.UNKNOWN,
        explanation="The exact simulator identity shared by the tasks is not recovered.",
        evidence=(_R2_WORKLOAD, _R2_SENSOR_LINEAGE),
        identity_consequence=IdentityConsequence.NON_BENCHMARK_RESEARCH_LINEAGE,
        research_lineage_consequence=TransitionStatus.UNKNOWN,
    ),
)


EXPLICIT_NON_TRANSITIONS = (
    ScientificTransition(
        transition_id="future_response_no_recovered_benchmark",
        transition_group_id="future_response_reconstruction_outcome",
        source=TransitionEndpoint(FUTURE_RESPONSE, "R1 research intent"),
        target=TransitionEndpoint(FUTURE_RESPONSE, "R2 family state"),
        transition_kind=TransitionKind.EXPLICIT_NON_TRANSITION,
        layer="historical_benchmark_recovery",
        status=TransitionStatus.NOT_APPLICABLE,
        explanation=(
            "R2 recovered no historical benchmark contract or predecessor object; the research "
            "family remains intent and has no benchmark identity."
        ),
        evidence=(_R1_TAXONOMY, _R2_FUTURE, _R2_FUTURE_LINEAGE),
        identity_consequence=IdentityConsequence.NO_SUPPORTED_TRANSITION,
    ),
    ScientificTransition(
        transition_id="whole_session_to_signed_acceleration_no_successor_edge",
        transition_group_id="workload_performance_branch",
        source=TransitionEndpoint(WHOLE_SESSION, "historical partial study"),
        target=TransitionEndpoint(SIGNED_ACCELERATION, "invalidated synthetic formulation"),
        transition_kind=TransitionKind.EXPLICIT_NON_TRANSITION,
        layer="benchmark_predecessor_successor",
        status=TransitionStatus.NOT_APPLICABLE,
        explanation=(
            "The whole-session study and samplewise signed-acceleration formulation remain "
            "distinct objects; no direct benchmark predecessor or successor is established."
        ),
        evidence=(_R1_TAXONOMY, _R1_QUESTION_MATRIX, _R2_WORKLOAD),
        identity_consequence=IdentityConsequence.NO_SUPPORTED_TRANSITION,
    ),
    ScientificTransition(
        transition_id="sensor_state_to_conditional_motion_project_switch",
        transition_group_id="sensor_state_to_later_dfl_work",
        source=TransitionEndpoint(SENSOR_STATE, "multimodal sensor-state pilot"),
        target=TransitionEndpoint(CONDITIONAL_MOTION, "later DFL response work"),
        transition_kind=TransitionKind.PROJECT_LEVEL_SWITCH,
        layer="project_source_regime_and_scientific_question",
        status=TransitionStatus.CHANGED,
        explanation=(
            "The later DFL work is a project-level source-regime and scientific-question switch; "
            "this record does not assert scientific object continuity."
        ),
        evidence=(_R1_PROGRAM, _R1_QUESTION_MATRIX, _R1_TRANSITIONS),
        identity_consequence=IdentityConsequence.NO_SUPPORTED_TRANSITION,
    ),
    ScientificTransition(
        transition_id="sensor_state_to_conditional_motion_no_model_data_successor",
        transition_group_id="sensor_state_to_later_dfl_work",
        source=TransitionEndpoint(SENSOR_STATE, "multimodal sensor-state pilot"),
        target=TransitionEndpoint(CONDITIONAL_MOTION, "later DFL response work"),
        transition_kind=TransitionKind.EXPLICIT_NON_TRANSITION,
        layer="model_or_data_successor_edge",
        status=TransitionStatus.NOT_APPLICABLE,
        explanation="No model or data successor edge is established between these work branches.",
        evidence=(_R1_PROGRAM, _R1_TRANSITIONS, _R2_SENSOR_LINEAGE),
        identity_consequence=IdentityConsequence.NO_SUPPORTED_TRANSITION,
    ),
    ScientificTransition(
        transition_id="whole_session_to_future_response_no_predecessor",
        transition_group_id="future_response_no_predecessor",
        source=TransitionEndpoint(WHOLE_SESSION, "historical partial study"),
        target=TransitionEndpoint(FUTURE_RESPONSE, "research family"),
        transition_kind=TransitionKind.EXPLICIT_NON_TRANSITION,
        layer="benchmark_predecessor",
        status=TransitionStatus.NOT_APPLICABLE,
        explanation=(
            "No evidence supports the whole-session study as a Future Response predecessor."
        ),
        evidence=(_R1_TAXONOMY, _R2_FUTURE, _R2_FUTURE_LINEAGE),
        identity_consequence=IdentityConsequence.NO_SUPPORTED_TRANSITION,
    ),
    ScientificTransition(
        transition_id="signed_acceleration_to_future_response_no_predecessor",
        transition_group_id="future_response_no_predecessor",
        source=TransitionEndpoint(SIGNED_ACCELERATION, "invalidated synthetic formulation"),
        target=TransitionEndpoint(FUTURE_RESPONSE, "research family"),
        transition_kind=TransitionKind.EXPLICIT_NON_TRANSITION,
        layer="benchmark_predecessor",
        status=TransitionStatus.NOT_APPLICABLE,
        explanation="No evidence supports signed acceleration as a Future Response predecessor.",
        evidence=(_R1_TAXONOMY, _R2_FUTURE, _R2_FUTURE_LINEAGE),
        identity_consequence=IdentityConsequence.NO_SUPPORTED_TRANSITION,
    ),
    ScientificTransition(
        transition_id="sensor_state_to_future_response_no_predecessor",
        transition_group_id="future_response_no_predecessor",
        source=TransitionEndpoint(SENSOR_STATE, "multimodal sensor-state pilot"),
        target=TransitionEndpoint(FUTURE_RESPONSE, "research family"),
        transition_kind=TransitionKind.EXPLICIT_NON_TRANSITION,
        layer="benchmark_predecessor",
        status=TransitionStatus.NOT_APPLICABLE,
        explanation=(
            "No evidence supports sensor-state reconstruction as a Future Response predecessor."
        ),
        evidence=(_R2_SENSOR, _R2_FUTURE, _R2_FUTURE_LINEAGE),
        identity_consequence=IdentityConsequence.NO_SUPPORTED_TRANSITION,
    ),
    ScientificTransition(
        transition_id="absolute_position_to_future_response_no_predecessor",
        transition_group_id="future_response_no_predecessor",
        source=TransitionEndpoint(ABSOLUTE_POSITION, "conditional target-team response benchmark"),
        target=TransitionEndpoint(FUTURE_RESPONSE, "research family"),
        transition_kind=TransitionKind.EXPLICIT_NON_TRANSITION,
        layer="benchmark_predecessor",
        status=TransitionStatus.NOT_APPLICABLE,
        explanation=(
            "Realized future opponent and ball trajectories are conditional context, not ex-ante "
            "future exposure for Future Response forecasting."
        ),
        evidence=(_R1_PROGRAM, _ABSOLUTE_CONTRACT, _R2_FUTURE),
        identity_consequence=IdentityConsequence.NO_SUPPORTED_TRANSITION,
    ),
    ScientificTransition(
        transition_id="displacement_to_future_response_no_predecessor",
        transition_group_id="future_response_no_predecessor",
        source=TransitionEndpoint(DISPLACEMENT, "origin-relative target benchmark"),
        target=TransitionEndpoint(FUTURE_RESPONSE, "research family"),
        transition_kind=TransitionKind.EXPLICIT_NON_TRANSITION,
        layer="benchmark_predecessor",
        status=TransitionStatus.NOT_APPLICABLE,
        explanation=(
            "Origin-relative target representation does not change the conditional motion task "
            "into ex-ante future-exposure forecasting."
        ),
        evidence=(_R1_PROGRAM, _R2_FUTURE, _R2_FUTURE_LINEAGE),
        identity_consequence=IdentityConsequence.NO_SUPPORTED_TRANSITION,
    ),
)


TRANSITION_GRAPH = (
    *ABSOLUTE_POSITION_REPAIR,
    *RESEARCH_LINEAGE,
    *EXPLICIT_NON_TRANSITIONS,
    *PREDECESSOR_PARITY,
)


def validate_transition_graph(
    transitions: tuple[ScientificTransition, ...] = TRANSITION_GRAPH,
) -> tuple[str, ...]:
    errors: list[str] = []
    identifiers = [item.transition_id for item in transitions]
    if len(identifiers) != len(set(identifiers)):
        errors.append("transition IDs must be unique")
    for item in transitions:
        if not item.evidence:
            errors.append(f"transition {item.transition_id} has no evidence")
        if not item.explanation.strip():
            errors.append(f"transition {item.transition_id} has no rationale")
        if item.identity_consequence is not identity_consequence_for_kind(item.transition_kind):
            errors.append(f"transition {item.transition_id} has inconsistent identity consequence")
        for reference in item.evidence:
            errors.extend(
                f"transition {item.transition_id}: {error}"
                for error in validate_evidence_reference_shape(reference)
            )
    return tuple(errors)


def transition_evidence_references() -> tuple[EvidenceReference, ...]:
    return tuple(reference for item in TRANSITION_GRAPH for reference in item.evidence)
