# Actuator Surface Element Specification

## Purpose

Defines the behavior of the actuator surface element (ASM), a run-time-selected
variant of the actuator line element that replaces single-point inflow sampling
and line-based force projection with chord-averaged inflow sampling and uniform
chordwise force distribution over `nChordwise` equal chord strips. The surface
element inherits the full blade element momentum (BEM) force chain unchanged and
differs only in inflow sampling, force projection, and projection width.

## Requirements

### Requirement: Chord-averaged inflow sampling

The system MUST compute the inflow velocity for an actuator surface element as
the arithmetic mean of the cell-interpolated velocity samples taken at the
midpoint of each of `nChordwise` equal chord strips.

The sample point `X_k` for strip `k` MUST be located at
`X_k = position_ + (chordMount_ - f_k) * c * unit(chordDirection_)`, where
`c` is the chord length, `chordMount_` is the chordwise mounting position, and
`f_k = (k + 0.5) / nChordwise` for `k = 0 .. nChordwise - 1`.

#### Scenario: Chord-averaged inflow over equal strips

- GIVEN an actuator surface element with `nChordwise = 5` and a chord of length `c` mounted at quarter chord
- WHEN the element samples its inflow velocity
- THEN the reported inflow is the arithmetic mean of the velocity sampled at the 5 strip midpoints
- AND each midpoint lies on the chord line at `X_k = position_ + (chordMount_ - (k + 0.5) / 5) * c * unit(chordDirection_)`

#### Scenario: Single-strip element samples the chord midpoint

- GIVEN an actuator surface element with `nChordwise = 1`
- WHEN the element samples its inflow velocity
- THEN the single sample is taken at `f_0 = 0.5` (the chord midpoint)

#### Scenario: Unreachable chord sample

- GIVEN an actuator surface element whose chord sample point falls outside the mesh or on an unreachable processor
- WHEN the element attempts to sample at that point
- THEN the element aborts with a fatal error, consistent with the existing line element behavior

### Requirement: Uniform chordwise force distribution

The system MUST distribute the total aerodynamic force `forceVector_` of an
actuator surface element uniformly across its `nChordwise` chord strips, with
each strip carrying `forceVector_ / nChordwise` and projected with its own
Gaussian kernel. The sum of the projected strip forces MUST equal the element's
total `forceVector_`.

#### Scenario: Uniform strip-wise force projection

- GIVEN an actuator surface element with a computed `forceVector_` and `nChordwise = 5`
- WHEN the element applies its force field
- THEN each of the 5 strips carries `forceVector_ / 5`
- AND the total projected force over all strips equals `forceVector_`

#### Scenario: Force preservation is independent of strip count

- GIVEN the same actuator surface element and inflow conditions configured with different `nChordwise` values
- WHEN the element projects its force field
- THEN the total projected force is preserved regardless of the number of strips

### Requirement: Mesh-only projection epsilon

The system MUST compute the projection width (epsilon) of an actuator surface
element from the mesh only, as `2 * cbrt(V) * meshFactor`, and MUST NOT include
any chord-length term in the epsilon calculation.

#### Scenario: Epsilon independent of chord length

- GIVEN an actuator surface element on a mesh of cell volume `V` with `meshFactor` set
- WHEN the element computes its projection epsilon
- THEN epsilon equals `2 * cbrt(V) * meshFactor`
- AND epsilon does not grow with chord length

#### Scenario: Fine mesh with a large chord resolves chord geometry

- GIVEN an actuator surface element whose chord is much larger than the local mesh cells
- WHEN the element computes its projection epsilon
- THEN epsilon stays mesh-based and does not floor at a chord fraction, so the chord geometry remains resolvable

### Requirement: Inherited blade element force chain

The system MUST compute the aerodynamic loads of an actuator surface element
using the same blade element momentum chain as the actuator line element —
coefficient lookup, dynamic-stall, added-mass, and end-effect corrections — and
MUST write element-level CSV output in the same format as the line element. The
surface element differs only in inflow sampling, force projection, and
projection width.

#### Scenario: Identical BEM pipeline for a common flow

- GIVEN an actuator surface element and the foil and flow data shared with the line element
- WHEN the element computes its force
- THEN lift and drag are derived from the same coefficient, dynamic-stall, added-mass, and end-effect steps as the line element

#### Scenario: Element CSV output

- GIVEN a running actuator surface element
- WHEN the simulation writes performance output
- THEN an element-level CSV is produced in the same format used by the line element
