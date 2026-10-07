import pytest

from fpdbench.benchmarks import (
    FamilyLifecycleStatus,
    IdentityConsequence,
    TransitionKind,
    TransitionStatus,
)
from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    ABSOLUTE_POSITION_BENCHMARK,
    DISPLACEMENT_BENCHMARK,
    PARITY_FIELDS,
    PREDECESSOR_PARITY,
)
from fpdbench.benchmarks.multimodal_state_estimation import RESEARCH_OBJECT as SENSOR_STATE
from fpdbench.benchmarks.registry import default_registry
from fpdbench.benchmarks.transition_graph import (
    ABSOLUTE_POSITION_REPAIR,
    EXPLICIT_NON_TRANSITIONS,
    RESEARCH_LINEAGE,
    TRANSITION_GRAPH,
    validate_transition_graph,
)
from fpdbench.benchmarks.transitions import identity_consequence_for_kind
from fpdbench.benchmarks.workload_performance_state import (
    SIGNED_TANGENTIAL_ACCELERATION_RESEARCH_OBJECT,
    WHOLE_SESSION_RESEARCH_OBJECT,
)


def test_transition_graph_is_evidence_backed_and_uses_all_statuses() -> None:
    assert validate_transition_graph() == ()
    assert all(item.evidence and item.explanation for item in TRANSITION_GRAPH)
    assert {item.status for item in TRANSITION_GRAPH} == set(TransitionStatus)
    assert all(
        reference.uri.startswith("registry://sha256/")
        for item in TRANSITION_GRAPH
        for reference in item.evidence
    )


def test_workload_studies_and_model_bindings_remain_separate() -> None:
    assert WHOLE_SESSION_RESEARCH_OBJECT is not SIGNED_TANGENTIAL_ACCELERATION_RESEARCH_OBJECT
    assert WHOLE_SESSION_RESEARCH_OBJECT.task.execution_status.value == "non_executable"
    assert WHOLE_SESSION_RESEARCH_OBJECT.direct_model_bindings == ()
    assert len(SIGNED_TANGENTIAL_ACCELERATION_RESEARCH_OBJECT.direct_model_bindings) == 7
    assert all(
        binding.startswith("sha256:")
        for binding in SIGNED_TANGENTIAL_ACCELERATION_RESEARCH_OBJECT.direct_model_bindings
    )
    assert SIGNED_TANGENTIAL_ACCELERATION_RESEARCH_OBJECT.task.temporal.target_hz == 10.0
    task_lineage = next(
        item
        for item in RESEARCH_LINEAGE
        if item.transition_id == "whole_session_to_signed_acceleration_research_lineage"
    )
    assert task_lineage.identity_consequence is IdentityConsequence.NON_BENCHMARK_RESEARCH_LINEAGE
    assert task_lineage.research_lineage_consequence is TransitionStatus.CHANGED

    branch = next(
        item
        for item in EXPLICIT_NON_TRANSITIONS
        if item.transition_id == "whole_session_to_signed_acceleration_no_successor_edge"
    )
    assert branch.identity_consequence is IdentityConsequence.NO_SUPPORTED_TRANSITION
    assert branch.status is TransitionStatus.NOT_APPLICABLE


def test_synthetic_sensor_lineage_and_later_project_switch_are_distinct() -> None:
    lineage = next(
        item
        for item in RESEARCH_LINEAGE
        if item.transition_id == "signed_acceleration_to_sensor_state_research_lineage"
    )
    simulator = next(item for item in RESEARCH_LINEAGE if item.layer == "exact_simulator_identity")
    assert lineage.identity_consequence is IdentityConsequence.NON_BENCHMARK_RESEARCH_LINEAGE
    assert lineage.status is TransitionStatus.CHANGED
    assert simulator.status is TransitionStatus.UNKNOWN

    switch = next(
        item
        for item in EXPLICIT_NON_TRANSITIONS
        if item.transition_kind is TransitionKind.PROJECT_LEVEL_SWITCH
    )
    non_edge = next(
        item
        for item in EXPLICIT_NON_TRANSITIONS
        if item.transition_id == "sensor_state_to_conditional_motion_no_model_data_successor"
    )
    assert switch.status is TransitionStatus.CHANGED
    assert switch.identity_consequence is IdentityConsequence.NO_SUPPORTED_TRANSITION
    assert non_edge.status is TransitionStatus.NOT_APPLICABLE
    assert non_edge.identity_consequence is IdentityConsequence.NO_SUPPORTED_TRANSITION


def test_absolute_position_repair_keeps_identity_and_changes_data_state() -> None:
    by_layer = {item.layer: item for item in ABSOLUTE_POSITION_REPAIR}
    assert by_layer["measurement_data_state"].status is TransitionStatus.CHANGED
    assert by_layer["measurement_data_state"].identity_consequence is (
        IdentityConsequence.SAME_BENCHMARK_IDENTITY
    )
    assert by_layer["measurement_data_state"].data_state_consequence is TransitionStatus.CHANGED
    assert by_layer["dataset_membership"].identity_consequence is (
        IdentityConsequence.SAME_BENCHMARK_IDENTITY
    )
    assert by_layer["dataset_membership"].data_state_consequence is TransitionStatus.CHANGED
    for layer in (
        "benchmark_identity",
        "history_contract",
        "horizon_contract",
        "sampling_grid",
        "target_representation",
        "target_entities",
        "conditional_future_context",
        "information_boundary",
        "population_roles",
    ):
        row = by_layer[layer]
        assert row.status is TransitionStatus.SAME
        assert (
            row.source.object_id
            == row.target.object_id
            == (ABSOLUTE_POSITION_BENCHMARK.identity.scientific_id)
        )
        assert row.identity_consequence is IdentityConsequence.SAME_BENCHMARK_IDENTITY
        assert row.data_state_consequence is TransitionStatus.CHANGED


def test_absolute_position_to_displacement_reuses_final_parity_matrix() -> None:
    assert {item.layer for item in PREDECESSOR_PARITY} == set(PARITY_FIELDS)
    assert len(PREDECESSOR_PARITY) == len(PARITY_FIELDS)
    assert all(
        item.identity_consequence is IdentityConsequence.NEW_BENCHMARK_IDENTITY
        for item in PREDECESSOR_PARITY
    )
    assert all(
        item.source.object_id == ABSOLUTE_POSITION_BENCHMARK.identity.scientific_id
        and item.target.object_id == DISPLACEMENT_BENCHMARK.identity.scientific_id
        for item in PREDECESSOR_PARITY
    )
    rows = {item.layer: item for item in PREDECESSOR_PARITY}
    for field in (
        "scientific_task_type",
        "scene_history_inputs",
        "supplied_realized_future_context",
        "information_boundary",
        "history_duration",
        "history_cadence",
        "horizon_duration",
        "horizon_cadence",
        "target_cadence",
        "target_entities",
        "data_state",
        "split_protocol",
        "raw_metric_family",
    ):
        assert rows[field].status is TransitionStatus.SAME
    for field in ("research_question", "target_representation", "reference_frame"):
        assert rows[field].status is TransitionStatus.CHANGED
    for field in (
        "evaluator_scorer",
        "calibration",
        "baseline_ladder",
        "model_architecture",
        "model_selection_protocol",
    ):
        assert rows[field].status is TransitionStatus.UNKNOWN


def test_data_evaluator_and_calibration_changes_do_not_change_identity() -> None:
    for kind in (
        TransitionKind.DATA_STATE_REPAIR,
        TransitionKind.DATASET_MEMBERSHIP_CHANGE,
        TransitionKind.EVALUATOR_CHANGE,
        TransitionKind.CALIBRATION_CHANGE,
        TransitionKind.RELEASE_CHANGE,
    ):
        assert identity_consequence_for_kind(kind) is IdentityConsequence.SAME_BENCHMARK_IDENTITY
    assert identity_consequence_for_kind(TransitionKind.BENCHMARK_PARITY) is (
        IdentityConsequence.NEW_BENCHMARK_IDENTITY
    )


def test_future_response_is_a_family_without_a_benchmark_or_predecessor() -> None:
    registry = default_registry()
    family = registry.lookup_family("future_response_forecasting")
    assert family.current_lifecycle is (
        FamilyLifecycleStatus.NO_RECOVERABLE_HISTORICAL_BENCHMARK_RESEARCH_INTENT
    )
    assert registry.discover("future_response_forecasting") == ()
    assert all(
        item.identity.scientific_id != "future_response_forecasting"
        for item in registry.research_objects()
    )
    with pytest.raises(KeyError, match="unknown canonical research-object ID"):
        registry.lookup_research_object("future_response_forecasting")

    future_edges = tuple(
        item
        for item in EXPLICIT_NON_TRANSITIONS
        if item.transition_group_id == "future_response_no_predecessor"
    )
    assert len(future_edges) == 5
    assert all(item.target.object_id == "future_response_forecasting" for item in future_edges)
    assert all(
        item.identity_consequence is IdentityConsequence.NO_SUPPORTED_TRANSITION
        and item.status is TransitionStatus.NOT_APPLICABLE
        for item in future_edges
    )
    assert SENSOR_STATE.descriptor.scientific_maturity.value == "negative"
    assert (
        family.current_lifecycle
        is not FamilyLifecycleStatus.RECONSTRUCTION_COMPLETE_SCOPED_NEGATIVE_NO_SELECTED_BENCHMARK
    )
