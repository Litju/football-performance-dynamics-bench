"""Command-line interface for benchmark discovery and reproducibility checks."""

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import cast

from fpdbench.benchmarks.registry import default_registry
from fpdbench.provenance.scientific_lock import build_scientific_lock, verify_scientific_lock
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

    validation = commands.add_parser("validate")
    validation.add_argument("--root", type=Path, default=Path.cwd())
    naming = commands.add_parser("validate-naming")
    naming.add_argument("--root", type=Path, default=Path.cwd())

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
    if args.command == "validate":
        return _print_errors(validate_repository(args.root))
    if args.command == "validate-naming":
        return _print_errors(validate_naming(args.root))
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
