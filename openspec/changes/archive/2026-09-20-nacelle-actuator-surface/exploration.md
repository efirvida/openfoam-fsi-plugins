# Exploration: Nacelle/hub actuator surface model (ASM) + geometry pipeline + FSI seams

Change: `nacelle-actuator-surface` — project: `of-plugins` — date: 2026-09-19
Scope: `turbinesFoam/` (+ geometry pipeline; adapter read-only for the FSI seams).
Slice: **S1** of a staged program (S2 = blade STL surface option, S3 = preCICE FSI
wiring — both future changes; S3 deferred until S1–S2 validated).
Reference: Yang & Sotiropoulos, arXiv:1702.02108v4 (2018) — **Sec. 2.2** (nacelle
ASM) and **Sec. 4.1** (periodic-nacelle validation case). All paper content cited
from the arXiv HTML version; no paper numbers are invented.

## Current State

### 1. The nacelle path in AFTAL is a null-deref waiting for a user (verified)

- `axialFlowTurbineALSource::createNacelle()` is an empty stub — `axialFlowTurbineALSource.C:471-474`.
- `read()` sets `hasNacelle_ = true` whenever a non-empty `nacelle {}` subdict exists
  (`axialFlowTurbineALSource.C:984-988`); the constructor then calls the stub
  (`axialFlowTurbineALSource.C:609-612`).
- `nacelle_` is an `autoPtr<actuatorLineSource>` that is **never set** (declared
  `axialFlowTurbineALSource.H:76`). Any `nacelle {}` therefore crashes in all three
  `addSup` overloads via `nacelle_->addSup(...)` / `nacelle_->forceField()` /
  `nacelle_->force()` — `axialFlowTurbineALSource.C:780-789` (rho-less momentum),
  `:874-883` (compressible momentum), `:944-948` (scalar turbulence eqn). The
  comments even copy-paste "Add source for tower actuator line" (`:782`, `:876`).
- `crossFlowTurbineALSource` has **no** nacelle concept at all (no
  `createNacelle`/`hasNacelle_`/`nacelle_` matches in its sources).
- Consequence: today, `nacelle {}` is unusable. Fixing it is mandatory for S1 and
  must be **additive**: no `nacelle {}` → `hasNacelle_ == false` → current
  behavior byte-identical (the three `addSup` bodies skip the block).

### 2. Composition and the delivered blade ASM (verified)

- `fv::option` RTS → `turbineALSource` (protected `PtrList<actuatorLineSource>
  blades_`, `turbineALSource.H:105`) → `axialFlowTurbineALSource` /
  `crossFlowTurbineALSource` (build one `bladeSubDict` per blade and `new
  actuatorLineSource(...)`, `axialFlowTurbineALSource.C:75-291`) →
  `actuatorLineSource` (`:56-58` derives `cellSetOption`; `PtrList<actuatorLineElement>
  elements_`, `actuatorLineSource.H:94`) → `actuatorLineElement`.
- The blade ASM is **delivered** (`actuatorSurfaceElement.{H,C}`): `New` is now
  implemented (defaults to base type, `actuatorLineElement.C:47-81`), `elementType`
  + `nChordwise` pass through `createElements` (`actuatorLineSource.C:337-346`,
  selection at `:365-369`), and the subclass registers via
  `addToRunTimeSelectionTable` (`actuatorSurfaceElement.C:38-44`), overriding only
  `calcProjectionEpsilon` / `applyForceField` / `calculateInflowVelocity`
  (`actuatorSurfaceElement.H:81-88`). Tutorial `axialFlowTurbineASM` uses
  `elementType actuatorSurfaceElement; nChordwise 5;`. ALM remains the default
  (`elementType` defaults to `actuatorLineElement`).
- Element public accessors exist for the FSI/contract work: `position()`,
  `velocity()`, `force()`, `relativeVelocity()`, `angleOfAttack()`,
  `liftCoefficient()`… (`actuatorLineElement.H:299-339`). Turbine internals are
  protected: `blades_` (`turbineALSource.H:105`), `hub_`/`tower_`/`nacelle_`
  (`axialFlowTurbineALSource.H:70-76`), `torque_` (`turbineALSource.H:123`),
  `angleDeg_` (`:84`). `force.<turbine>` is a registered `volVectorField`,
  `IOobject::AUTO_WRITE` (`turbineALSource.C:199-223`) — the established
  registry-exposure precedent.

### 3. Kinematics are incremental, not time-derived (verified — the FSI seam)

- `turbineALSource::rotate()` does `angleDeg_ += radToDeg(radians)` with
  `radians = omega_*deltaT` (`turbineALSource.C:152-160`) and `updateTSROmega()`
  recomputes `omega_` from `angleDeg_` (`:143-149`, `meanTSR_` + optional
  `tsrAmplitude_`/`tsrPhase_` oscillation, `:316-317`).
- `addSup` triggers rotation only when the time advanced
  (`time_.value() != lastRotationTime_`, `axialFlowTurbineALSource.C:726-729`,
  `:820-823`, `:915-918`).
- `angleDeg_` is **never persisted** (grep: only `+=` at `:157`, CSV output at
  `:273`, debug print at `:171`, init at `:196`) → a `startFrom latestTime`
  restart resets the azimuth to 0 and re-integrates TSR oscillation incorrectly;
  a preCICE rollback would likewise leave the accumulator stale. This is the
  idempotency gap the seam must close.
- No `Function1` hook exists in turbinesFoam (grep: only transitive `.dep`
  references in build artifacts). The `fsiOmega/preciceOmega` Function1 exists
  but is consumed **only** by the motion solver (`rotatingMotion` in
  `dynamicMeshDict`; `preciceOmega.H` docstring: reads a
  `uniformDimensionedScalarField` "omega" updated by the preCICE adapter) —
  never by `turbineALSource`. Confirmed: adapter `globalData` interfaces can
  exchange a `uniformDimensionedScalarField` (`modules/generic/Generic.C:29-66`,
  `ReadWrite.C:425-445`).

### 4. Adapter facts relevant to the S1 seams (verified)

- preCICE v3+: `Adapter.H:23` uses `PRECICE_VERSION_GREATER_EQUAL(3, 2, 0)`.
- Coupling meshes are **patch or cellSet only** (`CouplingDataUser.H:35-39`
  `patchIDs_`/`cellSetNames_`; `Interface.C:122-124` adds `globalData`); there is
  **no point-cloud mesh source** — S3 will need one for surface nodes.
- Checkpointing copies `vol*/surface*/point*` GeometricFields only
  (`Adapter.C:922-935`); `uniformDimensionedScalarField` is explicitly not
  handled ("NOTE: Add here other object types to checkpoint, if needed.",
  `:935`) — so an omega/angle scalar field is not rolled back by the adapter
  today. `Adapter.C:935` is the exact seam for S3.
- FSI force module is face/patch-oriented (pressure + viscous on patches,
  `modules/FSI/ForceBase.C:126-182`); a body-frame surface-node force contract
  (`positions()`/`forces()`) is a different shape — to be provided by the S1
  sampling object, not by the adapter.

### 5. Geometry / formats / tooling (verified)

- `elementData` rows: `(axialDistance radius azimuth chord chordMount twist)`
  (`axialFlowTurbineALSource.C:136-143`; tutorial
  `axialFlowTurbineASM/system/elementData` header comment). Hub/tower use
  `(axialDistance height diameter)` (`:311-313`, `:399-401`).
- `profileData` (single-Re and multi-Re) in `tutorials/resources/foilData/`.
- STL reading: `triSurface::New(fileName)` auto-detects STL ASCII/binary
  (`$FOAM/src/surfMesh/triSurface/triSurfaceNew.C:86-97`); the class lives in
  **libsurfMesh** (`src/surfMesh/Make/files`). turbinesFoam currently links only
  `-lfiniteVolume -lsampling -lmeshTools -lfvOptions` (`turbinesFoam/src/Make/options`)
  → adding `-lsurfMesh` (+ `-I$(LIB_SRC)/surfMesh/lnInclude`) is required; the
  triSurface **search** utilities are already in `-lmeshTools`.
- gmsh available at `~/venv/bin/gmsh` (verified on this host).
- Validation conventions (NREL Phase VI precedent, `turbinesFoam/validation/phaseVI/`):
  `config/case.yaml` single source of truth → `tools/generate_case.py`
  (renderer + non-destructive `--check`) + `tools/element_data.py` +
  `scripts/makeElementData.py` (provenance banner, `--check` stale detection) +
  `data/{geometry,polars,experiment}/` with per-dir `PROVENANCE.md` +
  `scripts/runPhaseVI.sh` (+ `slurm/stage0.slurm` dev-partition job,
  `slurm/production.slurm` prepared-only) + committed `case/` skeleton +
  gitignored `runs/`/`results/` + `test_phasevi_{case,compare,data}.py` pure-Python
  pytest modules. This is the pattern to mirror.
- Tests: pytest integration suite (solver-driven modules skipped without
  OpenFOAM, `tests/conftest.py`); wmake build (`./Allwmake`); root `AGENTS.md`
  SDumont env recipe.

### 6. The paper's nacelle model (Sec. 2.2) and validation case (Sec. 4.1)

Requirement-level mapping (exact equations belong to design):

| Paper (arXiv:1702.02108v4) | Requirement for S1 |
|---|---|
| Nacelle = actual surface, forces distributed from it (Sec. 2.2 intro) | Surface triangulation read from an STL; per-node force samples |
| Normal force via direct-forcing IBM, Eq. (19): `f_n = h(−u^d + ũ)·e_n/Δt · e_n` with `h=(hx·hy·hz)^(1/3)`, `ũ` interpolated from the flow (Eqs. 7, 20), desired velocity `u^d` (0 for a stationary body) | Per-node normal force from sampled flow velocity, local cell size `h`, and `Δt`; `e_n` from the surface normal |
| Tangential force, Eq. (21): `f_τ = ½·cf·U²·e_τ`, `U` = reference incoming velocity (magnitude of streamwise incoming velocity in the paper) | Tangential force magnitude from a friction coefficient and a reference velocity |
| `cf` from Schultz–Grunow, Eq. (22): `cf = 0.37·(log Rex)^(−2.584)`, `Rex` from incoming velocity and distance from the upstream edge | Friction coefficient model keyed by streamwise distance from the nacelle nose |
| Tangential direction, Eq. (23): `e_τ = u(X + h·e_n)/|u(X + h·e_n)|` | Tangential direction sampled at a probe point `h` off the wall |
| Distribution, Eq. (18): smoothed delta kernel over the closest ~5 cells | Gaussian/spread kernel onto the cellSet; per-node area weights; total force preserved |
| Blade-inflow remedy (Sec. 2.2, last paragraph): relative velocity of the 2 blade stations closest to the nacelle set equal to the 3rd | **Deferred to S3** (only matters in a coupled rotor run); record as a design note |
| Sec. 4.1 periodic nacelles: hemisphere + cylinder, Re=1000 (cylinder radius R), domain 30R×20R×20R, periodic streamwise + free-slip crosswise; grids 502×348×348 (Δx=R/8, wall-resolved LES reference), 115×151×151 (Δx=R/3.75), 153×80×80 (Δx=R/2.5); 2652 surface triangles; permeable-disk comparison CD=0.48 | Validation anchor case (see Benchmark); 2652-triangle target surface; metrics = time-averaged ⟨u⟩, k, (stretch PSD) at 1R/3R/5R/7R downstream vs the paper's wall-resolved LES |
| Findings (Sec. 4.1): coarse ASM good at 1R and far wake, deficits too large at 3R–7R; medium grid good at all stations; permeable disk underpredicts everywhere | Acceptance must be set per-station/grid (coarse ≠ medium); do not over-promise coarse-grid agreement |

## Affected Areas

- `turbinesFoam/src/fvOptions/nacelleSurface/…` — NEW `nacelleSurfaceSource`
  (or equivalent) + surface sampling object (see Approaches).
- `turbinesFoam/src/fvOptions/axialFlowTurbineALSource/axialFlowTurbineALSource.{H,C}`
  — implement `createNacelle()` (build the nacelle source from `nacelleDict_`),
  rotate/tilt/yaw remain blade+hub only (nacelle static); null-deref fixed
  additively (`:471-474`, `:780-789`, `:874-883`, `:944-948`).
- `turbinesFoam/src/fvOptions/turbineALSource/turbineALSource.{H,C}` — idempotent,
  time-derived kinematics (replace `angleDeg_ +=` accumulation, `:152-160`);
  optional `omega` override source (Function1 or registry
  `uniformDimensionedScalarField`, mirroring `fsiOmega/preciceOmega`).
- `turbinesFoam/src/Make/files` + `Make/options` — register new `.C`; add
  `-lsurfMesh` and `-I$(LIB_SRC)/surfMesh/lnInclude` for `triSurface`.
- NEW `turbinesFoam/geometry/` — gmsh `.geo` + Python pipeline → per-component
  STL + metadata JSON + PROVENANCE (shared by S2; see Approaches).
- NEW `turbinesFoam/validation/nacelle-asn/` (or similar) — periodic-nacelle
  case + data (digitized paper profiles + PROVENANCE) + scripts + slurm.
- `turbinesFoam/tests/` — `test_nacelle.py` (integration), `test_nacelle_data.py`
  (pure-Python, CI-safe); existing `test_aftal.py`/`test_aftal_asm.py` regression gate.
- `turbinesFoam/README.md`, root `README.md`, root `CHANGELOG.md` — config keys,
  tutorial, validation reference, attribution.
- Untouched in S1: `actuatorLineElement`/`actuatorSurfaceElement`, `profileData`,
  dynamic stall, end effects, CFTAL, the adapter (`modules/*`), `fsiOmega`.

## Approaches

### 1. Where the nacelle model lives

**A. Dedicated `fv::option` source class + reusable surface-sampling object (recommended)**
New class `nacelleSurfaceSource` (derives `cellSetOption`, registered in the
`option` RTS as `type nacelleSurfaceSource;`), owning a surface-sampling object
(triangulation, node positions/normals/areas, per-node forces). Usable two ways:
standalone (`fvOptions` entry — exactly the periodic-nacelle case, no turbine
needed) **and** composed by `axialFlowTurbineALSource::createNacelle()` as an
`autoPtr` child (same pattern as `hub_`/`tower_`, `axialFlowTurbineALSource.C:371-379`).
- Pros: paper model maps 1:1 (no BEM, no CL/CD — the element machinery is the
  wrong abstraction); standalone registration makes the validation case trivial
  and keeps the FSI seam host in one object; fixes the null-deref additively;
  reusable by CFTAL/S3 without touching the blade pipeline.
- Cons: new source class (~350–450 lines) duplicates some `cellSetOption`
  plumbing; AFTAL must hand it the cellSet/fieldNames the way it does for
  `actuatorLineSource` children.
- Effort: Medium.

**B. Nacelle as an `actuatorLineSource` with a new `nacelleSurfaceElement` type**
`createNacelle()` builds `elementGeometry` from STL triangle centroids (normal →
`chordDirection`, area → `chordLength`) and a new element type computes the
direct-forcing/tangential forces in an overridden `calculateForce`.
- Pros: reuses selection, CSV, MPI, forceField machinery wholesale; consistent
  with the hub/tower precedent (which already abuses `chordLength = diameter`,
  `axialFlowTurbineALSource.C:341`).
- Cons: semantic abuse gets worse (no meaningful cl/cd/alpha; `createElements`
  interpolates a **1-D line**, nacelle surface is 2-D — needs
  `nElementsPerSegment == 1` bypass); overrides pile up on the BEM-shaped API;
  standalone validation case still needs a turbine-less entry point.
- Effort: Medium (more per-line wrestling than A).

**C. Inline `createNacelle()` in AFTAL only**
Implement the surface model directly inside `axialFlowTurbineALSource`.
- Pros: smallest diff surface.
- Cons: bloats the turbine class; not reusable (CFTAL, standalone nacelle case);
  FSI seam has no home; validation case impossible without a full turbine.
- Effort: Low-Medium. Extensibility: poor.

**Recommendation: A.** The paper's nacelle model is not blade-element physics;
Option B forces it through a line-oriented API, and C cannot host the validation
case or the S3 seam. A matches the paper's own usage (Sec. 4.1 runs the nacelle
model without any rotor) and the repository's composition precedent.

### 2. Geometry pipeline placement and formats

**A. Shared `turbinesFoam/geometry/` tree (recommended)**
`geometry/src/` (gmsh `.geo` + `makeGeometry.py`), `geometry/stl/` (committed,
binary STL, per component: blade ×3 + hub/nacelle), `geometry/metadata/` (JSON:
per-node radial station + chord-fraction mapping for blades; per-node normals +
areas for the nacelle), `geometry/PROVENANCE.md` (source references: MEXICO rotor
tables, the paper's nacelle description; generator version; sha256 of inputs).
- Pros: one pipeline feeds S1 (nacelle STL) and S2 (blade STL surface option);
  deterministic/regenerable via `makeGeometry.py --check` (mirrors
  `makeElementData.py`); STL is the OpenFOAM-native surface format
  (`triSurface::New` auto-detects it) and the snappyHexMeshDict geometry format.
- Cons: new top-level tree; blade STL generation is S2-consumed but S1-produced
  (scope creep risk — keep S1 blade STL minimal: geometry only, no consumption).
- Effort: Medium.

**B. Geometry under the validation case only** (`validation/nacelle-asn/data/geometry/`)
- Pros: smallest scope; only the nacelle STL is needed for S1.
- Cons: S2 re-factors it out later; no home for the blade STLs the S1 scope
  explicitly lists.
- Effort: Low.

**Recommendation: A**, with S1 producing: nacelle/hub STL (consumed), blade STLs
(artifacts only, consumed in S2), metadata JSON, and provenance.

### 3. FSI-readiness seams (design + minimal refactor, no preCICE)

**A. Time-derived idempotent kinematics (recommended)**
Replace the `angleDeg_ += omega_*dt` accumulator with `angleDeg_ = integral of
the omega law over [t0, t]` — for constant TSR this is `omega*t`; for the
`tsrAmplitude` oscillation it is the closed-form sine integral. Add an optional
`omega` override (Function1, or a registry `uniformDimensionedScalarField`
mirroring `fsiOmega/preciceOmega`), defaulting to the existing TSR law so results
are identical when unset. Register `angleDeg_` (and optionally `omega_`) as a
`uniformDimensionedScalarField` for restart/rollback idempotency; expose
`angleDeg()` accessor.
- Pros: additive (default byte-identical); restart-safe; rollback-safe; the
  `uniformDimensionedScalarField` is exactly what the adapter's `globalData`
  ReadWrite can already exchange (S3) and where `Adapter.C:935` will add
  checkpoint coverage.
- Cons: touches the shared turbine base class — gate with the existing pytest
  suite (CSV `angle_deg` column must match to floating-point).
- Effort: Low-Medium.

**B. Surface-sampling contract** — the nacelle source's sampling object exposes
`positions()` / `forces()` (+ `normals()`, `areas()`), SI, body frame, stable
node ordering; forces registered as a named object (precedent: `force.<name>`
volVectorField, `turbineALSource.C:199-223`) and as per-node data for a later
point-cloud mesh source. No adapter change in S1.
- Effort: Low (part of the sampling object in Approach 1A).

**Recommendation: A + B.** S3 then only adds the adapter point-cloud mesh source
and checkpoint coverage; the turbine/nacelle side is already contract-stable.

### 4. Benchmark: periodic-nacelle case

**A. Paper-faithful coarse+medium ASM vs digitized wall-resolved LES (recommended)**
Domain 30R×20R×20R (periodic streamwise, free-slip crosswise), hemisphere+cylinder
nacelle, Re=1000, surface mesh ≈2652 triangles (paper's count); grids: coarse
153×80×80 (~1M cells, Δx=R/2.5) and medium 115×151×151 (~2.6M cells, Δx=R/3.75).
Metrics: time-averaged ⟨u⟩(z) and k(z) profiles at 1R/3R/5R/7R (+10R stretch),
drag coefficient; reference = paper's wall-resolved LES profiles (Fig. 5/6),
digitized with PROVENANCE. Solver: pimpleFoam; turbulence: LES (WALE or
Smagorinsky; the paper uses dynamic SGS, not in standard OpenFOAM — document the
adaptation) for comparability, or URANS k-ω SST as a cheaper fallback with
documented caveats. Acceptance per-station (coarse vs medium differ in the paper).
- Pros: matches the paper's own standalone-usage case (no rotor); the coarse grid
  (~1M cells) fits the dev partition for mesh gen + stability + partial stats;
  the model is validated in isolation before any rotor coupling.
- Cons: LES statistics need several flow-through times (30R/U each) → production
  averaging needs the long queue; figure digitization is the only data source
  (paper figures, no tables).
- Effort: Medium-High.

**B. Minimal mechanics smoke only** — one coarse run, qualitative deficit check.
- Pros: fits the 20-min dev partition completely.
- Cons: not a genuine validation; weak claim.
- Effort: Low.

**Recommendation: A, staged**: (0) everything prepared + dev-partition mesh/stability
while long-queue authorization is pending; (1) coarse-grid LES partial statistics
on the dev partition; (2) production averaging on the long queue after
authorization (nothing launched before). Reuse from `validation/phaseVI/`: the
`config.yaml` + `generate_case.py --check` + slurm stage pattern; from the active
`mexico-validation` exploration: the digitize-with-PROVENANCE data convention and
the two-source cross-check rule.

### 5. Nacelle null-deref fix shape (part of Approach 1A)

Implement `createNacelle()` to construct the nacelle source from `nacelleDict_`
(geometry STL path, friction model, reference velocity, kernel params, cellSet);
`FatalError` if the STL is missing/invalid rather than silently continuing;
`hasNacelle_ == false` path untouched. Config surface: `nacelle { geometry stl; … }`
— no change to existing keys; `includeNacelleDrag_` semantics preserved
(`axialFlowTurbineALSource.C:989-993`).

## Recommendation

**Approach 1A (dedicated `nacelleSurfaceSource` + surface-sampling object) +
2A (shared `turbinesFoam/geometry/` pipeline) + 3A/3B (time-derived kinematics +
positions()/forces() contract) + 4A (paper-faithful periodic-nacelle case,
staged)**. Rationale: the paper's nacelle model is a bluff-body force model with
no BEM content — forcing it into the element API (B) or the turbine class (C)
entrenches the wrong abstraction, while A gives the validation case (which the
paper itself runs rotor-less) and the S3 FSI seam a natural home. The kinematics
refactor is small, additive, and gateable by the existing pytest suite. The
geometry pipeline is S1's main new asset and S2's input, so it belongs at
`turbinesFoam/geometry/`.

Rough work decomposition (not tasks):

- **W1 — Core nacelle source:** `nacelleSurfaceSource.{H,C}` + sampling object
  (triSurface read, normals/areas, direct-forcing + friction forces, kernel
  spread, CSV); `Make/files` + `-lsurfMesh`; `createNacelle()` wiring + null-deref
  fix; `tests/test_nacelle.py` (standalone nacelle fvOptions case, force CSV
  checks); regression: full pytest. ~600–800 lines.
- **W2 — Geometry pipeline:** `geometry/` (gmsh `.geo` for nacelle + blades,
  `makeGeometry.py`, STLs, metadata JSON, PROVENANCE) + pure-Python
  `test_nacelle_data.py`. ~400–600 lines (mostly data/scripts).
- **W3 — Kinematics seam:** time-derived `angleDeg_` + optional omega override +
  registry field + accessor; CSV-identical gate. ~100–200 lines.
- **W4 — Validation package:** `validation/nacelle-asn/` (case skeleton, config,
  digitized LES profiles + PROVENANCE, compare script, slurm stage0/production).
  ~400–600 lines.
- Forecast: **1500–2200 changed lines** — far over the 400-line `single-pr`
  review policy. Flag for chained PR slices ([W1] → [W2] → [W3] → [W4]) or an
  explicit `size:exception`.

## Risks

- **Review budget (blocking):** W1–W4 exceed the 400-line policy under
  `single-pr`; unresolved delivery shape blocks apply.
- **Null-deref fix safety:** the fix touches all three `addSup` overloads of the
  shared AFTAL path; gate = existing pytest suite + `test_libs.py`; default path
  must stay byte-identical.
- **Kinematics refactor:** `angleDeg_`/TSR-oscillation behavior changes must be
  CSV-identical for existing cases (integration tests only, no C++ unit tests);
  restart/rollback idempotency is the acceptance, not a behavior change.
- **No C++ unit tests:** nacelle force math (normal direct-forcing, cf, kernel)
  verified only via integration CSVs and the ALM-free validation case; add a
  Python-side expected-value check in `test_nacelle.py` (known velocity field →
  expected force).
- **Data sourcing:** the only reference data is the paper's own figures
  (wall-resolved LES profiles) — digitization needs PROVENANCE and a
  cross-check; the paper's `cf` (Schultz–Grunow) is zero-pressure-gradient —
  document validity limits for the hemisphere nose region.
- **LES vs URANS:** paper uses dynamic SGS LES; OpenFOAM lacks the dynamic model
  — WALE/Smagorinsky adaptation must be documented; acceptance per-station
  (coarse vs medium differ in the paper — don't over-promise coarse agreement).
- **Compute:** LES averaging of several flow-through times needs the long queue
  (authorization pending); dev partition covers mesh gen + stability + partial
  statistics only; medium grid (2.6M cells) and fine (60M, reference-only) on
  the long queue.
- **v2506 API constraints:** new code must follow `get<word>`, no `List` from
  iterators, `Pstream` guidance (AGENTS.md); `triSurface` requires `-lsurfMesh`
  (link-line change affects every turbinesFoam build — verify no symbol
  conflicts with the already-linked `-lmeshTools`).
- **Fork divergence:** new source class + geometry tree increase divergence from
  upstream turbinesFoam; acceptable, document in README.
- **MPI:** nacelle surface points on other processors than their cells — reuse
  the `reduce(minOp)` sentinel pattern from `actuatorSurfaceElement.C:73-92` and
  the bounding-box `findCell`; fatal on unreachable samples.
- **En gram mirror:** hybrid persistence requested, but no Engram MCP tools are
  available in this session — the file `openspec/changes/nacelle-actuator-surface/
  exploration.md` is the deliverable (noted per instructions).

## Open Questions

1. **Delivery shape (BLOCKING):** ~1500–2200 changed lines vs the 400-line
   `single-pr` policy. Chained PRs [W1 core] → [W2 geometry] → [W3 kinematics] →
   [W4 validation], or explicit `size:exception`? User decision before proposal.
2. **Turbulence closure for the validation case (BLOCKING for W4):** LES
   (WALE/Smagorinsky, paper-comparable, more compute) vs URANS k-ω SST (cheaper,
   weaker claim)? Recommend LES for the headline, URANS as a smoke fallback.
3. **Config shape (NON-BLOCKING):** `nacelle { geometry "stl"; cfModel
   schultzGrunow; referenceVelocity <U∞|sampled>; … }` — confirm keys in
   proposal/design; keep `includeInTotalDrag` semantics.
4. **Blade STL scope in S1 (NON-BLOCKING):** produce blade STLs as artifacts
   only (consumed in S2), or defer blade STL generation entirely to S2?
5. **Restart idempotency depth (NON-BLOCKING):** register `angleDeg_` as a
   `uniformDimensionedScalarField` now (S1) — or only design the seam and add
   the field when S3 needs it?
6. **Paper `cf` validity (NON-BLOCKING):** keep the paper's Schultz–Grunow
   relation as the only option, or add a user-overridable constant `cf` for
   calibration studies (cheap, useful for the drag-coefficient comparison)?

## Risks (summary)

See per-section risks above; the top three: (1) review budget/delivery shape,
(2) data digitization + closure choice for the validation case, (3) shared-path
regression (null-deref fix + kinematics refactor) gated only by integration tests.

## Ready for Proposal

**Yes.** Code facts verified with file:line evidence (nacelle stub + null-deref
sites, incremental kinematics, delivered element RTS, adapter seams, STL
readability via `-lsurfMesh`, phaseVI tooling pattern). Paper Sec. 2.2/4.1 mapped
to requirements; the periodic-nacelle case is a rotor-less validation anchor that
fits the staged HPC plan (dev partition now, long queue after authorization). The
orchestrator should tell the user two decisions gate the proposal: **(1) delivery
shape** (chained PRs vs `size:exception`, since the change exceeds the 400-line
`single-pr` budget), and **(2) turbulence closure** for the validation case (LES
WALE recommended vs URANS fallback). S3 (preCICE wiring) stays deferred as agreed;
S1 delivers the seams (time-derived kinematics, positions()/forces() contract,
registry exposure) but no adapter changes.