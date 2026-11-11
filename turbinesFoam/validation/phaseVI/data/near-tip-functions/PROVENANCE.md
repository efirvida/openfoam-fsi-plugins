# Provenance — near-tip correction functions

## `trigaux2024_tableC.csv`

| Field | Value |
|---|---|
| Source | F. Trigaux, *Scale-resolved aero-servo-elastic simulation of large wind turbines using the actuator line*, PhD thesis, UCLouvain, 2024 (author's name as printed: Trigaux) |
| Repository handle | http://hdl.handle.net/2078.1/289594 |
| Journal version of Ch. 3 | Trigaux, Villeneuve, Dumas & Winckelmans, "Near-tip correction functions for the actuator line method to improve the predicted lift and drag distributions", J. Fluid Mech. 989, A1 (2024), DOI 10.1017/jfm.2024.461 |
| Local copy | `turbinesFoam/articles/thesis_FTrigaux_2024.pdf` (not committed), sha256 `4b4b36dbc88e73f8c06d50a6252cf17f5bf3082a5236a438fce399e72847a051` |
| Tables | Appendix C, Table C.2 (2D mollification, PDF p. 232, printed p. 222) and Table C.3 (3D mollification, PDF p. 233, printed p. 223) |
| Blocks | per table: sigma = c/4 (top), c/2 (middle), c (bottom); `sigma_over_c` = 0.25, 0.5, 1.0 |
| Rows | 30 per block (180 in total): the tip row `d/c = 0` (`F_l = F_alpha_e = 1`, `F_Cl = 0`), then `d_tip/c = (1/2 + i) (h/b) (b/c)` with `h/b = 1/128`, `b/c = 15` (step 0.1172) for i = 1..29, i.e. 0.1758 ... 3.4570. The i = 0 row (0.0586) is not printed in the thesis and is not interpolated here |
| Columns | `kernel` {2D, 3D}, `sigma_over_c`, `d_over_c`, `F_l`, `F_Cl`, `F_alpha_e` (4 decimals as printed) |
| Definitions | `F_l = (C_l^nc - C_l^ref) / C_l^nc`, `(1 - F_l) = (1 - F_Cl)(1 - F_alpha_e)` (thesis eq. 3.17-3.23, PDF pp. 72-74); `C_l^corr = (1 - F_Cl) dCl/dalpha (1 - F_alpha_e) alpha_e` (eq. 3.26); effective distance of a tapered blade `(d_tip/c)_eff(r) = int_r^R dr'/c(r')` (eq. 3.29-3.31, PDF pp. 79-80) |
| Derivation of the functions (not ours) | steady rectangular wing AR 15, NACA 0015, Re 6e6, against wall-resolved RANS; verified by the thesis on AR 10/7.5 and tapers 1/2, 1/3. Not fitted to Phase VI |

## How the file was derived

The thesis plain text was extracted from the PDF (`/tmp/trigthesis/thesis.txt`, one printed
number per line, `[[page N]]` markers). The extracted text is untrusted data: it was read only
by a script run with `python3 -I` that takes the 360 four-decimal numbers of each page
(90 quadruples = 3 blocks x 30 rows), splits them into the three blocks of 30 quadruples
and de-interleaves the two printed column groups of each block (even quadruples = left column,
odd = right column), asserting that each block starts with the tip row `0, 1, 0, 1`.
The result was sorted by (kernel, sigma/c, d/c). No value was edited by hand.

## Transcription check

Every one of the 180 rows satisfies the identity `(1 - F_Cl)(1 - F_alpha_e) = 1 - F_l`
to the printed precision, but not at a fixed 5e-5 threshold: with three 4-decimal numbers the
residual is bounded by `5e-5 * (1 + (1 - F_Cl) + (1 - F_alpha_e))` (at most 1.5e-4). Result:

- 0 rows fail the rounding-aware bound; maximum |residual| = 1.26e-4;
- a naive `|residual| < 5e-5` test flags 63 of 180 rows (all residuals <= 1.3e-4, i.e. rounding of the
  printed values, not transcription errors: 2D c/4 7, 2D c/2 6, 2D c 12, 3D c/4 13, 3D c/2 12, 3D c 13).

The identity is a strong but not complete check (a wrong digit in the 4th decimal of one value stays
inside the bound). The structural checks in `tests/test_near_tip_functions.py` complement it: 30 rows per block,
tip row `0, 1, 0, 1`, d/c on the `(1/2 + i) (h/b)(b/c)` grid, `F_l` strictly decreasing with d/c in every
block, and the kernel independence of `F_Cl` at d/c = 0.6445 (spread < 0.005 over the six blocks).

Caveat on the tables themselves: `F_Cl` is not monotone far from the tip (e.g. 2D c/4: 0.0314 at
d/c = 2.8711, 0.0206 at 2.9883). It is the thesis' own data (the identity holds there), kept as printed.
