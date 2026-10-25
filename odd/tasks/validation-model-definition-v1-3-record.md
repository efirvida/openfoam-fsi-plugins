# Model Definition v1.3 decision record — Phase VI pitch reference and drag polar

**Status: PROPOSED, owner decision pending.** Nothing here changes the definition of record:
`validation-model-definition.md` and `config/model-definition.yaml` stay v1.2 until the owner
adopts, amends or rejects this record. Evidence: `odd/tasks/phasevi-tip-pitch-reference.md`
(T3, Log L9), outputs `turbinesFoam/validation/phaseVI/runs/tip-pitch-2x2-20261023/`. Date: 2026-10-23.

## Proposal

Two knob changes on the Phase VI pillar, everything else v1.2:

1. **Pitch reference: tip chord** (`--pitch-reference tip`, registry variant `tip-pitch`, commit `77462a9`).
   NREL/TP-500-29955 p.20: "blade pitch is defined as the angle between the blade tip chord line and the
   plane of the turbine disk"; Table A-1 note 2: twist "relative to zero twist at the 3.772-m station".
   v1.2 adds the 3 deg pitch at the zero-twist station, so the whole blade sits 1.815 deg towards stall
   (tip mounting -1.185 deg instead of -3.0 deg). This is a geometry defect against the published
   definition, not a tuning knob.
2. **Polar: OSU Re 1e6 with total drag** (`data/polars/S809_OSU_Re1M_total.dat`, the v1.1 table),
   replacing the v1.2 pressure-drag table. The measured references are shaft power and torque
   (ROTPOW, LSSTQCOR), which include skin friction; a pressure-drag polar leaves it out. v1.2 adopted
   pressure drag "for now" because D3 was the best result (H 7 m/s P -11.0 -> -2.2 %) while the blade
   was mis-pitched. The 2x2 shows that drag moves only the level and that the U5 surplus it was
   compensating came from the pitch.

The proposal is made on physical consistency, not on the numbers: the tip + **pressure** cell scores
better at U5 and U8 (below), and picking it for that reason would be fitting the drag model to the data
(owner rule S3: "No ajustar coeficientes para acercarse a los datos").

## Evidence (Sequence S, coarse D/32, windows U5 16..24 rev, U7/U8 4..12 rev)

Error vs experiment in %, pp change vs v1.2 of the same speed in brackets. Bands are the
pre-registered ones (P 10 %, T 15 %, c_n 10 % at r/R 0.47-0.80, 15 % at 0.30, 0.95 reported only).

| Speed | Quantity | v1.2 (pressure) | v1.2 pitch + total | tip + pressure | **tip + total (proposed)** |
| --- | --- | --- | --- | --- | --- |
| 5 | P | +26.5 | +20.2 (-6.3) | +3.1 (-23.4) | **-4.5 (-31.0)** |
| 5 | T | +15.7 | +15.8 | -11.2 | **-11.1** |
| 5 | dR 0.30/0.47/0.63/0.80/0.95 | +17.5/+16.7/+14.0/+18.6/+16.5 | identical | -17.9/-6.3/-9.9/-11.0/-15.0 | **identical to tip** |
| 7 | P / T | -2.1 / -0.8 | not run | -4.0 / -7.6 | **not run** |
| 7 | dR | +15.0/+1.7/+2.5/+0.0/-12.1 | not run | +10.8/-2.0/-3.7/-9.5/-19.9 | **not run** |
| 8 | P | -19.9 | -27.1 (-7.3) | -16.0 (+3.8) | **-21.7 (-1.8)** |
| 8 | T | -12.7 | -12.6 | -15.8 | **-15.7** |
| 8 | dR | -9.7/-16.7/-6.8/-10.3/-30.6 | identical | -13.8/-21.4/-8.0/-13.5/-33.2 | **identical to tip** |

Verdict against the predictions written before the runs (L8, not moved):

- **The pitch reference is the dominant cause of the speed-dependent slope: supported.** U5 power moves
  -23.4 pp against -6.3 pp from drag, and every U5 station drops by 23-35 pp. The U5-U8 power spread
  shrinks from 46.4 to 19.1 pp, the thrust spread from 28.4 to 4.6 pp. At U5 the twist residual against
  the experiment's frame rotation goes from -2.65..-2.93 deg to -1.0..-1.4 deg inboard and +0.06 deg at the tip.
  Where the prediction was too strong: U5 overshoots (from +14..+19 % to -6..-18 %, so c_n at 0.30 and
  0.80 is now low and outside its band); U7 drops but keeps its power match (-4.0 %); U8 power rises
  +3.8 pp instead of staying flat.
- **Drag shifts the level, not the slope: supported.** Total vs pressure moves power by 5.7-7.6 pp
  with either pitch, at U5 and U8, and moves dR by at most 0.6 pp (only the tangential force changes).
- **Tip + total: U5 near, U8 low, consistent with a 3D stall-delay limitation.** U5 is inside the P and
  T bands; U8 is 21.7 % low in power, with the deficit inboard (dR -21.4 % at 0.47) and at the Glauert
  tip (-33 %, the known v1.2 tip under-load).

## Pre-registered band status under the proposal (R2, speeds 5-8)

| Speed | P (10 %) | T (15 %) | c_n 0.30 (15 %) | c_n 0.47 / 0.63 / 0.80 (10 %) |
| --- | --- | --- | --- | --- |
| 5 | pass (-4.5) | pass (-11.1) | fail (-17.9) | pass (-6.3) / pass (-9.9) / fail (-11.0) |
| 6 | not run | not run | not run | not run |
| 7 | not run with total; tip + pressure -4.0 | tip + pressure -7.6 | tip + pressure +10.6 | tip + pressure -2.1 / -3.8 / -9.6 |
| 8 | fail (-21.7) | fail (-15.7) | pass (-13.9) | fail (-21.6) / pass (-7.6) / fail (-13.4) |

c_n from `comparePhaseVI.py` (summary), dR from `compareSectionLoads.py`; they differ by < 0.5 pp here.
Under v1.2, U5 fails P, T and every c_n band, and U8 fails P. The proposal does not make R2 pass; it
moves the failure from a geometry defect (U5, all stations) to a modelling limitation (U8 inboard and tip).

## What adopting it would change

- `generate_case.py` defaults: `--pitch-reference tip` and the total polar; `config/model-definition.yaml`
  `version: v1.3` with the polar path and a pitch-reference knob the checker certifies (the tip mounting
  -3.0 deg is already certified by `checkModelDefinition.py`).
- Every v1.2 Phase VI result becomes non-of-record: the R2 Sequence S speeds 5-8, the H 7 m/s acceptance
  point (D3 included) and the R1 mesh ladder would have to be re-run under v1.3. The pressure-drag D3
  conclusion ("-11.0 -> -2.2 %") was obtained on the mis-pitched blade and would be withdrawn.
- The IEA pillar's renderer is untouched: the switch exists only in the Phase VI generator
  (`phaseVI/tools/generate_case.py`, `element_data.py`), and the IEA polar was never switched to pressure
  drag. Whether the IEA blade carries an equivalent pitch-reference offset was not audited here.

## Gaps before adoption (each needs new runs: owner authorisation)

1. **(Closed 2026-10-25, see the v1.3 matrix section.)** **U7 and U6 tip + total cells** do not exist; R2 needs 5, 6, 7 and 8 m/s. From the measured level shift
   (-5.7..-7.6 pp), U7 tip + total would be expected at about -10..-12 % power, at the edge of the band;
   that is an estimate, not evidence.
2. **H 7 m/s acceptance point** (and 10 m/s) under tip + total. (H 7 closed 2026-10-25; 10 m/s not run.)
3. **(Du-Selig run 2026-10-25; CH pending.)** **RA arms on the corrected geometry**: the U8 inboard deficit is the region rotational augmentation
   addresses; the RA verdicts in `RESULTS.md` were all obtained with the 1.815 deg pitch error.
4. **ASM-mesh twin**: native review warning `R3-asm-mesh-pitch-reference-unproved` (`runPhaseVI.sh:437-439`)
   has to be closed before the ASM pillars run v1.3.
5. `scripts/bemPhaseVI.py:17` shares the old pitch convention.

## Evidence from the v1.3 matrix (2026-10-25; `phasevi-physics-review.md` T7, diagnosis `phasevi-physics-diagnosis.md`)

All arms tip pitch, Sequence S unless noted; `runs/v13-matrix-compare/` (`run_compare.sh`, `summary.log`,
`sections-*.log`); BEM `runs/physics-review-scripts/bem-matrix-20261023.txt`. Errors in %. Checker: every new
directory conforms except the polar override of the `*-total` labels (expected).

**Gaps 1-2 closed for option A (tip + total).** The estimate in gap 1 (U7 about -10..-12 %) did not hold:

| cell | P (10 %) | T (15 %) | c_n 0.30 (15 %) | c_n 0.47 / 0.63 / 0.80 (10 %) | c_n 0.95 |
| --- | --- | --- | --- | --- | --- |
| A S U6 | pass (-2.9) | pass (-4.2) | pass (+9.6) | pass (+0.6) / pass (-1.7) / pass (-5.2) | -14.3 |
| A S U7 | pass (-7.7) | pass (-7.6) | pass (+10.8) | pass (-1.9) / pass (-3.7) / pass (-9.5) | -20.0 |
| A H U7 | pass (-7.7) | pass (-7.5) | pass (+9.3) | pass (-2.9) / pass (-3.9) / pass (-9.1) | -21.7 |

With U5 and U8 above, A passes every band at 5, 6 and 7 m/s except U5 c_n 0.30 and 0.80, and fails U8
(P -21.7). Sequence S and H agree at 7 m/s (P -7.7 both). The power spread over 5-8 m/s is 18.8 pp.

**A vs B (drag) moves only the level.** Normal loads are identical within 0.2 pp at every speed. The power
shift A - B is -7.6 / -3.3 / -3.7 (H -3.6) / -5.7 pp at 5 / 6 / 7 / 8 m/s; the BEM on the same inputs gives
-8.1 / -3.7 / -3.1 / -3.6. The handoff range "5.7-7.6 pp" was the U5/U8 pair only and does not hold at 6-7
m/s, where the ALM matches the BEM's 3.1-3.7 pp.

**Tip treatment (OSU total polar; P1 = A).** Station dR % at r/R 0.80 / 0.95 and alpha at 0.95 (BEM alpha
from diagnosis E2):

| arm | U5 P | U8 P | spread | U5 dR 0.80 / 0.95 | U8 dR 0.80 / 0.95 | alpha 0.95 U5 / U8 |
| --- | --- | --- | --- | --- | --- | --- |
| P1 Glauert on cl | -4.5 | -21.7 | 17.2 | -11.0 / -14.9 | -13.4 / -33.1 | 3.84 / 8.47 |
| P2 D&S, Glauert tip off | -1.7 | -7.8 | 6.1 | -7.5 / +8.4 | +3.3 / +25.3 | 2.71 / 6.09 |
| P3 no tip correction | +9.6 | +0.7 | 8.9 | -7.6 / +38.4 | +3.8 / +41.5 | 3.54 / 7.85 |
| BEM, Prandtl tip | -3.7 | -7.6 | 3.9 | -11.0 / +0.7 | +1.4 / +18.9 | 2.49 / 5.69 |

The predictions hold: P3 over-loads the tip (+38/+42 %, as Jha et al. 2014 state and as the BEM with the
tip loss off gives, +26/+39 %); P2 lies between P1 and P3 and tracks the BEM, its 0.95 alpha within
0.2 / 0.4 deg of it. P3's better U8 power is the tip over-load offsetting the inboard deficit, a
cancellation of the kind that made v1.2 U7 look right, so **P2 is the best tip treatment** and carries P4.
The U8 inboard deficit is untouched by every tip arm (dR 0.47 -20.5..-21.4 %, BEM -20.3 %).

**Rotational augmentation (tip + total, Glauert tip, S U8).** Du-Selig moves the inboard stations only, as
predicted: dR 0.30 -13.8 -> +4.4, 0.47 -21.4 -> -12.7, 0.63 -7.9 -> -5.1, 0.80 and 0.95 unchanged (< 0.4
pp); power -21.7 -> -16.5. The Chaviaropoulos-Hansen arm landed on a slow node (11623030, 250 steps in 10 h,
no written time) and was relaunched from scratch (11623807, `LIB_DIR=runs/lib-v13`, confirmed in its .out).

**Pending:** CH RA S U8 (11623807); P4 = P2 with the DUT polar at S U5 / U8 (11623816 / 11623817,
label `var-tip-pitch-dag-sorensen-dut`; confound: mirrored CSU rows below -1.04 deg and the DUT->CSU step
at 20.2 deg, review lineage review-77ffa9548bfe3646). P2 has no U6/U7/H7 cell yet: if P2 (or P4) becomes the
definition, the R2 gate needs those three cells under it, and the D&S tip treatment adds the cost of the
prescribed wake.

## Options for the owner

- **A (proposed): adopt v1.3 = tip pitch + total polar**, then run gaps 1-2 as the new R2 baseline.
- **B: adopt the tip pitch only, keep pressure drag**, which gives better numbers (U5 +3.1 %, U8 -16.0 %)
  but keeps a polar inconsistent with the shaft-torque reference; B should then carry a written reason
  other than the score.
- **C: keep v1.2** and record the pitch error as a known defect of record.
- In every case, closing gaps 1-2 before freezing the new bands avoids adopting on two speeds.
