# Delta for Phase VI Data Provenance

Delta for change `blade-actuator-surface` (S2). The S809 profile coordinates
become a committed Phase VI derived dataset under the same provenance rules as
the existing geometry, polar, and experimental data.

## ADDED Requirements

### Requirement: Committed S809 profile coordinates

The package MUST commit the S809 profile coordinates as a derived CSV under
`data/s809/`, with a `PROVENANCE.md` under the same rules as the other data
directories: the locally verified source (Somers, NREL/SR-440-6918), the source
PDF sha256, the table identifier, the extraction method, tool and version, the
extraction date, the cross-check source, and the committed CSV sha256. The
committed coordinates MUST be the data the blade geometry generator consumes;
the local, unverified text dump MUST NOT be the committed source.

#### Scenario: S809 CSV committed and attributed

- GIVEN the validation package
- WHEN the S809 coordinate CSV and its `PROVENANCE.md` are inspected
- THEN the CSV is present and the provenance records the report, table, extraction method, tool/version/date, cross-check, and hashes

#### Scenario: Coordinates parse

- GIVEN the committed S809 CSV
- WHEN the data-sanity tests parse it
- THEN upper and lower surface `x/c, z/c` pairs are present with a shared trailing edge and numeric values

## MODIFIED Requirements

### Requirement: Per-directory provenance records

Each data directory (`geometry/`, `polars/`, `experiment/`, and `s809/`) MUST
contain a `PROVENANCE.md` that records, for every committed file, the source URL
or DOI, the source file sha256, the table or sheet name, the row selection, the
units, and the extraction date, so that every committed number is traceable to a
specific NREL table or WDH workbook row, sheet, and unit.
(Previously: the three existing directories; `s809/` is new.)

#### Scenario: Provenance fields present

- GIVEN each data directory
- WHEN its `PROVENANCE.md` is inspected
- THEN it records the source URL or DOI, sha256, table or sheet name, row selection, units, and extraction date for each committed data file

#### Scenario: Field omission detected

- GIVEN a `PROVENANCE.md` missing one of the required fields
- WHEN the data-sanity tests run
- THEN the provenance test fails

### Requirement: Derived artifacts only

The package MUST commit only derived numeric CSVs and provenance documents.
Report PDFs and the WDH workbooks MUST NOT be committed, including the S809
source PDF, whose sha256 is recorded in the provenance instead.
(Previously: stated without naming an additional source PDF.)

#### Scenario: No PDFs or workbooks committed

- GIVEN the committed contents of the validation package
- WHEN the file list is inspected
- THEN no report PDF (including the S809 source) and no WDH workbook is present

### Requirement: Pure-Python data-sanity tests

The package MUST provide pytest data-sanity tests under `turbinesFoam/tests/`
covering polar and CSV parsing, geometry monotonicity, TSR mapping,
experimental anchors, provenance presence, and the S809 coordinate dataset. The
tests MUST NOT run a solver and MUST NOT require OpenFOAM, and this change MUST
NOT add a solver run or a validation regression gate to CI.
(Previously: the S809 dataset did not exist.)

#### Scenario: Tests pass without OpenFOAM

- GIVEN a Python environment with the test dependencies and no OpenFOAM
- WHEN `pytest` runs the data-sanity tests
- THEN they pass

#### Scenario: S809 provenance omission fails

- GIVEN an S809 provenance record missing a required field
- WHEN the data-sanity tests run
- THEN the test fails

#### Scenario: Anchor mismatch fails the tests

- GIVEN an experimental CSV whose anchor value disagrees with the verified row
- WHEN the data-sanity tests run
- THEN the anchor test fails

#### Scenario: Missing provenance fails the tests

- GIVEN a data directory without `PROVENANCE.md`
- WHEN the data-sanity tests run
- THEN the provenance test fails

### Requirement: Source attribution and provenance pinning

The package MUST credit the adaptation source `mttbrbr/single-actuator-line`
(main `8284be8c…`) under GPL-3.0-or-later, cite the NREL sources (TP-500-29955,
DOI 10.2172/15000240; TP-442-7817; WDH workbooks, DOI
10.21947/WDH-DAP/1910052; and NREL/SR-440-6918 for the S809 profile), and record
the `of-plugins` commit plus the ASM patch note in the case README or the
provenance documents.
(Previously: the S809 report was not a committed dataset source.)

#### Scenario: Attribution present

- GIVEN the case README and the provenance documents
- WHEN they are inspected
- THEN the SAL adaptation credit, the NREL citations including the S809 report, and the pinned of-plugins commit with the ASM patch note are present
