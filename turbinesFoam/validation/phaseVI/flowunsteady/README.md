# Phase VI FLOWUnsteady — code-to-code diagnostic, NOT a validated reference

FLOWUnsteady (UVLM + reformulated VPM) runs of the NREL Phase VI rotor at
sequence H, 7 m/s (TSR 5.408, 71.878 rpm, rho 1.2337), the 2x2 of Du-Selig
3-D correction (on/off) and drag polar (total / pressure). Purpose: test whether
those two switches explain the gap between Mehr, Alvarez & Ning 2024 (App. A,
Fig. A4: CT 0.459, CQ 0.0699) and our ALM (power -11 %).

**Result (2026-10-17): they do not.** All four converged runs over-predict the
rotor loads (CQ +18 % to +29 % vs the measured 0.0653), and the excess sits at
the tip, insensitive to both switches. Do not quote these runs as a reference
for our ALM.

| tag | CT | CQ | CQ vs exp | station-sum torque vs exp |
| --- | ---: | ---: | ---: | ---: |
| `fu-total-dson` | 0.603 | 0.0797 | +22 % | +17.9 % |
| `fu-total-dsoff` | 0.574 | 0.0773 | +18 % | +14.7 % |
| `fu-pressure-dson` | 0.601 | 0.0844 | +29 % | +25.1 % |
| `fu-pressure-dsoff` | 0.573 | 0.0815 | +25 % | +21.1 % |

Last-revolution means of 10 revolutions; the convergence gate (CT and CQ change
< 1 % per revolution over the last 2) passes on all four with < 0.1 %/rev.

Per station (`scripts/compareFlowUnsteadyStations.py`):

- r/R 0.95: F'n +72 %, F't +93 % to +99 % in every run; 0.80: +15 %. The tip
  alone is +12.9 points of the +17.9 % station-sum torque excess (total, DS on).
  The force angle at 0.95 is ~1 deg above the experiment's (less induction): the
  tip vortex is under-resolved at this fidelity (sigma R/10, n 50) with the
  Prandtl factor off. That is an inference; no run isolates it yet.
- Du-Selig only moves the root: F'n at r/R 0.30 +5 % (off) vs +29 % (on).
- The pressure-drag polar only moves F't (+2 to +6 N/m at mid-span), never F'n.

## Working configuration

`phaseVI.jl` runs with `turbine_flag=false`, input pitch = -(twist + 3 deg),
`Vinf = [-7, 0, 0]`, `CW=false`, positive RPM, torque reported as -torque
(propeller sign). Evidence: `signScan.jl` (wake-free, 16 combinations) — only
this combination gives a physically consistent global blade force; with
`turbine_flag=true` the tangential component of `DistributedLoad` is flipped
(drag/lift 0.74, force.velocity < 0) and corrupts the bound circulation fed to
the VPM. `rotationProbe.jl`: a positive `rotate` moves the blade along
-x_local, as `calc_inflow` assumes. Input sweep = +chord_mount x chord
(`_generate_blade` negates sweep); `geometry.csv` archives the generated LE/TE
and the driver asserts LE x < 0 < TE x.

Kept FLOWUnsteady defaults: Du-Selig via `apply_correction3D` (the `ds=` switch),
Viterna on, Prandtl factor off, no hub/tip correction; n 50, 72 steps/rev,
2 particles/step, RK3, no SFS, inviscid VPM, sigma_surf R/10, relaxation 0.5,
fountain suppression for 3 revolutions. Polars: S809 OSU Re 1e6 within
|alpha| <= 20.1 deg. Mehr 2024 does not state its polar or 3-D correction, so
none of the four runs is "the" Mehr setting.

## Reproduce

From the repository root (`runs/` is git-ignored; a run directory must not exist):

```sh
python3 turbinesFoam/validation/phaseVI/scripts/buildFlowUnsteadyDatabase.py \
  turbinesFoam/validation/phaseVI/flowunsteady/runs/db-total --drag total   # or --drag pressure
sbatch --output=turbinesFoam/validation/phaseVI/flowunsteady/runs/%j.out \
  --error=turbinesFoam/validation/phaseVI/flowunsteady/runs/%j.err \
  turbinesFoam/validation/phaseVI/scripts/slurm/flowunsteady-production.slurm \
  turbinesFoam/validation/phaseVI/flowunsteady/runs/db-total ds=on 10 fu-total-dson
```

Driver arguments: `DB_DIR ds=on|off NREVS TAG`. The production launcher asks for
`--nodes=1 --ntasks=24 --time=10:00:00` (24 Julia threads; with `--ntasks` alone
Slurm spreads the tasks over several nodes and the single-node guard aborts).
10 revolutions took 5 h 17 min to 5 h 25 min; cost per revolution grows with
wake age (165 s for revolution 1, 4400 s for revolution 10). The smoke launcher
`scripts/slurm/flowunsteady.slurm` targets `sequana_cpu_dev` (20 min).

Analysis (read-only):

```sh
cd turbinesFoam/validation/phaseVI
python3 flowunsteady/check_smoke.py flowunsteady/runs/fu-total-dson
python3 scripts/compareFlowUnsteadyStations.py flowunsteady/runs/fu-total-dson \
  [--step 720] [--alm-dir runs/alm-U7-coarse-p21]
```

`check_smoke.py` prints last-revolution means, per-revolution CT/CQ/CP, the
convergence gate, the independent force.velocity power, and wall time per
revolution; it exits 1 on a wrong geometry or extraction sign.
`compareFlowUnsteadyStations.py` reads the saved `*_vlm.<step>.vtk` of both
blades (`Ftot`/`L` are N/m including density), prints F'n/F't and the inflow
angle at r/R 0.30-0.95 next to the experiment (and our ALM with `--alm-dir`),
the force x arm table, and a units check of the blade integrals against the
run's own `power.csv` (agreement within 0.3 % in thrust, 1.1 % in torque).

## History

The first smoke (jobs 11617318/11617324, `turbine_flag=true`, PyCall finalizer
SIGSEGV and its GC workaround, the failed extraction-sign check) is documented
in this file at commit `fa9196f`; the driver keeps the GC workaround (automatic
GC off inside threaded VPM kernels, collection between steps).
