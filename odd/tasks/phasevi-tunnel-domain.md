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
- T1 (S2-S6): implement in `phaseVI/tools/case_config.py`, `generate_case.py`, `config/case.yaml`, `scripts/mesh.sh`, `scripts/runPhaseVI.sh` (domain choice + `-tunnel` run-dir suffix like squat), README, CHANGELOG. Route: gentle-ai-worker. Commit: pending.
- T2: run ALM v1.3 S U7 coarse tunnel (12 rev) on Slurm, compare vs free-box ALM. Route: parent. Commit: n/a (run).

## Log
- L1 (owner, 2026-11-02): "si por favor" (go ahead with the tunnel blockage).
