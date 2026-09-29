# Apply Progress: `nacelle-actuator-surface`

**Change:** `nacelle-actuator-surface` — slice **S1**; work units **W1 (core source)**, **W2 (geometry pipeline)**, **W3 (kinematics seam)** and **W4 (validation package; W4a skeleton → W4b compare/run/slurm/tests/docs, complete)**
**Mode:** Standard (`strict_tdd: false`; integration + data tests, no RED-GREEN ritual)
**Batches:** W1 close-out (W1.1–W1.7, no previous apply-progress existed) → W2 (W2.1–W2.5) → W3 (W3.1–W3.4) → W4a (W4.1, W4.2, W4.6, W4.7a) → **W4b (W4.3 registration, W4.4, W4.5, W4.7, W4.8; this batch)**.
W1 and W2 sections below are unchanged from their batches; the W3 and W4a blocks are appended.
**Branch:** `feat/nacelle-actuator-surface` (base `93da696`), local commits only — no push, no PR.
**Date:** 2026-09-20 (W1–W4a batches); 2026-09-20/21 (W4b batch, stage0 submission)

## Status

### W1 (core source) — batch 1

| Task | Status | Evidence (this batch) |
|------|--------|------------------------|
| W1.1 `nacelleSurfaceSampler` | [x] | files build; sampler contract exercised by `tests/test_nacelle.py` (body frame, SI node forces, aligned node lists, stable order) |
| W1.2 `nacelleSurfaceSource` | [x] | `./Allwmake` exit 0; standalone case writes `postProcessing/nacelle/nacelle.csv`; kernel partition of unity verified (see below) |
| W1.3 `Make/files` + `Make/options` | [x] | `-lsurfMesh` linked (`ldd` resolves `libsurfMesh.so`); full build + full suite green |
| W1.4 `createNacelle()` + null-deref fix | [x] | AFTAL diff matches design §6; full suite unchanged (ALM default path untouched) |
| W1.5 build gate + symbol check | [x] | `./Allwmake` exit 0; `ldd -r` clean; 53 `nacelle` symbols; no source newer than the `.so` |
| W1.6 `tests/test_nacelle.py` | [x] | 6 tests pass (`6 passed in 9.80s`), added to `conftest.SOLVER_DRIVEN` |
| W1.7 regression gate + docs | [x] | full suite `52 passed` (all pre-existing tests unchanged); `turbinesFoam/README.md` nacelle section |

### W2 (geometry pipeline) — batch 2

| Task | Status | Evidence (this batch) |
|------|--------|------------------------|
| W2.1 `geometry/src/nacelle.geo` | [x] | hemisphere + `6R` cylinder; `L` resolved from Fig. 3 (labels `R`/`6R`/`2R`, pixel cross-check **6.03**); 2616 triangles (paper `~2652`, −1.4 %) |
| W2.2 `geometry/src/makeGeometry.py` | [x] | CLI `generate`/`--check`/`--component`/`--gmsh`, exit codes 0/1/2; byte-identical regeneration; `--check` non-destructive (proven on a corrupted copy) |
| W2.3 `stl/nacelle.stl` + `metadata/nacelle.json` | [x] | binary STL `18c7beef…`, 2616 triangles; metadata schema + per-node normals/areas + `_reserved.blade` nulls |
| W2.4 `geometry/PROVENANCE.md` + `geometry/README.md` | [x] | source refs (arXiv:1702.02108v4 Sec. 4.1/Fig. 3, MEXICO blades deferred), gmsh **4.15.2**, `glu` module requirement, input/artefact sha256 |
| W2.5 `tests/test_nacelle_data.py` | [x] | **14 passed** (`14 passed in 3.87s`); 3 gmsh-gated tests **skip cleanly with an explicit reason** when gmsh is broken/unpinned (verified) |

### W3 (kinematics seam) — batch 3

| Task | Status | Evidence (this batch) |
|------|--------|------------------------|
| W3.1 time-derived `angleDeg_` | [x] | `rotate()` no longer accumulates; `azimuth(t)` = `ω0·(t−t0)` / closed-form separable integral; closed form vs RK4: **max 4.093e-11 deg** over 6 periods, monotone over 12; C++ ≡ independent Python reference (≤4.9e-11 deg, i.e. printed precision) |
| W3.2 registry persistence + restart | [x] | `angleDeg.<name>` (`dimless`, degrees, `AUTO_WRITE`, Time registry) written every step; `startFrom latestTime` restart resumed **38.1971863421 deg at t = 0.005** (the persisted value) and continued with byte-identical angle increments |
| W3.3 omega override field | [x] | `omega.<name>` (`(0,0,-1,0,0,0,0)` rad/s, `AUTO_WRITE`, Time registry); configured zero override drove `angle_deg = 0`, `tsr = 0` at every step (TSR law bypassed); unset → byte-identical CSV |
| W3.4 W3 regression gate | [x] | AFTAL CSV **byte-identical** to the accumulator baseline (sha256-equal files); full suite **66 passed, 1 warning** (unchanged); CFTAL Euler-vs-exact deviation quantified (below) |

### W4a (validation package skeleton) — batch 4

The batch closes out the interrupted W4a run: it verified the uncommitted work against
`tasks.md` W4.1/W4.2/W4.6 and design §8, then committed it. No W4b task was touched.

| Task | Status | Evidence (this batch) |
|------|--------|------------------------|
| W4.1 `config/case.yaml` | [x] | 117-line single source of truth: domain 30R×20R×20R, streamwise `cyclic` + crosswise `symmetry`, Re = 1000 (`U∞=1`, `R=1`, `ν=1e-3`), WALE headline + URANS k-ω SST fallback, coarse/medium grids + declared-only reference, `geometry` → pipeline STL, wash-out/averaging knobs; `test_config_schema`, `test_grids_and_reference_declared_only`, `test_metrics_and_acceptance`, `test_stage_plan` pass |
| W4.2 `tools/generate_case.py` | [x] | 799-line single-module renderer (YAML → committed `case/`); non-destructive `--check` exit 0 on the clean tree (14 file sha256 hashes identical before/after), exit 1 on stale/missing; standalone `nacelleSurfaceSource` entry (no turbine) whose `geometry` path resolves to `geometry/stl/nacelle.stl` from the case root **and** from a `runs/` directory; `test_cli_variant_render`, `test_generated_case_is_current`, `test_stale_file_detection_is_non_destructive`, `test_missing_file_detection_is_non_destructive` pass |
| W4.6 case skeleton + README + gitignore | [x] | committed 14-file `case/` skeleton (625 lines, renders clean), package `.gitignore` (`runs/`, `results/`, run artefacts, `__pycache__`), root `.gitignore` +4 lines; README documents setup, staged run plan, metrics, closure adaptation, limitations and attribution; `test_turbulence_headline_and_fallback` reads the README and asserts WALE + dynamic SGS + fallback + arXiv id |
| W4.7a `tests/test_nacelle_case.py` | [x] (partial W4.7) | **14 passed in 1.47s** in the plain env (no OpenFOAM: `WM_PROJECT_VERSION` empty); pure-Python and deliberately **not** in `conftest.SOLVER_DRIVEN`; W4.7 itself stays open until `test_nacelle_compare.py` (W4b) exists |
| W4.3, W4.4, W4.5, W4.7b, W4.8 | [x] | **W4b — completed in this batch** (see the "W4b batch" section below; W4.3 registered from `7cb1f3c`) |

**Delivery decision (size):** the tasks forecast is `400-line budget risk: High` with
`single-pr` as the recorded session strategy. W1 alone was ~2,600 changed lines and this
batch records an explicit **`size:exception`** recommendation for the W1 slice; W2 is
self-contained — `git diff --stat` over its two commits: **7 files, 3906 insertions**, of
which only ~**1277 authored lines** are reviewable code/docs (generator 564, tests 412,
`.geo` 43, docs 258) and the rest is the committed generated artefacts (STL 130,884 bytes
binary, metadata 2629 lines). It carries the same `size:exception` note. The orchestrator
authorized both batches and commits were created (no PR opened), so the exception is
stated here and in the return summary.

W4a is **~1956 changed lines** (authored **1331**: renderer 799, test 292, `case.yaml` 117,
README 95, gitignore 28; generated `case/` skeleton 625) and carries the same
`size:exception` note. The two W4a commits were created by this close-out batch, still
local-only (no push, no PR).

## Commands and observed results

### Environment (important — the preflight env block is not sufficient at runtime)

The preflight env block works for `wmake` but **not** for running solvers/tests. Three
observed failure modes, all fixed by sourcing the install's own environment:

- module only → `pimpleFoam: command not found` (the module prepends the dead
  `platforms/linux64GccDPInt32Opt/bin`; this install is `linux64GccDPInt64Opt`)
- `decomposePar: error while loading shared libraries: libmetisDecomp.so` (the metis
  stub lives in `…/lib/dummy`)
- `libkahip.so` not found (lives in `ThirdParty-v2506/platforms/linux64GccDPInt64/lib`)
- putting `lib/dummy` before `lib/sys-openmpi` makes the dummy `libPstream.so` win →
  `The dummy Pstream library cannot be used in parallel mode`

Canonical, verified environment (Int64, resolves Pstream/metis/KaHIP correctly):

```sh
module load openfoam/v2506_openmpi-4.1.4_gnu
source $WM_PROJECT_DIR/etc/bashrc          # WM_OPTIONS=linux64GccDPInt64Opt, full PATH + LD_LIBRARY_PATH
cd turbinesFoam
```

(`python3 -m pytest` is used instead of `pytest` to pin the venv interpreter with
numpy/pandas.)

### Build gate (after the batch's C++ corrections)

```sh
cd turbinesFoam && ./Allwmake                                  # exit 0
ldd -r $FOAM_USER_LIBBIN/libturbinesFoam.so 2>&1 | grep -i undefined   # empty (clean)
nm -D --defined-only $FOAM_USER_LIBBIN/libturbinesFoam.so | grep -ci nacelle   # 53
ldd $FOAM_USER_LIBBIN/libturbinesFoam.so | grep surfMesh       # libsurfMesh.so resolved
find src -newer $FOAM_USER_LIBBIN/libturbinesFoam.so \( -name '*.C' -o -name '*.H' -o -name files -o -name options \)   # empty
```

The link run with the AGENTS.md-style `LD_LIBRARY_PATH` emitted `rpath-link`
warnings for OpenFOAM's own transitive libs (`libOpenFOAM.so`, `libfileFormats.so`,
...). They are benign for a `-shared` link (the library is complete: `ldd -r` is clean
and the run works); they do not appear in `ldd`. Relinking with the `etc/bashrc`
environment would resolve them but was not re-run (no source changes after the gate
build).

### Case repair (the previously failing `tests/nacelleSurface` run)

The stale `log.pimpleFoam` came from an older Allrun/invocation. With the correct
environment the **current** `Allrun` runs clean in serial and in parallel
(`runParallel pimpleFoam`, 2 ranks, `decomposeParDict` splits `x` at 0.5):

```sh
cd turbinesFoam/tests/nacelleSurface && ./Allclean && ./Allrun              # exit 0
./Allclean && ./Allrun -parallel                                           # exit 0, "Finalising parallel run"
```

Both produce the analytic CSV (plate: 2 triangles, `A_node = 0.02`,
outward normal `(1 0 0)`, `h = 0.1`, `dt = 0.1`, `U = 1`, `cf = 0.01`, `rho = 1`):

```
time,fx,fy,fz,f_n_mag,f_tau_mag,cd
0.1,0.0402,0,0,0.04,0.0002,2.01
```

The `forceIntegral` function object (added to `system/controlDict`) confirms the
partition of unity `sum_c forceField[c]*V_c == sum_i F_i` (Eq. 18 carries the negative
sign — the field is the force on the flow):

```
# Time         volIntegrate(force.nacelle)
0.1            (-4.020000e-02 0.000000e+00 0.000000e+00)
```

Fatal-error paths, run on copies of the case:

| geometry | exit | log |
|----------|------|-----|
| `geometry/doesNotExist.stl` | 1 | `FOAM FATAL ERROR: Nacelle surface file "…" not found` |
| `geometry/empty.stl` | 1 | `FOAM FATAL ERROR: Nacelle surface file "…" contains no triangles` |
| unparseable text file | 1 | `FOAM FATAL ERROR: while reading solid on line 1 …` |

### Tests

```sh
cd turbinesFoam
python3 -m pytest -q tests/test_nacelle.py                                    # 6 passed in 9.80s
python3 -m pytest -q tests/test_libs.py tests/test_aftal.py                   # 4 passed in 63.91s
python3 -m pytest -q tests/test_al.py tests/test_asm.py tests/test_aftal_asm.py tests/test_cftal.py
                                                                              # 11 passed in 146.54s
python3 -m pytest -q                                                          # 52 passed, 1 warning in 213.81s
```

The full suite was run **after** all C++ changes and **after** the new tests were in
place; the only warning is the pre-existing `pytest.mark.timeout` unknown-mark warning
in `tests/test_al.py:131`. Nothing was deferred: the full suite fits in ~4 minutes.

## What `tests/test_nacelle.py` verifies (W1.6)

1. `test_serial` — rotor-less standalone source runs, `postProcessing/nacelle/nacelle.csv`
   parses, and the total force equals the analytic `Σ h·U/Δt·A_i + Σ ½·cf·U²·A_i`
   (rtol 1e-6); per-node CSV has the same node set, body-frame normals, SI forces.
2. `test_total_force_preserved` — `Σ_c forceField[c]·V_c == −Σ_i F_i` (partition of unity),
   also asserted inside the serial and parallel runs.
3. `test_parallel` — `mpirun -np 2`; the plate at `x = 0.45` with `2.5h = 0.25` support
   straddles the `x = 0.5` processor boundary, so the 5³ stencil exercises cross-rank
   interpolation/distribution; totals match serial to rtol 1e-9.
4. `test_missing_stl_aborts`, `test_empty_stl_aborts`, `test_corrupt_stl_aborts` — the
   three `FatalError` scenarios, run on temporary copies of the case.

## Deviations and corrections vs design

1. **`forces()` body-frame contract (correctness fix in this batch):** the interrupted
   run stored the SI list in the global frame. `calcForceField` now rotates it with
   `bodyToGlobal().T()` (new sampler accessor) so `forces()` really is body-frame as
   the `surface-sampling-contract` spec requires. The identity body frame of the W1
   case means no CSV change; no test change needed.
2. **Compressible split diagnostics:** `forceNormal_`/`forceTangential_` are now
   rho-weighted like the total (`rhoNode = 1` on the incompressible path), so
   `f_n_mag + f_tau_mag` stays consistent with the total SI force in compressible runs.
3. **`interpolateVelocity(X, U, h)`** takes `h` explicitly (design §4.1 lists `(X, U)`);
   the kernel width needs the node's local cell size.
4. **`referenceArea`** implemented as a config key with default `1.0` (design §4.4
   mentions it; the §4.3 key list does not).
5. **No `returnReduce` on the total force** (design §4.2 step 5 mentions one): the node
   loop is replicated on every rank, so reducing would double count. `force_` is the
   global total on every rank; `interpolateVelocity` and `cellSize` are the quantities
   actually reduced.
6. **`cf = 0` when `Rex <= 1`** (Schultz–Grunow is undefined for `log(Rex) <= 0`),
   documented in the README nacelle notes.
7. **`writeOutput()` per `addSup`** — one CSV row per time step because the case sets
   `nOuterCorrectors 1` (PIMPLE would otherwise write one row per outer iteration).
8. **Test case:** the pre-existing `system/fvOptions.schultzGrunow` +
   `geometry/plateTilted.stl` variant files are committed but not yet exercised by a
   test (kept for the friction-model variant; W1.6 does not require it).

## Files

| File | Action | Note |
|------|--------|------|
| `turbinesFoam/src/fvOptions/nacelleSurface/nacelleSurfaceSampler.{H,C,I.H}` | Create (this batch: H +5, I.H +8) | sampler + body-frame accessor |
| `turbinesFoam/src/fvOptions/nacelleSurface/nacelleSurfaceSource.{H,C,I.H}` | Create (this batch: C ~+15 net) | source; body-frame forces + rho-consistent split |
| `turbinesFoam/src/Make/files`, `src/Make/options` | Modify | register sources; `-lsurfMesh` + surfMesh include |
| `turbinesFoam/src/fvOptions/axialFlowTurbineALSource/axialFlowTurbineALSource.{H,C}` | Modify | `autoPtr<nacelleSurfaceSource>`; `createNacelle()` |
| `turbinesFoam/tests/nacelleSurface/` | Create | standalone plate case (`Allrun`/`Allclean`, `0.org`, `constant`, `geometry/{plate,plateTilted,empty}.stl`, `system/*`, `.gitignore`, force-integral function object) |
| `turbinesFoam/tests/test_nacelle.py` | Create | 255 lines, 6 tests |
| `turbinesFoam/tests/conftest.py` | Modify | add `test_nacelle.py` to `SOLVER_DRIVEN` |
| `turbinesFoam/README.md` | Modify | "Nacelle surface model" section (keys, wiring, CSV, notes, fork divergence) |
| `openspec/changes/nacelle-actuator-surface/tasks.md` | Modify | W1.1–W1.7 checked |
| `openspec/changes/nacelle-actuator-surface/apply-progress.md` | Create | this file |

Generated artifacts (`0/`, `0.1/`, `constant/polyMesh/`, `postProcessing/`,
`processor*/`, `log.*`, `turbinesFoam/log.Allwmake`) were removed or are gitignored and
are **not** part of any commit.

## W2 batch — commands and observed results

### Environment (gmsh) — the W1 gmsh finding is superseded

```sh
module load glu/9.0.2_gnu                                   # provides libGLU.so.1 for libgmsh
/scratch/leahk/eduardo.donestevez/venv/bin/gmsh --version    # -> 4.15.2
ldd /scratch/leahk/eduardo.donestevez/venv/lib/libgmsh.so.4.15 | grep -i glu
# libGLU.so.1 => /lib64/libGLU.so.1 ; also libGL.so.1 (OpenGL)
```

- The pinned toolchain is the **pip `gmsh` 4.15.2** in
  `/scratch/leahk/eduardo.donestevez/venv` (`lib/libgmsh.so.4.15`), not a system binary;
  `shutil.which("gmsh")` resolves to `/scratch/leahk/eduardo.donestevez/venv/bin/gmsh`.
- Without a runnable library environment `import gmsh` fails (`env -i` probe:
  `OSError: libpsm_infinipath.so.1`, i.e. the MPI stack; the orchestrator observed the
  `libGLU.so.1` variant). Tests skip with that reason instead of failing.
- `venv/bin/gmsh` is a thin Python shim (`#!/usr/bin/env python`), so the venv must be on
  `PATH` for it to import gmsh; the CLI requires `-2` (without it: exit 1 and no output).
- **Module order:** loading `glu/9.0.2_gnu` together with
  `openfoam/v2506_openmpi-4.1.4_gnu` + `source $WM_PROJECT_DIR/etc/bashrc` works in any
  order tried; no conflict observed. Both were loaded for the regression runs below.

### Generation

```sh
cd turbinesFoam/geometry
python3 src/makeGeometry.py --gmsh /scratch/leahk/eduardo.donestevez/venv/bin/gmsh
# nacelle: 2616 triangles, x [-6.996, 0] y [-1, 1] z [-1, 1], area 46.9962, volume 20.8102
# wrote stl/nacelle.stl
# wrote metadata/nacelle.json
# input sha256: e0a69771736aa3b26a11b00880ddd0acf2cf45d8782f13d56fd78ccb89d20de5
# stl sha256:   18c7beef9e323ba28da20f5c813232c0059693f221a594fd913c4e69c14cb74c
```

Determinism (two consecutive runs, then both environments):

```sh
sha256sum stl/nacelle.stl metadata/nacelle.json      # same digests after a re-run
python3 src/makeGeometry.py --check --gmsh …/gmsh    # exit 0 (plain env)
# same command inside `module load openfoam/… && source $WM_PROJECT_DIR/etc/bashrc`
# previously failed here (see the incident below); now exit 0
```

**Cross-environment determinism incident (fixed in this batch).** The first committed STL
was produced in the plain environment; `--check` under the OpenFOAM environment regenerated
a *different* file (`6ca5bd92…`) — and diagnosis showed the mesh was identical (1310 nodes,
2708 elements, same vertex set, same triangle multiset) and only gmsh's **element order**
differed. `--check` therefore now requires an environment-independent artefact: the
generator re-serializes the mesh (each triangle rotated to its lexicographically smallest
cyclic form, triangles sorted, fixed 80-byte header, recomputed facet normals, duplicate
triangles rejected) and writes the binary STL itself. Verified: `--check` exits 0 in both
environments with the committed `18c7beef…` STL.

### Mesh facts (committed STL)

| Quantity | Committed | Analytic / target |
|---|---|---|
| triangles | **2616** | paper 2652 (−1.4 %) |
| area sum | 46.9962 | `15πR² = 47.1239` (−0.27 %) |
| signed volume (outward) | +20.8102 | `(2/3)πR³ + 6πR³ = 20.9439` (−0.64 %) |
| bounds | `x ∈ [-6.996, 0]`, `y,z ∈ [-1, 1]` | `x ∈ [-7, 0]` (inscribed mesh misses the analytic nose point) |
| cap (downstream disc) | 184 triangles, area 3.1187 | `πR² = 3.1416` (−0.73 %) |

Closed manifold (every edge shared by exactly two triangles), consistently outward
oriented, binary STL (`84 + 50·n` bytes). The mesh seed sweep (0.199–0.229 in 5e-4 steps)
showed plateaued counts (2590–2616 over 0.2095–0.2145); `meshSizeRatio = 0.2125` is the
closest reproducible value to 2652 — recorded, not over-tuned.

### Tests

```sh
cd turbinesFoam
python3 -m pytest -q tests/test_nacelle_data.py            # 14 passed in 3.87s
GMSH=<broken gmsh> python3 -m pytest -q tests/test_nacelle_data.py
                                                           # 11 passed, 3 skipped (explicit reasons) — corrected in the W3 batch
                                                           # (14 tests total: 3 gmsh-gated; re-verified 2026-09-20: `GMSH=/nonexistent/gmsh` → 11 passed, 3 skipped)
python3 -m pytest -q tests/test_nacelle.py tests/test_nacelle_data.py tests/test_phasevi_data.py
                                                           # 30 passed in 12.06s (OpenFOAM env)
python3 -m pytest -q                                       # 66 passed, 1 warning in 217.14s
```

The full suite grew from W1's `52 passed` to `66 passed` (the 14 new pure-Python tests are
always collected; `test_nacelle_data.py` is deliberately **not** in `conftest.SOLVER_DRIVEN`);
the only warning is the pre-existing `pytest.mark.timeout` unknown-mark warning in
`tests/test_al.py:131`.

### What `tests/test_nacelle_data.py` verifies (W2.5)

1. Binary STL with the paper's triangle count band (±5 %) and the exact committed count.
2. Geometry: downstream cap at `x = 0`, nose at `-7R`, body of revolution of radius `R`
   (per-node `y²+z² ≤ R²`, extremes reaching `R`).
3. Closure + orientation: edge-manifold check, facet normals vs winding, positive signed
   volume ≈ analytic within 1 %.
4. Total area ≈ `15πR²` within 1 % (inscribed, so strictly below).
5. Canonical triangle order (sorted, cyclically minimal, no duplicates, fixed header) —
   the environment-independence invariant.
6. Metadata schema: `component`/`format_version`/`units`/`generator`/`input_sha256`/
   `n_triangles`/`parameters`/`stl_sha256`/`nodes`/`_reserved.blade`; per-node index order,
   unit normals, positive areas, agreement with the STL triangles.
7. Hash linkage: `parameters` and `input_sha256` reproduce the `.geo` + parameter recipe;
   `stl_sha256` matches the committed STL.
8. `PROVENANCE.md` source refs (arXiv:1702.02108v4, Sec. 4.1, Fig. 3, MEXICO blades),
   gmsh 4.15.2, the `glu` requirement and both sha256 values; `README.md` usage, component
   list and S2 deferral.
9. CLI contract: deferred `blade0` and unknown components exit non-zero with the documented
   message.
10. (gmsh-gated) `--check` is clean on the committed tree; a corrupted STL and a stale
    PROVENANCE are detected (exit 1) **without** modifying the (copied) tree.

## W2 batch — deviations and extensions vs design

1. **Mesh-size options:** `Mesh.CharacteristicLengthMin/Max` are set (design §7 suggested
   `Mesh.CharacteristicLengthFactor`). Same "mesh-resolution seed" concept: the
   characteristic length is relative to `R` directly instead of to OCC's bounding-box
   sizes, which makes the seed a single documented number.
2. **Metadata schema additions:** `parameters` (the `primary:` block parsed from the
   `.geo`) and `stl_sha256` are recorded alongside the design §7 fields, so the input hash
   is auditable and metadata ↔ STL linkage is checkable. `_reserved.blade` is exactly per
   design. No design field was dropped. Floats are rounded to 6 significant digits
   (within the binary STL's float32 resolution).
3. **The generator writes the STL** (canonical order, fixed header, recomputed facet
   normals) instead of committing gmsh's raw output — required for byte-identical
   regeneration, see the incident above. The design did not specify the writer.
4. **`--check` exit codes:** `2` (gmsh missing/not runnable/not pinned) is distinct from
   `1` (stale artefact) so missing tooling produces an honest test skip rather than a
   false failure. Generating with an unpinned gmsh warns and records the actual version.
5. **`--gmsh` path:** the tasks' `~/venv/bin/gmsh` was resolved to the actual venv
   (`/scratch/leahk/eduardo.donestevez/venv/bin/gmsh`); the tests additionally accept
   `$GMSH`, `PATH`, or a `gmsh` next to the pytest interpreter.
6. **PROVENANCE updates stay manual:** regenerating changes the hashes, so the generator
   prints both values and `--check` fails until the doc records them (no prose file is
   auto-rewritten).
7. **`nacelle.geo` keeps the design's frame** (downstream end at `x = 0`, nose upstream at
   `-7R`) and the canonical `R = 1 m`; the derived `L`/`lc` are computed in the `.geo` so
   the parameter block stays the single source of truth.

## W2 batch — files

| File | Action | Note |
|------|--------|------|
| `turbinesFoam/geometry/src/nacelle.geo` | Create | hemisphere + `6R` cylinder, OCC, Frontal-Delaunay, binary STL, `primary:` parameters |
| `turbinesFoam/geometry/src/makeGeometry.py` | Create | generator CLI + canonical STL writer + metadata renderer (564 lines) |
| `turbinesFoam/geometry/stl/nacelle.stl` | Create | committed binary STL, 2616 triangles, sha `18c7beef…` |
| `turbinesFoam/geometry/metadata/nacelle.json` | Create | per-node normals/areas, hashes, parameters, `_reserved.blade` |
| `turbinesFoam/geometry/PROVENANCE.md` | Create | sources, Fig. 3 resolution, generator, environment, hashes |
| `turbinesFoam/geometry/README.md` | Create | usage, components, schema, determinism, S2 deferral |
| `turbinesFoam/tests/test_nacelle_data.py` | Create | 14 pure-Python tests (3 gmsh-gated) |
| `openspec/changes/nacelle-actuator-surface/tasks.md` | Modify | W2.1–W2.5 checked |
| `openspec/changes/nacelle-actuator-surface/apply-progress.md` | Modify | W2 merged (this file) |

## W3 batch — commands and observed results

Environment: the same canonical one as W1/W2 (`module load openfoam/v2506_openmpi-4.1.4_gnu`
+ `source $WM_PROJECT_DIR/etc/bashrc`, `python3` = the venv interpreter). Case runs here use
the case's own `Allrun`, which **skips** any step whose `log.<app>` already exists — remove
`log.pimpleFoam` between consecutive runs on the same case or the solver silently does not run.

### Baseline provenance (captured before touching the code)

The batch opened with an **uncommitted partial W3 implementation** left by an interrupted
earlier session (working tree `M turbineALSource.{H,C}`, installed `.so` from 14:03). The
baseline was therefore re-captured first-hand from a HEAD rebuild:

```sh
cp turbineALSource.{H,C} /tmp/opencode/w3/partial/ && git diff > …/w3-partial.patch
git stash push -m w3-partial-preserved -- turbineALSource.{H,C}   # tree back to HEAD (cb9f010)
cd turbinesFoam && ./Allwmake                                     # exit 0, 0 errors, 62 s
sha256sum $FOAM_USER_LIBBIN/libturbinesFoam.so                    # 233b1d4f… (HEAD accumulator build)
cd tests/axialFlowTurbineALSource && ./getTutorialFiles.sh && ./Allclean && ./Allrun
cp postProcessing/turbines/0/turbine.csv /tmp/opencode/w3/base/aftal-turbine.csv
cd tests/crossFlowTurbineALSource  && ./getTutorialFiles.sh && ./Allclean && ./Allrun
cp postProcessing/turbines/0/turbine.csv /tmp/opencode/w3/base/cftal-turbine.csv
```

The fresh HEAD baseline is **byte-identical** to the interrupted session's stored captures
(`/tmp/opencode/w3-baseline/{aftal,cftal}-baseline.csv`), which validates both captures.
`git stash pop` restored the partial work byte-identically (sha256 checked), then the
corrections below were applied. New build: exit 0, 0 errors, **54 warnings (same as the
baseline build — all pre-existing)**, `ldd -r` clean, `.so` sha256 `59afcffd…`.

### W3.4 — CSV regression gate (baseline accumulator vs time-derived library)

Same cases, same commands, after the rebuild:

| Case | Result |
|------|--------|
| `tests/axialFlowTurbineALSource` (constant TSR 6) | `cmp` → **BYTE-IDENTICAL** (3 rows, all 12 columns) — sha256 equal |
| `tests/crossFlowTurbineALSource` (`tsrAmplitude 0.19`) | `angle_deg` differs by the explicit-Euler truncation of the accumulator (table below); all other columns follow |

```
time   angle_deg (accumulator)   angle_deg (integral)   diff [deg]   rel
0.01   2.35897659627            2.3511380248           7.8386e-03   0.33 %
0.05   11.6112218835            11.5625338836          4.8688e-02   0.42 %
0.10   22.653412807             22.5472700102          1.0614e-01   0.47 %
```

**Tolerance recorded:** for constant TSR (the phaseVI/AFTAL path) the agreement is exact to
floating point — the AFTAL CSV is byte-identical, not merely within tolerance, because the
accumulator sums `ω·dt` per step and `t` itself is the same accumulated sum. For
`tsrAmplitude != 0` the accumulator is first-order Euler and the new value is the **exact**
integral, so the residual is the accumulator's truncation error, not a regression: an
independent Python Euler reproduction gives `2.358976596269` @ 0.01 and `22.653412806998` @
0.1 (matching the baseline CSV to all printed digits), while the new CSV matches an
independent RK4 integration of the ODE. No existing test pins the absolute `angle_deg` for
`tsrAmplitude` cases (`check_periodic_tsr` recomputes `tsr` from the CSV's own angle), so the
suite is unchanged — see open item §12 Q3.

### W3.1 — independent closed-form check (`/tmp/opencode/w3/azimuth_check.py`)

An exact Python replica of `azimuth()` (same IEEE-754 arithmetic, `std::round` semantics)
compared against a fine RK4 integration of `dθ/dt = ω0(1 + m·cos(nB(θ−φ)))` for the CFTAL
parameters:

```
closed form vs RK4 (t in (0, 10] s): max |dtheta| = 4.093e-11 deg (at t=9.940)
monotone over (0, 20] s: True ; max increment between 1e-5 steps = 2.395e-03 deg
azimuth(0) = 2.5444437451708134e-14 (== angle0 within floating point)
```

The replica reproduces the compiled library's CSV to the printed precision (max 4.85e-11 deg),
i.e. the `atan` branch unwrapping, the `C` fixed by `θ(t0) = degToRad(angle0_)`, and the
monotonic continuation are correct.

### W3.2 — restart idempotency (`startFrom latestTime`)

With real writes enabled (`writeInterval 0.001`, `endTime 0.007`) the case was run 0 → 0.005,
then restarted `startFrom latestTime` to 0.007:

```
Resuming azimuth of turbine from angleDeg.turbine: 38.1971863421 deg at t = 0.005
0.005/angleDeg.turbine:  value 38.1971863421;      # == fresh run CSV row at t = 0.005
fresh run:      0.006 → 45.8366236105   0.007 → 53.4760608789
resumed run:    0.006 → 45.8366236105   0.007 → 53.4760608789   # byte-identical angles
```

The **azimuth** is idempotent across the restart (exact, byte-identical column). The force
coefficients of the resumed steps differ from a from-scratch continuation (cp 0.3556 vs
0.6526 at t=0.006): turbinesFoam does not persist the actuator-line elements' internal state,
so the solver restart is not bit-identical — a pre-existing property of the case/solver, not
of the azimuth seam. Parallel runs write one `angleDeg.<name>` per rank directory
(`processorN/<time>/angleDeg.<name>`, correct values), as expected for uncollated output.

### W3.3 — omega override seam

`omegaOverrideField omega.turbine;` added to the AFTAL turbine subdict (case dir is
gitignored and was restored afterwards):

```
Created omega override field omega.turbine
time,angle_deg,tsr,... 
0.001,0,0,0,0.171314940039,...      # TSR law bypassed: the (zero) override drives the azimuth
```

The run then aborts with **SIGFPE** in `axialFlowTurbineALSource::calcEndEffects()`
(`elementVel/mag(elementVel)`, `axialFlowTurbineALSource.C:529`, unguarded) because a
stationary rotor has zero element velocity — a **pre-existing** divide-by-zero, out of W3's
file scope, not addressed here. The adapter-supplied seam writes a non-zero ω before the
first step, so the supported path does not hit it; a zero override (parked rotor) does.

### Tests

```sh
cd turbinesFoam
GMSH=/nonexistent/gmsh python3 -m pytest -q tests/test_nacelle_data.py   # 11 passed, 3 skipped (W2 doc fix)
python3 -m pytest -q                                                     # 66 passed, 1 warning in 235.28s
```

Full suite identical to W2 (`66 passed`, same pre-existing `pytest.mark.timeout` warning);
`test_aftal` (serial, parallel, opposite rotation) and `test_cftal` (serial, parallel,
multiRe) pass unchanged.

## W3 batch — deviations and findings vs design

1. **No `mod 360` wrapping.** Spec/design mention "modulo 360°"; the implementation keeps the
   integral continuous and monotonic (unwrapped). Rationale: the stronger normative
   requirement is "CSV output identical to the accumulator (to floating point)", which a wrap
   would break past one revolution. The unwrapped value is the same angle modulo 360° (the
   scenario's phrasing), and the persisted field may be seeded from any representative.
   Documented in the `azimuth()` comment.
2. **Override is integrated incrementally** (`angleDeg_ += radToDeg(omega*(t - lastRotationTime_))`),
   not as a pure function of time: the override is an external stepwise signal whose history
   cannot be recovered from `(t0_, angle0_, t)`. This mirrors the accumulator it replaces and
   makes a repeated call at the same time a no-op. The TSR-law path remains a pure function.
3. **Open Q2 resolved (read-back mode + registry host).** Host = **Time** (the adapter reads
   `mesh_.time().foundObject/lookupObject<uniformDimensionedScalarField>` and
   `sortedNames<…>` in `modules/generic/Generic.C`, `runTime_.foundObject/lookupObjectRef` in
   `ReadWrite.C`; `fsiOmega/preciceOmega.C` likewise). Read-back = `IOobject::READ_IF_PRESENT`
   at `time_.timeName()` with `typeHeaderOk<uniformDimensionedScalarField>(true)` to
   distinguish "read from disk" from "defaulted"; under `startFrom latestTime` that instance
   is the latest written time directory. The adapter/fsiOmega seams only create fields in
   memory (`NO_READ`), so they give no disk read-back precedent; `NO_READ` on the create path
   is kept for the **created** object when no file exists (READ_IF_PRESENT degenerates to it).
4. **Per-step persistence side effect.** The design §5.1 snippet and tasks W3.1 mandate the
   field write inside `rotate()`, so `angleDeg.<name>` is written every step, not only at
   write intervals. Observed: for the stock AFTAL case (`writeInterval 0.005`, `endTime
   0.003`) the run creates `0.001/`, `0.002/`, `0.003/` containing **only**
   `angleDeg.turbine`; the case itself never wrote a time directory. This is the checkpoint
   behaviour the rollback requirement needs, and design §11 calls these directories harmless;
   noted as a follow-up risk for cases that restart with `startFrom latestTime` (a
   checkpoint-only directory can be picked as "latest").
5. **Interrupted-session partial work was reused and corrected,** not rewritten: the batch
   verified the closed form independently, corrected the override interval to
   `t − lastRotationTime_`, resolved/documented the read-back conventions, and added the
   no-wrap rationale. The baseline was re-captured from scratch before any edit.
6. **`cftal` Euler-vs-exact deviation is expected** (open Q3): quantified above; the new law
   is the exact integral, so no tolerance "adjustment" is needed in any test.

## W3 batch — files

| File | Action | Note |
|------|--------|------|
| `turbinesFoam/src/fvOptions/turbineALSource/turbineALSource.H` | Modify | `t0_`/`angle0_`, override + persisted-field members, `azimuth()`, `createAngleDegField()`, `createOmegaOverrideField()`, `angleDeg()` accessor |
| `turbinesFoam/src/fvOptions/turbineALSource/turbineALSource.C` | Modify | time-derived `rotate()`, closed-form `azimuth()`, registry persistence, override read in `updateTSROmega()`/`read()` |
| `openspec/changes/nacelle-actuator-surface/tasks.md` | Modify | W3.1–W3.4 checked |
| `openspec/changes/nacelle-actuator-surface/apply-progress.md` | Modify | W3 merged (this file); W2 `10 → 11 passed` correction |

## W4a batch — commands and observed results

Environment: **plain shell** (no OpenFOAM) for every command below; `WM_PROJECT_VERSION`
was empty. Both checks are pure-Python, which is the CI-safe path the spec requires.

### Non-destructive render check

```sh
cd turbinesFoam
python3 validation/nacelle-asn/tools/generate_case.py --check    # exit 0, no output
```

`--check` re-renders in memory and compares; it never writes (the `--check` branch returns
before the write loop). Non-destructiveness was verified first-hand by hashing the whole
skeleton around the check:

```sh
find validation/nacelle-asn/case -type f | sort | xargs sha256sum > /tmp/opencode/w4a-case-before.sha256   # 14 files
python3 validation/nacelle-asn/tools/generate_case.py --check    # exit 0
find validation/nacelle-asn/case -type f | sort | xargs sha256sum > /tmp/opencode/w4a-case-after.sha256
diff /tmp/opencode/w4a-case-before.sha256 /tmp/opencode/w4a-case-after.sha256   # empty
```

### Tests

```sh
cd turbinesFoam
python3 -m pytest -q tests/test_nacelle_case.py                  # 14 passed in 1.47s (exit 0)
```

`tests/conftest.py` `SOLVER_DRIVEN` does **not** list `test_nacelle_case.py`, so the module
is always collected without OpenFOAM (14 tests = the 14 `def test_` in the file).

### What `tests/test_nacelle_case.py` verifies (W4.7a)

1. Config schema: Re = 1000, domain/boundaries, `stl` resolves to
   `geometry/stl/nacelle.stl`, WALE headline + URANS fallback, fixed time step.
2. Grids: coarse/medium counts and uniform spacings; the 502×348×348 reference is
   `declared_only` and absent from `MESH_CHOICES`.
3. Rendered dictionaries in memory: blockMesh patches/vertices/counts, controlDict run
   schedule (Δt 0.1, endTime 210, 150 samples), turbulence WALE/URANS, fvSchemes,
   standalone fvOptions entry (no `axialFlowTurbineALSource`), topoSet box, field BCs.
4. The `geometry` entry resolves from both the case root and a `runs/` directory depth,
   and the committed `case/system/fvOptions` equals the in-memory render.
5. `--check` clean-tree pass; stale-file and missing-file detection exit non-zero and are
   **non-destructive** (tampered/missing files left as-is).
6. Metrics/acceptance: stations 1R/3R/5R/7R + 10R stretch, CD definition, datum 0.48,
   medium all-stations vs coarse 1R/far-wake only.
7. Stage plan: only `stage0` executes; `production` is prepared-only on a different queue.

### Deviations and notes vs design (W4a)

1. **Single-module renderer.** phaseVI splits config loading/rendering between
   `tools/case_config.py` and `tools/generate_case.py`; the nacelle package keeps one
   module (799 lines) so the slice stays self-contained. YAML loading mirrors phaseVI
   (`yaml.safe_load`); the test loads the module under a private name because both
   packages ship the same file name.
2. **W4.7 is split.** `W4.7a` = `tests/test_nacelle_case.py` (this batch); `W4.7b` =
   `tests/test_nacelle_compare.py` (W4b, blocked on the digitized reference W4.3). The
   W4.7 checkbox stays open in `tasks.md` with a partial note.
3. **Grid Δ values vs cell counts (finding, not fixed here).** The spec/exploration state
   coarse `153×80×80` with `Δx=R/2.5` and medium `115×151×151` with `Δx=R/3.75`; over the
   30R×20R×20R domain the counts imply `Δx≈R/5.1` (coarse) and `≈R/3.83` (medium),
   `Δy≈R/7.55` (medium). The renderer follows the **cell counts** (the paper's grids and
   what the spec scenario asserts); the Δ values are not rendered or asserted anywhere.
   Carried to W4b: any grid-spacing claim or station-sampling assumption should use the
   rendered counts, and the tension should be resolved against the paper before
   documenting Δ.
4. **`cf -1.0`** in the rendered fvOptions is the W1 source's documented sentinel
   (`cfOverride_` defaults to `-1.0`; `cfModel schultzGrunow` uses the model), not a typo.
5. **Root `.gitignore` addition is belt-and-braces** with the package `.gitignore`; both
   ignore `runs/`/`results/` (the root one keeps the intent visible from the repo root).

### W4a batch — files (committed by this batch)

| File | Action | Note |
|------|--------|------|
| `turbinesFoam/validation/nacelle-asn/config/case.yaml` | Create | single source of truth (117 lines) |
| `turbinesFoam/validation/nacelle-asn/tools/generate_case.py` | Create | renderer + non-destructive `--check` (799 lines) |
| `turbinesFoam/validation/nacelle-asn/case/` | Create | 14-file committed skeleton (625 lines): `0.org/`, `constant/`, `system/` |
| `turbinesFoam/validation/nacelle-asn/README.md` | Create | setup, staged plan, metrics, closure adaptation, limitations, attribution |
| `turbinesFoam/validation/nacelle-asn/.gitignore` | Create | `runs/`, `results/`, run artefacts, `__pycache__` |
| `.gitignore` (root) | Modify | +4 lines: `validation/nacelle-asn/{runs,results}/` |
| `turbinesFoam/tests/test_nacelle_case.py` | Create | 14 pure-Python tests (292 lines) |
| `openspec/changes/nacelle-actuator-surface/tasks.md` | Modify | W4.7 partial note (checkbox stays open) |
| `openspec/changes/nacelle-actuator-surface/apply-progress.md` | Modify | W4a merged (this file) |

Commits (local only — no push, no PR; `openspec/` remains untracked as in W1–W3):

| Commit | Unit |
|--------|------|
| `a052d0d` | `feat(turbinesFoam): add nacelle validation case skeleton and renderer` (19 files, +1664) |
| `bb72be7` | `test(turbinesFoam): add nacelle case render check` (1 file, +292) |

## W4b batch — commands and observed results

W4b resumed an **interrupted W4b run**: commits `951525a` (profile probes +
renderer `--end-time`/`--start-from`), `e70f8ec` (compare/run/slurm scripts +
`tests/test_nacelle_compare.py` + README) and `002106a` (docs) already existed,
and the working tree carried two kinds of uncommitted change: **temporary
diagnostics** in `nacelleSurfaceSampler.C`/`nacelleSurfaceSource.C` (explicitly
marked "not for commit") and **two real fixes** (probe output naming,
short-window CD fallback). The diagnostics had already located a genuine
correctness bug that this batch fixed before committing anything.

### W4b task table

| Task | Status | Evidence (this batch) |
|------|--------|------------------------|
| W4.3 digitized reference + PROVENANCE | [x] (registered) | Implemented and committed as **`7cb1f3c`** but never checked off; registered here. `data/reference/` has `u_`/`k_` at 1R…19R (paper's **odd** panels; no 10R), `PROVENANCE.md` + `digitization.json` two-source cross-check, `tools/digitize_reference.py` tooling-only |
| W4.4 compare + run scripts | [x] | `e70f8ec` + repairs `1b6636a`/`9dad3ab`; plain env **28 passed**; end-to-end compare on the real stage0 run (job 11597925) |
| W4.5 slurm staging | [x] | `e70f8ec`; real stage0 submission **COMPLETED** (`sequana_cpu_dev`, job **11597925**, `ExitCode 0:0`, 1m39s); production `--test-only` on `sequana_cpu_long`, **never submitted** |
| W4.7 case + compare tests | [x] (both files now exist) | `tests/test_nacelle_case.py` (15) + `tests/test_nacelle_compare.py` (13) = **28 passed in 5.06s** in the plain env; neither in `conftest.SOLVER_DRIVEN` |
| W4.8 docs + final gate | [x] | docs commit `002106a` (root README/CHANGELOG, turbinesFoam README); final gate `./Allwmake` exit 0, `ldd -r` clean, full suite **95 passed, 1 warning** |
| (W1-scope bug fix) kernel reduction | [x] | commit **`29c6ce1`**: `interpolateVelocity()` now assigns the `returnReduce()` results; regression test added (negative control below) |

### Root cause fixed in this batch: the kernel sums were never reduced

`returnReduce()` in OpenFOAM v2506 returns a reduced **copy** — the installed
header (`OpenFOAM-v2506/src/OpenFOAM/db/IOstreams/Pstreams/PstreamReduceOps.H:317-328`)
takes `const T&` and returns `T`. `nacelleSurfaceSampler::interpolateVelocity()`
called `returnReduce(sumW, …)` / `returnReduce(sumU, …)` **discarding the
results**, so `sumW`/`sumU` stayed rank-local partial sums.

The interrupted session's diagnostics on `runs/diag48` proved it first-hand:
`reduce()` in place works (`pScalar 48`, `pVector (48 48 48)` on every rank),
while `globW == localW` on all 48 ranks. On a rank holding no cell in a node's
stencil, `sumW == 0` → the guard returned a zero velocity; ranks with cells used
their own subset average instead of the paper's Eq. 7 global kernel average.
Observed on the real coarse stage0 run **before** the fix:

```
time,fx,fy,fz,f_n_mag,f_tau_mag,cd
0.1,0,0,0,0,0,0
0.2,0,0,0,0,0,0      # every row zero — nacelle force never applied
```

After the fix (`29c6ce1`), the same stage0 run (job 11597925) reports a real
force decaying over the 2 s stability window:

```
0.1,12.03539035,-0.0008604843283,0.0007034229353,11.98645495,0.04893545114,7.661967501
1,6.501788432,-0.0002069680987,0.0009789786116,6.453048489,0.04874002456,4.139167121
2,5.214063441,-0.0001363820852,0.0009185431589,5.165527722,0.04853581358,3.319375934
```

Regression coverage: `test_parallel_master_without_stencil` translates the W1
test plate to `x = 0.85` so the whole kernel support lies in the second rank's
half of the `x = 0.5` split (the master has no stencil cell). **Negative
control:** with the discarded-return version rebuilt, that test fails with
`DESIRED: array(0.0402)`; with the fix it passes. The six pre-existing W1 tests
could not see the bug because the test flow is uniform and both ranks held
stencil cells (partial averages of a uniform field are still exact).

### Commands and observed results

| Command | Observed |
|---------|----------|
| `cd turbinesFoam && python3 -m pytest -q tests/test_nacelle_case.py tests/test_nacelle_compare.py` (plain env, `WM_PROJECT_VERSION` empty) | `28 passed in 5.06s`, exit 0 |
| `cd turbinesFoam/validation/nacelle-asn && python3 tools/generate_case.py --check` | exit 0, **no output** |
| `sh -n runNacelle.sh`; `bash -n runNacelle.sh slurm/stage0.slurm slurm/production.slurm` | all exit 0. `shellcheck` is **not installed** (`command -v shellcheck` empty), so no shellcheck run |
| `sbatch --test-only scripts/slurm/stage0.slurm` | `Job 11597923 to start at … using 48 processors … partition sequana_cpu_dev`, exit 0 |
| `sbatch --test-only scripts/slurm/production.slurm` | `Job 11597924 … partition sequana_cpu_long`, exit 0 (test-only never submits) |
| `sinfo -o "%P %a %l %D %N"` | `sequana_cpu_dev up 20:00` (166 nodes), `sequana_cpu_long up infinite` — README's documented production partition confirmed |
| `sbatch scripts/slurm/stage0.slurm` (from the package dir) | `Submitted batch job 11597925`; `squeue` → RUNNING on `sequana_cpu_dev` (sdumont6165, 48 procs); `sacct` → **COMPLETED, ExitCode 0:0, Elapsed 00:01:39**; `.out` ends `Stage 0 job finished`, `.err` only the OpenFOAM banner |
| `python3 scripts/compareNacelle.py --run-dir runs/nacelle-coarse-s0 --mesh coarse --allow-short-window` | exit **3** (acceptance). `probes: 120 points, 20 samples`; `averaging window: [60, 210] s (short, 20 samples)`; `CD = 4.47999`; acceptance FAIL at claimed stations `1R, 10R` — the tool's per-grid gate working on a 2 s unconverged stability run (expected; production is not run) |
| `python3 -m pytest -q tests/test_nacelle.py` (OpenFOAM env) | `7 passed in 9.76s` (6 existing + the new regression) |
| negative control: fix reverted, `./Allwmake`, single test | `1 failed in 3.16s` — `test_parallel_master_without_stencil` reports `DESIRED: array(0.0402)`; fix restored and rebuilt |
| `cd turbinesFoam && ./Allwmake` | exit 0, **0 errors, 0 warnings** |
| `ldd -r $FOAM_USER_LIBBIN/libturbinesFoam.so 2>&1 \| grep -i undefined` | no output (clean); `ldd … \| grep -c surfMesh` → 1 |
| `python3 -m pytest -q` (full suite, OpenFOAM env) | **`95 passed, 1 warning in 230.32s`** — the only warning is the pre-existing `pytest.mark.timeout` unknown-mark warning at `tests/test_al.py:131` |

### Corrections committed in this batch (beyond the reduction fix)

1. **Probe output directory (`1b6636a`).** OpenFOAM's `probes` function object
   derives its output directory from the **dictionary key** and ignores a
   `name` entry: the committed case wrote `postProcessing/profileSamples/`
   while `compareNacelle.py` reads `postProcessing/profiles/`. The renderer,
   committed `controlDict`, README and tests now use the `profiles` key, and a
   pure-Python test binds `PROBE_GLOB` to the committed dictionary.
2. **Short-window CD (`9dad3ab`).** `drag_coefficient()` raised `ShortWindow`
   even under `--allow-short-window`, so CD could not be formed from the only
   run stage0 may launch. It now falls back like the probe series and records
   the sample time range in `metrics.json`/`report.txt`.

### Deviations and findings vs design (W4b)

1. **W4.3 was implemented but never registered** — no code change; the
   checkbox and this table now reference `7cb1f3c`.
2. **Grid Δ resolution (W4a finding 3):** the rendered **cell counts** are
   authoritative; the package README documents spacings **derived** from them
   (`Δx ≈ R/5.1`, `Δy = Δz = R/4` coarse; `Δx ≈ R/3.8`, `Δy = Δz ≈ R/7.6`
   medium) and explicitly supersedes the exploration Δ values. No rendered file
   or script asserts `R/2.5` or `R/3.75`.
3. **Station reconciliation:** the paper's panels are at odd multiples of `R`;
   the declared `10R` stretch is bracketed by the **9R/11R** profiles and judged
   against the worse of the two. No 10R profile was invented; `metrics.json`
   records the mapping and offsets. README updated accordingly.
4. **Production partition:** documented as `sequana_cpu_long` and confirmed
   `up` by `sinfo`; `production.slurm` keeps its `NACELLE_LONG_QUEUE_AUTHORIZED`
   gate and was **not submitted** (only `--test-only`).
5. **Run-directory note:** prior stage0 artifacts from the interrupted session
   (`11597862`–`11597874`, `runs/diag48`, `runs/mini-diag`) remain as gitignored
   run data; the current run directory also holds a stale
   `postProcessing/profileSamples/` directory from the pre-fix naming next to
   the current `profiles/` (the compare tool reads the latter).
6. **The reduction bug is W1-scope** (committed in W1) and was found by the W4b
   validation run; it is fixed here as its own work unit with the regression
   test, rather than left as a partial-result report.
7. **No push, no PR, no long-queue submission** — this batch created three
   local commits only. The `single-pr` + **already-authorized `size:exception`**
   delivery decision (recorded for W1/W2/W4a) is unchanged and applies to the
   W4b commits as well.

### W4b batch — files and commits

| File | Action | Note |
|------|--------|------|
| `turbinesFoam/src/fvOptions/nacelleSurface/nacelleSurfaceSampler.C` | Modify | `sumW`/`sumU` assigned from `returnReduce()`; diagnostics removed |
| `turbinesFoam/src/fvOptions/nacelleSurface/nacelleSurfaceSource.C` | Modify | diagnostics removed (file returns to its W1 content) |
| `turbinesFoam/tests/test_nacelle.py` | Modify | `_run_with_geometry(parallel=…)` + `test_parallel_master_without_stencil` regression |
| `turbinesFoam/validation/nacelle-asn/case/system/controlDict` | Modify | probes key `profiles` (output directory) |
| `turbinesFoam/validation/nacelle-asn/tools/generate_case.py` | Modify | renders the `profiles` key |
| `turbinesFoam/validation/nacelle-asn/scripts/compareNacelle.py` | Modify | short-window force fallback + sample time range |
| `turbinesFoam/validation/nacelle-asn/README.md` | Modify | probe directory contract (W4a README stays otherwise) |
| `turbinesFoam/tests/test_nacelle_case.py` | Modify | probes-key assertion |
| `turbinesFoam/tests/test_nacelle_compare.py` | Modify | probe-glob contract + short-window force tests |
| `openspec/changes/nacelle-actuator-surface/tasks.md` | Modify | W4.3–W4.5, W4.7, W4.8 checked; W4.7 partial note replaced |
| `openspec/changes/nacelle-actuator-surface/apply-progress.md` | Modify | this W4b section (W1–W4a untouched) |

Commits (local only — no push, no PR):

| Commit | Already existed / created here | Unit |
|--------|-------------------------------|------|
| `7cb1f3c` | existed (registered now) | `feat(turbinesFoam): digitize nacelle wall-resolved-LES reference profiles` |
| `951525a` | existed | `feat(turbinesFoam): sample nacelle validation profiles in the rendered case` |
| `e70f8ec` | existed | `feat(turbinesFoam): add nacelle validation compare and staged run scripts` |
| `002106a` | existed | `docs(turbinesFoam): document the nacelle validation package and fork extensions` |
| `29c6ce1` | **created** | `fix(turbinesFoam): reduce nacelle kernel sums on every rank` |
| `1b6636a` | **created** | `fix(turbinesFoam): write nacelle probe output under profiles/` |
| `9dad3ab` | **created** | `fix(turbinesFoam): compare short force series with --allow-short-window` |



- **gmsh is usable** with `module load glu/9.0.2_gnu` + the venv interpreter
  (pip `gmsh` 4.15.2); the W1 "gmsh is not usable" note is superseded (it predated the
  `pip install gmsh` in the venv).
- **`~/venv/bin/gmsh` resolves to** `/scratch/leahk/eduardo.donestevez/venv/bin/gmsh`; the
  shim needs the venv on `PATH` and the CLI requires `-2`.
- **gmsh element order is environment-dependent** (the mesh is not): the committed STL is
  canonicalized by the generator, and `--check` now proves byte-identity in both the plain
  and the OpenFOAM environments. Any future regeneration should re-run `--check` in at
  least those two environments.
- **Pinned gmsh:** the test gates on the exact version (4.15.2). A gmsh upgrade requires
  regenerating and updating `PROVENANCE.md` + `metadata/*.json` (the version is recorded).
- MPI: 2 ranks are affordable here; `-np 4` was not needed for the W1 acceptance
  (the partition boundary `x = 0.5` is crossed at `-np 2`).
- `openspec/` is untracked in this repo; the change artifacts were **not** committed by
  any batch (only `turbinesFoam/` work units were), so the orchestrator can decide how
  to record them. Unrelated pre-existing untracked paths (`.atl/`, `odd/`, the Wind
  Energy 2024 PDF) were left untouched.
- **`Allrun` skips a run when `log.<app>` exists** (`runApplication` guard). Any manual
  baseline/re-run on a case must delete `log.pimpleFoam` (or `Allclean`) between runs or the
  solver silently does not execute — observed while preparing the W3 restart check.
- **Zero omega override is degenerate:** `axialFlowTurbineALSource::calcEndEffects()`
  (`axialFlowTurbineALSource.C:529`) divides by `mag(elementVel)` with only `mag(relVel)`
  guarded, so a stationary rotor aborts with SIGFPE. Pre-existing; out of W3 scope; fix
  candidate (guard on `mag(elementVel) > VSMALL`) for W4 or a follow-up.
- **Per-step `angleDeg.<name>` writes create checkpoint-only time directories** (no `U`/`p`)
  for cases whose write interval never lands (observed on the stock AFTAL case). Needed for
  arbitrary-time rollback, but a `startFrom latestTime` restart can pick such a directory as
  "latest". Follow-up decision: keep as-is (design §11 "harmless") or switch to
  `time_.writeTime()`/AUTO_WRITE-only persistence.
- **`startFrom latestTime` restart is azimuth-idempotent but not solver-bit-identical** for
  the ALM cases (element internal state is not persisted). Relevant if W4 compares restarted
  runs.

## Next

**S1 apply is complete:** W1–W4 (including W4b) are implemented, tested and
committed on `feat/nacelle-actuator-surface`; every task in `tasks.md` is
checked. What remains is orchestrator/user delivery, not apply work:

1. **Delivery (single PR, `size:exception`):** the session strategy is
   `single-pr` and the size exception was authorized for W1/W2/W4a; the W4b
   commits carry the same exception. Nothing has been pushed and no PR was
   opened — the orchestrator decides when to push/open the PR.
2. **Production run (only after explicit long-queue authorization):** submit
   `scripts/slurm/production.slurm` (array coarse/medium, `sequana_cpu_long`)
   and compare with `scripts/compareNacelle.py --run-dir runs/nacelle-<grid>
   --mesh <grid>`. The stage0 job already proved the mesh/stability path and
   the compare toolchain on the real case.
3. **Follow-ups carried forward (unchanged, out of S1 scope):** the W3 findings
   (zero-omega-override SIGFPE in `calcEndEffects()`, checkpoint-only time
   directories from per-step `angleDeg.<name>` writes) and S2/S3 (blade STL,
   preCICE seams).
4. **Optional cosmetic follow-up:** the stage0 run directory keeps a stale
   `postProcessing/profileSamples/` directory from a pre-fix run (gitignored);
   `runNacelle.sh` could clean `postProcessing/` on re-render if desired.

