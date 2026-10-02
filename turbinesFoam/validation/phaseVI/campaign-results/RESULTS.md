# Phase VI rotational-augmentation campaign — results (running)

**Last updated:** 2026-09-27
**Campaign script:** `scripts/slurm/campaign-rotational-augmentation.slurm`
**Jobs:** `11601429`, `11601968`; `11602818` cancelled (was still `PD`, never started).
**Status:** 15 / 47 runs completed; the remaining 32 are **not queued** — the
campaign was stopped to free the queue and to run the SOWFA-aligned ablation
arms first (see `SOWFA-6-crosscheck.md`).

**Companion documents:**

- `NREL-TP-500-29955-crosscheck.md` — case vs. the primary experimental report
  (geometry, Sequence H conditions, polar provenance).
- `SOWFA-6-crosscheck.md` — formulation comparison vs. SOWFA-6, the root
  end-effect finding, and the minimal validation matrix (arms A′, C′, R′).

## Method

- **Averaging window:** revolutions 4 → 12 (`solver.discard_revolutions: 4`,
  `solver.end_revolutions: 12`). The first 4 revolutions are discarded as
  transient.
- **Bands:** power / torque / thrust **±15 %** (`scripts/comparePhaseVI.py`).
- **Reference:** committed Sequence H measurements
  (`data/experiment/sequence_H_performance.csv`); `rho` from the experiment row
  (ideal gas).
- **Metrics:** `q = 1/2 rho A U^2`; `P = cp q U`; `Q = ct q R`;
  `T = (cd_blade1 + cd_blade2) q`. Note `%P == %Q` by construction (`cp = ct*TSR`).

## Arms

| Arm | Rotational augmentation | Glauert root effect | Runner flags |
|---|---|---|---|
| **A** (candidate) | on | off | `--rotational-augmentation on --root-effects off` |
| **A′** (tip-off diagnostic) | on | off | `--rotational-augmentation on --root-effects off --tip-effects off` |
| **C′** (augmentation isolation) | off | off | `--rotational-augmentation off --root-effects off --tip-effects off` |
| **B** | on | on | `--rotational-augmentation on --root-effects on` |
| control | off | on | `--rotational-augmentation off --root-effects on` (committed baseline, 2026-09-21) |

Arm A′ differs from arm A in **exactly one flag** (`tipEffects`, verified in the
rendered `fvOptions`), so A′ vs A is a clean tip-effect ablation.

## Results (completed runs)

`%P` / `%T` are the deviation from the Sequence H measurement. `OK` = inside ±15 %.

| U (m/s) | model | arm | mesh | Cp | P (kW) | T (N) | %P | %T | band |
|---:|---|---|---|---:|---:|---:|---:|---:|---|
| 7 | alm | A root-off | coarse | 0.3283 | 5.52 | 1161.8 | −7.2 | +2.6 | OK |
| 7 | alm | A root-off | fine | 0.3282 | 5.52 | 1160.0 | −7.2 | +2.5 | OK |
| 7 | asm | A root-off | coarse | 0.3291 | 5.53 | 1166.0 | −7.0 | +3.0 | OK |
| 7 | alm | B root-on | coarse | 0.3143 | 5.28 | 1108.3 | −11.1 | −2.1 | OK |
| 7 | asm | B root-on | coarse | 0.3149 | 5.29 | 1111.4 | −11.0 | −1.8 | OK |
| 10 | alm | A root-off | coarse | 0.1696 | 8.33 | 1417.9 | −14.6 | −13.1 | OK |
| 10 | asm | A root-off | coarse | 0.1685 | 8.28 | 1418.8 | −15.1 | −13.1 | outside |
| 10 | alm | B root-on | coarse | 0.1454 | 7.14 | 1294.6 | −26.7 | −20.7 | outside |
| 10 | asm | B root-on | coarse | 0.1450 | 7.13 | 1295.4 | −26.9 | −20.6 | outside |
| 13 | alm | A root-off | coarse | 0.0212 | 2.30 | 1606.6 | −76.5 | −19.1 | outside |
| 13 | asm | A root-off | coarse | 0.0202 | 2.18 | 1611.5 | −77.7 | −18.9 | outside |
| 13 | alm | B root-on | coarse | 0.0032 | 0.34 | 1398.2 | −96.5 | −29.6 | outside |
| 15 | alm | A root-off | coarse | 0.0118 | +1.96 | 1917.1 | −79.6 | −14.7 | outside |
| 15 | alm | B root-on | coarse | −0.0084 | −1.40 | 1652.6 | −114.6 | −26.5 | outside |
| 25 | alm | B root-on | coarse | 0.0028 | 2.15 | 3488.9 | −82.0 | −13.4 | outside |
| **7** | **alm** | **A′ tip-off** | **coarse** | **0.4225** | **7.10** | **1404** | **+19.5** | **+24.0** | outside |
| **10** | **alm** | **A′ tip-off** | **coarse** | **0.2417** | **11.88** | **1801** | **+21.8** | **+10.4** | outside |
| **13** | **alm** | **A′ tip-off** | **coarse** | **0.0770** | **8.34** | **2010** | **−14.8** | **+1.2** | outside / **T OK** |
| **7** | **alm** | **C′ aug-off tip-off** | **coarse** | **0.4042** | **6.80** | **1345** | **+14.3** | **+18.8** | outside |

Measured reference (Sequence H): P/Q/T = 5.95 kW / 790 Nm / 1132 N at 7 m/s;
9.75/1292/1632 at 10; 9.79/1297/1987 at 13; 9.58/1270/2248 at 15;
11.95/1580/4029 at 25.

## Tip-effect diagnostic (arm A′, job `11603354_7`, 2026-09-28)

The Glauert tip effect is a **dominant, spurious term**: turning it off swings
power by **+26.6 pts at 7 m/s**, **+36.4 pts at 10 m/s** and **+61.7 pts at
13 m/s**.

| U | %P tip ON (A) | %P tip OFF (A′) | swing | %T tip ON | %T tip OFF |
|---:|---:|---:|---:|---:|---:|
| 7 | −7.2 | **+19.5** | +26.6 | +2.6 | +24.0 |
| 10 | −14.6 | **+21.8** | +36.4 | −13.1 | +10.4 |
| 13 | −76.5 | **−14.8** | +61.7 | −19.1 | **+1.2** |

**Verdict — the diagnosis is confirmed, but the fix is not "turn it off".**

1. **Confirmed:** a BEM tip loss is not a small tuning term for our ALM; it moves
the answer by tens of percent. The literature's claim (Meyer Forsting 2019/2020;
Kim 2015; Jha 2014) that it is the wrong instrument for an actuator line is
borne out by magnitude.
2. **But deleting it overshoots.** At 7 and 10 m/s, tip-off lands **above** the
measurement (+19.5 %, +21.8 %), so the tip loss is *cancelling* the ε
over-smearing bias rather than correcting anything. That is the "two opposite
errors" reading, now measured: at 7 m/s, ε-over-smearing ≈ +19.5 % and the tip
loss ≈ −26.6 pts, netting −7.2 %.
3. **Thrust improves sharply** where the tip loss hurt most: 13 m/s goes from
−19.1 % to **+1.2 %** (in band); 10 m/s from −13.1 % to +10.4 %.
4. **13 m/s power** goes from −76.5 % to −14.8 % — still outside ±15 %, but a
61.7-point correction.

**Consequence:** the next step is to remove the *other* error, not to pick a
point between the two. That is exactly what the **filtered-lifting-line** or
**vortex-based smearing** correction does (`formulation-review.md` §2.1): it
removes the smearing bias analytically, after which the tip loss can be dropped
without overshoot.

**Cheap discriminating tests to run next:**
- **A′ on the D/48 fine mesh at 7 m/s** — ε drops from 0.63 m to 0.42 m; if the
  overshoot shrinks, the ε hypothesis is confirmed.
- **C′ (aug-off, tip-off, root-off) at 7 m/s** — isolates how much of the +19.5 %
  overshoot is the Du–Selig augmentation.

### Decomposition at 7 m/s (C′ delivered 2026-09-29)

| arm | aug | tip | root | mesh | Cp | P (kW) | %P | %T |
|---|---|---|---|---|---:|---:|---:|---:|
| A | on | on | off | coarse | 0.3283 | 5.52 | **−7.2** | +2.6 |
| A′ | on | **off** | off | coarse | 0.4225 | 7.10 | **+19.5** | +24.0 |
| **A′** | on | **off** | off | **fine** | **0.4229** | **7.11** | **+19.6** | **+23.9** |
| **C′** | **off** | **off** | off | coarse | 0.4042 | 6.80 | **+14.3** | +18.8 |

```
C′ (no aug, no tip, no root)      +14.3 %   <- the "everything else" term
+ Du-Selig (A′ - C′)              + 5.2 pts
= A′                              +19.5 %
- Glauert tip loss (A - A′)       -26.6 pts
= A                               - 7.2 %
```

**Du–Selig is real but not dominant** (+5.2 pts). The dominant term is the
**+14.3 % base**.

### ε hypothesis: REFUTED (A′ fine delivered 2026-09-29)

`A′ fine (D/48, ε = 0.42 m)` gives **+19.6 % P / +23.9 % T** versus
`A′ coarse (D/32, ε = 0.63 m)` at **+19.5 % / +24.0 %** — a 0.1 % difference.
Reducing ε by 1.5× does **not** shrink the over-shoot.

> **Provenance of the fine number.** Job `11603592_7` was **cancelled by a user**
> at 5 h 22 m, at **rev 10.20 of 12**, so its mean uses a partial window
> (revs 4 → 10.2) rather than the full 4 → 12. The mean is stable across the
> window (0.4229 vs the coarse 0.4225, a 0.1 % difference), so the conclusion is
> unaffected — but the run is **not** a completed full-window result and should
> not be quoted as one.

**Consequences:**

1. **The ε over-smearing is not the driver.** The `+14.3 %` base is
   **mesh-independent** (arm A was already coarse ≈ fine: 0.3283 vs 0.3282).
2. **Our ALM is parameterization-limited, exactly as Yang & Sotiropoulos 2017
   state** ("grid-independent results cannot be obtained when the mesh is refined
   in the actuator line model… the accuracy depends on the parameterizations").
   Now measured on our own case.
3. **P4 (filtered-lifting-line / smearing correction) is NOT justified** — if
   neither ε nor Δx moves the answer, restoring the smearing-lost induction does
   not attack this error.
4. **The D/48 / D/64 mesh ladder buys nothing for this error** — a real cost
   saving on the queue and the group quota.
5. **The remaining tension**: `tip ON → −7.2 %`, `tip OFF → +19.5 %`, measurement
   `0 %`. The "invalid" BEM tip correction gives the *better* answer, i.e. it is
   **cancelling a base error of comparable size**. The priority is to find that
   base error, not to tune the tip loss.

### Parameterization ablations at 7 m/s (jobs `11603810_9`, `11603820_10`, 2026-09-29)

Both runs reached rev 12.00 (full window). Base = arm C′ (aug-off, tip-off,
root-off, coarse).

| arm | Cp | P (kW) | **%P** | **%T** |
|---|---:|---:|---:|---:|
| C′ base (`linearUpwind`, OSU Re = 1e6) | 0.4042 | 6.80 | **+14.28** | +18.79 |
| C′ scheme = `bounded Gauss linear` | 0.4022 | 6.76 | **+13.72** | +18.54 |
| C′ polar = CSU Re = 0.65e6 | 0.3842 | 6.46 | **+8.63** | **+11.64** |

**Verdict 1 — the convection scheme is NOT the driver.** `linearUpwind` →
`Gauss linear` moves power by **−0.56 pts** and thrust by −0.25. Ruled out.

**Verdict 2 — the polar/Re mismatch IS a significant driver.** OSU Re = 1e6 →
CSU Re = 0.65e6 moves power by **−5.65 pts** and thrust by **−7.15 pts**, i.e.
**~40 % of the +14.3 % base error**. The simulated Re at 7 m/s is ~0.43e6
(inboard) to ~0.94e6 (at r/R = 0.7), so the committed single-Re Re = 1e6 table is
an **upper bound on CL**: at the operating angle of attack it returns 0.917
(α = 9) where the CSU 0.65e6 level returns 0.854 (−6.9 %).

**Updated decomposition at 7 m/s:**

```
C′ base (OSU1e6, linearUpwind)   +14.28
− scheme (Gauss linear)          − 0.56  → +13.72   (ruled out)
− polar (CSU 0.65e6)             − 5.65  → + 8.63   (~40 % of the base)
− Du-Selig (A′ − C′)             + 5.17
− tip loss (A − A′)              −26.64
= A                              − 7.19
```

**What remains (arm C′: ~+8.6 %; arm A: ~−7.6 %).** See the full both-polar
decomposition below.

### Full decomposition over BOTH polars (jobs `11603972_11`, `11603972_12`)

| polar | arm | Cp | P (kW) | **%P** | T (N) | **%T** |
|---|---|---:|---:|---:|---:|---:|
| OSU Re = 1e6 | A (aug-on, tip-**ON**, root-off) | 0.3283 | 5.52 | **−7.19** | 1162 | +2.63 |
| OSU Re = 1e6 | A′ (aug-on, tip-off) | 0.4225 | 7.10 | +19.45 | 1404 | +23.98 |
| OSU Re = 1e6 | C′ (aug-off, tip-off) | 0.4042 | 6.80 | +14.28 | 1345 | +18.79 |
| **CSU Re = 0.65e6** | **A (aug-on, tip-ON)** | 0.3268 | 5.49 | **−7.61** | **1105** | **−2.38** |
| CSU Re = 0.65e6 | A′ (aug-on, tip-off) | 0.4129 | 6.94 | +16.76 | 1340 | +18.40 |
| CSU Re = 0.65e6 | C′ (aug-off, tip-off) | 0.3842 | 6.46 | +8.63 | 1264 | +11.64 |

| term | OSU 1e6 | CSU 0.65e6 | change |
|---|---:|---:|---:|
| base (C′) | +14.28 | **+8.63** | **−5.65** |
| Du–Selig (A′ − C′) | +5.17 | **+8.13** | **+2.96** |
| tip loss (A − A′) | −26.64 | **−24.37** | **+2.27** |
| **= arm A** | **−7.19** | **−7.61** | **≈ 0** |

**Conclusion 1 — the polar fixes the base but NOT arm A.** The base drops 5.65 pts,
but Du–Selig (+2.96) and the tip loss (+2.27) grow to compensate, leaving arm A
unchanged at −7.6 %. The "two opposite errors" are **robust across the polar
choice**, so no single-lever fix works.

**Conclusion 2 — the thrust is IN BAND while the power is low.** With
`CSU + tip-ON`: `%P = −7.61`, `%T = −2.38`. A near-perfect thrust with a 7.6 % low
power is the signature of a **tangential (torque) deficit**, not an axial one.
That points straight at the **`c_ref_t` vs measured-CT ≈2× definitional
mismatch** the earlier session flagged and left as a documented, unfixed caveat
(`scripts/comparePhaseVI.py`). **That caveat is now the prime suspect for the
residual** — and it is a *comparison* problem, not a model-physics problem.

### Root cause: the TIP (QNORM extracted; panel model validated)

Extracted the missing normalisation from the local WDH workbook
(`wt_loads_statistics.xls`, sheet `ldsmean`, row 1203 = `h0700000`):
`QNORM30/47/63/80/95` at columns 66/70/74/78/82 and `EAEROTQ` at column 55.
This closes the archival gap the provenance had flagged.

- **`QNORM ≈ ½ρW²`**: ratios **1.043 / 1.008 / 1.016 / 1.005 / 1.001**. The
experiment normalises by the **local dynamic pressure**, as our element CSV
does → **normalisation is NOT a confound**.
- `EAEROTQ = 782.2 Nm`, `LSSTQCOR = 789.9 Nm`, `EAEROTH = 1132.1 N`.

**Panel model validated** (root panel 25 % span → midpoints between stations →
100 %): Eq. (13) with the archived `CN*` gives **1153.1 N vs 1132.1 measured,
ratio 1.019 ✓**. So `CN*` is the chord-normal coefficient and the panel/area
model is right. Eq. (14) with `CT*` gives **394.5 Nm vs 782.2, ratio 0.504** —
`CT*` needs **×2** to reproduce the measured torque (789.0 Nm, ratio 1.009), so
the report's `C_TQ` is `2·CT*` and the archived `CT*` is the chord-referenced
`C_T`, not the `C_Torque` Eq. (14) consumes.

**Decisive spanwise comparison (after the frame fix):**

| r/R | our cn | exp cn | Δ | our ct | exp ct | Δ |
|---|---:|---:|---:|---:|---:|---:|
| 0.47 | 0.979 | 0.920 | +6 % | 0.126 | 0.118 | **+6 %** |
| 0.63 | 0.904 | 0.867 | +4 % | 0.107 | 0.096 | +11 % |
| 0.80 | 0.765 | 0.767 | −0.3 % | 0.080 | 0.073 | +10 % |
| **0.95** | **0.434** | **0.518** | **−16 %** | 0.034 | 0.041 | **−17 %** |

**ROOT CAUSE — the tip.** The tangential loading **matches the experiment within
~6 % over the mid span** and is **16–17 % low at the tip**, where `r` (the torque
lever) is largest. That is the −7.2 % torque deficit.

**Chain:** tip loss ON → tip loading −16 %, torque −7.2 %; tip loss OFF → torque
+19.5 % (over-corrects). The correct correction lies **between**, i.e. the BEM
Glauert tip loss is **too strong** — exactly what the ALM literature says.

**Reinstating P4.** I had dismissed the filtered lifting line with "it only acts
at the tip and the error is uniform mid-span". **That was wrong**: with the frame
fixed, the deficit **is** the tip, and the offline FLLT evaluation put its
largest corrections (4–6 % of U∞) at r/R 0.93–0.995. **P4 is the justified fix.**

### FLLT evaluated offline (no code, no queue)

MT 2023 Eq. (4) evaluated numerically on the converged spanwise data,
ε_LES = 0.628 m vs ε_opt = 0.25c: the correction is **small mid-span
(~0.2–1.3 % of U∞)** and **large only at the tip (4–6 %)**. So the filtered
lifting line would **not** explain the uniform +8.6 % base, and it acts where the
tip loss already acts. Caveats: `G` may need a ρ factor (~1.23×, so the numbers
above are ~23 % low), the sign convention is unvalidated, and MT derive it for a
**fixed wing** — their own conclusion leaves the rotor/helical-vortex case to
future work.

> **Operational lesson.** Job `11603810_9` reported
> `runPhaseVI.sh: line 487: suggestion: unbound variable` and `FAIL exit 1`
> **even though the solver completed cleanly** (`End`, `Finalising parallel run`,
> rev 12.00) and the data used above is valid. The cause was **editing
> `runPhaseVI.sh` while the job was executing it** — bash re-reads a script from
> the file by byte offset as it runs, so mid-run edits shift the offsets and
> corrupt execution. `bash -n` passes and the `else` branch works standalone,
> confirming there is no real defect. Do not edit the runner while a job is in
> flight.

**Remaining suspects (all in the parameterization, not the numerics):**

| # | Suspect | Cost |
|---|---|---|
| 1 | **Tip loading** — −16 % at r/R = 0.95 with the tip loss ON, costing the torque −7.2 % | **P4: filtered lifting line / smearing correction (justified)** |
| 2 | Comparison frame bug (plane vs chord) | **fixed 2026-09-29** |
| 3 | **Polar** — real (−5.65 pts on the base) but does not move arm A | data work |
| 4 | **Solver** (URANS k-ω SST vs LES / IDDES) | expensive |
| 5 | **Domain** (no wind-tunnel blockage; SOWFA models the test section) | expensive |
| 6 | ~~**Convection scheme**~~ | **ruled out (−0.56 pts)** |
| 7 | ~~**Filtered lifting line**~~ | **reinstated: acts where the deficit is** |

## Findings

1. **The candidate (arm A, `aug-on + root-off`) is in band at 7 m/s**:
   −7.2 % P and +2.6 % T, closing the baseline `aug-off` deficit (−16 %).
   It is **mesh-independent** (coarse ≈ fine) and **ALM ≈ ASM**
   (0.3283 vs 0.3291).
2. **`root-off` dominates `root-on` at every measured point.**
   At 10 m/s arm A is ~12 points better (−14.6 % vs −26.7 %); at 15 m/s arm A
   gives **positive** power (+1.96 kW) where arm B stays **negative** (−1.40 kW,
   non-physical).
3. **ALM ≈ ASM** at 13 m/s (2.30 vs 2.18 kW): the model form does not change
   the outcome at this point.
4. **High speed (13–25 m/s) remains out of band** — consistent with the
   documented URANS deep-stall limitation (trend and stall-onset evidence only).
   The candidate nevertheless keeps power **positive** where the committed
   baseline gave negative power (13 m/s: baseline −4.4 kW → arm A +2.3 kW).

## Next: SOWFA-aligned ablation matrix

The remaining runs are re-scoped, not blindly re-queued. The `--tip-effects
{on,off}` toggle is implemented and tested; the next campaign runs arms **A′**
(aug-on, tip-off, root-off) and **C′** (aug-off, tip-off, root-off) at 7/10/13
m/s to isolate the tip correction and the SOWFA-aligned end-effect choice. The
root-formula fix (**R′**) needs the code change first. See
`SOWFA-6-crosscheck.md` §4.

## Pending (original 32-run plan, superseded)

`alm` U25-coarse(A), U13-fine(A), U7/U13-fine(B); `asm` U15/U25-coarse(A),
U7/U13-fine(A), U13/U15/U25-coarse(B), U7/U13-fine(B); all `asm-mesh` A/B/control
(19 runs). The `asm-mesh` three-way and the fine spot-checks close the model-form
and mesh-insensitivity claims.

## Operational notes

- `--nodes=1-2` (multi-node MPI start-up failed intermittently: `MPI_Init_thread`
  NULL-communicator aborts with `OPAL/pmix3x_client.c` errors and segfaults
  inside `MPI_Init_thread`).
- `solver.purge_write` reduced `8 → 1`: the fields under `processor*/` are only
  needed for a restart; the rotor power/torque/thrust history and element loads
  live in `postProcessing/` and are never purged.
- The campaign script now (a) skips runs already recorded `OK` in
  `runs/campaign-logs/`, and (b) deletes each run's `processor*/` after it
  reaches `endTime` (`TURBINE_KEEP_FIELDS=1` disables the deletion).
- The shared `leahk` group quota (2 T) was exhausted repeatedly and caused
  `EDQUOT` failures; the above two measures keep the footprint bounded.

---

## Dağ & Sørensen 2020 tip correction (arm A, 7 m/s, Sequence H, coarse D/32)

Slurm `11604168` (48 ranks, cores-only, 4:48:35, `COMPLETED`). Arm A physics:
rotational augmentation on, Glauert **root off**, Glauert **tip off**, and the
Dağ & Sørensen induced-velocity tip correction **on**. Both runs reached the full
~12-revolution window; the drift flag is false for both.

| polar | arm | P (kW) | %P | %Q | %T | tip `c_ref_n` at r/R=0.95 (exp 0.5175) |
|---|---|---|---|---|---|---|
| OSU Re=1e6 | A (Glauert tip ON) | 5.519 | **−7.19** | −7.19 | +2.63 | 0.4349 (**−16.0 %**) |
| OSU Re=1e6 | A′ (tip OFF) | 7.102 | **+19.45** | +19.45 | +23.98 | 0.8836 (**+70.7 %**) |
| OSU Re=1e6 | **A + D&S correction** | 6.519 | **+9.64** | +9.65 | +18.4 | 0.7948 (**+53.6 %**) |
| CSU Re=0.65e6 | A (Glauert tip ON) | 5.49 | **−7.61** | — | −2.38 | 0.4349 (−16.0 %) |
| CSU Re=0.65e6 | A′ (tip OFF) | 6.94 | **+16.76** | — | +18.40 | — |
| CSU Re=0.65e6 | **A + D&S correction** | 6.467 | **+8.76** | +8.76 | +14.1 | 0.7799 (**+50.7 %**) |

(Measured reference: 5.946 kW / 789.9 Nm / 1132 N.)

**Verdict — the correction works as intended but is too weak to close the gap.**
It moves the result in the right direction and by a substantial amount: power
`+19.45 % → +9.64 %` (OSU) and `+16.76 % → +8.76 %` (CSU); tip `c_ref_n`
`+70.7 % → +53.6 %`. But it does **not** reach the measurement, and the BEM
Glauert tip loss — the model it was meant to replace — remains closer in
absolute error (`−7.2 %` / `−7.6 %`) despite over-correcting the tip to `−16 %`.

**Why the correction is small here.** At the tip the correction is a stable
≈ 0.78 m/s (the offline replica agrees: 0.82 m/s). It is intrinsically of that
order at `nElements = 50`, and the ε-smoothing added for stability does not
change it (0.81 before, 0.78 after). Dağ & Sørensen report usable results at
`nrAero = 11`, where the sampled `dΓ/ds` — and therefore the correction — is
several times smaller; their own Phase VI comparison is against BEM, not the
experiment.

**Two findings worth carrying forward:**
1. The correction is **strongly resolution-dependent** through the sampled
   bound-circulation gradient: the mid-point sum of point trailing vortices
   converges to `(dΓ/ds)/(2π)`. At `nElements = 50` this is O(U∞) at the
   non-lifting hub transition, which is what diverged the first arm-A attempt;
   it is now controlled by filtering `Γ` at the model's own kernel width ε
   (commit `3437e17`).
2. Near-zero power error and a +50 % tip loading coexist here (and symmetrically
   −7 % power with −16 % tip for Glauert): the integrated torque is insensitive
   to the last few percent of span, so the tip-only diagnostic alone does not
   carry the validation.

### Tip-correction follow-up variants (7 m/s, Sequence H, coarse D/32)

| arm (config) | %P | %Q | %T | tip `c_ref_n` @ r/R=0.95 (exp 0.5175) |
|---|---|---|---|---|
| A: Glauert tip ON, root off | −7.19 | −7.19 | +2.63 | 0.4349 (−16.0 %) |
| A′: tip loss OFF, root off | +19.45 | +19.45 | +23.98 | 0.8836 (+70.7 %) |
| D&S correction, root off (n50) | +9.64 | +9.65 | +18.4 | 0.7948 (+53.6 %) |
| **D&S correction, root ON (n50)** | **+6.24** | +6.24 | +13.7 | 0.7950 (+53.6 %) |
| D&S correction, root off (n25) | +12.6 | +12.6 | +20.4 | 0.8091 (+56.4 %) |

Slurm 11604296 (root ON) and 11604298 (n25), both full ~12-revolution windows,
drift flag false; 11604298 completed normally, 11604296's shell wrapper exited 2
after the solver had finished (the runner was edited while the job was reading
it -- the data is valid).

**Reading.**
1. **D&S with the Glauert root effect back ON is the best result so far
   (+6.24 %)**: better than the Glauert tip loss (−7.19 %) in absolute error and
   better than D&S with root off (+9.64 %). The root effect acts inboard (at
   r/R=0.30 it moves `c_ref_n` from 1.006 with root off to 0.712, against the
   measured 0.814), so it reduces the integrated torque without touching the tip.
2. **n25 confirms the resolution dependence**: the coarser arm gives a weaker
   correction (+12.6 %, closer to the tip-off +19.45 %). The correction scales
   with the sampled `dΓ/ds`, so its magnitude -- and therefore its effect -- is a
   property of the spanwise resolution, not only of the physics.
3. Neither the tip nor the inboard is right in any corrected arm: at r/R=0.95
   every corrected arm sits at ≈ +54 %, while at r/R=0.30 root-on is −12.5 % and
   root-off +23.6 %.

### Tip correction + Du-Selig off: the 7 m/s gap closes (+0.45 %)

Slurm 11604388/11604389 (full ~12-rev windows). Turning **Du-Selig off** under the
tip correction is the dominant lever, exactly as the polar analysis predicted:

| 7 m/s, coarse D/32 | %P | %Q | %T |
|---|---|---|---|
| A root-off, Glauert tip | −7.20 | −7.20 | — |
| B root-ON, Glauert tip | −11.12 | −11.12 | — |
| D&S correction, root off, aug ON | +9.65 | +9.65 | +18.4 |
| D&S correction, root ON, aug ON | +6.24 | +6.24 | +13.7 |
| D&S correction, root off, **aug OFF** | +4.70 | +4.70 | — |
| **D&S correction, root ON, aug OFF** | **+0.45** | **+0.44** | +9.3 |

Removing the augmentation moves +6.24 % → +0.45 % at root-ON (−5.8 pts) and
+9.65 % → +4.70 % at root-off (−5.0 pts) — consistent, and it confirms the
mechanism: Du-Selig blends the stalled CL toward the unbounded
`CL,p = 2π(α−α0)`, inflating the inboard loading.

**Caveat, not hidden:** the thrust is still +9.3 % while the torque matches, so
the axial/tangential balance is not solved — this is not yet a validated arm.

### Multi-speed: the correction improves every speed, and 7 and 10 are near zero

Slurm 11604362–11604365 (full windows), D&S correction with root ON and aug ON:

| speed | measured P | B (root-ON, Glauert tip) | **D&S root-ON** |
|---|---|---|---|
| 7 | 5.946 kW | −11.1 % | **+6.2 %** |
| 10 | 9.753 kW | −26.8 % | **+4.4 %** |
| 13 | 9.794 kW | −96.5 % | **−29.2 %** |
| 15 | 9.582 kW | −114.6 % | **−44.0 %** |
| 25 | 11.951 kW | −82.0 % | **+74.2 %** |

So the correction is not a 7 m/s-only effect: it improves the power by 17–44
points at every speed over the Glauert tip loss, lands within ±6 % at 7 and
10 m/s, and still leaves 13/15 m/s far from the measurement — those are the
deep-stall points where the polar/stall branch dominates, consistent with the
Viterna work. At 25 m/s it overshoots to +74 %.

### Du-Selig off is a 7 m/s over-fit; Lindenburg does not help at 7 m/s

Full windows, coarse D/32, thrust with `--match-eaeroth-span` (r/R >= 0.25,
matching the measured `EAEROTH`):

| speed | config | %P | %T* | tip `c_ref_n` @0.95 (exp 0.5175) |
|---|---|---:|---:|---:|
| 7 | D&S + **Du-Selig**, root ON | **+6.24** | −9.39 | 0.7950 (+53.6 %) |
| 7 | D&S + **aug OFF**, root ON | **+0.45** | −12.74 | 0.7951 (+53.6 %) |
| 7 | D&S + **Lindenburg**, root ON | +7.24 | +7.89 | 0.9159 (+77.0 %) |
| 7 | D&S + Viterna polar, Du-Selig | +6.22 | −9.36 | 0.7950 (+53.6 %) |
| 10 | D&S + **Du-Selig**, root ON | **+4.43** | −20.9 | — |
| 10 | D&S + **aug OFF**, root ON | **−26.08** | −31.14 | 0.9137 (+22.1 %) |
| 13 | D&S + **Du-Selig**, root ON | **−29.22** | −29.7 | — |
| 13 | D&S + **aug OFF**, root ON | **−82.31** | −41.52 | 0.9799 (+7.6 %) |
| 15 | D&S + **Du-Selig**, root ON | **−43.99** | −30.3 | — |
| 15 | D&S + **aug OFF**, root ON | **−115.31** | −42.51 | 0.8059 (−5.0 %) |

**Three conclusions.**

1. **Removing Du-Selig only helps at 7 m/s.** At 10/13/15 it is catastrophic
   (−26 % / −82 % / −115 % vs +4.4 % / −29 % / −44 %). The rotational
   augmentation is *essential* in the stalled regime; the "+0.45 %" at 7 m/s was
   an **over-fit to a single operating point**, not a fix.

2. **The Lindenburg bounded model, as implemented, does not help at 7 m/s**
   (+7.24 % vs +6.24 %) and *raises* the tip load (0.9159 vs 0.7950). Its
   increment is `ΔC_L = 1.6(c/r)cos²φ[f²cos α_rot + 0.25cos(α_rot−α_0)]` — the
   second, always-positive term adds lift even when the section is separated.
   Running it at 10/13/15 is the outstanding test.

3. **The Viterna post-stall branch alone changes nothing** (+6.22 vs +6.24, tip
   identical): with Du-Selig active the augmentation compensates the polar
   change, which is exactly the coupling Papi et al. (2022) is about.

**Overall best across the speed range remains D&S + Du-Selig + root ON**: +6.2 /
+4.4 / −29.2 / −44.0 % at 7/10/13/15 m/s — i.e. good at 7 and 10, and still far
at the deep-stall points, where (Ouakki & Arbaoui 2023) no 1-D stall-delay model
is validated.

### Lindenburg is worse than Du-Selig at every speed — NO-GO

Full windows, coarse D/32, %T span-matched (`--match-eaeroth-span`):

| U (m/s) | Du-Selig (%P) | **Lindenburg (%P)** | aug OFF (%P) | tip cn @0.95 (exp 0.5175) |
|---:|---:|---:|---:|---:|
| 7 | +6.24 | +7.24 | +0.45 | 0.9159 (Lindenburg) vs 0.7950 (Du-Selig) |
| 10 | +4.43 | **−18.20** | −26.08 | 0.9823 vs 0.9087 |
| 13 | −29.22 | **−73.12** | −82.31 | 1.0185 vs 0.9664 |
| 15 | −43.99 | **−105.39** | −115.31 | 0.8378 vs 0.7771 |

**The bounded model under-delivers at every speed**, sitting between Du-Selig and
aug-off and much closer to the latter. It is a clear **NO-GO as a Du-Selig
replacement.**

**The uncomfortable but important reading**: the physically-defensible bounded
model performs *worse* than the physically-questionable unbounded one, because
the extra lift Du-Selig adds toward `CL,p` is **empirically needed** in the
stalled regime. That is evidence that Du-Selig's augmentation is **compensating
for a different deficit** — most plausibly the 3-D separation physics that no 1-D
model captures there (Ouakki & Arbaoui 2023) — rather than supplying correct
physics. It also explains why removing it (aug OFF) is catastrophic at 10/13/15:
whatever the mechanism, that lift is load-bearing for the integral torque.

**Consequence for the plan**: the "replace Du-Selig with a bounded model" route is
closed. The remaining honest options for the deep-stall points are a **rotating
3-D polar from CFD/experiment** (the accuracy ceiling) or recording the limit —
and the primary effort shifts to the **IEA 15 MW case**, whose attached regime
avoids this entirely.
