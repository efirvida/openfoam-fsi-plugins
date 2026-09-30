# Feasibility — Filtered Lifting Line Theory (Martínez-Tossas et al. 2023) for the Phase VI ALM

Feature: `phasevi-fllt-feasibility` · Branch: `feat/dagsorensen-tip-correction` · Date: 2026-09-30.
Read-only analysis: no code, no queue. Companion to
`campaign-results/formulation-review.md` §2.1(a)/§4 (P4) and
`campaign-results/RESULTS.md` (the Dağ & Sørensen section).

> **Provenance.** §1 was re-verified **with vision** against the source PDF
> (rendered pages 2–3). The equations below are transcribed from the page
> images, not from a text dump. §3 is computed from data files read directly.

---

## 1. The formulation (vision-verified)

Paper: *Generalized filtered lifting line theory for arbitrary chord lengths
and application to wind turbine blades*, Wind Energy 6(2):101–106, 2023 (6
pages). It is a **short communication**: page 2 states the original theory and
its procedure, page 3 gives the generalized equation and the "shortcomings".

### 1.1 The original statement — Eq. (1), p. 102

```
u'_y(z) = −∫₀^S  [dG(z')/dz'] · (1 − exp(−(z − z')²/ε(z')²))
                / [ U∞(z') · 4π (z − z') ]  dz'
```

`z` is spanwise, `S` the span, and — transcribed from the text below the
equation — **`G(z') = ½ C_L(α) c W²` is the lift force per unit span**,
`U∞` the inflow velocity, **`W = √(U∞² + u'_y²)` the magnitude of the velocity
vector**, `c` the chord, `ε` the width of the body-force kernel and/or vortex
core size, and `α` depends on `u'_y(z)`. That last dependence makes Eq. (1) an
**integro-differential** equation.

The paper states the procedure explicitly: *"The correction is done by computing
the difference between the induced velocity in the LES (from using ε_LES) and
the desired optimal (ε_opt = 0.25c) and adding the difference to the velocity
sampled from the LES"*, with the grid criterion **`ε/Δ > 4`**.

### 1.2 The generalized statement — Eq. (4), p. 103

Page 3 derives that Eq. (1) assumed `dε/dz << 1` (which lets `ε` move outside
the `z'` integral, enabling integration by parts). Keeping every term inside the
integral and evaluating analytically gives

```
u'_y(z) = −(1/2π) ∫₀^S  [G(z')/(U∞(z') ε(z')²)] ·
          [ exp(−(z−z')²/ε(z')²) + (ε(z')²/(2 (z−z')²))·(exp(−(z−z')²/ε(z')²) − 1) ]
          dz'
```

Two properties the paper highlights, both important for us:

1. **It is an integral equation in `G`, not in `dG/dz`** — Eq. (1) is
   integro-differential, Eq. (4) is integral, "because it involves G instead of
   dG/dz".
2. **It does not diverge**: "in the limit of `z → z'`, the function inside the
   integral tends to `G(z')/(2 U∞(z') ε(z')²)`."

The generalization exists because of the shortcoming documented in §3 below —
i.e. the 2023 paper is a *fix* of the 2019 form, not a new model.

### 1.3 What the paper itself says about the failure mode (p. 102, §3)

This is the most decision-relevant part of the paper and it was not in the
project's prior notes. Section 3 ("Shortcomings of the theory") reports an
**LES of a fixed wing with a chord distribution similar to a wind turbine
blade** and concludes:

> "there is disagreement **near the root of the blade, where the changes in
> chord occur over distances comparable to `c`**. Careful examination helped us
> understand that the difference is caused by the theory's limitation assuming
> that the changes in chord and `ε` along the blade are small (`dε/dz << 1`,
> in their normalized form `d(ε/c)/d(z/S)`). This finding motivates a new and
> more general formulation..."

So the **original** FLLT correction is *known by its own authors* to fail exactly
where a wind-turbine blade changes chord fastest — the inboard region — which on
Phase VI is compounded by the non-lifting `cylinder` placeholder. Their Fig. 2
shows the corrected curves for several `ε` collapsing onto each other but off
the optimal-`ε` reference at the root.

### 1.4 What it is derived for

Fix a **straight lifting line with a planar trailing wake in uniform inflow**; the
2023 extension adds an arbitrary chord distribution, still on that geometry. The
rotor / helical-wake case is **not** treated; `formulation-review.md` §2.1(a)
records it as the authors' own "future work". The nonlocal induction of a
helical wake — precisely what the prescribed-wake Dağ & Sørensen sum captures —
is outside the FLLT model. Applying FLLT per radial section of a rotor is an
explicit approximation the authors do not make.

---

## 2. Reconciliation with `formulation-review.md`

**Still standing.** §2's conclusion (a BEM tip-loss factor is the wrong
instrument; the coherent remedies are correct-the-induction, compute-the-
induction, or sample-around-it) and §4's ranking of FLLT as the cheapest
induction correction are unchanged. The identification of the mechanism (the
Gaussian projection is a Lamb–Oseen core, so the sampled induced velocity is low
and the AoA high) is unchanged and is the same mechanism as Dağ & Sørensen.

**Where this note departs.** `RESULTS.md` recorded an offline FLLT evaluation of
**0.2–1.3 % of U∞ mid-span and 4–6 % at the tip**, later reinstated as
justified. That estimate was made **on the tip-effect-on state**. The
configuration a shipping correction would replace the Glauert tip factor *in* is
the **tip-loss-off** state (arm A′), and there the estimate collapses (§3). The
reconciliation is therefore: the physics and the ranking are right; the
*magnitude* is configuration-dependent, and on the shipping configuration it is
negligible.

---

## 3. Quantitative payoff on our data

### 3.1 Method and assumptions

Data: the arm-A (tip-on) and arm-A′ (tip-off) converged element CSVs
(`runs/alm-U7-coarse-aug-on-root-off/` and
`runs/alm-U7-coarse-aug-on-tip-off-root-off/postProcessing/actuatorLineElements/0/`),
one late instant `t = 9.952 s` (~rev 11.9, inside the revs-4→12 window; the
field is statistically steady). Assumptions, all stated:

- **A1** `Γ = ½ c C_L u_rel`, `C_L` from the element `cl` column, `u_rel` from
  `rel_vel_mag`.
- **A2** chord from `data/geometry/phaseVI_blade.csv` interpolated at the element
  radius.
- **A3** the fixed-wing kernel of the documented procedure,
  `K(s) = [e^{−s²/ε_LES²} − e^{−s²/ε_opt²}]/s`, `ε_LES = 0.628 m` (coarse D/32),
  `ε_opt = 0.25 c` (≈ 0.089–0.178 m). No helical wake, no self-induction/Lloyd
  term.
- **A4** trapezoidal quadrature over ± ~1 m; **A5** sign convention not
  independently validated (magnitudes only); **A6** the review's `G·ρ ≈ 1.23×`
  caveat (≤ +23 %) is not applied.

### 3.2 Estimated FLLT correction

| r/R | arm A′ (tip-off) Δu | % U∞ | arm A (tip-on) Δu | % U∞ |
|---:|---:|---:|---:|---:|
| 0.30 | ~0.2 (+~0.6 placeholder artifact) | ~2.9 | ~0.2 | ~2.9 |
| 0.47 | 0.031 | 0.45 | 0.04 | 0.6 |
| 0.63 | 0.025 | 0.36 | 0.03 | 0.4 |
| 0.80 | ~0.01 | 0.15 | 0.08 | 1.1 |
| 0.95 | **0.003** | **0.04** | **0.31** | **4.4** |

D&S measured for comparison: **0.78 m/s = 11.1 % of U∞ at the tip**. So FLLT at
the tip is ≈ 1/10 of D&S on the tip-off state and ≈ 1/2.5 on the tip-on state.

**Why it collapses on arm A′**: the arm-A′ Γ profile is almost **flat at the
tip** (6.39 m²/s at r = 4.04 m → 6.07 at r = 5.02, `dΓ/dr ≈ −0.4 /m`), and the
Eq. (1) kernel is driven by `dG/dz`; the inboard and outboard halves of the odd
kernel cancel. On arm A (tip-on) Γ drops 5.2 → 0.5 over the last 0.9 m and the
estimate reproduces the previously recorded 4–5.5 %.

### 3.3 The measured deficit at the same stations (chord-referenced cn)

| r/R | exp cn | arm A cn | Δ | arm A′ cn | Δ |
|---:|---:|---:|---:|---:|---:|
| 0.30 | 0.814 | 1.025 | +25.9 % | 1.022 | +25.6 % |
| 0.47 | 0.920 | 0.973 | +5.8 % | 0.980 | +6.5 % |
| 0.63 | 0.867 | 0.902 | +4.0 % | 0.931 | +7.4 % |
| 0.80 | 0.767 | 0.762 | −0.7 % | 0.893 | +16.4 % |
| 0.95 | 0.518 | 0.451 | −12.9 % | 0.883 | +70.5 % |

Cross-check against `RESULTS.md`'s windowed values at the tip (−16.0 % arm A,
+70.7 % arm A′) — consistent to the single-instant approximation.

**The tip loading is +70 % with the tip loss off and still +54 % after the full
D&S correction.** No smearing correction of the 0.3–0.8 m/s class addresses an
error of that size.

### 3.4 Uncertainty

1. §3 uses **Eq. (1)** (the `dG/dz` form). **Eq. (4)** is an integral equation
   in `G` and is finite at `z = z'`, so its correction on a *flat* Γ is not
   strictly zero — the estimate above is the documented procedure, not a
   solution of Eq. (4).
2. The task-named `campaign-results/alm-U7-*/U7-H/` directories are gitignored
   and absent on a clean checkout; the station values were recomputed from the
   raw element CSVs. `results/U7-H` is a *different* configuration and was used
   for the experimental reference only.
3. Single-instant sampling; hand quadrature over ~10 elements per station;
   signs not independently validated.

---

## 4. Smallest additive implementation (only if a GO is forced)

The Dağ & Sørensen feature already supplied the plumbing, so FLLT is a smaller
delta than D&S was:

- `axialFlowTurbineALSource.{H,C}` — a `FilteredLiftingLine` model branch inside
  the existing `tipCorrection` block, reusing the Γ sampler, the per-element
  loop and the three `addSup` call sites.
- `actuatorLineElement.{H,C}` — **no change**: reuse `inducedVelocityCorrection_`
  / `setInducedVelocityCorrection` (applied after the spanwise removal, before
  `relativeVelocity_`).
- config / render / CLI — `tipCorrection.model FilteredLiftingLine` and an
  `epsilonOptFactor` (0.25).
- tests — planar-wing limit, zero-Γ → zero, default-off gate.

Missing input: only `ε_opt` (derived) and the self-induction term (needs blade
curvature/taper; a straight-line approximation silently omits it). The hard part
is the same one D&S hit: the `cylinder → S809` placeholder discontinuity must be
filtered before any spanwise derivative/integral. Effort ≈ 1–2 engineering days
plus a campaign — cheaper than D&S, but §3 says it cannot buy the answer.

---

## 5. GO / NO-GO

### Verdict: **NO-GO.**

1. **Negligible on the shipping configuration.** Tip loss off, FLLT predicts
   ≈ 0.003 m/s (0.04 % U∞) at r/R = 0.95 and < 0.01 m/s for r/R ≥ 0.63 — two
   orders below the 0.78 m/s D&S correction, and it cannot move the tip loading
   (currently +70 % over experiment).
2. **Too weak even on the tip-on state.** 0.31 m/s (4.4 %) ≈ 2.5× smaller than
   D&S, and D&S already only closed ~24 % of the way (power +19.5 % → +9.6 %,
   tip +70.7 % → +53.6 %).
3. **Wrong geometry class, by the authors' own statement.** Fixed wing / planar
   wake; the rotor helical wake is untrated, and that nonlocal induction is
   exactly where D&S's 0.82 m/s tip value comes from.
4. **Its own authors document a root failure for turbine-like chord
   distributions** (§1.3, their §3): the original form assumes `dε/dz << 1` and
   disagrees near the root where the chord changes over distances comparable to
   `c` — our configuration, worsened by the placeholder jump.
5. **The residual is the wrong size for any smearing correction.** A +70 %
   tip-over-loading (still +54 % after D&S) is not the ~0.5–1.5 m/s
   induction-deficit class these methods address; it points at the polar /
   3-D rotational / stall-modelling family, not at the induction kernel.

### The single discriminating experiment (only if overridden to GO)

A **no-queue offline prototype**: solve Eq. (4) in Python on the converged arm-A′
element data (it is an integral equation, so iterate `G ← G(u'_y)`), add `Δu`
per element to the sampled inflow, re-derive `α` through the S809 polar, and
predict `Δ(torque)` and `Δ(c_ref_n at r/R = 0.95)`. **Gate:** predicted torque
gain ≥ +2 points and tip `cn` movement ≥ +10 points toward the measurement.
Predicted from §3: torque change < 0.5 points, tip `cn` change < 2 points →
stays NO-GO. Run only as a cheap falsification, never as a campaign.

---

*Prepared from the vision-verified 2023 paper, the element CSVs, the case config
and the project's campaign documents. Not submitted to Slurm; no source changed.*
