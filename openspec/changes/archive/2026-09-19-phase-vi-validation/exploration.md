# Exploration: NREL Phase VI experimental validation (turbinesFoam ALM vs ASM)

Change: `phase-vi-validation` — project `of-plugins` — 2026-09-19.
Read-only exploration; no source, tutorial, or test files were modified.

## Current State

`turbinesFoam/` is the vendored fork (history stripped, GPL-3.0) with the
newly delivered, additive **actuator surface model (ASM)**:

- ALM (`actuatorLineElement`) remains the default; ASM is selected per
  blade line via `elementType actuatorSurfaceElement; nChordwise 5;`
  (`actuatorLineSource.C` lines 337-346). ASM adds chord-averaged inflow
  (mean of `nChordwise` chord-strip samples), uniform strip-wise force
  splitting, and a mesh-only Gaussian projection width
  `epsilon = 2*cbrt(V)*GaussianCoeffs.meshFactor` (`actuatorSurfaceElement.C`).
  `meshFactor` default 2.0; the SAL scaffold uses 1.0.
- Rotor kinematics: `omega_ = tipSpeedRatio * |Uinf| / rotorRadius`
  (`turbineALSource.C` line 148) — **the rotor speed is set through TSR,
  not RPM**. Measured Phase VI runs are constant-RPM, so each wind speed
  must be driven with its own measured TSR (table in §1.1).
- Turbine CSV header `time,angle_deg,tsr,cp,cd,ct`
  (`turbineALSource.C` line 131); `cp = cq*TSR`, `cq = torque/(0.5*rho*A*R*U^2)`,
  `cd = force·Uinf/(0.5*rho*A*U^2)` (`axialFlowTurbineALSource.C` lines 791-798).
- Element CSV header (19 cols, `actuatorLineElement.C` lines 521-523):
  `time,root_dist,x,y,z,rel_vel_mag,Re,alpha_deg,alpha_geom_deg,cl,cd,fx,fy,fz,end_effect_factor,c_ref_t,c_ref_n,f_ref_t,f_ref_n`.
  **No per-element `cm` column** — spanwise CM comparison has no direct
  simulation output (gap; §5.7).
- The comparison utility `tutorials/axialFlowTurbineASM/compareALMvsASM.py`
  already reads `postProcessing/turbines/0/turbine.csv` and the element CSVs
  (fails loudly on missing input) — a good base for the validation script.
- `turbinesFoam/validation/` does not exist yet; repo `AGENTS.md` states
  validation is manual/on-demand HPC, no CI regression suite.
- Repo toolchain is OpenFOAM v2506 (module `openfoam/v2506_openmpi-4.1.4_gnu`)
  with the verified WM_* export recipe; the SAL scaffold hard-checks v2412.
  `kOmegaSST`, `kOmegaSSTIDDES`, `DESModelRegions`, `fieldAverage`,
  `surfaces`/`probes` function objects are available on v2506 (verified in
  the ASM change).
- HPC (verified via `sinfo`): `sequana_cpu` 240 nodes @ 48 cores/node
  (2×24), 384 GB, `infinite`; `sequana_cpu_dev` same node pool, `20:00`
  limit; `sequana_cpu_long` exists. User authorization for the long queue
  is **still pending** — nothing may be launched there yet.

Inputs consumed: Engram `sdd/phase-vi-validation/direction|research`,
`validation/single-actuator-line-repo`, `sdd/mexico-validation/explore|research`,
`config/hpc-launch-sequana`; local verified data at
`$SCRATCH/tmp/phasevi_research/` (+`verified/`) and `$SCRATCH/tmp/phasevi/`;
SAL bare repo `$SCRATCH/tmp/sal/repo.git` (main `8284be8c...`, branch
`mesh/refinement-study` `d9c1831d...`); working clone actually lives at
`$SCRATCH/tmp/phasevi/sal-work/` (the prompt's `$SCRATCH/tmp/sal-work/`
does not exist).

### Verified measured anchors (read from `wt_loads_statistics.xls`, sheet `ldsmean`)

| Row (Seq) | U∞ | RPM | TSR to set | ROTPOW | LSSTQCOR | EAEROTH | CN30/47/63/80/95 |
|---|---|---|---|---|---|---|---|
| h0700000 (H) | 7 | 71.878 | 5.408 | 5.946 kW | 789.86 Nm | 1132.07 N | 0.814/0.920/0.867/0.767/0.517 |
| h1000000 (H) | 10 | 72.107 | 3.798 | 9.753 kW | 1291.59 Nm | 1631.82 N | 1.341/1.401/1.000/0.986/0.748 |
| h1300000 (H) | 13 | 72.091 | 2.920 | 9.794 kW | 1297.22 Nm | 1986.93 N | 2.032/1.200/1.203/0.839/0.911 |
| h1500000 (H) | 15 | 72.062 | 2.530 | 9.582 kW | 1269.73 Nm | 2247.89 N | 2.349/1.164/1.306/0.844/0.849 |
| h2000002 (H) | 20 | 72.064 | 1.898 | 9.219 kW | 1221.49 Nm | 3094.78 N | 2.392/1.486/1.153/1.178/0.828 |
| h2500000 (H) | 25 | 72.208 | 1.521 | 11.951 kW | 1580.41 Nm | 4028.63 N | 2.248/1.568/1.204/1.277/0.775 |
| s0700000 (S) | 7 | 71.867 | 5.407 | 6.030 kW | 801.27 Nm | 1149.53 N | 0.803/0.911/0.865/0.771/0.506 |

CM at the five stations is in the same columns (`CM30..CM95`; e.g. h0700000:
−0.028/−0.039/−0.046/−0.042/−0.022). The workbook also contains yaw sweeps
(2/3/5/10/.../180°) at every speed — a natural stretch campaign later.

**Correction to the research note**: at 15 and 25 m/s the research memo
swapped LSSTQCOR and EAEROTH. Correct: 15 m/s → LSSTQCOR 1269.73 Nm,
EAEROTH 2247.89 N; 25 m/s → LSSTQCOR 1580.41 Nm, EAEROTH 4028.63 N.

Other verified facts carried forward: blade CSV (`phaseVI_blade.csv`, sha256
`e678d6c5...`) matches TP-500-29955 Table A-1 exactly; scaffold polar
(`S809_Re1M_extended`, sha256 `a0961f5c...`) has 4 flipped Cm signs
(α = −20.1/−18.2/−16.2/−14.1°) and 2 unexplained Cd values, plus a hand-made
±30..±180° extension; WDH workbooks sha256 `8e1cfad2...` / `aa25d7d1...`;
`wt_pressure_tap_statistics.xls` adds chordwise Cp (22 taps) at
30/47/63/80/95 % span (stretch metric for ASM).

## 1. Case design options and tradeoffs

### 1.1 Comparison set (recommended)

- **Headline: 7 m/s, Sequence H, 0° yaw** (row `h0700000`). CN30 ≈ 0.81 —
  near-attached; this is the canonical ALM validation point, *not* a
  massively separated case. Both models on the identical case.
- **Separation onset: 10 m/s** (CN30 1.34); **deep stall: 13 and 15 m/s**
  (CN30 2.03/2.35); **stress test: 25 m/s** (CN30 2.25, thrust ~4 kN).
- **Repeat check: Sequence S, 7 m/s** (`s0700000`) — same rig, different
  blade set; nearly free once the case exists.
- Sequence H is preferred for the headline because the reference numerics
  (Churchfield & Schreck 2017: Sequence H, 7 m/s, 71.9 rpm, 3° pitch,
  fine cell 0.05 m, Δt 0.0025 s) and Jha et al. 2013 target it.
- Set `tipSpeedRatio` per measured RPM (table above), never the scaffold's
  fixed 5.3894 except at 7 m/s.
- Reference acceptance is qualitative (integral loads within a documented
  few–15 % band, correct spanwise trend and stall onset); there is no repo
  regression gate. Do not promise <5 % a priori.

### 1.2 Inflow and domain

| Option | Pros | Cons | Effort |
|---|---|---|---|
| **A. Uniform-inflow free box (recommended headline)** — no ABL, no Mann; slip/symmetry far field, velocity inlet, pressure outlet; rotor-only with hub (tower optional) | Replicates the tunnel's uniform approach flow; removes the scaffold's ABL+Mann (environment simulation, not a tunnel replica); cheap setup; standard for Phase VI ALM/URANS references | Blockage ≈ 2 % vs the NASA Ames 24.4 m × 36.6 m test section (~8.9 % rotor-area blockage) — document like MEXICO's 1.2 % vs 18 % | Low-Med |
| B. Tunnel-replica walls (36.6 m wide × 24.4 m high) | Matches experimental blockage | Wall boundary layers + cost + uncertain tunnel BL state; not needed for the headline | High |
| C. Scaffold ABL + Mann (20D×8D×5D, z0=0.03, 10 % TI) | Already exists; good environment/wake benchmark | Wrong inflow definition for this validation; `hipersim` preprocessing dependency; keep only as a separate benchmark, out of scope here | Low (existing) |

Recommended domain geometry reuses the scaffold's 20D×8D×5D extents but
re-centres on the hub and drops the ground: x ∈ [−5D, 15D],
y ∈ ±4D, z ∈ hub ± 2.5D (hub at 12.192 m), i.e. 201 m × 80.5 m × 50.3 m.
This keeps the 18-block renderer and the proven mesh family unchanged while
making all far boundaries slip/symmetry. A tighter 15D×6D×6D variant is the
cheaper fallback (≈ 0.6× cells) if the budget demands it.

Site conditions: pitch 3°, 2 blades, azimuthalOffset 0/180°, axis (−1,0,0),
vertical (0,0,1), `freeStreamVelocity (U 0 0)`. Hub is included as in the
scaffold; tower inclusion is an open question (§5.5) because the scaffold's
tower element data has no verified source.

### 1.3 Mesh and ASM chordwise resolution

Reuse the SAL **18-block Cartesian `blockMeshDict` renderer** (3×3×2 blocks,
`generate_case.py: render_block_mesh`) — fully hexahedral, non-orthogonality
≈ 0, no snappyHexMesh, mesh generation is minutes not hours. Cell counts
computed from the block arithmetic (verified against both SAL branches):

| Target | Core cell | Total cells | chord tip / 80 % / max (cells) | ASM strip c/5 (m) |
|---|---|---|---|---|
| D/32 (main) | 0.3143 m | 6.67 M | 1.13 / 1.45 / 2.34 | 0.071–0.147 |
| D/48 (refinement branch) | 0.2095 m | 22.5 M | 1.69 / 2.18 / 3.52 | 0.071–0.147 |
| D/64 (proposed) | 0.1572 m | ~40.0 M | 2.26 / 2.91 / 4.69 | 0.071–0.147 |

Honest limitation to document: **at every affordable mesh the ASM's chordwise
strips are sub-cell** (strip width < cell size), so the strip-wise force
distribution is sub-grid. The validation therefore tests the chord-averaged
inflow + Gaussian spreading and the load shift vs ALM, not a chord-resolved
surface. Square this with an **nChordwise sensitivity sweep {1, 3, 5}** at
7 m/s on D/48 — cheap, genuinely informative, and the ASM README explicitly
asks for re-validation "on a finer mesh where it gives 1–2 cells of overlap".
`meshFactor`: keep 1.0 (SAL) or 2.0 (tutorial); pick one, print it in
provenance, and note epsilon = 2·Δx (factor 1) → ≈ 2-cell kernel.

Recommendation: **D/32 for dev/stability and the wind-speed sweep; D/48 for
the 7 m/s headline and the nChordwise sweep; D/64 only as a URANS
sensitivity point if the queue budget allows.**

### 1.4 Solver and time integration

| Option | Pros | Cons | Effort |
|---|---|---|---|
| **URANS pimpleFoam + k-ω SST (recommended primary)** | Standard for Phase VI load comparisons; ~2× cheaper per step; stable on blockMesh; converges in ~10 revs | Cannot capture deep-stall unsteadiness/hysteresis (13–25 m/s results become "trend" evidence); k-ω SST may under-predict separation | Med |
| IDDES `kOmegaSSTIDDES` (scaffold) | Resolves wake/vortex shedding; matches the scaffold and Churchfield-class fidelity | Δt ~2.5e-3 s (334/rev) and long averaging windows → 4–20× the URANS cost; uniform inflow gives laminar-ish tunnel flow (acceptable, document) | High |
| kEpsilon (tutorial default) | Cheapest, matches tutorials | Not the reference closure; weaker validation claim | Low |

Time-step rule: ALM tip displacement per step must stay below the cell size,
Δs = ΩR·Δt ≤ Δx (MEXICO-style constraint; the scaffold's Δt 0.03 s / Co 1.0
does not satisfy it at 72 rpm and must not be copied). Chosen fixed steps:
D/32 Δt = 0.008 s (104 steps/rev, Δs = 0.303 m); D/48 Δt = 0.005 s
(167 steps/rev, Δs = 0.189 m); D/64 Δt = 0.004 s (209 steps/rev,
Δs = 0.151 m); IDDES Δt = 0.0025 s (334 steps/rev) per Churchfield.
`adjustTimeStep off` (fixed Δt keeps the rotor azimuth exact);
`T_rev = 0.835 s` at ~72 rpm.

Run length: 12 revs total, discard 0–4, average 4–12 with a rolling <1 %
gate on `cp`/`ct` (extend if drifting); IDDES should target 20–30 revs if
the budget allows (Churchfield ran ~36). Write every ~0.5 rev; `purgeWrite`
to bound disk; restart from latest time.

### 1.5 ALM/ASM twins, S809 polars, endEffects

- One shared case; `system/fvOptions.ALM` and `system/fvOptions.ASM` differ
  only in the blade subdict (`elementType actuatorLineElement` vs
  `actuatorSurfaceElement; nChordwise 5;`). Runner copies the variant into
  `run-{ALM,ASM}-U{U}`; compare script reads both + experiment.
- Polars: **rebuild from the NREL tables** — TP-500-29955 A-3..A-6 (CSU
  Re 0.3/0.5/0.65 M), A-7 (OSU Re 1 M), A-8 (DUT Re 1 M) and TP-442-7817
  (OSU Re 0.75/1/1.25/1.5 M, clean+grit) — **not** the scaffold polar as-is
  (flipped Cm, suspect Cd). Use OSU Re 1 M total drag as the single-Re
  baseline and the multi-Re set (`ReList`/`clData`/`cdData`/`cmData`,
  supported by `profileData.C`) as a sensitivity variant; document each Re
  level's source and α-range because cross-source blending introduces
  kinks. Operational chord Re ≈ 0.3–1.1 M across the 7–25 m/s matrix.
- **endEffects ON with Glauert** (2D measured polars ⇒ 3D tip/root
  correction required; Shen as variant). Never combine RANS-BR span polars
  with Glauert (double counting) — not applicable here but document.
- Dynamic stall: OFF for the near-attached 7 m/s headline; consider
  Leishman–Beddoes ON for the 13–25 m/s points as a documented variant.

### 1.6 Comparison metrics and definitions

- **Turbine level**: dimensional power (W) and shaft torque (Nm) from the
  simulation torque (blades+hub) vs measured ROTPOW / LSSTQCOR; thrust from
  blade forces vs EAEROTH. Prefer dimensional comparison (or state the air
  density used) because CP/CT depend on the test-day density (the workbook
  carries WTBARO/WTATEMP; the report/design phase must fix the reference
  value).
- **Spanwise**: simulation `c_ref_n`/`c_ref_t` vs measured CN/CT at
  30/47/63/80/95 % span. **CM has no element-column output** — either drop
  CM from the headline or add `momentCoefficient_` to the element CSV in a
  separate small change (source is out of scope here).
- **Note**: `EAEROTH` is pressure-integrated rotor thrust (no skin
  friction); confirm whether it includes hub/tower effects in the report
  before defining the sim-side equivalent (`force_` includes hub; tower
  only if `includeInTotalDrag true`). Sign conventions of c_ref_n/c_ref_t
  must be checked against the measured sign at 7 m/s and documented.
- Stretch: chordwise Cp from `wt_pressure_tap_statistics.xls` at the five
  stations (ASM's natural target), and the yaw sweep (2–180°) later.

## 2. Scaffold reuse plan (`mttbrbr/single-actuator-line`, GPL-3.0-or-later)

**Reuse (adapted, not copied blindly):**
- `data/turbines/phaseVI_blade.csv` — verified byte-faithful to Table A-1
  (keep, with attribution and PROVENANCE).
- `tools/case_config.py` + `tools/generate_case.py` structure — YAML single
  source of truth, 18-block `blockMeshDict`/`topoSetDict`/`controlDict`/
  `decomposeParDict` renderers, `--check` staleness mode, `blade_element_data()`
  pitch-sign handling (`-(twist + pitch)`; re-verify against the turbinesFoam
  pitch convention before trusting).
- `scripts/` patterns (mesh/check/smoke/clean, RunFunctions) and
  `Makefile`/unit-test layout (`tests/test_configuration.py`,
  `tests/test_rendering.py`) — mirror the *structure*, not Mann-specific
  code.
- Postprocessing ideas: `tools/postprocess_wakes.py`,
  `export_final_les_diagnostics.py` (adapt field names if IDDES is used).

**Rebuild:**
- S809 polars from the NREL tables (above); drop `S809_Re1M_extended`.
- All experimental CSVs extracted from the WDH workbooks (below).
- fvOptions twins with `elementType`; uniform-inflow BCs; no `hipersim`
  (remove the Mann dependency entirely); blockMesh-only mesh (drop
  snappy/topoSet cell-set if not needed for the ALM selection, or keep
  `topoSet` only to build the `turbine` cellSet).
- `check_environment.sh` version check — make it accept the repo's v2506
  (and keep v2412 compatible), not hard-fail on v2412.
- New `comparePhaseVI.py` (turbine + spanwise + experiment merge; fail
  loudly on missing input, reusing `compareALMvsASM.py` conventions).

**Licensing/attribution**: SAL original content is GPL-3.0-or-later —
compatible with this repo; credit "adapted from mttbrbr/single-actuator-line
(main `8284be8c...`)". NREL reports are US-Government works (public):
cite TP-500-29955 (DOI 10.2172/15000240) and TP-442-7817; WDH data are
public (DOI 10.21947/WDH-DAP/1910052). Do **not** commit the report PDFs or
the 44 MB workbooks; commit derived numeric CSVs + `PROVENANCE.md`
(URL, sha256, sheet, row selection, units, extraction date).

**Upstream pinning**: the vendored fork has no upstream history. Record the
of-plugins commit (`git rev-parse HEAD`, currently `52fd258...`) plus a note
that the fork carries the ASM patch, in the case README/PROVENANCE — same
discipline the SAL README asks for its external turbinesFoam.

## 3. Data requirements checklist and proposed layout

```
turbinesFoam/validation/phaseVI/
├── case/                      # generated: 0.org, constant, system/fvOptions.{ALM,ASM}
├── data/
│   ├── geometry/phaseVI_blade.csv (+ PROVENANCE.md)
│   ├── polars/S809_OSU_Re1M.dat, S809_multiRe_{Re,cl,cd,cm} (+ PROVENANCE.md)
│   └── experiment/
│       ├── sequence_H_performance.csv   # U, RPM, TSR, ROTPOW_kW, LSSTQCOR_Nm, EAEROTH_N, GENPOW
│       ├── sequence_H_spanwise.csv      # U, r/R, CN, CT, CM
│       ├── sequence_S_performance.csv
│       └── PROVENANCE.md                # workbook sha256, sheet ldsmean, File Name rows, units
├── scripts/
│   ├── makeElementData.py     # optionally reuse the generator instead
│   ├── runPhaseVI.sh          # -m alm|asm -u <windspeed> [-mesh coarse|fine]
│   └── comparePhaseVI.py      # sim vs data/experiment, mean±std over window
├── README.md
└── config/case.yaml + tools/generate_case.py   # if the generator is imported wholesale
```

Exact data to derive: blade CSV (Table A-1, already verified); polar tables
(A-3..A-8 + TP-442-7817); experimental CSVs from `wt_loads_statistics.xls`
sheet `ldsmean`, rows `h0{07,10,13,15,20,25}00000`/`h2000002` and
`s0700000` (0° yaw only), columns `Windspeed, RPM, ROTPOW, LSSTQCOR,
EAEROTH, CN30..CM95`; optionally from `wt_pressure_tap_statistics.xls`
sheet `prsmean` the chordwise taps at the five stations. An extraction
script may live in `scripts/` but requires the workbooks (not committed) —
the derived CSVs are the committed artifact.

## 4. Compute estimate and Slurm strategy

Assumptions: rotor 72 rpm (T_rev 0.835 s); throughput 4 000 cell·step/s/core
for URANS, 2 500 for IDDES (MEXICO-explore convention, ×0.5–×2 uncertainty);
12 revs; 48-core nodes; parallel efficiency ~0.75.

| Mesh | Cells | Model | Δt (s) | steps/rev | steps (12 rev) | core-h | wall @2 nodes | wall @10 nodes |
|---|---|---|---|---|---|---|---|---|
| D/32 | 6.67 M | URANS | 0.008 | 104 | 1 250 | ~580 | ~8 h | ~1.6 h |
| D/48 | 22.5 M | URANS | 0.005 | 167 | 2 004 | ~3 100 | ~43 h | ~8.7 h |
| D/64 | 40 M | URANS | 0.004 | 209 | 2 508 | ~7 000 | — | ~19 h |
| D/32 | 6.67 M | IDDES | 0.0025 | 334 | 4 008 | ~3 000 | ~41 h | ~8 h |
| D/48 | 22.5 M | IDDES | 0.0025 | 334 | 4 008 | ~10 000 | — | ~28 h |

Program size: recommended URANS core (7 m/s × 2 models × D/32+D/48) ≈ 7.4 k
core-h; adding {10,13,15,25} × 2 models at D/32 ≈ +4.6 k core-h; optional
IDDES confirmation at D/48 × 2 models ≈ +20 k core-h.

Staged plan:
- **Stage 0 (now, `sequana_cpu_dev` 20 min, authorized)**: build case +
  generator; `blockMesh` + `checkMesh` for D/32 and D/48 (minutes);
  stability runs of both models at 7 m/s on D/32 for **≤ 0.3 rev**
  (0.2 rev ≈ 21 steps ≈ 10 core-h ≈ 12 min on 48 ranks; 1 full rev ≈ 49
  core-h would exceed 20 min on 48 cores but fits ~96–144 ranks).
- **Stage 1 (long queue, pending authorization — do not launch)**:
  7 m/s, URANS, ALM+ASM, D/32 first (job array of 2), then D/48 (job array
  of 2); extract headline numbers.
- **Stage 2**: windspeed extension {10,13,15,25} at D/32 (ALM baseline all,
  ASM at 10/13 as budget allows); Sequence S 7 m/s repeat.
- **Stage 3 (optional)**: IDDES at D/32 (both models) and/or D/48 (one);
  nChordwise {1,3,5} sweep at D/48/7 m/s URANS; D/64 URANS sensitivity.
- Slurm: per the verified `runAll.srm`/`RunFunctions` pattern (`module load
  openfoam/v2506_openmpi-4.1.4_gnu gcc`, source bashrc, payload on
  `$SLURM_PROCID -eq 0`); one array task per (model, speed, mesh); 48-rank
  granularity; ≤24 h wall requests with restart from the latest written
  time; logs `%j.out/.err`.
- Everything except Stage 0 is prepared but **not launched** until the
  long-queue authorization is granted.

## 5. Risks and open questions

1. **ASM chordwise resolution** — at D/32–D/64 the chord/5 strips are
   sub-cell; the ASM cannot be validated as a chord-resolved surface on any
   affordable Phase VI mesh. Mitigation: state the limitation, run the
   nChordwise sensitivity sweep, and treat D/48 as the headline mesh.
2. **URANS vs IDDES fidelity/cost** — URANS is affordable and standard for
   integral loads at 7–10 m/s but cannot resolve deep-stall unsteadiness at
   13–25 m/s; IDDES costs 4–20×. Resolution: URANS headline + optional
   IDDES confirmation; treat high-speed points as trend/onset evidence.
3. **Comparison definitions** — EAEROTH (pressure-integrated, friction-free;
   hub/tower inclusion to confirm), ROTPOW/LSSTQCOR drivetrain-correction
   details, and air density (dimensional vs coefficient comparison). The
   design phase must fix these against TP-500-29955 before writing metrics.
4. **Spanwise CM gap** — element CSV has no `cm`; CM comparison needs a
   tiny source addition (add `momentCoefficient_` to the element writer) or
   must be dropped. Source changes are outside this change's scope.
5. **Tower geometry provenance** — the scaffold's tower element data has no
   cited source; either source it from the test report or run rotor+hub only
   and document. Tower shadow is in the measured loads.
6. **TSR sign/kinematics** — must set per-speed measured TSR (not the fixed
   5.3894); verify rotation direction, `axis (−1,0,0)` handedness, and the
   `-(twist + pitch)` convention reproduce the measured CN/CT signs at
   7 m/s before any production campaign.
7. **Delivery size** — case + data + scripts + docs will far exceed the
   400-line single-PR budget. Recommend chained slices: (1) generator + case
   skeleton + fvOptions twins + mesh/check scripts, (2) data files +
   PROVENANCE, (3) run/compare scripts + README/CHANGELOG + sanity tests;
   or an explicit `size:exception`.
8. **Long-queue authorization** — still pending; Stage 1–3 cannot run until
   granted. Nothing is blocked for exploration/design/tasks.
9. **MEXICO fallback** — `openspec/changes/mexico-validation/` remains
   historical input; Phase VI is the chosen primary because its data is
   public and complete. Re-open MEXICO only if the user reverses the pivot.
10. **Data extraction correctness** — workbooks must be parsed with the
    `ldsmean` sheet and 0°-yaw rows only (yaw sweeps present in the same
    sheet); derived CSVs need cross-checks (anchors in §Verified table) and
    PROVENANCE.

## Approaches (overall)

1. **Scaffold-derived uniform-inflow URANS program (recommended)** —
   re-centred 20D×8D×5D free box, blockMesh D/32→D/48, pimpleFoam k-ω SST,
   fixed Δt from the tip-speed constraint, ALM/ASM twins via `elementType`,
   NREL-rebuilt S809 polars, Glauert ON, staged 7 m/s first.
   - Pros: genuine comparison basis (public measured anchors), reuses the
     proven generator/mesh family, affordable, ALM and ASM on the same case.
   - Cons: ASM chordwise resolution limitation; URANS deep-stall limits.
   - Effort: Medium-High.
2. **IDDES-first (scaffold fidelity, uniform inflow)** — same case but
   `kOmegaSSTIDDES`, Δt 0.0025 s, 20–30 revs, no Mann (uniform inlet).
   - Pros: highest fidelity, directly comparable to Churchfield-class runs.
   - Cons: 4–20× cost; uniform inlet under-resolves tunnel turbulence;
     delays first results.
   - Effort: High.
3. **Tunnel-replica walls** — physical blockage matched.
   - Pros: closest to the experiment's flow constraint.
   - Cons: wall BL setup, cost, little precedent; not needed for headline.
   - Effort: High.
4. **Minimal smoke only (D/32, 7 m/s, URANS, ALM only)** — quick numbers.
   - Pros: cheap, fast.
   - Cons: not a validation of the ASM; weak claim.
   - Effort: Low.

## Recommendation

**Approach 1, staged**, delivered as `turbinesFoam/validation/phaseVI/`
(case + data + scripts + README, no `src/` changes): re-centred uniform-inflow
20D×8D×5D box with the SAL 18-block blockMesh renderer (D/32 dev, D/48
headline, D/64 optional), pimpleFoam URANS k-ω SST with tip-constrained fixed
Δt, ALM/ASM fvOptions twins, S809 polars rebuilt from the NREL tables,
2D-polars + Glauert endEffects ON, and the verified WDH anchors compiled into
`data/experiment/`. Run 7 m/s Sequence H first with both models; extend to
10/13/15/25 m/s and Sequence S; add IDDES and nChordwise sweeps only if the
queue budget allows. Prepare and dry-check everything on `sequana_cpu_dev`
now; launch production only after the long-queue authorization is granted.

## Affected Areas

- `turbinesFoam/validation/phaseVI/` — new case, data (+PROVENANCE),
  scripts, README (the main deliverable; directory does not exist yet).
- `turbinesFoam/tests/` — optional cheap data-sanity tests (polar/CSV parse,
  geometry monotonicity, TSR mapping); no solver in tests.
- `turbinesFoam/src/` — **unchanged** (`elementType`/`nChordwise` shipped);
  spanwise CM would be a separate opt-in change.
- Root `README.md` / `CHANGELOG.md` — document the validation case.
- `openspec/changes/phase-vi-validation/` — this artifact and the downstream
  proposal/spec/design/tasks.

## Ready for Proposal

**Yes.** Surface these user decisions to the orchestrator:
1. **Authorization gate** — long-queue (`sequana_cpu`) is still pending;
   Stage 0 (dev partition mesh/stability) can start immediately.
2. **Fidelity/cost mix** — confirm URANS headline + optional IDDES, and the
   mesh ladder D/32 → D/48 (D/64 only if affordable).
3. **Delivery shape** — the change exceeds the 400-line budget: chained PR
   slices vs `size:exception`.
4. **Comparison definitions** — confirm the density convention, whether the
   sim-side thrust includes hub/tower, and whether spanwise CM is required
   (would need the small element-CSV addition).
