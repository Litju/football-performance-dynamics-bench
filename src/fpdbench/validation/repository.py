"""Repository config, registry, naming, and artifact validation."""

import json
import tomllib
from pathlib import Path
from typing import cast

from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
    HISTORICAL_RESULTS,
    LOMO_RAW_SCIENTIFIC_LOCK,
    PRIVATE_RESULT_RECORDS,
    PUBLIC_VALIDATION_PHYSICAL_SCIENTIFIC_LOCK,
    PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK,
)
from fpdbench.benchmarks.registry import default_registry
from fpdbench.benchmarks.transition_graph import validate_transition_graph
from fpdbench.experiments import EvaluatorState, ResultPopulation, ScientificStateBinding
from fpdbench.experiments.provenance import evidence_sha256
from fpdbench.protocols import validate_canonical_protocols
from fpdbench.provenance import EvidenceReference, validate_evidence_reference_shape
from fpdbench.provenance.scientific_lock import (
    validate_scientific_lock_provenance,
    verify_scientific_lock,
)
from fpdbench.validation.artifacts import validate_artifacts
from fpdbench.validation.naming import validate_naming


def validate_repository(root: Path) -> tuple[str, ...]:
    errors = list(validate_naming(root))
    errors.extend(validate_artifacts(root))
    errors.extend(validate_transition_graph())
    errors.extend(validate_canonical_protocols())
    result_output_hashes = tuple(
        digest for result in HISTORICAL_RESULTS for digest in result.output_sha256s
    )
    lock_files = (
        (
            "public-validation raw lock",
            PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK,
            "benchmarks/conditional_multi_agent_motion_prediction/public_validation_raw_displacement_scientific_lock.json",
        ),
        (
            "LOMO raw lock",
            LOMO_RAW_SCIENTIFIC_LOCK,
            "benchmarks/conditional_multi_agent_motion_prediction/lomo_raw_displacement_scientific_lock.json",
        ),
        (
            "public-validation physical diagnostic lock",
            PUBLIC_VALIDATION_PHYSICAL_SCIENTIFIC_LOCK,
            "benchmarks/conditional_multi_agent_motion_prediction/public_validation_physical_diagnostic_scientific_lock.json",
        ),
    )
    locks_by_hash: dict[str, dict[str, object]] = {}
    for name, lock, relative_path in lock_files:
        lock_hash = lock.get("scientific_lock_hash")
        if not verify_scientific_lock(lock) or not isinstance(lock_hash, str):
            errors.append(f"{name}: scientific lock does not verify")
        else:
            locks_by_hash[lock_hash] = lock
            try:
                serialized = json.loads((root / relative_path).read_text())
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(f"{name}: cannot read lock file {relative_path}: {exc}")
            else:
                if serialized != lock:
                    errors.append(f"{name}: lock file disagrees with the source manifest")
        try:
            ScientificStateBinding.from_verified_lock(lock)
        except ValueError as exc:
            errors.append(f"{name}: invalid scientific state binding: {exc}")
        snapshot_value = lock.get("scientific_provenance_snapshot")
        if isinstance(snapshot_value, dict):
            snapshot = cast(dict[str, object], snapshot_value)
            citations_value = snapshot.get("citations")
        else:
            citations_value = None
        if isinstance(citations_value, list):
            citations = cast(list[object], citations_value)
            for citation in citations:
                if isinstance(citation, str):
                    try:
                        evidence_sha256(EvidenceReference(citation))
                    except ValueError as exc:
                        errors.append(f"{name}: invalid immutable provenance citation: {exc}")
                else:
                    errors.append(f"{name}: scientific provenance citation must be a string")
        errors.extend(
            f"{name}: {error}"
            for error in validate_scientific_lock_provenance(lock, result_output_hashes)
        )
    if len(HISTORICAL_RESULTS) != 19:
        errors.append("historical scientific result count must remain 19")
    if PRIVATE_RESULT_RECORDS:
        errors.append("private result records must remain empty")
    for result in HISTORICAL_RESULTS:
        lock = locks_by_hash.get(result.scientific_lock_hash)
        if lock is None:
            errors.append(f"result {result.run_id}: scientific lock is missing or unverified")
            continue
        binding = ScientificStateBinding.from_verified_lock(lock)
        if binding.scientific_lock_hash != result.scientific_lock_hash:
            errors.append(f"result {result.run_id}: scientific state binding does not match lock")
        expected_lock_hash = (
            PUBLIC_VALIDATION_PHYSICAL_SCIENTIFIC_LOCK["scientific_lock_hash"]
            if result.evaluator_state is EvaluatorState.PHYSICAL_DIAGNOSTIC
            else LOMO_RAW_SCIENTIFIC_LOCK["scientific_lock_hash"]
            if result.population is ResultPopulation.LOMO_CROSS_MATCH
            else PUBLIC_VALIDATION_RAW_SCIENTIFIC_LOCK["scientific_lock_hash"]
        )
        if result.scientific_lock_hash != expected_lock_hash:
            errors.append(
                f"result {result.run_id}: scientific lock does not match its population/evaluator"
            )
        for reference in result.evidence:
            errors.extend(
                f"result {result.run_id}: {error}"
                for error in validate_evidence_reference_shape(reference)
            )
        for digest in result.output_sha256s:
            if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
                errors.append(f"result {result.run_id}: malformed output SHA-256")
    registry = default_registry()
    expected_families = set(registry.family_ids())
    config_families: set[str] = set()
    for config_path in sorted((root / "benchmarks").glob("*/benchmark.toml")):
        try:
            config = cast(dict[str, object], tomllib.loads(config_path.read_text()))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            errors.append(f"invalid benchmark config {config_path.relative_to(root)}: {exc}")
            continue
        family_id = config.get("family_id")
        raw_benchmark_ids = config.get("benchmark_ids")
        raw_object_ids = config.get("research_object_ids")
        if (
            not isinstance(family_id, str)
            or not isinstance(raw_benchmark_ids, list)
            or not isinstance(raw_object_ids, list)
        ):
            errors.append(f"invalid family or benchmark IDs in {config_path.relative_to(root)}")
            continue
        values = cast(list[object], raw_benchmark_ids)
        object_values = cast(list[object], raw_object_ids)
        if not all(isinstance(value, str) for value in values + object_values):
            errors.append(f"invalid family or benchmark IDs in {config_path.relative_to(root)}")
            continue
        benchmark_ids = tuple(value for value in values if isinstance(value, str))
        research_object_ids = tuple(value for value in object_values if isinstance(value, str))
        config_families.add(family_id)
        registered_ids = {item.identity.scientific_id for item in registry.discover(family_id)}
        if set(benchmark_ids) != registered_ids:
            errors.append(
                f"benchmark config disagrees with registry: {config_path.relative_to(root)}"
            )
        registered_object_ids = {
            item.identity.scientific_id for item in registry.research_objects(family_id)
        }
        if set(research_object_ids) != registered_object_ids:
            errors.append(
                f"research-object config disagrees with registry: {config_path.relative_to(root)}"
            )
    if config_families != expected_families:
        errors.append("benchmark configuration family set disagrees with registry")
    pyproject_path = root / "pyproject.toml"
    try:
        pyproject = tomllib.loads(pyproject_path.read_text())
        project = pyproject["project"]
        if project["name"] != "football-performance-dynamics-bench":
            errors.append("Python distribution name is not canonical")
        if project["requires-python"] != ">=3.12":
            errors.append("Python requirement must be >=3.12")
        if pyproject["project"]["scripts"].get("fpdbench") != "fpdbench.cli:main":
            errors.append("console script does not target the CLI")
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError) as exc:
        errors.append(f"invalid project configuration: {exc}")
    return tuple(sorted(set(errors)))
