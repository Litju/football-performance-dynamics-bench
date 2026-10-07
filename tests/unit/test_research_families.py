import pytest

from fpdbench.benchmarks import UNKNOWN, ResearchFamilyDefinition, ReleaseStatus, ScientificMaturity
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
            "Can noisy, asynchronous, multirate sensor observations support reconstruction of clean "
            "or latent athlete state, and which target families are identifiable?"
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
    for family in families:
        assert family.public_name
        assert family.research_question == expected_questions[family.family_id]
        assert family.scientific_scope
        assert family.known_non_claims
        assert family.release_status is ReleaseStatus.UNRELEASED
        assert registry.lookup_family(family.family_id) is family

    maturities = {family.family_id: family.scientific_maturity for family in families}
    assert maturities == {
        "workload_performance_state": ScientificMaturity.PARTIAL,
        "multimodal_state_estimation": ScientificMaturity.NEGATIVE,
        "future_response_forecasting": ScientificMaturity.UNRECOVERABLE,
        "conditional_multi_agent_motion_prediction": ScientificMaturity.RECONSTRUCTED,
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
    assert len(registry.research_objects()) == 6

    with pytest.raises(KeyError, match="unknown research family"):
        registry.lookup_family("unknown_family")
