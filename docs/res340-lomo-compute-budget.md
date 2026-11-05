# RES340 LOMO resource estimate

**Purpose:** preparation estimate only. No RES340 fit or held-out score has run.
All values below use the existing 18 verified RES338 receipts, progress ledger,
cache archive/readback records, and read-only Colab CLI observations.

## Verified RES338 runtime

The 18 raw Drive receipts and 18 selected checkpoints were read back and hashed.
All receipt and checkpoint file hashes match their content-addressed filenames;
each checkpoint hash matches its receipt. All 18 receipts are `completed`, use the
frozen plan/protocol/research population, and bind 12 optimization matches plus the
four validation matches. The latest progress index records 18 of 18 fits as
`COMPLETED_AND_VERIFIED`, with 18 checkpoint/receipt readbacks.

The GPU fit time from the receipts is **11,304.443444 seconds**. Model input and
target representation were unchanged, so the initial projection scales the
measured regime totals by 12 folds. Fewer training matches do not reduce per-step
batch cost because every fit still samples 128 scenes with replacement.

| Information regime | 18-fit total | Per-fit median | Per-fit p90 | Per-fit maximum | 216-fit projected time |
|---|---:|---:|---:|---:|---:|
| `history_only` | 3,023.440 s | 588.927 s | 596.064 s | 597.462 s | 10.078 h |
| `future_ball` | 3,652.456 s | 659.586 s | 673.913 s | 673.913 s | 12.175 h |
| `future_opponent_plus_ball` | 4,628.548 s | 824.573 s | 869.284 s | 869.284 s | 15.429 h |
| **All** | **11,304.443 s** | **627.582 s** | **827.425 s** | **869.284 s** | **37.681 h** |

The measured information-regime difference is material: the future-opponent
regime took about 53% longer per fit on average than history-only. The highest
single fit took 14.49 minutes, below the existing 60-minute per-fit stop limit.

## Colab compute units

The frozen RES338 GPU amendment recorded 256.78 CU before allocation. Its
progress index recorded 188.34 CU at fit-campaign start and 133.00 CU at completion:

- Preparation, environment qualification, cache staging, and earlier Colab
  interruptions consumed **68.44 CU** before the fit ledger started.
- The 18-fit campaign and its inter-fit/reconnect overhead consumed **55.34 CU**.
- The exact fit-seconds alone would have cost about **21.13 CU** at 6.73 CU/hour;
  the remaining **34.21 CU** is the observed campaign-control and idle/reconnect
  overhead.

At the last observed active A100 rate of **6.73 CU/hour**, the 216 fit-seconds
alone project to **253.60 CU**. Scaling the measured 18-fit campaign overhead by
12 and adding one observed preparation/staging allowance gives the expected total:

```text
216-fit measured time:             253.60 CU
12 × measured 18-fit overhead:     410.48 CU
RES338 setup/staging allowance:     68.44 CU
Expected campaign consumption:     732.52 CU
```

The approved scientific ceiling would allow at most 3,600 seconds for each of 216
fits plus one 900-second infrastructure retry for each fit: **270 GPU hours**.
At the last observed rate this is 1,817.10 CU of fit/retry time. A 336-hour wall
ceiling is 2,261.28 CU at that rate; adding the 68.44-CU historical
preparation/staging allowance gives a conservative envelope of **2,329.72 CU**.
The proposed fixed campaign cap is **2,400 CU**, leaving 70.28 CU beyond that
envelope. The wall timer starts from the RES340 progress index initialized before
cache staging. If the A100 rate changes, the owner authorization and cap must be
recalculated before any staging or fit.

## Live quota gate

The last observed A100 execution rate was 6.73 CU/hour. Colab reports 0 CU/hour
when there is no active assignment, so the owner or operator must re-read the
account before provisioning. The RES340 host preflight does not allocate a session;
it blocks unless the exact authorized balance covers the full cap. The remote
worker rechecks the live A100 rate and remaining campaign budget before staging
and before each fit.

The Colab history records five session terminations and six session creations for
the prior campaign. Its 18 fits completed with verified Drive readbacks and no
configuration changes. The estimates above include the measured historical
staging and inter-fit overhead.

## Cache and storage estimate

The existing owner-only RES338 Drive archive contains all 16 exact training and
validation caches: 12 training plus four validation, **6,687,918,080 bytes** across
106 chunks. All 106 chunks have verified readback. RES340 reuses that archive and
does not create another Drive copy of the caches or rebuild them from raw source.
The Colab worker extracts the archive into the separate RES340 campaign root,
verifies every cache and array, then removes only its temporary local transfer
chunks and tar files. The cache arrays remain in the LOMO campaign root, with the
existing 8 GiB free-disk reserve checked before fitting.

The 18 existing checkpoints occupy about 4.12 MB and receipts 0.58 MB. Scaling
those exact artifacts to 216 fits estimates about **49.43 MB of checkpoints** and
**7.01 MB of receipts**. Append-only progress-index versions and attempt records
are estimated at 30–50 MB; the fit matrix, 234-checkpoint manifest, 216 fold scores,
and private reports add under a few MB. Expected new Drive storage is roughly
**90–110 MB**, separate from the existing 6.69 GB cache archive. Drive storage
bytes do not consume Colab compute units; transfer and setup time are included in
the CU estimate above.

## Restart and stop policy

Before cache staging, require an owner-supplied execution authorization, a
verified owner-only RES340 Drive root, the exact code/matrix/cache hashes, a live
A100 rate equal to the approved rate, and an account balance at least equal to the
full 2,400 CU cap. Initialize and read back the content-addressed 216-fit progress
index before staging. Before each one-fit worker job, re-read balance and rate; ensure
the remaining balance and unspent cap cover every remaining fit's 60-minute plus
15-minute retry ceiling. No fit starts if that check fails.

After each fit, verify the local checkpoint, receipt, and campaign-ledger version
against their hashes, upload them under content-addressed names, read them back,
and then advance the content-addressed progress index. If Colab expires, re-stage
the same 16-cache archive, restore the last verified campaign ledger and completed
run artifacts, verify all hashes, and resume at the first incomplete fit. Preserve
all attempt history. Only an independently confirmed infrastructure interruption
with OOM excluded permits one fresh-seeded retry. A missing identity, evaluation
role access, validation/held-out overlap, source mismatch, failed readback, 270 GPU
hours, 292.5 CPU hours, 336 campaign hours, or 2,400 CU stops the campaign; an
incomplete matrix is never scored or summarized as complete.
