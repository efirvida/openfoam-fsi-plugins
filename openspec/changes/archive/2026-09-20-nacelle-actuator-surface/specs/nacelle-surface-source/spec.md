# Nacelle Surface Source Specification

## Purpose

Defines `nacelleSurfaceSource`, a dedicated `fv::option` source implementing the
nacelle/hub actuator surface model from Yang & Sotiropoulos (arXiv:1702.02108v4,
Sec. 2.2). The source reads a triangulated nacelle surface from STL, samples the
per-node flow velocity, computes a normal force via the paper's direct-forcing
immersed-boundary closure and a tangential force via a friction coefficient and a
reference incoming velocity, distributes the force onto the cell set through the
paper's smoothed kernel, writes CSV output, and is MPI-correct. It is usable
standalone (a rotor-less `fvOptions` entry — exactly the paper's periodic-nacelle
validation case) and composed by `axialFlowTurbineALSource::createNacelle()`,
which also closes the existing null-deref. The source carries no blade-element
(BEM) content: there is no coefficient lookup, angle of attack, dynamic stall,
added mass, or `profileData`.

## Requirements

### Requirement: STL surface triangulation

The system MUST read the nacelle geometry from an STL file via
`triSurface::New`, which MUST auto-detect both ASCII and binary STL, and MUST
compute per-node position, outward unit normal, and area weight from the
triangulation. The source MUST NOT require any blade-element or BEM data.

#### Scenario: ASCII STL read

- GIVEN a case configuring the nacelle source with an ASCII STL path
- WHEN the source initializes
- THEN the surface triangulation is read and per-node positions, outward unit normals, and area weights are computed

#### Scenario: Binary STL read

- GIVEN a case configuring the nacelle source with a binary STL path
- WHEN the source initializes
- THEN `triSurface::New` auto-detects the binary format and the same per-node geometry is produced

#### Scenario: No blade-element data required

- GIVEN a nacelle source configured with only a geometry path and force-model keys
- WHEN the source reads its configuration
- THEN it accepts the dictionary without any `profileData`, coefficient, angle-of-attack, or dynamic-stall keys

### Requirement: Direct-forcing normal force

The system MUST compute the per-node normal force using the paper's
direct-forcing immersed-boundary closure (Eq. 19),
`f_n = h(−u^d + ũ)·e_n / Δt · e_n`, where `h = (hx·hy·hz)^(1/3)` is the local
cell size, `ũ` is the flow velocity interpolated at the node (Eqs. 7 and 20 of
the paper), `u^d` is the desired body velocity — zero for a stationary nacelle —
`e_n` is the outward surface normal, and `Δt` is the current time step. The
resulting normal force MUST act along `e_n`.

#### Scenario: Stationary nacelle opposes the flow

- GIVEN a stationary nacelle surface node with an incoming flow velocity `ũ` and local cell size `h`
- WHEN the source computes the node's normal force
- THEN the force equals `h·(0 + ũ)·e_n / Δt · e_n`, directed along the outward normal and opposing the incoming flow

#### Scenario: Local cell size from the mesh

- GIVEN a node located in a cell of dimensions `hx`, `hy`, `hz`
- WHEN the source computes the normal force
- THEN the geometric mean `h = (hx·hy·hz)^(1/3)` of the containing cell is used

#### Scenario: Zero incoming velocity yields zero normal force

- GIVEN a surface node where the interpolated flow velocity `ũ` is zero
- WHEN the source computes the normal force
- THEN the normal force is zero

### Requirement: Tangential force via friction model

The system MUST compute the tangential force magnitude as `f_τ = ½·cf·U²`
(Eq. 21), where `U` is the reference incoming velocity (the magnitude of the
streamwise incoming velocity), and MUST direct it along the unit tangential
vector `e_τ = u(X + h·e_n) / |u(X + h·e_n)|` (Eq. 23), sampled at a probe point
offset `h` off the wall along the outward normal. The source MUST remain
numerically well-defined when the off-wall probe velocity magnitude vanishes.

#### Scenario: Tangential direction sampled off the wall

- GIVEN a surface node with cell size `h` and an off-wall probe point `X + h·e_n`
- WHEN the source computes the tangential direction
- THEN `e_τ` is the normalized flow velocity at the probe point

#### Scenario: Tangential force magnitude from friction and reference velocity

- GIVEN a friction coefficient `cf` and a reference incoming velocity `U`
- WHEN the source computes the tangential force
- THEN the magnitude is `½·cf·U²` and the direction is `e_τ`

#### Scenario: Stagnation-point probe velocity

- GIVEN a node whose off-wall probe velocity magnitude is zero
- WHEN the source computes the tangential direction
- THEN the source does not divide by zero and the tangential force is zero

### Requirement: Friction coefficient model with constant override

The system MUST compute `cf` from the Schultz–Grunow relation
`cf = 0.37·(log Rex)^(−2.584)` (Eq. 22) by default, where `Rex` is derived from
the incoming velocity and the streamwise distance from the upstream (nose) edge.
The system MUST accept an optional user-supplied constant `cf` override for
calibration studies and the drag-coefficient comparison. The paper's
zero-pressure-gradient validity limits in the hemisphere nose region MUST be
documented.

#### Scenario: Schultz-Grunow default

- GIVEN a nacelle source configured without a constant `cf` override
- WHEN the source computes the per-node friction coefficient
- THEN `cf` is evaluated from `0.37·(log Rex)^(−2.584)` with `Rex` keyed by the streamwise distance from the nose

#### Scenario: Constant override

- GIVEN a nacelle source configured with a user-supplied constant `cf`
- WHEN the source computes the per-node friction coefficient
- THEN every node uses the configured constant value

#### Scenario: Nose-region validity documented

- GIVEN the nacelle source documentation
- WHEN the friction model is described
- THEN the zero-pressure-gradient assumption and its limits near the hemisphere nose are documented

### Requirement: Smoothed kernel force distribution

The system MUST distribute each node's total force onto the cell set using the
paper's smoothed delta kernel (Eq. 18), spread over the closest approximately
five cells, weighted by per-node area. The sum of the distributed force MUST
equal the sum of the per-node forces.

#### Scenario: Total force preserved

- GIVEN a set of per-node forces distributed by the smoothed kernel
- WHEN the distributed field is integrated over the cell set
- THEN the total force equals the sum of the node forces

#### Scenario: Per-node area weighting

- GIVEN two nodes of different area on the same surface
- WHEN the source distributes their forces
- THEN each node's contribution is weighted by its area

### Requirement: Standalone and composed usage

The source MUST be usable standalone as an `fvOptions` entry
(`type nacelleSurfaceSource;`) with no turbine present — the rotor-less
validation case. The source MUST also be composable via
`axialFlowTurbineALSource::createNacelle()` as an owned child (the same pattern
as `hub_`/`tower_`), constructed from `nacelleDict_`.

#### Scenario: Standalone fvOptions entry

- GIVEN a case with `nacelleSurfaceSource` in `fvOptions` and no turbine
- WHEN the case runs
- THEN the source applies the nacelle force and produces output without requiring a turbine

#### Scenario: Composed through createNacelle

- GIVEN an `axialFlowTurbineALSource` case with a `nacelle {}` subdictionary
- WHEN `createNacelle()` runs
- THEN it constructs a valid `nacelleSurfaceSource` from `nacelleDict_` as an owned child

### Requirement: Null-deref closed additively

When `axialFlowTurbineALSource` reads a `nacelle {}` subdictionary, the system
MUST construct a valid nacelle source and the three `addSup` overloads MUST no
longer dereference a null `nacelle_` pointer. Rotate, tilt, and yaw MUST remain
blade-and-hub only (the nacelle is static).

#### Scenario: No null-deref in any addSup overload

- GIVEN an `axialFlowTurbineALSource` case with a `nacelle {}` subdictionary
- WHEN the momentum (incompressible and compressible) and scalar turbulence `addSup` overloads run
- THEN none dereferences a null `nacelle_` pointer

#### Scenario: Nacelle stays static

- GIVEN an `axialFlowTurbineALSource` with rotate, tilt, and yaw configured
- WHEN the source applies the nacelle block
- THEN the nacelle surface is not rotated, tilted, or yawed

### Requirement: Additive default path is byte-identical

With no `nacelle {}` or geometry configured, `hasNacelle_` MUST be false and the
three `addSup` bodies MUST skip the nacelle block, so current behavior remains
byte-identical and the actuator line model remains the default. The existing
pytest suite MUST pass unchanged.

#### Scenario: Default ALM path unchanged

- GIVEN an existing `axialFlowTurbineALSource` case with no `nacelle {}` subdictionary
- WHEN the case runs against the new library
- THEN the results are identical to the baseline actuator line model run

#### Scenario: Existing suite regression gate

- GIVEN the new library is built with the nacelle source wired in
- WHEN the existing pytest suite (`test_libs`, `test_al`, `test_aftal`, `test_aftal_asm`, `test_cftal`) runs
- THEN it passes unchanged

### Requirement: FatalError on missing or invalid STL

The system MUST raise `FatalError` rather than silently continuing when the
configured STL is missing, unreadable, or invalid (empty or unparseable).

#### Scenario: Missing STL

- GIVEN a nacelle source configured with an STL path that does not exist
- WHEN the source initializes
- THEN it raises `FatalError` and the run aborts

#### Scenario: Invalid STL

- GIVEN a nacelle source configured with an empty or corrupt STL file
- WHEN the source initializes
- THEN it raises `FatalError` and the run aborts

### Requirement: CSV output

The system MUST write nacelle force output as CSV — per-node force and/or total
nacelle force — in a format consumable by the integration tests and the
validation comparison script.

#### Scenario: Standalone run produces force CSV

- GIVEN a standalone `nacelleSurfaceSource` case that has run
- WHEN the output directory is inspected
- THEN a nacelle force CSV is present

#### Scenario: CSV is machine-readable

- GIVEN the produced force CSV
- WHEN the integration test parses it
- THEN the columns parse as numbers with the expected per-node and/or total force

### Requirement: MPI correctness

The system MUST correctly assign forces when a surface node's containing cell
resides on a different processor than the node itself, using a reduce/minimum
sentinel and bounding-box `findCell` pattern, and MUST fatal on unreachable
samples.

#### Scenario: Node on another processor

- GIVEN a parallel run where a nacelle surface node's containing cell is on a different processor
- WHEN the source resolves the node's cell
- THEN the node is assigned to the correct cell and its force is applied there

#### Scenario: Unreachable sample

- GIVEN a surface node that cannot be matched to any cell on any processor
- WHEN the source resolves the node's cell
- THEN the source raises a fatal error
