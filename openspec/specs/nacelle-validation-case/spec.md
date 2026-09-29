# Nacelle Validation Case Specification

## Purpose

Defines the periodic-nacelle benchmark at
`turbinesFoam/validation/nacelle-asn/`, the paper-faithful validation anchor for
the nacelle actuator surface model (Yang & Sotiropoulos, arXiv:1702.02108v4,
Sec. 4.1). The case runs the nacelle model rotor-less against the paper's
wall-resolved-LES reference: a hemisphere + cylinder nacelle at Re=1000 in a
30R×20R×20R periodic domain, on coarse and medium grids, with digitized
reference profiles (with provenance), per-station acceptance, and staged HPC
execution (dev partition now; nothing on the long queue before authorization).

## Requirements

### Requirement: Paper-faithful geometry

The case MUST use the paper's nacelle geometry — a hemisphere + cylinder of
radius R at Re=1000 (based on the cylinder radius) — in a domain of
30R×20R×20R with periodic streamwise and free-slip crosswise boundaries. The
nacelle surface MUST target approximately 2652 triangles (the paper's count),
taken from the geometry pipeline's nacelle STL.

#### Scenario: Geometry matches the paper

- GIVEN the case configuration
- WHEN the domain, boundaries, and surface are inspected
- THEN the domain is 30R×20R×20R, the nacelle is a hemisphere + cylinder at Re=1000, and the surface mesh targets ~2652 triangles

#### Scenario: Consumes the pipeline STL

- GIVEN the nacelle validation case
- WHEN the nacelle `fvOptions` entry is inspected
- THEN its geometry path points at the pipeline-generated nacelle STL

### Requirement: Coarse and medium grids

The case MUST define two grids: a coarse grid of 153×80×80 (Δx=R/2.5,
~1M cells) and a medium grid of 115×151×151 (Δx=R/3.75, ~2.6M cells). The
paper's 502×348×348 (Δx=R/8) grid is the wall-resolved-LES reference resolution
only and MUST NOT be produced as a run grid.

#### Scenario: Two run grids defined

- GIVEN the case configuration
- WHEN the mesh resolutions are inspected
- THEN the coarse (153×80×80) and medium (115×151×151) grids are defined

#### Scenario: Reference grid not produced

- GIVEN the case package
- WHEN the run grids are generated
- THEN the 502×348×348 grid is used only as the reference resolution, not generated for a run

### Requirement: Digitized wall-resolved-LES reference with provenance

The case MUST include digitized reference profiles — time-averaged ⟨u⟩(z) and
k(z) at 1R/3R/5R/7R downstream — taken from the paper's wall-resolved-LES
figures, with provenance recording the source figure, the digitization method,
and a two-source cross-check. The reference MUST be documented as the paper's
502×348×348 wall-resolved LES, whose dynamic SGS model is not available in
standard OpenFOAM.

#### Scenario: Reference profiles digitized and provenanced

- GIVEN the validation data directory
- WHEN the reference profiles and their `PROVENANCE.md` are inspected
- THEN the profiles at 1R/3R/5R/7R are present and the provenance records the source figure, method, and cross-check

#### Scenario: Reference limitation documented

- GIVEN the case documentation
- WHEN the reference description is inspected
- THEN it states the reference is the paper's 502×348×348 wall-resolved LES and that the dynamic SGS model is unavailable in standard OpenFOAM

### Requirement: Per-station acceptance with coarse and medium differentiation

Acceptance MUST be evaluated per-station and per-grid: the medium grid MUST
agree at all stations, while the coarse grid is only expected to agree at 1R and
in the far wake (the paper reports coarse deficits too large at 3R–7R). The
comparison MUST NOT over-promise coarse-grid agreement.

#### Scenario: Medium grid agreed at all stations

- GIVEN a completed medium-grid run
- WHEN its profiles are compared to the reference
- THEN agreement is assessed at every station (1R, 3R, 5R, 7R)

#### Scenario: Coarse grid accepted per-station only

- GIVEN a completed coarse-grid run
- WHEN its profiles are compared to the reference
- THEN agreement is only claimed at 1R and the far wake, consistent with the paper's coarse-grid finding

### Requirement: Metric definitions

The comparison MUST use time-averaged ⟨u⟩(z) and k(z) profiles at 1R/3R/5R/7R
downstream (with a 10R stretch) and the drag coefficient, evaluated against the
digitized wall-resolved-LES reference. The paper's permeable-disk comparison
value CD=0.48 is a reference datum, not a target for the actuator-surface case.

#### Scenario: Metrics defined against the reference

- GIVEN the compare script configuration
- WHEN the metric definitions are inspected
- THEN ⟨u⟩(z), k(z) at 1R/3R/5R/7R (+10R) and the drag coefficient are defined against the digitized reference

#### Scenario: Permeable-disk value is a datum, not a target

- GIVEN the comparison documentation
- WHEN the drag-coefficient comparison is described
- THEN CD=0.48 is cited as the paper's permeable-disk comparison datum, not as an acceptance target

### Requirement: Turbulence closure adaptation

The headline closure MUST be LES with WALE — the paper's dynamic SGS model is
not in standard OpenFOAM — with the adaptation documented. A URANS k-ω SST
fallback MAY be provided as a cheaper documented smoke path (a weaker claim),
not the headline.

#### Scenario: WALE headline with documented adaptation

- GIVEN the case configuration
- WHEN the turbulence model is inspected
- THEN the headline is LES with WALE and the adaptation from the paper's dynamic SGS model is documented

#### Scenario: URANS fallback is a smoke path only

- GIVEN a URANS k-ω SST configuration, if provided
- WHEN the documentation is inspected
- THEN it is described as a cheaper smoke fallback with a weaker claim, not the headline

### Requirement: Staged HPC execution

The case MUST stage runs: prepare and dev-partition mesh/stability now, with
production averaging on the long queue after authorization. The package MUST
NOT launch anything on the long queue before authorization.

#### Scenario: Dev-partition stage only until authorized

- GIVEN the staged run plan
- WHEN the slurm scripts are inspected
- THEN a dev-partition stage0 job prepares the mesh and checks stability, and the production job is prepared but not launched

#### Scenario: Long queue gated on authorization

- GIVEN no long-queue authorization has been granted
- WHEN the case package is run
- THEN nothing is submitted to the long queue

### Requirement: Case package tooling mirroring the phaseVI pattern

The case MUST mirror the Phase VI package pattern: a `config/case.yaml` single
source of truth rendered by `generate_case.py` (with non-destructive `--check`),
a compare script, slurm stage0/production scripts, a committed case skeleton,
gitignored `runs/`/`results/`, and pure-Python pytest coverage. The solver MUST
be `pimpleFoam`.

#### Scenario: Single source of truth renders the case

- GIVEN the case `config/case.yaml`
- WHEN `generate_case.py` renders the case
- THEN the skeleton reflects the configured domain, grid, solver (`pimpleFoam`), and turbulence model

#### Scenario: Non-destructive check mode

- GIVEN a rendered case with a stale generated file
- WHEN `generate_case.py --check` runs
- THEN it reports the stale file, exits non-zero, and leaves files unchanged

#### Scenario: Pure-Python tests present

- GIVEN the case package
- WHEN its pytest modules run without a solver
- THEN they pass, covering the comparison and data-sanity behavior

### Requirement: Case package documentation and attribution

The case MUST include a `README.md` documenting the setup, the staged run plan,
the metric definitions, the closure adaptation (WALE vs the paper's dynamic
SGS), and the modelling limitations. The root `README.md` and root
`CHANGELOG.md` MUST be updated to reference the validation package and attribute
the paper.

#### Scenario: Case README documents setup and limitations

- GIVEN the case package
- WHEN its `README.md` is inspected
- THEN it documents the setup, staged run plan, metric definitions, closure adaptation, and limitations

#### Scenario: Root documentation updated

- GIVEN the repository root documentation
- WHEN `README.md` and `CHANGELOG.md` are inspected
- THEN both reference the nacelle validation package and attribute the paper (arXiv:1702.02108v4)
