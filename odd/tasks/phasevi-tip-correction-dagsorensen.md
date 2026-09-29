# Feature: Dag & Sørensen tip correction for the ALM (P4)

- **Status:** in progress
- **Branch:** (cut before the first commit)
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

1. [ ] Re-verify Eqs. (15)–(24) and the prescribed-wake prescription (pp. 155–157).
2. [ ] ODD design note: interfaces, the wake geometry, the iteration, MPI safety.
3. [ ] Implement the per-element circulation Γ and the prescribed wake geometry.
4. [ ] Implement Eq. (23) accumulation and Eq. (21) application.
5. [ ] Config + render plumbing; default-off byte-identical gate.
6. [ ] Tests: the planar-wing limit (their Fig. 3/4), a zero-strength sanity
       check, default-off regression, parallel invariance.
7. [ ] Launch the Phase VI arm A with the correction **and the tip loss OFF** at
       7 m/s, against the measured 790 Nm / 1132 N.
8. [ ] Record the verdict in `RESULTS.md`.

## Evidence log

- **2026-09-29** — paper read (vision): Table 1, Fig. 2, Eqs. (9)–(24). Their
  Phase VI case matches ours (2 blades, TSR 5.39, D = 10.058 m, pitch **3°**,
  cone 0°, 7 m/s, ε/Δ = 2). Their Fig. 2 reproduces our exact symptom.
  **Their Table 1 gives root cutout 0.9 m** where the committed case uses
  0.5083 m (per NREL/TP-500-29955) — noted, not changed.
