# Apply Progress: actuator-surface-model

**Change**: actuator-surface-model — project `of-plugins`
**Branch**: `feat/asm-blade-surface`
**Mode**: Standard (strict_tdd: false)
**Delivery**: `single-pr` with maintainer-approved `size:exception` (whole change = one PR slice)
**Resumed**: after two interruptions; prior apply-progress did not exist (verified via Engram search), so this is the first persisted progress artifact.

## Status: 18/18 tasks complete — ready for verify

All checkboxes in `tasks.md` are `[x]`. Tasks 4.1, 4.2, 5.1, 5.2 had committed files from the
interrupted run but were never verified/ticked; they were re-verified end-to-end in this batch
before being marked complete.

## Evidence (observed in this batch)

### Build — tasks 3.3, 6.1

- `cd turbinesFoam && ./Allwclean && ./Allwmake` (module `openfoam/v2506_openmpi-4.1.4_gnu` + WM_* exports):
  `EXIT:0`, **0 errors**, **54 compiler warnings** (matches baseline), 07:41:18 → 07:43:18.
  Log: `$SCRATCH/tmp/asm-apply-logs/apply2-wmake.log`.
- `ldd -r $FOAM_USER_LIBBIN/libturbinesFoam.so`: exit 0, **0 undefined symbols**;
  `nm -D` shows 30 `actuatorSurfaceElement` symbols.
  Log: `$SCRATCH/tmp/asm-apply-logs/apply2-ldd-r.log`.

### Full regression — task 6.1

- `pytest -v tests/` from `turbinesFoam/`: **15 passed, 1 warning in 216.17s, EXIT:0**
  (`test_libs` 1, `test_al` 5, `test_aftal` 3, `test_cftal` 3, `test_asm` 1, `test_aftal_asm` 2).
  Log: `$SCRATCH/tmp/asm-apply-logs/apply2-pytest-full.log`.

### New ASM tests — tasks 4.1, 4.2

- `tests/test_asm.py` (4.1): PASSED. Patches `tutorials/actuatorLine/static/system/fvOptions.template`
  (mandatory correction #1; the runtime `scripts/set_alpha.py` regenerates `system/fvOptions`), asserts
  `Selecting finite volume options`, element CSV exists, `fx,fy,fz,f_ref_t,f_ref_n` finite, and an
  explicit Python expected-value chord-average check (`chord_strip_mean`, midpoint rule, ≠ single-point).
  No Σ-stripForce / line-CSV `f_ref_n/t` assertions (mandatory correction #2).
  Standalone `-s` run: ALM `rel_vel_mag` 0.99943220, ASM 0.99955434, relative difference 1.222e-04 > 1e-5.
  Log: `$SCRATCH/tmp/asm-apply-logs/apply2-pytest-asm-s.log`.
- `tests/test_aftal_asm.py` + `tests/axialFlowTurbineASMSource/` (4.2): `test_serial` PASSED and
  `test_parallel` PASSED (same full-suite run); `getTutorialFiles.sh` seds `endTime 0.003`, appends
  `debugSwitches` (`actuatorSurfaceElement 1`), asserts turbine + element CSVs and the surface
  element debug line (`chord-averaged inflow velocity`).

### Tutorial + comparison — tasks 5.1, 5.2, 6.2

- 5.1: `tutorials/axialFlowTurbineASM/` is a byte-identical copy of `tutorials/axialFlowTurbineAL/`
  except `blade1` gains `elementType actuatorSurfaceElement;` + `nChordwise 5;` (blade2 = `$blade1`,
  blade3 = `$blade2`) and `system/controlDict` `endTime` is truncated to `0.1`. `Allrun`/`Allclean`
  verified identical to the ALM tutorial.
- 5.2: `compareALMvsASM.py` reads `postProcessing/turbines/0/turbine.csv` + spanwise element CSVs and
  prints side-by-side mean TSR/Cp/CT and 7 spanwise tables. Missing-input path verified:
  `compareALMvsASM.py --alm ./no-such-run --asm ./axialFlowTurbineASM` → exit **1** with
  `Missing input for ALM run:` and both missing paths.
  Log: `$SCRATCH/tmp/asm-apply-logs/apply2-compare-missing.log`.
- 6.2 (Slurm job `11597083`, `sequana_cpu_dev`, `--ntasks=8 --nodes=1`, elapsed 2:25): both tutorial
  cases run in place, ALM `exit:0`, ASM `exit:0`, comparison `exit:0`:
  ```
  Model   mean TSR    mean Cp    mean CT
  ALM      6.0000     0.5489     0.0915
  ASM      6.0000     0.6719     0.1120
  ```
  plus spanwise `root_dist/cl/alpha_deg/rel_vel_mag/c_ref_t,c_ref_n/f_ref_t,f_ref_n` tables.
  Logs: `$SCRATCH/tmp/asm-apply-logs/e2e-compare-apply.log`, `e2e-alm-allrun.log`,
  `e2e-asm-allrun.log`, `11597083.out`.
- Epsilon cross-check (both with `DebugSwitches`): ALM and ASM both report
  `epsilon (mesh-based): 0.183333082243` on the tutorial mesh, i.e. the ALM already selects the
  mesh-based width there; the comparison load shift comes from chord-averaged inflow + strip-wise
  spreading, not epsilon. (Logs: `tests/axialFlowTurbineALSource/log.pimpleFoam`,
  `tests/axialFlowTurbineASMSource/log.pimpleFoam`.)
- 5.3: root `CHANGELOG.md` (Files/Problem/Solution entry), root `README.md` (fork extension),
  `turbinesFoam/README.md` (keys, tutorial, comparison instructions, Gaussian-kernel adaptation vs
  the paper's 5-cell cosine kernel, approximate/inherited force preservation, turbulence-injection
  scope, HAWT-only + CFTAL/VAWT untested, fork divergence) — all written/verified against the
  observed evidence above.

## Files changed in this batch

| File | Commit | Action |
|------|--------|--------|
| `turbinesFoam/src/.../actuatorLineElement/actuatorLineElement.H` | `4d45e35` | Modified — `debugLevel_` member (see deviations) |
| `turbinesFoam/src/.../actuatorLineElement/actuatorLineElement.C` | `4d45e35` | Modified — profile/added-mass debug reference lifetime |
| `CHANGELOG.md`, `README.md`, `turbinesFoam/README.md` | `f7bd8c2` | Modified — docs (task 5.3) |
| `turbinesFoam/tutorials/axialFlowTurbineASM/compareALMvsASM.py` | `52fd258` | Mode 644 → 755 |
| `openspec/changes/actuator-surface-model/tasks.md` | (not committed) | 7 pending checkboxes → `[x]` |

Earlier work-unit commits (unchanged): `26a1f46` core element, `eb94e64` tutorial, `40236b3` tests.

## Deviations from design / decisions on interrupted edits

1. **`endTime` = 0.1 kept (design's "e.g. 0.1")**, not 0.5: the interrupted run's uncommitted
   `controlDict endTime 0.5` was reverted. The E2E (6.2) ran both cases at 0.1 by temporarily
   truncating the *ALM* tutorial controlDict for the run (restored afterwards), so the comparison is
   same-window; this is documented in `turbinesFoam/README.md`. The Slurm job restores all
   runtime-only overrides; they were additionally verified/restored by hand afterwards.
2. **`decomposeParDict` restored to the committed 2 subdomains** (interrupted edit to 8 reverted) to
   keep the tutorial a faithful copy; 8 ranks were used only as a runtime override inside the job.
3. **Added the `debugLevel_` fix** (not in tasks/design): `profileData` and `addedMassModel` hold
   `const label& debug`; passing the static `int debug` switch bound the reference to a temporary that
   died at the end of the base constructor, so `test_al.py`'s Reynolds-correction grep
   (`Initial maximum lift coefficient`) failed. Storing the switch in a member fixes the dangling
   read; `test_al.py` now passes.
4. **`compareALMvsASM.py` made executable** (chore commit) for consistency with `plot.py`.
5. README comparison numbers corrected to the observed same-window values (mean Cp 0.67 ASM vs 0.55
   ALM over 0.1 s); the earlier draft's "0.67 vs 0.50 at endTime 0.1" mixed windows and is fixed.

## Workload / PR boundary

- Mode: single PR with `size:exception` (maintainer-approved, Engram `sdd/actuator-surface-model/delivery`).
- Boundary: whole change; this batch adds the fix + docs + script-mode commits, no new source scope.

## Remaining

- None. Ready for `sdd-verify`.

## Logs / evidence location

`$SCRATCH/tmp/asm-apply-logs/` (untracked repo-root logs were moved there; nothing committed).
