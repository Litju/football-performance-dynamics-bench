# Synthetic pre-import streaming runtime attestation

State: **synthetic-only, runtime gate BLOCKED, qualification NOT_PERFORMED**.
This continues the unified integration at
`ab37fd1aad44dca844d94b362bc3fdf104411b64`; the completed PR #26 repairs and
independent scoped review were not repeated. Git inspection found that exact
clean integration head, with no uncommitted runtime-attestation implementation.
The existing receipts and reports explicitly marked executable-runtime
attestation NOT_PROVIDED. No separate session-progress file was present.

`tools/attest_streaming_runtime.py` is a standalone Linux launcher. It does not
import the benchmark package before checking the runtime manifest. Existing
producer/verifier modules, source identities, scientific authorities, receipts,
and qualification behavior are unchanged. Its evidence is separate from worker
receipts: it never upgrades them or authenticates an earlier producer run.

## Executable contract

Capture and execution both require Python `-I -S -B -X pycache_prefix=/dev/null`.
`-B` alone prevents cache writes but still permits reads; the prefix under the
Linux `/dev/null` regular device prevents normal prefixed cache reads too.
The launcher admits only PATH, LANG, LC_ALL, LC_CTYPE and TZ environment names;
values are pinned. Python can itself add LC_CTYPE during locale coercion. Use an
empty environment for both invocations. Shells, site processing, user site,
PYTHONPATH, `.pth` processing and third-party distribution imports are not part
of the supported worker launch path.

The captured canonical manifest records:

- Invoked and resolved interpreter paths, executable SHA-256, Python version,
  implementation, ABI/cache tag, prefixes, flags and extended options. The
  resolved executable must identify the running `/proc/self/exe` inode.
- Launcher bytes, complete package inventory, standard-library inventory and
  native extension inventory. Directory traversal and regular-file reads reject
  symlinks; files must remain stable while read. Cache directories are excluded,
  and sourceless bytecode elsewhere fails closed. Package additions and frozen
  JSON changes invalidate the manifest.
- Startup and resolved import paths, bootstrap-module origins, working directory,
  kernel release/version/architecture, permitted environment values, loader
  cache/preload files when present, and hashes of file-backed process mappings.
  Deleted mappings and unidentified executable mappings fail closed.
- An empty third-party dependency set. These two workers declare no third-party
  runtime dependencies. Site-package directories are excluded and cannot be
  imported by the installed finder; this is not a dependency resolver or a
  general-purpose launcher for packages with external dependencies.

Execution requires a separately supplied canonical manifest digest, compares
the full observed runtime before worker import, and records the request digest.
A source loader rehashes each imported Python file immediately before compiling
those exact bytes. It does not deserialize cached bytecode. Package resources
read through the loader are also checked before use. The import finder admits
only inventoried source/native-extension origins, builtins and interpreter
frozen modules. The independent verifier is loaded directly from its verified
module source, without executing benchmark package initializers or importing the
producer. The producer uses its existing package imports.

After a worker returns, the launcher repeats the runtime inventory and mapping
checks. A mismatch or worker error produces REJECTED evidence and a nonzero
launcher exit. Evidence contains whether import/execution began. Only a completed
consistent launch produces SYNTHETIC_RUNTIME_CONSISTENT, which always retains
runtime gate BLOCKED and qualification NOT_PERFORMED. A verifier MISMATCH remains
its worker status; runtime consistency does not imply scientific reconciliation.
Manifest and evidence files are exclusively created with mode 0600 and fsynced;
existing files cannot be overwritten. They are local synthetic records, not
signed or protected-storage receipts.

## Synthetic invocation

From this repository, use new absolute manifest/evidence paths in a private
synthetic directory. The launcher path and environment must be the same in both
calls; capture prints the canonical manifest digest.

```sh
env -i .venv/bin/python -I -S -B -X pycache_prefix=/dev/null \
  tools/attest_streaming_runtime.py capture \
  --package-root "$PWD/src/fpdbench" --manifest /absolute/synthetic/runtime.json

env -i .venv/bin/python -I -S -B -X pycache_prefix=/dev/null \
  tools/attest_streaming_runtime.py run \
  --package-root "$PWD/src/fpdbench" --manifest /absolute/synthetic/runtime.json \
  --expected-sha256 CANONICAL_DIGEST_FROM_CAPTURE --worker verifier \
  --request /absolute/synthetic/request.json --evidence /absolute/synthetic/evidence.json
```

The verifier request contains `input_root`, `artifact_root`,
`producer_package_root`, and `report`, all absolute paths to synthetic material.
The producer request contains `output_directory` and an `inputs` array of
objects with `match_id`, `metadata_path`, `tracking_jsonl_path`, and
`phase_intervals_path`. Producer output restrictions still apply, including a
new private output directory outside Git. No input-kind assertion in this
launcher authenticates data rights: pass only public synthetic fixtures.

## Security evidence and production blockers

The integration tests run the real integrated producer and verifier against the
pinned complete 20-match synthetic fixture. They compare all four scientific
producer artifacts byte for byte and require non-authoritative verifier
reconciliation. A valid timestamp/size-matching poisoned cache must not execute.
Negative cases cover interpreter/native/dependency inventory forgery, changed
source/initializers/resources, added files, symlinks, sourceless bytecode,
environment injection, manifest-pin substitution, imports outside the inventory,
source mutation between verification and import, post-execution mutation, and
worker failure. Production qualification remains blocked in every case.

These are **consistency checks under an explicitly trusted bootstrap**, not a
self-established root of trust. Python, the dynamic loader and bootstrap imports
already execute before a Python launcher can hash them. A hostile interpreter,
process-memory writer, privileged host, or swapped native library can falsify
self-observation. Hashes of mapped backing files do not attest resident memory.
Native extension verification followed by the platform loader also has a path
race; final checks detect persistent changes, not transient swap-and-restore
attacks. Direct worker filesystem reads have the same transient-mutation limit.
Kernel identity strings are recorded provenance, not kernel authenticity.

Before any separately authorized production execution, remaining work is:

1. Independently review this new launcher and its execution contract. The completed
   PR #26 review does not cover this change.
2. Establish an external verified bootstrap and immutable executable closure
   (interpreter, standard library, native libraries, launcher and package), with
   host/mount enforcement that prevents concurrent replacement. Validate the
   closure before process startup, including native-loader configuration.
3. Bind separately approved producer and verifier runtime manifests and their
   launch/output evidence into an externally root-signed policy and independent
   reviewer process. Caller-supplied digests and newly captured local manifests
   cannot supply production authority or authenticate an earlier run.
4. Provision production trust material outside the repository only under separate
   authorization, and finish protected-source authentication, trusted storage,
   immutable input handoff, real-data capacity evidence and qualification review.

No production key was provisioned, protected SkillCorner input accessed,
integration branch pushed, or empirical gate enabled.

## Validation record

Implementation commit: `4e8a3e25f1b6bfe9dca25ad74d9671fa19709e98`, on the existing
integration branch, directly after the completed unified
integration. The follow-up documentation commit records validation only.
Validation used Linux and CPython 3.12.13; no new dependency was installed.

The final focused command was:

```sh
.venv/bin/pytest -q tests/integration/test_streaming_runtime_attestation.py
```

It passed **23 tests**, with no skips, including a native-mapping change using
the host's system libuuid. The poisoned-cache test includes a positive control
showing that ordinary Python executes the poisoned cache before the attested
launcher successfully ignores it. A mutation-probe setup error encountered
during development was corrected before the final targeted validation.

Ruff checking, Ruff formatting (129 Python files), strict Pyright (zero errors),
repository and naming validation, evidence validation (232 references / 63
digests), and public reproducibility checking passed. The public snapshot remains
`a22f93f11cf428b7f326a93714fbcc798c99e5d0dbcab5122edb48d050b4a873`.
`git diff --exit-code ab37fd1aad44dca844d94b362bc3fdf104411b64 -- src benchmarks`
passed: all package code and frozen scientific authorities remain byte-identical.
Wheel/sdist smoke was not repeated because package code and packaging
configuration did not change; the launcher is a separately controlled repository
tool, not a new wheel entry point.

The original full run completed both unchanged resource-scaling checks
successfully. It reported 617 passed and two failures: the development probe
setup error noted above, and a branch-name literal added to these notes that
violated the repository's structured-provenance naming rule. Both were fixed.
The clean regression rerun reused the two successful expensive scaling checks:

```sh
FPDBENCH_PR25_PACKAGE_ROOT="$PWD/.pytest_cache/pr25-source/src/fpdbench" \
  .venv/bin/pytest -q \
  --deselect tests/integration/test_streaming_population_verifier_v1.py::test_source_and_artifact_scaling_keeps_worker_memory_bounded \
  --deselect tests/unit/test_streaming_population_producer_v1.py::test_separate_worker_memory_stays_bounded_at_10x_input_scale
```

That package root was extracted with `git archive` from the existing local
`aad8888eb6c7c046e4dfbce866886bf2ec8dd123` commit. It is an ignored synthetic
fixture copy, not a new branch or worktree. No fetch, checkout or push was used.

The clean rerun passed **618 tests, 2 deselected in 333.91 seconds**, including
all 23 final attestation tests. Together with the two previously successful
unchanged scaling checks, all **620 current test cases** have successful coverage.
No production qualification is implied. Final repository/naming validation,
whitespace checks, and the unchanged-source/authority comparison also passed.
