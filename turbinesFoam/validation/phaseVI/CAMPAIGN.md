# Phase VI rotational-augmentation validation campaign (prepared only)

Converged power-curve campaign for the **rotational-augmentation candidate**:
the full staged curve at D/32 plus a D/48 spot-check, for the three models
`alm`, `asm` and `asm-mesh`, in a **single arm** for clean comparability.

> **Prepared only.** The array is never submitted by the preparing change.
> It refuses to run without `PHASEVI_LONG_QUEUE_AUTHORIZED=1` (exit 5). The
> launch order stays with the maintainer.

## Candidate configuration

| Key | Value | Runner flag |
|---|---|---|
| Rotational augmentation | active | `--rotational-augmentation on` |
| Glauert root effect | off (ablation) | `--root-effects off` |
| Dynamic stall | off (committed) | — |
| Tip effect | on (committed) | — |
| Du–Selig constants | `a=b=d=1` (committed) | — |

The candidate is the `augmentation-on + root-off` arm that the 0.25-rev proxy
identified as the only one inside the ±15 % band at 7 m/s (deficit −14.99 % →
+1.79 %; see the archived change
`openspec/changes/archive/2026-09-24-rotational-augmentation/archive-report.md`).
The proxy's own U13 primary criterion was **not** met (augmentation-on `cp`/`ct`
≈ 0, strictly negative), which is exactly why this converged campaign is the
real gate (archive-report finding **C-1**).

## Matrix — 21 array tasks

`--array=0-20`; `#SBATCH --ntasks=48`, one node, `--time=96:00:00`, partition
`sequana_cpu`. Each task restarts from the latest written time.

| Id | Model | Speed (m/s) | Mesh | Block |
|---|---|---|---|---|
| 0–4 | `alm` | 7, 10, 13, 15, 25 | `coarse` (D/32) | full curve |
| 5–9 | `asm` | 7, 10, 13, 15, 25 | `coarse` (D/32) | full curve |
| 10–14 | `asm-mesh` | 7, 10, 13, 15, 25 | `coarse` (D/32) | full curve |
| 15–16 | `alm` | 7, 13 | `fine` (D/48) | spot-check |
| 17–18 | `asm` | 7, 13 | `fine` (D/48) | spot-check |
| 19–20 | `asm-mesh` | 7, 13 | `fine` (D/48) | spot-check |

Per-task invocation (the array maps each index to a `model:speed:mesh` tuple):

```sh
scripts/runPhaseVI.sh -m <model> -u <speed> -mesh <coarse|fine> -s H \
    --rotational-augmentation on --root-effects off --restart --run
```

20 m/s is deliberately absent (renderable but not staged). Sequence S is not
part of this matrix.

`runs/` directories are the runner's canonical ids (`runs/<model>-U<speed>-<mesh>`,
e.g. `runs/alm-U13-coarse`). The augmentation/root state is **not** encoded in
the run id or in `run.json`; the committed array script (and its commit) is the
config provenance for this arm.

## Launch

```sh
cd turbinesFoam/validation/phaseVI
PHASEVI_LONG_QUEUE_AUTHORIZED=1 \
    sbatch scripts/slurm/campaign-rotational-augmentation.slurm
```

Without `PHASEVI_LONG_QUEUE_AUTHORIZED=1` the script prints the prepared-only
error and exits **5**. Nothing in this package submits the array.

### Association submit-limit caveat (verified 2026-09-24)

The `leahk/eduardo.donestevez@sequana_cpu` association has
`MaxSubmitJobs=24` and the limit counts **each array task**. With 15 jobs
already queued on the association, `sbatch --test-only` of the full
`--array=0-20` fails with `AssocMaxSubmitJobLimit`; the same test passes for
`--array=0-8` (9 tasks) and fails again at `--array=0-9` (10 tasks), i.e. only
9 free slots at the time of writing. **Before launch the association must have
at most 3 other queued jobs** (24 − 21), or the array must be split into chunks
(e.g. the 15 coarse tasks, then the 6 fine tasks). The array definition itself
is accepted by Slurm: `sbatch --test-only --array=0 …` reports *"using 48
processors on nodes sdumont6141 in partition sequana_cpu"* and creates no job.

## Acceptance criteria

Comparison is against the committed Sequence H measurements with the harness
bands **power / torque / thrust ±15 %** (`scripts/comparePhaseVI.py`). Compare
into a **separate `--out`** so the preserved baseline outputs are not
overwritten:

```sh
scripts/comparePhaseVI.py \
    --alm-dir runs/alm-U7-coarse \
    --asm-dir runs/asm-U7-coarse \
    --asm-mesh-dir runs/asm-mesh-U7-coarse \
    --speed 7 --sequence H --out campaign-results/U7-H
```

- **In-band curve (primary).** Candidate power/torque/thrust inside ±15 % of the
  measured Sequence H curve at the staged speeds — in particular the speeds at
  which the `aug off` baseline failed: 7 m/s (−16 %), 10 m/s (−55 %, nonphysical
  trend) and 13/15 m/s (**negative** power/torque). The proxy predicts the 7 m/s
  deficit closes to ≈ +1.8 % with `root off`; whether the high-speed sign flips
  under augmentation is the open question the campaign settles.
- **Trend and stall onset.** 10/13/15/25 m/s are URANS deep-stall points: the
  accepted claim is trend and stall onset within the bands, not sub-5 %
  agreement (`README.md` "Modelling limitations").
- **Three-way model form.** `asm-mesh` is compared against `alm`/`asm` of the
  *same arm* to test the model form (distribution difference), not resolved
  chordwise physics (sub-grid caveat, `README.md`).

## Baseline it compares against

- The **ALM/ASM `aug off` Stage 1+2 converged runs (2026-09-21)**, preserved as
  aggregated outputs under `results/U{7,10,13,15}-*-H/` and summarised in
  `results/DIAGNOSIS-2026-09-21.md`. The completed run directories were deleted;
  the comparison outputs are the baseline.
- There is **no 25 m/s baseline output** and **no ASM-MESH `aug off` baseline**
  (the candidate is the ASM-MESH arm being launched). For those, the campaign
  is trend/model-form evidence, not a baseline delta.

## Why the D/48 spot-check is with the NEW physics

The 2026-09-21 **mesh-insensitivity** result (D/32 vs D/48 within 1 % at 7 m/s,
`results/DIAGNOSIS-2026-09-21.md`) was measured with the augmentation **off**
and the Glauert root effect **on** — i.e. it predates the candidate physics.
Neither the Du–Selig stall-delay correction nor the `rootEffects off` ablation
has a mesh-sensitivity result, and the mesh-backed surface is sub-grid by
construction (cells 0.314/0.210 m vs chord 0.218–0.744 m). The spot-check at
7 m/s (attached-flow headline) and 13 m/s (deep-stall collapse) therefore tests
that the new physics is not mesh-dependent; it is a convergence check, not a
re-derivation of the old result. The full curve stays on D/32 (affordable) and
the D/48 pair is a bounded spot-check, not a second full ladder.

## Runner interface

This campaign relies on the runner's `--root-effects on|off` render-time
ablation, added alongside the existing `--rotational-augmentation on|off`:
the flag overrides `actuator.end_effects.root` for the render, and when absent
the YAML value governs (matching the augmentation flag contract). The rest of
the runner interface is documented in `README.md`.

## Verification performed while preparing (no job submitted)

| Check | Result |
|---|---|
| `bash -n scripts/slurm/campaign-rotational-augmentation.slurm` | exit 0 |
| Gate without `PHASEVI_LONG_QUEUE_AUTHORIZED` | exit 5, prepared-only message |
| `sbatch --test-only --array=0 <script>` | job `11601042` → 48 processors, `sequana_cpu`; `squeue -j 11601042` → *Invalid job id* (no job created) |
| Full `--array=0-20` `--test-only` | `AssocMaxSubmitJobLimit` (association submit limit; see caveat above) |
| `case_config.py --select` for all 21 combinations | all accepted |
| `generate_case.py --check` | exit 0 (unchanged) |
| Runner `--root-effects` contract test | `pytest -k runner_lets_yaml or root_effect_ablation` → 2 passed |
