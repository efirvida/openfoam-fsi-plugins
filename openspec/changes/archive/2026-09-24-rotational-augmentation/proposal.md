# Proposal: Rotational augmentation (3D stall delay) in the shared blade-load chain

## Intent

The NREL Phase VI validation cannot support a claim in its current state
(`results/DIAGNOSIS-2026-09-21.md`): at 13–15 m/s the simulated rotor delivers
**negative** torque/power while the measurement delivers ~9.6–9.8 kW, and at
10 m/s the simulated power *decreases* with wind speed (4.98 → 4.34 kW) while
the measurement increases (5.9 → 9.8 kW). The diagnosis isolates the mechanism:
at 13 m/s mid-span the effective α ≈ 26.7° is deep stall, the **quasi-steady 2D
polar** returns cl ≈ 0.73 / cd ≈ 0.57, so `c_ref_t = cl·sinφ − cd·cosφ ≈ −0.13`
(braking); the measurement implies cl ≳ 1.2. **Rotational augmentation (3D stall
delay) is missing.** ALM and ASM agree within <1 %, so the defect is in the
**shared BEM/polar/stall/end-effect chain** that both inherit, not in the
surface-vs-line difference.

Every element force is produced by one method,
`actuatorLineElement::calculateForce` (`actuatorLineElement.C:757-880`);
`actuatorSurfaceElement` does not override it, and the mesh
`bladeSurfaceSource` consumes `element.force()`. A correction placed in that
chain therefore fixes ALM, ASM and the mesh surface **at once**. This change is
**orthogonal to the archived S2 `blade-actuator-surface`** (mesh-based surface
already delivered); it targets the physics chain underneath.

The fix must be additive: with the new switch absent, default output stays
byte-identical and the change is regression-gated. It targets the **diagnosed
failure mechanism**; a validation claim still requires the later authorized
campaign (out of scope here).

## Scope

### In Scope

- **Du–Selig rotational augmentation** in the shared chain: `CL,3D`/`CD,3D`
  (Eqs. 9–10) with `fL`/`fD` (Eqs. 11–12), applied after the static coefficient
  lookup and before the dynamic-stall correction, in place on
  `liftCoefficient_`/`dragCoefficient_`, so dynamic stall, added mass, the
  end-effect factor and the per-element CSV all see the corrected values.
- **Geometry interface**: inject `radius` and `rotorRadius` into every element
  dict from `actuatorLineSource::createElements`, sourced from the rotor radius
  AFTAL already holds; `c/r` and `Λ` are then available per element and per
  operating point.
- **Additive, default-off switch** `rotationalAugmentation { active off;
  model DuSelig; a 1; b 1; d 1; }`, mirroring `dynamicStall`/`endEffects`, with
  the paper constants only.
- **Minimal Leishman–Beddoes guard**: a determinant check / analytic 2×2 solve
  with a documented fallback at `LeishmanBeddoes.C:321`, so the optional
  dynamic-stall path runs instead of aborting.
- **Phase VI integration**: an on-switch for the validation case and the
  `rootEffects` ablation configuration, rendered through the existing YAML
  single source of truth.
- **Committed proxy verification harness**: the 0.25-rev D/32 short-run proxy
  (7 and 13 m/s, authorized dev queue) with the control / augmentation-on /
  augmentation-on + root-off variant matrix and explicit pass/fail criteria.
- **Tests + docs**: C++-driven integration tests, pure-Python case/render
  tests, the equation→code statement, the constants and sensitivity note, the
  comparison caveat, and `CHANGELOG.md` entries.

### Out of Scope

- **Production campaign**: no production Slurm submission, cancellation or
  resubmission. The campaign stays **prepared-only** and requires explicit HPC
  authorization; the suspended arrays are read-only baselines.
- **`c_ref_t` vs measured CT definitional fix**: the ≈2× mismatch at U7 is
  **not** fixed here. It is recorded as a documented comparison caveat; the
  proxy uses integrated `cp`/`ct`/torque as the primary signal and the
  `c_ref_t` **sign** as secondary. A definitional/angle-reference fix is a
  separate follow-up (open question).
- **Dynamic-stall fit-input review** (`cm` data, `cmFitExponent_`): the LB
  guard makes the path *runnable*; reviewing the K1/K2 fit inputs is a separate
  change.
- **New polar data / calibration**: no new tables, no free-parameter tuning.
  The static polar extension (`S809_OSU_Re1M_total.dat`) is documented and
  unchanged; the augmentation acts on it.
- **End-effect model change**: production stays on `Glauert`; activating the
  ported `Shen` tip-loss model is a possible later ablation, not part of the
  primary fix.
- **S3 / preCICE / adapter / `fsiOmega`**: untouched.

## Capabilities

> Contract between proposal and specs. Existing capabilities in
> `openspec/specs/`: `actuator-surface-element`, `element-type-selection`,
> `axial-flow-turbine-asm-tutorial`, `nacelle-surface-source`,
> `nacelle-validation-case`, `phasevi-data-provenance`,
> `phasevi-run-and-compare`, `phasevi-validation-case`,
> `surface-sampling-contract`, `time-derived-kinematics`,
> `turbine-geometry-pipeline`, `blade-surface-source`,
> `blade-geometry-generation`.

### New Capabilities

- `rotational-augmentation`: the Du–Selig 3D stall-delay correction in the
  shared element load chain — additive default-off block, per-element
  `radius`/`rotorRadius` inputs, `CL,3D`/`CD,3D` and `fL`/`fD` (Eqs. 9–12) with
  `a=b=d=1`, `CL,p = 2π(α−α0)`, `CD,0`, `Λ = ΩR/√(U²+(ΩR)²)`, and the ordering
  relative to dynamic stall and end effects.
- `dynamic-stall-singularity-guard`: a determinant guard (or analytic 2×2
  solve) with a documented, recorded fallback in
  `LeishmanBeddoes::calcK1K2`, so a singular normal-equation matrix no longer
  aborts the run.
- `phasevi-proxy-verification`: the committed 0.25-rev D/32 short-run proxy —
  variant matrix (control, augmentation-on, augmentation-on + root-off), the
  7/13 m/s dev-queue configuration, the fail-loud criteria, and the
  prepared-only boundary for production.

### Modified Capabilities

- `actuator-surface-element`: the "inherits the full BEM force chain unchanged"
  requirement is extended — the optional rotational augmentation is inherited
  by the surface element (and the mesh surface) with no per-model code.
- `element-type-selection`: `createElements` injects the per-element radial
  geometry keys (`radius`, `rotorRadius`) into every element dict; absent keys
  keep the current behaviour.
- `phasevi-validation-case`: the YAML single source of truth gains the
  `rotationalAugmentation` on-switch and the root-effect ablation
  configuration; the ALM/ASM twins stay identical except the element keys.

## Approach

### Decision 1 — Formulation, ordering, and geometry interface

**Chosen: Du–Selig Eqs. 9–12 with `a=b=d=1`, applied inside
`calculateForce` after `lookupCoefficients()` (`:819`) and before the
dynamic-stall correction (`:835`); geometry injected as `radius` + `rotorRadius`
per element dict from `createElements`.**

- **Equations (exact algebra taken from the PDF, not the text dump).** The
  exploration flagged that the text extraction splits the superscript
  fractions. Rendering the equation region of
  `yang_arxiv_1702.02108.pdf` (verified this session) gives:
  - Eq. 9 `CL,3D = CL,2D + fL·(CL,p − CL,2D)`;
  - Eq. 10 `CD,3D = CD,2D − fD·(CD,2D − CD,0)`;
  - Eq. 11 `fL = (1/2π)[ (1.6(c/r)^a − (c/r)^((d/Λ)(R/r))) /
    (0.1267b + (c/r)^((d/Λ)(R/r))) − 1 ]`;
  - Eq. 12 `fD = (1/2π)[ (1.6(c/r)^a − (c/r)^((d/(2Λ))(R/r))) /
    (0.1267b + (c/r)^((d/(2Λ))(R/r))) − 1 ]`;
  - `Λ = ΩR/√(U²+(ΩR)²)`, `CL,p = 2π(α−α0)`, `CD,0` = 2D drag at α = 0,
    `a=b=d=1` (lines 210–260).
  The exponent is **`(d/Λ)(R/r)`** (Eq. 11) and **`(d/(2Λ))(R/r)`** (Eq. 12);
  the text-dump reading "`d·ΛR/r`" is a layout artifact and MUST NOT be used.
  Numerically, at U13 mid-span (`c/r ≈ 0.271`, `R/r ≈ 2.27`, `Λ ≈ 0.95`) the
  formula gives `fL ≈ 0.20` → `CL,3D ≈ 1.19`, consistent with the diagnosis's
  implied `cl ≳ 1.2` — the formulation reproduces the diagnosed mechanism.
- **Ordering vs. the ported Shen tip loss.** The paper's chain is
  Du–Selig → Shen tip loss (Eqs. 13–16). Shen is **already ported**
  (`axialFlowTurbineALSource.C:634-658`) and the end-effect factor is applied
  at `:862`, *after* the proposed hook, so the paper's order is preserved by
  construction. This change does **not** switch the end-effect model;
  production stays on `Glauert`. `α0` and `CD,0` come from
  `profileData_.zeroLiftAngleOfAttack()` / `zeroLiftDragCoeff()` (per-Re).
- **Geometry interface.** `actuatorLineSource::createElements`
  (`:316-329`) currently injects `position`, `chordLength`, `spanLength`,
  `rootDistance`, etc., but **no radial geometry**. AFTAL already holds
  `rotorRadius_` (`turbineALSource.C:517`, rendered by `generate_case.py:552`)
  and forwards per-blade subdicts (`axialFlowTurbineALSource.C:314-328`, same
  seam as `dynamicStall`). AFTAL forwards `rotorRadius` and the blade root
  radius into each blade subdict; `createElements` then injects `radius` and
  `rotorRadius` into every element dict, with
  `radius = rootRadius + rootDistance·(rotorRadius − rootRadius)` — the exact
  identity behind the compare tool's `r/R` (`comparePhaseVI.py:286-287`). The
  element reads them with `lookupOrDefault` (absent → old dicts stay valid),
  and computes `c/r = chordLength_/radius`,
  `R/r = rotorRadius/radius`,
  `Λ = omega_·rotorRadius/√(|freeStreamVelocity_|² + (omega_·rotorRadius)²)`.
  All inputs are pure per-element scalars — no new restart state, MPI-safe.
- Alternatives: **(B) per-element polar-table rewrite** — rejected: `c/r` and
  `Λ` vary per element *and* per operating point (`Λ` depends on TSR/U), so a
  static rewrite is valid for one condition only and mutates the LB fit inputs.
  **(C) new RTS correction-model class** — rejected: one formula does not
  justify new files/RTS for a heavier abstraction; the hook is one method.

### Decision 2 — Switch shape and default

**Chosen: additive `rotationalAugmentation` sub-block, default off, rendered
into each blade subdict via the YAML generator and read with
`dictionary::get<>`/`lookupOrDefault`.**

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

- **Default off** keeps every existing run byte-identical and makes the change
  regression-gated; the Phase VI case switches it on explicitly. Placement
  mirrors `dynamicStall` (element/actuator dict, forwarded by AFTAL), so no new
  dictionary topology is introduced.
- Alternatives: **default on** — rejected: breaks byte-identical default output
  and the regression gate for all other cases. **Option inside `profileData`** —
  rejected: the correction is element/rotor-level (needs `radius`, `omega`),
  while `profileData` is a per-profile table shared by elements.

### Decision 3 — Root-effect and LB-guard scope

**Chosen: keep `rootEffects on` in the primary fix; run root-off as a separate
ablation. Add a minimal determinant guard at `LeishmanBeddoes.C:321`; the
fit-input review stays a follow-up.**

- **Root effect.** Production sets `tipEffects on` *and* `rootEffects on`
  (`case.yaml:201-205`); the Glauert root factor gives `F_root ≈ 0.87` at
  r/R 0.44 and a ~20 % mid-span lift haircut. The 22/09 diagnostic shows
  root-off alone is **necessary but insufficient** (+17 % cl, `c_ref_t` → ≈0
  but no sign flip at U13; +7.6 % at U7). Keeping it on in the primary fix and
  running root-off as a **separate variant** resolves the confound and keeps
  attribution clean.
- **LB guard.** `calcK1K2` builds a 2×2 normal-equation matrix
  (`LeishmanBeddoes.C:313-320`) and calls `simpleMatrix::solve()` (`:321`),
  which has no singularity guard; both 22/09 LB variants aborted at
  t = 0.008 s. Add a determinant check with a documented fallback (recommended:
  analytic 2×2 solve when well-conditioned, otherwise `K1=K2=0` with
  `WarningInFunction` and a debug record). Blast radius is one method.
- Alternatives: **root-off in the primary fix** — rejected: changes production
  physics and confounds the augmentation attribution. **Hub-bounded root
  factor** — deferred: a new model, out of scope. **Defer the LB path with the
  defect documented** — rejected: the guard is one method and cheap, and it
  unblocks the optional high-speed dynamic-stall path the design recommends
  keeping; the fit-input review remains follow-up.

### Decision 4 — Campaign scope and delivery slicing

**Chosen: verified-fix-only. The change delivers the fix plus a cheap
0.25-rev D/32 proxy at 7 and 13 m/s on the authorized dev queue; the
production campaign stays prepared-only. Delivery is `single-pr` with an
explicit `size:exception` (S1/S2 precedent).**

- **Verification.** The 22/09 method is a validated proxy: the 0.25-rev control
  reproduced the converged U13 failure quantitatively (`cp −0.0459` vs
  `−0.0411` averaged). Variants: control, augmentation-on,
  augmentation-on + root-off. Production arrays are suspended
  (`DIAGNOSIS-2026-09-21.md:3-6`) and MUST NOT be submitted.
- **Delivery.** The session strategy is `single-pr`; S2 set the recorded
  precedent that oversized work units land under an explicit `size:exception`.
  The forecast below (~810–1470 lines) exceeds the 400-line budget, so under
  `single-pr` **apply requires an explicit `size:exception` before it starts**.
  The W1→W4 chain is prepared as the alternative; each unit is independently
  testable and revertable.
- Alternatives: **re-run the campaign** — requires explicit HPC authorization,
  out of scope. **Chained PRs as the primary** — prepared as fallback.

## Work-Unit Plan

Each unit ends with its own tests and docs, has a single reviewable purpose,
and reverts cleanly on its own. Line counts are change totals (additions +
deletions).

| Unit | Deliverable | Likely PR | Est. lines | Focused verification | Rollback boundary |
|------|-------------|-----------|------------|----------------------|-------------------|
| W1 | Du–Selig in the shared chain: `rotationalAugmentation` block read (default off), correction method, hook in `calculateForce`, `radius`/`rotorRadius` injection in `createElements`, AFTAL forwarding, `profileData` accessors if needed, C++/Python tests, turbinesFoam README | PR 1 | ~300–500 | `cd turbinesFoam && ./Allwmake`; `pytest -q tests/test_al.py tests/test_asm.py tests/test_aftal.py tests/test_aftal_asm.py`; default-off byte-compare; hand-computed Eq. 9–12 sample check | `git revert` W1: removes correction + geometry keys; default paths byte-identical |
| W2 | LB singularity guard: determinant check/analytic solve at `LeishmanBeddoes.C:321`, documented fallback, debug record, test | PR 2 | ~60–120 | `./Allwmake`; enable `dynamicStall` + `LeishmanBeddoesCoeffs`; run passes t = 0.008 s; fallback recorded | `git revert` W2: LB reverts to `solve()`; other dynamic-stall models untouched |
| W3 | Phase VI config/render: `rotationalAugmentation` on-switch + root-effect ablation in `case.yaml`, `generate_case.py`, case tests, docs | PR 3 | ~250–450 | `pytest -q tests/test_phasevi_case.py`; `generate_case.py --check`; `runPhaseVI.sh -m alm -u 13` prepares without `--run`/`--submit` | `git revert` W3: removes switch/variants; ALM/ASM twins unchanged |
| W4 | Proxy verification harness + comparison caveat + README/CHANGELOG | PR 4 | ~200–400 | Proxy script dry-run/`--check`; docs updated; **no submission** | `git revert` W4: removes harness/docs; W1–W3 unaffected |

`tests/test_al.py`/`test_asm.py`/`test_phasevi_case.py` exist; design may add
a dedicated augmentation test file. C++ has no unit framework — the chain is
verified through solver-driven integration tests plus pure-Python
expected-value checks.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | W1 ~300–500 · W2 ~60–120 · W3 ~250–450 · W4 ~200–400 — **total ~810–1470** |
| 400-line budget risk | **High** |
| Chained PRs recommended | **Yes** |
| Suggested split | W1 → W2 → W3 → W4 |
| Delivery strategy | `single-pr` (session strategy — recorded, not decided here) |
| Size exception | Required before apply if `single-pr` stands (S1/S2 precedent) |

```
Decision needed before apply: Yes
Chained PRs recommended: Yes
400-line budget risk: High
```

## Validation Program

- **Variants (0.25-rev D/32 proxy, 7 and 13 m/s, authorized dev queue,
  prepared-only):** `control` (default off, root on) — must reproduce the
  converged U13 failure (`cp ≈ −0.0459`) before any variant is trusted;
  `augmentation-on` (root on); `augmentation-on + root-off` (the ablation).
  All other keys shared and unchanged.
- **Primary success signal:** integrated turbine `cp`/`ct`/torque from the
  short window, not the spanwise `c_ref_t` magnitude. At U13, augmentation-on
  must turn mid-span `c_ref_t` **clearly positive** (not just ≈0) and `cp`/`ct`
  positive. At U7, the augmentation-on + root-off ablation must shrink the
  −16 % power/torque deficit toward or inside the ±15 % band.
- **Secondary signal:** the `c_ref_t` **sign** at the spanwise stations; the
  ≈2× magnitude mismatch vs measured CT is a documented caveat, not a target.
- **Guard test:** enable `dynamicStall` with `LeishmanBeddoesCoeffs`; confirm
  the run passes `t = 0.008 s` without `Singular Matrix`; record `K1`/`K2` and
  the fallback path taken.
- **Regression gate:** `./Allwmake` exits 0; the existing pure-Python suite
  passes; default-off output is byte-identical to a pre-change run; ALM/ASM/
  ASM-mesh all reflect the correction through the single shared chain.
- **Full campaign:** only after the proxy passes and with explicit
  authorization; the ±15 % / max(15 %, 20 %) bands and the sign gate remain
  the acceptance policy (`comparePhaseVI.py:67-69,243-259`).
- **Acceptance framing:** engineering acceptance is build + tests + byte-
  identical default + guard test + proxy control reproduction. The scientific
  claim (validation passes) is **not** made by this change; it requires the
  later authorized campaign.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/actuatorLineElement.{H,C}` | Modified | `rotationalAugmentation` read (default off), correction method, hook in `calculateForce` (`:819-835`) |
| `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineSource.C` | Modified | `createElements` (`:316-329`) injects `radius`/`rotorRadius`; AFTAL forwards rotor/root radius |
| `turbinesFoam/src/fvOptions/axialFlowTurbineALSource/axialFlowTurbineALSource.{H,C}` | Modified | Forward `rotorRadius`/root radius and the `rotationalAugmentation` block into blade subdicts (`:314-328`) |
| `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/profileData/profileData.{H,C}` | Modified | Expose/confirm `α0`, `CD,0` accessors used by the correction (no new table) |
| `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/dynamicStallModels/LeishmanBeddoes/LeishmanBeddoes.C` | Modified | Determinant guard / analytic 2×2 solve with fallback at `:321` |
| `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/actuatorSurfaceElement.{H,C}`, `fvOptions/bladeSurface/bladeSurfaceSource.C` | Untouched | Inherit the correction; regression-gated |
| `turbinesFoam/src/Make/files` | Modified only if a new `.C` is added | No new file expected for W1 |
| `turbinesFoam/validation/phaseVI/config/case.yaml`, `tools/generate_case.py` | Modified | `rotationalAugmentation` on-switch + root-effect ablation rendering (`:200-210`, `:531-570`) |
| `turbinesFoam/validation/phaseVI/scripts/` | New/Modified | Committed 0.25-rev proxy harness; no production submission |
| `turbinesFoam/tests/` | New/Modified | Augmentation, guard, case/render tests |
| `turbinesFoam/README.md`, root `README.md`, root `CHANGELOG.md` | Modified | Formulation, constants, sensitivity note, comparison caveat |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Du–Selig interacts with dynamic stall (LB refits on the static polar) | High | Hook placed before the dynamic-stall call; ordering documented; LB path exercised via the guard test; primary fix does not enable LB |
| Near-tip `fL < 0` (small `c/r`) reduces tip lift — a published-model characteristic | Medium-High | Implement Eqs. 9–12 literally (paper constants only, no invented clamps); record the behaviour in the sensitivity note; tip loss is applied after by the end-effect factor |
| Geometry plumbing changes the parallel/restart path | Medium-High | Pure per-element scalars; `lookupOrDefault` so absent keys keep old dicts; default-off byte-identical gate |
| No free-parameter calibration | Medium-High | `a=b=d=1` only; sensitivity note records no tuning and the tip behaviour |
| End-effect confound (root-off vs augmentation both raise inboard lift) | Medium | Root stays on in the primary fix; root-off is a separate ablation variant |
| `c_ref_t` ≈2× mismatch unresolved | Medium | Out of scope as a code fix; documented caveat; integrated metrics are the primary signal |
| LB guard masks a deeper fit-input defect | Medium | Guard is minimal and records the fallback; fit-input review is an explicit follow-up |
| HPC authorization | Medium | Proxy only on the authorized dev queue; production prepared-only; existing arrays untouched |
| Review budget exceeded | High (blocking) | `size:exception` or chained PRs resolved before apply |

## Rollback Plan

The change is additive and opt-in; absent keys leave ALM, ASM and the mesh
surface byte-identical.

1. Remove the `rotationalAugmentation` block — the element skips the correction
   and returns to the pre-change chain without recompiling. The geometry keys
   are only consumed when the correction is active.
2. Code rollback is per work unit via `git revert`: W1 removes the correction
   and geometry injection; W2 restores the LB `solve()` path; W3 removes the
   Phase VI switch/variants; W4 removes the proxy harness and docs. No case
   schema migration is required.
3. The `rootEffects` configuration is unchanged in the primary fix, so no
   physics-policy rollback is needed; the ablation is a render-time variant.
4. Verify with `cd turbinesFoam && ./Allwmake` and `pytest`; the existing suite
   must pass unchanged and default-off output must remain byte-identical.

## Dependencies

- Loaded OpenFOAM v2506 module environment (SDumont recipe in AGENTS.md).
- No new external libraries; preCICE is not a dependency.
- The verified equation source is the local PDF
  `yang_arxiv_1702.02108.pdf` (non-committed; the exact algebra is recorded in
  the design's equation→code table).
- The committed Phase VI inputs (`S809` polars, `case.yaml`, generator) and the
  existing short-run proxy method (`$SCRATCH/tmp/phasevi-diag/`).
- HPC authorization for the proxy execution and the campaign (prepared-only
  otherwise); existing Phase VI arrays are read-only baselines.

## Open Questions

1. **Campaign authorization and timing** — when (and whether) to run the full
   production campaign is a user/HPC decision, not implied by this change.
2. **`c_ref_t` definitional fix** — separate follow-up (comparison-definition
   and/or angle-reference), or accept the documented caveat indefinitely?
   Engineering recommendation: dedicated follow-up change.
3. **Delivery** — explicit `size:exception` under `single-pr` vs the prepared
   W1→W4 chained PRs; user decision required before apply.
4. **Shen tip-loss ablation** — should the paper's full Du–Selig → Shen chain
   be run as an extra proxy variant, or keep `Glauert` to isolate the
   augmentation? Engineering recommendation: keep `Glauert` in this change.
5. **LB fallback choice** — analytic 2×2 solve when well-conditioned vs always
   `K1=K2=0` on a singular matrix; design detail with a stated recommendation.

## Success Criteria

- [ ] `cd turbinesFoam && ./Allwmake` exits 0; full existing pytest suite passes
      unchanged; default-off output is byte-identical to a pre-change run.
- [ ] With `rotationalAugmentation active on`, the correction matches Eqs. 9–12
      (`a=b=d=1`) at hand-computed sample points, and the pre-stall polar
      coefficients are unchanged.
- [ ] ALM, ASM and the mesh surface all reflect the correction through the
      single shared chain, with no per-model code.
- [ ] The LB guard lets `dynamicStall` + `LeishmanBeddoesCoeffs` pass
      t = 0.008 s without `Singular Matrix`; the fallback path is recorded.
- [ ] The 0.25-rev D/32 proxy control reproduces `cp ≈ −0.0459` at U13;
      augmentation-on turns mid-span `c_ref_t` clearly positive and `cp`/`ct`
      positive at U13; the augmentation-on + root-off ablation reduces the U7
      deficit toward or inside the ±15 % band.
- [ ] The proxy harness is committed and prepared-only; **no production job is
      submitted** and the suspended arrays are undisturbed.
- [ ] Docs state the formulation (Eqs. 9–12, exact algebra from the PDF,
      `a=b=d=1`), the sensitivity note (no calibration, near-tip `fL`), the
      `c_ref_t` comparison caveat, and the honest claim boundary; root
      `CHANGELOG.md` updated.
- [ ] S3/preCICE remains deferred and untouched.
