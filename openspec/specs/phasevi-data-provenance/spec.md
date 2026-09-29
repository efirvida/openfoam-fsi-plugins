# Phase VI Data Provenance Specification

## Purpose

Defines the input-data capability of the Phase VI validation package: the
derived geometry, polar, and experimental CSVs committed under
`turbinesFoam/validation/phaseVI/data/`, the per-directory `PROVENANCE.md`
documents that bind every committed number to a specific NREL table or WDH
workbook sheet, row, and unit, and the pure-Python data-sanity tests that
enforce those bindings without a solver or OpenFOAM.

## Requirements

### Requirement: Derived blade geometry data

The package MUST commit `data/geometry/phaseVI_blade.csv` derived from
NREL/TP-500-29955 Table A-1, with attribution to that source. The committed
geometry values MUST match the source table.

#### Scenario: Geometry committed and attributed

- GIVEN the validation package
- WHEN `data/geometry/phaseVI_blade.csv` and its `PROVENANCE.md` are inspected
- THEN the CSV is present and the provenance attributes it to TP-500-29955 Table A-1

#### Scenario: Geometry parses and is monotonic

- GIVEN the committed geometry CSV
- WHEN the data-sanity tests parse it
- THEN the blade span coordinate is strictly monotonic and the chord and twist columns parse as numbers

### Requirement: S809 polars rebuilt from NREL tables

The committed S809 polar data MUST be rebuilt from the NREL tables
(TP-500-29955 Tables A-3..A-8 and TP-442-7817) and MUST NOT reuse the SAL
scaffold's `S809_Re1M_extended` polar. The package MUST provide a single-Re OSU
Re 1 M total-drag baseline and a multi-Re set as a sensitivity variant, and the
provenance MUST document each Reynolds level's source and angle-of-attack range.

#### Scenario: NREL tables are the source

- GIVEN the committed polar files and their `PROVENANCE.md`
- WHEN the provenance records are inspected
- THEN every polar file cites an NREL table and no polar file cites the scaffold polar as its source

#### Scenario: Baseline and sensitivity polar sets

- GIVEN the committed polar data
- WHEN the polar set is inspected
- THEN a single-Re OSU Re 1 M total-drag baseline and a multi-Re sensitivity set are both present

#### Scenario: Polar files parse

- GIVEN the committed polar files
- WHEN the data-sanity tests parse them
- THEN each file yields monotonic angle-of-attack samples with numeric lift, drag, and moment coefficient columns

### Requirement: Experimental data extraction rules

The committed experimental CSVs MUST be extracted from the WDH statistics
workbook sheet `ldsmean`, MUST include only 0°-yaw rows, and MUST cover the
Sequence H and Sequence S performance and spanwise data. The performance rows
MUST carry the measured TSR and the dimensional power (ROTPOW), shaft torque
(LSSTQCOR), and rotor thrust (EAEROTH) statistics, and the spanwise data MUST
cover the 30 %, 47 %, 63 %, 80 %, and 95 % span stations.
The derived values MUST match the verified anchors exactly, including
`h0700000` (5.946 kW, 789.86 Nm, 1132.07 N) and `h2500000` (11.951 kW,
1580.41 Nm, 4028.63 N).

#### Scenario: Verified anchors reproduced

- GIVEN the committed experimental performance CSV
- WHEN the Sequence H 7 m/s and 25 m/s rows are read
- THEN they contain 5.946 kW / 789.86 Nm / 1132.07 N and 11.951 kW / 1580.41 Nm / 4028.63 N respectively

#### Scenario: Yaw rows excluded

- GIVEN the source workbook contains yaw sweeps in the same `ldsmean` sheet
- WHEN the committed experimental CSVs are inspected
- THEN only 0°-yaw rows are present

#### Scenario: Measured TSR mapping

- GIVEN the committed experimental performance CSV
- WHEN the per-speed Sequence H rows are read
- THEN each speed carries its measured TSR (5.408, 3.798, 2.920, 2.530, 1.898, and 1.521 for 7, 10, 13, 15, 20, and 25 m/s)

#### Scenario: Spanwise stations present

- GIVEN the committed spanwise experimental CSV
- WHEN its stations are inspected
- THEN normal and tangential load coefficients are present at 30 %, 47 %, 63 %, 80 %, and 95 % span

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

