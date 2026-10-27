# AeroDyn BEM verification (task T12 of `odd/tasks/v13-adoption-asm.md`)

Is the OpenFAST AeroDyn BEM, the repository's only BEM, implemented and installed correctly?
Two tests, both reproducible from this directory:

1. **Code verification** (a): the installed binary against the OpenFAST r-test v5.0.0 references.
2. **Experiments on disk** (b): the AeroDyn BEM against every measured Phase VI point of the three table
   families the repository holds (the UAE Phase VI archive is the only experiment on disk).

Binary: OpenFAST `AeroDyn_driver-v5.0.0`, conda-forge `openfast-5.0.0 hd1f9c02_2` (GCC 15.3.0, **single
precision**: the recipe sets `-DDOUBLE_PRECISION=OFF`) at
`/scratch/leahk/eduardo.donestevez/conda-envs/openfast`. Date of the runs: 2026-10-27.

## (a) r-test v5.0.0, AeroDyn driver, `Wake_Mod = 1` — `rtest_bem.csv`, `rtest_bem_double.csv`

```sh
python3 -I openfast/rtestAeroDyn.py --rtest <r-test checkout at v5.0.0> \
    --openfast-env /scratch/leahk/eduardo.donestevez/conda-envs/openfast --scratch <new empty dir> \
    --out analysis/aerodyn-verification/rtest_bem.csv
```

Rule (OpenFAST v5.0.0 `reg_tests/lib/pass_fail.py::passing_channels`, `executeAerodynRegressionCase.py`,
`CTEST_RTEST_RTOL=2`, `CTEST_RTEST_ATOL=1.9`), reproduced in `openfast/rtestAeroDyn.py`:
`rtol = 1e-2`; `atol = max(10**(max_t floor(log10(b - min b + 1e-12)) - 1.9), 1e-6)` per channel; a channel
passes when every sample satisfies `|t - b| <= atol + rtol |b|` and is finite; a case passes when all channels
do (`ConvIter`, `ConvError`, `NumUJac` dropped). `max_rel_err` is the largest `|t - b| / |b|` over samples with
`|b| > atol`; `max_norm_over_range` is the suite's own `calculate_max_norm_over_range`.

Run: the nine BEM cases (`Wake_Mod = 1`) of `modules/aerodyn`. Skipped: `ad_B1n2_OLAF`, `ad_BAR_OLAF`,
`ad_EllipticalWingInf_OLAF`, `ad_HelicalWakeInf_OLAF`, `ad_Kite_OLAF`, `ad_QuadRotor_OLAF`, `ad_Sphere_OLAF`,
`ad_VerticalAxis_OLAF` (`Wake_Mod = 3`, OLAF; not BEM) and the two `py_ad_*` cases (Python driver).

| Binary | PASS | FAIL |
|---|---|---|
| conda-forge, single precision (`rtest_bem.csv`) | `ad_BAR_CombinedCases`, `ad_MultipleHAWT` | `ad_BAR_RNAMotion`, `ad_BAR_SineMotion`, `ad_BAR_SineMotion_UA4_DBEMT3`, `ad_MHK_RM1_Fixed`, `ad_MHK_RM1_Fixed_IfW`, `ad_MHK_RM1_Floating`, `ad_timeseries_shutdown` |
| same source, **double precision** built here (GCC 14.2, OpenBLAS 0.3.29; `rtest_bem_double.csv`) | all nine (six at 0 error, largest `max_rel_err` 5.1e-3) | none |

The r-test references are double precision. The source of the conda package (tarball sha256
`f84793e7...063a`, the recipe's) built with `-DDOUBLE_PRECISION=ON` reproduces every reference, so the AeroDyn
BEM code is correct; the single-precision conda build differs from the double-precision baselines in the
start-up transient and in channels whose reference is 0 or tiny. Does that touch the Phase VI path?

`precision_single_vs_double*.csv` (`openfast/comparePrecision.py`) compare the 253 Phase VI points of (b) run
with both binaries. At 5-8 m/s, 0 yaw and the pitch sweep: power, thrust and torque agree to 1.7e-4, c_n to
4.2e-4. The differences grow only where the BEM is ill-conditioned: deep stall (S curve 19 m/s, c_n at r/R 0.80
2.3e-1; power 6e-3) and yaw >= 135 deg (power 3.4e-2, where the power itself is near zero). The mean-power
ratio of (d) differs by at most 0.004 pp (|yaw| <= 30 deg, U <= 7 m/s). **The installed single-precision binary
is adequate for the Phase VI BEM path in the regimes judged; it is not r-test bit-compatible.**

## (b) Phase VI tables — `scripts/verifyAeroDyn.py`

```sh
cd turbinesFoam/validation/phaseVI
python3 scripts/verifyAeroDyn.py --out analysis/aerodyn-verification --work <new scratch dir>
```

253 cases in 288 s of wall time on one login node (serial driver runs; the 95 `SkewMomCorr=False` sensitivity
runs of the yawed points are extra), 0 failed, all converged. Each case: v1.3 inputs (tip pitch reference
geometry, OSU total polar, cylinder root, rigid, no tower, cone 0, tilt 0), `Wake_Mod=1`.

| Family | Rule | Points |
|---|---|---|
| `s-curve` | `uae6-archive/sequence_S_*.csv`: every speed, 5-25 m/s, 0 yaw, pitch 3 | 21 |
| `pitch` | `yaw-pitch/pitch_*.csv`: every row (sequences I 0, T 2, H 3, S 3, U 4, J 6 deg), 0 yaw | 125 |
| `yaw-S`, `yaw-H` | `yaw-pitch/yaw_{S,H}_*.csv`: speeds 5-10 m/s, every nominal yaw, first (lowest) repetition per (speed, yaw), ties by file name | 42, 65 |

Inputs per point and their source (`case.json` of each case records them):

- **rpm**: the table's measured `rpm` (not `tsr * U / R`); **density**: `rho_kg_m3`; **wind speed**: the nominal
  `wind_speed_m_s`.
- **pitch**: the sequence's nominal tip pitch (`pitch_nominal_deg`; measured B1/B3 pitch agree within 0.06 deg),
  positive toward feather = AeroDyn `BldPitch` (Hand et al. p. 20: tip chord to the plane of the disk). Under the
  tip reference `BlTwist + BldPitch = -mounting` for any pitch, tip `BlTwist = 0` (tested for 0, 2, 3, 4, 6).
- **yaw**: the file-name nominal yaw. The report has the rotor turning counterclockwise seen from upwind and
  positive yaw clockwise seen from above (Fig. B-25: "the blade advances into the wind at 180 deg azimuth");
  AeroDyn turns clockwise seen from upwind with `NacYaw` positive counterclockwise seen from above. The set-ups
  are mirror images, so `NacYaw = +yaw`. Pinned by `test_nac_yaw_sign_...` and, with the driver, by the blade
  seeing more `Vrel` at 180 deg azimuth than at 0 deg for positive yaw.
- **skew model**, yawed points only (v5.0.0 names): `Skew_Mod=1`, `SkewMomCorr=True`, `SkewRedistr_Mod=1`
  (Glauert/Pitt-Peters, `SkewRedistrFactor` default); chosen from the docs ("`Skew_Mod=1` ... recommended") before
  any run. `yaw_power_ratio.csv` also gives the ratio with `SkewMomCorr=False` as a sensitivity.

Tables:

| File | Content |
|---|---|
| `points.csv` | every case: inputs, status, power/thrust/torque model, experiment, error % |
| `stations.csv` | every case at r/R 0.30, 0.47, 0.63, 0.80, 0.95: c_n, c_t (chord line) model, experiment, error %, alpha |
| `s_curve.csv` | S curve: power and thrust error % per speed |
| `pitch_slopes.csv` | dP/dpitch and dT/dpitch per speed and pitch step, model vs experiment, sign agreement; ladder `S3` uses sequence S at pitch 3, `H3` uses H; `*_exp_flat` marks steps whose experimental change is below 3 % |
| `pitch_attached_power.csv` | power error % at 5-7 m/s per pitch |
| `yaw_power_ratio.csv` | P(yaw)/P(0) per sequence, speed, yaw: model, experiment, difference in pp (and the `SkewMomCorr=False` variant) |
| `probes_H_vs_S.csv` | sequence H over S at pitch 3: experiment and model power/thrust ratios |
| `summary.json` | counts, failures, sign tally, `l12` block, OpenFAST version, date, command, wall time |
| `precision_single_vs_double*.csv`, `rtest_bem*.csv` | see (a) |

## Sequence H and S: same rotor, different probe configuration

Sequences H, I, J carry the five-hole probes; S, T, U have them removed and the holes plugged and taped
(Hand et al., sequence descriptions, report p. 17 and 21; `uae6-archive/CATALOG.md`). Both are upwind, rigid, 0 deg cone,
72 rpm, 3 deg tip pitch (H, S). The model does not see the probes, so its H/S ratio is 0.985-1.017 (rpm and
density only). The measured H/S power ratio is 0.95-1.01 at 5-10 m/s and 0.99-1.13 from 11 m/s (largest 1.13 at 19 m/s, deep stall), `probes_H_vs_S.csv`.
