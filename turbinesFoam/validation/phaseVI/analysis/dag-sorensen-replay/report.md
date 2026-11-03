# Dag & Sorensen replay on frozen ALM S U7 element states (T7)

Tool `scripts/replayDagSorensen.py`, tests `tests/test_replay_dag_sorensen.py`. Run:
`alm-U7-coarse-seqS-var-tip-pitch-dag-sorensen-total`, written time t = 10.018 s (lagged state
t = 10.017 s), two blades, 84 elements/blade, projection width 0.64-1.28 m (mesh-based,
6 674 304 cells = the polyMesh cell count). Outputs: `U7-t10.018/` (table + JSON), `U7-t9.000/`
(second time, same conclusions), `validation-*.{json,log}`.

## What the CSV contains

* `alpha_deg`: angle of the CORRECTED relative velocity (sampled inflow + w - blade velocity),
  after `flowCurvature` (off), before nothing else (rotational augmentation, dynamic stall, added
  mass all off in this case). `alpha_geom_deg`: angle of `freestream - blade velocity`, no induction
  at all. The uncorrected angle is not written, so `rel0 = rel_csv(t) - w_replica(t)`; the
  as-implemented replay therefore reproduces the CSV by construction (alpha to 4e-8 deg,
  C_L to 1e-10, C_D to 6e-12 at r/R >= 0.5, which also confirms the polar chain incl. the Re drag
  correction of `profileData::updateRe`). Only the DEVIATIONS carry information.
* The correction applied at step t is computed from the relative velocity and C_L of step t-1.

## Validation of the replica (before any deviation was evaluated)

Local solver run (OpenFOAM v2506, private `libturbinesFoam` built from HEAD in `/tmp`, never in
`$FOAM_USER_LIBBIN`), `tests/tipCorrection/rotor` + `debug true`, 4 steps, `tests/dagSorensenReplayCase`.

| case | tip corr, rel. error | max corr, rel. error | argmax element | per-element on/off check (rel. to max w) |
|---|---|---|---|---|
| meshEps (eps 0.4 m, 1 blade) | <= 1.8e-5 | <= 7.5e-6 | 5 = 5 | 2.6e-4 |
| eps006 (eps 0.06 m, 1 blade) | <= 1.4e-5 | <= 1.7e-5 | 5 = 5 | 4.2e-5 |
| twoBlade (eps 0.4 m, blade 2 = blade 1 turned 180 deg) | <= 2.4e-4 | <= 1.1e-4 | 5 = 5 | 1.8e-3 |

Tolerance stated: 1e-4 (one blade), 1e-3 (two blades); limited by the six-digit CSV/debug output. The
check resolves the switches: smoothing off, sweep reversed and tip-hold each exceed the tolerance
by >100x on the same data (test `test_replica_rejects_the_wrong_switch_sets`).
NOT validated against the solver: the production mesh epsilon (checked only through the cell count
and the identities above), and the production S809/cylinder two-profile blade.

## Results at t = 10.018 (changes are relative to the as-implemented set)

| switch | r/R | w_axial | w_tang | alpha | d alpha | cl | d cl | d c_n | d c_n % | d c_n,q % |
|---|---|---|---|---|---|---|---|---|---|---|
| as-implemented | 0.8 | -0.067 | +0.010 | 6.251 | +0.000 | 0.7979 | +0.0000 | +0.0000 | +0.00 | +0.00 |
| as-implemented | 0.9 | -0.331 | +0.042 | 5.845 | +0.000 | 0.7594 | +0.0000 | +0.0000 | +0.00 | +0.00 |
| as-implemented | 0.95 | -1.137 | +0.148 | 4.838 | +0.000 | 0.6386 | +0.0000 | +0.0000 | +0.00 | +0.00 |
| as-implemented | 0.98 | -2.911 | +0.388 | 2.363 | +0.000 | 0.3351 | +0.0000 | +0.0000 | +0.00 | +0.00 |
| a:no-smooth | 0.8 | -0.090 | +0.013 | 6.210 | -0.041 | 0.7958 | -0.0021 | -0.0021 | -0.26 | -0.31 |
| a:no-smooth | 0.9 | -0.752 | +0.103 | 5.173 | -0.672 | 0.6787 | -0.0806 | -0.0796 | -10.52 | -11.18 |
| a:no-smooth | 0.95 | -1.260 | +0.148 | 4.645 | -0.193 | 0.6154 | -0.0232 | -0.0230 | -3.61 | -3.71 |
| a:no-smooth | 0.98 | +0.069 | +0.025 | 6.822 | +4.459 | 0.8278 | +0.4927 | +0.4882 | +145.64 | +155.61 |
| b:fixed-point | 0.8 | -0.067 | +0.010 | 6.251 | +0.000 | 0.7979 | +0.0000 | +0.0000 | +0.00 | +0.00 |
| b:fixed-point | 0.9 | -0.331 | +0.042 | 5.844 | -0.000 | 0.7593 | -0.0001 | -0.0001 | -0.01 | -0.01 |
| b:fixed-point | 0.95 | -1.138 | +0.148 | 4.837 | -0.001 | 0.6384 | -0.0002 | -0.0002 | -0.02 | -0.03 |
| b:fixed-point | 0.98 | -2.913 | +0.388 | 2.360 | -0.003 | 0.3348 | -0.0004 | -0.0004 | -0.10 | -0.11 |
| c:sweep-reversed | 0.8 | +0.073 | +0.011 | 6.505 | +0.254 | 0.8112 | +0.0133 | +0.0130 | +1.63 | +1.80 |
| c:sweep-reversed | 0.9 | +0.345 | +0.044 | 6.944 | +1.099 | 0.8342 | +0.0748 | +0.0732 | +9.68 | +10.42 |
| c:sweep-reversed | 0.95 | +1.167 | +0.152 | 8.404 | +3.566 | 0.9037 | +0.2652 | +0.2600 | +40.82 | +43.89 |
| c:sweep-reversed | 0.98 | +2.989 | +0.398 | 11.262 | +8.900 | 0.9455 | +0.6104 | +0.5988 | +178.64 | +193.86 |
| d:tip-hold | 0.8 | -0.067 | +0.010 | 6.251 | -0.000 | 0.7979 | -0.0000 | -0.0000 | -0.00 | +0.00 |
| d:tip-hold | 0.9 | -0.332 | +0.037 | 5.842 | -0.003 | 0.7591 | -0.0003 | -0.0003 | -0.04 | -0.01 |
| d:tip-hold | 0.95 | -1.139 | +0.129 | 4.830 | -0.008 | 0.6376 | -0.0010 | -0.0009 | -0.15 | -0.05 |
| d:tip-hold | 0.98 | -2.921 | +0.341 | 2.341 | -0.022 | 0.3326 | -0.0025 | -0.0025 | -0.76 | -0.52 |
| a:no-smooth+b:fixed-point | 0.8 | -0.120 | +0.019 | 6.158 | -0.093 | 0.7930 | -0.0049 | -0.0047 | -0.60 | -0.72 |
| a:no-smooth+b:fixed-point | 0.9 | -0.476 | +0.066 | 5.615 | -0.230 | 0.7317 | -0.0276 | -0.0272 | -3.60 | -3.86 |
| a:no-smooth+b:fixed-point | 0.95 | -1.036 | +0.139 | 4.994 | +0.156 | 0.6572 | +0.0187 | +0.0185 | +2.90 | +3.03 |
| a:no-smooth+b:fixed-point | 0.98 | -1.749 | +0.246 | 4.123 | +1.760 | 0.5521 | +0.2170 | +0.2161 | +64.47 | +66.76 |
| no-correction | 0.8 | +0.000 | +0.000 | 6.369 | +0.118 | 0.8041 | +0.0062 | +0.0061 | +0.76 | +0.91 |
| no-correction | 0.9 | +0.000 | +0.000 | 6.372 | +0.527 | 0.8042 | +0.0449 | +0.0440 | +5.82 | +6.42 |
| no-correction | 0.95 | +0.000 | +0.000 | 6.567 | +1.729 | 0.8144 | +0.1759 | +0.1733 | +27.21 | +29.48 |
| no-correction | 0.98 | +0.000 | +0.000 | 6.711 | +4.349 | 0.8220 | +0.4869 | +0.4825 | +143.96 | +154.03 |

`c_n = cl cos(alpha) + cd sin(alpha)` (chord-referenced, local dynamic pressure); `c_n,q` is the same
scaled by `|rel|^2 / (U_inf^2 + (omega r)^2)`, the normalisation of the experiment. `no-correction` is
`w = 0` (what the solver would use without D&S). Convergence: `b` 17 iterations (relax 1), `a+b`
184 iterations (relax 0.5); radial part of w <= 0.02 % of |rel|, w <= 9 % of |rel| at r/R >= 0.5.

## Reading

* The whole as-implemented correction removes 27.2 % of c_n at 0.95 (alpha 6.57 -> 4.84 deg).
* (b) one lagged pass vs fixed point: -0.025 % at 0.95 (t = 9.0: +0.001 %). The time-marched lagged
  scheme IS the fixed-point iteration, and the written state is already converged. No effect.
  (Undamped iteration of the whole blade in the frozen state is a period-3 cycle at the root stall
  region; with r/R < 0.5 frozen it contracts in 17 iterations.)
* (c) sweepSign as implemented is the physical one: w_axial = -1.14 m/s at 0.95 reduces the inflow
  angle (Eq. 21/26: u_x + w_x, alpha down by 1.73 deg); reversed gives +1.17 m/s, alpha +3.57 deg,
  c_n +40.8 %. Right for axis -x and axis +x (unit test). Not a source of the residual.
* (d) hold instead of 1.5/-0.5 extrapolation at the tip station: -0.15 % at 0.95 (-0.76 % at 0.98). Nothing.
* (a) smoothing: removing it in ONE pass on the smoothed state gives -3.6 % at 0.95 but is not
  self-consistent (the lagged Gamma was produced under smoothing). The self-consistent unsmoothed
  solution (a + b) gives +2.9 % c_n at 0.95 (+2.4 % at t = 9.0), -0.6 % at 0.80, -3.6 % at 0.90 and
  +64 % at 0.98, i.e. the smoothing makes the correction STRONGER at 0.95, and the paper form would
  raise the 0.95 error, not lower it.
* None of the three deviations explains the 6.4-8.9 pp ALM-specific residual. That is 5.1-7.1 % of the
  as-implemented c_n, i.e. an extra alpha of about -0.3 to -0.45 deg (extra w_axial about -0.2 to -0.3 m/s,
  18-26 % more correction), by linear scaling of the no-correction -> as-implemented response.

## Assumptions and caveats

* Frozen CFD inflow: the response of the flow field to a changed force is not modelled (it would
  partly offset the change). These are first-order, same-step predictions.
* Blade 2 is blade 1 turned by 180 deg (no CSV for blade 2): bounded by the twoBlade validation, 2.4e-4.
* In-plane relative velocity from `rel_vel_mag`, `alpha_deg` and `alpha_geom_deg`; radial part of w
  neglected in the frame (second order, measured above). End-effect factor frozen (1.0 at r/R >= 0.8).
* r/R stations are linear interpolations between the element centres (0.0099 R apart).
* `--compare-run` (same case without D&S, 200-step mean): alpha(D&S) - alpha(no D&S) = -0.43 / -0.88 /
  -2.02 / -4.57 deg at 0.80 / 0.90 / 0.95 / 0.98 against the replica's -0.12 / -0.53 / -1.73 / -4.35
  from w alone; plausibility only (different flow, averaging window).
