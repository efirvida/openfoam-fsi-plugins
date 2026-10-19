# solidBodyDisplacementLaplacianZone

A single mesh-motion solver for FSI of rotating machinery: it applies a *solved*
structural displacement and a rigid rotation to the same rotating zone, in one
`motionSolver`.

Build: `./Allwmake` → `libsolidBodyDisplacementLaplacianZoneFvMotionSolver.so`,
installed to `$FOAM_USER_LIBBIN`.

## Why this plugin exists

Stock OpenFOAM gives you either a prescribed rigid transform or a multi-solver list, and
neither expresses the motion of an FSI rotor in one place:

- `solidBodyMotionFvMesh` with a `solidBodyMotionFunction` (e.g. `rotatingMotion`) applies a
  **prescribed** rigid transform to the mesh. The transform is a function of time only; there
  is no input for a displacement field solved on the blade surface.
- `dynamicMotionSolverListFvMesh` (the "multibody" configuration) composes **several**
  motion solvers and accumulates their point displacement. Composing an FSI displacement
  field with a rigid rotation through that mechanism accumulates motion rather than
  superimposing it in the physical order, and it puts the case behind a `solvers { ... }`
  dictionary.

This plugin is one motion solver that does all four steps in the right order:

1. takes the structural displacement `u_fsi` from a patch,
2. diffuses it inside the rotation zone with a Laplacian,
3. applies the rigid rotation to the **deformed** zone,
4. keeps the deformation from leaking past the zone boundary and past an AMI interface.

> **Pending author rationale.** The paragraphs above state only what is verifiable in this
> repository: what the plugin does and which stock component it stands in for. The author's
> own reasons for choosing this route, and any evaluation that supported it, are not written
> yet and belong here.

## The FSI motion model

The solver implements

```text
U_total(x) = R(t) · (x + u_fsi(x)) - x
```

where

- `x` are the original point coordinates,
- `u_fsi` is the structural deformation from the FSI solver, applied on the reference patch
  named in the `inverseDistance(...)` diffusivity and propagated diffusively inside the
  rotation zone,
- `R(t)` is the rigid rotation from the configured `solidBodyMotionFunction`.

**The order of operations is the point.** The deformation is applied first and the rotation
second:

1. deform: `x' = x + u_fsi`
2. rotate: `x_final = R(t) · x'`

This is what a real blade does: it deflects under aerodynamic load, and the already-deformed
blade then rotates.

The Laplacian diffusion (`div(gamma nabla U) = 0`) propagates `u_fsi` from the reference patch
through the rotation zone. Cells at the zone boundary are pinned to zero displacement so the
deformation cannot diffuse outside the zone. On overset meshes the deformation stays confined
to the rotation zone and does not reach acceptor cells.

## Zone selection

| Input | Effect |
| --- | --- |
| `cellZone <name>` | the named cell zone rotates rigidly; the rest of the mesh deforms |
| `cellSet <name>` | same, selected by cell set |
| neither | the rigid transform is applied to the full mesh |

Use one or the other, never both.

## AMI protection

### `boundaryDecay` diffusivity

With AMI meshes, a non-linear diffusivity function can propagate deformation all the way to
the AMI boundary and break the interface connectivity. `boundaryDecay` wraps any existing
diffusivity chain and ramps it to zero near the selected patches:

```text
patch AMI        decayDistance          interior
   |                 |
   |  D=0  --smooth--  D=D_base
   |                 |
```

```c++
diffusivity  boundaryDecay 0.05 (AMI.*) quadratic inverseDistance (blade);
```

| Parameter | Example | Description |
| --- | --- | --- |
| `decayDistance` | `0.05` | distance (m) from the AMI where the diffusivity ramps from 0 to 1 |
| `patchNames` | `(AMI.*)` | regex matching the AMI boundary patches |
| `baseDiffusivity` | `quadratic inverseDistance (blade)` | any existing `motionDiffusivity` chain |

The decay factor is a quintic smooth-step (`6x^5 - 15x^4 + 10x^3`), so it is C2 continuous
(zero first and second derivatives) at both ends of the transition.

### `displacementDecay` clamping

`boundaryDecay` keeps the deformation from *reaching* the AMI, but the `cyclicAMI` boundary
condition can still interpolate non-zero displacement back onto AMI points during
`correctBoundaryConditions()`. `displacementDecay` clamps the solved displacement afterwards,
guaranteeing zero motion at the interface:

```c++
displacementDecay
{
    distance  0.05;      // decay length (m)
    patches   (AMI.*);   // regex matching the boundary patches
}
```

| Parameter | Example | Description |
| --- | --- | --- |
| `distance` | `0.05` | distance (m) from the patches over which the displacement ramps 0 → 1 |
| `patches` | `(AMI.*)` | regex matching the patches near which to clamp |

Behaviour:

- points/cells **outside** the rotation zone: displacement set to exactly zero;
- points/cells **inside** the zone: quintic smooth-step decay over `distance`, measured from
  the patches with `patchWave`;
- applied after `correctBoundaryConditions()` in `curPoints()` and after the solve in
  `solve()`, so `cyclicAMI` interpolation cannot reintroduce non-zero displacement at the
  interface;
- skipped in `moveAllCells` mode (no zone selected).

## Full example (non-overset)

`constant/dynamicMeshDict`:

```c++
dynamicFvMesh   dynamicMotionSolverFvMesh;

motionSolverLibs
(
    "libsolidBodyDisplacementLaplacianZoneFvMotionSolver.so"
    "libfvMotionSolvers.so"
);

motionSolver    solidBodyDisplacementLaplacianZone;

solidBodyDisplacementLaplacianZoneCoeffs
{
    // use cellZone OR cellSet, not both
    cellZone    rotorZone;
    // cellSet  rotorCells;

    solidBodyMotionFunction rotatingMotion;

    rotatingMotionCoeffs
    {
        origin  (0 0 0);
        axis    (0 1 0);
        omega   158;   // rad/s, or any Function1<scalar>
    }

    diffusivity quadratic inverseDistance (rotorTip);

    // for AMI meshes, wrap the chain to protect the interface:
    // diffusivity boundaryDecay 0.05 (AMI.*) quadratic inverseDistance (rotorTip);

    // optionally clamp the displacement near the AMI after the solve:
    // displacementDecay
    // {
    //     distance 0.05;
    //     patches (AMI.*);
    // }
}
```

`system/controlDict` must load the standard motion libraries:

```c++
libs (fvMotionSolvers);
```

## Driving the rotation from an FSI solver

Set `omega` to the `preciceOmega` Function1 so the angular velocity comes from the coupled
structural solver instead of a constant:

```c++
rotatingMotionCoeffs
{
    origin  (0 0 0);
    axis    (0 1 0);
    omega   preciceOmega;

    preciceOmegaCoeffs
    {
        fieldName   omega;   // must match nameOmegaField in preciceDict
    }
}
```

That requires `"libfsiOmega.so"` in `motionSolverLibs`. See
[../fsiOmega/README.md](../fsiOmega/README.md) for the contract, and
[../dynamicOversetZoneDisplacementFvMesh/README.md](../dynamicOversetZoneDisplacementFvMesh/README.md)
for the overset variant.
