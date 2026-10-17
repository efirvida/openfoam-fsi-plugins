# P2.2 follow-up — analysis and validation plan (2026-10-16)

Evidence: `p2-2-sequence-s.md` (results table), H1 root A/B read 2026-10-16.

## Findings
1. 7 m/s power -11 % (H and S, ALM/ASM) with thrust -0.7 % and mid-span c_n within 2.5 %: the miss is
   tangential, not normal. Plane torque coefficient by station (S, ALM): r/R 0.30 +9 %, 0.47 -10.5 %,
   0.63 -5 %, 0.80 -2 %, 0.95 -22 %. Inboard-to-mid (0.47) and tip (0.95) carry the deficit.
2. Root factor is NOT the lever: `alm-U7-coarse-p21-rootoff` vs `p21` on H: power -10.9 vs -11.0 %,
   c_n(0.30) +14.7 vs +13.6 %. Drop the root-factor hypothesis for power.
3. 10 m/s: the experiment is in 3-D stall delay (c_n 1.29-1.35 at 0.30-0.47); the model with RA off cannot
   reproduce it. Structural; ASM = ALM there.
4. Earlier evidence (Model Definition, decision 1): Du-Selig on shifted %P by about +5.8 points at 7 m/s
   (+0.45 off vs +6.24 on, older platform). Applied to the present -11 % that would land near -5 %,
   i.e. inside the 10 % band. The platform changed since (D&S tip, hub loss), so it must be re-measured.
5. Code: Du-Selig (`correctRotationalAugmentation`) and Lindenburg
   (`correctLindenburgRotationalAugmentation`) are implemented in `actuatorLineElement.C`; switch is
   `--rotational-augmentation on|off` in `runPhaseVI.sh`. Dynamic stall/added mass off by definition.
   Subagents were unavailable (routing model `claude-bridge/claude-opus-5-5:high` not found in models.json).

## Plan (pre-registered ordering; nothing retuned on S)
A. (running) asm-mesh U10 S, job 11616862.
B. RA-on variant S, ALM only, 7 and 10 m/s, paper constants a=b=d=1, same config as P2.2, 12 rev
   (`--rotational-augmentation on`, new label `-seqS-p22-ra`). Judged only on stall onset and reported
   beside the definition (decision 1); it also tells whether 7 m/s power moves into the band.
C. 21-point S curve RA off, then RA on (stall onset >= 10 m/s). Cheaper: ALM only, fewer revs for
   attached points after checking drift.
D. Tip diagnostic on H (not S): same 7 m/s, D&S vs Glauert tip off/on; the 0.95 station (-22 % torque,
   -12 % c_n) is the second deficit source. Reuse `phasevi-endeffect-diagnostic.md` arm A'.
E. Documentation: P2.3 envelope, P2.4 ASM effect of P0.1, P2.8 blockage (+1 %, +2 % inflow).
F. Mesh: ASM+mesh -3.9 % vs ALM at D/32 -> one D/48 run to see whether the gap closes (P3.4 link).
G. Fix subagent routing in `~/.pi/gentle-ai/models.json` (owner action) before the next delegated pass.

## Diagnostics run 2026-10-16 (after the owner asked for all of them)

**Finding D0 — the torque deficit is a force-direction error, closed to < 1 point.**
Station torque = R_sim/R_exp x sin(phi_force,sim)/sin(phi_force,exp). With `compareSectionLoads.py`
(R) and `compareInflowAngle.py` (phi_force, S 7 m/s ALM) the product gives +8.8 / -10.0 / -5.9 / -2.4 /
-22.5 % at r/R 0.30-0.95 against the measured +9.0 / -10.5 / -5.4 / -2.4 / -21.6 %. The lift level (R)
is right at 0.47-0.80; the resultant points 0.3-1.8 deg too close to the rotor axis at every station.

**Finding D1 — a classical BEM on identical inputs has the same angle error** (`scripts/bemPhaseVI.py`,
test `tests/test_phasevi_bem.py`; U 7, 71.87 rpm, rho 1.2525, pitch 3, Prandtl tip+hub):
phi_force BEM 24.45/14.70/11.28/9.07/6.40 vs exp 25.88/16.81/12.18/9.82/7.79 (CFD 24.73/15.02/11.17/9.53/7.01).
BEM power 6.01 kW (exp 6.03) is a cancellation: BEM thrust 1310 N (+14 %) and R 14-40 % high outboard,
which the CFD does not have (thrust -0.7 %). So the CFD loading is better than BEM; the angle error is
inherited from the shared inputs, not from the coupling.

**Finding D2 — the shared input is the polar drag definition.** OSU Table A-7 at alpha 10.1: Cdw 0.0487
(total, wake traverse, used by the model) vs Cdp 0.0231 (pressure); at 8.2: 0.0167 vs 0.0096. The
experiment integrates pressure taps. BEM with Cdp: phi_force 25.90/16.24/12.15/9.43/6.64 (exp
25.88/16.81/12.18/9.82/7.79: exact at 0.30 and 0.63, <= 0.6 deg at 0.47/0.80, 1.2 deg at the tip) and
power +5.7 % over the total-drag BEM. Caveat: LSSTQCOR 801 Nm vs pressure-integrated EAEROTQ 796 Nm
differ by 0.6 %, so the measurement does not by itself separate friction; D2 is a hypothesis until D3.

**Open points.** The residual 1.2 deg at the tip is flow angle (tip model), not drag. At 10 m/s the
deficit is RA (structural). Kept out of S tuning: arms below use H or are pre-registered variants.

## Jobs submitted 2026-10-16
| job | what | notes |
|---|---|---|
| 11616862 | asm-mesh U10 S (resubmitted after IB failure) | P2.2 |
| ~~11616887~~ → 11616964 | D3: ALM U7 **H**, `--polar S809_OSU_Re1M_pressure.dat`, 12 rev, label `d1-pdrag` | compare with `alm-U7-coarse-p21`; `scripts/slurm/d1-pressure-drag.slurm` |
| 11616888 | B: ALM U7 **S**, RA on (Du-Selig a=b=d=1), label `p22-ra` | pre-registered variant; `scripts/slurm/p2-2-ra-on.slurm` |
Pending after these: B at 10 m/s, then D3 on the tip (D&S arm A') only if the tip stays at -20 % torque.
Polar file `data/polars/S809_OSU_Re1M_pressure.dat` is generated by `buildPolars.py` (committed `*_total.dat` unchanged, verified byte-identical).

## HANDOFF — resume here (session 3, 2026-10-17: every queued job COMPLETED and analysed)

### Session 3 results (2026-10-17) — read this first
Jobs 11616862 (asm-mesh U10 S), 11616888 (B), 11617387-90 (FLOWUnsteady) all COMPLETED 0:0. No job is queued.

**FLOWUnsteady 2x2 (DS x drag), H 7 m/s, 10 rev.** Convergence gate passes on all four (< 0.1 %/rev; `check_smoke.py` now prints
per-revolution means and the gate). Rotor: total+DSon CT 0.603 CQ 0.0797 (+22 % vs exp 0.0653); total+DSoff 0.574 / 0.0773 (+18 %);
pressure+DSon 0.601 / 0.0844 (+29 %); pressure+DSoff 0.573 / 0.0815 (+25 %). Mehr Fig. A4: 0.459 / 0.0699. **The hypothesis "the ~18-point
gap = DS on/off and drag definition" is refuted**: no combination reproduces Mehr or the experiment.
Stations (`scripts/compareFlowUnsteadyStations.py`, new; units check of blade integrals vs `power.csv` 0.2 % thrust / 1.1 % torque):
- r/R 0.95: F'n +72 %, F't +93..99 % in all four runs; 0.80 +15 %. Tip = +12.9 of the +17.9 % station-sum torque excess (total, DS on).
  Force angle at 0.95 ~1 deg above the experiment (8.7-9.0 vs 7.8): less tip induction. Inference (not isolated by any run): tip vortex
  under-resolved at sigma R/10, n 50, with Prandtl factor off.
- Du-Selig only moves the root: F'n at 0.30 +5 % (off) vs +29 % (on). Pressure drag only moves F't (+2..6 N/m mid-span), never F'n.
- Mid-span (0.47-0.63) with DS off: F'n -1..+7 %, F't -9..+7 %, i.e. FLOWUnsteady is close to the experiment only away from tip and root.

**Job B (RA on = Du-Selig a=b=d=1, S 7 m/s, `alm-U7-coarse-seqS-p22-ra`)** vs RA off (`...-seqS-p22`), experiment `uae6-archive` (comparePhaseVI)
and enriched `data/experiment/sequence_S_*` (force x arm; `compareSectionLoads.py`/`compareInflowAngle.py` gained `--sequence`, default H, H output byte-identical):
| | RA off | RA on |
|---|---|---|
| power (band 10) | -11.0 FAIL | **-6.5 PASS** |
| thrust (band 15) | -0.7 | +2.8 |
| c_n 0.30 / 0.47 / 0.63 / 0.80 / 0.95 | +15.1 / +1.8 / +2.4 / -0.3 / -12.1 | **+28.1 FAIL** / +8.8 / +4.6 / +0.1 / -12.2 |
| station-sum torque / edgewise / flapwise | -9.0 / -9.2 / -3.2 % | -5.1 / -5.7 / -1.1 % |
| F't 0.30 / 0.47 / 0.63 (exp 29.7 / 38.7 / 39.4 N/m) | 29.5 / 34.0 / 36.0 | 34.1 / 37.0 / 37.3 |
| tip 0.95 torque / flap share (N.m) | -12.5 / -43.5 | -13.4 / -44.0 |
| phi_sim - phi_exp at 0.30 / 0.47 (deg) | -1.15 / -1.80 | -0.56 / -1.64 |
Reading: RA gains torque at r/R 0.30-0.63 by raising inboard LIFT, overshooting F'n at 0.30 (+18 %); its flapwise "improvement" is that
overload compensating the untouched tip deficit. D3 (pressure drag, H) closed torque to +0.2 % with F'n unchanged: the cleaner 7 m/s lever.
Cross-code agreement: FLOWUnsteady's Du-Selig and our RA both over-augment r/R 0.30 at 7 m/s (attached regime). B is a diagnostic; nothing
was changed in the definition (plan rule 2).

**asm-mesh U10 S (11616862)**: P -40.3 %, T -28.2 %, c_n -41.3 / -35.6 / -15.5 / -19.6 / -43.1 % (ALM U10: -43.5 / -28.1 %). Same structural
3-D-stall-delay miss as ALM/ASM; asm-mesh vs ALM power +5.6 % (6.04 vs 5.72 kW; the 2 % agreement band fails, at 7 m/s it was -3.9 %).

Caveat found: `compareSectionLoads.py`/`compareInflowAngle.py` average t in [3, 4] periods ("last revolution" in their comment) although
the current runs have 12 revolutions; kept unchanged so session-2 numbers stay comparable. Decide whether to move the window.

### Next steps (session 4, in order)
1. Owner decisions (nothing proceeds without them): (a) FLOWUnsteady: stop here and record it as "not a usable reference at this
   fidelity", or run ONE isolating variant (e.g. total+DSoff with the Prandtl hub/tip correction on, or sigma R/20) at ~5.5 h / 24 threads;
   (b) pressure-drag polar (D3) as a v1.2 definition change, or diagnostic only; (c) RA: not adopted at 7 m/s (c_n 0.30 +28 %); whether
   to run B at 10 m/s, where its physical justification (stall delay) lies; (d) the compare window above.
2. The 21-point S curve (trend and stall onset) per `p2-2-sequence-s.md`.

### Next steps of session 2 (done in session 3; kept for the commands)

### Jobs (check first)
`sacct -j 11616888,11617387,11617388,11617389,11617390 -X --format=JobID,JobName%16,State,Elapsed,NNodes,NodeList%20`; the FLOWUnsteady run dirs are
`turbinesFoam/validation/phaseVI/flowunsteady/runs/fu-{total,pressure}-ds{on,off}/`; our runs: `ls turbinesFoam/validation/phaseVI/runs | grep -E "d1|p22"`.
| job | what | state at handoff |
|---|---|---|
| 11616862 | asm-mesh U10 S (P2.2) | COMPLETED (not yet analysed in this pass) |
| 11616964 | **D3** ALM U7 H, pressure-drag polar -> `runs/alm-U7-coarse-d1-pdrag` | COMPLETED, analysed (see "Session 2 results") |
| 11616888 | **B**: ALM U7 **S**, RA (Du-Selig a=b=d=1) on, label `p22-ra` -> `runs/alm-U7-coarse-seqS-p22-ra` | RUNNING (5.4 s of ~10 s at 3 h 20 min; 24 h limit). Owner: analyse after it finishes |
| 11617387-90 | **FLOWUnsteady Phase VI**, 10 rev, 24 threads, `--nodes=1 --ntasks=24 --time=10:00:00` (owner exception to the ntasks-only rule, memory `feedback-slurm-ntasks-only`; do NOT ask for the whole node) | PENDING on `AssocMaxJobsLimit` (shared running-job cap). 87: total drag + DS on; 88: total + DS off; 89: pressure + DS on; 90: pressure + DS off. Tags `fu-<drag>-ds<on|off>` |
If a job FAILED, read the `.err` first (Slurm/InfiniBand/UCX or a Julia trace such as the PyCall/NumPy finalizer SIGSEGV seen in smoke 11617318) before suspecting code.
Resubmit line (repository root): `sbatch --output=turbinesFoam/validation/phaseVI/flowunsteady/runs/%j.out --error=turbinesFoam/validation/phaseVI/flowunsteady/runs/%j.err turbinesFoam/validation/phaseVI/scripts/slurm/flowunsteady-production.slurm turbinesFoam/validation/phaseVI/flowunsteady/runs/db-<total|pressure> ds=<on|off> 10 fu-<total|pressure>-ds<on|off>` (the run dir must not exist: remove a failed one first).

### Decisions taken by the owner (2026-10-16)
1. **Roadmap**: (1) Phase VI experimental validation -> model limits + every feasible improvement; (2) IEA 15 MW numerical validation in the
   regime step 1 reproduces best; (3) FSI. Write the step-1 acceptance band BEFORE reading step-2 results.
2. **FSI goal**: root loads matter less (stiffer blade); tangential force matters structurally. Rank deficits by force x arm, not percent;
   station deficits that count: r/R 0.47 (-10.5 % torque) and 0.95 (-22 %). Declare the root simplification after tuning.
3. **Scope**: thesis turbine is the IEA 15 MW at its real operating regime (attached). Stall is out of thesis scope but must still be
   characterised and documented as a model limit (Phase VI 10 m/s RA miss; DS/CH/Lindenburg behaviour). The claim "never stalls" is NOT
   established (repo/docs are numerical): write "no stall observed in steady or static-gust BEMT, nor in the EOG with controller + B-L".
4. Implement nothing from the literature yet; Chaviaropoulos-Hansen (`ch`) option was declined for now.

### What this session established (details in the sections below)
- Literature: only MIRAS Eq. 17-18 (separate pressure/friction drag in the tangential force) is usable; supports D2 (polar Cdw ~2x Cdp). Kleine/Muscari/Xie/Zilic
  give no accuracy lever; CH rotational model (Burgos Tafur 2020) is the candidate for 10 m/s; check eps/c vs 0.25 (Martinez-Tossas 2019) before reading tip physics.
- IEA 15 MW stall margin (BEMT sweep 74 cases + EOG with ROSCO and B-L): r/R > 0.5 attached with >= 4.7 deg to cl_max (EOG), ~1 deg to the end of linear lift at 8-10.7 m/s;
  r/R 0.28-0.5 reaches the end of linear lift in steady rated operation and goes into trailing-edge separation in gusts (alpha 12-14.5 deg, no cl peak); root < r/R 0.14 is deep post-stall.
- FLOWUnsteady (Mehr 2024 App. A, Phase VI H series): at TSR 5.4 CQ 0.0699 is ABOVE the experimental range (+7 % vs our measured 0.0653), CT 0.459 inside; our ALM is -11 % in power.
  Its defaults include Du-Selig 3-D correction and Viterna, Prandtl factor off, bound-vortex self-induction omitted from sampling. Hypothesis (unproven): the ~18-point gap = DS on/off and drag definition.

1. **Check the jobs** (table above). Then, for each finished FLOWUnsteady run: `python3 turbinesFoam/validation/phaseVI/flowunsteady/check_smoke.py <rundir>` (last-revolution CT/CQ/CP, power monitor vs force.velocity, wall per revolution)
   and read `<rundir>/power.csv`. **Convergence gate before any comparison**: CT and CQ change < 1 % per revolution over the last 2 revolutions; if not, record it and decide with the owner whether to extend (the driver has no restart: a longer run is a new run).
2. **Compare FLOWUnsteady vs experiment vs our ALM** at TSR 5.408 (U 7, 71.878 rpm, rho 1.2337):
   - rotor level: CT, CQ, CP of the four runs against the experiment (CQ measured 0.0653 from LSSTQCOR 789.9 Nm; Fig. A4 FLOWUnsteady 0.0699, CT 0.459) and our ALM (p21 P -11.0 %, D3 -2.2 %, `comparePhaseVI.py` metrics.json).
   - the question it answers: is the ~18-point power gap between FLOWUnsteady (+7 % CQ) and our ALM (-11 %) explained by Du-Selig on/off and by total vs pressure drag? The four runs are the 2x2 of those two switches. State the result as measured, not as the hypothesis.
   - station level (write a tool, do not compute inline): the saved `*_Rotor_BladeN_vlm.<step>.vtk` carry `Ftot`/`L`/`D`/`Gamma` per horseshoe at steps 0, 72, 144, ... (legacy ASCII VTK; `Ftot` is N/m? verify units against the integrated thrust before using it). Build `scripts/compareFlowUnsteadyStations.py` that reads the last vtk and prints Fn/Ft at r/R 0.30/0.47/0.63/0.80/0.95 next to the experiment and our ALM, using the force x arm convention of `compareSectionLoads.py` (`arm_contributions`, rho already included on both sides). Tests with a tiny synthetic vtk.
3. **Job B** (RA on, S) when it finishes: `comparePhaseVI.py --run-dir runs/alm-U7-coarse-seqS-p22-ra --speed 7 --sequence S --out /tmp/cmpS_ra`, `summarizeBands.py`, `compareInflowAngle.py`, `compareSectionLoads.py` (now with the force x arm block). Compare against FLOWUnsteady DS-on result of step 2 (RA is our Du-Selig a=b=d=1). Plan rule 2: no retuning on S; do not stack drag and RA into the definition without an owner decision.
4. **Owner decisions still open**: (a) is the pressure-drag polar a v1.2 definition change or only a diagnostic (D3 closed the power gap to -2.2 % but never applied to S)? (b) whether to act on the remaining normal-force misses (c_n +13 % at r/R 0.30, -14 % at 0.95; the tip carries ~95 % of the flapwise root-moment deficit). Do not implement anything from the literature without the owner (Chaviaropoulos-Hansen option declined for now).
5. Pending small items: `openfast_gust.py` has SeaState/HydroDyn/SubDyn off and platform DOFs off (repo files are pre-v5); IEA polars are Re 3e6 vs 1.4e7 in operation; nothing is uncommitted (see "Committed work").

### Committed work (branch `fix/compare-phasevi-surface-stations`, 2026-10-16; nothing pending in git)
`4217630` force x arm table + lit_search tests; `5f54505` FLOWUnsteady database writer + tests; `fa9196f` Julia driver, signScan, Slurm launchers, README;
this handoff commit. Not pushed. Still to do in code: `flowunsteady/README.md` body below its status note still describes the first smoke (`turbine_flag=true`); rewrite it once the four runs finish.

### FLOWUnsteady facts established this session (do not re-derive)
- Package source is in `/scratch/leahk/eduardo.donestevez/julia-depot/packages/{FLOWUnsteady,FLOWVLM,FLOWVPM,AirfoilPrep}/*/` (no clone needed). Run line in the install script.
- Working configuration (`flowunsteady/phaseVI.jl`): **`turbine_flag=false`**, pitch distribution = -(twist + 3 deg) (the driver negates the database value), `Vinf = [-7, 0, 0]`, `CW=false`, positive RPM; torque reported as -torque (propeller sign). Evidence: `signScan.jl` (wake-free, 16 combinations): only this one has a physically consistent global force (D/L at 0.47R = 0.12, Np 126 and Tp 33 N/m vs experiment 126 and 38); with `turbine_flag=true` the global `DistributedLoad` has a flipped tangential component (D/L 0.74, force.velocity < 0) and corrupts the bound circulation fed to the VPM. `rotationProbe.jl`: a positive `rotate` moves the blade along -x_local, as `calc_inflow` assumes.
- Smoke 11617359 (2 rev, DS on, total drag, 48 threads): force.velocity 7306 W vs monitor 7334 W; CT 0.658 -> 0.598, CQ 0.0955 -> 0.0800 falling with wake age (not converged; the 0.45-0.47 / 0.065-0.070 band applies to converged runs). 148 s + 412 s per revolution at 48 threads.
- FLOWUnsteady defaults kept: Du-Selig via `apply_correction3D` (switch), Viterna on, Prandtl factor off, no hub/tip correction; mid-high fidelity of rotorhover (n 50, 72 steps/rev, 2 sheds/step, RK3, no SFS, sigma R/10). Polars: S809 OSU Re 1e6 within |alpha| <= 20.1 deg (no +-180 closure written); Mehr 2024 does not say which polar/DS it used, so none of the four runs is "the" reference.
- Slurm placement: with `--ntasks` alone 32-48 tasks were spread over 4-6 nodes (all Julia runs failed in 1 s on the single-node guard). `--nodes=1` fixes it; `sequana_cpu_dev` (20 min) is only for smokes.

### Session 2 results (2026-10-16)
- Jobs: 11616862 (asm-mesh U10 S) and 11616964 (D3) COMPLETED; 11616888 (B, RA on S) still running, 5.4 s of ~10 s at 3 h 20 min (limit 24 h, left as is).
- **D3 (`alm-U7-coarse-d1-pdrag`, 12 rev, H)**: power 5.816 kW vs 5.946 kW = **-2.2 %** (baseline p21 5.292 kW, -11.0 %); prediction was about -6 %, so the closure is larger than predicted.
  Thrust -0.8 % (unchanged: drag does not touch the normal force). phi_force - phi_exp: +0.25 / -0.42 / +0.13 / +0.35 / +0.73 deg at r/R 0.30-0.95 (p21: -1.16 / -1.80 / -1.00 / -0.29 / -0.78): inside the 0.6 deg prediction at 0.30-0.80.
  Remaining misses are normal-force ones: c_n +13 % at 0.30 and -14 % at 0.95 (identical to p21).
- **Force x arm** (new block of `compareSectionLoads.py`; sim `f_ref_*` are kinematic, multiplied by the experiment rho; the experiment 5-station sum closes EAEROTQ at 0.990):
  station-sum torque deficit p21 -8.7 % -> D3 +0.2 %; edgewise root moment -8.9 % -> +0.1 %; flapwise root moment -3.2 % -> -3.4 % (unchanged), and ~95 % of that flapwise deficit is r/R 0.95 (Fn 139 vs 163 N/m, -50 N.m of -53).
  So for the FSI goal the surviving defect is the tip normal force, not the tangential force. Station 0.95 still misses tangential force by -6 % (20.8 vs 22.2 N/m).
- D3 is a DIAGNOSTIC (pressure-drag polar on H); decision 5 (v1.2 definition change or not) remains open. Nothing was applied to S.
- New: `tools/tests/test_lit_search.py` (5 tests, offline), `turbinesFoam/tests/test_section_moments.py` (3 tests).

### Environment facts
- Text of PDFs: `python3 -I tools/pdf_to_text.py OUTDIR PDF...`; literature search: `python3 -I tools/lit_search.py "query" --top 6 --since 2010 [--abstract 600]` (OpenAlex, no key).
- OpenFAST v5.0.0: `/scratch/leahk/eduardo.donestevez/conda-envs/openfast/bin/openfast`; sweep cases `simulations/tmp/iea15-of-sweep`, EOG cases `simulations/tmp/iea15-of-gust`,
  ROSCO libdiscon `simulations/tmp/rosco-2.10.6/rosco/lib/libdiscon.so` (PyPI wheel). These are outside git; regenerate with `openfast_sweep.py setup` / `openfast_gust.py setup --libdiscon ...`.
- Summaries: `openfast_sweep.py summarize DIR [--rmin 0.28 --rmax 0.5]`, `openfast_gust.py summarize DIR [--rmin --rmax]`, `stall_margin.py`.
- PDFs live in `turbinesFoam/articles/` (git-ignored). Subagent routing was broken earlier (`claude-bridge/claude-opus-5-5:high` not in models.json): explore directly.

## Literature review: Ramos-Garcia / MIRAS / Q3UIC (2026-10-16)
Files: `turbinesFoam/articles/A_quasi_3D.pdf`, `Validation of a three-dimensional viscous-inviscid ...pdf`,
`Wind Energy - 2020 - Ramos-Garcia ...pdf`. Text dump: `python3 -I tools/pdf_to_text.py OUTDIR PDF...`.
- MIRAS Eq. 16-18 (Renewable Energy 70, 2014, p. 81): Cd = Cd_3D,P + (Cd_SY - Cd_Q3P); Ct = Ct_3D,P - (Cd_SY - Cd_Q3P) cos(alpha).
  Pressure and friction drag are handled separately because integrating pressure gives a large drag error; the
  paper says tangential force is critical for power at high TSR. Supports D2 (polar Cdw 2x Cdp), does not prove it.
- Their own tangential-force misses sit at root/mid span (MEXICO root rotation under-predicted), same pattern as ours.
- Q3UIC rotation (RO = Omega r / U_rel, c/r): delays separation, raises lift, lowers drag slightly. Relevant only to
  the 10 m/s stall-delay miss, as a physical alternative to Du-Selig; not to the attached 7 m/s deficit.
- MIRAS-HAWC2 (2020): lifting-line + HAWC2 coupling; nothing on tangential loads. Not actionable.
- Decision: implement nothing from these. Wait for D3 (job 11616887). If D3 does not close the torque deficit,
  get Cd_p/Cd_f per section from an integral boundary-layer code (XFOIL-type) and use the Eq. 17-18 split.

## Literature search 2026-10-16 (OpenAlex via `tools/lit_search.py`; titles + abstracts only, no PDF read)
Matched to a diagnosed gap. Download PDFs into `turbinesFoam/articles/` before relying on any of them.
| gap | candidate | DOI | why |
|---|---|---|---|
| angle/sampling (D0: force 0.3-1.8 deg off) | Muscari 2024, effective velocity model | 10.1002/we.2894 | power ~independent of epsilon; current code samples at a point (`sampleInflow` hook in actuator-model-architecture.md) |
| same | Xie 2021, Lagrangian-averaged sampling + piecewise projection | 10.1002/we.2619 | alternative sampling |
| same | Zilic de Arcos 2020, six AoA extraction methods (SAM) | 10.1002/we.2523 | defines what "angle" the polar should be fed |
| tip (0.95: -22 % torque) | Kleine 2023, non-iterative vortex smearing correction | 10.1017/jfm.2023.237 | replaces iterative Meyer Forsting correction already vendored |
| tip / epsilon | Martinez-Tossas 2019, filtered lifting line | 10.1017/jfm.2018.994 | 2017 and 2023 papers already in articles/ |
| 10 m/s stall delay | Burgos Tafur 2020, CFD-calibrated Chaviaropoulos-Hansen on Phase VI (OpenFOAM) + Shen tip | 10.1007/s10409-020-00949-0 | closest to our case |
| same | Guntur 2013; Herraez 2014; Sant 2006 (AoA from Phase VI pressures) | 10.3390/en7106798, 10.1002/we.201 | rotational augmentation data on this rotor |
Not found: any paper on total (wake-rake) vs pressure drag for S809 in ALM/BEM. D2 stays an own result.

## Papers read 2026-10-16 (PDFs now in turbinesFoam/articles/; text via tools/pdf_to_text.py)
- **Burgos Tafur 2020** (Sci-Hub. _ 2,.pdf): on Phase VI, Chaviaropoulos-Hansen (CH) is the best of DS, Snel, Lindenburg,
  CH against rotating OpenFOAM polars; DS under-corrects lift after ~5 deg inboard (r/R 0.33, 0.39); CH with Shen tip is ~20 % off
  after stall at 0.95. CH corrects lift AND drag: f_L = f_D = a (c/r)^h cos^n(theta), a=2.2, h=1, n=4; CL3D = CL2D + f_L (CL,inv - CL2D),
  CD3D = CD2D + f_D (CD2D - CD0). Their fitted a_n(r/R, U) (Tables 3-4, 6-10 and 10-20 m/s) come from CFD of this same rotor;
  Table 3 is garbled in the text dump, read it from the PDF before use. We implement DS and Lindenburg only: CH is the
  candidate for the 10 m/s stall-delay miss. Baseline constants only (a=2.2); do not use the fitted tables on S.
- **Zilic de Arcos 2020**: 5 of 6 AoA methods agree at mid-span; the pressure method is the outlier; near the tip AoA is ill-defined.
  A definition check for D0, not a fix.
- **Kleine 2023**: non-iterative equivalent of the Meyer Forsting correction; authors report no significant difference vs
  iterative. Speed/stability gain only: NOT a lever for the tip -22 % torque.
- **Muscari 2024 / Xie 2021**: velocity sampling that reduces epsilon dependence (power independent of epsilon below rated;
  thrust under-predicted, viscous-core angle correction suggested). Neither addresses tangential force; BEM shares our
  angle error, so sampling is not the main cause.
- Proposed next step (not started, owner decision): add `ch` to `--rotational-augmentation`, test 10 m/s on H first,
  then S as a pre-registered variant beside DS (same rule as B).
- **Martinez-Tossas & Meneveau 2019** (Sci-Hub. _ ,.pdf): epsilon_opt ~ 0.25 c; epsilon > epsilon_opt over-predicts tip lift and needs
  the filtered-lifting-line sub-filter velocity correction (assumes inviscid, tabulated polars). Our production eps =
  2*cbrt(V)*meshFactor (grid-based, see p2-2-sequence-s.md l.161): check eps/c along the span against 0.25 before reading
  tip differences as physics. Tested only on fixed wings; rotation left to later work.
- **Guntur & Sorensen 2014** (guntur2014.pdf, MEXICO CFD): rotation delays separation onset to higher AoA and moves the separation
  point downstream; centrifugal effects act along the whole chord, so augmentation can exist with no visible separation;
  cp is unreliable to locate separation on a rotating blade. Supports a rotational correction inboard even when attached.
- Not in articles/: Herraez 2014 (10.3390/en7106798), Sant 2006 (10.1002/we.201). 2206.05448v3.pdf is the arXiv copy of Kleine 2023.
- Remaining unread: Ramos-Garcia 2020 (FSI) beyond the abstract-level pass; low value.

## Owner priority (2026-10-16): FSI is the goal
Root loads matter less (stiffer blade); tangential force matters structurally. Tune the model first, then declare the
root simplification. Consequence: the station deficits that count are r/R 0.47 (-10.5 % torque) and 0.95 (-22 %), not 0.30 (+9 %).
Inboard rotational augmentation (DS/CH) ranks below tip and mid-span work, except for 10 m/s stall onset.

## Validation priority (owner, 2026-10-16): thesis turbine is IEA 15 MW, real operating regime first
Phase VI is the experimental anchor for the method. That the IEA 15 MW operates without stall is NOT established: the
IEA-15-240-RWT repository and official documentation show no blade stall, but all of it is numerical, so it must be
analysed (AoA vs span in our own IEA 15 MW runs against the polar stall angle). The solver should end up accurate in stall
and out of it; the order is: real operating regime first, stall (10 m/s RA miss) second, not discarded. The Phase VI
envelope to defend first is the attached range; its upper wind speed is read off the 21-point S curve, not assumed.
Open points for the report:
- Phase VI at 7 m/s is TSR ~5; IEA 15 MW is at a higher TSR, where MIRAS says the tangential force (small difference of
  large terms) is most sensitive to the friction drag: the drag definition (D3) is then more important, not less.
- Inboard thick airfoils of the IEA 15 MW can still see high AoA and rotation effects; state that as a limitation.

## IEA 15 MW stall margin (2026-10-16) — `turbinesFoam/validation/iea15mw/scripts/stall_margin.py`
Test: `turbinesFoam/tests/test_iea15mw_stall_margin.py` (4 pass). Input: committed `analysis/spanwise-profiles.csv`
(alm/asm/asm-mesh, rated point, TSR 8.91, last revs); polars at nominal Re 3e6.
Result (model alm, 147 stations): r/R > 0.5: alpha 6.7-7.8 deg vs cl_max angle 14-15 deg (margin 6.4-8.1 deg), but only
2.7-3.7 deg below the departure from linear lift (alpha_dev ~10.5 deg, threshold 0.1 in cl). r/R 0.29-0.5: margin to cl_max
7-8 deg, to departure 0-2.2 deg. r/R < ~0.28: NONLIN; r/R < ~0.14: past cl_max (thick root airfoils, alpha up to 58 deg).
Counts: STALL 10, NONLIN 21, NEAR 80, ok 29, n/a 7 (cylinders).
Reading: at the rated point the outer blade is attached, not stalled; the root is deep in post-stall (low structural
priority per owner). Not yet covered: other wind speeds / pitch (only the rated snapshot is committed), gusts, yaw, shear,
Re = 1.4e7 vs polar Re 3e6, and the arbitrary 0.1 departure threshold (`--dev`).

## Owner roadmap (2026-10-16)
1. Experimental validation against Phase VI; set the model limits from the results plus every improvement we can make.
2. Numerical validation on the IEA 15 MW, in the regime that step 1 shows the model reproduces with the best fidelity.
3. FSI.
Gate between 1 and 2: the intersection of (a) the Phase VI range where the model is inside its band and (b) the IEA 15 MW
operating envelope from `openfast_sweep.py` (job 11616921, cases in simulations/tmp/iea15-of-sweep). Write the band
for step 1 before reading step 2 results. The 10 m/s Phase VI stall miss becomes a declared limit of step 1.

## OpenFAST BEMT sweep result (job 11616921, 74/74 ok, rpm/TMax verified per case; cases in simulations/tmp/iea15-of-sweep)
`openfast_sweep.py summarize`, r/R > 0.5, blade 1, max alpha over the last 2 revs, polar Re 3e6, departure threshold 0.1 in cl.
- No station at r/R > 0.5 reaches the cl peak in any of the 74 cases (no STALL flag).
- Operating table: max alpha 7.6 deg at U 7-10.7 m/s (margin to cl_max 6.6 deg, to departure 2.9 deg, worst r/R 0.82); above rated pitch
  drops alpha to 3-5 deg. OpenFAST 7.6 deg agrees with our ALM at rated (6.7-7.8 deg).
- Yaw +-15 deg: worst case 7.9 deg (margin 6.4 / 2.6). Shear 0.2: no change. Static +15 % gust at fixed rpm/pitch: 9.0-9.1 deg at
  7.97 and 10.66 m/s (margin 5.1-5.3 to cl_max, 1.4-1.5 to departure, 24 of 26 stations NEAR); above rated 5.6-6.7 deg.
- Limits: BEMT without unsteady aerodynamics, static gust (no pitch lag, no dynamic stall), r/R <= 0.5 not summarised,
  no test for `summarize`.

## Thesis scope decision (owner, 2026-10-16)
Stall region is outside the thesis scope; it is still characterised and documented as a limit of the implemented models
(Phase VI 10 m/s RA miss, DS/CH/Lindenburg behaviour). Supporting evidence so far: steady BEMT sweep only; a dynamic-gust
check (pitch lag, dynamic stall) is the open item that could reopen the scope.

## OpenFAST EOG result (job 11616935, 4/4 terminated normally; cases in simulations/tmp/iea15-of-gust)
Script `validation/iea15mw/scripts/openfast_gust.py` (no test yet). ROSCO 2.10.6 libdiscon (PyPI wheel, simulations/tmp/rosco-2.10.6),
BEMT + Beddoes-Leishman (UA_Mod 3), flexible blades/tower, EOG class IB at t=120 s, window 110-180 s, r/R > 0.5, polar Re 3e6.
Limits: SeaState/HydroDyn/SubDyn off (repo files are pre-v5 layout), platform DOFs off (tower cantilevered; with them on the run
went NaN at ~19 s); input files merged onto v5 templates (data/openfast-v5-templates/ServoDyn_r-test_v5.0.0.dat).
| Vhub | peak alpha (r/R) | margin cl_max | margin departure | pitch max | rpm max |
| 8.0 | 9.5 (0.51) | 4.7 | 1.0 | 0 (region 2) | 6.12 |
| 10.66 | 9.6 (0.51) | 4.7 | 0.9 | 7.3 | 8.29 |
| 12.5 | 7.0 (0.51) | 7.2 | 3.5 | 11.2 | 8.34 |
| 18.0 | 6.1 (0.51) | 8.1 | 4.4 | 16.8 | 8.57 |
Reading: even with controller lag and dynamic-stall model on, the outer blade stays below the cl peak (min margin 4.7 deg);
it reaches the edge of linear lift (~1 deg) at 8 and 10.66 m/s, where trailing-edge separation starts. The worst station is
r/R 0.51 = the lower bound of the summarised zone, so the zone r/R <= 0.5 may be worse and is NOT summarised yet.
Stall stays out of thesis scope but at rated/below-rated gusts the model operates at the limit of linear lift: document it.

## Zone r/R 0.28-0.5 (`--rmin 0.28 --rmax 0.5` on both summarize commands; worst station is always r/R 0.29)
Steady sweep: operating table 7-10.7 m/s alpha max 8.2-8.6 deg, margin to cl_max 7.5-7.8, to departure ~0 (NEAR, one NONLIN at rated);
above rated 7.4-7.6 deg (margin departure +0.8..+1.0). Yaw/shear at 10.66: 8.8-9.0 deg, departure margin -0.3..-0.6 (NONLIN 1).
Static +15 % gust: 11.4-11.6 deg at 9.2/12.3 m/s (margin cl_max 4.5-4.7, departure -2.9..-3.1, 6-7 stations NONLIN);
gust at 25 m/s (28.75): 16.9 deg, one STALL. EOG with controller + B-L: 12.4-14.5 deg at r/R 0.29 (margin cl_max 1.6-3.7,
departure -3.9..-6.0, i.e. past linear lift but before the peak).
Reading: r/R > 0.5 is attached with margin; the inner blade (r/R 0.28-0.5) already sits at the end of linear lift in steady rated
operation and goes into trailing-edge separation (no peak) in gusts. This is where polar quality (Re 3e6 vs 1.4e7, 3-D effects)
matters for the IEA 15 MW, and is structurally secondary per the owner's root criterion but not negligible near r/R 0.4-0.5.

## Mehr, Alvarez & Ning 2024 (Wind Energy 28:e2957) and FLOWUnsteady (read 2026-10-16; figures not read)
File: `turbinesFoam/articles/Wind Energy - 2024 - Mehr - Interactional Aerodynamics Analysis of a Multirotor Energy Kite.pdf`.
Code: https://github.com/byuflowlab/FLOWUnsteady (open source, Julia; actuator line/surface + reformulated vortex particle method).
- Appendix A validates FLOWUnsteady on **UAE Phase VI sequence H** (72 rpm, 5-24 m/s, 20 cases, S809 polars Re 3e5-1e6, 50 blade
  elements, 72 steps/rev, convergence <1 % CT, <3 % CP). Reported (text only): CT and CP within experimental range except lowest
  TSR (errors 1 % and 13 %); torque within 10 % for TSR > 2, within 25 % below. The paper does not say whether the polar drag is total
  or pressure, and mentions no rotational-augmentation correction for UAE (CCBlade rotational correction + Viterna only for the Makani rotor).
  => An independent code-to-code reference on our exact experiment; worth comparing our 7 m/s result (-11 % power) against their CQ curve
  (digitise Fig. A4 or run their example).
- Docs validation page, wing case (Weber & Brebner): experimental drag was integrated from pressure taps and "excludes skin friction"; the
  authors compare against ASM drag accordingly. Same pressure-vs-total drag issue as our D2; supports checking what the experiment integrates.
- ASM (actuator surface model) of Alvarez & Ning (J. Aircraft 2023, 10.2514/1.C037279): lift/drag on a surface with spanwise flow, good up to
  moderate AoA, no separation modelling: same stated limit as ours.
- Not actionable: energy-kite interaction results; airfoil data there are approximations (no XFOIL).
Proposed (not started): (1) digitise Fig. A4 and tabulate CQ(TSR) vs ours; (2) skim FLOWUnsteady's rotor/ALM source for drag handling,
tip treatment and angle-of-attack sampling (Alvarez & Ning 2022 on core overlap/relaxation); (3) add Alvarez 2022 dissertation
(https://scholarsarchive.byu.edu/etd/9589/) if more detail on the actuator-line force projection is needed.

## FLOWUnsteady code-to-code reference (2026-10-16): Fig. A4 digitised, source skimmed
Tools: `turbinesFoam/validation/phaseVI/scripts/digitizeFlowUnsteadyFigA4.py` (reads the vector drawing of the PDF, not an image; calibrates axes from the
tick marks) -> `validation/phaseVI/data/reference/flowunsteady_mehr2024_figA4.csv`; tests in `tests/test_openfast_scripts.py` (4 pass; also covers
openfast_sweep/gust helpers). Experimental bars are the min/max range of each case, not the mean.
Result at TSR 5.37-5.41 (7 m/s, 72 rpm): FLOWUnsteady CT 0.4592 (exp range 0.4436-0.4777, mid -0.3 %), CQ 0.0699 (exp range 0.0591-0.0667,
**above** the range, +11 % vs mid), CP 0.373 (range 0.244-0.453, +7 % vs mid). Against our measured CQ 0.0653 (LSSTQCOR 801 Nm, rho 1.2525, R 5.029)
FLOWUnsteady is +7.0 %; our ALM is -11 % in power. Whole TSR sweep: CQ +9..+11 % above mid for TSR 3.8-7.4 (above range at 4.7-6.2), CT within +-5 % from TSR 2.1.
The paper's statement "torque within 10 %" holds only vs the mid-range, and it never says which polar/corrections were used for UAE.
Source (byuflowlab/FLOWUnsteady + FLOWVLM, cloned in /tmp/flowu, not kept):
- Force: thetaV = atan(Vx, Vy) of the local velocity, alpha = thetaV - twist, cn = cl cos + cd sin, ct = cl sin - cd cos (identical to our ALM);
  tip/hub Prandtl factor multiplies **cl only** and is OFF by default (`hubtiploss_nocorrection`).
- Polar treatment defaults: `apply_correction3D = true` (AirfoilPrep **Du-Selig** rotational correction, and per Alvarez's thesis also a 3-D drag correction),
  `apply_extrapolate = true` (Viterna). So FLOWUnsteady's UAE result most likely includes Du-Selig; our -11 % is with Du-Selig OFF, and our own
  estimate was +5.8 points for DS on (job 11616888 will measure it). Consistent with the 18-point gap, not proven: Mehr does not state the setting.
- Velocity sampling: only wake-induced velocity (`Vinds = Vvpm_rotors`; the rotor-on-rotor bound-vortex term is commented out "to reduce noise"),
  i.e. no self-induction of the smeared bound vorticity: lifting-line-like, which avoids the sampling problem of Muscari/Xie/Martinez-Tossas by construction.
  The thesis states it probes the LES at the quarter chord.
- Thesis (Alvarez 2022, in articles/): the validation cases compare against pressure-tap-integrated experimental drag "excluding skin friction"
  (swept wing, Veldhuis tangential force): same awareness as D2; no UAE case in the thesis.
Next (not started): when job 11616888 finishes compare RA-on power against this +7 % reference; if D3 does not close the deficit, the 18-point gap to FLOWUnsteady
is the second thing to explain (DS on? polar? tip off?). FLOWUnsteady is Julia; running its UAE case needs Julia + VPM packages (not installed here).

## FLOWUnsteady installed (2026-10-16)
Julia 1.11.3 + `/scratch/leahk/eduardo.donestevez/flowunsteady-env` (depot `julia-depot`); `import FLOWUnsteady` works (generate_rotor, run_simulation present).
Recipe and the four traps (broken Pkg in other modules, depot path colon, unregistered deps with docs names, FastMultipole master): `validation/phaseVI/flowunsteady/install_flowunsteady.sh`.
Run: `LD_LIBRARY_PATH=/scratch/app/julia/1.11.3/lib JULIA_DEPOT_PATH=<depot>: /scratch/app/julia/1.11.3/bin/julia --project=<env> script.jl`.
Not done: the Phase VI rotor case (repo has no UAE example; Mehr's script is not published). Needs geometry + S809 polars of ours.

## Owner decisions 2026-10-17 (session 3)
1. FLOWUnsteady: not used as a reference (it does not match the experiment). No further runs.
2. Pressure-drag polar (D3): adopted for now as the best result; keep diagnosing.
3. No more simulation time in stall (RA at 10 m/s not run); model limits are documented from existing results once the attached regime is validated.
4. Window: agent's choice, provided it is quasi-steady. Done: `compareSectionLoads.py`, `compareInflowAngle.py` and the ALM columns of
   `compareFlowUnsteadyStations.py` now use `comparePhaseVI.window_bounds` (revolutions 4-12, per-sequence TSR) and refuse a window that fails
   `drift_flags` (exit 2; `--allow-drift`). All current runs pass. Numbers move < 0.5 points: D3 torque +0.2 -> -0.3 %, p21 -8.7 -> -9.1 %,
   S p22 -9.0 -> -9.3 %, B -5.1 -> -5.3 %; flapwise unchanged within 0.2 points.

**Finding (blocks the v1.2 definition text):** every P2.1/P2.2 Phase VI run (H and S, ALM/ASM/ASM-mesh, p21, D3, seqS-p22, B) ran with
`endEffectsModel Glauert; tipEffects on` and `tipCorrection active off`, while `validation-model-definition.md` v1.1 freezes D&S on and Glauert
tip off. Cause: `config/case.yaml:337-354` defaults (Glauert tip+root on, D&S off) and the P2 launchers pass no tip flags. Only `dagtip`/`dagtipd`
(2026-10-08, 4 rev, root off, 50 elements, pre-`4c49dc3`) used D&S on Phase VI: H 7 m/s %P +0.5, c_n 0.80 +13.2 %, 0.95 +50.8 %, station-sum
flapwise +14.1 % (vs Glauert p21: -11.0 %, +0.2 %, -14.0 %, -3.2 %). D&S over-loads the tip like FLOWUnsteady; Glauert under-loads it.
IEA control (P0.4): Glauert cp 0.5461 vs OLAF 0.5312 (+2.8 %), D&S ~0.562-0.565 (+5.5..6 %). Owner decision pending.
