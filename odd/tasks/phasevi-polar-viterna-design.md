# Design — Viterna–Corrigan post-stall branch for the S809 polars

Feature: `phasevi-polar-viterna` · Branch: `feat/dagsorensen-tip-correction` ·
Date: 2026-09-30.

Companion evidence: `odd/tasks/phasevi-fllt-feasibility.md` and
`campaign-results/RESULTS.md` (the Dağ & Sørensen section). Those records show
that at 7 m/s the corrected ALM arms still leave the tip `c_ref_n` ≈ +54 % and
the inboard (`r/R = 0.30`) ≈ +25 % over experiment, and that the committed polar
is the prime suspect.

Status: read-only analysis plus NEW derived artifacts. No existing `*.dat` file,
`scripts/runPhaseVI.sh`, or `tools/generate_case.py` is touched — running
Phase VI Slurm jobs read the committed `*_total.dat` files live.

---

## 1. Problem

`S809_OSU_Re1M_total.dat` is measured (TP-500-29955 Table A-7) only to
`alpha = +26.1 deg`. Beyond that the committed file pastes **CSU Table A-3**
rows, which are **Re = 0.3e6** — a 3.3x Reynolds step whose high-alpha shape is
the measured CSU post-stall curve, not a flat-plate closure as the file header
claims. The lower-Re CSU variant `S809_CSU_Re0.65M_total.dat` has the mirror
problem on its **negative** side: Table A-5 measures only to `alpha = -0.25 deg`
and the committed file fills everything below it with the same Re = 0.3e6
Table A-3 data.

This task replaces **only the beyond-measurement rows** of those two polars with
a Viterna–Corrigan (1982) post-stall branch, emitted as two NEW files:

- `data/polars/S809_OSU_Re1M_viterna.dat`
- `data/polars/S809_CSU_Re0.65M_viterna.dat`

The measured rows are byte-identical to the committed files; the files keep the
`profileData` flat-list format `(alpha_deg Cl Cd Cm)` and the same `-180..180`
alpha range.

---

## 2. Reynolds anchors

| New file | Re anchor | Measured source | Measured alpha range |
|---|---|---|---|
| `S809_OSU_Re1M_viterna.dat` | `1.0e6` | TP-500-29955 Table A-7 (OSU, total drag `Cdw`→`Cdp`) | `[-20.1, +26.1]` |
| `S809_CSU_Re0.65M_viterna.dat` | `0.65e6` | TP-500-29955 Table A-5 (CSU, pressure drag `Cdp`) | `[-0.25, +90.2]` |

The operating Re at 7 m/s is ≈ `0.43e6` inboard to ≈ `0.94e6` at `r/R = 0.7`, so
these two levels bracket the simulation. `S809_OSU_Re1M_total.dat` remains the
committed baseline; the Viterna files are opt-in ablation polars.

---

## 3. Stall point and blend anchor, per Re

Viterna–Corrigan is defined from a stall point `(a_s, CL_s, CD_s)`. Each
measured table already carries post-stall data, so there are two candidate
anchors:

| File / side | max-CL **stall point** (`alpha`, CL, CD) | **blend anchor** used (`alpha`, CL, CD) |
|---|---|---|
| OSU `+` | `15.2`, `1.03`, `0.0705` | `26.1`, `0.91`, `0.5356` |
| OSU `-` | `-16.2`, `-0.80`, `0.1826` (magnitude); first negative lift break | `-20.1`, `-0.55`, `0.2983` |
| CSU `+` | `16.0`, `0.928`, `0.107` (lift break; a post-stall peak sits at `40 deg`, CL `1.12`) | none — the table already reaches `90.2 deg` |
| CSU `-` | none measured (Table A-5 starts at `-0.25`, CL `+0.151`) | `-0.25`, `+0.151`, `0.002` |

**Decision — anchor at the outermost measured sample, not at the interior
max-CL stall point.** The branch is re-anchored at the last measured sample on
each side (the *blend point*) and emitted on the same angle grid the committed
extension used. This is required, not cosmetic:

1. **Continuity.** The measured rows must stay byte-identical, so the branch can
   only be appended beyond the table. Anchoring an interior stall point would
   leave the branch discontinuous at the table edge, e.g. OSU `+`: measured
   `CD(26.1) = 0.5356` but the true-stall Viterna branch gives `CD(26.1) = 0.21`
   — a 0.33 drop across one row, and a non-physical dip in `CD`.
2. **Defined domain.** CSU `-` measures only to `-0.25`; the emitted negative
   grid starts at `-1.99`. An interior anchor (`-16`) would leave the whole
   `[-16, -0.25]` interval outside the Viterna domain `[a_s, 90]`.

The interior max-CL stall points are recorded above for traceability, and the
anchor is guaranteed past the lift break on the OSU `+` side (`26.1 > 15.2`) and
on the OSU `-` side (`20.1 > 16.2`). The CSU `-` anchor is pre-stall; see the
limitations in §6.

---

## 4. Viterna–Corrigan branch

Implemented as `viterna_extrapolation(alpha_s_deg, cl_s, cd_s, alpha_deg,
aspect_ratio=0.0)` in `scripts/buildPolars.py`. With angles in degrees converted
to radians:

```
B1 = 1.11 + 0.018*AR
A1 = B1 / 2
A2 = (CL_s - B1*sin(a_s)*cos(a_s)) * sin(a_s) / cos^2(a_s)
B2 = (CD_s - B1*sin^2(a_s)) / cos(a_s)

CL(a) = A1*sin(2a) + A2*cos^2(a)/sin(a)
CD(a) = B1*sin^2(a) + B2*cos(a)
```

`A2` is the same as the task's `(CL_s - A1*sin(2 a_s))*sin(a_s)/cos^2(a_s)`
because `A1*sin(2 a_s) = B1*sin(a_s)*cos(a_s)`. The negative side mirrors the
branch: `CL(-a) = -CL(a)`, `CD(-a) = +CD(a)`.

Constants actually used (AR term dropped, `B1 = 1.11`):

| Anchor | A1 | A2 | B1 | B2 |
|---|---|---|---|---|
| OSU `+` `(26.1, 0.91, 0.5356)` | 0.555000 | 0.257195 | 1.11 | 0.357187 |
| OSU `-` `(20.1, 0.55, 0.2983)` | 0.555000 | 0.074730 | 1.11 | 0.178051 |
| CSU `-` `(0.25, -0.151, 0.002)` | 0.555000 | -0.000680 | 1.11 | 0.001979 |

### 4.1 Aspect-ratio factor

The reference flat-plate term is `B1 = 1.11 + 0.018*AR`. This is a **finite
3-D wing** correction; the S809 tables are **2-D airfoil section** polars and
`profileData` consumes a 2-D section polar, so the finite-aspect-ratio term is
not applicable and is dropped: `B1 = 1.11`, the planar/2-D flat-plate baseline.
Taking `AR -> infinity` literally in `1.11 + 0.018*AR` is undefined (`B1`
diverges), so the task's "AR -> infinity" phrasing is read as "take the
AR-independent limit", which is what dropping the term does. `B1` is exposed as
`VITERNA_B1_2D` and asserted by the tests.

### 4.2 Continuity / blend treatment

No transform is applied to the measured rows. The branch is anchored so that
`viterna(a_s) = (CL_s, CD_s)` exactly at the blend point on each side; the
emitted first extension row is the same branch evaluated one grid step further
(e.g. OSU `+`: `26.1 -> 26.2`, `CL 0.91 -> 0.9087`, `CD 0.5356 -> 0.5369`).
Continuity is therefore exact at the junction and monotone across it.

### 4.3 Beyond the Viterna range

Viterna–Corrigan is valid only up to `|alpha| = 90 deg`. The committed
flat-plate closure at `+-120/150/180 deg` is retained unchanged so the files
keep the same alpha range and `profileData` never reads outside the table. That
closure is outside the Viterna model and is not claimed to be physical; the
pre-existing `90 -> 120 deg` step is not addressed here.

---

## 5. Emitted shape (eyeball)

`S809_OSU_Re1M_viterna.dat`, positive branch:

```
(26.1 0.91 0.5356 -0.1783)   measured edge
(26.2 0.908707 0.536858 0)   Viterna
(30.2 0.864497 0.58957 0)
(45.2 0.734954 0.81056 0)
(60   0.55489  1.01109 0)
(90   6.8e-17  1.11    0)
```

Negative branch mirrors (`CL` odd, `CD` even), and the CSU variant fills its
unmeasured negative side the same way (`-1.99: CL -0.019, CD 0.0033;
-30.2: CL -0.482, CD 0.283; -90: CL ~0, CD 1.11`).

---

## 6. Limitations (explicit)

1. **Viterna–Corrigan is an empirical post-stall engineering model, not measured
   data.** It is a smooth engineering branch fitted to a stall point; it is not
   the S809 post-stall flow physics and must not be cited as measurement.
2. **The anchor is the measured table edge, not the classic max-CL stall
   angle.** It is used because the measured table already contains post-stall
   data (continuity requirement, §3). The branch therefore continues the
   measured post-stall trend rather than re-deriving it.
3. **The CSU `-` anchor is pre-stall** (`-0.25 deg`), because Table A-5 has no
   negative post-stall data. The resulting branch is a flat-plate-like
   extension (peak `|CL| ~ 0.55` near `-45 deg`); a measured S809 negative
   post-stall curve would be preferable.
4. **`B1 = 1.11` is low** relative to the measured deep-stall drag (`CSU A-3`
   `CD(90 deg) = 2.24`). The AR term is the reference's knob for this; it is
   left at the 2-D baseline and the discrepancy is accepted.
5. **The near-90 deg `CD` maximum is shallow but not monotone.** For the OSU
   anchors `CD` peaks a few percent above `B1` around `80 deg` and settles to
   `B1` at `90 deg`. This is an intrinsic feature of the `B1 sin^2 + B2 cos`
   form with `B2 > 0`; the tests assert monotonicity through `80 deg` and
   finiteness at `90 deg`, not strict monotonicity to `90`.
6. **Deep (`|alpha| > 90 deg`) closure is unchanged** from the committed
   flat-plate rows and is not part of the model.

---

## 7. Verification

- `scripts/buildPolars.py --viterna-only` writes only the two new files
  (`--check` validates them; `--check` alone still validates the three committed
  polars against their `*_total.dat` renders and does not write).
- `tests/test_phasevi_data.py` adds: measured-row byte preservation, blend-point
  continuity, `CL(+-90) ~ 0` / `CD(+-90)` finite + monotone to `80 deg`,
  negative-branch mirroring, row count/format/sorting, and a sha256 guard that
  the two original committed polars are byte-unchanged.
- Manual: rebuild with
  `python scripts/buildPolars.py --viterna-only` from
  `turbinesFoam/validation/phaseVI/`.
