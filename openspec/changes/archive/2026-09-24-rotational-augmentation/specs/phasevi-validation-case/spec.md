# Delta for Phase VI Validation Case

Delta for change `rotational-augmentation`. The YAML single source of truth
gains the rotational-augmentation on-switch and the root-effect ablation
configuration, rendered into the case and its model variants.

## MODIFIED Requirements

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
