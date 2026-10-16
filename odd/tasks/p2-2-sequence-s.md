# P2.2 — Phase VI Sequence S frozen evaluation (submitted 2026-10-14)

Plan: `odd/tasks/validation-master-plan.md` (P2.2). Same configuration as P2.1 (`p2-1-calibration.md`), nothing
touched in between (plan rule 2); only `--sequence S` differs. Config: coarse (D/32), delta t 0.001 s,
**12 revolutions**, 84 tasks, blade dz 0.05, `scripts/slurm/p2-2-sequence-s.slurm`.

| run dir (`runs/`) | model | U [m/s] | job |
|---|---|---|---|
| `alm-U7-coarse-seqS-p22` | alm | 7 | 11615752 |
| `alm-U10-coarse-seqS-p22` | alm | 10 | 11615753 |
| `asm-U7-coarse-seqS-p22` | asm | 7 | 11615754 |
| `asm-U10-coarse-seqS-p22` | asm | 10 | 11615755 |
| `asm-mesh-U7-coarse-seqS-p22` | asm-mesh | 7 | 11615756 |
| `asm-mesh-U10-coarse-seqS-p22` | asm-mesh | 10 | 11615757 |

Submitted together with the H1 root-factor A/B (`alm-U7-coarse-p21-rootoff`, job 11615758,
`odd/tasks/nacelle-onoff-study.md`). Four run at once, the rest queue.

## Resume here (once `sacct` shows COMPLETED)

1. `sacct -j 11615752,11615753,11615754,11615755,11615756,11615757 -X --format=JobID,State,Elapsed`;
   `python3 turbinesFoam/validation/tools/case_state.py runs/<dir>` for revolutions reached.
2. Per run: `python3 scripts/comparePhaseVI.py --run-dir runs/<dir> --speed <U> --sequence S --out /tmp/cmp_<dir>`.
   `data/experiment/` holds only the S 7 m/s row; for 10 m/s point `--experiment` at
   `data/experiment/uae6-archive/` (check the column layout first; it has all 21 speeds).
3. Judge against the pre-registered bands (`validation-model-definition.md`, "Pre-registered bands"):
   `abs(%P)` <= **10 %** (not 15 %: `p2-1-calibration.md` step 3 misquoted it), `abs(%T)` <= 15 %,
   `c_n` +-10 % at r/R 0.47-0.80 and +-15 % at 0.30 (0.95 reported only), ASM-ALM and ASM+mesh-ALM <= 2 %.
   On H the 7 m/s power already sat at -11 / -11 / -14.5 %, so S may fail the power band; report it, do
   not retune. This is the validation that is quoted.
4. Then the 21-point S curve (trend and stall onset) per the plan.

## Results (2026-10-16) — judged with `scripts/summarizeBands.py` on `comparePhaseVI.py` output

Jobs 11615752-56 COMPLETED (12 rev). 11615757 (asm-mesh U10) FAILED at t=5.48 s: InfiniBand completion error
(`uct_ib_mlx5_check_completion` inside an MPI Allreduce, nodes sdumont6037/6247), infrastructure, not code.
Resubmitted unchanged as job **11616862** (`--restart`, no written time, restarts from 0; ~8.5 h).

| run | %P (band 10) | %T (band 15) | c_n 0.30 (15) | 0.47 | 0.63 | 0.80 (10) | 0.95 (report) |
|---|---|---|---|---|---|---|---|
| ALM 7 | -11.0 FAIL | -0.7 pass | +15.1 FAIL (marginal) | +1.8 | +2.4 | -0.3 | -12.1 |
| ASM 7 | -10.9 FAIL | -0.6 pass | +15.1 FAIL (marginal) | +1.8 | +2.4 | -0.3 | -12.1 |
| ASM-mesh 7 | -14.4 FAIL | -2.9 pass | +12.9 pass | +0.4 | +1.0 | -2.8 | -11.6 |
| ALM 10 | -43.5 FAIL | -28.1 FAIL | -40.5 | -39.3 | -17.6 | -19.4 | -43.0 |
| ASM 10 | -43.3 FAIL | -27.9 FAIL | -40.5 | -39.0 | -17.5 | -19.4 | -43.0 |

- 7 m/s: ASM-ALM power 0.1 % (pass, <= 2 %); ASM-mesh vs ALM -3.9 % (fails the 2 % band). Power misses by
  ~1 point (ALM/ASM) as predicted from H; thrust and mid-span c_n are inside the bands.
- 10 m/s: the experiment is in 3-D stall delay (c_n 1.29-1.35 at r/R 0.30-0.47); the model has no
  rotational augmentation, so the underprediction is structural. Reported, not retuned (plan rule 2).
- The comparison script's own band is 15 % for power; the 10 % verdict comes from the summary script.

Next: when 11616862 completes, judge asm-mesh U10; then the 21-point S curve.
