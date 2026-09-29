# Delta for Surface Sampling Contract

Delta for change `blade-actuator-surface` (S2). The contract gains a second
implementation on a rotating frame and a shared sampling base; the S1 nacelle
behavior is unchanged and regression-gated.

## ADDED Requirements

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

## MODIFIED Requirements

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
