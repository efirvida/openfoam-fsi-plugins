# Delta for Phase VI Run and Compare

Delta for change `blade-actuator-surface` (S2). The runner gains the `asm-mesh`
model with STL staging, the comparison becomes three-way with the existing bands
and sign gate, and the ASM-mesh array is prepared-only. No job is submitted.

## MODIFIED Requirements

### Requirement: Run orchestration interface

`scripts/runPhaseVI.sh` MUST accept `-m alm|asm|asm-mesh`, `-u <wind-speed>`,
and the optional `-mesh coarse|fine`. It MUST select the matching `fvOptions`
variant and mesh, apply the per-speed measured TSR, produce the model-specific
run id (`asm-mesh-U<speed>-<mesh>`), and place results in per-variant run
directories so the comparison tool can locate the ALM, ASM, ASM-mesh, and
experiment data for the same case. `--nchordwise` MUST remain restricted to the
ASM family (`asm`, `asm-mesh`).
(Previously: only `alm|asm` were accepted.)

#### Scenario: ALM coarse run prepared

- GIVEN the rendered case package
- WHEN `runPhaseVI.sh -m alm -u 7 -mesh coarse` is invoked
- THEN the actuator line `fvOptions` variant and the D/32 mesh are selected

#### Scenario: ASM fine run prepared

- GIVEN the rendered case package
- WHEN `runPhaseVI.sh -m asm -u 7 -mesh fine` is invoked
- THEN the actuator surface `fvOptions` variant and the D/48 mesh are selected

#### Scenario: ASM-mesh fine run prepared

- GIVEN the rendered case package
- WHEN `runPhaseVI.sh -m asm-mesh -u 7 -mesh fine` is invoked
- THEN the ASM-mesh `fvOptions` variant, the staged surface STL, and the D/48 mesh are selected without `--run` or `--submit`

#### Scenario: Unsupported input rejected

- GIVEN a model flag or wind speed without a configured case
- WHEN `runPhaseVI.sh` is invoked with that value
- THEN it fails loudly instead of running a misconfigured case

### Requirement: Comparison inputs and merge

`scripts/comparePhaseVI.py` MUST accept the third (ASM-mesh) run directory in
addition to the ALM and ASM inputs, read its turbine-level CSV and its
per-station surface output, convert the surface output to the existing
`c_ref_n`/`c_ref_t` element conventions and r/R stations
(`comparePhaseVI.py:259-275`), and merge all three models with the committed
experimental data into one turbine-level and one spanwise output at the five
measured stations (30 %, 47 %, 63 %, 80 %, and 95 % span). A missing ASM-mesh
input MUST fail loudly.
(Previously: only the ALM and ASM element CSVs were merged.)

#### Scenario: Three-way comparison produced

- GIVEN completed ALM, ASM, and ASM-mesh runs and the committed experimental data
- WHEN `comparePhaseVI.py` is executed
- THEN it produces one turbine-level and one spanwise table containing all three models

#### Scenario: Surface output converted

- GIVEN the ASM-mesh surface output
- WHEN the comparison consumes it
- THEN its per-station forces are mapped to `c_ref_n`/`c_ref_t` and the five r/R stations without changing the existing definitions

#### Scenario: Missing third input fails loudly

- GIVEN a comparison invoked without a complete ASM-mesh run directory
- WHEN the tool runs
- THEN it reports the missing input and exits non-zero

#### Scenario: Sequence S repeat compared

- GIVEN the Sequence S experimental row and the corresponding simulation run
- WHEN the comparison runs
- THEN the Sequence S repeat is included in the turbine-level comparison

### Requirement: Long-queue authorization gate

All prepared stages and arrays, including the new ASM-mesh array, MUST be
prepared but MUST NOT be submitted until the long-queue authorization is
explicitly granted. No automated step of this change MUST submit a job. The
existing queued `phaseVI-prod`, `phaseVI-stage3`, and `phaseVI-stage3-d64`
arrays MUST NOT be submitted, cancelled, or modified.
(Previously: the gate covered the ALM/ASM staged runs only.)

#### Scenario: Preparation does not submit

- GIVEN the prepared stages and arrays, including ASM-mesh
- WHEN the preparation workflow runs
- THEN no job is submitted to any queue

#### Scenario: Stage 0 runs on the authorized queue

- GIVEN the development-queue authorization
- WHEN Stage 0 is executed
- THEN it runs on the development queue only

#### Scenario: Existing arrays untouched

- GIVEN the queued Phase VI baseline arrays
- WHEN this change completes
- THEN they have not been submitted, cancelled, or modified

### Requirement: Slurm job preparation

The package MUST prepare job scripts for the staged runs with one array task per
(model, speed, mesh) combination, bounded wall-time requests, and restart from
the latest written time. The ASM-mesh array MUST follow the same shape and MUST
be prepared-only.
(Previously: the arrays covered ALM/ASM combinations only.)

#### Scenario: One array task per combination

- GIVEN the prepared staged and ASM-mesh job scripts
- WHEN they are inspected
- THEN each (model, speed, mesh) combination is a separate array task

#### Scenario: Wall time bounded and restartable

- GIVEN a prepared job script
- WHEN its resource request is inspected
- THEN the wall time is bounded to at most 24 h and a resubmission resumes from the latest written time

### Requirement: Documented tolerance bands and honest claims

The comparison MUST report each headline metric against the documented bands for
all three models — ±15 % turbine-level and max(0.15, 20 %) spanwise with the
sign gate — and the reported claim MUST NOT be stronger than the evidence. The
three-way comparison MUST be framed as a test of model form (how the load is
distributed): at D/32–D/64 the background cells are 0.314/0.210/0.157 m while
the blade chord is 0.218–0.744 m, so the imported surface is sub-grid and the
comparison cannot demonstrate resolved chordwise physics. The kernel/width
difference between the paper-cosine surface and the no-mesh Gaussian MUST be
documented, with the kernel-matched ASM-mesh configuration documented as an
ablation, and the pre-registered hypothesis MUST be recorded before the
campaign. An agreement better than the documented band MUST NOT be promised a
priori.
(Previously: the limitation statement covered sub-cell ASM chord strips and
URANS deep-stall limits for two models.)

#### Scenario: Band documented before results

- GIVEN the comparison tool and its documented band definitions
- WHEN a result is reported
- THEN the metric's tolerance band is reported alongside it

#### Scenario: Bands reported per model

- GIVEN a comparison result
- WHEN the turbine and spanwise tables are inspected
- THEN each model's metric is reported with its documented band and the sign gate

#### Scenario: Qualitative-to-semi-quantitative claim

- GIVEN a 7 m/s headline result
- WHEN the claim is written
- THEN it is limited to trend, stall onset, and agreement within the documented band
- AND no sub-5 % agreement is promised a priori

#### Scenario: Sub-grid framing stated

- GIVEN the comparison report
- WHEN the claim is written
- THEN it states that the imported surface is sub-grid at the affordable meshes and tests model form, not resolved chordwise physics

#### Scenario: Kernel confound and ablation documented

- GIVEN the comparison documentation
- WHEN the kernel/width difference is inspected
- THEN it is documented and the kernel-matched ASM-mesh configuration is identified as an ablation

#### Scenario: Pre-registered hypothesis

- GIVEN the campaign preparation
- WHEN the README is inspected before any run
- THEN the expected direction and approximate size of the geometry effect are recorded

#### Scenario: Limitation statement present

- GIVEN a comparison report
- WHEN it is inspected
- THEN it states the sub-grid ASM limitation (including the imported surface), the URANS deep-stall limitation, and treats separated high-speed points as trend and stall-onset evidence

## ADDED Requirements

### Requirement: STL staging into run directories

Every surface-model run directory MUST receive a copy of the committed blade STL
at a case-relative path (for example `constant/triSurface/phaseVI_blade.stl`) so
runs and restarts are self-contained, and the staged copy MUST match the
committed STL sha256. A mismatch MUST abort preparation.

#### Scenario: STL staged and referenced

- GIVEN `runPhaseVI.sh -m asm-mesh -u <speed>` without `--run` or `--submit`
- WHEN the run directory is prepared
- THEN the STL is staged inside the run directory and `surfaceGeometry` references it with a case-relative path

#### Scenario: Staged hash matches

- GIVEN a prepared ASM-mesh run directory
- WHEN the staged STL is hashed
- THEN it matches the committed STL sha256

#### Scenario: Mismatch aborts

- GIVEN a staged STL whose bytes differ from the committed STL
- WHEN preparation validates the staged copy
- THEN it fails loudly instead of running with a stale surface
