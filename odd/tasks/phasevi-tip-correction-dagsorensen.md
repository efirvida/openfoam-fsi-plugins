# Feature: Dag & Sørensen tip correction for the ALM (P4)

- **Status:** in progress
- **Branch:** `feat/dagsorensen-tip-correction` (cut from `faad66f` on
  `feat/nacelle-actuator-surface`; carries the Phase VI ablation switches and
  the compare frame fix that the campaign needs — user decision 2026-09-29)
- **Created:** 2026-09-29
- **Reference:** Dağ, K.O. & Sørensen, J.N., *A new tip correction for actuator line
  computations*, Wind Energy 23(2):148-160, 2020
  (`turbinesFoam/articles/Wind Energy - 2019 - Dağ - A new tip correction for actuator line computations.pdf`).

## Objective

Replace the BEM Glauert tip loss — which the Phase VI campaign proved is **too
strong** — with the physically-motivated induced-velocity correction of Dağ &
Sørensen 2020, and validate it on the 7 m/s arm A.

## Problem / Why — the measured evidence

The 7 m/s campaign (all coarse, D/32, arm A = aug-on + tip-ON + root-off):

| quantity | measured | ours | Δ |
|---|---|---|---|
| power | 5.95 kW | 5.49 kW | **−7.6 %** |
| thrust | 1132 N | 1105 N | −2.4 % (in band) |
| **tip cn at r/R = 0.95** | **0.518** | **0.434** | **−16 %** |
| **tip ct at r/R = 0.95** | **0.041** | **0.034** | **−17 %** |
| cn at r/R = 0.47–0.80 | — | — | ±6 % (matches) |

With the tip loss **OFF** the 7 m/s power is **+19.5 %**. So:
**ALM over-predicts the tip; Glauert over-corrects it; the truth lies between
and the deficit is concentrated at the tip** (where `r`, the torque lever, is
largest).

**Dağ & Sørensen measured the identical symptom on the identical case** (their
Table 1: 2 blades, TSR 5.39, D = 10.058 m, **pitch 3°**, cone 0°, 7 m/s;
Fig. 2):

> "at the tip region an **overestimation of the ALM loadings** is clearly
> visible… Correcting the load distribution by the Prandtl tip correction,
> however, **does not remedy the situation, as the loading becomes highly
> underestimated**."

and their diagnosis is ours:

> "This behavior can only be explained by an **underestimated wake induction
> near the tip, causing an increased angle of attack**, which results in a
> stronger circulation."

**Why the smearing causes it**: the ALM Gaussian kernel is numerically identical
to a **Lamb–Oseen viscous vortex core**, so the induction at the blade is
reduced. Dağ & Sørensen subtract that viscous part analytically and add it back.

## Formulation (verified with vision, Eqs. 15–24)

- **Eq. (15)** Lamb–Oseen: `w_i = Γ/(4πr)·[1 − exp(−(r/r_vc)²)]`
- **Eq. (16)** the correction factor: `w_corr = Γ/(4πr)·exp(−(r/ε)²)`
- **Eq. (17)** planar-wing total: `w_corr(i) = Σ_j Γ_w(j)/(4π d_ij)·exp(−(d_ij/ε)²)`
- **Eq. (18)** wake strength: `Γ_w(j) = Γ(j) − Γ(j−1)` (tip vortices: `Γ_w = Γ`
  at each tip)
- **Eq. (19)/(24)** Kutta–Joukowski: `Γ(i) = ½·c(i)·C_L(i)·u_rel(i)`
- **Eq. (22)** per vortex line (vector form):
  `w_corr = Γ/(4π)·(dl × d)/|d|³·exp(−(|d|/ε)²)`
- **Eq. (23)** rotor total: sum over the wake system indexed `(h, p, q)` = blade,
  span position, azimuthal position:
  `w_corr^{N,m} = Σ_h Σ_p Σ_q Γ_w(h,p,q)/(4π)·(d_{h,p,q} × d^{N,m}_{h,p,q})/|d^{N,m}_{h,p,q}|³·exp(−(|d^{N,m}_{h,p,q}|/ε)²)`
- **Eq. (21)** apply: `α(i) = α_g − sin⁻¹((−u_x(i) + w_corr(i))/u_rel(i))`

**Implementation licence from the paper**: the wake may be a **prescribed,
straight-segment model** — "we restrict the modeling of the wake vortices to
straight lines in order to simplify the bookkeeping… even a simple prescribed
wake greatly improves the resulting circulation distribution." The correction is
**iterative within each time step**.

## Design sketch

- **Where**: `axialFlowTurbineALSource` already holds the span, the rotor
  geometry (axis, origin) and an element loop (`calcEndEffects` is the precedent
  for a rotor-level per-element correction). The correction belongs there, or in
  a dedicated `tipCorrection` class owned by the source.
- **Per element** it needs: the chord, the effective `C_L`, `u_rel`, the position,
  the span direction, the rotor axis and Ω.
- **Wake model**: helical lines trailing from each blade's quarter-chord,
  discretized into straight segments `(h, p, q)` over a prescribed number of
  revolutions at the local `φ`. Strength `Γ_w = Γ(p) − Γ(p−1)`, plus the tip
  vortex `Γ(N)`.
- **Apply**: pass the correction per element (like `setEndEffectFactor`) and add
  it to the inflow in `calculateInflowVelocity` before the AoA is formed (Eq. 21).
- **Iteration**: recompute Γ from the updated `C_L` within the PIMPLE iteration
  (the existing per-iteration `calcEndEffects` pattern).
- **Config**: a `tipCorrection { active on/off; model DagSorensen; epsilon ...; wakeTurns N; }`
  block, additive and default-off so every existing case is byte-identical.

## Scope

**In scope:** the correction for the **axial-flow** turbine ALM; config plumbing;
render plumbing; tests; a Phase VI ablation arm.

**Out of scope:** free-wake analysis; the cross-flow ALM; replacing the Glauert
model as the committed default (the ablation decides).

## Tasks

1. [x] Re-verify Eqs. (15)–(24) and the prescribed-wake prescription (pp. 155–157).
       Verified with vision on printed pp. 150–158 (PDF pp. 3–11) — see the
       evidence log below for the exact transcribed forms.
2. [x] ODD design note: interfaces, the wake geometry, the iteration, MPI safety.
       Written to `odd/tasks/phasevi-tip-correction-design.md` (D1–D9, the
       concrete algorithm, the test plan, and three revertable slices).
3. [x] Implement the per-element circulation Γ and the prescribed wake geometry.
       Done in `axialFlowTurbineALSource::calcTipCorrection()` (Γ from Eq. 24,
       N+1 vortex stations closed by Eq. 25, 2 revs / 2° helical segments).
4. [x] Implement Eq. (23) accumulation and Eq. (21)/(26) application.
       Done: the vector sum is stored per element and added to
       `inflowVelocity_` in `calculateForce` before the AoA.
5. [x] Config + render plumbing; default-off byte-identical gate.
       C++ default-off block + Phase VI render plumbing landed
       (`case.yaml`, `generate_case.py`, `runPhaseVI.sh --tip-correction`,
       regenerated `fvOptions.{ALM,ASM,ASM-MESH}`). Verified: `--check` exit 0,
       the committed default renders `active off` in all three twins, and
       `test_phasevi_case.py` passes (23).
6. [ ] Tests: the planar-wing limit (their Fig. 3/4), a zero-strength sanity
       check, default-off regression, parallel invariance.
       Done: Eq. (16)/(17) reference kernel, zero-strength, right-hand-rule
       sign, both axis conventions, default-off gate, badmodel, source pin
       (10 passed). Pending: parallel invariance.
7. [ ] Launch the Phase VI arm A with the correction **and the tip loss OFF** at
       7 m/s, against the measured 790 Nm / 1132 N.
8. [ ] Record the verdict in `RESULTS.md`.

## Evidence log

- **2026-09-29** — paper read (vision): Table 1, Fig. 2, Eqs. (9)–(24). Their
  Phase VI case matches ours (2 blades, TSR 5.39, D = 10.058 m, pitch **3°**,
  cone 0°, 7 m/s, ε/Δ = 2). Their Fig. 2 reproduces our exact symptom.
  **Their Table 1 gives root cutout 0.9 m** where the committed case uses
  0.5083 m (per NREL/TP-500-29955) — noted, not changed.

### 2026-09-29 — Task 1 re-verification with vision (printed pp. 150–158)

Rendered the paper pages to PNG (220 dpi) and read them with vision. The
handoff's Eq. (15)–(24) summary is **confirmed and completed**. Exact forms:

**Local kinematics (Eqs. 2–4, p. 150).** Corotating frame `(r, θ, x)`, `x`
downstream along the rotor axis, `θ` azimuthal, `γ` = local twist + pitch:

- (2) `u_θ = Ω r − (u_y cos θ + u_z sin θ)`
- (3) `φ = tan⁻¹(u_x / u_θ)`
- (4) `α = φ − γ`
- `u_rel = √(u_θ² + u_x²)`; (5) `f_L = ½ ρ u_rel² c C_L`; (6) `f_D = ½ ρ u_rel² c C_D`
- (7) `f_θ = f_L sin φ − f_D cos φ`; (8) `f_n = f_L cos φ + f_D sin φ`

**Gaussian kernel (Eqs. 12–13, p. 151).** The ALM kernel is `
η = (1/(ε³ √π³)) exp(−(d/ε)²)`; `d` = grid↔actuator-point distance.

**Correction core (Eqs. 15–16, p. 153).**

- (15) Lamb–Oseen: `w_i = Γ/(4πr)·[1 − exp(−(r/r_vc)²)]`
- (16) `w_corr = Γ/(4πr)·exp(−(r/ε)²)` — the viscous part subtracted; `r_vc`→`ε`.

**Planar wing (Eqs. 17–21, pp. 154–155).**

- (17) `w_corr(i) = Σ_{j=1}^{N+1} Γ_w(j)/(4π d_(i,j)) · exp(−(d_(i,j)/ε)²)`
- (18) `Γ_w(j) = Γ_(j) − Γ_(j−1)`
- (19) `Γ_(i) = ½ c_(i) C_L(i) u_rel(i)`
- (20) `d_(i,j) = y_(i) − y_w(j)` (planar, span = y; a note fixes `*`)
- (21) `α_(i) = α_g − sin⁻¹((−u_x(i) + w_corr(i)) / u_rel(i))`

**Rotor (Eqs. 22–27, pp. 155–156).** Vector form; `h,p,q` = wake blade,
span, azimuth; `N,m` = actuator blade, span:

- (22) `[w_xcorr,w_ycorr,w_zcorr]ᵀ = Γ/(4π) · (d𝒍 × d)/|d|³ · exp(−(|d|/ε)²)`
- (23) `[·]^{N,m} = Σ_h Σ_p Σ_q Γ_w(h,p,q)/(4π) ·
  (d_{h,p,q} × d^{N,m}_{h,p,q}) / |d^{N,m}_{h,p,q}|³ ·
  exp(−(|d^{N,m}_{h,p,q}|/ε)²)`
- (24) `Γ^{N,m} = ½ c^{N,m} C_L^{N,m} u_rel^{N,m}`
- (25) `Γ_w(h,p,q) = Γ_(p−1,q) − Γ_(p,q)`
- (26) `φ^{N,m} = tan⁻¹( (u_x^{N,m} + w_xcorr^{N,m}) /
  (u_θ^{N,m} + w_θcorr^{N,m}) )`
- (27) `w_θcorr^{N,m} = w_ycorr^{N,m} cos(θ^N) + w_zcorr^{N,m} sin(θ^N)`
- then the new AoA is Eq. (4): `α = φ − γ`.

**Correction applied to φ, not directly to α** for the rotor (Eq. 26 adds the
correction to the axial and tangential inflow, then (4) forms the AoA). The
planar-wing Eq. (21) is the 2-D analogue.

**Prescribed-wake recipe (p. 156, verbatim facts).** "the helical pitch of each
individual trailing vortex is assumed to be constant and equal to the relative
flow angle at the position where the trailing vortex is released"; updated every
time step (quasi-steady); **"the length of the helical vortex sheet is fixed at
two full revolutions"**; **"the azimuthal discretization of the wake is made
with 2° intervals"** (→ 180 segments/rev). The paper explicitly says the wake
vortices are restricted to straight lines "in order to simplify the
bookkeeping" and that "even a simple prescribed wake greatly improves the
resulting circulation distribution". The correction is iterative within each
time step (Fig. 1 caption / p. 155).

**Sign note (must be resolved in the design).** Planar (18) has
`Γ_w = Γ_j − Γ_{j−1}` while rotor (25) has `Γ_w = Γ_{p−1} − Γ_p`, i.e. opposite
differences; in the vector form the sign is carried by the segment direction
`d𝒍` in the `d𝒍 × d` cross product, so the two are consistent **only under a
stated segment-orientation convention**. The design MUST fix the convention and
the sign explicitly rather than copy one difference into the other case.

**Comparison-case numbers (their Table 1, p. 151).** Phase VI: 2 blades, TSR
5.39, AR 7.5, D = 10.058 m, root cutout **0.9 m**, Ω **7.50107 rad/s**, pitch
**3°**, cone 0°, U **7 m/s**. **Their verification case (Fig. 2, p. 152): domain
180×60×60 m, Δx=Δy=0.5, Δz=0.25, ε = 3Δ = 1.5 m, 10 points along the rotor
radius.** Their rotor validation (Fig. 10, p. 158) uses Δ = R/5 and R/20 with
ε/Δ = 5 and 3.

**Their Fig. 10 result (p. 158) = our target behaviour.** For Phase VI, ALM
*without* correction over-predicts the tip `F_n`/`F_t`; adding the correction
(`ALM*`) collapses them onto the BEM curves. This matches our chain: Glauert
OFF leaves us +19.5 % (over-predicted tip) → the Dağ & Sørensen correction must
lower it toward the measurement. Their reported 5-MW effect: peak error 23 %→5 %
(normal) and 77 %→17 % (tangential).

**Caveats recorded, not acted on.** (a) Their root cutout 0.9 m ≠ our 0.5083 m.
(b) Table 3's `ε, m` column prints 6/10 (coarse) and 1.5/2.5 (fine) while its
next column prints 3/5 and the Fig. 10 legend uses ε = 5Δ and 3Δ — the meter
column is internally inconsistent; the design uses **ε/Δ ∈ {3,5}** as the paper's
tested values and our own case's ε as the configured default, not the ambiguous
meter column.

### 2026-09-29 — Slices A/B implemented, verified, committed; arm A submitted

**Commits** (branch `feat/dagsorensen-tip-correction`, newest first):
- `516cf8f` `feat(phaseVI): add the prepared tip-correction arm-A submission script`
- `a7a95be` `feat(phaseVI): render and CLI plumbing for the tip correction`
- `1eb4fb0` `feat(turbinesFoam): add the Dag & Sorensen induced-velocity tip correction`

**Implementation** — `axialFlowTurbineALSource::calcTipCorrection()` (Γ = Eq. 24,
N+1 vortex stations closed by Eq. 25, 2 revs / 2° helical straight-segment
wake, Eq. 23 vector accumulation), plus the per-element
`inducedVelocityCorrection_` added to `inflowVelocity_` before the AoA in
`actuatorLineElement::calculateForce`.

**Sign convention resolved empirically** (design D4): the flow angle must use
the `calcEndEffects` blade-motion convention (`u_θ = −(bladeDir · rel)`), and
the sweep sign is `−sign(omega_·(axisHat · downstream))` (spin about the flow
axis). A blade-motion-derived sweep sign was tried and **refuted** by an
isolation experiment (it inverted the upstream rotor's tip-vortex induction and
made the correction *increase* tip loading). Measured fixture element at
r/R = 0.917 (`alpha_deg` / `f_ref_n`): upstream off 12.176 / 42.844 → on
9.070 / 39.079; axis-aligned off 12.176 / 42.844 → on 8.848 / 40.837 — both
reduce, as Fig. 10 requires.

**Independent verification** (gentle-ai-verify, read-only): `./Allwmake` exit 0
with the library newer than every source and exporting `calcTipCorrection` /
`setInducedVelocityCorrection`; `pytest tests/test_tip_correction.py` 10 passed;
`tests/test_phasevi_case.py` 23 passed; full `pytest tests` 166 passed,
**2 pre-existing failures unrelated to this change**
(`test_blade_surface.py::test_missing_empty_corrupt_stl_aborts`,
`test_nacelle.py::test_empty_stl_aborts` — stale `"contains no triangles"`
expectation vs the source's `"contains no faces"` in
`nacelleSurface/surfaceSamplerBase.C`), 3 skipped. Default-off gate confirmed
(all three twins render `active off`; `generate_case.py --check` exit 0). The
regression/reduction tests were confirmed non-tautological.

**Known limitations recorded**: MPI parallel invariance is still untested (task
6); the sweep handedness is pinned empirically by the fixture, not symbolically
derived; a single-element blade (`nEl == 1`) yields a zero correction.

**Campaign** — arm A submitted: Slurm job **11604127** (`phaseVI-tipcorr`,
`sequana_cpu`, 48 ranks, cores-only): 7 m/s coarse D/32, `--rotational-augmentation
on --root-effects off --tip-effects off --tip-correction on`, default and CSU
polars, restartable, full ~12-rev window. Verdict to be recorded in
`campaign-results/RESULTS.md` (task 8).

### 2026-09-29 — Arm A FAILED: the tip correction destabilizes the real case

Slurm job **11604127** (`phaseVI-tipcorr`) ended `FAILED 1:0` at 00:11:07.
**Both** the OSU and the CSU run diverged in the first ~11 steps:
`kOmegaSSTBase::F2()` floating-point exception after the Courant number exploded
(OSU max 6612, CSU max 82041; the previous tip-off arm A′ ran the full 12 revs
from the same mesh and initialization).

Evidence from the tip element (element 49, r/R = 0.999) CSV
(`runs/alm-U7-coarse-tipcorr/postProcessing/actuatorLineElements/0/…element49.csv`):

| t | rel_vel_mag | alpha_deg |
|---|---|---|
| 0.008 | 38.44 | 9.30 (identical to arm A′ — the correction is 0 on the first call) |
| 0.072 | 29.61 | **24.43** |
| 0.080 | 341.0 | −83.77 (blown up) |
| 0.088 | 3126.1 | 57.17 |

A correction that changed the tip α by ~+15° cannot be the intended small
induction fix, and it drives the force → wake → sampled inflow feedback loop
past its stability limit.

**Offline replication (Python, faithful to the C++ geometry) says the
correction should be small.** Using the run's own t = 0.008 element CSV and the
rendered `fvOptions.ALM` geometry (origin, axis `(-1 0 0)`, downstream `+x`,
TSR 5.408, R = 5.029, Ω = 7.53 rad/s, ε = 0.63, 2 revs / 2°), the reconstructed
Eq. (23) gives at the tip `|w_corr| = 0.82 m/s` (≈ 12 % of U∞), w = (−0.81,
0.15, −0.01); mid-span `0.04 m/s`; root `0.35 m/s`. The vector sum is dominated
by strong cancellation (the tip vortex station alone contributes ≈ 11.8 m²/s of
magnitude but nearly cancels). So the implemented physics *should* be stable.

**Therefore the C++ computation differs from the replica by ~10× on the real
case, and the fixture (6 elements, 2 steps, one corrector) did not expose it.**
The instability is a real blocker for task 7.

**Cleanup**: `processor*/` of both failed runs removed (quota). The run dirs
(logs, `postProcessing/`, `system/`) are kept for the diagnosis.

**Next step (needs a decision):** instrument `calcTipCorrection` with a
`debugTipCorrection` max-|w_corr| `Info` line (default off), rebuild, and run a
short (≈ 0.25–0.5 s) 7 m/s coarse case on the authorized development queue to
measure the real correction magnitude and its growth across PIMPLE iterations;
then either (a) fix the driver of the disagreement, or (b) damp/relax the
correction. Do not relaunch the full arm until the correction magnitude is
bounded.

### 2026-09-29 — Diagnosis: the instability is the INBOARD near-field singularity, not the tip

Diagnostic run: Slurm **11604142** (dev queue, 00:05:54, `COMPLETED`), the
pre-rendered 7 m/s coarse arm-A case with `tipCorrection { debug true; }` and
`endTime 0.30`. The new `tipCorrectionDebug` dump prints one line per
`calcTipCorrection` call.

**The tip is correct and small.** At t = 0.016 the tip element (blade 0,
element 49) stores `corr = (−0.814, 0.149, −0.020)` m/s — exactly the offline
replica's 0.82 m/s. The tip-region physics the feature targets is fine.

**The blow-up is inboard.** `max |w_corr|` over all elements grows
exponentially and jumps between blade/element indices:

| t | max\|w_corr\| (m/s) | location |
|---|---|---|
| 0.008 | 0 | (ε still unset; all stations skipped) |
| 0.016 | 15.76 | blade 1, element 7 |
| 0.024 | 17.16 | blade 1, element 9 |
| 0.032 | 84.09 | blade 0, element 9 |
| 0.040 | 264.06 | blade 0, element 9 |
| 0.088 | **1 972 755** | — |

**Root cause.** With the clean state (t = 0.008, before any correction is
applied) the bound circulation jumps from `Γ = 0` at elements 0–7 — the
`cylinder` placeholder profile, `cl ≡ 0` — to `Γ = +5.72` at element 8, the
first S809 element. Those elements are only ≈ 0.03 m apart in the radial
direction (the inboard `elementData` is densely packed), so the trailing vortex
shed at station 8, `Γ_w(8) = Γ(7) − Γ(8) = −5.72`, sits ≈ 0.015 m from the
element-8 actuator point. The kernel then gives `|w_corr| ≈ 14 m/s` there
(surrogate) — an order of magnitude above the correction's intended magnitude
and enough to drive the PIMPLE feedback loop unstable.

Both kernel forms diverge in this near field: the paper's point-segment
surrogate `(d𝒍 × d)/|d|³` gives 14.0 m/s at element 8, and the exact
finite-straight-segment Biot–Savart gives 27.2 m/s (and 66.6 m/s at the tip
element) — the actuator point is effectively **on** the vortex line, where any
Biot–Savart kernel is singular. The paper's own discretisation avoids this: at
`nrAero = 11` spanwise points the nearest vortex is ≈ 0.25 m away, i.e.
`≈ 1–2 m/s`.

So the failure is a **near-field resolution/regularisation** problem created by
our dense inboard sampling plus the non-lifting placeholder, not an error in the
tip correction itself and not a sign error.

**Options (need a decision; none applied):**
1. **Regularise the near field** — floor `|d|` (e.g. at a fraction of the local
   spanwise spacing or of ε), or cap `|w_corr|` at a fraction of `|U∞|`. Simple,
   but introduces a parameter the paper does not have.
2. **Coarsen the wake sampling** — shed the wake vortices at a coarser radial
   resolution (≈ the paper's spacing) or merge stations closer than ~ε, so no
   vortex sits within the near field of an actuator point.
3. **Neutralise the placeholder jump** — exclude the wake stations that straddle
   the non-lifting `cylinder`/first-lifting-element transition, where the jump is
   an artefact of `cl ≡ 0` placeholders rather than real loading.
4. **Extend the model** — make the correction the difference between the
   inviscid induction and the induction the ALM kernel already provides (the
   literal reading of the paper's "subtract the viscous part"), which is
   bounded by construction but is a larger change.

Option 3 + 1 look like the smallest credible fix; option 2 is the most faithful
to the paper's demonstrated resolution. Do **not** relaunch the full arm until
the inboard `max |w_corr|` is bounded to a few percent of `U∞`.

### 2026-09-29 — Near-field parameter study: the obvious fixes do not work cleanly

Offline (vectorised Python over the run's clean t = 0.008 state, ε = 0.677):

| variant | max \|w_corr\| | element | tip el 49 | elements > 2 m/s |
|---|---|---|---|---|
| baseline | 15.72 | el 7 | 0.83 | 11 |
| floor \|d\| ≥ 0.05 | 10.15 | el 6 | 0.83 | 11 |
| floor \|d\| ≥ 0.10 | 4.83 | el 5 | **0.58** | 8 |
| floor \|d\| ≥ 0.20 | 2.19 | el 4 | **0.09** | 2 |
| floor \|d\| ≥ 0.34 | 1.05 | el 3 | **0.03** | 0 |
| exclude station 8 | 4.22 | **el 47** | 0.83 | — |
| coarse wake nW = 10 | 17.03 | el 7 | **2.89** | 10 |
| coarse wake nW = 20 | 15.71 | el 8 | **3.77** | 11 |

Conclusions:

1. **Flooring `|d|` works only by killing the correction.** Any floor large
   enough to bound the inboard spike (≥ 0.2ε) collapses the tip correction to
   ≈ 0.03–0.09 m/s, i.e. it destroys the very signal the feature exists to add.
2. **Excluding the placeholder-transition station is not sufficient.** It removes
   the worst station but leaves a 4.2 m/s spike at element 47 (near the tip).
3. **Coarsening the wake does not help — it makes it worse.** The mid-point sum
   of point vortices converges to `(dΓ/ds)/(2π)`, which does not shrink with
   spacing; coarsening just enlarges each `Γ_w`, so the tip correction grows to
   2.9–3.8 m/s while the inboard spike stays.

**The mechanism, stated properly.** Our wake is a sum of *point* trailing
vortices evaluated with the surrogate `(d𝒍 × d)/|d|³`. As the spanwise spacing
shrinks, `Γ_w ≈ (dΓ/ds)·Δs` and `|d| ≈ Δs/2`, so each term contributes
`≈ (dΓ/ds)/(2π)` — **independent of Δs**. The sum therefore converges to the
physical downwash `(dΓ/ds)/(2π)`, which is large wherever `Γ` rises steeply.
The inboard `cylinder → S809` jump makes `dΓ/ds` enormous; even a purely
physical root loading would still give several m/s. The paper never sees this
because its discretisation is coarse enough that the sampled `dΓ/ds` stays
modest, and it reports only BEM comparisons, whose own root loading is smooth.

So this is not a bug in the tip correction; it is the **resolution/continuum
behaviour of a discrete point-vortex wake with a steep bound-circulation
gradient**. The credible fixes are structural, not parametric:

- **A. Sheet formulation** — integrate the trailing vorticity along the span (or
  use the exact finite-segment Biot–Savart *and* a spanwise sheet quadrature), so
  the near field is the bounded sheet induction rather than a sum of point
  vortices.
- **B. Smooth the bound circulation** — remove the placeholder discontinuity and
  smooth `Γ(s)` before differencing, so `dΓ/ds` is physical everywhere. Cheap,
  but only reduces the spike, it does not bound a genuinely steep root.
- **C. Local limiter** — cap `|w_corr|` at a fraction of the local relative
  velocity (e.g. 0.1·u_rel). Pragmatic and preserves the tip signal, but adds a
  non-physical clamp and needs its own justification.
- **D. Restrict the correction to the outer span** (where the paper targets the
  tip over-prediction), blended in over the outer ~30 %. Ad hoc but matches the
  feature's actual purpose.

Recommendation: **A (or A+B) for correctness**, with **D** as the minimal,
defensible scope reduction if a quick validation arm is wanted first. Do not
relaunch the full arm on the current formulation.
