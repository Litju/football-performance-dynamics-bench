import pytest

from fpdbench.benchmarks import (
    UNKNOWN,
    BenchmarkRegistry,
    FamilyLifecycleStatus,
    ReleaseStatus,
    ResearchFamilyDefinition,
)
from fpdbench.benchmarks.registry import default_registry


def test_four_typed_family_definitions_keep_object_counts_unambiguous() -> None:
    registry = default_registry()
    families = registry.families()
    expected_questions = {
        "workload_performance_state": (
            "Can workload and performance state be inferred or reconstructed from observed or "
            "synthetic training and session information, and which formulations are scientifically "
            "recoverable from the historical evidence?"
        ),
        "multimodal_state_estimation": (
            "Can noisy, asynchronous, multirate sensor observations "
            "support reconstruction of clean or latent athlete state, and "
            "which target families are identifiable?"
        ),
        "future_response_forecasting": (
            "Given causal history and ex-ante available future exposure, can subsequent athlete or "
            "performance response be forecast?"
        ),
        "conditional_multi_agent_motion_prediction": (
            "Given observed scene history plus supplied realized future opponent-team and ball "
            "trajectories, can the target team's future response be predicted?"
        ),
    }

    assert len(families) == 4
    assert all(isinstance(family, ResearchFamilyDefinition) for family in families)
    assert {family.family_id for family in families} == set(expected_questions)
    assert {family.technical_name for family in families} == set(expected_questions)
    assert BenchmarkRegistry().families() == families
    assert all(
        value is UNKNOWN for family in families for _, value in family.unresolved_task_fields
    )
    for family in families:
        assert family.public_name
        assert family.research_question == expected_questions[family.family_id]
        assert family.scientific_scope
        assert family.known_non_claims
        assert family.release_status is ReleaseStatus.UNRELEASED
        assert registry.lookup_family(family.family_id) is family

    lifecycle = {
        family.family_id: (family.r1_lifecycle, family.current_lifecycle) for family in families
    }
    assert lifecycle == {
        "workload_performance_state": (
            FamilyLifecycleStatus.RECONSTRUCTION_PENDING,
            FamilyLifecycleStatus.RECONSTRUCTION_COMPLETE_NO_QUALIFIED_BENCHMARK,
        ),
        "multimodal_state_estimation": (
            FamilyLifecycleStatus.RECONSTRUCTION_PENDING,
            FamilyLifecycleStatus.RECONSTRUCTION_COMPLETE_SCOPED_NEGATIVE_NO_SELECTED_BENCHMARK,
        ),
        "future_response_forecasting": (
            FamilyLifecycleStatus.RECONSTRUCTION_PENDING,
            FamilyLifecycleStatus.NO_RECOVERABLE_HISTORICAL_BENCHMARK_RESEARCH_INTENT,
        ),
        "conditional_multi_agent_motion_prediction": (
            FamilyLifecycleStatus.RECOVERED_BENCHMARKS_AVAILABLE,
            FamilyLifecycleStatus.RECOVERED_BENCHMARKS_AVAILABLE,
        ),
    }
    future_response = registry.lookup_family("future_response_forecasting")
    assert dict(future_response.unresolved_task_fields) == {
        "benchmark_identity": UNKNOWN,
        "history_variables": UNKNOWN,
        "input_modalities": UNKNOWN,
        "target": UNKNOWN,
        "ex_ante_exposure_definition": UNKNOWN,
        "scorer": UNKNOWN,
        "horizon": UNKNOWN,
        "population": UNKNOWN,
    }
    assert "No recovered benchmark identity exists." in future_response.known_non_claims
    assert registry.family_ids() == tuple(expected_questions)
    assert len(registry.discover()) == 2
    assert len(registry.research_objects()) == 5
    assert registry.discover("future_response_forecasting") == ()
    assert not any(
        family.family_id == item.identity.scientific_id
        for family in families
        for item in registry.research_objects()
    )
    with pytest.raises(KeyError, match="unknown canonical research-object ID"):
        registry.lookup_research_object("future_response_forecasting")

    with pytest.raises(KeyError, match="unknown research family"):
        registry.lookup_family("unknown_family")
