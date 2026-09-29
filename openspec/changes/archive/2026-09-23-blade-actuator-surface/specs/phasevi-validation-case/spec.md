# Delta for Phase VI Validation Case

Delta for change `blade-actuator-surface` (S2). The case package gains the third
model variant (mesh-backed ASM) and the documentation statement for the model
form being validated.

## MODIFIED Requirements

### Requirement: ALM and ASM fvOptions twins

The generator MUST render three `fvOptions` variants: the actuator line
(`elementType actuatorLineElement;`), the no-mesh actuator surface
(`elementType actuatorSurfaceElement; nChordwise 5;`), and the mesh-backed
actuator surface (`fvOptions.ASM-MESH`, the surface element keys plus
`surfaceGeometry` — and optional kernel keys — in each blade subdictionary). The
variants MUST differ only in the blade subdictionary element/surface keys; no
other difference is permitted. The case tooling MUST accept `asm-mesh` as a
valid model (the `--select` whitelist at `case_config.py:585` is extended), MUST
treat `asm-mesh` as ASM-family for `--nchordwise`, and `generate_case.py --check`
MUST be clean for the committed case.
(Previously: two twins, ALM and ASM, differing only in `elementType`/`nChordwise`.)

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
