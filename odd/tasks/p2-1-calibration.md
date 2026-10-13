# P2.1 — Phase VI Sequence H calibration (submitted 2026-10-13)

Plan: `odd/tasks/validation-master-plan.md` (P2.1). Layout: equispaced dz 0.05 (Model Definition v1.1, P1.5).
Config: coarse (D/32), delta t 0.001 s, **12 revolutions**, 84 tasks, 24 h limit, `scripts/slurm/p2-1-calibration.slurm`.
The "ASM+mesh has zero runs / check staging" note in the plan is stale: P1.5 E3 ran it (`asm-mesh-U7-coarse-eqb-mesh-*`).

| run dir (`runs/`) | model | U [m/s] | job |
|---|---|---|---|
| `alm-U7-coarse-p21` | alm | 7 | 11614175 |
| `alm-U10-coarse-p21` | alm | 10 | 11614176 |
| `asm-U7-coarse-p21` | asm | 7 | 11614177 |
| `asm-U10-coarse-p21` | asm | 10 | 11614178 |
| `asm-mesh-U7-coarse-p21` | asm-mesh | 7 | 11614179 |
| `asm-mesh-U10-coarse-p21` | asm-mesh | 10 | 11614180 |

Expected: ~5 h (ALM/ASM) to ~8 h (ASM+mesh) of run time each, at 12 revs (E3 took 1.7-2.7 h for 4 revs).
A run that hits the 24 h limit is resumed by resubmitting the same command (`--restart`).

## Resume here (fresh session, high effort, once `sacct` shows COMPLETED)

1. `sacct -j 11614175,11614176,11614177,11614178,11614179,11614180 -X --format=JobID,State,Elapsed`;
   `python3 turbinesFoam/validation/tools/case_state.py` for revolutions reached.
2. Per run: `python3 scripts/comparePhaseVI.py --run-dir runs/<dir> --speed <U> --sequence H --out /tmp/cmp_<dir>`
   (full 12-rev window, so NO `--allow-short-window`; `run.json` `blade_dz` must be 0.05).
3. Judge against the pre-registered bands (Model Definition): |%P|, |%T| <= 15 %, spanwise cn within +-15 % at
   r/R 0.30/0.47/0.63/0.80, |cp_ASM - cp_ALM|/cp_ALM <= 2 %, ASM+mesh vs ALM same band as ASM.
4. Open question carried from P1.5 E3: ASM+mesh sits 3.6 % below ALM in power on 4 revs
   (`odd/issues/asm-mesh-residual-vs-alm.md`); confirm or retire it on the 12-rev window.
5. Then P2.2 (Sequence S) per the plan. Do not rebuild `libturbinesFoam` while any run is queued or running.
