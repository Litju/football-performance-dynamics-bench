"""Command-line interface for benchmark discovery and reproducibility checks."""

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import cast

from fpdbench.benchmarks.registry import default_registry
from fpdbench.data_sources.skillcorner import (
    load_manifest,
    validate_manifest,
    verify_live,
    verify_local_checkout,
)
from fpdbench.provenance.evidence_inventory import validate_evidence_inventory
from fpdbench.provenance.scientific_lock import build_scientific_lock, verify_scientific_lock
from fpdbench.reproducibility import (
    CAPABILITY_MATRIX,
    check_reproducibility,
    render_reproducibility_snapshot,
    snapshot_sha256,
)
from fpdbench.validation import validate_naming, validate_repository


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fpdbench")
    commands = parser.add_subparsers(dest="command", required=True)

    benchmarks = commands.add_parser("benchmarks")
    benchmark_commands = benchmarks.add_subparsers(dest="benchmark_command", required=True)
    listing = benchmark_commands.add_parser("list")
    listing.add_argument("--family")
    description = benchmark_commands.add_parser("describe")
    description.add_argument("scientific_id")

    families = commands.add_parser("families")
    family_commands = families.add_subparsers(dest="family_command", required=True)
    family_commands.add_parser("list")
    family_description = family_commands.add_parser("describe")
    family_description.add_argument("family_id")

    research_objects = commands.add_parser("research-objects")
    object_commands = research_objects.add_subparsers(dest="research_object_command", required=True)
    object_commands.add_parser("list")
    object_description = object_commands.add_parser("describe")
    object_description.add_argument("scientific_id")

    validation = commands.add_parser("validate")
    validation.add_argument("--root", type=Path, default=Path.cwd())
    evidence = commands.add_parser("evidence")
    evidence_commands = evidence.add_subparsers(dest="evidence_command", required=True)
    evidence_validation = evidence_commands.add_parser("validate")
    evidence_validation.add_argument("--registry-root", type=Path)
    reproducibility = commands.add_parser("reproducibility")
    reproducibility_commands = reproducibility.add_subparsers(
        dest="reproducibility_command", required=True
    )
    reproducibility_commands.add_parser("check")
    snapshot = reproducibility_commands.add_parser("snapshot")
    snapshot.add_argument("--output", type=Path)
    naming = commands.add_parser("validate-naming")
    naming.add_argument("--root", type=Path, default=Path.cwd())

    sources = commands.add_parser("sources")
    source_commands = sources.add_subparsers(dest="source_command", required=True)
    source_commands.add_parser("list")
    source_description = source_commands.add_parser("describe")
    source_description.add_argument("source_id")
    source_verification = source_commands.add_parser("verify")
    source_verification.add_argument("--live", action="store_true")
    source_verification.add_argument("--local-root", type=Path)

    lock = commands.add_parser("lock")
    lock_commands = lock.add_subparsers(dest="lock_command", required=True)
    compute = lock_commands.add_parser("compute")
    compute.add_argument("input", type=Path)
    compute.add_argument("--output", type=Path)
    verify = lock_commands.add_parser("verify")
    verify.add_argument("input", type=Path)
    return parser


def _load_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("lock input must be a JSON object with string keys")
    typed_value = cast(dict[object, object], value)
    if not all(isinstance(key, str) for key in typed_value):
        raise ValueError("lock input must be a JSON object with string keys")
    return cast(dict[str, object], typed_value)


def _print_errors(errors: Sequence[str]) -> int:
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("validation passed")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "benchmarks" and args.benchmark_command == "list":
        for benchmark in default_registry().discover(args.family):
            task = benchmark.task
            print(
                f"{benchmark.identity.scientific_id}\t"
                f"{task.execution_status.value}\t{task.scientific_maturity.value}"
            )
        return 0
    if args.command == "benchmarks" and args.benchmark_command == "describe":
        benchmark = default_registry().lookup(args.scientific_id)
        print(json.dumps(asdict(benchmark), indent=2, sort_keys=True))
        return 0
    if args.command == "families" and args.family_command == "list":
        print("\n".join(family.family_id for family in default_registry().families()))
        return 0
    if args.command == "families" and args.family_command == "describe":
        family = default_registry().lookup_family(args.family_id)
        print(json.dumps(asdict(family), indent=2, sort_keys=True))
        return 0
    if args.command == "research-objects" and args.research_object_command == "list":
        for research_object in default_registry().research_objects():
            descriptor = research_object.descriptor
            print(
                f"{research_object.identity.scientific_id}\t"
                f"{descriptor.research_object_type.value}\t"
                f"{descriptor.scientific_maturity.value}"
            )
        return 0
    if args.command == "research-objects" and args.research_object_command == "describe":
        registry = default_registry()
        if args.scientific_id in registry.family_ids():
            print(
                f"{args.scientific_id} is a research family; use 'families describe'.",
                file=sys.stderr,
            )
            return 2
        research_object = registry.lookup_research_object(args.scientific_id)
        print(json.dumps(asdict(research_object), indent=2, sort_keys=True))
        return 0
    if args.command == "validate":
        return _print_errors(validate_repository(args.root))
    if args.command == "evidence" and args.evidence_command == "validate":
        report = validate_evidence_inventory(args.registry_root)
        if args.registry_root is None:
            if report.errors:
                return _print_errors(report.errors)
            print(
                "evidence reference shape passed "
                f"({report.reference_count} references / {report.unique_digests} digests; "
                f"{report.legacy_alias_count} legacy aliases retained)"
            )
            return 0
        print(json.dumps(asdict(report), indent=2, sort_keys=True))
        return 1 if report.errors else 0
    if args.command == "reproducibility" and args.reproducibility_command == "check":
        root = Path.cwd()
        errors = check_reproducibility(root)
        if errors:
            return _print_errors(errors)
        print(
            json.dumps(
                {
                    "status": "passed",
                    "snapshot_sha256": snapshot_sha256(root),
                    "capabilities": dict(CAPABILITY_MATRIX),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "reproducibility" and args.reproducibility_command == "snapshot":
        snapshot_bytes = render_reproducibility_snapshot(Path.cwd())
        if args.output is None:
            sys.stdout.buffer.write(snapshot_bytes)
        else:
            args.output.write_bytes(snapshot_bytes)
            print(snapshot_sha256(Path.cwd()))
        return 0
    if args.command == "validate-naming":
        return _print_errors(validate_naming(args.root))
    if args.command == "sources" and args.source_command == "list":
        print("skillcorner_open_data_v1")
        return 0
    if args.command == "sources" and args.source_command == "describe":
        if args.source_id != "skillcorner_open_data_v1":
            print(f"unknown source: {args.source_id}", file=sys.stderr)
            return 2
        print(json.dumps(load_manifest(), indent=2, sort_keys=True))
        return 0
    if args.command == "sources" and args.source_command == "verify":
        try:
            manifest = load_manifest()
            errors = list(validate_manifest(manifest))
            live_report = verify_live(manifest) if args.live and not errors else None
            if live_report is not None:
                errors.extend(cast(list[str], live_report["errors"]))
            local_errors = (
                verify_local_checkout(manifest, args.local_root)
                if args.local_root is not None and not errors
                else ()
            )
            errors.extend(local_errors)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            return _print_errors((f"source authority verification failed: {exc}",))
        if errors:
            if live_report is not None:
                print(json.dumps(live_report, indent=2, sort_keys=True))
            return _print_errors(errors)
        report = {
            "status": "passed",
            "source_id": manifest["source_id"],
            "source_release_id": manifest["source_release_id"],
            "source_population_hash": manifest["source_population_hash"],
            "manifest_sha256": manifest["manifest_sha256"],
            "live": live_report,
            "local_checkout": str(args.local_root) if args.local_root is not None else None,
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if args.command == "lock" and args.lock_command == "compute":
        lock = build_scientific_lock(_load_object(args.input))
        rendered = json.dumps(lock, indent=2, sort_keys=True) + "\n"
        if args.output is None:
            print(rendered, end="")
        else:
            args.output.write_text(rendered)
            print(lock["scientific_lock_hash"])
        return 0
    if args.command == "lock" and args.lock_command == "verify":
        valid = verify_scientific_lock(_load_object(args.input))
        print("scientific lock valid" if valid else "scientific lock invalid")
        return 0 if valid else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
