# Delta for Actuator Surface Element

Delta for change `rotational-augmentation`. The surface element inherits the
optional rotational augmentation through the shared force chain, with no
per-model code.

## MODIFIED Requirements

### Requirement: Inherited blade element force chain

The system MUST compute the aerodynamic loads of an actuator surface element
using the same blade element momentum chain as the actuator line element —
coefficient lookup, rotational augmentation, dynamic-stall, added-mass, and
end-effect corrections — and MUST write element-level CSV output in the same
format as the line element. The surface element differs only in inflow sampling,
force projection, and projection width. The optional rotational augmentation
MUST be inherited unchanged when active and MUST NOT require surface-specific
code.
(Previously: the chain listed coefficient lookup, dynamic-stall, added-mass, and end-effect corrections only.)

#### Scenario: Identical BEM pipeline for a common flow

- GIVEN an actuator surface element and the foil and flow data shared with the line element
- WHEN the element computes its force
- THEN lift and drag are derived from the same coefficient, rotational-augmentation, dynamic-stall, added-mass, and end-effect steps as the line element

#### Scenario: Augmentation inherited without per-model code

- GIVEN an augmentation-on case using the actuator surface element
- WHEN its element output is compared with the actuator line element under the same flow
- THEN the augmentation is reflected through the shared chain and no surface-specific correction code exists

#### Scenario: Element CSV output

- GIVEN a running actuator surface element
- WHEN the simulation writes performance output
- THEN an element-level CSV is produced in the same format used by the line element
