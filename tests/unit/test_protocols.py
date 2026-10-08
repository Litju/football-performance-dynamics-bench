import json
from dataclasses import replace
from pathlib import Path

import pytest

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    displacement_reconstruction,
)
from fpdbench.protocols import (
    ABSOLUTE_POSITION_MEMBERSHIP,
    BENCHMARK_IDS,
    BENCHMARK_PROTOCOL_BINDINGS,
    CANONICAL_LOMO_PROTOCOL,
    CANONICAL_MATCH_ROLE_PROTOCOL,
    DISPLACEMENT_MEMBERSHIP,
    HISTORICAL_PRIVATE_MATCHES,
    HISTORICAL_TRAINING_SEEDS,
    PUBLIC_TRAIN_MATCHES,
    PUBLIC_VALIDATION_MATCHES,
    AggregationRule,
    AnalysisUnit,
    DirectedScenePartition,
    MatchRole,
    ModelSelectionUse,
    RoleAvailability,
    TruthAccess,
    UncertaintyStatus,
    canonical_protocol_evidence_references,
    lomo_split_sha256,
    make_lomo_folds,
    match_role_assignment_sha256,
    summarize_lomo_scores,
    summarize_match_scores,
    validate_canonical_protocols,
    validate_match_group_assignments,
)
from fpdbench.provenance.scientific_lock import verify_scientific_lock


def test_two_benchmark_bindings_share_roles_but_keep_memberships_distinct() -> None:
    assert tuple(item.benchmark_id for item in BENCHMARK_PROTOCOL_BINDINGS) == BENCHMARK_IDS
    assert len(BENCHMARK_PROTOCOL_BINDINGS) == 2
    assert ABSOLUTE_POSITION_MEMBERSHIP.membership_id != DISPLACEMENT_MEMBERSHIP.membership_id
    assert ABSOLUTE_POSITION_MEMBERSHIP.fixture_manifest_sha256 != (
        DISPLACEMENT_MEMBERSHIP.fixture_manifest_sha256
    )
    assert ABSOLUTE_POSITION_MEMBERSHIP.row_crosswalk_status.startswith("unresolved")
    assert all(
        item.role_protocol_id == CANONICAL_MATCH_ROLE_PROTOCOL.protocol_id
        and item.lomo_protocol_id == CANONICAL_LOMO_PROTOCOL.protocol_id
        for item in BENCHMARK_PROTOCOL_BINDINGS
    )
    assert CANONICAL_MATCH_ROLE_PROTOCOL.experimental_unit is AnalysisUnit.MATCH
    assert CANONICAL_MATCH_ROLE_PROTOCOL.measurement_unit is AnalysisUnit.DIRECTED_SCENE
    assert CANONICAL_MATCH_ROLE_PROTOCOL.aggregation_unit is AnalysisUnit.MATCH
    assert CANONICAL_MATCH_ROLE_PROTOCOL.uncertainty_unit is AnalysisUnit.MATCH
    assert all(
        item.public_validation_aggregation is AggregationRule.FULL_MATCH_POPULATION
        and item.lomo_aggregation is AggregationRule.EQUAL_MEAN_ACROSS_MATCHES
        for item in BENCHMARK_PROTOCOL_BINDINGS
    )


def test_exact_disjoint_base_roles_private_boundary_and_absent_public_test() -> None:
    assignments = {item.role: item for item in CANONICAL_MATCH_ROLE_PROTOCOL.assignments}
    assert assignments[MatchRole.PUBLIC_TRAIN].match_ids == PUBLIC_TRAIN_MATCHES
    assert assignments[MatchRole.PUBLIC_VALIDATION].match_ids == PUBLIC_VALIDATION_MATCHES
    assert assignments[MatchRole.HISTORICAL_PRIVATE_QUALIFICATION].match_ids == (
        HISTORICAL_PRIVATE_MATCHES
    )
    assert assignments[MatchRole.HISTORICAL_PRIVATE_QUALIFICATION].availability is (
        RoleAvailability.METADATA_ONLY
    )
    assert assignments[MatchRole.HISTORICAL_PRIVATE_QUALIFICATION].truth_access is (
        TruthAccess.PRIVATE_NOT_OPENED
    )
    public_test = assignments[MatchRole.PUBLIC_TEST]
    assert public_test.match_ids == ()
    assert public_test.availability is RoleAvailability.NOT_DEFINED
    assert not CANONICAL_MATCH_ROLE_PROTOCOL.public_test_defined
    memberships = [match for item in assignments.values() for match in item.match_ids]
    assert len(memberships) == len(set(memberships))
    with pytest.raises(ValueError, match="repaired-state authority"):
        private_as_test = replace(
            public_test,
            match_ids=HISTORICAL_PRIVATE_MATCHES,
            availability=RoleAvailability.AVAILABLE,
            truth_access=TruthAccess.PUBLIC,
        )
        replace(
            CANONICAL_MATCH_ROLE_PROTOCOL,
            assignments=tuple(
                private_as_test if item.role is MatchRole.PUBLIC_TEST else item
                for item in CANONICAL_MATCH_ROLE_PROTOCOL.assignments
            ),
        )
    with pytest.raises(ValueError, match="no available public match membership"):
        CANONICAL_MATCH_ROLE_PROTOCOL.available_matches(MatchRole.PUBLIC_TEST)
    for binding in BENCHMARK_PROTOCOL_BINDINGS:
        with pytest.raises(ValueError, match="not an available public evaluation population"):
            binding.require_evaluation_population(MatchRole.HISTORICAL_PRIVATE_QUALIFICATION)
        with pytest.raises(ValueError, match="not an available public evaluation population"):
            binding.require_evaluation_population(MatchRole.PUBLIC_TEST)


def test_canonical_lomo_is_five_deterministic_four_train_one_heldout_folds() -> None:
    folds = CANONICAL_LOMO_PROTOCOL.folds
    assert len(folds) == 5
    assert folds == make_lomo_folds(PUBLIC_TRAIN_MATCHES)
    assert folds == make_lomo_folds(tuple(reversed(PUBLIC_TRAIN_MATCHES)))
    assert {fold.held_out_match for fold in folds} == set(PUBLIC_TRAIN_MATCHES)
    assert len({fold.held_out_match for fold in folds}) == 5
    for fold in folds:
        assert len(fold.training_matches) == 4
        assert set(fold.training_matches) == set(PUBLIC_TRAIN_MATCHES) - {fold.held_out_match}
        assert fold.held_out_match not in fold.training_matches
        assert fold.evaluation_role is MatchRole.LOMO_HELDOUT
    assert set(CANONICAL_LOMO_PROTOCOL.excluded_matches) == set(
        (*PUBLIC_VALIDATION_MATCHES, *HISTORICAL_PRIVATE_MATCHES)
    )
    with pytest.raises(ValueError, match="exactly the five PUBLIC_TRAIN matches"):
        make_lomo_folds((*PUBLIC_TRAIN_MATCHES[:4], *PUBLIC_VALIDATION_MATCHES))
    with pytest.raises(ValueError, match="exactly the five PUBLIC_TRAIN matches"):
        make_lomo_folds((*PUBLIC_TRAIN_MATCHES[:4], *HISTORICAL_PRIVATE_MATCHES))


def test_lomo_hash_uses_fold_assignment_only() -> None:
    run_folds_by_seed = {seed: CANONICAL_LOMO_PROTOCOL.folds for seed in HISTORICAL_TRAINING_SEEDS}
    assert len({lomo_split_sha256(folds) for folds in run_folds_by_seed.values()}) == 1
    assert "seeds" not in CANONICAL_LOMO_PROTOCOL.__dataclass_fields__
    first, second, *rest = CANONICAL_LOMO_PROTOCOL.folds
    swapped = (
        replace(
            first,
            training_matches=tuple(m for m in PUBLIC_TRAIN_MATCHES if m != second.held_out_match),
            held_out_match=second.held_out_match,
        ),
        replace(
            second,
            training_matches=tuple(m for m in PUBLIC_TRAIN_MATCHES if m != first.held_out_match),
            held_out_match=first.held_out_match,
        ),
        *rest,
    )
    assert lomo_split_sha256(swapped) != CANONICAL_LOMO_PROTOCOL.split_sha256


def test_role_hash_depends_on_match_to_role_not_declaration_order() -> None:
    assignments = CANONICAL_MATCH_ROLE_PROTOCOL.assignments
    permuted = tuple(
        replace(item, match_ids=tuple(reversed(item.match_ids))) for item in reversed(assignments)
    )
    assert match_role_assignment_sha256(permuted) == (
        CANONICAL_MATCH_ROLE_PROTOCOL.assignment_sha256
    )


def _pair(match: str, window: str, partition: str) -> tuple[DirectedScenePartition, ...]:
    return tuple(
        DirectedScenePartition(match, window, direction, partition)
        for direction in ("home", "away")
    )


def test_match_groups_overlapping_windows_and_directed_scenes_cannot_leak() -> None:
    valid = (*_pair("J03WOH", "w1", "fold-1"), *_pair("J03WOH", "w2", "fold-1"))
    validate_match_group_assignments(valid)
    with pytest.raises(ValueError, match="directed scenes"):
        validate_match_group_assignments(
            (
                DirectedScenePartition("J03WOH", "w1", "home", "fold-1"),
                DirectedScenePartition("J03WOH", "w1", "away", "fold-2"),
            )
        )
    with pytest.raises(ValueError, match="windows from one match"):
        validate_match_group_assignments(
            (*_pair("J03WOH", "w1", "fold-1"), *_pair("J03WOH", "w2", "fold-2"))
        )


def test_public_validation_has_one_match_and_no_between_match_uncertainty() -> None:
    summary = summarize_match_scores({"J03WN1": 0.42})
    assert summary.unit == "match"
    assert summary.n_match == 1
    assert summary.point_estimate == 0.42
    assert summary.between_match_standard_deviation is None
    assert summary.between_match_standard_error is None
    assert summary.confidence_interval is None
    assert summary.confidence_interval_status == "method not declared"
    assert summary.status is UncertaintyStatus.NOT_ESTIMABLE
    assert summary.reason is not None
    with pytest.raises(ValueError, match="at least one match"):
        summarize_match_scores({})
    with pytest.raises(ValueError, match="known public match IDs"):
        summarize_match_scores({"directed-row-1": 0.42})


def test_multiseed_lomo_aggregates_by_match_then_reports_seed_sensitivity() -> None:
    scores = {
        seed: {
            match: float(index + 1) + seed_index / 10
            for index, match in enumerate(PUBLIC_TRAIN_MATCHES)
        }
        for seed_index, seed in enumerate(HISTORICAL_TRAINING_SEEDS)
    }
    summary = summarize_lomo_scores(scores)
    assert len(summary.per_match_means) == 5
    assert summary.generalization.n_match == 5
    assert summary.generalization.status is UncertaintyStatus.ESTIMABLE
    assert summary.generalization.between_match_standard_deviation is not None
    assert summary.generalization.between_match_standard_error is not None
    assert summary.generalization.confidence_interval is None
    assert summary.seed_sensitivity.n_seeds == 3
    assert len(summary.seed_sensitivity.seed_level_means) == 3
    assert "not independent match uncertainty" in summary.seed_sensitivity.interpretation
    arithmetic_cell_mean = (
        sum(value for values in scores.values() for value in values.values()) / 15
    )
    assert summary.balanced_grand_mean == pytest.approx(arithmetic_cell_mean)
    assert summary.generalization.point_estimate == pytest.approx(arithmetic_cell_mean)
    assert summary.generalization.n_match != 15
    with pytest.raises(ValueError, match="exactly the five held-out matches"):
        summarize_lomo_scores({1: {PUBLIC_TRAIN_MATCHES[0]: 0.5}})


def test_evaluators_and_historical_locks_stay_outside_new_split_hashes() -> None:
    assert BENCHMARK_PROTOCOL_BINDINGS[0].evaluator_ids == (
        "absolute_position.population_sre_targets",
        "absolute_position.per_target_progress",
        "absolute_position.historical_continuous_pwl_v3",
        "physical_trajectory.ade_fde_xy_rmse",
    )
    assert BENCHMARK_PROTOCOL_BINDINGS[1].evaluator_ids == (
        "origin_relative_displacement_raw_population_sre",
        "physical_trajectory.ade_fde_xy_rmse",
    )
    assert BENCHMARK_PROTOCOL_BINDINGS[1].calibrated_scorer_status == "unavailable"
    role_hash = CANONICAL_MATCH_ROLE_PROTOCOL.assignment_sha256
    binding_with_other_evaluator = replace(
        BENCHMARK_PROTOCOL_BINDINGS[0], evaluator_ids=("another.evaluator",)
    )
    assert (
        binding_with_other_evaluator.evaluator_ids != BENCHMARK_PROTOCOL_BINDINGS[0].evaluator_ids
    )
    assert match_role_assignment_sha256(CANONICAL_MATCH_ROLE_PROTOCOL.assignments) == role_hash
    assert lomo_split_sha256(CANONICAL_LOMO_PROTOCOL.folds) == CANONICAL_LOMO_PROTOCOL.split_sha256

    assert displacement_reconstruction.PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK_HASH == (
        "d56ef8e1ff37276e258d516fa9ce26231403222e549296777ee27e5f38cfeedc"
    )
    assert displacement_reconstruction.LOMO_RAW_SCIENTIFIC_LOCK_HASH == (
        "572e28bb5b4675a1fac91eb7c2c2c9cd4f00b28119aa447dd563c080a704cfd0"
    )
    assert verify_scientific_lock(displacement_reconstruction.PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK)
    assert verify_scientific_lock(displacement_reconstruction.LOMO_RAW_SCIENTIFIC_LOCK)
    root = Path(__file__).resolve().parents[2]
    lock_directory = root / "benchmarks/conditional_multi_agent_motion_prediction"
    public_json = json.loads(
        (lock_directory / "public_validation_raw_displacement_scientific_lock.json").read_text()
    )
    lomo_json = json.loads(
        (lock_directory / "lomo_raw_displacement_scientific_lock.json").read_text()
    )
    assert (
        public_json["scientific_lock_hash"]
        == displacement_reconstruction.PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK_HASH
    )
    assert (
        lomo_json["scientific_lock_hash"]
        == displacement_reconstruction.LOMO_RAW_SCIENTIFIC_LOCK_HASH
    )
    assert verify_scientific_lock(public_json)
    assert verify_scientific_lock(lomo_json)
    assert BENCHMARK_PROTOCOL_BINDINGS[1].historical_scientific_lock_hashes == (
        displacement_reconstruction.PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK_HASH,
        displacement_reconstruction.LOMO_RAW_SCIENTIFIC_LOCK_HASH,
    )


def test_canonical_protocol_and_evidence_shapes_validate_without_local_registry() -> None:
    assert validate_canonical_protocols() == ()
    assert len(canonical_protocol_evidence_references()) == 5
    assert all(
        item.uri.startswith("registry://sha256/")
        for item in canonical_protocol_evidence_references()
    )
    assert all(
        binding.historical_model_selection_use is ModelSelectionUse.UNKNOWN_HISTORICAL
        and binding.future_model_selection_use is ModelSelectionUse.DECLARED_PER_EXPERIMENT
        for binding in BENCHMARK_PROTOCOL_BINDINGS
    )
