"""Explicit public-data research reconciliation; never protected qualification.

Run from the repository with PYTHONPATH=src. All row artifacts stay in a fresh
private run directory; the protected APIs, receipts and gates remain unchanged.
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures
import dataclasses
import hashlib
import importlib.metadata
import json
import os
import platform
import resource
import shutil
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import cast

SCHEMA = "fpdbench.public-skillcorner-research-admission"
VERSION = "1.0.0"
RESERVE = 32 * 1024**3
REPO = Path(__file__).resolve().parents[1]


def canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


def digest(path: Path) -> str:
    h = hashlib.sha256()
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError("content identity requires an exclusive regular file")
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
        after = os.fstat(stream.fileno())
        if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise ValueError("file changed while computing content identity")
    return h.hexdigest()


def write(path: Path, value: object) -> None:
    with path.open("xb") as stream:
        stream.write(canonical(value))
        stream.flush()
        os.fsync(stream.fileno())


def code_inventory() -> dict:
    paths = sorted((REPO / "src/fpdbench").rglob("*"))
    paths += [
        Path(__file__),
        REPO / "tools/research_population_verifier_v1.py",
        REPO / "docs/research-population-admission-v1.md",
    ]
    return {
        p.relative_to(REPO).as_posix(): digest(p)
        for p in paths
        if p.is_file() and p.suffix in {".py", ".json", ".md"}
    }


def resource_estimate(census: dict, free: int) -> dict:
    """128 KiB/row allows >10x the largest archived synthetic diagnostic row."""
    totals = census["total"]["C"]
    rows = totals["theoretical"] + totals["scoreable_scenes"]
    estimated = 2 * rows * 128 * 1024 + 8 * 1024**3
    if free < estimated + RESERVE:
        raise ValueError(f"insufficient disk: need {estimated + RESERVE}, available {free}")
    return {
        "estimated_peak_bytes": estimated,
        "reserve_bytes": RESERVE,
        "available_bytes": free,
        "row_allowance_bytes": 128 * 1024,
        "memory_limit_per_worker_bytes": 2 * 1024**3,
        "basis": "census rows + scenes, fixture max diagnostic 12571 / truth 6213 bytes",
    }


def training_validation_resource_estimate(reference: dict, free: int) -> dict:
    source_files = cast(list[dict[str, object]], reference["source_manifest"])
    inputs = sum(
        int(row.get("lfs_payload_size", row["byte_size"]))
        for row in source_files
        if str(row["repository_path"]).endswith(
            ("_tracking_extrapolated.jsonl", "_match.json", "_phases_of_play.csv")
        )
    )
    population = 2 * sum(
        int(item["bytes"])
        for item in cast(dict[str, dict[str, object]], reference["artifacts"]).values()
    )
    reserve = 8 * 1024**3
    estimated = inputs + population
    if free < estimated + reserve:
        raise ValueError(f"insufficient Colab disk: need {estimated + reserve}, available {free}")
    return {
        "estimated_peak_bytes": estimated,
        "reserve_bytes": reserve,
        "available_bytes": free,
        "source_input_bytes": inputs,
        "independent_population_outputs_bytes": population,
        "basis": (
            "pinned training/validation source sizes and both frozen reconciliation output sizes"
        ),
    }


def produce(inputs: Path, match: str, output: Path) -> dict:
    from fpdbench.benchmarks.conditional_multi_agent_motion_prediction import (
        streaming_population_producer_v1 as p,
    )
    from fpdbench.data_sources import protected_skillcorner as source
    from fpdbench.data_states.skillcorner import iter_skillcorner_5hz_v2
    from fpdbench.eligibility.skillcorner import (
        PhaseInterval,
        diagnose_skillcorner_window_v2,
        load_manifest_v2,
        skillcorner_period_ranges,
    )

    metadata = json.loads((inputs / match / "metadata.json").read_bytes())
    authority = source._authority()
    release = authority["source_release_id"]
    phases = tuple(
        PhaseInterval(release, int(match), **row)
        for row in json.loads((inputs / match / "phases.json").read_bytes())
    )
    bounds, errors = skillcorner_period_ranges(metadata)
    if errors:
        raise ValueError("invalid period metadata")
    role = next(role for role, mid in p._roles() if mid == match)
    counts, stats = {}, {}
    retained = 0
    policy = load_manifest_v2()
    h = hashlib.sha256()
    partial = output.with_suffix(".partial")
    with source.private_directory(inputs / match) as fd, partial.open("xb") as stream:

        def samples():
            nonlocal retained
            for sample in iter_skillcorner_5hz_v2(
                source._rows(fd, "tracking.jsonl", stats), metadata, source_release_id=release
            ):
                retained += 1
                ball = sample["ball"]
                if (
                    ball
                    and ball["is_detected"] is None
                    and ball["x_m"] is not None
                    and ball["y_m"] is not None
                ):
                    raise ValueError("BALL_NULL_FLAG_WITH_FINITE_XY_UNAPPROVED")
                yield sample

        for (period, frame, origin), support in p._population_events(samples(), bounds):
            complete = all(s is not None for s in support)
            diagnostic = diagnose_skillcorner_window_v2(
                support,
                history_intervals=25,
                future_intervals=15,
                match_metadata=metadata,
                phase_intervals=phases,
                policy_manifest=policy,
            )
            scenes = []
            passing = complete and diagnostic.candidate_rules_pass
            window = p.prospective_window_id_v2(match, origin) if passing else None
            if passing:
                for side in ("home", "away"):
                    _, truth, _ = p._scene(support, side)
                    scenes.append(truth)
            row = {
                "match_id": match,
                "role": role,
                "period": period,
                "source_frame": frame,
                "origin_sample_id": origin,
                "complete_support": complete,
                "diagnostic": dataclasses.asdict(diagnostic),
                "window_id": window,
                "scenes": scenes,
            }
            payload = canonical(row) + b"\n"
            stream.write(payload)
            h.update(payload)
            c = counts.setdefault(
                str(period),
                {
                    "theoretical": 0,
                    "complete_support": 0,
                    "rules_pass": 0,
                    "scoreable_windows": 0,
                    "home_scenes": 0,
                    "away_scenes": 0,
                },
            )
            c["theoretical"] += 1
            c["complete_support"] += complete
            c["rules_pass"] += passing
            c["scoreable_windows"] += any(s["scoreable"] for s in scenes)
            for s in scenes:
                c[s["scene_id"] + "_scenes"] += s["scoreable"]
        stream.flush()
        os.fsync(stream.fileno())
    if retained != stats["even_source_rows"]:
        raise ValueError("retained frame coverage differs")
    for period, (start, end) in bounds.items():
        if counts[str(period)]["theoretical"] != len(range(start + start % 2, end, 2)):
            raise ValueError("theoretical origin coverage differs")
    os.replace(partial, output)
    return {
        "match_id": match,
        "role": role,
        "periods": counts,
        "artifact_sha256": h.hexdigest(),
        "tracking_sha256": stats["tracking_sha256"],
        "source_rows": stats["source_rows"],
        "retained_samples": retained,
    }


def launch(command: list[str], log: Path, run: Path, abort=None) -> None:
    if abort is not None and abort.is_set():
        raise ValueError("research phase cancelled")
    with log.open("xb") as stream:
        process = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT)
        try:
            while process.poll() is None:
                if abort is not None and abort.is_set():
                    raise ValueError("research phase cancelled")
                if shutil.disk_usage(run).free < RESERVE:
                    raise ValueError("disk reserve reached; partial research artifacts retained")
                time.sleep(1)
            if process.returncode:
                raise ValueError(f"research subprocess failed; private log: {log.name}")
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=30)


def reconcile(producer: Path, verifier: Path, matches: list[str], expected_hashes: dict) -> dict:
    """Require independent byte identity, source identity and all summary counts."""
    per_match, roles = {}, {}
    total = collections.Counter()
    artifacts = {}
    names = {f"{mid}{suffix}" for mid in matches for suffix in (".jsonl", ".summary.json")}
    if {p.name for p in producer.iterdir()} != names or {
        p.name for p in verifier.iterdir()
    } != names:
        raise ValueError("missing or unexpected research artifact")
    for mid in matches:
        a = json.loads((producer / f"{mid}.summary.json").read_bytes())
        b = json.loads((verifier / f"{mid}.summary.json").read_bytes())
        for root, summary in ((producer, a), (verifier, b)):
            actual = digest(root / f"{mid}.jsonl")
            if actual != summary["artifact_sha256"]:
                raise ValueError(f"artifact changed for match {mid}")
        if a != b or a["tracking_sha256"] != expected_hashes[mid]:
            raise ValueError(f"independent scientific reconciliation differs for match {mid}")
        c = collections.Counter()
        for period in a["periods"].values():
            c.update(period)
        if not (
            c["scoreable_windows"] <= c["rules_pass"] <= c["complete_support"] <= c["theoretical"]
            and c["home_scenes"] + c["away_scenes"] <= 2 * c["rules_pass"]
        ):
            raise ValueError("inconsistent research counts")
        if not c["scoreable_windows"]:
            raise ValueError(f"match {mid} has no scoreable window")
        per_match[mid] = {"role": a["role"], "periods": a["periods"], "counts": dict(c)}
        roles.setdefault(a["role"], collections.Counter()).update(c)
        total.update(c)
        artifacts[mid] = {
            "producer_sha256": a["artifact_sha256"],
            "verifier_sha256": b["artifact_sha256"],
            "producer_summary_sha256": digest(producer / f"{mid}.summary.json"),
            "verifier_summary_sha256": digest(verifier / f"{mid}.summary.json"),
            "bytes": (producer / f"{mid}.jsonl").stat().st_size,
        }
    return {
        "per_match": per_match,
        "roles": {k: dict(v) for k, v in roles.items()},
        "total": dict(total),
        "artifacts": artifacts,
    }


def run(
    source: Path,
    output: Path,
    census: Path | None,
    *,
    scope: str = "full",
    reference_path: Path | None = None,
    reference_sha256: str | None = None,
) -> None:
    from fpdbench.data_sources import protected_skillcorner as p
    from fpdbench.data_sources.phase_normalization_c import normalize_phases_c

    if scope not in {"full", "training-validation"}:
        raise ValueError("unknown research population scope")
    reference = json.loads(reference_path.read_bytes()) if reference_path else None
    if scope == "training-validation" and not isinstance(reference, dict):
        raise ValueError("training-validation execution requires its frozen reference manifest")
    if scope == "full" and reference_path is not None:
        raise ValueError("a scoped reference manifest is only valid for training-validation")
    if scope == "training-validation" and (
        reference_sha256 is None
        or hashlib.sha256(reference_path.read_bytes()).hexdigest() != reference_sha256
    ):
        raise ValueError("training-validation reference SHA-256 differs")
    with p.private_directory(output.parent):
        output.mkdir(mode=0o700)
    if scope == "full":
        if census is None:
            raise ValueError("full-population reconciliation requires its census")
        resource_census = json.loads(census.read_bytes())
        authority = p._authority()
        matches = [str(match) for match in authority["selected_source_matches"]]
        role_counts_expected = {"training": 12, "validation": 4, "evaluation": 4}
        records = p._records(authority)
    else:
        assert isinstance(reference, dict)
        if (
            reference.get("schema_id") != "fpdbench.res338.training-validation-reference"
            or reference.get("parent_research_manifest_sha256")
            != "a8c82bfa09ac792d6c4ae779d4b28158c33ed3c2500f8548f3e94d48197f4fd1"
        ):
            raise ValueError(
                "training-validation reference is not bound to the ratified population"
            )
        authority = p._authority()
        if reference.get("source_commit") != authority["upstream"]["pinned_commit"]:
            raise ValueError("training-validation source commit differs from the pinned release")
        roles_in_source = {str(match): role for role, match in p._roles()}
        reference_roles = cast(dict[str, list[str]], reference["roles"])
        role_counts_expected = {"training": 12, "validation": 4}
        if reference_roles != {
            role: sorted(mid for mid, actual in roles_in_source.items() if actual == role)
            for role in role_counts_expected
        }:
            raise ValueError("training-validation roles differ from the frozen v2 split")
        matches = cast(list[str], reference["source_match_order"])
        expected_matches = {
            match for role in role_counts_expected for match in reference_roles[role]
        }
        if len(matches) != 16 or set(matches) != expected_matches:
            raise ValueError("training-validation source scope contains missing or extra matches")
        records = [
            record
            for record in p._records(authority)
            if any(
                str(record["repository_path"]).startswith(f"data/matches/{mid}/") for mid in matches
            )
        ]
        if len(records) != 64 or any(
            str(record["repository_path"]) == "data/matches.json" for record in records
        ):
            raise ValueError("training-validation source scope must contain exactly 64 match files")
        if {
            str(row["repository_path"])
            for row in cast(list[dict[str, object]], reference["source_manifest"])
        } != {str(record["repository_path"]) for record in records}:
            raise ValueError("projected source manifest differs from the pinned authority")
    if scope == "full":
        estimate = resource_estimate(
            cast(dict[str, object], resource_census), shutil.disk_usage(output).free
        )
    else:
        assert isinstance(reference, dict)
        estimate = training_validation_resource_estimate(reference, shutil.disk_usage(output).free)
    write(output / "resource-estimate.json", estimate)
    inventory = code_inventory()
    environment = {
        "python": sys.version,
        "executable": str(Path(sys.executable).resolve()),
        "executable_sha256": digest(Path(sys.executable).resolve()),
        "platform": platform.platform(),
        "dependencies": sorted(
            (d.metadata["Name"], d.version) for d in importlib.metadata.distributions()
        ),
        "commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
        ).strip(),
        "code_inventory": inventory,
    }
    write(output / "environment.json", environment)
    inputs, normalization = output / "inputs", output / "normalization"
    inputs.mkdir(mode=0o700)
    normalization.mkdir(mode=0o700)
    with p.private_directory(source) as fd:
        before = p._verify_sources(fd, records)
        for match in matches:
            directory = inputs / str(match)
            directory.mkdir(mode=0o700)
            prefix = f"data/matches/{match}/{match}"
            metadata = p._document(fd, prefix + "_match.json")
            phases, lineage, _ = normalize_phases_c(
                p._document(fd, prefix + "_phases_of_play.csv"), metadata
            )
            (directory / "metadata.json").write_bytes(metadata)
            (directory / "phases.json").write_bytes(phases)
            (normalization / f"{match}-lineage.json").write_bytes(lineage)
            with p._open_file(fd, prefix + "_tracking_extrapolated.jsonl") as src:
                with (directory / "tracking.jsonl").open("xb") as dst:
                    shutil.copyfileobj(src, dst, length=1024 * 1024)
    write(output / "source-inventory.json", before)
    if scope == "training-validation" and before != reference["source_files"]:
        raise ValueError("downloaded sources differ from the frozen training-validation identity")
    logs = output / "logs"
    logs.mkdir(mode=0o700)
    verifier_tool = REPO / "tools/research_population_verifier_v1.py"
    for phase in ("producer", "verifier"):
        destination = output / phase
        destination.mkdir(mode=0o700)
        if phase == "verifier":
            check_command = [
                sys.executable,
                str(verifier_tool),
                "check-source",
                str(source),
                str(inputs),
                str(normalization),
                str(output / "independent-source.json"),
            ]
            if scope != "full":
                check_command.extend(["--scope", scope])
            launch(
                check_command,
                logs / "independent-source.log",
                output,
            )
        abort = threading.Event()

        def worker(mid, phase=phase, destination=destination, abort=abort):
            command = (
                [sys.executable, str(Path(__file__)), "produce"]
                if phase == "producer"
                else [sys.executable, str(verifier_tool), "derive"]
            )
            command += [str(inputs), mid, str(destination / f"{mid}.jsonl")]
            if scope != "full" and phase == "verifier":
                command += ["--scope", scope]
            try:
                launch(command, logs / f"{phase}-{mid}.log", output, abort)
            except Exception:
                abort.set()
                raise
            print(phase, "MATCH_COMPLETE", mid, flush=True)

        with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 1)) as pool:
            list(pool.map(worker, matches))
        if code_inventory() != inventory:
            raise ValueError("research code changed during execution")
    selected_matches = set(matches)
    expected = {
        str(m["match_id"]): next(r["lfs_oid_sha256"] for r in m["files"] if "lfs_oid_sha256" in r)
        for m in authority["available_matches"]
        if str(m["match_id"]) in selected_matches
    }
    result = reconcile(output / "producer", output / "verifier", matches, expected)
    role_counts = collections.Counter(v["role"] for v in result["per_match"].values())
    if role_counts != role_counts_expected:
        raise ValueError("frozen role coverage differs")
    if scope == "training-validation":
        if (
            result["per_match"] != reference["per_match"]
            or result["artifacts"] != reference["artifacts"]
        ):
            raise ValueError("Colab research outputs differ from the ratified 16-match projection")
        independent = json.loads((output / "independent-source.json").read_bytes())
        expected_independent = cast(dict[str, object], reference["independent_source"])
        if independent.get("source_files") != expected_independent.get("source_files") or sorted(
            independent.get("normalization_receipts", []), key=lambda item: item["match_id"]
        ) != sorted(
            expected_independent.get("normalization_receipts", []),
            key=lambda item: item["match_id"],
        ):
            raise ValueError(
                "independent source and phase normalization differ from the projection"
            )
    with p.private_directory(source) as fd:
        if p._verify_sources(fd, records) != before:
            raise ValueError("source changed during research reconciliation")
    if code_inventory() != inventory:
        raise ValueError("code changed during final checks")
    result.update(
        schema_id=SCHEMA,
        schema_version=VERSION,
        status="RESEARCH_RECONCILED",
        admission="RESEARCH_ADMISSION_PENDING_OWNER_APPROVAL",
        protected_status="NOT_QUALIFIED",
        source_release_hash=authority["source_release_hash"],
        source_population_hash=authority["source_population_hash"],
        environment_sha256=digest(output / "environment.json"),
        source_inventory_sha256=digest(output / "source-inventory.json"),
        independent_source_sha256=digest(output / "independent-source.json"),
        empirical_execution="BLOCKED_PENDING_OWNER_RATIFICATION",
    )
    if scope == "training-validation":
        result["execution_scope"] = scope
        result["parent_research_manifest_sha256"] = reference["parent_research_manifest_sha256"]
        result["source_match_order"] = matches
    write(output / "research-admission.json", result)
    print("RESEARCH_RECONCILED", canonical(result["total"]).decode(), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    whole = modes.add_parser("run")
    whole.add_argument("source", type=Path)
    whole.add_argument("output", type=Path)
    whole.add_argument("census", type=Path, nargs="?")
    whole.add_argument("--scope", choices=("full", "training-validation"), default="full")
    whole.add_argument("--reference", type=Path)
    whole.add_argument("--reference-sha256")
    worker = modes.add_parser("produce")
    worker.add_argument("inputs", type=Path)
    worker.add_argument("match")
    worker.add_argument("output", type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    if args.mode == "produce":
        result = produce(args.inputs, args.match, args.output)
        write(args.output.with_suffix(".summary.json"), result)
    else:
        try:
            run(
                args.source,
                args.output,
                args.census,
                scope=args.scope,
                reference_path=args.reference,
                reference_sha256=args.reference_sha256,
            )
        except Exception as error:
            if args.output.is_dir() and not (args.output / "research-admission.json").exists():
                write(
                    args.output / "failure.json",
                    {
                        "schema_id": SCHEMA,
                        "schema_version": VERSION,
                        "status": "RESEARCH_RECONCILIATION_FAILED",
                        "error": str(error),
                    },
                )
            raise


if __name__ == "__main__":
    main()
