# Verify Report: blade-actuator-surface (S2)

Change: `blade-actuator-surface` — slice S2 of the staged program
(S1 = `nacelle-actuator-surface`, archived 2026-09-20; S3 = preCICE FSI,
deferred). Reference: Yang & Sotiropoulos, arXiv:1702.02108v4.

**Status: partial** — the implementation matches the eight delta specs and the
engineering checks pass, but one test fails inside the required Slurm execution
environment (a test-harness robustness gap, not a production defect). No
scientific validation run was executed (prepared-only by design).

TDD mode: Standard (`strict_tdd: false`). No RED/GREEN ritual is assessed; tests
are required and are present.

---

## Scope

Artifacts inspected (all read-only):

- `openspec/changes/blade-actuator-surface/{proposal,design,tasks,apply-progress}.md`
- the eight delta specs under `specs/` (`blade-surface-source`,
  `blade-geometry-generation`, `surface-sampling-contract`,
  `element-type-selection`, `phasevi-validation-case`,
  `phasevi-run-and-compare`, `phasevi-data-provenance`,
  `turbine-geometry-pipeline`)
- the implementation: commits `5d1acad`..`fc136b4` over base `d4496ae`
  (82 files, +11273/−754), `turbinesFoam/src/fvOptions/bladeSurface/**`,
  `surfaceSamplerBase.*`, `actuatorLineSource`/`actuatorLineElement`/AFTAL,
  `turbinesFoam/geometry/**`, `turbinesFoam/validation/phaseVI/**`, tests.

Execution environment:

- Heavy checks ran on the `sequana_cpu_dev` partition via `sbatch`
  (user-authorized for builds, solver-driven tests and the full pytest suite).
  Job **11599975** on `sdumont6037`, log
  `/scratch/leahk/eduardo.donestevez/tmp/verify-slurm/verify_11599975.log`.
  The Slurm script is not a repo artifact.
- Trivial pure-Python checks ran inline on the login node
  (`/scratch/leahk/eduardo.donestevez/venv/bin/python`, OpenFOAM v2506 module
  for the tooling invocations).

No implementation, test, spec, proposal, design, tasks or apply-progress file
was modified. The only write is this report.

---

## Observed progress

All W1→W4 tasks are marked complete in `tasks.md`; W4.4 is correctly left open
and conditional ("Conditional — NOT triggered", `tasks.md:343`). This matches
the apply-progress record and the implementation. Checkboxes were not altered.

| Unit | State (as recorded) | Verification note |
|------|---------------------|-------------------|
| W1 distributor C++ | complete | build + link + `test_blade_surface.py` green |
| W2 blade geometry | complete | `--check` byte-identical, `test_blade_data.py` green |
| W3 ASM-mesh variant | complete | twin/staging/compare green (one harness failure) |
| W4 instrumentation | complete (W4.4 conditional, not triggered) | `test_instrumentation_line` green |

---

## Checks — commands and observed results

### Slurm job 11599975 (`sequana_cpu_dev`, 4 tasks, 1 node)

Script: `$SCRATCH/tmp/verify-slurm/run_checks.slurm` (not committed). It loads
`openfoam/v2506_openmpi-4.1.4_gnu`, sets the Int64 identity
(`WM_OPTIONS=linux64GccDPInt64Opt`), sources `etc/bashrc` with `set +eu`, sets
`FOAM_USER_LIBBIN`/`LD_LIBRARY_PATH` as the package Slurm scripts do, then runs
the build, `ldd -r`, the full suite and the focused files, teeing to the log.

| Check | Command | Observed | Exit |
|-------|---------|----------|------|
| Build | `./Allwmake` | `wmake libso src` | `ALLWMAKE_EXIT=0` |
| Link | `ldd -r $FOAM_USER_LIBBIN/libturbinesFoam.so` | no `undefined`/`not found` lines; gcc-14 retry not needed | `LDD_EXIT=0` |
| Full suite | `pytest -q` | `1 failed, 123 passed, 1 warning in 488.39s (0:08:08)` | `FULL_SUITE_EXIT=1` |
| Focused files | `pytest -q tests/test_blade_surface.py test_blade_data.py test_blade_stage.py test_phasevi_case.py test_phasevi_compare.py test_phasevi_data.py test_nacelle.py` | `1 failed, 65 passed in 40.50s` | `FOCUSED_EXIT=1` |

The single failure in both runs is
`tests/test_phasevi_case.py::test_asm_mesh_selection`:

```
AssertionError: ERROR: --ranks 48 does not match SLURM_NTASKS=4.
  Re-run with --ranks 4 or fix the allocation.
```

`mpirun -np 2` inside the allocation worked: `test_parallel_total_preserved`
(`test_blade_surface.py`) and the nacelle parallel test both passed.

### Inline pure-Python checks (login node)

| Check | Command | Observed | Exit |
|-------|---------|----------|------|
| Blade geometry check, no gmsh | `env PATH=/usr/bin:/bin python src/makeGeometry.py --check --component phaseVI_blade` | `phaseVI_blade: committed STL, metadata and PROVENANCE.md are up to date`; `input sha256: 7a43047d…` | 0 |
| Blade check ignores `--gmsh` | `… --check --component phaseVI_blade --gmsh /nonexistent/gmsh` | same clean result | 0 |
| Nacelle check, pinned gmsh | `module load glu/9.0.2_gnu`; `… --check --component nacelle --gmsh …/venv/bin/gmsh` | `nacelle: … up to date`; `input sha256: e0a69771…` | 0 |
| Retired name | `… --component blade0` | `error: component 'blade0' was retired in S2; … 'phaseVI_blade' (available: nacelle, phaseVI_blade)` | 1 |
| Unknown name | `… --component bogus` | `error: unknown component 'bogus' (available: nacelle, phaseVI_blade)` | 2 |
| Case render check | `python validation/phaseVI/tools/generate_case.py --check` | no output (clean) | 0 |
| Model select | `python …/case_config.py --select 7 coarse asm-mesh` | kinematics JSON, `"model": "asm-mesh"`, `tsr 5.408` | 0 |
| Bogus select | `… --select 7 coarse bogus` | `unsupported model 'bogus'; choose from ['alm', 'asm', 'asm-mesh']` | 2 |
| Prepare-only run | `sh scripts/runPhaseVI.sh -m asm-mesh -u 7 -mesh coarse` | `Installed fvOptions.ASM-MESH as system/fvOptions`; `Staged blade STL sha256 77def499…`; `Wrote run.json`; no `--run`/`--submit` | 0 |
| Submit refusal | `sh scripts/runPhaseVI.sh -m asm-mesh -u 7 -mesh coarse --submit` | `ERROR: --submit is not available for -m asm-mesh; … asm-mesh.slurm …` | 2 |
| ASM-family guard | `sh scripts/runPhaseVI.sh -m alm -u 7 -mesh coarse --nchordwise 3` | `ERROR: --nchordwise is ASM-family-only` | 2 |
| Array guard | `bash scripts/slurm/asm-mesh.slurm` (no env) | `ERROR: long-queue authorization not granted; this file is prepared only.` | 5 |
| Array syntax/resources | `sbatch --test-only scripts/slurm/asm-mesh.slurm` | `Job 11599976 to start … using 48 processors … partition sequana_cpu`; no job created (`squeue` has no ASM-mesh entry) | 0 |
| Pure-Python focused set, no `SLURM_NTASKS` | `env -u SLURM_NTASKS pytest -q tests/test_phasevi_case.py tests/test_phasevi_compare.py tests/test_phasevi_data.py tests/test_blade_data.py tests/test_blade_stage.py` | `48 passed in 8.04s` | 0 |
| Reproduce harness failure | `SLURM_NTASKS=4 pytest -q tests/test_phasevi_case.py::test_asm_mesh_selection` | `1 failed in 1.58s` (same `--ranks 48 does not match SLURM_NTASKS=4`) | 1 |

Artifact identity (recomputed):

```
77def499047fe0633e57564247a0fdd1330afbf4148b707db08ec79af0a2ec27  geometry/stl/phaseVI_blade.stl
01f75d17e2febb296a7b093f20ff011eb583de52e8f510815f876fcb8169e7dc  geometry/metadata/phaseVI_blade.json
861f3fe5bbda4d5e5d8985e47c5805bada76fc8e1b2157b944ff78d500f4af8b  validation/phaseVI/data/s809/s809_somers_nlr.csv
```

All three match the constants pinned in `tests/test_blade_data.py` (lines 65-69).
The staged STL in `runs/asm-mesh-U7-coarse/constant/triSurface/phaseVI_blade.stl`
is `cmp`-identical to the committed STL; `run.json` records the same
`staged_stl_sha256`. `system/fvOptions` in the run dir differs from the committed
twin only in the case-relative polars `#include` path.

---

## Per-capability coverage

Evidence is `file:line`, test name and observed output. "Verified" means a check
was executed in this session or a passing test exercises it.

### `blade-surface-source` (ADDED)

| Requirement | Evidence | Verdict |
|---|---|---|
| Additive surface activation | `actuatorLineSource.C:211-212,577-582`; key injected only with surface (`:369-376`). `test_default_path_projects_strips` passed. | Verified |
| Exactly-once force application | Guard at `actuatorLineElement.C:1109` / `:1154`; `test_serial_surface`, `test_suppressed_element_still_reports` passed. | Verified |
| Imported triangulation + node metadata | `surfaceSamplerBase.C:135-148` fatal on missing/empty STL; `test_missing_empty_corrupt_stl_aborts`, `test_partition_invariants_from_csv` passed. | Verified |
| Element-force-to-patch mapping | `bladeSurfaceSampler.C:90` (`buildPartition`) with fatal invariants; `test_partition_invariants_from_csv` passed. | Verified |
| Distribution-only model | No `interpolateVelocity` call on the blade path; element CSV/`force()` stay valid (`test_suppressed_element_still_reports`). | Verified |
| Selectable kernel and width | `kernel cosine` default / `gaussian`; `test_kernel_gaussian_conserves` passed. | Verified |
| Rotating-frame lockstep + restart | `actuatorLineSource.C:620-653` forwards rotate/pitch; `test_rotation_lockstep` passed; no surface state in the restart path (static). | Verified |
| Blade moment includes surface | `moment()` returns surface node moment when active; `test_surface_moment_in_torque` passed. | Verified |
| Surface CSV output | `test_station_and_node_csv` passed; writer schema pinned by `test_surface_csv_schema_matches_writer`; conversion by `test_main_three_way_surface_merge`. | Verified |
| MPI correctness | `test_parallel_total_preserved` passed (`mpirun -np 2`); `reduce(minOp)` sentinel at `surfaceSamplerBase.C:187`. | Verified |
| Bounded distribution + measurement | Bin-grid candidate query (`bladeSurfaceSampler.C:211`); instrumentation at `bladeSurfaceSource.C:336-363`; `test_instrumentation_line` passed. D/32 measurement prepared-only (W4.3). | Verified (measurement not executed) |
| Sampling contract on rotating frame | `bladeSurfaceSampler` accessors in body frame; SI; no adapter/`fsiOmega` dependency (diff empty). | Verified |

### `blade-geometry-generation` (ADDED)

| Requirement | Evidence | Verdict |
|---|---|---|
| S809 coordinates + provenance | `data/s809/PROVENANCE.md` + CSV; `test_s809_provenance_complete`, `test_s809_parses_as_airfoil` passed. | Verified |
| Pure-Python loft, full wetted span | `geometry/src/blade_phasevi.py`; `test_stl_manifold_wetted_only` passed (3000 triangles, two 60-edge boundary rings at 0.5083/5.029). | Verified |
| Deterministic byte-identical regeneration | `--check --component phaseVI_blade` exit 0; `test_check_byte_identical_without_gmsh` passed. | Verified |
| Canonical STL + station/chord metadata | `test_blade_metadata_complete` passed (no `_reserved`, populated fields). | Verified |
| Component registration + naming policy | Inline CLI: `phaseVI_blade` accepted, `blade0` retired (exit 1), unknown rejected (exit 2); `test_builder_registry_and_retired_reservation` passed. | Verified |
| Blade component documentation | `geometry/README.md`, `geometry/PROVENANCE.md` (inspected). | Verified (static) |
| Pure-Python blade data tests | `test_blade_data.py` (6 tests) passed without OpenFOAM. | Verified |

### `surface-sampling-contract` (1 ADDED, 3 MODIFIED)

| Requirement | Evidence | Verdict |
|---|---|---|
| Shared base, S1 regression-gated | `surfaceSamplerBase.*` extracted; `test_nacelle.py` passed in the job. Byte-identical nacelle CSVs are recorded in apply-progress (W1.2 `cmp`), not re-run here. | Verified (byte-cmp from apply-progress) |
| Body frame (MODIFIED) | Blade body frame rotates; `test_rotation_lockstep` passed. | Verified |
| Stable node ordering (MODIFIED) | Fixed at init; tests pass. | Verified |
| Seam only — no adapter/`fsiOmega` | `git diff d4496ae..HEAD -- precice-openfoam-adapter fsiOmega` empty. | Verified |

### `element-type-selection` (2 MODIFIED, 1 ADDED)

| Requirement | Evidence | Verdict |
|---|---|---|
| Config key plumbing | `actuatorLineSource.C:207-212,365-376`; `test_default_path_projects_strips`, `test_suppressed_element_still_reports` passed. | Verified |
| Default actuator line behavior preserved | Key absent → `true`; `test_default_path_projects_strips` passed. | Verified |
| Strip-projection suppression control | Guard only the `applyForceField` calls; `test_suppressed_element_still_reports` passed. | Verified |

### `phasevi-validation-case` (2 MODIFIED)

| Requirement | Evidence | Verdict |
|---|---|---|
| Three twins differ only in blade keys | Inline `diff fvOptions.ASM fvOptions.ASM-MESH` = one `surfaceGeometry` line; `test_twins_differ_only_in_blade_keys` passed. | Verified |
| Model selection accepted | Inline `--select 7 coarse asm-mesh` exit 0; bogus exit 2; `test_asm_mesh_selection` (see finding). | Verified without Slurm env; fails inside it |
| Renderer check clean | `generate_case.py --check` exit 0. | Verified |
| Case package documentation | `validation/phaseVI/README.md`, root `README.md`, `CHANGELOG.md` (entries 14/15/16) inspected. | Verified (static) |

### `phasevi-run-and-compare` (5 MODIFIED, 1 ADDED)

| Requirement | Evidence | Verdict |
|---|---|---|
| Run orchestration interface | Prepare-only exit 0, run id `asm-mesh-U7-coarse`, `--submit` exit 2, `--nchordwise` ASM-family-only. | Verified |
| Comparison inputs and merge | `test_phasevi_compare.py` (9 tests) passed, including the three-way merge and missing-input exit. | Verified |
| Long-queue authorization gate | `asm-mesh.slurm` guard exit 5; no ASM-mesh job in `squeue`; baselines not submitted/cancelled/modified. | Verified |
| Slurm job preparation | `--test-only` exit 0; `--time=24:00:00`; 2 array tasks. | Verified (static/test-only) |
| Documented bands and honest claims | `LIMITATIONS` + README (sub-grid, kernel confound/ablation, pre-registered hypothesis) inspected. | Verified (static) |
| STL staging into run dirs | Inline staged hash `77def499…` matches; `test_blade_stage.py` (7 tests) passed. | Verified |

### `phasevi-data-provenance` (1 ADDED, 4 MODIFIED)

| Requirement | Evidence | Verdict |
|---|---|---|
| Committed S809 profile coordinates | CSV + PROVENANCE present; `test_phasevi_data.py` passed. | Verified |
| Per-directory provenance records | `test_phasevi_data.py` passed (`data/s809/` included). | Verified |
| Derived artifacts only | No PDF/workbook committed (`git diff --name-status` has no `.pdf`/workbook). | Verified |
| Pure-Python data-sanity tests | Passed without OpenFOAM. | Verified |
| Source attribution and provenance pinning | README/provenance inspected (SAL credit, NREL citations, pinned commit). | Verified (static) |

### `turbine-geometry-pipeline` (6 MODIFIED, 1 ADDED, 1 REMOVED)

| Requirement | Evidence | Verdict |
|---|---|---|
| Deterministic gmsh and Python generation | Blade `--check` exit 0 (no gmsh); nacelle `--check` exit 0 (pinned gmsh). | Verified |
| Per-component STL output | One `phaseVI_blade.stl`; no `blade0/1/2`. | Verified |
| Metadata JSON | Blade populated; nacelle metadata pinned by `test_nacelle_data.py` (passed). | Verified |
| Provenance | Per-component sources/hashes inspected. | Verified |
| `--check` regenerability | Exit 0 clean; stale detection covered by `test_check_byte_identical_without_gmsh`. | Verified |
| Pure-Python CI-safe test | `test_blade_data.py` + `test_nacelle_data.py` passed. | Verified |
| Component builder registry | `BUILDERS` dispatch; CLI evidence above. | Verified |
| Blade STL accommodation (REMOVED) | Blade has no `_reserved` null mapping; registry supersedes. | Verified |

---

## Findings by severity

### WARNING — `test_asm_mesh_selection` is not robust to `SLURM_NTASKS`

- **Evidence**: full suite `1 failed, 123 passed`; focused `1 failed, 65 passed`;
  both fail at `tests/test_phasevi_case.py:313` with
  `ERROR: --ranks 48 does not match SLURM_NTASKS=4`. Reproduced inline with
  `SLURM_NTASKS=4` (`1 failed in 1.58s`); the same test passes when
  `SLURM_NTASKS` is unset (`48 passed in 8.04s`).
- **Cause**: the test builds `env = dict(os.environ)` and forwards it to the
  sandboxed `runPhaseVI.sh`, which (correctly) enforces `--ranks == SLURM_NTASKS`
  when `SLURM_NTASKS` is set. The test does not clear or override the variable.
- **Impact**: the project's own required workflow runs the suite inside a Slurm
  allocation, where this test always fails. The success criterion "full pytest
  suite passes" is not met as executed. Production behavior is unaffected: the
  runner's guard is intentional and correct, and the test passes in a normal
  login-node environment.
- **Suggested remediation (not applied — read-only verify)**: in
  `test_asm_mesh_selection`, `env.pop("SLURM_NTASKS", None)` (or pass an explicit
  matching `--ranks`). This is a test-harness fix, not a production change.

### SUGGESTION — "byte-identical ALM/no-mesh ASM" not independently re-verified

- **Evidence**: the change asserts ALM/no-mesh ASM paths are byte-identical
  (proposal Success Criteria; `element-type-selection` "Existing case
  regression"). This session verified the default path behaviorally
  (`test_default_path_projects_strips`) and the unchanged suite; the explicit
  byte-level `cmp` evidence exists only for the nacelle (apply-progress W1.2).
  No fresh ALM/ASM byte comparison was executed here.
- **Impact**: low; the default-path test and the unchanged suite are strong
  indirect evidence. Flagged for completeness.

### SUGGESTION — validation claims remain unearned (by design)

- **Evidence**: no ASM-mesh production run was executed; the D/32 measurement
  gate and the D/48 headline array are prepared-only
  (`asm-mesh.slurm`, `tasks.md` W4.3). This is the documented, intended scope.
- **Impact**: the scientific three-way comparison is not demonstrated; only the
  tooling and engineering acceptance are verified. Correctly disclosed in the
  README and the comparison `LIMITATIONS`.

No CRITICAL findings. No requirement was found unmet in the implementation.

---

## Honesty checks

| Check | Result |
|---|---|
| Additive/default paths unchanged | Default-path test passed; nacelle byte-identical evidence from apply-progress W1.2; suite green except the harness failure. ALM/ASM byte-cmp not re-run (see SUGGESTION). |
| S3 / adapter / `fsiOmega` untouched | `git diff d4496ae..HEAD -- precice-openfoam-adapter fsiOmega` empty. |
| `mexico-validation` / archive untouched | `git diff` empty. |
| No submission of validation arrays | `squeue` has no `phaseVI`/`asm-mesh` job; `--test-only` created no job; the only `sbatch` calls are inside the guarded `--submit` branches. |
| W4.4 conditional status correct | `tasks.md:341-348`, `[ ]` "Conditional — NOT triggered"; no measurement evidence exists. |
| Sub-grid caveat + kernel-confound framing | `validation/phaseVI/README.md:288-299,394-402`, root `README.md:97`; `comparePhaseVI.py` `LIMITATIONS`. |
| MEXICO naming resolution recorded | `validation/phaseVI/README.md:316-320`, `geometry/README.md:75-76`. |
| `size:exception` recorded per work unit | 28 mentions across apply-progress batches (W1a…W4). |
| Existing baseline Slurm scripts untouched | `git diff` empty for `production.slurm`, `stage3.slurm`, `stage3-d64.slurm`, `stage0.slurm`; only `asm-mesh.slurm` is added. |
| Prepared-only arrays / no PDF committed | `git diff --name-status` shows no PDF/workbook; only the ASM-mesh array is added. |

---

## Gaps and what is / is not verified

**Verified**

- Build (`./Allwmake` exit 0) and clean dynamic link (`ldd -r` exit 0).
- All eight delta specs' requirements have concrete implementation evidence and,
  except where noted, a passing test.
- Geometry determinism, provenance, registry and retirement behavior.
- Staging, model selection, twin rendering and three-way comparison tooling.
- Prepared-only array shape and guards; no submission.
- Docs honesty framing (sub-grid, kernel confound/ablation, MEXICO, hypothesis).
- Isolation: no S3/adapter/`fsiOmega`/MEXICO change.

**Not verified / unearned**

- Scientific validation of the ASM-mesh model (no production run; prepared-only
  by design).
- D/32 performance measurement gate (prepared, not executed).
- Byte-identical ALM/no-mesh ASM at the `cmp` level in this session.
- The full suite does not pass *inside a Slurm allocation* because of the
  `SLURM_NTASKS` harness gap (see WARNING).
- W4.4 candidate-query hardening is open and correctly conditional.

---

## Summary and recommendation

The implementation faithfully realizes the eight delta specs; every engineering
check that was executable passed, and the single suite failure is a
test-harness robustness gap triggered by running the suite inside a Slurm
allocation (`SLURM_NTASKS` inherited into a sandboxed runner invocation), not a
production defect. The change is additive, isolated from S3/adapter/`fsiOmega`,
prepared-only on HPC, and honest about its sub-grid limitations.

Recommended next phase: **sdd-archive**. Before or alongside archive, fix the
`SLURM_NTASKS` harness gap so the suite passes in the project's required Slurm
execution environment; scientific acceptance remains contingent on an
explicitly authorized D/32 measurement and campaign.

## Post-verify resolution (orchestrator)

The `SLURM_NTASKS` harness WARNING above was fixed in `4fb3b11`
(`test(turbinesFoam): isolate the sandboxed runner test from an ambient Slurm
allocation`): the sandbox environment now filters every `SLURM_*` variable, so
the test behaves identically on the login node and inside an allocation.

Re-verified on the Slurm partition `sequana_cpu_dev` (job `11599987`,
COMPLETED 0:0, 6:32): `./Allwmake` exit 0, `ldd -r` clean, **full suite
`124 passed, 1 warning`** (`FULL_SUITE_EXIT=0`) and the focused files
`66 passed` (`FOCUSED_EXIT=0`). With the harness gap closed, the engineering
verdict is **PASS**; the scientific-acceptance gap (no production run) and the
remaining SUGGESTIONS stand unchanged.
