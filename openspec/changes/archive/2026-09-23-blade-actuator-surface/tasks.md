# Tasks: Blade actuator surface model over an imported blade mesh (S2)

Change: `blade-actuator-surface` — slice **S2** of the staged program
(S1 = `nacelle-actuator-surface`, archived 2026-09-20; S3 = preCICE FSI,
deferred). Reference: Yang & Sotiropoulos, arXiv:1702.02108v4.

Mode: **Standard** (`strict_tdd: false` → tests required, no strict RED-GREEN
ritual). Tasks are grouped by **work unit** (the design's delivery slices
W1→W4, design §9) with hierarchical numbering; each task is completable in one
session. Each work unit ends with its own tests and docs so every slice is
independently reviewable and revertable (proposal §Rollback).

Threat matrix: **N/A** (design §10) — the change introduces no routing, shell
command, VCS/PR-automation or executable-file-classification boundary. The
subprocess surfaces are the S1 class: `makeGeometry.py` invokes pinned `gmsh`
for the **nacelle component only** (fixed inputs, sha256-verified output,
non-destructive `--check`); the blade builder is pure Python with no
subprocess; `runPhaseVI.sh` stages a committed file read-only and **refuses
`--submit` for `-m asm-mesh`** (exit 2); the new Slurm array is prepared-only,
refuses to run without `PHASEVI_LONG_QUEUE_AUTHORIZED=1`, and is never launched
by this change. No threat-matrix RED-test tasks apply; the prepared-only Slurm
guard is asserted by W3.4 and W4.3.

---

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | W1 ~600–900 · W2 ~400–600 · W3 ~400–600 · W4 ~150–350 — **total ~1550–2450** |
| 400-line budget risk | **High** |
| Chained PRs recommended | **Yes** |
| Suggested split | W1 → W2 → W3 → W4 |
| Delivery strategy | `single-pr` (session strategy — maintainer selected Single PR at the session preflight; the S1 `size:exception` precedent is recorded and pre-authorized for this change) |
| Chain strategy | `size-exception` (pre-authorized; chained W1→W2→W3→W4 remains the fallback) |

```
Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: size-exception
400-line budget risk: High
```

The forecast (~1550–2450 changed lines, design §1.2/§9) is far over the
400-line review budget. The maintainer selected **Single PR** at the session
preflight, and the S1 `size:exception` precedent (W1/W2/W4a/W4b) is recorded and
pre-authorized for this change, so `sdd-apply` starts without a further
delivery decision. The W1→W2→W3→W4 boundary remains the prepared fallback: each
unit has a single reviewable purpose, ends with its own tests and docs, and
reverts cleanly on its own; W2/W3/W4 do not change W1 semantics. Under
single-PR delivery, commits should still follow the work units so the reviewer
can verify slice by slice.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| W1 | Shared base extraction (nacelle byte-comparable), element suppression, `bladeSurfaceSource` distribution/CSV/rotation lockstep, integration tests, turbinesFoam README | PR 1 (chained alternative) | `cd turbinesFoam && pytest -q tests/test_blade_surface.py tests/test_nacelle.py tests/test_asm.py tests/test_al.py tests/test_aftal.py tests/test_aftal_asm.py tests/test_libs.py` | `./Allwmake` (exit 0) + `ldd -r $FOAM_USER_LIBBIN/libturbinesFoam.so` clean; serial vs `mpirun -np 2` totals | `git revert` W1 → removes `bladeSurface/`, the base extraction, the suppression key and the `Make/files` lines; nacelle byte-comparable; ALM/no-mesh ASM unchanged (no `surfaceGeometry`) |
| W2 | S809 dataset + PROVENANCE, pure-Python `phaseVI_blade` loft, canonical STL + metadata, builder registry, geometry tests/docs | PR 2 (chained alternative) | `cd turbinesFoam && pytest -q tests/test_blade_data.py tests/test_nacelle_data.py tests/test_phasevi_data.py` | `cd turbinesFoam/geometry && python3 src/makeGeometry.py --check --component phaseVI_blade` (byte-identical, no gmsh) | `git revert` W2 → removes `data/s809/`, `blade_phasevi.py`, registry changes and blade artifacts; nacelle untouched; Phase VI case unaffected (staging is W3) |
| W3 | `fvOptions.ASM-MESH` twin, renderer/`--select`/runner + STL staging, three-way compare, prepared-only array, case/compare/stage tests, README/CHANGELOG | PR 3 (chained alternative) | `cd turbinesFoam && pytest -q tests/test_phasevi_case.py tests/test_phasevi_data.py tests/test_phasevi_compare.py tests/test_blade_stage.py` | `python3 validation/phaseVI/tools/generate_case.py --check`; `sh validation/phaseVI/scripts/runPhaseVI.sh -m asm-mesh -u 7 -mesh coarse` (prepare only; no `--run`/`--submit`); no `sbatch` | `git revert` W3 → removes twin/staging/compare/array additions; `-m alm`/`-m asm` behavior unchanged |
| W4 | Per-`addSup` instrumentation + test, prepared D/32 measurement gate (prepared-only); candidate-query hardening **only if** the gate demands it | PR 4 (conditional, chained alternative) | `cd turbinesFoam && pytest -q tests/test_blade_surface.py::test_instrumentation_line` | Instrumented run reports nodes/candidates/seconds; measurement executed only under explicit authorization | `git revert` W4 → removes instrumentation/measurement additions (and any optimized query); W1 default distribution unchanged |

---

## W1 — Blade surface distributor (C++)

Reference: design §3 D1–D9 (architecture), §4 (interfaces/CSV), §5 (data flow),
§8.1 (test design), §9 W1. Specs: `blade-surface-source`,
`surface-sampling-contract`, `element-type-selection`.

### W1.1 — Element suppression key and frame accessors

- [x] Completed (W1a batch) — `projectElementForce_` (protected, `lookupOrDefault` default `true`) read in `read()` after `writePerf_`; only the two `applyForceField` call sites guarded (incompressible `.C` and compressible overload, `multiplyForceRho` untouched); `chordDirection()`/`spanDirection()` accessors added next to `chordLength()`. `./Allwmake` exit 0 with no warnings from the changed files; `pytest -q tests/test_asm.py tests/test_al.py` unchanged (full suite 92 passed / 3 pre-existing gmsh skips). Commit `5d1acad`. End-to-end `false`-path test owned by W1.7 (key not reachable from a case until the W1.6 plumbing).
- **Files (modify):** `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/actuatorLineElement.{H,C}`
- **Work (design §3 D3, §3 D4/D5):**
  - Add protected `bool projectElementForce_`, read in `read()` after `writePerf_` (`.C:140-141`) via `lookupOrDefault("projectElementForce", true)`.
  - Guard **only** the `applyForceField(forceFieldI)` call: incompressible `.C:1074-1075` and compressible `:1113-1114` (`multiplyForceRho` at `:1117` still runs, preserving `force()` semantics). `calculateForce(Uin)` and `writePerf()` untouched.
  - Add `chordDirection()` accessor next to `chordLength()` (`.H:302-303`) and a `spanDirection()` accessor for the surface pitch forwarding (D5).
- **Acceptance:** absent/true → strip projection exactly as delivered; `false` → force computed, element CSV and public `force()` valid, no strip contribution to the field.
- **Verification:** `cd turbinesFoam && ./Allwmake` (after W1.5); `cd turbinesFoam && pytest -q tests/test_asm.py tests/test_al.py` unchanged.
- **Traces to:** spec `element-type-selection` — "Element strip-projection suppression control" (ADDED), "Default keeps strip projection", "Config key plumbing" (MODIFIED).

### W1.2 — Extract `surfaceSamplerBase` and re-base the nacelle sampler

- [x] Completed (W1a batch) — `surfaceSamplerBase.{H,C,I.H}` extracted with the generic assets (triSurface load + case-relative resolution, centroid node lists, body frame + `createBodyFrame`, `cellSize()`, Eq. 8 `kernel()`, Eq. 7 `interpolateVelocity()` verbatim, `distributeForce(..., candidates)` whose `nullptr` path reproduces the S1 all-local-cells loop byte-for-byte, `rhoRef_`); `nacelleSurfaceSampler`/`nacelleSurfaceSource` re-based keeping the nacelle force model, static frame and CSV. Serial and parallel `postProcessing/nacelle/nacelle.csv` + `nacelle_nodes.csv` and `forceIntegral` `.dat` byte-identical to the S1 baseline (`cmp`/`diff -r`); `pytest -q tests/test_nacelle.py tests/test_libs.py` 8 passed. Commit `5f357c8`.
- **Files (create):** `turbinesFoam/src/fvOptions/nacelleSurface/surfaceSamplerBase.H`, `surfaceSamplerBase.C`, `surfaceSamplerBaseI.H`
- **Files (modify):** `turbinesFoam/src/fvOptions/nacelleSurface/nacelleSurfaceSampler.H`, `nacelleSurfaceSampler.C`, `nacelleSurfaceSamplerI.H`, `nacelleSurfaceSource.H`, `nacelleSurfaceSource.C`
- **Work (design §3 D2, §4.1):** move exactly the generic assets: `triSurface::New` load + case-relative path resolution, `positions_/normals_/areas_` (`faceCentres`/`faceNormals`/`magFaceAreas`, stable face order), body frame (`positionsBody_`, `normalsBody_`, `bodyOrigin_`, `bodyToGlobal_`, `identityBodyFrame_`) + `createBodyFrame`, `cellSize()` (`findCell` + `reduce(minOp)` sentinel), `kernel()` (Eq. 8, support 2.5), `interpolateVelocity()` (Eq. 7, verbatim), and `distributeForce(ff, nodeForces, nodeH, candidates)` where `candidates == nullptr` reproduces the S1 all-local-cells loop byte-for-byte (`ff[cellI] -= F*(w/V)`, `nacelleSurfaceSource.C:194-205`), plus `rhoRef_`. Keep the nacelle force model (`normalForce`/`tangentialForce`/`frictionCoefficient`/`tangentialDirection`/`readViscosity`), static frame, and the `forces_`/`nodeForces_` lists in the nacelle classes.
- **Acceptance:** base is frame- and force-model-agnostic; nacelle accessors, SI units, static body frame and CSV remain as delivered and byte-comparable to the S1 baseline.
- **Verification:** `cd turbinesFoam && ./Allwmake` (after W1.5); `cd turbinesFoam && pytest -q tests/test_nacelle.py tests/test_libs.py`; diff `postProcessing/nacelle/*.csv` against the S1 baseline (byte-comparable).
- **Traces to:** spec `surface-sampling-contract` — "Shared sampling base with regression-gated S1 behavior" (ADDED), "Nacelle behavior unchanged", "Base is force-model agnostic".

### W1.3 — `bladeSurfaceSampler` (rotating frame, partition, bounded candidates)

- [x] Completed (W1b batch) — `bladeSurfaceSampler.{H,C,I.H}` created (construction frame, LE-based station/chord association, 1-D Voronoi partition with fatal invariants, per-rank bin-grid candidate query, `rotate`/`translate`/`pitch`); `./Allwmake` exit 0, `ldd -r` clean, `nm` sampler symbols present; `pytest -q tests/test_nacelle.py tests/test_libs.py` 8 passed. Commit `6789953`.
- **Files (create):** `turbinesFoam/src/fvOptions/bladeSurface/bladeSurfaceSampler.{H,C}`
- **Work (design §3 D4–D7, §4.1/4.3/4.4):**
  - Node set: triangle centroids in `triSurface` face order; canonical, global and body-frame node lists.
  - Station/chord association: `s(X) = (X − surfaceOrigin_)·spanAxis_`; `c(X) = chordMount_i − ((X − position_i)·unit(chordDirection_i))/chordLength_i` (LE-based, element frame of the assigned patch).
  - Partition (once, constructor): 1-D Voronoi along station with midpoint boundaries (open root/tip), `patchAreaShare_[i] = A_i / Σ_patch A_j`; fatal assertions that every node is assigned, every element owns a non-empty patch, and the patch area sum equals the total `triSurface` area (relative tolerance).
  - Body frame (contract): `bodyOrigin_ = surfaceOrigin` (user `bodyOrigin` overrides), `bodyAxis = surfaceSpanDirection` (user `bodyAxis` overrides); `positions()` = `bodyToGlobal_.T() & (positionsGlobal_ − bodyOrigin_)` — azimuth-dependent, ordering fixed at initialization.
  - Bounded candidates (once): per-rank uniform bin grid over local cell centres, bin size `max(min_i support_i, small)`, 27-bin overlap query per node with the S1 axis-aligned prefilter; support `2.5·h_i` (cosine) or `ε_i·sqrt(ln(1000))` with `ε_i = 2·cbrt(V_i)·meshFactor` (Gaussian, `meshFactor` fallback chain per D7); fatal on an unreachable `cellSize`.
  - Rigid `rotate`/`translate`/`pitch` entry points for the blade forwarding (pitch about the element pitch axis through the root chord pitch-axis point; documented approximation).
- **Acceptance:** every node in exactly one patch with patch areas summing to the surface area; candidates never a full local-cell scan; node ordering stable under rotation while `positions()` reflect azimuth.
- **Verification:** `cd turbinesFoam && ./Allwmake` (after W1.5); invariants and lockstep asserted by W1.7 (`test_partition_invariants_from_csv`, `test_rotation_lockstep`).
- **Traces to:** spec `blade-surface-source` — "Imported blade triangulation and node metadata", "Element-force-to-patch mapping and force preservation", "Selectable kernel and width", "Rotating-frame lockstep and restart idempotency", "Bounded distribution and performance measurement" (bounded query, W1 deliverable); spec `surface-sampling-contract` — "Body frame" (MODIFIED), "Stable node ordering" (MODIFIED).

### W1.4 — `bladeSurfaceSource` (distribution, moment, CSV)

- [x] Completed (W1b batch) — `bladeSurfaceSource.{H,C,I.H}` created (`distribute` Eq. 18 with S1 sign and patch area shares, `moment`, SI accessors, per-station/per-node CSV, compressible rho path; no instrumentation — W4 owns it); `src/Make/files` registrations done; `./Allwmake` exit 0, `ldd -r` clean, 29 `bladeSurface*` symbols; `pytest -q tests/test_nacelle.py tests/test_libs.py` 8 passed. Commit `02d18f5`.
- **Files (create):** `turbinesFoam/src/fvOptions/bladeSurface/bladeSurfaceSource.{H,C}`
- **Work (design §3 D1/D8/D9, §4.1–4.5):** plain helper class (not an `fv::option`, no RTS registration; sink is the owning blade `forceField_`, input `PtrList<actuatorLineElement>`).
  - Config keys (design §4.2): `surfaceGeometry` (case-relative through `mesh_.time().path()`), `kernel` (`cosine` default | `gaussian`), `meshFactor` (Gaussian only; fallback `profileData` GaussianCoeffs then 2.0), `rho`, `referenceVelocity`/`nu` accepted for template parity, `bodyOrigin`/`bodyAxis` overrides, `writePerf true`, `writeNodePerf false`.
  - `distribute(volVectorField&, vector&, const volScalarField* rhoPtr = nullptr)`: per node `F_node = patchAreaShare_[i]·elements_[patch_[i]].force()` (per unit density); `forceField_[c] -= F_node*(w/V_c)` over the node's candidates (Eq. 18, S1 sign); compressible path scales by local `rho`; total via `returnReduce(sumOp)`.
  - `moment(point)` from the node shares in the global frame (D8); SI accessors `positions()/forces()/normals()/areas()` delegated to the sampler (body frame, force-on-blade).
  - CSV on master only: `postProcessing/bladeSurface/<name>.csv` per station (`time,station,root_dist,area,force_x,force_y,force_z,c_ref_n,c_ref_t,f_ref_n,f_ref_t`, patch force in SI via `rhoRef_`, coefficient columns from the element public accessors) and opt-in `<name>_nodes.csv` (`time,node,x,y,z,nx,ny,nz,fx,fy,fz,area,station,chord_fraction`).
  - No instrumentation in W1 (W4 owns it).
- **Acceptance:** field integral equals the summed element forces exactly once; CSV parses with the documented schema and is convertible to the existing element conventions; SI contract exposed in the body frame with force-on-blade sign.
- **Verification:** `cd turbinesFoam && ./Allwmake` (after W1.5); exercised by W1.7 (`test_serial_surface`, `test_station_and_node_csv`, `test_surface_moment_in_torque`, `test_parallel_total_preserved`).
- **Traces to:** spec `blade-surface-source` — "Additive surface activation", "Exactly-once force application", "Distribution-only model, no surface-sampled BEM", "Blade moment includes the surface contribution", "Surface CSV output", "MPI correctness", "Sampling contract exposure on the rotating blade frame".

### W1.5 — `Make/files` registration and link gate

- [x] Completed (W1a batch; blade lines deferred to W1b) — `fvOptions/nacelleSurface/surfaceSamplerBase.C` registered after the nacelle lines; `./Allwmake` exit 0 and `ldd -r $FOAM_USER_LIBBIN/libturbinesFoam.so 2>&1 | grep -i undefined` empty (`libsurfMesh.so` resolved, no duplicate symbols). The `fvOptions/bladeSurface/bladeSurfaceSampler.C` and `bladeSurfaceSource.C` entries are intentionally deferred to W1b because those files are created there; adding them now would fail the build. Commit `5f357c8`.
- **Files (modify):** `turbinesFoam/src/Make/files`
- **Work (design §13):** register `fvOptions/nacelleSurface/surfaceSamplerBase.C`, `fvOptions/bladeSurface/bladeSurfaceSampler.C` and `fvOptions/bladeSurface/bladeSurfaceSource.C` after the nacelle lines (`Make/files:15-16`). `-lsurfMesh` is already linked by S1 (`src/Make/options:13`) — do not modify it.
- **Acceptance:** all new sources compile into `libturbinesFoam.so` with no duplicate-symbol link error.
- **Verification:** `cd turbinesFoam && ./Allwmake` (exit 0); `ldd -r $FOAM_USER_LIBBIN/libturbinesFoam.so 2>&1 | grep -i undefined` empty.
- **Traces to:** design §13 (file table), §4.5; spec `surface-sampling-contract` — "Shared sampling base with regression-gated S1 behavior" (build integration).

### W1.6 — `actuatorLineSource` and AFTAL plumbing

- [x] Completed (W1c1 batch) — `read()` stores `surfaceGeometry_` (`fileName::null` sentinel); `createElements()` plumbs a user `projectElementForce` and overrides it to `false` when a surface is configured (key omitted otherwise, element default `true` kept); the source owns an `autoPtr<bladeSurfaceSource>` built after the element loop and calls `distribute(forceField_, force_, rhoPtr)` after it in both momentum overloads; `rotate`/`translate` forward and `pitch` (both overloads) forwards the rigid root-frame rotation while `setSpeed`/`scaleVelocity`/`setOmega` leave the geometry untouched; `moment()` returns the surface node moment when active; AFTAL injects `surfaceOrigin`/`surfaceSpanDirection` (outward root→tip)/`surfaceChordDirection` post-cone/azimuth only with `surfaceGeometry`; `bladeSurfaceSource` gained the three forwarding methods D5 requires. `./Allwmake` exit 0 (no new warnings), `ldd -r` clean; `pytest -q tests/test_aftal.py tests/test_aftal_asm.py tests/test_asm.py tests/test_al.py` 11 passed (1 pre-existing warning); `pytest -q tests/test_nacelle.py tests/test_libs.py` 8 passed. Commit `6e6719d`.
- **Files (modify):** `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineSource.{H,C}`, `turbinesFoam/src/fvOptions/axialFlowTurbineALSource/axialFlowTurbineALSource.C`
- **Work (design §3 D1/D3/D5, §4.2, §5):**
  - `read()` stores `surfaceGeometry_` when present (`.C:55-101`).
  - `createElements()` (`.C:337-346`) plumbs a user `projectElementForce` exactly like `elementType`/`nChordwise`; when `surfaceGeometry` is present it overrides it to `false` for every element of that blade (precedence: surface injection > blade-subdict value > element default); the key is never added when no surface is configured.
  - Constructs and owns `autoPtr<bladeSurfaceSource>` from the blade subdict + `elements_`; calls `distribute(forceField_, force_, rhoPtr)` after the element loop (`.C:704-708`).
  - Transform lockstep (`.C:577-647`): `rotate(point, axis, radians)` and `translate()` also forward to the surface; `pitch(radians[, chordFraction])` rotates the surface rigidly about `elements_[0].spanDirection()` through the root chord pitch-axis point (documented approximation); `setSpeed()`/`scaleVelocity()`/`setOmega()` do not move the geometry.
  - `moment(point)` (`.C:668-683`) returns the surface node moment instead of the element moment when the distributor is active (D8).
  - AFTAL `createBlades()` injects `surfaceOrigin` (`origin_`), `surfaceSpanDirection` = `unit(elementGeometry[nGeomPoints-1][0] − elementGeometry[0][0])` (outward root→tip) and `surfaceChordDirection` = `unit(elementGeometry[0][3])`, taken after cone/azimuth, only when `surfaceGeometry` is present (`axialFlowTurbineALSource.C:179-194,202,211-228`); the element pitch axis `unit(elementGeometry[0][1])` is deliberately not used (it would mirror the surface).
- **Acceptance:** a surface-enabled case applies the blade force once and follows rotation/pitch/translate; no `surfaceGeometry` → no distributor, no injection, byte-identical ALM/no-mesh ASM; the injected frame places both blades (blade2 azimuth 180) without a separate user key.
- **Verification:** `cd turbinesFoam && ./Allwmake`; `cd turbinesFoam && pytest -q tests/test_aftal.py tests/test_aftal_asm.py tests/test_asm.py tests/test_al.py`; placement asserted end-to-end by W1.7.
- **Traces to:** spec `blade-surface-source` — "Additive surface activation", "Exactly-once force application", "Rotating-frame lockstep and restart idempotency", "Blade moment includes the surface contribution"; spec `element-type-selection` — "Config key plumbing", "Suppression injected only with a surface".

### W1.7 — Integration fixtures and `tests/test_blade_surface.py`

- [x] Completed (W1c2a + W1c2b batches) — fixtures + all ten tests; W1c2b committed the remaining five tests (`c787ed2`) plus the 12-significant-digit CSV fix (`c53711d`). Orchestrator-verified on the committed tree: `/scratch/leahk/eduardo.donestevez/venv/bin/python -m pytest -q tests/test_blade_surface.py` → **10 passed in 44.50s**; full suite → **105 passed, 1 warning in 445.52s**.
- Progress W1c2a (2026-09-21, commit `648e21a`): fixtures
  `tests/bladeSurface/**` (26^3 0.1 m cubic mesh, uniform inflow, standalone
  one-cylinder-element blade, two-triangle plate STL, `system/fvOptions`
  default plus `fvOptions.surface` cosine and `fvOptions.surface.gaussian`,
  `forceIntegral` functionObject, `Allrun`/`Allclean`) and
  `tests/bladeSurfaceAFTAL/**` (one blade, two geometry rows → one element, no
  hub/tower, `writeNodePerf true`, `rho 1.0`, multi-triangle plate at the
  element station with nodes offset from the element position);
  `tests/conftest.py` `SOLVER_DRIVEN` updated. Five tests green:
  `test_serial_surface`, `test_default_path_projects_strips`,
  `test_suppressed_element_still_reports`, `test_station_and_node_csv`,
  `test_partition_invariants_from_csv`
  (`cd turbinesFoam && python3 -m pytest -q tests/test_blade_surface.py` →
  5 passed; `tests/test_nacelle.py tests/test_libs.py` → 8 passed).
  Pending for W1c2b: `test_rotation_lockstep`,
  `test_surface_moment_in_torque`, `test_parallel_total_preserved`,
  `test_kernel_gaussian_conserves`, `test_missing_empty_corrupt_stl_aborts`
  (listed at the end of the test module).
- **Files (create):** `turbinesFoam/tests/test_blade_surface.py`, `turbinesFoam/tests/bladeSurface/**` (0.1 m cubic mesh, uniform inflow, standalone one-cylinder-element blade + two-triangle plate STL, `system/fvOptions` and `system/fvOptions.surface` (plus a Gaussian variant) with a `forceIntegral` functionObject), `turbinesFoam/tests/bladeSurfaceAFTAL/**` (minimal AFTAL fixture: one blade, two geometry rows → one element, no hub/tower, `writeNodePerf true`, `rho 1.0`, multi-triangle plate at the element station so nodes are offset from the element position)
- **Files (modify):** `turbinesFoam/tests/conftest.py` (add `"test_blade_surface.py"` to `SOLVER_DRIVEN`)
- **Work (design §8.1):** implement `test_serial_surface` (partition-of-unity / no-double-count), `test_default_path_projects_strips`, `test_suppressed_element_still_reports` (first PIMPLE step matches default exactly), `test_station_and_node_csv`, `test_partition_invariants_from_csv`, `test_rotation_lockstep`, `test_surface_moment_in_torque` (`rtol 1e-6`; element-position moment must fall outside the band, asserting the D8 replacement), `test_parallel_total_preserved` (`mpirun -np 2`, node straddling the processor boundary), `test_kernel_gaussian_conserves`, `test_missing_empty_corrupt_stl_aborts`.
- **Acceptance:** all tests pass with OpenFOAM loaded and skip cleanly without it; the moment/torque test asserts the applied-load convention, not merely that a moment exists.
- **Verification:** `cd turbinesFoam && pytest -q tests/test_blade_surface.py`.
- **Traces to:** design §8.1; spec `blade-surface-source` — "Exactly-once force application", "Imported blade triangulation and node metadata", "Element-force-to-patch mapping and force preservation", "Rotating-frame lockstep and restart idempotency", "Blade moment includes the surface contribution", "Surface CSV output", "MPI correctness", "Sampling contract exposure on the rotating blade frame"; spec `element-type-selection` — "Suppressed element still computes and reports".

### W1.8 — W1 regression gate and turbinesFoam docs

- [x] Completed (W1c2b batch, commit `bd450c8`) — `turbinesFoam/README.md` documents `surfaceGeometry`, the `projectElementForce` suppression semantics, kernel modes + `meshFactor` fallback, CSV paths/schemas, the surface-moment/torque convention and the fork-divergence note. Regression gate verified by the orchestrator: full suite **105 passed, 1 warning** (ALM/ASM/cftal/nacelle unchanged; the +10 are the new blade-surface tests).
- **Files (modify):** `turbinesFoam/README.md`
- **Work:**
  - Regression gate: full existing suite unchanged (`test_al`, `test_asm`, `test_aftal`, `test_aftal_asm`, `test_cftal`, `test_libs`, `test_nacelle`); ALM and no-mesh ASM CSVs byte-identical.
  - Docs: document `surfaceGeometry`, the `projectElementForce` suppression semantics, kernel modes (`cosine` default / `gaussian` ablation) and the `meshFactor` fallback, the CSV paths/schemas, the surface-moment/torque convention, and the fork-divergence note (new source classes not in upstream).
- **Acceptance:** build + full suite green; README documents the new source; no adapter/`fsiOmega` file changed.
- **Verification:** `cd turbinesFoam && ./Allwmake`; `cd turbinesFoam && pytest -q`; README review.
- **Traces to:** spec `element-type-selection` — "Default actuator line behavior preserved", "Existing case regression"; spec `surface-sampling-contract` — "Seam only — no adapter or fsiOmega change".

---

## W2 — Blade geometry (`turbinesFoam/geometry/`)

Reference: design §3 D10–D12, §4.6, §7.1–7.4, §8.2, §9 W2. Specs:
`blade-geometry-generation`, `turbine-geometry-pipeline`,
`phasevi-data-provenance`.

### W2.1 — Committed S809 dataset and provenance

- [x] Completed (W2a batch) — `data/s809/s809_somers_nlr.csv` (31 upper + 30 lower, shared TE `(1.0000, 0.0000)`, upper LE→TE then lower LE→TE) and `PROVENANCE.md` committed. Table 2 of Somers, NREL/SR-440-6918 (PDF page index 19) extracted with PyMuPDF 1.27.2.3 from the locally verified PDF (sha256 `a7496aad…feeb3`, re-verified live); recipe (regex/row grouping) and closure convention recorded. Both cross-checks pass and abort non-zero on failure: (1) TP-500-29955 Table A-2 agrees to all published digits (31/31 upper, 30/30 lower; the documented extra zero row recorded); (2) Ramsay Table A1 measured model normalized by the 18-inch chord is within 1 % chord outside the last 10 % of chord (max deviation upper `0.000894` at `x/c = 0.00037`, lower `0.000906` at `x/c = 0.04223`; the documented TE thickening excluded and reported). Re-extraction reproduces the committed CSV byte-identically (sha256 `861f3fe5…`). Commit `64d9cb8`.
- **Files (create):** `turbinesFoam/validation/phaseVI/data/s809/s809_somers_nlr.csv`, `turbinesFoam/validation/phaseVI/data/s809/PROVENANCE.md`
- **Work (design §3 D11, §7.4):** extract Table 2 ("S809 Airfoil Coordinates", PDF page index 19) from the verified local `/scratch/leahk/eduardo.donestevez/tmp/phasevi_research/verified/s809_somers_nlr.pdf` (Somers, NREL/SR-440-6918; sha256 `a7496aad…feeb3`, re-verified live) with PyMuPDF (recorded tool/version, no `pdftotext` on this host); numeric-token regex `-?(?:\d+\.\d+|\.\d+)`, row grouping `(upper x/c, upper z/c, lower x/c, lower z/c)`, 31 upper + 30 lower ending at the shared TE `(1.0000, 0.0000)`; commit the long CSV `surface,x_over_c,z_over_c` (upper LE→TE then lower LE→TE) with source header comments. PROVENANCE records report, PDF sha256, table id, method/tool/version/date, committed CSV sha256, and both cross-checks: (1) independent transcription of TP-500-29955 Table A-2 (`29955_nlr.pdf`, sha256 `822ee980…`); (2) Ramsay Table A1 measured model (`s809_ramsay.pdf`, sha256 `9b5d151f…`) normalized by the 18-inch desired chord with a 1 % chord tolerance outside the last 10 % of chord, the documented upper-surface thickness addition excluded and reported, and the measured maximum deviation recorded; a cross-check failure aborts non-zero. No PDF is committed.
- **Acceptance:** provenance complete per the spec; coordinates parse as upper/lower pairs with a shared trailing edge and numeric values.
- **Verification:** content review; `cd turbinesFoam && pytest -q tests/test_blade_data.py::test_s809_provenance_complete tests/test_blade_data.py::test_s809_parses_as_airfoil` (after W2.5).
- **Traces to:** spec `blade-geometry-generation` — "Committed S809 coordinates with extraction provenance"; spec `phasevi-data-provenance` — "Committed S809 profile coordinates", "Per-directory provenance records" (MODIFIED), "Derived artifacts only".

### W2.2 — `blade_phasevi.py` pure-Python structured loft

- [x] Completed (W2a batch) — `geometry/src/blade_phasevi.py` created (490 lines): committed-input parse, closed 60-point profile, circle/S809 section rule, §7.3 generation frame with `SIGMA = -1`, 25×60 = 3000 outward-wound wetted triangles (no caps), `canonical_triangles`/`write_binary_stl` reuse with the per-component header, populated `radial_station`/`chord_fraction` metadata and the §4.6 hashes. Two fresh generations byte-identical (STL `77def499…`, metadata `01f75d17…`); an independent re-implementation of §7.3 confirms the exact triangulation (count/winding/order), 1560 ring vertices, 120 boundary edges forming two 60-edge rings at `z = 0.5083`/`5.029`, all 26 station planes, and every metadata node value; `PITCH_DEG = 3.0` equals `case.yaml` `turbine.pitch_deg`. No gmsh/subprocess. Commit `98444eb`. The committed STL/metadata and the registry wiring are W2.3/W2.4.
- **Files (create):** `turbinesFoam/geometry/src/blade_phasevi.py`
- **Work (design §3 D10, §7.3):** parse the 26 committed stations (`phaseVI_blade.csv`) and the S809 CSV; closed 60-point profile (31 upper points + reversed lower surface without the TE duplicate, closing over the small blunt-LE gap); per-station section: circle of radius `chord/2` at mid-chord for `r ≤ 0.8835` with the same fixed perimeter fractions/order, S809 (`u = x/c`, `w = z/c`) for `r ≥ 1.0085`; map `y = (0.25 − u)·chord`, `x = w·chord`, `z = r`, rotate about `+z` by `σ·(−(twist_report + pitch_deg))` with `σ = −1` (Phase VI; quarter-chord on the radial reference line); `PITCH_DEG = 3.0` asserted against `case.yaml` `turbine.pitch_deg`; loft 25 segments × 60 points with fixed winding = 3000 triangles; wetted surface only, no root/tip caps; node metadata `radial_station` (mean vertex `z`) and `chord_fraction` (mean vertex `u`); reuse `canonical_triangles`/`write_binary_stl` with the per-component header and recomputed normals.
- **Acceptance:** surface spans all 26 stations (cylinder + transition + S809), one edge-manifold open shell with exactly two boundary rings; regeneration from committed inputs is byte-identical; no gmsh involved.
- **Verification:** local generation run; `cd turbinesFoam && pytest -q tests/test_blade_data.py::test_stl_manifold_wetted_only tests/test_blade_data.py::test_check_byte_identical_without_gmsh` (after W2.5).
- **Traces to:** spec `blade-geometry-generation` — "Pure-Python structured loft over the full wetted span", "Deterministic byte-identical regeneration", "Canonical STL and per-node station/chord metadata"; spec `turbine-geometry-pipeline` — "Deterministic gmsh and Python generation" (MODIFIED), "Blade uses the Python builder".

### W2.3 — Builder registry and route-aware `generate`/`check`

- [x] Completed (W2b batch) — `Component` gains `builder` (the route string); `BUILDERS = {"nacelle": "gmsh", "phaseVI_blade": "python"}` with `COMPONENTS = tuple(BUILDERS)`, `RESERVED_COMPONENTS = ()` and `RETIRED_COMPONENTS = ("blade0", "blade1", "blade2")` (the retired-name error is the only remaining `blade0/1/2` policy); the single `STL_HEADER` became per-component `STL_HEADERS` (nacelle bytes unchanged); the gmsh path is renamed `build_gmsh_component` and `build_blade_component` lazily imports `blade_phasevi` (header-consistency guard, no subprocess); `generate`/`check` dispatch on `Component.builder`, the blade route regenerates into a temp dir with no gmsh lookup at all (`--gmsh /nonexistent/gmsh` is ignored on that route); `shutil.which("gmsh")` moved behind the gmsh route; `--component` help and the unknown/retired errors derive from the registry. Verified: `env PATH=/usr/bin:/bin python src/makeGeometry.py --check --component phaseVI_blade` → exit 0; `--component blade0` → exit 1 with the S2-retired message; `--component bogus` → exit 2 listing `available: nacelle, phaseVI_blade`; `--check --component nacelle` with pinned gmsh 4.15.2 → clean. Commit `67708d4`.
- **Files (modify):** `turbinesFoam/geometry/src/makeGeometry.py`
- **Work (design §3 D12, §7.2):** `Component` gains `builder`; `COMPONENTS = ("nacelle", "phaseVI_blade")`; `RESERVED_COMPONENTS = ()`; `BUILDERS` mapping (`nacelle → gmsh builder`, `phaseVI_blade → Python builder`); rename the gmsh implementation to `build_gmsh_component` and add `build_blade_component`; `generate()`/`check()` dispatch on the registry, with the blade route regenerating into a temp dir and no gmsh lookup; move `shutil.which("gmsh")` behind the nacelle route (`:549-556`); `--component` help and unknown/retired-name errors derive from the registry (`:522-547`); per-component STL headers with the nacelle header bytes unchanged; no `_reserved` block for the blade.
- **Acceptance:** `--check --component phaseVI_blade` works without a runnable gmsh; the nacelle remains gmsh-pinned; unknown components are rejected listing the registry; the retired `blade0/1/2` names are not advertised.
- **Verification:** `cd turbinesFoam/geometry && python3 src/makeGeometry.py --check --component phaseVI_blade` (exit 0, no gmsh); nacelle `--check` unchanged with gmsh present.
- **Traces to:** spec `turbine-geometry-pipeline` — "Component builder registry" (ADDED), "`--check` regenerability" (MODIFIED), "Unknown component rejected", "Blade STL accommodation with S2 deferral" (REMOVED — superseded by the registry and the populated blade component); spec `blade-geometry-generation` — "Component registration and naming policy", "Reservation retired".

### W2.4 — Committed blade STL, metadata and geometry docs

- [x] Completed (W2b batch) — `stl/phaseVI_blade.stl` (150 084 bytes = 84 + 50×3000) and `metadata/phaseVI_blade.json` committed with sha256 `77def499…` / `01f75d17…` — byte-identical to both W2a generations (`cmp`, and the committed git blobs via `git cat-file`) — and input sha256 `7a43047d…`; the metadata is populated per §4.6 (component, `format_version`, generator `{"script": "src/makeGeometry.py", "builder": "phaseVI_blade"}`, inputs with both CSV sha256 and `pitch_deg 3.0`, `input_sha256`, units, `n_triangles 3000`, `stl_sha256`, 3000 node entries with `normal`/`area`/`radial_station`/`chord_fraction`, no `_reserved`). README documents the two components, the builder routes, the naming resolution (blade0/1/2 retired, one STL serves both blades, MEXICO a separate component) and both metadata schemas; PROVENANCE records the per-component source/generator/input hashes citing NREL/TP-500-29955 Table A-1 and the committed S809 coordinates (NREL/SR-440-6918 Table 2) and retires the blade0/1/2 deferral. Regeneration twice in place produced the same two hashes; stale STL/metadata/PROVENANCE copies are detected with exit 1 and the tree is never modified. Commits `7c3d7e2` (artifacts + PROVENANCE) and `bbd143f` (README).
- **Files (create):** `turbinesFoam/geometry/stl/phaseVI_blade.stl`, `turbinesFoam/geometry/metadata/phaseVI_blade.json`
- **Files (modify):** `turbinesFoam/geometry/README.md`, `turbinesFoam/geometry/PROVENANCE.md`
- **Work (design §4.6, §7.1, §7.4, §3 D12):** generate and commit the canonical binary STL (3000 triangles, fixed header, recomputed facet normals) and the §4.6 metadata (component, `format_version`, generator, inputs with `blade_csv`/`s809_csv` sha256 and `pitch_deg`, `input_sha256`, units, `n_triangles`, `stl_sha256`, one entry per node with `normal`/`area`/`radial_station`/`chord_fraction`, no `_reserved`). README gains the component table (nacelle + `phaseVI_blade`), the builder route, and the naming resolution; PROVENANCE records per-component source, generator route and input hashes citing the Phase VI geometry and the committed S809 coordinates instead of the deferred MEXICO tables.
- **Acceptance:** committed bytes match regeneration; metadata is populated (numeric `radial_station`/`chord_fraction`, no reserved-null blade mapping); docs cite the S809 dataset and retire `blade0/1/2`.
- **Verification:** `cd turbinesFoam/geometry && python3 src/makeGeometry.py --check --component phaseVI_blade` clean; `sha256sum` stable across two regenerations.
- **Traces to:** spec `turbine-geometry-pipeline` — "Per-component STL output", "Metadata JSON", "Provenance"; spec `blade-geometry-generation` — "Blade component documentation", "One blade STL serves both blades".

### W2.5 — Blade data tests, nacelle/Phase VI test updates, W2 gate

- [x] Completed (W2c batch) — `tests/test_blade_data.py` created with the six pure-Python tests: `test_s809_provenance_complete` (report/DOI/Table 2/PyMuPDF 1.27.2.3/date/PDF sha256/cross-checks/committed CSV sha256 recomputed), `test_s809_parses_as_airfoil` (31 upper + 30 lower, shared TE `(1.0000, 0.0000)`, strictly increasing `x/c`, blunt-LE closure, `load_s809` agreement), `test_blade_metadata_complete` (component/generator/inputs with both CSV hashes, `pitch_deg == PITCH_DEG == case.yaml`, `input_sha256` recomputed, pinned STL/metadata sha256, no `_reserved`, 3000 nodes with sig6-exact centroid `radial_station` and `chord_fraction ∈ [0,1]` spanning the chord), `test_stl_manifold_wetted_only` (4440 interior edges opposed, 120 boundary edges in two 60-edge rings at `0.5083`/`5.029`, no duplicate/degenerate triangles, all 26 station planes), `test_check_byte_identical_without_gmsh` (in-place `--check --component phaseVI_blade --gmsh /nonexistent/...` exit 0 + `up to date` + `input sha256` printed + tree snapshot unchanged; package-layout copies with corrupt STL/metadata/PROVENANCE exit 1 with the exact stale label and leave both the copy and the committed tree unchanged), `test_builder_registry_and_retired_reservation` (registry tuples, Python-route acceptance, help/unknown/retired CLI text, nacelle route still gated on the pinned gmsh). `test_nacelle_data.py` updated (`_reserved` documented as the legacy S1 placeholder with explicit null asserts, README token list now the naming policy, `blade0/1/2` rejection renamed to retirement semantics; nacelle bytes newly pinned by literal sha256 in `test_committed_nacelle_bytes_are_pinned`). `test_phasevi_data.py` updated (`data/s809/` in the provenance-directory checks with its own field assertions; no-artifacts walk unchanged). W2 gate verified: modules are pure-Python and not in `SOLVER_DRIVEN`; stale detection non-destructive; no nacelle artifact changed. Runtime: `pytest -q tests/test_blade_data.py tests/test_nacelle_data.py tests/test_phasevi_data.py` → `28 passed, 3 skipped` (no gmsh) / `31 passed` with `glu/9.0.2_gnu`; `makeGeometry.py --check` clean on the blade route without gmsh and on the nacelle route with the pinned gmsh. Commit `b567d26`. **This closes W2.**
- **Files (create):** `turbinesFoam/tests/test_blade_data.py`
- **Files (modify):** `turbinesFoam/tests/test_nacelle_data.py`, `turbinesFoam/tests/test_phasevi_data.py`
- **Work (design §8.2):** `test_s809_provenance_complete`, `test_s809_parses_as_airfoil`, `test_blade_metadata_complete`, `test_stl_manifold_wetted_only`, `test_check_byte_identical_without_gmsh`, `test_builder_registry_and_retired_reservation`; update the nacelle data assertions (`_reserved`, README token list, deferred-blade rejection) while keeping the nacelle bytes/hashes pinned; include `data/s809/` in the Phase VI provenance-directory checks and keep the no-artifacts walk.
- **Acceptance:** pure-Python and CI-safe (no OpenFOAM); stale-artifact detection is non-destructive; nacelle artifacts unchanged.
- **Verification:** `cd turbinesFoam && pytest -q tests/test_blade_data.py tests/test_nacelle_data.py tests/test_phasevi_data.py`; `cd turbinesFoam/geometry && python3 src/makeGeometry.py --check` (nacelle gmsh checks skip cleanly when gmsh is absent).
- **Traces to:** spec `blade-geometry-generation` — "Pure-Python blade data tests"; spec `turbine-geometry-pipeline` — "Pure-Python CI-safe test"; spec `phasevi-data-provenance` — "Pure-Python data-sanity tests".

---

## W3 — Phase VI third variant (`fvOptions.ASM-MESH`)

Reference: design §4.7, §6.1–6.6, §8.3, §9 W3, §13. Specs:
`phasevi-validation-case`, `phasevi-run-and-compare`,
`phasevi-data-provenance`.

### W3.1 — Third twin renderer and `case.yaml` stage

- [x] Completed (W3a batch, committed by the interrupted run as `e7f8dd7` and re-verified from the committed tree) — `render_fv_options(..., surface_geometry=None, surface_kernel=None)` renders `surfaceGeometry "constant/triSurface/phaseVI_blade.stl";` at the element-key indentation (16 spaces) and `kernel gaussian;` only for the ablation (cosine renders no key); `projectElementForce` is never rendered; `blade2` keeps `$blade1;` + `azimuthalOffset 180`; `outputs()` emits `case/system/fvOptions.ASM-MESH` on every run; CLI `--surface-kernel {cosine,gaussian}` (default cosine); `case.yaml` gains the prepared `asm-mesh` stage (`queue: sequana_cpu_long`, `models: [asm-mesh]`, `meshes: [coarse, fine]`, `speeds: [7]`, `executes: false`). Verified: `generate_case.py --check` exit 0; committed twin vs ASM = exactly the one `surfaceGeometry` line, vs ALM = the three blade keys only; default render byte-matches the committed twin (only the case-relative polars include differs in a temp dir); gaussian render adds exactly `kernel gaussian;`; `pytest -q tests/test_phasevi_case.py` 15 passed. Commit `e7f8dd7`.
- **Files (modify):** `turbinesFoam/validation/phaseVI/config/case.yaml`, `turbinesFoam/validation/phaseVI/tools/generate_case.py`
- **Work (design §6.1, §4.2):** `render_fv_options(..., surface_geometry=None, surface_kernel=None)` adds `surfaceGeometry "constant/triSurface/phaseVI_blade.stl";` (plus `kernel gaussian;` only when the ablation is selected; cosine is the default) at the element-key indentation in each blade subdict; `projectElementForce` is **not** rendered (the source injects it); `blade2` keeps `$blade1;` + `azimuthalOffset 180`, propagating the keys to both identical blades; `outputs()` emits `case/system/fvOptions.ASM-MESH` on every run so `--check` covers it; CLI gains `--surface-kernel {cosine,gaussian}` (default `cosine`); `case.yaml` gains the prepared stage `asm-mesh` (`queue: sequana_cpu_long`, `models: [asm-mesh]`, `meshes: [coarse, fine]`, `speeds: [7]`, `executes: false`).
- **Acceptance:** the three twins differ only in the blade element/surface keys; `generate_case.py --check` is clean; the committed ASM-MESH twin matches the renderer.
- **Verification:** `cd turbinesFoam && python3 validation/phaseVI/tools/generate_case.py --check`; `cd turbinesFoam && pytest -q tests/test_phasevi_case.py` (after W3.5).
- **Traces to:** spec `phasevi-validation-case` — "ALM and ASM fvOptions twins" (MODIFIED), "Three variants differ only in blade keys", "ASM-mesh variant carries the surface keys", "Renderer check clean".

### W3.2 — Model selection, runner and STL staging

- [x] Completed (W3a batch; the interrupted run left the three files uncommitted, reviewed, completed and committed here) — `stage_blade_stl.py` reads `meta.stl_sha256`, hashes the source, creates `constant/triSurface/`, copies to `constant/triSurface/phaseVI_blade.stl`, checks the copy and echoes the staged hash (exit 3 on missing source or mismatch, before any copy); `case_config.py` gains `MODEL_CHOICES = ("alm", "asm", "asm-mesh")` and the three-model error text; `runPhaseVI.sh` accepts `-m asm-mesh` (twin mapping `fvOptions.ASM-MESH`, run id `asm-mesh-U<speed>-<mesh>`, `--nchordwise` ASM-family-only, `--submit` refused exit 2 pointing at `scripts/slurm/asm-mesh.slurm`), stages through the helper before the mesh link and records `staged_stl_sha256` in `run.json`. Verified: `runPhaseVI.sh -m asm-mesh -u 7 -mesh coarse` prepare-only exit 0; staged sha256 `77def499…` == committed STL and `cmp` identical; `surfaceGeometry` stays case-relative and resolves inside the run dir; `--submit` exit 2; corrupt STL exit 3 with no stale copy left; missing source exit 3; `--select 7 coarse asm-mesh` accepted while `bogus` exits 2; `sh -n` clean. Commit `6474bdc`.
- **Files (create):** `turbinesFoam/validation/phaseVI/tools/stage_blade_stl.py`
- **Files (modify):** `turbinesFoam/validation/phaseVI/tools/case_config.py`, `turbinesFoam/validation/phaseVI/scripts/runPhaseVI.sh`
- **Work (design §6.2/§6.3):** extend the `--select` whitelist to `("alm", "asm", "asm-mesh")` and the error text (`case_config.py:585-586`); `runPhaseVI.sh` accepts `-m asm-mesh`, run id `asm-mesh-U<speed>-<mesh>`, twin mapping `asm-mesh) twin="fvOptions.ASM-MESH"`, keeps `--nchordwise` ASM-family-only, and `--submit` refuses (exit 2) pointing at `scripts/slurm/asm-mesh.slurm` (mirroring the Stage 3 refusal). Staging: `stl_src="$root/../../geometry/stl/phaseVI_blade.stl"`, `meta="$root/../../geometry/metadata/phaseVI_blade.json"`; `stage_blade_stl.py` reads `meta.stl_sha256`, hashes the source, creates `constant/triSurface/`, copies to `constant/triSurface/phaseVI_blade.stl`, aborts with exit 3 on hash mismatch or missing source, and echoes the staged hash; `run.json` records `staged_stl_sha256`. `surfaceGeometry` stays case-relative (the base sampler resolves it).
- **Acceptance:** `runPhaseVI.sh -m asm-mesh -u 7 -mesh coarse` prepares a self-contained run directory without `--run`/`--submit`; the staged copy hash equals the committed STL; a mismatch aborts.
- **Verification:** `cd turbinesFoam && sh validation/phaseVI/scripts/runPhaseVI.sh -m asm-mesh -u 7 -mesh coarse` (prepare only); `cd turbinesFoam && pytest -q tests/test_blade_stage.py` (after W3.5).
- **Traces to:** spec `phasevi-run-and-compare` — "Run orchestration interface" (MODIFIED), "STL staging into run directories" (ADDED), "ASM-mesh fine run prepared", "STL staged and referenced", "Staged hash matches", "Mismatch aborts".

### W3.3 — Three-way comparison

- [x] Completed (W3b batch; a previous interrupted run left the `comparePhaseVI.py` diff uncommitted — reviewed against design §4.7/§6.4, completed and committed here) — `--asm-mesh-dir` maps the directory to model `asm-mesh`; `read_surface_stations` reads the window-filtered `postProcessing/bladeSurface/*.csv` station tables (excluding `*_nodes.csv`), merges by station id and returns `(root_dist, c_ref_n, c_ref_t)`; the shared `r_over_r_from_root_dist` applies the element r/R mapping (identical arithmetic to `spanwise_profile`; no coefficient redefined); `analyse_model(model="asm-mesh")` takes turbine metrics from the same `turbine.csv` (surface moment already in AFTAL torque) and keeps the element CSVs for `element_profiles`/`--match-eaeroth-span`; `read_surface_audit` records `staged_stl_sha256` (from `run.json`) and `surface_kernel` (from `system/fvOptions`, cosine default); `LIMITATIONS` gains the sub-grid caveat, the kernel/width confound + Gaussian ablation and the distribution-only framing; `definitions.surface_conversion` is recorded only when a surface model is compared so ALM/ASM-only `metrics.json` keeps its delivered definition block. Verified: three-way dry run (synthetic dirs under `$SCRATCH/tmp`) → both tables carry `alm/asm/asm-mesh`, sign gate PASS, surface rows equal an independent r/R mapping at CSV precision; missing dir → exit 1; ALM-only and two-way tables byte-identical to `6474bdc` (`d92c63d^`), `metrics.json`/`report.txt` identical except the three new limitations. `pytest -q tests/test_phasevi_compare.py tests/test_phasevi_case.py tests/test_phasevi_data.py` → `31 passed`. Commit `d92c63d`.
- **Files (modify):** `turbinesFoam/validation/phaseVI/scripts/comparePhaseVI.py`
- **Work (design §4.7, §6.4):** add `--asm-mesh-dir` and analyse the directory as model `asm-mesh`; `read_surface_stations(run_dir)` reads `postProcessing/bladeSurface/*.csv` inside the averaging window and returns `(root_dist, c_ref_n, c_ref_t)`, mapped to the five r/R stations by the existing formula (no coefficient definition redefined); turbine metrics from `turbine.csv` (the surface moment is already in AFTAL's torque, D8); one turbine-level and one spanwise table with all three models, the existing ±15 % / max(0.15, 20 %) bands and the sign gate; `metrics.json` gains `staged_stl_sha256` and the kernel selection; a missing/incomplete ASM-mesh directory fails loudly (`EXIT_MISSING_INPUT`); `LIMITATIONS` extended with the **sub-grid caveat** (cells 0.314/0.210/0.157 m vs chord 0.218–0.744 m — model form, not resolved chordwise physics), the **kernel/width confound** and its Gaussian ablation, and the distribution-only framing.
- **Acceptance:** the three-way tables are produced against the documented bands; surface rows convert with the existing definitions; missing input exits non-zero; the claim is not stronger than the evidence.
- **Verification:** `cd turbinesFoam && pytest -q tests/test_phasevi_compare.py` (after W3.5).
- **Traces to:** spec `phasevi-run-and-compare` — "Comparison inputs and merge" (MODIFIED), "Documented tolerance bands and honest claims" (MODIFIED), "Three-way comparison produced", "Surface output converted", "Missing third input fails loudly", "Sub-grid framing stated", "Kernel confound and ablation documented"; spec `blade-surface-source` — "Compare-compatible conversion".

### W3.4 — Prepared-only ASM-mesh Slurm array

- [x] Completed (W3b batch) — `scripts/slurm/asm-mesh.slurm` (85 lines) follows the `production.slurm` shape: `PHASEVI_LONG_QUEUE_AUTHORIZED=1` guard (exit 5), the Int64 module preamble, package resolved from `${PHASEVI_PKG_DIR:-${SLURM_SUBMIT_DIR:-$PWD}}`, 48 ranks / 1 node, `--time=24:00:00`, `--array=0-1`, one task per `(model, speed, mesh)`: task 0 `asm-mesh:7:coarse:H` is the D/32 measurement gate, task 1 `asm-mesh:7:fine:H` the D/48 headline, both `--restart --run`; the header documents prepared-only, the gate-before-D/48 procedure and the read-only baselines. Verified: `bash -n` clean (`sh -n` also exit 0, same as the `production.slurm` baseline); running the script without the env var → exit 5 with the prepared-only message; `sbatch --test-only` → exit 0 (`Job 11599857 ... 48 processors on nodes sdumont6287 in partition sequana_cpu`) with `squeue -j 11599857` reporting an invalid job id — the test-only run created no job; no `phaseVI-asm-mesh`/`phaseVI-prod`/`phaseVI-stage3*` entry in `squeue`; `runPhaseVI.sh -m asm-mesh ... --submit` → exit 2 pointing at this script. No submission. Commit `94c8898`.
- **Files (create):** `turbinesFoam/validation/phaseVI/scripts/slurm/asm-mesh.slurm`
- **Work (design §6.5):** same shape as `production.slurm` — `PHASEVI_LONG_QUEUE_AUTHORIZED=1` guard, module/setup preamble, package resolved from `$SLURM_SUBMIT_DIR`, one array task per `(model, speed, mesh)`: task 0 `asm-mesh:7:coarse:H` is the **D/32 measurement gate**, task 1 `asm-mesh:7:fine:H` is the headline run; 48 ranks; `--restart` from the latest written time; `--time=24:00:00` (the delta's at-most-24 h bound, stricter than the untouched 96 h `production.slurm`); the header documents that the D/32 task is executed and reviewed **before** any D/48 submission and that the script is prepared-only. The existing `phaseVI-prod`, `phaseVI-stage3` and `phaseVI-stage3-d64` arrays are read-only baselines.
- **Acceptance:** the array is prepared but never submitted by this change; wall time is bounded and restartable; no automated step submits a job.
- **Verification:** syntax/`--test-only` inspection only (no `sbatch`); confirm `squeue`-visible baselines untouched and no ASM-mesh job exists.
- **Traces to:** spec `phasevi-run-and-compare` — "Slurm job preparation" (MODIFIED), "Long-queue authorization gate" (MODIFIED), "One array task per combination", "Wall time bounded and restartable", "Preparation does not submit", "Existing arrays untouched".

### W3.5 — Phase VI case, compare and staging tests

- [x] Completed (W3c batch) — `tests/test_blade_stage.py` created (7 tests: committed defaults/sha256, run-dir layout equal to the twin's `surfaceGeometry`, stage-into-run-dir idempotence, mismatch abort before any copy, missing-source abort, unusable-metadata abort, CLI contract with the bare staged hash on stdout and exit 3); `tests/test_phasevi_case.py` extended (`BLADE_KEYS` gains `surfaceGeometry`/`kernel`, three-twin stripped-render equality across the in-memory renders and the committed files, `test_asm_mesh_selection` end-to-end including a sandboxed prepare-only `runPhaseVI.sh -m asm-mesh` that stages the STL and writes `run.json`, `test_stage_matrix` asserts the prepared `asm-mesh` stage with `executes false` and only `stage0` executing, `test_generated_case_is_current` compares the committed `fvOptions.ASM-MESH` to the renderer and runs `--check`); `tests/test_phasevi_compare.py` extended (`test_surface_csv_schema_matches_writer` pins the fixture constants against the real `bladeSurfaceSource.C` `stationFile_`/`nodeFile_` headers; `test_main_three_way_surface_merge` builds a synthetic `bladeSurface` station table plus a `*_nodes.csv` the reader must ignore, asserts all three models in both tables and the sign gate, and checks the surface rows against an independent r/R + interpolation oracle; `test_main_three_way_missing_surface_input` covers a missing dir and a turbine-only incomplete dir → `EXIT_MISSING_INPUT`). Verified: `cd turbinesFoam && $PY -m pytest -q tests/test_blade_stage.py tests/test_phasevi_case.py tests/test_phasevi_compare.py tests/test_phasevi_data.py` → **42 passed in 4.67s** (7/16/9/10); `generate_case.py --check` exit 0. Commit `00f60d4`.
- **Files (create):** `turbinesFoam/tests/test_blade_stage.py`
- **Files (modify):** `turbinesFoam/tests/test_phasevi_case.py`, `turbinesFoam/tests/test_phasevi_compare.py`
- **Work (design §8.3):** extend `test_twins_differ_only_in_blade_keys` (three twins; `BLADE_KEYS` gains `surfaceGeometry`/kernel keys; stripped renders and committed files identical; `fvOptions.ASM-MESH` carries `surfaceGeometry` in both blades); `test_asm_mesh_selection` (`--select 7 coarse asm-mesh` accepted, unconfigured model rejected, run id `asm-mesh-U7-coarse`); `test_stage_matrix` (new prepared stage present, `executes false`, only `stage0` executes); `test_generated_case_is_current` for the committed ASM-MESH twin; `test_blade_stage.py` (stages into `constant/triSurface/`, reports the committed sha256, aborts on mismatch/missing source); extend `test_phasevi_compare.py` with a three-way synthetic dry merge including a `bladeSurface` CSV, the r/R conversion, a missing-directory non-zero exit, and the sign gate over three models.
- **Acceptance:** pure-Python and CI-safe; the tooling contracts (selection, staging, three-way merge) are pinned.
- **Verification:** `cd turbinesFoam && pytest -q tests/test_phasevi_case.py tests/test_phasevi_data.py tests/test_phasevi_compare.py tests/test_blade_stage.py`; `cd turbinesFoam && python3 validation/phaseVI/tools/generate_case.py --check`.
- **Traces to:** design §8.3; spec `phasevi-run-and-compare` (comparison/selection/staging scenarios), spec `phasevi-validation-case` (model selection and renderer scenarios).

### W3.6 — Phase VI docs, changelog and W3 gate

- [x] Completed (W3c batch) — `validation/phaseVI/README.md` gains the three-model variant table, the formulation being implemented (the paper's chord-line blade ASM extended to an imported surface — explicitly **not a literal equation port**; distribution-only), the sub-grid caveat, the kernel/width confound + Gaussian ablation, the MEXICO naming resolution, the pre-registered hypothesis (expected direction — root transition/tip first, mid-span least — and approximate size at or below the spanwise band), the prepared-only arrays including the ASM-mesh D/32 gate + D/48 array, and the attribution (SAL credit, NREL citations including NREL/SR-440-6918 for S809, pinned `of-plugins` commit `26a1f46…` with the ASM patch note); the staged plan and comparison sections document `asm-mesh`/`--asm-mesh-dir`. Root `README.md` documents the mesh-backed variant and the `phaseVI_blade` pure-Python geometry component plus the three-model Phase VI package. Root `CHANGELOG.md` gains one entry per S2 work unit (W1 distributor, W2 geometry component, W3 ASM-mesh variant) in the `Files:`/`Problem:`/`Fix:` format. Verified: `generate_case.py --check` exit 0; `runPhaseVI.sh -m asm-mesh -u 7 -mesh coarse` (prepare-only, OpenFOAM v2506) exit 0 staging sha256 `77def499…`; focused suite 42 passed. Commit `a901c3c`. **This closes W3.**
- **Files (modify):** `turbinesFoam/validation/phaseVI/README.md`, root `README.md`, root `CHANGELOG.md`
- **Work (design §6.6):**
  - `validation/phaseVI/README.md`: the three models; the formulation being implemented (the paper's chord-line blade ASM extended to an imported surface — explicitly **not a literal equation port**); the **sub-grid caveat**; the **kernel/width confound** and the Gaussian ablation (ablation, not a model); the MEXICO naming resolution; the prepared-only arrays (no submission); the **pre-registered hypothesis** (expected direction and approximate size of the geometry effect, before the campaign); attribution (SAL adaptation credit, NREL citations including NREL/SR-440-6918 for the S809 profile, pinned `of-plugins` commit with the ASM patch note).
  - Root `README.md`: the ASM-mesh variant and the imported-surface geometry component.
  - Root `CHANGELOG.md`: one entry per work unit under `## [Unreleased]` in the repository's `Files:` / `Problem:` / `Fix:` format.
- **Acceptance:** the claim is limited to trend, stall onset and agreement within the documented band; no agreement better than the band is promised a priori; docs are updated; no job is submitted.
- **Verification:** `cd turbinesFoam && python3 validation/phaseVI/tools/generate_case.py --check`; `cd turbinesFoam && sh validation/phaseVI/scripts/runPhaseVI.sh -m asm-mesh -u 7 -mesh coarse` (prepare-only rehearsal, no `--run`/`--submit`); docs review.
- **Traces to:** spec `phasevi-validation-case` — "Case package documentation" (MODIFIED); spec `phasevi-run-and-compare` — "Documented tolerance bands and honest claims", "Pre-registered hypothesis", "Limitation statement present"; spec `phasevi-data-provenance` — "Source attribution and provenance pinning".

---

## W4 — Performance measurement gate (conditional hardening)

Reference: design §3 D6 (instrumentation), §8.4, §9 W4, §6.5. Spec:
`blade-surface-source` — "Bounded distribution and performance measurement".

### W4.1 — Per-`addSup` instrumentation

- [x] Completed (W4 batch) — `bladeSurfaceSource.{H,C}`: `logDistribution_` (`lookupOrDefault("logDistribution", true)`) plus `lastCandidateTotal_`/`lastSeconds_` and a `distributionFile_`; `distribute()` times the call with `std::chrono::steady_clock`, counts the candidate entries per node, reduces the candidate total (`sumOp<label>`) and per-node maximum (`maxOp<label>`) across ranks, emits one `Info` line on the master rank (`Blade surface distribution '<owner>.surface': nodes N, candidates C, mean C/N, max M, seconds S`) and appends one row to `postProcessing/bladeSurface/<owner>.surface_distribution.csv` (`time,nodes,candidates,mean_candidates,max_candidates,seconds`). The counters are observational: the distribution math is untouched and the default distribution result is unchanged. Commit `4452fed`. |
- **Files (modify):** `turbinesFoam/src/fvOptions/bladeSurface/bladeSurfaceSource.{H,C}`
- **Work (design §3 D6, §8.4):** after each `distribute()`, count the node count, total candidate entries, mean/max candidates per node and the `addSup` wall seconds (`clockTime`/`std::chrono`); emit one `Info` line on master and an optional CSV row when `logDistribution` is true. No model default changes.
- **Acceptance:** the line reports nodes, candidates and seconds; the candidate count is far below `nNodes × N_local cells` (bounded-query evidence).
- **Verification:** `cd turbinesFoam && ./Allwmake`; `cd turbinesFoam && pytest -q tests/test_blade_surface.py` (after W4.2).
- **Traces to:** spec `blade-surface-source` — "Bounded distribution and performance measurement", "Candidate set is bounded", "Measurement output present".

### W4.2 — Instrumentation test and regression gate

- [x] Completed (W4 batch) — `tests/test_blade_surface.py` gains `test_instrumentation_line` (regex-pinned `Info` line + CSV schema, candidate count far below `N_NODES × N_LOCAL_CELLS` and within the 5³ support stencil, partition-of-unity total re-checked, default run never instrumented) and the constants/helpers (`DISTRIBUTION_RE`, `DISTRIBUTION_COLUMNS`, `N_LOCAL_CELLS`, `_read_distribution`). The existing W1 partition-of-unity and MPI tests now run instrumented unchanged. Commit `4452fed`. |
- **Files (modify):** `turbinesFoam/tests/test_blade_surface.py`
- **Work (design §8.4):** add `test_instrumentation_line` pinning the line format and asserting candidate counts are far below a full local-cell scan; re-run the W1 partition-of-unity and MPI tests instrumented. No separate parser is added.
- **Acceptance:** instrumentation is observable and does not alter the distribution totals.
- **Verification:** `cd turbinesFoam && pytest -q tests/test_blade_surface.py::test_instrumentation_line tests/test_blade_surface.py`; `cd turbinesFoam && pytest -q` (full suite unchanged); `ldd -r` clean.
- **Traces to:** design §8.4; spec `blade-surface-source` — "Measurement output present".

### W4.3 — Prepared-only D/32 measurement setup

- [x] Completed (W4 batch) — `scripts/slurm/asm-mesh.slurm` header and `validation/phaseVI/README.md` document task 0 (`asm-mesh:7:coarse:H`) as the D/32 **performance** measurement gate, the instrumentation source (`logDistribution`, the `Info` line and the `_distribution.csv` schema) and the recorded decision procedure (proceed / harden the query / restrict the campaign, the scope choice with the user), with the measurement executed only under explicit authorization. The array stays prepared-only: no `sbatch` was run, `squeue` has no ASM-mesh job, the read-only baselines are untouched, and the sub-grid caveat + kernel/width confound framing are unchanged. Commit `fc136b4`. |
- **Files (modify):** `turbinesFoam/validation/phaseVI/scripts/slurm/asm-mesh.slurm` (task-0 documentation), `turbinesFoam/validation/phaseVI/README.md`
- **Work (design §6.5, §8.4):** document that task 0 (`asm-mesh:7:coarse:H`) is the **D/32 measurement gate** and record the gate decision procedure (proceed / harden the query / restrict the campaign — the campaign-scope choice stays with the user, design §14 Q2). The array remains prepared-only and **must not be submitted** without explicit authorization; the gate decision must be recorded before any D/48 preparation.
- **Acceptance:** the measurement setup is prepared and no job has been submitted; the run is framed as a **performance** gate only — the **sub-grid caveat** stands (D/32 cells 0.314 m vs chord 0.218–0.744 m; no resolved chordwise physics claim) and the kernel/width confound framing is unchanged.
- **Verification:** script/README review; confirm no submission (`squeue` has no ASM-mesh job; baselines untouched).
- **Traces to:** spec `blade-surface-source` — "Measurement is prepared-only"; spec `phasevi-run-and-compare` — "Long-queue authorization gate", "Slurm job preparation".

### W4.4 — Conditional candidate-query hardening (only if the gate demands it)

- [ ] **Conditional — NOT triggered.** No D/32 measurement evidence exists (the measurement is prepared-only and was not executed), so the gate cannot demand hardening. W4.4 stays open and conditional; if a future authorized measurement exceeds the practical per-step budget, the uniform-bin query would be replaced/extended by a mesh-tree/stencil candidate query with the default distribution unchanged and no model default changed by a measurement result.
- **Files (modify):** `turbinesFoam/src/fvOptions/bladeSurface/bladeSurfaceSampler.{H,C}` (candidate query only, if triggered)
- **Work (design §3 D6 alternatives, §9 W4):** if the measured D/32 numbers exceed the practical per-step budget, replace/extend the uniform-bin query with a mesh-tree/stencil candidate query; the default distribution stays unchanged and **no measurement result may change model defaults**. If the gate passes, close this task as "not needed" with the recorded numbers.
- **Acceptance:** after hardening, the same partition-of-unity and MPI totals hold and W1's integration tests pass; the W4 rollback leaves W1 distribution unchanged.
- **Verification:** `cd turbinesFoam && pytest -q tests/test_blade_surface.py`; instrumented run numbers reviewed against the W4.3 budget.
- **Traces to:** spec `blade-surface-source` — "Candidate set is bounded"; design §9 W4 (conditional hardening), §12 risk 4.

---

## Non-goals (honest scoping)

- **No surface-sampled BEM**: the surface does not sample per-node inflow or recompute BEM loads; the element BEM chain, chord-averaged inflow, dynamic stall, added mass and end effects remain as delivered (proposal §Out of Scope; spec `blade-surface-source` "Distribution-only model").
- **No no-mesh ASM changes**: `actuatorSurfaceElement` stays the reference variant; the new kernel option lives on the surface distributor only.
- **No S3 / preCICE / adapter / `fsiOmega` / `modules/*` changes**: the contract gains a second rotating implementation, nothing more (spec `surface-sampling-contract` "Seam only").
- **No MEXICO geometry or validation**: `openspec/changes/mexico-validation/**` is untouched; `phaseVI_blade` is rotor-qualified and one STL serves both identical Phase VI blades.
- **No mesh ladder, wall resolution, root-loss model, or CFTAL/VAWT support.**
- **No HPC execution**: the prepared ASM-mesh array and the D/32 measurement are never submitted by this change; queued ALM/ASM arrays are read-only baselines.
- **No resolved-chordwise-physics claim**: at D/32–D/64 the imported surface is sub-grid; the three-way comparison tests **model form** (how the load is distributed) and the Gaussian ablation separates geometry from the kernel/width confound.
- **Acceptance semantics** (design §14 Q4) remain reported-comparison with engineering-only merge criteria; no band adherence is promised a priori.

---

## Cross-cutting verification gates (recap)

| Gate | Command | Guarded by |
|------|---------|-----------|
| Build exit 0 + link clean | `cd turbinesFoam && ./Allwmake`; `ldd -r $FOAM_USER_LIBBIN/libturbinesFoam.so` | W1.5, W1.8, W4.2 |
| Full pytest suite unchanged (ALM/no-mesh ASM byte-identical) | `cd turbinesFoam && pytest -q` | W1.8, W2.5, W3.5, W4.2 |
| New C++ integration tests: partition of unity / no-double-count / surface moment / lockstep / MPI | `cd turbinesFoam && pytest -q tests/test_blade_surface.py` | W1.7, W4.2 |
| Nacelle byte-comparable regression (S1 behavior preserved by the base extraction) | `cd turbinesFoam && pytest -q tests/test_nacelle.py` + `postProcessing/nacelle/*.csv` diff | W1.2, W1.8 |
| Pure-Python geometry determinism (`--check` byte-identical, non-destructive, no gmsh) | `cd turbinesFoam/geometry && python3 src/makeGeometry.py --check --component phaseVI_blade` | W2.3, W2.5 |
| Phase VI tooling acceptance (`--select` / runner staging / `--check`; no submission) | `case_config.py --select 7 coarse asm-mesh`; `runPhaseVI.sh -m asm-mesh -u 7 -mesh coarse` (prepare only); `generate_case.py --check` | W3.1, W3.2, W3.5, W3.6 |
| Three-way comparison (bands + sign gate, surface conversion) | `cd turbinesFoam && pytest -q tests/test_phasevi_compare.py` | W3.3, W3.5 |
| Prepared-only Slurm array (never submitted without explicit authorization) | `asm-mesh.slurm` guard `PHASEVI_LONG_QUEUE_AUTHORIZED=1`; no `sbatch` in this change | W3.4, W4.3 |
| Instrumentation bounded-query evidence | `cd turbinesFoam && pytest -q tests/test_blade_surface.py::test_instrumentation_line` | W4.1, W4.2 |

Rollback (proposal §Rollback): remove `surfaceGeometry` (and optional kernel keys)
from a blade subdict to restore the no-mesh ASM without recompiling; `git revert`
the W1–W4 units (each independently revertable) restores prior code, `Make/files`
and the element/source paths, removes the geometry data (W2), the twin/staging/
compare/array additions (W3) and the instrumentation (W4). The queued
`phaseVI-prod` / `phaseVI-stage3` / `phaseVI-stage3-d64` arrays are read-only and
untouched.
