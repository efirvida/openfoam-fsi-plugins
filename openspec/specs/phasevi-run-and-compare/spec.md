# Phase VI Run and Compare Specification

## Purpose

Defines the execution-and-evaluation capability of the Phase VI validation
package: the staged run preparation on the verified Slurm environment with
tip-constrained fixed time steps and restart, and the comparison tool that
merges simulation turbine-level and spanwise output with the committed
experimental anchors and reports metrics with documented definitions, fail-loud
input handling, and honest, evidence-bounded claims.

## Requirements

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

### Requirement: Staged run plan

The run preparation MUST implement the staged plan: Stage 0 — mesh generation
and `checkMesh` for both mesh resolutions plus stability runs of both models at
7 m/s on D/32 for at most 0.3 revolutions on the authorized development queue;
Stage 1 — 7 m/s URANS ALM and ASM on D/32 first, then D/48; Stage 2 — the wind
speeds {10, 13, 15, 25} m/s and the Sequence S 7 m/s repeat; Stage 3
(optional) — IDDES confirmation, the `nChordwise` {1, 3, 5} sweep at D/48 and
7 m/s, and the D/64 sensitivity mesh. URANS with `kOmegaSST` MUST be the
headline model; IDDES MUST remain an optional confirmation.

#### Scenario: Stage 0 stability runs bounded

- GIVEN Stage 0 on the authorized development queue
- WHEN the stability runs are launched at 7 m/s on D/32 for both models
- THEN each run is bounded to at most 0.3 revolutions and both complete without divergence

#### Scenario: Stage 1 headline ordering

- GIVEN the staged plan
- WHEN Stage 1 is prepared
- THEN it contains 7 m/s URANS runs for ALM and ASM with D/32 first and D/48 second

#### Scenario: Stage 2 extension and Sequence S

- GIVEN the staged plan
- WHEN Stage 2 is prepared
- THEN it contains the {10, 13, 15, 25} m/s points and the Sequence S 7 m/s repeat

#### Scenario: Stage 3 optional items

- GIVEN the staged plan
- WHEN Stage 3 is prepared
- THEN IDDES, the `nChordwise` {1, 3, 5} sweep, and the D/64 mesh are optional items and not part of the headline

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

### Requirement: Restart from the latest written time

The run preparation MUST support restarting an interrupted run from the latest
written time so that resubmission continues the run instead of restarting it
from the beginning, and output MUST be written at intervals that bound disk
usage while preserving the averaging window.

#### Scenario: Interrupted run continues

- GIVEN a run that was interrupted after writing time directories
- WHEN the run is resumed
- THEN it continues from the latest written time and does not restart from the initial condition

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

### Requirement: Averaging window and convergence gate

Turbine and spanwise metrics MUST be averaged over revolutions 4–12 after
discarding revolutions 0–4, and the comparison MUST report whether the rolling
window variation of the power and thrust coefficients stays below 1 % across
the averaging window, flagging results whose window is still drifting.

#### Scenario: Averaged window reported

- GIVEN a 12-revolution run
- WHEN the comparison runs
- THEN the reported metrics state that they are averaged over revolutions 4–12

#### Scenario: Drift flagged

- GIVEN a run whose rolling power or thrust coefficient variation exceeds 1 % across the averaging window
- WHEN the comparison runs
- THEN the result is flagged as not converged instead of being reported as a stable mean

### Requirement: Metric definitions fixed against the NREL reports

The comparison MUST report dimensional turbine-level power (W) and shaft torque
(Nm) from the simulation torque (blades and hub) against the measured ROTPOW
and LSSTQCOR values, and rotor thrust from the blade forces against the
measured EAEROTH values, and MUST state the reference air density used. The
simulation-side thrust scope (hub and tower inclusion) MUST be stated
explicitly. The spanwise comparison MUST use the simulation `c_ref_n` and
`c_ref_t` against the measured CN and CT. The metric definitions MUST be fixed
against the NREL report definitions before production results are claimed and
MUST be documented in the comparison output.

#### Scenario: Dimensional metrics with stated density

- GIVEN a comparison run
- WHEN the turbine-level output is inspected
- THEN power, torque, and thrust are reported in dimensional units and the reference air density is stated

#### Scenario: Thrust scope stated

- GIVEN a comparison run
- WHEN the output is inspected
- THEN it states whether the simulation-side thrust includes the hub and whether a tower is present

#### Scenario: Spanwise coefficient comparison

- GIVEN a comparison run
- WHEN the spanwise output is inspected
- THEN `c_ref_n` and `c_ref_t` are compared against CN and CT at 30 %, 47 %, 63 %, 80 %, and 95 % span

### Requirement: Spanwise CM excluded from the headline

The headline comparison MUST NOT report spanwise CM while the element CSV
provides no `cm` column; the missing column and its follow-up change MUST be
documented. Spanwise CM MAY be reported only if a future element-level CSV
provides a `cm` column.

#### Scenario: CM absent from the headline

- GIVEN the element CSV format without a `cm` column
- WHEN the comparison output is inspected
- THEN no spanwise CM comparison is claimed
- AND the missing column and the follow-up change are documented

### Requirement: Sign-convention verification gate

No production run MUST be launched before the 7 m/s configuration reproduces
the measured sign of the normal and tangential load coefficients with the
measured TSR, the axis (−1, 0, 0), and the `-(twist + pitch)` convention.

#### Scenario: Sign gate blocks a mirrored configuration

- GIVEN a 7 m/s verification run whose spanwise load signs oppose the measured signs
- WHEN the production launch gate is evaluated
- THEN the gate fails and production runs are not launched

#### Scenario: Sign gate passes

- GIVEN a 7 m/s verification run that reproduces the measured signs
- WHEN the production launch gate is evaluated
- THEN the gate passes

### Requirement: Fail-loud on missing input

The comparison tool MUST report any missing or incomplete input — run
directories, turbine CSVs, element CSVs, or experimental files — and MUST exit
non-zero instead of producing a misleading comparison.

#### Scenario: Missing run directory

- GIVEN a comparison invoked with a missing or incomplete run directory
- WHEN the tool runs
- THEN it reports the missing input and exits non-zero

#### Scenario: Missing experimental data

- GIVEN a comparison invoked with a missing experimental CSV
- WHEN the tool runs
- THEN it reports the missing input and exits non-zero

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
