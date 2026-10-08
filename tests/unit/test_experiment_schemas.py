import hashlib
import math
from dataclasses import replace
from pathlib import Path

import pytest

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    HISTORICAL_RESULTS,
    LOMO_FOLD_RESULTS,
    LOMO_RAW_SCIENTIFIC_LOCK,
    LOMO_RAW_SCIENTIFIC_LOCK_HASH,
    PUBLIC_VALIDATION_PHYSICAL_RESULT,
    PUBLIC_VALIDATION_PHYSICAL_SCIENTIFIC_LOCK,
    PUBLIC_VALIDATION_PHYSICAL_SCIENTIFIC_LOCK_HASH,
    PUBLIC_VALIDATION_RAW_RESULT,
    PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK,
    PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK_HASH,
    RAW_DISPLACEMENT_EVALUATOR,
    build_lomo_raw_scientific_lock,
    build_public_validation_physical_scientific_lock,
    build_public_validation_raw_scientific_lock,
)
from fpdbench.data import ArtifactReference
from fpdbench.evaluation.metrics.trajectory import PHYSICAL_TRAJECTORY_EVALUATOR
from fpdbench.experiments import (
    ArtifactDeclaration,
    ArtifactRelation,
    EnvironmentFingerprint,
    EvaluatorState,
    ExecutionProvenance,
    ExperimentManifest,
    InferentialStatus,
    ModelSelectionUse,
    ProvenanceCompleteness,
    ResultManifest,
    ResultMetric,
    ResultPopulation,
    ResultRecord,
    ResultValidity,
    RunConfiguration,
    ScientificStateBinding,
    SystemIdentity,
    SystemKind,
    from_lomo_summary,
    from_match_summary,
)
from fpdbench.protocols import (
    CANONICAL_LOMO_PROTOCOL,
    CANONICAL_MATCH_ROLE_PROTOCOL,
    PUBLIC_TRAIN_MATCHES,
    PUBLIC_VALIDATION_MATCHES,
    summarize_lomo_scores,
    summarize_match_scores,
)
from fpdbench.provenance import EvidenceReference, build_scientific_lock, canonical_scientific_bytes
from fpdbench.provenance.scientific_lock import validate_scientific_lock_provenance

_REPO_ROOT = Path(__file__).resolve().parents[2]
_OUTPUT_SHA256 = "b29250984c897c1184cb1208a390c6fdeb2a4764cfe5ee530c73c0a1c9269528"


def _execution_manifest(
    *,
    scientific_lock: object = PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK,
    metadata: tuple[tuple[str, str], ...] = (),
) -> ExperimentManifest:
    binding = ScientificStateBinding.from_verified_lock(scientific_lock)
    evidence = EvidenceReference("registry://sha256/" + "c" * 64, "c" * 64, "source")
    input_artifacts = (
        ArtifactDeclaration(
            "fixture",
            "test-input",
            ArtifactRelation.INPUT,
            ArtifactReference("file:///tmp/input-a", "a" * 64, 10),
            "application/octet-stream",
        ),
        ArtifactDeclaration(
            "weights",
            "checkpoint",
            ArtifactRelation.INPUT,
            ArtifactReference("s3://bucket/model", "b" * 64, 20),
            "application/octet-stream",
        ),
    )
    output_artifacts = (
        ArtifactDeclaration(
            "predictions",
            "prediction-output",
            ArtifactRelation.OUTPUT,
            ArtifactReference("file:///tmp/predictions", "d" * 64),
            "application/json",
        ),
    )
    return ExperimentManifest(
        run_id="example-run",
        scientific_state=binding,
        system=SystemIdentity("baseline.constant", SystemKind.BASELINE, evidence=(evidence,)),
        run_configuration=RunConfiguration(
            "e" * 64, seed=7, model_selection_use=ModelSelectionUse.NONE
        ),
        environment=EnvironmentFingerprint(
            "3.12.3",
            "f" * 64,
            "ed88564c95ad994810cfb8696b203a9ac60ce89b",
            platform_accelerator=(("accelerator", "cpu"), ("platform", "linux-x86_64")),
        ),
        input_artifacts=input_artifacts,
        output_artifacts=output_artifacts,
        execution_provenance=ExecutionProvenance(
            "execution-7",
            evidence=(evidence,),
            metadata=metadata,
        ),
        metadata=metadata,
    )


def _synthetic_scope_lock(
    *,
    split_protocol_id: str | None = None,
    split_protocol_hash: str | None = None,
    evaluator_id: str | None = None,
) -> dict[str, object]:
    state = {
        key: value
        for key, value in PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK.items()
        if key != "scientific_lock_hash"
    }
    if split_protocol_id is not None:
        state["split_protocol_id"] = split_protocol_id
    if split_protocol_hash is not None:
        state["split_protocol_hash"] = split_protocol_hash
    if evaluator_id is not None:
        state["evaluator_id"] = evaluator_id
        state["evaluator_hash"] = "a" * 64
    return build_scientific_lock(state)


def _execution_result_record(
    execution: ExperimentManifest,
    population: ResultPopulation,
    evaluator_state: EvaluatorState,
) -> ResultRecord:
    return ResultRecord(
        run_id=execution.run_id,
        scientific_lock_hash=execution.scientific_state.scientific_lock_hash,
        model_checkpoint_sha256=None,
        metrics=(),
        population=population,
        evaluator_state=evaluator_state,
        validity=ResultValidity.RECORDED,
        provenance_completeness=ProvenanceCompleteness.EXECUTION_MANIFEST_BOUND,
        experiment_manifest=execution,
    )


def _direct_execution_result_manifest(
    execution: ExperimentManifest,
    population: ResultPopulation,
    evaluator_state: EvaluatorState,
) -> ResultManifest:
    return ResultManifest(
        run_id=execution.run_id,
        scientific_state=execution.scientific_state,
        metrics=(),
        population=population,
        evaluator_state=evaluator_state,
        validity=ResultValidity.RECORDED,
        model_checkpoint_sha256=None,
        output_artifacts=(),
        evidence=(),
        provenance_completeness=ProvenanceCompleteness.EXECUTION_MANIFEST_BOUND,
        experiment_manifest=execution,
    )


def test_result_record_requires_a_lowercase_scientific_lock() -> None:
    fields = {
        "run_id": "invalid",
        "model_checkpoint_sha256": None,
        "metrics": (),
        "population": PUBLIC_VALIDATION_RAW_RESULT.population,
        "evaluator_state": EvaluatorState.RAW_EVALUATION,
        "validity": ResultValidity.RECORDED,
        "evidence": (EvidenceReference("registry://sha256/" + "a" * 64),),
        "provenance_completeness": ProvenanceCompleteness.HISTORICAL_EVIDENCE_BOUND,
    }
    with pytest.raises(ValueError, match="scientific lock SHA-256"):
        ResultRecord(scientific_lock_hash=None, **fields)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="scientific lock SHA-256"):
        ResultRecord(scientific_lock_hash="A" * 64, **fields)


def test_all_historical_records_bind_to_verified_historical_locks() -> None:
    assert len(HISTORICAL_RESULTS) == 19
    assert len(LOMO_FOLD_RESULTS) == 15
    assert sum(result.population.value == "lomo_cross_match" for result in HISTORICAL_RESULTS) == 17
    assert sum(result.population.value == "public_validation" for result in HISTORICAL_RESULTS) == 2
    assert all(result.scientific_lock_hash for result in HISTORICAL_RESULTS)
    assert (
        sum(result is not PUBLIC_VALIDATION_PHYSICAL_RESULT for result in HISTORICAL_RESULTS) == 18
    )
    assert {
        result.scientific_lock_hash
        for result in HISTORICAL_RESULTS
        if result is not PUBLIC_VALIDATION_PHYSICAL_RESULT
    } == {LOMO_RAW_SCIENTIFIC_LOCK_HASH, PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK_HASH}
    assert PUBLIC_VALIDATION_PHYSICAL_RESULT.scientific_lock_hash == (
        PUBLIC_VALIDATION_PHYSICAL_SCIENTIFIC_LOCK_HASH
    )
    assert PUBLIC_VALIDATION_PHYSICAL_RESULT.evaluator_state is EvaluatorState.PHYSICAL_DIAGNOSTIC


def test_raw_lock_json_bytes_remain_at_the_starting_head_values() -> None:
    lock_directory = _REPO_ROOT / "benchmarks/conditional_multi_agent_motion_prediction"
    public_path = lock_directory / "public_validation_raw_displacement_scientific_lock.json"
    lomo_path = lock_directory / "lomo_raw_displacement_scientific_lock.json"
    assert hashlib.sha256(public_path.read_bytes()).hexdigest() == (
        "1f0254c5d687aa6a383d8ce6b53fe825473a6f23cbd7f9bbf7c787a362fa1171"
    )
    assert hashlib.sha256(lomo_path.read_bytes()).hexdigest() == (
        "d3fa4e56b1d4c7c93b424960e0440217f2c45252ceab85f0fc516eb26a3fd621"
    )


def test_physical_lock_uses_only_the_historical_physical_evaluator_state() -> None:
    lock = PUBLIC_VALIDATION_PHYSICAL_SCIENTIFIC_LOCK
    assert lock["scientific_lock_hash"] == (
        "2fa5bbb3f5e56f0b2e2256f8b53483480168b098ab569dc6509548a0dba4a3d5"
    )
    assert lock["evaluator_id"] == "physical_trajectory.ade_fde_xy_rmse"
    assert lock["evaluator_version"] == "1.0.0"
    assert (
        lock["evaluator_hash"] == "7ce838398fc0939145362077dea7d62023129cd7936086cf042269a48d918b10"
    )
    assert lock["evaluator_hash"] == PHYSICAL_TRAJECTORY_EVALUATOR.scientific_config_sha256
    assert lock["split_protocol_id"] == "match_grouped_displacement_public_split"
    assert lock["split_protocol_hash"] == (
        "5e060c84952cd4544fde6b80a93675c02c06036440ef9d2c97aa96eec618709c"
    )
    assert lock["scientific_lock_hash"] not in {
        PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK_HASH,
        LOMO_RAW_SCIENTIFIC_LOCK_HASH,
    }
    citations = lock["scientific_provenance_snapshot"]["citations"]
    assert f"registry://sha256/{_OUTPUT_SHA256}" not in citations
    assert validate_scientific_lock_provenance(lock, (_OUTPUT_SHA256,)) == ()


def test_evaluator_mutations_only_change_the_lock_that_owns_that_evaluator() -> None:
    changed_physical = build_public_validation_physical_scientific_lock("a" * 64)
    assert (
        changed_physical["scientific_lock_hash"] != PUBLIC_VALIDATION_PHYSICAL_SCIENTIFIC_LOCK_HASH
    )
    assert build_public_validation_raw_scientific_lock()["scientific_lock_hash"] == (
        PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK_HASH
    )
    assert build_lomo_raw_scientific_lock()["scientific_lock_hash"] == LOMO_RAW_SCIENTIFIC_LOCK_HASH

    changed_raw_evaluator = replace(RAW_DISPLACEMENT_EVALUATOR, aggregation="changed raw metric")
    assert (
        build_public_validation_raw_scientific_lock(evaluator=changed_raw_evaluator)[
            "scientific_lock_hash"
        ]
        != PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK_HASH
    )
    assert (
        build_public_validation_physical_scientific_lock()["scientific_lock_hash"]
        == PUBLIC_VALIDATION_PHYSICAL_SCIENTIFIC_LOCK_HASH
    )


def test_scientific_binding_requires_verified_lock_and_ignores_governance() -> None:
    binding = ScientificStateBinding.from_verified_lock(PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK)
    assert binding.scientific_lock_hash == PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK_HASH
    assert binding.benchmark_id == PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK["benchmark_id"]
    assert binding.data_release_id == PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK["data_release_id"]
    assert (
        binding.data_release_version
        == PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK["data_release_version"]
    )
    assert binding.data_manifest_hash == PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK["data_manifest_hash"]
    assert binding.data_state_id == PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK["data_state_id"]
    assert binding.split_protocol_id == PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK["split_protocol_id"]
    assert (
        binding.split_protocol_version
        == PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK["split_protocol_version"]
    )
    assert (
        binding.split_protocol_hash == PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK["split_protocol_hash"]
    )
    assert binding.evaluator_id == PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK["evaluator_id"]
    assert binding.evaluator_version == PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK["evaluator_version"]
    assert binding.evaluator_hash == PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK["evaluator_hash"]
    assert binding.schema_version == PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK["schema_version"]
    assert binding.schema_hash == PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK["schema_hash"]
    assert (
        binding.fixture_manifest_hash
        == PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK["fixture_manifest_hash"]
    )

    governed = dict(PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK)
    governed.update(legal_status="restricted", hosting_provider="example")
    assert ScientificStateBinding.from_verified_lock(governed) == binding
    for field in ("benchmark_id", "split_protocol_hash", "evaluator_hash"):
        mismatched = dict(PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK)
        mismatched[field] = "0" * 64
        with pytest.raises(ValueError, match="verified scientific lock"):
            ScientificStateBinding.from_verified_lock(mismatched)


def test_run_manifest_hash_is_canonical_and_excludes_machine_metadata() -> None:
    first = _execution_manifest(metadata=(("hostname", "runner-a"), ("started_at", "t1")))
    second = replace(
        first,
        input_artifacts=tuple(reversed(first.input_artifacts)),
        output_artifacts=(
            replace(
                first.output_artifacts[0],
                reference=replace(first.output_artifacts[0].reference, uri="/another/local/path"),
            ),
        ),
        execution_provenance=replace(
            first.execution_provenance,
            metadata=(("hostname", "runner-b"), ("started_at", "t2"), ("username", "other")),
        ),
        metadata=(("ci_url", "https://ci.invalid/2"),),
    )
    assert first.manifest_hash == second.manifest_hash
    assert first.environment.manifest_hash == second.environment.manifest_hash
    changed_state = replace(
        first,
        run_configuration=replace(first.run_configuration, seed=8),
    )
    assert changed_state.manifest_hash != first.manifest_hash
    assert replace(first.environment, source_revision="f" * 40).manifest_hash != (
        first.environment.manifest_hash
    )


def test_structured_result_hashes_values_with_float_hex_and_keep_lock_independent() -> None:
    result = PUBLIC_VALIDATION_RAW_RESULT
    manifest = result.to_manifest(PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK)
    assert manifest.metrics[0].metric_id == "raw_sre"
    assert manifest.identity_payload()["metrics"][0]["value_hex"] == (0.25698394782524847).hex()
    assert (
        manifest.scientific_state.scientific_lock_hash == PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK_HASH
    )
    changed_metrics = replace(result, metrics=(("raw_sre", 0.9),))
    changed_output = replace(result, output_sha256="a" * 64)
    assert changed_metrics.result_hash != result.result_hash
    assert changed_output.result_hash != result.result_hash
    assert (
        changed_metrics.to_manifest(PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK).manifest_hash
        != manifest.manifest_hash
    )
    assert (
        changed_output.to_manifest(PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK).manifest_hash
        != manifest.manifest_hash
    )
    assert changed_metrics.scientific_lock_hash == result.scientific_lock_hash
    assert changed_output.scientific_lock_hash == result.scientific_lock_hash

    changed_evidence_description = replace(
        result,
        evidence=(
            replace(result.evidence[0], description="updated annotation"),
            *result.evidence[1:],
        ),
    )
    assert changed_evidence_description.result_hash == result.result_hash


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_result_metrics_reject_nonfinite_values(value: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        ResultMetric("metric.value", value)
    with pytest.raises(ValueError, match="finite"):
        replace(PUBLIC_VALIDATION_RAW_RESULT, metrics=(("raw_sre", value),))


def test_experiment_manifest_cannot_bind_a_stale_or_mismatched_lock() -> None:
    lock = dict(PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK)
    lock["evaluator_id"] = "physical_trajectory.ade_fde_xy_rmse"
    with pytest.raises(ValueError, match="verified scientific lock"):
        ScientificStateBinding.from_verified_lock(lock)

    experiment = _execution_manifest()
    with pytest.raises(ValueError, match="model-selection use"):
        replace(
            experiment,
            run_configuration=replace(
                experiment.run_configuration,
                model_selection_use=ModelSelectionUse.UNKNOWN,
            ),
        )


def test_provenance_completeness_keeps_historical_and_future_records_distinct() -> None:
    historical = PUBLIC_VALIDATION_RAW_RESULT.to_manifest(PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK)
    assert historical.provenance_completeness is ProvenanceCompleteness.HISTORICAL_EVIDENCE_BOUND
    assert historical.experiment_manifest is None

    with pytest.raises(ValueError, match="experiment manifest"):
        replace(
            PUBLIC_VALIDATION_RAW_RESULT,
            provenance_completeness=ProvenanceCompleteness.EXECUTION_MANIFEST_BOUND,
        )

    execution = _execution_manifest()
    future = ResultRecord(
        run_id=execution.run_id,
        scientific_lock_hash=execution.scientific_state.scientific_lock_hash,
        model_checkpoint_sha256=None,
        metrics=(("score.v1", 0.5),),
        population=PUBLIC_VALIDATION_RAW_RESULT.population,
        evaluator_state=EvaluatorState.RAW_EVALUATION,
        validity=ResultValidity.RECORDED,
        provenance_completeness=ProvenanceCompleteness.EXECUTION_MANIFEST_BOUND,
        experiment_manifest=execution,
    )
    assert future.experiment_manifest.manifest_hash == execution.manifest_hash


_INCOMPATIBLE_RESULT_SCOPES = (
    pytest.param(
        PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK,
        ResultPopulation.PUBLIC_VALIDATION,
        EvaluatorState.PHYSICAL_DIAGNOSTIC,
        id="raw-lock-physical-label",
    ),
    pytest.param(
        PUBLIC_VALIDATION_PHYSICAL_SCIENTIFIC_LOCK,
        ResultPopulation.PUBLIC_VALIDATION,
        EvaluatorState.RAW_EVALUATION,
        id="physical-lock-raw-label",
    ),
    pytest.param(
        LOMO_RAW_SCIENTIFIC_LOCK,
        ResultPopulation.PUBLIC_VALIDATION,
        EvaluatorState.RAW_EVALUATION,
        id="lomo-lock-public-validation-label",
    ),
    pytest.param(
        PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK,
        ResultPopulation.LOMO_CROSS_MATCH,
        EvaluatorState.RAW_EVALUATION,
        id="raw-public-lock-lomo-label",
    ),
    pytest.param(
        PUBLIC_VALIDATION_PHYSICAL_SCIENTIFIC_LOCK,
        ResultPopulation.LOMO_CROSS_MATCH,
        EvaluatorState.PHYSICAL_DIAGNOSTIC,
        id="physical-public-lock-lomo-label",
    ),
)


@pytest.mark.parametrize(
    ("scientific_lock", "population", "evaluator_state"), _INCOMPATIBLE_RESULT_SCOPES
)
def test_execution_result_record_rejects_incompatible_scientific_scope(
    scientific_lock: object,
    population: ResultPopulation,
    evaluator_state: EvaluatorState,
) -> None:
    execution = _execution_manifest(scientific_lock=scientific_lock)
    with pytest.raises(ValueError, match="contradicts|incompatible"):
        _execution_result_record(execution, population, evaluator_state)


@pytest.mark.parametrize(
    ("scientific_lock", "population", "evaluator_state"), _INCOMPATIBLE_RESULT_SCOPES
)
def test_direct_result_manifest_rejects_incompatible_scientific_scope(
    scientific_lock: object,
    population: ResultPopulation,
    evaluator_state: EvaluatorState,
) -> None:
    execution = _execution_manifest(scientific_lock=scientific_lock)
    with pytest.raises(ValueError, match="contradicts|incompatible"):
        _direct_execution_result_manifest(execution, population, evaluator_state)


@pytest.mark.parametrize(
    ("scientific_lock", "population", "evaluator_state"),
    (
        pytest.param(
            PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK,
            ResultPopulation.PUBLIC_VALIDATION,
            EvaluatorState.RAW_EVALUATION,
            id="public-raw",
        ),
        pytest.param(
            PUBLIC_VALIDATION_PHYSICAL_SCIENTIFIC_LOCK,
            ResultPopulation.PUBLIC_VALIDATION,
            EvaluatorState.PHYSICAL_DIAGNOSTIC,
            id="public-physical",
        ),
        pytest.param(
            LOMO_RAW_SCIENTIFIC_LOCK,
            ResultPopulation.LOMO_CROSS_MATCH,
            EvaluatorState.RAW_EVALUATION,
            id="historical-lomo",
        ),
    ),
)
def test_execution_records_and_manifests_accept_compatible_historical_scopes(
    scientific_lock: object,
    population: ResultPopulation,
    evaluator_state: EvaluatorState,
) -> None:
    execution = _execution_manifest(scientific_lock=scientific_lock)
    record = _execution_result_record(execution, population, evaluator_state)
    manifest = _direct_execution_result_manifest(execution, population, evaluator_state)
    assert record.population is population
    assert manifest.evaluator_state is evaluator_state


def test_relabeling_execution_result_cannot_preserve_validity() -> None:
    execution = _execution_manifest()
    record = _execution_result_record(
        execution, ResultPopulation.PUBLIC_VALIDATION, EvaluatorState.RAW_EVALUATION
    )
    manifest = _direct_execution_result_manifest(
        execution, ResultPopulation.PUBLIC_VALIDATION, EvaluatorState.RAW_EVALUATION
    )
    with pytest.raises(ValueError, match="incompatible"):
        replace(record, population=ResultPopulation.LOMO_CROSS_MATCH)
    with pytest.raises(ValueError, match="contradicts"):
        replace(record, evaluator_state=EvaluatorState.PHYSICAL_DIAGNOSTIC)
    with pytest.raises(ValueError, match="incompatible"):
        replace(manifest, population=ResultPopulation.LOMO_CROSS_MATCH)
    with pytest.raises(ValueError, match="contradicts"):
        replace(manifest, evaluator_state=EvaluatorState.PHYSICAL_DIAGNOSTIC)


@pytest.mark.parametrize(
    ("evaluator_id", "evaluator_state"),
    (
        ("origin_relative_displacement_raw_population_sre", EvaluatorState.RAW_EVALUATION),
        ("physical_trajectory.ade_fde_xy_rmse", EvaluatorState.PHYSICAL_DIAGNOSTIC),
        ("absolute_position.population_sre_targets", EvaluatorState.RAW_EVALUATION),
        (
            "absolute_position.historical_continuous_pwl_v3",
            EvaluatorState.CALIBRATED_REWARD,
        ),
    ),
)
def test_registered_evaluators_accept_only_their_result_state(
    evaluator_id: str, evaluator_state: EvaluatorState
) -> None:
    lock = _synthetic_scope_lock(evaluator_id=evaluator_id)
    execution = _execution_manifest(scientific_lock=lock)
    _execution_result_record(execution, ResultPopulation.PUBLIC_VALIDATION, evaluator_state)


@pytest.mark.parametrize(
    "evaluator_id", ("example.future_evaluator", "absolute_position.per_target_progress")
)
def test_execution_results_fail_closed_for_unregistered_or_intermediate_evaluators(
    evaluator_id: str,
) -> None:
    lock = _synthetic_scope_lock(evaluator_id=evaluator_id)
    execution = _execution_manifest(scientific_lock=lock)
    with pytest.raises(ValueError, match="unsupported evaluator identity"):
        _execution_result_record(
            execution, ResultPopulation.PUBLIC_VALIDATION, EvaluatorState.RAW_EVALUATION
        )
    with pytest.raises(ValueError, match="unsupported evaluator identity"):
        _direct_execution_result_manifest(
            execution, ResultPopulation.PUBLIC_VALIDATION, EvaluatorState.RAW_EVALUATION
        )


def test_canonical_protocol_scopes_use_only_declared_public_populations() -> None:
    role_lock = _synthetic_scope_lock(
        split_protocol_id=CANONICAL_MATCH_ROLE_PROTOCOL.protocol_id,
        split_protocol_hash=CANONICAL_MATCH_ROLE_PROTOCOL.descriptor.assignment_sha256,
    )
    role_execution = _execution_manifest(scientific_lock=role_lock)
    _execution_result_record(
        role_execution, ResultPopulation.PUBLIC_TRAIN, EvaluatorState.RAW_EVALUATION
    )
    _direct_execution_result_manifest(
        role_execution, ResultPopulation.PUBLIC_VALIDATION, EvaluatorState.RAW_EVALUATION
    )

    lomo_lock = _synthetic_scope_lock(
        split_protocol_id=CANONICAL_LOMO_PROTOCOL.protocol_id,
        split_protocol_hash=CANONICAL_LOMO_PROTOCOL.split_sha256,
    )
    lomo_execution = _execution_manifest(scientific_lock=lomo_lock)
    _execution_result_record(
        lomo_execution, ResultPopulation.LOMO_CROSS_MATCH, EvaluatorState.RAW_EVALUATION
    )
    with pytest.raises(ValueError, match="incompatible"):
        _direct_execution_result_manifest(
            role_execution, ResultPopulation.HISTORICAL_PRIVATE, EvaluatorState.RAW_EVALUATION
        )
    with pytest.raises(ValueError, match="incompatible"):
        _direct_execution_result_manifest(
            lomo_execution, ResultPopulation.PUBLIC_VALIDATION, EvaluatorState.RAW_EVALUATION
        )


def test_res329_uncertainty_adapters_keep_three_axes_separate() -> None:
    public = from_match_summary(
        summarize_match_scores({PUBLIC_VALIDATION_MATCHES[0]: 0.25698394782524847})
    )
    assert public.descriptive_dispersion.n_units == 1
    assert public.point_estimate == pytest.approx(0.25698394782524847)
    assert public.descriptive_dispersion.sample_standard_deviation is None
    assert public.inferential_uncertainty.standard_error is None
    assert public.inferential_uncertainty.confidence_interval is None
    assert public.inferential_uncertainty.status is InferentialStatus.NOT_ESTIMABLE

    scores_by_seed = {
        seed: {match: float(index + seed % 7) for index, match in enumerate(PUBLIC_TRAIN_MATCHES)}
        for seed in (101, 102, 103)
    }
    lomo = from_lomo_summary(summarize_lomo_scores(scores_by_seed))
    assert lomo.descriptive_dispersion.unit == "held_out_match"
    assert lomo.descriptive_dispersion.n_units == 5
    assert math.isfinite(lomo.point_estimate)
    assert lomo.descriptive_dispersion.sample_standard_deviation is not None
    assert lomo.inferential_uncertainty.status is InferentialStatus.NOT_ESTIMABLE
    assert lomo.inferential_uncertainty.standard_error is None
    assert lomo.inferential_uncertainty.confidence_interval is None
    assert "overlapping cross-validation training sets" in lomo.inferential_uncertainty.reason
    assert lomo.algorithmic_sensitivity is not None
    assert lomo.algorithmic_sensitivity.n_units == 3
    assert lomo.algorithmic_sensitivity.unit == "training_seed"


def test_final_res329_protocol_identities_are_consumed_without_rebinding_history() -> None:
    assert CANONICAL_MATCH_ROLE_PROTOCOL.protocol_id == "conditional_motion.match_role_assignment"
    assert CANONICAL_MATCH_ROLE_PROTOCOL.version == "1.0.0"
    assert CANONICAL_MATCH_ROLE_PROTOCOL.assignment_sha256 == (
        "4fe08dd448096f0f54c3c773dcbd672e2f2e47c0b7faca591c72ba9167c0d444"
    )
    assert CANONICAL_LOMO_PROTOCOL.protocol_id == "conditional_motion.public_train_lomo"
    assert CANONICAL_LOMO_PROTOCOL.version == "1.0.0"
    assert CANONICAL_LOMO_PROTOCOL.split_sha256 == (
        "17d8e3bbc388971f4b52266c706830f449e5a4fbec77e1be214c52f703d289ee"
    )
    assert PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK["split_protocol_hash"] == (
        "5e060c84952cd4544fde6b80a93675c02c06036440ef9d2c97aa96eec618709c"
    )
    assert PUBLIC_VALIDATION_PHYSICAL_SCIENTIFIC_LOCK["split_protocol_hash"] == (
        "5e060c84952cd4544fde6b80a93675c02c06036440ef9d2c97aa96eec618709c"
    )
    assert LOMO_RAW_SCIENTIFIC_LOCK["split_protocol_id"] != CANONICAL_LOMO_PROTOCOL.protocol_id
    assert LOMO_RAW_SCIENTIFIC_LOCK["split_protocol_hash"] != CANONICAL_LOMO_PROTOCOL.split_sha256


def test_physical_lock_rejects_result_output_provenance_cycles() -> None:
    assert (
        validate_scientific_lock_provenance(
            PUBLIC_VALIDATION_PHYSICAL_SCIENTIFIC_LOCK, (_OUTPUT_SHA256,)
        )
        == ()
    )
    state = {
        key: value
        for key, value in PUBLIC_VALIDATION_PHYSICAL_SCIENTIFIC_LOCK.items()
        if key != "scientific_lock_hash"
    }
    snapshot = dict(state["scientific_provenance_snapshot"])
    citations = list(snapshot["citations"])
    citations.append(f"registry://sha256/{_OUTPUT_SHA256}")
    snapshot["citations"] = citations
    snapshot["snapshot_hash"] = hashlib.sha256(
        canonical_scientific_bytes(
            {"citations": "\n".join(citations), "snapshot_id": snapshot["snapshot_id"]}
        )
    ).hexdigest()
    state["scientific_provenance_snapshot"] = snapshot
    cyclic = build_scientific_lock(state)
    assert validate_scientific_lock_provenance(cyclic, (_OUTPUT_SHA256,)) == (
        f"scientific provenance cites result output SHA-256 {_OUTPUT_SHA256}",
    )
