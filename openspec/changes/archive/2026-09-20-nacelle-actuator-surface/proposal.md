# Proposal: Nacelle/hub actuator surface model (ASM) + geometry pipeline + FSI seams

## Intent

`turbinesFoam` has no working nacelle/hub force model. `axialFlowTurbineALSource`
declares a `nacelle {}` subdict and a `nacelle_` `autoPtr` but `createNacelle()` is
an empty stub (`axialFlowTurbineALSource.C:471-474`) and the pointer is never set —
so any `nacelle {}` in a case dereferences null in all three `addSup` overloads
(momentum `:780-789`/`:874-883`, scalar turbulence `:944-948`). Separately, the
rotor kinematics are incremental (`angleDeg_ += omega_*dt`,
`turbineALSource.C:152-160`) and never persisted, so a `startFrom latestTime`
restart or a preCICE rollback silently resets the azimuth and re-integrates the TSR
oscillation incorrectly — an idempotency gap that blocks FSI.

This change (slice **S1** of a staged program) adds the paper's **nacelle/hub
actuator surface model** (Yang & Sotiropoulos, arXiv:1702.02108v4, Sec. 2.2) as a
dedicated, reusable `fv::option` source — forces sampled from the actual nacelle
surface, normal component via the direct-forcing IBM closure, tangential component
via a friction coefficient and a reference incoming velocity — and wires it into
`axialFlowTurbineALSource::createNacelle()` so the null-deref is fixed additively.
It also delivers a deterministic geometry pipeline that produces the nacelle STL,
lays down the FSI-readiness seams (time-derived idempotent kinematics + a stable
`positions()`/`forces()` sampling contract) without implementing preCICE, and
packages the paper's periodic-nacelle-array case as the validation anchor.

The change must be additive: with no `nacelle {}`/geometry configured,
`hasNacelle_ == false` and the three `addSup` bodies skip the nacelle block, so
current behavior stays byte-identical and ALM remains the default.

## Scope

### In Scope
- **Nacelle/hub actuator surface source** (`nacelleSurfaceSource` + reusable
  surface-sampling object): STL triangulation read (`triSurface::New`), per-node
  positions/normals/areas, normal force via the direct-forcing IBM closure
  (Eq. 19, `f_n = h(-u^d + u_tilde)*e_n/Dt * e_n`, `h = (hx*hy*hz)^(1/3)`,
  `u^d = 0`), tangential force via the friction model (Eq. 21,
  `f_tau = 0.5*cf*U^2*e_tau` with `cf` from Schultz-Grunow Eq. 22 and an optional
  constant override), smoothed kernel distribution onto the cellSet (Eq. 18), CSV
  output, and MPI handling. Usable standalone (an `fvOptions` entry — exactly the
  rotor-less validation case) and composed via `createNacelle()`.
- **Null-deref fix**: implement `createNacelle()` to build the nacelle source from
  `nacelleDict_`; `FatalError` on a missing/invalid STL; the `hasNacelle_ == false`
  path untouched (additive, byte-identical default).
- **Geometry pipeline** (`turbinesFoam/geometry/`): gmsh `.geo` + Python
  (`makeGeometry.py`) → per-component STL + metadata JSON + provenance, deterministic
  and regenerable (`--check`, mirroring `makeElementData.py`). S1 produces the
  nacelle/hub STL (consumed) and metadata + provenance; the layout/schema accommodate
  blade STLs but blade generation is deferred to S2.
- **FSI-readiness seams** (design + minimal additive refactor, no preCICE):
  time-derived idempotent rotor kinematics (replace the `angleDeg_` accumulator with
  an integral of the omega law; optional omega override; register `angleDeg_` as a
  `uniformDimensionedScalarField` for restart/rollback idempotency) and the
  surface-sampling object's stable `positions()`/`forces()` (+ `normals()`,
  `areas()`) contract — SI, body frame, force-on-body, registry exposure.
- **Validation anchor** (`turbinesFoam/validation/nacelle-asn/`): the paper's
  periodic-nacelle-array case (hemisphere + cylinder, Re=1000, domain
  30R x 20R x 20R, ~2652-triangle surface) with coarse+medium grids, digitized
  wall-resolved-LES reference profiles + provenance, compare script, and slurm
  staging mirroring the `validation/phaseVI/` pattern (dev partition now, long queue
  after authorization).
- **Tests + docs**: `tests/test_nacelle.py` (integration) and
  `tests/test_nacelle_data.py` (pure-Python, CI-safe); `Make/files` + `-lsurfMesh`
  link change; `turbinesFoam/README.md`, root `README.md`, root `CHANGELOG.md`.

### Out of Scope
- Blade STL **generation** and consumption, and the MEXICO surface case — deferred to
  S2 (MEXICO geometry tables are un-sourced; the pipeline architecture accommodates
  blades but does not produce them in S1).
- preCICE/adapter changes (S3): no point-cloud mesh source, no `Adapter.C:935`
  checkpoint coverage, no blade-inflow remedy (Sec. 2.2 last paragraph). S3 deferred
  until S1-S2 are validated.
- Wall-resolved CFD meshes and boundary-layer resolution — the ASM grids are coarse
  vs. the paper's reference.
- Blade-element physics changes (BEM coefficients, dynamic stall, end effects,
  added mass, `profileData`) — untouched.
- CFTAL/VAWT nacelle support — `crossFlowTurbineALSource` has no nacelle concept;
  unchanged.
- The paper's exact dynamic SGS LES model (not available in standard OpenFOAM).

## Capabilities

> This section is the CONTRACT between proposal and specs phases.
> The sdd-spec agent reads this to know exactly which spec files to create or update.
> Existing capabilities in `openspec/specs/`: `actuator-surface-element`,
> `element-type-selection`, `axial-flow-turbine-asm-tutorial`,
> `phasevi-data-provenance`, `phasevi-run-and-compare`, `phasevi-validation-case`.

### New Capabilities
- `nacelle-surface-source`: the nacelle/hub actuator surface `fv::option` source and
  its force model — STL surface triangulation, direct-forcing normal force,
  friction-based tangential force (Schultz-Grunow `cf` with optional constant
  override), smoothed kernel distribution, standalone and composed via
  `createNacelle()` (which also closes the null-deref).
- `surface-sampling-contract`: the reusable surface-sampling object's stable
  `positions()`/`forces()` (+ `normals()`, `areas()`) contract — SI units, body
  frame, force-on-body, stable node ordering, registry exposure (`force.<name>`
  precedent) — the S3 FSI seam host.
- `turbine-geometry-pipeline`: the shared `turbinesFoam/geometry/` gmsh + Python
  pipeline producing per-component STL + metadata JSON + provenance, deterministic
  and regenerable (`--check`), laid out to accommodate blade STLs in S2.
- `time-derived-kinematics`: idempotent time-derived rotor kinematics — `angleDeg_`
  computed from an integral of the omega law over `[t0, t]` (not an accumulator),
  optional omega override source, and registry persistence for restart/rollback
  idempotency.
- `nacelle-validation-case`: the paper-faithful periodic-nacelle-array benchmark
  (coarse + medium grids, digitized wall-resolved-LES reference + provenance,
  staged HPC) with per-station acceptance.

### Modified Capabilities
- None. No existing capability in `openspec/specs/` changes at the spec level: the
  nacelle path and kinematics are new behavior, and the default ALM path (blade
  ASM, element selection, phaseVI validation) is preserved byte-identical. The
  `createNacelle()` wiring and kinematics refactor are additive internal changes to
  `axialFlowTurbineALSource`/`turbineALSource`, not requirement changes to any
  existing capability.

## Approach

Adopt the recommended architecture from exploration (decision level):

- **A — Dedicated `nacelleSurfaceSource` + reusable surface-sampling object.** The
  paper's nacelle model is a bluff-body force model with no BEM content; forcing it
  through the element API (`actuatorLineSource`/`actuatorSurfaceElement`) or inline
  in AFTAL entrenches the wrong abstraction. A dedicated `cellSetOption`-derived
  source maps 1:1 to Sec. 2.2, hosts the validation case (which the paper itself
  runs rotor-less), and gives the S3 FSI seam a stable home. It is usable standalone
  (`fvOptions` entry) and composed by `axialFlowTurbineALSource::createNacelle()` as
  an `autoPtr` child (same pattern as `hub_`/`tower_`).
- **B — Shared `turbinesFoam/geometry/` pipeline.** One deterministic gmsh + Python
  pipeline feeds S1 (nacelle STL) and S2 (blade STL surface option); STL is the
  OpenFOAM-native surface format and the snappyHexMesh geometry format.
- **C — Time-derived idempotent kinematics + `positions()`/`forces()` contract.**
  Replace the `angleDeg_ +=` accumulator with an integral of the omega law
  (`omega*t` for constant TSR; closed-form for the `tsrAmplitude` oscillation),
  add an optional omega override (Function1 or registry
  `uniformDimensionedScalarField`, mirroring `fsiOmega/preciceOmega`), register
  `angleDeg_` for restart/rollback idempotency, and expose `angleDeg()`. The
  surface-sampling object exposes `positions()`/`forces()` (+ `normals()`,
  `areas()`), SI, body frame, stable ordering, registry-exposed.
- **D — Paper-faithful periodic-nacelle benchmark, staged.** Coarse
  (153x80x80, ~1M cells) + medium (115x151x151, ~2.6M cells) grids, ~2652-triangle
  surface, metrics = time-averaged <u>(z)/k(z) at 1R/3R/5R/7R downstream + drag
  coefficient vs. the paper's digitized wall-resolved LES. Staged: prepare + dev
  partition mesh/stability now; production averaging on the long queue after
  authorization (nothing launched before).

### Decisions

1. **Validation turbulence closure — LES (WALE) headline.** The user's directive is
   to reproduce the article; the paper validates against wall-resolved LES. Standard
   OpenFOAM lacks the paper's dynamic SGS model, so the closest comparable is LES
   with WALE as the headline closure, with the adaptation documented. A URANS k-omega
   SST fallback is included as a cheaper, documented smoke path (weaker claim), not
   the headline. Rationale: paper-comparability is the point of the validation case;
   WALE is deterministic (no averaging of the model coefficient) and is the standard
   OpenFOAM choice for bluff-body wake LES.
2. **Blade STL production — defer to S2.** S1 produces the nacelle/hub STL and the
   pipeline machinery; blade STL *generation* is deferred to S2 because the MEXICO
   geometry tables are un-sourced (a research/data-sourcing step must precede
   generation) and the periodic-nacelle bench only needs the paper's parametric
   hemisphere + cylinder. The pipeline's directory layout, generator structure, and
   metadata schema are designed to accept blades with no rework.
3. **`angleDeg_`/omega registry fields — include in S1.** Register `angleDeg_` (and
   the optional omega override when used) as `uniformDimensionedScalarField` now.
   Rationale: this closes a real, existing gap — `startFrom latestTime` restarts
   currently reset the azimuth and re-integrate TSR oscillation incorrectly — and it
   is exactly the field shape the adapter's `globalData` ReadWrite can already
   exchange (S3) and where `Adapter.C:935` will add checkpoint coverage. Deferring
   the field to S3 would leave a known correctness bug in S1 and make the FSI seam
   a promise rather than a tested behavior.
4. **`cf` — Schultz-Grunow default + optional constant override.** Keep the paper's
   Schultz-Grunow relation (Eq. 22) as the default, with an optional
   user-overridable constant `cf` for calibration studies and the drag-coefficient
   comparison. Rationale: the constant override is cheap and directly serves the
   validation case's CD comparison; the paper's zero-pressure-gradient relation is
   documented as less valid in the hemisphere nose region.

**Delivery note (decision required before apply, NOT pre-decided here):** exploration
forecasts ~1500-2200 changed lines across W1 (core source) → W2 (geometry pipeline)
→ W3 (kinematics seam) → W4 (validation package), far over the 400-line `single-pr`
review policy. This proposal records the forecast; the delivery-shape resolution
(chained PR slices W1→W2→W3→W4 vs. an explicit `size:exception`) is handled
post-`sdd-tasks` by the orchestrator/user, not chosen here.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `turbinesFoam/src/fvOptions/nacelleSurface/...` | New | `nacelleSurfaceSource` + surface-sampling object (triSurface read, normals/areas, direct-forcing + friction forces, kernel spread, CSV, MPI) |
| `turbinesFoam/src/fvOptions/axialFlowTurbineALSource/axialFlowTurbineALSource.{H,C}` | Modified | Implement `createNacelle()` from `nacelleDict_`; fix null-deref additively (`:471-474`, `:780-789`, `:874-883`, `:944-948`); rotate/tilt/yaw remain blade+hub only |
| `turbinesFoam/src/fvOptions/turbineALSource/turbineALSource.{H,C}` | Modified | Time-derived idempotent kinematics (replace `angleDeg_ +=` at `:152-160`); optional omega override; registry field; `angleDeg()` accessor |
| `turbinesFoam/src/Make/files`, `turbinesFoam/src/Make/options` | Modified | Register new `.C`; add `-lsurfMesh` + `-I$(LIB_SRC)/surfMesh/lnInclude` for `triSurface` |
| `turbinesFoam/geometry/` | New | gmsh `.geo` + `makeGeometry.py` → per-component STL + metadata JSON + `PROVENANCE.md` |
| `turbinesFoam/validation/nacelle-asn/` | New | Periodic-nacelle case skeleton, config, digitized LES profiles + provenance, compare script, slurm stage0/production |
| `turbinesFoam/tests/test_nacelle.py`, `tests/test_nacelle_data.py` | New | Integration + pure-Python tests |
| `turbinesFoam/README.md`, root `README.md`, root `CHANGELOG.md` | Modified | Config keys, tutorial/validation reference, fork-divergence and closure-adaptation notes |
| Untouched | — | `actuatorLineElement`/`actuatorSurfaceElement`, `profileData`, dynamic stall, added mass, end effects, CFTAL, the adapter (`modules/*`), `fsiOmega` |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Review budget exceeded (W1-W4 ~1500-2200 lines vs. 400-line `single-pr` policy) | High | Record the forecast here; resolve delivery shape (chained PR slices or `size:exception`) before apply — not chosen in this phase |
| Shared-path regression in AFTAL `addSup` (null-deref fix touches all three overloads) | Medium | Additive only (`hasNacelle_ == false` skips the block); gate = existing pytest suite + `test_libs.py`; default path byte-identical |
| Kinematics refactor changes `angleDeg_`/TSR-oscillation behavior | Medium | Time-derived law must be CSV-identical to the accumulator for existing cases (integration tests only, no C++ unit tests); acceptance is idempotency, not a behavior change |
| No C++ unit tests — nacelle force math (direct-forcing, `cf`, kernel) unverifiable in isolation | Medium | Integration CSVs + the ALM-free validation case; Python expected-value check in `test_nacelle.py` (known velocity field → expected force) |
| Data digitization (only the paper's figures as reference, no tables) | Medium | Digitize with `PROVENANCE.md` + two-source cross-check; document validity limits of Schultz-Grunow in the nose region |
| LES adaptation (paper's dynamic SGS not in OpenFOAM) | Medium | WALE headline with documented adaptation; per-station acceptance (coarse != medium in the paper — do not over-promise coarse agreement) |
| `-lsurfMesh` link change affects every turbinesFoam build | Medium | Verify no symbol conflicts with the already-linked `-lmeshTools`; full `./Allwmake` + `ldd -r` check |
| MPI: nacelle surface points land on other processors than their cells | Low | Reuse `reduce(minOp)` sentinel + bounding-box `findCell` from `actuatorSurfaceElement.C:73-92`; fatal on unreachable samples |
| Fork divergence from upstream turbinesFoam grows | Low | New source class + geometry tree documented in README fork notes; acceptable for a vendored fork |

## Rollback Plan

The change is additive and opt-in: with no `nacelle {}`/geometry configured, the
default ALM path is byte-identical. To revert:
1. Remove the `nacelle {}` subdict (or the standalone `nacelleSurfaceSource`
   `fvOptions` entry) from any case that adopted it — behavior returns to baseline
   without recompiling.
2. To roll back the code itself, `git revert` the change work units; the ALM
   classes, `createNacelle`, `Make/files`, and `Make/options` return to their prior
   state with no data or case migration required (no schema changes, no generated
   artifacts outside the new `geometry/`/`validation/`/`tests/` trees, which are
   reverted with the change).
3. The kinematics refactor is separately revertible: `git revert` the W3 unit
   restores the `angleDeg_ +=` accumulator and the prior CSV output. Registering
   `angleDeg_` as a `uniformDimensionedScalarField` adds a new field directory under
   time steps; a revert leaves harmless extra field files that OpenFOAM ignores (no
   schema migration).
4. Verify with `cd turbinesFoam && ./Allwmake` and `pytest` (the existing suite must
   pass unchanged; `test_libs.py` gates the `-lsurfMesh` link change).

## Dependencies

- Loaded OpenFOAM v2506 module environment (SDumont recipe in AGENTS.md).
- `-lsurfMesh` (+ `-I$(LIB_SRC)/surfMesh/lnInclude`) added to `turbinesFoam`
  `Make/options` — `triSurface::New` lives in `libsurfMesh`; verify no symbol
  conflict with the already-linked `-lmeshTools`.
- gmsh (`~/venv/bin/gmsh`, verified on this host) for geometry generation.
- No new external CFD/FSI libraries; preCICE is NOT a dependency for S1.
- Validation reference data: digitized wall-resolved-LES profiles from the paper
  (arXiv:1702.02108v4, Sec. 4.1), with provenance — no published tables.

## Success Criteria

- [ ] `cd turbinesFoam && ./Allwmake` exits 0 with no new warnings/errors and
      produces `libturbinesFoam.so` (with `-lsurfMesh` linked, `ldd -r` clean).
- [ ] Full existing pytest suite passes unchanged: `test_libs`, `test_al`,
      `test_aftal`, `test_aftal_asm`, `test_cftal` (ALM default path byte-identical —
      regression gate for the null-deref fix and the kinematics refactor).
- [ ] A standalone `nacelleSurfaceSource` `fvOptions` case runs rotor-less and
      produces a force CSV; `tests/test_nacelle.py` passes, including a Python
      expected-value check (known velocity field → expected force).
- [ ] `axialFlowTurbineALSource` with a `nacelle {}` subdict composes the source via
      `createNacelle()` (no null-deref) and reports nacelle force; a missing/invalid
      STL raises `FatalError`.
- [ ] `tests/test_nacelle_data.py` passes: `makeGeometry.py --check` regenerates the
      committed nacelle STL deterministically (sha256 match) and PROVENANCE is present.
- [ ] Kinematics CSV output is byte-identical for existing cases; `angleDeg_` is
      registered as a `uniformDimensionedScalarField` and a restart resumes the same
      azimuth (idempotency check).
- [ ] `validation/nacelle-asn/` prepares (mesh + stability on the dev partition) and
      documents the staged coarse/medium LES plan; nothing is launched on the long
      queue before authorization.
- [ ] Docs updated: config keys, geometry pipeline, closure adaptation (WALE vs the
      paper's dynamic SGS), fork-divergence note, attribution.
