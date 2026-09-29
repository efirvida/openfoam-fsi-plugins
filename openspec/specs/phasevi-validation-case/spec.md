# Phase VI Validation Case Specification

## Purpose

Defines the case-generation capability of the NREL Phase VI (NASA Ames Unsteady
Aerodynamics Experiment) validation package at `turbinesFoam/validation/phaseVI/`.
A YAML single source of truth renders the uniform-inflow case skeleton: domain
and boundary conditions, the 18-block hexahedral `blockMeshDict` at selectable
resolution, solver and fixed time-step settings, per-speed measured TSR
kinematics, the decomposition dictionary, and the actuator line / actuator
surface `fvOptions` twins. The generator also detects stale generated files and
the package documents its setup, run stages, metric definitions, and
limitations.

## Requirements

### Requirement: YAML single source of truth

The case package MUST define its case parameters — domain extents, mesh
resolution, wind speed, per-speed measured tip-speed ratio, pitch, solver
settings, decomposition, the rotational-augmentation switch, and the end-effect
root setting — in a single YAML configuration at `config/case.yaml`, and MUST
render the case skeleton from that configuration. Re-rendering after a
configuration change MUST update the generated files. The committed case MUST
keep `rotationalAugmentation` off by default and `rootEffects on`; the
root-effect ablation MUST be a render-time configuration, not a change to the
committed default.
(Previously: the parameter list omitted the augmentation switch and the root-effect ablation.)

#### Scenario: Render from configuration

- GIVEN a YAML configuration selecting a mesh resolution and a wind speed
- WHEN the case generator renders the case
- THEN the generated `0.org/`, `constant/`, and `system/` files reflect the configured domain, mesh resolution, inflow speed, and solver settings

#### Scenario: Configuration change re-renders

- GIVEN an already rendered case and a changed YAML parameter
- WHEN the generator re-renders the case
- THEN the generated files reflect the new parameter value

#### Scenario: Augmentation switch rendered

- GIVEN a YAML configuration with the rotational-augmentation switch on
- WHEN the case generator renders the case
- THEN the generated `fvOptions` variants carry the `rotationalAugmentation` block with `active on` and the paper constants

#### Scenario: Root-effect ablation is a render-time variant

- GIVEN the YAML root-effect setting
- WHEN the ablation variant is rendered
- THEN it sets `rootEffects off` while the committed default keeps `rootEffects on`

### Requirement: Stale generated-file detection

The generator MUST provide a check mode that reports generated files that are
missing or no longer match what the current YAML configuration renders, and
MUST exit non-zero when any stale generated file is found. The check mode MUST
NOT modify generated files.

#### Scenario: Stale file detected

- GIVEN a rendered case and a generated file that was edited by hand or left behind by a configuration change
- WHEN the generator runs in check mode
- THEN it reports the stale file and exits non-zero

#### Scenario: Check mode is non-destructive

- GIVEN a rendered case with a stale generated file
- WHEN the generator runs in check mode
- THEN the generated files are left unchanged

#### Scenario: Clean case passes

- GIVEN a case rendered from the current YAML configuration
- WHEN the generator runs in check mode
- THEN it reports no stale files and exits zero

### Requirement: Uniform-inflow domain and boundary conditions

The case MUST use a free box re-centred on the rotor hub with extents
x ∈ [−5D, 15D], y ∈ ±4D, and z ∈ hub ± 2.5D, with the hub at 12.192 m (for the
reference rotor: 201 m × 80.5 m × 50.3 m). The inlet MUST be a uniform velocity
inlet, the outlet MUST be a pressure outlet, and all remaining far boundaries
MUST be slip/symmetry. The case MUST NOT require an atmospheric boundary layer,
Mann turbulence, or any external inflow-preprocessing dependency.

#### Scenario: Re-centred free box

- GIVEN the case configuration for the reference rotor and hub height
- WHEN the generated mesh extents are inspected
- THEN the domain spans x from −5D to 15D, y from −4D to 4D, and z from hub − 2.5D to hub + 2.5D

#### Scenario: Far field is slip/symmetry

- GIVEN the generated boundary conditions
- WHEN the far-field patch types are inspected
- THEN the inlet is a uniform velocity inlet, the outlet is a pressure outlet, and every other far boundary is slip/symmetry

#### Scenario: Squat fallback domain available

- GIVEN a tighter 15D × 6D × 6D fallback domain is selected
- WHEN the case generator renders the case
- THEN the generated domain reflects the fallback extents

### Requirement: 18-block hexahedral block mesh at selectable resolution

The generator MUST render a fully hexahedral 18-block Cartesian
`blockMeshDict`. The renderer MUST support at least the D/32 development mesh
(≈ 6.67 M cells, cell size 0.3143 m) and the D/48 headline mesh (≈ 22.5 M
cells, cell size 0.2095 m), and MAY support the D/64 sensitivity mesh
(≈ 40 M cells, cell size 0.1572 m). A rendered mesh MUST pass `blockMesh` and
`checkMesh` cleanly.

#### Scenario: Production resolutions render and check clean

- GIVEN the case generator
- WHEN it renders the D/32 and D/48 meshes and `blockMesh` and `checkMesh` are run on each
- THEN both meshes are generated and `checkMesh` reports them as valid with no errors

#### Scenario: D/64 is an optional sensitivity mesh

- GIVEN the case generator
- WHEN the D/64 resolution is requested
- THEN a mesh of approximately 40 M cells is rendered

### Requirement: ALM and ASM fvOptions twins

The generator MUST render three `fvOptions` variants: the actuator line
(`elementType actuatorLineElement;`), the no-mesh actuator surface
(`elementType actuatorSurfaceElement; nChordwise 5;`), and the mesh-backed
actuator surface (`fvOptions.ASM-MESH`, the surface element keys plus
`surfaceGeometry` — and optional kernel keys — in each blade subdictionary). The
variants MUST differ only in the blade subdictionary element/surface keys; no
other difference is permitted. The `rotationalAugmentation` block MUST be
rendered identically in all three variants, so the twins stay identical except
for the element keys. The case tooling MUST accept `asm-mesh` as a valid model
(the `--select` whitelist already includes it — `MODEL_CHOICES` at
`case_config.py:45`, validated at `:589-592` — so no whitelist change is
required), MUST treat `asm-mesh` as ASM-family for `--nchordwise`, and
`generate_case.py --check` MUST be clean for the committed case.
(Previously: the twins requirement did not mention the augmentation block rendered across variants.)

#### Scenario: Three variants differ only in blade keys

- GIVEN the generated `system/fvOptions.ALM`, `system/fvOptions.ASM`, and `system/fvOptions.ASM-MESH`
- WHEN the three files are compared with the blade keys stripped
- THEN the remaining lines are identical

#### Scenario: ASM-mesh variant carries the surface keys

- GIVEN the rendered ASM-mesh twin
- WHEN the blade subdictionary is inspected
- THEN it carries the surface element keys plus `surfaceGeometry`, and nothing else differs from the other variants

#### Scenario: Model selection accepted

- GIVEN the rendered case package
- WHEN `case_config.py --select 7 coarse asm-mesh` runs
- THEN the triple is accepted and the kinematics are printed, while an unconfigured model name is still rejected

#### Scenario: Renderer check clean

- GIVEN the committed case rendered from the current configuration
- WHEN `generate_case.py --check` runs
- THEN it reports no stale files and exits zero
### Requirement: Solver and tip-constrained fixed time step

The case MUST use `pimpleFoam` with the `kOmegaSST` turbulence model,
`adjustTimeStep off`, and a fixed time step chosen so that the actuator line
tip displacement per step does not exceed the cell size: D/32 Δt = 0.008 s,
D/48 Δt = 0.005 s, and D/64 Δt = 0.004 s. The scaffold's 0.03 s / Courant 1.0
setting MUST NOT be reused. The generated `controlDict` MUST set a 12-revolution
run length at the per-speed rotor speed and MUST write output frequently enough
to support the averaging window used by the comparison.

#### Scenario: Fixed time step per mesh

- GIVEN a rendered case at D/32, D/48, or D/64
- WHEN the `controlDict` time settings are inspected
- THEN `adjustTimeStep` is off and the fixed time step is 0.008 s, 0.005 s, or 0.004 s respectively

#### Scenario: Tip-displacement constraint satisfied

- GIVEN the D/32 case driven at 7 m/s with the measured TSR
- WHEN the tip displacement per step is evaluated
- THEN it stays below the D/32 cell size (0.303 m versus 0.3143 m)

#### Scenario: Scaffold time step not reused

- GIVEN any rendered case
- WHEN the time settings are inspected
- THEN the fixed time step is the resolution-specific value and not the scaffold's 0.03 s

### Requirement: Per-speed measured TSR kinematics

The case configuration MUST carry the per-speed measured tip-speed ratio so
that the rotor speed is set through `tipSpeedRatio`, and MUST NOT use a single
fixed value across wind speeds. The Sequence H measured values MUST be present:
7 m/s → 5.408, 10 m/s → 3.798, 13 m/s → 2.920, 15 m/s → 2.530, 20 m/s → 1.898,
and 25 m/s → 1.521. The case MUST use two blades, pitch 3°, azimuthal offsets
0°/180°, axis (−1, 0, 0), vertical (0, 0, 1), and the `-(twist + pitch)` blade
mounting convention.

#### Scenario: Measured TSR selected per speed

- GIVEN a request for a supported wind speed
- WHEN the case configuration is rendered
- THEN the `tipSpeedRatio` equals the measured value for that speed

#### Scenario: Fixed TSR is not used globally

- GIVEN the case configuration for any supported speed other than 7 m/s
- WHEN the `tipSpeedRatio` is inspected
- THEN it is the measured value for that speed and not the fixed 5.3894

#### Scenario: Rotation conventions rendered

- GIVEN a rendered 7 m/s case
- WHEN the rotor and blade configuration is inspected
- THEN it uses two blades, pitch 3°, azimuthal offsets 0°/180°, axis (−1, 0, 0), vertical (0, 0, 1), and the `-(twist + pitch)` mounting convention

### Requirement: Blade element data generation

The case package MUST provide the blade element data consumed by turbinesFoam,
derived from the committed Phase VI geometry CSV, and MUST include the
`makeElementData.py` generation script.

#### Scenario: Element data derived from committed geometry

- GIVEN the committed `data/geometry/phaseVI_blade.csv`
- WHEN `makeElementData.py` runs
- THEN element data in the format consumed by turbinesFoam is written for the blade

### Requirement: Decomposition dictionary

The generator MUST render a `decomposeParDict` consistent with the configured
run granularity so that the case can be decomposed for the prepared runs.

#### Scenario: Decomposition rendered

- GIVEN a rendered case and a configured number of subdomains
- WHEN the generated `decomposeParDict` is inspected
- THEN it declares that number of subdomains

### Requirement: Environment check accepts the repository toolchain

The case environment check MUST accept the repository's OpenFOAM v2506
toolchain and MUST remain compatible with OpenFOAM v2412.

#### Scenario: v2506 environment accepted

- GIVEN a loaded OpenFOAM v2506 environment
- WHEN the case environment check runs
- THEN it passes without a version error

#### Scenario: v2412 remains accepted

- GIVEN a loaded OpenFOAM v2412 environment
- WHEN the case environment check runs
- THEN it passes without a version error

### Requirement: Case package documentation

The case package MUST include a `README.md` documenting the case setup, the
staged run plan, the metric definitions, the modelling limitations, the three
model variants, the formulation being implemented (the paper's chord-line blade
ASM extended to an imported surface — explicitly not a literal equation port),
the sub-grid caveat, the kernel/width confound and its ablation, and the MEXICO
naming resolution. The root `README.md` and root `CHANGELOG.md` MUST be updated
to document the change, with the changelog entry following the repository's
`Files:` / `Problem:` / `Fix:` format.
(Previously: the README documented the two-model case; root docs referenced the
validation package.)

#### Scenario: Case README documents setup and limitations

- GIVEN the validation case package
- WHEN its `README.md` is inspected
- THEN it documents the setup, staged plan, metrics, limitations, the three models, the formulation extension, the sub-grid caveat, the kernel confound and its ablation, and the naming resolution

#### Scenario: Root documentation updated

- GIVEN the repository root documentation
- WHEN `README.md` and `CHANGELOG.md` are inspected
- THEN both document the S2 change and the changelog entry follows `Files:` / `Problem:` / `Fix:`
