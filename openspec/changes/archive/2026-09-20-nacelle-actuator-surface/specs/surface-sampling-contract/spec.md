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

`positions()` and `forces()` MUST be reported in the body (nacelle) frame, not
the global mesh frame, so that a downstream coupling exchanges forces and node
locations in the body frame.

#### Scenario: Body-frame coordinates

- GIVEN a nacelle whose body frame is offset and rotated relative to the global mesh frame
- WHEN `positions()` is called
- THEN the returned node coordinates are in the nacelle body frame

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
surface, so a later point-cloud mesh source can map forces to positions
deterministically.

#### Scenario: Ordering stable across time steps

- GIVEN the same sampling object across consecutive time steps
- WHEN `positions()` and `forces()` are called each step
- THEN the node ordering is identical at every step

#### Scenario: Ordering stable across runs

- GIVEN two runs initialized from the same STL surface
- WHEN their `positions()` results are compared
- THEN the node ordering matches

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

S1 MUST deliver this contract as a seam and MUST NOT modify the adapter
(`modules/*`) or `fsiOmega`.

#### Scenario: Adapter and fsiOmega untouched

- GIVEN the S1 change set
- WHEN the adapter and `fsiOmega` sources are inspected
- THEN no files under `modules/*` or `fsiOmega/` are changed
