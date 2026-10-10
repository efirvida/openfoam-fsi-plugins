# IEA 15 MW — ASM validation on the FROZEN L2 platform

**Status:** T1-T4 done; T5 next
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
- [x] **T3 — ASM run on the frozen platform. DONE.**
      **Job 11611470 COMPLETED**, 2026-10-09 15:26:28 -> 21:24:45,
      **05:58:17 wall, exit 0, in ONE allocation** (no chaining was needed).
      Case verified before reading anything: `system/fvOptions` has
      `elementType actuatorSurfaceElement` + `nChordwise 5`, `controlDict`
      `deltaT 0.0187` / `endTime 159.61692` (20 revs), and a single history
      `postProcessing/turbines/0/` (8536 rows, revs 1-21, the one-row rev-21
      stub excluded by the tool). The actuator-surface rate on L2 is ~3.4 rev/h,
      the same as the ALM's, so the 5x-per-element estimate was pessimistic.
- [x] **T4 — ASM plateau, drift and the ratio against the L2 ALM. DONE.** One
      command, same horizon on both sides, after adding `--max-rev` to
      `rev_history.py` (the tool takes its plateau from the tail, so a
      whole-directory read of the ALM silently reports its dt/2 continuation):

      ```sh
      python3 tools/rev_history.py --max-rev 20 \
        iea15mw/runs/iea15mw-screen-m3-l2 iea15mw/runs/iea15mw-asm-l2
      #   iea15mw-screen-m3-l2  recortado a rev <= 20 (5 revoluciones descartadas)
      #        plateau (ultimas 2 rev): cp 0.53651  ct 0.06019  deriva media -0.084%/rev
      #   iea15mw-asm-l2        plateau (ultimas 2 rev): cp 0.57431  ct 0.06443  deriva media -0.092%/rev
      #   comparacion           iea15mw-asm-l2  cp 0.57431 (+7.05% vs iea15mw-screen-m3-l2)
      ```

      | arm (dt 0.0187, same mesh, same 96 ranks, revs 19-20) | cp | ct | mean drift revs 17-20 |
      | --- | --- | --- | --- |
      | ALM, `runs/iea15mw-screen-m3-l2` revs 1-20 | 0.53651 | 0.06019 | -0.084 %/rev |
      | ASM, `runs/iea15mw-asm-l2` | **0.57431** | 0.06443 | -0.092 %/rev |
      | **ASM / ALM** | **+7.05 %** | +7.05 % | — |

      Both arms are read over the same window definition (2-rev mean of revs
      19-20) and at the same horizon. The ALM's dt/2 continuation (revs 21-25 in
      the same directory) is excluded: `rev_history.py` takes its plateau from the
      tail, so a union read reports the dt/2 arm instead. Note the platform doc's
      "dt plateau 0.53633" is the LAST revolution alone, not a 2-rev mean; the
      plateau definition must be the same on both sides or the ratio picks up
      0.03 %.

      **The sign flips.** The prior (floor of this doc) was the ASM at
      0.871-0.903 of the ALM, a ~10-13 % DEFICIT measured on another mesh with a
      different sampling argument. On the frozen platform the actuator surface
      carries **+7.05 %** of cp AND ct. The two arms converge at nearly the same
      rate (residual drifts differ by 0.008 %/rev), so this is a controlled
      comparison and not one arm lagging. cp and ct move by the same 7.05 %
      (cp = ct·TSR by construction), so the ASM shifts the load LEVEL, not the
      rotor's ct/cp relationship.

      Against the references the ASM lands FURTHER out than the ALM:

      | | cp | vs OLAF free wake 0.5312 | vs CCBlade/BEM 0.4910 |
      | --- | --- | --- | --- |
      | ALM | 0.5344 | +0.6 % | +8.8 % |
      | ASM | 0.5743 | **+8.1 %** | **+17.0 %** |

      So the old story ("the gap is the ALM's sampling argument, the ASM is the
      lower one") does not survive on this platform. Whether the surplus is
      finite-chord physics — the surface distributes the load over the chord, so
      the local self-induction is weaker than a thin line's and the sections see
      a higher effective angle of attack — or a residual defect in the surface
      path is decided by T5, because the integral alone cannot separate them.
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
- 2026-10-09 — T3 done: job COMPLETED in one 6 h allocation, single history.
  T4 done: ASM cp 0.57431 against the ALM dt 0.53651 = **+7.0 %**, the opposite
  sign to the prior; both arms converged by the campaign criterion at revs 19-20.
  T5 (spanwise) is now the discriminator, and `rev_history.py` needs a
  `--max-rev` cut so the ALM's dt arm can be read without its dt/2 continuation.
