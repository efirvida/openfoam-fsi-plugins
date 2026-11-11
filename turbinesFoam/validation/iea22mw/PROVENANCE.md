# Provenance — IEA 22-280-RWT case geometry and polars

All source files below are **read-only, untrusted inputs**. Nothing under the
input tree was modified; the committed geometry table, polars and case are
derived from them by the tools in this package (run with `python -I`, paths
passed as data).

## Sources

Repository: <https://github.com/IEAWindSystems/IEA-22-280-RWT>, shallow clone at
commit `7c3cf5df656774bafc6909a92dae8d12f734b122`, local root (not committed)
`/scratch/leahk/eduardo.donestevez/simulations/tmp/iea22-src/repo` (`<repo>`).

| Source | Path under `<repo>` | sha256 |
|---|---|---|
| AeroDyn15 blade table (chord/twist/span/prebend/`BlAFID` authority) | `OpenFAST/IEA-22-280-RWT/IEA-22-280-RWT_AeroDyn15_blade.dat` | `828528ff3d19bb6ea6bb750ef596c9c40026f55daf71b64fa143ff4cab58cf85` |
| 59 AirfoilInfo per-station polars | `OpenFAST/IEA-22-280-RWT/Airfoils/IEA-22-280-RWT_AeroDyn15_Polar_00..58.dat` | combined `9700d9daaca0d9fac9eb3a2094aba900923212ad59d75684da9657c08d3b0dd1` (sha256 of the sorted `sha256sum` list); station 30 = `2c25cc41bbbba740c7f40acf7b56add35a4b5d513adc8dbf7c4a8fde42cff7ff` |
| ElastoDyn blade file (T2 OpenFAST templates) | `OpenFAST/IEA-22-280-RWT/IEA-22-280-RWT_ElastoDyn_blade.dat` | `0b7fb7f5e4d19bab0ede1f8a2ef80afbf7b42d663ff513777263653fa42f4459` |
| WindIO-2.0 definition (aerodynamic centres, tower, drivetrain, chord/twist cross-check) | `windIO/IEA-22-280-RWT.yaml` | `6b844389cdf34df398a51d201efb849c4317b8e84b977af2a788b2c61f95231a` |
| OpenFAST ElastoDyn, monopile (`TipRad`, `HubRad`, `PreCone`, `ShftTilt`, `OverHang`) | `OpenFAST/IEA-22-280-RWT-Monopile/IEA-22-280-RWT_ElastoDyn.dat` | `da941432b0ec6708e5f39b159ac9ce4b6f536ed206f4ca11717126106a5c9c35` |
| OpenFAST AeroDyn15, monopile (airfoil order, tower aero) | `OpenFAST/IEA-22-280-RWT-Monopile/IEA-22-280-RWT_AeroDyn15.dat` | `0258997b6b5c1d740c7262655aced37be4f2acec7a7322d1643dd879448c2a90` |
| OpenFAST ElastoDyn, semi-submersible (cross-check only) | `OpenFAST/IEA-22-280-RWT-Semi/IEA-22-280-RWT-Semi_ElastoDyn.dat` | `ea04a4ec4a491cc6a2a26d10ac3d540bcedf0f2cbc37f519b9a0cb732c03ddba` |
| Tabular documentation (WISDEM quasi-static rotor performance, Overview) | `Documentation/IEA-22-280-RWT_tabular.xlsx` | `8cf9a552a955982b210e8bc77702adc85c8ee0f1d1e10b5f717b3d29e95b4f84` |

Override locations with `IEA22MW_BLADE_FILE`, `IEA22MW_WINDIO`,
`IEA22MW_AEROFOIL_DIR`.

## Radius decision (S4)

windIO says `rotor_diameter: 284.0`. It was checked against ElastoDyn and the
tabular documentation, as done for IEA-15. **Decision: R = 142.0 m
(D = 284.0 m), equal to the along-blade tip radius, NOT precone-projected.**

| Evidence | Value |
|---|---|
| windIO `assembly.rotor_diameter` | 284.0 |
| Workbook Overview "Rotor diameter [m]" | 284 |
| Workbook "Rotor Performance - WISDEM", first row: tip speed 101.9203 m/s at 6.853997 rpm | `R = 101.9203/(6.853997*2*pi/60) = 142.0000` (to 1e-6) |
| ElastoDyn (monopile and semi) `TipRad` | 142.0 |
| ElastoDyn `HubRad`; windIO `hub.diameter` 8.4; workbook "Hub diameter" 8.4 | 4.2 m (8.4 m) |
| AeroDyn blade table last `BlSpn` | 137.8 m, and `HubRad + 137.8 = 142.0` |
| ElastoDyn `PreCone(1..3)`; windIO `hub.cone_angle`; workbook "Rotor cone angle" | -4.0 (OpenFAST sign) ; 4.0 ; 4 deg |

**This differs from IEA-15.** There `2*TipRad*cos(precone)` reproduced the
published diameter (R was the projected radius, 120.675 m vs `TipRad` 120.97 m).
Here `2*TipRad*cos(4 deg) = 283.3 m` does **not** match 284.0, whereas
`2*TipRad = 284.0` does; WISDEM used the unprojected radius for the tip speed.
Applying the IEA-15 rule would have given R = 141.65 m (0.25 % low). Only one
radius is in circulation for IEA-22 (no modified copy as for IEA-15); the
projected in-plane tip, `142*cos(4 deg) = 141.65 m` before the 7 m prebend, is a
derived geometric quantity and is not called R.

Consequences, all implemented in `tools/blade_geometry.py`:

- `rotorRadius 142` and the tip-speed ratio `Omega*R/V` use R = 142.0 m;
  TSR 9.1532 at the rated row = the reference design TSR (workbook Overview
  9.153211), a consistency check on R.
- `radius_m = HubRad + BlSpn` (tip 142.0 m, `coneAngle 4` in the case);
  `r_over_R = radius_m / R` (tip exactly 1.0; no `cos(precone)` factor).

### Hub, precone, tilt, overhang

| Quantity | Decision | Evidence |
|---|---|---|
| Hub radius | 4.2 m (hub diameter 8.4 m) | ElastoDyn `HubRad` = windIO `hub.diameter/2` = workbook |
| Precone | 4 deg, rendered as `coneAngle 4` with the along-blade radius column | windIO `hub.cone_angle` 4; ElastoDyn `PreCone` -4 (OpenFAST sign: blades cone upwind) |
| Shaft tilt | **none** (owner decision 2026-11-02, "sin inclinaciones"): rotor axis horizontal in the OpenFOAM case, the optional nacelle capsule horizontal (`--shaft-tilt on` opts into the 6 deg for the STL only), OpenFAST `ShftTilt = 0` (`setup --tilt` opts into the real -6 deg). The tower is kept. Precone 4 deg is blade geometry and is **kept** | windIO `drivetrain.outer_shape.uptilt` 6; ElastoDyn `ShftTilt` -6.0000 (OpenFAST sign), the tilted values are not used by default |
| Prebend | tip `BlCrvAC` = -7.0 m, mapped as `axialDistance = -BlCrvAC` (7 m upwind), identical to IEA-15 | AeroDyn blade table; windIO reference axis x tip -7.0 |
| Overhang | 14.0 m horizontal (windIO), used for the tower offset and the nacelle length; OpenFAST tilt-0 `OverHang = -14.0`, `Twr2Shft = 5.614` (= 170 - `TowerHt`, windIO `distance_tt_hub`), so the hub stays at 170 m | ElastoDyn tilted `OverHang` -14.0771 = 14.0/cos 6 deg and `Twr2Shft` 4.1425 + 14.0771 sin 6 deg = 5.614 (checked in the tests); the tilted values are restored by `setup --tilt` |
| Hub height | 170.0 m | windIO `hub_height` 170; ElastoDyn `TowerHt` 164.386 + 5.614 tower-top-to-hub = 170.0 (windIO `distance_tt_hub` 5.614) |

## Derivation

| Committed file | Built from | Rule |
|---|---|---|
| `data/iea22mw_blade.csv` | AeroDyn15 blade table + WindIO | one row per node (59); `radius_m = HubRad + BlSpn`, `r_over_R = radius_m/R`, `chord_mount` = section aerodynamic centre interpolated over `outer_shape.airfoils[].spanwise_position` (0.5 circular root, 0.25 elsewhere), `pitch_deg = -(twist_deg + collective)`, prebend/sweep/curve angle as IEA-15. Emitter: `tools/blade_geometry.py`. |
| `data/polars/polar_NN.dat` | AirfoilInfo `..._Polar_NN.dat` | `Re` + `data ( (alpha Cl Cd Cm) )`, 200 rows per file; `Cm` unchanged; `liftReCorrExp 0` as in IEA-15. Polar `NN` serves `BlAFID = NN+1` (the AeroDyn15 `AFNames` list is in file order, tested). Converter: `scripts/buildPolars.py`. |
| `case/**` | the two tables above + WindIO tower/drivetrain | `tools/generate_case.py` (the IEA-15 generator bound to the IEA-22 data, see README). |

Rebuild and staleness-check:

```sh
python -I turbinesFoam/validation/iea22mw/tools/blade_geometry.py [--check]
python -I turbinesFoam/validation/iea22mw/scripts/buildPolars.py [--check]
python -I turbinesFoam/validation/iea22mw/tools/generate_case.py [--check]
```

Cross-check against the WindIO `outer_shape` chord/twist (linear interpolation of
a 102-point grid onto the 59 AeroDyn nodes): max chord difference `1.53e-2 m`,
max twist difference `1.19e-2 deg`. This is larger than the IEA-15 `1.1e-4 m`
because the AeroDyn nodes are a re-sampling of a spline; it is an interpolation
effect, the AeroDyn table remains authoritative, and the test bound is 0.05.

## Operating point of the generated case

`V = 11.134927 m/s`, `Omega = 6.853997 rpm`, collective pitch `4.127462 deg`
(owner decision 2026-11-02: nominal speeds, **the** default and only documented point):
the WISDEM rated row (workbook sheet "Rotor Performance - WISDEM", rated power
22.000 MW, Cp 0.4156). Unlike IEA-15 (pitch 0 at rated), the IEA-22 rated point
is already pitched (peak shaving above the optimum pitch -0.955 deg). The
OpenFAST steady-state sheet gives a different row (11 m/s, 6.771 rpm, 2.429 deg),
which is **not used**; the flags `--speed/--rpm/--pitch` remain for sweeps. No
coefficient is tuned.

## Mesh proportions (owner decision 2026-11-02)

"la malla con las mismas proporciones que la IEA 15MW": every mesh length of the
IEA-22 case equals the IEA-15 value times `R22/R15 = 142/120.67532316 = 1.17674`,
i.e. it is identical in units of the rotor radius R. The generator computes the
castellated extents from the IEA-15 constants (`SNAPPY_SCALED` in
`tools/generate_case.py`); nothing is re-typed. This **replaces** the earlier guessed
extents (disk radius 175 m, wake radius 200 m, downstream 550 m, half-thickness 12 m,
tower box floor -190 m), which did not follow (175/R = 1.232 vs 1.243; the floor was
tied to H + 20 m instead of R).

| Quantity | IEA-15 [m] | IEA-15 [R] | IEA-22 [m] | IEA-22 [R] |
|---|---|---|---|---|
| R | 120.6753 | 1 | 142.0000 | 1 |
| rotorDisk radius | 150 | 1.24300 | 176.5 | 1.24300 |
| rotorDisk point1 y (flow axis) | 10 | 0.08287 | 11.77 | 0.08287 |
| rotorDisk point2 y (flow axis) | -10 | -0.08287 | -11.77 | -0.08287 |
| rotorWake radius | 170 | 1.40874 | 200 | 1.40874 |
| rotorWake point1 y (flow axis) | -20 | -0.16573 | -23.53 | -0.16573 |
| rotorWake point2 y (flow axis) | 470 | 3.89475 | 553.1 | 3.89475 |
| tower box lateral half-width | 20 | 0.16573 | 23.53 | 0.16573 |
| tower box upwind face | -20 | -0.16573 | -23.53 | -0.16573 |
| tower box downwind end | 470 | 3.89475 | 553.1 | 3.89475 |
| tower box floor | -170 | -1.40874 | -200 | -1.40874 |
| tower box top | 10 | 0.08287 | 11.77 | 0.08287 |
| domain upwind | -1207 | -10.00000 | -1420 | -10.00000 |
| domain downwind | 3620 | 30.00000 | 4260 | 30.00000 |
| domain lateral | 965.4 | 8.00000 | 1136 | 8.00000 |
| domain top | 603.4 | 5.00000 | 710 | 5.00000 |
| base (hub) cell, D/32 | 7.542 | 0.06250 | 8.875 | 0.06250 |
| near-ground cell | 2 | 0.01657 | 2.353 | 0.01657 |
| disk castellated cell, level 3 | 0.9428 | 0.00781 | 1.109 | 0.00781 |
| hub height (real geometry) (exception) | 150 | 1.24300 | 170 | 1.19718 |
| realised hub-adjacent cell (exception) | 7.496 | 0.06212 | 8.993 | 0.06333 |
| cells (blockMesh base) | 4,299,792 | | 4,171,440 | |

(Table produced by `python -I tools/mesh_proportions.py`; it exits 1 if a proportional
row differs by more than 1e-4, and `tests/test_iea22_mesh_proportions.py` pins it.)
Same on both sides: castellation level 3 with the wake/tower one level lower, blockMesh
horizontal block counts (50/272/60 x 36/96/36) and gradings, ALM/ASM velocity sample
radius 0 (point sampling; the ring radius is in projection-epsilon units, so
dimensionless), tower elements 40; elements per blade differ only through the station
count (174 vs 147, 3 per geometry segment). The tower box lateral half-width is IEA-15's
`2 x 10 m` tower diameter scaled by R (`ASM_TOWER_LATERAL_FACTOR x 1.17674`), although
the IEA-22 tower diameter (10 m) is the real one.

**Exceptions, both from the real hub height (170 m = 1.197 R vs 150 m = 1.243 R):** the
ground sits at -170 m, so the vertical block below the hub has 34 instead of 36 cells
(integer layer count at the same ground-cell/R and hub-cell/R), giving 4,171,440 vs
4,299,792 base cells (x 0.970) and a realised hub-adjacent cell of 0.0633 R vs 0.0621 R.
`deltaT` follows that cell (`0.95 x cell / tip speed`, rounded to 3 digits): per-step
tip travel `deltaT x Omega` is 0.0602 / 0.00754 rad vs 0.0590 / 0.00738 rad at snappy
level 0 / 3 (+1.9 % / +2.2 %); `deltaT` is 0.0838 s (background) / 0.0105 s (level 3)
vs 0.075 / 0.00937 s. Castellated cell count: **not meshed** (not cheap, never run);
all refinement regions and levels are identical in R units, so expect the IEA-15
castellated count scaled only by the vertical-layer ratio ~0.97.

## Known input limitations (not fixed here)

- `Re = 3.0e6` in every one of the 59 AirfoilInfo headers; `profileData` receives
  3.0e6 for all stations (the QBlade polars carry Re 8.5e6-1.8e7, not used).
- The AirfoilInfo polars are the 2-D tables, with no 3-D stall-delay correction.
- WindIO-2.0 has no structural `pitch_axis`; the `pitch_axis` column is `nan`
  (audit-only in IEA-15 as well).
- The tower starts at the transition piece (z = 15 m); the monopile below is not
  modelled. The nacelle capsule radius is the generator radius 4.89 m
  (`drivetrain.generator.radius`; WindIO-2.0 has no `rad_ag/h_m/h_yr`).
- Nothing was run on Slurm; the case has never been meshed or solved.
