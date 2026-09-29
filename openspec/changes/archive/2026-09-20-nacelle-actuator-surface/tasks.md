# Tasks: Nacelle/hub actuator surface model (ASM) + geometry pipeline + FSI seams

Change: `nacelle-actuator-surface` — slice **S1** (S2 = blade STL surface option,
S3 = preCICE FSI wiring; both deferred).

Mode: **Standard** (`strict_tdd: false` → tests required, no strict RED-GREEN ritual).
Tasks are grouped by **work unit** (the delivery slices W1→W2→W3→W4) with
hierarchical numbering, each task completable in one session. Each work unit ends
with its own tests and docs so every slice is independently reviewable and
revertable (proposal rollback plan, §Rollback).

Threat matrix: **N/A** (design §15) — no routing/shell/VCS boundaries; `gmsh` is
invoked on fixed inputs with sha256-verified output and `production.slurm` is
prepared-only. No threat-matrix RED-test tasks apply.

---

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | W1 ~600–800 · W2 ~400–600 · W3 ~100–200 · W4 ~400–600 — **total ~1500–2200** |
| 400-line budget risk | **High** |
| Chained PRs recommended | **Yes** |
| Suggested split | W1 → W2 → W3 → W4 |
| Delivery strategy | `single-pr` (session strategy — recorded, NOT decided here) |
| Chain strategy | `pending` (chained delivery possible if requested later) |

```
Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High
```

The forecast exceeds the 400-line `single-pr` review policy. Natural slice
boundaries (each a self-contained, individually-tested, independently-revertable
unit) are **W1 (core source) → W2 (geometry pipeline) → W3 (kinematics seam) →
W4 (validation + docs)**. This records the delivery shape as `single-pr` per the
session strategy without choosing it: the orchestrator/user resolves chained PR
slices (W1→W2→W3→W4) vs an explicit `size:exception` after this phase. Under
`single-pr`, apply is gated on an explicit `size:exception` (see §E of the shared
phase protocol).

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| W1 | Core `nacelleSurfaceSource` + `nacelleSurfaceSampler` + `createNacelle()` + null-deref fix + `-lsurfMesh` | PR 1 | `cd turbinesFoam && pytest -q tests/test_nacelle.py tests/test_libs.py tests/test_aftal.py tests/test_aftal_asm.py tests/test_al.py tests/test_cftal.py` | `cd turbinesFoam && ./Allwmake` (exit 0) + `ldd -r $FOAM_USER_LIBBIN/libturbinesFoam.so` clean; standalone rotor-less fvOptions case + `mpirun -np 2` parallel case | `git revert` W1 → removes `nacelleSurface/`, `Make/*` additions, `createNacelle()` impl; ALM default path byte-identical (no `nacelle {}`) |
| W2 | Deterministic geometry pipeline (`geometry/`) + `test_nacelle_data.py` | PR 2 | `cd turbinesFoam && pytest -q tests/test_nacelle_data.py` | `python3 geometry/src/makeGeometry.py --check --gmsh ~/venv/bin/gmsh` (sha256 deterministic, non-destructive) | `git revert` W2 → removes `turbinesFoam/geometry/` tree |
| W3 | Time-derived idempotent kinematics + omega override + registry field | PR 3 | `cd turbinesFoam && pytest -q tests/test_aftal.py tests/test_aftal_asm.py` | `./Allwmake`; `startFrom latestTime` restart idempotency check; `angle_deg` CSV column matches baseline to floating point | `git revert` W3 → restores `angleDeg_ +=` accumulator; leftover `angleDeg.*`/`omega.*` field dirs are harmless (OpenFOAM ignores) |
| W4 | Validation package (`validation/nacelle-asn/`) + docs | PR 4 | `cd turbinesFoam && pytest -q tests/test_nacelle_case.py tests/test_nacelle_compare.py` + full suite | `python3 tools/generate_case.py --check`; `stage0.slurm` on dev partition only (mesh + stability); `production.slurm` prepared-only | `git revert` W4 → removes `validation/nacelle-asn/` + doc edits |

---

## W1 — Core nacelle source

Reference: design §4 (`nacelleSurfaceSource` + `nacelleSurfaceSampler`), §6 (AFTAL
wiring), §10 (MPI), §9 (test design). Equations: paper Sec. 2.2 (Eqs. 7, 8, 18–23).

### W1.1 — `nacelleSurfaceSampler` (reusable surface-sampling object)

- [x] Completed (W1 close-out batch) — evidence in `apply-progress.md`
- **Files (create):** `turbinesFoam/src/fvOptions/nacelleSurface/nacelleSurfaceSampler.H`, `turbinesFoam/src/fvOptions/nacelleSurface/nacelleSurfaceSampler.C`
- **Work:**
  - Owned geometry: `triSurface surface_` via `triSurface::New(geometryPath)` (auto-detect ASCII/binary); `List<point> positions_` = `surface_.faceCentres()`; `List<vector> normals_` = `surface_.faceNormals()`; `List<scalar> areas_` = `surface_.magFaceAreas()` (deterministic face order, design §Decision 2).
  - **Validator note (explicit member):** declare a **per-unit-density node-force storage list** used by the distribution step — `List<vector> nodeForces_` (m⁴/s², `(f_n + f_τ)_i · A_i`) — distinct from the SI contract list `forces_` (N) = `rhoRef_ · nodeForces_`. This closes the gap between design §4.1 (class layout lists only `forces_`) and §4.2 step 4 (`distributeForce` consumes the per-unit-density `F_i`). Both lists share the same node ordering.
  - Force model (per-node, per unit density): `normalForce(i, ũ, h, dt)` (Eq. 19, `u^d = 0`), `tangentialForce(i, cf, e_tau)` (Eq. 21), `frictionCoefficient(i)` (Eq. 22 Schultz–Grunow `0.37·(log Rex)^(−2.584)` + constant `cf` override), `tangentialDirection(i, U)` (Eq. 23, `e_τ = 0` when `|u(probe)| < SMALL`).
  - Kernel + interpolation: `static scalar kernel(r)` (Eq. 8, support `[−2.5, 2.5]`), `interpolateVelocity(X, U)` (Eq. 7 kernel sum over the 5³-cell stencil, `returnReduce(sumOp)`).
  - Contract accessors: `positions()`, `forces()` (SI N, body frame, force-on-body), `normals()`, `areas()`.
  - Body-frame transform: `bodyOrigin_` (default `(0 0 0)`), `bodyToGlobal_` (default identity), optional `bodyOrigin`/`bodyAxis` keys.
  - `FatalError` on missing/empty/unparseable STL (spec requirement).
- **Acceptance:** compiles; ASCII + binary STL read produce identical node geometry; deterministic face order; sign convention per design §2.2.
- **Verification:** `cd turbinesFoam && ./Allwmake` (after W1.3 registers the files).

### W1.2 — `nacelleSurfaceSource` (the `fv::option`)

- [x] Completed (W1 close-out batch) — evidence in `apply-progress.md`
- **Files (create):** `turbinesFoam/src/fvOptions/nacelleSurface/nacelleSurfaceSource.H`, `turbinesFoam/src/fvOptions/nacelleSurface/nacelleSurfaceSource.C`
- **Work:**
  - Derive `cellSetOption`; RTS registration `defineTypeNameAndDebug(nacelleSurfaceSource, 0); addToRunTimeSelectionTable(option, nacelleSurfaceSource, dictionary);` inside `namespace Foam { namespace fv {`.
  - Members: `nacelleSurfaceSampler sampler_`; `volVectorField forceField_` (`"force." + name_`, `dimForce/dimVolume/dimDensity`, `AUTO_WRITE`); `vector force_` (total, per-unit-density); `writePerf_`/`outputFile_`, `writeNodePerf_`/`nodeFile_`.
  - `addSup` (incompressible momentum) sequence per design §4.2: `U = eqn.psi()` → zero fields → per node `ũ = interpolateVelocity`, `h = cbrt(V[cell])`, `f_n`, `cf`, `e_τ`, `f_τ`, `nodeForces_[i] = (f_n + f_τ)·A_i`, `forces_[i] = rhoRef_·nodeForces_[i]` → `distributeForce()` → `force_ = Σ_i nodeForces_[i]` (`returnReduce(sumOp)`) → reset `forceField_` dims → `eqn += forceField_` → `writePerf()` on master.
  - `distributeForce()` (Eq. 18): `forceField_[c] += −nodeForces_[i]·(1/V_c)·φφφ` over each node's 5×5×5 stencil, `boundBox` prefilter inflated by `2.5·h` (mirror `actuatorSurfaceElement.C` chordBox).
  - Compressible `addSup(rho, …)`: multiply `forceField_`/`force_` by local `rho`. Scalar-turbulence `addSup(fvMatrix<scalar>&, …)`: **no-op** (documented deviation, design §4.2).
  - `writePerf()` CSV `postProcessing/nacelle/<name>.csv` (`time,fx,fy,fz,f_n_mag,f_tau_mag,cd`); per-node CSV `postProcessing/nacelle/<name>_nodes.csv` when `writeNodePerf true`.
  - MPI (design §10): replicated-node/local-cell; `returnReduce(partial, sumOp<vector>())` for interpolation and total force; `findCell` + `reduce(minOp)` sentinel; `FatalErrorInFunction` on unreachable sample.
  - Config keys per design §4.3 (`geometry`, `referenceVelocity`, `rho`, `nu`, `cfModel`, `cf`, `bodyOrigin`, `bodyAxis`, `writeForceField`, `writePerf`, `writeNodePerf`); read via `get<word>` (no `dictionary::lookup`, AGENTS.md v2506 gotcha); no `List<T>` from STL iterators.
- **Acceptance:** standalone `fvOptions` entry runs rotor-less and writes the CSV; total force preserved by partition of unity.
- **Verification:** `cd turbinesFoam && ./Allwmake` (after W1.3).

### W1.3 — `Make/files` + `Make/options` (`-lsurfMesh`)

- [x] Completed (W1 close-out batch) — evidence in `apply-progress.md`
- **Files (modify):** `turbinesFoam/src/Make/files`, `turbinesFoam/src/Make/options`
- **Work:**
  - `Make/files`: add `fvOptions/nacelleSurface/nacelleSurfaceSampler.C` and `fvOptions/nacelleSurface/nacelleSurfaceSource.C` (after the actuator lines).
  - `Make/options`: add `-I$(LIB_SRC)/surfMesh/lnInclude` to `EXE_INC` and `-lsurfMesh` to `LIB_LIBS` (design §4.5). Keep the existing `-lfiniteVolume -lsampling -lmeshTools -lfvOptions` untouched.
- **Acceptance:** new files compile into `libturbinesFoam.so`; no symbol conflict with `-lmeshTools`.
- **Verification:** `cd turbinesFoam && ./Allwmake` (exit 0); `ldd -r $FOAM_USER_LIBBIN/libturbinesFoam.so` reports no undefined symbols and no duplicate-symbol link error.

### W1.4 — `createNacelle()` wiring + null-deref fix

- [x] Completed (W1 close-out batch) — evidence in `apply-progress.md`
- **Files (modify):** `turbinesFoam/src/fvOptions/axialFlowTurbineALSource/axialFlowTurbineALSource.H`, `turbinesFoam/src/fvOptions/axialFlowTurbineALSource/axialFlowTurbineALSource.C`
- **Work:**
  - Change `nacelle_` from `autoPtr<actuatorLineSource>` to `autoPtr<nacelleSurfaceSource>` (`.H:76`); `#include "nacelleSurfaceSource.H"`.
  - Implement `createNacelle()` (`.C:471-474`) mirroring `createHub()`/`createTower()` (design §6): build `nacelleSurfaceSourceCoeffs` from `nacelleDict_`, inherit `fieldNames`/`selectionMode`/`cellSet` from `coeffs_`, add `referenceVelocity = mag(freeStreamVelocity_)`, `lookupOrAddDefault("writeForceField", false)`, `nacelle_.reset(new nacelleSurfaceSource(...))`.
  - Null-deref closed additively: the three `addSup` blocks (`.C:780-789`, `:874-883`, `:944-948`) now call a valid `nacelle_`; they still skip when `hasNacelle_ == false`.
  - Preserve `includeNacelleDrag_`/`includeInTotalDrag` semantics (`.C:989-993`): `nacelle_->forceField()` always added to `forceField_`; total `force_`/`dragCoefficient_` includes nacelle only when `includeNacelleDrag_` true.
  - Nacelle stays static: `rotate(scalar)` (`.C:643-662`), `rotateBladesAndHub` (`.C:664-696`), `tilt`, `yaw` remain blade+hub only.
- **Acceptance:** a case with a `nacelle {}` subdict composes the source with no null-deref; a missing/invalid STL raises `FatalError`.
- **Verification:** `cd turbinesFoam && ./Allwmake`; `cd turbinesFoam && pytest -q tests/test_aftal.py tests/test_aftal_asm.py`.

### W1.5 — W1 build gate + symbol check

- [x] Completed (W1 close-out batch) — evidence in `apply-progress.md`
- **Files:** none (gate task)
- **Work:** full build and link verification.
- **Acceptance:** `./Allwmake` exits 0 with no new warnings/errors; `libturbinesFoam.so` produced with `-lsurfMesh` linked.
- **Verification:**
  - `cd turbinesFoam && ./Allwmake`
  - `ldd -r $FOAM_USER_LIBBIN/libturbinesFoam.so 2>&1 | grep -i undefined` (empty) and confirm no `-lsurfMesh`/`-lmeshTools` duplicate-symbol error.

### W1.6 — `tests/test_nacelle.py` (integration + parallel)

- [x] Completed (W1 close-out batch) — evidence in `apply-progress.md`
- **Files (create):** `turbinesFoam/tests/test_nacelle.py` (plus a solver-driven case under `turbinesFoam/tests/nacelleSurface/` if needed; mark `collect_ignore` via `conftest.py`'s `SOLVER_DRIVEN` tuple — add `"test_nacelle.py"` so it skips without OpenFOAM)
- **Files (modify):** `turbinesFoam/tests/conftest.py` (add `test_nacelle.py` to `SOLVER_DRIVEN`)
- **Work (design §9):**
  - Standalone `nacelleSurfaceSource` rotor-less case runs and writes `postProcessing/nacelle/<name>.csv`; test parses it as numbers.
  - **Python expected-value check:** feed a known (uniform) velocity field to a simple surface; assert the normal force equals `Σ h·U/Δt·A_i` within tolerance (Eq. 19); asserts **total-force preservation** `Σ_c forceField[c]·V_c == Σ_i nodeForces[i]`.
  - **`FatalError` case:** missing and invalid/empty STL abort the run (spec scenario).
  - **Parallel case:** `mpirun -np 2` (and/or `-np 4`) exercises node→cell MPI resolution; assert `Σ distributed force == Σ node forces` on every rank count and N-rank total == serial total within tolerance; include a **partition-boundary case** (nodes whose 5³ stencils straddle a processor boundary — no missed/double-counted cell).
- **Acceptance:** all tests pass with OpenFOAM loaded.
- **Verification:** `cd turbinesFoam && pytest -q tests/test_nacelle.py`.

### W1.7 — W1 regression gate + W1 docs

- [x] Completed (W1 close-out batch) — evidence in `apply-progress.md`
- **Files (modify):** `turbinesFoam/README.md`
- **Work:**
  - Regression gate: full existing suite passes unchanged — `test_libs` (gates the `-lsurfMesh` link change), `test_al`, `test_aftal`, `test_aftal_asm`, `test_cftal`; ALM default path byte-identical.
  - Docs: add a "Nacelle surface model" section to `turbinesFoam/README.md` documenting the `nacelleSurfaceSource` config keys (§4.3), the `nacelle {}` subdict wiring, and a fork-divergence note (new source class not in upstream).
- **Acceptance:** `pytest` green; README documents the new source.
- **Verification:** `cd turbinesFoam && pytest -q` (full suite); visual README check.

---

## W2 — Geometry pipeline (`turbinesFoam/geometry/`)

Reference: design §7. Deterministic gmsh + `makeGeometry.py` → per-component STL +
metadata JSON + PROVENANCE; S1 produces the nacelle STL only (blade STLs deferred
to S2, layout reserves them).

### W2.1 — `geometry/src/nacelle.geo` (gmsh source)

- [x] Completed (W2 batch) — `L = 6R` resolved from Fig. 3 (dimension labels, pixel cross-check 6.03); evidence in `apply-progress.md`
- **Files (create):** `turbinesFoam/geometry/src/nacelle.geo`
- **Work:** hemisphere (upstream) + cylinder of radius `R`, parameterised by `R`, `L` (cylinder length), and a mesh-resolution seed chosen to hit the paper's **~2652 triangles**. Resolve the cylinder length `L` from the paper's Fig. 3 (design §12 open Q1); if Fig. 3 is ambiguous, adopt a documented aspect ratio and record it in `PROVENANCE.md`.
- **Acceptance:** regenerates a committed STL targeting ~2652 triangles.
- **Verification:** `~/venv/bin/gmsh geometry/src/nacelle.geo` produces the surface mesh (manual/visual + triangle count).

### W2.2 — `geometry/src/makeGeometry.py` (generator CLI)

- [x] Completed (W2 batch) — evidence in `apply-progress.md`
- **Files (create):** `turbinesFoam/geometry/src/makeGeometry.py`
- **Work:** CLI `generate` (default) | `--check` | `--component nacelle` | `--gmsh PATH`; deterministic (pinned gmsh version, fixed options); `--check` regenerates to temp, sha256-compares, exits non-zero on mismatch, and never modifies committed artifacts (mirror `makeElementData.py --check`, `validation/phaseVI/scripts/makeElementData.py` (read-only)).
- **Acceptance:** byte-identical regeneration from committed inputs; non-destructive `--check`.
- **Verification:** `python3 geometry/src/makeGeometry.py --check --gmsh ~/venv/bin/gmsh` (exit 0 on clean tree).

### W2.3 — Commit `stl/nacelle.stl` + `metadata/nacelle.json`

- [x] Completed (W2 batch) — 2616 triangles (−1.4 % vs ~2652); evidence in `apply-progress.md`
- **Files (create):** `turbinesFoam/geometry/stl/nacelle.stl`, `turbinesFoam/geometry/metadata/nacelle.json`
- **Work:** generate and commit the binary STL (~2652 triangles); emit metadata JSON per design §7 schema (per-node `normal`/`area`, `n_triangles`, `units`, `generator`, `input_sha256`, and `_reserved.blade` with `radial_station`/`chord_fraction` null).
- **Acceptance:** committed STL sha256 matches regeneration; metadata schema present.
- **Verification:** `makeGeometry.py --check` clean; `sha256sum` stable.

### W2.4 — `geometry/PROVENANCE.md` + `geometry/README.md`

- [x] Completed (W2 batch) — evidence in `apply-progress.md`
- **Files (create):** `turbinesFoam/geometry/PROVENANCE.md`, `turbinesFoam/geometry/README.md`
- **Work:** PROVENANCE records the paper's Sec. 4.1/Fig. 3 source for the nacelle, the (deferred) MEXICO rotor tables as the blade source, the generator/gmsh version, and the sha256 of the `.geo` inputs. README documents usage, the component list, and the S2 deferral note.
- **Acceptance:** provenance + usage present (spec requirement).
- **Verification:** content review.

### W2.5 — `tests/test_nacelle_data.py` (pure-Python, CI-safe)

- [x] Completed (W2 batch) — 14 tests, 3 gmsh-gated; evidence in `apply-progress.md`
- **Files (create):** `turbinesFoam/tests/test_nacelle_data.py`
- **Work (design §9):** no OpenFOAM. Assert `makeGeometry.py --check` regenerates the committed `stl/nacelle.stl` with a sha256 match (mirror `GEOMETRY_SHA256` in `test_phasevi_data.py` (read-only)); assert `metadata/nacelle.json` schema present (per-node normals/areas, `_reserved.blade`); assert `PROVENANCE.md` present with source refs + input sha256. Add to `SOLVER_DRIVEN`? **No** — keep it pure-Python (always collected, like the phaseVI data tests).
- **Acceptance:** passes without OpenFOAM (CI-safe).
- **Verification:** `cd turbinesFoam && pytest -q tests/test_nacelle_data.py` (in an env with gmsh on PATH or `--gmsh` fallback; skip cleanly if gmsh absent and document).

---

## W3 — Kinematics seam (time-derived `angleDeg_`)

Reference: design §5. Replace the `angleDeg_ += omega*dt` accumulator with an
integral of the omega law; optional omega override; registry persistence.

### W3.1 — Time-derived `angleDeg_` (accumulator → integral)

- [x] Completed (W3 batch) — closed form vs RK4 max **4.1e-11 deg** over 6 periods, monotone over 12; AFTAL `angle_deg` CSV **byte-identical** to the accumulator; evidence in `apply-progress.md`
- **Files (modify):** `turbinesFoam/src/fvOptions/turbineALSource/turbineALSource.H`, `turbinesFoam/src/fvOptions/turbineALSource/turbineALSource.C`
- **Work (design §5.1):**
  - Add state: `scalar t0_`, `scalar angle0_`, `bool hasOmegaOverride_`, `word omegaOverrideField_`, `autoPtr<uniformDimensionedScalarField> angleDegField_`.
  - Replace the accumulator at `.C:152-160` (`rotate()`): `angleDeg_ = azimuth(t)` (degrees, pure function of `(t0, angle0, t)`), compute `deltaRad = degToRad(angleDeg_ - anglePrev)` **before** overwriting, `rotate(deltaRad)`, `lastRotationTime_ = t`, `updateTSROmega()`, write `angleDegField_` if valid.
  - `azimuth(t)`: constant TSR → `ω0·(t − t0)`; `tsrAmplitude` oscillation → closed-form separable integral (design §5.1), with `atan` branch unwrapping, `C` fixed by `θ(t0) = degToRad(angle0_)`, reduced mod 360.
  - `updateTSROmega()` (`.C:143-149`): read `omega_` from the registry field when `hasOmegaOverride_`, else existing TSR law unchanged. `read()` (`.C:302-340`): read `omegaOverrideField` (+ existing `tsrAmplitude`/`tsrPhase`).
  - `angleDeg()` accessor (degrees). Keep `azimuthalOffset` a separate geometric rotation (`.C:616-617` untouched).
- **Acceptance:** `angleDeg_` is a pure function of time + initial state (no `+=` accumulator).
- **Verification:** `cd turbinesFoam && ./Allwmake`; `cd turbinesFoam && pytest -q tests/test_aftal.py tests/test_aftal_asm.py`.

### W3.2 — Registry persistence + restart idempotency

- [x] Completed (W3 batch) — `startFrom latestTime` resumed **38.1971863421 deg at t = 0.005** and continued with byte-identical angle increments; read-back mode + registry host resolved (evidence in `apply-progress.md`)
- **Files (modify):** `turbinesFoam/src/fvOptions/turbineALSource/turbineALSource.C` (and `.H` if needed)
- **Work (design §5.2):** register `angleDegField_` (`uniformDimensionedScalarField` `angleDeg.<name>`, `dimless`, degrees, `AUTO_WRITE`); on construction seed `angle0_ = field.value()` / `t0_ = time_.value()` when the field exists (restart via `startFrom latestTime`), else create at `angle0_ = 0`, `t0_ = startTime`, `IOobject::NO_READ`.
  - **Task-level verification (design §12 open Q2):** confirm the exact read-back mode (`MUST_READ` vs explicit lookup) and the registry host (`mesh_` vs `Time`) so the adapter's `globalData` can find it — check against `precice-openfoam-adapter/modules/generic/Generic.C:29-66` (read-only) and `fsiOmega/preciceOmega.C` (read-only) conventions.
- **Acceptance:** a `startFrom latestTime` restart resumes the same azimuth (not zero); rollback idempotency (re-reading the field restores the azimuth at that time).
- **Verification:** `./Allwmake`; manual restart check on an existing AFTAL case (or a focused integration case).

### W3.3 — Omega override field

- [x] Completed (W3 batch) — zero-valued override forced `angle_deg`/`tsr` to 0 at every step (TSR law bypassed); default (unset) path byte-identical; evidence in `apply-progress.md`
- **Files (modify):** `turbinesFoam/src/fvOptions/turbineALSource/turbineALSource.{H,C}`
- **Work (design §Decision 4):** register the override as a `uniformDimensionedScalarField` `omega.<name>` (dimension `(0,0,-1,0,0,0,0)` rad/s, `AUTO_WRITE`), mirroring the `fsiOmega` "omega" field the adapter already exchanges. Default unset → existing TSR law runs byte-identical.
- **Acceptance:** override drives the azimuth integral; unset → byte-identical TSR law.
- **Verification:** `./Allwmake`; `pytest -q tests/test_aftal.py tests/test_aftal_asm.py`.

### W3.4 — W3 regression gate (CSV "to floating point" + tolerance)

- [x] Completed (W3 batch) — full suite **66 passed** unchanged; AFTAL (constant TSR) CSV byte-identical; CFTAL (`tsrAmplitude`) deviation quantified as explicit-Euler vs exact-integral truncation (evidence in `apply-progress.md`)
- **Files:** none (gate task)
- **Work:** confirm the time-derived law reproduces the accumulator's `angle_deg` CSV column **to floating point** (spec acceptance, not bit-for-bit — the accumulator sums `ω·dt` per step). Confirm the floating-point tolerance the existing `test_aftal` comparison will accept for the `tsrAmplitude` cases (design §12 open Q3).
- **Acceptance:** existing suite passes unchanged; CSV `angle_deg` column matches baseline within the accepted tolerance.
- **Verification:** `cd turbinesFoam && pytest -q` (full suite); diff `angle_deg` columns of a baseline vs new run for a `tsrAmplitude` case.

---

## W4 — Validation package + docs

Reference: design §8 (case), §9 (compare test). Mirrors the
`validation/phaseVI/` package pattern (single source of truth → renderer →
compare → slurm → skeleton → pytest).

### W4.1 — `config/case.yaml` (single source of truth)

- [x] Completed (W4a batch) — domain 30R×20R×20R with the nacelle downstream end at the origin, cyclic/symmetry boundaries, Re = 1000, WALE headline + URANS fallback, coarse/medium grids + declared-only reference, `geometry.stl` → `../../geometry/stl/nacelle.stl`, wash-out/averaging knobs; evidence in `apply-progress.md`
- **Files (create):** `turbinesFoam/validation/nacelle-asn/config/case.yaml`
- **Work:** domain `30R × 20R × 20R`, periodic streamwise (`cyclic`) + free-slip crosswise (`symmetry`); nacelle hemisphere + cylinder `R = 1`, Re = 1000 (`U∞ = 1`, `ν = 1e-3`); `pimpleFoam` + LES **WALE** headline + URANS k-ω SST fallback (weaker claim); coarse (153×80×80, Δx=R/2.5) + medium (115×151×151, Δx=R/3.75) grids (reference 502×348×348 declared only, never generated); `geometry` path → `../../geometry/stl/nacelle.stl`; run length (wash-out 2·T_ft, average 5·T_ft) + statistics knobs.
- **Acceptance:** YAML renders a paper-faithful case with WALE headline + URANS fallback.
- **Verification:** `python3 tools/generate_case.py --check` (after W4.2).

### W4.2 — `tools/generate_case.py` (renderer + `--check`)

- [x] Completed (W4a batch) — single-module renderer (YAML → committed `case/` skeleton) with non-destructive `--check`; standalone `nacelleSurfaceSource` entry (no turbine) whose `geometry` path resolves to the pipeline STL from the case root; evidence in `apply-progress.md`
- **Files (create):** `turbinesFoam/validation/nacelle-asn/tools/generate_case.py`
- **Work:** render `config/case.yaml` → committed `case/` skeleton (non-destructive `--check` mirroring `validation/phaseVI/tools/generate_case.py` (read-only)); geometry `fvOptions` entry points at the pipeline STL (`type nacelleSurfaceSource;`, standalone, no turbine).
- **Acceptance:** `--check` reports stale generated files and exits non-zero without modifying them.
- **Verification:** `python3 tools/generate_case.py --check` (clean tree passes).

### W4.3 — Digitized reference profiles + PROVENANCE

- [x] Completed (W4.3, commit `7cb1f3c`; registered in the W4b batch) — `data/reference/` holds `u_`/`k_` CSVs at the paper's **odd** stations (1R/3R/…/19R; the paper has **no 10R panel**, so the declared `10R` stretch is bracketed by 9R/11R and no 10R profile is invented), plus `PROVENANCE.md` + `digitization.json` (two-source cross-check); `tools/digitize_reference.py` is tooling only. Evidence in `apply-progress.md` (W4b batch).
- **Files (create):** `turbinesFoam/validation/nacelle-asn/data/reference/*.csv`, `turbinesFoam/validation/nacelle-asn/data/reference/PROVENANCE.md`
- **Work:** digitize Fig. 5 (`⟨u⟩`) and Fig. 6 (`k`) profiles at 1R/3R/5R/7R (+10R stretch) from the arXiv v4 images into per-station CSVs; `PROVENANCE.md` records the source figure, digitization method, and a two-source cross-check (two independent digitizations compared within a stated tolerance); document the reference as the paper's 502×348×348 wall-resolved LES whose dynamic SGS model is unavailable in standard OpenFOAM.
- **Acceptance:** profiles + provenance present (spec requirement).
- **Verification:** content review; `pytest` data/compare test loads them (after W4.7).

### W4.4 — Compare script + run script

- [x] Completed (W4b batch; commits `951525a`/`e70f8ec`, repairs `1b6636a`/`9dad3ab`) — `compareNacelle.py` (time-averaged `⟨u⟩`/resolved `k`/`CD`, per-station/per-grid acceptance, 10R bracket, `CD = 0.48` datum, `--allow-short-window`) and `runNacelle.sh` (env/render/library/queue gates, stale-log removal, POSIX `sh`); plain env **28 passed**; end-to-end compare on the real stage0 run (job 11597925). Evidence in `apply-progress.md` (W4b batch).
- **Files (create):** `turbinesFoam/validation/nacelle-asn/scripts/compareNacelle.py`, `turbinesFoam/validation/nacelle-asn/scripts/runNacelle.sh`
- **Work:** `compareNacelle.py` loads digitized reference profiles, computes time-averaged `⟨u⟩(z)`/`k(z)` at 1R/3R/5R/7R (+10R) and `CD = F_drag/(0.5·ρ·U∞²·πR²)`, enforces per-station/per-grid acceptance (medium agrees all stations; coarse only 1R + far wake), treats `CD = 0.48` as datum not target. `runNacelle.sh` mirrors `runPhaseVI.sh` (read-only) gates (env check, `generate_case.py --check`, queue gates).
- **Acceptance:** compare script computes the defined metrics against the digitized reference.
- **Verification:** `pytest -q tests/test_nacelle_compare.py` (after W4.7).

### W4.5 — Slurm staging (dev now, long queue prepared-only)

- [x] Completed (W4b batch; commit `e70f8ec`) — `stage0.slurm` submitted and **COMPLETED** on `sequana_cpu_dev` (job **11597925**, ExitCode `0:0`, 1m39s, 48 ranks); `production.slurm` (`--test-only` OK on `sequana_cpu_long`, confirmed up by `sinfo`) was **never submitted** and keeps its `NACELLE_LONG_QUEUE_AUTHORIZED` gate. Evidence in `apply-progress.md` (W4b batch).
- **Files (create):** `turbinesFoam/validation/nacelle-asn/scripts/slurm/stage0.slurm`, `turbinesFoam/validation/nacelle-asn/scripts/slurm/production.slurm`
- **Work:** `stage0.slurm` (dev partition) runs `blockMesh` + `checkMesh` + a short stability run — mesh generation and sanity **now**. `production.slurm` (long queue) runs full averaging — **prepared only, never submitted before explicit authorization** (spec requirement; no long-queue launch in S1).
- **Acceptance:** stage0 dev job prepares mesh/stability; production job is present but not submitted.
- **Verification:** submit `stage0.slurm` to the dev partition only; confirm `production.slurm` is not submitted.

### W4.6 — Case skeleton + case README + gitignore

- [x] Completed (W4a batch, README compact) — committed 14-file `case/` skeleton (renders clean, `--check` exit 0), package `.gitignore` + root `runs/`/`results/` entries, README covers setup, staged run plan, metrics, closure adaptation, limitations and attribution; evidence in `apply-progress.md`
- **Files (create):** `turbinesFoam/validation/nacelle-asn/case/` (skeleton), `turbinesFoam/validation/nacelle-asn/README.md`; **Files (modify):** `.gitignore` (add `runs/`/`results/` under `validation/nacelle-asn/`)
- **Work:** committed `case/` skeleton; gitignored `runs/`/`results/`; case `README.md` documents setup, staged run plan, metric definitions, closure adaptation (WALE vs the paper's dynamic SGS), modelling limitations, and attribution (arXiv:1702.02108v4).
- **Acceptance:** skeleton renders via `generate_case.py --check`; README documents setup + limitations.
- **Verification:** `python3 tools/generate_case.py --check`.

### W4.7 — `tests/test_nacelle_case.py` + `tests/test_nacelle_compare.py` (pure-Python)

- [x] Completed (W4b batch) — both files exist and pass in the plain env: `tests/test_nacelle_case.py` (15 tests) + `tests/test_nacelle_compare.py` (13 tests) = **28 passed**; neither is in `conftest.SOLVER_DRIVEN`. Evidence in `apply-progress.md` (W4b batch).
- **Files (create):** `turbinesFoam/tests/test_nacelle_case.py`, `turbinesFoam/tests/test_nacelle_compare.py`
- **Work (design §9):** `test_nacelle_case.py` mirrors `test_phasevi_case.py` (read-only) — `generate_case.py --check` clean-tree pass + stale-file detection (non-destructive). `test_nacelle_compare.py` mirrors `test_phasevi_compare.py` (read-only) — loads digitized reference profiles and computes `⟨u⟩`/`k`/`CD` metrics without a solver.
- **Acceptance:** both pass without OpenFOAM (CI-safe, pure-Python).
- **Verification:** `cd turbinesFoam && pytest -q tests/test_nacelle_case.py tests/test_nacelle_compare.py`.

### W4.8 — Docs consolidation + final regression gate

- [x] Completed (W4b batch; docs commit `002106a`) — root `README.md` (nacelle ASM extension, `geometry/` pipeline, validation package, WALE adaptation, fork divergence), root `CHANGELOG.md` entry under `## [Unreleased]` in the `Files:`/`Problem:`/`Fix:` format with attribution to arXiv:1702.02108v4, `turbinesFoam/README.md` validation section. Final gate: `./Allwmake` exit 0 (0 errors/warnings), `ldd -r` clean, full suite **95 passed, 1 warning** (only the pre-existing `timeout` mark warning). Evidence in `apply-progress.md` (W4b batch).
- **Files (modify):** root `README.md`, root `CHANGELOG.md`, `turbinesFoam/README.md`
- **Work:**
  - Root `README.md`: reference the nacelle validation package and the `turbinesFoam/geometry/` pipeline; note the closure adaptation (WALE vs the paper's dynamic SGS) and the fork-divergence (new source class + geometry tree).
  - Root `CHANGELOG.md`: add a `Files:`/`Problem:`/`Fix:` entry (repo format) under `## [Unreleased]` documenting the nacelle ASM, geometry pipeline, and kinematics seam, with attribution to the paper.
  - `turbinesFoam/README.md`: add the `validation/nacelle-asn/` reference (setup, staged plan, metrics, limitations).
  - Final regression gate: full build + full suite.
- **Acceptance:** docs reference the package and attribute the paper; full suite + build green.
- **Verification:** `cd turbinesFoam && ./Allwmake` (exit 0); `cd turbinesFoam && pytest -q` (full suite unchanged); review README/CHANGELOG diff.

---

## Cross-cutting verification gates (recap)

| Gate | Command | Guarded by |
|------|---------|-----------|
| Build exit 0 + `-lsurfMesh` link | `cd turbinesFoam && ./Allwmake` + `ldd -r $FOAM_USER_LIBBIN/libturbinesFoam.so` | W1.3, W1.5 |
| Existing suite byte-identical (ALM default, `angle_deg` CSV) | `cd turbinesFoam && pytest -q` | W1.7, W3.4, W4.8 |
| Standalone nacelle CSV + expected-value + total-force preservation + MPI (incl. partition boundary) | `pytest -q tests/test_nacelle.py` | W1.6 |
| `FatalError` on missing/invalid STL | `pytest -q tests/test_nacelle.py` | W1.6 |
| Geometry deterministic regeneration + metadata schema + provenance | `pytest -q tests/test_nacelle_data.py` | W2.5 |
| Validation case render + compare (pure-Python) | `pytest -q tests/test_nacelle_case.py tests/test_nacelle_compare.py` | W4.7 |
| No long-queue launch before authorization | `production.slurm` prepared-only | W4.5 |

Rollback (proposal §Rollback): remove the `nacelle {}` subdict / standalone
`fvOptions` entry to restore baseline without recompiling; `git revert` the W1–W4
units (each independently revertable) restores prior code, `Make/*`, and the
`createNacelle` stub; the W3 revert restores the `angleDeg_ +=` accumulator with
only harmless leftover field directories.
