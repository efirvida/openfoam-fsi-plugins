# FLOWUnsteady Phase VI code-to-code case
Reproduce NREL Phase VI sequence H at 7 m/s (72 rpm, 3 deg tip pitch, 0 deg yaw) in FLOWUnsteady (Julia, VLM-ALM + VPM) with OUR geometry and S809 polars,
to explain the gap between FLOWUnsteady (Mehr 2024 Fig. A4: CQ +7 % vs our measured 0.0653) and our ALM (-11 % power, -2.2 % with the D3 pressure-drag polar).

## Specs
- S1: "No implementes nada de la literatura sin mi decisión." This task builds an EXTERNAL reference run only; nothing is added to the turbinesFoam model.
- S2: "Slurm: solo --ntasks." No nodes/memory/exclusive/cpus-per-task.
- S3: Run DS (Du-Selig, `apply_correction3D`) on/off x total/pressure drag polar (4 runs) at 7 m/s, report CQ, CT, CP and the station force x arm table in the same format as `compareSectionLoads.py`.
- S4: Inputs come from the repository data only: `data/geometry/phaseVI_blade.csv`, `data/s809/s809_somers_nlr.csv`, `data/polars/S809_OSU_Re1M_{total,pressure}.dat`; case values from `config/case.yaml` (rho from the experiment row, 72 rpm, pitch 3 deg).
- S5: Exact FLOWUnsteady settings must be recorded in the run directory (it saves the script); Mehr 2024 does not state DS/drag, so none of them is claimed as THE reference.

## Tasks
- T1 (S4): `scripts/buildFlowUnsteadyDatabase.py` writes a FLOWUnsteady database (rotors/ CSVs, airfoils/ contour + polar) from repo data; tested.
- T2 (S3): `flowunsteady/phaseVI.jl` + slurm script (ntasks only); smoke test on `sequana_cpu_dev`.
- T3 (S3): sign check: turbine_flag/precone/pitch reproduce CT ~0.46, torque > 0 at TSR 5.4.
- T4 (S3,S5): 4 production runs. DONE: jobs 11617387-90 COMPLETED, 10 rev, convergence gate passes (session 3).
- T5: compare table + record in `p2-2-next-cycle-plan.md`. DONE: `scripts/compareFlowUnsteadyStations.py` (+ tests), results in the plan ("Session 3 results"), README rewritten.

## Log
- L1 (user, 2026-10-16): "Continúa el trabajo de P2.2. Lee la sección "HANDOFF — resume here" de odd/tasks/p2-2-next-cycle-plan.md ... No implementes nada de la literatura sin mi decisión. Slurm: solo --ntasks."
- L2 (user): "si, vamos a continuar entonces, el job B lo analizamos despues cuando termine"
- L3 (agent, 2026-10-16) T2/T3 outcome: worker's `turbine_flag=true` run FAILED the extraction check (force.velocity < 0, D/L at 0.47R = 0.74). `flowunsteady/signScan.jl` (wake-free, 16 combinations) shows the only physically consistent global force is `turbine_flag=false`, pitch = -(twist+3), Vinf = -x, CW=false; torque is reported as -torque (propeller sign). Smoke 11617359 (2 rev, DS on, total drag): P_monitor 7334 W vs force.velocity 7306 W (both > 0); CT 0.658 -> 0.598 and CQ 0.0955 -> 0.0800 falling with wake age (not converged: acceptance band CT 0.45-0.47 / CQ 0.065-0.070 is for the converged run, not the smoke). Wall 148 s + 412 s per revolution (48 tasks, one node).
- L4 (agent): T4 submitted: jobs 11617371 (total, DS on), 11617372 (total, DS off), 11617373 (pressure, DS on), 11617374 (pressure, DS off); `scripts/slurm/flowunsteady-production.slurm`, 48 tasks, 06:00:00, 10 revolutions. Convergence must be checked (CT drift < 1 % per revolution) before comparing; extend if not.
- L5 (agent): first submissions (11617371-74, 48 tasks) and a 32-task retry (11617376-77) FAILED in 1 s: with `--ntasks` alone Slurm spread the tasks over 4-6 nodes and the script refuses a multi-node allocation (Julia threads are shared memory). Owner decision (2026-10-16): exception `--nodes=1` for these Julia runs ("pero no hay que pedir los 48 cores del nodo creo yo": do NOT request the whole node). Resubmitted as `--nodes=1 --ntasks=24 --time=10:00:00`: jobs 11617387 (total, DS on), 11617388 (total, DS off), 11617389 (pressure, DS on), 11617390 (pressure, DS off). They wait on `AssocMaxJobsLimit` (the association's running-job cap is shared with other sessions' jobs).
- L6 (user, 2026-10-17): "ya terminaron todas las simulaciones que estaban en el HPC vamos a continuar las validaciones"
- L7 (agent, 2026-10-17): T4/T5 closed. All four runs converge (< 0.1 %/rev) and over-predict: CQ +18 % to +29 % vs exp, CT 0.57-0.60 vs Mehr 0.459. Excess at the tip (r/R 0.95 F'n +72 %, F't +93..99 %) in every run; DS moves only r/R 0.30, drag only F't. The DS x drag hypothesis is refuted; whether to run an isolating variant (tip correction / smaller sigma) is an open owner decision.
