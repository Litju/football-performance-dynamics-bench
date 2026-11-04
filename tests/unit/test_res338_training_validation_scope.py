from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
import train_res338_final_fits as trainer  # noqa: E402
from research_population_v1 import training_validation_source_roles  # noqa: E402
from research_population_verifier_v1 import _scoped_authorities  # noqa: E402
from train_res338_final_fits import (  # noqa: E402
    _frozen_training_validation_resume_authority,
    _has_staged_preloaded_caches,
)


def test_training_validation_authorities_exclude_evaluation_matches() -> None:
    authorities = _scoped_authorities("training-validation")
    role_counts = {
        role: sum(actual_role == role for actual_role, _ in authorities.roles)
        for role in ("training", "validation", "evaluation")
    }
    selected = {str(match_id) for match_id in authorities.source["selected_source_matches"]}

    assert role_counts == {"training": 12, "validation": 4, "evaluation": 0}
    assert len(selected) == 16
    assert selected == set(authorities.match_order)
    assert len(authorities.match_order) == 16


def test_source_role_lookup_uses_the_frozen_training_validation_roles() -> None:
    roles = training_validation_source_roles()

    assert len(roles) == 16
    assert list(roles.values()).count("training") == 12
    assert list(roles.values()).count("validation") == 4


def test_empty_preloaded_cache_root_allows_colab_regeneration(tmp_path: Path) -> None:
    cache_root = tmp_path / "preloaded-cache"
    cache_root.mkdir(mode=0o700)
    assert not _has_staged_preloaded_caches(cache_root, {"match-1"})

    training = cache_root / "training"
    training.mkdir(mode=0o700)
    assert not _has_staged_preloaded_caches(cache_root, {"match-1"})
    (training / "match-1").mkdir(mode=0o700)
    assert _has_staged_preloaded_caches(cache_root, {"match-1"})

    (training / "match-extra").mkdir(mode=0o700)
    with pytest.raises(ValueError, match="staged cache set"):
        _has_staged_preloaded_caches(cache_root, {"match-1"})


def test_cuda_resume_uses_the_content_addressed_population_freeze(tmp_path: Path) -> None:
    plan, _, all_roles = trainer._frozen_split_and_authorities()
    roles = {role: sorted(all_roles[role]) for role in ("training", "validation")}
    authority = plan["population_authority"]
    reference = {
        "schema_id": "fpdbench.res338.training-validation-reference",
        "parent_research_manifest_sha256": trainer.RESEARCH_MANIFEST_SHA256,
        "source_release_hash": authority["source_release_hash"],
        "source_population_hash": authority["source_population_hash"],
        "roles": roles,
        "source_match_order": roles["training"] + roles["validation"],
        "preloaded_cache_identities": {match_id: {} for match_id in roles["training"][:6]},
    }
    reference_path = tmp_path / "reference.json"
    reference_path.write_bytes(trainer._canonical(reference))
    reference_path.chmod(0o600)
    reference_sha = trainer._sha256_file(reference_path)
    population_rehash = {
        "scope": "training-validation",
        "reference_manifest_sha256": reference_sha,
        "source_files_rehashed": 64,
        "independent_source_files_rehashed": 64,
        "producer_outputs_rehashed": 16,
        "verifier_outputs_rehashed": 16,
        "producer_verifier_mismatches": 0,
        "exact_role_assignment_match": True,
    }
    freeze = {
        "schema_id": "fpdbench.res338-research-final-fit-campaign",
        "research_manifest_sha256": trainer.RESEARCH_MANIFEST_SHA256,
        "research_scope": "training-validation",
        "reference_manifest_sha256": reference_sha,
        "protected_status": "NOT_QUALIFIED",
        "source_release_hash": authority["source_release_hash"],
        "source_population_hash": authority["source_population_hash"],
        "source_inventory_sha256": "c" * 64,
        "independent_source_sha256": "d" * 64,
        "source_reconciliation_status": "PASSED",
        "research_roles": roles,
        "population_rehash": population_rehash,
    }

    research_manifest, rehash, resumed_roles = _frozen_training_validation_resume_authority(
        freeze, reference_path, reference_sha, plan, all_roles
    )

    assert resumed_roles == roles
    assert rehash == population_rehash
    assert (
        research_manifest["preloaded_cache_identities"] == reference["preloaded_cache_identities"]
    )
    assert research_manifest["protected_status"] == "NOT_QUALIFIED"

    population_rehash["source_files_rehashed"] = 63
    with pytest.raises(ValueError, match="frozen training-validation population"):
        _frozen_training_validation_resume_authority(
            freeze, reference_path, reference_sha, plan, all_roles
        )
