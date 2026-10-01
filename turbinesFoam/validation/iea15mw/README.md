# IEA 15-240-RWT case — P0 geometry, P1 polar ingestion and P2 case assembly

This package holds the reproduced blade geometry, the `profileData` polars and
the assembled OpenFOAM case skeleton for the IEA 15-240-RWT turbinesFoam case.
It is the **P0 + P1 + P2** slice of `odd/tasks/iea15mw-case-readiness.md`; the
physics runs (P3+) are not part of it.

> The IEA 15 MW reference turbine has **no measurements**. Any comparison it
> supports is code-to-code (OpenFAST / WISDEM / HAWC2), not against nature. The
> measurement claim for turbinesFoam rests on the NREL Phase VI case.

## Layout

```
tools/blade_geometry.py     decode + emit the geometry table; tested loader
scripts/buildPolars.py      AirfoilInfo -> profileData converter, with --check
tools/generate_case.py      render case/ from the committed data, with --check
data/iea15mw_blade.csv      committed geometry table (50 stations)
data/polars/polar_NN.dat    committed profileData polars (50 stations)
case/                       generated OpenFOAM skeleton (system/, constant/, 0.org/)
PROVENANCE.md               sources, sha256, derivation, limitations
```

Rebuild / verify:

```sh
python turbinesFoam/validation/iea15mw/tools/blade_geometry.py
python turbinesFoam/validation/iea15mw/tools/blade_geometry.py --check
python turbinesFoam/validation/iea15mw/scripts/buildPolars.py
python turbinesFoam/validation/iea15mw/scripts/buildPolars.py --check
python turbinesFoam/validation/iea15mw/tools/generate_case.py
python turbinesFoam/validation/iea15mw/tools/generate_case.py --check
```

## P0 — the radius decision

Three rotor radii were in circulation:

| Source | D [m] | R [m] |
|---|---|---|
| NREL/TP-5000-75698, Table ES-1 / 1-1 (original report) | 240 | 120.0 |
| Repo ontology yaml + tabular xlsx (published) | **241.35064632** | **120.67532316** |
| Sim-root `IEA-15-240-RWT.yaml` (modified copy) | 242.23775645 | 121.118878225 |

**Decision: R = 120.67532316 m (D = 241.35064632 m).** The evidence:

1. The repo's ontology yaml
   (`IEA-15-240-RWT/WT_Ontology/IEA-15-240-RWT.yaml`) gives
   `rotor_diameter: 241.35064632`. The sim-root yaml is its windIO-2.0
   re-serialization with **only** `rotor_diameter` changed; every chord, twist,
   pitch-axis and reference-axis value is identical (`tools/blade_geometry.py`
   verifies the chord/twist cross-check).
2. `Documentation/IEA-15-240-RWT_tabular.xlsx` sheet **Overview** gives
   `Rotor diameter [m] = 241.35064632`; its **Rotor Performance** sheet lists a
   5 rpm tip speed of 63.185 m/s = 0.523599 rad/s x 120.675 m, i.e. WISDEM used
   R = 120.675 m.
3. OpenFAST `..._Monopile_ElastoDyn.dat` gives `TipRad = 120.97`,
   `HubRad = 3.97`, `PreCone = -4.0 deg`, and
   `2 x 120.97 x cos(4 deg) = 241.35065 m`, reproducing the published diameter
   to 8 significant figures. The published R is the **projected (in-plane)**
   tip radius.
4. The `fem-shell` V-01 test hard-codes `_ROTOR_RADIUS = 120.675`.

**No primary source supports 242.23775645.** `fem-shell`'s `load_blade_aero`
inherits it for `BladeAero.rotor_radius`, but its stations and its own test use
HubRad = 3.97 and R = 120.675, so the offending value is isolated to the
sim-root yaml.

### Hub radius

The physical hub radius is **3.97 m** (hub diameter 7.94 m, NREL/TP-5000-75698
Table ES-1 and ElastoDyn `HubRad`). The published R is **not** a naive
`HubRad + blade_span`:

```
HubRad + blade_span = 3.97 + 117.0 = 120.97 m   (structural tip radius, TipRad)
R_published         = 120.97 * cos(4 deg) = 120.67532316 m   (projected)
HubRad              = R_published / cos(4 deg) - 117.0 = 3.9699... ~ 3.97 m
```

The 0.295 m between the naive `R - span = 3.675 m` and the true `HubRad = 3.97 m`
is the 4 deg precone projection of the blade onto the rotor plane.

## P0 — the geometry table

`data/iea15mw_blade.csv`, 50 rows:

| column | meaning |
|---|---|
| `r_over_R` | projected radius / R_published; tip -> 1.0 |
| `radius_m` | `HubRad + BlSpn` (along-blade; tip 120.9699 m). Feed this to the ALM `radius` column together with `coneAngle 4`. |
| `span_m` | AeroDyn `BlSpn` (0 .. 116.99993 m) |
| `chord_m` | AeroDyn `BlChord` |
| `twist_deg` | AeroDyn `BlTwist`, positive nose-up towards feather |
| `pitch_axis` | structural pitch axis (OpenFAST ElastoDyn `PitchAxis`), 0.5045 -> 0.3682; **audit only** |
| `chord_mount` | ALM chord mount (aerodynamic centre), 0.25 outboard |
| `pitch_deg` | `-(twist_deg + collective)` (ALM mount sign) |
| `airfoil_id` | AeroDyn `BlAFID` (1..50, per-node polar index) |

**Cross-check (numerical).** The AeroDyn table is authoritative for
chord/twist/span; the WindIO yaml `outer_shape_bem` agrees to
`max |delta chord| = 1.14e-4 m` and `max |delta twist| = 7.6e-6 deg`, and
`fem-shell`'s `load_blade_aero` agrees with the yaml to machine precision
(2e-14 m chord). No disagreement is left unexplained.

### Two ALM conversion conventions

**1. `chordMount` (chordwise mount fraction).** Cited from
`axialFlowTurbineALSource.C:166-173`: the element point is shifted by
`(chordMount - 0.25)*chord` along the chord, so `0.25` is the quarter chord.
The AeroDyn polar `Cm` is referenced to the quarter chord, so the correct mount
is the section aerodynamic centre:

```
chordMount(eta) = aero_center interpolated across the airfoil_position grid
                = 0.25 for the FFA-W3 sections, blending to 0.316 at
                  SNL-FFA-W3-500 and 0.5 at the circular root
```

from the WindIO `airfoils[].aerodynamic_center` (0.25 for every FFA-W3 section,
0.316 for SNL-FFA-W3-500, 0.5 for the circular root), interpolated across the
`airfoil_position` grid. Check: **37 of the 50 stations are exactly 0.25** and
the rest blend monotonically toward the root cylinder; no station exceeds 0.5.

The WindIO `pitch_axis` (ElastoDyn `PitchAxis`, 0.5045 -> 0.3682) is a
**different, structural** quantity (where the pitch bearing sits), not the
aerodynamic centre, and is **not** used as `chordMount`. It is recorded in the
table for the audit only.

**2. Twist/mounting sign.** `validation/phaseVI/tools/element_data.py` uses
`pitch = -(twist + pitch_deg)`. The same negation applies here:

```
pitch_deg = -(BlTwist + collective_pitch_deg)
```

Derivation from the consuming code: `axialFlowTurbineALSource.C` builds
`chordDirection = azimuthalDirection`, `spanDirection = chordDirection x
freeStreamDirection`, then `actuatorLineElement::pitch` rotates the chord about
the span. For that frame, a *positive* element pitch **increases** the angle of
attack (`planformNormal` is rotated into the inflow). A positive physical twist
(nose up, towards feather) must *reduce* the angle of attack, so the element
pitch is the negated twist. The AeroDyn `BlTwist` is positive-nose-up (it equals
OpenFAST ElastoDyn `StrcTwst` and the WindIO `twist`), exactly the convention the
measurement-validated Phase VI blade uses, and both are upwind power-producing
rotors, so the Phase VI anchor transfers unchanged.

Verification performed here: a hand computation of the ALM frame and angle of
attack (the equations above, with the case's `axis`/`freeStreamVelocity`
handedness) at the rated point gives, at `r/R = 0.53` (twist +2.73 deg),
`alpha = 8.9 deg` for `pitch = -twist` but `alpha = 14.3 deg` for the wrong
`pitch = +twist`. The committed OpenFAST output (which includes induction) gives
per-node `AB1N*Alpha` of 7.4 / 6.1 / 5.9 / 6.4 deg at stations 15 / 26 / 31 / 40
and 1.3 deg at the tip; only the `-twist` mapping reproduces that attached-flow
band (the root stays stalled in both: 58 deg geometric vs 64 deg OpenFAST). A
definitive check still requires an OpenFOAM run (P3), which is out of scope for
this slice.

### `nElements` constraint

`actuatorLineSource.C:145-155` requires
`nElements % (nGeometryPoints - 1) == 0`. With 50 rows there are 49 geometry
segments, so `nElements` must be a multiple of 49. **Recommended: `nElements =
147`** (3 elements per segment, ~0.80 m spacing), which matches the Phase VI
chord-relative element density (`0.136 c` per element). Cheaper variants: 98
(2/segment) and 49 (the minimum, ~2.39 m spacing). See README "Layout" for the
radius convention the element rows must use.

## P1 — the polar converter

`scripts/buildPolars.py` reads each `IEA-15-240-RWT_AeroDyn15_Polar_NN.dat`
(AirfoilInfo v1.01.x) and emits `data/polars/polar_NN.dat`:

```
Re 3e+06;
data
(
    (alpha_deg Cl Cd Cm)
    ...
);
```

included inside a `profileData` sub-dictionary:

```
profileData
{
    polar_00 { #include "../data/polars/polar_00.dat" }
    ...
}
```

**UA block and comments.** The parser locates the `Re` and `NumAlf` keywords and
reads exactly `NumAlf` rows after `NumAlf`; the optional 30-coefficient UA block
(stations 05..49) and every `!` comment are skipped without relying on their
position or count. Station 00..04 have `InclUAdata False`.

**`Cm` convention — no conversion.** AirfoilInfo stores the quarter-chord
pitching moment, positive nose-up (the UA block's `Cm0` description); the WindIO
`c_m` and the NREL S809 `Cm` that turbinesFoam's `profileData` already consumes
use the same convention. Verified numerically: the AeroDyn `Cm` correlates
`+1.000` with the WindIO `c_m` for the matching sections. **The readiness note's
"different `Cm` sign convention" is not reproducible**, so `Cm` is passed through
unchanged and the tests assert the identity.

**Per-station set = all 50 files.** The AeroDyn blade table assigns a distinct
`BlAFID = 1..50` per node and the OpenFAST reference itself uses 50 per-node
polars; emitting all 50 avoids introducing a further family-interpolation or
reduction step. The distinct families (8 shapes) are the fallback only if a
smaller committed set is wanted.

## P2 — the case assembly

`tools/generate_case.py` renders `case/` from the committed P0/P1 data, mirroring
the NREL Phase VI case structure (`validation/phaseVI/case/`) scaled to the
15 MW rotor. Every file carries a "Generated by tools/generate_case.py" banner;
`--check` re-renders in memory and fails when a file on disk is missing or stale.

```sh
python turbinesFoam/validation/iea15mw/tools/generate_case.py
python turbinesFoam/validation/iea15mw/tools/generate_case.py --check
python turbinesFoam/validation/iea15mw/tools/generate_case.py \
    --speed 10.659 --rpm 7.518 --pitch 0 --mesh coarse --end-revs 3
```

The rendered skeleton is `system/{blockMeshDict,topoSetDict,controlDict,
decomposeParDict,fvSchemes,fvSolution,fvOptions}`,
`constant/{transportProperties,turbulenceProperties}` and
`0.org/{U,p,k,omega,nut}`.

### Rated operating point

| quantity | value | source |
|---|---|---|
| `V` | 10.659 m/s | NREL/TP-5000-75698 Table 3-1 (WISDEM rated) |
| `Omega` | 7.518 rpm = 0.787283119 rad/s | Table 3-1 |
| collective pitch | 0 deg | Table 3-1 |
| `R` | 120.67532316 m | P0 projected radius |
| `tipSpeedRatio` | **8.9131856** | computed `Omega*R/V` |

`tipSpeedRatio` is **computed** by the generator, never hard-coded. The
readiness note's proposed 9.0786 is *not* reproduced: it implies 7.6575 rpm, not
the rated 7.518 rpm (the tests assert both the computed value and this
discrepancy).

### Precone decision — option (b): physical radius + `coneAngle 4`

The 15 MW rotor has a 4 deg precone. Two representations were considered:

- **(a)** flatten the rotor in-plane: put the *projected* radius in `elementData`
  and set `rotorRadius 120.675`;
- **(b)** keep the *physical* along-blade radius (`HubRad + BlSpn`, tip
  120.9699 m) and render `coneAngle 4`, letting the source project it.

**Chosen: (b).** `axialFlowTurbineALSource` supports the cone directly —
`coneAngle` is a documented `lookupOrDefault` key
(`axialFlowTurbineALSource.C:83`) that rotates the element points and span
directions out of the rotor plane — so the only cost is one extra key, and (b)
preserves the real geometry committed in P0. The projected tip lands exactly on
`rotorRadius`:

```
120.9699 * cos(4 deg) = 120.6753 m = R
```

Consequence: `elementData` carries the physical radius (tip 120.9699 m, which is
**greater** than `rotorRadius 120.675`), and `rotorRadius` is the projected
in-plane radius used for the coefficient normalisation. With `endEffects off`
and no `tipCorrection` in this baseline, `rotorRadius` only normalises the
outputs, so the choice is inert for the P3 comparison; the projected `r/R` seen
by the physics still matches the P0 table.

### `elementData` and `nElements`

- 50 rows in the AFTAL format `(axialDistance radius azimuth chord chordMount
  pitch curveAngle)` (`axialFlowTurbineALSource.C:134-143`), straight from
  `blade_geometry.element_rows`. The first six columns are the classic AFTAL
  set; the **7th `curveAngle`** is an additive turbinesFoam extension (absent in
  legacy 6-column tables) that tilts the element section frame:
  - `radius = HubRad + BlSpn` (physical along-blade radius; cone via
    `coneAngle 4`);
  - `axialDistance = -BlCrvAC` (prebend, up to 3.999 m at the tip; `+axis_` is
    upwind);
  - `azimuth = asin(BlSwpAC / radius)` (sweep);
  - `chordMount` = section aerodynamic centre; `pitch = -(twist + collective)`
    (AeroDyn also negates `BlTwist`);
  - `curveAngle = BlCrvAng` (the local prebend slope, up to -5.77 deg at the
    tip), applied as a rotation of the element frame about the local tangential
    axis.

  The mapping was verified against the AeroDyn node locus
  (`position = root + RefOrientation @ (BlCrvAC, BlSwpAC, BlSpn)`, `theta =
  (0, BlCrvAng, -BlTwist)`) — every lifting station matches to < 5 mm — in
  `odd/tasks/iea15mw-blade-geometry-mapping.md` and
  `tests/test_iea15mw_case.py::TestAlmConventions::test_element_positions_reproduce_aerodyn_locus`.
- 50 geometry control points -> 49 segments, so `nElements` must be a multiple
  of 49. **`nElements = 147`** (3 per segment, ~0.80 m spacing).
- `elementProfiles` lists the 50 per-station profiles (`polar_00` .. `polar_49`)
  in station order; the source maps element `i` to
  `elementProfiles[i*50/147]` (`actuatorLineSource.C:251`).
- Three blade dictionaries 120 deg apart via `azimuthalOffset` 0 / 120 / 240
  (blade 2 and 3 inherit blade 1 with `$blade1`).

### `fvOptions` neutral baseline

One `axialFlowTurbineALSource` at `origin (0 0 0)` (the rotor/hub at the
origin), `verticalDirection (0 0 1)`. `generate_case.py --flow-axis` selects the
orientation:

- **`y` (default, Aeroelast/FSI)** — `axis (0 -1 0)`, `freeStreamVelocity (0
  10.659 0)`: fluid in **+Y**, rotor axis **−Y**, blade axis **+Z**, profiles in
  the XY plane — the Aeroelast frame, so the fluid and structural meshes
  coincide for FSI. The domain is the `R_z(+90°)` image (Y the 20D axis, X the
  8D one).
- **`x` (OpenFAST/AeroDyn)** — `axis (-1 0 0)`, `freeStreamVelocity (10.659 0
  0)`: fluid and rotor axis along X, domain elongated in X.

The `elementData` is rotor-relative and does **not** change with the flow axis.
Neutral baseline (both orientations):

- `dynamicStall { active off; }`
- `rotationalAugmentation { active off; }`
- `endEffects { active off; }`
- **no `tipCorrection` block at all**

The 50 per-station `profileData` entries include the committed polars
(`#include "../../data/polars/polar_NN.dat"`) with `GaussianCoeffs { chordFactor
0.25; dragFactor 1.0; meshFactor 1; }`.

Objects are **configurable** so the model matches the reference used for
validation (adding an object the reference omits would compare different
models). The validation default is the OpenFAST-faithful set — **blades +
tower, no hub, no nacelle** — and objects are added only when scaling:

- **Blades** — always present.
- **Tower** (`--tower on|off`, default **on**) — an ALM built from the WindIO
  tower (`(axialDistance, height, diameter)`, 11 collapsed stations, 40
  elements), with the AeroDyn `TwrCd = 0.5` in a dedicated `tower` profile (the
  `cylinder` profile is 1.1). OpenFAST has `TwrAero=True`, so the tower is on to
  compare like-for-like; `includeInTotalDrag false` keeps `RotThrust`
  rotor-only. The tower is `OverHang = 12.098 m` downwind of the rotor apex and
  reaches from the floor (z = −135, 15 m above the ground) to −5.614 m below the
  hub.
- **Hub** (`--hub on|off`, default **off**) — a 7.94 m vertical cylinder
  (WindIO `components.hub.diameter = 7.94`, half `HubRad`). **AeroDyn models no
  hub aero** (`NacelleDrag = False`, no hub drag), so it is off for the
  blade-loading comparison; enable it for a physical/full-system study. It is a
  crude drag body (frontal area ~63 m² vs ~49.5 m² for a 7.94 m sphere).
- **Nacelle** — turbinesFoam models it as a `nacelleSurfaceSource`, an actuator
  **surface** (needs an STL + `cf`), not an ALM. The WindIO yaml only gives the
  drivetrain (overhang 12.03 m, uptilt 6°, diameters), and the AeroDyn reference
  has `NacelleDrag = False`, so the nacelle is **not in the reference**. Not
  rendered yet.

### Mesh

The domain is **ground-anchored**: the rotor/hub sits at the origin `(0 0 0)`,
the floor (ground, `bottom` = `wall`, no-slip with `kOmegaSST` wall functions)
at `z = -HUB_HEIGHT = -150 m`, and the top at `+DEFAULT_DOMAIN_TOP = +603.4 m`
(`--domain-top`, configurable). The default horizontal box is 20D streamwise x
8D lateral around the rotor (`D = 241.35064632 m`); both are configurable. This
makes the case ready for ABL / parameterisation studies, not just a bare rotor.

The mesh is **parametric** (`--mesh` and the `--domain-*` extents):

- **Resolution** `--mesh {coarse,medium,fine}` = `D/32`, `D/48`, `D/64` in the
  horizontal, and the same hub-adjacent size in the vertical. Other resolutions
  scale the base (D/32) cells proportionally, so the relative refinement and the
  grading are preserved.
- **Extents** `--domain-upstream` / `--domain-downstream` / `--domain-lateral`
  (rotor diameters) and `--domain-fine-max` / `--domain-fine-lat` set the
  refined region. `--domain-top` sets the top [m].
- **`deltaT` is derived** from the hub-adjacent cell (tip displacement per step
  below it): `0.075 s` coarse, `0.0498` medium, `0.0375` fine.

A finer mesh is affordable by shrinking the domain — the point of the P5 mesh
sweep:

| mesh | hub cell | default (20D x 8D) | compact (10D x 5D) | cells/rank @48 |
|---|---|---|---|---|
| `coarse` D/32 | 7.50 m | **4.30 M** | 2.02 M | ~90 k |
| `medium` D/48 | 4.98 m | 11.98 M | 5.65 M | ~118 k (compact) |
| `fine` D/64 | 3.75 m | 24.39 M | 11.48 M | ~239 k (compact) |

`decomposeParDict` uses `numberOfSubdomains 48` (the P3 plan). `endTime 3`
revolutions (23.94 s): the tip displacement per step is `95.006 * 0.075 =
7.13 m`, below the coarse hub-adjacent cell `7.50 m`.

Verified with a loaded OpenFOAM v2506 environment on the rendered coarse case:
`blockMesh` reports `nCells: 4299792` (matching the analytic count) and
`checkMesh` reports `Mesh OK` (non-orthogonality 3.1e-06).

**Running the finer meshes**: they do not fit the 20-minute development queue,
so `scripts/slurm/production.slurm` runs the whole case (96 h) for a given
`PHASEVI_MESH` / `PHASEVI_*` domain, while `scripts/slurm/coarse-dev.slurm`
keeps the 20-minute sliced/self-requeuing path for the coarse mesh.

## Known limitations

See `PROVENANCE.md`: the `Re = 3.0e6` header is nominal for all 50 stations
(the WindIO per-section Re differs), and the polars are the 2-D tables with no
3-D stall-delay correction.
