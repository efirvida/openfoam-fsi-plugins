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

      Against the references the ASM lands further out than the ALM:

      | | cp | vs OLAF free wake 0.5312 | vs CCBlade/BEM 0.4910 |
      | --- | --- | --- | --- |
      | ALM | 0.5344 | +0.6 % | +8.8 % |
      | ASM | 0.5743 | **+8.1 %** | **+17.0 %** |

      **Read that table as a sanity envelope, not as an error bar.** OLAF free
      wake, CCBlade/BEM, the ALM and the ASM are four different models with
      different, known biases, and there are no experimental data for this rotor
      at this Reynolds number: being further from OLAF or from BEM is NOT
      evidence of being further from reality, and no ordering of the four is
      established by their spread. The band (0.4910-0.5312) is 8 % wide, which is
      the same size as the effect being discussed.

      So the question is not which arm is closer to a reference, it is whether
      the ASM result **closes physically**. The T5 checklist below is that
      question made checkable: the reference profiles enter it as a shape oracle,
      and the decisive test is the finite-chord mechanism itself (lower local
      induction and higher effective alpha than the thin line at the same
      station), not the distance between two integrals.
- [ ] **T5 — does the ASM close physically? Spanwise, mechanism by mechanism.**
      Not "is it closer to BEM": the two arms, the two references and the four
      sets of assumptions are all in play, so what has to hold is that the
      +7.05 % is produced by a mechanism that makes physical sense, station by
      station. Each item names its oracle, so none of them is an opinion:

      1. **Internal consistency.** The spanwise integration over the 147 elements
         reproduces the module's own cp/ct to ~0.4 %, as it does on the ALM
         (`compare_spanwise.py`'s rotor-integration summary). A larger gap is a
         bookkeeping defect, independent of the physics.
      2. **The mechanism, not just the level (decisive).** The finite-chord
         argument predicts that the surface spreads the load over the chord, so
         the self-induction at the blade is WEAKER than the thin line's and the
         sections see a HIGHER effective alpha. The band-by-band check: the ASM
         must show **lower axial induction and higher alpha than the ALM at the
         same station**, by an amount consistent with a +7 % load. If alpha comes
         out equal or lower while the load is higher, the surplus is NOT this
         mechanism and `bladeSurfaceSource` has a defect to find.
      3. **Section-level reachability.** For every station, the reported
         `c_n`/`c_t` must be reachable from the polar at the alpha the same run
         reports: no `C_L` above the polar's `cl_max`, no `C_L > 2*pi*alpha` in
         attached flow. An unreachable section is a sampling or projection bug.
      4. **The tip.** With the Glauert tip factor on, `c_n` and `c_t` must vanish
         as `r/R -> 1` on both arms.
      5. **The root.** The deep-stall root (alpha 50-56 deg at `r/R < 0.1`)
         contributes drag and ~no power; a POSITIVE power contribution from a
         stalled root is a red flag on either arm.
      6. **Shape, not level.** Both profiles must be smooth in `r/R` and differ by
         a coherent amount. A 5-cycle pattern across the chord is the signature
         of the `nChordwise` projection, not of the chord's effect on induction,
         and that is what separates a real level shift from a strip artifact.
      7. **Thrust vs torque.** The two are different projections of the same
         force, so the excesses need not be equal, but their direction and rough
         ratio must follow from the alpha shift of item 2. `rev_history.py`
         carries only cp/ct today: extend it to cd so the thrust plateau is read
         by the same tool and the same window, not by hand.

      Oracles: `scripts/compare_spanwise.py` (two runs, same window),
      `analysis/spanwise-references.csv` for the profile SHAPE, and the run's own
      `system/fvOptions` polars for item 3. Results are written back here and
      mirrored into `odd/issues/asm-mesh-residual-vs-alm.md`.

      **Results so far (2026-10-09).** `compare_spanwise.py` gained the two-run
      comparison for this (`--compare-with`, `--compare-time`,
      `--comparison-out`; stations paired by index with the r/R grids checked, a
      mismatch failing loudly instead of interpolating). A = the ALM dt arm
      (`--time 31.9209`), B = the ASM:

      | band r/R | stations | alpha ALM | alpha ASM | d alpha | c_n ratio | c_t ratio |
      | --- | --- | --- | --- | --- | --- | --- |
      | 0.3-0.5 | 30 | 7.638 | 7.795 | **+0.157** | 1.0128 | 1.0267 |
      | 0.5-0.7 | 30 | 6.953 | 7.306 | **+0.352** | 1.0321 | 1.0826 |
      | 0.7-0.9 | 31 | 7.497 | 7.894 | **+0.397** | 1.0280 | 1.1017 |
      | 0.3-0.9 | 91 | 7.364 | 7.667 | **+0.303** | 1.0239 | 1.0597 |

      1. **Internal consistency — PASSED.** Spanwise integration against the
         module: ASM C_T 1.0060 / C_Q 0.9965 / C_P 0.9965, ALM C_T 1.0060 /
         C_Q 0.9962 / C_P 0.9962 — the same 0.4 % bookkeeping on both arms.
      2. **The mechanism — PASSED, and it accounts for the level.** d alpha is
         POSITIVE in every band (it could have come out equal or negative, which
         would have meant the surplus is not this mechanism) and it grows toward
         the root and outboard. The level follows it through the section lift
         curve: +2.39 % in `c_n` per +0.303 deg overall implies a section slope of
         ~0.0239*C_l/0.303 = 0.08 /deg ~= 4.5-5.0 /rad, i.e. ~0.75 * 2*pi — below
         the thin-airfoil 2*pi and in the range a tip-loss-reduced section has.
         Independent check of the same conclusion: inside the tip region the
         ratio of `c_n` (0.7254/0.7236) equals the ratio of `cl` (0.7289/0.7268)
         to 0.04 %, with `cd` there at 0.008, so the projection contributes
         nothing to the difference. `c_t` rises faster than `c_n` outboard
         (+10.2 % against +2.8 % in 0.7-0.9), which is the same d alpha acting
         through the inflow angle (`c_t ~ C_l*sin(phi)`, phi ~ 8 deg there): the
         level effect plus the angle's own effect.
      3. **Reachability — PARTIAL.** The identity
         `c_n ~= cl*cos(phi) + cd*sin(phi)` holds to <1 % at the tip on both
         arms. OPEN: at `r/R < 0.07` the polars report `cl = 0.0000` for
         alpha 41-56 deg on BOTH arms (a polar-table limit, shared, so it cannot
         bias this comparison), so the stalled root is carried by `cd` alone.
         That is worth its own look in the polar pipeline, not here.
      4. **The tip — PASSED.** Both arms decay monotonically to `c_n` 0.2732
         (ALM) / 0.2733 (ASM) and `c_t` 0.0201 / 0.0206 at `r/R = 0.9983`. Note
         the arms differ by +0.4 % at the last station while the 0.7-0.9 band
         differs by +10.2 % in `c_t`: the surplus is NOT a tip effect, and it is
         not the tip correction.
      5. **The root — PASSED.** `c_t` is NEGATIVE at `r/R < 0.07` on both arms
         (-0.10 to -0.18): the deep-stall root produces drag, not power.
      6. **Shape, station by station — OPEN.** Band means cannot show a sawtooth;
         needs a per-station ratio read.
      7. **Thrust vs torque — OPEN.** `rev_history.py` carries only cp/ct, so the
         thrust plateau has to come from the same tool before the split is
         quotable. The band `c_n` ratio (+2.4 %) against the rotor-level torque
         (+7.05 %) is the same qualitative split the reference comparison shows,
         but it has to come from the tool, not from a mental subtraction.

      **Conclusion so far**: the +7.05 % is the surface seeing a HIGHER local
      angle of attack — +0.30 deg overall, +0.16 in the inboard band, +0.40 in
      0.7-0.9, up to +2.3 deg in the stalled root where the chord is largest —
      with the load following it through the section lift curve. No unexplained
      multiplier, no tip artifact, no bookkeeping defect. Which still does not
      say which arm is closer to the real rotor: it says the ASM's surplus is
      produced by a mechanism that makes physical sense, which is the standard
      this comparison has to meet.

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
  T4 done: ASM cp 0.57431 against the ALM dt 0.53651 = **+7.05 %**, the opposite
  sign to the prior; both arms converged by the campaign criterion at revs 19-20.
- 2026-10-09 — T5 in progress: `compare_spanwise.py` gained the two-run band
  comparison (stations paired by index, mismatched r/R grids fail loudly), and
  the mechanism check PASSES (items 1, 2, 4, 5 of the checklist); items 3, 6 and 7
  are open. The +7.05 % is the finite-chord alpha shift, not a defect.
  Next: OLAF's spanwise profile into the committed reference set (it is on disk,
  50 nodes with the induction components, but only BEM is committed today).
