# Delta for Element Type Selection

Delta for change `rotational-augmentation`. `createElements` additionally
injects the per-element radial geometry keys the augmentation needs; absent
inputs keep the delivered behavior.

## MODIFIED Requirements

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
