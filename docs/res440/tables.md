# RES-440 scientific tables

All errors are metres. Four independent matches; three seeds averaged within each match. SD is descriptive sample SD across four match means, not uncertainty. Research-only `NOT_QUALIFIED`. Source: [safe findings](findings.json).

## 1. Physical trajectory error

| Information regime | Target | ADE mean ± SD | FDE mean ± SD | XY RMSE mean ± SD |
| --- | --- | --- | --- | --- |
| history_only | Absolute XY | 2.1216 ± 0.0513 | 4.0672 ± 0.1047 | 1.9570 ± 0.0506 |
| history_only | Displacement | 1.6680 ± 0.0478 | 3.5601 ± 0.0981 | 1.6537 ± 0.0470 |
| future_ball | Absolute XY | 1.8330 ± 0.0506 | 3.3712 ± 0.1001 | 1.6918 ± 0.0473 |
| future_ball | Displacement | 1.4298 ± 0.0413 | 2.8572 ± 0.0790 | 1.4041 ± 0.0396 |
| future_opponent_plus_ball | Absolute XY | 1.7182 ± 0.0436 | 3.0447 ± 0.0859 | 1.5744 ± 0.0416 |
| future_opponent_plus_ball | Displacement | 1.2958 ± 0.0404 | 2.5438 ± 0.0780 | 1.2843 ± 0.0377 |

## 2. Prespecified paired ADE contrasts

C1 = history − future ball; C2 = future ball − (future opponents + ball). Positive values indicate lower ADE with added realized future context.

| Contrast | Target | 1874553 | 1925299 | 2006229 | 2010085 | Mean | SD | Delete-one range |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C1 | Absolute XY | 0.2820 | 0.2847 | 0.2908 | 0.2970 | 0.2886 | 0.0067 | 0.2858–0.2908 |
| C1 | Displacement | 0.2425 | 0.2263 | 0.2412 | 0.2428 | 0.2382 | 0.0080 | 0.2367–0.2422 |
| C2 | Absolute XY | 0.1305 | 0.1059 | 0.1129 | 0.1096 | 0.1147 | 0.0109 | 0.1095–0.1177 |
| C2 | Displacement | 0.1390 | 0.1344 | 0.1340 | 0.1284 | 0.1339 | 0.0044 | 0.1323–0.1358 |

Deletion ranges are descriptive sensitivity, not confidence intervals.

## 3. History-only comparisons with frozen deterministic baselines

| Baseline | Learned target | Metric | Baseline | Learned | Reduction (m) | % |
| --- | --- | --- | --- | --- | --- | --- |
| origin_persistence_v1 | Absolute XY | ade_m | 3.5219 | 2.1216 | 1.4003 | 39.8 |
| origin_persistence_v1 | Absolute XY | fde_m | 6.3739 | 4.0672 | 2.3067 | 36.2 |
| origin_persistence_v1 | Absolute XY | xy_rmse_m | 3.0952 | 1.9570 | 1.1382 | 36.8 |
| origin_persistence_v1 | Displacement | ade_m | 3.5219 | 1.6680 | 1.8538 | 52.6 |
| origin_persistence_v1 | Displacement | fde_m | 6.3739 | 3.5601 | 2.8138 | 44.1 |
| origin_persistence_v1 | Displacement | xy_rmse_m | 3.0952 | 1.6537 | 1.4415 | 46.6 |
| constant_velocity_1s_v1 | Absolute XY | ade_m | 2.2433 | 2.1216 | 0.1217 | 5.4 |
| constant_velocity_1s_v1 | Absolute XY | fde_m | 4.9257 | 4.0672 | 0.8585 | 17.4 |
| constant_velocity_1s_v1 | Absolute XY | xy_rmse_m | 2.2384 | 1.9570 | 0.2813 | 12.6 |
| constant_velocity_1s_v1 | Displacement | ade_m | 2.2433 | 1.6680 | 0.5753 | 25.6 |
| constant_velocity_1s_v1 | Displacement | fde_m | 4.9257 | 3.5601 | 1.3656 | 27.7 |
| constant_velocity_1s_v1 | Displacement | xy_rmse_m | 2.2384 | 1.6537 | 0.5847 | 26.1 |

Baselines are means of the published four-decimal match values; each baseline mean and baseline-minus-learned difference has a rounding bound of 0.00005 m. Conditional regimes are excluded from this forecasting comparison.

## 4. Predeclared horizon and target-quality ADE

| Stratum | Information regime | Target | ADE |
| --- | --- | --- | --- |
| early | history_only | Absolute XY | 0.9466 |
| early | history_only | Displacement | 0.4744 |
| early | future_ball | Absolute XY | 0.8501 |
| early | future_ball | Displacement | 0.4545 |
| early | future_opponent_plus_ball | Absolute XY | 0.8810 |
| early | future_opponent_plus_ball | Displacement | 0.4291 |
| middle | history_only | Absolute XY | 1.9782 |
| middle | history_only | Displacement | 1.5689 |
| middle | future_ball | Absolute XY | 1.7528 |
| middle | future_ball | Displacement | 1.3989 |
| middle | future_opponent_plus_ball | Absolute XY | 1.6468 |
| middle | future_opponent_plus_ball | Displacement | 1.2804 |
| late | history_only | Absolute XY | 3.4400 |
| late | history_only | Displacement | 2.9607 |
| late | future_ball | Absolute XY | 2.8960 |
| late | future_ball | Displacement | 2.4359 |
| late | future_opponent_plus_ball | Absolute XY | 2.6269 |
| late | future_opponent_plus_ball | Displacement | 2.1780 |
| detected_only | history_only | Absolute XY | 2.1482 |
| detected_only | history_only | Displacement | 1.6949 |
| detected_only | future_ball | Absolute XY | 1.8312 |
| detected_only | future_ball | Displacement | 1.4311 |
| detected_only | future_opponent_plus_ball | Absolute XY | 1.7287 |
| detected_only | future_opponent_plus_ball | Displacement | 1.3047 |
| with_provider_extrapolation | history_only | Absolute XY | 2.1201 |
| with_provider_extrapolation | history_only | Displacement | 1.6665 |
| with_provider_extrapolation | future_ball | Absolute XY | 1.8328 |
| with_provider_extrapolation | future_ball | Displacement | 1.4304 |
| with_provider_extrapolation | future_opponent_plus_ball | Absolute XY | 1.7183 |
| with_provider_extrapolation | future_opponent_plus_ball | Displacement | 1.2965 |

Early/middle/late = 0.2–1.0/1.2–2.0/2.2–3.0 s. Quality strata classify scenes; windows can contribute to both quality strata. They are not additive or causal quality comparisons. All stratum FDE/RMSE values are in [strata.csv](strata.csv).
