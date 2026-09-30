# Phase VI tip-loading calibration — what tip strength would move cn(r/R=0.95) to 0.5175

Feature: `phasevi-tiploss-calibration` · Branch: `feat/dagsorensen-tip-correction`.
Read-only analysis: no source change, no queue. Data read from the converged
element CSVs of `alm-U7-coarse-aug-on-root-off` (Glauert tip ON),
`alm-U7-coarse-aug-on-tip-off-root-off` (tip OFF) and
`alm-U7-coarse-tipcorr-rooton` (D&S), plus the code at HEAD.

## 0. Assumptions (all used below)

- **A1** Single-instant sampling at `t = 10.016 s` (≈ rev 12) reproduces the
  revs-4→12 window means to < 0.5 %. Verified against the quoted windowed values
  (reproduces A = 0.4348 vs 0.4349; A′ = 0.8835 vs 0.8836; D&S root-ON =
  0.7923 vs 0.7950).
- **A2** The compared `cn` is **chord-referenced**, `cn = cl·cosα + cd·sinα`,
  recomputed per row and interpolated in `r/R` (`comparePhaseVI.py:341-353`,
  `:425`); the element-CSV `c_ref_n` is the plane-of-rotation
  `normalRefCoefficient()` and is **not** used (`actuatorLineElement.C:1010-1018`,
  `profileData.C:534-543`).
- **A3** `r/R = 0.101073 + 0.898927·root_dist` (`comparePhaseVI.py:293-301`).
- **A4** The end-effect factor scales **lift only**
  (`actuatorLineElement.C:1174`) — a known deviation (H3a) from Shen 2005, which
  applies `F1` to `Cn` *and* `Ct`.
- **A5** TSR at 7 m/s `λ = 5.408` (`config/case.yaml:34`); Shen `c1 = 0.125`.
- **A6** Measured reference: NREL Sequence H spanwise `CN` at r/R = 0.95 =
  **0.5175**.
- **A7** "Tip-loss strength" is a scalar on the Prandtl exponent (Glauert `g=1`,
  Shen `g`); `cn(f)` is interpolated between the two measured endpoints.

## 1. What the tip models do (file:line)

### 1.1 Glauert — `axialFlowTurbineALSource.C:629-647`
`F = (2/π)acos(exp[−(B/2)(1/rootDist−1)/sinφ])`, φ from the blade-motion
convention (`:609-618`). Applied at `actuatorLineElement.C:1174`; written by
`setEndEffectFactor(f)` (`:678`) from call sites `:1249`, `:1349`, `:1437` — all
**before** the element `addSup` loop (the H3b one-iteration staleness).

### 1.2 Shen — `axialFlowTurbineALSource.C:649-679`
The **same Prandtl kernel with the exponent multiplied by `g`**:
`g = exp(−c1(B·λ − c2)) + 0.1` (`:655`), `acosArg = exp(−g·B/2·(1/rootDist−1)/sinφ)`
(`:658-661`). `g>1` ⇒ weaker loss; `g<1` ⇒ stronger. `c1`/`c2` are dict knobs;
nothing derives `c2`.

### 1.3 Dağ & Sørensen 2020 — `axialFlowTurbineALSource.C:684-1055`
Not a coefficient factor: a rotor-level induced-velocity correction added to the
inflow. `Γ = 0.5·c·C_L·|u_rel|` (`:753`); width `ε` = the element's
`projectionEpsilon()` (`:755`); **Γ smoothing** at width `ε` (`:800`); wake
strengths `Γ_w(p) = Γ(p−1) − Γ(p)` (`:885`); prescribed helical wake 2 rev / 2°
(`:820-870`); accumulation `acc += Γ_w(Δl × d)/|d|³exp(−(|d|/ε)²)` (`:995-997`).
**Effective tip strength** ≈ 0.78–0.82 m/s (≈11 % of `U∞`); it scales with the
**sampled `dΓ/ds`** at the model's resolution — D&S tip `cn` = 0.7950 at n50 vs
0.8091 at n25, i.e. a coarser span samples a smaller `dΓ/ds` and a *weaker*
correction.

## 2. Quantitative bracket at r/R = 0.95

### 2.1 End-effect factor per element (Glauert tip-ON, t = 10.016 s)

| element | root_dist | r/R | `end_effect_factor` | cn |
|---:|---:|---:|---:|---:|
| 45 | 0.94021 | 0.94624 | **0.50310** | 0.45063 |
| 46 | 0.95702 | 0.96137 | **0.43186** | 0.38691 |
| 47 | 0.98135 | 0.98326 | 0.28948 | 0.26037 |
| 48 | 0.99512 | 0.99567 | 0.14960 | 0.13661 |
| 49 | 0.99833 | 0.99855 | 0.08779 | 0.08210 |

Interpolating at r/R = 0.95 (w = 0.2483):

- **Glauert tip ON**: `f_g = 0.48541`, `cn = 0.43481`
- **Tip OFF** (f ≡ 1): `cn = 0.88349`
- **D&S (root ON)** (f ≡ 1): `cn = 0.79226`

These reproduce the windowed table (0.4349 / 0.8836 / 0.7950) to ≤ 0.3 %.

### 2.2 What tip strength reaches 0.5175?

Fit between the two measured endpoints `(f=1, 0.88349)` and
`(f=0.48541, 0.43481)`.

**Model 1 — cn linear in f**: slope `b = 0.87192`, intercept `a = 0.01158`,
`f_req = (0.5175 − 0.01158)/0.87192 = **0.5802**`.
**Model 2 — cn ∝ f**: `f_req = 0.5175/0.88349 = **0.5857**`.

→ **`f_req = 0.583 ± 0.003`.**

- As a fraction of the **Glauert factor**: `0.583/0.48541 = **1.20×**`.
- As a fraction of the Glauert **loss**: `0.417/0.51459 = **0.81**` — the
  required tip loss is **~81 % of Glauert's**, i.e. **Glauert is only ~23 % too
  strong** at r/R = 0.95, no more.

**Equivalent Shen `c2`** (the code's own formula):
`K = −ln(cos(π f_g/2)) = 0.32313`; `K_req = 0.49511`; `g_req = 1.532`;
`c2 = 2λ + ln(g_req − 0.1)/c1 = 10.816 + 2.874 = **13.69**`.

### 2.3 Where each candidate lands

| tip model | `g` (λ=5.408) | `f`(0.95) | predicted cn | vs 0.5175 |
|---|---:|---:|---:|---:|
| Glauert (`c2`≈9.97) | 1.000 | 0.485 | 0.435 | **−16.0 %** |
| **required** | **1.532** | **0.583** | **0.5175** | **0 %** |
| Shen standard `c2=21` | 3.673 | 0.802 | 0.711 | **+37.5 %** |
| Bernardi calibrated `c2=32` | 14.24 | 0.994 | 0.878 | **+69.7 %** |
| tip off | ∞ | 1.000 | 0.883 | +70.7 % |
| D&S correction | — (induction) | ≈0.90 eff. | 0.795 | +53.6 % |

## 3. Is the required value defensible? — **No.**

- **Standard Shen `c2 = 21`** → cn ≈ 0.711 (**+37.5 %**): too weak by a wide
  margin, not near the measurement.
- **Bernardi `c2 = 32`** → cn ≈ 0.878 (**+69.7 %**): almost no tip loss, the
  **opposite direction** from what Phase VI needs (higher `c2` ⇒ weaker loss).
- **Glauert** → cn = 0.435 (**−16 %**); the requirement sits only ~23 % softer
  than Glauert.
- **The requirement** `c2 ≈ 13.7` lies between the Glauert-equivalent (~10) and
  standard Shen (21) — a value **no independent study reports**.

**Reading.** The requirement is best described as "*Glauert, ~20 % softer*", not
as a Shen calibration. It is a **single-station fit** — the number that makes
`cn(0.95)` equal the very measurement that motivated it — while the same table
shows the inboard is simultaneously wrong (`r/R = 0.30` at −32 % under aug-off /
+23.6 % under root-off). **A single scalar tip factor cannot repair a spanwise
shape error**, so the number is a fitting artefact for the tip station rather
than a defensible physical constant. That Bernardi's peer-reviewed calibration
moves `c2` in the **opposite direction** is direct evidence that a "calibrated
`c2`" is case-specific and not transferable.

## 4. A three-way, non-circular discriminator

**The circular trap:** selecting a tip parameter to match Phase VI `cn(0.95)`
and then declaring Phase VI validated against that same number. Break it by
fitting on a **local response** and validating on **held-out observables**.

- **H-A "tip model wrong"** — a tip-localised multiplier error. Signature: a
  tip-strength change moves cn at r/R = 0.80–0.95, leaves r/R = 0.30–0.63
  invariant.
- **H-B "distribution wrong elsewhere"** — inboard magnitude/shape (stall /
  polar / augmentation). Signature: a global change moves the inboard and the
  integrated torque; the tip shape is not separately correctable.
- **H-C "comparison/integration artefact"** — largely retired by the frame fix
  and `--match-eaeroth-span`.

**Cheapest concrete runs** — the strongest lever without new physics is the
already-implemented **Shen** path: a 2–3 point **`c2` sweep at 7 m/s**
(`c2 ∈ {14, 21}`; the `c2≈10` endpoint is arm A / Glauert), paired with the
existing variant matrix:

| run | lever | reads out |
|---|---|---|
| `Shen c2 = 14` (new, render-only) | tip-localised | cn(r/R) shape, locality |
| `Shen c2 = 21` (new) | tip-localised | locality / monotonicity |
| `rooton` (exists) | inboard (root band) | H-B inboard |
| `augoff-rooton` (exists) | inboard (Du-Selig) | H-B inboard |
| `csu` / `multire` (exists) | polar/Re (inboard) | H-B inboard |
| `n25` (exists) | spanwise resolution → D&S strength | tip-model robustness |

**Acceptance signals (non-circular):**

1. **Locality.** The `c2` sweep must move cn(0.95)/cn(0.80) monotonically while
   cn(0.30)/cn(0.47) stay within ±2 %. If the inboard moves with the tip
   parameter, the "tip" is entangled ⇒ H-B.
2. **Cross-observable holdout.** The same `c2` that fits cn(0.95) at 7 m/s must
   also reproduce the measured chord-referenced **`ct`** and the
   **strip-integrated torque** at 7 m/s, *and* predict the tip cn at **10 m/s**
   without refitting. If the required `c2` drifts with speed, the parameter is
   absorbing a speed-dependent stall error ⇒ H-B.
3. **Robustness.** `n25` vs n50 (0.8091 vs 0.7950) shows the D&S strength is a
   resolution property. A genuine tip model must give an `n`-independent fitted
   strength.

**Verdict this study returns:** if (1)–(3) all hold, the tip model is the
isolated lever (H-A) and a `c2`-style retune is defensible; if any fails, the
Phase VI tip requirement is a fitting artefact (H-B), consistent with §3.

## 5. What the IEA 15 MW case would add

It has an **attached-tip regime with no stall confound** — the polar/Re/Du-Selig
ambiguity that dominates the Phase VI inboard and pollutes the tip comparison is
absent.

- **Circular against OpenFAST BEM.** AeroDyn/BEM **already contains a tip-loss
  model**. Calibrating an ALM tip parameter to match OpenFAST's tip-force
  distribution would merely recover whatever tip-loss ansatz OpenFAST uses — it
  validates the *shared assumption*, not the ALM's induced-velocity physics. The
  BEM annular-momentum closure and its high-induction/skewed-wake corrections
  add further model-specific error.
- **What it would genuinely validate.** (i) The **shape** of the tip-loading
  roll-off in attached flow, free of stall-model ambiguity — a cleaner test of
  the D&S correction and of the `ε`-sensitivity. (ii) The **transferability** of
  the required tip parameter: if the `c2` that fits the 15 MW tip equals the
  Phase VI requirement (≈14), the calibration is physical across geometry and
  operating point; if it differs, it is case-fitting. (iii) Larger scale and a
  different chord taper exercise the smearing kernel where `ε/c` differs.
- **To be truly non-circular** the 15 MW reference must be a distribution that
  does **not** embed the same tip-loss ansatz — blade-resolved CFD, a free-wake
  vortex method, or an OpenFAST lifting-line run with tip loss disabled — not
  AeroDyn BEM with tip loss on.

---

### Evidence index
- Code: `axialFlowTurbineALSource.C:629-647, 649-679, 684-1055, 678, 1521-1550`;
  `actuatorLineElement.C:1174, 1010-1018`; `profileData.C:534-543`.
- Data: `runs/alm-U7-coarse-aug-on-root-off/postProcessing/actuatorLineElements/0/blade1.element{45..49}.csv`;
  `.../alm-U7-coarse-aug-on-tip-off-root-off/.../blade1.element{45,46}.csv`;
  `.../alm-U7-coarse-tipcorr-rooton/.../blade1.element{45,46}.csv` (t = 10.016 s).
- Harness: `comparePhaseVI.py:66,172-215,293-353,425`; `config/case.yaml:20-34,228-233`.
- Results: `campaign-results/RESULTS.md:251-256,353-425`.
- Bernardi `c2 = 32`: inherited from the task brief; the PDF is compressed and
  its text was not machine-readable in the read-only agent, so not independently
  re-verified there (the parent vision-verified it).
