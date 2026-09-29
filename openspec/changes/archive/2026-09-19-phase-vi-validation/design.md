# Design: NREL Phase VI validation case package (`phase-vi-validation`)

Change: `phase-vi-validation` — project `of-plugins` — 2026-09-19. Artifact store: hybrid.
Status: design (HOW). Satisfies `specs/phasevi-validation-case/`,
`specs/phasevi-data-provenance/`, `specs/phasevi-run-and-compare/`.

## 1. Technical Approach

Add `turbinesFoam/validation/phaseVI/` as a self-contained, additive package. A
YAML single source of truth (`config/case.yaml`) renders the uniform-inflow case
(boundary conditions, 18-block Cartesian `blockMeshDict`, solver dictionaries,
decomposition, and the ALM/ASM `fvOptions` twins) through a generator adapted
from the SAL scaffold (`mttbrbr/single-actuator-line`, main `8284be8c…`,
GPL-3.0-or-later). Committed derived data carry per-directory `PROVENANCE.md`.
One runner selects a twin; one comparison tool merges simulation output with the
WDH measured rows and fails loudly. Only Stage 0 may execute (development queue);
Stages 1–3 are prepared, never submitted.

No `turbinesFoam/src/` change; no solver in CI; no regression gate.

## 2. Data Flow

```
config/case.yaml ──generate_case.py──► case/{0.org,constant,system}
      │                                     │            │
      │                        fvOptions.ALM / .ASM    blockMesh+topoSet
      ▼                                     │            │
data/geometry ──makeElementData.py──► elementData      ▼
data/polars (A-3..A-8, TP-442-7817) ──► profile data   mesh (D/32|D/48|D/64)
data/experiment (wdh .xls, 0° yaw) ────► committed CSV  │
                                            runPhaseVI.sh ──► runs/<id>/
                                                              │  turbine.csv
                                                              │  actuatorLineElements/*.csv
                                                              ▼
                              comparePhaseVI.py ◄── data/experiment/*.csv
                                    │
                                    ├─ metrics.json (+bands, ρ, gates, CM note)
                                    ├─ turbine_comparison.csv / spanwise_comparison.csv
                                    └─ sign_gate.json ──► production launch gate
```

## 3. Architecture Decisions

| # | Decision | Choice | Alternatives rejected | Rationale |
|---|----------|--------|-----------------------|-----------|
| D1 | Domain re-centring | `x∈[−5D,15D]`, `y∈±4D`, `z∈hub±2.5D` (hub 12.192 m), all far field slip/symmetry | keep ground/ABL (scaffold) | Uniform tunnel approach flow; removes Mann/`hipersim`; spec pins extents |
| D2 | z-mesh fix | z split **at the hub**: blocks `[hub−2.5D, hub]` and `[hub, hub+2.5D]`, 52/78/104 cells per block (coarse/fine/ultra), grading `[1/2.2404, 2.2404]`; hub-adjacent cell = D/32, D/48, D/64 | reuse scaffold ground-based `[0,2,5]D` z split | With a ground-based split the rotor straddles a coarse block; the hub-centred split keeps the whole disk in fine cells and preserves the spec cell counts (6,674,304 / 22,525,776) |
| D3 | Turbulence | URANS `pimpleFoam` + `kOmegaSST` headline; `kOmegaSSTIDDES` optional Stage 3 | IDDES headline (4–20× cost, delays results); kEpsilon (weak claim) | Standard for Phase VI integral loads; affordable; spec requires URANS headline |
| D4 | Mesh ladder | D/32 dev + Stage 0, D/48 headline + nChordwise sweep, D/64 optional | single mesh | Cost/fidelity; ASM strips sub-cell at every affordable mesh (documented) |
| D5 | Polars | Baseline = TP-500-29955 **Table A-7** (OSU Re 1 M, total drag). Multi-Re sensitivity = **TP-442-7817 single-source OSU clean series** 0.75/1/1.25/1.5 M; CSU/DUT documented but not blended | scaffold `S809_Re1M_extended` (flipped Cm, suspect Cd); cross-source blends (kinks) | Single-source fidelity; spec forbids scaffold reuse |
| D6 | End effects | `endEffects on; Glauert; tipEffects on; rootEffects on` | Shen (variant), off | 2D measured polars require 3D tip/root correction |
| D7 | Dynamic stall | OFF at 7 m/s headline; optional Leishman–Beddoes at 13–25 m/s | ON everywhere | 7 m/s near-attached; LB only matters for stall |
| D8 | Spanwise CM | Excluded from headline; `metrics.json` records the reason; follow-up change adds `momentCoefficient_` to the element writer | compare blade-mean cm from `actuatorLines/*.csv` | Element CSV has no `cm`; blade-mean is not spanwise, comparison would mislead |
| D9 | Tower | **Not modelled.** Rotor+hub only; EAEROTH is blade-pressure-only and shaft torque has no tower term; A-15 tower dims (11.5 m, OD 0.6096/0.4064 m) recorded in PROVENANCE; tower-shadow noted as an optional Stage-3 variant | scaffold tower (x=−1.401 m placement unverified, downwind of an upwind rotor) | Placement/orientation for upwind rigid Sequence H is not numerically tabulated; forces do not enter the headline metrics |
| D10 | Density | Dimensional comparison; `ρ` per speed from the row's `WTBARO`/`WTATEMP` ideal gas (`ρ=p/(287.058·T[K])`), printed in every output; `--rho` override | coefficient-only comparison; fixed 1.225 | Dimensional measured values depend on test-day ρ (1.219–1.253 across the set) |
| D11 | TSR source | Frozen table from the spec (`5.408/3.798/2.920/2.530/1.898/1.521`); derived from canonical row RPM via `TSR=ΩR/U` | scaffold fixed 5.3894 at all speeds | `turbineALSource` sets `omega_=TSR·\|Uinf\|/R`; measured rows vary per speed |
| D12 | Canonical experimental rows | Sequence H/S, `\|YAW\|≤0.5°`, lowest `Repetition`: `h0700000, h1000000, h1300000, h1500000, h20m0000, h2500000, s0700000` | first `Yaw=='0000'` only (misses `m000`) | Deterministic, reproduces the spec TSR values (20 m/s → 1.898 from h20m0000) |
| D13 | Generated files | `case/` skeleton **committed** (reviewable twins, runnable); meshes, `processor*`, `runs/`, logs gitignored; `--check` enforces YAML↔files consistency | commit nothing (unreviewable twins); commit meshes (huge) | Repo convention keeps `case/` dictionaries in git (SAL) |
| D14 | Delivery | Additive single change; `turbinesFoam/src/` untouched | — | Rollback = delete/revert |

### File changes

| File | Action | Description |
|---|---|---|
| `turbinesFoam/validation/phaseVI/**` | Create | Case generator, committed case skeleton, data (+PROVENANCE), scripts, README |
| `turbinesFoam/tests/test_phasevi_data.py`, `test_phasevi_case.py` | Create | Pure-Python data sanity + generator/rendering contracts |
| `README.md` (root) | Modify | Document the validation package and staged plan |
| `CHANGELOG.md` (root) | Modify | `Files:`/`Problem:`/`Fix:` entry |
| `turbinesFoam/src/**` | Untouched | ASM/ALM already shipped; CM column is a follow-up change |

### Metric definitions (fixed against TP-500-29955 before any result)

| Metric | NREL definition (source) | Simulation equivalent |
|---|---|---|
| `LSSTQCOR` | Upwind Eq. 27: `LSSTQ + 252.82·cos(B3AZI + 177.35)` Nm; gravity/bending sine correction of the low-speed shaft strain gauge; tabulated means are already corrected | Time-mean `Q = ct·½ρAU∞²` (turbine.csv `ct` is the **torque** coefficient, rows include hub moment) |
| `ROTPOW` | Eq. 30: `ROTPOW = LSSTQCOR·RPM·π/30000` **kW**; aerodynamic rotor power from corrected shaft torque; **excludes** drivetrain losses (`GENPOW` is separate) | `P = cp·½ρAU∞³` (cp = ct·TSR) |
| `EAEROTH` | Eq. 13: `EAEROTH = 2·Σₙ₌₁⁵ C_TH·QNORM·area` N; pressure integration only, panels 25% span→tip, no tip loss; **excludes skin friction, hub, tower**; positive downwind | `T_blade = Σ_blades cd_bladeN·½ρAU∞²` from per-blade columns (blade-only). `T_rotor = cd·½ρAU∞²` (adds hub) reported as a labelled secondary. `--match-eaeroth-span` restricts to elements `r/R≥0.25` |
| Spanwise | `CN/CT` from pressure integration (Eqs. 8–9) at 30/47/63/80/95% span | Element `c_ref_n`/`c_ref_t`, time-mean, mapped `r/R = 0.5083/R + root_dist·(1−0.5083/R)` (`root_dist` is blade-normalized, **not** r/R), then linearly interpolated to the five stations |
| `CM` | Eq. 10 | Not reported (D8) |

Averaging: revolutions 4–12 (discard 0–4); `T_rev = 2πR/(TSR·U∞)` (matches the
actual `omega_`, not `60/RPM`); 1-rev rolling means of `cp`/`cd`; flag
"not converged" when `(max−min)/|mean| > 1%`. Bands (fixed in code and README):
turbine power/torque/thrust ±15%; spanwise max(0.15, 20% of measured); sign gate
on `c_ref_n`/`c_ref_t` vs measured at all five stations.

## 4. Package Layout

```
turbinesFoam/validation/phaseVI/
├── README.md                     # setup, staged plan, metrics, limitations
├── config/case.yaml              # single source of truth
├── tools/case_config.py          # load/validate YAML; derived quantities
├── tools/generate_case.py        # renderer + --check (stale) mode
├── tools/element_data.py         # blade/root profile + elementData rows
├── case/                         # committed generated skeleton
│   ├── 0.org/{U,p,k,omega,nut}
│   ├── constant/{transportProperties,turbulenceProperties}
│   └── system/{blockMeshDict,topoSetDict,controlDict,decomposeParDict,
│               fvSchemes,fvSolution,fvOptions.ALM,fvOptions.ASM}
├── data/
│   ├── geometry/phaseVI_blade.csv (+PROVENANCE.md)
│   ├── polars/{S809_OSU_Re1M_total.dat,S809_multiRe.dat,raw/*.csv,PROVENANCE.md}
│   └── experiment/{sequence_H_performance.csv,sequence_H_spanwise.csv,
│                   sequence_S_performance.csv,sequence_S_spanwise.csv,PROVENANCE.md}
├── scripts/{makeElementData.py,buildPolars.py,extractExperimentalData.py,
│            runPhaseVI.sh,stage0.sh,comparePhaseVI.py,check_environment.sh,
│            mesh.sh,slurm/{stage0.slurm,production.slurm}}
└── runs/                         # generated run dirs (gitignored)
turbinesFoam/tests/test_phasevi_data.py   # pure-Python data sanity
turbinesFoam/tests/test_phasevi_case.py   # generator/rendering contracts
```

Generator CLI: `generate_case.py [--mesh coarse|fine|ultra] [--speed <7|10|13|15|20|25>]
[--profile production|smoke] [--check]`. `--check` re-renders in memory, diffs
against disk, never writes, exits 1 on missing/stale. Rendered files carry
`// Generated from config/case.yaml. Do not edit by hand.`

`case.yaml` keys: `project{name,openfoam_versions}`; `turbine{diameter,radius,
hub_height,pitch_deg,n_blades,n_elements,axis,vertical_direction,
gaussian_mesh_factor,position_D}`; `kinematics{sequence,speeds{U:{tsr,rpm,row}}}`;
`domain_D{x,y,z}`; `mesh.resolutions.{coarse,fine,ultra}{x,y,z:{breaks_D,cells,
grading}}`; `solver{application,turbulence_model,delta_t{...},end_revolutions,
discard_revolutions,write_interval_rev,purge_write}`; `inflow{velocity,
turbulence_intensity,mixing_length_D}`; `decomposition{number_of_subdomains}`;
`actuator{end_effects{model,tip,root},dynamic_stall{active,model},
n_chordwise_sweep}`.

## 5. Case Generation

**Mesh arithmetic** (verified against both SAL branches; all three resolutions
use `simpleGrading` per z block `[0.4464, 2.2404]`, far cell = 2.2404× hub cell):

| Res | Δ hub (m) | x cells (3 blocks) | y cells (3) | z cells (2) | total hexes |
|---|---|---|---|---|---|
| coarse D/32 | 0.3143 | 50/272/60 = 382 | 36/96/36 = 168 | 52/52 = 104 | 6,674,304 |
| fine D/48 | 0.2095 | 75/408/90 = 573 | 54/144/54 = 252 | 78/78 = 156 | 22,525,776 |
| ultra D/64 | 0.1572 | 100/544/120 = 764 | 72/192/72 = 336 | 104/104 = 208 | 53,394,432 |

x grading `[0.160029, 1, 9.252929]`, y `[0.241240, 1, 4.145249]`; z breaks
`[hub−2.5D, hub, hub+2.5D]` = `[−12.953, 12.192, 37.337]` m. 3×3×2 = **18 blocks**,
100% hex. (The proposal's D/64 "≈40 M" is corrected to 53.4 M — the 40 M figure
held z at its D/48 count.)

**Boundary conditions** (6 patches; separate planar patches keep `symmetryPlane`
valid): `inlet` patch — U `fixedValue (U 0 0)`, p `zeroGradient`, k/omega
`fixedValue`; `outlet` — U `inletOutlet (0 0 0)`, p `fixedValue 0`, k/omega
`inletOutlet`; `top/bottom/sideMinus/sidePlus` — `symmetryPlane` for all fields
(nut `symmetryPlane`, fallback `calculated` if the runtime rejects it). Inflow
turbulence: `TI=0.5%` (documented choice), `k=1.5(TI·U)²`,
`ω=√k/(Cμ^0.25·ℓ)`, `ℓ=0.07D`. `transportProperties: nu 1.5e-5`.

**Solver**: `pimpleFoam`, `simulationType RAS; RASModel kOmegaSST`. `controlDict`:
`adjustTimeStep off`; Δt = 0.008 / 0.005 / 0.004 s; `endTime = 12·2πR/(TSR·U)`
(≈10.0 s); `writeControl runTime`, `writeInterval = 0.5·T_rev`, `purgeWrite 8`.
Tip-displacement gate `ΩRΔt ≤ Δ_cell` at the blade tip: Δs = 0.303 m at 7 m/s and
≤0.304 m across the whole 7–25 m/s matrix, below the D/32 cell adjacent to the
tip (0.392 m at `|z−hub|=0.5D`, hub-adjacent cell 0.3143 m); likewise 0.189 m <
0.2095 m (D/48) and 0.151 m < 0.1572 m (D/64). The scaffold's 0.03 s is rejected
by a generator validation (`assert ΩRΔt < Δ_hub`). `fvSchemes`: `backward` ddt;
`bounded Gauss linearUpwind grad(U)` for U, `bounded Gauss upwind` for k/omega;
`Gauss linear orthogonal` laplacians (Cartesian mesh). `fvSolution`: GAMG p,
`smoothSolver` U/k/omega, PIMPLE `nOuterCorrectors 1; nCorrectors 2`,
relaxation 0.9/0.7/0.7 (scaffold values).

**topoSet**: one `cellSet` box around the rotor: `[x±0.5D]×[y±1.0D]×[hub±1.0D]`.

**fvOptions twins** (identical except the marked lines; both rendered from one
function with an `element_type` parameter):

```
T1 { type axialFlowTurbineALSource; active on;
  axialFlowTurbineALSourceCoeffs {
    fieldNames (U); selectionMode cellSet; cellSet T1;
    origin (0 0 12.192); axis (-1 0 0); verticalDirection (0 0 1);
    freeStreamVelocity (7 0 0); tipSpeedRatio 5.408; rotorRadius 5.029;
    azimuthalOffset 0;
    dynamicStall { active off; dynamicStallModel LeishmanBeddoes; }
    endEffects { active on; endEffectsModel Glauert;
                 GlauertCoeffs { tipEffects on; rootEffects on; } }
    blades { blade1 { writePerf true; writeElementPerf true;
        elementType actuatorLineElement;          # ASM: actuatorSurfaceElement; nChordwise 5;
        nElements 50; elementProfiles (cylinder×8 S809×42);
        elementData ( <26 stations, pitch = -(twist+3°) > ); }
      blade2 { $blade1; writePerf false; writeElementPerf false; azimuthalOffset 180; } }
    hub { nElements 4; elementProfiles (cylinder);
          elementData ((0 0.5083 1.0166) (0 -0.5083 1.0166)); }
    profileData { S809 { Re 1e6; GaussianCoeffs { chordFactor 0.25;
        dragFactor 1.0; meshFactor 1.0; } data (#include "..."); }
      cylinder { data ((-180 0 1.1 0) (180 0 1.1 0)); } } } }
```

Hub: cylinder diameter 1.0166 m (2× the blade root station 0.5083 m), spanning
±0.5083 m along y; derived from the blade root cutout and documented as a lumped
model (TP-500-29955 has no hub dimensions table). Tower absent (D9).
`decomposeParDict`: `numberOfSubdomains 48; method scotch;` (one 48-core node;
configurable, 96 for 2-node runs). Environment check accepts v2506 **and**
v2412, checks `blockMesh/topoSet/checkMesh/pimpleFoam/decomposePar/mpirun` and
`libturbinesFoam.so`, then runs `generate_case.py --check`.

## 6. Kinematics

| U∞ (m/s) | TSR (frozen) | Ω=TSR·U/R (rad/s) | T_rev (s) | row RPM | canonical row |
|---|---|---|---|---|---|
| 7 | 5.408 | 7.527 | 0.835 | 71.878 | h0700000 |
| 10 | 3.798 | 7.551 | 0.832 | 72.107 | h1000000 |
| 13 | 2.920 | 7.550 | 0.832 | 72.091 | h1300000 |
| 15 | 2.530 | 7.547 | 0.833 | 72.063 | h1500000 |
| 20 | 1.898 | 7.548 | 0.832 | 72.084 | h20m0000 |
| 25 | 1.521 | 7.561 | 0.831 | 72.208 | h2500000 |

Conventions: 2 blades, pitch 3°, `azimuthalOffset 0/180`, axis `(−1,0,0)`,
vertical `(0,0,1)`, mounting `−(twist + pitch)`; `freeStreamVelocity (U 0 0)`.
`rotor_speed_rpm` in YAML is informational only (ω comes from TSR). The frozen
TSR values reproduce the canonical-row formula within ±0.001 (e.g. 10 m/s: spec
3.798 vs derived 3.7974); the data-sanity test asserts |case TSR − row-derived
TSR| ≤ 0.002 for every speed.

**7 m/s sign-verification gate** (`comparePhaseVI.py --sign-gate`, run on the
Stage 0 D/32 7 m/s runs; production submission refuses without a PASS file):
(1) `tsr` in turbine.csv within 1e-3 of the configured TSR; (2) mean `cp>0` and
`cd>0`; (3) time-mean `c_ref_n>0` and `c_ref_t>0` at the five stations (measured
CN/CT are positive at 7 m/s). Any failure → exit 1, `sign_gate.json` FAIL, and
`runPhaseVI.sh --submit` refuses. This catches a mirrored axis/pitch/rotation
before any production cost is spent.

## 7. Data Pipeline

| Output | Source (verified local copies) | Extraction |
|---|---|---|
| `geometry/phaseVI_blade.csv` | TP-500-29955 Table A-1 | Commit the byte-verified copy (sha256 `e678d6c5…`, 26 stations r=0.5083→5.029 m). `chord_mount` is part of the committed geometry (root cylinder 0.50, airfoil 0.30 = the report's 30%-chord pitch/twist axis); `twist_deg_report` is used with the `−(twist+pitch)` conversion |
| `polars/raw/table_A3..A8.csv`, `table_TP442-7817.csv` | Tables A-3..A-8; TP-442-7817 | `buildPolars.py` reads committed raw CSVs (transcribed from the tables) and emits final `.dat`; each row carries α/Cl/Cd/Cm and source tag |
| `polars/S809_OSU_Re1M_total.dat` | Table A-7 (OSU Re 1e6) | Single-Re baseline, total drag, `Re 1e6` |
| `polars/S809_multiRe.dat` | TP-442-7817 (OSU clean) | `ReList (7.5e5 1e6 1.25e6 1.5e6)` + `clData/cdData/cmData` (profileData.C format); CSU A-3..A-5 / DUT A-8 documented but not blended |
| `experiment/sequence_H_performance.csv` | `wt_loads_statistics.xls`, sheet `ldsmean` | One row per canonical row: FileName,U∞,YawToken,YAW,Rep,RPM,TSR,ROTPOW_kW,LSSTQCOR_Nm,EAEROTH_N,WTBARO,WTATEMP,rho; 0°-yaw (`\|YAW\|≤0.5°`) only |
| `experiment/sequence_H_spanwise.csv` | same sheet | FileName,r_over_R∈{0.30,0.47,0.63,0.80,0.95},CN,CT,CM (columns `CN30…CM95`) |
| `experiment/sequence_S_performance.csv`, `sequence_S_spanwise.csv` | same sheet | `s0700000` repeat (performance + spanwise) |

`extractExperimentalData.py` (needs the 17 MB workbook path, not committed)
parses `xlrd`, enforces the YAW/Repetition rule (D12), writes the CSVs, and
prints the row map. Column indices are frozen in a manifest constant
(ROTPOW 61, LSSTQCOR 58, EAEROTH 54, RPM 52, YAW 47, CN30..CM95 63..81,
WTBARO 30, WTATEMP 34). TSR is derived: `RPM·2πR/(60·U)`.

**Correction (must be recorded)**: the exploration table's 20 m/s anchor
(72.064 rpm / 9.219 kW / 1221.49 Nm / 3094.78 N) belongs to `g2000002`
(**Sequence G, teetered**), not `h2000002`. The canonical Sequence H 0° row is
`h20m0000` (RPM 72.0839 → TSR 1.898, 9.3661 kW / 1240.72 Nm / 3152.37 N); the
spec's TSR list is therefore satisfied exactly. `h0700000`/`h2500000` anchors
are unchanged and exact.

`PROVENANCE.md` per directory: DOI/URL, sha256 of the source, table/sheet, row
selection rule, column names, units, extraction date, extraction script, plus
the SAL attribution, NREL citations and the pinned `of-plugins` commit
(`52fd258…`) with the ASM patch note. No PDFs/workbooks committed (test-scanned).

## 8. Run and Compare Tooling

`runPhaseVI.sh -m alm|asm -u <speed> [-mesh coarse|fine|ultra] [--stage0]
[--restart] [--submit]`:
1. validates the (model, speed, mesh) triple against YAML and fails loudly on an
   unsupported value; 2. renders/updates the case; 3. creates
   `runs/<model>-U<UU>-<mesh>/` (hardlink copy of `case/` incl. `constant/polyMesh`
   when present) and installs `system/fvOptions` from the selected twin;
4. `blockMesh`, `topoSet`, `checkMesh` (band from YAML, e.g. 6.6–6.8 M for
   coarse, 22.4–22.7 M fine, 53.0–53.8 M ultra, hex-only, non-orthogonality ≤1e-10);
5. `decomposePar -force`, `mpirun -np 48 pimpleFoam -parallel`;
6. writes `run.json` (git commit, OF version, config hash, model, speed, mesh,
   start time). `--stage0` caps `endTime` at 0.25 rev (≤0.3 spec bound) so a
   48-rank dev job fits the 20-min `sequana_cpu_dev` limit; `--restart` sets
   `startFrom latestTime`. `--submit` is allowed only for `sequana_cpu_dev`
   unless `PHASEVI_LONG_QUEUE_AUTHORIZED=1` is explicitly exported (Stage-1–3
   gate). `scripts/stage0.sh` orchestrates the whole Stage 0: `mesh.sh coarse`,
   `mesh.sh fine` (+`checkMesh`), then `runPhaseVI.sh -m alm|asm -u 7 -mesh coarse
   --stage0` for both models; `scripts/slurm/stage0.slurm` (dev, 20 min, 48 tasks)
   is executable now. `scripts/slurm/production.slurm` (array per
   model×speed×mesh, `--time=24:00:00`, requeue/restart) is committed
   **prepared-only** with no auto-submit path.

`comparePhaseVI.py [--alm-dir …] [--asm-dir …] [--experiment data/experiment]
[--speed 7] [--sequence H|S] [--revolutions 4 12] [--rho auto|<kg/m³>]
[--thrust-scope blade|rotor] [--match-eaeroth-span] [--sign-gate]
[--allow-short-window] [--out results/<id>/]`:
- reads `postProcessing/turbines/0/turbine.csv` and
  `postProcessing/actuatorLineElements/0/*.csv` (per-element time series,
  last-written per element for spanwise; full series for the window mean);
- maps `root_dist`→`r/R` (blade-normalized, formula above), interpolates to the
  five stations; averages revs 4–12; computes the drift flag; applies the
  density (§3/D10) and the metric table of §3; prints/writes turbine + spanwise tables, the band
  per metric, and a limitations block (sub-cell ASM strips, URANS deep-stall,
  high-speed points = trend/onset evidence only).
- outputs: `turbine_comparison.csv`, `spanwise_comparison.csv`, `metrics.json`
  (values, definitions, ρ, window, gates, bands, CM exclusion), `report.txt`.
- fail-loud: missing run dir/turbine.csv/element CSVs/experiment CSV → exit 1;
  window < 4 revs without `--allow-short-window` → exit 2; TSR/config mismatch →
  exit 3. Nothing is averaged from an incomplete window silently.

## 9. Interfaces / Contracts

- YAML schema and `case.yaml` keys: §4. The generator is the only writer of
  `case/`; hand edits are detected by `--check`.
- `fvOptions.ALM` vs `fvOptions.ASM`: byte-identical except
  `elementType actuatorLineElement;` ↔ `elementType actuatorSurfaceElement;` +
  `nChordwise 5;` (test `test_twins_differ_only_in_blade_keys`).
- Element CSV columns (frozen, 19): `time,root_dist,x,y,z,rel_vel_mag,Re,
  alpha_deg,alpha_geom_deg,cl,cd,fx,fy,fz,end_effect_factor,c_ref_t,c_ref_n,
  f_ref_t,f_ref_n`. Turbine CSV: `time,angle_deg,tsr,cp,cd,ct[,cd_<blade>,ct_<blade>]`
  (`ct` = torque coefficient, `cd` = axial force coefficient).
- `runPhaseVI.sh` exit codes: 2 unsupported input, 3 environment/checkMesh,
  4 stale generated case, 5 authorization gate.
- `comparePhaseVI.py` exit codes: 1 missing input, 2 short window, 3 config/TSR
  mismatch, 0 pass (drift/band failures flag in `metrics.json`, they do not hide).

## 10. Failure Modes

| Failure | Detection | Response |
|---|---|---|
| Mirrored rotation/pitch/axis | sign gate §6 | production blocked; fix conventions |
| Wrong workbook row / yaw rows mixed | extraction manifest + anchor tests | fail tests; re-extract |
| Stale generated case | `generate_case.py --check` | exit 1; re-render |
| Non-hex / non-orthogonal mesh | `checkMesh` band | abort before solving |
| Stage 0 divergence | solver log / NaN | `scancel`, delete run dir |
| Drift > 1% | rolling-window gate | flagged "not converged" |
| Short averaging window | window check | exit 2 (except explicit override) |
| Long-queue submission | env gate | refuses without authorization |
| Density mis-stated | `metrics.json` always prints ρ | review before claiming |
| Sub-cell ASM strips | documented limitation | claim limited to chord-averaged behaviour |

## 11. MPI / Decomposition, Performance

48 subdomains (one node, 2×24), `scotch`; D/32 = 139 k cells/rank, D/48 =
469 k; 96-rank option documented. Per exploration compute table (4 000
cell·step/s/core URANS, 48 ranks, 0.75 efficiency): D/32 12 rev ≈ 580 core-h
(≈8 h wall on 2 nodes), D/48 ≈ 3 100 core-h (≈43 h on 2 nodes), D/64 ≈ 9 300
core-h, IDDES D/48 ≈ 10 000 core-h. Stage 0: 0.25 rev D/32 ≈ 12 core-h ≈
15–20 min at 48 ranks (fits the 20-min dev partition). Restart via `latestTime`
bounds each Slurm task at ≤24 h.

## 12. Testing Strategy

| Layer | What | How |
|---|---|---|
| Unit (pure Python) | YAML validation, mesh arithmetic/cell counts, 18 blocks, twins diff, TSR table, tip-constraint assert, topoSet box | `turbinesFoam/tests/test_phasevi_case.py` (pytest, no OpenFOAM) |
| Data | geometry monotone, polar parse/monotone α, experimental anchors (`h0700000` 5.946 kW/789.86 Nm/1132.07 N; `h2500000` 11.951 kW/1580.41 Nm/4028.63 N), TSR mapping (±0.002), provenance fields, no PDF/XLS committed | `turbinesFoam/tests/test_phasevi_data.py` |
| Tooling | density auto, metric formulas, window/drift, fail-loud exit codes, sign gate, root_dist→r/R mapping | pytest with fixture CSVs |
| Integration | `blockMesh` + `checkMesh` at D/32 and D/48; ALM+ASM 0.25 rev at 7 m/s | Stage 0 on `sequana_cpu_dev` only (manual) |
| CI | nothing new | No solver, no regression gate (spec) |

## 13. Threat Matrix

| Threat | Mitigation |
|---|---|
| Unauthorized long-queue submission | `PHASEVI_LONG_QUEUE_AUTHORIZED` gate; production Slurm file prepared-only; no auto-submit |
| Committing restricted/large sources | derived CSVs only; test scans for `*.pdf`/`*.xls*` |
| Silent metric bias | definitions fixed in code, printed with every result; ρ stated |
| Mirrored loads | sign gate blocks production |
| Provenance drift | sha256 + row manifest + PROVENANCE tests |

## 14. Migration / Rollback

No migration. Purely additive: no `turbinesFoam/src/` change, no CI change, no
existing behavior touched. Rollback = single `git revert` of the change commits
(delete the package, tests, and root README/CHANGELOG notes). A diverged Stage 0
run is cancelled and its `runs/` directory deleted; all inputs are in git.

## 15. Resolved Decisions (rationale)

1. **URANS k-ω SST headline + optional IDDES** — integral-load validation at
   affordable cost; IDDES (4–20×) only if Stage 3 budget allows.
2. **Mesh ladder D/32 → D/48; D/64 optional** — D/32 dev/Stage 0, D/48 headline;
   D/64 optional at the corrected 53.4 M cells.
3. **Polars A-7 baseline + TP-442-7817 multi-Re** — coherent single-source
   series avoids cross-source kinks; A-7 total drag is the headline.
4. **Glauert ON** — 2D measured polars need a 3D correction; Shen documented as
   variant.
5. **Dynamic stall OFF at 7 m/s**; optional Leishman–Beddoes at 13–25.
6. **CM excluded** — no element `cm` column; follow-up source change documented.
7. **Tower not modelled** — geometry dims are sourced but the upwind placement is
   not; EAEROTH excludes tower and shaft torque is unaffected; recorded in
   PROVENANCE, tower-shadow optional Stage 3.
8. **20 m/s canonical row corrected** to `h20m0000` (spec TSR 1.898 satisfied);
   exploration's 20 m/s numbers are the Sequence G row `g2000002`.

## 16. Open Questions for Tasks / Apply

- [ ] Confirm the 20 m/s anchor correction (exploration `h2000002`→`g2000002`
      mislabel; design uses `h20m0000`) and whether the proposal success
      criterion "match the exploration table exactly" needs a spec note.
- [ ] Confirm D/64 53.4 M (vs the proposal's 40 M) or drop D/64 from Stage 3.
      The 40 M figure assumes z is not refined to D/64; the renderer's
      arithmetic gives 53.4 M with z refined like x/y.
- [ ] Long-queue authorization: when may Stages 1–3 be submitted?
- [ ] Delivery shape: chained slices (generator/case → data/provenance →
      scripts/docs/tests) or `size:exception` (proposal risk).
- [ ] Inflow `TI=0.5%` / `ℓ=0.07D` are documented choices, not sourced values —
      confirm acceptable.
- [ ] Hub cylinder (diameter 1.0166 m = 2× the 0.5083 m blade root station) is
      derived, not tabulated — confirm acceptable as a lumped model.
