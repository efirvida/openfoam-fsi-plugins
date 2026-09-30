# Design — Lindenburg bounded rotational augmentation (`turbinesFoam` ALM)

Feature: `phasevi-lindenburg-design` · Branch: `feat/dagsorensen-tip-correction`
Companion to `odd/tasks/phasevi-stall-delay-literature.md` §6 (vision-verified
equations) and the existing Du-Selig implementation in
`turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/`.

## 1. Goal

Add a **bounded** rotational-augmentation (3-D stall-delay) model alongside the
existing Du-Selig one. Du-Selig blends toward the unbounded potential reference
`CL,p = 2π(α − α0)`, so in deep stall it keeps inflating: at `r/R = 0.216`,
`α = 26.8°` it gives `CL = 2.276` where the 2-D polar says `0.71`. Lindenburg
adds bounded increments and self-limits as the section separates.

The default stays **Du-Selig**; the absent-`rotationalAugmentation` path and the
Du-Selig arithmetic are byte-for-byte unchanged.

## 2. Model (Ouakki & Arbaoui 2023, Eqs. 5–9; vision-verified)

```
dCL = 1.6 (c/r) (cos φ)² [ f² cos(α_rot) + 0.25 cos(α_rot − α0) ]   (7)
dCD = 1.6 (c/r) (cos φ)² f² sin(α_rot)                              (8)
α_rot = α + (0.25/2π) · 1.6 (c/r) (cos φ)²                          (9)
CL,3D = CL,2D + dCL ,   CD,3D = CD,2D + dCD
```

The `rΩ/V_eff` of Eq. (5) is replaced by the `cos φ` form throughout, per the
task contract.

* `c/r = chordLength_/radius_` (the per-element `radius` is already injected by
  the `rotationalAugmentation` feature).
* `α0 = degToRad(profileData_.zeroLiftAngleOfAttack())`.
* `cos φ`: with the element's already-computed `planformNormal_` (set in
  `calculateForce` before the hook),
  `V_N = relativeVelocity_ & planformNormal_`,
  `V_T = mag(relativeVelocity_ − V_N·planformNormal_)`,
  `cos φ = V_T / max(mag(relativeVelocity_), VSMALL)`.
  Because `α` is itself formed as `asin(V_N/|V_rel|)` from the same
  `planformNormal_`, this is exactly `cos φ = cos α` for this element; the
  normal/tangential split is nevertheless kept as written so the code is
  correct if the angle definition changes.

## 3. `f(α)` — Beddoes–Leishman / Kirchhoff trailing-edge separation factor

`f` is derived **from the static polar itself**, with no invented constants.
Invert the Kirchhoff relation

```
CL,2D = CL,inv · ((1 + √f)/2)² ,      CL,inv = (dCL/dα)(α − α0)
```

to

```
ratio = clamp(CL,2D / max(CL,inv, VSMALL), 0, 1)
r     = √ratio
f     = clamp((2r − 1)², 0, 1)
```

### What `normalCoeffSlope()` actually returns (checked)

`profileData::normalCoeffSlope()` returns **`dCN/dα`, in 1/rad**, fitted by
least squares over `[0, staticStallAngle/2]` on the **normal**-force
coefficient (`calcNormalCoeffSlope` builds `cnList =
normalCoefficientList(...)` and solves for the slope). It is **not**
`dCL/dα`, so it is not the right quantity for the CL-form Kirchhoff inversion
above. (`LeishmanBeddoes::cnToF` uses it correctly for its own CN-form
Kirchhoff inversion; that path is untouched.)

### Chosen slope: `profileData::liftCoeffSlope()` (new)

A new `profileData::liftCoeffSlope()` mirrors `calcNormalCoeffSlope` exactly but
fits `CL` rather than `CN` over the same `[0, staticStallAngle/2]` window
(identical least-squares normal equations, `liftCoefficientList` substituted for
`normalCoefficientList`). It is plumbed through the existing `multiRe` path
(`liftCoeffSlopeList_`, `interpPropsMultiRe`) and lazily computed for
`singleRe`. No constant is invented: the linear window is the repo's existing
stall-slope window, and the slope comes from the committed polar.

## 4. Boundary / guard choices

| Guard | Choice | Reason |
|---|---|---|
| `CL,inv ≤ 0` (i.e. `α ≤ α0`) | `f = 1` (attached) | cannot be separated on/inside the zero-lift line; avoids dividing by a non-positive reference |
| `CL,2D > CL,inv` | ratio clamps to 1 → `f = 1` | measurement scatter above the inviscid line still yields `f ≤ 1` |
| `f` | clamped to `[0, 1]` | `f` is a separation fraction |
| degenerate placeholder polar | skip (shared `hasZeroLiftReference()` guard) | the Phase VI root `cylinder` has no zero-lift reference; matches Du-Selig |
| unknown `model` | `FatalIOError` | still fails loudly; now accepts `DuSelig` and `Lindenburg` |

## 5. Wire-in

* `actuatorLineElement::read()` accepts `model DuSelig | Lindenburg`; default
  `DuSelig` (`lookupOrDefault`), unknown models still `FatalIOError`.
* `correctRotationalAugmentation()` dispatches to the new private
  `correctLindenburgRotationalAugmentation()` when the model is `Lindenburg`,
  then `return`s. The Du-Selig body below the dispatch is untouched.
* New fixture `tests/rotationalAugmentation/rotor/system/fvOptions.lindenburg`
  (basis `fvOptions.on`, only `model` differs) + an `Allrun -lindenburg` branch.

## 6. Tests

Pure Python (`tests/test_rotational_augmentation.py`):

* `f` in `[0,1]` and non-increasing over `0..20°` (pre-stall through stall at
  ~17.2° and just past it); `f ≈ 1` pre-stall, `f < 0.05` at 20°.
* pre-stall `f = 1` when `CL,2D ≥ CL,inv`.
* deep-stall boundedness: `CL,3D` finite, below the potential reference, below
  Du-Selig, and increments below their hard bounds `1.6(c/r)·1.25` / `1.6(c/r)`;
  the Du-Selig increment is shown to grow with `α`.
* structural/config pins so the Python reference cannot drift from the C++ and
  the rendered fixture.
* integration: the `-lindenburg` fixture's element CSV matches the Python
  reference; the default-off / Du-Selig tests are unchanged.

## 7. Judgement calls (recorded, not hidden)

1. **Pre-stall "increment near zero" is a Du-Selig property, not a Lindenburg
   one.** The task asks for a pre-stall check where `CL,2D ≈ CL,inv ⇒ f = 1` and
   "the increment is near zero". With the Eqs. 7–9 as written, `f = 1` retains
   the attached-lift term `1.6(c/r)(cos φ)²[cos α_rot + 0.25 cos(α_rot − α0)]`,
   which is **bounded but not zero**. The near-zero pre-stall increment is the
   Du-Selig blend's behaviour (`CL,2D ≈ CL,p`), already covered by
   `test_pre_stall_unchanged`. The Lindenburg pre-stall test therefore pins
   `f = 1` and the bounded attached increment and states this explicitly.
2. **`f` is monotone only through the stall onset.** The committed S809 table
   (measured OSU range + static extension) has non-monotone `CL` bumps in the
   deep-stall region (e.g. `0.67@20°`, `0.77@24°`, `0.95@30°`), so the inverted
   `f` has small non-monotone wiggles beyond ~24°. The monotonicity test is
   limited to `0..20°`, the region the task calls "through stall".
3. `Lindenburg` is applied to both `CL` and `CD` (Eqs. 7–8); unlike Snel/SD-ALM
   (lift only) no coefficient is left uncorrected.
