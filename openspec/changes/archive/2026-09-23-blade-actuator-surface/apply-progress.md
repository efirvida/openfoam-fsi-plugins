# Apply Progress: blade-actuator-surface (S2)

Cumulative progress artifact for the `blade-actuator-surface` change.
Store: OpenSpec files in this directory + Engram mirror
(`sdd/blade-actuator-surface/apply-progress`).

## Batch W1a — W1.1, W1.2, W1.5

- **Date**: 2026-09-21
- **Mode**: Standard (`strict_tdd: false` — tests required, no strict
  RED-GREEN ritual)
- **Delivery**: `single-pr` with the pre-authorized S1 `size:exception`
  (tasks.md Review Workload Forecast; chain strategy `size-exception`)
- **Base commit**: `d4496ae`
- **Result**: W1.1 and W1.2 complete; W1.5 complete for this batch scope with
  the two `bladeSurface/*.C` registrations deferred to W1b. All required
  checks green, no failures.

### Task status

| Task | Status | Evidence |
|------|--------|----------|
| W1.1 Element suppression key and frame accessors | ✅ Complete | `projectElementForce_` protected bool, `lookupOrDefault("projectElementForce", true)` in `read()` after `writePerf_`; only the two `applyForceField` call sites guarded; `chordDirection()`/`spanDirection()` added. `./Allwmake` exit 0; regression tests unchanged. Commit `5d1acad`. |
| W1.2 Extract `surfaceSamplerBase` and re-base the nacelle sampler | ✅ Complete | `surfaceSamplerBase.{H,C,I.H}` created with the generic assets incl. the `candidates == nullptr` S1 loop byte-for-byte; nacelle re-based keeping its force model, static frame and CSV. Serial + parallel nacelle CSVs and `forceIntegral` outputs byte-identical to the S1 baseline; `test_nacelle.py`/`test_libs.py` 8 passed. Commit `5f357c8`. |
| W1.5 `Make/files` registration and link gate | ✅ Complete (batch scope) | `fvOptions/nacelleSurface/surfaceSamplerBase.C` registered after the nacelle lines. `./Allwmake` exit 0; `ldd -r` no undefined symbols, `libsurfMesh.so` resolved. The `fvOptions/bladeSurface/bladeSurfaceSampler.C` and `bladeSurfaceSource.C` entries are deferred to W1b because those files are created there; registering them now would fail the build. Commit `5f357c8`. |

### Work Unit Evidence

| Evidence | W1.1 | W1.2 + W1.5 |
|----------|------|-------------|
| Focused test command and exact result | `cd turbinesFoam && python3 -m pytest -q tests/test_asm.py tests/test_al.py` → 11 passed (run together with `test_aftal.py`, `test_aftal_asm.py`), 1 pre-existing warning | `cd turbinesFoam && python3 -m pytest -q tests/test_nacelle.py tests/test_libs.py` → 8 passed in 16.08 s |
| Runtime harness command/scenario and exact result | `./Allwmake` exit 0; the same command builds the element into `libturbinesFoam.so` and the existing ALM/no-mesh ASM cases run unchanged through the pytest suite | `cd turbinesFoam/tests/nacelleSurface && ./Allclean && ./Allrun` (serial) and `./Allclean && ./Allrun -parallel`: `postProcessing/nacelle/nacelle.csv`, `nacelle_nodes.csv` and `postProcessing/forceIntegral/*/volFieldValue.dat` byte-identical to the S1 baseline (`cmp`, `diff -r`); values `fx = 0.0402`, `cd = 2.01` on both paths |
| Rollback boundary | Revert `5d1acad`: `actuatorLineElement.{H,C}` only — removes the key, the guards and the accessors; no other file depends on them yet | Revert `5f357c8`: `surfaceSamplerBase.{H,C,I.H}` removed, `nacelleSurfaceSampler.{H,C,I.H}` and `nacelleSurfaceSource.{H,C}` back to the S1 implementation, `Make/files` line removed; nacelle behavior returns to the S1 code path |

### Commands and observed results

1. **Baseline at HEAD `d4496ae`** (before edits were built):
   `cd turbinesFoam && ./Allwmake` → `ALLWMAKE_EXIT=0`.
2. **Baseline capture**: `cd turbinesFoam/tests/nacelleSurface && ./Allclean && ./Allrun`
   → serial `nacelle.csv` sha256 `5f220fc983d5b610b589ba81949268aaeaef6bdb2ac6a78167df8d1258226e4b`,
   `nacelle_nodes.csv` sha256 `a9868626aa35a6f48be608c187821af1561542c4e8840a411a51fd4c33894fc0`;
   `./Allclean && ./Allrun -parallel` → identical sha256 values.
   Baselines copied to `/scratch/leahk/eduardo.donestevez/tmp/w1a/baseline/{serial,parallel}/`.
3. **Post-refactor build**: `cd turbinesFoam && ./Allwmake` → exit 0, no `error:` lines,
   no warnings attributable to the changed files (only the pre-existing
   `NamedEnum` / `autoPtr::set` deprecations from OpenFOAM headers and untouched sources).
4. **Link gate**: `ldd -r $FOAM_USER_LIBBIN/libturbinesFoam.so 2>&1 | grep -i undefined` → empty;
   full `ldd -r` stderr 0 lines; `libsurfMesh.so` resolved.
5. **Nacelle byte comparison after the refactor** (post outputs in
   `/scratch/leahk/eduardo.donestevez/tmp/w1a/post/`):
   - `cmp baseline/serial/nacelle.csv post/serial/nacelle.csv` → IDENTICAL
   - `cmp baseline/serial/nacelle_nodes.csv post/serial/nacelle_nodes.csv` → IDENTICAL
   - `cmp baseline/parallel/nacelle.csv post/parallel/nacelle.csv` → IDENTICAL
   - `cmp baseline/parallel/nacelle_nodes.csv post/parallel/nacelle_nodes.csv` → IDENTICAL
   - `diff -r baseline/serial/forceIntegral post/serial/forceIntegral` → IDENTICAL
   - `diff -r baseline/parallel/forceIntegral post/parallel/forceIntegral` → IDENTICAL
6. **Nacelle + libs tests**: `python3 -m pytest -q tests/test_nacelle.py tests/test_libs.py`
   → `8 passed in 16.08s`.
7. **Regression spot-checks**: `python3 -m pytest -q tests/test_asm.py tests/test_al.py
   tests/test_aftal.py tests/test_aftal_asm.py` → `11 passed, 1 warning in 165.76s`
   (warning is the pre-existing unregistered `pytest.mark.timeout` in `test_al.py`).
8. **Full suite**: `cd turbinesFoam && python3 -m pytest -q` →
   `92 passed, 3 skipped, 1 warning in 662.08s`. The 3 skips are pre-existing
   environment skips in `test_nacelle_data.py` (pinned gmsh 4.15.2 not runnable here);
   95 tests collected in total, 0 failures.

### Deviations from design / tasks

1. **W1.5 split by batch scope.** Only `surfaceSamplerBase.C` is registered in this
   batch; the two `bladeSurface/*.C` lines require the files created in W1b. The build
   and link gates for everything that exists are green.
2. **Base diagnostic text generalized.** The base prints `Surface sampler: read ...`
   and raises `Surface file ... not found` / `contains no triangles` / `The 'bodyAxis'
   entry must be non-zero`, because it serves two consumers. Nacelle observable output
   (CSVs, `forceIntegral`) is byte-identical, and `test_nacelle.py` only asserts the
   `not found` / `contains no triangles` substrings, so the S1 gates hold.
3. **Optional `geometryKey` constructor parameter.** `surfaceSamplerBase(dict, mesh,
   geometryKey = "geometry")` keeps the design's two-argument call valid while letting
   `bladeSurfaceSampler` (W1b) pass `surfaceGeometry` without dict translation.
4. **Base helpers are protected (design §4.1).** `nacelleSurfaceSource` reaches
   `distributeForce` / `cellSize` / `interpolateVelocity` through the existing
   `friend class nacelleSurfaceSource;` on `nacelleSurfaceSampler`; the W1b blade source
   will need an equivalent friend declaration.
5. **`streamwiseDirection_` moved out of `createBodyFrame`.** The base frame stays
   force-model agnostic; the nacelle subclass recomputes `axis/mag(axis)` from the same
   `bodyAxis` entry, preserving the exact floating-point streamwise coordinates.

### Files changed

| File | Action | What was done |
|------|--------|---------------|
| `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/actuatorLineElement.H` | Modified | `projectElementForce_` protected member; `chordDirection()`/`spanDirection()` accessors |
| `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/actuatorLineElement.C` | Modified | Read the key after `writePerf_`; guard the two `applyForceField` sites; accessor definitions |
| `turbinesFoam/src/fvOptions/nacelleSurface/surfaceSamplerBase.H` | Created | Generic base declaration |
| `turbinesFoam/src/fvOptions/nacelleSurface/surfaceSamplerBase.C` | Created | Geometry load/path resolution, node lists, body frame, `cellSize`, `kernel`, `interpolateVelocity`, `distributeForce` (candidate-aware) |
| `turbinesFoam/src/fvOptions/nacelleSurface/surfaceSamplerBaseI.H` | Created | Inline accessors |
| `turbinesFoam/src/fvOptions/nacelleSurface/nacelleSurfaceSampler.H` | Modified | Derives from the base; keeps the nacelle force model and static frame |
| `turbinesFoam/src/fvOptions/nacelleSurface/nacelleSurfaceSampler.C` | Modified | Keeps `readViscosity`, the force model and the streamwise coordinates; generic assets removed |
| `turbinesFoam/src/fvOptions/nacelleSurface/nacelleSurfaceSamplerI.H` | Modified | Only `forces()` and `referenceVelocity()` remain |
| `turbinesFoam/src/fvOptions/nacelleSurface/nacelleSurfaceSource.H` | Modified | Local `distributeForce` declaration removed |
| `turbinesFoam/src/fvOptions/nacelleSurface/nacelleSurfaceSource.C` | Modified | Distributes through the base helper with the `nullptr` exhaustive loop |
| `turbinesFoam/src/Make/files` | Modified | `surfaceSamplerBase.C` registered |

### Commits

| Commit | Message |
|--------|---------|
| `5d1acad` | `feat(turbinesFoam): add element strip-projection suppression key` |
| `5f357c8` | `refactor(turbinesFoam): extract shared surface sampler base` |

No `openspec/`, `odd/`, `.atl/` or PDF content is committed.

### Remaining tasks (other batches)

- **W1b**: W1.3 `bladeSurfaceSampler`, W1.4 `bladeSurfaceSource`, and the two deferred
  `Make/files` registrations (plus the W1b friend declaration for the blade source).
- **W1c**: W1.6 `actuatorLineSource`/AFTAL plumbing, W1.7 integration fixtures and
  `tests/test_blade_surface.py` (including the end-to-end `projectElementForce false`
  path), W1.8 regression gate and turbinesFoam README.
- W2–W4 remain pending.

---

## Batch W1b — W1.3, W1.4

- **Date**: 2026-09-21
- **Mode**: Standard (`strict_tdd: false` — tests required, no strict
  RED-GREEN ritual)
- **Delivery**: `single-pr` with the pre-authorized S1 `size:exception`
  (tasks.md Review Workload Forecast; chain strategy `size-exception`)
- **Base commit**: `5f357c8`
- **Result**: W1.3 and W1.4 complete, plus the two `bladeSurface/*.C`
  registrations deferred from W1a (W1.5 now fully registered). All required
  checks green. Integration tests remain W1c's scope by assignment.

### Task status

| Task | Status | Evidence |
|------|--------|----------|
| W1.3 `bladeSurfaceSampler` (rotating frame, partition, bounded candidates) | ✅ Complete | `bladeSurfaceSampler.{H,C,I.H}`: canonical STL nodes placed through the injected construction frame; LE-based station/chord association with the element frame of the assigned patch; 1-D Voronoi partition with fatal invariants (every node assigned, every element patch non-empty, patch areas = total surface area); per-rank bin-grid candidate query with the S1 axis-aligned prefilter and `max(min_i support_i, small)` bins; cosine support `2.5*h_i` / Gaussian `2*cbrt(V_i)*meshFactor*sqrt(ln 1000)`; `positions()` refreshed as `bodyToGlobal_.T() & (positionsGlobal_ - bodyOrigin_)` on every rigid transform; `rotate`/`translate`/`pitch` (SOWFA matrix, same arithmetic as the elements). `./Allwmake` exit 0, `ldd -r` clean, `nm` sampler symbols present. Commit `6789953`. |
| W1.4 `bladeSurfaceSource` (distribution, moment, CSV) | ✅ Complete | `bladeSurfaceSource.{H,C,I.H}`: plain helper (no RTS); `distribute` computes `F_node = patchAreaShare_i*elements_[patch_i].force()`, writes `forceField_[c] -= F_node*(w/V_c)` over the candidates, returns the `returnReduce` total; `moment(point)` from the global-frame node shares; per-station CSV (`time,station,root_dist,area,force_x,force_y,force_z,c_ref_n,c_ref_t,f_ref_n,f_ref_t`) and opt-in per-node CSV (`time,node,x,y,z,nx,ny,nz,fx,fy,fz,area,station,chord_fraction`) on master only; compressible node-local density path. Commit `02d18f5`. |
| W1.5 `Make/files` registration (blade lines) | ✅ Complete (W1b) | `fvOptions/bladeSurface/bladeSurfaceSampler.C` and `bladeSurfaceSource.C` registered after the nacelle lines. `./Allwmake` exit 0 (rebuilt from a removed `.so`, because wmake does not relink on a `Make/files` change alone); `ldd -r` no undefined symbols; `nm -D --defined-only` 29 `bladeSurface*` symbols. Commits `6789953` (sampler) and `02d18f5` (source). |

### Work Unit Evidence

| Evidence | W1.3 sampler | W1.4 source |
|----------|--------------|-------------|
| Focused test command and exact result | `cd turbinesFoam && python3 -m pytest -q tests/test_nacelle.py tests/test_libs.py` → `8 passed in 13.83s` at the `6789953` state (build + link + sampler symbols) | same command → `8 passed in 12.43s` at the `02d18f5` state (build + link + 29 `bladeSurface*` symbols) |
| Runtime harness command/scenario and exact result | **N/A** — no runtime boundary exists yet: the distributor is not reachable from a case until W1.6 wires `bladeSurfaceSource` into `actuatorLineSource`/AFTAL and W1.7 adds the fixtures; `tests/test_blade_surface.py` is explicitly W1c scope. The batch evidence is the build/link/symbol gate plus the unchanged nacelle regression. | **N/A** — same reason; W1c owns `test_serial_surface`, `test_station_and_node_csv`, `test_surface_moment_in_torque`, `test_parallel_total_preserved`. |
| Rollback boundary | Revert `6789953`: removes `bladeSurface/bladeSurfaceSampler.{H,C,I.H}`, the `Make/files` sampler line and the two `actuatorLineElement` accessors; no other file uses those accessors. The source commit owns the sampler, so the W1b rollback is `git revert 02d18f5 6789953` (source first) | Revert `02d18f5`: removes `bladeSurface/bladeSurfaceSource.{H,C,I.H}` and its `Make/files` line; the sampler (commit 1) stays intact and independently buildable |

### Commands and observed results

1. **Baseline at HEAD `5f357c8`**: `cd turbinesFoam && ./Allwmake` → `EXIT=0`;
   `python3 -m pytest -q tests/test_nacelle.py tests/test_libs.py` → `8 passed in 12.41s`.
2. **W1.3 build** (`6789953` state, library rebuilt from a removed `.so`):
   `cd turbinesFoam && ./Allwmake` → `ALLWMAKE_EXIT=0`, no `error:` lines, no warnings
   attributable to the new files.
3. **W1.3 link gate**: `ldd -r $FOAM_USER_LIBBIN/libturbinesFoam.so 2>&1 | grep -i undefined`
   → empty (grep exit 1); `nm -D --defined-only ... | grep -c bladeSurfaceSampler` → 19;
   `bladeSurfaceSource` symbols 0 (not yet registered).
4. **W1.3 regression**: `python3 -m pytest -q tests/test_nacelle.py tests/test_libs.py`
   → `8 passed in 13.83s`.
5. **W1.4 build** (`02d18f5` state, library rebuilt from a removed `.so`):
   `./Allwmake` → `ALLWMAKE_EXIT=0`, no `error:` lines, no warnings.
6. **W1.4 link gate**: `ldd -r` undefined → empty; `nm -D --defined-only ... | grep -ci bladeSurface`
   → `29` (19 sampler + 10 source symbols).
7. **W1.4 regression**: `python3 -m pytest -q tests/test_nacelle.py tests/test_libs.py`
   → `8 passed in 12.43s`.
8. **Intermediate misbuild caught and corrected**: the first `02d18f5`-state build had left a
   stale `libturbinesFoam.so` (wmake does not relink when only `Make/files` changes), so the
   `.so` was removed before each verification build; the reported symbol counts are from the
   relinked libraries.

### Deviations from design / tasks

1. **Sampler constructor takes the owning elements.** Design §4.1 does not show a
   constructor signature for `bladeSurfaceSampler`, but D4's station/chord association and
   the D5 pitch frame need `elements_[i].position()/chordDirection()/chordMount()/spanDirection()`.
   `bladeSurfaceSampler(dict, mesh, elements)` is therefore the signature; the source owns
   the reference and forwards it.
2. **Two new `actuatorLineElement` accessors.** `chordMount()` is required by the D4 chord
   fraction formula (`c(X) = chordMount_i - ((X - position_i) & unit(chordDirection_i))/chordLength_i`);
   `profileDict()` is required by the D7 `meshFactor` fallback chain, because AFTAL copies
   `profileData` into the per-element dictionaries only — the blade subdictionary does not
   carry it, so reading `meshFactor` from the blade's `profileData GaussianCoeffs` needs the
   element's profile dictionary. `profileDict()` is non-const because `profileData::dict()`
   is non-const (same pattern as `position()`/`rootDistance()`).
3. **`bladeSurfaceSource` constructor takes the owning blade name** and derives
   `<name> = ownerName + ".surface"` (design §4.5), and takes a non-const
   `PtrList<actuatorLineElement>&` because `force()`, `position()`, `moment()` and the
   coefficient accessors are non-const methods.
4. **`distribute` assigns the distributed total to `bladeForce`** (it does not add). The
   design's §5 flow already has `force_ += element.force()` before the call, so adding the
   patch total would double the reported blade force; assignment keeps the reported total
   equal to the applied load (D8-consistent) and is a no-op in the incompressible reference
   by partition of unity.
5. **Compressible interpretation.** In the compressible overload the element's public
   `force()` already carries `multiplyForceRho` at the element position. The distributor
   therefore recovers the per-unit-density share (`/rho_element`) and re-applies the
   node-local density, following the S1 node-local convention; the incompressible reference
   (Phase VI) has a unit ratio. Documented in the class descriptions.
6. **Bounded-query memory guard.** The bin size is `max(min_i support_i, SMALL)` as designed,
   with a guard that doubles it if the local grid would exceed 1e6 bins (pathological
   support-to-box ratio). Correctness is unchanged: the per-node support prefilter still
   removes every cell outside the node's support box.
7. **No instrumentation.** `logDistribution` and the per-`addSup` counters are deliberately
   not read/implemented; W4 owns them (design D6).
8. **`size:exception`.** The two work-unit commits are 1115 + 562 authored lines, far over
   the 400-line budget; the session strategy is the pre-authorized S1 `size:exception`
   (tasks.md Review Workload Forecast), recorded here explicitly.

### Files changed

| File | Action | What was done |
|------|--------|---------------|
| `turbinesFoam/src/fvOptions/bladeSurface/bladeSurfaceSampler.H` | Created | Rotating-frame sampler declaration, D4-D7 invariants and body-frame contract |
| `turbinesFoam/src/fvOptions/bladeSurface/bladeSurfaceSampler.C` | Created | Construction-frame placement, station/chord association, Voronoi partition, bin-grid candidates, kernel distribution, rigid transforms |
| `turbinesFoam/src/fvOptions/bladeSurface/bladeSurfaceSamplerI.H` | Created | Inline accessors |
| `turbinesFoam/src/fvOptions/bladeSurface/bladeSurfaceSource.H` | Created | Distributor declaration, unit convention, CSV schemas |
| `turbinesFoam/src/fvOptions/bladeSurface/bladeSurfaceSource.C` | Created | `distribute` (Eq. 18, S1 sign), `moment`, per-station/per-node CSV, compressible density path |
| `turbinesFoam/src/fvOptions/bladeSurface/bladeSurfaceSourceI.H` | Created | Inline `sampler()`/`active()` |
| `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/actuatorLineElement.H` | Modified | `chordMount()` and `profileDict()` accessors |
| `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/actuatorLineElement.C` | Modified | Accessor definitions |
| `turbinesFoam/src/Make/files` | Modified | `bladeSurfaceSampler.C` and `bladeSurfaceSource.C` registered after the nacelle lines |

### Commits

| Commit | Message |
|--------|---------|
| `6789953` | `feat(turbinesFoam): add blade surface sampler with rotating frame and bounded candidates` |
| `02d18f5` | `feat(turbinesFoam): add blade surface force distributor with moment and CSV` |

No `openspec/`, `odd/`, `.atl/` or PDF content is committed.

### Remaining tasks (W1c and later)

- **W1c**: W1.6 `actuatorLineSource`/AFTAL plumbing (surface construction, `projectElementForce`
  injection, transform forwarding, moment replacement, AFTAL frame injection), W1.7 integration
  fixtures and `tests/test_blade_surface.py` (partition invariants, rotation lockstep, surface
  moment in torque, MPI total, Gaussian conservation, STL failure paths), W1.8 regression gate
  and turbinesFoam README.
- W2–W4 remain pending.

---

## Batch W1c1 — W1.6

- **Date**: 2026-09-21
- **Mode**: Standard (`strict_tdd: false` — tests required, no strict
  RED-GREEN ritual)
- **Delivery**: `single-pr` with the pre-authorized S1 `size:exception`
  (tasks.md Review Workload Forecast; chain strategy `size-exception`)
- **Base commit**: `02d18f5`
- **Result**: W1.6 complete. Build and link gates green with no new warnings;
  the ALM/no-mesh ASM regression suites are unchanged. The surface-enabled
  runtime path is exercised end-to-end by W1.7 (next batch) by assignment;
  this batch verified the wiring by the build/link gate, a static key-name
  trace, and the unchanged no-surface runtime.

### Task status

| Task | Status | Evidence |
|------|--------|----------|
| W1.6 `actuatorLineSource` and AFTAL plumbing | ✅ Complete | `read()` stores `surfaceGeometry_` (`fileName::null` sentinel); `createElements()` plumbs a user `projectElementForce` and overrides it to `false` when a surface is configured; the source owns an `autoPtr<bladeSurfaceSource>` constructed after the element loop and calls `distribute()` after it in both momentum overloads; `rotate`/`translate` forward to the surface, `pitch` (both overloads) forwards the rigid root-frame rotation, `setSpeed`/`scaleVelocity`/`setOmega` leave the geometry untouched; `moment()` returns the surface node moment when active; AFTAL `createBlades()` injects `surfaceOrigin`/`surfaceSpanDirection` (outward root→tip)/`surfaceChordDirection` after cone/azimuth only when `surfaceGeometry` is present; `bladeSurfaceSource` gained the three D5 forwarding methods. Commit `6e6719d`. |

### Work Unit Evidence

| Evidence | W1.6 |
|----------|------|
| Focused test command and exact result | `cd turbinesFoam && python3 -m pytest -q tests/test_aftal.py tests/test_aftal_asm.py tests/test_asm.py tests/test_al.py` → `11 passed, 1 warning in 164.05s` (the warning is the pre-existing unregistered `pytest.mark.timeout` in `test_al.py`) |
| Runtime harness command/scenario and exact result | The existing solver-driven ALM/no-mesh ASM cases re-ran through the suites above after rebuilding `libturbinesFoam.so`: without `surfaceGeometry`, `surface_.valid()` is false, no key is injected, and `addSup`/`moment`/transform behavior is unchanged (suite assertions). The surface-enabled runtime boundary does not exist in this batch — `tests/bladeSurface/**` and `tests/bladeSurfaceAFTAL/**` are W1.7 scope — so construction is covered by the build/link gate plus the key-name trace (AFTAL injects `surfaceOrigin`/`surfaceSpanDirection`/`surfaceChordDirection`; the sampler reads exactly those keys) |
| Rollback boundary | `git revert 6e6719d`: restores `actuatorLineSource.{H,C}` and `axialFlowTurbineALSource.C` to the pre-plumbing state and removes the three `bladeSurfaceSource` forwarders; the W1b sampler/source/distributor and `Make/files` registrations stay intact and independently buildable |

### Commands and observed results

1. **Build**: `cd turbinesFoam && ./Allwmake` → `ALLWMAKE_EXIT=0`, 0 `error:` lines. A forced
   recompile of the three changed `.C` files produced zero warnings from `actuatorLineSource.C`
   and `bladeSurfaceSource.C`; `axialFlowTurbineALSource.C`'s only warnings are the pre-existing
   `autoPtr::set` deprecations at `.C:441`/`.C:529`, untouched by this batch.
2. **Link gate**: `ldd -r $FOAM_USER_LIBBIN/libturbinesFoam.so 2>&1 | grep -i undefined`
   → empty (0 undefined lines; `ldd` exit 0).
3. **Regression (required)**: `cd turbinesFoam && python3 -m pytest -q tests/test_aftal.py
   tests/test_aftal_asm.py tests/test_asm.py tests/test_al.py` → `11 passed, 1 warning in
   164.05s`.
4. **Regression (nacelle/libs)**: `cd turbinesFoam && python3 -m pytest -q tests/test_nacelle.py
   tests/test_libs.py` → `8 passed in 12.22s`.

### Deviations from design / tasks

1. **`bladeSurfaceSource` gained three forwarding methods.** D5 specifies
   `surface_->rotate(...)`, `surface_->translate(...)` and `surface_->pitch(radians)`, but the
   W1.4 class exposed only a const `sampler()` accessor, so the lockstep was unreachable without
   extending a file outside W1.6's declared list. The three one-line forwarders were added to
   `bladeSurfaceSource.H`/`bladeSurfaceSourceI.H` (purely additive; no behavior change); this is
   the only file-scope deviation.
2. **`projectElementForce` presence semantics.** The key reaches an element dict when the user
   set it in the blade subdict (pass-through, per the MODIFIED requirement) OR when a surface is
   configured (forced `false`). It is never added when neither holds, keeping the element default
   `true` and the no-mesh behavior byte-identical.
3. **`pitch(radians, chordFraction)` forwards the rigid root-frame rotation.** The surface has no
   per-chord-fraction mount (D5 documents the rigid approximation); the `chordFraction` argument
   drives the elements only.
4. **AFTAL degeneracy guards.** The injection fatals on a zero root→tip point difference or a
   zero reference chord (e.g. single-row `elementData`) instead of injecting NaN into the
   sampler; valid geometry is unaffected.
5. **`size:exception`.** The W1.6 work-unit commit is 206 authored lines; the cumulative W1 is
   far over the 400-line budget and the session strategy is the pre-authorized S1
   `size:exception` (tasks.md Review Workload Forecast), recorded here explicitly.

### Files changed

| File | Action | What was done |
|------|--------|---------------|
| `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineSource.H` | Modified | `surfaceGeometry_` + `autoPtr<bladeSurfaceSource> surface_` members; explicit `autoPtr.H`/`bladeSurfaceSource.H` includes |
| `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineSource.C` | Modified | `read()` stores the path; `createElements()` plumbing/injection; distributor construction; `distribute()` after both element loops; transform forwarding; surface moment |
| `turbinesFoam/src/fvOptions/axialFlowTurbineALSource/axialFlowTurbineALSource.C` | Modified | `createBlades()` injects `surfaceOrigin`/`surfaceSpanDirection`/`surfaceChordDirection` after cone/azimuth when `surfaceGeometry` is present |
| `turbinesFoam/src/fvOptions/bladeSurface/bladeSurfaceSource.H` | Modified | Forwarding method declarations (D5) |
| `turbinesFoam/src/fvOptions/bladeSurface/bladeSurfaceSourceI.H` | Modified | Inline forwarding definitions |

### Commits

| Commit | Message |
|--------|---------|
| `6e6719d` | `feat(turbinesFoam): wire the blade surface source into actuatorLineSource and AFTAL` |

No `openspec/`, `odd/`, `.atl/` or PDF content is committed.

### Remaining tasks (W1c2 and later)

- **W1c2**: W1.7 integration fixtures (`tests/bladeSurface/**`, `tests/bladeSurfaceAFTAL/**`,
  `tests/conftest.py`) and `tests/test_blade_surface.py` (partition invariants, rotation lockstep,
  surface moment in torque, MPI total, Gaussian conservation, STL failure paths, the end-to-end
  `projectElementForce false` path), then W1.8 regression gate and the turbinesFoam README.
- W2–W4 remain pending.

---

## Batch W1c2a — W1.7 (fixtures + first five tests)

- **Date**: 2026-09-21
- **Mode**: Standard (`strict_tdd: false` — tests required, no strict
  RED-GREEN ritual)
- **Delivery**: `single-pr` with the pre-authorized S1 `size:exception`
  (tasks.md Review Workload Forecast; chain strategy `size-exception`)
- **Base commit**: `6e6719d`
- **Result**: W1.7 fixtures and the first five integration tests complete
  (W1c2b owns the remaining five tests, the README and the task checkbox).
  This was the first runtime execution of the blade surface path: no
  implementation defect was found; the partition of unity is exact and the
  D8 surface moment reaches the turbine torque as designed.

### Task status

| Task | Status | Evidence |
|------|--------|----------|
| W1.7 (W1c2a scope) Integration fixtures and base tests | ✅ Complete (batch scope) | `tests/bladeSurface/**` (26³ 0.1 m mesh, uniform inflow, one-cylinder-element standalone blade, two-triangle plate STL, `system/fvOptions` default + `.surface` cosine + `.surface.gaussian`, `forceIntegral`), `tests/bladeSurfaceAFTAL/**` (one blade, two geometry rows → one element, no hub/tower, `writeNodePerf true`, `rho 1.0`, multi-triangle plate at the element station), `conftest.py` `SOLVER_DRIVEN` updated; five tests green. Commit `648e21a`. Remaining five tests are W1c2b. |

### Work Unit Evidence

| Evidence | W1c2a |
|----------|-------|
| Focused test command and exact result | `cd turbinesFoam && python3 -m pytest -q tests/test_blade_surface.py` → `5 passed in 4.73s` (`test_serial_surface`, `test_default_path_projects_strips`, `test_suppressed_element_still_reports`, `test_station_and_node_csv`, `test_partition_invariants_from_csv`) |
| Runtime harness command/scenario and exact result | Fixtures run end-to-end through their own `./Allrun` in throwaway copies: standalone `./Allrun` (default), `./Allrun -surface`, `./Allrun -gaussian` and AFTAL `./Allrun` all exit 0. Surface run: `volIntegrate(force.blade)` at t = 0.1 is `(-2.200000e-02, 0, 0)` = minus the station CSV patch force exactly; the element CSV total equals the patch total; the surface run's first element row is byte-identical to the default run's first row. Default run: integral `-2.199522e-02` = 0.999783 × element total (the delivered strip projection's discrete truncation; support unclipped in this fixture). Gaussian run: integral `-2.198965e-02` = 0.99953 × patch total. AFTAL run: `turbine.csv` `ct = -0.299527` at t = 0.001 reconstructs to the surface node moment (`Σ X_i × F_i` about the rotor axis = `-4.28739`), confirming D8 end-to-end |
| Rollback boundary | Revert `648e21a`: removes `tests/bladeSurface/**`, `tests/bladeSurfaceAFTAL/**`, `tests/test_blade_surface.py` and the `conftest.py` `SOLVER_DRIVEN` entry; no production source, library or case behavior changes |

### Recovery verification (interrupted run)

The orchestrator reported this batch interrupted. On re-entry the committed
state (`648e21a`) was already complete — fixtures, tests, `tasks.md` note and
the Engram mirror (observation **#149**, topic
`sdd/blade-actuator-surface/apply-progress`) — with no partial file left and
no implementation defect to fix. The batch was re-verified from a fresh shell
and the results below supersede the original run's timing:

- `cd turbinesFoam && python3 -m pytest -q tests/test_blade_surface.py`
  → `5 passed in 5.10s` (exit 0).
- `cd turbinesFoam && python3 -m pytest -q tests/test_nacelle.py tests/test_libs.py`
  → `8 passed in 13.30s` (exit 0).
- Working tree clean of tracked changes after the runs; no generated artifacts
  under `tests/bladeSurface` / `tests/bladeSurfaceAFTAL`; the installed
  `libturbinesFoam.so` (2026-09-21 15:46) is newer than the newest W1 source
  (15:45:32), so no rebuild was needed.

### Commands and observed results

1. **Focused tests**: `cd turbinesFoam && python3 -m pytest -q tests/test_blade_surface.py`
   → `5 passed in 4.73s`.
2. **Regression (required)**: `cd turbinesFoam && python3 -m pytest -q tests/test_nacelle.py
   tests/test_libs.py` → `8 passed in 16.42s` (unchanged).
3. **Manual smoke runs** (throwaway copies under the session temp dir, not committed):
   standalone default/surface/gaussian and AFTAL `./Allrun` → all `EXIT=0`.
4. **Surface partition of unity** (smoke, `-surface`): station CSV t = 0.1 force
   `(0.022, 0, 0)`; `forceIntegral` t = 0.1 `(-2.200000e-02, 0, 0)`; t = 0.2
   `(-1.919624e-02, 1.4e-10, 0)` vs patch `(0.0191962, ...)` — exact to the CSV
   write precision.
5. **Default path** (smoke): element force `(0.022, 0, 0)`; integral t = 0.1
   `(-2.199522e-02, 0, 0)` (ratio 0.999783, the truncated strip Gaussian); no
   `Blade surface sampler` / `Blade surface source` log lines and no
   `postProcessing/bladeSurface/` output.
6. **Gaussian ablation** (smoke): integral t = 0.1 `(-2.198965e-02, 0, 0)` vs
   patch `(0.022, ...)` (ratio 0.99953) — W1c2b owns the pinned test.
7. **AFTAL** (smoke): `turbine.csv` `0.001,7.63944,6,...,-0.299527`; 8 node rows
   per time; node `station` equals the construction station (body x is only
   equal to it at construction; rotation moves the body x) and
   `chord_fraction ∈ [0.1667, 0.6333]`.

### Deviations from design / tasks

1. **Fixture domain sized for the delivered strip projection.** The standalone
   domain is 26³ cells of 0.1 m (−0.8…1.8 m) with the plate at the centre,
   not the nacelle-like 1 × 0.6 × 0.6 m box. The element strip projection uses
   `sphereRadius = chord + eps·sqrt(ln 1000)` with `eps = 2·h·meshFactor = 0.4`
   (meshFactor default 2.0), so a smaller domain clipped the projected total by
   ~2.1 %. The larger domain keeps the strip, cosine and Gaussian supports
   unclipped; the default-path test can then assert the element total with a
   documented 1e-3 tolerance (measured 0.999783) instead of a loose 5 %.
2. **Tests run on throwaway copies.** The surface and Gaussian variants replace
   `system/fvOptions`, which is a committed file, so every test copies the case
   to `tmp_path_factory` and installs the variant through `./Allrun -surface` /
   `-gaussian`. The committed fixture is never mutated; the default variant is
   the committed `system/fvOptions`.
3. **CSV write precision.** The station/node/element CSVs and the
   `volFieldValue` dat use limited stream precision (6 significant digits in
   the CSVs), so integral-vs-CSV comparisons use `rtol 1e-5`; the analytic
   first-step force (0.022) is asserted at `rtol 1e-12`.
4. **`projectElementForce` never injected is asserted behaviourally.** The key
   is not echoed by the element, so the default-path test proves the absence by
   the non-zero field integral that equals the element total (a suppressed
   element would project zero).
5. **`size:exception`.** The work-unit commit is 1736 authored lines, far over
   the 400-line budget; the session strategy is the pre-authorized S1
   `size:exception` (tasks.md Review Workload Forecast), recorded here
   explicitly.

### Files changed

| File | Action | What was done |
|------|--------|---------------|
| `turbinesFoam/tests/bladeSurface/**` | Created | Standalone surface fixture: 26³ 0.1 m mesh, uniform inflow, one cylinder element, two-triangle plate STL, default/`-surface`/`-gaussian` `fvOptions` variants, `forceIntegral`, `Allrun`/`Allclean`/`.gitignore`, `geometry/empty.stl` |
| `turbinesFoam/tests/bladeSurfaceAFTAL/**` | Created | Minimal AFTAL fixture: one blade, two geometry rows (one element), no hub/tower, `writeNodePerf true`, `rho 1.0`, 8-triangle plate at the element station |
| `turbinesFoam/tests/test_blade_surface.py` | Created | Five solver-driven tests + shared run/read helpers; the remaining five W1c2b tests are listed at the end of the module |
| `turbinesFoam/tests/conftest.py` | Modified | `"test_blade_surface.py"` added to `SOLVER_DRIVEN` |

### Commits

| Commit | Message |
|--------|---------|
| `648e21a` | `test(turbinesFoam): add blade surface fixtures and base integration tests` |

No `openspec/`, `odd/`, `.atl/` or PDF content is committed.

### W1c2b batch (completed)

The W1c2b run was interrupted after committing but before updating this file; the orchestrator closed the bookkeeping on the committed tree.

| Task | Status | Evidence (orchestrator-verified) |
|------|--------|----------------------------------|
| W1.7 remaining five tests | ✅ Complete | `test_rotation_lockstep`, `test_surface_moment_in_torque`, `test_parallel_total_preserved`, `test_kernel_gaussian_conserves`, `test_missing_empty_corrupt_stl_aborts` committed in `c787ed2` (plus the 12-significant-digit CSV fix `c53711d`). `/scratch/leahk/eduardo.donestevez/venv/bin/python -m pytest -q tests/test_blade_surface.py` → **10 passed in 44.50s**. |
| W1.8 regression gate + docs | ✅ Complete | `turbinesFoam/README.md` (`bd450c8`); full suite → **105 passed, 1 warning in 445.52s** (previous 95 collected; +10 new tests; ALM/no-mesh paths unchanged). |

### Commits (W1c2b)

| Commit | Message |
|--------|---------|
| `c53711d` | `fix(turbinesFoam): write blade surface CSVs at 12 significant digits` |
| `c787ed2` | `test(turbinesFoam): complete the blade surface integration suite` |
| `bd450c8` | `docs(turbinesFoam): document the blade surface source` |

### Next

**W1 is complete** (W1.1–W1.8 checked; 6 commits W1a→W1c2b; full suite 105 passed). Next: **W2** — the S809 dataset + PROVENANCE (W2.1), the pure-Python `phaseVI_blade` loft (W2.2), the builder registry (W2.3), the committed STL/metadata/docs (W2.4) and the blade data tests (W2.5).

---

## Batch W2a — W2.1, W2.2

- **Date**: 2026-09-23
- **Mode**: Standard (`strict_tdd: false` — tests required, no strict
  RED-GREEN ritual)
- **Delivery**: `single-pr` with the pre-authorized S1 `size:exception`
  (tasks.md Review Workload Forecast; chain strategy `size-exception`)
- **Base commit**: `bd450c8` (the interrupted run had already committed W2.1
  as `64d9cb8`; on re-entry that commit was re-verified from the committed
  tree and not recreated, and W2.2 was completed as `98444eb`)
- **Result**: W2.1 and W2.2 complete. The extraction and both provenance
  cross-checks pass and reproduce the committed CSV byte-identically; the
  loft is byte-identical across fresh generations and matches an independent
  re-implementation of design §7.3. No required check failed.

### Task status

| Task | Status | Evidence |
|------|--------|----------|
| W2.1 Committed S809 dataset and provenance | ✅ Complete | `data/s809/s809_somers_nlr.csv` (31 upper + 30 lower, shared TE) + `PROVENANCE.md` committed. Table 2 of Somers, NREL/SR-440-6918 (PDF page index 19) extracted with PyMuPDF 1.27.2.3 from the sha256-verified local PDF; cross-check 1 (TP-500-29955 Table A-2) agrees to all published digits (31/31 + 30/30, the documented extra zero row recorded); cross-check 2 (Ramsay Table A1, 18-inch chord) is within 1 % chord outside the last 10 % of chord (max upper `0.000894` at `x/c = 0.00037`, lower `0.000906` at `x/c = 0.04223`; the documented TE thickening excluded and reported); failures abort non-zero. Re-extraction is byte-identical to the committed CSV (sha256 `861f3fe5…`). Commit `64d9cb8`. |
| W2.2 `blade_phasevi.py` pure-Python structured loft | ✅ Complete | `geometry/src/blade_phasevi.py` (490 lines): committed-input parse, closed 60-point profile, circle/S809 rule at `0.8835`/`1.0085`, §7.3 frame with `SIGMA = -1`, 25×60 = 3000 outward-wound wetted triangles, no caps, canonical writer with the per-component header, populated `radial_station`/`chord_fraction` and §4.6 hashes. Two fresh generations byte-identical (STL `77def499…`, metadata `01f75d17…`); independent §7.3 re-implementation confirms the exact triangulation, 1560 ring vertices, 120 boundary edges in two 60-edge rings at `z = 0.5083`/`5.029`, all 26 station planes, every metadata node, and `PITCH_DEG 3.0 == case.yaml turbine.pitch_deg`. Commit `98444eb`. |

### Work Unit Evidence

| Evidence | W2.1 | W2.2 |
|----------|------|------|
| Focused test command and exact result | `/scratch/leahk/eduardo.donestevez/venv/bin/python` re-running the extraction recipe against the three verified PDFs (redirected output) → all sha256 checks OK, both cross-checks PASSED, exit 0, re-extracted CSV sha256 `861f3fe5…` == committed | `python -c` invoking `blade_phasevi.build()` twice in fresh interpreters → `cmp` IDENTICAL for STL and metadata; `verify_blade.py` → ALL CHECKS PASSED (exit 0); independent `verify_w2a_independent.py` → INDEPENDENT CHECKS PASSED (exit 0) |
| Runtime harness command/scenario and exact result | **N/A** — W2.1 is a data artifact with no executable path; the extraction recipe is the harness and was re-run end-to-end | The generator itself is the runtime path: two full `build()` runs into `$SCRATCH/tmp/w2a/gen{A,B}/`, 3000 triangles, area `4.88423 m²`, `z [0.5083, 5.029]`; the manifold/metadata verifier and the independent loft re-implementation both exit 0 |
| Rollback boundary | `git revert 64d9cb8`: removes `validation/phaseVI/data/s809/` only; nothing consumes it from a committed artifact yet (W2.2 reads it at generation time; no committed STL/metadata depends on it) | `git revert 98444eb`: removes `geometry/src/blade_phasevi.py` only; nothing imports it yet (W2.3 adds the builder registry); the W2.1 dataset and the nacelle path stay intact |
| Regression command (batch) | `cd turbinesFoam && /scratch/leahk/eduardo.donestevez/venv/bin/python -m pytest -q tests/test_nacelle_data.py tests/test_phasevi_data.py` → `21 passed, 3 skipped in 1.15s`; the 3 skips are the pre-existing `test_nacelle_data.py` gmsh-environment skips (pinned gmsh 4.15.2 not runnable here). No tracked file was modified by this batch, so the result is the committed baseline. | same |

### Commands and observed results

1. **W2.1 re-verification** (extraction redirected to
   `/scratch/leahk/eduardo.donestevez/tmp/w2a/reverify/s809_reverify.csv`):
   `sha256 OK` for all three verified PDFs (`a7496aad…`, `822ee980…`,
   `9b5d151f…`); `Somers Table 2: 31 upper, 30 lower (shared TE ('1.0000',
   '.0000'))`; `TP-500 Table A-2: 31 upper, 31 lower`, `upper: 31 points, 0
   mismatches`, `lower[:-1]: 30 points, 0 mismatches`, extra trailing zero row
   confirmed as the documented erratum; `Ramsay Table A1: 223 upper, 221 lower
   measured points`; gated max deviations `0.000894` (upper) / `0.000906`
   (lower); `cross-checks PASSED`, exit 0; committed CSV sha256
   `861f3fe5bbda4d5e5d8985e47c5805bada76fc8e1b2157b944ff78d500f4af8b`.
2. **W2.2 two fresh generations** (separate interpreters, into `genA/` and
   `genB/`): `phaseVI_blade: 3000 triangles, x [-0.1061, 0.2163] y [-0.5095,
   0.1703] z [0.5083, 5.029], area 4.88423, wetted surface (no caps)`;
   STL sha256 `77def499047fe0633e57564247a0fdd1330afbf4148b707db08ec79af0a2ec27`
   and metadata sha256
   `01f75d17e2febb296a7b093f20ff011eb583de52e8f510815f876fcb8169e7dc` identical
   in both; `cmp` IDENTICAL; the same hashes as the interrupted run.
3. **Topology/manifold verifier** (`verify_blade.py`): 3000 triangles, 0
   duplicate, 0 degenerate; 4560 edges with `boundary 120; non-opposite pairs
   0; edges with >2 triangles 0`; `boundary rings: [60, 60]` at
   `z = [0.5083, 5.029]`; signed closed-shell volume `+0.151498` (outward
   normals); `radial_station` vs STL centroid z mismatches 0; all 26 station z
   planes present. `ALL CHECKS PASSED`, exit 0.
4. **Independent §7.3 re-implementation** (`verify_w2a_independent.py`, no
   import of `blade_phasevi`): triangulation mismatches (count/winding/order)
   `0`; 1560 distinct STL vertices, 0 outside the expected rings; node
   mismatches `radial_station 0, chord_fraction 0, bad area 0`;
   `chord_fraction [0.0000, 1.0000]`; `case.yaml pitch_deg: 3.0`; hashes
   recomputed independently match the metadata. `INDEPENDENT CHECKS PASSED`,
   exit 0.
5. **Batch regression**: `cd turbinesFoam && pytest -q tests/test_nacelle_data.py
   tests/test_phasevi_data.py` → `21 passed, 3 skipped in 1.15s` (exit 0).
6. **Resume hygiene**: the W2.1 commit `64d9cb8` was present and complete at
   re-entry (CSV + PROVENANCE, 167 lines, no PDF); no partial file was
   recreated; the untracked `blade_phasevi.py` was reviewed against design
   D10/§7.3, re-verified and committed unchanged.

### Deviations from design / tasks

1. **Loft triangle pattern.** Design §7.3 writes the literal pattern
   `(a,b,c)`/`(b,d,c)` annotated "(outward)". For this closed profile the
   traversal is clockwise in the generation frame (signed 2D area < 0), so the
   literal pattern produces inward normals; the implementation emits the
   reversed pair `(a,c,b)`/`(b,c,d)` to make the facet normals outward. The
   intent (fixed, outward winding) is preserved; the reason is
   documented in the module docstring and verified by the closed-shell signed
   volume (+0.151498) and the exact triangulation check.
2. **W2.1 committed before the interruption.** The interrupted run had already
   committed the dataset (`64d9cb8`); on re-entry the committed bytes were
   re-derived from the verified PDFs and byte-compared rather than rewritten.
   `tasks.md` had not been updated by the interrupted run; this batch records
   both W2.1 and W2.2 as complete.
3. **`input_sha256` canonical parameter block.** The design §4.6 defines the
   digest as "input bytes + canonical parameter block" without fixing the
   serialization; the implementation uses the committed blade bytes + S809
   bytes + `json.dumps(PARAMETERS, sort_keys=True, separators=(",", ":"))` with
   `PARAMETERS` = the cut radii, point/station counts, pitch and sigma.
4. **`PITCH_DEG` assertion.** The module declares `PITCH_DEG = 3.0` and
   documents that `tests/test_blade_data.py` (W2.5) asserts it against
   `config/case.yaml`; this batch verified the equality directly (`3.0`).
5. **`size:exception`.** W2a is 167 (W2.1) + 490 (W2.2) = 657 authored lines,
   over the 400-line budget; the session strategy is the pre-authorized S1
   `size:exception` (tasks.md Review Workload Forecast), recorded here
   explicitly.

### Files changed

| File | Action | What was done |
|------|--------|---------------|
| `turbinesFoam/validation/phaseVI/data/s809/s809_somers_nlr.csv` | Created | Committed S809 design coordinates (long CSV, source header comments) |
| `turbinesFoam/validation/phaseVI/data/s809/PROVENANCE.md` | Created | Source/PDF sha256/table/tool/date, committed CSV sha256, closure convention, both cross-checks |
| `turbinesFoam/geometry/src/blade_phasevi.py` | Created | Pure-Python structured loft, canonical writer, populated metadata |

### Commits

| Commit | Message |
|--------|---------|
| `64d9cb8` | `feat(turbinesFoam): commit the S809 profile coordinates with provenance` |
| `98444eb` | `feat(turbinesFoam): add the pure-Python phaseVI blade loft` |

No `openspec/`, `odd/`, `.atl/`, PDF or generated STL content is committed
(the generated STL/metadata are W2.4).

---

## Batch W2b — W2.3, W2.4

- **Date**: 2026-09-23
- **Mode**: Standard (`strict_tdd: false` — tests required, no strict
  RED-GREEN ritual)
- **Delivery**: `single-pr` with the pre-authorized S1 `size:exception`
  (tasks.md Review Workload Forecast; chain strategy `size-exception`)
- **Base commit**: `98444eb`
- **Result**: W2.3 and W2.4 complete. The registry routes the nacelle to the
  pinned gmsh and `phaseVI_blade` to the pure-Python loft; the committed blade
  STL/metadata are byte-identical to the W2a generations and to fresh
  regenerations, and `--check --component phaseVI_blade` is green without any
  gmsh. All required checks green, no failures.

### Task status

| Task | Status | Evidence |
|------|--------|----------|
| W2.3 Builder registry and route-aware `generate`/`check` | ✅ Complete | `Component` gains `builder` (the route string); `BUILDERS = {"nacelle": "gmsh", "phaseVI_blade": "python"}`, `COMPONENTS = tuple(BUILDERS)`, `RESERVED_COMPONENTS = ()`, `RETIRED_COMPONENTS = ("blade0", "blade1", "blade2")`; per-component `STL_HEADERS` (nacelle bytes unchanged); `build_gmsh_component` renamed + `build_blade_component` (lazy `blade_phasevi` import, header guard, no subprocess); `generate`/`check` dispatch on the route, blade regenerates into a temp dir with no gmsh lookup (`--gmsh /nonexistent/gmsh` ignored); `shutil.which("gmsh")` behind the gmsh route; CLI help/unknown/retired errors from the registry. Commit `67708d4`. |
| W2.4 Committed blade STL, metadata and geometry docs | ✅ Complete | `stl/phaseVI_blade.stl` (150 084 bytes = 84 + 50×3000) + `metadata/phaseVI_blade.json` committed, sha256 `77def499…`/`01f75d17…` identical to W2a and to two fresh in-place regenerations; metadata §4.6-complete (inputs with both CSV sha256 + `pitch_deg 3.0`, `input_sha256 7a43047d…`, 3000 nodes with `normal`/`area`/`radial_station`/`chord_fraction`, no `_reserved`); README component table/builder routes/naming resolution; PROVENANCE per-component sources (NREL/TP-500-29955 Table A-1 + committed S809 Table 2) and input hashes, blade0/1/2 retired. Commits `7c3d7e2` (artifacts + PROVENANCE) and `bbd143f` (README). |

### Work Unit Evidence

| Evidence | W2.3 | W2.4 |
|----------|------|------|
| Focused test command and exact result | `cd turbinesFoam && /scratch/leahk/eduardo.donestevez/venv/bin/python -m pytest -q tests/test_nacelle_data.py tests/test_phasevi_data.py` → `21 passed, 3 skipped in 1.28s` (committed-tree baseline; the nacelle gmsh path is untouched) | same command → same `21 passed, 3 skipped`; with `module load glu/9.0.2_gnu` → `24 passed in 4.39s` (the 3 gmsh-gated nacelle tests run) |
| Runtime harness command/scenario and exact result | `env PATH=/usr/bin:/bin python src/makeGeometry.py --check --component phaseVI_blade` → `phaseVI_blade: committed STL, metadata and PROVENANCE.md are up to date`, exit 0 (no gmsh anywhere); `--component blade0` → exit 1 retired-name error; `--component bogus` → exit 2 `available: nacelle, phaseVI_blade`; `--check --component nacelle` with pinned gmsh 4.15.2 → clean, exit 0 | two full in-place generations + `cmp` against `$SCRATCH/tmp/w2a/genA/` → both hashes stable and `BYTE_IDENTICAL_TO_W2A`; `git cat-file blob 7c3d7e2:…stl` → 150 084 bytes, sha256 `77def499…`; stale-copy checks: corrupt STL → exit 1 + `TREE_UNCHANGED`, corrupt metadata → exit 1, PROVENANCE without the input hash → exit 1 |
| Rollback boundary | `git revert 67708d4`: restores the single-route `makeGeometry.py` (nacelle only, `STL_HEADER`, `RESERVED_COMPONENTS`); the W2.4 artifacts/docs stay but are no longer reachable from the CLI; the nacelle path is byte-identical throughout | `git revert bbd143f 7c3d7e2`: removes `stl/phaseVI_blade.stl`, `metadata/phaseVI_blade.json` and the README/PROVENANCE updates; `makeGeometry.py` keeps the registry but the blade check reports missing artifacts; the S809 dataset and `blade_phasevi.py` (W2a) are untouched |

### Commands and observed results

1. **W2.3 CLI contract** (pre-commit, then re-verified on the committed tree):
   - `env PATH=/usr/bin:/bin $PY src/makeGeometry.py --check --component phaseVI_blade`
     → `phaseVI_blade: committed STL, metadata and PROVENANCE.md are up to date`,
     `input sha256: 7a43047dc0728a04fb3ea5ca9510119242e9aca390bde6895c023140500fe456`, exit 0.
   - `$PY src/makeGeometry.py --component blade0` → exit 1,
     `error: component 'blade0' was retired in S2; the blade surface component is 'phaseVI_blade' (available: nacelle, phaseVI_blade)`.
   - `$PY src/makeGeometry.py --component bogus` → exit 2,
     `error: unknown component 'bogus' (available: nacelle, phaseVI_blade)`.
   - `$PY src/makeGeometry.py --check --component phaseVI_blade --gmsh /nonexistent/gmsh`
     → same clean result: the gmsh argument is never consulted on the Python route.
2. **W2.4 generation and stability**: `$PY src/makeGeometry.py --component phaseVI_blade`
   → `phaseVI_blade: 3000 triangles, x [-0.1061, 0.2163] y [-0.5095, 0.1703] z [0.5083, 5.029], area 4.88423, wetted surface (no caps)`;
   two further in-place generations kept STL `77def499047fe0633e57564247a0fdd1330afbf4148b707db08ec79af0a2ec27`
   and metadata `01f75d17e2febb296a7b093f20ff011eb583de52e8f510815f876fcb8169e7dc`
   unchanged; `cmp` against `$SCRATCH/tmp/w2a/genA/` → `STL_IDENTICAL` + `METADATA_IDENTICAL`.
3. **Committed blobs**: `git cat-file blob 7c3d7e2:turbinesFoam/geometry/stl/phaseVI_blade.stl`
   → 150 084 bytes, sha256 `77def499…`; the metadata blob → `01f75d17…`.
   (`rtk git show <rev>:<binary>` corrupts binary output — the STL hashed to
   `b105b7aa…` through the wrapper; use `git cat-file`/redirection for binary blobs.)
4. **Non-destructive stale detection** (package-layout copy under
   `$SCRATCH/tmp/w2b2/`): corrupt blade STL → `stale STL: … (committed 758aa984…,
   regenerated 77def499…)`, exit 1, tree snapshot unchanged (`TREE_UNCHANGED`);
   corrupt metadata → `stale metadata: … (regenerated content differs)`, exit 1;
   PROVENANCE with the input hash zeroed → `stale PROVENANCE.md`, exit 1.
5. **Nacelle check with gmsh** (`module load glu/9.0.2_gnu`,
   `--gmsh /scratch/leahk/eduardo.donestevez/venv/bin/gmsh`) →
   `nacelle: committed STL, metadata and PROVENANCE.md are up to date`,
   `input sha256: e0a69771736aa3b26a11b00880ddd0acf2cf45d8782f13d56fd78ccb89d20de5`, exit 0 —
   the per-component header left the nacelle bytes unchanged.
6. **Required regression** (committed tree):
   `cd turbinesFoam && $PY -m pytest -q tests/test_nacelle_data.py tests/test_phasevi_data.py`
   → `21 passed, 3 skipped in 1.28s` (unchanged; the 3 skips are the pre-existing
   gmsh-environment skips). With `glu/9.0.2_gnu` loaded → `24 passed in 4.39s`.

### Deviations from design / tasks

1. **`RETIRED_COMPONENTS` added next to the registry.** Design D12 names only
   `RESERVED_COMPONENTS = ()`; the retired `blade0/1/2` names stay as an explicit
   policy tuple so the CLI answers them with a useful "retired in S2, use
   `phaseVI_blade`" error instead of a bare unknown-component error.
   `RESERVED_COMPONENTS` is empty exactly as designed and the README documents the
   retirement (not a deferral).
2. **Per-component `STL_HEADERS` replaces `STL_HEADER`; `Component.geo` is
   optional.** `build_blade_component` checks the builder module's own header
   against the registry before building, and converts the builder's
   `OSError`/`ValueError` into `GenerationError` so `generate`/`check` stay
   route-agnostic.
3. **`generate`/`check` read `input_sha256` from the rendered metadata** on both
   routes (identical to the recomputed `.geo` digest for the nacelle) instead of
   re-reading the gmsh source; the shared provenance gate is unchanged.
4. **Discovery for W2.5 — the blade check needs the package layout.** The blade
   inputs resolve through the *package* root
   (`turbinesFoam/validation/phaseVI/data/…`), so `--check --component phaseVI_blade`
   requires the sibling `validation/` tree: a copy of `geometry/` alone (as
   `test_nacelle_data.py`'s stale tests do) fails with a missing-input error.
   `test_check_byte_identical_without_gmsh` must run in place or copy the package
   root (or the two input directories).
5. **Discovery for W2.5 — binary verification through `rtk`.** `rtk git show`
   mangles binary output; committed STL blobs must be verified with
   `git cat-file blob` (or `git show … > file` + `sha256sum`).
6. **`size:exception`.** Authored changes: `makeGeometry.py` 212 changed lines,
   README 155, PROVENANCE 153 (~520 total; the generated 146 KB STL and 403 KB
   metadata are generated goldens excluded from the authored count). Over the
   400-line budget; the session strategy is the pre-authorized S1
   `size:exception` (tasks.md Review Workload Forecast), recorded here explicitly.

### Files changed

| File | Action | What was done |
|------|--------|---------------|
| `turbinesFoam/geometry/src/makeGeometry.py` | Modified | Builder registry (`Component.builder`, `BUILDERS`, `COMPONENTS`, `RESERVED_COMPONENTS`, `RETIRED_COMPONENTS`), per-component `STL_HEADERS`, `build_gmsh_component` / `build_blade_component`, route-aware `generate`/`check`/CLI |
| `turbinesFoam/geometry/stl/phaseVI_blade.stl` | Created | Committed canonical binary STL (3000 triangles, fixed header, recomputed normals) |
| `turbinesFoam/geometry/metadata/phaseVI_blade.json` | Created | §4.6 metadata: inputs + hashes, 3000 populated node entries, no `_reserved` |
| `turbinesFoam/geometry/PROVENANCE.md` | Modified | Per-component sources (Phase VI Table A-1 + committed S809 Table 2), generator routes, input/artefact hashes; blade0/1/2 retired; gmsh requirement scoped to the gmsh route |
| `turbinesFoam/geometry/README.md` | Modified | Component table, builder routes, naming resolution, both metadata schemas, blade consumption frame |

### Commits

| Commit | Message |
|--------|---------|
| `67708d4` | `feat(turbinesFoam): add the geometry builder registry` |
| `7c3d7e2` | `feat(turbinesFoam): commit the phaseVI blade STL, metadata and provenance` |
| `bbd143f` | `docs(turbinesFoam): document the phaseVI blade component` |

No `openspec/`, `odd/`, `.atl/`, PDF or build-artifact content is committed.

### Next (W2c)

- **W2c**: W2.5 `tests/test_blade_data.py`
  (`test_s809_provenance_complete`, `test_s809_parses_as_airfoil`,
  `test_blade_metadata_complete`, `test_stl_manifold_wetted_only`,
  `test_check_byte_identical_without_gmsh`,
  `test_builder_registry_and_retired_reservation`), the nacelle/Phase VI test
  updates (`_reserved`, README token list, deferred-blade rejection, `data/s809/`
  in the provenance-directory checks) and the W2 gate. Note deviations 4 and 5
  above for the check-copy strategy and binary blob verification.
- **W2c**: W2.5 `tests/test_blade_data.py`
  (`test_s809_provenance_complete`, `test_s809_parses_as_airfoil`,
  `test_blade_metadata_complete`, `test_stl_manifold_wetted_only`,
  `test_check_byte_identical_without_gmsh`,
  `test_builder_registry_and_retired_reservation`), the nacelle/Phase VI test
  updates (`_reserved`, README token list, deferred-blade rejection, `data/s809/`
  in the provenance-directory checks) and the W2 gate. Note deviations 4 and 5
  above for the check-copy strategy and binary blob verification.
- W3–W4 remain pending.

---

## Batch W2c — W2.5 (closes W2)

- **Date**: 2026-09-23
- **Mode**: Standard (`strict_tdd: false` — tests required, no strict
  RED-GREEN ritual)
- **Delivery**: `single-pr` with the pre-authorized S1 `size:exception`
  (tasks.md Review Workload Forecast; chain strategy `size-exception`)
- **Base commit**: `bbd143f`
- **Resume**: no partial work existed — `tests/test_blade_data.py` was absent and
  `git status` showed no test diffs; the batch ran from the committed W2b tree.
- **Result**: W2.5 complete. **W2 is complete** (W2.1–W2.5). The six pure-Python
  blade tests, the nacelle and Phase VI test updates and the W2 gate are green
  with and without a runnable gmsh; no nacelle artifact changed. No required
  check failed.

### Task status

| Task | Status | Evidence |
|------|--------|----------|
| W2.5 Blade data tests, nacelle/Phase VI updates, W2 gate | ✅ Complete | `tests/test_blade_data.py` (538 lines) with the six required tests: S809 provenance fields + recomputed CSV sha256; independent airfoil parse (31 upper/30 lower, shared TE, strict `x/c`, blunt-LE closure) agreeing with `load_s809`; blade metadata (`pitch_deg == PITCH_DEG == case.yaml`, recomputed `input_sha256`, pinned STL/metadata sha256, no `_reserved`, 3000 nodes with sig6-exact centroid `radial_station` and `chord_fraction ∈ [0,1]` spanning the chord); STL manifoldness (4440 opposed interior edges, 120 boundary edges in two 60-edge rings at 0.5083/5.029, no duplicates/degenerates, all 26 station planes); `--check` byte-identical without gmsh + non-destructive stale STL/metadata/PROVENANCE detection; registry tuples, Python-route acceptance, help/unknown/retired CLI text and the nacelle pinned-gmsh gate. Nacelle test updates (`_reserved` legacy-placeholder asserts, README naming-policy tokens, `blade0/1/2` retirement, literal byte pins) and Phase VI updates (`data/s809/` in the provenance-directory checks) complete. Commit `b567d26`. |

### Work Unit Evidence

| Evidence | W2c |
|----------|-----|
| Focused test command and exact result | `cd turbinesFoam && /scratch/leahk/eduardo.donestevez/venv/bin/python -m pytest -q tests/test_blade_data.py tests/test_nacelle_data.py tests/test_phasevi_data.py` → `28 passed, 3 skipped in 5.13s` (no gmsh; the 3 skips are the pre-existing gmsh-environment nacelle skips). With `module load glu/9.0.2_gnu` → `31 passed in 7.73s`, exit 0. |
| Runtime harness command/scenario and exact result | `cd turbinesFoam/geometry && $PY src/makeGeometry.py --check --component phaseVI_blade` → `phaseVI_blade: committed STL, metadata and PROVENANCE.md are up to date`, `input sha256: 7a43047d…`, exit 0, no gmsh. Default nacelle `--check`: without `glu` → exit 2 with the pinned-gmsh-not-runnable error + hint (environment skip); with `glu/9.0.2_gnu` → `nacelle: … up to date`, `input sha256: e0a69771…`, exit 0. Manual non-destructive gate: package-layout copy under `/scratch/leahk/eduardo.donestevez/tmp/w2c/pkg`, STL byte flipped → corrupted sha256 `758aa984…`, `--check` → exit 1 with `stale: stale STL: stl/phaseVI_blade.stl (committed 758aa984…, regenerated 77def499…)`, `TREE_UNCHANGED_COPY=True`, `TREE_UNCHANGED_COMMITTED=True`. |
| Rollback boundary | `git revert b567d26`: restores `tests/test_nacelle_data.py` and `tests/test_phasevi_data.py` and removes `tests/test_blade_data.py`; no production code, library, geometry artifact or case behavior changes (the W2a/W2b dataset, builder, registry and committed STL/metadata stay intact). |

### Commands and observed results

1. **Required tests (no gmsh)**: `cd turbinesFoam && $PY -m pytest -q
   tests/test_blade_data.py tests/test_nacelle_data.py tests/test_phasevi_data.py`
   → `28 passed, 3 skipped in 5.13s` (exit 0); the three skips are the
   pre-existing `GMSH_SKIP` environment skips in `test_nacelle_data.py`.
2. **Required tests (glu loaded)**: `module load glu/9.0.2_gnu && … pytest -q …`
   → `31 passed in 7.73s` (exit 0); the three gmsh-gated nacelle regeneration
   tests (clean check + stale STL + stale provenance) ran and passed.
3. **Blade `--check` without gmsh** (in place): exit 0, `up to date`,
   `input sha256: 7a43047dc0728a04fb3ea5ca9510119242e9aca390bde6895c023140500fe456`.
4. **Nacelle `--check` per environment**: without `glu` → exit 2 with
   `libGLU.so.1: cannot open shared object file` plus the pinned-gmsh hint;
   with `glu/9.0.2_gnu` → exit 0, `input sha256: e0a69771…`.
5. **Manual stale gate** (fresh package-layout copy, corrupted STL, snapshot
   after corruption): exit 1, the exact `stale STL` line above, both the copy
   and the committed tree byte-unchanged. The test module additionally covers
   stale metadata (`stale metadata: … (regenerated content differs)`) and stale
   PROVENANCE (`stale PROVENANCE.md: it does not record the current input
   sha256 …`) with the same non-destructiveness snapshots.
6. **Nacelle artifacts unchanged**: `git status --short` after all runs shows only
   the three test files; `tests/test_nacelle_data.py::test_committed_nacelle_bytes_are_pinned`
   passes with the PROVENANCE literals
   (`stl 18c7beef…`, `metadata f237fc40…`).

### Deviations from design / tasks

1. **Extra pinned-hash test in `test_nacelle_data.py`.** Beyond the three named
   updates, `test_committed_nacelle_bytes_are_pinned` pins the nacelle STL and
   metadata sha256 literals recorded in `geometry/PROVENANCE.md`, making the W2
   gate's “nacelle artifacts unchanged” executable rather than only observed.
2. **`_reserved` asserts kept and re-scoped.** The nacelle schema keeps the
   `_reserved` block for byte stability (README), so the bytes are unchanged and
   the assertion now documents it as the legacy S1 placeholder with explicit
   null asserts; the S2 policy is asserted on the blade side (no `_reserved` in
   `metadata/phaseVI_blade.json`, populated station/chord fields).
3. **Check-copy layout.** `test_check_byte_identical_without_gmsh` runs `--check`
   in place *and* against package-layout copies containing `geometry/` plus
   `validation/phaseVI/data/{geometry,s809}/`, because the blade route resolves
   its inputs through the package root (W2b deviation 4). Copies run with
   `PYTHONDONTWRITEBYTECODE=1` and a test-local `TMPDIR` so the tree snapshot is
   exact.
4. **Registry test asserts the nacelle gmsh gate without a live gmsh.** It passes
   `--gmsh /nonexistent/gmsh-not-installed` and expects exit 2
   (`cannot execute gmsh`), which proves the nacelle route still requires the
   pinned gmsh while the blade route ignores the flag (exit 0) — deterministic
   with or without gmsh installed.
5. **`size:exception`.** Authored changes are 616 insertions + 21 deletions = 637
   lines (`test_blade_data.py` 538 new; `test_nacelle_data.py` +50/−16;
   `test_phasevi_data.py` +28/−5), over the 400-line budget; the session
   strategy is the pre-authorized S1 `size:exception` (tasks.md Review Workload
   Forecast), recorded here explicitly.

### Files changed

| File | Action | What was done |
|------|--------|---------------|
| `turbinesFoam/tests/test_blade_data.py` | Created | Six pure-Python W2.5 tests (S809 provenance/parse, blade metadata, STL manifold/wetted, byte-identical `--check` without gmsh + non-destructive stale detection, builder registry/CLI retirement) with independent STL/CSV readers and pinned hashes |
| `turbinesFoam/tests/test_nacelle_data.py` | Modified | Legacy `_reserved` asserts; README naming-policy tokens; `blade0/1/2` retirement test; new literal byte pins for the nacelle STL/metadata |
| `turbinesFoam/tests/test_phasevi_data.py` | Modified | `data/s809/` added to the provenance-directory checks (fields, source, PDF/CSV sha256, cross-checks); no-artifacts walk unchanged |

### Commits

| Commit | Message |
|--------|---------|
| `b567d26` | `test(turbinesFoam): add blade geometry data tests and retirement assertions` |

No `openspec/`, `odd/`, `.atl/`, PDF, geometry artifact or build-artifact
content is committed. `tasks.md` marks W2.1–W2.5 `[x]`; the Engram mirror
(observation **#149**, revision 8, topic
`sdd/blade-actuator-surface/apply-progress`) is refreshed with this batch.

### Next (W3)

**W2 is complete.** Next: **W3** — the Phase VI third variant: W3.1 renderer +
`case.yaml` stage, W3.2 model selection/runner/STL staging, W3.3 three-way
comparison, W3.4 prepared-only ASM-mesh Slurm array, W3.5 case/compare/stage
tests, W3.6 docs/changelog and the W3 gate. Then W4 (instrumentation +
prepared-only measurement gate).

---

## Batch W3a — W3.1, W3.2

- **Date**: 2026-09-23
- **Mode**: Standard (`strict_tdd: false` — tests required, no strict
  RED-GREEN ritual)
- **Delivery**: `single-pr` with the pre-authorized S1 `size:exception`
  (tasks.md Review Workload Forecast; chain strategy `size-exception`)
- **Base commit**: `b567d26`
- **Resume**: the interrupted run had committed W3.1 as `e7f8dd7` and left
  W3.2 uncommitted — modifications to `scripts/runPhaseVI.sh` and
  `tools/case_config.py` plus the untracked `tools/stage_blade_stl.py`. On
  re-entry the committed W3.1 state was re-verified from the committed tree
  (no partial file, no defect) and the W3.2 work was reviewed against design
  §6.2/§6.3, verified end-to-end in the OpenFOAM v2506 environment and
  committed unchanged as `6474bdc`; nothing was recreated.
- **Result**: W3.1 and W3.2 complete. The ASM-MESH twin is byte-checked
  against the renderer; the prepare-only `asm-mesh` run stages the committed
  STL with a matching sha256 and refuses `--submit`; no job was submitted and
  no `sbatch` was run. No required check failed.

### Task status

| Task | Status | Evidence |
|------|--------|----------|
| W3.1 Third twin renderer and `case.yaml` stage | ✅ Complete | `render_fv_options(..., surface_geometry=None, surface_kernel=None)` adds `surfaceGeometry "constant/triSurface/phaseVI_blade.stl";` at the 16-space element-key indentation and `kernel gaussian;` only for the ablation (cosine renders no key); `projectElementForce` is never rendered; `blade2` keeps `$blade1;` + `azimuthalOffset 180`; `outputs()` always emits `case/system/fvOptions.ASM-MESH`; CLI `--surface-kernel {cosine,gaussian}` (default cosine); `case.yaml` gains the prepared `asm-mesh` stage (`queue: sequana_cpu_long`, `models: [asm-mesh]`, `meshes: [coarse, fine]`, `speeds: [7]`, `executes: false`). Committed by the interrupted run as `e7f8dd7`; re-verified here. |
| W3.2 Model selection, runner and STL staging | ✅ Complete | `tools/stage_blade_stl.py` (145 lines) checks the committed STL against `metadata.stl_sha256`, creates `constant/triSurface/`, copies `phaseVI_blade.stl`, re-checks the copy and echoes the staged hash (exit 3 before any copy on a missing source or mismatch); `case_config.py` gains `MODEL_CHOICES = ("alm", "asm", "asm-mesh")` and the three-model error text; `runPhaseVI.sh` accepts `-m asm-mesh` (twin `fvOptions.ASM-MESH`, run id `asm-mesh-U<speed>-<mesh>`, `--nchordwise` ASM-family-only, `--submit` refused exit 2 pointing at `scripts/slurm/asm-mesh.slurm`), stages through the helper before the mesh link and records `staged_stl_sha256` in `run.json` for `asm-mesh` only. Commit `6474bdc`. |

### Work Unit Evidence

| Evidence | W3.1 | W3.2 |
|----------|------|------|
| Focused test command and exact result | `cd turbinesFoam && /scratch/leahk/eduardo.donestevez/venv/bin/python validation/phaseVI/tools/generate_case.py --check` → exit 0, no stale files; `… -m pytest -q tests/test_phasevi_case.py` → `15 passed in 0.77s` (unchanged; the three-twin extension is W3.5) | `cd turbinesFoam && sh validation/phaseVI/scripts/runPhaseVI.sh -m asm-mesh -u 7 -mesh coarse` → exit 0, prepared `runs/asm-mesh-U7-coarse/`; `--submit` → exit 2 with the prepared-only message; `stage_blade_stl.py` corrupt STL → exit 3 (no stale copy), missing source → exit 3, happy path → exit 0 with the hash on stdout |
| Runtime harness command/scenario and exact result | The renderer is the runtime path: committed twin vs `fvOptions.ASM` = exactly the `+ surfaceGeometry` line; vs `fvOptions.ALM` = `elementType` + `nChordwise` + `surfaceGeometry`; `blade2` carries `$blade1;` + `azimuthalOffset 180`; default render byte-matches the committed twin (only the case-relative polars include differs under a temp `--case-dir`); gaussian render adds exactly `kernel gaussian;` | `runPhaseVI.sh -m asm-mesh -u 7 -mesh coarse` under OpenFOAM v2506 → exit 0; `cmp runs/asm-mesh-U7-coarse/constant/triSurface/phaseVI_blade.stl geometry/stl/phaseVI_blade.stl` identical, sha256 `77def499…` on the staged copy, `run.json` `staged_stl_sha256` `77def499…`, `system/fvOptions` == `system/fvOptions.ASM-MESH`, `surfaceGeometry` case-relative and resolving inside the run dir; `--select 7 coarse asm-mesh` accepted (bogus → exit 2), `-m alm --nchordwise 3` rejected while `-m asm-mesh --nchordwise 3` prepared `asm-mesh-U7-coarse-nc3`; no `sbatch` |
| Rollback boundary | `git revert e7f8dd7`: removes `case/system/fvOptions.ASM-MESH`, the renderer/CLI additions and the `case.yaml` `asm-mesh` stage; `-m alm`/`-m asm` and `--check` behavior are unchanged (the twin was additive) | `git revert 6474bdc`: removes `tools/stage_blade_stl.py` and the `case_config.py`/`runPhaseVI.sh` changes; `-m alm`/`-m asm` and every existing refusal keep their exact behavior; `runs/` is gitignored, so prepared directories are not part of the revert |

### Commands and observed results

1. **W3.1 renderer check**: `cd turbinesFoam && $PY validation/phaseVI/tools/generate_case.py --check`
   → exit 0; on a copy of `case/` with a corrupted `system/fvOptions.ASM-MESH`
   the same command reports `stale generated file: system/fvOptions.ASM-MESH`
   and exits 1, proving the twin is covered on every run.
2. **Twin byte differences**: `diff fvOptions.ASM fvOptions.ASM-MESH` → one added line
   (`surfaceGeometry "constant/triSurface/phaseVI_blade.stl";`, 16-space indent);
   `diff fvOptions.ALM fvOptions.ASM-MESH` → `elementType` + `nChordwise` +
   `surfaceGeometry` only; `grep kernel` on the committed twin → none (cosine
   default); `blade2` block = `$blade1;` + `writePerf false;` +
   `writeElementPerf false;` + `azimuthalOffset 180;`.
3. **Gaussian ablation**: `generate_case.py --mesh coarse --speed 7 --case-dir <temp>
   --surface-kernel gaussian` → exit 0, `surfaceGeometry` + `kernel gaussian;`
   at the same indentation; the default render into another temp dir has no
   `kernel` key and matches the committed twin except the case-relative polars
   `#include` path.
4. **Prepare-only** (OpenFOAM v2506, `FOAM_USER_LIBBIN` = the Int64 user lib):
   `sh validation/phaseVI/scripts/runPhaseVI.sh -m asm-mesh -u 7 -mesh coarse`
   → `Preparing asm-mesh-U7-coarse`, `Installed fvOptions.ASM-MESH as system/fvOptions`,
   `staged …/constant/triSurface/phaseVI_blade.stl (sha256 77def499…)`,
   `Staged blade STL sha256 77def499…`, `Wrote run.json`, exit 0.
5. **Staged identity**: staged sha256
   `77def499047fe0633e57564247a0fdd1330afbf4148b707db08ec79af0a2ec27` == committed
   `geometry/stl/phaseVI_blade.stl` == `metadata.stl_sha256`; `cmp` staged vs
   committed → identical; `cmp system/fvOptions system/fvOptions.ASM-MESH` →
   identical; `run.json` carries `"staged_stl_sha256": "77def499…"`.
6. **Submit refusal**: `sh validation/phaseVI/scripts/runPhaseVI.sh -m asm-mesh
   -u 7 -mesh coarse --submit` → `ERROR: --submit is not available for -m
   asm-mesh; … scripts/slurm/asm-mesh.slurm …`, exit 2. The only `sbatch`
   calls in the runner are inside the refused `--submit` branch; no job was
   submitted and no `sbatch` was executed by this batch.
7. **Staging failure paths** (temp dir, helper invoked directly): corrupted STL
   (`dd` byte flip) → `blade STL sha256 mismatch … is 037d1038…, metadata
   records 77def499…`, exit 3, no copy created; missing source → `committed
   blade STL not found`, exit 3; happy path → exit 0, bare hash on stdout.
8. **Selection**: `case_config.py --select 7 coarse asm-mesh` → exit 0 with the
   kinematics JSON (`model: "asm-mesh"`, `tsr 5.408`); `--select 7 coarse asm`
   → exit 0 unchanged; `--select 7 coarse bogus` → exit 2,
   `unsupported model 'bogus'; choose from ['alm', 'asm', 'asm-mesh']`.
9. **Family guards**: `-m alm --nchordwise 3` → exit 2 (`ASM-family-only`);
   `-m asm-mesh --nchordwise 3` → exit 0, prepared `asm-mesh-U7-coarse-nc3`
   (run directory removed after the check).
10. **Required tests**: `cd turbinesFoam && $PY -m pytest -q tests/test_phasevi_case.py`
    → `15 passed in 0.77s` (exit 0). `py_compile` on the two Python files and
    `sh -n` on the runner → clean.
11. **Environment note** (resume hygiene): the module's PATH/LD_LIBRARY_PATH point
    at a dead Int32 platform dir, so the Int64 bin/lib dirs and
    `lib/sys-openmpi` were prepended explicitly (AGENTS.md recipe) before the
    prepare-only run.

### Deviations from design / tasks

1. **W3.1 was committed by the interrupted run.** On re-entry the commit was
   present, complete and consistent with design §6.1/§4.2; it was re-verified
   from the committed tree rather than rewritten or recreated.
2. **W3.2's uncommitted files were complete as left.** The review against
   design §6.2/§6.3 found no missing requirement (helper exit codes, paths,
   `run.json` field, refusals, family guard), so the files were committed
   unchanged; the batch's value is the end-to-end verification, the task
   bookkeeping and the Engram mirror.
3. **`python3` inside the runner.** The staging call and the `run.json` heredoc
   use the runner's existing `python3` convention (the venv's `python3` here);
   no absolute interpreter path is baked into a committed script.
4. **`--submit` ordering.** For `-m asm-mesh --submit --nchordwise N` the
   pre-existing Stage 3 refusal fires first; both paths exit 2, so the
   documented refusal code holds.
5. **`size:exception`.** W3a authored 393 insertions + 19 deletions = 412
   changed lines across the two work-unit commits (`e7f8dd7` 195/7,
   `6474bdc` 198/12); excluding the 132-line generated twin golden it is 280
   authored lines, and including it the batch is 12 lines over the 400-line
   budget. The session strategy is the pre-authorized S1 `size:exception`
   (tasks.md Review Workload Forecast), recorded here explicitly.

### Files changed

| File | Action | What was done |
|------|--------|---------------|
| `turbinesFoam/validation/phaseVI/config/case.yaml` | Modified | Prepared `asm-mesh` stage (sequana_cpu_long, coarse+fine, 7 m/s, `executes: false`) |
| `turbinesFoam/validation/phaseVI/tools/generate_case.py` | Modified | `surface_geometry`/`surface_kernel` rendering, `SURFACE_GEOMETRY`/`SURFACE_KERNELS`, ASM-MESH output on every run, `--surface-kernel` CLI |
| `turbinesFoam/validation/phaseVI/case/system/fvOptions.ASM-MESH` | Created | Committed third twin (generated; `--check`-covered) |
| `turbinesFoam/validation/phaseVI/tools/stage_blade_stl.py` | Created | sha256-gated STL staging helper (exit 3 on mismatch/missing; echoes the staged hash) |
| `turbinesFoam/validation/phaseVI/tools/case_config.py` | Modified | `MODEL_CHOICES` whitelist and three-model error text for `--select` |
| `turbinesFoam/validation/phaseVI/scripts/runPhaseVI.sh` | Modified | `-m asm-mesh` (twin mapping, run id, ASM-family `--nchordwise`, `--submit` refusal), staging call and `run.json` `staged_stl_sha256` |

### Commits

| Commit | Message |
|--------|---------|
| `e7f8dd7` | `feat(validation): add the ASM-MESH Phase VI twin and stage` (interrupted run; re-verified) |
| `6474bdc` | `feat(validation): select, stage and prepare the asm-mesh variant` |

No `openspec/`, `odd/`, `.atl/`, PDF, run-directory or build-artifact content
is committed. `tasks.md` marks W3.1 and W3.2 `[x]`; the Engram mirror
(observation **#149**, topic `sdd/blade-actuator-surface/apply-progress`,
upserted by the `engram save` CLI because the MCP save was session-ambiguous)
is refreshed with this batch.

### Next (W3b)

**W3.1 and W3.2 are complete.** Next: **W3b** — W3.3 three-way comparison
(`--asm-mesh-dir`, `bladeSurface` conversion, `LIMITATIONS`), W3.4 the
prepared-only `scripts/slurm/asm-mesh.slurm` array, W3.5 the case/compare/stage
tests (including the three-twin extension and `tests/test_blade_stage.py`),
W3.6 docs/changelog and the W3 gate. Then W4 (instrumentation + prepared-only
measurement gate).

---

## Batch W3b — W3.3, W3.4

- **Date**: 2026-09-23
- **Mode**: Standard (`strict_tdd: false` — tests required, no strict
  RED-GREEN ritual)
- **Delivery**: `single-pr` with the pre-authorized S1 `size:exception`
  (tasks.md Review Workload Forecast; chain strategy `size-exception`)
- **Base commit**: `6474bdc`
- **Resume**: the interrupted run had left the `comparePhaseVI.py` diff
  uncommitted (165 insertions / 24 deletions) and no `asm-mesh.slurm`. On
  re-entry the diff was reviewed against design §4.7/§6.4 and the
  `phasevi-run-and-compare` delta, one comment was corrected (blade2 has
  `writePerf false`, so the Phase VI twin writes station output for blade1
  only), and one refinement was made (the `definitions.surface_conversion`
  entry is emitted only when a surface model is compared, so ALM/ASM-only
  `metrics.json` keeps its delivered definition block). W3.4 was created from
  scratch. Nothing was recreated or overwritten.
- **Result**: W3.3 and W3.4 complete. The three-way comparison accepts the
  surface variant, converts it with the existing r/R mapping, keeps the bands
  and sign gate, and leaves the ALM/ASM tables byte-identical to `6474bdc`;
  the ASM-mesh array is prepared-only, guarded, 24 h-bounded and never
  submitted. No required check failed.

### Task status

| Task | Status | Evidence |
|------|--------|----------|
| W3.3 Three-way comparison | ✅ Complete | `--asm-mesh-dir` → model `asm-mesh`; `read_surface_stations` reads the window-filtered `postProcessing/bladeSurface/*.csv` station tables (excluding `*_nodes.csv`), merges by station id and returns `(root_dist, c_ref_n, c_ref_t)`; the shared `r_over_r_from_root_dist` applies the element mapping (identical arithmetic; no coefficient redefined); `analyse_model(model="asm-mesh")` takes turbine metrics from `turbine.csv` and keeps the element CSVs for `element_profiles`/`--match-eaeroth-span`; `read_surface_audit` records `staged_stl_sha256` + `surface_kernel`; `LIMITATIONS` gains the sub-grid, kernel-confound/ablation and distribution-only entries. Dry run: three models in both tables, sign gate PASS, independent r/R conversion match, missing dir exit 1, ALM/ASM tables byte-identical to `d92c63d^`. Commit `d92c63d`. |
| W3.4 Prepared-only ASM-mesh Slurm array | ✅ Complete | `scripts/slurm/asm-mesh.slurm` (85 lines), `production.slurm` shape: guard exit 5, Int64 module preamble, `${PHASEVI_PKG_DIR:-${SLURM_SUBMIT_DIR:-$PWD}}` package resolution, 48 ranks / 1 node, `--time=24:00:00`, `--array=0-1`; task 0 `asm-mesh:7:coarse:H` D/32 measurement gate, task 1 `asm-mesh:7:fine:H` D/48 headline, both `--restart --run`; header documents prepared-only and gate-before-D/48. `bash -n` clean; guard without env → exit 5; `sbatch --test-only` exit 0 with `squeue -j` invalid (no job created); no phaseVI job queued; `runPhaseVI.sh --submit` → exit 2 pointing here. Commit `94c8898`. |

### Work Unit Evidence

| Evidence | W3.3 | W3.4 |
|----------|------|------|
| Focused test command and exact result | `cd turbinesFoam && $PY -m pytest -q tests/test_phasevi_compare.py` → `6 passed in 0.29s`; with the adjacent modules `tests/test_phasevi_compare.py tests/test_phasevi_case.py tests/test_phasevi_data.py` → `31 passed in 0.99s` | `bash -n scripts/slurm/asm-mesh.slurm` → clean (`sh -n` also exit 0, same as the `production.slurm` baseline); `sbatch --test-only` → exit 0, simulated job 11599857; `squeue -j 11599857` → `Invalid job id` |
| Runtime harness command/scenario and exact result | Three-way CLI dry run on synthetic ALM/ASM/ASM-MESH dirs (`$SCRATCH/tmp/w3b/dryrun_three_way.py`, 29 checks all PASS): exit 0, sign gate PASS, turbine/spanwise tables carry all three models (9/15 rows), `metrics.json` audit fields (`staged_stl_sha256` `77def499…`, `surface_kernel gaussian`, `surface_stations 5`), surface rows equal an independent r/R mapping at CSV precision, missing dir → exit 1, ALM-only and two-way tables byte-identical to `6474bdc` (`metrics.json`/`report.txt` identical except the three new limitations). The real prepared dir (`runs/asm-mesh-U7-coarse`, never run) fails loudly: exit 1, `missing input for asm-mesh: …/postProcessing/turbines/0/turbine.csv` | Running the script without `PHASEVI_LONG_QUEUE_AUTHORIZED` → exit 5, `ERROR: long-queue authorization not granted; this file is prepared only.`; `runPhaseVI.sh -m asm-mesh -u 7 -mesh coarse --submit` → exit 2, `the ASM-mesh runs are prepared through scripts/slurm/asm-mesh.slurm, which is prepared-only…`; `squeue -n phaseVI-prod,phaseVI-stage3,phaseVI-stage3-d64,phaseVI-asm-mesh` → empty (nothing submitted/cancelled/modified) |
| Rollback boundary | `git revert d92c63d`: removes `--asm-mesh-dir`, the surface readers/audit, the model dispatch and the new limitations/definition; ALM/ASM comparison returns to the delivered `spanwise_profile` path (tables byte-identical either way) | `git revert 94c8898`: removes `scripts/slurm/asm-mesh.slurm` only; the runner's `--submit` refusal message then points at a non-existent path, but no behavior or submission changes |

### Commands and observed results

1. **Required tests (committed tree)**: `cd turbinesFoam && $PY -m pytest -q
   tests/test_phasevi_compare.py` → `6 passed in 0.29s` (exit 0); the wider
   pure-Python set → `31 passed in 0.99s`.
2. **`--help`**: `/scratch/leahk/eduardo.donestevez/venv/bin/python
   validation/phaseVI/scripts/comparePhaseVI.py --help` → exit 0, the usage
   shows `--asm-mesh-dir ASM_MESH_DIR` and the docstring documents the surface
   conversion.
3. **Three-way dry run** (synthetic placeholder dirs, not results): `rc=0`,
   `sign gate PASS`; `turbine_comparison.csv` models `['alm','asm','asm-mesh']`
   (9 rows), `spanwise_comparison.csv` same models (15 rows), every row carries
   a band verdict and populated deltas; `metrics.json`
   `models.asm-mesh.metrics` has `staged_stl_sha256`
   `77def499047fe0633e57564247a0fdd1330afbf4148b707db08ec79af0a2ec27`,
   `surface_kernel gaussian`, `surface_stations 5`, and
   `definitions.surface_conversion`; the three new limitations are present.
4. **Surface conversion**: for every asm-mesh row the reported
   `c_ref_n`/`c_ref_t` equals an independently computed
   `root_cutout/radius + root_dist*(1 - root_cutout/radius)` interpolation at
   the five r/R stations (rel. tol. 1e-5, the CSV write precision).
5. **Unchanged existing outputs**: ALM-only and two-way runs against the
   pre-change tool (`d92c63d^` = `6474bdc`, extracted with `git cat-file blob`)
   → `turbine_comparison.csv`, `spanwise_comparison.csv` and `sign_gate.json`
   byte-identical; `metrics.json` and `report.txt` differ only by the three
   new limitation entries (spec/design §6.4 require the extended statement);
   the two-way `alm`/`asm` rows inside the three-way tables equal the two-way
   table rows exactly.
6. **Prepared run dir**: `comparePhaseVI.py --asm-mesh-dir
   runs/asm-mesh-U7-coarse` (no `postProcessing/`, never executed) → exit 1,
   `missing input for asm-mesh: …/postProcessing/turbines/0/turbine.csv` — the
   missing-third-input contract on the real W3a artifact.
7. **W3.4 syntax and guard**: `bash -n` clean; `sh -n` exit 0; `bash
   scripts/slurm/asm-mesh.slurm` (no env) → exit 5 with the prepared-only
   message (the guard is the first statement, so nothing else ran).
8. **`sbatch --test-only`** (syntax/resource validation only): exit 0,
   `Job 11599857 to start at 2026-09-29T18:32:01 using 48 processors on nodes
   sdumont6287 in partition sequana_cpu`; `squeue -j 11599857` → `Invalid job
   id specified` (the test-only run created no job); `squeue -n
   phaseVI-prod,phaseVI-stage3,phaseVI-stage3-d64,phaseVI-asm-mesh` → empty.
   No `sbatch` without `--test-only` was executed and no job was submitted.
9. **`--submit` refusal**: `sh scripts/runPhaseVI.sh -m asm-mesh -u 7 -mesh
   coarse --submit` → exit 2 pointing at `scripts/slurm/asm-mesh.slurm`.

### Deviations from design / tasks

1. **W3.3's uncommitted diff was left by the interrupted run.** It was
   reviewed against design §4.7/§6.4 and the delta spec, not recreated. Two
   edits were made: an inaccurate comment was corrected (the Phase VI twin
   writes station output for blade1 only, `writePerf false` on blade2 — the
   merge-by-station-id code stays as defensive behavior for any multi-blade
   output) and `definitions.surface_conversion` became conditional on a
   surface model being present.
2. **`read_surface_stations` takes the averaging window.** The design shows
   `read_surface_stations(run_dir)`; the window filter needs `start`/`end`/
   `allow_short`, exactly like `spanwise_profile`, so the signature is
   `(run_dir, start, end, allow_short)`. The returned tuples are
   `(root_dist, c_ref_n, c_ref_t)` as designed.
3. **`surface_stations` metric added.** The design names only
   `staged_stl_sha256` and the kernel for `metrics.json`; the surface station
   count is recorded next to the existing `element_profiles` for auditability.
4. **ALM/ASM `report.txt`/`metrics.json` gain the three limitations.** This is
   required by design §6.4 and the delta ("Limitation statement present",
   "Sub-grid framing stated"); the metric values, tables, bands and sign gate
   are byte-identical to the pre-change tool.
5. **`-p sequana_cpu` for the ASM-mesh array.** `case.yaml` records the stage
   queue as `sequana_cpu_long`, but all three existing prepared arrays
   (`production`, `stage3`, `stage3-d64`) submit to the `sequana_cpu`
   partition; the new script matches them (the `queue` key is stage metadata).
6. **`size:exception`.** W3.3 is 165 insertions + 24 deletions = 189 changed
   lines and W3.4 is 85 new lines (274 authored this batch); cumulative W3 is
   over the 400-line budget, and the session strategy is the pre-authorized S1
   `size:exception` (tasks.md Review Workload Forecast), recorded here
   explicitly.

### Files changed

| File | Action | What was done |
|------|--------|---------------|
| `turbinesFoam/validation/phaseVI/scripts/comparePhaseVI.py` | Modified | `--asm-mesh-dir`, `read_surface_stations`, `read_surface_audit`, shared `r_over_r_from_root_dist`, surface model dispatch, extended `LIMITATIONS`, conditional `surface_conversion` definition |
| `turbinesFoam/validation/phaseVI/scripts/slurm/asm-mesh.slurm` | Created | Prepared-only 2-task array (D/32 measurement gate + D/48 headline), guarded, 24 h, restartable, 48 ranks |

### Commits

| Commit | Message |
|--------|---------|
| `d92c63d` | `feat(validation): compare the ASM-MESH variant three ways` |
| `94c8898` | `feat(validation): prepare the asm-mesh Slurm array` |

No `openspec/`, `odd/`, `.atl/`, PDF, run-directory or build-artifact content
is committed. `tasks.md` marks W3.3 and W3.4 `[x]`; the Engram mirror
(observation **#149**, revision 10, topic
`sdd/blade-actuator-surface/apply-progress`, upserted by the `engram save` CLI
because the MCP save was session-ambiguous) is refreshed with this batch.

### Next (W3c)

**W3.3 and W3.4 are complete.** Next: **W3c** — W3.5 the case/compare/stage
tests (`tests/test_blade_stage.py`; the three-twin extension, `test_asm_mesh_selection`,
`test_stage_matrix`, the committed ASM-MESH twin check, and the three-way
synthetic merge with the r/R conversion, missing-directory exit and three-model
sign gate) and W3.6 docs/changelog plus the W3 gate. Then W4 (instrumentation +
prepared-only measurement gate).

---

## Batch W3c — W3.5, W3.6 (closes W3)

- **Date**: 2026-09-23
- **Mode**: Standard (`strict_tdd: false` — tests required, no strict
  RED-GREEN ritual)
- **Delivery**: `single-pr` with the pre-authorized S1 `size:exception`
  (tasks.md Review Workload Forecast; chain strategy `size-exception`)
- **Base commit**: `94c8898`
- **Resume**: the interrupted run had left partial work uncommitted —
  `tests/test_blade_stage.py` (untracked, 141 lines) and the
  `test_phasevi_case.py` / `test_phasevi_compare.py` diffs (+207/−14 and
  +193/−14). On re-entry the three files were read and run against design §8.3
  and the W3.5 task text: every required contract was already present and the
  focused suite was green, so the tests were **not recreated** — they were
  verified, and the batch continued with the still-missing W3.6 docs. No partial
  file was rewritten.
- **Result**: W3.5 and W3.6 complete. **W3 is complete** (W3.1–W3.6). The
  staging/twin/selection/three-way tests are green; the case README, root README
  and root CHANGELOG document the three-way plan; the W3 gate
  (`generate_case.py --check`, focused suite, prepare-only rehearsal) is green
  and no job was submitted. No required check failed.

### Task status

| Task | Status | Evidence |
|------|--------|----------|
| W3.5 Phase VI case, compare and staging tests | ✅ Complete | `tests/test_blade_stage.py` created (7 tests: committed defaults/sha256, run-dir layout equal to the twin's `surfaceGeometry`, stage-into-run-dir idempotence, mismatch abort before any copy, missing-source abort, unusable-metadata abort, CLI contract with the bare staged hash on stdout and exit 3). `tests/test_phasevi_case.py` extended: `BLADE_KEYS` gains `surfaceGeometry`/`kernel`; `test_twins_differ_only_in_blade_keys` compares the stripped in-memory renders of ALM/ASM/ASM-MESH/Gaussian and the committed ALM/ASM/ASM-MESH files, asserting `surfaceGeometry` in `blade1` and the `$blade1;` propagation to `blade2`; `test_asm_mesh_selection` runs `--select 7 coarse asm-mesh` (kinematics JSON), rejects a bogus model, asserts the `--submit` refusal (exit 2) and then prepares `runs/asm-mesh-U7-coarse` in a sandbox (stubbed environment, pre-created shared mesh, `python3` shim) and checks the staged STL bytes, `run.json` `staged_stl_sha256`, and the installed twin vs the committed one modulo the polars include; `test_stage_matrix` asserts the `asm-mesh` stage (`sequana_cpu_long`, `models ["asm-mesh"]`, coarse+fine, speed 7, `executes false`) with only `stage0` executing; `test_generated_case_is_current` pins the committed `fvOptions.ASM-MESH` to the renderer and runs `--check`. `tests/test_phasevi_compare.py` extended: `test_surface_csv_schema_matches_writer` pins `SURFACE_STATION_COLUMNS`/`SURFACE_NODE_COLUMNS` against the real `bladeSurfaceSource.C` `stationFile_`/`nodeFile_` headers; `test_main_three_way_surface_merge` writes a synthetic `bladeSurface` station table plus a `*_nodes.csv` the reader must ignore, asserts all three models in the turbine/spanwise tables and the three-model sign gate, and checks each surface row against an independent r/R + linear-interpolation oracle; `test_main_three_way_missing_surface_input` covers a missing directory and a turbine-only incomplete directory → `EXIT_MISSING_INPUT`. Commit `00f60d4`. |
| W3.6 Phase VI docs, changelog and W3 gate | ✅ Complete | `validation/phaseVI/README.md`: three-model variant table; formulation (paper chord-line blade ASM extended to an imported surface — explicitly not a literal equation port; distribution-only); sub-grid caveat; kernel/width confound + Gaussian ablation; MEXICO naming resolution; pre-registered hypothesis; prepared-only arrays incl. the ASM-mesh D/32 gate + D/48 array; staged plan/comparison document `asm-mesh`/`--asm-mesh-dir`; attribution (SAL credit, NREL citations incl. NREL/SR-440-6918, pinned `of-plugins` commit `26a1f46…` with the ASM patch note). Root `README.md`: the mesh-backed variant and the pure-Python `phaseVI_blade` geometry component, plus the three-model Phase VI package. Root `CHANGELOG.md`: one entry per S2 work unit (W1 distributor, W2 geometry component, W3 ASM-mesh variant) under `## [Unreleased]` in the `Files:`/`Problem:`/`Fix:` format. Commit `a901c3c`. |

### Work Unit Evidence

| Evidence | W3.5 (tests) | W3.6 (docs + W3 gate) |
|----------|--------------|------------------------|
| Focused test command and exact result | `cd turbinesFoam && /scratch/leahk/eduardo.donestevez/venv/bin/python -m pytest -q tests/test_blade_stage.py tests/test_phasevi_case.py tests/test_phasevi_compare.py tests/test_phasevi_data.py` → **42 passed in 4.67s** (exit 0; 7 + 16 + 9 + 10) | same command on the docs-committed tree → **42 passed in 4.88s** (exit 0) |
| Runtime harness command/scenario and exact result | The sandboxed `test_asm_mesh_selection` prepare-only path is the runtime boundary (staged bytes, `run.json`, installed twin); the schema pin reads the real C++ writer source | `cd turbinesFoam && sh validation/phaseVI/scripts/runPhaseVI.sh -m asm-mesh -u 7 -mesh coarse` under OpenFOAM v2506 → `Environment OK`, `Generated case: consistent with config/case.yaml`, `Preparing asm-mesh-U7-coarse`, `Staged blade STL sha256 77def499…`, `Wrote run.json`, exit 0 — prepare-only, no `--run`/`--submit`, no `sbatch`, no job submitted |
| Rollback boundary | `git revert 00f60d4`: removes `tests/test_blade_stage.py` and restores the two Phase VI test modules to `94c8898`; no production code, case, runner or comparison behavior changes | `git revert a901c3c`: restores `validation/phaseVI/README.md`, root `README.md` and `CHANGELOG.md` to `00f60d4`; the tests and tooling stay intact |

### Commands and observed results

1. **Required focused tests** (interrupted-work verification, then on the
   docs-committed tree): `cd turbinesFoam && $PY -m pytest -q
   tests/test_blade_stage.py tests/test_phasevi_case.py
   tests/test_phasevi_compare.py tests/test_phasevi_data.py` →
   `42 passed in 4.67s` then `42 passed in 4.88s` (exit 0). Per module:
   `test_blade_stage` 7, `test_phasevi_case` 16, `test_phasevi_compare` 9,
   `test_phasevi_data` 10.
2. **W3 gate**: `$PY validation/phaseVI/tools/generate_case.py --check` →
   exit 0 (clean, no stale files).
3. **Prepare-only rehearsal** (OpenFOAM v2506, Int64 platform dirs prepended
   explicitly because the module's PATH/LD_LIBRARY_PATH point at a dead Int32
   dir): `sh validation/phaseVI/scripts/runPhaseVI.sh -m asm-mesh -u 7 -mesh
   coarse` → `Environment OK: OpenFOAM v2506`; the shared coarse mesh linked;
   `Staged blade STL sha256 77def499047fe0633e57564247a0fdd1330afbf4148b707db08ec79af0a2ec27`;
   `Wrote run.json`; exit 0. No `--run`, no `--submit`, no `sbatch`; no job
   submitted.
4. **Schema pin sanity**: the real writer emits
   `time,station,root_dist,area,force_x,force_y,force_z,c_ref_n,c_ref_t,f_ref_n,f_ref_t`
   and `time,node,x,y,z,nx,ny,nz,fx,fy,fz,area,station,chord_fraction`; the
   test rebuilds them from the `<< "..."` chunks and matches the fixture
   constants.
5. **Working tree**: after both commits only `openspec/`, `odd/`, `.atl/` and
   `.codegraph/` remain untracked (never committed); `runs/` and `results/`
   are gitignored.

### Deviations from design / tasks

1. **The interrupted run's tests were complete.** On re-entry the untracked
   `test_blade_stage.py` and the two modified test modules were verified against
   design §8.3 and the W3.5 task text and were already green, so they were
   committed unchanged; this batch's value is the W3.6 docs, the task
   bookkeeping and the W3 gate. No test was rewritten.
2. **Pre-registered hypothesis left qualitative on direction.** The proposal
   requires the expected direction and approximate size; the README records the
   direction (root transition/tip first, mid-span least affected) and the size
   bound (at or below the spanwise band), without inventing station numbers the
   design does not fix.
3. **Attribution commit pin.** The spec requires "the pinned `of-plugins` commit
   with the ASM patch note"; the README cites `26a1f46d79ff1481bba8d7fe2866516c367de232`
   (*feat(turbinesFoam): add actuator surface element type*), the in-history
   commit that adds the blade actuator-surface patch, and notes that later S2
   commits add the imported surface, the geometry component and the ASM-mesh
   variant.
4. **`size:exception`.** W3.5 is 527 insertions + 14 deletions = 541 changed
   lines (mostly the pre-existing partial test work) and W3.6 is 300 insertions
   + 31 deletions = 331 lines; cumulative W3 is far over the 400-line budget and
   the session strategy is the pre-authorized S1 `size:exception` (tasks.md
   Review Workload Forecast), recorded here explicitly.

### Files changed

| File | Action | What was done |
|------|--------|---------------|
| `turbinesFoam/tests/test_blade_stage.py` | Created | Seven pure-Python staging-helper contracts (defaults/hash, run-dir layout, idempotent staging, mismatch/missing-source/unusable-metadata aborts, CLI exit 3 and stdout hash) |
| `turbinesFoam/tests/test_phasevi_case.py` | Modified | Three-twin diff with `surfaceGeometry`/`kernel` keys and committed-file equality; `test_asm_mesh_selection` (select/reject/refuse + sandboxed prepare-only staging); `test_stage_matrix` `asm-mesh` stage; `test_generated_case_is_current` committed ASM-MESH twin |
| `turbinesFoam/tests/test_phasevi_compare.py` | Modified | Real `bladeSurface` CSV schema pin; three-way synthetic merge with the r/R conversion and three-model sign gate; missing/incomplete ASM-mesh input exit |
| `turbinesFoam/validation/phaseVI/README.md` | Modified | Three-model variant table, formulation/sub-grid/kernel-confound/MEXICO/pre-registered-hypothesis sections, prepared-only ASM-mesh array, three-way comparison, extended limitations, attribution |
| `README.md` | Modified | Mesh-backed blade ASM extension, pure-Python `phaseVI_blade` geometry component, three-model Phase VI package |
| `CHANGELOG.md` | Modified | One `Files:`/`Problem:`/`Fix:` entry per S2 work unit (W1, W2, W3) under `## [Unreleased]` |

### Commits

| Commit | Message |
|--------|---------|
| `00f60d4` | `test(turbinesFoam): add blade staging and three-way compare tests` |
| `a901c3c` | `docs(validation): document the three-way Phase VI plan` |

No `openspec/`, `odd/`, `.atl/`, PDF, run-directory or build-artifact content
is committed. `tasks.md` marks W3.5 and W3.6 `[x]` (**W3 complete**); the Engram
mirror (topic `sdd/blade-actuator-surface/apply-progress`) is refreshed with
this batch.

### Next (W4)

**W3 is complete.** Next: **W4** — W4.1 per-`addSup` instrumentation in
`bladeSurfaceSource` (nodes/candidates/seconds, `logDistribution`), W4.2
`test_instrumentation_line` + regression gate, W4.3 the prepared-only D/32
measurement gate documentation (no submission) and W4.4 the conditional
candidate-query hardening (only if the gate demands it).

### Post-verify fix and apply close-out (orchestrator)

- `4fb3b11` — `test(turbinesFoam): isolate the sandboxed runner test from an ambient Slurm allocation` (filters `SLURM_*` out of the sandbox env; the verify phase had caught `test_asm_mesh_selection` failing inside a batch job). Re-verified on `sequana_cpu_dev` (job `11599987`, COMPLETED 0:0, 6:32): `./Allwmake` exit 0, `ldd -r` clean, full suite **124 passed, 1 warning**, focused files **66 passed**.
- **Heavy-task policy (user requirement):** builds, solver-driven tests and the full suite now run on `sequana_cpu_dev` via `sbatch`; the job script lives under `$SCRATCH/tmp/verify-slurm/` and is not a repo artifact.
- **Apply phase closed:** W1–W4 applied and verified; W4.4 remains conditional (not triggered). The change is ready for `sdd-archive`.


