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

The system MUST accept the `elementType` and `nChordwise` keys in the line/blade
subdictionary and pass them through to every element. `nChordwise` MUST default
to 5 when absent.

#### Scenario: Keys reach every element

- GIVEN a blade subdictionary containing `elementType actuatorSurfaceElement;` and `nChordwise 5;`
- WHEN the blade source creates its elements
- THEN every element receives both keys

#### Scenario: nChordwise default

- GIVEN a blade subdictionary containing `elementType actuatorSurfaceElement;` without `nChordwise`
- WHEN the blade source creates its elements
- THEN each surface element is configured with `nChordwise = 5`

#### Scenario: No new keys present

- GIVEN an existing case with neither `elementType` nor `nChordwise` present
- WHEN the source creates its elements
- THEN elements are created as line elements with default `nChordwise = 5` and no behavior change

### Requirement: Default actuator line behavior preserved

The system MUST preserve the existing actuator line model behavior when
`elementType` is absent: the resulting elements MUST behave identically to the
current hard-coded `actuatorLineElement` construction, so existing cases and
tests pass unchanged.

#### Scenario: Existing case regression

- GIVEN an existing actuator line model case with no `elementType` key
- WHEN the case is run against the new library
- THEN the produced element, line, and turbine results are identical to the baseline actuator line model run
- AND the existing actuator line model integration tests pass unchanged
