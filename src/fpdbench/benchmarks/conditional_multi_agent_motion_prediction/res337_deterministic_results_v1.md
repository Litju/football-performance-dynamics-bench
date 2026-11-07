# Deterministic baseline research results

Frozen implementation commit `f14537acc17f4381d0c95907f1f1a1654152410a`; execution identity SHA-256 `05f6e22566e6781d7465bce00ae5e32fb7c5f7d163ea9efbfed1ad4640c9fb1e`.

Research-only descriptive results under `fpdbench.public-skillcorner-research-admission/1.0.0`; private manifest SHA-256 `a8c82bfa09ac792d6c4ae779d4b28158c33ed3c2500f8548f3e94d48197f4fd1`. Protected population status remains NOT_QUALIFIED. No learned training, checkpoint selection, or learned LOMO was performed.

Metrics below are physical XY ADE / FDE / coordinate RMSE in metres. Scene scores are averaged within each window, windows within each match, and matches equally within each role. Scored-point and final-target counts are totals across scoreable scenes; each scene metric uses its own valid-point or final-target denominator before equal-weight aggregation. Forecast origins overlap, so windows are not independent statistical units. These results are descriptive, with no significance claims.

| Cell | Validation | Evaluation | Training control |
|---|---:|---:|---:|
| origin_persistence_v1 / history_only / absolute_xy | 3.7098 / 6.7162 / 3.2552 | 3.5219 / 6.3739 / 3.0952 | 3.6288 / 6.5791 / 3.1986 |
| origin_persistence_v1 / future_ball / absolute_xy | 3.7098 / 6.7162 / 3.2552 | 3.5219 / 6.3739 / 3.0952 | 3.6288 / 6.5791 / 3.1986 |
| origin_persistence_v1 / future_opponent_plus_ball / absolute_xy | 3.7098 / 6.7162 / 3.2552 | 3.5219 / 6.3739 / 3.0952 | 3.6288 / 6.5791 / 3.1986 |
| origin_persistence_v1 / history_only / origin_relative_displacement | 3.7098 / 6.7162 / 3.2552 | 3.5219 / 6.3739 / 3.0952 | 3.6288 / 6.5791 / 3.1986 |
| origin_persistence_v1 / future_ball / origin_relative_displacement | 3.7098 / 6.7162 / 3.2552 | 3.5219 / 6.3739 / 3.0952 | 3.6288 / 6.5791 / 3.1986 |
| origin_persistence_v1 / future_opponent_plus_ball / origin_relative_displacement | 3.7098 / 6.7162 / 3.2552 | 3.5219 / 6.3739 / 3.0952 | 3.6288 / 6.5791 / 3.1986 |
| constant_velocity_1s_v1 / history_only / absolute_xy | 2.3522 / 5.1717 / 2.3404 | 2.2433 / 4.9257 / 2.2384 | 2.2599 / 4.9647 / 2.2649 |
| constant_velocity_1s_v1 / future_ball / absolute_xy | 2.3522 / 5.1717 / 2.3404 | 2.2433 / 4.9257 / 2.2384 | 2.2599 / 4.9647 / 2.2649 |
| constant_velocity_1s_v1 / future_opponent_plus_ball / absolute_xy | 2.3522 / 5.1717 / 2.3404 | 2.2433 / 4.9257 / 2.2384 | 2.2599 / 4.9647 / 2.2649 |
| constant_velocity_1s_v1 / history_only / origin_relative_displacement | 2.3522 / 5.1717 / 2.3404 | 2.2433 / 4.9257 / 2.2384 | 2.2599 / 4.9647 / 2.2649 |
| constant_velocity_1s_v1 / future_ball / origin_relative_displacement | 2.3522 / 5.1717 / 2.3404 | 2.2433 / 4.9257 / 2.2384 | 2.2599 / 4.9647 / 2.2649 |
| constant_velocity_1s_v1 / future_opponent_plus_ball / origin_relative_displacement | 2.3522 / 5.1717 / 2.3404 | 2.2433 / 4.9257 / 2.2384 | 2.2599 / 4.9647 / 2.2649 |

Equal-match persistence-minus-constant-velocity ADE is 1.3577 m on validation, 1.2785 m on evaluation, 1.3689 m on training. These are descriptive comparisons.

All six cells per model share the same physical predictions: the models consume only target history, and both target representations were checked for metric parity for each scored scene.

| Role | Match | Windows | Scenes | Scored points | Final targets | Persistence ADE / FDE / RMSE | Constant velocity ADE / FDE / RMSE |
|---|---:|---:|---:|---:|---:|---:|---:|
| validation | 1953632 | 12725 | 25450 | 4199250 | 279950 | 3.4324 / 6.1856 / 3.0184 | 2.2869 / 5.0245 / 2.2723 |
| validation | 1996435 | 12282 | 24564 | 4053060 | 270204 | 3.6589 / 6.6334 / 3.2178 | 2.2580 / 4.9517 / 2.2648 |
| validation | 2015213 | 10844 | 21688 | 3578520 | 238568 | 3.9321 / 7.1305 / 3.4307 | 2.4986 / 5.5104 / 2.4681 |
| validation | 2017461 | 10072 | 20144 | 3323760 | 221584 | 3.8160 / 6.9156 / 3.3537 | 2.3653 / 5.2005 / 2.3563 |
| evaluation | 1874553 | 12363 | 24726 | 4079790 | 271986 | 3.6619 / 6.6389 / 3.2044 | 2.2771 / 4.9935 / 2.2673 |
| evaluation | 1925299 | 14018 | 28036 | 4625940 | 308396 | 3.4419 / 6.2250 / 3.0213 | 2.1703 / 4.7783 / 2.1647 |
| evaluation | 2006229 | 12501 | 25002 | 4125330 | 275022 | 3.4937 / 6.3159 / 3.0860 | 2.2816 / 5.0098 / 2.2820 |
| evaluation | 2010085 | 12831 | 25662 | 4234230 | 282282 | 3.4899 / 6.3160 / 3.0691 | 2.2442 / 4.9212 / 2.2394 |
| training | 1886347 | 11983 | 23966 | 3954390 | 263626 | 3.7205 / 6.7321 / 3.2691 | 2.3574 / 5.1957 / 2.3494 |
| training | 1899585 | 10479 | 20958 | 3458070 | 230538 | 3.6024 / 6.5286 / 3.1976 | 2.2859 / 5.0044 / 2.3075 |
| training | 1927964 | 15434 | 30868 | 5093220 | 339548 | 3.2904 / 5.9695 / 2.9107 | 2.0620 / 4.5339 / 2.0752 |
| training | 1959846 | 10914 | 21828 | 3601620 | 240108 | 3.6357 / 6.5968 / 3.1953 | 2.2242 / 4.8905 / 2.2294 |
| training | 1986691 | 11428 | 22856 | 3771240 | 251416 | 3.4463 / 6.2448 / 3.0506 | 2.1463 / 4.7067 / 2.1546 |
| training | 1996436 | 9549 | 19098 | 3151170 | 210078 | 3.5569 / 6.4454 / 3.1610 | 2.2012 / 4.8244 / 2.2263 |
| training | 2006363 | 12764 | 25528 | 4212120 | 280808 | 3.6084 / 6.5509 / 3.1805 | 2.2138 / 4.8773 / 2.2248 |
| training | 2007448 | 11139 | 22278 | 3675870 | 245058 | 3.7980 / 6.9000 / 3.3325 | 2.2873 / 5.0333 / 2.2936 |
| training | 2007721 | 12995 | 25990 | 4288350 | 285890 | 3.4689 / 6.2898 / 3.0613 | 2.1608 / 4.7520 / 2.1596 |
| training | 2011166 | 9614 | 19228 | 3172620 | 211508 | 3.9002 / 7.0764 / 3.4400 | 2.3555 / 5.1805 / 2.3705 |
| training | 2013725 | 11138 | 22276 | 3675540 | 245036 | 3.8262 / 6.9303 / 3.3502 | 2.4168 / 5.2942 / 2.4044 |
| training | 2016236 | 12201 | 24402 | 4026330 | 268422 | 3.6920 / 6.6847 / 3.2347 | 2.4079 / 5.2839 / 2.3830 |

Provider-extrapolation quality counts are finite truth observations in scoreable scenes; overlapping windows may count an observation repeatedly. The two scene strata classify a scene as containing provider extrapolation if any of its finite future targets has the provider flag `is_detected=false`. Within each match, each stratum metric averages scoreable scenes of that stratum within windows and then those windows equally; stratum windows can overlap.

| Role | Detected observations | Provider-extrapolated observations | Detected-only stratum windows | Extrapolation stratum windows |
|---|---:|---:|---:|---:|
| validation | 10064031 | 5090559 | 711 | 45923 |
| evaluation | 11056471 | 6008819 | 1343 | 51713 |
| training | 28844935 | 17235605 | 1831 | 139638 |

| Role | Stratum | Matches represented | Persistence ADE / FDE / RMSE | Constant velocity ADE / FDE / RMSE |
|---|---|---:|---:|---:|
| validation | detected_only | 4 | 2.8785 / 5.0618 / 2.5601 | 2.3359 / 5.0465 / 2.3005 |
| validation | with_extrapolation | 4 | 3.7088 / 6.7148 / 3.2546 | 2.3497 / 5.1669 / 2.3383 |
| evaluation | detected_only | 4 | 2.5657 / 4.4648 / 2.2870 | 2.4019 / 5.0610 / 2.3617 |
| evaluation | with_extrapolation | 4 | 3.5206 / 6.3727 / 3.0948 | 2.2395 / 4.9183 / 2.2358 |
| training | detected_only | 12 | 2.7230 / 4.8000 / 2.4471 | 2.3410 / 5.0115 / 2.3004 |
| training | with_extrapolation | 12 | 3.6283 / 6.5788 / 3.1987 | 2.2580 / 4.9607 / 2.2634 |

All listed matches completed with zero prediction failures. Validation preceded the code/runtime freeze; the evaluation role was scored in one pass, followed by the training descriptive controls. The complete private execution identity, research manifest, stream hashes, per-cell manifests, and per-match quality strata remain in private storage. No tracking rows, player identities, truth masks, or predictions are published here.

The sequential scoring stages took approximately 45 minutes wall time on the local CPU,
including identity rechecks. Resident memory observed during the final control was about
36 MiB; the scorer streamed one match at a time without replicating the private corpus.
