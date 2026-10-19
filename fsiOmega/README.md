# fsiOmega

A `Function1<scalar>` that reads the rotor angular velocity from a
`uniformDimensionedScalarField`, so any OpenFOAM dict that accepts a `Function1` can be driven
by an external FSI solver through preCICE.

Build: `./Allwmake` → `libfsiOmega.so`, installed to `$FOAM_USER_LIBBIN`.

## Why this plugin exists

OpenFOAM ships many `Function1` types (`constant`, `table`, `polynomial`, `coded`, ...) but
none that reads a field from the object registry at run time. The preCICE adapter publishes
coupled scalars as `uniformDimensionedScalarField` objects in the `Time` registry, so a
`Function1` is needed that resolves that field by name and returns its current value. That is
the whole job of this plugin: it is the bridge between *"the adapter wrote an angular
velocity"* and *"`rotatingMotion` consumes an `omega`"*.

> **Pending author rationale.** The paragraphs above state only what is verifiable in this
> repository: what the plugin does and which stock component it stands in for. The author's
> own reasons for choosing this route, and any evaluation that supported it, are not written
> yet and belong here.

## Data flow

```text
External solver (MBDyn, structural FEM, AeroElast, ...)
        |
        v
preCICE (coupling library)
        |
        v
OpenFOAM adapter (writes the coupled scalar)
        |
        v
uniformDimensionedScalarField "omega"  (Time registry)
        |
        v
preciceOmega Function1
        |
        v
solidBodyMotionFunction rotatingMotion  ->  mesh motion
```

## The name contract

`fieldName` must match the field the adapter writes:

| Side | Key |
| --- | --- |
| `preciceDict` (adapter) | `nameOmegaField` |
| `dynamicMeshDict` (this plugin) | `preciceOmegaCoeffs { fieldName ...; }` |

The example throughout this repository uses `omega` on both sides.

## Usage

Add the library to `motionSolverLibs` and replace the `omega` value:

```c++
motionSolverLibs
(
    "libsolidBodyDisplacementLaplacianZoneFvMotionSolver.so"
    "libfvMotionSolvers.so"
    "libfsiOmega.so"
);

solidBodyDisplacementLaplacianZoneCoeffs
{
    cellZone    bladeZone;

    solidBodyMotionFunction rotatingMotion;

    rotatingMotionCoeffs
    {
        origin  (0 0 0);
        axis    (0 1 0);

        omega   preciceOmega;

        preciceOmegaCoeffs
        {
            // Name of the field updated by the preCICE adapter.
            // Must match nameOmegaField in preciceDict.
            fieldName   omega;
        }
    }
}
```

This works with **both** non-overset (`dynamicMotionSolverFvMesh`) and overset
(`dynamicOversetZoneDisplacementFvMesh`) configurations — see
[../solidBodyDisplacementLaplacianZone/README.md](../solidBodyDisplacementLaplacianZone/README.md)
and
[../dynamicOversetZoneDisplacementFvMesh/README.md](../dynamicOversetZoneDisplacementFvMesh/README.md).

## Notes on ownership

The field is created by whoever registers it first: the adapter creates its own
in-memory `uniformDimensionedScalarField` (`constant()`, `NO_READ`, `NO_WRITE`) when the field
does not exist yet, and this `Function1` only reads it. A case that makes another component
create the same field first changes the field's IO flags — see
[../precice-openfoam-adapter/README.md](../precice-openfoam-adapter/README.md).
