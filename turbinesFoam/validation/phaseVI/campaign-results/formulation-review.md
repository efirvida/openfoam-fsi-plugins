# Formulation review — the ALM/ASM evolution, and where we sit in it

**Purpose.** Review our actuator-line / actuator-surface formulation against the
literature in `turbinesFoam/articles/` (23 documents), understand **how the
method evolved** and why each step was taken, and rank the changes worth making.
Read-only analysis; no code changed by this document.

**Method.** Text extraction with PyMuPDF to locate sections; **formulas, tables
and figures read by vision** (page renders), not plain text.

**Framing.** Newer is not automatically better. The old papers define the method
and its compromises; the new ones remove those compromises. Both are kept here,
with the *reason* for each step recorded, so a change is adopted on its
justification rather than its date.

---

## 1. The evolution of the method

| Year | Work | Contribution / why it mattered |
|---|---|---|
| 1932/1911 | Lamb; Oseen | Viscous vortex core model — the physics the smearing accidentally imitates (used later by Meyer Forsting). |
| 2002 | **Sørensen & Shen** | The ALM is introduced: blade = a line of body forces, Gaussian projection. States that the freestream velocity "must be sampled" but **does not say how**. |
| 2005 | **Shen, Mikkelsen, Sørensen, Bak** | The `F1` tip-loss correction for BEM: `F1 = (2/π)acos(exp(−g·B(R−r)/(2R·sinφ_R)))`, `g = exp[−0.125(Bλ−21)]+0.1`. **Explicitly a BEM correction** (it exists to correct the disc assumption). |
| 2007 | **Shen, Sørensen, Zhang** | ASM: the chordwise force shape is **empirical** (XFOIL curve-fits), and the bound-vorticity induction is **computed with Biot–Savart over the chord**. This is *why* an ASM "does not need a tip-loss correction". |
| 2009 | **Troldborg** (PhD) | Establishes the **`ε = 2Δr` compromise** from a sensitivity study: `ε = 1.5Δr` oscillates; large `ε` "smears out the distinct pattern of the tip and root vortices". States the *ideal* would be the chordwise pressure distribution "as in the actuator surface approach", but "due to limited computer resources this is not an option". |
| 2013 | **Shives & Crawford** | First physical criterion: `ε/c = 0.25` **and** `ε/Δx ≥ 4`. |
| 2014 | **Jha, Churchfield, Moriarty, Schmitz** | **NREL Phase VI at 7 m/s** with SOWFA. Quantifies the ε bias; shows a Prandtl tip loss *under*-predicts; proposes a **span-varying (elliptic) ε**. |
| 2015 | **Kim, Oh, Yee** | ASM that "eliminates the need for a tip-loss correction"; documents hub/tip force over-estimation as an open ALM problem. |
| 2016 | **Sørensen, Dag, Ramos-García** | Tip correction based on **decambering** (a physical, not disc-based, mechanism). |
| 2017 | **Yang & Sotiropoulos** | A new class of ASM: uniform chordwise load, **4-point cosine kernel** with a fixed 5-cell stencil (width **decoupled from mesh refinement**), chord-integral inflow, plus a nacelle ASM. |
| 2017 | **Martínez-Tossas, Churchfield, Meneveau** | The **physically optimal ε** from filtered lifting-line theory: **ε_opt/c ≈ 0.14–0.25 (≈0.2)**, force centre **13–26 % downstream of the LE**; drag width tied to the wake momentum thickness; an elliptical 2D kernel is better still. |
| 2017 | **Churchfield, Schreck, Martinez, Meneveau, Spalart** | The two ambiguous steps are **sampling** and **projection**; "there is **no general consensus on the proper sampling location**". Introduces the **VAS** (volume average) to average out blade-local effects. |
| 2018 | **Jost, Klein, Leipprand, Lutz, Krämer** | Every AoA extraction must **eliminate `Γ_bound`**; introduces the **LineAve (LAS)** sampling that does it geometrically. |
| 2019 | **Martínez-Tossas & Meneveau** | **Filtered lifting line theory** — the analytical induced velocity for a Gaussian body force. Turns the ε choice from a tuning knob into a solvable problem. |
| 2019 | **Meyer Forsting, Pirrung, Ramos-García** | **Vortex-based smearing correction**: recover the induction the smearing removed. With it "the AL truly functions as a LL". Shows a conventional tip correction is "**incorrect**" for an AL. |
| 2020 | **Dag & Sørensen** | A **new tip correction for ALM** for "over-estimated tip loads when using coarse CFD grids", validated on the NREL 5-MW **and the Phase VI rotor**. |
| 2020 | **Meyer Forsting, Pirrung, Ramos-García** | The **fast** version of the smearing correction: cost cut by **≥ 98 %**, power affected ≤ 0.8 %. |
| 2023 | **Martínez-Tossas, Sakievich, Churchfield, Meneveau** | **Generalized FLLT** for **arbitrary (tapering) chord** — the original FLLT assumed small chord change, which is wrong for wind-turbine blades. |
| 2024 | **Santoni, Sotiropoulos, Khosronejad** | ALM vs. ASM for a utility-scale rotor: **0.6 % / 0.3 % / 2.3 %** mean discrepancy (velocity / power / TKE). |
| 2024 | **Mohammadi, Olivares-Espinosa, Navarro Diaz, Ivanell** | **Actuator sector model** (75 % cheaper) + a sampling comparison: the **vortex-based smearing correction gives the lowest error** on radial load distributions. |
| 2025 | **Zormpa, Zilic de Arcos, Chen, Vogel, Willden** | **LAS robustness**: sampling on a ring at `r_s = 3.3ε` with `N = 16` **decouples** the sampling error from the smearing error and converges faster in `Δt`. Constraint `N_ε ≥ 2`. |

**The arc:** 2002–2009 built the ALM on a *numerical compromise* (`ε = 2Δr`)
while knowing the physically right answer was the ASM. 2017–2023 turned the
compromise into a *theory* (filtered lifting line) and a *correction* (vortex-based
smearing). 2024–2025 made the correction cheap and the sampling robust.

---

## 2. The core physics: why smearing breaks the lifting line

This is the thread that ties the old and the new papers together.

The smeared force produces a **viscous vortex core** instead of a concentrated
bound vortex. Its induced swirl is the Lamb–Oseen profile,

```
u_θ = (Γ/2πr)·[1 − exp(−r²/ε²)]
```

so at the blade the induction is **lower** than a true lifting line would give.
Lower induction ⇒ larger effective angle of attack ⇒ **larger blade forces**.
The effect is largest where the load changes fastest, i.e. **at the root and the
tip** — exactly where our campaign is worst.

Stated independently by:

- **Meyer Forsting 2019/2020**: "This force smearing leads to the formation of a
  viscous core in the released vorticity, which subsequently reduces the induced
  velocity at the blade. Lower induction implies larger angles of attack and thus
  increased blade forces. **Especially in regions presenting large load changes,
  as around the root and tip of the blade, does the AL thus overestimate the
  forces.**"
- **Kim 2015**: "the sectional forces … tend to be **overestimated at both the
  rotor hub and tip regions**, and the reason remains unclear."
- **Jha 2014**: "a constant Gaussian radius ε leads to **blade tip loads being
  overpredicted**".
- **Churchfield 2017**: the sampled velocity must be the *freestream*, i.e.
  "blade-local flow effects (blade-circulation-induced upwash and downwash) are
  **not** seen" — the bound-circulation contamination is the whole difficulty.
- **Shen 2007**: avoids it by **computing** the bound induction (Biot–Savart).
- **Jost 2018 / Zormpa 2025**: avoid it by **sampling where it cancels**.

**Therefore there are exactly three coherent remedies, and a tip-loss factor is
none of them:**

1. **Correct the induction** — vortex-based smearing correction (Meyer Forsting
   2019/2020; Dag & Sørensen 2020) or a span-varying ε (Jha 2014).
2. **Compute the induction** — an ASM carrying the bound vorticity explicitly
   (Shen 2007, Kim 2015).
3. **Sample around it** — LAS (Jost 2018, Zormpa 2025), or VAS (Churchfield 2017).

A BEM tip-loss factor is a *disc* correction. Meyer Forsting: "it is **incorrect**
to apply conventional tip corrections to ALs — they correct actuator discs for
missing discrete blades."

### 2.1 The modern corrections, concretely

Two of the three remedies now exist as **implementable, published algorithms**,
and a 2024 paper has benchmarked them.

**(a) Filtered-lifting-line (FLLT) correction — Martínez-Tossas & Meneveau 2019;
Martínez-Tossas et al. 2023.** Analytical. The induced velocity of a Gaussian
body force is (their Eq. 1)

```
u'_y(z) = −∫₀ˢ (dG(z')/dz') · (1 − e^{−(z−z')²/ε(z')²}) / (U_∞(z')·4π(z−z')) dz'
```

— note the **same Lamb–Oseen factor** `(1 − e^{−·})`. The generalized form for a
**varying chord** is their Eq. (4). The **procedure** is the practical part:

> "computing the difference between the induced velocity in the LES (from using
> ε_LES) and the desired optimal (ε_opt = 0.25c) and **adding the difference to
> the velocity sampled from the LES**."

Result: corrected simulations agree with the optimal-ε reference to **< 1 %**.
Their grid criterion is **`ε/Δ > 4`** — which **contradicts Troldborg's
`ε/Δ = 2`** that we use. The reconciliation matters: `ε/Δ = 2` is the compromise
*without* a correction; **once the FLLT correction is applied you can (and should)
use a finer, less-smeared force (`ε/Δ > 4`)**, because the correction removes the
smearing bias that Jha measured.

**(b) Vortex-based smearing correction — Meyer Forsting et al. 2019, 2020.**
Near-wake model + viscous core. The 2020 fast version reduces the smearing factor
to `f_ε = exp(−|x_⊥|²/ε²)` and the correction to `u* = f_ε·ũ`, cutting the cost
by **≥ 98 %** with ≤ 0.8 % effect on power. **Mohammadi et al. 2024 ported the
public FORTRAN implementation to C++** and found it gives the **lowest error on
radial load distributions** among the correction methods tested.

**(c) The rotor-update scheme — Mohammadi et al. 2024.** A separate, cheap
result. Two schemes exist:
- **OP (old position)**: project forces → sample velocity → rotate lines. This is
  the standard ALM (and ours).
- **NP (new position)**: rotate lines first → sample velocity at the new
  position → compute and project forces back.

With OP, "the power and thrust values have **decreased with each refinement** … as
ε is proportional to the cell side length"; with **NP the values plateau** with
mesh refinement. NP therefore removes a mesh-dependence we currently have.

## 3. Where we sit

### 3.0 Code-level defects (cross-checked against the earlier architecture audit)

An earlier session left a code-verified bug index in memory
(`turbinesfoam/latent-bugs`, observation #216, from the H1–H10 architecture
audit #214). Re-checked against the current tree, only **one** of them bears on
the end-effect diagnostic:

- **H3a — the end-effect factor is applied to the LIFT ONLY (applies to us).**
  `actuatorLineElement.C:1036` is `liftCoefficient_ *= endEffectFactor_;` with the
  comment "Apply end effect correction factor to lift coefficient"; the drag and
  moment coefficients are untouched. **Shen et al. 2005 (Eqs. 23–24) apply `F1`
  to `Cn` *and* `Ct`**, and Yang & Sotiropoulos 2017 (Eqs. 13–14) to `CL` *and*
  `CD`. Scaling only the lift does not scale the force magnitude uniformly — it
  **rotates the local force vector toward drag**, exactly in the tip/root region
  where the factor departs from 1. This is a deviation from the literature in
  the very term the arm A/A′ diagnostic measures.
- **H3b — the end-effect factor is one iteration stale (applies to us, minor).**
  `axialFlowTurbineALSource.C:859` calls `calcEndEffects()` *before* the element
  `addSup` loop at `:863-865`, so `calcEndEffects` reads each element's
  `relativeVelocity()`/`velocity()` from the **previous** PIMPLE iteration and
  writes `endEffectFactor_` for the current one. In a converged periodic flow
  this is a phase lag, not a magnitude error.
- **H8 — polar interpolation extrapolates above the table (does NOT apply).**
  `interpolateUtils::binarySearch` fails to reach the last index only for table
  sizes of the form **`n = 2^k + 1`** (3, 5, 9, 17, 33, 65, 129). Our committed
  polar `S809_OSU_Re1M_total.dat` has **59 rows** (not of that form), and a query
  above the maximum alpha does return the last index, so the `getPart` top-edge
  clamp is reached. Re-verified by replicating the algorithm.
- **H9 / H7 — Leishman–Beddoes uninitialised read and the never-called
  `reduceParallel` stall-state sync (do NOT apply).** Dynamic stall is off in the
  Phase VI case.
- **H4 — incomplete FSI geometry update (does NOT apply).** No FSI in this case.

**Consequence for the diagnostic:** the arm A → A′ swing of +26.6 points is the
removal of a factor that was (a) applied to lift only and (b) one iteration
stale. The *magnitude* conclusion (a BEM tip loss is a dominant, spurious term)
stands; the **shape** of the correction is additionally wrong, which strengthens
the case for replacing it rather than tuning it.

| Component | Our implementation | Position in the evolution |
|---|---|---|
| Projection kernel | 3D Gaussian `exp(−(d/ε)²)/(ε³π^1.5)` (`actuatorLineElement.C:546-568`) | The 2002 Sørensen–Shen kernel. Fine. |
| ε rule | `max(2·cbrt(V)·meshFactor, 0.25c, C_D·c/2)`; case uses `meshFactor 1.0` → **`ε/Δx = 2`** | **Troldborg 2009's compromise**, verbatim. Physical optimum is `ε/c ≈ 0.2`; we are at `ε/c ≈ 2` because the mesh term wins. |
| Sampling | **CPS** (point at the element centre), `velocitySampleRadius` default 0 | The 2002 assumption Churchfield calls ambiguous; **pre-LAS**. |
| End effects | Glauert tip (on) / root (off) + Shen `F1` | **BEM corrections (2005-era) applied to an ALM** — the thing Meyer Forsting 2019 calls invalid. |
| ASM | uniform strips + Gaussian; arithmetic strip mean | Between Shen 2007 and Yang 2017: **no bound-vorticity term**, no cosine kernel in the no-mesh element. |
| Rotational augmentation | Du–Selig, `a=b=d=1` | Matches Yang 2017 Eqs. 9–12. Keep. |
| Dynamic stall | Leishman–Beddoes family | Present; off by default. |
| Mesh | D/32 → `cbrt(V_min) = 0.3142 m`, D/48, D/64 | Δx ≈ chord, i.e. the "numerical" regime Martínez-Tossas describes. |

**Two concrete numbers that frame everything:**

1. Our `ε = 2Δx = 0.63 m` vs. the physical optimum `0.2c ≈ 0.07 m` → **~9×**.
2. Our arm A at 7 m/s is **−7.2 %**; Jha 2014's uncorrected ALM at the same
   `ε/Δx = 2` is **+5.5 %**; Jha's ALM **+ Prandtl** is **−8.5 %** — which is
   very close to our −7.2 %. **The BEM tip correction is plausibly the whole gap
   between us and the uncorrected ALM.**

---

## 4. Improvement plan

| # | Change | Evidence | Cost | Expected |
|---|---|---|---|---|
| **P0** | Run the prepared **tip-off arm (A′)** at 7/10/13 m/s | Meyer Forsting 2019, Kim 2015, Jha 2014 | **config, ready** | power moves from −7.2 % toward Jha's ≈ +5 %; tests §2 |
| **P1** | Keep **root-off** (arm A) | same + our data | done | already our best arm |
| **P2** | Switch sampling to **LAS**: `velocitySampleRadius 3.3`, `nVelocitySamples 16` | Jost 2018, Zormpa 2025, Mohammadi 2024 | **config-only** | removes ε/Δt sensitivity; faster Δt convergence |
| **P3** | Pin `gaussian_mesh_factor = 1.0` (never the code default 2.0) | Jha 2014 (`ε/Δx=4` → +22.6 %) | none | avoids a large power regression |
| **P4** | **Correct the induction.** Cheapest concrete route: the **FLLT correction** (MT 2019/2023) — evaluate the induced-velocity difference between our `ε` and `ε_opt = 0.25c` and add it to the sampled velocity. Heavier: the **fast vortex-based smearing correction** (Meyer Forsting 2020, publicly available). | MT 2019/2023, MF 2019/2020, Dag 2020, Mohammadi 2024 | code | the physically correct tip fix; Mohammadi 2024 finds the smearing correction gives the **lowest** radial-load error; FLLT is analytical and cheaper |
| **P4b** | Adopt the **NP rotor-update scheme** (rotate, then sample) | Mohammadi 2024 | code, small | removes the mesh-dependence of power/thrust |
| **P5** | **Compute the induction**: give the ASM a bound-vorticity term (Shen Eq. 5) and a chordwise force shape (Shen Eqs. 10–11) or Yang's cosine kernel | Shen 2007, Yang 2017, Kim 2015 | code, medium | removes the need for any tip correction |
| **P6** | Consider an **actuator sector** model (75 % cheaper, larger Δt) | Mohammadi 2024 | code, larger | only if cost becomes binding |

**Recommended order:** P0 + P2 + P3 as one cheap campaign (all config), then
choose between **P4 (correct the induction)** and **P5 (compute the induction)**
on the result. P4 keeps the ALM and is the one Mohammadi 2024 validates as most
accurate; P5 is the bigger architectural change but is what the ASM literature
validates.

---

## 5. Open items

- **Martínez-Tossas & Meneveau 2019** (JFM 863, "Filtered lifting line theory and
  application to the actuator line model") is **not in the folder** — OSTI is
  blocked from this host. It is the analytical basis for P4; the 2023
  generalization **is** in the folder.
- **Sørensen, Dag & Ramos-García 2016** (decambering tip correction) is not OA.
- **Shen 2007's empirical coefficients** A..G and `f_T` were not extracted; only
  the two functional forms (Eqs. 10–11) are recorded.
- The exact **SOWFA root-loss algebra** still needs a fresh read of the SOWFA
  source — though §2 argues we should not be using a root loss at all.
- **Not yet read in detail:** Troldborg's wake/sampling chapters (pp. 55–134),
  Mohammadi's sampling-method comparison (p. 3–7), Churchfield's projection
  sections (pp. 5–9), and the rotorcraft ASM/IBM papers (`138994`, `161926`,
  `JackPark`, `SciTech2020`, `Memòria`).
