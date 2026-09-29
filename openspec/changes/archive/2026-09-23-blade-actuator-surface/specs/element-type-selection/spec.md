# Delta for Element Type Selection

Delta for change `blade-actuator-surface` (S2). A new additive per-element key
lets the blade surface distributor suppress the element strip projection without
changing the default ALM/no-mesh ASM behavior.

## MODIFIED Requirements

### Requirement: Config key plumbing

The system MUST accept the `elementType`, `nChordwise`, and `projectElementForce`
keys in the line/blade subdictionary and pass them through to every element.
`nChordwise` MUST default to 5 and `projectElementForce` MUST default to true
when absent. When a blade surface is configured (`surfaceGeometry` present), the
blade source MUST inject `projectElementForce false` into every element dict of
that blade; when no surface is configured, the key MUST NOT be injected.
(Previously: only `elementType` and `nChordwise` were plumbed; `createElements`
copied them at `actuatorLineSource.C:337-346`.)

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

#### Scenario: No new keys present

- GIVEN an existing case with none of the keys present
- WHEN the source creates its elements
- THEN elements are created as line elements with `nChordwise = 5` and `projectElementForce` true, and no behavior change

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

## ADDED Requirements

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
