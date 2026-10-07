# dynamicOversetZoneDisplacementFvMesh

An overset (chimera) `dynamicFvMesh` wrapper that drives **one** motion solver, so an FSI
rotor case keeps the plain `dynamicMotionSolverFvMesh` configuration while running on an
overset mesh.

Build: `./Allwmake` → `libdynamicOversetZoneDisplacementFvMesh.so`, installed to
`$FOAM_USER_LIBBIN`.

## Why this plugin exists

OpenFOAM's overset support is reached through `dynamicOversetFvMesh`, whose
`dynamicMotionSolverListFvMesh` base composes a **list** of motion solvers and accumulates
their point displacement. For an FSI rotor that means:

- the case has to be written as a `solvers { ... }` dictionary of multiple motion solvers,
- and the accumulation semantics of that list are what produce the wrong motion when the
  rotation and the solved FSI displacement have to be superimposed, not summed.

This wrapper follows the overset integration pattern of the native `dynamicOversetFvMesh` —
the same overset lifecycle, update and write behaviour — but it derives from
`dynamicMotionSolverFvMesh`, the **single**-motion-solver configuration. The result is that

```c++
dynamicFvMesh   dynamicOversetZoneDisplacementFvMesh;
motionSolver    solidBodyDisplacementLaplacianZone;
```

keeps working exactly like the non-overset case, with no `solvers { ... }` block.

> **Pending author rationale.** The paragraphs above state only what is verifiable in this
> repository: what the wrapper does and which stock component it stands in for. The author's
> own reasons for choosing this route, and any evaluation that supported it, are not written
> yet and belong here.

## Usage

The only differences from the non-overset configuration are the `dynamicFvMesh` type and the
`libs (...)` line in `controlDict`. The motion solver syntax is identical.

`constant/dynamicMeshDict`:

```c++
dynamicFvMesh   dynamicOversetZoneDisplacementFvMesh;

motionSolverLibs
(
    "libsolidBodyDisplacementLaplacianZoneFvMotionSolver.so"
    "libfvMotionSolvers.so"
    "libfsiOmega.so"
);

motionSolver    solidBodyDisplacementLaplacianZone;

solidBodyDisplacementLaplacianZoneCoeffs
{
    cellZone    bladeZone;

    solidBodyMotionFunction rotatingMotion;

    rotatingMotionCoeffs
    {
        origin  (0 0 0);
        axis    (0 1 0);
        omega   158;

        // or driven by the coupled structural solver:
        // omega   preciceOmega;
        // preciceOmegaCoeffs
        // {
        //     fieldName omega;
        // }
    }

    diffusivity inverseDistance (propellerTip);

    // displacementDecay may be used here too:
    // displacementDecay
    // {
    //     distance 0.05;
    //     patches (AMI.*);
    // }
}
```

`system/controlDict` **must** load the overset libraries, including this wrapper:

```c++
libs (overset fvMotionSolvers dynamicOversetZoneDisplacementFvMesh);
```

## Notes

- The wrapper exists to remove the `solvers { ... }` multi-motion accumulation approach from
  FSI cases.
- On overset meshes the FSI deformation stays confined to the rotation zone and does not
  propagate to acceptor cells.
- Pair it with [../solidBodyDisplacementLaplacianZone/README.md](../solidBodyDisplacementLaplacianZone/README.md)
  for the motion model itself, and with [../fsiOmega/README.md](../fsiOmega/README.md) when
  the angular velocity comes from preCICE.
