# Exploration: Rotational augmentation of the shared blade-load chain

Change: `rotational-augmentation` — project: `of-plugins` — date: 2026-09-23
Scope: `turbinesFoam/` (shared element load chain, end effects, dynamic stall,
Phase VI comparison/runner).
Reference: Yang & Sotiropoulos, arXiv:1702.02108v4 (2018), local text copy at
`/scratch/leahk/eduardo.donestevez/simulations/tmp/mexico_research/yang_arxiv_1702.02108.txt`.
Primary evidence: `turbinesFoam/validation/phaseVI/results/DIAGNOSIS-2026-09-21.md`
(read in full). This change is **orthogonal to the archived S2
`blade-actuator-surface`** (mesh-based surface already delivered): it targets the
**shared BEM/polar/stall/end-effect chain** that both ALM and ASM inherit.

## Current State

### 1. The shared load chain (verified)

Every element force is produced by one method,
`actuatorLineElement::calculateForce` (`actuatorLineElement.C:757-880`):

1. inflow interpolation + spanwise removal (`:780-786`), relative velocity and
   `Re` (`:789-790`);
2. effective angle of attack `angleOfAttack_` and geometric
   `angleOfAttackGeom_` (`:792-813`);
3. `profileData_.updateRe(Re_)` (`:816`) then `lookupCoefficients()`
   (`:819`) → `profileData_.liftCoefficient/dragCoefficient/momentCoefficient`
   at `angleOfAttack_` (`:238-243`);
4. dynamic-stall correction when active (`:835-845`);
5. added-mass correction when active (`:848-859`);
6. **end-effect factor**: `liftCoefficient_ *= endEffectFactor_` (`:862`);
7. force build `forceVector_ = lift*liftDirection + drag*dragDirection`
   (`:865-872`).

The per-element CSV coefficients are the public reference definitions:
`tangentialRefCoefficient()` = `convertToCRT(cl, cd, inflowRefAngle())` =
`cl·sinφ − cd·cosφ` (`:703-711`; `profileData.C:492-501`) and
`normalRefCoefficient()` = `cl·cosφ + cd·sinφ` (`:721-729`;
`profileData.C:504-513`), written as `c_ref_t,c_ref_n` (`:527-529,539-547`).
Both are evaluated **after** step 6, so they already include the end-effect
factor and any dynamic-stall/added-mass correction.

`actuatorSurfaceElement` is an `actuatorLineElement` subclass that overrides
only `calcProjectionEpsilon`, `applyForceField` and `calculateInflowVelocity`
(`actuatorSurfaceElement.H:59-110`; `.C:103,154`). It does **not** override
`calculateForce`/`lookupCoefficients`, so ASM inherits the whole chain. The
mesh-backed `bladeSurfaceSource` consumes `element.force()`
(`actuatorLineElement.C:1063`; callers in `bladeSurfaceSource.C`). **Consequence:
a correction placed inside `calculateForce` (or `lookupCoefficients`) reaches
ALM, ASM and the mesh surface at once** — exactly the "both inherit it"
requirement.

### 2. What the element already exposes, and what augmentation needs (verified)

`profileData` exposes the Du–Selig inputs: `zeroLiftAngleOfAttack()`
(`profileData.C:879-886`), `zeroLiftDragCoeff()` (`:869-876`),
`staticStallAngleRad()` (`:859-866`), `normalCoeffSlope()` (`:899-906`), plus
`liftCoefficient/dragCoefficient/momentCoefficient` lookups (`:596-626`) and
the conversion helpers `convertToCN/CC/CL/CD/CRT/CRN` (`:444-513`). The element
exposes `angleOfAttack()`, `chordLength()`, `rootDistance()`, `position()`,
`omega` (flow-curvature member) and `freeStreamVelocity_` (`actuatorLineElement.H:301-377`).

The Du–Selig formulation needs **`c/r` and `Λ = ΩR/√(U²+(ΩR)²)`**, i.e. the
actual local radius `r` and rotor radius `R`. The element dict currently carries
`position`, `chordLength`, `spanLength`, `rootDistance` (`actuatorLineSource.C:314-329`)
— **no `radius`/`rotorRadius`**. `rootDistance_ = mag(position − rootLocation)/totalLength_`
(`actuatorLineSource.C:314`) is normalised 0 at the root cutout, 1 at the tip,
and the comparison recovers `r/R = ROOT_CUTOUT_RADIUS/R + rootDist·(1 − ROOT_CUTOUT_RADIUS/R)`
(`comparePhaseVI.py:280-287`). So `c/r` is derivable only if the element (or its
dict) is given `R` (and the root cutout), or the source passes `c/r` directly.
This is a concrete interface addition, not free data.

### 3. Du–Selig in the paper (verified)

The paper states (lines 210-214) that blade rotation causes stall delay inboard
and uses Du & Selig to correct 2D coefficients:

- `CL,3D = CL,2D + fL·(CL,p − CL,2D)` — Eq. 9, line 215;
- `CD,3D = CD,2D − fD·(CD,2D − CD,0)` — Eq. 10, line 218;
- `CL,p = 2π(α − α0)`, `CD,0` = 2D drag at zero angle of attack — line 220;
- `fL` — Eq. 11, lines 221-237; `fD` — Eq. 12, lines 239-255. The PDF text
  extraction splits each fraction across lines (the `1.6(c/r)a − (c/r)`,
  `d·ΛR/r` and `0.1267b + (c/r)` pieces are visible), so the exact algebra
  **must be taken from the source PDF, not the text dump**; Eq. 12 differs from
  Eq. 11 by a factor 2 in the `ΛR/r` term;
- `Λ = ΩR/√(U²+(ΩR)²)`, `a=b=d=1` as in Du & Selig — lines 257-260.

The paper then applies the Shen tip-loss correction (`CL = F1·CL,3D`,
`CD = F1·CD,3D`, Eqs. 13-16, lines 261-285) with `g = exp(−c1(B·TSR − c2)) + c3`,
`c1=0.125, c2=21, c3=0.1`. **That Shen tip-loss is already implemented** as the
`Shen` end-effect model: `g = exp(−c1·(nBlades·TSR − c2)) + 0.1`
(`axialFlowTurbineALSource.C:634-658`), `F = 2/π·acos(exp(−g·B/2·(1/rootDist−1)/sinφ))`
(`:641-648`). So the paper's chain is Du–Selig → Shen; turbinesFoam has the Shen
half and is **missing only Du–Selig**. The production config uses the alternative
`Glauert` model instead (`case.yaml:200-208`; `axialFlowTurbineALSource.C:614-633`).

### 4. End effects: the measured haircut and the 22/09 root result (verified)

`axialFlowTurbineALSource::calcEndEffects` computes `f` per element
(`axialFlowTurbineALSource.C:608-665`): Glauert tip factor (`:616-623`), Glauert
root factor (`:624-632`), Shen variants (`:634-658`), then
`setEndEffectFactor(f)` (`:663`). Production sets `tipEffects on` **and**
`rootEffects on` (`case.yaml:201-205`; `fvOptions.ALM:41-50`). The diagnosis
records `F ≈ 0.79–0.82` across mid-span, with `F_root ≈ 0.87` at r/R 0.44 for
φ≈30° (DIAGNOSIS lines 64-68) — a ~20 % lift haircut. The 22/09 diagnostic
`rootEffects off` raised midspan `cl` by ~17 % (0.598→0.700), moved
`c_ref_t` from −0.063 to ≈0.00 at U13, and recovered +7.6 % at U7, but **did not
flip the sign** (DIAGNOSIS lines 118-127; raw rows in
`$SCRATCH/tmp/phasevi-diag/summary/`). So root-effect removal is necessary but
insufficient; it is not the primary fix.

### 5. Dynamic stall: Leishman–Beddoes is not usable as configured (verified)

`LeishmanBeddoes::calcK1K2` builds a 2×2 normal-equation matrix from
`Σ(1−f)²`, `Σ sin(π f^m)`, `Σ sin(π f^m)(1−f)`, `Σ sin²(π f^m)`
(`LeishmanBeddoes.C:313-320`) and calls `simpleMatrix<scalar> A(2).solve()`
(`:321`). For this S809 polar/`cmFitExponent_` set (default `2`, `:527`) the
system is linearly dependent; OpenFOAM's `simpleMatrix::solve()` has no
singularity guard and aborts with `FOAM FATAL ERROR: Singular Matrix`. Both 22/09
LB variants crashed at `t=0.008 s` (DIAGNOSIS lines 114-115,128-136; status
files `u13-lb.status`/`u13-lb-noroot.status` = `SOLVER-FAIL rc=1`). The coeffs
block needed to enable the model exists as precedent in
`tutorials/actuatorLine/pitching/system/fvOptions:40-58`
(`LeishmanBeddoesCoeffs { speedOfSound 343; }`). A fix is either a determinant
guard with a defined fallback (e.g. `K1=K2=0` or a regularised fit) or an
analytic 2×2 solve; `calcK1K2` is the **only** `.solve()` in the dynamic-stall
models (grep), so the blast radius is one method.

### 6. Comparison definition: the flagged c_ref_t mismatch (verified)

`comparePhaseVI.py` compares element `c_ref_t` directly against measured CT and
`c_ref_n` against measured CN at 30/47/63/80/95 % span
(`comparePhaseVI.py:66,290-305,569-610`; bands max(0.15, 20 %), `:67-69`;
sign gate `:243-259`). Turbine metrics are F1-fixed: `Q = ct·q_dyn·R`,
`P = cp·q_dyn·U∞`, `T_blade = Σ cd_blade·q_dyn` (`:395-420`; spec
`phasevi-run-and-compare/spec.md:199-227`).

At U7 the simulated `c_ref_t` is ≈0.24 at 0.47–0.63 span against measured
CT 0.118/0.096 (**≈2×**), while the integrated torque is **−16 %** low
(`results/U7-coarse-H/spanwise_comparison.csv`, `turbine_comparison.csv`). At
U13 the measured CT itself is near zero/negative at 0.47 (DIAGNOSIS lines 33-38).
So the spanwise tangential comparison is internally inconsistent with the
integrated torque and must be re-checked before it can carry any claim. Candidate
causes (not yet decided): the angle reference (`inflowRefAngle()` is measured
from `chordRefDirection_`, `actuatorLineElement.C:739-748`, not from the rotor
plane) and the dynamic-pressure/normalisation reference used for the WDH
`CN/CT` columns (`data/experiment/PROVENANCE.md:14,45`). The measured data are
the WDH workbook `CN30..CT95` columns; the report's exact coefficient
normalisation is not recorded in the provenance file.

### 7. Polar extension is a static extension (verified)

`profileData::interpolate` linearly interpolates and extrapolates at the table
ends (`profileData.C:33-94`). The OSU table beyond the measured range is a
documented static extension: "Rows with |alpha| beyond the measured OSU range are
a STATIC EXTENSION from CSU Table A-3 … plus a flat-plate closure"
(`data/polars/S809_OSU_Re1M_total.dat` header). This is reasonable but cannot
represent rotation-corrected deep-stall lift; it is the object the augmentation
must act on.

### 8. Cheap verification loop (verified)

The 22/09 method is a valid proxy: pre-rendered **0.25-rev D/32** case,
**7 and 13 m/s**, **48 ranks**, `sequana_cpu_dev`, each variant ≈5–8 min
(`$SCRATCH/tmp/phasevi-diag/diag.slurm:1-6,17-24`; `run_all.sh` chains jobs
serially because the dev queue has `MaxSubmit=1`). The 0.25-rev control
reproduced the converged U13 failure quantitatively (`cp −0.0459` vs `−0.0411`
averaged; DIAGNOSIS lines 120-121), so the short run is a valid regression
signal. Harness bands: power/torque/thrust ±15 %, spanwise max(15 %, 20 %)
(`comparePhaseVI.py:67-69`; spec `:279-294`).

## Affected Areas

- `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/actuatorLineElement.{H,C}`
  — the augmentation hook in `calculateForce`/`lookupCoefficients`, the new
  config read, and (if chosen) passing `radius`/`rotorRadius` through the dict.
- `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/profileData/profileData.{H,C}`
  — exposes `α0`, `CD,0`; possibly a helper for the separated-lift slope. No new
  table needed.
- `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineSource.C`
  — `createElements` dict population (`:314-329`) to pass the radial geometry.
- `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/actuatorSurfaceElement.{H,C}`
  — inherits the correction unchanged (no edit expected, regression-gated).
- `turbinesFoam/src/fvOptions/bladeSurface/bladeSurfaceSource.C` — consumes
  `element.force()`; inherits the correction (no edit expected).
- `turbinesFoam/src/fvOptions/axialFlowTurbineALSource/axialFlowTurbineALSource.{H,C}`
  — end-effect policy (`:608-665`) and the `rotorRadius` source for the dict.
- `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/dynamicStallModels/LeishmanBeddoes/LeishmanBeddoes.C`
  — determinant guard / analytic 2×2 solve at `:321` (if in scope).
- `turbinesFoam/src/Make/files` — register any new `.C`
  (`:9-14` lists the dynamic-stall models).
- `turbinesFoam/validation/phaseVI/config/case.yaml` (`:200-208`) +
  `tools/generate_case.py` (`:531-570`) — render the new switch and any
  root-effect policy change into `fvOptions.{ALM,ASM}`.
- `turbinesFoam/validation/phaseVI/scripts/comparePhaseVI.py` — if the
  `c_ref_t`/CT definition is corrected, update the documented definition and the
  pre-registered hypothesis (`spec.md:199-227,279-294`).
- `turbinesFoam/validation/phaseVI/README.md`, root `CHANGELOG.md` — document
  the model, the constants, the end-effect policy and the comparison caveat.

## Approaches

### 1. Augmentation formulation and where it enters

**A. Du–Selig applied inside `calculateForce`, after `lookupCoefficients()`,
before the dynamic-stall call (recommended).** Correct `liftCoefficient_` and
`dragCoefficient_` in place (Eqs. 9-10), so dynamic stall, added mass, the
end-effect factor and the CSV all see the corrected coefficients; ALM/ASM/mesh
inherit it with no per-model code.
- Pros: paper-faithful order (Du–Selig then tip loss, since the end-effect
  factor is applied at `:862`); one hook; the CSV and `c_ref_*` reflect it.
- Cons: interacts with dynamic stall, which internally refits on the **static**
  polar (`LeishmanBeddoes.C:308-311`), so an LB path would need the augmentation
  order reviewed; `c/r` requires new geometry in the dict.

**B. Apply Du–Selig to the polar tables at read time (per element).** Rewrite
`liftCoefficientList_`/`dragCoefficientList_` from the table using the element's
`c/r`, `Λ`, `α0`.
- Pros: the dynamic-stall fit sees corrected data.
- Cons: `c/r` and `Λ` vary per element and per operating point (`Λ` depends on
  TSR/U), so a static table rewrite is only valid for one condition; table
  mutation also feeds `analyze()` and the LB fit. Not recommended.

**C. New correction model class in the element RTS.** A
`rotationalAugmentationModel` base with a `DuSelig` implementation, selectable
in the element/actuator dict.
- Pros: matches the dynamic-stall/added-mass architecture; easy to add other
  models later; testable in isolation.
- Cons: more files (`Make/files`, H/C, RTS) for a single formula; the current
  correction models are per-element `autoPtr` members, so it fits, but it is
  heavier than the need.

**Effort:** A Low-Medium; B Low (but physically fragile); C Medium.

### 2. Constants and the additive/backward-compatible default

- Paper constants `a=b=d=1` (line 260); expose them as `a`, `b`, `d` with those
  defaults so they can be tuned later.
- New config block, default **off**, mirroring `dynamicStall`/`endEffects`:
  `rotationalAugmentation { active off; model DuSelig; a 1; b 1; d 1; }`. Off by
  default keeps every existing run byte-comparable and makes the change
  additive; the Phase VI config can switch it on.
- Alternative: default **on** for the Phase VI case only, via `case.yaml`, so
  the generic library stays opt-in. Same net effect, different blast radius.

### 3. Root-effect policy

- Keep `rootEffects on` and add Du–Selig (fixes lift inboard, keeps the Glauert
  tip behaviour); or
- set `rootEffects off` for Phase VI to match the paper (which has only a
  tip-loss correction) and let Du–Selig supply the inboard lift; or
- bound the root factor by hub radius / apply it only below a cut-out.
The 22/09 data show root-off alone is insufficient and changes U7 by +7.6 %
(DIAGNOSIS lines 118-127), so this is a coupled decision with the augmentation
constants, not an independent fix.

### 4. Leishman–Beddoes guard: in scope vs follow-up

- **In scope (minimal):** add a determinant guard / analytic 2×2 solve at
  `LeishmanBeddoes.C:321` with a documented fallback, so the dynamic-stall path
  at least runs and can be evaluated.
- **Follow-up:** treat the LB fit-input review (`cm` data, `cmFitExponent_`) as
  a separate change; the diagnosis itself calls it "a separate, now-documented
  defect" (line 140).

### 5. c_ref_t vs measured CT scope

- **Definitional fix in `comparePhaseVI.py`** (documented reference/normalisation
  correction + updated limitation text); or
- **Element-side change** if the angle reference (`inflowRefAngle` from
  `chordRefDirection_`) is judged wrong; or
- **Out of scope** for this change, flagged as a known comparison caveat until a
  dedicated fix.

### 6. Campaign scope

- **Verified-fix only:** land the augmentation + guard, verify with the 0.25-rev
  proxy, keep the production campaign prepared-only. Consistent with the
  standing "no Slurm" constraint on this change.
- **Re-run campaign:** requires explicit HPC authorization and is a separate
  delivery; the diagnosis already records the production arrays as
  suspended/canceled (lines 3-6).

## Recommendation

**Recommended direction (to be decided in proposal/design): Approach 1A
(Du–Selig inside `calculateForce`, after `lookupCoefficients`, before dynamic
stall) with the paper constants `a=b=d=1`, exposed through a new default-off
`rotationalAugmentation` block; Approach 3 keeps `rootEffects on` in the first
slice and evaluates root-off as an ablation on the same 0.25-rev proxy;
Approach 4 is in scope as a minimal determinant guard only (the fit-input review
is a follow-up); Approach 5 is a documented comparison correction; Approach 6 is
verified-fix-only with the campaign prepared-only.** Rationale: the shared chain
is the only place that fixes ALM, ASM and the mesh surface together; the paper's
Shen half is already ported, so Du–Selig is the single missing physics term; and
a default-off switch preserves every archived behaviour while giving Phase VI an
explicit on-switch.

## Verification Strategy

- **Build gate:** `cd turbinesFoam && ./Allwmake` exits 0; run the existing
  pure-Python suite (`turbinesFoam/tests/`, adapter-independent) and the
  ALM/ASM/ASM-mesh regression tests; byte-compare default-off output against a
  pre-change run.
- **Cheap physics gate (0.25-rev proxy, prepared-only):** D/32, 48 ranks,
  7 and 13 m/s, using the 22/09 harness (`$SCRATCH/tmp/phasevi-diag/diag.slurm`)
  with variants: control, augmentation-on, augmentation-on + root-off. Success
  criteria on the same 0.25-rev window: at U13 midspan `c_ref_t` becomes clearly
  positive (not just ≈0) and `cp`/turbine `ct` turn positive; at U7 the −16 %
  power/torque deficit shrinks inside or toward the ±15 % band. The control must
  reproduce `cp ≈ −0.0459` at U13 before any variant is trusted.
- **Guard test:** enable `dynamicStall` with `LeishmanBeddoesCoeffs` and confirm
  the run passes `t = 0.008 s` without `Singular Matrix`; record `K1/K2` values
  and the fallback path taken.
- **Comparison check:** verify `c_ref_t` vs CT is self-consistent with the
  integrated torque at U7 after the definitional fix (or document the remaining
  caveat).
- **Full campaign:** only after the proxy passes and with explicit
  authorization; the ±15 % / max(15 %, 20 %) bands and the sign gate stay as the
  acceptance policy (`comparePhaseVI.py:67-69,243-259`).

## Open Questions (decisions needed; none decided here)

1. **Formulation/constants (blocking for design):** exact Du–Selig form and
   whether `a,b,d` stay 1; how `CL,p` handles `α0` (per-Re `α0` from
   `profileData` vs fixed).
2. **Geometry interface (blocking):** how `c/r` and `Λ` reach the element —
   pass `radius`+`rotorRadius` (or `chordOverRadius`) through the element dict
   from `actuatorLineSource::createElements`, or compute from `rootDistance` +
   cut-out/`R` supplied by AFTAL? Which is the least invasive and parallel-safe?
3. **Default and switch shape (blocking):** default off in the library with a
   Phase VI on-switch, or default on? New `rotationalAugmentation` block vs an
   option inside the element `profileData`/`actuator` block?
4. **Root-effect policy (non-blocking, coupled):** keep `rootEffects on`, turn
   it off, or hub-bound it, given the 22/09 result?
5. **LB guard scope (non-blocking):** minimal determinant guard in this change
   vs a separate dynamic-stall fix? If in scope, what fallback is physically
   acceptable?
6. **c_ref_t fix scope (non-blocking):** comparison-definition fix, element
   angle-reference fix, or documented caveat?
7. **Campaign scope (blocking for apply):** verified-fix-only (prepared-only
   campaign) vs re-run? HPC authorization is not implied by this change.
8. **Delivery slicing (blocking for apply):** source + config/render + tests +
   docs likely exceed the 400-line review budget; chained slices or
   `size:exception` before tasks?

## Risks

- **Interaction with dynamic stall (high):** Du–Selig before an LB correction
  that internally refits on the static polar may double-count or conflict; the
  order must be specified and, if LB is enabled, tested.
- **Geometry plumbing (medium-high):** adding `radius`/`rotorRadius` to every
  element dict touches `createElements` and the element constructor; the
  parallel/restart path must stay identical and default-off output unchanged.
- **No free parameter calibration (medium-high):** `a,b,d=1` is the paper
  default but Phase VI may need the paper's exact `c/r`/`Λ` definitions; an
  unvalidated correction can overshoot lift at low span.
- **c_ref_t comparison unresolved (medium):** if the 2× mismatch is a genuine
  definitional error, any spanwise claim built on `c_ref_t` remains untrustworthy
  regardless of the augmentation.
- **End-effect confound (medium):** root-effect removal and augmentation both
  raise inboard lift; changing both at once makes the attribution ambiguous, so
  the proxy must run them as separate variants.
- **HPC authorization (medium):** the production campaign is suspended and no
  new job may be submitted from this change; the verification loop must use the
  authorized dev queue and stay prepared-only for production.
- **Review budget (blocking):** element + profileData + source + config/render +
  compare + tests + docs will likely exceed the 400-line policy.

## Ready for Proposal

**Yes.** The code facts are verified with file:line evidence: the single shared
force chain and its exact insertion point, the Du–Selig equations and constants
from the paper, the already-ported Shen tip loss, the Glauert end-effect haircut
and the 22/09 root-off result, the Leishman–Beddoes singularity at
`LeishmanBeddoes.C:321`, the `c_ref_t`/CT comparison mismatch, the polar static
extension, and the cheap 0.25-rev verification harness. The orchestrator should
surface four decisions before/inside the proposal: **(1) the formulation and its
geometry interface** (`c/r`, `Λ`), **(2) the switch shape and default**
(additive/backward-compatible), **(3) the root-effect and LB-guard scope**, and
**(4) the campaign scope and delivery slicing** (verified-fix-only, prepared-only
campaign, review budget). This change is orthogonal to the archived S2
`blade-actuator-surface`.
