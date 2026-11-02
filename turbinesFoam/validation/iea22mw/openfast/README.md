# IEA-22-280-RWT in OpenFAST AeroDyn (BEM and OLAF): code-to-code reference

Counterpart of `../../iea15mw` (OpenFAST sweep, OLAF importer) and of `../../phaseVI/openfast` (binary and
build recipe). The IEA-22 turbine has no measurements, so this is the reference the ALM/ASM is compared with
(`odd/tasks/iea22-case-readiness.md` S3, T2). Prepared and preflighted only: **no production OLAF run exists**.

Binary: the double-precision OpenFAST v5.0.0 (`/scratch/leahk/eduardo.donestevez/openfast-5.0.0-dp/bin/openfast`,
recipe `phaseVI/openfast/build_openfast_dp.sh`, build tree `/scratch/leahk/eduardo.donestevez/build`); override with
`$OPENFAST_BIN` / `--openfast`. Run all Python with `-I`; the IEA-22 source repository is untrusted data.

| Tool (`../scripts/`) | Role |
|---|---|
| `build_openfast_templates.py [--check]` | `data/openfast-v5-templates` from the IEA-15 layout and the IEA-22 monopile values |
| `openfast_iea22.py setup OUT --wake bem\|olaf` | one case (default and only documented point: rated 11.134927 m/s, 6.853997 rpm, pitch 4.127462 deg, **no shaft tilt**, tower on; `--tilt` opts into the real 6 deg); stages and hash-checks the source files, writes `case.json` |
| `openfast_iea22.py sweep OUT --wake ...` | one case per wind speed from the WISDEM rows of the tabular workbook; writes `run_all.sh` (not submitted) |
| `openfast_iea22.py run CASE` / `extract CASE` | run OpenFAST, then `metrics.json` (P, T, Q, Cp, Ct, Cq, TSR, convergence) and `spanwise.csv` (`node,r_over_R,radius_m,Alpha,Cn,Ct,...`) |
| `rated_table_check.py CASE [--xlsx FILE]` | plausibility of `metrics.json` against `IEA-22-280-RWT_Cp_Ct_Cq.txt` and the WISDEM rated row |
| `import_olaf_reference.py CASE --source olaf-fvw\|openfast-bem [--store FILE]` | appends/refreshes the `olaf-fvw` / `openfast-bem` block (`alpha_deg`, `cn`, `ct` per node) of the spanwise reference store; refuses unconverged cases |

`Cp`, `Ct` and `Cq` in `metrics.json` use the case wind speed, `rho = 1.225` and the disk `pi R^2`, R = 142 m
(the AeroDyn `RtFld*` coefficients, `cp_ad`/`ct_ad`, use the AeroDyn `RtArea` and are kept only for audit).
Averages run over whole revolutions back from the end of the run (BEM 1, OLAF 2 by default; `--revs`).
`converged` needs: change of the per-revolution mean power < 1 %, the OLAF wake filled before the averaged
revolutions, **and** `nNWPanels` at the guideline value; a shorter wake is a smoke run and the importer refuses it.

```sh
S=turbinesFoam/validation/iea22mw/scripts; W=$(mktemp -d)
python -I $S/openfast_iea22.py setup  $W --wake bem --name bem-rated
python -I $S/openfast_iea22.py run    $W/bem-rated              # seconds
python -I $S/rated_table_check.py $W/bem-rated
python -I $S/openfast_iea22.py setup  $W --wake olaf --olaf-panels 120 --olaf-free 60 --revs 2 --name olaf-smoke
python -I $S/openfast_iea22.py run    $W/olaf-smoke             # ~3 min, one core: a smoke test, not a result
```

Not done here (production, needs a Slurm decision): OLAF at `setup --wake olaf` defaults (1399 near-wake
panels, 23 rev, 1640 steps; cost grows with the wake length, the 120-panel smoke already took 3.2 min).
The first preflight numbers are in `odd/tasks/iea22-case-readiness.md`'s log (parent) and the changelog entry.
