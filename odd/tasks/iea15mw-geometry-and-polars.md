# IEA 15-240-RWT case — P0 geometry + P1 polar ingestion

- **Branch:** `feat/dagsorensen-tip-correction`
- **Contract:** `odd/tasks/iea15mw-case-readiness.md` (plan P0–P6)
- **Scope:** P0 (reconcile + emit the blade geometry table and its loader) and
  P1 (AirfoilInfo -> `profileData` polar converter with `--check`).
- **Not in scope:** the case assembly (P2), physics runs (P3+), any C++ change.
- **Inputs are read-only:** the WindIO yaml, the AeroDyn blade table and the 50
  per-station polars are never modified. `fem-shell` is a read-only cross-check.

## P0 — radius decision (evidence)

Three values were on the table:

| Source | Rotor diameter | Radius |
|---|---|---|
| NREL/TP-5000-75698, Table ES-1 / 1-1 (original report) | 240 m | 120.0 m |
| Repo WindIO ontology yaml + tabular xlsx (published) | **241.35064632 m** | **120.67532316 m** |
| `IEA-15-240-RWT.yaml` at the sim root (modified) | 242.23775645 m | 121.118878225 m |

**Decision: R = 120.675 m (D = 241.35064632 m).** Evidence:

1. The repo's own ontology yaml `IEA-15-240-RWT/WT_Ontology/IEA-15-240-RWT.yaml`
   gives `rotor_diameter: 241.35064632`. The sim-root yaml is a windIO-2.0
   re-serialization of that same file with **only** `rotor_diameter` changed
   (242.23775645); chord, twist, pitch_axis, reference_axis and the hub diameter
   are identical.
2. `Documentation/IEA-15-240-RWT_tabular.xlsx` sheet **Overview** gives
   `Rotor diameter [m] = 241.35064632`; the **Rotor Performance** sheet tip speed
   at 5 rpm is 63.185 m/s = 0.523599 rad/s x 120.675 m, i.e. WISDEM used
   R = 120.675 m.
3. OpenFAST `IEA-15-240-RWT-Monopile_ElastoDyn.dat`: `TipRad = 120.97 m`,
   `HubRad = 3.97 m`, `PreCone = -4.0 deg`. Then
   `2 x TipRad x cos(PreCone) = 2 x 120.97 x cos(4 deg) = 241.35065 m`, matching
   the published value to 8 significant figures. The published R is the
   **projected (in-plane)** tip radius.
4. `fem-shell`'s V-01 test hard-codes `_ROTOR_RADIUS = 120.675`.

**No primary source supports 242.23775645**; it is a modification of the
sim-root yaml. `fem-shell`'s `load_blade_aero` inherits it (`rotor_radius =
121.1189`), but its stations and its own test use HubRad = 3.97 and R = 120.675,
so the loader is internally inconsistent and the test value is the published one.

**Hub radius:** the physical hub radius is **3.97 m** (hub diameter 7.94 m,
ElastoDyn `HubRad`). The published R = 120.675 is *not* `HubRad + blade_span`
(that would be 120.97); the 0.295 m difference is the 4 deg precone projection:

```
R_published = (HubRad + blade_span) * cos(precone) = 120.97 * cos(4 deg)
HubRad      = R_published / cos(precone) - blade_span = 3.9699... ~ 3.97 m
```

## P0 — geometry table

- `data/iea15mw_blade.csv`, 50 rows, columns
  `r_over_R, radius_m, span_m, chord_m, twist_deg, pitch_axis, chord_mount,
  pitch_deg, airfoil_id`.
- Source of truth: `IEA-15-240-RWT_AeroDyn15_blade.dat` (chord/twist/span).
  Cross-checks (numerical, in README): WindIO yaml `outer_shape_bem` and
  `aeromodel` loader both agree to < 1.2e-4 m (chord) and < 1e-5 deg (twist).
- `radius_m = HubRad + BlSpn` (along-blade, tip 120.9699 m, ElastoDyn `TipRad`).
  The ALM input radius; the case applies `coneAngle 4`.
- `r_over_R = radius_m * cos(precone) / R_published` -> tip exactly 1.0.
- `chord_mount` = section aerodynamic centre, linearly interpolated across the
  WindIO `airfoil_position` grid: 0.5 (circular root), 0.316 (SNL-FFA-W3-500),
  **0.25 for the FFA-W3 families** (outboard majority).
- `pitch_deg = -(twist_deg + collective)` (turbinesFoam ALM mount sign).

### nElements constraint

`actuatorLineSource.C:145-155` requires `nElements % (nGeometryPoints - 1) == 0`.
50 rows -> 49 segments -> **recommended nElements = 147** (3 per segment,
~0.80 m spacing, matching the Phase VI chord-relative element density);
98 (2/segment) as the cheap variant; 49 the minimum.

## P1 — polar converter

- `scripts/buildPolars.py`: AirfoilInfo v1.01.x -> `profileData` (`Re` + `data`).
  Parses by locating `NumAlf` (so the optional 30-coefficient UA block and all
  `!` comments are skipped robustly) and `Re` (millions).
- Team `Cm` handling: **no sign conversion.** AirfoilInfo Cm is the quarter-chord
  pitching moment, positive nose-up; it correlates +1.000 with the WindIO
  `c_m` for the matching sections and matches the NREL S809 `Cm` that
  turbinesFoam's `profileData` already consumes verbatim. The readiness note's
  "different Cm sign convention" is not reproducible.
- Per-station set: **all 50 files** (`data/polars/polar_NN.dat`), matching the
  per-node `BlAFID = 1..50`; no further interpolation step is introduced.
- `--check` re-reads the source and fails on missing/stale output.

## Tasks

- [x] T1 — write the geometry tools (`tools/blade_geometry.py`) + loader.
- [x] T2 — emit `data/iea15mw_blade.csv`.
- [x] T3 — write the converter (`scripts/buildPolars.py`).
- [x] T4 — emit the 50 `data/polars/polar_NN.dat`.
- [x] T5 — tests in `turbinesFoam/tests/test_iea15mw_case.py`.
- [x] T6 — README + PROVENANCE.
- [ ] T7 — commit (parent-owned; worker does not commit).
