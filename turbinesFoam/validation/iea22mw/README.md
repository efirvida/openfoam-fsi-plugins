# IEA 22-280-RWT case — geometry, polars and case assembly

Counterpart of [`../iea15mw`](../iea15mw/README.md) for the 22 MW reference
turbine: reproduced blade geometry, `profileData` polars and the assembled
OpenFOAM case skeleton for turbinesFoam. Sources, sha256 and the radius decision
are in [`PROVENANCE.md`](PROVENANCE.md). Task: `odd/tasks/iea22-case-readiness.md` T1.

> The IEA 22 MW reference turbine has **no measurements**. Any comparison is
> code-to-code (OpenFAST BEM/OLAF, HAWC2, WISDEM). The measurement claim for
> turbinesFoam rests on the NREL Phase VI case.

## Layout

```
tools/blade_geometry.py     decode + emit the geometry table; tested loader (59 stations)
scripts/buildPolars.py      AirfoilInfo -> profileData converter, with --check
tools/generate_case.py      render case/ from the committed data, with --check
data/iea22mw_blade.csv      committed geometry table (59 stations)
data/polars/polar_NN.dat    committed profileData polars (NN = 00..58, BlAFID = NN+1)
case/                       generated OpenFOAM skeleton (system/, constant/, 0.org/)
PROVENANCE.md               sources, sha256, radius decision, limitations
data/openfast-v5-templates/ OpenFAST v5.0.0 AeroDyn BEM/OLAF input templates (generated, see its README)
scripts/openfast_iea22.py   setup / sweep / run / extract of the OpenFAST reference cases
scripts/build_openfast_templates.py, rated_table_check.py, import_olaf_reference.py
openfast/README.md          OpenFAST reference workflow, preflight recipe
```

Rebuild / verify (source repository paths default to the documented ones; use
`python -I`, the sources are untrusted data):

```sh
python -I turbinesFoam/validation/iea22mw/tools/blade_geometry.py [--check]
python -I turbinesFoam/validation/iea22mw/scripts/buildPolars.py [--check]
python -I turbinesFoam/validation/iea22mw/tools/generate_case.py [--check]
python -m pytest turbinesFoam/tests/test_iea22mw_case.py -q
```

## Key numbers (differences from IEA-15 in bold)

| | IEA-15-240 | IEA-22-280 |
|---|---|---|
| Rotor radius R | 120.67532316 m, *projected* (`TipRad*cos 4 deg`) | **142.0 m = `TipRad`, not projected** |
| Hub radius / precone | 3.97 m / 4 deg | 4.2 m / 4 deg |
| Blade stations / polars | 50 / 50 | **59 / 59** |
| Prebend at tip | 4 m | **7 m** |
| `r_over_R` | `radius_m*cos(precone)/R` | `radius_m/R` |
| Hub height / overhang / shaft tilt | 150 m / 12.03 m / 6 deg | 170 m / 14 m / 6 deg (tilt only on the nacelle) |
| Operating point | 10.659 m/s, 7.518 rpm, pitch 0 | 11.134927 m/s, 6.853997 rpm, pitch 4.127462 (WISDEM rated row) |
| Elements per blade | 147 | 174 (3 per segment) |

## How the generator is shared

`tools/generate_case.py` does not copy the 2800-line IEA-15 renderer. It loads
`../iea15mw/tools/generate_case.py` into a private module whose
`import blade_geometry` resolves to this package's `tools/blade_geometry.py` and
whose turbine constants (operating point, radius/diameter, hub height, element
count, data paths, castellated-mesh extents) are replaced by the IEA-22 values.
All flags, `TURBINE_*` environment bridges and the ALM / ASM / ASM-MESH variants
therefore behave exactly as in IEA-15, and a fix there reaches this case. The
IEA-15 side only gained backward-compatible parameters (`n_stations`, default
50) in `blade_geometry.read_blade_table/read_geometry`, and
`blade_profile_names()` counts the stations of the geometry CSV.
`buildPolars.py` likewise reuses the IEA-15 AirfoilInfo parser.

The mesh domain scales with `ROTOR_DIAMETER`; the castellated extents are the
IEA-15 absolute values scaled by `142/120.675` (see PROVENANCE). The case has
only been rendered, never meshed or run.

## Conventions (identical to IEA-15)

- ALM element rows `(axialDistance radius azimuth chord chordMount pitch
  curveAngle)`, radius = `HubRad + BlSpn` with `coneAngle 4`.
- `chordMount` = section aerodynamic centre (0.5 root cylinder, 0.25 airfoils).
- `pitch = -(BlTwist + collective)`; prebend `axialDistance = -BlCrvAC`.
- `Cm` passed through unchanged; `liftReCorrExp 0` in every polar.

## OpenFAST code-to-code reference (T2)

The reference for the ALM/ASM comparison is OpenFAST AeroDyn BEMT and OLAF with the same polars, rigid fixed-speed
rotor and uniform rated inflow; see [`openfast/README.md`](openfast/README.md) and
[`data/openfast-v5-templates/README.md`](data/openfast-v5-templates/README.md). Prepared and preflighted only;
no converged OLAF run exists yet.
