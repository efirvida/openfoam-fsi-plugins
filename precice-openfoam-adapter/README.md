# OpenFOAM–preCICE adapter (FSI-only fork)

> **Fork notice.** This directory is an **independent, diverging copy** of
> [precice/openfoam-adapter](https://github.com/precice/openfoam-adapter), vendored here as a
> plain directory (no git submodule). Changes made here are not synced upstream
> automatically, and the badges, community links and maintenance statements of the upstream
> README do not describe this copy. Read the two sections below first.

## What this copy is for

It is the coupling side of this repository's FSI stack: it exchanges forces and displacements
with an external structural solver through preCICE, and it publishes coupled scalars (such as
the angular velocity) as `uniformDimensionedScalarField` objects in the OpenFOAM registry.

This is also the component that makes the whole repository solver-agnostic: the coupling
contract is preCICE, so the structural participant can be any preCICE participant, not
[the one this repository was originally written for](../README.md).

## Fork divergence

**Removed** to make this an FSI-only adapter:

- the CHT (conjugate heat transfer) module,
- the FF (free-surface) module,
- the `Stress` and `DisplacementDelta` coupling-data modules of the FSI module.

**Kept and modified:**

- `modules/FSI/` (`Force`, `ForceBase`, `Displacement`) and `modules/generic/`
  (`Generic`, `ReadWrite`) are the surviving coupling paths.
- OpenFOAM v2506 fix: the deprecated `Pstream::scatterList` / `gatherList` are replaced with
  `OPstream` / `IPstream`.
- `Interface.C` carries `fsiDiagLog` diagnostics for every READ/WRITE of coupling data.
- The generic module's global scalar coupler is the **producer** of the
  `uniformDimensionedScalarField` that [`fsiOmega`](../fsiOmega/README.md) reads and that the
  motion solver consumes. Note its IO flags: it creates the field only when the field does not
  exist yet, with `constant()`, `NO_READ` and `NO_WRITE`, and otherwise binds to the existing
  object with `lookupObjectRef`.

> **Pending author rationale and divergence list.** The fork's delta against upstream is **not
> enumerated anywhere yet**: `changelog-entries/*.md` holds *upstream* PR entries (338…394),
> not this fork's changes. Diffing the vendored snapshot against its upstream pin is the way
> to produce the complete list, and the author's reasons for maintaining a fork instead of
> upstreaming belong in this section.

## Build

Requires preCICE development files discoverable through `pkg-config`:

```sh
cd precice-openfoam-adapter && ./Allwmake
```

- `pkg-config libprecice` is resolved automatically; a missing `.pc` file is a **warning**, not
  an error.
- `Allwmake` fails on any `error:` line in `wmake.log` and then runs `ldd -r`, so undefined
  symbols fail the build.

| Variable | Effect |
| --- | --- |
| `PRECICE_OPENFOAM_CFLAGS` | extra preprocessor flags, e.g. `-DADAPTER_DEBUG_MODE` |
| `PRECICE_OPENFOAM_TARGET_DIR` | install destination (default `$FOAM_USER_LIBBIN`) |

On SDumont, the preCICE installation is built with GCC 14, so the matching `libstdc++` must be
on the runtime search path at link and `ldd -r` time: prepend `/scratch/app/gcc/14.2.0/lib64`
to `LD_LIBRARY_PATH` or the adapter reports undefined `GLIBCXX_3.4.32` / `CXXABI_1.3.15`.

## Documentation and contributing

Upstream documentation applies and is vendored under [`docs/`](docs/):
[`config.md`](docs/config.md) for `preciceDict`, [`extend.md`](docs/extend.md) to add modules,
[`openfoam-support.md`](docs/openfoam-support.md) for the version matrix. The project overview
is at <https://precice.org/adapter-openfoam-overview.html>.

Adapter changes follow [`CONTRIBUTING.md`](CONTRIBUTING.md): add
`changelog-entries/<PR-number>.md` and never edit `CHANGELOG.md` directly — entries are merged
at release.

## Citing

Whenever using or referring to this adapter in academic publications, please cite it [1]. See
the option "Cite this repository" in the "About" section, as well as the
[preCICE literature guide](https://precice.org/fundamentals-literature-guide.html) and the
[adapter overview page](https://precice.org/adapter-openfoam-overview.html) for more
information.

## References

[1] Chourdakis, G., Schneider, D., & Uekermann, B. (2023). OpenFOAM-preCICE: Coupling OpenFOAM
with External Solvers for Multi-Physics Simulations. OpenFOAM® Journal, 3, 1–25.
[DOI: 10.51560/ofj.v3.88](https://doi.org/10.51560/ofj.v3.88)

## Disclaimer

This offering is not approved or endorsed by OpenCFD Limited, producer and distributor of the
OpenFOAM software via www.openfoam.com, and owner of the OPENFOAM® and OpenCFD® trade marks.
