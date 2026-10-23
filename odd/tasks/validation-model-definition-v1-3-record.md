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

1. **U7 and U6 tip + total cells** do not exist; R2 needs 5, 6, 7 and 8 m/s. From the measured level shift
   (-5.7..-7.6 pp), U7 tip + total would be expected at about -10..-12 % power, at the edge of the band;
   that is an estimate, not evidence.
2. **H 7 m/s acceptance point** (and 10 m/s) under tip + total.
3. **RA arms on the corrected geometry**: the U8 inboard deficit is the region rotational augmentation
   addresses; the RA verdicts in `RESULTS.md` were all obtained with the 1.815 deg pitch error.
4. **ASM-mesh twin**: native review warning `R3-asm-mesh-pitch-reference-unproved` (`runPhaseVI.sh:437-439`)
   has to be closed before the ASM pillars run v1.3.
5. `scripts/bemPhaseVI.py:17` shares the old pitch convention.

## Options for the owner

- **A (proposed): adopt v1.3 = tip pitch + total polar**, then run gaps 1-2 as the new R2 baseline.
- **B: adopt the tip pitch only, keep pressure drag**, which gives better numbers (U5 +3.1 %, U8 -16.0 %)
  but keeps a polar inconsistent with the shaft-torque reference; B should then carry a written reason
  other than the score.
- **C: keep v1.2** and record the pitch error as a known defect of record.
- In every case, closing gaps 1-2 before freezing the new bands avoids adopting on two speeds.
