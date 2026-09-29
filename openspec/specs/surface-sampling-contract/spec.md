# Surface Sampling Contract Specification

## Purpose

Defines the stable sampling-object contract of the reusable surface-sampling
object owned by `nacelleSurfaceSource`. The object exposes `positions()`,
`forces()`, `normals()`, and `areas()` in SI units, in the body frame, with a
force-on-body sign convention and a stable node ordering, and registers its
force following the existing `force.<name>` `volVectorField` precedent. This
contract is the S3 FSI seam host: it is designed so a future preCICE point-cloud
mesh source can map forces to surface nodes deterministically, without any
adapter change in S1.

## Requirements

### Requirement: Accessor contract

The sampling object MUST expose `positions()`, `forces()`, `normals()`, and
`areas()` accessors. `positions()` MUST return the node positions, `forces()`
the per-node force vectors, `normals()` the per-node unit normals, and `areas()`
the per-node area weights, all indexed over the same node set.

#### Scenario: Accessors return aligned node data

- GIVEN a sampling object initialized from an STL surface
- WHEN `positions()`, `forces()`, `normals()`, and `areas()` are called
- THEN each returns one entry per node over the same ordering

### Requirement: SI units

All quantities exposed by the sampling object MUST be reported in SI units —
metres for positions, newtons for forces, square metres for areas — consistent
with OpenFOAM's dimensional units, without unit conversion at the boundary.

#### Scenario: Units are SI

- GIVEN a sampling object
- WHEN the exposed positions, forces, and areas are inspected
- THEN they are in metres, newtons, and square metres respectively

### Requirement: Body frame

`positions()` and `forces()` MUST be reported in the body frame of the owning
body, not the global mesh frame. For the static nacelle this remains the nacelle
body frame. For the blade implementation the body frame is the blade-local frame
that rotates with the rotor, so `positions()` are azimuth-dependent while
remaining the same node set.
(Previously: only the static nacelle body frame existed.)

#### Scenario: Nacelle body-frame coordinates

- GIVEN a nacelle whose body frame is offset and rotated relative to the global mesh frame
- WHEN `positions()` is called
- THEN the returned node coordinates are in the nacelle body frame

#### Scenario: Blade body frame rotates

- GIVEN a blade sampling object at two different azimuths
- WHEN `positions()` is called at each azimuth
- THEN the coordinates are expressed in the rotating blade-local frame and reflect the azimuth

### Requirement: Force-on-body sign convention

`forces()` MUST report the force ON the body (the reaction force applied to the
nacelle), with a consistent sign convention, matching the force a future
structure-coupling would apply back to the body.

#### Scenario: Force is on the body

- GIVEN an incoming flow impinging on the nacelle surface
- WHEN `forces()` is called
- THEN the returned vectors represent the force on the nacelle with a consistent, documented sign

### Requirement: Stable node ordering

The node ordering returned by `positions()`, `forces()`, `normals()`, and
`areas()` MUST be stable across time steps and across runs for the same input
surface, including under rotation: the ordering MUST be fixed at initialization
from the input surface and MUST NOT depend on azimuth, so a later point-cloud
mesh source can map forces to positions deterministically.
(Previously: stability was stated only for a static surface.)

#### Scenario: Ordering stable across time steps

- GIVEN the same sampling object across consecutive time steps
- WHEN `positions()` and `forces()` are called each step
- THEN the node ordering is identical at every step

#### Scenario: Ordering stable across runs

- GIVEN two runs initialized from the same STL surface
- WHEN their `positions()` results are compared
- THEN the node ordering matches

#### Scenario: Ordering stable under rotation

- GIVEN a rotating blade sampling object over a revolution
- WHEN the node orderings at different azimuths are compared
- THEN the ordering is unchanged and only the coordinates rotate

### Requirement: Registry exposure following the `force.<name>` precedent

The sampling object's force MUST be registered as a named object following the
existing `force.<name>` `volVectorField` precedent, written with
`IOobject::AUTO_WRITE`, so downstream consumers (including the adapter's
`globalData` interface) can read it. The per-node data MUST additionally be
exposed for a later point-cloud mesh source.

#### Scenario: Named force field registered

- GIVEN a running nacelle source with a name
- WHEN the registry is inspected
- THEN a `force.<name>` `volVectorField` is registered and written

#### Scenario: Per-node data exposed for a point-cloud source

- GIVEN the sampling object
- WHEN a consumer requests per-node positions and forces
- THEN both are available in a stable, SI, body-frame form suitable for a point-cloud mesh source

### Requirement: Seam only — no adapter or fsiOmega change

This contract MUST remain a seam: S2 MUST NOT modify the adapter (`modules/*`)
or `fsiOmega`, and S3 (preCICE FSI) MUST remain deferred and untouched. The
blade implementation is a second consumer of the same contract, not a coupling
change.
(Previously: stated for S1.)

#### Scenario: Adapter and fsiOmega untouched

- GIVEN the S2 change set
- WHEN the adapter and `fsiOmega` sources are inspected
- THEN no files under `modules/*` or `fsiOmega/` are changed
### Requirement: Shared sampling base with regression-gated S1 behavior

The generic sampling assets (triSurface load, centroid node set with normals and
areas, stable surface order, `cellSize`, kernel, distribution loop, MPI reduce
patterns) MUST be extracted into a frame- and force-model-agnostic base reusable
by a second surface implementation. `nacelleSurfaceSource`'s observable behavior
MUST NOT change: its accessors, SI units, static body frame, force-on-body sign,
registry exposure, and CSV output MUST remain as delivered, regression-gated by
the existing nacelle tests.

#### Scenario: Nacelle behavior unchanged

- GIVEN the nacelle source rebuilt on the shared base
- WHEN the existing nacelle tests run against the same case
- THEN they pass unchanged and the produced output remains byte-comparable to the S1 baseline

#### Scenario: Base is force-model agnostic

- GIVEN the shared base
- WHEN a second implementation consumes it
- THEN it provides geometry, kernel, and distribution only and contains no nacelle-specific direct-forcing or friction model

