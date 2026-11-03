# Speed trend of the r/R 0.95 c_n error, Sequence S (T13)

Odd `tip-model-analysis` T13 (S6, S7). Offline, read-only, existing data. Tool `scripts/tipSpeedTrend.py`
(tests `tests/test_tip_speed_trend.py`). Reproduce (about 2 min, most of it reading the ALM element CSVs):

```sh
cd turbinesFoam/validation/phaseVI
R=<main checkout>/turbinesFoam/validation/phaseVI/runs; P=<main checkout>/turbinesFoam/articles/uae6/parquet
python3 -I scripts/tipSpeedTrend.py --runs-dir $R --records $P/uae6.z18.00.s0{5,6,7,8}00000.parquet --out analysis/tip-speed-trend
```

Files: `speed_trend.csv` (27 columns x 12 cells), `alm_dut_variant.csv` (existing ALM DUT-polar runs, U5 and U8 only),
`cp_shape.csv`, `cp_vs_alpha.csv`, `cp_s<NN>_<station>.csv` (time-mean Cp per tap, raw record read-only).
Windows as in `applyNearTipFunctions.py` (S5, S6 rev 16..24; S7, S8 rev 4..12). Errors are the committed
`cl.csv` values (reproduced to 0.1 pp).

## Per-speed table (ALM v1.3 total polar, OLAF-DP, AeroDyn BEM; errors in %)

| quantity | S5 | S6 | S7 | S8 |
|---|---|---|---|---|
| tip Re (ALM 0.95) [1e6] | 0.916 | 0.918 | 0.921 | 0.925 |
| tip alpha ALM / BEM [deg] | 2.71 / 2.49 | 3.76 / 3.52 | 4.86 / 4.59 | 6.09 / 5.69 |
| polar lift slope at tip alpha [1/deg] | 0.122 | 0.123 | 0.121 | 0.087 |
| polar Re effect on cl, Re_tip vs 1e6 (OSU multi-Re fit) [%] | -1.39 | -1.41 | -0.84 | -0.22 |
| measured c_n 0.95 | 0.3467 | 0.4268 | 0.5064 | 0.6200 |
| per-revolution sigma of c_n 0.95 [%] | 0.20 | 0.25 | 0.18 | 0.13 |
| PCHIP re-integration, 0.95 [%] / leave-one-tap RMS [%] | +2.48 / 6.4 | +2.18 / 4.8 | +1.93 / 4.0 | +1.62 / 3.2 |
| QNORM 0.95 [Pa] | 823.5 | 823.2 | 844.3 | 849.1 |
| err 0.63 ALM / OLAF / BEM | -10.8 / -11.7 / -11.7 | -1.7 / -2.4 / -2.5 | -1.6 / -1.8 / -1.9 | -3.4 / -3.5 / -3.4 |
| err 0.80 ALM / OLAF / BEM | -7.5 / -9.2 / -11.0 | +1.6 / -0.4 / -2.2 | +2.9 / +0.7 / -0.3 | +3.3 / +2.1 / +1.5 |
| err 0.95 ALM / OLAF / BEM | +8.4 / +1.8 / +0.6 | +18.9 / +12.4 / +11.8 | +26.2 / +19.7 / +20.0 | +25.4 / +16.5 / +19.1 |
| tip excess (err 0.95 minus mean of 0.63, 0.80) ALM / OLAF / BEM [pp] | 17.6 / 12.2 / 11.9 | 18.9 / 13.8 / 14.2 | 25.6 / 20.2 / 21.1 | 25.4 / 17.2 / 20.1 |
| alpha offset that closes the 0.63 / 0.80 gap, ALM [deg] | +0.48 / +0.29 | +0.11 / -0.08 | n/a (slope < 0.08) | n/a |
| OSU -> DUT lift ratio at ALM tip alpha | 1.21 | 1.14 | 1.10 | 1.07 |
| Cp(0.02c)/Cp(0.20c) upper surface, 0.63 / 0.80 / 0.95 | 0.89 / 0.83 / 0.75 | 1.23 / 1.13 / 1.03 | 1.56 / 1.40 / 1.30 | 1.84 / 1.67 / 1.54 |

## ALM with the DUT polar (existing runs U5, U8; same everything else)

| err % | S5 0.63 | S5 0.80 | S5 0.95 | S8 0.63 | S8 0.80 | S8 0.95 |
|---|---|---|---|---|---|---|
| OSU total | -10.8 | -7.5 | +8.4 | -3.4 | +3.3 | +25.4 |
| DUT total | -2.8 | +2.6 | +22.5 | +0.1 | +9.0 | +31.8 |
| OSU x (1 - F_Cl) | -10.8 | -10.7 | -10.9 | -3.4 | -0.2 | +3.0 |
| DUT x (1 - F_Cl) | -2.8 | -0.9 | +0.7 | +0.1 | +5.4 | +8.3 |

(F_Cl = 0.034 at 0.80, 0.178 at 0.95, none at 0.63; applied to c_n, within 0.05 pp of the lift-part form.)

## Verdicts

- (a) Reynolds number: REJECTED. Tip Re is 0.92e6 at every speed (spread 1 %), so there is no speed-dependent Re.
  The OSU Re 0.75-1.5e6 set changes cl by -0.2 to -1.4 % at the tip alpha; the trend S5 -> S7 it could explain is 0.5 pp
  of 18. The ALM runs `liftReCorrExp = 0` anyway (the 1e6 polar is used as is; `alm_cl` equals the polar value).
- (b) Tip alpha / polar regime: PARTLY SUPPORTED as a polar-low-alpha effect, not as a transition feature. The tip alpha
  is 2.7-4.9 deg at S5-S7, on the linear range (slope 0.12 per deg); S8 (6.1 deg) is entering the nonlinear part (slope 0.087), which
  caps the S8 error. The S809 polar has no kink there, but the three Re 1e6 sources differ by a constant lift offset:
  DUT - OSU = +0.07..0.08 in cl at 0..4 deg (zero-lift angle -1.2 vs -0.64 deg), i.e. +21 % at the S5 tip alpha, +7 % at S8.
- (c) Measurement: REJECTED as the cause of the trend. Repeatability 0.13-0.25 % at 0.95; QNORM within 3 % across speeds;
  integration sensitivity (PCHIP +2.5 % at S5, +1.6 % at S8; leave-one-tap RMS 6.4 -> 3.2 %) moves the S5-S8 trend by under 1 pp.
  Not enough to explain 18 pp, and the same size at 0.63 and 0.80, where models agree at S6-S8.
- (d) Cp shape / transition: REJECTED as a speed-specific signature, UNDETERMINED for a laminar bubble. At S5 0.95 the
  upper surface is a plateau (Cp -0.60...-0.73 over 0.04-0.36c, no leading-edge peak, ratio 0.75), but the LE-peak ratio follows the
  local ALM alpha over all 12 station-speed cells (Spearman rho = 0.986; S5 0.63 at 3.6 deg gives 0.89, S6 0.95 at 3.8 deg gives 1.03). No tip or
  S5 cell departs from that curve. The raw taps cannot separate a bubble from low-alpha attached flow.
- (e) Other: SUPPORTED. The S5 offset is global, not tip-specific. All three models are 9-10 pp lower at S5 than at S6 at all three stations
  (ALM -9.1/-9.2/-10.5 pp at 0.63/0.80/0.95; OLAF -9.3/-8.8/-10.6; BEM -9.3/-8.8/-11.2). Inboard S5 is -8..-12 % where S6-S8 are within +-3.5 %.
  Split of the S5 -> S7 rise of the 0.95 error (ALM +17.8, OLAF +17.9, BEM +19.4 pp): about 10 pp is the inboard shift (global),
  the remainder, 8-9 pp, is the growth of the tip excess (12 -> 20 OLAF, 18 -> 26 ALM).

## Most likely explanation of S5

The S5 deficit is mostly a low-alpha lift deficit of the OSU Re 1e6 total polar, common to every station: the same models
are 8-12 % low at 0.63 and 0.80 at S5, where alpha is 3-4 deg and the OSU polar lifts 0.07-0.08 less than the DUT Re 1e6
polar (equivalent alpha offset +0.3..0.5 deg). Because that deficit decays with alpha, it makes the shared 0.95 error look speed
dependent. It is of opposite sign to the virtual-camber correction, which is why F_Cl alone over-corrects S5. The existing DUT ALM
runs confirm it directly: inboard S5 goes from -10.8/-7.5 to -2.8/+2.6 and the tip from +8.4 to +22.5, so the tip excess grows less
with speed (S5 -> S8 +4.6 pp instead of +7.8). With F_Cl on top, S5 0.95 is +0.7 % and S8 0.95 +8.3 % (both inside 10 %), versus
-10.9 and +3.0 with the OSU polar. This is a polar-source choice, not a fitted coefficient (S6). It is not a settled result:
the polar choice is a decision of record (the OSU total is the case of record; DUT was a diagnostic P4 arm, and the literature favours
DUT for Phase VI, `phasevi-physics-diagnosis.md` E5), and what remains of the tip excess growth with speed (about 5 pp ALM) is unexplained.

## Caveats

- DUT ALM runs exist only for U5 and U8; U6, U7 are not available. The `predicted_dut_err_pct` column (cn scaled by the polar ratio) overshoots
  the actual run by 7-9 pp at the tip (31.1 vs 22.5 at S5) because the ALM alpha falls when lift rises; treat it as an upper bound.
- F_Cl x DUT is a first-order composition (c_n x (1 - F_Cl)) on frozen runs, not a run with both switched on.
- The Cp-shape index tests alpha-dependence only; absolute S809 Cp at the same alpha is not available in the repository.
- Tip alpha is the ALM/BEM alpha, not a measured one. BEM alpha is the mean of blades from `metrics.json`.
- The tool was written after the analysis shape was known; its tests were not RED-first (analysis tool, no prior behaviour).
