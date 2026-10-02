# Feature: Phase VI end-effect diagnostic (tip-off arm A′)

- **Status:** in progress
- **Branch:** (feature branch to be cut before the first commit)
- **Created:** 2026-09-28
- **Reference:** `turbinesFoam/validation/phaseVI/campaign-results/formulation-review.md`
  §2 (the smearing/bound-circulation thesis) and `SOWFA-6-crosscheck.md`.

## Objective

Decide, by measurement, whether our **Glauert tip end-effect** is the main cause
of the Phase VI 7 m/s deficit (−7.2 % power, arm A), before any code change to the
formulation.

## Problem / Why

Two independent lines of evidence say our BEM-type end effects are the wrong
instrument for an actuator line:

**Class A — provable by code inspection (no campaign needed):**

- **A1. The root factor is the tip factor mirrored.** In
  `axialFlowTurbineALSource.C:639-647`, `tipDist = 1.0 − rootDist` makes
  `f_root ∝ 1/(1−r/R) − 1`, which vanishes at **r = 0 (the axis)**, not at
  `r = HubRad`. At the hub it evaluates to `F_root ≈ 0.75`. A root loss must
  vanish at the hub. SOWFA's confirmed form
  (`F_root = (2/π)acos(exp(−(B/2)(r−R_hub)/(R sinφ)))`, Mohammadi 2024 §2) does.
- **A2. The `meshFactor` default is a trap.** `actuatorLineElement.C:412-433`
  defaults `meshFactor` to **2.0** → `ε/Δx = 4`. Jha 2014 Table 2 measures
  `ε/Δx = 4` as **+22.6 %** power on the Phase VI rotor. The case sets 1.0.
- **A3. The Shen `c1` sign is inverted vs. the paper.** The code computes
  `g = exp(−c1(Bλ−c2)) + 0.1`; Shen 2005 writes `g = exp[−0.125(Bλ−21)] + 0.1`,
  so the dict must pass `c1 = +0.125`, not the paper's `−0.125`.

**Class B — empirical (the campaign):** arm B (`root-on`) is worse than arm A
(`root-off`) at **every** measured point (10 m/s: −26.7 % vs −14.6 %; 15 m/s:
−1.40 kW vs +1.96 kW). The root correction hurts.

**Class C — literature consensus (the modeling choice):** Meyer Forsting 2019/2020,
Kim 2015, Jha 2014, Mohammadi 2024 all state that a BEM tip/root loss corrects a
*disc* for missing discrete blades and is therefore invalid for an ALM. The
physically consistent fix is to restore the missing bound-circulation induction.

## Hypothesis and falsifiable prediction

Turning the **tip** effect off (arm **A′**: aug-on, tip-off, root-off) should move
the 7 m/s power from **−7.2 %** toward Jha 2014's uncorrected `ε/Δx = 2` value of
**≈ +5 %** (a ~12-point swing). If it does **not** move, the Class C diagnosis is
wrong for our case and no further formulation change is justified.

## Scope

**In scope**

- Add an `aug-on-tip-off-root-off` arm to
  `scripts/slurm/campaign-rotational-augmentation.slurm` (task id 7), threading
  `--tip-effects` through `map_task` / `task_runs` / `run_one` / the dry-run.
- Dry-run verification of the task → run map.
- Launch the arm at 7 / 10 / 13 m/s, `alm`, coarse.
- Compare against the existing arm A with `scripts/comparePhaseVI.py`.

**Out of scope (only after the result)**

- P2 LAS sampling (`velocitySampleRadius` / `nVelocitySamples` are **not**
  rendered by `generate_case.py` — a real code change).
- P4b the NP rotor-update scheme.
- P4 the filtered-lifting-line or vortex-based smearing correction.
- Any change to the committed `case/` defaults.

## Tasks

1. [x] Add the tip-off arm to the campaign script and dry-run verify.
2. [x] Launch the arm (7/10/13, alm, coarse) — job `11603354_7`, RUNNING.
3. [x] Compare against arm A and record the verdict in `RESULTS.md`.
4. [ ] Decide P2 / P4b / P4 from the result.

### Discriminating tests (launched 2026-09-29)

- **A′ on the D/48 fine mesh, 7 m/s** — ε drops 0.63 m → 0.42 m. If the +19.5 %
  over-shoot shrinks, the ε hypothesis is confirmed.
- **C′ (aug-off, tip-off, root-off), 7 m/s** — A′ vs C′ differ only in the
  augmentation flag, isolating how much of the over-shoot is Du–Selig.

Both in job `11603576` (tasks 7 and 8).

**Result (2026-09-29):**

- **C′ delivered** (task 8, 4 nodes, reached rev 12.00): `Cp = 0.4042`,
  **+14.3 % P / +18.8 % T**. A′ vs C′ isolates Du–Selig at **+5.2 pts** — real but
  **not dominant**.
- **A′ fine FAILED** (task 7, 7 nodes) in `MPI_Init_thread`: `ibv_cmd_reg_dm_mr`
  → `btl_openib_connect_udcm` → signal 11. The run produced **no data**. This is
  the documented multi-node MPI failure the removed `--nodes` cap used to
  prevent — it reproduced at **7 nodes**, while **4 nodes succeeded**.
- **MPI diagnosis:** OpenMPI 4.1.4 on SDumont has `pml ucx` available, but the
  backtrace shows `mca_bml_base_init()` — i.e. the **ob1** PML is active, which
  initializes the legacy `openib` BTL and crashes. `mpirun` in
  `runPhaseVI.sh:391` is called with no `--mca` flags.
- **Probe launched:** job `11603591` (`--nodes=7` deliberately, to reproduce)
  tests `mpirun -np 48 hostname` baseline vs `--mca pml ucx` vs
  `--mca btl ^openib`.
- **2026-09-29 — probe result (job `11603591`, 29 s, exit 0).** On 7 nodes
  (`sdumont6146..6150,6246,6247`) **all three transports succeeded**:
  `baseline OK (48 ranks)`, `pml_ucx OK`, `btl_noopenib OK`. The `MPI_Init`
  crash is therefore an **intermittent race** in the legacy `openib` BTL device-
  memory registration (`btl_openib_connect_udcm` -> `ibv_cmd_reg_dm_mr`), not a
  node-count-deterministic failure. Excluding that BTL still removes the
  possibility.
- **2026-09-29 — MPI fix applied.** `scripts/runPhaseVI.sh` now runs
  `mpirun ${TURBINE_MPI_MCA---mca pml ucx --mca btl ^openib} -np <ranks>`,
  overridable via `TURBINE_MPI_MCA` (empty = site default). Verified: `bash -n`
  OK; the expansion yields the default when unset, empty when set empty, and the
  custom value otherwise.
- **2026-09-29 — A′ fine relaunched** (`runs/alm-U7-fine-aug-on-tip-off-root-off`
  removed so it re-runs): job `11603592_[7]` (pending). The three already-
  complete coarse A′ runs are caught by the skip guard.
- **2026-09-29 — H-index re-check (memory `turbinesfoam/latent-bugs` #216,
  audit #214).** Re-verified per case:
  - **H3a — APPLIES, and is a new physics deviation.**
    `actuatorLineElement.C:1036` is `liftCoefficient_ *= endEffectFactor_;` — the
    end-effect factor multiplies the **lift only**; drag and moment are
    untouched. **Shen 2005 Eqs. 23–24 apply `F1` to `Cn` *and* `Ct`**, and Yang
    2017 Eqs. 13–14 to `CL` *and* `CD`. Scaling only lift rotates the local force
    vector toward drag, precisely in the tip/root region where `F` departs
    from 1.
  - **H3b — APPLIES (minor).** `axialFlowTurbineALSource.C:859` calls
    `calcEndEffects()` *before* the element `addSup` loop (`:863-865`), so the
    factor uses the **previous** PIMPLE iteration's velocity (one-step lag). The
    Glauert `phi` itself is computed correctly from the element state; H3's
    "geometry-only" note refers to a different lifting-line function
    (`actuatorLineSource.C:498-499`), not the AFTL Glauert/Shen path.
  - **H8 — DOES NOT APPLY.** The `binarySearch` bug hits only table sizes of the
    form **`n = 2^k + 1`** (verified by replicating: 3/5/9/17/33/65/129 fail;
    11/25/49/69/103 pass). Our committed polar has **59 data rows** and a query
    above the max returns the last index, so the top-edge clamp is reached.
  - **H9 / H7 — DO NOT APPLY** (dynamic stall is off). **H4 — DOES NOT APPLY**
    (no FSI).
  - **Consequence:** the +26.6-point A→A′ swing removed a factor that was both
    mis-shaped (lift-only) and stale — strengthening the case for *replacing* the
    BEM correction rather than tuning it. Recorded in
    `campaign-results/formulation-review.md` §3.0 and memory observation #220.

### 7 m/s decomposition

```
C′ (no aug, no tip, no root)      +14.3 %   <- "everything else"
+ Du-Selig (A′ - C′)              + 5.2 pts
= A′                              +19.5 %
- Glauert tip loss (A - A′)       -26.6 pts
= A                               - 7.2 %
```

### ε hypothesis REFUTED (A′ fine, 2026-09-29)

| arm | mesh | ε | %P | %T |
|---|---|---:|---:|---:|
| A′ | coarse D/32 | 0.63 m | +19.5 | +24.0 |
| **A′** | **fine D/48** | **0.42 m** | **+19.6** | **+23.9** |

A 1.5× ε reduction changed the answer by **0.1 %** → the base over-shoot is
**mesh-independent**, so it is **parameterization-limited**, not numerical.

**Decisions this forces:**

- **P4 (FLLT / smearing correction) is NOT justified.** If neither ε nor Δx
  moves the answer, restoring the smearing-lost induction does not attack this
  error.
- **P2 (LAS sampling)** remains a robustness improvement, not a fix.
- **The D/48 / D/64 ladder buys nothing** for this error → queue/quota saving.
- **Next lever is the parameterization**: polar (OSU Re=1e6 vs CSU), solver
  (URANS vs LES), domain (no tunnel blockage), or the convection scheme.
- **The tension to resolve**: tip ON → −7.2 %, tip OFF → +19.5 %, measurement
  0 %. The BEM tip correction is **cancelling a base error of ~+14.3 %**; find
  that base error first.

## Evidence log

- **2026-09-28 — script change verified.** `bash -n` passes. Dry-run
  (`TURBINE_CAMPAIGN_DRY_RUN=1`) gives exactly three runs for task 7:
  `alm U7/U10/U13 coarse --rotational-augmentation on --root-effects off
  --tip-effects off --run-label aug-on-tip-off-root-off`. Arm A (task 0) is
  unchanged (5 coarse + 2 fine). Total run count 47 → 50.
- **2026-09-28 — launched.** `TURBINE_LONG_QUEUE_AUTHORIZED=1 sbatch --array=7`
  → job `11603351_[7]`, **PENDING, Reason=Priority, StartTime +32 h**.
- **2026-09-28 — SBATCH policy fix (project-wide).** The job was pending because
  of the SBATCH header, not the script logic:
  - `#SBATCH --nodes=1-2` with `--ntasks=48` on 48-CPU / 384 GB nodes, combined
    with the partition default `DefMemPerCPU=8000`, produced
    `ReqTRES=cpu=48,mem=375G` — i.e. **100 % of a node's memory**, so the job
    could only start on a fully free node (`idle total: 0` at the time).
  - The `--nodes=1-2` cap was there for a real reason (documented in the script):
    uncapped, Slurm spread the 48 ranks over **7+ nodes** and the OpenMPI/PMIx
    startup failed intermittently. Per project policy the cap is now removed.
  - **Removed `--nodes` from all six `scripts/slurm/*.slurm`** (asm-mesh,
    campaign, production, stage0, stage3, stage3-d64). No `--mem` existed in any
    of them. Verified: `grep 'SBATCH.*--nodes\|SBATCH.*--mem'` → none.
- **2026-09-28 — relaunched.** `scancel 11603351`; `sbatch --array=7` → job
  `11603354_7`, **RUNNING immediately**, `NumNodes=7`
  (`sdumont[6057,6264-6269]`). Removing the cap fixed schedulability; it also
  reproduced the 7-node placement the cap used to prevent — watch for MPI
  startup failures and fix them with `--distribution`/`--ntasks-per-node`, not
  with a node cap.
- **2026-09-28 — physics verified.** Rendered `fvOptions` for the running case:
  `GlauertCoeffs { tipEffects off; rootEffects off; }`. Arm A renders
  `tipEffects on; rootEffects off;`. The **only** delta between the two arms is
  the tip effect — a clean ablation.
- **2026-09-28 — RESULT (job `11603354_7`, 3 h 39 m, all 3 runs OK).**

  | U | %P tip ON (A) | %P tip OFF (A′) | swing | %T ON | %T OFF |
  |---:|---:|---:|---:|---:|---:|
  | 7 | −7.2 | **+19.5** | +26.6 | +2.6 | +24.0 |
  | 10 | −14.6 | **+21.8** | +36.4 | −13.1 | +10.4 |
  | 13 | −76.5 | **−14.8** | +61.7 | −19.1 | **+1.2** |

  **Hypothesis verdict: the direction was right, the magnitude was 2× larger
  than predicted.** The prediction was “−7.2 % → ≈ +5 %” (a 12-point swing); the
  measured swing is **+26.6 points**, landing at **+19.5 %**, i.e. past the
  measurement.

  **Interpretation.** The diagnosis (a BEM tip loss is a dominant spurious term
  for our ALM) is **confirmed**. But deleting it **overshoots**, which shows the
  tip loss was *cancelling* the ε over-smearing bias, not correcting anything:
  at 7 m/s, ε-over-smearing ≈ +19.5 % and the tip loss ≈ −26.6 pts, netting
  −7.2 %. Both are artifacts; the answer is to remove both, not to tune between
  them. Thrust improves sharply where the tip loss hurt most (13 m/s: −19.1 % →
  **+1.2 %**, in band).

  **Next:** P4 (filtered-lifting-line / vortex-based smearing correction) becomes
  the justified code change. Two cheap discriminating runs first: A′ on the D/48
  fine mesh at 7 m/s (tests the ε hypothesis), and C′ (aug-off, tip-off,
  root-off) at 7 m/s (isolates Du–Selig).
- **2026-09-29 — discriminating tests launched.** Added `fine_speeds="7"` to arm
  A′ and a new task 8 for arm C′ (`aug-off-tip-off-root-off`, 7 m/s coarse).
  `--array=0-8`, `n_tasks=9`, total run count 50 → 52. Dry-run verified; the
  three already-complete A′ runs are caught by the skip guard. Submitted
  `--array=7,8` → job `11603576`; both tasks RUNNING (7 and 4 nodes).
  Group quota at launch: **2 048 397 008 KB of 2 147 483 648 KB (~95 %)**.
- **Risk — group quota.** `lfs quota -g leahk /scratch` read **1.908 T of 2 T**
  (95 %) before this job. The script deletes `processor*/` after each run reaches
  `endTime`, so at most one run's field data is on disk at a time (~5-6 GB); a
  single `EDQUOT` fails the run. Watch the quota.
