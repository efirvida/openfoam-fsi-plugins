# IEA 15-240-RWT — OpenFAST + OLAF rated-point reference (P4 tip comparison)

- **Status:** done (reference produced and persisted)
- **Artifacts:** `turbinesFoam/validation/iea15mw/reference/olaf-rated/`
  (gitignored, regenerable with `make_olaf_reference.py`)
- **Produced:** 2026-09-30, OpenFAST **v5.0.0** (GCC 14.3.0, single precision),
  IEA-15-240-RWT-Monopile + OLAF free-vortex wake, rated point.

## Why OLAF and not BEM for the tip

OLAF resolves the wake **explicitly with vortex particles**, so it does **not**
use a Prandtl/Glauert-type tip loss. The BEM path (`AB1N*` in
`IEA-15-240-RWT-Monopile.out`) **does** carry a tip loss internally. Comparing
our ALM tip correction against the BEM tip would be **circular**: it would
recover the Prandtl ansatz that AeroDyn already assumes. OLAF is the
**non-circular** tip reference for P4. OpenFAST is still not CFD: BEM is
algebraic, OLAF is a free vortex wake, ours resolves the wake in the mesh.

## Rotor level (`rotor_summary.csv`)

| model | V (m/s) | rpm | thrust (MN) | torque (MN·m) | Cp | Ct | TSR |
|---|---|---|---|---|---|---|---|
| **OLAF** (free vortex wake) | 10.659 | 7.518 | **2.972** | **24.75** | **0.590** | **0.861** | 8.957 |
| OpenFAST BEM | 10.59 | 7.56 | 2.748 | 19.51 | 0.482 | 0.803 | 9.19 |
| WISDEM (published) | 10.659 | 7.518 | 2.457 | 19.91 | 0.4618 | 0.7718 | 8.913 |

The cross-code spread is wide: OLAF thrust is **+21 %** vs WISDEM and **+8 %**
vs BEM; OLAF torque is **+24 %** vs WISDEM and **+27 %** vs BEM; OLAF Ct is
**+12 %** vs WISDEM. An explicit free wake that resolves the induction
difference (and, likely, a less aggressive induced-velocity deficit) predicts a
substantially higher loading than the two engineering models. **P3's acceptance
band must therefore be stated against BEM and WISDEM, with OLAF as the upper
envelope, not as a narrow target.**

## Spanwise (P4 input)

`spanwise_olaf.csv` / `spanwise_bem.csv` / `spanwise_olaf_vs_bem.csv`: per-node
`r/R + {Vrel, Alpha, Vindx, Vindy, Cn, Ct, Fn, Ft, TnInd, AxInd}` for the 50
`AB1N001..050` nodes, side by side plus `dCn`/`dCt`. r/R from the committed
`data/iea15mw_blade.csv` (projected radius). Key spanwise facts:

- **The tip is where the models disagree most.** At `AB1N050` (r/R = 1.0):
  OLAF `Alpha 6.49` / `Cn 1.14` vs BEM `Alpha 1.21` / `Cn 0.52`. The BEM tip
  node's near-zero alpha is a known BEM/tip-loss artefact — **another reason the
  BEM tip is not a trustworthy target**.
- Inboard (r/R ≈ 0.2–0.4) OLAF and BEM `Cn` agree within ~1 %, while the BEM
  `Vrel`/`Alpha` diverge at the circular root (a force-free region).
- The mid-span (r/R 0.5–0.9) `Cn` tracks within a few percent, with OLAF
  systematically higher and the gap growing toward the tip.

## Use in the campaign

- **P3** (neutral baseline): rotor-level against the WISDEM↔BEM band; spanwise
  `Cn/Ct` shape against both the BEM `AB1N*` channels and OLAF.
- **P4** (D&S tip correction + end effects): compare our **tip** loading against
  **OLAF**, not BEM.
- Regenerate with `python3 reference/olaf-rated/make_olaf_reference.py`; it
  reads the OpenFAST `.out` and overwrites the four CSVs.
