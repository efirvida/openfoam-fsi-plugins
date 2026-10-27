# Phase VI ALM — physics diagnosis before more runs (2026-10-23)

> **Note 2026-10-27 (T11, `odd/tasks/v13-adoption-asm.md`):** the in-house BEM (`bemPhaseVI.py`) numbers quoted
> in this record carry the root-polar defect (S809 applied over the cylinder r < 1.0675 m; power only, normal
> loads unaffected within ~1 pp). The AeroDyn BEM (L11 of that file) supersedes them and the script was removed.

Deliverable of `odd/tasks/phasevi-physics-review.md` T6. Read-only diagnosis: no coefficient changed, no CFD run.
Scripts and outputs (git-ignored, main-checkout `runs/`): `turbinesFoam/validation/phaseVI/runs/physics-review-scripts/`
(`bem_matrix.py` -> `bem-matrix-20261023.txt`, `polar_osu_dut.py` -> `polar-osu-dut-20261023.txt`) and
`runs/tip-pitch-2x2-20261023/fixed-twist/` (section loads with the corrected twist inverse, commit 3c46a6d).

## Answer in one paragraph

The speed-dependent error has three separable sources, and the U7 match is a cancellation between them.
(1) **Blade geometry**: the 1.815 deg pitch-reference error (measured, NREL definition) loads every station at
every speed; with it fixed, a BEM on the same inputs is within -1..-8 % of the measured power at 5-8 m/s.
(2) **The ALM tip treatment**, which is ALM-specific: inboard of r/R 0.63 the ALM and the BEM agree on alpha
within 0.2 deg at every speed, but outboard the ALM sees 0.3-2.8 deg MORE alpha (too little induction from a
kernel 0.9-1.65 chords wide) and then multiplies cl by a full Glauert factor. The two errors cancel at high TSR
and not at low TSR: this is the remaining U5-U8 slope (ALM tip+total -4.5 % -> -21.7 %, BEM -3.7 % -> -7.6 %).
The literature names exactly this configuration as wrong (Jha et al. 2014). (3) **Shared 2D inputs**: the
missing 3D stall delay under-loads r/R 0.30-0.47 at 8 m/s in both ALM and BEM, and the OSU polar has 0.07-0.08
less lift than the DUT polar (same report, Table A-8) at the 2-5 deg where 5 m/s operates.

## Evidence

### E1. BEM on the ALM's inputs (Prandtl tip on, measured rpm and rho; power error vs ROTPOW %)

| drag, pitch reference | 5 m/s | 6 m/s | 7 m/s | 8 m/s | spread 5-8 |
| --- | --- | --- | --- | --- | --- |
| pressure, v1.2 (twist-zero) | +20.6 | +12.7 | +5.4 | -4.4 | 25.0 |
| total, tip chord | -3.7 | -1.3 | -1.2 | -7.6 | 3.9 |
| ALM v1.2 (for reference) | +26.5 | +13.5 | -2.1 | -19.9 | 46.4 |
| ALM tip + total | -4.5 | not run | not run | -21.7 | 17.2 |

The BEM spread nearly vanishes with the geometry fixed; the ALM keeps 17 pp. So the remaining slope is not in
the polar, the pitch or the momentum balance: it is in how the ALM loads the outer blade.

### E2. ALM vs BEM per station (tip pitch, pressure polar; alpha in deg, ALM cl includes the Glauert factor F)

| r/R | U5 alpha ALM / BEM | U5 cl ALM / BEM | U7 alpha | U7 cl | U8 alpha | U8 cl |
| --- | --- | --- | --- | --- | --- | --- |
| 0.30 | 2.09 / 2.58 | 0.30 / 0.36 | 8.44 / 8.26 | 0.90 / 0.90 | 12.12 / 11.92 | 0.95 / 0.96 |
| 0.47 | 3.74 / 3.67 | 0.50 / 0.50 | 8.48 / 8.45 | 0.90 / 0.91 | 11.42 / 11.49 | 0.93 / 0.94 |
| 0.63 | 3.69 / 3.57 | 0.49 / 0.48 | 7.55 / 7.34 | 0.84 / 0.86 | 9.86 / 9.64 | 0.89 / 0.93 |
| 0.80 | 3.40 / 3.11 | 0.43 / 0.43 | 6.67 / 5.94 | 0.70 / 0.77 | 8.52 / 7.65 | 0.74 / 0.87 |
| 0.95 | 3.84 / 2.49 | 0.30 / 0.35 | 6.88 / 4.59 | 0.41 / 0.61 | 8.47 / 5.69 | 0.42 / 0.74 |

Midspan agreement rules out a global under-induction of the ALM (hypothesis L-impl #1 refuted inboard of 0.63).
The outboard alpha excess grows from 1.35 to 2.8 deg at 0.95 as TSR falls, and the Glauert factor (0.60 at
U5, 0.48 at U8 at 0.95; implemented with the arc fraction, +2..5 % too large) does not track it.

### E3. The tip treatment decides the outer blade (existing S arms, v1.2 pitch; dR % at r/R 0.80 / 0.95, station torque)

| arm | U5 | U8 |
| --- | --- | --- |
| Glauert on cl (v1.2) | +18.6 / +16.5, +20.8 % | -10.3 / -30.6, -16.1 % |
| D&S induced-velocity correction **plus** Glauert (`dag-sorensen-tip`) | +17.6 / +3.0, +14.4 % | -10.0 / -28.8, -16.6 % |
| Shen F1 instead of Glauert (`shen-tip`) | +22.7 / +52.0, +27.2 % | +8.5 / +23.2, -0.5 % |

D&S lowers the U8 tip alpha by 1.3 deg (10.25 -> 8.95), the right direction, but the registered arm keeps the
Glauert factor on top (`config/model-variants.yaml:15` "Retains Glauert"), so the tip correction is applied
twice. No arm on disk tests the consistent combination: a velocity-side correction with no cl-side factor.

### E4. Literature (text in `runs/articles-text-20261023/`)

- Jha, Churchfield, Moriarty, Schmitz, J. Sol. Energy Eng. 136:031003 (2014), p.6, Phase VI 7 m/s: constant
  eps = 2 dx over-predicts tip AoA and loads; adding Prandtl on the coefficients "leads to an underprediction of
  the blade tip loads" and of power; "there should be no need for using the Prandtl correction within the ALM
  framework". Their remedy is an elliptic chord-scaled eps (eps/c* constant, actuator spacing >= 1.25 dx).
- Dag & Sorensen, Wind Energy (2019/2020), abstract: large projection widths give too large tip loads; their
  correction acts on the induced velocity. Meyer Forsting et al. (2019, 2020 WES): the smearing correction
  "recovers this missing induction". Both replace, not complement, a tip-loss factor.
- Martinez-Tossas et al., Wind Energy (2017), abstract: optimal eps is 14-25 % of the chord. Ours is 88-165 %.
- Ouakki & Arbaoui, J. Renew. Sustain. Energy (2022), p.15: of the two Re 1e6 S809 data sets "The DUT
  measurements show better agreement with 3D data" (Phase VI at r/R 0.8); they use DUT as baseline.
- Churchfield et al. 2017 (NREL 67611): AL eps = 0.235 m with point sampling over-predicts Phase VI tip loads;
  our eps is 2.7 times larger.

### E5. Polar sources (TP-500-29955 Tables A-7 OSU vs A-8 DUT, Re 1e6)

DUT - OSU lift: +0.08 at 2-3 deg (+19..+29 %), +0.068 at 4 deg (+13 %), +0.055 at 6-8 deg (+6..+7 %),
+0.02-0.03 at 10-14 deg (+2..+3 %). Zero-lift angle -0.64 (OSU) vs -1.2 deg (DUT); same slope. At tip pitch the
U5 midspan BEM and ALM sections are -8..-12 % low, where DUT adds +13..+16 %; at U8 inboard (10-14 deg) DUT adds
only +2..+3 %, so the inboard U8 deficit (-13..-21 %) stays a stall-delay matter.

### E6. Reference side (lane L-ref)

The experiment's own torques differ: LSSTQCOR / EAEROTQ = 0.95 (5 m/s) ... 1.034 (8 m/s), about 8 pp of
slope inside the reference. Comparing like with like (five-station sums) removes ~9 of the 46 pp. Blockage
(< 2 %, wrong sign) and nominal vs VTUN speed (+0.2..0.8 %) are small. Numerical independence is shown only at
H 7 m/s (dt, mesh level 1; level 2 not analysed).

## Why U7 looked right

At v1.2, U7 runs at alpha 7-9 deg midspan, on the knee of the OSU polar where the +1.8 deg pitch error costs
little lift, and its tip under-load (0.95: -12 %) offsets a small midspan surplus. Neither error is absent at U7:
they cancel there by position on the polar.

## Implementation and definition items found (not fixed here)

1. Glauert tip argument uses the arc fraction from the root instead of r/R (`axialFlowTurbineALSource.C:659`
   vs `actuatorLineSource.C:323`): +2..5 % cl outboard. C++ change, needs a library rebuild and breaks v1.2
   reproducibility; becomes moot if the cl-side tip factor is removed.
2. `dag-sorensen-tip` arm stacks D&S with Glauert (definition defect of the arm, renderer-only fix).
3. Polar choice OSU vs DUT is a definition decision (both are in the report; literature favours DUT for Phase VI).
4. `scripts/bemPhaseVI.py:17` uses the old pitch convention (`--pitch 4.815` reproduces the tip reference).
5. Transition region r 1.06-1.26 m runs the S809 polar on non-S809 sections (2-3 % of torque).

## Proposed run plan (replaces "run the three v1.3 options" as stated; owner decides)

The three options A/B/C differ only in pitch and drag, whose effect E1 already predicts (BEM); running them at
U6/U7/H7 would mostly confirm the BEM. The open physics is the tip treatment. Proposed matrix, all with tip
pitch (geometry correction), Sequence S U5 and U8 first (the extremes), 24/12 rev as before:

| arm | tip treatment | polar | question |
| --- | --- | --- | --- |
| P1 | Glauert on cl (current) | OSU total | baseline of A (exists: `var-tip-pitch-total`) |
| P2 | D&S correction, Glauert tip off (root kept) | OSU total | does the velocity-side correction alone close the U8 tip? |
| P3 | no tip correction | OSU total | Jha's statement on our mesh: size of the tip over-load |
| P4 | best of P2/P3 | DUT (A-8 + same extension) | polar source at U5 midspan |

P2/P3 render with existing flags (`generate_case.py --tip-effects`, `--tip-correction`, `tools/generate_case.py:1282,1298`).
P4 needs a DUT `.dat` that does not exist yet: `buildPolars.py` writes OSU only (`:359` "Not blended with ... DUT"),
so P4 needs a small tested polar-builder change first.

Then U6/U7 and H7 only for the winning definition (the R2 gate), and RA arms on that definition for the U8
inboard deficit. A chord-scaled or finer eps (Jha, Martinez-Tossas) is the structural fix and needs a mesh
decision (cost), so it is listed, not proposed first.
