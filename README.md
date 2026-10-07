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
