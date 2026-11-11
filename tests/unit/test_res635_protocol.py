"""RES635: the proposed post-failure protocol is separate, claim-bounded and non-executable."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from fpdbench.evaluation.metrics.trajectory import (
    XY_RMSE_METRIC_ID,
    masked_physical_trajectory_metrics,
)

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "src/fpdbench/benchmarks/conditional_multi_agent_motion_prediction"
PROTOCOL = ROOT / "res635_post_failure_descriptive_protocol_v1.json"
AUTH_SCHEMA = ROOT / "res635_owner_authorization_v1.schema.json"
MANIFEST = ROOT / "res593_checkpoint_manifest_v1.json"
AMENDMENT = ROOT / "res593_amendment_v1.json"
BASELINE = ROOT / "res593_baseline_reference_v1.json"
BASELINE_INDEX = ROOT / "res593_private_baseline_manifest_index_v1.json"
DETERMINISTIC_RESULTS = ROOT / "res337_deterministic_results_v1.md"
DECISION = REPO / "docs/res635-admissibility-decision.md"
PROTOCOL_DOC = REPO / "docs/res635-post-failure-descriptive-protocol-v1.md"

PROTOCOL_SHA256 = "e53f83ec7096d00a391ecb5dd82822ff9165b612f9a3f92e7b639944357d77da"
HEX64 = set("0123456789abcdef")


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    assert isinstance(value, dict)
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cell_key(cell: dict[str, Any]) -> tuple[str, str, int]:
    return (
        str(cell["information_regime"]),
        str(cell["target_representation"]),
        int(cell["seed"]),
    )


def test_protocol_file_identity_is_frozen() -> None:
    assert _sha256(PROTOCOL) == PROTOCOL_SHA256


def test_protocol_is_proposed_and_not_an_execution_go() -> None:
    protocol = _load(PROTOCOL)
    assert protocol["status"] == "PROPOSED_UNRATIFIED"
    decision = protocol["decision"]
    assert decision["ticket_token"] == "DESIGN_GO_FOR_OWNER_REVIEW"
    assert decision["harness_token"] == "RES635_READY_FOR_INDEPENDENT_SCIENTIFIC_REVIEW"
    assert decision["route"] == "OPTION_B_POST_FAILURE_DESCRIPTIVE_SAME_FOUR_MATCHES"
    assert decision["confirmatory"] is False
    assert decision["authorizes_execution"] is False
    assert decision["execution_go_granted"] is False
    assert decision["owner_ratification_required"] is True
    authorization = protocol["authorization"]
    assert authorization["owner_authorization_present"] is False
    assert authorization["owner_go_granted"] is False
    assert authorization["one_campaign_only"] is True
    assert authorization["retry_after_failure"] is False
    assert authorization["reuse_res594_scope"] is False
    assert authorization["reuse_res594_go_phrase"] is False
    template = authorization["go_phrase_template"]
    assert template.startswith("RES635-OWNER-GO:")
    assert "RES594-OWNER-GO" not in template


def test_historical_authorities_match_the_repository_bytes() -> None:
    protocol = _load(PROTOCOL)
    authorities = protocol["historical_authorities"]
    assert _sha256(AMENDMENT) == authorities["res593_amendment_sha256"]
    assert authorities["res593_amendment_sha256"] == (
        "e54f067a07479b81c4625428e49e5a5b907c49987d4c5bd7982138e270e66913"
    )
    assert _sha256(MANIFEST) == authorities["res593_checkpoint_manifest_sha256"]
    assert authorities["res593_checkpoint_manifest_sha256"] == (
        "770f1d9bbca3020237992181a56e4f5be4adaae7aab07f5f1313aa699d8693e0"
    )
    assert _sha256(BASELINE) == authorities["res593_baseline_reference_sha256"]
    assert _sha256(BASELINE_INDEX) == authorities["res593_private_baseline_manifest_index_sha256"]
    assert (
        _sha256(DETERMINISTIC_RESULTS)
        == (authorities["res337_deterministic_results_document_sha256"])
    )
    assert authorities["res594_terminal_status"] == "CONSUMED_IRREVERSIBLY"
    assert authorities["res594_retry_allowed"] is False
    assert authorities["res594_issue_status"] == "Canceled"
    assert authorities["res594_result_bundle_committed"] is False
    assert authorities["res594_learned_result_records_observed"] == 0
    assert authorities["protected_population_status"] == "NOT_QUALIFIED"
    assert authorities["lomo_216_fit_status"] == "DEFERRED_NOT_EXECUTED"


def test_protocol_binds_every_res614_qualification_artifact() -> None:
    protocol = _load(PROTOCOL)
    authorities = protocol["historical_authorities"]
    artifacts = {
        "res614_incident_evidence_index_sha256": REPO / "docs/res614/incident_evidence_index.json",
        "res614_incident_report_sha256": REPO / "docs/res614-sigterm-incident-report.md",
        "res614_execution_architecture_proposal_sha256": REPO
        / "docs/res614-execution-architecture-proposal.md",
        "res614_runtime_audit_governance_sha256": REPO
        / "docs/res614-runtime-audit-and-governance.md",
        "res614_synthetic_performance_report_sha256": REPO
        / "docs/res614-synthetic-performance-report.md",
        "res614_synthetic_benchmark_v1_sha256": REPO / "docs/res614/synthetic_benchmark_v1.json",
        "res614_resilient_runner_sha256": REPO / "tools/res614_resilient_runner.py",
    }
    for key, path in artifacts.items():
        assert _sha256(path) == authorities[key], key


def test_model_matrix_matches_the_frozen_manifest_exactly() -> None:
    protocol = _load(PROTOCOL)
    manifest = _load(MANIFEST)
    matrix = protocol["model_matrix"]
    cells = matrix["cells"]
    assert matrix["checkpoint_count"] == 18
    assert matrix["cell_count"] == 18
    assert matrix["match_scoped_result_count"] == 72
    assert matrix["new_fits"] == 0
    assert matrix["checkpoint_reselection"] is False
    assert matrix["checkpoint_substitution"] is False
    assert matrix["warm_start"] is False
    assert matrix["hyperparameter_search"] is False
    assert matrix["optimizer_steps"] == 0
    assert len(cells) == 18
    assert {_cell_key(cell) for cell in cells} == {
        ("history_only", "absolute_xy", 1729),
        ("history_only", "absolute_xy", 2718),
        ("history_only", "absolute_xy", 31415),
        ("history_only", "origin_relative_displacement", 1729),
        ("history_only", "origin_relative_displacement", 2718),
        ("history_only", "origin_relative_displacement", 31415),
        ("future_ball", "absolute_xy", 1729),
        ("future_ball", "absolute_xy", 2718),
        ("future_ball", "absolute_xy", 31415),
        ("future_ball", "origin_relative_displacement", 1729),
        ("future_ball", "origin_relative_displacement", 2718),
        ("future_ball", "origin_relative_displacement", 31415),
        ("future_opponent_plus_ball", "absolute_xy", 1729),
        ("future_opponent_plus_ball", "absolute_xy", 2718),
        ("future_opponent_plus_ball", "absolute_xy", 31415),
        ("future_opponent_plus_ball", "origin_relative_displacement", 1729),
        ("future_opponent_plus_ball", "origin_relative_displacement", 2718),
        ("future_opponent_plus_ball", "origin_relative_displacement", 31415),
    }
    manifest_by_key = {_cell_key(cell): cell for cell in manifest["checkpoints"]}
    protocol_by_key = {_cell_key(cell): cell for cell in cells}
    assert set(manifest_by_key) == set(protocol_by_key)
    for key, manifest_cell in manifest_by_key.items():
        protocol_cell = protocol_by_key[key]
        assert protocol_cell["checkpoint_sha256"] == manifest_cell["checkpoint_sha256"]
        assert protocol_cell["configuration_sha256"] == manifest_cell["configuration_sha256"]
        assert protocol_cell["selected_step"] == manifest_cell["selected_step"]
        assert protocol_cell["optimizer_steps"] == manifest_cell["optimizer_steps"]
        assert protocol_cell["receipt_sha256"] == manifest_cell["receipt_sha256"]


def test_population_is_exactly_the_four_frozen_evaluation_matches() -> None:
    protocol = _load(PROTOCOL)
    population = protocol["population"]
    assert population["role"] == "evaluation"
    assert population["match_ids"] == ["1874553", "1925299", "2006229", "2010085"]
    assert population["n_independent_matches"] == 4
    assert population["overlapping_windows_independent"] is False
    assert population["seeds_independent_matches"] is False
    assert population["training_matches_scored"] is False
    assert population["validation_matches_scored"] is False
    assert population["provider_mixing"] is False
    assert population["history_intervals"] == 25
    assert population["future_steps"] == 15
    assert population["step_seconds"] == 0.2
    assert population["horizon_seconds"] == 3.0
    assert population["support_slots"] == 41
    manifest = _load(MANIFEST)
    assert population["match_ids"] == manifest["roles"]["evaluation"]


def test_endpoints_and_aggregation_are_inherited_without_post_failure_changes() -> None:
    protocol = _load(PROTOCOL)
    endpoints = protocol["endpoints"]
    assert endpoints["primary"] == "physical XY ADE in metres"
    assert endpoints["secondary"] == [
        "physical XY FDE in metres",
        "physical XY RMSE in metres",
    ]
    assert endpoints["new_endpoints"] is False
    assert endpoints["endpoint_changes_after_failure"] is False
    aggregation = protocol["aggregation"]
    assert aggregation["record_count"] == 72
    assert aggregation["preserve_all_records"] is True
    assert aggregation["pool_overlapping_windows"] is False
    assert aggregation["inferential_tests"] is False
    assert aggregation["confidence_intervals"] is False
    assert aggregation["p_values"] is False
    assert aggregation["significance_claims"] is False
    assert aggregation["seed_to_match"] == (
        "arithmetic mean of three frozen seed values within each match"
    )
    assert aggregation["match_to_configuration"] == (
        "equal arithmetic mean of the four match-level seed means"
    )


def test_xy_rmse_metric_contract_is_scalar_coordinate_rmse() -> None:
    protocol = _load(PROTOCOL)
    contract = protocol["endpoints"]["metric_contract"]["xy_rmse"]
    assert contract["metric_id"] == XY_RMSE_METRIC_ID == "trajectory.xy_rmse_m.v1"
    assert contract["denominator"] == "2 * N_masked_points"
    assert "2 * N_masked_points" in contract["formula"]
    assert contract["not_root_mean_squared_euclidean_displacement"] is True
    assert contract["historical_values_unchanged"] is True

    prediction = [[[[3.0, 4.0]], [[0.0, 0.0]], [[3.0, 4.0]]]]
    truth = [[[None], [[0.0, 0.0]], [[0.0, 0.0]]]]
    metrics = masked_physical_trajectory_metrics(prediction, truth)
    assert metrics.scored_points == 2
    assert metrics.final_targets == 1
    assert metrics.xy_rmse_m == 2.5
    assert metrics.ade_m == 2.5
    assert metrics.fde_m == 5.0
    root_mean_squared_euclidean = math.sqrt((0.0**2 + 5.0**2) / 2)
    assert metrics.xy_rmse_m != root_mean_squared_euclidean


def test_contrasts_are_the_four_frozen_contrasts_and_paired_within_match() -> None:
    protocol = _load(PROTOCOL)
    contrasts = {
        (item["id"], item["representation"], item["formula"]) for item in protocol["contrasts"]
    }
    assert contrasts == {
        (
            "C1",
            "absolute_xy",
            "history_only ADE - future_ball ADE",
        ),
        (
            "C1",
            "origin_relative_displacement",
            "history_only ADE - future_ball ADE",
        ),
        (
            "C2",
            "absolute_xy",
            "future_ball ADE - future_opponent_plus_ball ADE",
        ),
        (
            "C2",
            "origin_relative_displacement",
            "future_ball ADE - future_opponent_plus_ball ADE",
        ),
    }
    interpretation = protocol["contrast_interpretation"]
    assert interpretation["paired_within_match"] is True
    assert interpretation["report_all_four_match_values"] is True
    assert interpretation["report_equal_match_mean"] is True
    assert interpretation["conditional_not_ex_ante"] is True


def test_claims_are_descriptive_only_and_forbid_confirmatory_overreach() -> None:
    protocol = _load(PROTOCOL)
    claims = protocol["claims"]
    assert claims["classification"] == "descriptive only"
    assert claims["confirmatory_hypothesis_tests"] is False
    assert claims["population_generalization"] is False
    assert claims["deployment_claims"] is False
    assert claims["ex_ante_future_context_claims"] is False
    assert claims["original_v2_completion"] is False
    assert claims["lomo_completion"] is False
    assert claims["protected_qualification"] is False
    allowed = " ".join(claims["allowed"]).lower()
    forbidden = " ".join(claims["forbidden"]).lower()
    assert "descriptive" in allowed
    assert "four fixed evaluation matches" in allowed
    for phrase in (
        "statistical significance",
        "generalization",
        "deployment",
        "original v2",
        "216-fit",
        "protected population",
        "new authorization hash",
        "consumed res594 scope",
    ):
        assert phrase in forbidden


def test_interruption_policy_is_fail_closed_and_does_not_reauthorize_the_old_scope() -> None:
    protocol = _load(PROTOCOL)
    policy = protocol["interruption_policy"]
    assert policy["mode"] == "FAIL_CLOSED_WITH_NARROW_INFRASTRUCTURE_CONTINUATION"
    assert policy["scientific_or_integrity_failure"] == {
        "terminal": True,
        "retry": False,
        "new_owner_go_required": True,
    }
    assert policy["unknown_interruption_cause"] == {
        "terminal": True,
        "retry": False,
        "new_owner_go_required": True,
    }
    continuation = policy["proven_infrastructure_interruption"]
    assert continuation["continuation_allowed"] is True
    assert continuation["same_frozen_scope_only"] is True
    assert continuation["match_boundary_only"] is True
    assert continuation["sealed_receipts_only"] is True
    assert continuation["bitwise_parity_required"] is True
    assert continuation["no_human_access_to_interim_results"] is True
    assert continuation["no_outcome_dependent_decision"] is True
    assert continuation["max_continuations"] == 1
    assert continuation["max_total_cpu_seconds"] == 14400
    assert continuation["max_total_wall_seconds"] == 21600
    assert continuation["reuse_consumed_res594_scope"] is False
    assert continuation["new_scope_per_continuation"] is False
    assert policy["partial_results_scientifically_usable"] is False
    assert policy["sender_attribution_required"] is True
    assert policy["terminal_record_required"] is True


def test_resource_budget_is_cpu_only_zero_paid_and_no_training() -> None:
    protocol = _load(PROTOCOL)
    budget = protocol["resource_budget"]
    assert budget["device"] == "cpu"
    assert budget["precision"] == "float32"
    assert budget["threads"] == 1
    assert budget["python"] == "3.12.8"
    assert budget["numpy"] == "2.2.4"
    assert budget["pytorch"] == "2.6.0+cpu"
    assert budget["cpu_seconds_ceiling"] == 14400
    assert budget["wall_seconds_ceiling"] == 21600
    assert budget["rss_bytes_ceiling"] == 2147483648
    assert budget["private_working_disk_bytes_ceiling"] == 2147483648
    assert budget["paid_compute_units"] == 0
    assert budget["paid_cost_usd"] == 0
    assert budget["gpu"] is False
    assert budget["training"] is False
    assert budget["lomo_fits"] == 0
    assert budget["checkpoint_loads"] == 18
    assert budget["forward_calls_estimate"] == 930834
    assert budget["full_snapshot_bytes"] == 0


def test_authorization_schema_rejects_the_old_scope_and_old_go_phrase() -> None:
    schema = _load(AUTH_SCHEMA)
    properties = schema["properties"]
    assert properties["schema_id"]["const"] == "fpdbench.res635.owner-execution-authorization"
    assert properties["study_id"]["const"] == (
        "fpdbench.public-skillcorner-post-failure-descriptive-heldout/1.0.0"
    )
    assert properties["res594_scope_reuse"]["const"] is False
    assert properties["res594_go_phrase_reuse"]["const"] is False
    assert properties["retry_after_scientific_failure"]["const"] is False
    assert properties["retry_after_unknown_interruption"]["const"] is False
    assert properties["one_campaign_only"]["const"] is True
    assert properties["protected_status"]["const"] == "NOT_QUALIFIED"
    assert properties["checkpoint_manifest_sha256"]["const"] == (
        "770f1d9bbca3020237992181a56e4f5be4adaae7aab07f5f1313aa699d8693e0"
    )
    assert properties["research_admission_sha256"]["const"] == (
        "a8c82bfa09ac792d6c4ae779d4b28158c33ed3c2500f8548f3e94d48197f4fd1"
    )
    assert properties["evaluation_match_ids"]["const"] == [
        "1874553",
        "1925299",
        "2006229",
        "2010085",
    ]
    template = properties["go_phrase_template"]["const"]
    assert template.startswith("RES635-OWNER-GO:")
    assert "RES594-OWNER-GO" not in template
    required = set(schema["required"])
    for field in (
        "protocol_sha256",
        "scorer_code_sha256",
        "new_scope_sha256",
        "ledger_root_identity_sha256",
        "independent_validation_report_sha256",
        "interruption_policy",
    ):
        assert field in required


def test_authorization_schema_is_consistent_with_the_protocol() -> None:
    protocol = _load(PROTOCOL)
    schema = _load(AUTH_SCHEMA)
    properties = schema["properties"]
    budget = protocol["resource_budget"]
    limits = properties["resource_limits"]["properties"]
    assert limits["cpu_seconds"]["const"] == budget["cpu_seconds_ceiling"]
    assert limits["wall_seconds"]["const"] == budget["wall_seconds_ceiling"]
    assert limits["rss_bytes"]["const"] == budget["rss_bytes_ceiling"]
    assert (
        limits["private_working_disk_bytes"]["const"]
        == (budget["private_working_disk_bytes_ceiling"])
    )
    assert limits["paid_compute_units"]["const"] == budget["paid_compute_units"]
    assert limits["paid_cost_usd"]["const"] == budget["paid_cost_usd"]
    assert limits["gpu"]["const"] == budget["gpu"]
    runtime = properties["runtime"]["properties"]
    assert runtime["python"]["const"] == budget["python"]
    assert runtime["numpy"]["const"] == budget["numpy"]
    assert runtime["pytorch"]["const"] == budget["pytorch"]
    assert runtime["device"]["const"] == budget["device"]
    assert runtime["precision"]["const"] == budget["precision"]
    assert runtime["threads"]["const"] == budget["threads"]
    policy = properties["interruption_policy"]["properties"]
    assert policy["mode"]["const"] == protocol["interruption_policy"]["mode"]
    assert policy["max_continuations"]["const"] == 1
    assert policy["bitwise_parity_required"]["const"] is True
    assert policy["no_human_access_to_interim_results"]["const"] is True
    assert policy["no_outcome_dependent_decision"]["const"] is True
    assert policy["scientific_or_integrity_failure_terminal"]["const"] is True
    assert policy["unknown_interruption_terminal"]["const"] is True


def test_protocol_has_no_private_paths_or_historical_entrypoint_reuse() -> None:
    text = PROTOCOL.read_text()
    for forbidden in (
        "evaluation-input.private",
        "/srv/fpdbench-private",
        "score_res594_heldout",
        "fpdbench-res594",
        "RES594-OWNER-GO",
        "tracking_extrapolated.jsonl",
    ):
        assert forbidden not in text
    protocol = _load(PROTOCOL)
    execution = protocol["execution"]
    assert execution["reuse_res594_scorer"] is False
    assert execution["reuse_res594_entrypoint"] is False
    assert execution["full_private_snapshot"] is False
    assert execution["streaming_input"] is True
    assert execution["per_match_sealed_receipts"] is True
    assert execution["receipt_hash_chain"] is True
    assert execution["independent_completion_verification"] is True
    assert execution["detached_supervisor"] is True
    assert execution["own_session"] is True
    assert execution["worker_process_group"] is True
    assert execution["signal_attribution"] is True
    assert execution["transient_agent_session_supervision"] is False
    assert execution["real_data_qualified"] is False
    assert execution["synthetic_end_to_end_qualification_required"] is True


def test_protocol_gates_are_strictly_ordered_and_only_gate_six_authorizes_execution() -> None:
    protocol = _load(PROTOCOL)
    gates = protocol["gates"]
    assert [gate["order"] for gate in gates] == list(range(1, 10))
    assert [gate["name"] for gate in gates] == [
        "proposed scientific protocol",
        "independent scientific review",
        "express owner ratification",
        "separately approved synthetic-only engineering qualification",
        "private non-consuming preflight",
        "new and distinct express owner GO",
        "one controlled real study",
        "independent private 72-result verification",
        "public-safe reporting",
    ]
    assert [gate["order"] for gate in gates if gate["authorizes_execution"]] == [6]
    assert gates[0]["status"] == "DRAFTED"
    assert all(gate["status"] in {"DRAFTED", "REQUIRED", "NOT_STARTED"} for gate in gates)


def test_publication_requirements_and_rights_boundaries_are_explicit() -> None:
    protocol = _load(PROTOCOL)
    publication = protocol["publication"]
    assert publication["paper_b_claim_class"] == "descriptive"
    assert publication["no_confirmatory_claims"] is True
    assert publication["no_generalization_claims"] is True
    assert publication["no_deployment_claims"] is True
    assert publication["no_v2_completion_claims"] is True
    assert publication["no_lomo_completion_claims"] is True
    assert publication["no_protected_qualification_claims"] is True
    assert publication["rights_cleared_aggregates_only"] is True
    assert publication["skillcorner_attribution_required"] is True
    disclosures = " ".join(publication["required_disclosures"]).lower()
    for phrase in (
        "original v2",
        "deterministic baselines",
        "validation means",
        "res594",
        "four matches",
        "realized future observations",
        "not_qualified",
        "no statistical significance",
    ):
        assert phrase in disclosures
    provenance = protocol["provenance"]
    assert provenance["raw_or_row_level_publication"] is False
    assert provenance["new_ledger_root_required"] is True
    assert provenance["ledger_root_independent_of_output"] is True
    assert provenance["single_owner_private_ledger_root"] is True


def test_decision_memo_is_evidence_linked_and_not_an_execution_go() -> None:
    text = DECISION.read_text()
    assert "DESIGN_GO_FOR_OWNER_REVIEW" in text
    assert "RES635_READY_FOR_INDEPENDENT_SCIENTIFIC_REVIEW" in text
    assert PROTOCOL_SHA256 in text
    assert "No execution GO is granted" in text
    assert "Option 2, descriptive only" in text
    assert "not qualified now" in text.lower()
    assert "new authorization hash is not sufficient" in text.lower()
    assert "RES594-OWNER-GO" not in text
    for forbidden in (
        "evaluation-input.private",
        "/srv/fpdbench-private",
        "tracking_extrapolated.jsonl",
    ):
        assert forbidden not in text


def test_protocol_document_matches_the_machine_readable_identity() -> None:
    protocol = _load(PROTOCOL)
    text = PROTOCOL_DOC.read_text()
    assert protocol["study_id"] in text
    assert PROTOCOL_SHA256 in text
    assert "PROPOSED / UNRATIFIED / NOT AUTHORIZED FOR EXECUTION" in text
    assert "Execution GO" in text
    for match_id in protocol["population"]["match_ids"]:
        assert match_id in text
    for phrase in ("sealed receipts", "detached supervisor", "fail-closed", "n=4", "NOT_QUALIFIED"):
        assert phrase.lower() in text.lower()


def test_all_sha256_authorities_are_well_formed() -> None:
    protocol = _load(PROTOCOL)
    serialized = json.dumps(protocol, sort_keys=True)
    assert "RES594-OWNER-GO" not in serialized
    authorities = protocol["historical_authorities"]
    for key, value in authorities.items():
        if key.endswith("_sha256"):
            assert len(value) == 64 and set(value) <= HEX64, key
    for cell in protocol["model_matrix"]["cells"]:
        for key in ("checkpoint_sha256", "configuration_sha256", "receipt_sha256"):
            value = cell[key]
            assert len(value) == 64 and set(value) <= HEX64, (key, value)
