"""Repository config, registry, naming, and artifact validation."""

import tomllib
from pathlib import Path
from typing import cast

from fpdbench.benchmarks.registry import default_registry
from fpdbench.validation.artifacts import validate_artifacts
from fpdbench.validation.naming import validate_naming


def validate_repository(root: Path) -> tuple[str, ...]:
    errors = list(validate_naming(root))
    errors.extend(validate_artifacts(root))
    registry = default_registry()
    expected_families = set(registry.families())
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
