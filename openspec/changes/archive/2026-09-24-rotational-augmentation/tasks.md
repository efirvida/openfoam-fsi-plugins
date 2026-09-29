# Tasks: Rotational augmentation (3D stall delay) in the shared blade-load chain

Change: `rotational-augmentation` — orthogonal to the archived S1/S2
(`nacelle-actuator-surface`, `blade-actuator-surface`); S3 (preCICE FSI) remains
deferred. Reference: Yang & Sotiropoulos, *A new class of actuator surface models
for wind turbines*, arXiv:1702.02108v4. Primary evidence:
`turbinesFoam/validation/phaseVI/results/DIAGNOSIS-2026-09-21.md`.

Mode: **Standard** (`strict_tdd: false` → tests required, no strict RED-GREEN
ritual). Tasks are grouped by **work unit** (the design's delivery slices W1→W4,
design §1.2/§9) with hierarchical numbering; each task is completable in one
session. Each work unit ends with its own tests and docs so every slice is
independently reviewable and revertable (proposal §Rollback Plan). Every task
cites the design section and the delta-spec requirement(s) it satisfies.

Threat matrix: **N/A** (design §10) — the change introduces no routing, shell
command, VCS/PR-automation or executable-file-classification boundary. The
subprocess surfaces are the same class S1/S2 assessed: `runPhaseVI.sh` invoking
`generate_case.py`, `mesh.sh` and `mpirun` on committed inputs; the new W4 proxy
harness invoking the same committed preparation path and an authorized
dev-queue scheduler only under explicit invocation; and the production arrays,
which are **prepared-only** and never launched by this change. The relevant
constraint is the dev-queue proxy + prepared-only production guard: no
automated step submits, cancels or modifies a production job (W4.3/W4.4 assert
it). No threat-matrix RED-test tasks apply.

---

## Fidelity correction (2026-09-24) — Du–Selig prefactor form

Reference: `research-formulation-fidelity.md` (Engram #179) and commit `ea399ae`.
The Du–Selig equations W1 implemented were read from arXiv:1702.02108v4
Eqs. 11–12 *as printed*; that printed form is a **transcription error** relative
to the original Du & Selig (1998) formulation. Commit `ea399ae` restores the
primary-source **prefactor** form for `fL` and `fD` and resolves the latent
`a`-role bug (`a` is a fraction constant, not an exponent of `c/r`). The
exponent `(d/Λ)(R/r)`, `Λ`, the near-tip behaviour and the default-off semantics
are unchanged; no clamp was introduced.

- **Corrected equations** (supersede the split form quoted in W1.2/W1.5):
  `fL = (1/2π)[(1.6(c/r)/0.1267)·(a − X_L)/(b + X_L) − 1]`,
  `fD = (1/2π)[(1.6(c/r)/0.1267)·(a − X_D)/(b + X_D) − 1]`, with
  `X_L = (c/r)^((d/Λ)(R/r))` and `X_D = (c/r)^((d/(2Λ))(R/r))`. The split form
  `(1.6(c/r)a − X)/(0.1267b + X) − 1` is forbidden by
  `test_cpp_constants_and_config_pinned`.
- **Corrected reference values** (supersede W1.5 and the W1 evidence table):
  `fL = 0.339437`, `CL,3D = 1.534` at the hand sample (`c/r ≈ 0.271`,
  `R/r ≈ 2.27`, `Λ ≈ 0.95`); the near-tip `fL → −1/(2π) ≈ −0.159` limit is
  unchanged.
- **Docs updated:** design §1.1/§2.2/§2.4/§8.1, the delta spec
  "Equation form and paper constants", `turbinesFoam/README.md`, the Phase VI
  README formulation block, root `README.md` and `CHANGELOG.md`.
- **In-code documentation:** `correctRotationalAugmentation()` and its
  declaration document the formulation, every symbol, the primary source, the
  independent cross-checks, the transcription-error note, the constants
  `a=b=d=1`, the unclamped outboard behaviour and the `c/r`/`R/r`/`Λ` inputs.
- **Proxy re-run:** see the "Fidelity correction" section of `apply-progress.md`
  for the corrected matrix numbers.

---

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | W1 ~300–500 · W2 ~60–120 · W3 ~250–450 · W4 ~200–400 — **total ~810–1470** |
| 400-line budget risk | **High** |
| Chained PRs recommended | **Yes** |
| Suggested split | W1 → W2 → W3 → W4 |
| Delivery strategy | `single-pr` (session strategy; the explicit `size:exception` is **recorded as required and pre-authorized** — S1/S2 precedent) |
| Chain strategy | `size-exception` (pre-authorized; the chained W1→W2→W3→W4 units remain the prepared fallback) |

```
Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: size-exception
400-line budget risk: High
```

The forecast (~810–1470 changed lines, design §1.2/§9) is far over the 400-line
review budget. The session strategy is **Single PR**, and the explicit
`size:exception` is **required** for this change and **pre-authorized** under the
S1/S2 precedent, so `sdd-apply` starts without a further delivery decision; the
`size:exception` must be recorded on the single PR at creation time. The
W1→W2→W3→W4 boundary remains the prepared fallback: each unit has a single
reviewable purpose, ends with its own tests and docs, and reverts cleanly on its
own; W2/W3/W4 do not change W1 semantics. Under single-PR delivery, commits
should still follow the work units so the reviewer can verify slice by slice.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| W1 | Du–Selig correction + radial geometry in the shared chain; C++ integration + pure-Python expected-value tests; turbinesFoam README | PR 1 (chained alternative) | `cd turbinesFoam && pytest -q tests/test_rotational_augmentation.py tests/test_al.py tests/test_asm.py tests/test_aftal.py tests/test_aftal_asm.py tests/test_blade_surface.py tests/test_libs.py` | `./Allwmake` (exit 0) + `ldd -r $FOAM_USER_LIBBIN/libturbinesFoam.so` clean; default-off byte-compare; `mpirun -np 2` invariance | `git revert` W1 → removes the correction, the geometry keys and the tests; default paths byte-identical |
| W2 | Leishman–Beddoes singularity guard + fallback record + guard tests | PR 2 (chained alternative) | `cd turbinesFoam && pytest -q tests/test_leishman_beddoes_guard.py tests/test_al.py tests/test_asm.py` | `./Allwmake`; `dynamicStall` + `LeishmanBeddoesCoeffs` passes `t = 0.008 s` | `git revert` W2 → LB reverts to `solve()`; other dynamic-stall models untouched |
| W3 | Phase VI `rotationalAugmentation` on-switch + `rootEffects` ablation in `case.yaml`/`generate_case.py`; case/render tests; docs | PR 3 (chained alternative) | `cd turbinesFoam && pytest -q tests/test_phasevi_case.py` | `python3 validation/phaseVI/tools/generate_case.py --check`; `runPhaseVI.sh -m alm -u 13` (prepare only; no `--run`/`--submit`) | `git revert` W3 → removes the switch/ablation; ALM/ASM twins unchanged |
| W4 | Committed 0.25-rev D/32 proxy harness, variant matrix, control gate + fail-loud criteria, caveat, tests, README/CHANGELOG | PR 4 (chained alternative) | `cd turbinesFoam && pytest -q tests/test_phasevi_proxy.py` | `python3 validation/phaseVI/scripts/proxyRotationalAugmentation.py --check` (submits nothing); dev queue only; **no production submission** | `git revert` W4 → removes harness/docs; W1–W3 unaffected |

---

## W1 — Du–Selig correction in the shared chain (C++)

Reference: design §1.1, §2 (equation→code), §3 D1–D3, §4.1–4.2, §5, §8.1, §9 W1.
Specs: `rotational-augmentation`, `actuator-surface-element`,
`element-type-selection`.

### W1.1 — Element members, `rotationalAugmentation` block read, geometry sentinels

- [x] **Files (modify):** `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/actuatorLineElement.H`, `actuatorLineElement.C`
- **Work (design §3 D3, §4.1):**
  - Declare protected members next to the coefficient members (`.H:135-169`): `rotationalAugmentationActive_`, `rotationalAugmentationModel_`, `a_`, `b_`, `d_`, `radius_`, `rotorRadius_`.
  - Read the `rotationalAugmentation` sub-block mirroring `dynamicStall` (`.C:103-116`): `active` (`lookupOrDefault`, default `false`), `model` (default `DuSelig`), `a`/`b`/`d` (default `1.0`); `FatalIOErrorInFunction(raDict)` on any model other than `DuSelig` (design §3 D3 code).
  - Read `radius_`/`rotorRadius_` with `lookupOrDefault` sentinels; if active but either is absent, `WarningInFunction` and set `rotationalAugmentationActive_ = false` (no abort).
- **Acceptance:** absent block / `active off` → no state change and the old dictionary stays valid; unknown `model` fails loudly; active-without-geometry warns and skips the correction.
- **Verification:** `cd turbinesFoam && ./Allwmake`; exercised by W1.6 (`test_absent_keys_keep_old_dict`, `test_unknown_model_rejected`).
- **Traces to:** spec `rotational-augmentation` — "Additive default-off switch" / "Unknown model rejected"; "Per-element radial geometry interface" / "Absent keys keep the old dictionary valid".

### W1.2 — `correctRotationalAugmentation()` and the `calculateForce` hook

- [x] **Files (modify):** `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/actuatorLineElement.H`, `actuatorLineElement.C`
- **Work (design §2.2, §2.4, §3 D1):**
  - Add private `void correctRotationalAugmentation();` next to `lookupCoefficients()` (`.H`).
  - Implement Eqs. 9–12 verbatim (design §3 D1 code): `cOverR = chordLength_/radius_`, `ROverR = rotorRadius_/radius_`, `omegaR = omega_*rotorRadius_`, `lambda = omegaR/sqrt(magSqr(freeStreamVelocity_) + sqr(omegaR))`, exponent `(d_/lambda)*ROverR` for `fL` and `(d_/(2*lambda))*ROverR` for `fD`; `CLp = 2π(degToRad(angleOfAttack_) − degToRad(profileData_.zeroLiftAngleOfAttack()))`; `CD0 = profileData_.zeroLiftDragCoeff()`; `liftCoefficient_ += fL*(CLp − liftCoefficient_)`, `dragCoefficient_ -= fD*(dragCoefficient_ − CD0)`. No invented clamp (design §2.4).
  - Hook immediately after `lookupCoefficients()` (`:819`) and before the dynamic-stall call (`:835`): `if (rotationalAugmentationActive_) correctRotationalAugmentation();` — in place, so dynamic stall, added mass, the end-effect factor (`:862`) and the CSV consume the corrected values with no downstream re-application.
- **Acceptance:** `liftCoefficient_`/`dragCoefficient_` hold `CL,3D`/`CD,3D` before any later correction; pre-stall (`CL,2D ≈ CL,p`) leaves lift unchanged and drag follows Eq. 10; exponent is `(d/Λ)(R/r)` / `(d/(2Λ))(R/r)` — never `d·ΛR/r`.
- **Verification:** `cd turbinesFoam && ./Allwmake`; W1.5 `test_du_selig_reference_values`; W1.6 `test_correction_applied`, `test_pre_stall_unchanged`, `test_order_relative_to_dynamic_stall`.
- **Traces to:** spec `rotational-augmentation` — "Du–Selig correction in the shared load chain" (all 3 scenarios); "Equation form and paper constants" (both scenarios).

### W1.3 — Radial geometry injection in `actuatorLineSource::createElements`

- [x] **Files (modify):** `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineSource.C`
- **Work (design §3 D2, §5):** read `rotorRadius = coeffs_.lookupOrDefault("rotorRadius", -VGREAT)` and `rootRadius = coeffs_.lookupOrDefault("rootRadius", -VGREAT)`; when both `> 0` inject `radius = rootRadius + rootDistance*(rotorRadius − rootRadius)` and `rotorRadius` into every element dict alongside the existing keys (`:316-378`). Additive: absent inputs → nothing injected.
- **Acceptance:** keys present → every element dict carries `radius`/`rotorRadius`; the injected `radius` equals the comparison tool's local station (`comparePhaseVI.py:280-287`); absent inputs → old dicts valid, no behavior change.
- **Verification:** `cd turbinesFoam && ./Allwmake`; W1.6 `test_radial_geometry_keys`, `test_absent_keys_keep_old_dict`.
- **Traces to:** spec `rotational-augmentation` — "Per-element radial geometry interface" / "Keys present compute the ratios"; spec `element-type-selection` — "Config key plumbing" / "Radial geometry keys injected", "No new keys present".

### W1.4 — AFTAL forwarding of the block and the rotor/root radii

- [x] **Files (modify):** `turbinesFoam/src/fvOptions/axialFlowTurbineALSource/axialFlowTurbineALSource.C`
- **Work (design §3 D2, §5):** at the existing `dynamicStall` seam (`:314-328`) forward the `rotationalAugmentation` block and inject `rotorRadius` (`turbineALSource.H:109`, `turbineALSource.C:517`) and the root station (`elementData[0][1]`, `:138`) into each blade subdict, additively and identically for both blades.
- **Acceptance:** with radial keys the block and both radii reach every blade subdict; when absent, nothing is added; no new dictionary topology.
- **Verification:** `cd turbinesFoam && ./Allwmake`; `cd turbinesFoam && pytest -q tests/test_aftal.py tests/test_aftal_asm.py`.
- **Traces to:** spec `rotational-augmentation` — "Additive default-off switch" / "Switch on applies the correction"; "Single-chain inheritance by ALM, ASM and the mesh surface"; spec `element-type-selection` — "Radial geometry keys injected"; spec `actuator-surface-element` — "Inherited blade element force chain".

### W1.5 — Pure-Python expected-value test and `SOLVER_DRIVEN` registration

- [x] **Files (create):** `turbinesFoam/tests/test_rotational_augmentation.py`
- [x] **Files (modify):** `turbinesFoam/tests/conftest.py`
- **Work (design §8.1):** implement `test_du_selig_reference_values` — a Python re-implementation of Eqs. 9–12 reproduces the hand-computed U13 sample (`fL ≈ 0.20`, `CL,3D ≈ 1.11–1.21` at `c/r ≈ 0.271`, `R/r ≈ 2.27`, `Λ ≈ 0.95`) and the near-tip `fL → −1/(2π)` limit; pin the C++ constants/exponents with a source/rendered-dict check so the Python reference cannot silently drift. Add the module to `SOLVER_DRIVEN` (`conftest.py:17-26`) so it skips cleanly without OpenFOAM. **Superseded by the 2026-09-24 fidelity correction:** the prefactor form gives `fL ≈ 0.34`, `CL,3D ≈ 1.53` (see the fidelity-correction section above).
- **Acceptance:** pure-Python and CI-safe (no OpenFOAM); the reference values and the C++ constants/exponents are pinned against each other.
- **Verification:** `cd turbinesFoam && pytest -q tests/test_rotational_augmentation.py::test_du_selig_reference_values`.
- **Traces to:** spec `rotational-augmentation` — "Equation form and paper constants" (both scenarios).

### W1.6 — Case fixture and C++ integration tests

- [x] **Files (create):** `turbinesFoam/tests/rotationalAugmentation/**` (minimal standalone `actuatorLineSource` with an S809 profile, a `rotationalAugmentation { active on; }` block and injected `radius`/`rotorRadius`; `writeElementPerf true` element CSV; a `forceIntegral` functionObject)
- [x] **Files (modify):** `turbinesFoam/tests/test_rotational_augmentation.py`
- **Work (design §8.1):** implement `test_correction_applied` (CSV `cl`/`cd` differ from the static polar in the Eqs. 9–10 direction; block off → byte-identical CSV), `test_pre_stall_unchanged`, `test_absent_keys_keep_old_dict`, `test_unknown_model_rejected`, `test_all_models_inherit` (same augmentation-on configuration as `elementType actuatorLineElement` and `elementType actuatorSurfaceElement`, and the mesh surface where the fixture supports it), `test_parallel_restart_invariance` (`mpirun -np 2` matches serial; restart reproduces the scalars).
- **Acceptance:** all tests pass with OpenFOAM loaded and skip cleanly without it; default-off output is byte-identical to the pre-change chain; pre-stall coefficients are unchanged; all models reflect the correction with no per-model code.
- **Verification:** `cd turbinesFoam && pytest -q tests/test_rotational_augmentation.py`.
- **Traces to:** design §8.1; spec `rotational-augmentation` — "Du–Selig correction in the shared load chain", "Equation form and paper constants", "Per-element radial geometry interface" / "Parallel and restart safety", "Additive default-off switch", "Single-chain inheritance by ALM, ASM and the mesh surface"; spec `actuator-surface-element` — "Identical BEM pipeline for a common flow", "Augmentation inherited without per-model code", "Element CSV output".

### W1.7 — W1 default-off regression gate and turbinesFoam docs

- [x] **Files (modify):** `turbinesFoam/README.md`
- **Work:**
  - Regression gate: `./Allwmake` exit 0; `ldd -r` clean; full existing suite unchanged (`test_al`, `test_asm`, `test_aftal`, `test_aftal_asm`, `test_blade_surface`, `test_libs`); default-off element/line/turbine CSV byte-compare against a pre-change run.
  - Docs: document the `rotationalAugmentation` key (`active`/`model`/`a`/`b`/`d`), the `radius`/`rotorRadius` injection and identity, the formulation (Eqs. 9–12, `a=b=d=1`), the sensitivity note (no free-parameter calibration; near-tip `fL < 0` behaviour; end-effect factor applied after the hook) and the honest claim boundary.
- **Acceptance:** build + full suite green; default-off output byte-identical; README states the equations, constants, sensitivity note and claim boundary.
- **Verification:** `cd turbinesFoam && ./Allwmake`; `ldd -r $FOAM_USER_LIBBIN/libturbinesFoam.so`; `cd turbinesFoam && pytest -q`; README review.
- **Traces to:** spec `rotational-augmentation` — "Additive default-off switch" / "Default-off byte-identical output"; "Formulation documentation and claim boundary".

### W1 evidence (batch W1)

All observed on `sequana_cpu_dev` via Slurm (jobs 11600114 and 11600121),
OpenFOAM v2506 / OpenMPI 4.1.4 / GNU, GCC 14 libstdc++.

| Gate | Command | Observed |
|------|---------|----------|
| Build exit 0 + no new warnings | `cd turbinesFoam && ./Allwmake` | exit 0; `wmake.log` has no `warning:`/`error:` lines for the W1 sources (and none at all) |
| Link clean | `ldd -r $FOAM_USER_LIBBIN/libturbinesFoam.so` | exit 0; no `undefined`/`not found` |
| W1 focused module | `pytest -q tests/test_rotational_augmentation.py` | **12 passed** in 17.71 s |
| Full suite | `pytest -q` | **136 passed**, 1 pre-existing `PytestUnknownMarkWarning` (`test_al.py:131`), 368.28 s |
| Pure-Python Eqs. 9–12 sample | reference `fL`/`CL,3D` | W1 (split form): `fL = 0.203585`, `CL,3D = 1.212497`. After the 2026-09-24 fidelity correction (prefactor form): `fL = 0.339437`, `CL,3D = 1.534` |
| Default-off byte gate | `test_default_off_byte_identical` | block absent vs `active off` element CSV byte-identical; default path equals the static polar |
| Radial geometry | `test_radial_geometry_keys` | CSV `root_dist` 0.25/0.75 inverts to injected `r` 0.15/0.35 m, matching the element centres |
| Parallel / restart | `test_parallel_matches_serial`, `test_restart_reproduces_scalars` | `mpirun -np 2` reproduces the serial corrected rows; restart reproduces the corrected scalars |
| Inheritance | `test_all_models_inherit` | ALM (`actuatorLineElement`) and ASM (`actuatorSurfaceElement`) match the same reference |

Test-defect fixes made during the W1 review (the previous interrupted run left
them): `_initial_row` read `time == 0.0`, but `pimpleFoam` writes the first row
at the first step, so it now returns the first written row; `ELEMENT_RADIUS`
held the `elementData` endpoints (0.05/0.45 m) instead of the element centres
(0.15/0.35 m); the two task-named tests
`test_order_relative_to_dynamic_stall` and `test_radial_geometry_keys` were
missing and were added. `test_parallel_restart_invariance` is delivered as the
two tests `test_parallel_matches_serial` + `test_restart_reproduces_scalars`.

---

## W2 — Leishman–Beddoes singularity guard

Reference: design §2.5, §3 D4, §4.3, §8.2, §9 W2. Spec:
`dynamic-stall-singularity-guard`.

### W2.1 — Analytic 2×2 solve with determinant guard in `calcK1K2`

- [x] **Files (modify):** `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/dynamicStallModels/LeishmanBeddoes/LeishmanBeddoes.C`
- **Work (design §3 D4):** replace the unguarded `simpleMatrix<scalar> A(2).solve()` (`:321`) with the analytic 2×2 solve guarded by `det = A[0][0]*A[1][1] − A[0][1]*A[1][0]` and `scale = max(mag(A[0][0]*A[1][1]), mag(A[0][1]*A[1][0])) + VSMALL`; when `mag(det) > 1e-12*scale` set `K1_`/`K2_` from the analytic expressions and emit the debug `Info` record; otherwise emit `WarningInFunction` with the determinant and fall back to `K1_ = K2_ = 0.0`. Confined to `calcK1K2`; no other dynamic-stall model and no fit input touched.
- **Acceptance:** well-conditioned matrix → same `K1`/`K2` as the unguarded solve to round-off; singular/ill-conditioned → documented fallback with a warning; `simpleMatrix::solve()` is never called; blast radius is one method.
- **Verification:** `cd turbinesFoam && ./Allwmake`; exercised by W2.2.
- **Traces to:** spec `dynamic-stall-singularity-guard` — "No abort on a singular fit matrix" / "Well-conditioned fit preserved"; "Documented, recorded fallback" / "Fallback recorded", "Blast radius is one method".

### W2.2 — Guard tests, case fixture and regression gate

- [x] **Files (create):** `turbinesFoam/tests/test_leishman_beddoes_guard.py`, `turbinesFoam/tests/leishmanBeddoes/**` (case with `dynamicStall { active on; dynamicStallModel LeishmanBeddoes; }` and `LeishmanBeddoesCoeffs { speedOfSound 343; }`, precedent `tutorials/actuatorLine/pitching/system/fvOptions:40-58`)
- [x] **Files (modify):** `turbinesFoam/tests/conftest.py`
- **Work (design §8.2):** pure-Python reference tests `test_well_conditioned_matches_solve` (analytic solve equals the unguarded solve within round-off) and `test_singular_matrix_falls_back` (dependent matrix → `K1 = K2 = 0` with the documented warning path, no `Singular Matrix` abort); integration `test_guard_run_passes_crash_point` (the run passes `t = 0.008 s` without `FOAM FATAL ERROR: Singular Matrix`; the determinant and the path taken are recorded); register the module in `SOLVER_DRIVEN`.
- **Acceptance:** the guarded run passes the former crash point; the fallback/fit path is recorded; `test_al`/`test_asm` unchanged; no fit retuning.
- **Verification:** `cd turbinesFoam && pytest -q tests/test_leishman_beddoes_guard.py tests/test_al.py tests/test_asm.py`.
- **Traces to:** spec `dynamic-stall-singularity-guard` — "No abort on a singular fit matrix" / "Guarded run passes the former crash point"; "Documented, recorded fallback"; "Fit-input review remains out of scope" / "No fit retuning".

### W2 evidence (batch W2)

All observed on `sequana_cpu_dev` via Slurm (job 11600173, node sdumont6037),
OpenFOAM v2506 / OpenMPI 4.1.4 / GNU, GCC 14 libstdc++.

| Gate | Command | Observed |
|------|---------|----------|
| Build exit 0 + no new warnings | `cd turbinesFoam && ./Allwmake` | exit 0; no `warning:`/`error:` lines |
| Link clean | `ldd -r $FOAM_USER_LIBBIN/libturbinesFoam.so` | exit 0; no `undefined`/`not found` |
| W2 focused module | `pytest -q tests/test_leishman_beddoes_guard.py` | **7 passed** in 23.40 s |
| W2 + `test_al` + `test_asm` gate | `pytest -q tests/test_leishman_beddoes_guard.py tests/test_al.py tests/test_asm.py` | **13 passed**, 1 pre-existing `PytestUnknownMarkWarning` (`test_al.py:131`), 113.09 s |
| Full suite | `pytest -q` | **143 passed** (136 pre-W2 + 7 new), 1 pre-existing warning, 471.70 s |
| Guarded run passes the former crash point | `tests/leishmanBeddoes/rotor/Allrun` (`deltaT 0.008`, `endTime 0.016`) | `Time = 0.008` and `Time = 0.016` both reached, no `FOAM FATAL ERROR`/`Singular Matrix`; fallback recorded `... (det = 0); falling back to K1 = K2 = 0`; analytic path recorded with debug on `... analytic solve (det = 2.85151, path = well-conditioned)` |
| Well-conditioned path numerically unchanged | `pytest -q tests/test_leishman_beddoes_guard.py::test_well_conditioned_matches_solve` | analytic Cramer solve equals `numpy.linalg.solve` (LU) of the same normal-equation matrix to `rel=1e-12`/`abs=1e-14`; `K1 = -0.126573`, `K2 = 0.077436` pinned |

Commits: `e56158a` (guard), `904a201` (tests + fixture + `SOLVER_DRIVEN`
registration). The first full-suite attempt (job 11600162) ran under
`--ntasks=1` and starved `test_nacelle.py::test_parallel_master_without_stencil`
of its `mpirun -np 2` slots (OpenMPI "not enough slots"), an allocation
difference only; the gate re-run under the W1 allocation `--ntasks=4`
(job 11600173) is green. No `profileData.C` change was needed: the guard is
confined to `calcK1K2` and `test_blast_radius_one_method` pins
`normalCoeffSlope_ = A.solve()[1];` unchanged.

---

## W3 — Phase VI config/render integration

Reference: design §3 D5, §4.4, §6.1–6.4, §8.3, §9 W3, §13. Specs:
`phasevi-validation-case`, `rotational-augmentation` (docs), `phasevi-proxy-verification`
(hand-off).

### W3.1 — `case.yaml` schema for the augmentation switch and the root ablation

- [x] **Files (modify):** `turbinesFoam/validation/phaseVI/config/case.yaml`
- **Work (design §4.4, §6.1):** add `actuator.rotational_augmentation` (`active: false`, `model: DuSelig`, `a: 1`, `b: 1`, `d: 1`) and confirm `end_effects.root` as the boolean used by the ablation; the committed default stays `active: false` and `root: true`.
- **Acceptance:** the schema carries the paper defaults; the committed default renders augmentation off and root on; no case-schema migration.
- **Verification:** `cd turbinesFoam && pytest -q tests/test_phasevi_case.py`; `cd turbinesFoam && python3 validation/phaseVI/tools/generate_case.py --check`.
- **Traces to:** spec `phasevi-validation-case` — "YAML single source of truth" (all scenarios, including "Augmentation switch rendered" and "Root-effect ablation is a render-time variant").

### W3.2 — `generate_case.py` renderer and CLI toggles

- [x] **Files (modify):** `turbinesFoam/validation/phaseVI/tools/generate_case.py`
- **Work (design §6.2, §6.3):** extend `render_fv_options` (`:482-625`) with `rotational_augmentation: dict | None = None` and `root_effects: bool | None = None`; render the `rotationalAugmentation` block (`active on`, `model DuSelig`, `a/b/d 1`) at the element-key indentation (`:524-530`) in each blade subdict, **identically across the three twins**, and render `rootEffects` from `end_effects.root` (`:568`); `outputs()` (`:628-677`) passes the same values to all three variants; add CLI `--rotational-augmentation {on,off}` (default `off`) and `--root-effects {on,off}` (default from `case.yaml`); keep `check_outputs` (`:680-699`) clean. `rotationalAugmentation` is **not** in `BLADE_KEYS` (`tests/test_phasevi_case.py:63-66`) because it is identical across the twins.
- **Acceptance:** the three twins differ only in the blade element/surface keys; the augmentation block is present and identical in all three; `--check` is clean for the committed case.
- **Verification:** `cd turbinesFoam && python3 validation/phaseVI/tools/generate_case.py --check`; `cd turbinesFoam && pytest -q tests/test_phasevi_case.py` (after W3.4).
- **Traces to:** spec `phasevi-validation-case` — "YAML single source of truth" / "Render from configuration", "Configuration change re-renders", "Augmentation switch rendered"; "ALM and ASM fvOptions twins" / "Three variants differ only in blade keys", "ASM-mesh variant carries the surface keys".

### W3.3 — Committed twin renders (default: augmentation off, root on)

- [x] **Files (modify):** `turbinesFoam/validation/phaseVI/case/system/fvOptions.ALM`, `fvOptions.ASM`, `fvOptions.ASM-MESH`
- **Work (design §13):** re-render the committed default through the W3.2 renderer so the three committed twins carry the augmentation block (off) and `rootEffects on`, identical except the element/surface keys.
- **Acceptance:** committed files match the renderer; `--check` reports no stale files.
- **Verification:** `cd turbinesFoam && python3 validation/phaseVI/tools/generate_case.py --check`; `cd turbinesFoam && pytest -q tests/test_phasevi_case.py::test_generated_case_is_current`.
- **Traces to:** spec `phasevi-validation-case` — "ALM and ASM fvOptions twins" / "Three variants differ only in blade keys", "Renderer check clean".

### W3.4 — Case/render tests

- [x] **Files (modify):** `turbinesFoam/tests/test_phasevi_case.py`
- **Work (design §8.3):** extend `test_twins_differ_only_in_blade_keys` (three twins; after stripping `BLADE_KEYS` the renders and committed files are identical; the `rotationalAugmentation` block is present and identical in all three); add `test_rotational_augmentation_rendered` (`--rotational-augmentation on` renders `active on`/`model DuSelig`/`a=b=d 1`; committed default renders `active off`), `test_root_effect_ablation_rendered` (`--root-effects off` renders `rootEffects off`; committed default keeps `on`), `test_generated_case_is_current`; extend `test_config_schema` (`actuator.rotational_augmentation` exists with the paper defaults; `end_effects.root` is boolean). `case_config.py --select 7 coarse asm-mesh` is accepted and an unconfigured model is rejected.
- **Acceptance:** pure-Python and CI-safe; the twin/render/ablation/selection contracts are pinned.
- **Verification:** `cd turbinesFoam && pytest -q tests/test_phasevi_case.py`; `cd turbinesFoam && sh validation/phaseVI/scripts/runPhaseVI.sh -m alm -u 13` (prepare only; no `--run`/`--submit`).
- **Traces to:** spec `phasevi-validation-case` — "YAML single source of truth", "ALM and ASM fvOptions twins" / "Model selection accepted"; design §8.3.

### W3.5 — Phase VI README: formulation, sensitivity and ablation

- [x] **Files (modify):** `turbinesFoam/validation/phaseVI/README.md`
- **Work (design §6.4):** document the augmentation formulation (Eqs. 9–12, exact algebra from the source PDF, `a=b=d=1`), the sensitivity note (no free-parameter calibration; near-tip `fL < 0` behaviour; end-effect factor applied after the hook), the root-effect ablation as a render-time variant, and the prepared-only production boundary; point to the W4 proxy matrix.
- **Acceptance:** docs state the equations, constants and sensitivity note; no agreement better than the documented band is promised a priori; no job is submitted.
- **Verification:** docs review; `cd turbinesFoam && python3 validation/phaseVI/tools/generate_case.py --check`.
- **Traces to:** spec `rotational-augmentation` — "Formulation documentation and claim boundary"; spec `phasevi-validation-case` — "Root-effect ablation is a render-time variant".

### W3 evidence (batch W3)

All observed on the repository checkout at commit `8df345c`; the prepare gate
ran with the OpenFOAM v2506 module loaded (OpenMPI 4.1.4 / GNU, GCC 14
libstdc++).

| Gate | Command | Observed |
|------|---------|----------|
| Renderer check clean | `cd turbinesFoam && python3 validation/phaseVI/tools/generate_case.py --check` | exit 0; no stale/missing files |
| W3 focused module | `cd turbinesFoam && pytest -q tests/test_phasevi_case.py` | **18 passed** in 3.43 s (16 pre-W3 + `test_rotational_augmentation_rendered` + `test_root_effect_ablation_rendered`) |
| Phase VI pure-Python suite | `pytest -q tests/test_phasevi_case.py tests/test_phasevi_data.py tests/test_phasevi_compare.py tests/test_blade_stage.py` | **44 passed** in 4.56 s |
| Committed twins current | `test_generated_case_is_current` | committed `fvOptions.{ALM,ASM,ASM-MESH}` byte-equal their in-memory renders; `--check` clean |
| Twins differ only in blade keys | `test_twins_differ_only_in_blade_keys` | after stripping `BLADE_KEYS` the four renders and the three committed files are identical; the `rotationalAugmentation` block is present and identical in all of them (`active off`) |
| Augmentation switch rendered | `test_rotational_augmentation_rendered` | `--rotational-augmentation on` renders `active on; model DuSelig; a 1; b 1; d 1;` identically in ALM/ASM/ASM-MESH; committed default renders `active off` |
| Root-effect ablation | `test_root_effect_ablation_rendered` | `--root-effects off` renders `rootEffects off;` with `tipEffects on;` unchanged; committed default keeps `rootEffects on;` |
| Prepare-only runner gate | `sh validation/phaseVI/scripts/runPhaseVI.sh -m alm -u 13 --ranks 4` (no `--run`/`--submit`) | exit 0; `runs/alm-U13-coarse` prepared, `fvOptions.ALM` installed as `system/fvOptions`, shared coarse mesh linked; installed twin byte-equal to the U13 render (polars include normalised) with the augmentation off and `rootEffects on` |
| Config schema | `test_config_schema` (extended) | `actuator.rotational_augmentation` = `{active: false, model: DuSelig, a: 1, b: 1, d: 1}`; `actuator.end_effects.root` is a boolean; `validate_config` pins both |
| No production submission | (not invoked) | the gate is prepare-only; no `sbatch`/array submission was issued |

Commit: `8df345c` (renderer + CLI + committed twins + tests + README). The
renderer renders the `rotationalAugmentation` block identically in all three
twins at the element-key indentation, so it is deliberately **not** in
`BLADE_KEYS`; `rootEffects` is rendered from the resolved toggle while the
committed default stays `on`.

---

## W4 — Proxy verification harness

Reference: design §3 D6–D7, §7.1–7.4, §8.4, §9 W4. Spec:
`phasevi-proxy-verification`.

### W4.1 — Committed harness core (render, self-contained copies, serial chain)

- [x] **Files (create):** `turbinesFoam/validation/phaseVI/scripts/proxyRotationalAugmentation.py`, `turbinesFoam/validation/phaseVI/scripts/proxyRotationalAugmentation.sh`
- **Work (design §7.1, §7.2):** render the committed case at D/32, 0.25 rev, 7 and 13 m/s, 48 ranks, `sequana_cpu_dev` through `generate_case.py` and the committed staging path; copy each variant into a self-contained package directory (own `system/fvOptions`, own `constant/polyMesh` link, own `postProcessing/`); patch only the augmentation switch and the root setting; chain the variants **serially** (`MaxSubmit=1`), never as an array; `--check`/`--dry-run` prints the configuration (variants, speeds, mesh, revs, ranks, queue) and submits nothing; `--submit` is not implemented for production and any production queue is refused. Assert the variants differ only in the two toggles by diffing the rendered `system/fvOptions` after stripping the toggle blocks.
- **Acceptance:** exactly three variants are rendered sharing all other keys; check mode submits nothing; no production queue is ever referenced.
- **Verification:** `cd turbinesFoam && python3 validation/phaseVI/scripts/proxyRotationalAugmentation.py --check`.
- **Traces to:** spec `phasevi-proxy-verification` — "Committed 0.25-rev D/32 proxy harness" / "Harness present and runnable", "Serial dev-queue execution"; "Variant matrix and control gate" / "Three variants share all keys but the toggles".

### W4.2 — Control-reproduction gate and fail-loud criteria

- [x] **Files (modify):** `turbinesFoam/validation/phaseVI/scripts/proxyRotationalAugmentation.py`
- **Work (design §7.3):** implement the mandatory control gate — the `control` U13 integrated `cp` MUST lie within 15 % of the converged baseline `cp = −0.0411`, i.e. in `[−0.0473, −0.0349]`, before any other variant is interpreted; primary signal = integrated turbine `cp`/`ct`/torque over the short window (at U13 augmentation-on MUST make `cp`/`ct` positive; at U7 the augmentation-on + root-off ablation MUST shrink the −16 % deficit toward or inside the ±15 % band); secondary signal = spanwise `c_ref_t` sign at 30/47/63/80/95 % span (at U13 mid-span `c_ref_t ≥ +0.02`, above `DRIFT_TOLERANCE = 0.01`, versus the control's `−0.063`); any unmet criterion exits non-zero naming the offending variant/metric.
- **Acceptance:** the control gate blocks interpretation on a miss; the primary integrated signal is reported as primary and the `c_ref_t` sign as secondary; a miss fails loudly.
- **Verification:** `cd turbinesFoam && python3 validation/phaseVI/scripts/proxyRotationalAugmentation.py --check`; W4.3 `test_fail_loud`.
- **Traces to:** spec `phasevi-proxy-verification` — "Variant matrix and control gate" / "Control must reproduce the failure"; "Fail-loud success criteria" (all 3 scenarios).

### W4.3 — Proxy tests

- [x] **Files (create):** `turbinesFoam/tests/test_phasevi_proxy.py`
- **Work (design §8.4):** implement `test_variant_matrix` (exactly three variants, differing only in the augmentation switch and the root setting, with an explicit diff assertion), `test_check_mode_no_submit` (check/dry-run reports the 7/13 m/s D/32 0.25-rev configuration and calls no `sbatch`), `test_serial_chain` (variants chained serially, not submitted as an array), `test_fail_loud` (a synthetic control `cp` outside tolerance exits non-zero naming the control gate), `test_no_production_submission` (no code path invokes `sbatch` against a production queue; the suspended arrays are not referenced).
- **Acceptance:** pure-Python and CI-safe; no production submission path exists; the harness contracts are pinned.
- **Verification:** `cd turbinesFoam && pytest -q tests/test_phasevi_proxy.py`.
- **Traces to:** spec `phasevi-proxy-verification` — "Committed 0.25-rev D/32 proxy harness", "Variant matrix and control gate", "Fail-loud success criteria", "Prepared-only production boundary" / "No production submission".

### W4.4 — Docs, comparison caveat, changelog and W4 gate

- [x] **Files (modify):** `turbinesFoam/validation/phaseVI/README.md`, root `README.md`, root `CHANGELOG.md`
- **Work (design §3 D7, §6.4, §7.3, §7.4):**
  - `validation/phaseVI/README.md`: the proxy variant matrix, the control gate and fail-loud criteria, the prepared-only production boundary, and the `c_ref_t` versus measured CT definitional caveat (≈2× mismatch documented, **not fixed**; integrated `cp`/`ct`/torque primary, spanwise sign secondary).
  - Root `README.md`: the `rotationalAugmentation` key and the honest claim boundary (trend, stall onset, agreement within the documented band only).
  - Root `CHANGELOG.md`: one entry per work unit under `## [Unreleased]` in the repository's `Files:` / `Problem:` / `Fix:` format.
- **Acceptance:** the claim is limited to trend/stall onset/band agreement; the caveat is recorded and no definitional fix is applied; no production job has been submitted, cancelled or modified; the changelog follows the repository format.
- **Verification:** docs review; `cd turbinesFoam && pytest -q`; `cd turbinesFoam && python3 validation/phaseVI/scripts/proxyRotationalAugmentation.py --check`; confirm no submission (`squeue` shows no proxy/production job; suspended arrays untouched).
- **Traces to:** spec `phasevi-proxy-verification` — "Prepared-only production boundary" / "Definitional mismatch documented, not fixed"; spec `rotational-augmentation` — "Formulation documentation and claim boundary".

### W4 evidence (batch W4)

All observed on `sequana_cpu_dev` via Slurm, OpenFOAM v2506 / OpenMPI 4.1.4
/ GNU, GCC 14 libstdc++.

**Harness/render defects found and fixed while running the matrix (they made
the expected outcome unreachable before the fixes):**

1. The augmentation block was rendered **inside each blade subdict**; AFTAL
   only forwards `rotationalAugmentation` (with `rotorRadius`/`rootRadius`)
   from the **rotor-coeffs** level, so the element silently skipped the
   correction. Fixed by rendering it next to `dynamicStall` (commit `cdddfca`).
2. With the block reaching the element, the Phase VI root `cylinder`
   placeholder (only ±180°) made `zeroLiftAngleOfAttack()` interpolate an
   empty `[-10, 10]°` sub-list and **segfault** at the first force evaluation
   (reproduced: job 11600415, `correctRotationalAugmentation()` →
   `profileData::interpolate()`). Fixed by skipping the correction when the
   profile has no zero-lift reference station (commit `4ca1957`).
3. Under `sbatch` the wrapper could not locate its Python driver (Slurm
   spools the script); `PROXY_SCRIPTS_DIR` is now exported and `scontrol` is
   the fallback (commit `2b20c15`).

| Gate | Command | Observed |
|------|---------|----------|
| Build exit 0 + link clean | `cd turbinesFoam && ./Allwmake`; `ldd -r $FOAM_USER_LIBBIN/libturbinesFoam.so` | exit 0; no `undefined`/`not found` (job 11600435) |
| Focused + harness tests | `pytest -q tests/test_rotational_augmentation.py tests/test_leishman_beddoes_guard.py tests/test_phasevi_proxy.py tests/test_phasevi_case.py` | **46 passed** in 70.79 s (job 11600435) |
| Renderer check clean | `cd turbinesFoam && python3 validation/phaseVI/tools/generate_case.py --check` | exit 0; no stale/missing files |
| Proxy matrix jobs (dev queue, serial, never an array) | `sbatch proxyRotationalAugmentation.sh 13:control 13:augmentation-on` → 11600440; `13:augmentation-on-root-off 7:control` → 11600447; `7:augmentation-on 7:augmentation-on-root-off` → 11600478 | all three **COMPLETED** (9:55 / 9:10 / 10:20); all six variants written 26 rows each |
| Control gate | U13 `control` integrated `cp` | `cp = −0.044809` ∈ `[−0.0473, −0.0349]` → **PASS** |
| Secondary sign signal | U13 `augmentation-on` mid-span `c_ref_t` | `+0.084376` ≥ `+0.02` (control `−0.070378`) → **PASS** |
| Primary U7 ablation | U7 `augmentation-on + root-off` power deficit | control `−14.99 %` → ablation `−7.75 %`, shrunk and inside ±15 % → **PASS** |
| Primary U13 signal | U13 `augmentation-on` integrated `cp`/`ct` | `cp = −0.051234`, `ct = −0.017546`, both **negative** → **FAIL** |
| Harness fail-loud | `proxyRotationalAugmentation.py --evaluate` | exit **1**, naming `U13 augmentation-on primary signal: cp is not positive` and `ct is not positive` |
| No production submission | (not invoked) | no production job submitted/cancelled/modified; the suspended arrays are untouched |

**Global result (honest):** the matrix does **not** reach the expected U13
outcome. The control gate reproduces the failure, the spanwise sign flips
clearly positive (`−0.070 → +0.084`) and the U7 root-off ablation shrinks the
deficit to `−7.75 %` (inside band), but the U13 integrated `cp`/`ct` remain
negative under augmentation-on — the harness correctly fails loudly rather
than reporting success. The primary criterion is left unweakened.

---

## Requirement → task coverage

| # | Requirement (spec) | Tasks |
|---|--------------------|-------|
| R1 | `rotational-augmentation` · Du–Selig correction in the shared load chain | W1.2, W1.6 |
| R2 | `rotational-augmentation` · Equation form and paper constants | W1.2, W1.5, W1.6 |
| R3 | `rotational-augmentation` · Per-element radial geometry interface | W1.1, W1.3, W1.6 |
| R4 | `rotational-augmentation` · Additive default-off switch | W1.1, W1.2, W1.4, W1.6, W1.7 |
| R5 | `rotational-augmentation` · Single-chain inheritance by ALM, ASM and the mesh surface | W1.4, W1.6 |
| R6 | `rotational-augmentation` · Formulation documentation and claim boundary | W1.7, W3.5, W4.4 |
| R7 | `dynamic-stall-singularity-guard` · No abort on a singular fit matrix | W2.1, W2.2 |
| R8 | `dynamic-stall-singularity-guard` · Documented, recorded fallback | W2.1, W2.2 |
| R9 | `dynamic-stall-singularity-guard` · Fit-input review remains out of scope | W2.2 |
| R10 | `phasevi-proxy-verification` · Committed 0.25-rev D/32 proxy harness | W4.1, W4.3 |
| R11 | `phasevi-proxy-verification` · Variant matrix and control gate | W4.1, W4.2, W4.3 |
| R12 | `phasevi-proxy-verification` · Fail-loud success criteria | W4.2, W4.3, W4.4 |
| R13 | `phasevi-proxy-verification` · Prepared-only production boundary | W4.3, W4.4 |
| R14 | `actuator-surface-element` · Inherited blade element force chain | W1.4, W1.6 |
| R15 | `element-type-selection` · Config key plumbing | W1.3, W1.4 |
| R16 | `phasevi-validation-case` · YAML single source of truth | W3.1, W3.2, W3.4, W3.5 |
| R17 | `phasevi-validation-case` · ALM and ASM fvOptions twins | W3.2, W3.3, W3.4 |

All 17 requirements / 43 scenarios are covered.

---

## Non-goals (honest scoping)

- **No production campaign**: no production Slurm submission, cancellation or
  resubmission. The campaign stays **prepared-only** and requires explicit HPC
  authorization; the suspended production arrays are read-only baselines
  (proposal §Out of Scope; spec `phasevi-proxy-verification` "Prepared-only
  production boundary").
- **No `c_ref_t` vs measured CT definitional fix**: the ≈2× mismatch is recorded
  as a documented comparison caveat only; the proxy uses integrated
  `cp`/`ct`/torque as primary and the `c_ref_t` sign as secondary (design §3 D7;
  spec `phasevi-proxy-verification` "Definitional mismatch documented, not
  fixed").
- **No LB fit-input review**: reviewing the K1/K2 fit inputs (`cm` data,
  `cmFitExponent_`) is a separate follow-up; W2 only makes the path runnable and
  does not retune the fit (spec `dynamic-stall-singularity-guard` "Fit-input
  review remains out of scope").
- **No new polar data or free-parameter calibration**: `a=b=d=1` only; the
  static polar extension is unchanged.
- **No end-effect model change**: production stays on `Glauert`; the ported
  `Shen` tip-loss model is not activated.
- **No surface-sampled BEM**: the correction rides the shared coefficient chain;
  `actuatorSurfaceElement` and `bladeSurfaceSource` are untouched.
- **No S3 / preCICE / adapter / `fsiOmega` / `modules/*` changes**: out of scope
  and untouched.

---

## Cross-cutting verification gates (recap)

| Gate | Command | Guarded by |
|------|---------|-----------|
| Build exit 0 + link clean | `cd turbinesFoam && ./Allwmake`; `ldd -r $FOAM_USER_LIBBIN/libturbinesFoam.so` | W1.7, W2.2, W4.4 |
| Full pytest suite unchanged with default off (byte-identical gate) | `cd turbinesFoam && pytest -q` + default-off element/line/turbine CSV byte-compare | W1.7, W2.2, W4.4 |
| New C++ tests — equation/algebra via pure-Python reference, default-off byte gate | `cd turbinesFoam && pytest -q tests/test_rotational_augmentation.py` | W1.5, W1.6 |
| New C++ test — LB-guard no-abort past `t = 0.008 s` | `cd turbinesFoam && pytest -q tests/test_leishman_beddoes_guard.py` | W2.1, W2.2 |
| YAML/render `--check` clean | `cd turbinesFoam && python3 validation/phaseVI/tools/generate_case.py --check` | W3.1, W3.2, W3.3, W3.4 |
| Proxy matrix — authorized dev queue only, **no production submission** | `cd turbinesFoam && python3 validation/phaseVI/scripts/proxyRotationalAugmentation.py --check`; confirm `squeue` has no proxy/production job and the suspended arrays are untouched | W4.1, W4.2, W4.3, W4.4 |

Rollback (proposal §Rollback Plan): remove the `rotationalAugmentation` block to
return to the pre-change chain without recompiling; `git revert` the W1–W4 units
(each independently revertable) removes the correction and geometry injection
(W1), restores the LB `solve()` path (W2), removes the Phase VI switch/ablation
(W3) and the proxy harness/docs (W4). No case-schema migration is required, the
root-effect configuration is unchanged in the primary fix, and the suspended
production arrays remain read-only and untouched.

---

## Fidelity correction — Du–Selig prefactor form (post-apply, 2026-09-24)

- **Finding.** The committed code implemented Eqs. 11–12 exactly as *printed* by
  the arXiv preprint (`(1.6(c/r)^a − X)/(0.1267b + X) − 1`), which is a
  transcription error relative to the original Du & Selig (1998) formulation.
  The prefactor form `(1.6(c/r)/0.1267)·(a − X)/(b + X) − 1` is reproduced by
  NREL `AirfoilPrep.py`, BYU `CCBlade.jl`, Munduate (2002) Eq. 3.6, IOP 2024
  Eq. (3) and Yang's own later peer-reviewed review (Li/Liu/Yang 2022,
  *Energies* 15:6533, Eqs. 21–22). Evidence and severity list:
  `research-formulation-fidelity.md`.
- **Impact.** The split form inverted the drag-correction sign over most of the
  blade (`fD` negative outboard of `r/R ≈ 0.36`) and enlarged the outboard
  `fL < 0` region ~4× (`fL = 0` at `r/R ≈ 0.69` versus `≈ 0.90` in the corrected
  form).
- **Fix.** `correctRotationalAugmentation()` uses the prefactor form; `a`/`b` are
  the fraction constants, not an exponent; the exponent, `Λ`, switch semantics
  and the no-clamp decision are unchanged; no free parameter is introduced.
  Commit `ea399ae`.
- **Tests/docs updated.** Reference values (`fL ≈ 0.3394`; the split form is
  pinned as forbidden by a source check), design §1.1/§2.2 equation table plus
  fidelity note, `turbinesFoam/README.md`, `validation/phaseVI/README.md`,
  `CHANGELOG.md`.
- **Corrected proxy outcome** (build/test job `11600617`; proxy jobs `11600623`,
  `11600630`, `11600635`; independent `--evaluate` re-run reproduces it):
  - U13 `cp` mean (final row): control −0.044809 (−0.045859); augmentation-on
    **−0.000080** (−0.002094, was −0.051234/−0.052943); root-off **+0.021690**
    (+0.019482, was −0.033349/−0.035671).
  - U13 mid-span `c_ref_t`: +0.305817 (augmentation-on, was +0.084376); +0.436461
    (root-off, was +0.188596).
  - U7 `cp` final row: 0.309981 / 0.344433 / 0.373306 (was 0.309981 / 0.309268 /
    0.336636); root-off power deficit −14.99 % → +1.79 %.
  - Control gate PASS; U13 secondary sign PASS; U7 ablation PASS; U13 primary
    (`cp`/`ct` > 0) still FAIL, but the corrected value is ≈0 and within the
    short-window spread — reported unweakened.
