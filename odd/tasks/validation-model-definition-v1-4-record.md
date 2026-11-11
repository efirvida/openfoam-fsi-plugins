# Model Definition v1.4 decision record — near-tip virtual-camber correction (F_Cl)

**Status: ADOPTED 2026-11-11.** Owner decision (`odd/tasks/tip-model-analysis.md` L20, "Si a los dos"): adopt F_Cl in
v1.4, and document the stall regime as a limitation of the method. `config/model-definition.yaml` is v1.4; v1.3 is
frozen as `config/model-definition-v1.3.yaml` (as v1.2 was, `odd/tasks/validation-model-definition-v1-3-record.md`).
Registry variant `v1.4` reproduces the record on the v1.2 base and has exactly the flags of the diagnostic arm
`tip-pitch-dag-sorensen-neartip` that was run in T14 and T16. Spec: `odd/tasks/phasevi-validation-extension.md` S1 (T1).

## Definition

v1.4 = v1.3 + `nearTipCorrection` on, nothing else:

- Pitch reference tip, Dag & Sorensen tip correction on, Glauert tip factor off (root kept), OSU total polar (all v1.3).
- `nearTipCorrection.active on`, `model TrigauxVirtualCamber`, `table system/trigaux2024_tableC.csv`, `kernel "3D"`,
  `sigmaOverC 0.25`. The correction is `cl x (1 - F_Cl((d_tip/c)_eff))` per element (Trigaux, Villeneuve, Dumas &
  Winckelmans, *J. Fluid Mech.* 989:A1, 2024, doi:10.1017/jfm.2024.461; thesis eq. 3.17-3.31, App. C Table C.3,
  3D, sigma = c/4). The table is published, no coefficient is fitted; `F_alpha_e` is not applied because the Dag &
  Sorensen correction already restores the mollification loss. Implementation: code commit `6f27aad`; the runs below
  used the private library `runs/lib-neartip-6f27aad`.
- Renderer flags of variant `v1.4`: `--pitch-reference tip --tip-correction on --tip-effects off --polar
  S809_OSU_Re1M_total.dat --near-tip-correction on`. The checker certifies the active flag and the four constants.

## Evidence (all Sequence S unless noted, coarse D/32, rev 4..12, R3, `--experiment data/experiment/uae6-archive`)

**T14** (`tip-model-analysis.md` L13, S U7, job 11643016, run `alm-U7-coarse-seqS-var-tip-pitch-dag-sorensen-total-neartip`).
Free-box v1.3 baseline: P 6.07 kW, c_n error +11.3/-1.5/-1.6/+2.9/+26.2 % at r/R 0.30/0.47/0.63/0.80/0.95. With F_Cl:
P 5.933 kW (-2.3 % vs v1.3, -1.6 % vs measured); c_n +11.3/-1.5/-1.7/-0.0/+7.9 %, i.e. the tip error goes
**+26.2 -> +7.9 %**. All four pre-registered clauses held (0.95 in [+4,+14], 0.80 lowered 1-4 pp, 0.30-0.63 within 1 pp,
P 5.83-6.01 kW). Every station is inside 10 % except 0.30, which the correction leaves unchanged by construction.

**T16** (L14 prediction, L19 table; `runs/t16t17-20261111/summary.txt`). Error vs experiment, v1.3 -> F_Cl, %:

| Quantity | S5 | S6 | H7 | S8 | S10 (T17) | S15 (T17) |
| --- | --- | --- | --- | --- | --- | --- |
| c_n 0.95 | +8.9 -> -6.6 | +19.2 -> +2.1 | +23.5 -> +5.6 | +25.4 -> +5.9 | +24.2 -> +2.9 | +24.4 -> +0.5 |
| P | -0.8 -> -3.1 | +1.7 -> -0.5 | +0.6 -> -1.7 | -7.8 -> -10.4 | -2.3 -> -5.8 | -56.0 -> -67.8 |

Predictions L14: (a) tip c_n in the pre-registered range at all four attached cells PASS; (b) c_n 0.30-0.63 change <= 0.1 pp
PASS; (c) P ratio F_Cl/v1.3 0.977/0.978/0.972/0.977 (S5/S6/S8/H7), -2.2..-2.8 % PASS; (d) S5 also inside 10 % at 0.95
(prediction wrong in the favourable direction). F_Cl generalises across speed and sequence in attached flow (S5-S8, H7).

## Known cost and limitations (reported, not hidden)

- **S8 P leaves the R3 band: -7.8 -> -10.4 %.** This is the one R3 regression F_Cl introduces. R3 with F_Cl: H7 passes all;
  S5 fails c_n 0.63 (-10.4, v1.3 -10.3, pre-existing polar offset); S6 fails c_n 0.30 (+16.3, pre-existing); S8 fails c_n
  0.30/0.47 (pre-existing) and now P. The power loss is the physical removal of tip lift (-2.2..-2.8 %), not a fit; the
  adoption accepts it.
- **Stall is extrapolation.** F_Cl is derived for attached flow (alpha 3-7 deg) and is a fixed factor of cl (0.178 at r/R 0.95),
  independent of alpha. In the stall runs the tip c_n ratio F_Cl/v1.3 is 0.829 (U10) and 0.808 (U15; pure factor 0.822), P
  drops 3.6 % (U10) and 26.8 % relative at U15 where torque is a small residual of stalled sections (-56 % already in
  v1.3). The v1.3 stall errors (tip +24 %, inboard -2..-54 %) resemble the BEM stall references: they are polar and URANS
  limits, not a tip effect. Stall results are limitations documentation (S6 of the extension), never validation; any stall
  table reports F_Cl on and off side by side.
- S5 and S6 (both arms) flag DRIFT (cp variation ~2 %), as the U5/U6 baselines did before.
- c_n at r/R 0.30 is unchanged by F_Cl and stays the known root residual (out of scope, S4 of `tip-model-analysis.md`).

## What adopting it changes

- `config/model-definition.yaml` is v1.4 (adds `nearTipCorrection.{model,table,kernel,sigmaOverC}`, active on);
  `config/model-definition-v1.3.yaml` is the frozen v1.3; registry variant `v1.3` now reproduces the frozen file, `v1.4`
  the record. `checkModelDefinition.py` defaults to v1.4; `summarizeVariants.py` takes v1.4 as baseline and resolves an
  unlabelled run that conforms to both `v1.4` and `tip-pitch-dag-sorensen-neartip` (identical definitions) to the record.
- v1.3 results stay reproducible and conform with `--variant v1.3` (or `--definition config/model-definition-v1.3.yaml`);
  they are no longer of record. F_Cl runs conform to v1.4 with no flag.
- **Not done here (follow-up, outside the T1 edit surface):** the renderer default of `--near-tip-correction` is still `off`
  (plain `runPhaseVI.sh` renders the v1.3 definition; a record render needs `--near-tip-correction on` or `VARIANT=v1.4`),
  the committed twins `case/system/fvOptions.*` have no near-tip block, and `tests/test_phasevi_pitch_reference.py::
  test_runner_default_is_the_record_and_forwards_the_reference` still expects a plain render to conform to the record.
  Switching the renderer default needs `generate_case.py`, `config/case.yaml`, `runPhaseVI.sh`, the launchers (which must
  pin `--near-tip-correction off` for v1.2/v1.3 arms) and the twins, as the v1.3 adoption did (commit `988fee6`).
