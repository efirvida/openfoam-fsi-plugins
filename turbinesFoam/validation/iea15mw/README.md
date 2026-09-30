# IEA 15-240-RWT case — P0 geometry and P1 polar ingestion

This package holds the reproduced blade geometry and the `profileData` polars for
the IEA 15-240-RWT turbinesFoam case. It is the **P0 + P1** slice of
`odd/tasks/iea15mw-case-readiness.md`; the case assembly (P2) and the physics
runs (P3+) are not part of it.

> The IEA 15 MW reference turbine has **no measurements**. Any comparison it
> supports is code-to-code (OpenFAST / WISDEM / HAWC2), not against nature. The
> measurement claim for turbinesFoam rests on the NREL Phase VI case.

## Layout

```
tools/blade_geometry.py     decode + emit the geometry table; tested loader
scripts/buildPolars.py      AirfoilInfo -> profileData converter, with --check
data/iea15mw_blade.csv      committed geometry table (50 stations)
data/polars/polar_NN.dat    committed profileData polars (50 stations)
PROVENANCE.md               sources, sha256, derivation, limitations
```

Rebuild / verify:

```sh
python turbinesFoam/validation/iea15mw/tools/blade_geometry.py
python turbinesFoam/validation/iea15mw/tools/blade_geometry.py --check
python turbinesFoam/validation/iea15mw/scripts/buildPolars.py
python turbinesFoam/validation/iea15mw/scripts/buildPolars.py --check
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

## Known limitations

See `PROVENANCE.md`: the `Re = 3.0e6` header is nominal for all 50 stations
(the WindIO per-section Re differs), and the polars are the 2-D tables with no
3-D stall-delay correction.
