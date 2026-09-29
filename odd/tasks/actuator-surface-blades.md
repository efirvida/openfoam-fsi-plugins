# Feature: blade actuator surface model (ASM)

- **Status:** superseded by the SDD change `actuator-surface-model` (archived 2026-09-19, `openspec/changes/archive/2026-09-19-actuator-surface-model/`). The delivered implementation follows the polymorphic-element design; this document remains as input context.
- **Branch:** `feat/asm-blade-surface` (from `main`)
- **Created:** 2026-09-18
- **Reference:** Yang & Sotiropoulos, *A new class of actuator surface models for wind turbines*, arXiv:1702.02108v4 (2018)

## Objective

Add an optional **blade actuator surface model (ASM)** to the existing actuator line
elements in `turbinesFoam/`, and deliver a HAWT tutorial based on
`tutorials/axialFlowTurbineAL/` configured for ASM plus a script to compare its
results against the ALM run.

## Problem / Why

- The current implementation distributes the blade-element force from a **line** with a
  single sample point per radial station (ALM). It cannot resolve chordwise flow features
  and the load width is tied to the chord (`epsilon = max(0.25c, mesh)`).
- The paper's blade ASM computes the same BEM loads but distributes them **uniformly over
  the surface formed by the chord lines**, with the relative velocity **averaged over the
  chord** (Eqs. 3-8, 17-18). This resolves more geometry and couples better to finer meshes.
- The vendored fork has no surface capability (verified: no `actuatorSurface*` code, no
  directional epsilon variants).

## Scope

**In scope**

- `surfaceModel` mode on `actuatorLineElement`, config keys `surfaceModel` (bool, default
  false) and `nChordwise` (label, default 5), plumbed through
  `actuatorLineSource::createElements`. Works for standalone lines and for all turbines
  (AFTAL/CFTAL inject the user blade subdict into the blade source unchanged).
- Chord-averaged inflow sampling: midpoint rule over `nChordwise` equal strips.
- Uniform chordwise force distribution: each strip carries `forceVector_/nChordwise`.
- Surface-mode projection width: mesh-based `epsilon` only.
- Integration tests for the static actuator-line case and for a HAWT case in ASM mode.
- ASM HAWT tutorial + comparison script against the ALM tutorial + docs.

**Out of scope (follow-ups, do not implement now)**

- Nacelle ASM (paper Sec. 2.2) and the empty `createNacelle` path of AFTAL.
- The paper's exact 3D smoothed-cosine delta kernel (Yang et al. 2009). We reuse the
  existing Gaussian projection and document the adaptation.
- Root-loss model; MEXICO validation (geometry is not in the paper).

## Authorized scope

- `turbinesFoam/` (source, tests, tutorials, its README) and root `README.md` /
  `CHANGELOG.md`. `odd/tasks/` for this document. No other plugin may be touched.
- No push, no PR. Commits only as work units on `feat/asm-blade-surface`.

## Model mapping (paper -> code)

| Paper | Code |
| --- | --- |
| Chord surface from radial stations | Chord line per element: `X_k = position_ + (chordMount_ - f_k) * c * unit(chordDirection_)`, `f_k = (k+0.5)/n`, `k = 0..n-1` |
| Chord-averaged `u_x`, `u_theta` (Eqs. 5-6) | Arithmetic mean of `interpolationCellPoint` samples at `X_k` |
| `f(X) = (L+D)/c` uniform chordwise (Eq. 17) | Strip force `forceVector_/nChordwise_` at each `X_k` |
| Delta kernel (Eq. 8, 5-cell cosine) | Existing 3D Gaussian (adaptation), `epsilon = 2*cbrt(V)*meshFactor` |
| Spreading (Eq. 18, area weights) | Per-strip Gaussian spreading; total force preserved by construction |
| Tip loss (Eqs. 13-16) | Existing end effects (Glauert/Shen/lifting line) unchanged |
| 3D stall delay (Eqs. 9-12) | Existing dynamic stall / profile corrections unchanged |

## Design decisions (rationale)

1. **Extend `actuatorLineElement`, no new classes.** All BEM physics, corrections, CSV
   output, turbine composition, and the `option` RTS registration are reused; the ALM path
   is untouched when `surfaceModel` is off (default). A separate element class would
   duplicate ~1k lines because the class is non-virtual and has no working `New`.
2. **Config at line/blade level**, copied into each element dict (same pattern as
   `velocitySampleRadius`/`nVelocitySamples`). AFTAL/CFTAL pass arbitrary blade subdict
   keys through, so no turbine changes are required.
3. **Surface mode takes precedence over `velocitySampleRadius_`** circle sampling.
4. **Surface-mode epsilon is mesh-based only**; chord-based thresholds would prevent the
   model from resolving the chord on fine meshes (the point of the surface model).
5. **One cell pass per element** with an inner chord-point loop, not one full mesh pass
   per chord point, to bound the cost increase to ~nChordwise x candidates.
6. **MPI patterns preserved**: `reduce(..., minOp)` sentinels, bounding-box `findCell`,
   fatal on unreachable samples.

## Tasks

- [ ] **T1 - Core surface mode + integration test (static AL case)**
  - Files: `actuatorLineElement.{H,C}`, `actuatorLineSource.C` (`createElements`),
    new `tests/test_asm.py`.
  - Acceptance: keys accepted; surface mode samples chord-averaged velocity and spreads
    `forceVector_/n` from chord points; mesh-based epsilon; ALM default behavior
    unchanged; build clean; `test_asm.py` passes; `tests/test_al.py` regression passes.
  - Evidence: build log, pytest results, smoke-run outputs.
- [ ] **T2 - HAWT ASM tutorial + comparison script + HAWT test + docs**
  - Files: `tutorials/axialFlowTurbineASM/` (copy of AFTAL case with ASM blade config),
    comparison script, `tests/test_aftal_asm.py`, `turbinesFoam/README.md`, root
    `README.md`, root `CHANGELOG.md`.
  - Acceptance: truncated ASM case runs and writes turbine/element CSVs; comparison script
    produces ALM-vs-ASM side-by-side output from two run directories; test passes.
- [ ] **T3 - Verification and comparison evidence**
  - Full relevant pytest suite; short ALM-vs-ASM run; record actual numbers and
    limitations (short, not converged; no experimental validation data available).

## Verification

- Build (see recipe below): `./Allwmake` exit 0, no new warnings (baseline: 0 errors,
  54 compiler warnings, 0 linker warnings with the corrected recipe).
- `python -m pytest tests/ -q` (or the relevant subset) with the module environment loaded.
- Short HAWT runs (ALM vs ASM) + comparison script output recorded as evidence.

## Build recipe (verified 2026-09-18, baseline)

```sh
module load openfoam/v2506_openmpi-4.1.4_gnu
export WM_ARCH=linux64 WM_COMPILER=Gcc WM_COMPILE_OPTION=Opt
export WM_PRECISION_OPTION=DP WM_LABEL_SIZE=64
export WM_OPTIONS=linux64GccDPInt64Opt
export FOAM_USER_LIBBIN=$WM_PROJECT_USER_DIR/platforms/$WM_OPTIONS/lib
export LD_LIBRARY_PATH=$FOAM_USER_LIBBIN:$WM_PROJECT_DIR/platforms/$WM_OPTIONS/lib:$WM_PROJECT_DIR/platforms/$WM_OPTIONS/lib/sys-openmpi:$LD_LIBRARY_PATH

cd turbinesFoam && ./Allwmake
```

Note: the repo `AGENTS.md` recipe is missing `$WM_PROJECT_DIR/platforms/$WM_OPTIONS/lib`
in `LD_LIBRARY_PATH`; without it the link emits 12 warnings and `ldd -r` fails. Documented
as a follow-up, not fixed in this feature.

## Delivery

- Work-unit commits on `feat/asm-blade-surface`, Conventional Commits, no AI attribution,
  tests and docs with the behavior.
- Push / PR are the user's decision. Forecast: T1 ~300 authored lines; T2 (tutorial copy +
  script + test + docs) likely pushes the accumulated branch over the ~400-line budget;
  natural PR slices if requested: [T1], [T2].
- RDD: off (global). Verification follows the delegated verification gate.

## Progress / Evidence

| Task | Status | Evidence |
| --- | --- | --- |
| Baseline build | done | `./Allwmake` exit 0, `libturbinesFoam.so` produced; recipe above |
| T1 | pending | - |
| T2 | pending | - |
| T3 | pending | - |

## Next step

T1: implement surface mode in `actuatorLineElement` + plumbing + `tests/test_asm.py`.
