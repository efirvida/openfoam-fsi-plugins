# Phase VI wind-tunnel blockage domain (`--domain tunnel`)
Close the free box on the NASA-Ames 24.4 x 36.6 m test section so blockage (rotor/section 8.9 %) is modelled; cell size around the rotor unchanged so the domain is the only change. Branch `feat/v13-adoption-asm`, worktree `.worktrees/tip-pitch`.

## Specs
- S1: "si por favor" (owner) to "Bloqueo del túnel. Está documentado como 'no simulado' ... Es barato: solo cambia el dominio y las paredes."
- S2: `--domain tunnel`: y in [-18.3, 18.3] m, z in [0, 24.4] m (hub 12.192 m), x as `long`; same 18-block topology; slip walls (symmetryPlane) as the other domains.
- S3: Cell size beside the rotor preserved (core y block cells unchanged; the y cells next to the core, and the hub-adjacent z cells, keep their size exactly); only block lengths/cell counts/gradings of the outer y blocks and both z blocks change.
- S4: `long` and `squat` outputs byte-identical to before.
- S5: Caveat to record in README: slip walls = upper bound of blockage (no tunnel wall boundary layer); blockage raises loads, so it helps under-predicted points (U8 inboard, S5 mid-span) and worsens over-predicted ones (tip, root).
- S6: Test: `turbinesFoam/tests/test_phasevi_tunnel.py` (written, RED: needs `blockage_ratio`, `domain_resolution`, `axis_extents_D(..., "tunnel")`).

## Tasks
- T1 (S2-S6): implement in `phaseVI/tools/case_config.py`, `generate_case.py`, `config/case.yaml`, `scripts/mesh.sh`, `scripts/runPhaseVI.sh` (domain choice + `-tunnel` run-dir suffix like squat), README, CHANGELOG. Route: gentle-ai-worker. Commit: 9f81b87 (done).
- T2: run ALM v1.3 S U7 coarse tunnel (12 rev) on Slurm, compare vs free-box ALM. Route: parent. Commit: n/a (run).

## Log
- L1 (owner, 2026-11-02): "si por favor" (go ahead with the tunnel blockage).
- L2 (agent, 2026-11-02): T1 done by gentle-ai-worker (9f81b87), 7/7 new tests, long/squat blockMeshDict byte-identical (coarse/fine/ultra), coarse tunnel blockMesh+checkMesh OK (2.61 M cells vs 6.67 M; fine 8.96 M; ultra 21.07 M), core cell 0.3143 m preserved; also fixed cell_sizes for uniform blocks (ratio 1). T2 submitted: job 11637399 (sequana_cpu, 24 h, 84 ranks) `VARIANT=tip-pitch-dag-sorensen MODEL=alm SPEED=7 SEQUENCE=S END_REVS=12 POLAR=S809_OSU_Re1M_total.dat LABEL=var-tip-pitch-dag-sorensen-total-tunnel LIB_DIR=runs/lib-v13 ... variant-run.slurm --domain tunnel` from the tip-pitch worktree at 9f81b87. RESUME: when it ends, check End/endTime, checker CONFORMS v1.3, then comparePhaseVI --alm-dir <tunnel run> vs `runs/alm-U7-coarse-seqS-var-tip-pitch-dag-sorensen-total` (free box ALM S U7: P +0.7, c_n 0.30 +11.3, 0.47 -1.5, 0.63 -1.6, 0.80 +2.9, 0.95 +26.2), window 4..12. Prediction (agent, before the run): blockage raises loads: P and c_n up by roughly 2-6 % (slip walls = upper bound), so 0.47-0.80 stay inside 10 %, 0.30 and 0.95 move further out, P stays within 10 %.
