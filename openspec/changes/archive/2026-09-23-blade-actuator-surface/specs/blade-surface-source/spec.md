# Blade Surface Source Specification

## Purpose

Defines the per-blade distributing actuator surface source (`bladeSurfaceSource`)
that applies the delivered no-mesh blade ASM's BEM element forces over an
imported blade triangulation instead of the flat chord strips
(`actuatorSurfaceElement.C:51-205`). It is the S2 counterpart of S1's nacelle
surface: the source loads the committed blade binary STL, uses triangle
centroids as nodes, maps each BEM element's force to the surface patch it owns,
spreads with a selectable kernel (paper cosine default; Gaussian ablation),
follows the blades' rotating frame, and emits CSV and the SI sampling contract
for the three-way comparison. The change is distribution-only: the BEM chain and
the chord-averaged inflow are unchanged, and no surface-sampled BEM is added.

## ADDED Requirements

### Requirement: Additive surface activation

The blade source MUST construct the surface distributor only when the blade
subdictionary contains a `surfaceGeometry` key, and MUST leave ALM and no-mesh
ASM cases without that key behaviorally byte-identical. Absence of
`surfaceGeometry` MUST construct no distributor and MUST NOT alter element
configuration.

#### Scenario: Surface configured

- GIVEN a blade subdictionary with `surfaceGeometry` pointing at the committed blade STL
- WHEN the blade source is constructed
- THEN exactly one per-blade surface distributor is constructed over the imported surface

#### Scenario: No surface configured

- GIVEN a blade subdictionary without `surfaceGeometry`
- WHEN the blade source is constructed and run
- THEN no distributor is constructed, no `projectElementForce` is injected, and results are identical to the delivered ALM and no-mesh ASM baselines

### Requirement: Exactly-once force application

When the distributor is active, each BEM element's force MUST reach the momentum
field exactly once: the element's own strip projection MUST be suppressed and
replaced by the distributed surface contribution. The summed field force MUST
equal the summed element forces (partition of unity), neither doubled nor lost.

#### Scenario: No double counting

- GIVEN an active blade surface and a computed set of element forces
- WHEN the element loop and the distribution complete
- THEN the summed force added to the momentum equation equals the sum of the element forces exactly once

#### Scenario: Element data stays valid

- GIVEN an active blade surface
- WHEN element performance output is written
- THEN the element CSV and the public element `force()` values remain those of the BEM chain

### Requirement: Imported blade triangulation and node metadata

The distributor MUST read the blade binary STL via `triSurface::New`, use
triangle centroids as nodes with their area weights and stable surface order
(the S1 sampler pattern, `nacelleSurfaceSampler.C:173-215`), and associate every
node with the radial station and chord fraction it belongs to. A missing, empty,
or unparseable STL MUST raise `FatalError` rather than run without a surface.

#### Scenario: Nodes carry station metadata

- GIVEN the committed full-span blade STL
- WHEN the distributor initializes
- THEN every node has an area weight, a radial station, and a chord fraction, in the stable STL order

#### Scenario: Missing or invalid STL

- GIVEN a configured `surfaceGeometry` path that is missing, empty, or unparseable
- WHEN the source initializes
- THEN it raises `FatalError` and the run aborts

### Requirement: Element-force-to-patch mapping and force preservation

The distributor MUST compute a node-to-element partition once per blade such
that every node belongs to exactly one element's patch, the patch areas sum to
the blade surface area, and each element's force is spread over its own patch
weighted by per-node area. The distributed total MUST equal the element force
total.

#### Scenario: Partition covers the blade once

- GIVEN the blade surface and the interpolated BEM elements
- WHEN the partition is computed
- THEN every node belongs to exactly one element patch and the patch area sum equals the total blade surface area

#### Scenario: Distributed total preserved

- GIVEN an element force spread over its patch
- WHEN the field contribution is integrated
- THEN its total equals the element's force

### Requirement: Distribution-only model, no surface-sampled BEM

This change MUST be distribution-only: the element BEM chain (coefficient
lookup, dynamic stall, added mass, end effects), the chord-averaged inflow, and
the per-element force definition MUST remain as delivered; the surface MUST NOT
sample inflow per node or recompute BEM loads. The model difference against the
no-mesh ASM MUST be the distribution geometry, and in the ablation the kernel
width, only.

#### Scenario: BEM chain unchanged

- GIVEN a surface-enabled blade element
- WHEN its force is computed
- THEN lift and drag come from the same BEM steps as the no-mesh ASM and no per-node inflow sampling exists

### Requirement: Selectable kernel and width

The distributor MUST default to the paper's smoothed cosine kernel with support
|r| ≤ 2.5 (`nacelleSurfaceSampler.C:374-404`, Eq. 8) and MUST offer a Gaussian
mode whose width matches the no-mesh ASM's mesh-only epsilon
`2*cbrt(V)*meshFactor` (`actuatorSurfaceElement.C:61-100`), so a kernel-matched
ASM-mesh configuration can separate geometry from the kernel/width confound.

#### Scenario: Paper cosine default

- GIVEN a blade surface with no kernel key
- WHEN the force is distributed
- THEN the paper cosine kernel with support 2.5 spreads the force

#### Scenario: Gaussian ablation mode

- GIVEN a blade surface configured with the Gaussian kernel
- WHEN the force is distributed
- THEN the width equals the no-mesh ASM epsilon for the local cell

### Requirement: Rotating-frame lockstep and restart idempotency

The surface nodes MUST follow the blade through the existing
rotate/tilt/yaw/pitch/translate/setSpeed calls
(`actuatorLineSource.C:577-647`), with `positions()` azimuth-dependent in the
blade-local body frame, and MUST add no new state to the restart path: the S1
time-derived azimuth (`angleDeg()`, `turbineALSource.C:315-345,430-432`) is the
only rotation source.

#### Scenario: Nodes follow the rotor

- GIVEN an active blade surface and a rotor rotating over a time step
- WHEN the blade transform is applied
- THEN the surface nodes move in lockstep with the blade elements

#### Scenario: Restart has no new state

- GIVEN an interrupted run restarted from a written time
- WHEN the surface resumes
- THEN no surface-specific state is required beyond the existing azimuth persistence

### Requirement: Blade moment includes the surface contribution

The reported blade moment MUST include the distributed surface node moment, so
the turbine torque and CP are consistent with the loads actually applied by the
surface.

#### Scenario: Torque sees the surface load

- GIVEN an active blade surface with distributed loads
- WHEN the turbine moment and torque are computed
- THEN the surface node moment contributes to the reported blade moment

### Requirement: Surface CSV output

The distributor MUST write a machine-readable CSV with per-station force data
and MAY write per-node data. The per-station values MUST be convertible to the
existing `c_ref_n`/`c_ref_t` element conventions and r/R stations
(`comparePhaseVI.py:259-275`; coefficient definitions
`actuatorLineElement.C:683-705`) so the existing comparison logic consumes them.

#### Scenario: Per-station CSV produced

- GIVEN a running surface-enabled case
- WHEN output is written
- THEN a per-station force CSV is present and parses with numeric columns

#### Scenario: Compare-compatible conversion

- GIVEN the per-station surface output
- WHEN it is converted with the existing element coefficient definitions
- THEN it yields `c_ref_n`/`c_ref_t` at the five r/R stations used by the comparison

### Requirement: MPI correctness

In a parallel run, the distributor MUST resolve each node's containing cell
across processors using the S1 reduce/minimum-sentinel pattern
(`nacelleSurfaceSampler.C:269-292`), apply the force on the owning rank, and
fatal on an unreachable sample; distributed totals MUST be MPI-summed correctly.

#### Scenario: Node cell on another rank

- GIVEN a parallel run where a node's containing cell is on a different processor
- WHEN the force is distributed
- THEN the node's contribution is applied on the owning rank and counted once in the global total

#### Scenario: Unreachable node

- GIVEN a node that cannot be matched to any cell on any processor
- WHEN the distributor resolves it
- THEN the source raises a fatal error

### Requirement: Bounded distribution and performance measurement

The distribution MUST use a bounded candidate query (mesh cell tree or cached
stencil sized from the kernel support) rather than scanning all local cells per
node, and MUST report per-`addSup` instrumentation: surface node count,
candidate cells per node, and seconds per `addSup`. The D/32 measurement run
MUST be prepared-only and executed only under explicit authorization.

#### Scenario: Candidate set is bounded

- GIVEN a node with the paper kernel support
- WHEN candidate cells are queried
- THEN only candidates within the support neighborhood are examined, not every local cell

#### Scenario: Measurement output present

- GIVEN an instrumented surface run
- WHEN the run produces output
- THEN it reports node count, candidate cells per node, and seconds per `addSup`

#### Scenario: Measurement is prepared-only

- GIVEN the D/32 measurement setup
- WHEN this change completes
- THEN the measurement is prepared and no job has been submitted

### Requirement: Sampling contract exposure on the rotating blade frame

The distributor MUST expose the S1 sampling contract (`positions()`, `forces()`,
`normals()`, `areas()`) with a stable node ordering, in SI units, in the
blade-local rotating body frame, with the force reported as the force on the
blade, and MUST NOT introduce an adapter or `fsiOmega` dependency.

#### Scenario: Contract accessors available

- GIVEN an active blade surface
- WHEN the contract accessors are called
- THEN aligned SI node data is returned in the blade-local frame with the force-on-blade sign
