# Model improvements register — every candidate lever, its status and what would reopen it

Owner request 2026-10-17: "recuerda que habiamos hablado de algunas posible mejoras no se si se estan
teniendo en cuenta o se olvidaron". Until now the candidates lived scattered across
`p2-2-next-cycle-plan.md` (literature review, papers read), `phasevi-fllt-feasibility.md`,
`phasevi-tiploss-calibration.md` and the master-plan log. This file is the single list; a candidate
changes status only with evidence or an owner decision, recorded here with the date.

Standing rules: no literature method is implemented without the owner; no fitted coefficient enters the
definition; stall-regime runs are out of scope (owner, 2026-10-17) and stall levers are parked as
documented limits, not discarded.

| id | lever | targets | status | evidence | reopen condition |
| --- | --- | --- | --- | --- | --- |
| I1 | Pressure-drag polar (MIRAS Eq. 17-18 idea: only pressure drag in the tangential force) | tangential force, power | **ADOPTED (v1.2)** | D3 H 7 m/s: power -11.0 -> -2.2 %, F'n unchanged | full Cd_p/Cd_f split per section from an integral BL code only if S (T1) does not confirm the gain |
| I2 | Glauert tip loss instead of D&S | tip normal force | **ADOPTED (v1.2)** | Glauert tip c_n -14 %, D&S +51 %; IEA Glauert +2.8 % vs OLAF, D&S +5.5..6 % | IEA re-evaluation contradicts it |
| I3 | Dag & Sorensen tip correction | tip | DROPPED (v1.2) | +50..77 % tip c_n in every arm; resolution-dependent | none planned |
| I4 | Muscari 2024 effective-velocity sampling / Xie 2021 Lagrangian sampling (reduce epsilon dependence) | tip and angle errors that depend on eps | **NOT TRIGGERED (T5, 2026-10-18)**: halving eps (0.63 -> 0.31 m) moved tip c_n 0.95 from -14.3 to -14.1 % and left tip F'n unchanged (139.3 N/m both) | literature only; power ~independent of eps below rated in their tests | T5 shows tip c_n moving > 2 points with eps (P2.3 decision rule) -> owner decision |
| I5 | Filtered lifting line (Martinez-Tossas 2019/2023) | tip lift with eps > 0.25 c | NO-GO (2026-09-30); T5 2026-10-18 did NOT show double counting (tip c_n +0.2 points), reopen condition not met | offline: < 2 points of tip c_n | T5 shows double counting (tip c_n drops > 2 points) -> re-run the offline estimate on the Glauert state |
| I6 | Resolution-aware tip correction (Glauert strength scaled by resolved induction) | tip | **REFUTED premise (T5, 2026-10-18)**: no double counting (tip c_n +0.2 points with eps halved) | follows from the T5 double-counting hypothesis | T5 confirms double counting; must be physics-derived, not fitted (I9 is the forbidden version) |
| I7 | Chaviaropoulos-Hansen rotational augmentation (Burgos Tafur 2020, a = 2.2, no fitted tables) | 10 m/s stall-delay miss | **IMPLEMENTED behind flag, not yet A/B tested** | Original baseline a=2.2, h=1, n=4; `ch-ra`; twist excludes pitch; fixed 2*pi inviscid lift; positive drag increment relative to Cd(alpha=0). Du-Selig evidence remains separate | C4 / alm-correction-flags S1, S2.4; A/B against v1.2 required before adoption |
| I8 | Du-Selig rotational augmentation (a = b = d = 1) | stall delay | NOT ADOPTED | B: power -6.5 % but c_n 0.30 +28 % (fails) | same as I7 |
| I9 | Tip-loss strength fit (g = 1.532 / Shen c2 ~ 13.7) | tip | FORBIDDEN (fitted) | `phasevi-tiploss-calibration.md` | never as definition; may be quoted as a diagnostic of how far Glauert is |
| I10 | Standard Shen tip correction (c2 = 21) | tip | REJECTED | offline +37.5 % tip c_n | none |
| I11 | Kleine 2023 non-iterative smearing correction | speed/stability | NOT A LEVER | authors: no accuracy difference vs iterative | none |
| I12 | Reynolds-consistent inboard polar (local Re 0.62e6 at r/R 0.30 vs polar 1e6) | root normal force | **CANDIDATE, owner decision** | T3(d): CSU 0.65e6 -9 % c_n (facility change too), OSU 0.75e6 -1.2 %; most of the +13 % is normalisation (T3(c)) | after T1, if the 0.30 band is judged on force and still fails |
| I13 | Zilic de Arcos 2020 angle-of-attack definition check | angle diagnostics | DIAGNOSTIC, not done | near the tip AoA is ill-defined | needed for the limits chapter (T6) |
| I14 | IEA 15 MW polars at operating Re (1.4e7 vs tables at 3e6) and drag split | IEA pillar | **OPEN (pillar 2)** | `p2-2-next-cycle-plan.md` small items | before the IEA v1.2 re-evaluation |
| I15 | OpenFAST gust model completeness (SeaState/HydroDyn/SubDyn, platform DOFs off) | IEA reference | OPEN, minor | repo files pre-v5 | only if the floating case enters the thesis |
| I16 | Glauert factor one-step lag (H3b) | tip | MEASURING (T4) | solver column `end_effect_phi_deg`, predicted ~0 | T4 result |
| I17 | Ring velocity sampling (radius 3.3 eps, 16 points; Jost 2018 / Zormpa 2025): intended to reduce eps dependence | angle error, tip | **NOT TRIGGERED (T5, 2026-10-18)**: tip shows no eps dependence (-14.3 -> -14.1 %) | listed as frozen in v1.1 but never run; v1.2 declares point sampling (owner 2026-10-17) | T5 shows eps dependence of the tip (> 2 points) -> owner decision, compare with I4 |

Not levers (kept so they are not proposed again): nacelle (no effect, T2), hub loss at r/R 0.30 (factor ~0.99),
station interpolation (< 0.2 %), FLOWUnsteady as a reference (over-predicts the tip +72 %).
