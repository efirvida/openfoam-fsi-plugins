# Element Type Selection Specification

## Purpose

Defines the run-time selection mechanism that lets a line or blade instantiate
any registered actuator element type from its configuration. This completes the
vestigial element run-time selection table so that an `elementType` key selects
the concrete element class, defaulting to `actuatorLineElement` when the key is
absent, and so that the `elementType` and `nChordwise` keys reach every element.

## Requirements

### Requirement: Run-time element instantiation

The system MUST instantiate each actuator element through a run-time selection
`New` method that reads the `elementType` key from the element dictionary, and
MUST select `actuatorLineElement` when the key is absent.

#### Scenario: Explicit element type selection

- GIVEN a line or blade subdictionary containing `elementType actuatorSurfaceElement;`
- WHEN the source creates its elements
- THEN each element is instantiated as an `actuatorSurfaceElement`

#### Scenario: Default element type

- GIVEN a line or blade subdictionary with no `elementType` key
- WHEN the source creates its elements
- THEN each element is instantiated as an `actuatorLineElement`

#### Scenario: Unknown element type

- GIVEN a line or blade subdictionary with an `elementType` value that is not registered
- WHEN the source creates its elements
- THEN element creation fails with a run-time selection error

### Requirement: Actuator surface element registration

The system MUST register the `actuatorSurfaceElement` type in the element
run-time selection table so that `elementType actuatorSurfaceElement;` resolves
to a concrete element instance.

#### Scenario: Surface element resolves from the selection table

- GIVEN the library is built with the actuator surface element registered
- WHEN a case requests `elementType actuatorSurfaceElement;`
- THEN the element run-time selection table resolves the type to the `actuatorSurfaceElement` class

### Requirement: Config key plumbing

The system MUST accept the `elementType`, `nChordwise`, and `projectElementForce`
keys in the line/blade subdictionary and pass them through to every element.
`nChordwise` MUST default to 5 and `projectElementForce` MUST default to true
when absent. When a blade surface is configured (`surfaceGeometry` present), the
blade source MUST inject `projectElementForce false` into every element dict of
that blade; when no surface is configured, the key MUST NOT be injected.
Additionally, `createElements` MUST inject the per-element radial geometry keys
`radius` and `rotorRadius` into every element dict, with `radius` derived from
the radial station identity used by the comparison tool
(`r = rootRadius + rootDistance·(rotorRadius − rootRadius)`). The injection MUST
be additive: when the rotor/root radius inputs are absent, the element dict MUST
remain valid and the delivered behavior MUST be unchanged.
(Previously: only `elementType`, `nChordwise`, and `projectElementForce` were plumbed; no radial geometry was injected.)

#### Scenario: Keys reach every element

- GIVEN a blade subdictionary containing `elementType actuatorSurfaceElement;` and `nChordwise 5;`
- WHEN the blade source creates its elements
- THEN every element receives the keys, including `projectElementForce` when the surface injects it

#### Scenario: nChordwise default

- GIVEN a blade subdictionary containing `elementType actuatorSurfaceElement;` without `nChordwise`
- WHEN the blade source creates its elements
- THEN each surface element is configured with `nChordwise = 5`

#### Scenario: Suppression injected only with a surface

- GIVEN a blade subdictionary with `surfaceGeometry` configured
- WHEN the blade source creates its elements
- THEN each element dict carries `projectElementForce false`

#### Scenario: Radial geometry keys injected

- GIVEN a blade source holding a rotor radius and a root radius
- WHEN it creates its elements
- THEN every element dict carries `radius` and `rotorRadius` derived from the radial station

#### Scenario: No new keys present

- GIVEN an existing case with none of the keys present
- WHEN the source creates its elements
- THEN elements are created as line elements with `nChordwise = 5` and `projectElementForce` true, no radial geometry is injected, and no behavior change
### Requirement: Default actuator line behavior preserved

The system MUST preserve the existing actuator line and no-mesh ASM behavior
when the new keys are absent: `projectElementForce` defaults to true, the
resulting elements MUST behave identically to the delivered construction, and
existing cases and tests MUST pass unchanged.
(Previously: preservation was stated for `elementType` absence only.)

#### Scenario: Existing case regression

- GIVEN an existing actuator line or no-mesh ASM case with no `surfaceGeometry` and no `projectElementForce`
- WHEN the case is run against the new library
- THEN the produced element, line, and turbine results are identical to the baseline run
- AND the existing integration tests pass unchanged

### Requirement: Element strip-projection suppression control

An element reading `projectElementForce false` MUST still compute its force
(`calculateForce`) and write its performance CSV and public `force()` values,
but MUST NOT project the strip force into the momentum field. The flag MUST be
additive: absent or true means the delivered strip projection, unchanged; the
guard is the two `applyForceField` call sites
(`actuatorLineElement.C:1074-1075,1113-1114`).

#### Scenario: Suppressed element still computes and reports

- GIVEN an element configured with `projectElementForce false`
- WHEN `addSup` runs
- THEN its force is computed and its CSV and `force()` values are valid, and no strip force is added to the field

#### Scenario: Default keeps strip projection

- GIVEN an element with the key absent
- WHEN `addSup` runs
- THEN the strip force is projected exactly as before
