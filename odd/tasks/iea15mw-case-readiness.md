# IEA 15 MW RWT case readiness — assessment

- **Status:** assessment (no source edits, no runs)
- **Branch:** `feat/dagsorensen-tip-correction`
- **Scope:** make the IEA 15-240-RWT a first-class, trustworthy turbinesFoam case

> Read-only inventory + plan. Every number was **read from a file**, not produced
> by running a solver. Unverified items are flagged in §6.

---

## 0. Framing — two complementary cases, two meanings of "validated"

The software is validated by a **pair** of cases, and they validate in
**different senses**:

| | **NREL Phase VI** | **IEA 15-240-RWT** |
|---|---|---|
| Reference class | **Measurement** (NREL/TP-500-29955, NASA-Ames tunnel) | **Cross-code** (OpenFAST, WISDEM quasi-static, HAWC2) |
| Regime | stall-regulated, deep-stall (~5–25 m/s) | pitch-regulated, attached, design point |
| Rotor | 10.058 m, 2 blades, 3° pitch | 242 m, 3 blades, variable pitch |
| Own measurements | **yes** | **none exist** |

**The IEA 15 MW has no measurements.** For this turbine "validation" can only
mean *code-to-code consistency* against other models. That distinction must be
stated in any claim, and is the honest reason the cases are complementary:
Phase VI proves the physics reproduces a **measured** rotor; the IEA 15 MW proves
the same machinery reproduces a **modern, versioned, pitch-regulated design**
against independent codes.

**Shared machinery the pair exercises** (what the pair actually establishes):

- **Geometry pipeline** — blade `(r/R, chord, twist, airfoil-id)` ingestion
  (`validation/phaseVI/tools/element_data.py`; reusable, already proven).
- **Polar ingestion** — `profileData` `(alpha cl cd cm)`, single- and multi-Re
  (`profileData/profileData.C:126-250`).
- **End-effects / tip-loss** — Glauert and Shen (`endEffects`), and the Dağ &
  Sørensen induced-velocity tip correction
  (`axialFlowTurbineALSource.C:1528-1558`, `actuatorLineElement.C:1089-1090`).
- **The ALM element chain** — one shared force chain
  (`actuatorLineElement::calculateForce`): static lookup → rotational
  augmentation → dynamic stall → added mass → end-effects → projection.

---

## 1. What exists locally

### 1.1 Repo copies

- `/scratch/leahk/eduardo.donestevez/IEA-15-240-RWT/` — IEA Wind Task 37 model
  repo v1.1 (`README.md` cites **NREL/TP-75698**, Gaertner et al. 2020).
- `/scratch/leahk/eduardo.donestevez/iea15mw-nrel/` — a **full clone** of the
  same repo (superset: `.git`, `CAD/`, `HAWC2/`, `WISDEM/`, `WT_Ontology/`,
  `OpenFAST/`).
- `/scratch/leahk/eduardo.donestevez/IEA-15-240-RWT.yaml` — the WindIO
  definition (**one geometry source of truth**, §1.7).

### 1.2 OpenFAST case set

Under `.../OpenFAST/IEA-15-240-RWT/` (common) plus per-configuration dirs:

| Subdir | Content | Controller |
|---|---|---|
| `IEA-15-240-RWT/` | common: `Airfoils/`, `_AeroDyn15_blade.dat`, `_BeamDyn*`, `_ElastoDyn_blade.dat`, `_InflowFile.dat`, `Cp_Ct_Cq.IEA15MW.txt`, `ServoData/`, `Wind/` | — |
| `IEA-15-240-RWT-Monopile/` | `.fst`, AeroDyn15, ElastoDyn(+tower), HydroDyn, SubDyn, SeaState, ROSCO | ROSCO |
| `IEA-15-240-RWT-Monopile_wDTUcontroller/` | `.fst`, `control/DISCON.IN`, prebuilt `DTUWEC_for_OpenFAST.so`, `wpdata.100` | DTU |
| `IEA-15-240-RWT-OLAF/` | `.fst`, `_AeroDyn15.dat`, `_OLAF.dat` (vortex-particle) | — |
| `IEA-15-240-RWT-UMaineSemi/` | `.fst` + UMaineSemi ElastoDyn/HydroDyn/MoorDyn/MAP/SeaState/ROSCO + `HydroData/` (WAMIT) | ROSCO |

`OpenFAST/README.md`: common files are for **OpenFAST v2.6+**.

### 1.3 AeroDyn15 polars — `Airfoils/IEA-15-240-RWT_AeroDyn15_Polar_00..49.dat`

**50 files** (one per blade node), AirfoilInfo v1.01.x:

- Header: `NumCoords`, `BL_file`, **`NumTabs = 1`**.
- `Re` field: **3.0e6 in every one of the 50 files** (verified by grep). The
  WindIO yaml uses *different* Re levels (§1.7), so the header Re is effectively
  nominal/collapsed — see §6.
- Some stations carry the 30-coefficient unsteady-aero block
  (`InclUAdata True`, e.g. `Polar_07`); others not (`False`).
- Table: **`NumAlf = 200`**, α = **−180° … +180° in 1.8° steps**, columns
  `Alpha Cl Cd Cm`. Full 360° (AirfoilPreppy-style extrapolation).
- **No 3-D stall-delay correction is baked in.** Every FFA-W3 section in the
  WindIO yaml says literally *"…no 3D correction. F Zahle, DTU Wind Energy 11
  May 2017"*. The 3-D-corrected variant exists only as a separate **HAWC2** file
  (§1.6).

### 1.4 Blade / geometry

`IEA-15-240-RWT_AeroDyn15_blade.dat`: **`NumBlNds = 50`**, columns
`BlSpn BlCrvAC BlSwpAC BlCrvAng BlTwist BlChord BlAFID BlCb BlCenBn BlCenBt`.

- `BlSpn`: 0 → **116.99993 m** (≈117 m blade span).
- `BlTwist`: **+15.5946° root → −1.2424° tip**.
- `BlChord`: **5.2 m** root butt, maximum **5.7648 m at BlSpn ≈ 23.88 m**
  (r/R ≈ 0.20), **0.5 m** at the tip.
- `BlAFID = 1 … 50` (per-node airfoil id = polar index + 1).

`IEA-15-240-RWT.yaml` (`components.blade.outer_shape_bem`):

- `airfoil_position.grid = [0.0, 0.02, 0.15, 0.2452, 0.3288, 0.4392, 0.5377,
  0.6382, 0.7717, 1.0]`, `labels = [circular, circular, SNL-FFA-W3-500,
  FFA-W3-360, FFA-W3-330blend, FFA-W3-301, FFA-W3-270blend, FFA-W3-241,
  FFA-W3-211, FFA-W3-211]` → the distinct section set is **8 shapes**, not 3.
- `chord`, `twist`, `pitch_axis`, `reference_axis{x,y,z}` at 50–52 stations.
- `assembly.rotor_diameter = 242.23775645 m`, `hub_height = 150 m`,
  `number_of_blades = 3`, `rated_power = 15e6 W`.

> **Radius ambiguity to resolve (~0.4 %):** the yaml gives
> `rotor_diameter 242.238` (R = 121.119 m); the Aeroelast BEM test and the
> tabular xlsx use **R = 120.675 m (Ø 241.35 m)**. Blade span 117.0 m ⇒ hub
> radius ≈ 3.675 m (Aeroelast) or ≈ 4.12 m (yaml). **Reconcile before any
> power/thrust comparison.**

### 1.5 Control / rated operating points

`yaml → control`: `supervisory: Vin 3.0 m/s`; `torque.control_type:
tsr_tracking`, **`tsr: 9.0`**, `VS_maxspd 0.7916813487046278 rad/s` (**7.56 rpm**),
`VS_minspd 0.5235988 rad/s` (5.0 rpm); `pitch.min_pitch 0`, `max_pitch 1.57 rad`.

The Aeroelast cross-check uses **V = 10.659 m/s, Ω = 7.518 rpm, pitch = 0**
(below-rated V = 5.006 m/s uses pitch 2.893° and 5.0 rpm). The local OpenFAST
steady run (§2.2) confirms V = **10.59 m/s**, GenSpeed **7.56 rpm**.

### 1.6 HAWC2 power curves

`iea15mw-nrel/HAWC2/IEA-15-240-RWT/`:

- `IEA_15MW_RWT_pc.dat` — 8 sections, Re = 1.0e7, default polars (120 α points).
- `IEA_15MW_RWT_pc_OpenFASTpolars_3dcorr.dat` — 39 sections, built from the
  **OpenFAST polars WITH a 3-D correction** (200 α points);
  `IEA_15MW_RWT_WTG_aero.htc:13` uses this file.

So three power-curve variants exist locally: (a) raw yaml 2-D polars,
(b) AeroDyn15 2-D polars, (c) HAWC2 3-D-corrected OpenFAST polars.

### 1.7 Aeroelast (`/scratch/leahk/eduardo.donestevez/fem-shell`) — strongest local reference

- `tests/IEA-15-240-RWT.yaml` **byte-identical** to the root yaml (`md5sum`
  verified) → one geometry source of truth.
- `src/aeroelast/models/blade/numad/` — **NuMAD blade mesh generation** from the
  same yaml (`io/yaml_to_blade.py`, `mesh_gen/…`).
- `src/aeroelast/models/blade/aerodynamics.py::load_blade_aero()` — WindIO polar
  tables → `AeroStation(r, chord, twist, pitch_axis, prebend, sweep, airfoil)` +
  `AirfoilAero.polars`; Viterna–Corrigan and NeuralFoil fallbacks implemented.
- `src/aeroelast/solvers/bem/engine.py::BEMSolver` (ccblade) → `thrust, torque,
  power, CP, CT, CQ` plus spanwise `Np, Tp, alpha, cl, cd, cn, ct, W, Re`.
- `tests/test_iea15mw_v01_rotor_performance.py` validates against
  **published** reference values — provenance `[R3] =
  IEA-15-240-RWT_tabular.xlsx` sheet "Rotor Performance" and **NREL/TP-5000-75698
  Table 3-1** (WISDEM quasi-static):

  | quantity | reference |
  |---|---|
  | Rated V | **10.659 m/s** |
  | Rated Ω | **7.518 rpm** |
  | Rotor thrust | **2.457e6 N** |
  | Rotor torque | **19.91e6 N·m** |
  | Ct | **0.7718** |
  | Cp_aero | **0.4618** |

  Curve points `(V, Cp_aero, Ct)`: `(5.006, 0.4164, 0.7842)`,
  `(7.159, 0.4616, 0.7783)`, `(9.027, 0.4616, 0.7783)`,
  `(10.659, 0.4618, 0.7718)`, `(12.259, 0.3036, 0.3875)`,
  `(15.471, 0.1511, 0.1796)`. Test tolerances: thrust/torque ±5 %, Cp ±0.02,
  Ct ±0.05. The xlsx is at
  `fem-shell/tests/IEA15MW/validation papers/github-IEA-15-240-RWT/Documentation/IEA-15-240-RWT_tabular.xlsx`.
- `tests/airfoils/` also holds NuMAD/interpolated polar text files.

**What Aeroelast can supply:** per-station `r, r/R, chord, twist`, airfoil-id
mapping, the full `cl/cd/cm` tables, the NuMAD blade surface (for a future ASM
blade), and the **BEM reference curve** (rotor + spanwise). **What it cannot:**
the AeroDyn15 file polars, the 3-D-corrected HAWC2 polars, any measurement, or
OpenFAST aeroelastic outputs.

---

## 2. The OpenFAST comparison path

### 2.1 OpenFAST is installed and runnable — no build needed

- `/scratch/leahk/eduardo.donestevez/conda-envs/openfast/bin/openfast` —
  **OpenFAST v5.0.0**. Second copy at
  `/scratch/leahk/eduardo.donestevez/tools/openfast-env/bin/openfast`; source at
  `/scratch/leahk/eduardo.donestevez/openfast-src/`.

### 2.2 Committed OpenFAST output already exists locally

`/scratch/leahk/eduardo.donestevez/ofruns/OpenFAST/IEA-15-240-RWT-Monopile/IEA-15-240-RWT-Monopile.out`
— a full OpenFAST v5.0.0 steady run (13-Sep-2026), **20 010 lines**, `dt =
0.005 s` ⇒ ~100 s of physical time. Channels include `RotThrust, RotTorq,
RtFldCp, RtFldCt, RtSpeed, RtTSR, RtVAvgxh`, **per-node `AB1N001..050 {Vrel,
Alpha, Vindx, Vindy, Cn, Ct, Fn, Ft, Fx, Fy, TnInd, AxInd}`**, plus
`Spn1..9 MLxb/MLyb` and `B1N001..050 TDx/TDy/RDz`. First row: `Wind1VelX 10.59
m/s`, `GenSpeed 7.56 rpm`, `RotThrust 2.471e6 N`, `RotTorq 1.979e7 N·m`,
`RtFldCp 0.486`, `RtFldCt 0.805`.

**Consequence:** a power/thrust/spanwise comparison dataset for the rated point
is available **without running OpenFAST**. Note the cross-code spread: OpenFAST
(`Ct 0.805, Cp 0.486`) vs WISDEM (`Ct 0.7718, Cp 0.4618`) differ by **~4–5 %** —
the target band must account for this.

### 2.3 ROSCO

ROSCO inputs ship in the repo, and a prebuilt DTU controller `.so` is present.
`libdiscon` itself was **not found** (would have to be built, and the shipped
`.so` host compatibility is unverified). For the **rated fixed-pitch /
fixed-rpm** comparison this is irrelevant — the design point can be prescribed in
AeroDyn/ServoDyn without the controller.

---

## 3. What turbinesFoam needs

### 3.1 Element-data format

Per row (`axialFlowTurbineALSource`, read at
`axialFlowTurbineALSource.C:134-143`):

```
(axialDistance  radius  azimuth  chord  chordMount  pitch)
```

`[0]` axial offset [L]; `[1]` radius from the hub axis [L]; `[2]` azimuth [deg];
`[3]` chord [L]; **`[4]` chordMount — chordwise mount fraction (0.25 =
quarter-chord), NOT the span**; `[5]` twist/pitch [deg]. (Hub/tower use a
different 3-column `(axialDistance, height, diameter)` layout.)

### 3.2 Station count and `nElements % nGeometrySegments`

`actuatorLineSource.C:145-155`:

```
nGeometryPoints    = elementGeometry_.size();   // = elementData rows
nGeometrySegments  = nGeometryPoints - 1;
if (nElements_ % nGeometrySegments) { FatalError… }
```

So the rows are **geometry control points** and `nElements` must be an integer
multiple of the segment count. The AeroDyn blade table has **50 nodes → 49
segments** ⇒ **`nElements ∈ {49, 98, 147, …}`**; 49 elements over 117 m gives
~2.39 m spacing. Alternatively thin the geometry to the ~8 airfoil boundaries
plus intermediate stations and pick a multiple of the reduced count.

### 3.3 Can `profileData` consume the AeroDyn15 polar files as-is? — **No.**

`profileData` reads OpenFOAM dictionaries: **singleRe** `data = ((alpha cl cd
cm)(…))`; **multiRe** `ReList` + 2-D `clData/cdData/cmData`. The AeroDyn15
`*.dat` are AirfoilInfo text files (header + optional 30-coefficient UA block +
`NumAlf=200` rows), with a **different `Cm` sign convention** and a UA block
`profileData` does not expect. **A converter is required.** The Phase VI path has
exactly this machinery (`validation/phaseVI/scripts/buildPolars.py` +
`PROVENANCE.md`) — generalise it to parse AirfoilInfo and emit `profileData`
entries, and to carry the 3-D-corrected HAWC2 tables as a separate arm. Decide
explicitly: **2-D AeroDyn polars** (primary, matching Bernardi's "no stall-delay"
premise) vs **HAWC2 3-D-corrected** (sensitivity) — different files, never mixed
silently.

### 3.4 Mesh cost and the smallest meaningful run

**Phase VI reference:** D = 10.058 m; D/32 = 0.3143 m → **6 674 304 cells** in a
20D × 8D × 5D box, 48 ranks, 12 revs, **≈4:48 wall** (RESULTS.md, Slurm
11604168). D/48 = 22.5 M; D/64 = 53.4 M.

**IEA 15 MW (D = 242.24 m):** a D-normalised box scales with the turbine, so the
same *relative* mesh has the same cell count:

| Relative mesh | Cell size | Cells (same D-box) | cells/rank @48 |
|---|---|---|---|
| D/24 | ≈10.1 m | ≈2.2–2.8 M | ≈50 k |
| **D/32** | **7.57 m** | **≈6.7 M** | **≈139 k** |
| D/48 | 5.05 m | ≈22.5 M | ≈470 k |
| D/64 | 3.79 m | ≈53 M | ≈1.1 M |

Cost per **revolution** is nearly invariant with turbine size at fixed relative
mesh: `steps/rev ≈ 2π·U_tip/(Ω·CFL·h)` with `h ∝ D` and `Ω ∝ U_tip/D` ⇒ Phase VI
U_tip ≈ 37.9 m/s, h = 0.314 m → ≈100 steps/rev; IEA 15 MW U_tip ≈ 95 m/s,
h = 7.57 m → ≈100 steps/rev. **So a 12-rev IEA 15 MW run at D/32 with 48 ranks
is the same wall-time class as the Phase VI D/32 12-rev run (hours–overnight)**,
even though its physical time is 9.6× longer (rev period 7.98 s vs 0.833 s).
D/64 at 48 ranks is cell-starved (~1 700 ranks) — a multi-node, multi-day job.

**Chord-resolution caveat (structural, not ALM):** the 15 MW max chord is
5.765 m (Phase VI ≈0.737 m, 7.8× larger). At D/32 the cell spans 0.76 chords; at
D/64, 1.5 chords. This does not block the *actuator-line* model (whose width is
set by the Gaussian ε), but it does block the ASM-mesh / blade-surface variant
until ~D/128+. Use the ALM and the mesh-based ε for the first case, as Phase VI
does.

**Smallest meaningful first check:** one operating point — the **rated point
V = 10.66 m/s, Ω = 7.518 rpm, pitch 0**; 3 blades (or one blade for a smoke);
coarse D/24–D/32 (≈3–7 M cells); 48 ranks; **3–4 revolutions**; wall-time class
hours–≈1 day. Acceptance: rotor power/thrust/Cp/Ct inside the cross-code band
[WISDEM 2.457 MN / 19.91 MN·m / Ct 0.7718 / Cp 0.4618 ↔ OpenFAST 2.471 MN /
19.79 MN·m / Ct 0.805 / Cp 0.486], plus the spanwise `Cn/Ct` trend vs OpenFAST
`AB1N*`.

---

## 4. AMR-Wind

**Not available here.** No source tree, no `amr-wind`/`incflo` binary, no conda
env or module found under `/scratch/leahk/eduardo.donestevez`. The only AMR-Wind
artifacts are **I/O helpers** in `openfast_toolbox` (readers, not the solver).

Its IEA 15 MW ALM setup is conceptually the same ALM as turbinesFoam (Gaussian /
Lamb–Oseen forcing, blade-element lookup), differing mainly in the AMR plus
overset/actuator infrastructure. It would be a **third cross-code reference, not
a measurement**. Bringing it up (clone + AMReX/hypre/Exawind dependency stack +
hardware/compiler matching) is a **large detour with no measurement payoff** —
**not on the critical path**; defer until the turbinesFoam↔OpenFAST/WISDEM
comparison is trusted.

---

## 5. Prioritised plan

Each step names its cheapest first action, its acceptance signal, and its
character (**measurement** vs **cross-code**).

| Step | Action | Acceptance signal | Character |
|---|---|---|---|
| **P0** | **Reconcile the geometry source.** Pin rotor radius (120.675 vs 121.119 m), hub radius, blade span (117.0 m), `chordMount` (from `pitch_axis`/aero centre) and the twist sign convention against Aeroelast's yaml loader | One documented `(r/R, chord, twist, airfoil-id)` table whose thrust/torque in Aeroelast's `BEMSolver` matches `[R3]` within ±5 % | cross-code (BEM) |
| **P1** | **Generalise polar ingestion.** Extend `buildPolars.py` to parse AirfoilInfo `.dat` → `profileData data (…)`, with `--check`. Two arms: 2-D AeroDyn (primary) and HAWC2 3-D-corrected (sensitivity) | Converter round-trips; a unit test asserts the emitted `(alpha cl cd)` matches the source rows | infrastructure |
| **P2** | **Assemble the case geometry.** Emit `system/elementData` (50 rows → `nElements` multiple of 49, or thinned) and `fvOptions` with 3 blades, `tipSpeedRatio 9.0786`, end-effects off, tip correction off (neutral baseline) | `blockMesh`+`checkMesh` clean; the source constructs and element CSVs are produced | setup |
| **P3** | **Cheapest meaningful physics run.** Rated point, D/24–D/32 (~3–7 M cells), 48 ranks, 3–4 revs, ALM | Power & thrust inside the cross-code band; spanwise `Cn/Ct` shape tracks OpenFAST `AB1N*` | **cross-code (NOT measurement — none exists)** |
| **P4** | **Turn on the tip/end-effect model**, run D&S correction on/off at the same mesh | The tip-loading deficit Phase VI exposed is quantified on the design rotor | cross-code + model sensitivity |
| **P5** | **Mesh independence.** D/32 → D/48 spot-check | Power/thrust drift inside the cross-code band | numerical |
| **P6** | **Extend to ASM / blade-surface** (only after P5; needs ~D/128+) | — | model sensitivity |

**Explicit claim boundary.** P0–P5 establish that turbinesFoam **reproduces the
IEA 15 MW design point consistently with OpenFAST/WISDEM/HAWC2**. They do **not**
establish agreement with nature — the IEA 15 MW has no measurements. The
measurement claim for the software rests **entirely on Phase VI**; the IEA 15 MW
extends it to the modern pitch-regulated design regime by cross-code consistency
alone. Because the two cases share the geometry/polar/end-effect/ALM-element
machinery, passing both means the *same* code reproduces a measured rotor and a
documented design rotor.

---

## 6. Uncertainty / not independently verified

- The Bernardi et al. 2026 statements (Shen tip loss, calibrated `c2 = 32`, no
  stall-delay) were taken from the parent's extraction; the worker did not
  re-read that PDF. The PDF is at
  `turbinesFoam/articles/wes-11-2345-2026.pdf` and **was** vision-verified by
  the parent.
- **No OpenFAST or turbinesFoam run was executed**; all OpenFAST numbers are read
  from the existing `.out`.
- **Radius discrepancy (242.238 vs 241.35 m)** unresolved (§1.4).
- The AeroDyn header **`Re = 3.0e6` for all 50 files** contradicts the yaml's
  per-section Re (3e6 / 8.1e6 / 1e7) — whether the header is nominal or
  meaningful is unverified.
- AMR-Wind absence was established by a filesystem search of
  `/scratch/leahk/eduardo.donestevez` only.
- ROSCO `libdiscon` availability/compatibility on this host unverified.
- The `pitch_axis`/aero-centre → `chordMount` mapping and the twist sign
  convention for the IEA blade were not verified against OpenFAST here.
