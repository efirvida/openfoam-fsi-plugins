# Near-tip correction functions applied offline to Phase VI stations (T10)

Odd task `odd/tasks/tip-model-analysis.md` T10 (S6, S7). No run, no solver change. The tool is
`scripts/applyNearTipFunctions.py`, the functions are `data/near-tip-functions/trigaux2024_tableC.csv`
(Trigaux 2024, App. C; provenance and transcription check in `PROVENANCE.md` there).

## Reproduce

```sh
cd turbinesFoam/validation/phaseVI
R=<main checkout>/turbinesFoam/validation/phaseVI/runs      # the worktree has no runs/
python3 -I scripts/applyNearTipFunctions.py --apply cl --runs-dir $R --out analysis/near-tip-functions/cl.csv --profile-out analysis/near-tip-functions/F_profile_cl.csv
python3 -I scripts/applyNearTipFunctions.py --apply full --kernel 3D --sigma-over-c 0.25 --runs-dir $R --out analysis/near-tip-functions/full_3D_s0.25.csv
python3 -I scripts/applyNearTipFunctions.py --apply full --kernel 3D --sigma-over-c 0.5  --runs-dir $R --out analysis/near-tip-functions/full_3D_s0.5.csv
python3 -I scripts/applyNearTipFunctions.py --summarize analysis/near-tip-functions/*.csv
# stall cells (opt-in, not in the default set; models without a run are skipped; stations with d/c > 3.457 are outside the table):
python3 -I scripts/applyNearTipFunctions.py --apply cl --models bem --cells S10 S13 S15 S20 S25 --runs-dir $R --out <tmp>/stall.csv
```

(`F_profile.csv` is an identical earlier copy of `F_profile_cl.csv`.) Inputs: ALM v1.3 `alm-U*-coarse-seqS-var-tip-pitch-dag-sorensen-total`
(H7: `alm-U7-coarse-var-...`) element CSVs, windows 16..24 revolutions (S5, S6) and 4..12 (S7, S8, H7);
AeroDyn OLAF-DP and BEM `metrics.json` stations (nodal Cn, Ct, alpha); experiment
`data/experiment/uae6-archive/sequence_{S,H}_spanwise.csv` (the committed `data/experiment/` file holds S7 only).

## Effective distance and functions

Blade `data/geometry/phaseVI_blade.csv`, R = 5.029 m, chord linear between stations,
`(d_tip/c)_eff(r) = int_r^R dr'/c`.

| r/R | r [m] | local c [m] | (d_tip/c)_eff | F_Cl (3D c/4) | F_alpha_e (3D c/4) | F_Cl range over the 6 tables | F_alpha_e (3D c/2) |
|---|---|---|---|---|---|---|---|
| 0.80 | 4.023 | 0.457 | 2.4885 | 0.0339 | -0.0097 | 0.0336 - 0.0341 | -0.0026 |
| 0.95 | 4.778 | 0.381 | 0.6834 | 0.1781 | 0.0659 | 0.1749 - 0.1784 | 0.1404 |

`F_Cl` is kernel/size independent (spread 0.004), so `--apply cl` is one number per station.
Profile at every blade-table radius: `F_profile_cl.csv` (blank beyond the table range d/c > 3.457, r/R < 0.78).

## Cross-check of the uncorrected errors against v13-adoption-asm L26 (r/R 0.95)

All 15 values reproduce to the printed 0.1 pp: ALM +8.4/+18.9/+26.2/+25.4/+23.5, OLAF-DP +1.8/+12.4/+19.7/+16.5/+17.1,
BEM +0.6/+11.8/+20.0/+19.1/+17.4 (S5, S6, S7, S8, H7). The 0.80 values also match the L26 BEM/OLAF table;
ALM c_n equals `runs/v14-compare/*/spanwise_comparison.csv` to 5e-5 at both stations. No mismatch.

## c_n error vs experiment [%] (inside the 10 % band: |e| <= 10)

Columns: uncorrected | `--apply cl` (lift part x (1 - F_Cl)) | `full` 3D sigma = c/4 | `full` 3D sigma = c/2.

r/R 0.95

| model | S5 | S6 | S7 | S8 | H7 |
|---|---|---|---|---|---|
| ALM | 8.4 / **-10.9** / -16.7 / -23.1 | 18.9 / -2.3 / -8.7 / -15.6 | 26.2 / 3.8 / -3.1 / -10.4 | 25.4 / 3.1 / -3.7 / -11.0 | 23.5 / 1.5 / -5.2 / -12.4 |
| OLAF-DP | 1.8 / -16.3 / -21.8 / -27.8 | 12.4 / -7.6 / -13.7 / -20.3 | 19.7 / -1.6 / -8.1 / -15.0 | 16.5 / -4.2 / -10.5 / -17.3 | 17.1 / -3.7 / -10.0 / -16.9 |
| BEM | 0.6 / -17.3 / -22.8 / -28.6 | 11.8 / -8.1 / -14.1 / -20.6 | 20.0 / -1.3 / -7.8 / -14.8 | 19.1 / -2.1 / -8.5 / -15.5 | 17.4 / -3.5 / -9.8 / -16.6 |

r/R 0.80

| model | S5 | S6 | S7 | S8 | H7 |
|---|---|---|---|---|---|
| ALM | -7.5 / -10.7 / -9.8 / -10.4 | 1.6 / -1.9 / -0.9 / -1.6 | 2.9 / -0.6 / 0.4 / -0.3 | 3.3 / -0.2 / 0.8 / 0.1 | 3.4 / -0.1 / 0.8 / 0.1 |
| OLAF-DP | -9.2 / -12.3 / -11.4 / -12.0 | -0.4 / -3.8 / -2.9 / -3.5 | 0.7 / -2.7 / -1.8 / -2.5 | 2.1 / -1.3 / -0.4 / -1.0 | 1.1 / -2.3 / -1.4 / -2.1 |
| BEM | -11.0 / -14.0 / -13.2 / -13.7 | -2.2 / -5.5 / -4.6 / -5.2 | -0.3 / -3.7 / -2.8 / -3.5 | 1.5 / -1.9 / -1.0 / -1.7 | 0.1 / -3.3 / -2.4 / -3.1 |

## Band count (10 cells = 5 cases x 2 stations), before -> after

| mode | ALM | OLAF-DP | BEM |
|---|---|---|---|
| `cl` | 6 -> 8 | 6 -> 8 | 5 -> 8 |
| `full` 3D c/4 | 6 -> 9 | 6 -> 5 | 5 -> 7 |
| `full` 3D c/2 | 6 -> 4 | 6 -> 4 | 5 -> 4 |

At 0.95 alone (5 cells): uncorrected 1/5 for each model (S5 only); `cl` 4/5 for each model (S5 fails: ALM -10.9, OLAF -16.3, BEM -17.3);
`full` c/4: ALM 4/5, OLAF 1/5, BEM 3/5.

## Reading

- `cl` (virtual camber only, kernel independent, no tuning) removes 20-23 pp at 0.95 in the S6-H7 cases (ALM +26.2 -> +3.8 at S7,
  OLAF +19.7 -> -1.6, BEM +20.0 -> -1.3) and brings all three models to within -8.1 ... +3.8 % there. It does not
  address the ALM-specific 6-9 pp: ALM keeps its excess over OLAF (+5.4 pp at S7) after the correction.
- S5 (5 m/s, tip error already +0.6..+8.4 %) is over-corrected to -10.9..-17.3 %: the correction is one number per
  position (F_Cl does not depend on load), the S5 tip was already inside the band. At 0.80 the `cl` correction moves the error by up to 3.4 pp (down) and
  pushes ALM S5 (-7.5 -> -10.7) and BEM S5 (-11.0 -> -14.0) outside the band.
- `full` is a double count with Dag-Sorensen (and for OLAF/BEM there is no mollification at all, so `F_alpha_e` has no meaning
  there): shown only because it was requested. It over-corrects every model at sigma = c/2.

## Approximation: scaling c_n instead of the lift part

`cn_scale` = c_n (1 - F) against the exact c_n - F c_l cos(alpha): the difference is F c_d sin(alpha), at most 0.05 pp over
all 90 rows (0.03 pp for `cl`). The ALM element rows (cl, cd, alpha) give c_l exactly; for AeroDyn c_l = c_n cos(alpha) + c_t sin(alpha)
from the station Cn, Ct and the mean-of-blades alpha.

## Caveats

- Derived on a steady rectangular/tapered wing with integral sampling, 2-D/3-D kernels and no D&S, against RANS; Phase VI has
  rotation, 3-D relief and a tip chord of 0.355 m (no verification of F_Cl on a rotor at this station).
  F_Cl is applied to the lift part with alpha and c_d unchanged.
- The thesis never shows a station value for Phase VI (Fig. 3.29 only), so this is an extrapolation of its function, not a reproduction.
- The experiment at 0.95 carries a 12.5 % single-tap sensitivity (T6) but its smooth integrations only raise C_N by 0.6-2 %.
- Dynamic stall (ALM) acts on the same station: F_Cl on the post-D&S cn assumes the D&S output is the uncorrected line-model value.
