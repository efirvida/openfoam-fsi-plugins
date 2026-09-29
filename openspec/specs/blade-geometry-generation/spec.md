# Blade Geometry Generation Specification

## Purpose

Defines the deterministic generator for the Phase VI blade component in the
shared `turbinesFoam/geometry/` pipeline: the committed S809 profile
coordinates with recorded extraction provenance, a pure-Python structured loft
over all 26 committed stations producing one wetted-surface binary STL, per-node
`radial_station`/`chord_fraction` metadata, and byte-identical
`makeGeometry.py --check`. It extends the S1 pipeline without changing the
gmsh-driven nacelle component.

## ADDED Requirements

### Requirement: Committed S809 coordinates with extraction provenance

The S809 profile coordinates MUST be committed as a derived dataset with a
`PROVENANCE.md` recording the locally verified source (Somers, NREL/SR-440-6918),
the source PDF sha256, the table identifier, the extraction method, tool and
version, the extraction date, the cross-check source, and the committed file
sha256. The coordinates MUST be extracted with a recorded, repeatable recipe
(PyMuPDF is the recorded tool; `pdftotext` is absent on the host) and cross-
checked against at least one independent source; a local text dump MUST NOT be
treated as authoritative on its own.

#### Scenario: Provenance complete

- GIVEN the committed S809 coordinate CSV
- WHEN its `PROVENANCE.md` is inspected
- THEN it records the report, PDF sha256, table id, extraction method/tool/version/date, cross-check, and committed sha256

#### Scenario: Coordinates parse as an airfoil profile

- GIVEN the committed S809 CSV
- WHEN the data-sanity test parses it
- THEN upper and lower surface `x/c, z/c` pairs are present with a shared trailing edge at (1.0000, 0.0000)

#### Scenario: Verified source, not the dump alone

- GIVEN the extraction chain
- WHEN the provenance is inspected
- THEN the coordinates are tied to the verified PDF and a cross-check, not to the local text dump alone

### Requirement: Pure-Python structured loft over the full wetted span

The generator MUST build one binary STL for the `phaseVI_blade` component from
the committed 26-station blade geometry and the committed S809 coordinates using
a pure-Python structured loft with fixed section point counts and fixed
triangulation, covering r = 0.5083 m → 5.029 m including the cylinder/transition
stations at r ≤ 0.8835 m. It MUST NOT use gmsh for blades. The output MUST be
the wetted surface only, with no root or tip caps; tip force zeroing, end
effects, and the inboard `chord_mount` transition remain BEM-side.

#### Scenario: Full span covered

- GIVEN the 26 committed stations and the 8 of 50 blade elements that are cylinder elements (`case/system/fvOptions.ASM:63`)
- WHEN the blade STL is generated
- THEN the surface spans all 26 stations, so no element's station lacks a surface patch

#### Scenario: Wetted surface only

- GIVEN the generated STL
- WHEN its topology is inspected
- THEN it contains the wetted surface without root or tip caps and the BEM-side tip/end-effect behavior is unchanged

#### Scenario: No gmsh dependency

- GIVEN a host without a runnable gmsh
- WHEN the blade component is generated or checked
- THEN generation and `--check` succeed for `phaseVI_blade`

### Requirement: Deterministic byte-identical regeneration

Regeneration from the committed inputs MUST reproduce the committed STL and
metadata byte-identically. `makeGeometry.py --check --component phaseVI_blade`
MUST exit zero on a clean tree, exit non-zero on a stale artifact, and MUST NOT
modify the tree.

#### Scenario: Byte-identical check

- GIVEN the committed blade artifacts
- WHEN `makeGeometry.py --check --component phaseVI_blade` runs
- THEN the regenerated STL and metadata match the committed bytes and the exit code is zero

#### Scenario: Stale blade artifact detected

- GIVEN a hand-edited or stale blade STL or metadata
- WHEN `--check` runs
- THEN it reports the stale artifact and exits non-zero without writing

### Requirement: Canonical STL and per-node station/chord metadata

The STL MUST be written with the pipeline's canonical triangle order, fixed
header, and recomputed facet normals (`makeGeometry.py:194-219`). The metadata
MUST populate `radial_station` and `chord_fraction` for every node, replacing
the reserved null placeholders (`makeGeometry.py:371-373`), together with the
component name, format version, input sha256, and STL sha256.

#### Scenario: Metadata populated

- GIVEN the generated blade metadata
- WHEN a node entry is inspected
- THEN it carries numeric `radial_station` and `chord_fraction` values, one entry per canonical triangle, plus the component/version/hash fields

#### Scenario: Canonical order is environment-independent

- GIVEN two regenerations in different environments
- WHEN the STL bytes are compared
- THEN they are identical because the triangles are canonicalized, sorted, and written with the fixed header

### Requirement: Component registration and naming policy

The generator MUST register the blade component under the rotor-qualified name
`phaseVI_blade` with a non-gmsh builder entry alongside the gmsh-driven
`nacelle`, and MUST retire the `blade0/1/2` reservation. Those names MUST no
longer be advertised as the reserved S2 blade outputs; a future MEXICO blade is
a separate component owned by the `mexico-validation` change. One STL MUST serve
both identical Phase VI blades.

#### Scenario: Component accepted

- GIVEN the generator CLI
- WHEN `--component phaseVI_blade` is requested
- THEN the blade component is generated or checked through the Python builder route

#### Scenario: Reservation retired

- GIVEN the generator CLI and documentation
- WHEN the retired `blade0/1/2` names are inspected
- THEN they are not presented as deferred S2 blade outputs

#### Scenario: Nacelle path unchanged

- GIVEN the generator registry
- WHEN the nacelle component is generated or checked
- THEN it still uses the pinned gmsh path and its committed artifacts and hash records are unchanged

### Requirement: Blade component documentation

The geometry `README.md` and `PROVENANCE.md` MUST document the `phaseVI_blade`
component: its Phase VI/S809 source, its pure-Python builder, the committed S809
coordinates dataset, and the naming resolution. They MUST NOT advertise the
retired `blade0/1/2` MEXICO deferral as pending S2 work.

#### Scenario: Documentation updated

- GIVEN the geometry documentation
- WHEN it is inspected
- THEN it documents the `phaseVI_blade` component, its S809 source and builder, and the retired `blade0/1/2` naming

### Requirement: Pure-Python blade data tests

The package MUST provide a pure-Python test (for example
`tests/test_blade_data.py`) covering the S809 provenance, the coordinate parse,
the blade metadata completeness, and byte-identical regeneration. The test MUST
NOT require a solver or OpenFOAM and MUST skip generation-dependent checks
explicitly when a runtime dependency is unavailable.

#### Scenario: Tests pass without OpenFOAM

- GIVEN a Python environment with the test dependencies and no OpenFOAM
- WHEN `pytest` runs the blade data tests
- THEN they pass

#### Scenario: Missing provenance fails

- GIVEN missing or incomplete S809 provenance
- WHEN the data-sanity tests run
- THEN the provenance test fails
