# Literature review — rotational augmentation (3-D stall delay) and post-stall polars

Feature: `phasevi-stall-delay-literature` · Branch: `feat/dagsorensen-tip-correction`
Date: 2026-09-30 · Read-only review (no code, no queue).

Companion to `campaign-results/RESULTS.md` (the tip-correction sections),
`campaign-results/formulation-review.md`, `odd/tasks/phasevi-fllt-feasibility.md`
and `odd/tasks/phasevi-polar-viterna-design.md`.

## 0. Evidence boundary (read first)

**Retrieval capability in this session.**
- `web_search` has **no provider configured** and returns an error; the
  search-engine workaround (`fetch_content` on DuckDuckGo/Bing) is CAPTCHA-blocked
  or returns unrelated results. So no free-text literature search was possible.
- `fetch_content` **does** work for direct URLs. The **Crossref REST API**
  (`api.crossref.org/...`) was used to obtain verified bibliographic records, and
  the **open-access InTech chapter** `10.5772/18632` was retrieved in full (62 802
  characters).
- `turbinesFoam/articles/` (23 PDFs) contains **no** stall-delay or post-stall
  paper — it is ALM / tip-loss / smearing / sampling only (verified by reading the
  first page of every file with PyMuPDF).
- MDPI full texts returned HTTP 403.

**What that means for the citations below.** Every row tagged **[CR]** was
verified through the Crossref record for the stated DOI in this session
(title, authors, year, venue). Every statement tagged **[OA]** was read in the
retrieved open-access chapter. Anything tagged **[bg]** is background knowledge
that could **not** be verified here — treat it as a lead to confirm, never as a
citation. No page or equation number is invented.

## 1. The rotational-augmentation literature — verified records

| Reference | Where | Verified as |
|---|---|---|
| **Du, Z. & Selig, M. (1998)** — *A 3-D stall-delay model for horizontal axis wind turbine performance prediction*, 1998 ASME Wind Energy Symposium | DOI `10.2514/6.1998-21` | [CR] — the model we implement |
| **Snel, H., Houwink, R. & Bosschers, J. (1993)** — *Sectional prediction of lift coefficients on rotating wind turbine blades in stall*, ECN-C-93-052 | ECN report | [bg] — not in Crossref; the first widely adopted stall-delay law |
| **Corrigan, J. & Schlichting, J. (1994)** — AWEA Windpower '94 | conference | [bg] — cited by name in [OA] as one of the pre-1998 attempts |
| **Dumitrescu, H. & Cardoş, V. (2011)** — *Inboard Stall Delay Due to Rotation*, in *Fundamental and Advanced Topics in Wind Power* (InTech) | DOI `10.5772/18632` (open access) | **[CR] + [OA] — read in full** |
| **Guntur, S. & Sørensen, N.N. (2014)** — *A study on rotational augmentation using CFD analysis of flow in the inboard region of the MEXICO rotor blades*, Wind Energy | DOI `10.1002/we.1726` | [CR] |
| **Breton, S.-P., Coton, F.N. & Moe, G. (2008)** — *A study on rotational effects and different stall delay models using a prescribed wake vortex scheme and NREL phase VI experiment data*, Wind Energy | DOI `10.1002/we.269` | [CR] — the Phase VI model-comparison study |
| **Syed Ahmed Kabir, I.F. & Ng, E.Y.K. (2017)** — *Insight into stall delay and computation of 3D sectional aerofoil characteristics of NREL phase VI wind turbine using inverse BEM…*, Energy | DOI `10.1016/j.energy.2016.11.102` | [CR] — inverse-BEM 3-D section polars from Phase VI |
| **Ouakki, Y. & Arbaoui, A. (2023)** — *Verification, calibration, and validation of stall delay models using NREL phase VI and MEXICO data*, J. Renewable Sustainable Energy | DOI `10.1063/5.0104437` | [CR] — calibration/validation of the models on **our** rotor |
| **Matsuoka, K. et al.** — *Development of Stall Delay Built-In Actuator Line Model (SD-ALM) for Wind Turbine Rotor CFD*, Energies | DOI `10.3390/en19051260` | [CR] — a stall-delay explicitly built **into an actuator-line model** (the same shape of change we would make) |
| **Zhu, C., Wang, T. & Zhong, W. (2019)** — *Combined Effect of Rotational Augmentation and Dynamic Stall on a HAWT*, Energies | DOI `10.3390/en12081434` | [CR] |
| **Schreck, S. & Robinson, M. (2002)** — *Dynamic Stall and Rotational Augmentation in Recent Wind Turbine Aerodynamics Experiments*, AIAA 2002-2967 | DOI `10.2514/6.2002-2967` | [CR] |
| **Dumitrescu, H. & Cardoş, V. (2010)** — 3-D integral boundary-layer model; *(2009)* leading-edge separation-bubble study | — | [bg] — cited inside [OA] |

### 1.1 What the reviewable primary source actually says

The [OA] chapter is explicit about the same defect we measured, and it is worth
quoting because it is the load-bearing literature statement:

> "During the development of stall-regulated wind turbines, there were several
> attempts to predict 3-D post-stall airfoil characteristics (Corrigan &
> Schlichting, 1994; Du & Schling, 1998; Snel et al., 1993), but **these methods
> predicted insufficient delayed stall in the root region and tended to extend
> the delayed stall region too far out on the blade**." — [OA] §1

That is a *published* statement that the classical models get the **radial
distribution** of the stall delay wrong in both directions — under-delayed at the
root, over-extended outboard. Our measurement is the same shape: `CL = 2.276` vs
the 2-D `0.71` at `r/R = 0.216` (a large inboard inflation) while the tip is
`+54 %` high with the tip loss off.

The physical mechanism, per the same source:

- The dominant inboard rotational effect at high tip-speed ratio is the
  **Coriolis force**, which "delays the occurrence of separation to a point
  further downstream towards the trailing edge"; the **centrifugal pumping**
  effect "is much weaker than was generally thought before" — [OA] §2.
- At the root the flow behaves "like a rotating disk in a fluid at rest" with a
  largely uniform radial velocity field — [OA] §2.
- The models that are parameterised only on `c/r` ("the local chord to radii
  (c/r) ratio of the blade section as the main parameter of influence",
  attributed to Snel et al.) are "confirmed" by Shen & Sørensen (1999) and
  Chaviaropoulos & Hansen (2000) — but that is a *confirmation of the dominant
  parameter*, not of the models' accuracy in deep stall.

**Consequence.** The literature's own diagnosis of the classical models is that
they are **mis-distributed radially**, and the physically-correct treatment is a
**separation-location model** (Coriolis-delayed separation), not an additive lift
blend. This is the same conclusion the FLLT review reached from the other side.

## 2. Post-stall polars — verified records

| Reference | Where | Verified as |
|---|---|---|
| **Tangler, J.L. (2004)** — *Insight into wind turbine stall and post-stall aerodynamics*, Wind Energy | DOI `10.1002/we.122` | [CR] — the standard reference on rotating-blade post-stall aerodynamics |
| **Papi, F., Nocentini, A., Melani, P.F. & Bianchini, A. (2022)** — *Impact of Post-Stall Extrapolation and Rotational-Augmentation Models on the Performance of Stall-Controlled Wind Turbines*, ASME GT2022-82268 | DOI `10.1115/gt2022-82268` | [CR] — **the exact question**: the interaction of the post-stall extrapolation with the augmentation model. Full text paywalled; not retrieved |
| **Viterna, L.A. & Corrigan, R.D. (1982)** — NASA CP-2230 | NASA report | [bg] — the empirical branch we already implemented (`buildPolars.py`) |
| **Montgomerie, B. (1996)** — FFA report | FFA | [bg] |
| **Tangler, J. & Ostowari, C. (1991)** — post-stall data synthesis | — | [bg] |

The one directly on-point paper (Papi et al. 2022) is **paywalled and could not
be retrieved**; its title alone says the community treats the post-stall
extrapolation and the augmentation model as a *coupled* choice, which is exactly
the coupling we measured (`aug OFF` moving the power by 5.0–5.8 points).

## 3. What could NOT be verified, and why it matters

1. **The exact algebra of Lindenburg (2003/04), Snel (1993) and Corrigan–Olsen
   (1994) was not retrieved.** My Crossref query for Lindenburg as an author
   returned nothing, and the ECN/conference reports are not in Crossref or open
   access. **Do not code any of these from this document.** A web-search-capable
   session must retrieve them (ECN reports are often free PDFs).
2. **Consequently there is no verified claim here that "model X is the most
   accurate".** What the retrieved sources *do* support is the weaker but
   sufficient statement: the classical `c/r`-parameterised, additive-lift-blend
   family is **known to be radially mis-distributed**, and the physically-grounded
   alternative is a **separation-location** treatment.
3. **Papi et al. (2022)**, the paper that would settle the coupled choice, is
   paywalled.

**To unblock**: configure a search provider — set one key in
`~/.pi/agent/web-search.json` (e.g. `braveApiKey`, `tavilyApiKey`,
`serpapiApiKey`, `kagiApiKey`) or the matching env var; the error message lists
the accepted names and notes that an Exa MCP key is rate-limited.

## 4. Recommendation

The verified evidence points at the **same** change the FLLT review reached from
the induction side, and it is the physically-precise option rather than a clamp:

**Replace the additive-lift-blend stall delay with a bounded,
separation-based correction, coupled to a physical post-stall polar.**

Concretely, three edits, in order of leverage (all inside the existing hook
`actuatorLineElement::correctRotationalAugmentation`, `actuatorLineElement.C:302-402`,
which already computes `CL,p = 2·π·(α−α0)` and blends toward it):

1. **Bound the reference lift.** Stop blending toward the unbounded
   `CL,p = 2π(α−α0)` (≈ 3.16 at the offending element, giving `CL ≈ 2.28`). Use
   a reference that is itself bounded by the physical post-stall ceiling. This is
   the single edit that removes our measured defect.
2. **Taper the correction out of the fully-separated regime.** The [OA] physics is
   that rotation acts on the **separation location**; once the section is fully
   separated it does not add potential-flow lift. Drive `f_L`/`f_D` to zero there.
   This is physics, not a numerical clamp.
3. **Use a physical post-stall polar** (`S809_OSU_Re1M_viterna.dat`, already
   built) instead of the pasted Re = 0.3 × 10⁶ rows, with the deep-stall drag
   level reconciled (`B1 = 1.11` under-predicts the measured `CD(90°) = 2.24`).

**Ranked alternatives.**

| Rank | Option | Why |
|---|---|---|
| 1 | Bounded + tapered stall delay + Viterna/measured post-stall polar | Attacks the measured defect; reuses the existing hook; **zero added run cost** |
| 2 | A **separation-location** model (Dumitrescu–Cardoş [OA] / Guntur–Sørensen [CR]) | The physically-correct form; larger implementation (boundary-layer or CFD-derived separation point), needs inputs we do not sample today |
| 3 | **Ouakki & Arbaoui (2023) [CR]** calibration/validation of several stall-delay models on **Phase VI + MEXICO** | The cheapest way to pick the constants from a peer-reviewed source instead of from background knowledge — retrieve and read it first |
| 4 | Rotating 3-D polar from CFD/experiment | The accuracy ceiling; a separate project, and the angle-of-attack definition dominates the result |
| — | Remove the augmentation (`aug OFF`) | A diagnostic ablation, **not** a model; it is what measured the lever (5.0–5.8 pts) |

**Caveat, unchanged:** the thrust is `+9.3 %` while the torque matches, so no
configuration is a validated arm yet. See the parallel thrust diagnosis.

## 5. The discriminating experiment (existing variant matrix)

All three variants already exist in
`turbinesFoam/validation/phaseVI/scripts/slurm/tip-correction-variants.slurm`
(tip correction on, Glauert tip off; they differ only in the named switch):

| variant | rot. aug | polar | root |
|---|---|---|---|
| `rooton` | on | committed | on |
| `augoff-rooton` | **off** | committed | on |
| `viterna-rooton` | on | **Viterna** | on |

7 m/s results already exist. Run the same three at **13/15/25 m/s** and read:

- `augoff-rooton` improves 13/15 → the **unbounded reference is the deep-stall
  driver**; fix #1 is confirmed.
- `viterna-rooton` improves 13/15 → the **polar shape** is the driver; fix #3.
- `viterna-rooton` pulls the 25 m/s overshoot (+74 %) down without breaking
  7/10 m/s → the polar hypothesis is confirmed for the overshoot.
- **Neither moves 13/15** → the residual is the solver (URANS k-ω SST) or the
  domain (no tunnel blockage), not the polar/stall branch.

**Cost**: 3 variants × 3 speeds = 9 coarse runs (same class as those already
run: 48 ranks, ≈ 1.5–5 h each). Note the standing group quota (2 T).

---

## 6. UPDATE — formulations retrieved (files supplied by the maintainer)

The maintainer supplied the paper PDFs. Verified **with vision** from those files:

### 6.1 Snel, as implemented inside an actuator-line model (SD-ALM, *Energies* 2026, §2.3, p. 5)

Matsuoka et al. integrate the **Snel** stall delay into an ALM, and state the
motivation is that there is "a paucity of research incorporating stall delay
models specifically into the ALM framework":

    ΔC_l = (∂C_l/∂α)(α − α0) − C_l                                (15)
    C_L  = C_l + 3 (c/r)² ΔC_l                                     (16)

and — relevant to our own design — "the Snel model is applied **exclusively to
the lift coefficient**, while the 2D static values are retained for the drag
coefficient as a preliminary study".

**This is the same unbounded class as Du-Selig**: the reference is the linear
extrapolation `(∂C_l/∂α)(α−α0)`, which grows with α, so `C_L` still inflates
without limit in deep stall. **Not the model to adopt for our defect** (their
drag asymmetry is also worth noting: they deliberately leave `C_D` uncorrected).

### 6.2 Lindenburg — the bounded model, exact equations (Ouakki & Arbaoui 2023, §I.2, p. 6, Eqs. 5–9)

    ΔC_n   = 1.6 (c/r)(rΩ/V_eff)² f(α)²                            (5)
    ΔC_p   = −2 · 1.6 (c/r)(rΩ/V_eff)² (1 − x/c)                   (6)
    ΔC_L   = 1.6 (c/r)(cos φ)² [ f(α)² cos(α_rot)
                                 + 0.25 cos(α_rot − α_0) ]         (7)
    ΔC_D   = 1.6 (c/r)(cos φ)² f(α)² sin(α_rot)                    (8)
    α_rot  = α + (0.25/2π) · 1.6 (c/r)(cos φ)²                     (9)

with `f(α)` the **trailing-edge separation factor** (Kirchhoff/Helmholtz), `φ`
the inflow angle, `rΩ/V_eff ≈ cos φ`, `x/c` the chordwise position, `α_0` the
zero-lift angle.

**Why this is the right class for our defect:** it produces **bounded increments**
`ΔC_L`, `ΔC_D` added to the 2-D values — there is no blend toward an unbounded
potential reference. Its magnitude is governed by `(c/r)(cos φ)² f(α)²`, and
`f(α)` *decreases* as the section separates, so the correction self-limits in deep
stall instead of inflating. This is the concrete replacement for
`correctRotationalAugmentation()`'s `CL,p = 2π(α−α0)` blend.

### 6.3 The limit the literature itself states (Ouakki & Arbaoui 2023, conclusions, p. 42)

The single most important sentence for our case — their calibrated/modified
stall-delay models:

> "give accurate predictions of the pressure reduction inside the separated
> boundary layer **if the blade has only a trailing edge separation type like the
> MEXICO rotor**. While for the **NREL rotor, these models show good agreement
> only at medium angles of attack** … At **high angles of attack toward the
> maximum flow separation, further work is needed** to account for the complex 3D
> flow near the hub. … the **lack of generality of current stall delay models is
> due to the centrifugal pumping assumption**."

Our 7 m/s inboard sits at `α ≈ 27–35°` — "toward the maximum flow separation".
So **no 1-D stall-delay model (Lindenburg included) is validated in our failing
region**, and this is stated by the very paper whose purpose was to calibrate
them on Phase VI.

### 6.4 Revised recommendation

| Priority | Action | Basis |
|---|---|---|
| 1 | Replace the unbounded `CL,p` blend in `correctRotationalAugmentation()` with the **Lindenburg** incremental form (§6.2), applied to **both** `C_L` and `C_D` | It is the bounded member of the family; exact equations now verified |
| 2 | Keep a **physical post-stall polar** (§2; the Viterna files already built, with the deep-stall drag reconciled) | The deep-stall branch is not a stall-delay question |
| 3 | Accept, and *record*, that the inboard `α > 25°` region is **outside the validated range of any 1-D model** (Ouakki §6.3); do not tune to it | Prevents fitting a model where the literature says none generalises |
| 4 | The accurate option for that region is a **rotating 3-D polar from CFD or experiment** (Guntur–Sørensen, Mauro et al. — both supplied), i.e. a data/CFD project, not a 1-D model change | The accuracy ceiling |

**Do not adopt Snel/SD-ALM** (§6.1) — same unbounded class as the model being
replaced. **`aug OFF` remains a diagnostic, not a fix**: it under-loads the
inboard to −32 % (§ thrust diagnosis).

### 6.5 The two unknowns pin down (from the paper's reference list)

- **`f(α)` is the Beddoes–Leishman trailing-edge separation factor** — Ouakki's
  ref 44 is *Leishman & Beddoes, "A generalised model for airfoil unsteady
  aerodynamic behaviour…"*. That is the standard `f(α)` (the familiar
  `f = 1 − 0.3·exp((α − α₁)/α₂)` family, or the Kirchhoff form), i.e. a
  **decreasing** function once the section separates — which is exactly what
  makes the Lindenburg increment self-limiting.
- **The Lindenburg source is Ouakki's ref 37**: Lindenburg,
  *"Modelling of rotational augmentation based on engineering considerations
  and …"* (the EWEC-era ECN work). That report is the one still worth retrieving
  **for the calibration of `f(α)` and any constants**; the functional form is
  already pinned above.

**Implementation note (in-repo).** `turbinesFoam` already ships a
Leishman–Beddoes dynamic-stall model
(`.../dynamicStallModels/LeishmanBeddoes/LeishmanBeddoes.{H,C}`), so the `f(α)`
separation factor is either already computed there or available from the same
literature — the Lindenburg increment would not need a new physical closure,
only the `(c/r)(cos φ)²` scaling and the two extra terms of Eqs. (7)–(8).
