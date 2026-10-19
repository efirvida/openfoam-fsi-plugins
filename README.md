# openfoam-fsi-plugins

OpenFOAM plugins for FSI of rotating machinery — mesh motion, overset meshes, preCICE
coupling and actuator-based turbine loading — as independent plugins built with `wmake`.

![OpenFOAM](https://img.shields.io/badge/OpenFOAM-v2406%E2%80%93v2512-brightgreen)
![preCICE](https://img.shields.io/badge/preCICE-v3-blue)
![License](https://img.shields.io/badge/License-GPL--3.0--or--later-green)

## What this repository is for

This repository is the **CFD side of [AeroElast](https://github.com/efirvida/AeroElast)**.
AeroElast is a structural and aeroelastic toolkit for wind-turbine blades and rotor FSI, and it
ships its own turbine fluid solver based on CCBLADE. This repository is the OpenFOAM
scaffolding that couples the same structural model to a full CFD solver instead.

It is **not restricted to AeroElast**. Every coupling boundary here is preCICE, so the
structural participant can be any preCICE participant — AeroElast, MBDyn, an in-house FEM
solver, or another OpenFOAM case. AeroElast is the reason this repository exists, not a
dependency of it: nothing here links against AeroElast, and the plugins are useful on their
own.

## The five pieces

| Component | What it does | Where it is loaded |
| --- | --- | --- |
| [`solidBodyDisplacementLaplacianZone`](solidBodyDisplacementLaplacianZone/README.md) | one motion solver: applies the solved FSI displacement and rotates the zone rigidly, deform-then-rotate, with AMI protection | `motionSolver` in `dynamicMeshDict` |
| [`dynamicOversetZoneDisplacementFvMesh`](dynamicOversetZoneDisplacementFvMesh/README.md) | overset (chimera) wrapper that drives that single motion solver | `dynamicFvMesh` in `dynamicMeshDict` |
| [`fsiOmega`](fsiOmega/README.md) | `Function1<scalar>` that reads the angular velocity published by the adapter | `omega` in `rotatingMotionCoeffs` |
| [`precice-openfoam-adapter`](precice-openfoam-adapter/README.md) | FSI-only fork of the OpenFOAM–preCICE adapter: exchanges forces and displacements | `functions` in `controlDict` |
| [`turbinesFoam`](turbinesFoam/README.md) | actuator-line and actuator-surface `fvOptions` adding turbine loading to any compatible solver | `fvOptions` |

No git submodules: every component is a plain directory in this repository.

Uniform-inflow validation package for the NREL/NASA-Ames Phase VI rotor with
three models: ALM, the no-mesh ASM and the mesh-backed ASM over the imported
`phaseVI_blade` surface. A YAML single source of truth renders an 18-block hex
case at D/32 (6.67 M cells), D/48 (22.5 M) or D/64 (53.4 M), with per-speed
measured TSR kinematics, the ALM/ASM/ASM-MESH `fvOptions` twins, committed WDH
experimental anchors and per-directory data provenance.

- `scripts/runPhaseVI.sh` prepares/runs/submits one variant (staging the
  hash-checked blade STL for `-m asm-mesh`) and enforces the queue gates;
  `scripts/comparePhaseVI.py` merges simulation output with the measured rows
  three ways and writes the spanwise/turbine comparisons, `metrics.json`, and
  the 7 m/s sign gate.
- Staged plan: Stage 0 (mesh check + ≤ 0.3 revolution 7 m/s stability runs on
  `sequana_cpu_dev`) is the only authorized execution; Stages 1–3 and the
  ASM-mesh array (7 m/s D/32 performance gate then D/48 headline) are prepared
  but **must not be submitted** until the long-queue authorization is granted.
- The mesh-backed variant tests model form, not resolved chordwise physics: at
  every affordable mesh the imported surface is sub-grid, and the Gaussian
  kernel is documented as an ablation of the kernel/width confound.
- **Rotational augmentation (Du–Selig 3D stall delay):** the shared actuator
  element chain supports an additive, default-off `rotationalAugmentation` block
  (`model DuSelig`, `a=b=d=1`; original Du & Selig 1998 prefactor form, the
  equations Yang & Sotiropoulos reproduce as Eqs. 9–12) inherited by ALM,
  ASM and the mesh surface. It is enabled for the Phase VI proxy through
  `--rotational-augmentation on`, never by the committed case. The correction is
  applied literally with no invented clamp and no free-parameter calibration;
  claims are limited to **trend, stall onset and agreement within the documented
  comparison bands** — no agreement better than those bands is promised a priori.
- See [turbinesFoam/validation/phaseVI/README.md](turbinesFoam/validation/phaseVI/README.md)
  for setup, metric definitions, tolerance bands, the pre-registered hypothesis
  and the modelling limitations.

## Nacelle actuator-surface validation (`turbinesFoam/validation/nacelle-asn/`)

Periodic-nacelle benchmark for the fork's nacelle/hub actuator surface model
(Yang & Sotiropoulos, *A new class of actuator surface models for wind
turbines*, [arXiv:1702.02108v4](https://arxiv.org/abs/1702.02108v4), Sec. 4.1).
A rotor-less hemisphere + cylinder nacelle at Re = 1000 in a
30R x 20R x 20R streamwise-periodic cell, represented **only** by the
`nacelleSurfaceSource` (no body-fitted mesh): the source distributes the surface
force onto the background grid.

- `config/case.yaml` is the single source of truth; `tools/generate_case.py`
  renders and non-destructively checks the committed `case/` skeleton for the
  paper's coarse (153x80x80) and medium (115x151x151) grids. The case probes the
  metric-station lines every time step.
- `scripts/compareNacelle.py` compares a run with the digitized
  wall-resolved-LES profiles (`data/reference/`, with `PROVENANCE.md`): the
  time-averaged `⟨u⟩(z)`, the resolved TKE `k(z)` and
  `CD = |F_drag| / (0.5 ρ U∞² πR²)` at `1R/3R/5R/7R` plus the `10R` stretch
  (bracketed by the `9R`/`11R` panels — the paper has no `10R` panel). The
  paper's permeable-disk `CD = 0.48` is a datum, not a target.
- Acceptance is per station and per grid: medium agrees at all stations, coarse
  only at `1R` and the far wake. `scripts/runNacelle.sh` enforces the queue
  gates; `scripts/slurm/stage0.slurm` (dev partition) is the only authorized
  execution and `production.slurm` (long queue) is **prepared only**.
- **Closure adaptation:** the paper's dynamic SGS model is not available in
  standard OpenFOAM, so the headline closure is LES **WALE** (documented) with a
  URANS k-ω SST smoke fallback. The nacelle is represented only by the actuator
  surface: no resolved boundary layer, and only wake profiles and integral drag
  are claimed.
- **Fork divergence:** new source class (`nacelleSurfaceSource` /
  `nacelleSurfaceSampler`), the new `geometry/` tree and the
  `validation/nacelle-asn/` package are not part of upstream turbinesFoam.
- See [turbinesFoam/validation/nacelle-asn/README.md](turbinesFoam/validation/nacelle-asn/README.md)
  for setup, the staged run plan, the sampling/station contract and the
  limitations.

## Why these plugins and not the alternatives

Four stock or upstream components are replaced here. For each one, what is verifiable in this
repository:

| Stands in for | Capability the stock component does not cover | Details |
| --- | --- | --- |
| `solidBodyMotionFvMesh` with a `solidBodyMotionFunction`, and the `dynamicMotionSolverListFvMesh` "multibody" list | one motion solver that takes a *solved* FSI displacement, diffuses it with a Laplacian, and rotates the **deformed** zone in that order, keeping the deformation off the zone boundary and off the AMI | [README](solidBodyDisplacementLaplacianZone/README.md) |
| `dynamicOversetFvMesh` (whose list-of-motion-solvers base accumulates several movers) | the same overset lifecycle driven by a **single** motion solver, so an FSI case needs no `solvers { ... }` accumulation | [README](dynamicOversetZoneDisplacementFvMesh/README.md) |
| a stock `Function1<scalar>` (`constant`, `table`, `polynomial`, …) | reads the coupled angular velocity from the registry field the adapter writes | [README](fsiOmega/README.md) |
| the upstream preCICE adapter and upstream turbinesFoam | an FSI-only adapter with local FSI changes, and a turbinesFoam fork with an actuator-surface extension | [adapter](precice-openfoam-adapter/README.md), [turbinesFoam](turbinesFoam/README.md) |

> **Pending author rationale.** The table above states only capability differences that are
> verifiable in this repository. It is **not** a benchmark, and it is not an evaluation of
> these alternatives against the plugins. The author's reasoning for each choice, and any
> measurements behind it, are not written yet and belong in this section.

## Quick start

### Requirements

- OpenFOAM (.com line, tested with v2406–v2512) with a loaded build environment:
  `wmake` in `PATH`, `WM_PROJECT_DIR` and `FOAM_USER_LIBBIN` set.
- Optional, for the preCICE adapter: preCICE development files discoverable by
  `pkg-config libprecice`.

### Build

```sh
./Allwmake                  # all plugins, serial
WM_NCOMPPROCS=4 ./Allwmake  # parallel
./Allclean                  # clean
```

The root `Allwmake` builds all five plugins into `$FOAM_USER_LIBBIN`:

- `libsolidBodyDisplacementLaplacianZoneFvMotionSolver.so`
- `libdynamicOversetZoneDisplacementFvMesh.so`
- `libfsiOmega.so`
- `libpreciceAdapterFunctionObject.so` (warns but continues when preCICE's `pkg-config` file is
  missing)
- `libturbinesFoam.so`

Each plugin can also be built on its own; see its README.

## Documentation

| Topic | Document |
| --- | --- |
| The FSI motion model and the deform-then-rotate order | [`solidBodyDisplacementLaplacianZone/README.md`](solidBodyDisplacementLaplacianZone/README.md) |
| AMI protection (`boundaryDecay`, `displacementDecay`) | [`solidBodyDisplacementLaplacianZone/README.md`](solidBodyDisplacementLaplacianZone/README.md) |
| Overset configuration | [`dynamicOversetZoneDisplacementFvMesh/README.md`](dynamicOversetZoneDisplacementFvMesh/README.md) |
| The angular-velocity contract with the adapter | [`fsiOmega/README.md`](fsiOmega/README.md) |
| The adapter fork and its divergence | [`precice-openfoam-adapter/README.md`](precice-openfoam-adapter/README.md), [`docs/`](precice-openfoam-adapter/docs/) |
| The turbine models and their fork extensions | [`turbinesFoam/README.md`](turbinesFoam/README.md) |
| NREL Phase VI validation package | [`turbinesFoam/validation/phaseVI/README.md`](turbinesFoam/validation/phaseVI/README.md) |
| Change history and provenance | [`CHANGELOG.md`](CHANGELOG.md) |
| Build environment gotchas, layout and contributor conventions | [`AGENTS.md`](AGENTS.md) |

## Validation

[`turbinesFoam/validation/phaseVI/`](turbinesFoam/validation/phaseVI/README.md) is the
uniform-inflow validation package for the NREL/NASA-Ames Phase VI rotor with the actuator-line
(ALM) and actuator-surface (ASM) models: a YAML single source of truth renders the case at
D/32, D/48 or D/64 with per-speed measured TSR kinematics, committed experimental anchors and
per-directory provenance. Its staged run plan is part of the package.

## Status

Research prototype, developed against a moving OpenFOAM and preCICE. Interfaces and case
dictionaries are not frozen.

The actuator-surface extensions of `turbinesFoam` — the mesh-backed blade surface over an
imported triangulation, the nacelle actuator-surface model, the `geometry/` pipeline and their
validation packages — are developed on the `feat/nacelle-actuator-surface` branch and are not
on `main` yet.

## License

GPL-3.0-or-later, the same family as OpenFOAM user-extension code. The vendored components keep
their upstream licences: `turbinesFoam/LICENSE` and `precice-openfoam-adapter/LICENSE`.
