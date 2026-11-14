# RES646 synthetic resource qualification

Every input is invented: artificial sources and DeepSets checkpoints, ephemeral synthetic signing
keys, and a synthetic-only ledger. No real source/tensor bytes, production key, GO, or execution
scope were used. Exact source hashes, runtime, four receipt seals and aggregate identity are in
`docs/res646-synthetic-resource-report.json`. The final-code run used source commit
`29e519104246866ed66f98a4c2fab1b26405e073` and the qualification-tool hash recorded in that report.
Later documentation/tool commits preserve these exact execution-path hashes.

Runtime: Python 3.12.8, NumPy 2.2.4, PyTorch 2.6.0+cpu, CPU only, one thread, no paid compute.
The complete signed campaign ran through the existing detached supervisor, including launcher,
setup, source identity/decoding, model loading, one prediction pass, independent audit, receipt
sealing, ledger operations, aggregation, final verification and post-accounting completion signal.
Fixture generation is excluded. Final verification used four receipts, 18 cells each, 72 total
records, the frozen ADE/FDE/scalar-coordinate XY RMSE, and four C1/C2 contrasts.

## Direct observations

| code generation | eligible windows | CPU s | wall s | peak combined RSS | transient disk |
|---|---:|---:|---:|---:|---:|
| historical | 80 | 21.1 | 22.4 | 435 MiB | 174 KB |
| historical | 800 | 90.2 | 93.0 | 436 MiB | 183 KB |
| historical | 4,000 | 437.4 | 449.7 | 437 MiB | 226 KB |
| intermediate remediation | 800 | 178.060 | 181.681 | 436.4 MiB | 191,361 bytes |
| scoring-scope remediation | 800 | 127.223 | 125.364 | 436.8 MiB | 187,233 bytes |
| final implementation | 800 | 115.987 | 114.954 | 436.6 MiB | 186,048 bytes |

The historical measurements predate the final supervisor status-ordering repair and these P1
repairs. They are preserved with their original code/runtime metadata under `prior_qualification`;
they do not qualify the current implementation. The intermediate and final observations are slower than the old
800-window result. All three remediation runs have an identical aggregate hash, which confirms unchanged synthetic scientific results. This run alone does not identify the cause or separate fixed setup overhead
from marginal per-window cost. No causal performance improvement or regression is asserted.

## Linear estimates and sensitivity scenarios

For the admitted 51,713 windows (~930,834 forward calls), zero-intercept scaling of the final
800-window observation gives the following. Scaling fixed overhead with every window can overstate
cost; real-source density and decode cost can also increase it. Neither effect was measured.

| quantity | frozen ceiling | linear estimate | 2x sensitivity scenario |
|---|---:|---:|---:|
| cumulative CPU | 14,400 s | 7,498 s (52%) | 14,995 s (104%) |
| cumulative wall | 21,600 s | 7,431 s (34%) | 14,861 s (69%) |
| combined RSS | 2 GiB | observed 436.6 MiB | real-data scaling unverified |
| transient disk | 2 GiB | observed 186,048 bytes | real-data scaling unverified |

The doubled cost is a sensitivity scenario, **not a proven worst-case upper bound**. It exceeds
the cumulative CPU ceiling on the final observation; its wall estimate fits. The linear estimate fits, but that
does not establish real-scale qualification. The preflight records this uncertainty and fails
closed when the required resource evidence/scenario does not qualify. No frozen budget changed.

## Remaining qualification

The final synthetic campaign passed scientifically and structurally. Real-source performance,
actual applicable quotas, and unchanged-byte evidence for the recovered private readback remain
unqualified. Current cgroup limits and filesystem capacity were observed in the owner-private
report; host free space alone does not establish a quota. A resource limit remains a permanent
terminal failure of the one-shot scope. No real execution is authorized by these measurements.
