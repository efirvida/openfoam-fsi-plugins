# Apply Progress — `phase-vi-validation`

- Project: `of-plugins`
- Artifact store: hybrid (Engram tools unavailable to the executor in this runtime → this file is the authoritative progress artifact)
- Batch: A — Phase 1 (tasks 1.1–1.5) + Phase 2 (tasks 2.1–2.4)
- Mode: Standard (no automated test suite / strict TDD not active; validation is command-driven)
- Date: 2026-09-19
- Branch: `feat/phase-vi-validation`

## Reconciliation with the dispatch brief

The brief said "no new commits yet" and "17 checkboxes, all pending". The
actual workspace was further along:

- Commits `472c8ae` (case generator) and `223099b` (data + provenance) already
  existed on the branch, and tasks 1.1–2.4 were already ticked.
- The untracked drafts listed in the brief were (mostly) those two commits'
  content; the real untracked leftovers were Phase 3–5 drafts (`runPhaseVI.sh`,
  `mesh.sh`, `stage0.sh`, `check_environment.sh`, `comparePhaseVI.py`,
  `slurm/`), which this batch leaves untouched.
- Additional uncommitted hunks existed in `tools/case_config.py` (Sequence S
  validation, `--target-cells`, `--stage`) and `tools/generate_case.py`
  (`--sequence`), plus executable bits on the three `scripts/*.py`. They were
  inspected, exercised, and committed as part of this batch.

## Completed tasks (ticks already present in `tasks.md`; verified this batch)

| Task | Outcome | Evidence |
|---|---|---|
| 1.1 `config/case.yaml` | F4 `rotor_speed_rpm` per speed; F2 20D×8D×5D free box + 15D×6D×6D fallback; frozen TSR 5.408/3.798/2.920/2.530/1.898/1.521; Sequence H + S rows | config read; `--domain squat` render 150.87/60.348/60.348 m = 15/6/6D (18 blocks) |
| 1.2 `tools/case_config.py`, `tools/element_data.py`, `scripts/makeElementData.py` | YAML validation; Ω/T_rev/Δt derivation; `ΩRΔt < Δ_hub` assert (0.3028–0.3042 m < 0.314156 m coarse); 0.03 s rejected; TSR ±0.002; 26 elementData rows with `-(twist+pitch)`; hub 1.0166 m | inline assertions run; `makeElementData.py` prints 26 stations, hub 1.0166 m (displayed 1.017 at 4 s.f.) |
| 1.3 `tools/generate_case.py` | 18-block hex blockMeshDict (coarse/fine/ultra + squat fallback), BCs, pimpleFoam/kOmegaSST `adjustTimeStep off`, decomposeParDict 48/scotch, topoSetDict T1 box; cell counts 6,674,304 / 22,525,776 / 53,394,432 (D/64 corrected from the spec's ≈40 M, per design §5 and the case.yaml comment) | `--check` 0; 18 hex blocks both domains; prior `runs/mesh-coarse|fine/log.checkMesh` = "Mesh OK", hex-only, non-orthogonality 0; smoke pimpleFoam (below) |
| 1.4 fvOptions twins | `diff case/system/fvOptions.ALM case/system/fvOptions.ASM` reports only `elementType` + `nChordwise 5` | exact diff (2 hunks, 3 lines) |
| 1.5 non-destructive `--check`, committed case, gitignore | stale/missing exit 1 with no writes; all 15 generated files committed; `.gitignore` covers meshes/`processor*`/`runs/`/logs | hand-edited copy: exit 1, file hash unchanged; missing-file: exit 1; `git check-ignore` confirms |
| 2.1 geometry + provenance | 25 report rows byte-exact vs TP-500-29955 Table A-1 (page 74), 5.029 m tip interpolated from the report stations (rounding 4e-4°); committed sha256 `e678d6c5…` = PROVENANCE = SAL scaffold copy | pypdf parse of `29955_nlr.pdf` p.74 |
| 2.2 polars | raw A-3..A-8 + TP-442-7817 committed; baseline matches all 29 A-7 rows exactly (Cdw→Cdp fallback); multiRe has `tableType multiRe` + 4 Re levels; scaffold `S809_Re1M_extended` referenced only as "not used" | `buildPolars.py --check` 0; 59-row monotonic baseline; 136/136 TP-442 rows found in report text |
| 2.3 experimental extraction | `ldsmean`, 0° yaw, canonical rows `h0700000…h2500000`/`s0700000`, 20 m/s = `h20m0000`; anchors exact 5.9458 kW/789.8572 Nm/1132.0692 N and 11.9507 kW/1580.4082 Nm/4028.6306 N; TSR within ±0.002 of all configured values | `extractExperimentalData.py --check` 0 (re-read the 17 MB workbook); row map matches PROVENANCE sheet rows 1204/1239/1272/1284/1328/1342/1843 |
| 2.4 provenance | DOI/URL + source sha256 (all three verified against the local copies), table/sheet, rows, units, extraction date; SAL `8284be8c…` credit; pinned `52fd258…` + ASM note; no PDF/XLS tracked | sha256sum matches; `git ls-files`/history grep finds no PDF/XLS |

## Defect found and fixed (Phase 1)

`render_field_uniform` emitted far-field patches as a nested
`U { type symmetryPlane; }` dictionary (no direct `type`), and the `U` inlet as
`value uniform (7 0 0)` with neither a `type` nor a terminating semicolon.
`pimpleFoam` reads the patch type with `get<word>("type")` (v2506
`fvPatchFieldNew.C:103`), so it aborts at field construction; `checkMesh`
never reads `0.org`, which is why the earlier mesh passes missed it.
Fixed in `747c171` (renderer + regenerated `0.org/{U,p,k,omega,nut}`).

## Verification evidence (final HEAD `16ff6ab`)

| Command | Result |
|---|---|
| `python3 tools/generate_case.py --check` | exit 0 |
| fresh render into a same-depth sibling, diff all 15 files | identical |
| stale copy (hand-edited `controlDict`) `--check` | exit 1, file unchanged (non-destructive) |
| missing-file copy `--check` | exit 1 |
| `diff case/system/fvOptions.ALM case/system/fvOptions.ASM` | only `elementType`/`nChordwise 5` |
| `python3 scripts/buildPolars.py --check` | exit 0 |
| `python3 scripts/extractExperimentalData.py --workbook wt_loads_statistics.xls --check` | exit 0 |
| `python3 scripts/makeElementData.py` | 26 stations 0.5083→5.029 m, hub 1.0166 m, 0 mismatches vs `-(twist+pitch)` |
| TSR / anchors assertion | PASS |
| `pimpleFoam` smoke (105 k cells, ALM then ASM, 2 steps) | exit 0 both; TSR 5.408; End; `libturbinesFoam.so` loaded |
| prior `checkMesh` D/32 + D/48 (gitignored `runs/` logs) | "Mesh OK", 6,674,304 / 22,525,776 hex cells, 6 patches |

## Commits created this batch

| Hash | Message |
|---|---|
| `567b16f` | `feat(validation): add Sequence S and stage introspection to case config` |
| `747c171` | `fix(validation): render valid boundary fields for the Phase VI case` |
| `16ff6ab` | `chore(validation): make Phase VI data scripts executable` |

Pre-existing, verified only: `472c8ae`, `223099b` (both after `52fd258`).
No push, no amend, no stash operations.

## Notes / deviations

- Design says the per-speed tip displacement is "≤0.304 m across the whole
  7–25 m/s matrix"; the actual maximum is 0.3042 m at 25 m/s (coarse), still
  below the 0.314156 m hub-adjacent cell. Design wording nit only.
- The spec's D/64 "≈40 M" is superseded by the design's 53,394,432 correction;
  recorded in `design.md` §5 and the `case.yaml` comment (case readme is a
  Phase 4 deliverable).
- `case/constant/polyMesh` and `case/log.*` exist locally from prior mesh runs
  but are gitignored and not committed.
- Phase 3–5 drafts remain untracked and untouched: `scripts/runPhaseVI.sh`,
  `mesh.sh`, `stage0.sh`, `check_environment.sh`, `comparePhaseVI.py`,
  `scripts/slurm/`. `openspec/`, `odd/`, `.atl/` and the repo-root PDF stay
  uncommitted per instructions.

## Batch B — Phase 3 + Phase 4 (tasks 3.1–3.5, 4.1–4.2)

- Date: 2026-09-19. Scope: run/compare tooling, stage plan, tests, docs. Phase 5
  (task 5.1, Stage 0 execution) was explicitly out of scope; no job was
  submitted and no long-queue work ran.
- The Phase 3–4 files written by the interrupted previous attempt were
  inspected, not rewritten. Three defects were found and fixed (below), one
  design testing layer was added, then everything was verified and committed.

### Defects found and fixed

1. **fvOption name vs `turbine.csv` contract (integration).** The rendered
   `fvOptions` entry and topoSet cellSet were named `T1`; turbinesFoam names
   the turbine-level CSV after the fvOption entry (`turbineALSource.C`
   `createOutputFile` → `dir/name_ + ".csv"`), so runs produced
   `postProcessing/turbines/0/T1.csv` while `comparePhaseVI.py` (and design
   §8/§9, task 3.4) requires `turbine.csv`. The comparison exited 1 on its own
   runner's output (reproduced on the prior smoke run). Fixed in
   `tools/generate_case.py` (entry + cellSet renamed `turbine`), the committed
   `case/system/{fvOptions.ALM,fvOptions.ASM,topoSetDict}` regenerated, and
   `--check` kept green. Runtime proof: a fresh 3-step smoke run in
   `$SCRATCH/tmp/phasevi-smoke` produced `postProcessing/turbines/0/turbine.csv`
   and element files `turbine.blade1.elementN.csv`, and `comparePhaseVI.py`
   parsed them (exit 0).
2. **Restart detection missed fractional written times.** `runPhaseVI.sh
   --restart` tested `"$run_dir"/[1-9]*`, which does not match time directories
   below 1 s (`writeInterval = 0.5·T_rev` ≈ 0.417 s), so an early-interrupted
   run could silently restart from scratch instead of `latestTime` (spec:
   "Interrupted run continues"). Replaced with a numeric
   `find -maxdepth 2 -name '[0-9]*' | awk '$NF+0>0'` detection; verified both
   ways (0.417 present → `startFrom latestTime`; absent → warning +
   `startFrom startTime`).
3. **README environment block incomplete.** The setup block omitted
   `. "$WM_PROJECT_DIR/etc/bashrc"`; on the SDumont `openfoam/v2506_*` module
   the identity exports alone leave the dead Int32 path, so `blockMesh` et al.
   are not on PATH and `check_environment.sh` exits 3. Added the source line
   (matching `slurm/*.slurm`) and corrected the `--rho auto|<kg/m³>` wording.

### Test layer added

Design §12 ("Tooling") had no coverage: added
`turbinesFoam/tests/test_phasevi_compare.py` (6 tests, pure Python, fixtures
generated under `tmp_path` — no fixture committed, no fabricated results) for
the F1 formulas, `root_dist`→r/R mapping and interpolation, the drift flag,
the fail-loud exit codes and the sign gate. Full suite is 28 tests.

### Verification evidence (this batch)

| Command | Result |
|---|---|
| `cd turbinesFoam && python3 -m pytest tests/ -q` (no OpenFOAM) | 28 passed |
| `python3 tools/generate_case.py --check` | exit 0 |
| `bash -n` on 4 `.sh` + 2 `.slurm` | all OK |
| `runPhaseVI.sh --help` | exit 0 |
| unsupported model/mesh/domain/sequence/speed/arg | all exit 2 |
| valid input without OpenFOAM | exit 3 (environment) |
| stale case copy (hand-edited `controlDict`) via `check_environment.sh` / `runPhaseVI.sh` | exit 4 both |
| production `--submit` unauthorized | exit 5 |
| production `--submit` authorized, no gate file / FAIL gate | exit 5 both |
| production `--submit` authorized + PASS gate + fake `sbatch` on PATH | proceeds to fake submission (exit 0); real submission never invoked; gate file deleted afterwards |
| fractional-time `--restart` render | `startFrom latestTime`; without it warning + `startFrom startTime` |
| `comparePhaseVI.py` missing run dir / missing experiment / short window / TSR mismatch | exit 1 / 1 / 2 / 3 |
| `--allow-short-window` override | exit 0 |
| mirrored-sign synthetic run `--sign-gate` | exit 1, `sign_gate.json` pass=false |
| real 3-step smoke output consumed (`turbine.csv`, 19-column element CSVs) | exit 0; definitions/rho/bands/limitations in `metrics.json` |
| F1 definitions | `Q = ct·q_dyn·R`, `R = rotorRadius`, `P = cp·q_dyn·Uinf`, `cp = ct·TSR`, `T_blade` headline / `T_rotor` secondary, ρ from WTBARO/WTATEMP (docstring, `metrics.json`, `report.txt`, README) |
| `check_environment.sh` with v2506 (identity + `etc/bashrc`) | exit 0 "Environment OK: OpenFOAM v2506" |
| `check_environment.sh` with `WM_PROJECT_VERSION=v2412` | version check passes; later tool lookup fails only because v2412 is not installed here |
| prior `runs/mesh-{coarse,fine}/log.checkMesh` | "Mesh OK", 6,674,304 / 22,525,776 hex, non-orthogonality 0 (heavy meshing not re-run on the login node) |
| `diff case/system/fvOptions.ALM case/system/fvOptions.ASM` | only `elementType` + `nChordwise 5` |
| stage introspection `--stage stage0..3` | S0 executes (dev queue, ≤0.3 rev, 7 m/s, D/32+D/48); S1/S2/S3 prepared, 20 m/s not staged |

### Commits created this batch

| Hash | Message |
|---|---|
| `d5088b4` | `fix(validation): align the Phase VI turbine fvOption name with the comparison contract` |
| `afaebbd` | `feat(validation): add Phase VI run, mesh, stage and comparison tooling` |
| `786f0f1` | `test(validation): add Phase VI case, data and tooling sanity tests` |
| `9e80a16` | `docs(validation): document the Phase VI validation package` |

### Deviations from design

- Design §4 names the fvOptions entry/cellSet `T1`; the interface contract in
  §8/§9 requires `turbine.csv`, so the entry and cellSet are now `turbine`.
  No spec requirement pinned `T1`.
- Design §12's tooling tests are covered by a third test module
  (`test_phasevi_compare.py`), beyond the two modules named in task 4.1.

## Batch C — Phase 5 (task 5.1, Stage 0 execution)

- Date: 2026-09-19. Scope: fix the Stage 0 Slurm wrapper, execute Stage 0 on
  `sequana_cpu_dev`, verify the mesh and stability outcomes. No long-queue
  submission; Stages 1–3 remain prepared-only.

### Defects found and fixed

1. **Spooled-script path (job `11597161`, exit 127).** Slurm executes a copy
   of the batch script from `/var/spool/slurmd/<job>/`, so `BASH_SOURCE[0]`
   resolved outside the repository and the job looked for
   `/var/spool/slurmd/stage0.sh`. `scripts/slurm/stage0.slurm` now resolves
   the package from `$SLURM_SUBMIT_DIR` (`PHASEVI_PKG_DIR` overrides), fails
   with a clear message when the driver is missing, and forwards extra
   arguments to `stage0.sh`. Verified with a stub package (args
   `--execute --mesh-only` forwarded) and a missing-package run (exit 3).
   `scripts/stage0.sh --submit` now `cd`s to the package root so
   `$SLURM_SUBMIT_DIR` is always the package directory.
2. **Existing meshes lacked the `turbine` cellSet.** The reuse path in
   `mesh.sh` (commit `24b1fa6`) refreshes `topoSet` when the rendered
   `topoSetDict` is newer than the log; the queue run re-rendered the dict and
   created `cellSet turbine` for both meshes. Added `--runs-only` to
   `stage0.sh`, which refuses to start unless the coarse mesh has
   `log.checkMesh` "Mesh OK" and `constant/polyMesh/sets/turbine` — the guard
   was reproduced failing before the mesh refresh (exit 3).
3. **The 20 min / 1-submission queue limit forces a split.** The
   `sequana_cpu_dev` association is `MaxJobs=1 / MaxSubmit=1 /
   MaxWall=00:20:00`, so Stage 0 ran as two serial jobs: `--mesh-only`, then
   `--runs-only`. Both completed (below).
4. **`run.json` records `git_commit: "unknown"` inside jobs.**
   `runPhaseVI.sh` shells out to `git -C <package> rev-parse HEAD`; the call
   works in the login environment but fails in the batch environment (stderr
   is discarded). Not a Stage 0 acceptance item; noted for a follow-up
   (read `.git/HEAD` fallback, or surface the git error).

### Jobs

| Job | Step | State | Exit | Elapsed |
|---|---|---|---|---|
| `11597164` | `stage0.slurm --mesh-only` | COMPLETED | 0:0 | 5:39 |
| `11597169` | `stage0.slurm --runs-only` | COMPLETED | 0:0 | 10:06 |

Earlier failed attempts: `11597160` (exit 1, `WM_PROJECT_SITE` unbound while
sourcing `etc/bashrc` under `set -eu`; fixed in `28de14e` before this batch),
`11597161` (exit 127, spooled-script path; fixed in `d5bb7bc`).

### Verification evidence

- D/32 (`runs/mesh-coarse/log.checkMesh`): "Mesh OK", 6,674,304 cells, 100 %
  hexahedra, max non-orthogonality 0; `topoSet` "Created cellSet turbine"
  (106,496 cells).
- D/48 (`runs/mesh-fine/log.checkMesh`): "Mesh OK", 22,525,776 cells, 100 %
  hexahedra, max non-orthogonality 0; `cellSet turbine` (359,424 cells).
- ALM 7 m/s D/32 (`runs/alm-U7-coarse-s0/log.pimpleFoam`): 26 steps to
  `Time = 0.208` s = 0.25 rev (stage0 `--end-revs 0.25`, spec bound 0.3),
  "End"; max Courant 0.201; 0 NaN/Inf tokens, 0 bounding lines, no fatal;
  continuity max sum local 2.8e-9 / global 4.9e-11; azimuth 3.45°→89.71°;
  last load: blade1 (431.64, 0.96, −87.38), hub (28.30, ~0, ~0); cp 0.3100
  (range 0.14–0.31), rotor c_d 0.4580.
- ASM 7 m/s D/32 (`runs/asm-U7-coarse-s0/log.pimpleFoam`): same shape, 26
  steps to 0.208, "End"; max Courant 0.200; 0 NaN/Inf/bounding/fatal;
  continuity max sum local 2.5e-9 / global 4.0e-11; last load blade1
  (431.23, 0.96, −87.22), hub (28.29, ~0, ~0); cp 0.3092, rotor c_d 0.4576.
- Both `run.json`: `stage0: true`, `wind_speed_m_s: 7.0`; endTime
  0.20867325 s, deltaT 0.008 s.
- `%j.err` files contain only the module banner; both `%j.out` end with
  "Stage 0 job finished".

### Commits created this batch

| Hash | Message |
|---|---|
| `d5bb7bc` | `fix(validation): resolve the Stage 0 package from the Slurm submit dir` |

### Deviations from design

- Stage 0 was split into a mesh job and a stability job (the design assumed a
  single job); the association allows one submitted job of at most 20 min.
  The payload is unchanged.
- The stability runs stop at the configured 0.25 rev (`--end-revs 0.25`),
  below the spec's ≤0.3 rev bound; the 5.1 acceptance is the configured bound.

## Remaining tasks

- None in `tasks.md`: task 5.1 is ticked, all 21 tasks complete. Next SDD
  phase is verify.

## Workload / PR boundary (cumulative)

- Mode: chained PR slices; batch A = config+generator+data (through
  `16ff6ab`), batch B = Phase 3+4 tooling/tests/docs (through `9e80a16`),
  batch C = Stage 0 wrapper fix (`d5bb7bc`) plus queue execution evidence.
- Batch B boundary: starts at `16ff6ab`, does not include any Stage 0
  execution or long-queue submission.
- Batch C boundary: the only tracked change is `d5bb7bc`
  (`scripts/slurm/stage0.slurm`, `scripts/stage0.sh`, package `.gitignore`,
  97 insertions / 24 deletions); job logs and `runs/` stay ignored, and no
  long-queue work was submitted.

