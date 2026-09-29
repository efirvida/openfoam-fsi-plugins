# Design: Rotational augmentation (3D stall delay) in the shared blade-load chain

Change: `rotational-augmentation` — project: `of-plugins` — date: 2026-09-23.
Reference: Yang & Sotiropoulos, *A new class of actuator surface models for wind
turbines*, arXiv:1702.02108v4 (2018); equation numbers below are the paper's own.
Primary evidence: `turbinesFoam/validation/phaseVI/results/DIAGNOSIS-2026-09-21.md`.
This change is orthogonal to the archived S2 `blade-actuator-surface`: it targets
the shared BEM/polar/stall/end-effect chain underneath, not the force
distribution geometry.

Status note: this document was produced from the proposal, the six delta specs,
`exploration.md`, and a direct read of the cited sources. Every code claim
carries a `file:line` reference into the tree at the time of writing. The
Du–Selig algebra is taken from the source PDF (the verified exponents recorded
in proposal Decision 1); the text-dump reading is not used. **Correction
(2026-09-24):** the preprint's printed Eqs. 11–12 are a transcription error and
this change implements the original Du & Selig prefactor form — see §1.1 and
`research-formulation-fidelity.md` (Engram #179).

---

## 1. Technical Approach

The change adds **one physics term** — the Du–Selig rotational augmentation
(3D stall delay) — to the **single element force chain every model inherits**,
and makes it additive and default-off. Every element force is produced by
`actuatorLineElement::calculateForce` (`actuatorLineElement.C:757-880`); the
no-mesh actuator surface element does not override it, and the mesh-backed
`bladeSurfaceSource` consumes `element.force()`. A correction placed after the
static coefficient lookup in that one method therefore reaches ALM, ASM and the
mesh surface at once, with no per-model code (spec
`rotational-augmentation`, "Single-chain inheritance").

The change is built from four pieces:

1. **Du–Selig correction in the shared chain** (W1): a new
   `rotationalAugmentation` block, read default-off and mirrored on
   `dynamicStall` (`actuatorLineElement.C:103-116`); a private
   `correctRotationalAugmentation()` method that rewrites `liftCoefficient_` and
   `dragCoefficient_` in place with Eqs. 9–10 (Du–Selig Eqs. 9–12); a hook in
   `calculateForce` after `lookupCoefficients()` (`:819`) and before the
   dynamic-stall call (`:835`).
2. **Per-element radial geometry** (W1): `createElements`
   (`actuatorLineSource.C:141-406`) injects `radius` and `rotorRadius` into every
   element dict, with `radius = rootRadius + rootDistance·(rotorRadius −
   rootRadius)` — the exact identity behind the compare tool's `r/R`
   (`comparePhaseVI.py:280-287`). AFTAL forwards `rotorRadius`/`rootRadius` into
   each blade subdict at the existing `dynamicStall` seam
   (`axialFlowTurbineALSource.C:314-328`).
3. **Leishman–Beddoes singularity guard** (W2): a determinant check / analytic
   2×2 solve with a documented fallback at `LeishmanBeddoes.C:321`, confined to
   `calcK1K2`, so the optional dynamic-stall path runs instead of aborting with
   `Singular Matrix`.
4. **Phase VI integration + proxy harness** (W3/W4): the YAML single source of
   truth gains the augmentation on-switch and the root-effect ablation, rendered
   through the existing generator (`generate_case.py:482-625`); a committed
   0.25-rev D/32 proxy harness runs the control / augmentation-on /
   augmentation-on + root-off variants serially on the authorized dev queue and
   fails loudly on the pass/fail criteria. Production stays **prepared-only**.

The primary fix keeps `rootEffects on` (`case.yaml:201-205`); root-off is a
render-time ablation variant, not a change to the committed default. The
`c_ref_t` versus measured CT definitional mismatch stays out of scope and is
recorded as a documented caveat (spec `phasevi-proxy-verification`,
"Definitional mismatch documented, not fixed").

### 1.1 Formulation being implemented (explicit)

The paper's chain is Du–Selig → Shen tip loss. This change implements the
**original Du & Selig (1998)** formulation; the paper defines

- Eq. 9  `CL,3D = CL,2D + fL·(CL,p − CL,2D)`;
- Eq. 10 `CD,3D = CD,2D − fD·(CD,2D − CD,0)`;
- Eq. 11 `fL = (1/2π)[ (1.6(c/r)/0.1267)·(a − (c/r)^((d/Λ)(R/r))) /
  (b + (c/r)^((d/Λ)(R/r))) − 1 ]`;
- Eq. 12 `fD = (1/2π)[ (1.6(c/r)/0.1267)·(a − (c/r)^((d/(2Λ))(R/r))) /
  (b + (c/r)^((d/(2Λ))(R/r))) − 1 ]`;
- `CL,p = 2π(α − α0)`, `CD,0` = the 2D drag at α = 0 (the paper's definition;
  the implementation maps it to `profileData_.zeroLiftDragCoeff()`, which is
  the drag at **CL = 0** — see §2.2), `Λ =
  ΩR/√(U² + (ΩR)²)`, with `a = b = d = 1`.

Here `1.6(c/r)/0.1267` is a **prefactor** on the fraction `(a − X)/(b + X)`;
`a` and `b` are the numerator/denominator constants, not an exponent or
multiplier of `c/r`.

**Fidelity correction (2026-09-24).** `arXiv:1702.02108v4` Eqs. 11–12 print a
*different*, split form — `(1.6(c/r)a − X)/(0.1267b + X) − 1`. That printed
form is a **transcription error**: it treats `1.6(c/r)` and `0.1267` as
numerator/denominator terms rather than as a prefactor, which inverts the drag
correction sign over most of the blade and enlarges the outboard `fL < 0` region
roughly fourfold by span. The corrected prefactor form is the primary-source
Du & Selig (1998, AIAA-98-0021) form and is reproduced independently by NREL
`AirfoilPrep.py`, BYU `CCBlade.jl`, Munduate (2002) Eq. 3.6, IOP 2024 Eq. (3),
and — decisively — Li, Liu & Yang (2022) *Energies* 15:6533 Eqs. (21)–(22), by
the same author as the preprint. Evidence:
`research-formulation-fidelity.md` (Engram #179).

The exponent is **`(d/Λ)(R/r)`** (Eq. 11) and **`(d/(2Λ))(R/r)`** (Eq. 12). The
text-dump reading `d·ΛR/r` is a layout artifact and MUST NOT be used (spec
`rotational-augmentation`, "Equation form and paper constants").

`CL,p` and `CD,0` come from `profileData`:
`profileData_.zeroLiftAngleOfAttack()` (`profileData.C:879-886`, degrees) and
`profileData_.zeroLiftDragCoeff()` (`profileData.C:869-876`). Semantic mismatch
recorded: the paper's `CD,0` is the drag at **zero angle of attack**, while
`zeroLiftDragCoeff()` returns the drag at **zero lift** (`CL = 0`;
`profileData.C:294` interpolates `cd` at `cl = 0`). The two differ because the
S809 profile has a non-zero zero-lift angle; the existing accessor is kept as
the closest available quantity. No new table and no free parameter is
introduced.

**Numerical check (this session, `/scratch/leahk/eduardo.donestevez/venv/bin/python`).**
At the diagnosed U13 mid-span point (`r/R ≈ 0.44`, `c/r ≈ 0.29`, `R/r ≈ 2.27`,
`Λ ≈ 0.95`, `a=b=d=1`) the corrected (prefactor) equations give `fL ≈ 0.339`,
so with the diagnosed 2D operating range (`CL,2D ≈ 0.598` control, `≈ 0.73`
static polar) and `CL,p ≈ 3.1` the corrected `CL,3D ≈ 1.45–1.53`, consistent
with the diagnosis's implied `cl ≳ 1.2`. A sweep over the committed Phase VI
blade geometry at `Λ ≈ 0.946` shows `fL` crossing zero near `r/R ≈ 0.90` and
staying negative only in a thin outboard band (`fL ≈ −0.02` at `r/R = 0.96`),
while `fD` is positive inboard (max ≈ +0.68 near the root cutout) and crosses
zero near `r/R ≈ 0.75` (`fD ≈ −0.03` at `r/R = 0.83`, `−0.06` at `r/R = 0.96`)
— the paper's intended inboard drag decrease; §2.4 fixes the handling (apply
literally, no invented clamp). For comparison, the split form printed by the
preprint crosses `fL = 0` near `r/R ≈ 0.70` and `fD = 0` near `r/R ≈ 0.36`,
leaving `fD < 0` (drag *increased*) over most of the blade.

### 1.2 Work decomposition (delivery forecast)

| Unit | Content | Est. lines |
|------|---------|-----------|
| W1 | `rotationalAugmentation` block read + `correctRotationalAugmentation()`, hook in `calculateForce`, `radius`/`rotorRadius` injection in `createElements`, AFTAL forwarding, C++ integration tests + pure-Python expected-value test, turbinesFoam README | ~300–500 |
| W2 | LB singularity guard in `calcK1K2` + fallback record + guard test | ~60–120 |
| W3 | Phase VI `rotationalAugmentation` on-switch + `rootEffects` ablation in `case.yaml`/`generate_case.py`, case/render tests, docs | ~250–450 |
| W4 | Committed 0.25-rev D/32 proxy harness + variant matrix + comparison caveat + README/CHANGELOG | ~200–400 |

Forecast total **~810–1470 changed lines**, over the 400-line `single-pr` review
budget. The session strategy is `single-pr`, so under that strategy **apply
requires an explicit `size:exception` before it starts** (S1/S2 precedent); the
W1→W4 chain is the prepared alternative and every unit is independently testable
and revertable (§9).

---

## 2. Paper → Code Mapping

The config rule (`openspec/config.yaml` `rules.design`) requires a paper → code
table. This change implements the paper's Eqs. 9–12 in the existing BEM chain; it
does not implement the Shen tip loss (already ported as the `Shen` end-effect
model, `axialFlowTurbineALSource.C:634-658`) and does not switch the end-effect
model (production stays `Glauert`, `:614-633`).

### 2.1 Dimensional chain and sign conventions

The correction works on the dimensionless coefficient stage, before the force is
built. `lookupCoefficients()` (`actuatorLineElement.C:238-243`) writes
`liftCoefficient_`, `dragCoefficient_`, `momentCoefficient_` from `profileData`
at `angleOfAttack_` (degrees). `correctRotationalAugmentation()` rewrites the
lift and drag members in place; the moment coefficient is untouched (Du–Selig
Eqs. 9–10 have no moment term). Downstream, the force is built as

    lift = 0.5*area*liftCoefficient_*magSqr(relativeVelocity_)
    drag = 0.5*area*dragCoefficient_*magSqr(relativeVelocity_)
    forceVector_ = lift*liftDirection + drag*dragDirection

(`actuatorLineElement.C:864-872`), so the corrected coefficients flow into
`forceVector_`, the per-element CSV (`:529,538-547`), and AFTAL's torque/power.

| Step | Quantity | Units | Where it lives |
|------|----------|-------|----------------|
| 1 | Static `CL,2D`/`CD,2D` | – | `lookupCoefficients()` (`:238-243`) |
| 2 | Augmented `CL,3D`/`CD,3D` (in place) | – | new `correctRotationalAugmentation()` (§3 D1) |
| 3 | Dynamic-stall / added-mass corrections | – | `:835-845`, `:848-859` (consume the augmented values) |
| 4 | End-effect factor on lift | – | `liftCoefficient_ *= endEffectFactor_` (`:862`) |
| 5 | Force per unit density | m⁴/s² (N/ρ) | `forceVector_` (`:864-872`) |
| 6 | Per-element CSV | – | `actuatorLineElement.C:529,538-547` |

**Sign/order**: the correction is dimensionless and multiplicative on the
existing signed coefficients, so no new sign convention is introduced. The
end-effect factor is applied **after** the hook (`:862`), so the paper's
Du–Selig → tip-loss order is preserved by construction. The element CSV is
written after `calculateForce`, so it already reports the corrected
`c_ref_t`/`c_ref_n` (`:529,545-546`).

### 2.2 Equation → code table

| Paper Eq. | Meaning | Code location | Notes |
|-----------|---------|---------------|-------|
| **Eq. 9** — `CL,3D = CL,2D + fL(CL,p − CL,2D)` | Augmented lift | `correctRotationalAugmentation()` (new, `actuatorLineElement.C`) | `liftCoefficient_ += fL*(CLp - liftCoefficient_)`; `CLp = 2π(α − α0)` with `α = degToRad(angleOfAttack_)`, `α0 = degToRad(profileData_.zeroLiftAngleOfAttack())` |
| **Eq. 10** — `CD,3D = CD,2D − fD(CD,2D − CD,0)` | Augmented drag | same method | `dragCoefficient_ -= fD*(dragCoefficient_ - CD0)`; `CD0 = profileData_.zeroLiftDragCoeff()` |
| **Eq. 11** — `fL = (1/2π)[(1.6(c/r)/0.1267)·(a − X_L)/(b + X_L) − 1]` | Lift factor | same method (private helper) | original prefactor form, primary source Du & Selig (1998) — **not** the arXiv preprint's split form (§1.1, fidelity correction); exponent `(d/Λ)(R/r)`, `X_L = (c/r)^exponent`; `c/r = chordLength_/radius_`, `R/r = rotorRadius_/radius_` |
| **Eq. 12** — `fD = (1/2π)[(1.6(c/r)/0.1267)·(a − X_D)/(b + X_D) − 1]` | Drag factor | same method (private helper) | original prefactor form; exponent `(d/(2Λ))(R/r)`, `X_D = (c/r)^exponent`; same ratios |
| **`Λ = ΩR/√(U²+(ΩR)²)`** | Local rotational parameter | same method | `ΩR = omega_*rotorRadius_`, `U = mag(freeStreamVelocity_)`; both are existing element members (`actuatorLineElement.H:108,169`) |
| **`CL,p = 2π(α − α0)`** | Potential-flow lift | same method | `α0` from `profileData.C:879-886` (degrees) |
| **`CD,0`** | 2D drag at α = 0 (paper) | same method | `zeroLiftDragCoeff()` (`profileData.C:869-876`) returns the drag at **CL = 0**, not at α = 0 (`profileData.C:294`) — documented mismatch, accessor kept |
| **Constants `a=b=d=1`** | Paper constants | read from the block, defaults 1 | spec: paper constants only; no calibration |
| **Eqs. 13–16 (Shen tip loss)** | Tip loss | Not implemented here | Already ported as the `Shen` end-effect model (`axialFlowTurbineALSource.C:634-658`); production stays `Glauert` |

### 2.3 Insertion point and in-place effect

`calculateForce` currently runs:

    calculateInflowVelocity(Uin);                 // :780
    ... relativeVelocity_, Re_                    // :788-790
    ... angleOfAttack_                             // :792-813
    profileData_.updateRe(Re_);                    // :816
    lookupCoefficients();                          // :819  -> CL,2D / CD,2D
    [HOOK HERE]                                    // ~:820 (new)
    if (dynamicStallActive_) dynamicStall_->correct(...)   // :835-845
    if (addedMassActive_) addedMass_.correct(...)          // :848-859
    liftCoefficient_ *= endEffectFactor_;                   // :862
    forceVector_ = lift*liftDirection + drag*dragDirection; // :864-872

The hook is a single call

```cpp
    // Apply rotational augmentation (Du-Selig) to the static coefficients
    if (rotationalAugmentationActive_)
    {
        correctRotationalAugmentation();
    }
```

placed immediately after `lookupCoefficients()` and before the dynamic-stall
call. It rewrites `liftCoefficient_`/`dragCoefficient_` in place, so
dynamic stall, added mass, the end-effect factor and the CSV all consume the
corrected values; no downstream stage re-applies the correction (spec: "The
correction MUST NOT be re-applied by any downstream stage").

**Pre-stall behaviour**: below stall the static polar has `CL,2D ≈ CL,p`, so
`(CL,p − CL,2D) ≈ 0` and `CL,3D ≈ CL,2D` (spec "Pre-stall lift unchanged"). The
drag term still follows Eq. 10.

### 2.4 Near-tip `fL < 0`: physical handling (no invented clamp)

For small `c/r` the prefactor `1.6(c/r)/0.1267` in Eq. 11 vanishes and
`(a − (c/r)^x)/(b + (c/r)^x) → a/b = 1`, so `fL → −1/(2π) ≈ −0.159`. The
numerical sweep in §1.1 (corrected form) shows `fL` crossing zero near
`r/R ≈ 0.90` and staying negative only in a thin outboard band; `fD` is positive
inboard and crosses zero near `r/R ≈ 0.75`, so it is negative only close to the
tip at the Phase VI `Λ`. With `fL < 0` and
`CL,p > CL,2D` (deep stall), Eq. 9 reduces the outboard lift; with `fD < 0`,
Eq. 10 raises the outboard drag.

**Handling**: implement Eqs. 9–12 literally. Do **not** clamp `fL`, do not zero
the correction outboard, and do not gate it on a stall threshold — the spec
("Near-tip behavior is recorded, not clamped") forbids an invented clamp. The
behaviour is recorded in the sensitivity note in `turbinesFoam/README.md` and the
Phase VI README, together with the fact that the end-effect factor is applied
after the hook (`:862`), so the tip lift is additionally reduced by the tip-loss
model. The inboard stalled region, where the correction is intended to act,
gains lift; the net power effect is an empirical outcome measured by the proxy
(§7), not something the design pre-judges.

### 2.5 Interaction and ordering with Leishman–Beddoes

`LeishmanBeddoes::calcK1K2` (`LeishmanBeddoes.C:305-324`) refits its K1/K2
constants on the **static** polar tables —
`profileData_.normalCoefficientList(0.5, 25)` and
`momentCoefficientList(0.5, 25)` (`:308-311`) — not on the element's
`liftCoefficient_`. Because the hook rewrites the element members only, the LB
internal fit sees the same static data as before: the correction does not mutate
the fit inputs.

The ordering is therefore: **augmentation first, dynamic stall second**. The
dynamic-stall model receives the augmented `CL,3D`/`CD,3D` as its input
coefficients, which is what the spec ("Ordering relative to dynamic stall")
requires. The potential double-count concern (LB also models deep-stall
overshoot) is real but out of scope for this change: the primary fix does not
enable LB, and the LB fit-input review (`cm` data, `cmFitExponent_`) is an
explicit follow-up (spec `dynamic-stall-singularity-guard`, "Fit-input review
remains out of scope"). W2 makes the LB path *runnable* and the guard test
records the ordering is exercised; the design does not claim the combined model
is validated.

---

## 3. Architecture Decisions

### D1 — Du–Selig in `calculateForce`, after the static lookup, before dynamic stall (proposal Decision 1)

**Choice**: one private method `correctRotationalAugmentation()` on
`actuatorLineElement`, called from `calculateForce` between
`lookupCoefficients()` (`actuatorLineElement.C:819`) and the dynamic-stall call
(`:835`). It rewrites `liftCoefficient_`/`dragCoefficient_` in place with
Eqs. 9–12 (`a=b=d=1`). No new class, no RTS registration, no new `.C` file.

```cpp
void Foam::fv::actuatorLineElement::correctRotationalAugmentation()
{
    const scalar pi = Foam::constant::mathematical::pi;
    const scalar cOverR = chordLength_/radius_;
    const scalar ROverR = rotorRadius_/radius_;
    const scalar omegaR = omega_*rotorRadius_;
    const scalar lambda = omegaR/Foam::sqrt
    (
        magSqr(freeStreamVelocity_) + sqr(omegaR)
    );

    const scalar xL = (d_/lambda)*ROverR;
    const scalar xD = (d_/(2.0*lambda))*ROverR;
    const scalar qL = Foam::pow(cOverR, xL);
    const scalar qD = Foam::pow(cOverR, xD);
    // Original Du & Selig (1998) prefactor form (see §1.1 fidelity correction)
    const scalar fL = (1.0/(2.0*pi))
        *((1.6*cOverR/0.1267)*((a_ - qL)/(b_ + qL)) - 1.0);
    const scalar fD = (1.0/(2.0*pi))
        *((1.6*cOverR/0.1267)*((a_ - qD)/(b_ + qD)) - 1.0);

    const scalar alpha = degToRad(angleOfAttack_);
    const scalar alpha0 = degToRad(profileData_.zeroLiftAngleOfAttack());
    const scalar CLp = 2.0*pi*(alpha - alpha0);
    const scalar CD0 = profileData_.zeroLiftDragCoeff();

    liftCoefficient_ += fL*(CLp - liftCoefficient_);
    dragCoefficient_ -= fD*(dragCoefficient_ - CD0);
}
```

**Alternatives considered**:

- **(B) per-element polar-table rewrite** (exploration Approach 1B): rewrite
  `liftCoefficientList_`/`dragCoefficientList_` from the table using the
  element's `c/r` and `Λ`. Rejected: `c/r` and `Λ` vary per element **and** per
  operating point (`Λ` depends on TSR/U), so a static rewrite is valid for one
  condition only; mutating the table also feeds `analyze()` and the LB fit
  inputs.
- **(C) new RTS correction-model class** (exploration Approach 1C): a
  `rotationalAugmentationModel` base with a `DuSelig` implementation. Rejected:
  one formula does not justify new files/`Make/files`/RTS for a heavier
  abstraction; the current per-element correction models are `autoPtr` members,
  but the hook is one method and the spec does not require selectable models
  beyond the `DuSelig` name.

**Rationale**: the single shared method is the only place that fixes ALM, ASM
and the mesh surface together (spec "Single-chain inheritance"); placing the
hook before dynamic stall and before the end-effect factor matches the paper's
chain order by construction; in-place mutation means the CSV, `force()` and
AFTAL's torque all see the corrected values.

### D2 — Per-element radial geometry `radius`/`rotorRadius` (proposal Decision 1)

**Choice**: AFTAL forwards `rotorRadius` and `rootRadius` into each blade
subdict at the existing `dynamicStall` seam
(`axialFlowTurbineALSource.C:314-328`); `actuatorLineSource::createElements`
(`actuatorLineSource.C:141-406`) reads them from `coeffs_` and injects
`radius` + `rotorRadius` into every element dict alongside the existing keys
(`:316-378`):

```cpp
const scalar rotorRadius =
    coeffs_.lookupOrDefault("rotorRadius", -VGREAT);
const scalar rootRadius =
    coeffs_.lookupOrDefault("rootRadius", -VGREAT);
const bool haveRadialGeometry =
    rotorRadius > 0.0 and rootRadius > 0.0;
...
if (haveRadialGeometry)
{
    const scalar radius =
        rootRadius + rootDistance*(rotorRadius - rootRadius);
    dict.add("radius", radius);
    dict.add("rotorRadius", rotorRadius);
}
```

- **`rootRadius`** is the radial station of the blade's first construction
  point, i.e. the root cutout. AFTAL already reads it as `elementData[0][1]`
  (the radius column, `axialFlowTurbineALSource.C:138`) and for Phase VI it
  equals `ROOT_CUTOUT_RADIUS = 0.5083` (`case_config.py:48`,
  `comparePhaseVI.py:72`). AFTAL forwards `rotorRadius_` (the existing member,
  `turbineALSource.H:109`, read at `turbineALSource.C:517`) and this root
  station.
- **`radius` identity**: `rootDistance` is computed in `createElements` as
  `mag(position − rootLocation)/totalLength_` (`:314`), 0 at the root cutout
  and 1 at the tip. The injected identity
  `radius = rootRadius + rootDistance·(rotorRadius − rootRadius)` is exactly the
  inverse of `comparePhaseVI.py:280-287`, so the element's `r` matches the
  comparison tool's `r/R`.
- **Element side**: the constructor reads both keys with `lookupOrDefault`
  sentinels and stores `radius_`/`rotorRadius_`; if either is absent the
  correction is not applied and the element behaves as before (spec "Absent keys
  keep the old dictionary valid"). The `c/r`, `R/r` and `Λ` are then computed
  from these scalars plus the element's own `chordLength_`, `omega_` and
  `freeStreamVelocity_` (spec "Per-element radial geometry interface").
- **AFTAL forwarding is additive**: when the rotor has no radial keys, nothing
  is added to the blade subdict and `createElements` injects nothing.

**Alternatives considered**: derive `rootRadius` inside `createElements` from
`rootLocation` and a rotor origin — rejected: the blade source does not hold the
rotor origin/axis (they live in `turbineALSource`), and adding them would be a
larger interface than forwarding two scalars; pass a precomputed
`chordOverRadius` per element — rejected: `Λ` still needs `rotorRadius`, and
the spec fixes the `radius`/`rotorRadius` key names.

**Rationale**: pure per-element scalars, no new restart state, no halo exchange,
and MPI-safe (every element is constructed identically on every rank from the
same replicated dictionary). Parallel/restart invariance follows from the
absence of new time state (spec "Parallel and restart safety").

### D3 — Additive default-off `rotationalAugmentation` switch (proposal Decision 2)

**Choice**: a new element sub-block, read in the element constructor exactly
like `dynamicStall` (`actuatorLineElement.C:103-116`) and forwarded by AFTAL like
`dynamicStallDict_` (`axialFlowTurbineALSource.C:316`):

```
rotationalAugmentation
{
    active  off;      // default; Phase VI switches it on
    model   DuSelig;
    a       1;        // paper constants only
    b       1;
    d       1;
}
```

Element-side read:

```cpp
if (dict_.found("rotationalAugmentation"))
{
    const dictionary raDict = dict_.subDict("rotationalAugmentation");
    rotationalAugmentationActive_ = raDict.lookupOrDefault("active", false);
    rotationalAugmentationModel_ = raDict.lookupOrDefault<word>
    (
        "model", "DuSelig"
    );
    a_ = raDict.lookupOrDefault("a", 1.0);
    b_ = raDict.lookupOrDefault("b", 1.0);
    d_ = raDict.lookupOrDefault("d", 1.0);
    if (rotationalAugmentationModel_ != "DuSelig")
    {
        FatalIOErrorInFunction(raDict)
            << "Unknown rotationalAugmentation model '"
            << rotationalAugmentationModel_ << "'; only DuSelig is registered"
            << exit(FatalIOError);
    }
    if (rotationalAugmentationActive_ and not haveRadialGeometry)
    {
        WarningInFunction
            << "rotationalAugmentation active but radius/rotorRadius absent; "
            << "the correction is skipped" << endl;
        rotationalAugmentationActive_ = false;
    }
}
```

- **Default off** keeps every existing run byte-identical and makes the change
  regression-gated (spec "Default-off byte-identical output"); the Phase VI case
  switches it on explicitly via `case.yaml`.
- **Unknown model fails loudly** (spec "Unknown model rejected").
- **Placement mirrors `dynamicStall`** (element/actuator dict, forwarded by
  AFTAL), so no new dictionary topology is introduced.

**Alternatives considered**: default on — rejected: breaks byte-identical
default output and the regression gate for every other case; an option inside
`profileData` — rejected: the correction is element/rotor-level (needs `radius`,
`omega`), while `profileData` is a per-profile table shared by elements.

### D4 — Leishman–Beddoes singularity guard (proposal Decision 3)

**Choice**: replace the unguarded `simpleMatrix<scalar> A(2).solve()`
(`LeishmanBeddoes.C:321`) with an **analytic 2×2 solve plus a determinant
guard** inside `calcK1K2`, with a documented fallback.

```cpp
// A is the 2x2 normal-equation matrix built at :313-320; b is its source.
const scalar det = A[0][0]*A[1][1] - A[0][1]*A[1][0];
const scalar scale =
    Foam::max(mag(A[0][0]*A[1][1]), mag(A[0][1]*A[1][0])) + VSMALL;
if (mag(det) > 1.0e-12*scale)
{
    K1_ = (A.source()[0]*A[1][1] - A[0][1]*A.source()[1])/det;
    K2_ = (A[0][0]*A.source()[1] - A.source()[0]*A[1][0])/det;
    if (debug)
    {
        Info<< "    Leishman-Beddoes K1/K2 analytic solve (det = "
            << det << ", path = well-conditioned)" << endl;
    }
}
else
{
    WarningInFunction
        << "singular/ill-conditioned Leishman-Beddoes K1/K2 fit matrix "
        << "(det = " << det << "); falling back to K1 = K2 = 0" << endl;
    K1_ = 0.0;
    K2_ = 0.0;
}
```

- **Well-conditioned fit preserved**: the analytic solve returns the same
  `K1`/`K2` as the unguarded `solve()` to round-off (spec "Well-conditioned fit
  preserved"); this is asserted by a test that feeds a well-conditioned matrix.
- **Fallback recorded**: a `WarningInFunction` plus an `Info`/debug record of
  the determinant and the path taken (spec "Documented, recorded fallback").
  `K1 = K2 = 0` is the documented physical fallback: it removes the K1/K2
  moment contribution rather than inventing a fit.
- **Blast radius one method**: `calcK1K2` is the only `.solve()` in the
  dynamic-stall models (exploration §5); no other model is touched (spec "Blast
  radius is one method").

**Alternatives considered**: always `K1=K2=0` on a singular matrix without the
analytic path — rejected as the primary because it would also discard a
well-conditioned fit; a regularised/least-squares refit — rejected: that changes
the fit inputs, which the spec explicitly leaves to the follow-up review.

### D5 — Root-effect policy and the Phase VI ablation (proposal Decision 3)

**Choice**: keep `rootEffects on` in the primary fix and the committed default
(`case.yaml:201-205`); run `rootEffects off` as a **separate render-time
ablation variant** in the proxy. The YAML single source of truth gains an
explicit root toggle that the generator renders into `GlauertCoeffs`
(`generate_case.py:561-570`), while the committed default stays `root: true`.

- The 22/09 data show root-off alone is necessary but insufficient (+17 % cl at
  U13, `c_ref_t` to ≈0 but no sign flip; +7.6 % at U7;
  `DIAGNOSIS-2026-09-21.md:118-127`). Keeping it on in the primary fix and
  running root-off separately resolves the end-effect confound and keeps the
  augmentation attribution clean (spec `phasevi-proxy-verification`, "Three
  variants share all keys but the toggles").
- The committed case MUST keep `rootEffects on`; the ablation is a render-time
  configuration, not a change to the committed default (spec
  `phasevi-validation-case`, "Root-effect ablation is a render-time variant").

**Alternatives considered**: root-off in the primary fix — rejected: changes
production physics and confounds attribution; a hub-bounded root factor —
deferred: a new model, out of scope.

### D6 — Committed 0.25-rev proxy harness (proposal Decision 4)

**Choice**: a committed harness under `validation/phaseVI/scripts/` that renders
the three variants from the committed case, copies each into a self-contained
package directory, patches only the augmentation switch and the root setting,
and chains the runs serially because the dev queue has `MaxSubmit=1`
(spec `phasevi-proxy-verification`). It is check/dry-run capable and never
submits a production job.

- The harness is the committed form of the 22/09 method
  (`$SCRATCH/tmp/phasevi-diag/diag.slurm`, `run_all.sh`): 0.25-rev D/32, 7 and
  13 m/s, 48 ranks, dev queue, ≈5–8 min per variant.
- Variant matrix: `control` (augmentation off, root on), `augmentation-on`
  (root on), `augmentation-on + root-off`; all other keys shared.
- Pass/fail: the control MUST reproduce `cp ≈ −0.0459` at U13 before any variant
  is interpreted; at U13 augmentation-on MUST turn mid-span `c_ref_t` clearly
  positive and `cp`/`ct` positive; at U7 the augmentation-on + root-off ablation
  MUST shrink the −16 % power/torque deficit toward or inside the ±15 % band
  (`comparePhaseVI.py:67-69`). The harness exits non-zero when a criterion is
  missed (spec "Fail-loud success criteria").
- Prepared-only: the production campaign stays prepared-only and the suspended
  arrays are read-only baselines (spec "Prepared-only production boundary").

**Alternatives considered**: an ad-hoc `$SCRATCH` script — rejected: the spec
requires a committed harness; a parallel Slurm array — rejected: the dev queue
has `MaxSubmit=1`, so the variants must chain serially.

### D7 — `c_ref_t` definitional caveat and claim boundary

**Choice**: do not fix the `c_ref_t` versus measured CT mismatch here. Record it
as a documented comparison caveat and use the integrated `cp`/`ct`/torque as the
primary proxy signal, with the spanwise `c_ref_t` **sign** secondary (spec
`phasevi-proxy-verification`). The mismatch is a separate follow-up (open
question).

**Rationale**: the diagnosis shows the simulated `c_ref_t` is ≈2× the measured
CT while the integrated torque is low (`DIAGNOSIS-2026-09-21.md:33-38`); fixing
the comparison definition is orthogonal to the physics fix and would confound
the proxy interpretation.

---

## 4. Interfaces / Contracts

### 4.1 `actuatorLineElement` additions

New protected members (declared next to the existing coefficient members,
`actuatorLineElement.H:135-169`):

```cpp
//- Switch for applying rotational augmentation
bool rotationalAugmentationActive_;

//- Rotational augmentation model name (only "DuSelig" registered)
word rotationalAugmentationModel_;

//- Du-Selig constants (paper defaults 1)
scalar a_;
scalar b_;
scalar d_;

//- Local radial station and rotor radius (sentinel when absent)
scalar radius_;
scalar rotorRadius_;
```

New private method, declared next to `lookupCoefficients()` in the header:

```cpp
//- Apply the Du-Selig rotational augmentation in place
void correctRotationalAugmentation();
```

No new public accessor is required; the existing `liftCoefficient()`,
`dragCoefficient()` (`:350-353`) and the CSV (`:529,538-547`) already expose the
corrected values.

### 4.2 Config keys

Element subdictionary (forwarded by AFTAL like `dynamicStall`,
`axialFlowTurbineALSource.C:314-328`; injected by `createElements`,
`actuatorLineSource.C:316-378`):

```
rotationalAugmentation
{
    active  off;      // default
    model   DuSelig;  // only registered name
    a       1;        // paper constants
    b       1;
    d       1;
}
```

Injected per element by `createElements` (authoritative, additive):
`radius` (m) and `rotorRadius` (m). AFTAL forwards `rotorRadius` and
`rootRadius` into the blade subdict; neither key is user-facing.

### 4.3 Leishman–Beddoes guard contract

`calcK1K2` returns either the analytic solve (`K1_`, `K2_` unchanged from the
unguarded result when well-conditioned) or the documented fallback
(`K1_ = K2_ = 0`) with a `WarningInFunction`. It never calls
`simpleMatrix::solve()`. No public signature changes.

### 4.4 Phase VI config contract

`config/case.yaml` `actuator` gains:

```yaml
actuator:
  rotational_augmentation:
    active: false          # committed default; Phase VI proxy turns it on
    model: DuSelig
    a: 1
    b: 1
    d: 1
  end_effects:
    active: true
    model: Glauert
    tip: true
    root: true             # ablation renders root: false
```

`generate_case.py::render_fv_options` (`:482-625`) renders the block into each
blade subdictionary at the same indentation as the element keys, identically in
all three twins, so the twins stay identical except for the element keys (spec
`phasevi-validation-case`).

---

## 5. Data Flow

```
case.yaml actuator.rotational_augmentation (W3)          element construction (W1)
-------------------------------------------              ---------------------------------
rotational_augmentation.active/model/a/b/d  ──►  generate_case.render_fv_options
                                                     │  (blade subdict, all 3 twins)
                                                     ▼
                                          system/fvOptions.{ALM,ASM,ASM-MESH}
                                                     │  runPhaseVI.sh installs the twin
                                                     ▼
AFTAL createBlades (axialFlowTurbineALSource.C:314-328)
   bladeSubDict.add("rotationalAugmentation", ...)      // forwarded like dynamicStall
   bladeSubDict.add("rotorRadius", rotorRadius_)
   bladeSubDict.add("rootRadius", elementData[0][1])
                     │
                     ▼
actuatorLineSource::createElements (actuatorLineSource.C:316-378)
   radius = rootRadius + rootDistance*(rotorRadius - rootRadius)   // :314
   dict.add("radius", radius); dict.add("rotorRadius", rotorRadius)
                     │
                     ▼
actuatorLineElement constructor
   read rotationalAugmentation block (default off, model DuSelig)
   read radius_/rotorRadius_ with lookupOrDefault sentinels
                     │
                     ▼
calculateForce (actuatorLineElement.C:757-880)
   lookupCoefficients()                      :819  -> CL,2D / CD,2D
   correctRotationalAugmentation()           ~:820 (NEW)
        c/r = chordLength_/radius_
        R/r = rotorRadius_/radius_
        Lambda = omega_*rotorRadius_/sqrt(|freeStreamVelocity_|^2 + (omega_*rotorRadius_)^2)
        fL, fD (Eqs. 11-12) ; CL,3D (Eq. 9) ; CD,3D (Eq. 10)  in place
   dynamicStall_->correct(...)               :835  (receives augmented values)
   addedMass_.correct(...)                   :848
   liftCoefficient_ *= endEffectFactor_      :862  (paper order: Du-Selig then tip loss)
   forceVector_ = lift*liftDirection + drag*dragDirection  :864-872
                     │
        ┌────────────┴─────────────┐
        ▼                          ▼
element CSV (c_ref_t/c_ref_n)   element.force() -> ALM field / ASM projection /
(:529,538-547)                  bladeSurfaceSource mesh distribution / AFTAL torque
```

Restart/parallel: the correction adds **no time state**. `radius_`,
`rotorRadius_` and the constants are construction-time scalars derived from the
replicated dictionary; `omega_` and `freeStreamVelocity_` are the existing
per-step values. A restarted or decomposed run reconstructs identical scalars on
every rank, so there is no new halo exchange and no restart file change.

---

## 6. Phase VI Integration Design

### 6.1 YAML single source of truth

`config/case.yaml` `actuator` gains `rotational_augmentation` (default off) and
the existing `end_effects.root` toggle is used for the ablation. The committed
default stays `active: false` and `root: true` (spec `phasevi-validation-case`,
"YAML single source of truth"). The `--select` whitelist
(`case_config.py:45,589-592`) already accepts `alm|asm|asm-mesh` and needs no
change for this feature.

### 6.2 Renderer

`generate_case.py::render_fv_options` (`:482-625`) gains optional
`rotational_augmentation: dict | None = None` and `root_effects: bool | None =
None`. When the augmentation is configured it renders, at the same indentation
as the element keys (`:524-530`):

```
                rotationalAugmentation
                {
                    active on;
                    model DuSelig;
                    a 1;
                    b 1;
                    d 1;
                }
```

and it renders `rootEffects` from the `end_effects.root` value already consumed
at `:568`. `outputs()` (`:628-677`) passes the same values to all three twins, so
`test_twins_differ_only_in_blade_keys` (`tests/test_phasevi_case.py:63-66`,
`BLADE_KEYS`) keeps passing with `rotationalAugmentation` not in `BLADE_KEYS`:
the block is **identical across the twins** and therefore must not be stripped.
`generate_case.py --check` (`check_outputs`, `:680-699`) stays clean for the
committed case.

### 6.3 CLI and runner

- `generate_case.py` CLI gains `--rotational-augmentation {on,off}` (default
  `off`, matching the committed default) and `--root-effects {on,off}` (default
  from `case.yaml`, `on`). These are render-time only; no case schema migration.
- `runPhaseVI.sh` needs no new model: the augmentation is a config/render
  variant of the existing models. `--submit` for `-m asm-mesh` already refuses
  (`:137-142`) and is unchanged. `runPhaseVI.sh -m alm -u 13` prepares a run
  directory without `--run`/`--submit` for the harness to reuse.
- The proxy harness (§7) renders the three variants directly through
  `generate_case.py` into self-contained package copies and patches only
  `system/fvOptions`.

### 6.4 Documentation

- `validation/phaseVI/README.md`: the augmentation formulation (Eqs. 9–12,
  `a=b=d=1`), the sensitivity note (no calibration, near-tip `fL < 0`), the
  root-effect ablation, the `c_ref_t` comparison caveat, the proxy matrix and
  the prepared-only production boundary.
- `turbinesFoam/README.md` and root `README.md`: the `rotationalAugmentation`
  key, the `radius`/`rotorRadius` injection and the claim boundary.
- Root `CHANGELOG.md`: one entry per work unit in the repository's
  `Files:` / `Problem:` / `Fix:` format.

---

## 7. Proxy Verification Harness Design

### 7.1 Shape and boundary

A committed harness under `validation/phaseVI/scripts/` (W4), for example
`proxyRotationalAugmentation.py` plus a thin `proxyRotationalAugmentation.sh`
wrapper. It is a **local/authorized-dev-queue** tool, not a production array:

- Renders the committed case at D/32, 0.25 rev, 7 and 13 m/s, 48 ranks,
  `sequana_cpu_dev`, using `generate_case.py` and the committed mesh staging
  (`runPhaseVI.sh` prepare path, `mesh.sh`).
- Copies each variant into a **self-contained package directory** (its own
  `system/fvOptions`, its own `constant/polyMesh` link and its own
  `postProcessing/`), so variants cannot contaminate one another (spec
  `phasevi-proxy-verification`, "Each variant MUST run in a self-contained
  package copy").
- Chains the three variants **serially** because the dev queue has
  `MaxSubmit=1` (spec "Serial dev-queue execution").
- `--check`/`--dry-run` prints the configuration (variants, speeds, mesh, revs,
  ranks, queue) and submits nothing (spec "Harness present and runnable").
- `--submit` is **not** implemented for production; the harness refuses any
  production queue and never cancels or modifies the suspended arrays.

### 7.2 Variant matrix

| Variant | `rotationalAugmentation` | `rootEffects` | Everything else |
|---------|--------------------------|---------------|-----------------|
| `control` | off | on | shared |
| `augmentation-on` | on (`DuSelig`, `a=b=d=1`) | on | shared |
| `augmentation-on-root-off` | on | off | shared |

The variants differ only in the augmentation switch and the root setting (spec
"Three variants share all keys but the toggles"). The harness asserts this by
diffing the rendered `system/fvOptions` after stripping the two toggle blocks.

### 7.3 Control-reproduction gate and pass/fail

1. **Control gate (mandatory)**: the `control` U13 integrated `cp` MUST lie
   within 15 % of the converged baseline `cp = −0.0411`, i.e. in
   `[−0.0473, −0.0349]`, before any other variant is interpreted
   (`DIAGNOSIS-2026-09-21.md:120-121`). The bound covers the observed ≈ 11 %
   short-window spread (proxy `cp ≈ −0.0459` versus converged `−0.0411`). A miss
   fails the harness loudly and stops interpretation.
2. **Primary signal**: integrated turbine `cp`/`ct`/torque over the short window
   (`comparePhaseVI.py::turbine_metrics`, `:395-420`). At U13 augmentation-on
   MUST make `cp`/`ct` positive; at U7 the augmentation-on + root-off ablation
   MUST shrink the −16 % power/torque deficit toward or inside the ±15 % band
   (`comparePhaseVI.py:67-69`).
3. **Secondary signal**: the spanwise `c_ref_t` **sign** at 30/47/63/80/95 %
   span (`comparePhaseVI.py:66,290-305`). At U13 augmentation-on MUST make
   mid-span `c_ref_t ≥ +0.02` at the U13 midspan station — positive with a
   margin above the `DRIFT_TOLERANCE = 0.01` short-window drift
   (`comparePhaseVI.py:71`), versus the control's `−0.063`. The ≈2× magnitude
   mismatch versus measured CT is a documented caveat, not a target.
4. **Fail-loud**: any unmet criterion makes the harness exit non-zero with the
   offending variant/metric named (spec "Fail-loud success criteria").

### 7.4 Prepared-only production boundary

No automated step of this change submits, cancels or modifies a production job
(spec `phasevi-proxy-verification`, "Prepared-only production boundary"). The
suspended production arrays (`DIAGNOSIS-2026-09-21.md:3-6`) remain read-only
baselines. The production campaign stays prepared-only and requires explicit HPC
authorization (open question 1).

---

## 8. Test Design

C++ has no unit framework in this repository; the C++ path is verified through
solver-driven integration tests plus pure-Python expected-value checks, exactly
as S1/S2 did. New solver-driven modules are added to `SOLVER_DRIVEN`
(`tests/conftest.py:17-26`) so they skip cleanly without OpenFOAM.

### 8.1 W1 — Du–Selig correction and radial geometry

| Artifact | Kind | What it verifies |
|---|---|---|
| `tests/test_rotational_augmentation.py::test_du_selig_reference_values` | Pure Python | A Python re-implementation of Eqs. 9–12 (prefactor form) reproduces the hand-computed U13 sample (`fL ≈ 0.34`, `CL,3D ≈ 1.45–1.53`) and the near-tip `fL → −1/(2π)` limit; the C++ constants and exponents are asserted by a source/rendered-dict check so the Python reference cannot silently drift, and the split form is forbidden by the source pin |
| `tests/rotationalAugmentation/` (new case dir, mirroring `tests/bladeSurface/`) | Case fixture | A minimal standalone `actuatorLineSource` with an S809 profile, a `rotationalAugmentation { active on; }` block and injected `radius`/`rotorRadius`; a `writeElementPerf true` element CSV and a `forceIntegral` functionObject |
| `tests/test_rotational_augmentation.py::test_correction_applied` | Integration (solver-driven) | With the block on, the element CSV `cl`/`cd` differ from the static polar at the same `alpha_deg` in the direction of Eqs. 9–10; with the block off the CSV is byte-identical to the pre-change chain |
| `::test_pre_stall_unchanged` | Integration | At an α below stall where `CL,2D ≈ CL,p`, `CL,3D ≈ CL,2D` (spec "Pre-stall lift unchanged") |
| `::test_absent_keys_keep_old_dict` | Integration | An element dict without `radius`/`rotorRadius` constructs and runs as before; an active block without geometry warns and skips the correction (no abort) |
| `::test_unknown_model_rejected` | Integration | `model notRegistered;` fails loudly (`FatalIOError`), not silently |
| `::test_all_models_inherit` | Integration | The same augmentation-on configuration run as `elementType actuatorLineElement` and `elementType actuatorSurfaceElement` (and, where the fixture supports it, the mesh surface) shows the correction through the shared chain with no per-model code (spec `actuator-surface-element`) |
| `::test_parallel_restart_invariance` | Integration | `mpirun -np 2` produces the same corrected CSV rows as serial; a restart from a written time reproduces the same scalars (no new restart state) |
| Regression gates | Existing suite | `test_al`, `test_asm`, `test_aftal`, `test_aftal_asm`, `test_blade_surface`, `test_libs` pass unchanged; default-off output byte-identical; `./Allwmake` exits 0; `ldd -r` clean |

Commands: `cd turbinesFoam && ./Allwmake && ldd -r $FOAM_USER_LIBBIN/libturbinesFoam.so`;
`cd turbinesFoam && pytest -q tests/test_rotational_augmentation.py tests/test_al.py tests/test_asm.py tests/test_aftal.py tests/test_aftal_asm.py tests/test_blade_surface.py tests/test_libs.py`.

### 8.2 W2 — Leishman–Beddoes guard

| Artifact | Kind | What it verifies |
|---|---|---|
| `tests/test_leishman_beddoes_guard.py::test_well_conditioned_matches_solve` | Pure Python (reference) | The analytic 2×2 solve returns the same K1/K2 as the unguarded solve on a well-conditioned matrix within round-off |
| `::test_singular_matrix_falls_back` | Pure Python (reference) | A singular/dependent matrix yields `K1 = K2 = 0` and the documented warning path, with no `Singular Matrix` abort |
| `tests/leishmanBeddoes/` (new case dir) | Case fixture | A case with `dynamicStall { active on; dynamicStallModel LeishmanBeddoes; }` and `LeishmanBeddoesCoeffs { speedOfSound 343; }` (precedent: `tutorials/actuatorLine/pitching/system/fvOptions:40-58`) |
| `tests/test_leishman_beddoes_guard.py::test_guard_run_passes_crash_point` | Integration (solver-driven) | The run passes `t = 0.008 s` without `FOAM FATAL ERROR: Singular Matrix`; the fallback/fit path and the determinant are recorded (spec "Guarded run passes the former crash point") |
| Regression gates | Existing suite | The other dynamic-stall models are untouched; `test_al`/`test_asm` unchanged |

Commands: `cd turbinesFoam && ./Allwmake`;
`cd turbinesFoam && pytest -q tests/test_leishman_beddoes_guard.py tests/test_al.py tests/test_asm.py`.

### 8.3 W3 — Phase VI config/render

| Artifact | Kind | What it verifies |
|---|---|---|
| `tests/test_phasevi_case.py::test_twins_differ_only_in_blade_keys` (extended) | Pure Python | Three twins; after stripping `BLADE_KEYS` (`:63-66`) the renders and the committed files are identical; the `rotationalAugmentation` block is present and identical in all three |
| `::test_rotational_augmentation_rendered` | Pure Python | `--rotational-augmentation on` renders the block with `active on`, `model DuSelig`, `a/b/d 1`; the committed default renders `active off` |
| `::test_root_effect_ablation_rendered` | Pure Python | `--root-effects off` renders `rootEffects off` while the committed default keeps `on` |
| `::test_generated_case_is_current` | Pure Python | Committed `case/system/fvOptions.{ALM,ASM,ASM-MESH}` match the renderer |
| `::test_config_schema` (extended) | Pure Python | `actuator.rotational_augmentation` exists with the paper defaults and `end_effects.root` is a boolean |

Commands: `cd turbinesFoam && pytest -q tests/test_phasevi_case.py`;
`python3 validation/phaseVI/tools/generate_case.py --check`;
`scripts/runPhaseVI.sh -m alm -u 13` (prepares only; no `--run`/`--submit`).

### 8.4 W4 — proxy harness

| Artifact | Kind | What it verifies |
|---|---|---|
| `tests/test_phasevi_proxy.py::test_variant_matrix` | Pure Python | The harness renders exactly the three variants, differing only in the augmentation switch and the root setting; the diff assertion is explicit |
| `::test_check_mode_no_submit` | Pure Python | `--check`/`--dry-run` reports the 7/13 m/s D/32 0.25-rev configuration and submits nothing (no `sbatch` call) |
| `::test_serial_chain` | Pure Python | The variants are chained serially (`MaxSubmit=1`), not submitted as an array |
| `::test_fail_loud` | Pure Python | A synthetic control `cp` outside tolerance makes the harness exit non-zero and name the control gate |
| `::test_no_production_submission` | Pure Python | No code path invokes `sbatch` against a production queue; the suspended arrays are not referenced |
| `validation/phaseVI/README.md` + root `CHANGELOG.md` | Review | Docs state the matrix, the criteria, the caveat and the prepared-only boundary; the changelog follows the repository format |

Commands: `cd turbinesFoam && pytest -q tests/test_phasevi_proxy.py`;
`python3 validation/phaseVI/scripts/proxyRotationalAugmentation.py --check`.

### 8.5 Cross-unit gates

- **Build gate**: `cd turbinesFoam && ./Allwmake` exits 0; `ldd -r` clean.
- **Default-off byte-identical**: no `rotationalAugmentation` block → no
  correction, no injected keys; existing element/line/turbine CSVs are the
  baseline (spec "Default-off byte-identical output").
- **Full-suite regression**: `cd turbinesFoam && pytest -q` passes; solver-driven
  modules auto-skip without OpenFOAM (`conftest.py:28-36`).
- **Guard gate**: `dynamicStall` + `LeishmanBeddoesCoeffs` passes `t = 0.008 s`.
- **Proxy gate**: the control `cp` is within 15 % of the converged baseline
  `−0.0411` at U13 before any variant is interpreted; no production job is
  submitted.

---

## 9. Work Units (delivery forecast)

Line counts are change totals (additions + deletions). Each unit ends with its
own tests and docs, has a single reviewable purpose, and reverts cleanly on its
own.

### W1 — Du–Selig correction in the shared chain (C++)

| Field | Value |
|---|---|
| Deliverable | `rotationalAugmentation` block read (default off), `correctRotationalAugmentation()`, hook in `calculateForce`, `radius`/`rotorRadius` injection in `createElements`, AFTAL forwarding, C++ integration tests + pure-Python expected-value test, turbinesFoam README |
| Files | `src/fvOptions/actuatorLineSource/actuatorLineElement/actuatorLineElement.{H,C}`, `src/fvOptions/actuatorLineSource/actuatorLineSource.C`, `src/fvOptions/axialFlowTurbineALSource/axialFlowTurbineALSource.C`, `tests/conftest.py`, `tests/test_rotational_augmentation.py` (new), `tests/rotationalAugmentation/**` (new), `turbinesFoam/README.md` |
| Est. lines | ~300–500 |
| Focused verification | `./Allwmake`; `ldd -r`; `pytest -q tests/test_rotational_augmentation.py tests/test_al.py tests/test_asm.py tests/test_aftal.py tests/test_aftal_asm.py tests/test_blade_surface.py tests/test_libs.py`; default-off byte-compare; hand-computed Eqs. 9–12 sample check; `mpirun -np 2` invariance |
| Rollback | `git revert` W1: removes the correction and the geometry keys; default paths byte-identical. Configuration rollback = delete the `rotationalAugmentation` block. |
| Boundary | Ends before the LB guard and any Phase VI change. No observable default-path change. |

### W2 — Leishman–Beddoes singularity guard

| Field | Value |
|---|---|
| Deliverable | Determinant guard / analytic 2×2 solve at `LeishmanBeddoes.C:321`, documented fallback, warning + record, guard test |
| Files | `src/fvOptions/actuatorLineSource/actuatorLineElement/dynamicStallModels/LeishmanBeddoes/LeishmanBeddoes.C`, `tests/test_leishman_beddoes_guard.py` (new), `tests/leishmanBeddoes/**` (new) |
| Est. lines | ~60–120 |
| Focused verification | `./Allwmake`; `pytest -q tests/test_leishman_beddoes_guard.py tests/test_al.py tests/test_asm.py`; enable `dynamicStall` + `LeishmanBeddoesCoeffs` and confirm the run passes `t = 0.008 s`; fallback recorded |
| Rollback | `git revert` W2: LB reverts to `solve()`; other dynamic-stall models untouched |
| Boundary | One method; no fit retuning. |

### W3 — Phase VI config/render

| Field | Value |
|---|---|
| Deliverable | `rotationalAugmentation` on-switch + `rootEffects` ablation in `case.yaml`, `generate_case.py` render path and CLI, case tests, docs |
| Files | `validation/phaseVI/config/case.yaml`, `validation/phaseVI/tools/generate_case.py`, `validation/phaseVI/case/system/fvOptions.{ALM,ASM,ASM-MESH}`, `tests/test_phasevi_case.py`, `validation/phaseVI/README.md` |
| Est. lines | ~250–450 |
| Focused verification | `pytest -q tests/test_phasevi_case.py`; `generate_case.py --check`; `runPhaseVI.sh -m alm -u 13` prepares without `--run`/`--submit`; twins differ only in `BLADE_KEYS` |
| Rollback | `git revert` W3: removes the switch/ablation; ALM/ASM twins unchanged |
| Boundary | Committed default stays `active off`, `root on`. |

### W4 — Proxy verification harness

| Field | Value |
|---|---|
| Deliverable | Committed 0.25-rev D/32 harness (7/13 m/s, serial dev queue), variant matrix, control gate and fail-loud criteria, comparison caveat, proxy tests, README/CHANGELOG |
| Files | `validation/phaseVI/scripts/proxyRotationalAugmentation.py` (new), `validation/phaseVI/scripts/proxyRotationalAugmentation.sh` (new), `tests/test_phasevi_proxy.py` (new), `validation/phaseVI/README.md`, root `README.md`, `CHANGELOG.md` |
| Est. lines | ~200–400 |
| Focused verification | `pytest -q tests/test_phasevi_proxy.py`; harness `--check`/dry-run; docs updated; **no submission** |
| Rollback | `git revert` W4: removes the harness/docs; W1–W3 unaffected |
| Boundary | Prepared-only; no production submission, cancellation or modification. |

### Delivery shape

The session strategy is `single-pr`; the forecast (~810–1470 lines) exceeds the
400-line budget, so under `single-pr` **apply requires an explicit
`size:exception` before it starts** (S1/S2 precedent). The W1→W2→W3→W4 chain is
prepared as the alternative: every unit is independently testable, independently
revertable, and W2/W3/W4 do not change W1 semantics.

```
Decision needed before apply: Yes
Chained PRs recommended: Yes
400-line budget risk: High
```

---

## 10. Threat Matrix

N/A — the change introduces no routing, shell-command, VCS/PR-automation, or
executable-file-classification boundary. The subprocess surfaces are the same
class S1/S2 assessed: `runPhaseVI.sh` invoking `generate_case.py`, `mesh.sh` and
`mpirun` on committed inputs (and refusing `--submit` for `-m asm-mesh`,
`:137-142`); the new proxy harness invoking the same committed preparation path
and an authorized dev-queue scheduler only under explicit invocation; and the
production arrays, which are **prepared-only** and never launched by this change.
None of these is an autonomous path with adversarial inputs, so the matrix's
boundaries (documentation-like paths, git repository selection, commit state,
push state, PR commands) do not apply and no rows are marked applicable. The
comparison tooling remains a local, human-invoked script.

## 11. Migration / Rollout

No data migration or schema changes to existing artifacts. The change is opt-in
and additive:

- **Configuration**: without the `rotationalAugmentation` block, the correction
  is skipped, no `radius`/`rotorRadius` keys are injected, and every existing
  case is byte-identical. Rollback from an adopting case = delete the block (no
  recompile).
- **Code**: `git revert` per work unit (§9); the LB guard reverts independently.
- **Data**: the Phase VI case changes revert with W3; the proxy harness is a
  local tool and reverts with W4. No committed polar or STL changes.
- **Rollout gates**: `./Allwmake` exit 0 + `ldd -r` clean; full pytest suite
  unchanged; `generate_case.py --check` clean for the committed case; the proxy
  control reproduces `cp ≈ −0.0459` before variant interpretation.
- **HPC**: the proxy runs only on the authorized dev queue; the production
  campaign stays prepared-only and requires explicit authorization. The suspended
  arrays (`DIAGNOSIS-2026-09-21.md:3-6`) are read-only baselines.

## 12. Risks and Open Items

**Risks**

1. **Du–Selig interacts with dynamic stall (high)**: the LB model refits on the
   static polar (`LeishmanBeddoes.C:308-311`) while receiving the augmented
   coefficients. Mitigated by the hook order (augmentation first), the guard test
   exercising the path, and by not enabling LB in the primary fix; the combined
   model is not claimed validated.
2. **Near-tip `fL < 0` reduces tip lift (medium-high)**: a published-model
   characteristic. Mitigated by implementing Eqs. 9–12 literally with no
   invented clamp, recording the behaviour in the sensitivity note, and noting
   that the end-effect factor is applied after the hook (`:862`).
3. **Geometry plumbing changes the parallel/restart path (medium-high)**:
   mitigated by pure per-element construction-time scalars, `lookupOrDefault`
   sentinels, the default-off byte-identical gate and the MPI/restart test.
4. **No free-parameter calibration (medium-high)**: `a=b=d=1` only; the
   sensitivity note records no tuning and the tip behaviour.
5. **End-effect confound (medium)**: root stays on in the primary fix; root-off
   is a separate ablation variant.
6. **`c_ref_t` ≈2× mismatch unresolved (medium)**: documented caveat; integrated
   metrics are the primary signal.
7. **LB guard masks a deeper fit-input defect (medium)**: the guard is minimal
   and records the fallback; the fit-input review is an explicit follow-up.
8. **HPC authorization (medium)**: proxy only on the authorized dev queue;
   production prepared-only.
9. **Review budget (blocking)**: `size:exception` or the chained W1→W4 units must
   be resolved before apply.

**Open items (task-level verification)**

- Confirm the C++ constant/exponent values match the design table on the real
  build (the pure-Python reference test pins the expected values; the C++ check
  must not drift).
- Confirm `radius`/`rotorRadius` injection on a running Phase VI ALM/ASM run:
  the element's `r` equals `comparePhaseVI.py`'s `r/R` mapping at the five
  stations.
- Confirm the LB guard passes the former crash point on the real S809 polar and
  records the fallback path (W2).
- Confirm the proxy harness renders self-contained copies and chains serially on
  the dev queue (`MaxSubmit=1`) without submitting production.

## 13. File Changes

| File | Action | Description |
|------|--------|-------------|
| `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/actuatorLineElement.{H,C}` | Modify | `rotationalAugmentation` block read (default off), `radius_`/`rotorRadius_`/constants members, `correctRotationalAugmentation()`, hook in `calculateForce` after `:819` |
| `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineSource.C` | Modify | `createElements` (`:316-378`) injects `radius`/`rotorRadius` from `rootDistance` and the forwarded radii |
| `turbinesFoam/src/fvOptions/axialFlowTurbineALSource/axialFlowTurbineALSource.C` | Modify | Forward `rotationalAugmentation`, `rotorRadius`, `rootRadius` into each blade subdict (`:314-328`) |
| `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/profileData/profileData.{H,C}` | Unchanged | `zeroLiftAngleOfAttack()`/`zeroLiftDragCoeff()` already exist (`:879-886`, `:869-876`); no new table |
| `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/dynamicStallModels/LeishmanBeddoes/LeishmanBeddoes.C` | Modify | Determinant guard / analytic 2×2 solve with fallback at `:321` |
| `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/actuatorSurfaceElement.{H,C}`, `src/fvOptions/bladeSurface/bladeSurfaceSource.C` | Untouched | Inherit the correction through the shared chain; regression-gated |
| `turbinesFoam/src/Make/files` | Unchanged | No new `.C` file for W1 |
| `turbinesFoam/validation/phaseVI/config/case.yaml` | Modify | `actuator.rotational_augmentation` (default off); `end_effects.root` used for the ablation |
| `turbinesFoam/validation/phaseVI/tools/generate_case.py` | Modify | Render `rotationalAugmentation` into all three twins; `--rotational-augmentation`/`--root-effects` |
| `turbinesFoam/validation/phaseVI/case/system/fvOptions.{ALM,ASM,ASM-MESH}` | Modify | Committed default render (augmentation off, root on) |
| `turbinesFoam/validation/phaseVI/scripts/proxyRotationalAugmentation.{py,sh}` | Create | Committed 0.25-rev D/32 proxy harness (W4) |
| `turbinesFoam/tests/test_rotational_augmentation.py`, `tests/rotationalAugmentation/**` | Create | W1 integration + expected-value coverage |
| `turbinesFoam/tests/test_leishman_beddoes_guard.py`, `tests/leishmanBeddoes/**` | Create | W2 guard coverage |
| `turbinesFoam/tests/test_phasevi_proxy.py` | Create | W4 harness coverage |
| `turbinesFoam/tests/conftest.py` | Modify | Register the new solver-driven modules in `SOLVER_DRIVEN` |
| `turbinesFoam/tests/test_phasevi_case.py` | Modify | Augmentation/root render and twin contracts |
| `turbinesFoam/README.md`, root `README.md`, root `CHANGELOG.md` | Modify | Formulation, constants, sensitivity note, comparison caveat, changelog entries |
| `precice-openfoam-adapter/**`, `fsiOmega/**`, `solidBodyDisplacementLaplacianZone/**`, `dynamicOversetZoneDisplacementFvMesh/**` | Untouched | Out of scope |

## 14. Open Questions

1. **`c_ref_t` definitional fix**: a dedicated follow-up change (comparison
   definition and/or angle reference) or accept the documented caveat
   indefinitely? Engineering recommendation: dedicated follow-up (proposal open
   question 2).
2. **Campaign authorization and timing**: when (and whether) to run the full
   production campaign is a user/HPC decision, not implied by this change
   (proposal open question 1).
3. **LB fit-input review**: reviewing the K1/K2 fit inputs (`cm` data,
   `cmFitExponent_`) is a separate change; the guard only makes the path runnable
   (proposal open question 5).
4. **Shen tip-loss ablation**: run the paper's full Du–Selig → Shen chain as an
   extra proxy variant, or keep `Glauert` to isolate the augmentation?
   Engineering recommendation: keep `Glauert` in this change (proposal open
   question 4).
5. **Delivery shape before apply**: explicit `size:exception` under `single-pr`
   vs the prepared chained units W1→W4 — user decision required before
   `sdd-apply` (proposal open question 3).
6. **Root-effect policy long term**: whether the committed default root setting
   should change after the proxy ablation is a follow-up decision, not part of
   this change.


