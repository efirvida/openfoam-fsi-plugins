# Axial Flow Turbine ASM Tutorial Specification

## Purpose

Defines the in-repo horizontal-axis wind turbine (HAWT) actuator surface model
tutorial case and the workflow that compares its results side by side against
the existing actuator line model tutorial.

## Requirements

### Requirement: HAWT actuator surface model tutorial case

The system MUST provide an in-repo tutorial case at
`tutorials/axialFlowTurbineASM/` based on the existing
`tutorials/axialFlowTurbineAL/` case, with the blade subdictionary configured
for the actuator surface element. The case MUST run to completion and produce
turbine-level and element-level CSVs.

#### Scenario: Tutorial case configured for the surface element

- GIVEN the tutorial case `tutorials/axialFlowTurbineASM/`
- WHEN its blade subdictionary is inspected
- THEN it contains `elementType actuatorSurfaceElement;` in the blade configuration

#### Scenario: Tutorial case runs and writes output

- GIVEN a loaded OpenFOAM environment and a built `libturbinesFoam`
- WHEN the tutorial case is run
- THEN it completes and writes turbine-level and element-level CSVs

#### Scenario: Tutorial case runs in bounded time

- GIVEN the tutorial case uses a truncated control dictionary to limit runtime
- WHEN the case is run
- THEN it completes within a bounded number of time steps

### Requirement: ALM-vs-ASM comparison workflow

The system MUST provide a comparison script that reads the results from both the
actuator line model tutorial run directory and the actuator surface model
tutorial run directory and produces side-by-side power (Cp), thrust (CT), and
spanwise output.

#### Scenario: Side-by-side comparison output

- GIVEN completed runs of the actuator line model tutorial and the actuator surface model tutorial
- WHEN the comparison script is executed against the two run directories
- THEN it produces side-by-side Cp and CT output
- AND it produces side-by-side spanwise output

#### Scenario: Missing run directory

- GIVEN the comparison script is executed while one of the two run directories is missing or incomplete
- WHEN the script runs
- THEN it reports the missing input rather than producing a misleading comparison
