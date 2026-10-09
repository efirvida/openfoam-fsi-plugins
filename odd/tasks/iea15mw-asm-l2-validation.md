# IEA 15 MW — ASM validation on the FROZEN L2 platform

**Status:** T1 and T2 done; T3 running (job 11611470); T4-T5 pending
**Owner:** orchestrator session, 2026-10-09
**Platform:** `odd/tasks/iea15mw-platform-freeze.md` (L2 snappy, 1.87 m, 2 363 760
cells, 96 ranks, dt 0.0187 s, 20 revs, cp 0.5344 / dt-verified). Nothing in the
platform changes here: **only the element type differs** between the two arms.

## Objective

Replace the stale ALM/ASM ratio with a measured one on the frozen mesh, so the
~10 % ASM-vs-ALM gap is either confirmed as a formulation difference on the
platform that everything else uses, or shown to be an artifact of the old mesh
and sampling argument.

The old pair (ASM cp = 0.871–0.903 of the ALM) came from a different mesh and a
different inflow-sampling argument, so it is **not citable** as the platform
answer. It is the prior, not the result.

## Tasks

- [x] **T1 — fix the `TURBINE_MODEL` override in `scripts/slurm/l2-long.slurm`.**
      The script hardcoded `export TURBINE_MODEL=alm` (line 45), which overrides
      the value passed on the submit line, so the documented ASM recipe
      (`TURBINE_MODEL=asm ... sbatch scripts/slurm/l2-long.slurm`) would have
      silently produced a **second ALM run** under `runs/iea15mw-asm-l2` — the
      same class of failure the platform doc warns about, and invisible in the
      exit code. Fixed to the overridable pattern already used by
      `TURBINE_RUN_DIR`, `TURBINE_TOTAL_REVS` and `TURBINE_DT_FACTOR`; the ASM
      recipe and the chaining note are now in the script header.
      **Evidence**: `bash -n` rc=0; the only assignment left is
      `export TURBINE_MODEL="${TURBINE_MODEL:-alm}"`; `run_iea15mw_case.sh:60`
      reads `model="${TURBINE_MODEL:-alm}"` and lines 78-79 pass
      `--n-chordwise "$TURBINE_N_CHORDWISE"`.
- [x] **T2 — deposit gate (must pass before the long job). PASSED.**
      `test_deposit_partition_of_unity_under_rotation` (serial **and** 2-rank)
      plus the whole file: **13 passed in 34.9 s**, 0 failed, 0 skipped, on a
      library rebuilt from the current source (`./Allwmake` rc=0,
      `libturbinesFoam.so` 1 470 336 B, mtime 10-07 16:06, source at `5026c97`).
      The 2-rank path really ran (mpirun not refused; `processor0/`, `processor1/`,
      `numberOfSubdomains 2`). Generate-only pre-flight of the ASM case
      (`tools/generate_case.py` into a scratch dir) confirmed the case the job
      will run: `elementType actuatorSurfaceElement`, `nChordwise 5`, rotor-disk
      castellated `levels ((1e15 2))` = L2, domain 3/7/3, `dynamicStall` and
      `rotationalAugmentation` `active off`.
      **Provenance**: `turbinesFoam/src/fvOptions/bladeSurface/` is clean at
      `5026c97` (10-07 16:10) and no turbine source has changed since, so the
      ALM reference run (Oct 8-9) and this ASM run share one build.
- [ ] **T3 — ASM run on the frozen platform.** IN PROGRESS.
      Submitted **job 11611470** on 2026-10-09, 96 ranks, 2 nodes, 10 h limit:

      ```sh
      TURBINE_MODEL=asm TURBINE_N_CHORDWISE=5 TURBINE_RUN_DIR=runs/iea15mw-asm-l2 \
        TURBINE_TOTAL_REVS=20 sbatch -J iea15mw-asm-l2 --time=10:00:00 \
        scripts/slurm/l2-long.slurm
      ```

      Same L2 case, same decomposition (`simple 4 6 4`), same domain, same
      horizon; only the element type differs. The rate is unknown on this mesh
      (ASM is ~5x the ALM per element), so 20 revs are expected NOT to fit one
      allocation: the same command is resubmitted to resume from `latestTime`,
      one submission at a time.
- [ ] **T4 — ASM plateau, drift and the ratio against the L2 ALM.**
      `turbinesFoam/validation/tools/rev_history.py` over the union of every
      split `postProcessing/turbines/<timeName>/` folder; the plateau is the
      last complete revolution, the stub row at `endTime` excluded.
- [ ] **T5 — spanwise ASM vs ALM vs BEM and the record.**
      `scripts/compare_spanwise.py --run-dir runs/iea15mw-asm-l2 --time <timeName>
      --revs 2`, compared against the same window of `runs/iea15mw-screen-m3-l2`
      and against `analysis/spanwise-references.csv`; results written back here
      and mirrored into `odd/issues/asm-mesh-residual-vs-alm.md`.

## Acceptance

- T2 green (serial and both ranks), on a build of the current source.
- The ASM drift reaches the campaign criterion (< 0.2 %/rev sustained) by the
  horizon the ratio is read at, or the ratio is explicitly reported as
  not-yet-converged.
- The ratio is stated with the same window definition for both arms (last
  complete revolution over a union history), plus the spanwise c_n / c_t / Δα
  bands, so the integral-only comparison (which is weak: the reference band is
  8 % wide) is not the sole evidence.

## Notes and traps

- Resuming splits the history into a new `postProcessing/turbines/<timeName>/`;
  the folder names sort wrongly as text (`"31.9209"` after `"159.6232"`).
- `runs/iea15mw-screen-m3-l2` is the ALM arm, and it currently holds the **dt/2
  continuation** (25 revs, dt 0.00935): the dt revolutions 1–20 live in
  `postProcessing/turbines/{0,31.9209}` only. Use them, not the continuation.
- `asm` does not default to snappy: the L2 level must come from the script (it
  does), and `TURBINE_N_CHORDWISE` must be set explicitly.
- ASM `moment()` omits the pitching moment (~0.1 %).

## Progress log

- 2026-10-09 — feature opened; T1 defect found and fixed (`c7eda86`); T2 gate
  passed; job 11611470 submitted (T3).
