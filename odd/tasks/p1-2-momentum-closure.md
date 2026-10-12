# P1.2 — Momentum-balance closure (Madsen 1988)

Plan: `odd/tasks/validation-master-plan.md` (P1.2). Source: Madsen 1988 (IEA 2nd symposium,
ch. 4): `dT = 2 rho V^2 a (1-a) dA` is the basis of BEM, "never proved", degrades with
loading and with the radial load gradient. So the output is a QUANTIFIED ratio per radius,
not a pass/fail, and its limits are stated with the number.

Data already on disk (no new simulation): `validation/phaseVI/runs/alm-U7-coarse-r2`
(U at t=3.339, 231 processors, ~11 M cells; rotor axis (-1 0 0), origin (0 0 12.192),
R = 5.029 m, U_inf = 7 m/s; element CSVs have `root_dist`, `fx`).

Definitions: `a(r)` from the azimuthally averaged axial velocity on a plane at the disc,
`a = 1 - u_x/U_inf`; annulus thrust = sum over blades of the axial element force per
unit radius (blade force, so `+fx` along the wind) averaged over the last revolution;
theory thrust per unit radius = `2 rho U_inf^2 a (1-a) 2 pi r`. Sampling planes: disc plane and
upstream planes (x/R = -0.25, -1) to show the sensitivity to where a is read.

- [x] **S1** Analysis tool `validation/tools/induction_closure.py` + unit tests with
      synthetic data (RED first: a field built from a known `a` and the exact force
      must give ratio 1; a wrong force must not). Registered in `validation/tools/README.md`.
- [x] **S2** Sample U of `alm-U7-coarse-r2` (reconstruct latest time, sample the planes with
      a committed script/dict, not an inline command).
- [x] **S3** Run the tool, record the table (ratio per r/R, plane sensitivity, total thrust
      vs the turbine CSV) and the limits in the master plan.
- [x] **S4** Plan + commit. Repeat on the IEA L2 platform only if its U is on disk
      (otherwise listed as open for P3).

Result and limits: see the 2026-10-12 P1.2 row of the master plan log. Sampling is reproducible with
`induction_closure.py write-dict` (rings written to `system/inductionClosureSample`), `reconstructPar -latestTime -fields '(U)'`
in a work dir of symlinked `processor*`, then `postProcess -func inductionClosureSample -latestTime` (about 4 + 2 min on the login node).
IEA L2 platform: NOT measured. Its U is on disk (`iea15mw/runs/iea15mw-l2-ctrl`, t = 183.5592, also `-ds`; the element CSV layout and
`--elements-per-segment` for its 147 elements still have to be established), so it is an open extension, not a data gap.
