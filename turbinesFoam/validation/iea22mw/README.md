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
tools/mesh_proportions.py   R-unit table IEA-15 vs IEA-22 mesh quantities (exit 1 if not proportional)
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
| Hub height / overhang / shaft tilt | 150 m / 12.03 m / 6 deg (nacelle STL) | 170 m / 14 m / **none** (owner decision 2026-11-02; `--shaft-tilt on` opts in; precone 4 deg kept) |
| Operating point | 10.659 m/s, 7.518 rpm, pitch 0 | 11.134927 m/s, 6.853997 rpm, pitch 4.127462 (WISDEM rated row; the only documented point) |
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

The mesh is IEA-15's in units of R: the domain scales with `ROTOR_DIAMETER`, and the
castellated extents, tower box and near-ground cell are the IEA-15 constants times
`142/120.675`, computed in `generate_case.py` (`SNAPPY_SCALED`). Run
`python -I tools/mesh_proportions.py` for the R-unit table (IEA-15 vs IEA-22) and
see PROVENANCE "Mesh proportions" for the two exceptions caused by the real hub
height (4,171,440 vs 4,299,792 base cells; `deltaT` +2 % in tip travel). Base cell
8.875 m (D/32), 1.109 m in the level-3 rotor disk. The case has only been rendered,
never meshed or run. No shaft tilt: rotor axis and the optional nacelle are
horizontal, the tower is kept; `generate_case.py --shaft-tilt on` tilts the nacelle STL 6 deg.

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

## Spanwise ALM-vs-OpenFAST comparison (`scripts/compare_spanwise.py`)

```sh
python3 -I scripts/compare_spanwise.py --run-dir runs/iea22mw-l2-ds --revs 2 --source olaf-fvw \
    --bands 0-0.2,0.2-0.4,0.4-0.6,0.6-0.8,0.8-0.9,0.9-0.95,0.95-1.0 --out /tmp/alm-vs-olaf.csv
```

Frames: the ALM `c_ref_n`/`c_ref_t` are the rotor-plane pair `(Cx, Cy)`; the AeroDyn
`Cn`/`Ct` of `analysis/spanwise-references.csv` are the chord pair,
`Cn = Cx cos(theta) + Cy sin(theta)`, `Ct = -Cx sin(theta) + Cy cos(theta)`,
`theta = BlTwist + pitch` (OpenFAST v5.0.0 `AeroDyn_IO.f90` `BNCn`/`BNCt`/`BNFn`/`BNFt`;
ALM `actuatorLineElement.C` `normalRefCoefficient`/`tangentialRefCoefficient`). The tool
rotates the reference into the plane frame (`--pitch`, default 4.127462 deg) and prints
`c_x` and `c_y` ratios (ALM / reference); `c_n` keeps its old chord-vs-plane definition.
The earlier "c_t ratio, informational" (0.77-3.3) compared `Cy` with `Ct` and is gone.

Integral check, printed with every run (`--reference-case`, default `runs/iea22mw-olaf-dp`
or `runs/scratch-of/bem-rated`): `3 * sum(Fy r dr)` of the reference reproduces the OpenFAST
`torque_nm` (OLAF 0.991, BEM 0.987) and `sum(Fx)` the thrust (0.995 / 0.996); the ALM
`f_ref_t * rho` integral reproduces the module `cq` (0.992). Per-band torque shares show where
the ALM power gap sits.

## Running on SDumont (T4)

The ALM run is the L2 D&S platform of the IEA-15 reference `iea15mw-l2-ds`, carried to IEA-22 by geometry only.
`scripts/run_iea22mw_case.sh` wraps (does not copy) the IEA-15 runner through `TURBINE_PKG_DIR`; every `TURBINE_*`
variable of that runner works unchanged. `scripts/platform_derive.py` reads the IEA-15 Slurm files and prints the derived
platform (`--env` for the Slurm scripts, `--get ranks` for the submit script):

| quantity | IEA-15 | IEA-22 | rule |
|---|---|---|---|
| R [m] / rated rpm | 120.675 / 7.518 | 142 / 6.853997 | generator defaults, never passed |
| domain up/down/lateral | 3 / 7 / 3 D = 6 / 14 / 6 R | 3 / 7 / 3 D = 6 / 14 / 6 R | multiples of D |
| base cell, snappy level, castellated cell | R/16, 2, R/64 | R/16, 2, R/64 | D/32, level carried |
| velocity-sample radius, samples | 3.3 eps, 16 | 3.3 eps, 16 | eps (projection width) is geometry-derived |
| background cells | 2.36 M | 2.29 M (3.36 M after snappy) | geometry |
| decomposition / ranks | simple 4 6 4 / 96 | simple 4 6 4 / 96 | lattice carried; cells-per-rank rule gives 93.1, lattice product kept |
| deltaT | 0.0187 s (427 / rev) | 0.021 s (417 / rev) | `delta_t()`: 0.95 x finest cell / tip speed |
| write interval, revolutions | 120 deg, 23 | 120 deg, 23 | carried, fresh start, no requeue |

Model: Glauert tip off, root kept as the Prandtl hub loss, Dag & Sorensen on (`scripts/slurm/l2-ds.slurm`).
`scripts/slurm/olaf-dp.slurm` runs the OLAF double-precision guideline setup (1399 near-wake panels, 699 free, dt 0.1459 s,
1640 steps = 23.3 wake revolutions + 4 averaged) on one task (the build has no OpenMP).
`scripts/submit_iea22.sh [--apply] [alm|olaf|all]` prints (default) or submits both; it refuses an existing run directory.
Runs live in `runs/` (git-ignored by `runs/.gitignore`).

Slurm sizing (dev partition, 2026-11-02): ALM 96 ranks, 3,357,872 cells, 6.0 s/step (steps 11-41, jobs 11637596/11637631)
-> 9,588 steps for 23 revolutions = 16 h, request 36 h. IEA-15 `l2-ds` runs 2.1-5.1 s/step on the same mesh size, so 6.0 s is a
pessimistic (loaded dev node) rate. OLAF: wall trace of a truncated production run (job 11637708, `olaf_trace.py fit`):
per-step cost grows with the wake (1.1 s at step 68, 4.2 s at step 377), 917 s for the first 411 steps; extrapolation to
1640 steps 4.0-5.2 h (quadratic then plateau at 1399 panels), request 12 h.

BEM rated reference (fast, 4 s): `analysis/spanwise-references.csv` (`openfast-bem` block, 177 rows) and
`analysis/bem-rated-metrics.json` (Cp 0.45243, Ct 0.64171).
