# Exploration: Blade actuator surface model over a real imported blade mesh (S2)

Change: `blade-actuator-surface` — project: `of-plugins` — date: 2026-09-21
Scope: `turbinesFoam/` (source, geometry pipeline, `validation/phaseVI/`).
Slice: **S2** of a staged program. S1 = `nacelle-actuator-surface` (real
imported nacelle surface + geometry pipeline + time-derived kinematics), archived
2026-09-20. S3 = preCICE FSI wiring, deferred. The previous blade ASM change
(`actuator-surface-model`, archived 2026-09-19) delivered the **no-mesh** element.
Reference: Yang & Sotiropoulos, arXiv:1702.02108v4 (2018). A local text copy of
the paper exists outside the repo at
`/scratch/leahk/eduardo.donestevez/simulations/tmp/mexico_research/yang_arxiv_1702.02108.txt`
(Sec. 2.1 = blade ASM, Sec. 2.2 = nacelle ASM); all equation references below
cite that text.

## Current State

### 1. The delivered blade ASM has no imported surface (verified)

- `actuatorSurfaceElement` (`turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/actuatorSurfaceElement.{H,C}`)
  is an `actuatorLineElement` subclass that overrides exactly three methods:
  `calcProjectionEpsilon` (mesh-only `2*cbrt(V)*meshFactor`, `.C:61-100`),
  `applyForceField` (uniform strip force `forceVector_/nChordwise_`, Gaussian
  spread at the strip midpoints, `.C:103-151`), and `calculateInflowVelocity`
  (arithmetic mean of `interpolationCellPoint` samples at `nChordwise` chord
  strip midpoints, `.C:154-205`). `nChordwise` defaults to 5 (`.C:218`).
- `chordPoint(k)` is the chord-line point `position_ + (chordMount_ -
  (k+0.5)/nChordwise_)*chordLength_*unit(chordDirection_)` (`.C:51-58`): the
  "surface" is a **flat chord line per radial element**, sampled and spread
  strip-wise — no triangulation, no per-node geometry, no metadata.
- The element force chain (BEM coefficient lookup, dynamic stall, end effects,
  added mass, CSV: `actuatorLineElement.C:515-540`) is inherited unchanged.
- Selection: `actuatorLineSource::createElements()` copies `elementType`
  (default `actuatorLineElement`) and `nChordwise` into every element dict
  (`actuatorLineSource.C:337-346`) and constructs them via
  `actuatorLineElement::New` (`:365-369`); the ASM registers itself in the
  element RTS (`actuatorSurfaceElement.C:38-44`).
- `createElements()` builds `nElements_` elements from the geometry points by
  **linear interpolation per segment** (position, chord, span direction, pitch,
  chord mount, chord direction, velocity): `actuatorLineSource.C:131-374`,
  interpolation at `:238-292`. For Phase VI, 26 `elementData` stations and
  `nElements 50` give `nElementsPerSegment = 2` (`:135-145`).
- Public per-element accessors exist (`position()`, `velocity()`, `force()`,
  `relativeVelocity()`, `angleOfAttack()`, `liftCoefficient()`,
  `spanLength()`, `chordLength()`, `rootDistance()`:
  `actuatorLineElement.H:299-339`). Turbine/blade internals are protected:
  `blades_` (`turbineALSource.H:105`), `elements_`/`forceField_`
  (`actuatorLineSource.H:94,83`).

**What a mesh-based surface replaces:** the two chord-strip loops — inflow
averaging (`actuatorSurfaceElement.C:154-205`) and force distribution
(`.C:103-151`). **What stays:** the entire BEM force chain and per-element CSV,
the rotation/TSR kinematics, the AFTAL composition, and the element selection
mechanism.

### 2. The paper's blade ASM is a chord-line surface — the "real mesh" is an extension (verified)

- Sec. 2.1: "the blade geometry is represented by a surface formed by the chord
  lines at different radial locations of a blade" (paper text line 105); the
  force per unit area is `f(X) = (L + D)/c` (Eq. 17, line 288), i.e. **uniform
  in the chordwise direction**, and is spread by the smoothed cosine kernel
  (Eq. 18, lines 293-300) with the node area `A(X)`. Inflow is chord-averaged
  per radial station (Eqs. 5-6, lines 138-150) with the same kernel (Eq. 7).
- The S1 nacelle model instead used the **actual** surface (Sec. 2.2, "the
  nacelle geometry is represented by the actual surface of the nacelle",
  line 320; Eq. 19-23, lines 332-379). S2 applying a real triangulated blade
  mesh is therefore an **extension of the paper's blade ASM in the S1
  direction**, not a literal equation port. All BEM content (Eqs. 1-16) is
  unchanged.

### 3. S1 machinery: what generalizes to a blade and what does not (verified)

`nacelleSurfaceSampler` (`turbinesFoam/src/fvOptions/nacelleSurface/`):

| Piece | Location | Blade suitability |
|---|---|---|
| `triSurface::New` load, ASCII/binary auto-detect, empty-file fatal | `nacelleSurfaceSampler.C:173-210` | Direct reuse |
| Node set = triangle centroids (`faceCentres`/`faceNormals`/`magFaceAreas`), stable surface face order | `.C:212-215` | Direct reuse |
| `cellSize(X)` — `findCell` + `reduce(minOp)` sentinel, fatal if unreachable | `.C:269-292` | Direct reuse |
| `kernel(r)` — paper smoothed 4-point cosine, support \|r\|≤2.5 (Eq. 8) | `.C:374-404` | Direct reuse |
| `interpolateVelocity(X,U,h)` — separable kernel sum, `returnReduce(sumOp)` on every rank | `.C:407-463` | Direct reuse |
| `distributeForce` — Eq. 18 spread `-F_i*w/V_cell`, node loop × all local cells | `nacelleSurfaceSource.C:163-209` | Reuse the math; **needs a rotating-frame node update and a cost review** (see Risks) |
| Body frame (`bodyOrigin`/`bodyAxis`, static), `positions()/forces()/normals()/areas()` contract, SI newtons via `rho` | `nacelleSurfaceSampler.H:196-283`, `.C:36-93,150-151` | Contract shape reusable; a **blade** body frame rotates with the rotor |
| Nacelle force model: normal direct forcing Eq. 19 (`normalForce`), friction Eq. 21-23 (`tangentialForce`, `frictionCoefficient`, `tangentialDirection`), `nu`/transportProperties | `.C:295-371`; `.C:96-142` | **Not applicable** — the blade load must come from the BEM chain (CL/CD), not a direct-forcing/friction closure |
| Source plumbing: `cellSetOption`, RTS, `force.<name>` volVectorField, total/per-node CSV, three `addSup` overloads (scalar no-op), `read()` | `nacelleSurfaceSource.C:280-431` | Template for a blade source; note the nacelle is **static** and composed once per turbine (`axialFlowTurbineALSource.C:471-502`) |

The S1 design calls the sampler "reusable" (design §4.1, file table at
`design.md:950`) but the class is **concrete**, not a base: reuse means a
refactor (shared geometry/kernel base) or duplication. This is an S2 decision,
not a free asset.

### 4. AFTAL wiring: where a per-blade surface attaches (verified)

- `createBlades()` builds one `actuatorLineSource` per blade from `bladesDict_`
  and the interpolated `elementGeometry` (`axialFlowTurbineALSource.C:75-291`);
  the constructor calls `createBlades()` then `createNacelle()` if
  `hasNacelle_` (`:626-640`).
- `createNacelle()` is the S1 composition precedent: it injects
  `fieldNames`/`selectionMode`/`cellSet`/`referenceVelocity`, wraps the
  `nacelle {}` subdict in `nacelleSurfaceSourceCoeffs`, and stores an
  `autoPtr<nacelleSurfaceSource> nacelle_` (`:471-502`, declared
  `axialFlowTurbineALSource.H:77`).
- The three `addSup` overloads sum child force fields/forces
  (`:779-817`, `:873-911`) and the scalar-turbulence overload delegates
  (`:975`). Torque is the blade-moment projection on the axis (`:820-826`).
- Rotation is blade+hub only: `rotate()` (`:671-690`) calls
  `blades_[i].rotate(origin_,axis_,radians)` and `setSpeed`;
  `rotateBladesAndHub()` (`:692-724`) covers tilt/yaw. `actuatorLineSource`
  forwards `rotate`/`pitch`/`translate`/`setSpeed` to its elements
  (`actuatorLineSource.C:577-647`). A blade surface must hook this path
  (its nodes rotate with the rotor), unlike the static nacelle.
- Kinematics are time-derived and restart-safe (S1 W3): azimuth is
  `angleDeg_ = ω·(t−t0)` (or the closed-form `tsrAmplitude` integral),
  persisted as `angleDeg.<name>` with an optional `omega.<name>` override and
  an `angleDeg()` accessor (`turbineALSource.C:315-345,430-432`). A rotating
  surface therefore needs **no new state** to be restart-idempotent.

### 5. Geometry pipeline is gmsh-only and the blade component is explicitly un-deferred (verified)

- `turbinesFoam/geometry/src/makeGeometry.py`: `COMPONENTS = ("nacelle",)`,
  `RESERVED_COMPONENTS = ("blade0","blade1","blade2")` (`:86-88`); the CLI
  rejects a reserved component with the S2-deferral message (`:535-541`).
- `build_component()` always reads `src/<name>.geo`, runs
  `gmsh -2 -format stl`, canonicalizes the triangles (cyclic-minimum vertex
  order + sort, `canonical_triangles`, `:194-209`), writes the binary STL
  with a fixed header and recomputed facet normals (`:212-219`), and emits
  metadata JSON (`:355-378`).
- Metadata already reserves the per-node blade mapping:
  `_reserved = {"blade": {"radial_station": null, "chord_fraction": null}}`
  (`:371-373`; README schema `geometry/README.md:60-88`), and
  `tests/test_nacelle_data.py:217-219,292-301` assert both the reserved fields
  and the blade-component rejection — **S2 must update those assertions and the
  README/PROVENANCE text**.
- `geometry/PROVENANCE.md:13` names the deferred blade source as **MEXICO**
  rotor tables (the same paper, Sec. 4.2), not Phase VI; `README.md:8-9,53-54`
  repeats the deferral. Targeting Phase VI changes that statement (open
  question Q2).
- Determinism constraints: gmsh pinned **4.15.2**, `--check` refuses other
  versions (exit 2) and is non-destructive; byte-identical regeneration is
  guaranteed by the canonicalization + fixed options
  (`PROVENANCE.md:41-64`, `makeGeometry.py:430-502`). gmsh needs
  `libGLU.so.1` (`module load glu/9.0.2_gnu` on SDumont) or the pure-Python
  tests skip regeneration.

### 6. Phase VI inputs are present, but the S809 shape is not committed (verified)

- Blade stations: `turbinesFoam/validation/phaseVI/data/geometry/phaseVI_blade.csv`
  (26 rows, `radius_m, chord_m, twist_deg_report, chord_mount`), extracted from
  NREL/TP-500-29955 Table A-1 with sha256-pinned `PROVENANCE.md`. Cylinder
  transition at `r <= 0.8835`, S809 from `r = 1.0085`; `chord_mount` 0.50 at the
  root cylinder and 0.30 through the airfoil (30 % chord pitch axis)
  (`PROVENANCE.md:13-24`). `case_config.py:44-45` defines
  `ROOT_CUTOUT_RADIUS = 0.5083`, `ROOT_CYLINDER_END = 1.2575`;
  `read_blade()` reads/validates the CSV (`case_config.py:479-508`).
- **S809 profile coordinates are not committed anywhere under `turbinesFoam/`**
  (grep: only polar coefficient tables `data/polars/S809_*.dat` and their
  references; `tutorials/resources/foilData/` has no S809 file). The canonical
  source is the locally verified PDF
  `/scratch/leahk/eduardo.donestevez/tmp/phasevi_research/verified/s809_somers_nlr.pdf`
  (Somers, NREL/SR-440-6918).
- **Extraction is already possible from a local text dump**: `pdftotext` is not
  installed on this host, but a PyMuPDF text dump exists at
  `/scratch/leahk/eduardo.donestevez/tmp/phasevi_research/somers_fitz.txt`
  containing "Table 2. S809 Airfoil Coordinates" (line 946): 31 upper-surface
  and 30 lower-surface `x/c, z/c` pairs (TE shared at `1.0000, 0.0000`).
  The dump is outside the repo and its extraction recipe is not recorded in any
  PROVENANCE, so committing the coordinates is a data-provenance task (not
  blocked; do **not** treat the dump as authoritative until cross-checked).
- Polars: `data/polars/S809_OSU_Re1M_total.dat` (single-Re, used by the
  generated `profileData` `#include`) and `S809_multiRe.dat`, each with
  PROVENANCE (`generate_case.py:495,583-597`).
- Experiment: `data/experiment/sequence_H_performance.csv` and
  `sequence_H_spanwise.csv` (CN/CT/CM at r/R = 0.30/0.47/0.63/0.80/0.95),
  Sequence S repeats, WDH provenance (local `.xls` not committed). Pressure-tap
  statistics exist locally
  (`phasevi_research/verified/wt_pressure_tap_statistics.xls`) but are not
  extracted and are not a direct match for a smeared force model.

### 7. Phase VI validation pipeline (verified)

- `config/case.yaml` is the single source of truth: rotor `diameter 10.058`,
  `n_blades 2`, `n_elements 50`, measured TSRs per speed, mesh ladder D/32,
  D/48, D/64 (6.67 M, 22.5 M, 53.4 M cells), fixed time steps, `n_chordwise 5`
  with a `[1,3,5]` Stage 3 sweep (`case.yaml:13-25,88-109,190-200`).
- ALM/ASM are rendered as twins that "differ only in the blade element keys"
  (`elementType`, `nChordwise`): `generate_case.py:480-505`, asserted by
  `tests/test_phasevi_case.py:147-174`. The committed case has
  `case/system/fvOptions.{ALM,ASM}`; `case/system/fvOptions.ASM:58-59` carries
  `elementType actuatorSurfaceElement; nChordwise 5;`.
- Runner: `scripts/runPhaseVI.sh -m alm|asm` (rejects any other model,
  `:80-82`), installs the twin into `runs/<model>-U<speed>-<mesh>` (`:211-213`),
  and validates combinations through `tools/case_config.py --select`
  (whitelist `("alm","asm")`, `case_config.py:552-557`). `--nchordwise` is
  ASM-only (`runPhaseVI.sh:102-104`).
- Compare: `scripts/comparePhaseVI.py` reads
  `postProcessing/turbines/0/turbine.csv` (`:54`) and
  `postProcessing/actuatorLineElements/0/*.csv` (`:55`), reads spanwise
  `c_ref_n`/`c_ref_t` per element and maps them to r/R
  (`:259-275`), computes F1-corrected CP/CT/thrust (`:292-317`), and applies
  ±15 % turbine / max(0.15, 20 %) spanwise bands plus a sign gate
  (README `Comparison`, `:198-249`). `--match-eaeroth-span` restricts the blade
  thrust sum to `r/R >= 0.25` (`:332-349`).
- Slurm: `stage0` (dev queue) authorized, `production`/`stage3`/`stage3-d64`
  prepared-only behind `PHASEVI_LONG_QUEUE_AUTHORIZED=1` (README `:161-196`).
  **Verified in `squeue`**: `phaseVI-prod` (`11597195_[2-8]`, `11597349_[9-13]`),
  `phaseVI-stage3` (`11597350_*`), `phaseVI-stage3-d64` (`11597373_[0-1]`) are
  pending/running — the no-mesh ASM/ALM validation pipeline is live. No new job
  may be submitted from this change without authorization.
- Tests: pure-Python `test_phasevi_{case,data,compare}.py`; solver-driven
  suites auto-skip without OpenFOAM (`tests/conftest.py`).

## Affected Areas

- `turbinesFoam/src/fvOptions/actuatorLineSource/` — the imported-surface load
  path (a distributing surface object; element hook to suppress double
  application; `actuatorSurfaceElement` may stay as the no-mesh variant).
- `turbinesFoam/src/fvOptions/axialFlowTurbineALSource/axialFlowTurbineALSource.{H,C}`
  — per-blade surface composition, rotation hook, force/`forceField_`/torque
  aggregation, config read (`bladeSurface {}` / per-blade `surface {}`).
- `turbinesFoam/src/fvOptions/nacelleSurface/nacelleSurfaceSampler.{H,C}` —
  possible refactor into a shared non-nacelle-specific sampling base (S1 code
  touched; regression-gated) or duplication into a parallel blade class.
- `turbinesFoam/src/Make/files` — register any new `.C`; `-lsurfMesh` already
  linked by S1.
- `turbinesFoam/geometry/` — blade component: generator (`src/*.geo` or a new
  Python builder), STL(s), metadata (`radial_station`/`chord_fraction` per
  node), PROVENANCE source row (Phase VI vs MEXICO), README; tests
  `test_nacelle_data.py` (reserved-field and deferral assertions).
- `turbinesFoam/validation/phaseVI/` — new case variant (`fvOptions.ASM-MESH`
  or similar), `case.yaml` model/stage entries, `tools/generate_case.py` third
  render, `tools/case_config.py` `--select` whitelist, `scripts/runPhaseVI.sh`
  `-m` handling + STL staging into run dirs, `scripts/comparePhaseVI.py`
  three-way inputs and a per-station converter for surface output, prepared
  Slurm arrays (no submission), README, tests.
- `turbinesFoam/README.md`, root `README.md`, root `CHANGELOG.md` — model,
  geometry, validation documentation.

## Approaches

### 1. Where the mesh-based blade surface lives

**A. Per-blade `bladeSurfaceSource` (or `actuatorSurfaceSource`) composing the
BEM elements — recommended shape to evaluate.** One source per blade, owned by
AFTAL (a `PtrList`, parallel to the per-blade `actuatorLineSource`) or by the
blade source itself; it reads the blade STL, maps nodes to radial elements,
takes each element's BEM `forceVector_` (or recomputes it), area-weights it onto
the surface nodes, spreads with the S1 kernel, and aggregates into
`force_`/`forceField_`.
- Pros: matches the S1 architecture (dedicated source + sampler); the paper's
  per-station BEM structure is preserved; a natural home for the S3 rotating
  blade-frame contract; the element CSV stays valid.
- Cons: must suppress the element's own `applyForceField` to avoid double
  counting; AFTAL gains rotation/aggregation plumbing; node→element mapping
  needed.

**B. New element type (`bladeSurfaceElement`) that owns the surface patch.**
The element distributes its own `forceVector_` over the part of the imported
surface between its station and the next; inflow averaging can stay or move to
the nodes.
- Pros: smallest integration delta — `createElements`, rotation, CSV, AFTAL and
  the existing ASM tests all keep working; the force is exactly the element's
  force (no double counting).
- Cons: the imported surface is per blade but each element would load/see it
  (shared cache needed); node↔segment assignment and patch edges must be
  consistent across elements; the element API has no per-node output today.

**C. Generalize the S1 nacelle source into a shared surface source with a
"blade" mode.** One class parameterized by force model (direct-forcing vs BEM
elements) and frame (static vs rotating).
- Pros: one surface implementation (load, kernel, MPI, contract, CSV);
  no duplication.
- Cons: the two force models and frames have little in common beyond geometry
  and kernel; the refactor touches the archived-and-tested nacelle code; risk of
  a god-class.

**Effort:** A/B Medium; C Medium-High.

### 2. What the surface changes physically: distribution law

1. **Distribution-only (paper-faithful, minimal):** keep the existing
   chord-averaged inflow and BEM force per element; replace only the strip
   spread with an area-weighted spread over the real surface nodes of that
   station's patch. `f(X)` remains uniform chordwise (Eq. 17), so the model
   difference vs the no-mesh ASM is exactly the **geometry of distribution**.
2. **Surface-sampled BEM (full):** sample inflow per surface node (Eq. 7) and
   recompute BEM per radial station from surface-averaged quantities; the real
   surface then affects the loads too.
- Option 1 isolates the geometry effect (good for the ALM/ASM/ASM-mesh
  comparison); Option 2 is closer to a "real surface" model but changes two
  things at once. Effort: 1 Low-Medium, 2 Medium-High.

### 3. Blade geometry generation

**A. Extend the generic `geometry/` pipeline with a non-gmsh builder** (e.g.
`src/blade_phasevi.py`, component `blade`), reusing `canonical_triangles`,
`write_binary_stl`, metadata/hash/`--check` and the `_reserved` fields.
- Pros: honors the S1 spec's "blade STLs in the shared pipeline" intent;
  deterministic by construction (structured section loft, fixed triangle
  topology); no gmsh dependency for blades.
- Cons: `makeGeometry.py`'s `Component`/`build_component` assumes a `.geo`;
  needs a builder registry; the reserved names/source row are MEXICO-flavoured.

**B. Generate a `.geo` from the interpolated sections and keep the gmsh path.**
- Pros: zero generator refactor; same determinism machinery.
- Cons: meshing a twisted/tapered lofted surface with a uniform characteristic
  length gives uncontrolled, less reproducible triangle counts per section;
  sliver triangles at the thin trailing edge risk non-manifold STL; extra gmsh
  dependency for every blade regeneration.

**C. Phase VI-local generator under `validation/phaseVI/tools/`.** Same
mechanics as A but scoped to the validation case.
- Pros: no coupling to the generic pipeline's MEXICO reservation; Phase VI
  inputs and STL live together.
- Cons: contradicts the S1 spec/README reservation; a future MEXICO blade would
  duplicate it.

**Effort:** A Medium, B Low, C Low-Medium.

### 4. Validation integration

**A. Third model flag in the existing package** (`-m asm-mesh`, twin
`fvOptions.ASM-MESH`, `case.yaml` entry, `comparePhaseVI.py` third directory +
surface-output converter, prepared-only Slurm array).
- Pros: one comparison script, one acceptance policy, the queued ALM/ASM runs
  are directly comparable.
- Cons: touches the runner/config/tests in several places; the surface STL must
  be staged into every run dir.

**B. Separate comparison script/package.** Isolated but duplicates the merge,
averaging and banding logic.

**Effort:** A Medium, B Low-Medium.

## Recommendation

**Recommended direction (to be decided in proposal/design): Approach 1A or 1B
(a per-blade distributing surface that replaces only the strip spread) + 2.1
(distribution-only, isolating the geometry effect) + 3A or 3C (deterministic
Python blade generator with committed S809 coordinates) + 4A (third model
variant in the existing Phase VI package, prepared-only).** Rationale: the S2
deliverable is a *distribution geometry* upgrade of the delivered ASM; keeping
the BEM chain and the paper's uniform-chordwise force (Eq. 17) makes the
ALM/ASM/ASM-mesh comparison interpretable, and reusing the S1 kernel/MPI
patterns minimizes new physics. The real surface only matters if the mesh can
see it — which the current Phase VI ladder cannot (see Risks) — so the
comparison must be framed as model-form sensitivity, not mesh resolution.

## Reuse map (S1 / existing ASM → S2)

| Asset | Reuse | Notes |
|---|---|---|
| `triSurface` load, node centroids/normals/areas, stable order | Yes | `nacelleSurfaceSampler.C:201-220` |
| `cellSize`, `kernel`, `interpolateVelocity` (Eq. 7/8, MPI reduce) | Yes | `.C:269-292,374-463` |
| `distributeForce` math (Eq. 18) | Yes | `nacelleSurfaceSource.C:163-209`; needs rotating nodes |
| `force.<name>` field, CSV, `cellSetOption`/RTS skeleton | Yes, as template | `nacelleSurfaceSource.C:280-431`; `turbineALSource.C:392` precedent |
| `positions()/forces()/normals()/areas()` contract | Shape yes, frame no | nacelle body frame is static (`.C:36-93`); blade frame rotates |
| Nacelle force model Eq. 19/21-23 | No | blade loads come from the BEM elements |
| `actuatorSurfaceElement` (chord strips) | Inflow chain may stay; strip spread is replaced | `actuatorSurfaceElement.C:103-205` |
| BEM elements, rotation, CSV, AFTAL composition | Stays | `actuatorLineSource.C:131-374,577-647`; `axialFlowTurbineALSource.C:779-817` |
| Time-derived azimuth (restart-safe) | Yes | `turbineALSource.C:315-345,430-432` |
| Geometry canonicalization/hash/`--check`/metadata | Yes | `makeGeometry.py:194-219,355-378,430-502` |
| `_reserved.blade` schema | Yes, must be populated | `makeGeometry.py:371-373`; `README.md:60-88` |
| Phase VI config/generator/compare/slurm | Yes, extended | `case.yaml`, `generate_case.py`, `comparePhaseVI.py`, prepared arrays |

## Validation plan (ALM vs ASM-no-mesh vs ASM-mesh)

- **Baselines:** the queued `phaseVI-prod` / `phaseVI-stage3` runs are the ALM
  and no-mesh ASM references (verified in `squeue`); do not resubmit or cancel
  them. The ASM-mesh variant must use the **same** `case.yaml` mesh, time step,
  solver, schemes, `endEffects`/`dynamicStall` settings and averaging window.
- **Metrics available now:**
  - Turbine-level CP/CT/torque/thrust from `turbine.csv`, per the fixed F1
    formulas in `comparePhaseVI.py:292-317` (bands ±15 %).
  - Spanwise CN/CT at r/R = 0.30/0.47/0.63/0.80/0.95 from
    `sequence_H_spanwise.csv`, compared against element `c_ref_n`/`c_ref_t`
    (`comparePhaseVI.py:259-275`; band max(0.15, 20 %)).
  - Sign gate (TSR match, cp/cd > 0, positive `c_ref_n`/`c_ref_t`).
- **New outputs needed for ASM-mesh:** per-node or per-radial-bin force CSV from
  the surface source (analogous to `writeNodePerf`,
  `nacelleSurfaceSource.C:259-275`), aggregated to the same r/R stations and to
  the same coefficient definitions (`c_ref_n = 0.5*c*cn`,
  `actuatorLineElement.C:683-705`) so the existing compare logic can consume it.
- **Fair-comparison constraints:** identical case config across the three
  models; the kernel/width difference between the no-mesh ASM (Gaussian
  `epsilon = 2*cbrt(V)*meshFactor`, `actuatorSurfaceElement.C:61-100`) and the
  S1 surface kernel (paper cosine, 5-cell support, `nacelleSurfaceSampler.C:374-404`)
  is a **confound** — either document it as part of the model form or offer a
  kernel/width option so the comparison can isolate geometry.
- **Mesh-resolution sensitivity:** the Phase VI ladder has cell sizes
  0.314/0.210/0.157 m (`case.yaml:88-109`); blade chord is 0.218-0.355 m (root
  to tip) and 0.349-0.744 m through the airfoil, so at every affordable mesh the
  chord is 1-2 cells and the surface is effectively sub-grid (the README
  already states the no-mesh version's strips are sub-grid, `README.md:251-262`).
  D/32/48 runs test model form, not resolved-surface physics; that limitation
  must be explicit in the README and acceptance.
- **Acceptance:** reuse the existing banded policy; add a documented,
  pre-registered hypothesis for the geometry effect (e.g. expected sign/size of
  the spanwise load shift and tip/root sensitivity) rather than post-hoc "better
  than ASM" claims.

## Open Questions (decisions needed; none decided here)

1. **C++ shape (blocking for design):** per-blade source (1A), element-type
   patch (1B), or generalized shared source (1C)? This determines the double
   counting control, the rotation hook and the S3 contract home.
2. **Geometry location/naming (blocking for scope):** generic
   `geometry/stl/blade*.stl` (S1 spec intent, currently documented as MEXICO
   source) vs Phase VI-local generator? Two blades, one geometry: is one STL
   enough (blade 2 = azimuthal offset) and what happens to `blade1`/`blade2`
   reserved names?
3. **Generator route (blocking for determinism):** gmsh loft (B) vs
   deterministic Python triangulation (A/C)? The pinned-gmsh `--check` contract
   and byte-identical regeneration must hold for whatever is committed.
4. **S809 coordinates (non-blocking, but a prerequisite):** commit the Table 2
   coordinates with PROVENANCE (source PDF sha256, table, extraction method and
   date). The local dump is available but unverified; the extraction recipe
   needs to be repeatable (no `pdftotext` on this host).
5. **Distribution law (non-blocking):** distribution-only (2.1) vs
   surface-sampled BEM (2.2). Recommendation: 2.1 for the first S2 slice.
6. **Section/node resolution (non-blocking):** how many generated sections vs
   the 26 stations and the 50 interpolated elements; expected surface node count
   (informs the cost); must every node carry `radial_station`/`chord_fraction`
   and which element it feeds?
7. **Frame and contract (non-blocking):** blade-local (rotating) vs global
   frame for per-node CSV and the `positions()/forces()` contract; how the
   rotating frame relates to `angleDeg()`; SI conventions.
8. **Kernel/width confound (non-blocking):** paper cosine for the surface vs
   Gaussian for the no-mesh ASM (and ALM); document as model form, or add a
   selectable kernel/width so the comparison isolates geometry?
9. **Phase VI integration shape (non-blocking):** `-m asm-mesh` third model
   vs a separate `--surface-geometry` option on `-m asm`; twin naming; STL
   staging into run dirs; compare script third input; which prepared arrays (and
   no submission without authorization).
10. **Root/tip handling (non-blocking):** closed STL with root/tip caps vs open
    wetted surface; cylindrical root section; force zeroing at the tip and the
    end-effects interaction (BEM end effects stay); the inboard `chord_mount`
    transition at r = 1.0085.
11. **Performance (non-blocking, but sizing):** the S1 distribution loops all
    local cells per node (`nacelleSurfaceSource.C:169-208`); at 6.7 M-53 M cells
    and O(10^3) surface nodes this is a per-`addSup` cost of O(10^9-10^10)
    prefilter checks. A cell-set/bounding-box restriction or local stencil walk
    will likely be required for Phase VI.
12. **Delivery shape (blocking for apply):** source + generator + Phase VI
    integration + tests + docs will almost certainly exceed the 400-line review
    budget; decide chained slices or `size:exception` before tasks.

## Risks

- **Sub-grid surface (high):** at D/32-D/64 the imported blade surface is below
  the background cell size, so the mesh-based ASM cannot deliver resolved
  chordwise physics; without careful framing the "real mesh" claim is
  unsupportable and the three-way comparison is confounded with kernel/width
  differences.
- **Double counting (high):** if the element strip spread is not suppressed
  when the surface is active, every blade force is applied twice; the switch
  must be additive and regression-gated (`test_alm`, `test_asm`, `test_aftal`,
  `test_aftal_asm`, `test_cftal`, `test_libs`).
- **Performance (high):** naive all-cells-per-node distribution at 22 M-53 M
  cells may make the ASM-mesh runs impractical; must be measured before
  committing to the validation campaign.
- **Geometry determinism (medium-high):** a gmsh-lofted twisted thin blade risks
  sliver/non-manifold triangles and version-sensitive triangle counts; the S1
  canonicalization only reorders triangles, it cannot repair a non-reproducible
  tessellation. A pure-Python structured loft is the safer determinism path.
- **Data provenance (medium):** the S809 coordinates must be committed from the
  verified Somers PDF with a recorded extraction method; the local text dump is
  convenient but not yet a provenance-quality source.
- **Scope conflict with the MEXICO reservation (medium):** S1 documents blades
  as MEXICO geometry in the shared pipeline; the active `mexico-validation`
  change may later want the same component names. Decide the ownership/naming
  now to avoid rework.
- **Regression surface (medium):** touching `nacelleSurfaceSampler` for a shared
  base would re-open S1 code; AFTAL changes touch the shared `addSup` path used
  by every model. Gate on the full pytest suite and byte-identical default
  behavior.
- **HPC authorization (medium):** the ASM-mesh validation runs need the long
  queue; the existing phaseVI arrays are already queued and must not be
  disturbed. New arrays are prepared-only until authorization.
- **Review budget (blocking):** S2 spans C++ source, geometry data/generator,
  Phase VI tooling, tests and docs — over the 400-line `single-pr` policy.

## Ready for Proposal

**Yes.** The code facts are verified with file:line evidence: the no-mesh ASM
mechanics, the exact S1 assets that generalize (load/kernel/interpolation/MPI/
CSV) and those that do not (nacelle force model, static frame), the AFTAL
composition and rotation paths, the gmsh-only geometry pipeline with its
reserved blade schema and tests, the Phase VI inputs/config/tooling and the live
queued runs, and the S809 extraction situation. The orchestrator should surface
three decisions before/inside the proposal: **(1) the C++ shape** (per-blade
source vs element patch vs generalized source) and the double-counting control;
**(2) the blade geometry home/generator route** (shared `geometry/` pipeline vs
Phase VI-local; gmsh loft vs Python loft) including the S809 coordinate
provenance; and **(3) the Phase VI integration shape and delivery slicing**
(third model variant + compare extension + prepared-only HPC arrays, given the
sub-grid-surface limitation and the 400-line review budget). S3 (preCICE FSI)
remains deferred.
