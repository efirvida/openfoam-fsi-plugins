# Handoff — A/B variant results analysis (rewritten 2026-10-21)

Fresh session, effort `medium`. Feature document: `odd/tasks/alm-correction-flags.md` (read until `## Log`, entries L7-L11).
Rules: AGENTS.md; Slurm `--ntasks` only (no nodes, no memory); do not rebuild `libturbinesFoam` while jobs run; no fitted coefficients.
The owner monitors the jobs; resume when they say the jobs ended.

## Git
- Primary worktree is on `feat/phasevi-paper-yaw-pilot` (another session's branch, paper-like pilot). Do NOT switch it.
- Commit to `main` from the git-excluded worktree `.wt-main` (already on `main`, last commits `8b72b47` reader fix, `d7d03e6` R1 closed). Nothing pushed (owner decides).
- Run analyses from the primary worktree (`runs/` lives there, git-ignored); `comparePhaseVI.py` is identical on both branches.

## Jobs in flight (submitted 2026-10-21)
| Job | What | Run dir (`turbinesFoam/validation/phaseVI/runs/`) | Partition |
|---|---|---|---|
| 11620999 | resume shen-tip S U5 to 24 rev | `alm-U5-coarse-seqS-var-shen-tip` | bigmem |
| 11621000 | resume dag-sorensen-tip S U5 | `alm-U5-coarse-seqS-var-dag-sorensen-tip` | bigmem |
| 11621001 | resume ch-ra S U5 | `alm-U5-coarse-seqS-var-ch-ra` | bigmem |
| 11620980 | ring-sampling S U5 from 0, 24 rev | `alm-U5-coarse-seqS-var-ring-sampling` | bigmem |
| 11621005 | v1.2 baseline H 7, 12 rev | `alm-U7-coarse-v12` | bigmem |
| 11621006 / 11621007 | shen-tip / dag-sorensen-tip H 7 | `alm-U7-coarse-var-<variant>` | bigmem |
| 11621008 / 11621009 / 11621010 | ring-sampling / du-selig-ra / ch-ra H 7 | `alm-U7-coarse-var-<variant>` | sequana_cpu |

H 7 dir names are expected (not created yet at writing): confirm with `ls runs | grep '^alm-U7-coarse-\(v12\|var-\)'`.
Already complete: `alm-U5-coarse-seqS-var-du-selig-ra` (24.1 rev) and baseline `alm-U5-coarse-seqS-v12`.
Check: `sacct -u $USER -S 2026-10-21 -X --format=JobID,JobName%28,State,Elapsed`; progress: `python3 ../tools/case_state.py --rpm 72 <run dirs>` (segment 0 only — a resumed run has a second segment `postProcessing/turbines/<time>/`).
If one TIMEOUTs: `sbatch --partition=<same> --time=08:00:00 --export=ALL,RUN_DIR=runs/<dir>,LIB_DIR=runs/lib-flags scripts/slurm/resume-run.slurm` (omit `LIB_DIR` for the v1.2 baseline). Never resubmit `variant-run.slurm`/`v1-2-run.slurm` on a dir with written state.

## Next steps
1. S U5 final (all six dirs above at 24 rev), window 16..24 (T11 rule), then summary; record as an L-entry in `alm-correction-flags.md` next to the interim 12..17 table of L10.
2. H 7: baseline + 5 arms, default window 4..12; summary; record; then close C5 (verdict per switch across H 7 and S 5/7/8).
3. C2 (Muscari 2024 / Xie 2021 velocity sampling, build into `runs/lib-c2`, NOT `runs/lib-flags`) and C3 (filtered lifting line) in a fresh session.

## Commands (from `turbinesFoam/validation/phaseVI`)
```sh
E=data/experiment/uae6-archive; A=$TMPDIR/ab16; mkdir -p $A
for r in v12 var-shen-tip var-dag-sorensen-tip var-ring-sampling var-du-selig-ra var-ch-ra; do
  python3 scripts/comparePhaseVI.py --alm-dir runs/alm-U5-coarse-seqS-$r --experiment $E --speed 5 --sequence S \
    --revolutions 16 24 --out $A/S-U5-$r > $A/S-U5-$r.log 2>&1; echo "$r $?"; done
python3 scripts/summarizeVariants.py $(ls -d $A/S-U5-*/)
# H 7: --alm-dir runs/alm-U7-coarse-{v12,var-<variant>} --speed 7 --sequence H, out $TMPDIR/abH/H-U7-<name>
```
Each comparison takes ~20-30 s: run loops with `bash_background`.
Gotchas: use `--alm-dir`, never `--run-dir` (it keys the model by directory name and every change vs v1.2 prints `n/a`); a DRIFT baseline also prints `n/a` by design; use `$TMPDIR`, not `/tmp/ab` (another user's file on some login nodes).

## Interim result (L10, S U5, revs 12..17, diagnostic only)
P error vs experiment: v1.2 +26.7 %; dag-sorensen-tip +20.3 % (-6.5 pp, tip fixed, cn0.30 +10 pp worse); ch-ra +24.0 %; du-selig-ra +26.7 %; shen-tip +33.5 %. No isolated switch removes the speed-dependent error (same conclusion as L7 at 7/8 m/s).

## Production criteria (validation-model-definition.md)
R1 PASS (2026-10-21, level 1 -> 2 max 0.42 %); R2 FAIL (this A/B); R3 open; R4 diagnosing; R5, R6 done.
Known unrelated: 2 pre-existing failures in `test_phasevi_yaw_pitch_reference.py` (`pitch_spanwise.csv` header), probably from the pilot branch work; `compareSectionLoads.py --help` crashes (`%` in help text).
