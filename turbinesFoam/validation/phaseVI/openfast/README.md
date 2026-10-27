# Phase VI in OpenFAST AeroDyn (BEM and OLAF): code-to-code arbiter of the v1.3 ALM

OpenFAST v5.0.0 built in **double precision** by `openfast/build_openfast_dp.sh` (GCC 14.2,
static reference BLAS/LAPACK, no OpenMP; owner decision 2026-10-27) at
`/scratch/leahk/eduardo.donestevez/openfast-5.0.0-dp/bin/{aerodyn_driver,openfast}`
(override with `$OPENFAST_ENV` / `--openfast-env`)
runs the NREL Phase VI rotor as a rigid, tower-less, uniform-inflow rotor with the
**same inputs as the v1.3 ALM** and two wake models: AeroDyn **BEMT** (`Wake_Mod=1`)
and **OLAF**, the free vortex wake (`Wake_Mod=3`). It is an independent
implementation to arbitrate the ALM, not a tuned model: no coefficient is adjusted
towards the data. Task: `odd/tasks/v13-adoption-asm.md` T9 (builder, comparator,
tests) and T10 (the runs).

**The AeroDyn BEM is the repository's only BEM** (owner, 2026-10-27, `odd/tasks/v13-adoption-asm.md` S7).
The former in-house BEM was removed: it applied the S809 polar on the cylindrical root
(r < 1.0675 m), see L11 of that file. `scripts/quantifyUncertainty.py` uses `--wake bem` with
`--inflow-scale` (inflow x (1 + increment), fixed rpm) for the blockage and VTUN sensitivities, with
the U^3/U^2 bound as fallback when `aerodyn_driver` is not found (`--openfast-env`, `$OPENFAST_ENV`).

Files (all generated from repository data; nothing here is hand-edited):

| Path | Role |
|---|---|
| `scripts/buildAeroDynCase.py` | `--sequence S\|H --speed N --wake bem\|olaf [--inflow-scale F] --out DIR`: writes the complete driver case and `case.json` (every derived input with its source) |
| `scripts/compareAeroDyn.py` | `--case DIR`: power, thrust, torque, Cn/Ct/alpha at r/R 0.30/0.47/0.63/0.80/0.95, error % vs the experiment, convergence; prints a table, writes `metrics.json` |
| `scripts/slurm/aerodyn.slurm` | one case: build, `aerodyn_driver`, compare (POSIX sh, `--ntasks=1`) |
| `openfast/submit_matrix.sh` | the 10 cases (dry run by default, `--submit` to queue) |
| `scripts/verifyAeroDyn.py` | the BEM against the Phase VI tables (S curve, pitch sweep, fixed yaw), one case per measured point with its own rpm, density, pitch and yaw; `analysis/aerodyn-verification/` |
| `openfast/rtestAeroDyn.py`, `openfast/comparePrecision.py` | the installed `aerodyn_driver` against the r-test v5.0.0 BEM references; single vs double precision on the Phase VI points |
| `tests/test_aerodyn_case.py` | geometry/sign pin against `element_data`, polar round trip, per-point inputs, option set, comparator on synthetic output |

## Template provenance

Input formats changed between OpenFAST versions, so the files follow v5.0.0 only.
Starting points (fetched as data from `github.com/OpenFAST/r-test`, tag `v5.0.0`,
`modules/aerodyn/`, plus the v5.0.0 docs `docs/source/user/aerodyn{,-olaf}/`):

- `ad_BAR_OLAF/ad_driver.dvr`: driver layout (`AnalysisType=1`, basic HAWT format).
- `ad_BAR_OLAF/OpenFAST_BAR_00_AeroDyn.dat`: AeroDyn primary file layout and the nodal-output block.
- `ad_BAR_OLAF/OLAF.dat`: OLAF file layout.
- `BAR_Baseline/OpenFAST_BAR_00_AeroDyn_blade.dat`: blade file columns.
- `BAR_Baseline/Airfoils/BAR0_AeroDyn_Polar_07.dat`: airfoil file header (AirfoilInfo v1.01.x).
- `aerodyn-olaf/RunningOLAF.rst` ("Guidelines"): time step, wake length, regularisation.

Everything else (values) comes from the repository, see "Like-for-like inputs".

## Like-for-like inputs (`case.json` records the source of each)

| Quantity | Value | Source |
|---|---|---|
| Rotor | rigid, 2 blades, `Precone=0`, `ShftTilt=0`, `Overhang=0`, `NacYaw=0`, no tower, no nacelle | ALM has none of them (`README.md` limitations) |
| R, hub radius | 5.029 m, 0.5083 m (`HubRad`) | `config/case.yaml`; first row of `phaseVI_blade.csv` = ALM `hubRadius` |
| Rotor speed | `tsr * U / R` (`RotSpeed`, rpm) | `config/case.yaml` kinematics, the ALM `tipSpeedRatio`; `comparePhaseVI` window uses the same |
| Air density | experiment `rho_kg_m3` of the measured row (`FldDens`) | `data/experiment/uae6-archive/sequence_{S,H}_performance.csv`, as `comparePhaseVI --rho auto` |
| Inflow | `CompInflow=0`, `HWindSpeed=U`, `PLExp=0` (uniform) | |
| Pitch | `BldPitch(1)=3.0` and tip reference | v1.3 definition of record (`config/model-definition.yaml`) |
| Blade stations | 85 nodes = the rows of `element_data.blade_element_rows` with `blade_dz 0.05` (the v1.3 gate runs, `run.json`) | `data/geometry/phaseVI_blade.csv` |
| Chord | row chord | same rows |
| Twist | `BlTwist = -mounting - pitch`, so that **`BlTwist + BldPitch = -mounting`** at every node | see sign note |
| Airfoil | node radius < 1.0675 m: `cylinder` (Cl 0, Cd 1.1); outboard `S809` | ALM `elementProfiles` (`ELEMENT_CYLINDER_END`) |
| Polar | `S809_OSU_Re1M_total.dat`, converted verbatim to one AeroDyn table | v1.3 polar, `liftReCorrExp 0` |

**Sign note.** The turbinesFoam mounting angle is `-(twist - twist_tip + 3 deg)`
(tip mounting -3.0 deg); AeroDyn's `BlTwist` and `BldPitch` are positive towards
feather (docs: "positive to feather, leading edge upwind; the blade-pitch angle will
be added to the local twist"). The sum is therefore the *negative* of the ALM mounting
angle. `test_twist_plus_pitch_is_minus_the_alm_mounting_angle` pins this against
`element_data` for both pitch references; the tip node has `BlTwist = 0` and a 3.0 deg
pitch.

**Nodes.** AeroDyn requires the first node at `BlSpn = 0` (the root), so its nodes sit
on the stations bounding the ALM elements (the ALM elements are the segment midpoints
between them). Node outputs are linearly interpolated in r/R at the five stations, the
same way `comparePhaseVI.interpolate` treats the ALM element profile.

**Cm.** The OSU total table has its own Cm column (0 where the source has none); it is
passed through, but `UseBlCm=False`, so it has no effect on Cn, Ct, power or thrust.

## Option table (v5.0.0 names)

AeroDyn primary file (`aerodyn.dat`):

| Option | BEM | OLAF | Reason |
|---|---|---|---|
| `Wake_Mod` | 1 | 3 | BEMT / OLAF |
| `TwrPotent`, `TwrShadow`, `TwrAero`, `NacelleDrag` | 0, 0, False, False | same | the ALM has no tower |
| `BEM_Mod` | 2 | 2 | v5 recommended polar BEM; also fixes the output coordinate system for every `Wake_Mod`; identical to 1 with zero cone/sweep/tilt |
| `Skew_Mod` | 0 | n/a | yaw 0, tilt 0, cone 0: no skewed inflow, model off |
| `TipLoss`, `HubLoss` | True, True | unused | Prandtl tip and hub loss, as requested |
| `TanInd`, `AIDrag`, `TIDrag` | True, True, True | unused | tangential induction, drag in axial and tangential induction |
| `DBEMT_Mod` | 0 | n/a | no dynamic wake, steady points |
| `IndToler`, `MaxIter` | default, 100 | n/a | defaults |
| `SectAvg` | False | False | no shear |
| `UA_Mod` | 0 | 0 | quasi-steady airfoil aerodynamics (ALM: no dynamic stall) |
| `AoA34` | False | False | angle of attack at the aerodynamic centre node; only matters with UA |
| `AFTabMod` | 1 | 1 | first (only) table, no Reynolds interpolation, like `liftReCorrExp 0` |
| `InterpOrd` (airfoil files) | 1 | 1 | linear in alpha, as the ALM `profileData` |
| `UseBlCm` | False | False | Cm cannot enter the forces compared |
| `BlCrvAC`, `BlSwpAC` | 0 | 0 | AC on the pitch axis. The ALM places the quarter chord 0.05 c (0.3 c mount) off the pitch axis; < 0.03 m, ignored (OLAF only) |
| `CompInflow`, `PLExp` (driver) | 0, 0 | 0, 0 | steady uniform inflow |
| `KinVisc`, `SpdSound` (driver) | 1.5e-5, 340.3 | same | inert: single table, no UA; only the output `Re` uses them |

Driver: `AnalysisType=1`, `BaseMotionType=0`, `OutFileFmt=1` (text `ad_driver.out`).
BEM: `DT = period / 36`, `TMax = 3` periods; the steady solution is averaged over the last
whole revolution. Outputs: `RtAeroPwr`, `RtAeroFxh`, and the nodal `Alpha`, `Cn`, `Ct`,
`Cl`, `Cd`, `AxInd`, `TnInd`, `Vrel` of blades 1 and 2 (the driver names them `AB1N001Cn`).

OLAF (`OLAF.dat`, from the "Guidelines" section of the v5.0.0 OLAF docs):

| Option | Value | Reason |
|---|---|---|
| `DTfvw` = driver `DT` | `6 deg / (6 rpm)` = period / 60 | guideline: 6 deg per step |
| `nNWPanels` | `max(4 D / (0.5 U dt), 10 revolutions)` | guideline: wake >= 4 D and >= 10 revolutions, `U_c = 0.5 U` (`k_a a = 0.5`); 725 (S 8) to 1154 (S 5) panels, 12 to 19 revolutions |
| `nNWPanelsFree` | `2 D / (0.5 U dt)` | guideline asks >= 1 D free; the rest is the frozen near wake that mitigates truncation |
| `nFWPanels`, `nFWPanelsFree` | 0, 0 | no far wake (a frozen near wake needs a zero free far wake) |
| `CircSolvMethod` | default (1, Cl-based) | uses the same polar as the ALM |
| `FullCircStart` | one period | gentle start of the circulation |
| `FreeWakeStart` | default (0) | free from the start |
| `RegDeterMethod`, `WakeRegFactor`, `WingRegFactor` | 3 (span), 0.6, 0.6 | guideline: 0.6 of the spanwise step (the blade nodes) |
| `WakeRegMethod`, `RegFunction`, `CoreSpreadEddyVisc` | default (3 age, 3 Vatistas), 1000 | 1000 is the guideline for multi-MW rotors and smooths the wake of a steady run |
| `VelocityMethod` | 2 (particle tree) | default, fast |
| `TMax` | `nNWPanels` steps + 4 revolutions | wake full, then 4 revolutions to average |

OLAF wake extent was taken from the guideline, not tuned; it is recorded per case in
`case.json["olaf"]` (panels, wake length in m and revolutions, steps).

## Comparison definitions (same as `comparePhaseVI.py`)

| Quantity | AeroDyn | `comparePhaseVI` |
|---|---|---|
| Power | `RtAeroPwr` (blades only, no losses) | `power_kw` (`cp q U`) vs `rotpow_kw` |
| Thrust | `RtAeroFxh` (blades only) | `thrust_n`, blade scope, vs `eaeroth_n` |
| Torque | power / omega | `torque_nm` vs `lsstqcor_nm` |
| Cn, Ct | nodal `Cn`, `Ct` (chord line; `Cn = Cl cos a + Cd sin a`), mean of blades 1 and 2, linear in r/R | `spanwise_profile`: the same chord-referenced formulas |
| Error | `(sim - exp) / exp`, bands 15 % (turbine), `max(0.15, 0.2 abs(exp))` (spanwise) | same |
| Experiment | `data/experiment/uae6-archive` (S 5-8 m/s, H 7 m/s) | the gate comparison's `--experiment` |

Averages run over **whole revolutions** counted back from the end of the run
(`--revolutions`, default 1 for BEM, 4 for OLAF). The convergence figure is the change of the
per-revolution mean power and of Cn at r/R 0.95 between the last two revolutions
(< 1 % = converged); an OLAF run is additionally not converged unless those two revolutions
lie after the `nNWPanels` steps that fill the wake. Report such a run as "not a result".

## Run

```sh
cd turbinesFoam/validation/phaseVI
# one case by hand
python3 scripts/buildAeroDynCase.py --sequence S --speed 7 --wake bem --out /tmp/ad-bem-S7
(cd /tmp/ad-bem-S7 && /scratch/leahk/eduardo.donestevez/openfast-5.0.0-dp/bin/aerodyn_driver ad_driver.dvr)
python3 scripts/compareAeroDyn.py --case /tmp/ad-bem-S7

# all 10 cases (S 5, 6, 7, 8 and H 7, BEM and OLAF): review, then queue
sh openfast/submit_matrix.sh
sh openfast/submit_matrix.sh --submit
```

Each job writes the case under `runs/aerodyn-<wake>-<sequence>U<speed>/` (refused if it
exists), `aerodyn_driver.log`, `compare.txt` and `metrics.json`. BEM takes seconds
(`sequana_cpu_dev`); OLAF runs on one core. Smoke measurement on a login node (S 7 m/s):
about 1 step per second while the wake was growing to 300 panels (60 steps per revolution),
so a production case is on the order of 0.5 to 1.5 h (S 5: 1394 steps, S 6: 1203, S 7 and
H 7: 1067, S 8: 965), requested as 3 h on `sequana_cpu` / `sequana_cpu_bigmem`, alternating
so both partition job limits are used (`AGENTS.md`).

## Limits

- AeroDyn's tip loss is Prandtl; the ALM uses Dag and Sorensen with the Glauert tip factor
  off. The two are different models by design, which is what the arbiter measures.
- The BEMT uses AeroDyn's own solver and induction handling, which this file does not
  switch; differences from any other BEM in hub-loss form, high-induction handling or node
  placement are implementation differences, to be located before any physical reading.
- Binary: the double-precision build passes the r-test v5.0.0 AeroDyn-driver cases, BEM 9/9 and OLAF 7/7
  (`ad_Sphere_OLAF` has no reference). The conda-forge package (`/scratch/leahk/eduardo.donestevez/conda-envs/openfast`)
  is single precision (`-DDOUBLE_PRECISION=OFF`) and passes BEM 2/9 and OLAF 2/7; on the Phase VI BEM points the
  two agree to 2e-4 at 5-8 m/s (`analysis/aerodyn-verification/README.md`). Rebuild:
  `sh turbinesFoam/validation/phaseVI/openfast/build_openfast_dp.sh` (about 10 min, `BUILD-INFO.txt` in the prefix).
- The measured loads include tower shadow, nacelle and blockage; none is in the ALM or here.
