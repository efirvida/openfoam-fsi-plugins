# Turbine Geometry Pipeline Specification

## Purpose

Defines the shared geometry pipeline at `turbinesFoam/geometry/` that generates
per-component STL surfaces from committed gmsh `.geo` sources driven by a Python
generator (`makeGeometry.py`), together with per-component metadata JSON and
provenance. The pipeline is deterministic and regenerable via
`makeGeometry.py --check` (mirroring `makeElementData.py` stale detection), and
is laid out to accommodate blade STLs in S2 without rework. S1 produces the
nacelle/hub STL (consumed by `nacelleSurfaceSource`) plus its metadata and
provenance; blade STL generation is deferred to S2.

## Requirements

### Requirement: Deterministic gmsh and Python generation

The pipeline MUST generate per-component STL files from committed gmsh `.geo`
sources driven by `makeGeometry.py`, and generation MUST be deterministic:
regenerating from the same committed inputs MUST reproduce byte-identical STL
files (matching sha256).

#### Scenario: Regeneration is byte-identical

- GIVEN the committed gmsh sources and generator inputs
- WHEN `makeGeometry.py` regenerates the STLs
- THEN the output sha256 matches the committed STLs exactly

### Requirement: Per-component STL output

The pipeline MUST emit one STL file per component, committed as binary STL. S1
MUST produce the nacelle/hub STL; the layout MUST reserve per-component output
for blades (blade ×3) to be generated in S2.

#### Scenario: Nacelle STL produced

- GIVEN the geometry pipeline run for S1
- WHEN the output directory is inspected
- THEN a committed binary nacelle/hub STL is present

#### Scenario: Per-component separation

- GIVEN the pipeline layout
- WHEN the output structure is inspected
- THEN each component (nacelle/hub now; blades later) has its own STL output path

### Requirement: Metadata JSON

The pipeline MUST emit per-component metadata JSON recording the data a
consumer needs: per-node normals and areas for the nacelle, with the schema
reserving per-node radial-station and chord-fraction mapping for blades.

#### Scenario: Nacelle metadata emitted

- GIVEN a generated nacelle STL
- WHEN the metadata directory is inspected
- THEN a nacelle metadata JSON records per-node normals and areas

#### Scenario: Blade mapping reserved in schema

- GIVEN the metadata schema
- WHEN the schema is inspected
- THEN it accommodates per-node radial-station and chord-fraction fields for blades

### Requirement: Provenance

The pipeline MUST include a `PROVENANCE.md` recording, for the generated
geometry, the source references (the paper's nacelle description; the MEXICO
rotor tables for blades), the generator version, and the sha256 of the inputs.

#### Scenario: Provenance present and complete

- GIVEN the geometry pipeline output
- WHEN `PROVENANCE.md` is inspected
- THEN it records the source references, generator version, and input sha256

### Requirement: `--check` regenerability

`makeGeometry.py --check` MUST detect when a committed STL, metadata, or
provenance file no longer matches what the current inputs regenerate, MUST exit
non-zero on mismatch, and MUST NOT modify committed artifacts.

#### Scenario: Clean tree passes

- GIVEN a geometry tree generated from the current inputs
- WHEN `makeGeometry.py --check` runs
- THEN it reports no stale artifacts and exits zero

#### Scenario: Stale STL detected

- GIVEN a committed STL that was hand-edited or left behind by an input change
- WHEN `makeGeometry.py --check` runs
- THEN it reports the stale STL and exits non-zero

#### Scenario: Check mode is non-destructive

- GIVEN a geometry tree with a stale artifact
- WHEN `makeGeometry.py --check` runs
- THEN the committed artifacts are left unchanged

### Requirement: Blade STL accommodation with S2 deferral

The pipeline's directory layout, generator structure, and metadata schema MUST
accommodate blade STLs with no rework, but S1 MUST NOT generate blade STLs;
blade STL generation is deferred to S2.

#### Scenario: Blade STLs deferred to S2

- GIVEN the S1 geometry pipeline run
- WHEN the output is inspected
- THEN no blade STL is generated, and the layout is ready to accept blade generation in S2

### Requirement: Pure-Python CI-safe test

The pipeline MUST be testable with a pure-Python test (`test_nacelle_data.py`)
that regenerates and checks the sha256 without a solver and without OpenFOAM.

#### Scenario: Data test runs without OpenFOAM

- GIVEN a Python environment with the test dependencies and no OpenFOAM
- WHEN `pytest` runs `test_nacelle_data.py`
- THEN the test passes, verifying deterministic regeneration and provenance presence
