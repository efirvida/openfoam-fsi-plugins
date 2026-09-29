# Research — Du–Selig formulation fidelity (`rotational-augmentation`)

- **Date**: 2026-09-24
- **Mode**: read-only source-fidelity investigation
- **Question**: Is the shared blade-load chain's Du–Selig rotational-augmentation
  formulation correctly *read* from the reference and correctly *implemented* —
  and does the outboard `fL < 0` / `fD < 0` behaviour reflect the paper's intent,
  a mis-reading, or a model limitation?
- **Verdict**: The code is a **faithful implementation of the arXiv preprint's
  printed Eqs. 11–12**, but the arXiv preprint's Eqs. 11–12 are a **transcription
  error** relative to the original Du–Selig formulation. The error is
  **material**: it inverts the drag-correction sign over most of the blade and
  expands the outboard `fL < 0` region from a thin tip band to roughly the outer
  half of the span. A correction is warranted.

---

## 1. Method and evidence base

- The reference PDF (`/scratch/leahk/eduardo.donestevez/tmp/opencode/nacelle-digitize/1702.02108v4.pdf`)
  was rendered with PyMuPDF at 5–12× and read visually (Eqs. 9–12 on page 4).
- The implementation was read in source (`actuatorLineElement.{H,C}`) and in
  `design.md`.
- The original Du–Selig formulation was established from peer-reviewed
  reproductions and reference implementations (below), because the 1998 AIAA
  paper itself is **closed access** and could not be read directly.
- The peer-reviewed Yang-group formulation was read from a later, open-access
  review by the same author.

---

## 2. (A) As-printed reference equations — arXiv:1702.02108v4, p. 4

Rendered directly from the PDF (verified visually, not from the garbled text
dump). The preprint prints, with `X_L ≡ (c/r)^{(d/Λ)(R/r)}` and
`X_D ≡ (c/r)^{(d/(2Λ))(R/r)}`:

```
Eq. 9   CL,3D = CL,2D + fL (CL,p − CL,2D)
Eq. 10  CD,3D = CD,2D − fD (CD,2D − CD,0)
Eq. 11  fL = (1/2π) ( (1.6(c/r)a − (c/r)^{(d/Λ)(R/r)}) / (0.1267b + (c/r)^{(d/Λ)(R/r)}) − 1 )
Eq. 12  fD = (1/2π) ( (1.6(c/r)a − (c/r)^{(d/(2Λ))(R/r)}) / (0.1267b + (c/r)^{(d/(2Λ))(R/r)}) − 1 )
```

with `CL,p = 2π(α − α0)`, `CD,0` = 2-D drag at zero angle of attack,
`Λ = ΩR/√(U² + (ΩR)²)`, and: *"In this work, a, b and d are equal to 1 as in
Du and Selig's paper [25]."* The exponent is **`(d/Λ)(R/r)`** (Eq. 11) /
**`(d/(2Λ))(R/r)`** (Eq. 12); the text-dump reading `d·ΛR/r` is a layout
artifact, not the printed form.

**Note on the symbol `a` (as printed):** `1.6(c/r)a` is rendered with `a` on the
**baseline**, i.e. a **multiplier** of `(c/r)` — not a superscript exponent. The
superscripted term on the same line is the exponent `(d/Λ)(R/r)`.

Rendered crops (evidence): `$SCRATCH/tmp/ra-formulation/eq9-12_page4.png`,
`.../eq11_full.png`, `.../eq12_full.png`.

## 3. As-implemented equations — `actuatorLineElement.C`

`correctRotationalAugmentation()` at
`turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/actuatorLineElement.C:289-328`:

```cpp
:311  const scalar xL = (d_/lambda)*ROverR;
:312  const scalar xD = (d_/(2.0*lambda))*ROverR;
:313  const scalar qL = Foam::pow(cOverR, xL);
:314  const scalar qD = Foam::pow(cOverR, xD);
:315  const scalar fL = (1.0/(2.0*pi))
:316      *((1.6*Foam::pow(cOverR, a_) - qL)/(0.1267*b_ + qL) - 1.0);
:317  const scalar fD = (1.0/(2.0*pi))
:318      *((1.6*Foam::pow(cOverR, a_) - qD)/(0.1267*b_ + qD) - 1.0);
:321  const scalar alpha  = degToRad(angleOfAttack_);
:322  const scalar alpha0 = degToRad(profileData_.zeroLiftAngleOfAttack());
:323  const scalar CLp = 2.0*pi*(alpha - alpha0);
:326  liftCoefficient_ += fL*(CLp - liftCoefficient_);
:327  dragCoefficient_ -= fD*(dragCoefficient_ - CD0);
```

with `cOverR = chordLength_/radius_`, `ROverR = rotorRadius_/radius_`,
`lambda = omegaR/√(|U|² + omegaR²)`, `omegaR = omega_*rotorRadius_` (`:300-307`).

The design's equation→code table (`design.md:64-103` §1.1, `:162-174` §2.2)
states the same split form, including `Eq. 11 fL = (1/2π)[ (1.6(c/r)^a −
(c/r)^((d/Λ)(R/r))) / (0.1267b + (c/r)^((d/Λ)(R/r))) − 1 ]`.

**Code ↔ arXiv (printed): MATCH.** The only difference is the role of `a`:
the code computes `(c/r)^{a}` (exponent, `:316`), the arXiv prints `(c/r)·a`
(multiplier). Identical for `a = 1`. Exponent, `Λ`, `c/r`, `R/r`, `CL,p`, and
the `−1` all match. The `fL = 0.2036` reference test and the design's
`fL ≈ 0.204` at the U13 mid-span point are the split form, so the tests pin the
split form, not the original.

---

## 4. (B) Primary-source / established formulation

### 4.1 Original Du–Selig (as reproduced by peer-reviewed sources)

The original formulation places `1.6(c/r)` and `0.1267` as a **prefactor** on the
fraction, and `a`/`b` are the constants inside `(a − X)` / `(b + X)`:

```
fL = (1/2π) [ (1.6(c/r)/0.1267) · (a − (c/r)^{(d/Λ)(R/r)}) / (b + (c/r)^{(d/Λ)(R/r)}) − 1 ]
fD = (1/2π) [ (1.6(c/r)/0.1267) · (a − (c/r)^{(d/(2Λ))(R/r)}) / (b + (c/r)^{(d/(2Λ))(R/r)}) − 1 ]
```

Verified reproductions (all read visually or in source):

1. **IOP 2024, *Limitations of lift correction models for thick airfoils*,
   J. Phys. Conf. Ser. 2767:022029** — rendered Eq. (3), attributed to
   Du & Selig [7]:
   `f = (1/2π) [ (1.6(c/r)/0.1267) · (a − (c/r)^{(dR)/(Λr)})/(b + (c/r)^{(dR)/(Λr)}) − 1 ]`,
   `a = b = d = 1`. DOI 10.1088/1742-6596/2767/2/022029.
2. **Munduate (2002), PhD thesis, Univ. of Glasgow**, Eq. (3.6), reproduced from
   Du & Selig (1998): `Δ(ks) = (1.6(s/r)/0.1267)·(C1 − (s/r)^{C3/λm})/(C2 +
   (s/r)^{C3/λm}) − 1`, with `C1=C2=C3=1` recommended. theses.gla.ac.uk/679.
   (Eq. 3.5 defines the separation factor; Eq. 3.6 is the difference used as the
   correction.)
3. **NREL AirfoilPrep.py** (Hansen / Ning), the NREL reference implementation of
   the Du–Selig method — source:
   `fcl = 1.0/m*(1.6*chord_over_r/0.1267*(a-chord_over_r**expon)/(b+chord_over_r**expon)-1)`,
   `expon = d/lam/r_over_R`. github.com/NLRWindSystems/AirfoilPreppy.
4. **BYU CCBlade.jl** — source:
   `fcl = 1.0/du.m*(1.6*cr/0.1267*(du.a-cr^expon)/(du.b+cr^expon)-1)`,
   `expon = du.d/(Lambda*rR)`. github.com/byuflowlab/CCBlade.jl.
5. **Jeong, Yoo & Lee (2012), *Wind turbine aerodynamics prediction using
   free-wake method in axial flow*** — Eqs. (9)–(10) render with the same
   prefactor structure (OCR-level confirmation). DOI 10.1142/S2010194512008707.

`a = b = d = 1` is the published/default value: *"the constants a, b, and d
given as 1 by the author were used here"* (Jeong 2012); *"The default values of
a, b, and d are equal to unity"* (Li/Liu/Yang 2022); *"a, b and d are equal to 1
as in Du and Selig's paper"* (arXiv reference).

### 4.2 Yang's own later peer-reviewed form

**Li, Liu & Yang (2022), *Review of Turbine Parameterization Models for
Large-Eddy Simulation of Wind Turbine Wakes*, Energies 15(18):6533**, Eqs.
(21)–(22) — rendered and read directly:

```
fL = (1/2π) ( (1.6(c/r)/0.1267) · (a − (c/r)^{(d/Λ)(R/r)}) / (b + (c/r)^{(d/Λ)(R/r)}) − 1 )
fD = (1/2π) ( (1.6(c/r)/0.1267) · (a − (c/r)^{(d/(2Λ))(R/r)}) / (b + (c/r)^{(d/(2Λ))(R/r)}) − 1 )
```

DOI 10.3390/en15186533. **This is the same author (Xiaolei Yang) as the
reference preprint, and it uses the prefactor form.** This is the strongest
single piece of evidence: the preprint's split form is inconsistent with the
same author's peer-reviewed treatment of the same model.

### 4.3 The reference preprint's published journal version

Yang & Sotiropoulos, *A new class of actuator surface models for wind turbines*,
**Wind Energy 2018, 21(5):285–302, DOI 10.1002/we.2162** — **closed access; could
not be fetched** (Semantic Scholar/OpenAlex both report `CLOSED`, no OA PDF).
Its Eq. 11 could not be checked directly. See §7.

---

## 5. (C) Discrepancy list with severity

Let `X_L = (c/r)^{(d/Λ)(R/r)}`, `X_D = (c/r)^{(d/(2Λ))(R/r)}`.

| ID | Discrepancy | arXiv / code (as-is) | Original Du–Selig | Severity |
|----|-------------|----------------------|-------------------|----------|
| **D-1** | Placement of `1.6(c/r)` and `0.1267` | `(1.6(c/r)a − X)/(0.1267b + X) − 1` | `(1.6(c/r)/0.1267)·(a−X)/(b+X) − 1` | **CRITICAL** — flips `fD` sign over most of the blade and expands outboard `fL<0` |
| **D-2** | Role of `a` | code `(c/r)^{a}`; arXiv `(c/r)·a` | constant in `(a − X)` | **LOW (latent)** — identical at `a=1`; matters only if `a≠1` |
| **D-3** | `CD,0` = drag at `α=0` vs at `CL=0` | `zeroLiftDragCoeff()` (drag at `CL=0`) | drag at `α=0` | **LOW** — documented (`design.md:83-91`); immaterial in deep stall |
| **D-4** | No `α`-based taper/gate | none | (Du–Selig is applied via `adj` taper in NREL/CCBlade) | **LOW** — robustness gap, not a fidelity error; the paper relies on the Shen tip loss (Eqs. 13–16) instead, which this change does not enable |

**D-1 is the material finding.** `D-2` is a latent bug that should be fixed with
`D-1`. `D-3` is already documented. `D-4` is a separate scope decision.

### 5.1 Quantified impact of D-1 (committed Phase VI geometry, U13 `Λ = 0.946`)

Recomputed at the five stations in `verify-report.md` §4.2:

| `r/R` | `c/r` | `fL` arXiv/code | `fL` Du–Selig | `fD` arXiv/code | `fD` Du–Selig |
|------:|------:|----------------:|--------------:|----------------:|--------------:|
| 0.453 | 0.278 | +0.195 | **+0.346** | −0.059 | **+0.195** |
| 0.585 | 0.192 | +0.071 | **+0.190** | −0.122 | **+0.085** |
| 0.706 | 0.142 | **−0.006** | **+0.097** | −0.161 | **+0.019** |
| 0.828 | 0.107 | **−0.061** | **+0.033** | −0.189 | **−0.027** |
| 0.961 | 0.078 | **−0.104** | **−0.020** | −0.211 | **−0.064** |

Consequences of the arXiv/code (split) form vs the original:

- `fD < 0` for **every** station outboard of the deep root, so Eq. 10
  (`CD,3D = CD,2D − fD(CD,2D−CD,0)`) **raises** drag over essentially the whole
  blade — the **opposite** of the model's stated purpose ("increases the lift
  coefficients and decreases the drag coefficients", arXiv p. 4). The original
  form gives `fD > 0` (drag decreases) out to `r/R ≈ 0.78`.
- `fL` crosses zero at `r/R ≈ 0.71` in the split form vs `≈ 0.94` in the original
  form, i.e. the outboard lift-reduction region is enlarged ~4× by span.
- The outboard elements carry the largest torque lever arm; this is the dominant
  mechanism behind the proxy regression documented in `verify-report.md` §4.2.

**A note on the design's own sweep:** `design.md:98-103` / §2.4 describes `fD`
as "positive inboard (≈ +0.61 at `r/R ≈ 0.10`) and crosses zero near
`r/R ≈ 0.36`". That description happens to agree with the split form only because
`c/r` is very large in the deep root; the split form's `fD` is negative for
`r/R ≳ 0.36`, which is why the verify table (stations `r/R ≥ 0.453`) is negative
throughout.

---

## 6. (D) Does Du–Selig's `fL` legitimately go negative outboard?

**Partly yes — but the split form makes it far worse.**

- In the **original** formula, as `c/r → 0` the prefactor term vanishes and
  `fL → −1/(2π) ≈ −0.159`. So `fL < 0` **is** inherent to Du–Selig in a thin tip
  band (`c/r ≲ 0.09`, i.e. roughly `r/R ≳ 0.94` for the Phase VI blade).
- The `−1` term is present in every established reproduction (IOP, NREL,
  CCBlade, Li review), so it is not a mis-reading.
- **Established implementations do not clamp `fL ≥ 0` and do not restrict it
  radially.** NREL AirfoilPrep.py and BYU CCBlade.jl apply an **angle-of-attack
  taper** (`adj`: full correction for `|α| ≤ 30°`, tapering to 0 by ≈85–90°),
  which suppresses the correction in the deep-stall/high-α region; they rely on
  attached flow near the tip (`CL,2D ≈ CL,p`, so `ΔCL ≈ 0` regardless of `fL`) to
  keep the negative-`fL` band harmless.
- The paper itself does not use the `adj` taper; it pairs Du–Selig with the
  **Shen tip loss** (Eqs. 13–16), which the current change does **not** enable
  (production keeps `Glauert`).

So: the outboard sign change is a **model limitation** that no correct
implementation removes; but the **extent** of the negative region in the current
code is a **transcription artifact** (D-1), not the model's intent.

---

## 7. Recommended correction

**Fix the code to the original prefactor form** (this is a fidelity fix to
Eqs. 11–12, not a calibration; no free parameter is introduced):

```cpp
// Du-Selig Eqs. 11-12 (original form): 1.6(c/r)/0.1267 multiplies the
// fraction (a - X)/(b + X); a, b are the numerator/denominator constants,
// not an exponent/multiplier of c/r.
const scalar fL = (1.0/(2.0*pi))
    *((1.6*cOverR/0.1267)*((a_ - qL)/(b_ + qL)) - 1.0);
const scalar fD = (1.0/(2.0*pi))
    *((1.6*cOverR/0.1267)*((a_ - qD)/(b_ + qD)) - 1.0);
```

with `qL`, `qD` unchanged (`:313-314`) and `xL`, `xD` unchanged (`:311-312`).
Eqs. 9–10 (`:326-327`) are unchanged. This matches NREL AirfoilPrep.py,
CCBlade.jl, the IOP 2024 rendering, Munduate Eq. 3.6, and Yang's own 2022
review, term for term. It also resolves D-2 (the `a` role).

**Expected effect (qualitative, not a claim of a U13 fix):** the outboard
drag-increase and lift-reduction are largely removed (crossover `r/R ≈ 0.71 →
0.94` for `fL`; `fD` positive out to `r/R ≈ 0.78`), while the intended inboard
lift augmentation is **strengthened** (`fL` +0.195 → +0.346 at `r/R = 0.453`).
Whether this alone flips the integrated U13 `cp`/`ct` sign is **not** asserted —
`verify-report.md` §4.3 shows the root/end-effect treatment is co-dominant and no
single tested lever flips the sign.

**Not recommended:** inventing a clamp/gate (the spec forbids it and the
original model has none). If a robustness safeguard is desired, the
`α`-taper used by NREL/CCBlade is the established, citable choice — but it
belongs in a separate change, since the paper pairs Du–Selig with Shen tip loss
instead.

**Documentation:** update `design.md` §1.1/§2.2 (the equation table is the
arXiv's erroneous split form), the `fL = 0.2036` reference test, and the
`README.md` sensitivity note; record that the preprint Eq. 11–12 differ from
Yang's own later peer-reviewed form.

---

## 8. Open uncertainties

1. **Published Wind Energy 2018 Eq. 11 not read** (DOI 10.1002/we.2162, closed
   access; no OA copy found via Semantic Scholar/OpenAlex). It is therefore
   unconfirmed whether the journal version carries the split or the prefactor
   form. The arXiv v4 (2018-04-15) postdates publication. If the journal version
   also prints the split form, then the error is in the published paper too, not
   only the arXiv — the correct form is still the one to implement, because it
   is the original Du–Selig formulation and Yang's own later review uses it.
2. **Original Du & Selig (1998) not read directly** (AIAA-98-0021, closed
   access). The "original" form is established by triangulation across five
   independent sources (§4.1), not by reading the 1998 paper. No source
   contradicts the prefactor form; the split form appears only in the arXiv
   preprint (and one lower-tier secondary paper, the WSEAS 2019 paper, which
   also omits `a`/`b` entirely).
3. **The `1/(2π)` prefactor** is present in the Yang/NREL/IOP/Li forms; Munduate's
   `Δ(ks)` form (Eq. 3.6) lacks it, possibly because it is a different stage of
   the derivation. Whether `1/(2π)` is original to Du–Selig is unresolved; it is
   consistent across all Yang sources and the code, so it does not affect the
   D-1 finding.
4. **`CD,0` semantics** (`α=0` vs `CL=0`) is a documented, immaterial mismatch
   (`design.md:83-91`); left open as already recorded.

---

## 9. Sources

| # | Source | Access | Used for |
|---|--------|--------|----------|
| 1 | Yang & Sotiropoulos, *A new class of actuator surface models for wind turbines*, arXiv:1702.02108v4, Eq. 11–12 (p. 4) | rendered PDF | as-printed reference |
| 2 | Li, Liu & Yang, *Review of Turbine Parameterization Models for LES of Wind Turbine Wakes*, Energies 15(18):6533, Eq. 21–22, DOI 10.3390/en15186533 | rendered PDF | same-author peer-reviewed form |
| 3 | IOP 2024, *Limitations of lift correction models for thick airfoils*, J. Phys. Conf. Ser. 2767:022029, DOI 10.1088/1742-6596/2767/2/022029 | rendered PDF | original Du–Selig form |
| 4 | Munduate (2002), PhD thesis, Univ. of Glasgow, Eq. 3.5–3.6 | rendered PDF | original Du–Selig form |
| 5 | NREL AirfoilPrep.py (Hansen/Ning), github.com/NLRWindSystems/AirfoilPreppy | source | reference implementation |
| 6 | BYU CCBlade.jl, github.com/byuflowlab/CCBlade.jl | source | reference implementation |
| 7 | Jeong, Yoo & Lee (2012), DOI 10.1142/S2010194512008707 | OCR | corroboration |
| 8 | Du & Selig (1998), AIAA-98-0021, DOI 10.2514/6.1998-21 | **closed — not read** | primary source (unverified) |
| 9 | Yang & Sotiropoulos, Wind Energy 2018, 21(5):285–302, DOI 10.1002/we.2162 | **closed — not read** | published version (unverified) |

Rendered evidence crops live under
`/scratch/leahk/eduardo.donestevez/tmp/ra-formulation/`
(`eq9-12_page4.png`, `eq11_full.png`, `eq12_full.png`, `iop_eq.png`,
`mdpi_eq21.png`, `munduate_p66.png`).
