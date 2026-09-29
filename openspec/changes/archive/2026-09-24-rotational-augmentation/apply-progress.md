# Apply Progress — rotational-augmentation

Cumulative apply state. Artifact store: `openspec` (files under
`openspec/changes/rotational-augmentation/`). Mirror:
`engram --topic sdd/rotational-augmentation/apply-progress`.

## Status

| Unit | Status | Commit(s) |
|------|--------|-----------|
| W1 — Du–Selig correction in the shared chain (C++) | **complete** | `feat` + `test` (see below) |
| W2 — Leishman–Beddoes singularity guard | **complete** | `e56158a` + `904a201` |
| W3 — Phase VI config/render integration | **complete** | `8df345c` |
| W4 — Proxy verification harness | **complete** (apply) — matrix gate **not met** | `cdddfca` + `2b20c15` + `4ca1957` + `f2c69e7` |

Mode: **Standard** (`strict_tdd: false`). Delivery: `single-pr` with the
pre-authorized `size:exception`; the W1→W4 work units remain the prepared chain
and each commit is independently revertable.

---

## Fidelity correction (2026-09-24) — Du–Selig prefactor form

Reference: `research-formulation-fidelity.md` (Engram #179); commit `ea399ae`.
The Du–Selig `fL`/`fD` implemented by W1 matched arXiv:1702.02108v4 Eqs. 11–12
*as printed*, but that printed **(split) form** is a transcription error relative
to the original Du & Selig (1998) formulation. The correction restores the
primary-source **prefactor** form
`fL = (1/2π)[(1.6(c/r)/0.1267)·(a − X_L)/(b + X_L) − 1]` (and likewise `fD`),
fixes the latent `a`-role (`a` is now a fraction constant, not an exponent of
`c/r`), and leaves the exponent `(d/Λ)(R/r)`/`(d/(2Λ))(R/r)`, `Λ`, the near-tip
behaviour and the default-off switch semantics unchanged. **No clamp** was
introduced (`fL < 0` in the thin outboard band is inherent to the model).

### What changed

| Artifact | Change |
|----------|--------|
| `actuatorLineElement.{H,C}` | Prefactor form for `fL`/`fD`; `correctRotationalAugmentation()` and its declaration document the formulation, every symbol, Du & Selig (1998) as the primary source, the five independent cross-checks (NREL `AirfoilPrep.py`, BYU `CCBlade.jl`, Munduate 2002, IOP 2024, Li/Liu/Yang 2022 *Energies* 15:6533), the arXiv:1702.02108v4 transcription-error note, `a=b=d=1`, the unclamped outboard `fL<0`/`fD<0` behaviour and the `c/r`/`R/r`/`Λ` inputs |
| `tests/test_rotational_augmentation.py` | Reference values updated to the prefactor form (`fL ≈ 0.3394`, `CL,3D ≈ 1.534`); the source check forbids the split form (`1.6*Foam::pow(cOverR, a_)`, `0.1267*b_`) |
| design §1.1/§2.2/§2.4/§8.1; delta spec "Equation form and paper constants" | Prefactor equations, correction note and corrected hand sample |
| `turbinesFoam/README.md`, Phase VI README, root `README.md`, `CHANGELOG.md` | Prefactor formulation, source list, corrected sensitivity note (fD zero near `r/R ≈ 0.75`) |
| `tasks.md` | Fidelity-correction section; W1.5 and the W1 evidence row annotated |

### Verification (dev queue, job `11600617`, node sdumont6037)

| Gate | Command | Observed |
|------|---------|----------|
| Build exit 0 + no new warnings | `cd turbinesFoam && ./Allwmake` | exit 0; `Allwmake.log` has no `warning:`/`error:` lines |
| Link clean | `ldd -r $FOAM_USER_LIBBIN/libturbinesFoam.so` | exit 0; 0 `undefined`/`not found` |
| Focused module | `pytest -q tests/test_rotational_augmentation.py` | **13 passed** in 20.40 s |
| Full suite | `pytest -q` | **154 passed**, 1 pre-existing `PytestUnknownMarkWarning`, 361.27 s |
| Corrected library pinned | `test_correction_applied` | the solver-driven CSV matches the prefactor-form Python oracle to `rel=2e-4`, so the built library implements the corrected form |

### Proxy re-run (matrix)

See the "Proxy re-run (fidelity correction)" subsection at the end of this file.

---

## W1 — Du–Selig correction in the shared chain

### Completed tasks

- [x] W1.1 Element members, `rotationalAugmentation` block read, geometry sentinels
- [x] W1.2 `correctRotationalAugmentation()` and the `calculateForce` hook
- [x] W1.3 Radial geometry injection in `actuatorLineSource::createElements`
- [x] W1.4 AFTAL forwarding of the block and the rotor/root radii
- [x] W1.5 Pure-Python expected-value test and `SOLVER_DRIVEN` registration
- [x] W1.6 Case fixture and C++ integration tests
- [x] W1.7 W1 default-off regression gate and turbinesFoam docs

### Files changed

| File | Action | What was done |
|------|--------|---------------|
| `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/actuatorLineElement.H` | Modified | `rotationalAugmentationActive_`/`Model_`, `a_`/`b_`/`d_`, `radius_`/`rotorRadius_` members; `correctRotationalAugmentation()` declaration |
| `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/actuatorLineElement.C` | Modified | Additive default-off block read with `FatalIOError` on an unknown model and warn-and-skip when geometry is absent; Du–Selig Eqs. 9–12 implemented verbatim; hook after `lookupCoefficients()` and before dynamic stall |
| `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineSource.C` | Modified | `createElements` reads `rotorRadius`/`rootRadius` and injects `radius = rootRadius + rootDistance*(rotorRadius - rootRadius)` and `rotorRadius` additively; forwards the block |
| `turbinesFoam/src/fvOptions/axialFlowTurbineALSource/axialFlowTurbineALSource.C` | Modified | Forwards the block and `rotorRadius`/`rootRadius` into each blade subdict, identically for both blades, additively |
| `turbinesFoam/tests/conftest.py` | Modified | Registers `test_rotational_augmentation.py` in `SOLVER_DRIVEN` |
| `turbinesFoam/tests/test_rotational_augmentation.py` | Created | Pure-Python Eqs. 9–12 reference + C++/render pin, and 10 solver-driven integration tests |
| `turbinesFoam/tests/rotationalAugmentation/rotor/**` | Created | Minimal one-blade `axialFlowTurbineALSource` fixture (S809, two elements at r = 0.15/0.35 m), default-off baseline plus `.on`/`.off`/`.asm`/`.on-fast`/`.nogeom`/`.badmodel` variants |
| `turbinesFoam/README.md` | Modified | `rotationalAugmentation` key, radial-geometry identity, Eqs. 9–12, sensitivity note and claim boundary |

### Work Unit Evidence

| Evidence | Value |
|---|---|
| Focused test command and exact result | `cd turbinesFoam && pytest -q tests/test_rotational_augmentation.py` → **12 passed** in 17.71 s |
| Runtime harness command/scenario and exact result | `cd turbinesFoam && ./Allwmake` → exit 0; `ldd -r $FOAM_USER_LIBBIN/libturbinesFoam.so` → exit 0, no undefined/not-found; full `pytest -q` → **136 passed**, 1 pre-existing warning, 368.28 s. Slurm jobs 11600114, 11600121 on `sequana_cpu_dev`. |
| Rollback boundary | Revert the W1 commits: removes the correction, the `radius`/`rotorRadius` injection and the tests; with the block absent the chain is byte-identical (proven by `test_default_off_byte_identical`). Configuration rollback = delete the `rotationalAugmentation` block (no recompile). |

### Deviations from design

None — the implementation matches design §3 D1–D3 and the equation→code table.
`test_parallel_restart_invariance` (tasks W1.6) is delivered as two tests
(`test_parallel_matches_serial` + `test_restart_reproduces_scalars`), which is
the same contract split by concern.

### Issues found and fixed during review

The previous interrupted run left three defects in the test artifact, all fixed
here without weakening the oracle:

1. `_initial_row` selected `time == 0.0`, but `pimpleFoam` writes the element
   CSV from the first step onward (no `t = 0` row), so six integration tests
   raised `IndexError`. It now returns the first written row — the uniform
   initial field — and the reference still recomputes from that row's own
   `alpha_deg`.
2. `ELEMENT_RADIUS` held the `elementData` endpoints (0.05/0.45 m) instead of
   the element centres `createElements` produces (0.15/0.35 m). The corrected
   values now match the running CSV to `rel=2e-4`.
3. The task-named tests `test_order_relative_to_dynamic_stall` (W1.2) and
   `test_radial_geometry_keys` (W1.3) were missing and were added.

Also removed an empty leftover `tests/rotationalAugmentation/line/` directory
and corrected stale fixture/test comments that still quoted the endpoints.

### Notes / hand-off

- The combined Du–Selig + Leishman–Beddoes model is not claimed validated
  (design §2.5); the augmentation-first ordering is pinned structurally in W1
  and exercised at runtime by W2.
- The root `CHANGELOG.md` and root `README.md` entries are scheduled per tasks
  in W4.4 (one entry per work unit); they are not part of W1.
- W3–W4 remain pending.

---

## W2 — Leishman–Beddoes singularity guard

### Completed tasks

- [x] W2.1 Analytic 2×2 solve with determinant guard in `calcK1K2`
- [x] W2.2 Guard tests, case fixture and regression gate

### Files changed

| File | Action | What was done |
|------|--------|---------------|
| `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/dynamicStallModels/LeishmanBeddoes/LeishmanBeddoes.C` | Modified | Replaced the unguarded `A.solve()` with an analytic Cramer solve behind a scaled determinant guard: `mag(det) > 1e-12*scale` → `K1_`/`K2_` from the analytic expressions plus a debug record; otherwise `WarningInFunction` + `K1_ = K2_ = 0.0`. Confined to `calcK1K2`. |
| `turbinesFoam/tests/test_leishman_beddoes_guard.py` | Created | Pure-Python analytic-solve and fallback oracles, structural blast-radius/fit-input pins, and the solver-driven crash-point test |
| `turbinesFoam/tests/leishmanBeddoes/rotor/**` | Created | Minimal one-blade `axialFlowTurbineALSource` fixture: element 0 has an empty K1/K2 fit range (cylinder polar, fallback path), element 1 is S809 (well-conditioned path) |
| `turbinesFoam/tests/conftest.py` | Modified | Registers `test_leishman_beddoes_guard.py` in `SOLVER_DRIVEN` |

### Work Unit Evidence

| Evidence | Value |
|---|---|
| Focused test command and exact result | `cd turbinesFoam && pytest -q tests/test_leishman_beddoes_guard.py` → **7 passed** in 23.40 s |
| Runtime harness command/scenario and exact result | `tests/leishmanBeddoes/rotor/Allrun` (`pimpleFoam`, `deltaT 0.008`, `endTime 0.016`) → passes `Time = 0.008` and `Time = 0.016` with no `FOAM FATAL ERROR: Singular Matrix`; fallback `(det = 0)` and analytic `(det = 2.85151, path = well-conditioned)` both recorded. Slurm job 11600173 on `sequana_cpu_dev`. |
| Rollback boundary | `git revert 904a201 e56158a` → LB reverts to `A.solve()` and the guard tests/fixture are removed; other dynamic-stall models untouched. |

### Deviations from design

None — the guard matches design §3 D4 and §4.3 exactly. The prompt's expected
`profileData.C` change is **not present and not required**: the guard is
confined to `calcK1K2`, and `test_blast_radius_one_method` pins
`normalCoeffSlope_ = A.solve()[1];` in `profileData.C` unchanged. The fixture
keeps `calcNormalCoeffSlope` non-singular through out-of-range stations instead
of editing `profileData.C`.

### Issues found

- The first full-suite attempt (job 11600162) ran under `--ntasks=1`; the
  nacelle parallel test could not obtain two OpenMPI slots. Re-ran the gate
  under the W1 allocation `--ntasks=4` (job 11600173) → **143 passed**. No W2
  regression; the failure was an allocation difference.
- The guard tests are 7 (5 pure-Python/structural + 2 solver-driven); the
  former `t = 0.008 s` crash point and the well-conditioned debug record are
  both asserted from the run log.

---

## W3 — Phase VI config/render integration

### Completed tasks

- [x] W3.1 `case.yaml` schema for the augmentation switch and the root ablation
- [x] W3.2 `generate_case.py` renderer and CLI toggles
- [x] W3.3 Committed twin renders (default: augmentation off, root on)
- [x] W3.4 Case/render tests
- [x] W3.5 Phase VI README: formulation, sensitivity and ablation

### Files changed

| File | Action | What was done |
|------|--------|---------------|
| `turbinesFoam/validation/phaseVI/config/case.yaml` | Modified | `actuator.rotational_augmentation` (`active: false`, `model: DuSelig`, `a/b/d: 1`); `end_effects.root` kept as the ablation boolean |
| `turbinesFoam/validation/phaseVI/tools/case_config.py` | Modified | `validate_config` pins the augmentation block (boolean `active`, `DuSelig`, positive `a/b/d`) and the boolean `end_effects.root` |
| `turbinesFoam/validation/phaseVI/tools/generate_case.py` | Modified | `render_fv_options` gains `rotational_augmentation`/`root_effects` and renders the identical `rotationalAugmentation` block at the element-key indentation in all three twins; `outputs()` forwards both; CLI `--rotational-augmentation {on,off}` (default off) and `--root-effects {on,off}` (default from `case.yaml`) |
| `turbinesFoam/validation/phaseVI/case/system/fvOptions.{ALM,ASM,ASM-MESH}` | Modified | Re-rendered committed default (augmentation off, `rootEffects on`), identical except the blade keys |
| `turbinesFoam/tests/test_phasevi_case.py` | Modified | Extended `test_config_schema`, `test_twins_differ_only_in_blade_keys` and `test_generated_case_is_current`; added `test_rotational_augmentation_rendered` and `test_root_effect_ablation_rendered` |
| `turbinesFoam/validation/phaseVI/README.md` | Modified | CLI flags; new "Rotational augmentation (Du–Selig) and the root-effect ablation" subsection (Eqs. 9–12, `a=b=d=1`, sensitivity/claim boundary, render-time ablation, prepared-only boundary, W4 proxy matrix) |

### Work Unit Evidence

| Evidence | Value |
|---|---|
| Focused test command and exact result | `cd turbinesFoam && pytest -q tests/test_phasevi_case.py` → **18 passed** in 3.43 s |
| Runtime harness command/scenario and exact result | `sh validation/phaseVI/scripts/runPhaseVI.sh -m alm -u 13 --ranks 4` (prepare only, no `--run`/`--submit`) → exit 0; `runs/alm-U13-coarse` prepared with `fvOptions.ALM` installed and the shared coarse mesh linked; installed twin byte-equal to the U13 render (polars include normalised), augmentation off and `rootEffects on`. `generate_case.py --check` → exit 0. |
| Rollback boundary | `git revert 8df345c` → removes the switch/ablation and reverts the committed twins; ALM/ASM render paths return to the pre-W3 form and W1/W2 are untouched. Configuration rollback = delete the `rotational_augmentation` block. |

### Deviations from design

None — the implementation matches design §3 D5, §4.4, §6.1–6.4 and §8.3.
`validate_config` additionally pins the switch schema and the boolean root
setting (W3.1 "confirm `end_effects.root` as the boolean used by the ablation");
the delta spec does not forbid it. The `--rotational-augmentation` CLI default is
`off` as designed, so the committed render is unchanged.

### Issues found

None. The previous interrupted W3 run left no tracked edits (the working tree was
clean and no W3 commit existed), so W3 was implemented from the baseline.

### Notes / hand-off

- `rotationalAugmentation` is deliberately **not** in `BLADE_KEYS`: it is
  identical across the three twins and must survive the stripped comparison.
- W4 uses the two CLI toggles to render the `control` / `augmentation-on` /
  `augmentation-on + root-off` matrix; the committed case stays off.
- Root `README.md`/`CHANGELOG.md` entries remain scheduled for W4.4.

---

## W4 — Proxy verification harness

### Completed tasks

- [x] W4.1 Committed harness core (render, self-contained copies, serial chain)
- [x] W4.2 Control-reproduction gate and fail-loud criteria
- [x] W4.3 Proxy tests
- [x] W4.4 Docs, comparison caveat, changelog and W4 gate

### Files changed

| File | Action | What was done |
|------|--------|---------------|
| `turbinesFoam/validation/phaseVI/scripts/proxyRotationalAugmentation.py` | Created (W4.1/W4.2) | Renders the three-variant matrix, self-contained copies, serial chain, `--check`/`--dry-run`/`--prepare`/`--run`/`--evaluate`/`--submit`; control gate + fail-loud criteria; `PROXY_SCRIPTS_DIR` export for the sbatch path |
| `turbinesFoam/validation/phaseVI/scripts/proxyRotationalAugmentation.sh` | Created (W4.1) | Serial dev-queue wrapper (`MaxSubmit=1`), refuses production; resolves its Python under `sbatch` via `PROXY_SCRIPTS_DIR`/`scontrol` |
| `turbinesFoam/tests/test_phasevi_proxy.py` | Created (W4.3) | Pure-Python contracts: variant matrix, check-mode no-submit, serial chain, fail-loud, no-production-submission, hardlink isolation, step selector, measured anchors |
| `turbinesFoam/validation/phaseVI/tools/generate_case.py` | Modified (W4 fix) | Renders the `rotationalAugmentation` block at the **rotor-coeffs** level so AFTAL forwards it with the radial geometry |
| `turbinesFoam/validation/phaseVI/case/system/fvOptions.{ALM,ASM,ASM-MESH}` | Modified (W4 fix) | Re-rendered with the rotor-level block |
| `turbinesFoam/tests/test_phasevi_case.py` | Modified (W4 fix) | Pins the rotor-level placement (not inside a blade subdict) |
| `turbinesFoam/src/.../actuatorLineElement.C`, `.../profileData/profileData.{H,C}` | Modified (W4 fix) | Skip the correction when the profile has no zero-lift reference station (degenerate `cylinder` root) |
| `turbinesFoam/tests/rotationalAugmentation/rotor/system/fvOptions.cylinder`, `rotor/Allrun` | Created/Modified (W4 fix) | Two-point-cylinder fixture and `-cylinder` variant |
| `turbinesFoam/tests/test_rotational_augmentation.py` | Modified (W4 fix) | `test_degenerate_profile_skipped` |
| `turbinesFoam/validation/phaseVI/README.md`, root `README.md`, root `CHANGELOG.md` | Modified (W4.4) | Proxy matrix, control gate, fail-loud criteria, `c_ref_t` caveat, claim boundary, per-work-unit changelog entries |

### Work Unit Evidence

| Evidence | Value |
|---|---|
| Focused test command and exact result | `pytest -q tests/test_rotational_augmentation.py tests/test_leishman_beddoes_guard.py tests/test_phasevi_proxy.py tests/test_phasevi_case.py` → **46 passed** in 70.79 s (job 11600435) |
| Runtime harness command/scenario and exact result | Proxy matrix on `sequana_cpu_dev`, jobs **11600440** (13:control, 13:augmentation-on), **11600447** (13:augmentation-on-root-off, 7:control), **11600478** (7:augmentation-on, 7:augmentation-on-root-off) — all COMPLETED, 6 variants × 26 rows. `--evaluate` exits **1** (fail-loud). |
| Rollback boundary | `git revert f2c69e7 4ca1957 2b20c15 cdddfca` → removes the harness/docs and reverts the render and degenerate-profile fixes; W1–W3 unaffected. |

### Observed proxy metrics vs the gates

| Variant | U13 `cp` | U13 `ct` | U13 mid-span `c_ref_t` | U7 power deficit |
|---|---|---|---|---|
| `control` | −0.044809 | −0.015346 | −0.070378 | −14.99 % |
| `augmentation-on` | −0.051234 | −0.017546 | **+0.084376** | — |
| `augmentation-on-root-off` | −0.033349 | −0.011421 | +0.188596 | **−7.75 %** |

- **Control gate:** PASS (`cp = −0.044809` ∈ `[−0.0473, −0.0349]`).
- **Secondary sign signal:** PASS (mid-span `c_ref_t = +0.084376 ≥ +0.02`).
- **Primary U7 ablation:** PASS (deficit shrunk to −7.75 %, inside ±15 %).
- **Primary U13 signal:** **FAIL** — `cp = −0.051234`, `ct = −0.017546`, both negative.

### Deviations from design

- The design §4.4 said the block renders at the **element-key indentation**
  (inside each blade subdict). The proxy matrix proved that placement silently
  skips the correction (AFTAL forwards the block only from the rotor-coeffs
  level), so the block is rendered next to `dynamicStall` instead. The W3
  section above describes the original (superseded) placement; the rotor-level
  render is the correct one.
- The design §13 listed `profileData.{H,C}` as **Unchanged**. A degenerate
  placeholder profile (the Phase VI root `cylinder`, only ±180°) has no station
  in the zero-lift reference window, and the correction's zero-lift lookup
  segfaulted; `hasZeroLiftReference()` + an element guard were added. This is a
  necessary robustness fix, not a change to the correction algebra.

### Issues found

1. Blade-level render → correction silently skipped (fixed, `cdddfca`).
2. Degenerate `cylinder` root → empty `[-10, 10]°` sub-list → segfault in
   `profileData::interpolate` (reproduced in the stray job 11600415 log;
   fixed, `4ca1957`).
3. sbatch spools the wrapper → `$0` no longer points at the committed script
   (fixed, `2b20c15`).

### Global result (closes the apply phase)

All W1–W4 tasks are implemented, tested and documented. The W4 proxy matrix
**does not meet the U13 primary criterion**: the control gate reproduces the
failure and the spanwise sign and the U7 ablation behave as intended, but the
U13 integrated `cp`/`ct` stay negative with augmentation on. The harness fails
loudly and the criterion is reported unweakened. Verification (`sdd-verify`)
must assess this failed criterion; the apply phase itself is complete.

### Post-apply evidence (orchestrator)

- **U7 matrix completed** (dev-queue job `11600478`, COMPLETED 0:0, 10:20): U7 `cp` control 0.30998, augmentation-on 0.30927, augmentation-on + root-off **0.33664** (+8.6 % vs control — the −16 % power deficit moves inside the ±15 % band). U13 as recorded above: the augmentation alone does not flip the deep-stall sign; `rootEffects off` is the effective lever.
- **CFtAL parallel fallback investigated** (the single full-suite failure in job `11600467`): `tests/test_cftal.py::test_parallel` passes in isolation in two consecutive dev-queue runs (job `11600496`: `1 passed` / `1 passed`, 17 s each). The full-suite segfault is environmental/flaky, not a regression from this change.
- The account submit limit cleared and the dev queue was used for all heavy work per the standing policy.

### Fidelity correction (post-apply, 2026-09-24)

- **What.** Restored the original Du & Selig (1998) **prefactor** form of
  Eqs. 11–12 (`(1.6(c/r)/0.1267)·(a − X)/(b + X) − 1`) after establishing that
  the arXiv preprint's printed split form
  (`(1.6(c/r)^a − X)/(0.1267b + X) − 1`) is a transcription error. `a`/`b` are
  the fraction constants, not an exponent of `c/r`; the exponent, `Λ`, switch
  semantics and the no-clamp decision are unchanged. Commit `ea399ae`.
- **Why.** The split form inverted the drag-correction sign over most of the
  blade and enlarged the outboard `fL < 0` region ~4× by span. Evidence and
  cross-checks (NREL `AirfoilPrep.py`, BYU `CCBlade.jl`, Munduate 2002, IOP
  2024, Li/Liu/Yang 2022 *Energies* 15:6533):
  `research-formulation-fidelity.md`.
- **Refreshed evidence.** Build/test job `11600617`: `./Allwmake` exit 0, `ldd
  -r` exit 0, RA focused module **13 passed**, full suite **154 passed**. Proxy
  jobs `11600623`, `11600630`, `11600635` re-ran the 0.25-rev D/32 matrix with
  the corrected library; an independent `--evaluate` re-run reproduces the JSON.
- **Corrected proxy numbers.** U13 `cp` mean (final row) control
  −0.044809 (−0.045859), augmentation-on **−0.000080** (−0.002094, previously
  −0.051234/−0.052943), root-off **+0.021690** (+0.019482, previously
  −0.033349/−0.035671). U13 mid-span `c_ref_t` +0.305817 (was +0.084376) and
  +0.436461 root-off (was +0.188596). U7 `cp` final row 0.309981 / 0.344433 /
  0.373306 (control / aug-on / root-off; previously 0.309981 / 0.309268 /
  0.336636); root-off power deficit −14.99 % → +1.79 %. Control gate PASS,
  U13 secondary sign PASS, U7 ablation PASS, U13 primary (`cp`/`ct` > 0) still
  FAIL but ≈0 (within the short-window spread) — unweakened.

---

## Follow-up fix — W-1 (YAML augmentation switch drives the render)

**Finding:** re-verify **W-1** — `generate_case.py` defaulted
`--rotational-augmentation` to `off` and unconditionally overwrote the YAML
`actuator.rotational_augmentation.active`, so a YAML `active: true` rendered
`active off`, and `runPhaseVI.sh` never let the YAML govern. The
`phasevi-validation-case` scenario "Augmentation switch rendered" failed.

### What changed

| Artifact | Change |
|----------|--------|
| `turbinesFoam/validation/phaseVI/tools/generate_case.py` | `--rotational-augmentation` defaults to `None` and overrides the YAML `active` only when the flag is present (mirrors `--root-effects`) |
| `turbinesFoam/validation/phaseVI/scripts/runPhaseVI.sh` | optional `--rotational-augmentation on|off` is forwarded to the renderer only when requested; absent, the YAML governs; an invalid value exits 2 |
| `turbinesFoam/tests/test_phasevi_case.py` | `test_rotational_augmentation_yaml_governs_and_flag_overrides` (YAML `active` true/false with no flag; the flag overrides both ways) + `test_runner_lets_yaml_govern_rotational_augmentation` (prepare-only runner end-to-end, including the invalid-value rejection) |

### Verification (login node, no Slurm)

| Gate | Command | Observed |
|------|---------|----------|
| Renderer check | `python validation/phaseVI/tools/generate_case.py --check` | exit 0 (committed twins unchanged) |
| Focused tests | `pytest -q tests/test_phasevi_case.py tests/test_phasevi_proxy.py` | **28 passed** |
| Adjacent Phase VI suites | `pytest -q tests/test_phasevi_case.py tests/test_phasevi_proxy.py tests/test_phasevi_compare.py tests/test_phasevi_data.py` | **47 passed** |
| YAML-governs demo | temp YAML `active: true`, no CLI flag | `fvOptions.ALM:43: active on;` inside the `rotationalAugmentation` block |
| Flag override demo | YAML `true` + `--rotational-augmentation off` | `active off;` |
| Runner end-to-end | prepare-only `runPhaseVI.sh -m alm -u 7` on a `active: true` sandbox YAML | `active on;` installed; `--rotational-augmentation off` → `active off;`; `bogus` → exit 2 |
| Shell syntax | `sh -n validation/phaseVI/scripts/runPhaseVI.sh` | exit 0 (`shellcheck` not installed in this environment) |

**Status:** W-1 **closed** — the CLI and the standard runner now let the YAML
switch drive the render. **C-1** (U13 `augmentation-on` `cp`/`ct` not positive)
is unchanged and remains open; the validation claim remains unearned.

### Work Unit Evidence

| Evidence | Value |
|----------|-------|
| Focused test command and exact result | `pytest -q tests/test_phasevi_case.py tests/test_phasevi_proxy.py` → **28 passed** in 7.91 s |
| Runtime harness command/scenario and exact result | `test_runner_lets_yaml_govern_rotational_augmentation`: prepare-only `runPhaseVI.sh -m alm -u 7 -mesh coarse` on a sandbox YAML `active: true` → installed `system/fvOptions` renders `active on;`; `--rotational-augmentation off` → `active off;`; `bogus` → exit 2. Renderer check `generate_case.py --check` → exit 0. |
| Rollback boundary | `git revert 47cb02e` → restores the forced `off` default and removes the runner option and the two tests; no other W1–W4 behavior changes. Configuration rollback = leave `actuator.rotational_augmentation.active: false` in `config/case.yaml`. |

---

## W-3 runtime closure — ASM-MESH proxy matrix completed (2026-09-24)

**Finding:** W-3 — the mesh-backed ASM (`asm-mesh`) inheritance of the
rotational-augmentation / root-effects toggles was structurally guaranteed but
not exercised at run time. The `0c4f9d3` model selector made the runtime path
available; the U13 ASM-MESH variants and the U7 control were run first, leaving
the two U7 augmentation variants prepared but unexecuted. This note closes the
gap by running exactly those two.

**Command (dev queue only, 48 ranks, 20-min limit):**

```sh
cd turbinesFoam/validation/phaseVI
sbatch --export=ALL,PROXY_SCRIPTS_DIR="$PWD/scripts",PROXY_MODEL=asm-mesh \
    "$PWD/scripts/proxyRotationalAugmentation.sh" \
    --model asm-mesh 7:augmentation-on 7:augmentation-on-root-off
```

The chunked `SPEED:VARIANT` steps re-run only the two missing variants; the
harness `prepare()` is idempotent and kept every already-completed variant
package untouched. No production queue, no Slurm array, no `--submit`.

**Jobs:** `11601023` — `phaseVI-proxy-ra`, `sequana_cpu_dev`, **COMPLETED 0:0**,
elapsed 10:12 (sdumont6167). No `solver failed` lines; both variants reached
`End` / `Finalising parallel run`. Context: the earlier smoke split the ASM-MESH
matrix across `11601002` (U13 control) and `11601007` (U13 aug-on, U13
augmentation-on-root-off, U7 control); the U7 augmentation steps were never
submitted and are the ones completed here.

**U7 ASM-MESH results** (same 0.25-rev D/32 coarse proxy, 26 samples to
t = 0.208 s; final-row values, harness mean in parentheses):

| Variant | final `cp` | final `ct` | mean `cp` | mean `ct` |
|---------|-----------:|-----------:|----------:|----------:|
| control (`0c4f9d3` smoke) | +0.3262 | +0.0603 | +0.3170 | +0.0586 |
| augmentation-on | **+0.3698** | **+0.0684** | +0.3568 | +0.0660 |
| augmentation-on-root-off | **+0.4076** | **+0.0754** | +0.3902 | +0.0721 |

Directional behavior matches the committed ALM matrix (U7 `cp` 0.3100 → 0.3444
/ 0.3733): both augmentations improve on the control and the root-off ablation
improves further. The ASM-MESH integrated `cp` sits above the ALM at the same
state, as expected for the mesh-backed surface load chain.

**Harness gate:** `python scripts/proxyRotationalAugmentation.py --evaluate
--model asm-mesh` exits **1** on the single pre-existing gate only — the U13
control-gate proxy bias (`control cp = −0.04872` vs the `[−0.0473, −0.0349]`
band; ALM control `−0.04481` is inside), the documented ≈11 % systematic proxy
bias, **not** a W-3 signal. The U7 root-off ablation gate **passes** (deficit
−10.4 % → +10.3 %, inside ±15 %), and the U13 `augmentation-on` `cp`/`ct` are
positive on the harness mean (`+0.00159` / `+0.00055`).

**W-3 verdict: CLOSED.** The ASM-MESH runtime path runs at both 7 and 13 m/s
with the expected directional augmentation/root-off behavior; the finding's
structural guarantee is now backed by executed ASM-MESH proxy runs. C-1 (U13
primary criterion vs the converged campaign) remains open and out of scope here.

*Evidence paths:* `turbinesFoam/validation/phaseVI/11601023.{out,err}`;
`runs/proxy-asm-mesh-U7-{augmentation-on,augmentation-on-root-off}/postProcessing/turbines/0/turbine.csv`;
`$SCRATCH/tmp/w3_asm_mesh_evaluate.json`. No commit: the note and the run
outputs live under untracked `openspec/` and `runs/` and are intentionally not
committed.

---

## Campaign preparation pointer (2026-09-24, post-archive)

The converged gate for **C-1** is now **prepared** (not submitted): commit
`3c15ac349cd0007d325ec14e0ac320d68318dec3` adds
`turbinesFoam/validation/phaseVI/scripts/slurm/campaign-rotational-augmentation.slurm`,
a prepared-only 21-task array (`sequana_cpu`, 48 ranks, ≤ 96 h) running
`alm` / `asm` / `asm-mesh` at 7/10/13/15/25 m/s on D/32 plus a D/48 spot-check
at 7 and 13 m/s, all with `--rotational-augmentation on --root-effects off`.
Matrix, launch command, baseline (the ALM/ASM `aug off` 2026-09-21 results),
acceptance bands (±15 % power/torque/thrust), the D/48-with-new-physics
rationale and the `MaxSubmitJobs=24` association caveat are in
`turbinesFoam/validation/phaseVI/CAMPAIGN.md`; the runner gained the
`--root-effects on|off` forwarding the candidate needs (it previously rejected
the flag with exit 2).

The array is gated by `PHASEVI_LONG_QUEUE_AUTHORIZED=1` and was **not**
submitted. This is an appended pointer note only; `archive-report.md` is left
unchanged. Untracked `openspec/` — not committed.
