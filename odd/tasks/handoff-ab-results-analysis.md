# Handoff — A/B variant results analysis (written 2026-10-20)

Fresh session, effort `medium`. Feature document: `odd/tasks/alm-correction-flags.md` (read until `## Log`, entries L7-L9).
Rules: AGENTS.md; Slurm `--ntasks` only (no nodes, no memory); do not rebuild `libturbinesFoam` while jobs run; no fitted coefficients.

## State
- Branch `main`; last commits `94edd3c` (comparePhaseVI joins resume segments) and the L9 note. Nothing pushed (owner decides).
- Done: C1 (A/B switches), C4 (`ch-ra`). Pending: C2 (Muscari 2024 / Xie 2021 velocity sampling, build into `runs/lib-c2`, NOT `runs/lib-flags`), C3 (filtered lifting line).
- Sequence S U7/U8 A/B table is complete (L7). Conclusion: no isolated switch removes the speed-dependent error (v1.2: U5 P +28 %, U6 +14 %, U7 -2 %, U8 -20 %) without breaking U7 or root/tip. shen-tip fixes U8 but U7 +12 % and tip cn +44 %; du-selig-ra/ch-ra help U8 but cn0.30 +28..32 % at U7; dag-sorensen-tip and ring-sampling are neutral.
- Submitted 2026-10-20 on `sequana_cpu_bigmem`, SEQUENCE=S SPEED=5 END_REVS=24: shen-tip 11619690, dag-sorensen-tip 11619691, ring-sampling 11619692, du-selig-ra 11619693, ch-ra 11619694 (`LIB_DIR=runs/lib-flags`). Outputs `runs/var-<variant>-S-U5.{out,err}`, case dirs `runs/alm-U5-coarse-seqS-var-<variant>`. Check with `squeue -u $USER` / `sacct`.
- Not launched: H 7 m/s arms. No unambiguous v1.2 H-7 baseline run exists; run a v1.2 baseline first (`variant-run.slurm`-style, SEQUENCE=H SPEED=7), then the 5 arms.

## Next steps
1. When the S 5 jobs end, compare each (commands below), then `summarizeVariants.py`; add the S U5 rows to L7-style entry in `alm-correction-flags.md`.
2. Baseline U5 and U6 (`alm-U5-coarse-seqS-v12`, `alm-U6-coarse-seqS-v12`) flag DRIFT (not converged). Decide whether they are usable as baselines or need a longer run.
3. H 7 baseline + arms (see above), then close C5.
4. C2 and C3 in a fresh session.
5. Fix the remaining segment-0-only readers: `scripts/plotComparisonFigures.py:36`, `scripts/proxyRotationalAugmentation.py:145` (reuse `comparePhaseVI.read_rows_resumed`, add a test).

## Commands that work (from `turbinesFoam/validation/phaseVI`)
```sh
E=data/experiment/uae6-archive    # REQUIRED: data/experiment/ has only the S 7 m/s row
python3 scripts/comparePhaseVI.py --run-dir runs/alm-U5-coarse-seqS-var-shen-tip --experiment $E --speed 5 --sequence S --out /tmp/ab/S-U5-var-shen-tip
python3 scripts/comparePhaseVI.py --run-dir runs/alm-U5-coarse-seqS-v12 --experiment $E --speed 5 --sequence S --out /tmp/ab/S-U5-v12
python3 scripts/summarizeVariants.py $(ls -d /tmp/ab/S-U*/)   # directories only, not the .log files
```
`/tmp/ab` is temporary: regenerate if gone. Each comparison takes ~15-20 s; run long loops with `bash_background`.
Gotchas: the summary prints `n/a` for change-vs-v1.2 when the output directory name does not follow `S-U<n>-<variant>`/`var-<variant>`; a run that was resumed has several `postProcessing/turbines/<time>/` segments (use `case_state.py` carefully, it reads segment 0 only).
Unrelated: jobs `b3-2-measure` in the queue belong to `fem-shell`.
