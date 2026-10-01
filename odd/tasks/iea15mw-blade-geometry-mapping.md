# IEA 15 MW blade geometry mapping — AeroDyn → turbinesFoam ALM

- **Status:** design (verified numerically; implementation next)
- **Branch:** `feat/dagsorensen-tip-correction`
- **Trigger:** maintainer flagged the blade orientation (Aeroelast builds the
  blade with the span along one axis and the profiles in the section plane).
- **Verification harness:** `/tmp/geoverify/verify2.py` (scratch; to be promoted
  into a package test).

## The gap

P0/P2 reduce the blade to `(axialDistance=0, radius=HubRad+BlSpn, azimuth=0,
chord, chordMount, -BlTwist)`. AeroDyn/OpenFAST carries three more terms
(`AeroDyn.f90:1323-1331`, `docs/.../aerodyn/input.rst:920-950`):

```fortran
positionL = (BlCrvAC, BlSwpAC, BlSpn)   ! aero-centre offsets from the pitch axis
theta     = (0, BlCrvAng, -BlTwist);  orientationL = EulerConstruct(theta)
```

| term | meaning | range (IEA 15 MW) | currently |
|---|---|---|---|
| `BlCrvAC` | prebend, out-of-plane, **+ downwind** | 0 … **−4.00 m** (tip) | 0 |
| `BlSwpAC` | sweep, in-plane, **+ opposite rotation** | −0.44 … +0.09 m | 0 |
| `BlCrvAng` | curve angle (= prebend slope `atan(dCrvAC/dSpn)`) | +0.93 … **−5.77°** | 0 |
| `BlTwist` | twist, about the airfoil-plane normal | +15.59 … −1.24° | `-BlTwist` ✓ |

`BlCrvAng = -5.765°` at the tip and `dCrvAC/dSpn = -0.2398/2.3877` →
`atan = -5.73°`: the curve angle **is** the local slope of the prebend. AeroDyn
tilts the local section frame to follow the curved axis.

## Verified mapping (numerical comparison of reconstructed AeroDyn nodes vs the
rendered element positions; frame: rotor axis `(-1 0 0)`, vertical `(0 0 1)`,
`coneAngle 4` ≡ ElastoDyn `PreCone=-4°` ≡ `R_y(-4°)`)

Residual of the **current case** vs the AeroDyn aero-centre locus:

| component | residual | source |
|---|---|---|
| axial | up to +3.99 m (tip) | prebend dropped |
| in-plane | +0.06…+0.20 m (FFA-W3); ≤1.35 m (root/SNL) | sweep + `chordMount` reference |
| radial | ≤0.28 m | cone projection (2nd order) |

**Mapping to implement**

- `axialDistance = -BlCrvAC`  ← the dominant fix (4 m), sign pinned by
  "`BlCrvAC` positive downwind" + the upwind prebend.
- `azimuth = deg(asin(BlSwpAC / radius))` ← the sweep, ≤0.1° for the lifting
  stations.
- `curveAngle = BlCrvAng` ← a **new optional elementData column**; the ALM must
  tilt the element frame (span + chord) about the tangential/azimuthal axis by
  `BlCrvAng`, mirroring AeroDyn's `R_y(BlCrvAng)`. `pitch` alone cannot express
  it (it is a rotation about the span, `actuatorLineElement.C:1275-1283`).
- Keep `pitch = -BlTwist` (AeroDyn also negates) and `radius = HubRad + BlSpn`
  (cone via `coneAngle`).

## Open items

- **`chordMount` reference line.** P0 sets `chordMount` = the section
  aerodynamic-centre fraction (0.5 root / 0.316 SNL / 0.25 FFA-W3). TurbinesFoam
  builds the element at `pitch-axis + (chordMount-0.25)*chord`; AeroDyn's node is
  the aero centre relative to the **pitch axis**. For the lifting sections
  (`chordMount=0.25`) this is consistent and only the sweep is missing; at the
  circular root the two reference lines differ by ~1.3 m (a force-free cylinder,
  so aerodynamically inert). Decide whether to leave the root as-is or align it.
- **Curve-angle span sign.** A first reconstruction shows the AeroDyn span must
  be matched up to a sign convention and carries the twist rotation; the sign of
  the curve-angle tilt needs a dedicated numeric check (the span comparison still
  has a ~10° residual from the twist/axis convention, unrelated to `BlCrvAng`).
- **`elementProfiles` mapping** (`elementProfiles[i*50/147]`,
  `actuatorLineSource.C:251`) is the other P2 risk and is untouched here.

## Tasks

1. [ ] Promote the verification harness into `tests/test_iea15mw_case.py`
       (reconstruct the AeroDyn aero-centre locus and assert the rendered
       `elementData` matches it to < 1 cm, plus the curve angle = `BlCrvAng`).
2. [ ] Emit `BlCrvAC`/`BlSwpAC`/`BlCrvAng` into `data/iea15mw_blade.csv`
       (`blade_geometry.py`), keeping `--check` clean.
3. [ ] Map them into `elementData` (axial / azimuth / new curve-angle column)
       in `tools/blade_geometry.py::element_rows` + `generate_case.py`.
4. [ ] C++: accept the optional curve-angle column and tilt the element frame
       about the azimuthal axis; **default-off byte-identical** when absent.
5. [ ] Re-render and re-run the P3 runner fix + launch.
