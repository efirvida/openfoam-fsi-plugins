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
- [x] **K2 (submitted; results not read yet)** `scripts/slurm/asm-epsilon-sensitivity.slurm` (one script, `meshFactor` from an
      environment variable) and the four submissions; read `sacct` before reporting anything.
- [ ] **K3** Read the four arms with the committed scripts; table in the plan log.

## Submitted 2026-10-12 (library built 09:04:58, includes the P0.1 prefilter fix)

| meshFactor | eps/h | label | job | out | run dir (expected) |
|---|---|---|---|---|---|
| 1 | 2 | `asm-mf1` | 11613259 | `runs/asm-mf1.out` | `runs/asm-U7-coarse-asm-mf1` |
| 0.5 | 1 | `asm-mf0p5` | 11613260 | `runs/asm-mf0p5.out` | `runs/asm-U7-coarse-asm-mf0p5` |
| 2 | 4 | `asm-mf2` | 11613261 | `runs/asm-mf2.out` | `runs/asm-U7-coarse-asm-mf2` |
| 4 | 8 | `asm-mf4` | 11613262 | `runs/asm-mf4.out` | `runs/asm-U7-coarse-asm-mf4` |

Submit line: `sbatch --export=ALL,MESH_FACTOR=<f>,RUN_LABEL=<label> --output=runs/<label>.out --error=runs/<label>.err scripts/slurm/asm-epsilon-sensitivity.slurm`.
Do NOT rebuild `libturbinesFoam` while any of these is queued or running.

**K3 recipe (after the jobs end).** For each arm read `sacct -j <job> --format=JobID,State,Elapsed,ExitCode,MaxRSS`
and the `.out`/`.err` before anything else; then
`python3 scripts/comparePhaseVI.py --run-dir runs/asm-U7-coarse-<label> --speed 7 --sequence H --allow-short-window`
and `python3 scripts/compareSectionLoads.py --alm-dir runs/asm-U7-coarse-<label>`; the comparator arm is
`runs/alm-U7-coarse-hubfix`. Check `run.json` has `mesh_factor` equal to the arm before trusting the label.
