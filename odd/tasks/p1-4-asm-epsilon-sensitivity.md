# P1.4 — ASM epsilon/h sensitivity (Phase VI, 4 revolutions)

Plan: `odd/tasks/validation-master-plan.md` (P1.4). Approved by the owner 2026-10-12.

Arms: ASM, coarse level 0, 7 m/s, sequence H, delta t 0.001, 4 revs, 84 tasks (same as
`hubfix` / `s6`, so directly comparable). `meshFactor` 0.5 / 1 / 2 / 4, i.e.
`eps/h` = 1 / 2 / 4 / 8, `eps` = 0.31 / 0.63 / 1.26 / 2.5 m (R = 5.029 m). `meshFactor 1`
is the frozen definition. Comparator: `runs/alm-U7-coarse-hubfix` (ALM, `meshFactor 1`).
Metrics: `comparePhaseVI.py` (cp, ct), `compareSectionLoads.py` (R per station), ASM minus ALM.
Cost: about 145 core-h per arm (S6 took 1 h 43 min on 84 tasks), 4 independent jobs; the
fourth waits in the queue while a `fem-shell` job holds one of the four slots.
Caveat: 4 revs is not converged (cp drifts ~0.7 %/rev); arms compare with each other, the
absolute level is not claimed.

- [x] **K1** `--mesh-factor F` in `tools/generate_case.py` and `scripts/runPhaseVI.sh`, recorded in
      `run.json`; test first.
- [ ] **K2** `scripts/slurm/asm-epsilon-sensitivity.slurm` (one script, `meshFactor` from an
      environment variable) and the four submissions; read `sacct` before reporting anything.
- [ ] **K3** Read the four arms with the committed scripts; table in the plan log.
