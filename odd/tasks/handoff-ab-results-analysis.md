# Handoff — A/B variant results analysis

## Resume here — 2026-10-22

The S5 and H7 jobs are complete. Do not resubmit them. C2 is deferred to a
separate session; C3 remains pending. No model changes, builds, simulations or
commits were made during this analysis/diagnostic correction.

### Final A/B and sectional evidence

- A/B artifacts: `turbinesFoam/validation/phaseVI/runs/ab-results-20261022/summary.txt`.
  All 26 comparison commands and both summaries exited 0. Late S5/S6 windows
  16..24 are stable; previous startup DRIFT does not invalidate these averages.
  This is not mesh/timestep-convergence proof.
- v1.2 power errors: S5 +26.5%, S6 +13.5%, S7 -2.1%, S8 -19.9%; H7 -2.2%.
  Existing-switch matrix H7/S5/S7/S8 is populated. No isolated switch resolves
  the trend without root/tip or U7 tradeoffs; do not promote an arm to baseline.
- Audited residuals: `runs/section-diagnosis-20261022/audited-residuals-U*.txt`
  relative to `turbinesFoam/validation/phaseVI/`. At r/R=0.30, alpha rises
  3.13/6.26/10.14/13.81 degrees while applied Cl rises 0.427/0.794/0.930/0.996.
  The static polar flattens before its post-peak decline; do not call all U8
  sections deep-stalled. Tip losses strengthen with speed. U7 also genuinely
  matches midspan loads: its good total is not solely a large cancellation.
- Low inboard Re (~0.58..0.64M) lies below the available multi-Re table range.
  Substituting CSU 0.65M at fixed inflow worsens both U5 and U8 inboard residuals;
  this is not a demonstrated Reynolds fix and changes facility as well.

### Corrected diagnostics and observed torque closure

User authorization, verbatim: "ok vamos a hacer las correcciones y reconciliacion de tests".
Four existing readers now join resumed histories, honor end windows and use
configured operating points. The angle output is a force-direction proxy, not
independent flow/induction evidence. The torque reader uses rowwise integrated
written fx/fy/fz moments, not an approximate integration of per-span f_ref_t.

Corrected artifacts: `turbinesFoam/validation/phaseVI/runs/section-diagnosis-20261022/corrected/`.
All twelve real torque/section/proxy commands exited 0 with empty stderr.

| S case | Window (rev) | Q rotor/rho | Q elements/rho | Ratio |
|---|---|---|---|---|
| U5 | 16..24 | 296.655750 | 296.651734 | 0.999986 |
| U6 | 16..24 | 480.787884 | 480.772750 | 0.999969 |
| U7 | 4..12 | 626.170045 | 626.130493 | 0.999937 |
| U8 | 4..12 | 707.333703 | 707.261869 | 0.999898 |

Only blade1 is written; scaling to two blades assumes axisymmetric averaging.
This supports internal force-to-torque consistency, not experimental validation.
CSV lacks sampled relative-velocity components, so independent flow-direction
attribution remains unavailable. Do not claim the polar-versus-sampling cause
has been identified. Five experimental stations cannot supply an exact radial
experimental torque distribution.

### Verification and delivery state

- Writer observed RED then GREEN: 53 focused tests passed; differential checks
  against HEAD covered all four CLIs. Parent repeated torque tests: 17 passed.
- Full Python suite job-2 exited 1: **672 passed, 3 skipped, 2 failed** in
  723.89 s. Both failures are
  `test_phasevi_yaw_pitch_reference.py::test_schema_prefix_matches_committed_sequence_tables[H|S]`
  at line 107: pitch_spanwise header lacks the three expected plane-reference
  columns (first mismatch: yaw_nominal_deg versus cth). These are the same
  known base failures recorded in `phasevi-paper-yaw-pilot.md` L8; their source
  and reference data were not changed here. Suite is not green; do not claim it.
- Independent verifier failed with provider error; unavailable, not approved,
  and not automatically retried. Native ASSESS was unassessable due to
  intended-untracked declaration; no review authority or approval was created.
- Changes remain uncommitted on `feat/phasevi-paper-yaw-pilot` (pre-existing
  branch). Preserve unrelated untracked `tools/__pycache__/` and
  `tools/tests/__pycache__/`. No push/PR/commit is authorized by this handoff.

## Handoff — 2026-10-21 (rewritten; jobs in flight at the time)

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

## Historical handoff — 2026-10-20 (superseded above)
### State
- Superseded by L10 of `alm-correction-flags.md` (2026-10-21): job ids and interim S U5 results live there.
- Branch `main`; last commits `94edd3c` (comparePhaseVI joins resume segments) and the L9 note. Nothing pushed (owner decides).
- Done: C1 (A/B switches), C4 (`ch-ra`). Pending: C2 (Muscari 2024 / Xie 2021 velocity sampling, build into `runs/lib-c2`, NOT `runs/lib-flags`), C3 (filtered lifting line).
- Sequence S U7/U8 A/B table is complete (L7). Conclusion: no isolated switch removes the speed-dependent error (v1.2: U5 P +28 %, U6 +14 %, U7 -2 %, U8 -20 %) without breaking U7 or root/tip. shen-tip fixes U8 but U7 +12 % and tip cn +44 %; du-selig-ra/ch-ra help U8 but cn0.30 +28..32 % at U7; dag-sorensen-tip and ring-sampling are neutral.
- Submitted 2026-10-20 on `sequana_cpu_bigmem`, SEQUENCE=S SPEED=5 END_REVS=24: shen-tip 11619690, dag-sorensen-tip 11619691, ring-sampling 11619692, du-selig-ra 11619693, ch-ra 11619694 (`LIB_DIR=runs/lib-flags`). Outputs `runs/var-<variant>-S-U5.{out,err}`, case dirs `runs/alm-U5-coarse-seqS-var-<variant>`. Check with `squeue -u $USER` / `sacct`.
- Not launched: H 7 m/s arms. No unambiguous v1.2 H-7 baseline run exists; run a v1.2 baseline first (`variant-run.slurm`-style, SEQUENCE=H SPEED=7), then the 5 arms.

### Commands (2026-10-20)
```sh
E=data/experiment/uae6-archive    # REQUIRED: data/experiment/ has only the S 7 m/s row
python3 scripts/comparePhaseVI.py --alm-dir runs/alm-U5-coarse-seqS-var-shen-tip --revolutions 16 24 --experiment $E --speed 5 --sequence S --out $TMPDIR/ab/S-U5-var-shen-tip
python3 scripts/comparePhaseVI.py --alm-dir runs/alm-U5-coarse-seqS-v12 --revolutions 16 24 --experiment $E --speed 5 --sequence S --out $TMPDIR/ab/S-U5-v12
python3 scripts/summarizeVariants.py $(ls -d $TMPDIR/ab/S-U*/)   # directories only, not the .log files
```
`$TMPDIR/ab` is temporary: regenerate if gone (`/tmp/ab` may belong to another user on some login nodes). Use `--alm-dir`, never `--run-dir`: the latter keys the model by directory name and the summary then prints `n/a` for every change vs v1.2. Continue a TIMEOUT run with `resume-run.slurm` (`RUN_DIR`, plus `LIB_DIR` for an arm), never by resubmitting `variant-run.slurm` (its `--restart` refuses written state). Each comparison takes ~15-20 s; run long loops with `bash_background`.
Gotchas: the summary prints `n/a` for change-vs-v1.2 when the output directory name does not follow `S-U<n>-<variant>`/`var-<variant>`; a run that was resumed has several `postProcessing/turbines/<time>/` segments (use `case_state.py` carefully, it reads segment 0 only).
Unrelated: jobs `b3-2-measure` in the queue belong to `fem-shell`.
