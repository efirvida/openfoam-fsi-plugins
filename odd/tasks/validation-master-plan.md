# Validation master plan — ALM / ASM / ASM+mesh (thesis CFD counterpart)

**Created:** 2026-10-11 · **Owner:** the user (decisions), one orchestrator session per phase
**Branch:** `feat/phasevi-sequence-s` (phase work may branch off it; see each phase)
**Engram mirror:** `odd/validation-master-plan/tasks`

## Why this exists

The thesis needs one CFD aerodynamic model whose credibility is documented. The
**ASM+mesh** is the CFD counterpart of the FSI analysis (preCICE), so the CFD
validation comes first and must hold for all three methods (ALM, ASM, ASM+mesh).

Two pillars, each answering a different question:

| Pillar | Reference | Question it answers |
|---|---|---|
| 1. Experiment | NREL Phase VI (`turbinesFoam/validation/phaseVI`), UAE6 archive in `articles/uae6/` | Is the **formulation** of the code right? |
| 2. Numerical | IEA 15 MW (`turbinesFoam/validation/iea15mw`), OLAF free-wake and BEM references | Is the **numerical model** adequate for the thesis rotor? |

A method that has no data of its own is accepted when it stays inside a band
that was **written down before the run** and justified. A band chosen after
seeing the result is not a validation.

## Rules that apply to every phase

1. **One frozen Model Definition** (P0.3) is used by both pillars. A knob that
   differs between pillars must be listed there with the reason.
2. **Calibrate on Sequence H, evaluate on Sequence S** without touching the
   configuration in between. Only the evaluation is quoted as validation.
3. **Bands are pre-registered** in the Model Definition before the run they judge.
4. **No claim outside the validity envelope.** Deep stall (13-25 m/s) is reported
   as a known limit, not as a criterion. The r/R = 0.95 spanwise station lies
   inside one epsilon of the tip (eps = 0.63 m coarse), so it is reported, not
   used as acceptance.
5. **Verify every subagent finding against the code before using it.** In the
   2026-10-11 review three explorer reports cited wrong line numbers and one
   asserted a false high-severity bug.
6. **One session per phase.** Start fresh, read this file and only that phase's
   resume pack. What must survive goes into this file and Engram, not the chat.
7. Analyses are scripts, not inline snippets (`python3 tools/analysis_gap.py`
   first, then the `validation-analysis-tools` skill).

## HPC protocol (all phases)

- Account limit: **4 jobs running at once**; more may be queued.
- Prefer **one job running several tasks in parallel** over many small jobs, so
  the queue is not saturated. One run = 48 ranks = one node; intermittent
  multi-node `MPI_Init` failures were recorded (`campaign-results/RESULTS.md`,
  operational notes), so each step is confined to a single node
  (`srun --nodes=1 --ntasks=48`). P0.5 proves the pattern before it is relied on.
- Jobs of about 20 min or less go to `sequana_cpu_dev`; long runs to
  `sequana_cpu` (`sequana_cpu_long` only where already used).
- Phase VI launch scripts refuse to run without `TURBINE_LONG_QUEUE_AUTHORIZED=1`.
  The user authorised up to 4 concurrent jobs on 2026-10-11; set the variable
  only for the jobs a phase lists.
- Never edit a runner (`runPhaseVI.sh`, `l2-long.slurm`) while a job is reading
  it: bash re-reads scripts by byte offset.
- Run `python3 -m pytest` with the OpenFOAM env sourced and output redirected to
  a file; the full suite takes about 7.5 min, so use targeted tests inside a phase
  and the full suite once at its end.

## Phase 0 — Common base (no long jobs)

Resume pack: `odd/tasks/phasevi-sequence-s-validation.md`,
`turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/actuatorSurfaceElement.C`,
Engram `turbinesfoam/code-review-2026-10-11`.

- [x] **P0.1** (914aa72) Fix `actuatorSurfaceElement.C:122`: `chordBox.inflate(projectionRadius)`
      passes metres where OpenFOAM v2506 expects a factor (`boundBox::inflate`
      = `grow(factor*mag(span))`); use `grow(projectionRadius)`. The defect is
      scale dependent (kernel truncated when chord < 1 m, oversized prefilter
      when chord > 1 m), so it hit Phase VI and not most of the IEA span.
      Test-first: a unit-level check of the fraction of kernel kept per strip.
      Add a `CHANGELOG.md` entry (`Files:` / `Problem:` / `Fix:`).
- [x] **P0.2** (ad49eef) Document the ASM as a hybrid: Yang & Sotiropoulos 2017 chord-averaged
      sampling + a Gaussian spreading kernel as in Massie/Ouro 2019
      (eps = max(c/4, 4*cbrt(V)); the code default `meshFactor 2` equals 4h, the
      Phase VI case overrides it to 1). Fix the README claim that it is the paper's model.
- [x] **P0.3** (v1 frozen except the IEA cp band, which is deferred to P3.1/P3.3 by owner order decision 2026-10-12; `odd/tasks/validation-model-definition.md`) Write `odd/tasks/validation-model-definition.md` (the frozen v1) with:
      tip correction = **Dag & Sorensen, Glauert tip loss off** (user decision
      2026-10-11); root = Prandtl hub loss with `hubRadius`; rotational
      augmentation, epsilon rule, velocity sampling, polars; the knobs that differ
      per pillar and why; and the pre-registered bands (proposed, confirm here):
      Phase VI |%P| and |%T| <= 15 % at 7 and 10 m/s, spanwise `c_n` within +-15 %
      at r/R 0.30/0.47/0.63/0.80; IEA cp inside the committed OLAF/BEM spread
      (read the spread from `iea15mw/data` before fixing the number);
      ALM-vs-ASM difference bound taken from the Phase VI result and the 0.3 %
      published by Santoni et al. 2024.
- [x] **P0.4** (gate measured, owner chose (b): D&S kept, IEA band re-centred in P3; control read 2026-10-12) Resolve the Dag-Sorensen risk on the IEA rotor: the correction is
      resolution dependent (n25 vs n50 changed the result) and diverged once at
      the hub transition; the IEA case has 147 elements. Run the correction on the
      frozen L2 platform at a short horizon (dev partition) before it is frozen.
      **Gate:** if it is unstable or inconsistent there, stop and bring the user the
      fallback options; do not freeze silently.
- [x] **P0.5** (c0a409b) Smoke-test the parallel-steps-in-one-job pattern on `sequana_cpu_dev`
      (two 48-rank steps on two nodes, one node each).
- [x] **P0.6** (off in both pillars, plus a pre-registered RA-on variant of the S curve in P2) Read the Du-Selig A/B on the IEA L2 (commit `ff58337`) and decide
      whether augmentation is on in both pillars (physics should not change
      between pillars; its effect on the attached IEA rotor is what the A/B measures).

**Exit:** Model Definition v1 committed; `-s S` and the corrected ASM covered by
tests; full suite green; the pattern for batched jobs proven.

## Phase 1 — Code verification (no experiment, cheap)

Resume pack: Phase 0 outputs, `src/fvOptions/bladeSurface/*`,
`odd/tasks/iea15mw-asm-mesh-cp-diagnosis.md`, Engram `turbinesfoam/madsen-1988-actuator-surface`.

- [x] **P1.1** (538f9d2 + the moment test; ratios 0.9998 ALM, 0.9996 ASM, 1.0000 moment) Conservation tests per method: injected force equals the sum of
      element forces; for ASM+mesh also the moment about the axis. Already
      established by reading (partition of unity 1.000 +-0.4 % on the coarse
      mesh; moment frame consistent), still to become tests.
- [x] **P1.2** (755265f + result in the log of 2026-10-12; ALM on Phase VI only, ASM arms open) Momentum-balance closure (Madsen 1988): sample the axial velocity at
      the disc, compute a(r), compare the annulus thrust with 2*rho*U^2*a(1-a);
      scripted, with a short run if the sampled velocity is not already written.
- [x] **P1.3** (decided: inert by design, pinned by a test, docs fixed; `odd/tasks/p1-3-meshfactor.md`) Decide the `meshFactor_` defect (knob documented but inert in the
      cosine path of the ASM+mesh deposit): honour it or stop documenting it as
      general (`odd/issues/asm-mesh-residual-vs-alm.md`).
- [ ] **P1.4** Epsilon/h sensitivity of the ASM kernel after P0.1, by Phase VI
      runs of 4 revolutions (dev or short jobs, in parallel).

- [ ] **P1.5** (proposal from the owner, measured, NOT started: `odd/tasks/p1-5-equispaced-blade.md`) Equispaced blade discretisation (elements and surface). Do before P2.1 if accepted.

**Exit:** each method has conservation tests; the closure result is written down.

## Phase 2 — Pillar 1: Phase VI against the experiment

Resume pack: Model Definition v1, `turbinesFoam/validation/phaseVI/campaign-results/RESULTS.md`,
`validation/phaseVI/README.md`, `tools/case_state.py`, `scripts/comparePhaseVI.py`.

- [ ] **P2.1** Calibration on Sequence H at 7 and 10 m/s, ALM, ASM and ASM+mesh
      (full 12-revolution window; 6 runs, batched as parallel steps of 1-2 jobs).
      The ASM+mesh has **zero** runs in `runs/`: check the blade surface staging
      first (the surface STL and `surfaceGeometry`) on the dev partition.
- [ ] **P2.2** Frozen evaluation on Sequence S at the same speeds, then the 21-point
      curve S for trend and stall onset. Report spanwise `c_n`/`c_t` at the
      stations of rule 4, power, thrust and the root flap moment.
- [ ] **P2.3** Declare the validity envelope per method and update
      `campaign-results/RESULTS.md` (its header still says 15/47 runs).
- [ ] **P2.4** Measure the effect of P0.1 on ASM against the pre-fix result at 7 m/s.

**Exit:** a table per method with the pre-registered bands judged, and the envelope.

## Phase 3 — Pillar 2: IEA 15 MW against the numerical references

Resume pack: `odd/tasks/iea15mw-platform-freeze.md`, `odd/tasks/iea15mw-asm-l2-validation.md`
(Handoff section), `odd/tasks/iea15mw-references.md`.

- [ ] **P3.1** Close the stalled-root polar (`cl = 0.0000` for alpha 41-56 deg at
      r/R < 0.07, both arms): read the polar table in a generated case, the lookup in
      `profileData.C`, and what `buildPolars.py` writes at the table ends. No run needed.
- [ ] **P3.2** Third arm: ASM+mesh on the frozen platform
      (`TURBINE_MODEL=asm-mesh TURBINE_RUN_DIR=runs/iea15mw-asm-mesh-l2
      TURBINE_TOTAL_REVS=20 sbatch scripts/slurm/l2-long.slurm`). Before launching:
      deposit gate (serial + 2 ranks), `surfaceGeometry` in the generated case,
      blade STL staged for the generated paths.
- [ ] **P3.3** Re-run ALM and ASM with Model Definition v1 if the frozen knobs differ
      from the 2026-10-09 platform (Glauert tip off, D&S on); keep the old numbers
      labelled as the previous platform.
- [ ] **P3.4** Explain the ASM +7.05 % against the ALM on this platform, which Phase VI
      does not show (0.3 %); compare scale (chord about 2.7 cells here).
- [ ] **P3.5** Three-way bands against OLAF/BEM with the per-station shape
      (`rev_history.py` thrust column, per-station ratio, plot consumers).

**Exit:** three methods on one platform, judged against the pre-registered bands.

## Phase 4 — Entry criterion for FSI

- [ ] **P4.1** ASM+mesh inside the bands of both pillars, spanwise load consistent
      (root flap moment and tip loading), and the envelope stated.
- [ ] **P4.2** Handoff note for the preCICE coupling work (what the CFD side
      guarantees and what it does not). Coupling verification is a separate plan.

## Progress log

| Date | Event |
|---|---|
| 2026-10-11 | Plan written. Decisions: tip correction frozen as D&S without Glauert tip loss; up to 4 concurrent jobs, parallel steps per job, `sequana_cpu_dev` for jobs of about 20 min. |
| 2026-10-11 | P0.1 done (914aa72): RED 12/18 -> GREEN 0/18 in `tests/asmPrefilterBox`; a 0.4 m chord kept 69-74 % of the kernel before. `test_asm` chord-averaging tolerance 1e-5 -> 1e-7 (difference now 9e-7). Pre-existing failure found: `tests/axialFlowTurbineASMSource` aborts (`hubRadius` missing since CHANGELOG #19); fix in the P0 exit. |
| 2026-10-12 | P0.2 done (ad49eef): Massie, Ouro, Stoesser & Luo 2019 (*Energies*, Eq. 13) verified in `articles/`: `eps = max(c/4, 4*cbrt(V))` after Mendoza et al.; the element keeps the `4*cbrt(V)` branch at the default `meshFactor 2` and has no `c/4` term. |
| 2026-10-12 | P0.5 done (c0a409b): `tools/run_parallel_steps.sh` + `parallel_steps_smoke.slurm` passed on `sequana_cpu_dev` (job 11613061): two 48-rank steps, one node each, overlapping, all ranks on their node. First attempt (11613059) failed: `mpirun --host <node>` gives one slot under Slurm; the launcher now passes `--host <node>:<ranks>`. |
| 2026-10-12 | **Finding (blocks the "frozen platform" numbers):** the IEA frozen platform (cp 0.534, run 2026-10-09 01:29) predates `4c49dc3` (2026-10-09 17:23), which made the Glauert root factor the Prandtl hub loss and made `hubRadius` mandatory. The IEA generator did not render it, so the recipe could not start on the current library (fixed in 8faff39). Also fixed: tutorials `axialFlowTurbineAL`/`ASM` lacked `hubRadius` (their tests aborted). |
| 2026-10-12 | P0.4 gate, short run (0.41 rev from the converged rev-20 state, jobs 11613044 D&S and 11613049 control, 96 ranks, dev): **stable**, no hub-transition instability. Control (Glauert tip+root, current lib) vs frozen Glauert: cp +2.4..2.7 %, all in r/R < 0.3 (root factor change of #19; r/R 0.3-1.0 within +-1 %). D&S vs control: cp +4.2..5.2 %, cd +5.3 %, localised at the tip (r/R 0.95-1.0 Fn x1.68, Ft x1.50, dalpha -0.96 deg; 0.90-0.95 x1.18; 0.7-0.9 x1.02; 0.3-0.7 within +0.5 %). Flow not relaxed after 0.4 rev, so the asymptote is not known: D&S transient cp 0.574 vs OLAF 0.5312 (+8 %). Confirmation run: job 11613058, 3 revs on `sequana_cpu` (`TURBINE_TOTAL_REVS=23`), reads with `tools/window_response.py` + `iea15mw/scripts/station_ratio.py`. |
| 2026-10-12 | P0.4 confirmation (job 11613058, 3 revs): D&S stable throughout; cp 0.5748 -> 0.5650 over 9 windows of 120 deg and still falling (~0.562 by Aitken). IEA D&S plateau is about +5.5..6 % over OLAF 0.5312, outside the proposed band [0.476, 0.546]; the Glauert control (0.4 rev) reads 0.5476. Gate "inconsistent" -> brought to the owner, not frozen silently. Full suite after the fixes: only `test_al.py::test_parallel` fails, an environment limit (no scotch in the module). |
| 2026-10-12 | Owner chose option (b) for D&S on IEA: keep D&S, re-centre the IEA band after a 3-rev Glauert control and the P3.1 root fix. Control job 11613092 (`runs/iea15mw-l2-ctrl`, to 23 revs, `sequana_cpu`). Decisions 1 (RA off) and 2 (bands) still unanswered; the Model Definition stays DRAFT. |
| 2026-10-12 | Owner delegated decisions 1-2 to physical judgment. Model Definition v1 frozen except the IEA cp band: RA off (RA-on S-curve as pre-registered variant, stall onset only); Phase VI `abs(%P)` <= 10 %, `abs(%T)` <= 15 %, `c_n` +-10 % (0.47-0.80) / +-15 % (0.30); ASM-ALM <= 2 % Phase VI, <= 3 % IEA. Phase VI D&S numbers in RESULTS.md predate 4c49dc3 -> P2.1 re-baselines. |
| 2026-10-12 | P0.4 control read (job 11613092, Glauert tip+root, revs 21-23): cp 0.5375 -> 0.5473 -> 0.5448, plateau 0.5461, drift +0.69 %/rev; ct 0.0613. D&S at the same horizon (11613058) 0.565, so D&S adds about +3.5 % over a control already +2.8 % over OLAF 0.5312; half of the excess over the references is not the tip model (root factor / flow relaxation, the P3.1 root polar is the suspect). Order decision (owner): the plan is followed in order; the IEA cp band stays provisional [0.476, 0.546] and is re-centred in P3.1/P3.3, not now. Phase 0 closes with that one explicit exception; next is P1.1. |
| 2026-10-12 | P1.1 done: `test_multi_element_{alm,asm}_conserves_force` and `test_deposit_moment_about_rotor_axis` in `tests/test_blade_surface.py`. Integral/sum 0.999795 (ALM), 0.999574 (ASM, nChordwise 5); with the P0.1 fix reverted the ASM ratio is 0.2303, so the test catches that bug. Deposited moment about the axis / node moment 1.0000 +-2e-7. Env: parallel tests cannot run here (`libkahip.so` missing for `decomposePar`); the shell env needs Int64 `WM_OPTIONS`, the Int64 bin in `PATH` and `FOAM_USER_APPBIN` (the exact exports are in Engram `turbinesfoam/test-env-int64`). Next: P1.2. |
| 2026-10-12 | **P1.2 momentum closure, ALM, Phase VI coarse `alm-U7-coarse-r2`** (`validation/tools/induction_closure.py`; rings: 40 radii x 3 planes, circle sets of 72 points; elements: last revolution t=2.504..3.339, `--elements-per-segment 2 --n-blades 2`; output `phaseVI/analysis/p12-closure-alm-r2.{txt,csv}`). Rotor thrust 914.3 m^4/s^2 x 1.225 = 1120 N (experiment 1116 N). Annulus thrust / `2 rho U^2 a(1-a) 2 pi r dr`, with `a = 1 - u_x/U_inf` read from the azimuth-averaged axial velocity: **disc plane integrated 1.096**, flat 1.10-1.13 over r/R 0.43-0.95, 1.23-1.25 at r/R 0.25-0.29, below 0.55 for r/R < 0.21 and at the last tip element; **the number depends on where a is read**: 1.61 at x/R = -0.25 and 4.26 at x/R = -1. No row reaches a >= 0.4 (max about 0.16). Read this as: the applied load is 10 % above the 1D relation evaluated with the velocity AT the disc, with no tuning. It does not separate an ALM induction error (force smearing, eps = 0.63 m coarse) from the known limit of the relation itself (Madsen 1988: unproved, degrades with load and radial gradient); no threshold is claimed. Limits: one velocity field instant (t=3.339) against force averaged over one revolution; coarse mesh; ALM only; the ASM and ASM+mesh arms and the IEA rotor are not measured yet (the IEA U fields exist on disk, e.g. `iea15mw-l2-ctrl` t=183.5592). Three tool traps found and now pinned by tests: `root_dist` is a 0..1 span fraction, not metres; element width comes from the geometry segments (50 elements = 25 segments x 2, some 13 mm), not from neighbouring centres; only `blade1` writes element CSVs, so a one-blade sum is half the rotor. |
| 2026-10-12 | P1.3 decided (agent, reversible): `meshFactor` stays inert in the ASM+mesh cosine kernel. Reason: the Yang & Sotiropoulos kernel has no free width and the Model Definition forbids adding a tuning knob; honouring it would also move every frozen result that renders `meshFactor 2`. Pinned by `test_mesh_factor_acts_only_in_gaussian_kernel` (cosine bit-identical for 1 vs 3, gaussian 95 % different); the help text of both case generators and the README now say it. If the owner prefers the other option (honour it, `meshFactor 1` = paper kernel), it is a one-line change in `nodeSupport`/`distributeNodeForce` plus rerunning the ASM+mesh arms. |
| 2026-10-12 | **Disk cleanup (owner request before P1.4).** Group quota `leahk` 1.56 T of a 2 T hard limit; this user 244 G. Deleted: `~/tmp/pytest-of-*` and codedFunctionObject caches (`~/tmp/.*.so`), the heavy case subdirectories of the September scratch dirs (`odd-integrate-origin-main`, `w3a`, `phasevi-scaling`, `nacelle-diag`, `opencode`; `~/tmp` 34 G -> 1.8 G), the P1.2 sampling work dir `phaseVI/runs/p12-closure-alm-r2` (regenerable, recipe in `p1-2-momentum-closure.md`), and the decomposed fields (`processor*`) of ten finished Phase VI runs (`alm-U7-coarse`, `-r1`, `-r3`, `-bothoff`, `-rootoff`, `-tipoff`, `-dagtip`, `-dagtipd`, `-s0`, `asm-U7-coarse-s0`; `phaseVI/runs` 50 G -> 18 G). Kept for each: `postProcessing`, logs, `system`, `constant` (no decomposed mesh), `0.org`. **These ten runs can no longer be restarted or sampled for fields; their CSV evidence is intact.** Kept whole: `alm-U7-coarse-r2`, `-hubfix`, `-s6-rot-aug` and every `iea15mw/runs` entry (restart states for P3.3). Not touched, other projects: `fem-shell*`, `frontiersin_results_corotational_100s` (30 G), `smoke_fix_results` (16 G), `convergence_b1_b2_rerun` (11 G), `frame_ab`, and a running job of `fem-shell-worktrees`. |
| 2026-10-12 | Owner observation: the Phase VI ASM+mesh surface has unevenly spread sections. Measured: 25 segments from the NREL table, dz 0.013..0.305 m (23.5:1), triangle aspect up to 212. Triangle quality does not hurt (nodes are point sources); the spanwise node spacing against the cell size does: 1D deposit ripple of the committed loft is 1.6 % at h = 0.31 m (coarse, P1.4/P2 unaffected), 7.5 % at 0.155, 55 % at 0.078, 126 % at 0.039, against 1.0 / 2.3 / 4.7 / 8.9 % for an equispaced layout with a fixed dz = 0.05 m (the rule dz versus h is still to be measured, not assumed). A refinement ladder of ASM+mesh on the committed loft is not interpretable. Equispaced surface needs equispaced elements (patch fatal if an element owns no node). Proposal registered as P1.5, not started. |
