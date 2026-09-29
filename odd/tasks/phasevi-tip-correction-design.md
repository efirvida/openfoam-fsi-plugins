# Design — Dağ & Sørensen 2020 tip correction for the ALM

Feature: `phasevi-tip-correction-dagsorensen` · Branch:
`feat/dagsorensen-tip-correction` · Date: 2026-09-29.
Formulation and evidence: task 1 of
`odd/tasks/phasevi-tip-correction-dagsorensen.md` (verified with vision,
printed pp. 150–158). Engram `turbinesfoam/dagsorensen-equations-verified`.

Status: every code claim below carries a `file:line` into the tree at
`faad66f`. Read-only code map produced by a `gentle-ai-explore` scout.

---

## 1. What is being built

A **rotor-level induced-velocity correction** for the axial-flow turbine ALM.
It replaces the BEM Glauert tip loss (which the Phase VI campaign proved is too
strong) with the physically-motivated Dağ & Sørensen model: subtract the viscous
part of the Lamb–Oseen core from the induction, computed from a **prescribed
straight-segment helical wake**, and add it to the local inflow before the angle
of attack is formed.

The correction is additive and **default-off**; with the block absent every
existing case must stay byte-identical.

Out of scope: the cross-flow ALM, a free-wake analysis, replacing the Glauert
model as the committed default, and any production campaign submission.

---

## 2. Code map (verified, `file:line`)

**Rotor owner — `axialFlowTurbineALSource` (AFTAL).** It already holds the span,
the rotor geometry and the rotor-level per-element loop that this feature
mirrors:

- `calcEndEffects()` decl `axialFlowTurbineALSource.H:131`, def
  `axialFlowTurbineALSource.C:582`; loops `forAll(blades_, i)` (`:590`) ×
  `forAll(blades_[i].elements(), j)` (`:592`); reads `rootDistance()` (`:594`),
  `relativeVelocity()` (`:595`), `velocity()` (`:596`); writes exactly one
  scalar per element via `setEndEffectFactor(f)` (`:678`).
- Call sites, all **before** the blade `addSup` loop: `:859` (incompressible
  momentum), `:953` (compressible momentum), `:1035` (scalar/energy), each under
  `if (endEffectsActive_ and endEffectsModel_ != "liftingLine")`.
- Rotor geometry (inherited from `turbineALSource`): `origin_` H:72, `axis_`
  H:75, `omega_` H:82, `nBlades_` H:94, `freeStreamVelocity_` H:97,
  `freeStreamDirection_` H:100, `radialDirection_` H:103, `rotorRadius_` H:109,
  `blades_` H:112, `azimuthalDirection_` (AFTAL) H:92, `verticalDirection_`
  H:88, `angleDeg_` H:85.

**Force chain — `actuatorLineElement::calculateForce`**
(`actuatorLineElement.C:923`):

- `:946` `calculateInflowVelocity(Uin)` → writes `inflowVelocity_` (member H:121)
- `:949-952` subtract the spanwise component of `inflowVelocity_`
- `:955` `relativeVelocity_ = inflowVelocity_ - velocity_`
- `:959-962` AoA from `planformNormal_ & relativeVelocity_`; `:979`
  `angleOfAttack_ = radToDeg(...)`
- `:981` lookup; `:989-992` rotational augmentation; `:1007-1017` dynamic stall
- `:1036` `liftCoefficient_ *= endEffectFactor_`; `:1039-1046` force assembly.

**There is no existing inflow/induced-velocity hook** (grep over
`turbinesFoam/src/fvOptions` for `induced|setInflow|inflowCorrection` is empty).

**Element public API available to the correction:** `chordLength()` H:341,
`chordDirection()` H:344, `spanDirection()` H:355, `spanLength()` H:358,
`position()` H:361, `velocity()` H:374, `force()` H:377,
`relativeVelocity()` H:380, `angleOfAttack()` H:386, `liftCoefficient()` H:392,
`rootDistance()` H:401. **No** getter for `freeStreamVelocity_`, `omega_`,
`radius_`, `rotorRadius_`, `inflowVelocity_`, `planformNormal_`.

**Per-element state precedent:** `endEffectFactor_` is one `scalar` per element
(H:223, init `1.0` C:753, `setEndEffectFactor` C:1420, consumed C:1036).

**Kernel width:** `calcProjectionEpsilon()` def `actuatorLineElement.C:406`
returns the 3-D Gaussian width `ε` (Eq. 13) as
`max(chordFactor·c, dragFactor·c·C_D/2)` vs `2·cbrt(V[cell])·meshFactor`, with a
`reduce(minOp)` (`:446`). It is **not cached** and depends on the current
`dragCoefficient_`.

**Config plumbing precedent:** `endEffects` read at rotor level
`AFTAL.C:1108-1110` and consumed lazily `:625-627`; `rotationalAugmentation`
forwarded rotor→blade→element at `AFTAL.C:322-330`,
`actuatorLineSource.C:358-372`, `actuatorLineElement.C:118-150`.

---

## 3. Decisions

### D1 — Owner and call site: a rotor-level `calcTipCorrection()` on AFTAL

**Choice.** Add `void calcTipCorrection();` to AFTAL (decl next to
`calcEndEffects`, `axialFlowTurbineALSource.H:131`) and call it from the same
three `addSup` sites, immediately after `calcEndEffects()` (`:859`, `:953`,
`:1035`), under its own `if (tipCorrectionActive_)` guard — **not** inside the
`endEffects` guard. It loops `blades_ × elements` exactly like `calcEndEffects`.

Rationale: the accumulation (Eq. 23) sums over **all** blades and **all**
actuator points at once, so it must be a rotor-level pass, and the existing
rotor-level loop is the reviewed precedent (including its documented
one-iteration staleness, finding H3b). A new class + `Make/files` + RTS
registration is not justified for one model and inflates the review budget.

**Alternative rejected:** a dedicated `tipCorrection` class owned by AFTAL —
cleaner isolation, but new files/RTS/`Make/files` for a single formula family;
deferred until a second model exists.

### D2 — Per-element storage and application point

**Choice.** Add one member `vector inducedVelocityCorrection_;` to
`actuatorLineElement` (beside `endEffectFactor_`, H:223), initialized
`vector::zero` in the constructors (mirror C:753), with
`setInducedVelocityCorrection(const vector&)` and
`inducedVelocityCorrection()` (mirror `setEndEffectFactor` C:1420 / H:464).
Apply it in `calculateForce` **after** the spanwise removal (`:952`) and
**before** `relativeVelocity_` is formed (`:955`):

```cpp
inflowVelocity_ += inducedVelocityCorrection_;
```

It is the **global-frame** correction vector `(w_xcorr, w_ycorr, w_zcorr)` of
Eq. (23). Adding it to the global inflow reproduces Eq. (26)–(27) without ever
materialising the azimuth `θ`: the element's own `planformNormal_` carries the
local tangential projection. The AoA (`:959`) and the force magnitude
(`:1039`) both then see the corrected inflow, exactly as the paper requires
(the correction enters the AoA, not the coefficients).

Default `(0,0,0)` makes the change a no-op when the correction is off.

### D3 — Circulation Γ (Eq. 24)

**Choice.** Per element, `Γ = 0.5·c·C_L·u_rel` from the element's own state:
`chordLength()`, `liftCoefficient()`, and `mag(relativeVelocity())`. Frozen for
the whole current pass — the wake strengths are sampled once per
`calcTipCorrection()` call and used for every wake segment ("quasi-steady",
p. 156). This is the same one-iteration lag as `calcEndEffects` (H3b): at call
time these getters hold the previous PIMPLE iteration's values.

Note recorded: `liftCoefficient()` already includes any active rotational
augmentation and the **previous** `endEffectFactor_` (`:1036`). The intended
campaign use is `tipEffects off`, where the factor is 1, so there is no
double-count; when both are on, the correction reads the tip-loss-scaled C_L.
This is documented, not special-cased.

### D4 — Prescribed helical wake (Eqs. 22–23, 25)

**Choice.** Build the wake at the current instant, attached to the blades, as
straight segments over **2 full revolutions** with **2° azimuthal steps**
(180 segments/revolution, `Q = 360`), per the paper's p. 156 recipe:

- One helical trailing vortex per **vortex station** `p = 0..N` (`N+1` per
  blade, `N = nElements`). Station 0 is the root end of element 0, station `p`
  the boundary between elements `p−1` and `p`, station `N` the tip end.
- Strength per Eq. (25): `Γ_w(p) = Γ(p−1) − Γ(p)`, with `Γ(−1) = 0` and
  `Γ(N) = 0` (closing at the root and the tip). The tip vortex therefore
  carries the bound circulation closest to the tip, as the paper states.
- Helix pitch: constant per station, `φ_p` = the local flow angle of the
  releasing element (Eq. 3). Downstream advance per unit azimuth is
  `r_p·tan φ_p`; the line is rotated about `axis_` away from the blade by the
  sweep angle and translated downstream along the free-stream direction.
- Nucleus width: `ε_p` = the releasing element's projection ε (D5).
- Segment contribution (Eq. 22):
  `(Γ_w/4π)·(Δl × d)/|d|³·exp(−(|d|/ε_p)²)`, `Δl` the segment vector, `d` from
  the segment centre to the actuator point.

**Sign convention (first-class).** The planar Eq. (18) is `Γ_j − Γ_{j−1}` while
the rotor Eq. (25) is `Γ_{p−1} − Γ_p` — opposite differences. In the vector form
the sign is carried by the direction of `Δl` in `Δl × d`. **Decision:** orient
`Δl` in the direction the vortex is laid down — downstream and along the sweep,
away from the blade — and use Eq. (25) literally for the rotor. The resulting
sign is then pinned by an explicit test (§7): a straight semi-infinite wake must
reproduce Eq. (16) up to the sign of the right-hand rule, and the full rotor
correction must **reduce** the tip loading (the paper's Fig. 10 behaviour, and
our required direction: Glauert-off is +19.5 %, the correction must bring it
down). If the planar-limit test shows the opposite sign, the difference is
swapped to the Eq. (18) orientation and the choice is recorded — the test is the
authority, not the notation.

**Resolved empirically (2026-09-29, `test_tip_correction.py`).** The sign is not
free: the flow angle must use the **blade-motion** convention of
`calcEndEffects` (`u_θ = −(bladeDir · rel)`, `u_x = rel · downstream`), which is
independent of the sign of `axis_` and `omega_`. With that φ, the original
sweep expression `sweepSign = −sign(omega_·(axisHat · downstream))` gives the
correct (lagging) helix for **both** the upstream `axis (−1 0 0)` convention
(Phase VI) and the axis-aligned `axis (1 0 0)` convention, because the two
rotors spin oppositely about the flow axis. A blade-motion-derived sweep sign
(`−sign(bladeDir · (axisHat ^ radialDir))`) was tried and **refuted**: it forces
`sweepSign = −1` for the upstream rotor and inverts its tip-vortex axial
induction, so the correction *increases* the tip loading. The two mirrors are
**not** required to match — they have opposite wake handedness — so the test
asserts the reduction direction in each, not their equality.

Measured (fixture element at r/R = 0.917, `alpha_deg` / `f_ref_n`): upstream
off 12.176 / 42.844 → on 9.070 / 39.079; axis-aligned off 12.176 / 42.844 → on
8.848 / 40.837. Both reduce, as the paper's Fig. 10 requires.

### D5 — Nucleus width ε

**Choice.** Cache the projection ε on the element: add
`scalar projectionEpsilon_;` set at the end of `calcProjectionEpsilon()`
(`actuatorLineElement.C:406`, before its `return`, after the existing
`reduce`), with a `projectionEpsilon()` const getter. The tip correction reads
the cached value from the previous iteration — **no extra `reduce` or
`findCell` per element**. An optional `epsilon` in the config block overrides it
for the paper's fixed-ε experiments. `projectionEpsilon_` is initialised to
`-VGREAT`; when unset the correction skips that station's wake for that step
(the first step only), mirroring the H3b lag rather than aborting.

Alternative rejected: calling `calcProjectionEpsilon()` per element from the
rotor loop — one global `reduce` and `findCell` per element per iteration, and
it can `FatalError` on a rank that does not own the cell.

### D6 — Config block, default-off

Rotor-level block, read in AFTAL's `read()` beside `endEffects`
(`AFTAL.C:1108`):

```
tipCorrection
{
    active             off;          // default; byte-identical when absent
    model              DagSorensen;  // only registered name
    wakeTurns          2;            // paper: two full revolutions
    wakeAzimuthalStep  2;            // paper: 2° intervals
    epsilon            0;            // 0 => use the element projection epsilon
}
```

Placement at the rotor `coeffs_` level (like `endEffects`), **not** forwarded to
the blade/element: the correction is computed and stored by AFTAL, and the
element only receives the resulting vector. An unknown `model` fails loudly with
`FatalIOErrorInFunction`. `wakeTurns`/`wakeAzimuthalStep` default to the
paper's tested values; `epsilon <= 0` selects the element projection ε.

### D7 — Iteration

One application per `calcTipCorrection()` call, i.e. per PIMPLE outer
correction, reading the previous iteration's Γ (D3) — the same iterative
mechanism the paper describes ("an iterative procedure in each time step") and
the same staleness the existing end effects already have (H3b). No internal
fixed-point loop is added: it would need the element to re-run the polar lookup
inline and would duplicate the PIMPLE loop.

### D8 — MPI and restart

- **MPI:** positions, geometry and Γ are replicated identically on every rank;
  the wake is built from these and each element's correction is computed
  locally. `calcEndEffects` does no communication and this pass does not either.
  The existing `reduce` in `calculateInflowVelocity` (`:595`) is untouched, so
  the correction is bit-identical across rank counts. This is asserted by the
  parallel-invariance test (§7).
- **Restart:** no new persisted state. `inducedVelocityCorrection_` and
  `projectionEpsilon_` are recomputed every pass; the only persisted rotor state
  (`angleDeg.<name>`) is unchanged.

### D9 — Guard: axial-flow only, geometry sanity

`calcTipCorrection` requires the free-stream to be (anti)parallel to `axis_`
and a positive `rotorRadius_`/elements with a resolvable radial direction. If
these fail, it emits one `WarningInFunction` and disables itself (no abort), so
a mis-configured case degrades to the pre-change behaviour.

---

## 4. Interfaces

**`actuatorLineElement` (new):** `vector inducedVelocityCorrection_;`,
`scalar projectionEpsilon_;` + `setInducedVelocityCorrection(const vector&)` /
`inducedVelocityCorrection() const` / `projectionEpsilon() const`. Applied at
`calculateForce` `:952→:955`.

**AFTAL (new):** `void calcTipCorrection();`, `bool tipCorrectionActive_;`,
`word tipCorrectionModel_`, `label wakeTurns_`, `scalar wakeAzimuthStepDeg_`,
`scalar tipCorrectionEpsilon_`; read in `read()`; called after
`calcEndEffects()` at `:859`, `:953`, `:1035`.

**Config:** the `tipCorrection` block of D6, rendered by `generate_case.py`
beside `endEffects` (`generate_case.py:614-623`) from `case.yaml`'s
`actuator.tip_correction` (next to `end_effects`, `case.yaml:206-210`).

---

## 5. Algorithm (concrete)

```
calcTipCorrection():
  if (!tipCorrectionActive_) return;
  axisHat   = axis_/mag(axis_)
  downstream = freeStreamDirection_            // unit, along the flow
  if (|axisHat & downstream| < 1 - tol) { warn; active=false; return; }

  // 1. Sample bound circulation, geometry, phi, eps for every station.
  //    For blade i: arrays P[i][j] (global QCPoint), r[i][j], radDir[i][j],
  //    phi[i][j] (Eq. 3 from the relative velocity), eps[i][j], Gamma[i][j].
  // 2. Vortex stations p=0..N: P_v, r_v, radDir_v, phi_v, eps_v, and
  //    Gamma_w(p) = Gamma(p-1) - Gamma(p)   (Eq. 25; Gamma(-1)=Gamma(N)=0).
  // 3. Pre-build Q straight segments per (i,p): start at the release point,
  //    step dTheta = 2*pi*(wakeAzimuthalStep/360); sweep the point about
  //    axisHat by sweepSign*k*dTheta (sweepSign from §5.1, i.e. the lagging
  //    rotation) and advance downstream by r_v*tan(phi_v)*dTheta per step.
  //    Segment k: centre C, vector dl.
  // 4. For each actuator point (i2,j2): acc = 0;
  //      for each (i,p,k): d = P_act - C; acc += Gamma_w * (dl x d)
  //        / max(|d|^3, VSMALL) * exp(-sqr(|d|/eps_v));
  //      element.setInducedVelocityCorrection(acc/(4*pi));
  //    The actuator point's own bound vortex is not in the wake set; the
  //    whole wake system is included (the paper's Eq. 23 sum).
```

Self-consistency: the paper excludes the *bound* vortex ("the bound vortex does
not contribute to the induced velocity defining the angle of attack") but
includes every trailing vortex, including the one shed by the evaluating blade
at other stations. No self-exclusion is applied beyond that.

Cost: `(N+1)·nBlades·Q` wake segments (`50+1)·2·360 ≈ 36.7k` for Phase VI at
2 rev/2°) evaluated at `N·nBlades = 100` actuator points → ≈3.7M segment-point
pairs per correction pass. Acceptable per the paper ("the added computational
expenses… are insignificant"); documented, not optimised.

### 5.1 Flow angle `φ_p` and the sweep direction (implementation contract)

**This is the final, implemented convention** (it supersedes the earlier sketch
that used `downstream ^ radialDir`; the code and
`test_cpp_flow_angle_and_sweep_convention_pinned` pin it):

```
axisHat     = axis_/mag(axis_)
downstream  = freeStreamDirection_            // unit, along the free stream
bladeDir    = element.velocity()/mag(element.velocity())
uX          = relativeVelocity() & downstream
uTheta      = -(bladeDir & relativeVelocity())    // calcEndEffects convention (Eq. 3)
phi         = atan2(uX, uTheta)               // Eq. (3); may be negative
dTheta      = 2*pi*(wakeAzimuthalStepDeg/360)
step(p,k)   = sweep about axisHat by sweepSign*k*dTheta, then advance
              downstream by k*r_p*tan(phi_p)*dTheta
sweepSign   = -sign(omega_*(axisHat & downstream))   // spin about the flow axis
```

The blade-motion form of `uTheta` is the `calcEndEffects` convention and is
**independent of the sign of `axis_` and `omega_`** (the earlier
`downstream ^ radialDir` form returned the supplement, ~135°, whenever the axis
was aligned with the free stream). `Δl` for segment `k` is
`step(p,k) − step(p,k−1)`, i.e. it points **away from the blade**, which is the
D4 orientation. When `|uTheta|` is below a small threshold the station is
skipped for that pass (a windmill-brake point is not physically meaningful and
`tan φ` diverges).

**The sweep sign comes from the spin about the flow axis, not from blade
motion** (see the D4 resolution): `sweepSign = -sign(omega_*(axisHat & downstream))`
gives the correct lagging helix for both the upstream (`axis (−1 0 0)`) and the
axis-aligned (`axis (1 0 0)`) conventions. A blade-motion-derived sign was
tried and refuted by the fixture tests.

`relativeVelocity()` at call time is the previous iteration's value (D3/H3b);
the wake pitch therefore lags one iteration, exactly like `calcEndEffects`.

**Known limitation (recorded, not fixed):** a single-element blade (`nEl == 1`)
collapses both extrapolated stations onto the element centre with
`Γ_w = ∓Γ`, so their contributions cancel and the correction is zero. Phase VI
uses 50 elements and the fixture 6, so this only affects degenerate fixtures.

---

## 6. Render and campaign plumbing

- `case.yaml`: `actuator.tip_correction` block (`active: false`, `model:
  DagSorensen`, `wake_turns: 2`, `wake_azimuthal_step: 2`, `epsilon: 0`).
- `generate_case.py`: render it beside `endEffects` (`:614-623`) into the rotor
  `axialFlowTurbineALSourceCoeffs`.
- `runPhaseVI.sh`: `--tip-correction on|off` (mirrors `--tip-effects`).
- Campaign arm (task 7): **arm A**: `--tip-effects off --tip-correction on`,
  plus the baseline `--tip-effects off --tip-correction off` (already measured:
  +19.5 %) as the control. No production submission; the prepared Slurm scripts
  stay prepared-only.

---

## 7. Test and verification plan (task 6)

No C++ unit framework exists (`AGENTS.md`: validation is solver-driven). So:

1. **Reference implementation (pure Python, committed under
   `turbinesFoam/tests/` or `validation/phaseVI/tools/`)** of Eqs. (15)–(27) for
   a synthetic wake. Tests:
   - single short segment → `Γ/(4πr)·exp(−(r/ε)²)` (Eq. 16) to `rtol 1e-9`;
   - a semi-infinite straight line discretised into segments → `Γ/(4πd)` (the
     Eq. 17 limit) within segment-resolution tolerance;
   - zero-strength wake (`Γ_w ≡ 0`) → exactly zero correction;
   - sign: a straight wake with a monotone Γ produces the right-hand-rule sign.
2. **C++ vs reference**: a debug/`Info` dump of the per-element correction for a
   fixed synthetic wake, compared with the Python reference. If a solver hook is
   too heavy, the reference test plus the statistical campaign gate carries the
   claim; the design does not assert a C++/Python bit-match it cannot run.
3. **Default-off regression**: with `tipCorrection` absent, the generated
   `fvOptions` is byte-identical to the pre-change render, and
   `inducedVelocityCorrection_ == 0` leaves `calculateForce` unchanged.
4. **Parallel invariance**: the correction computed from replicated data is
   identical on all ranks — verified by `grep`ing the per-element dump from a
   serial and a 48-rank run of the same prepared case.
5. **Campaign gate (task 7)**: arm A vs the measured 790 Nm / 1132 N; the
   primary signal is integrated torque/power, the tip `cn`/`ct` at r/R=0.95 is
   the secondary signal. Recorded in `RESULTS.md` (task 8).

---

## 8. Delivery slices and review budget

| Slice | Content | Est. lines |
|---|---|---|
| A | Element plumbing (D2, D5) + `calculateForce` application + config read + AFTAL wake/Γ/accumulation (D1, D3, D4, D9) + the Python reference test (Eq. 16 limit) + default-off gate | ~350–550 |
| B | Render plumbing + `--tip-correction` + Phase VI `case.yaml` + case tests (D6, §6) | ~120–250 |
| C | Docs (`turbinesFoam/README.md`, Phase VI `README.md`, root `CHANGELOG.md`) + records | ~80–150 |

Total ≈ 550–950 changed lines — over the 400-line single-PR budget. Each slice
is independently revertable and ends with its own tests and docs. The reviewer
workload is flagged; slicing is applied by default unless the user asks for one
PR.

---

## 9. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Sign convention wrong (Eq. 18 vs 25) | High | Explicit planar-limit sign test; the campaign direction (tip loading must fall) is the second gate |
| Stale Γ / one-iteration lag (H3b) | Certain, accepted | Documented; identical to `calcEndEffects`; the PIMPLE loop iterates |
| Cost of 3.7M pairs per pass | Low | Paper calls it insignificant; measured on the proxy, not optimised up front |
| `liftCoefficient()` already tip-loss-scaled | Medium | Intended use is `tipEffects off`; documented, not special-cased |
| ε caching changes behaviour | Low | Cache only *reads* in the correction; `calcProjectionEpsilon` still returns live values to the force path |
| Reference-vs-C++ test not runnable | Medium | Reference tests the math; the campaign tests the physics; no unverifiable bit-match claim |
| Review budget (550–950 lines) | High | Three independently revertable slices |

## 10. How this maps to the plan

Task 3 = D2/D3/D4/D5 wake and Γ; task 4 = D1/D2 accumulation and application;
task 5 = D6/§6; task 6 = §7; task 7 = §6 campaign; task 8 = the verdict record.
Every equation reference resolves to the task-1 evidence log.
