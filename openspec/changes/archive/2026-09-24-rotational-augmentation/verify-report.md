# Verify Report — `rotational-augmentation`

- **Change**: `rotational-augmentation` (of-plugins)
- **Date**: 2026-09-24
- **Verified revision**: `f2c69e7` (`docs(validation): document the proxy gates,
  caveat and claim boundary`), clean working tree except untracked
  `.atl/`, `.codegraph/`, `odd/`, `openspec/`
- **Mode**: Standard (`strict_tdd: false`)
- **Overall status**: **partial** — the implementation is faithful to the delta
  specs and every functional/regression check passes; the committed proxy
  harness works and fails loudly as designed; **but the change's own primary
  U13 success criterion is not met**, and one delta-spec scenario (YAML
  augmentation switch drives the render) fails. The validation claim remains
  unearned.

---

## 1. Scope

Inspected: the 6 delta specs (17 requirements / 43 scenarios), `proposal.md`,
`design.md`, `tasks.md` (W1–W4 + evidence), `apply-progress.md`, the
`DIAGNOSIS-2026-09-21.md` evidence base, the W1–W4 implementation commits
(`git log` since `a800be1`), the proxy matrix results under
`turbinesFoam/validation/phaseVI/runs/proxy-*`, and the committed docs.

Not inspected: the non-committed source PDF `yang_arxiv_1702.02108.pdf` (the
exact algebra is taken on trust from the design's equation→code table and the
pure-Python reference test, which pins the implemented constants and exponents).

Verification ran no production submission, no cancellation and no modification
of any suspended array. Heavy checks ran on `sequana_cpu_dev` via `sbatch`.

---

## 2. Commands and observed results

### 2.1 Heavy job — dev queue

Job **`11600509`** (`sequana_cpu_dev`, node `sdumont6171`, `--ntasks=4`,
OpenFOAM v2506 / OpenMPI 4.1.4 / GNU, GCC 14 `libstdc++` prepended to
`LD_LIBRARY_PATH`). Log:
`/scratch/leahk/eduardo.donestevez/tmp/ra-verify/verify_11600509.log`.

| Gate | Command | Observed |
|---|---|---|
| Build | `cd turbinesFoam && ./Allwmake` | `ALLWMAKE_EXIT=0` |
| Link | `ldd -r $FOAM_USER_LIBBIN/libturbinesFoam.so` | `LDD_EXIT=0`; no `undefined`/`not found` |
| Focused modules (RA + LB guard + proxy + phase VI + nacelle) | `pytest -q tests/test_rotational_augmentation.py tests/test_leishman_beddoes_guard.py tests/test_phasevi_proxy.py tests/test_phasevi_case.py tests/test_nacelle.py` | **53 passed** in 37.21 s; `FOCUSED_EXIT=0` |
| Full suite | `pytest -q` | **154 passed**, 1 pre-existing `PytestUnknownMarkWarning` (`test_al.py:131`), 402.50 s; `FULL_SUITE_EXIT=0` |

Component counts: `test_rotational_augmentation.py` 13, `test_leishman_beddoes_guard.py`
7, `test_phasevi_proxy.py` 8, `test_phasevi_case.py` 18, `test_nacelle.py` 7.

An **earlier attempt (job `11600505`)** failed the focused run (8 failed,
34 passed, 1 skipped, 10 errors): `libturbinesFoam.so` needs
`GLIBCXX_3.4.32`, which is only in `/scratch/app/gcc/14.2.0/lib64`, and the job
env resolved `/scratch/app/gcc/9.3/lib64/libstdc++.so.6` first, so
`pimpleFoam` reported `Unknown fvOption type axialFlowTurbineALSource`
(the plugin never loaded). This is an **environmental** misconfiguration of the
verify harness, not a repo regression; the documented GCC 14 prepend
(`AGENTS.md`) fixed it. Job `11600505` was cancelled.

### 2.2 Light checks — login node

| Check | Command | Observed |
|---|---|---|
| Proxy check | `python validation/phaseVI/scripts/proxyRotationalAugmentation.py --check` | exit 0; prints the 7/13 m/s, D/32, 0.25-rev, 48-rank, `sequana_cpu_dev` matrix; "submitting nothing" |
| Renderer check | `python validation/phaseVI/tools/generate_case.py --check` | exit 0; no stale/missing files |
| Proxy evaluate (verification of record) | `python validation/phaseVI/scripts/proxyRotationalAugmentation.py --evaluate` | exit **1** (fail-loud), reproducing the apply matrix exactly |

Proxy evaluation (harness means over the 26 written rows; final-row `t = 0.208 s`
values in parentheses):

| Variant | U13 `cp` | U13 `ct` | U13 mid-span `c_ref_t` | U7 power deficit |
|---|---|---|---|---|
| `control` | −0.044809 (−0.045859) | −0.015346 (−0.015705) | −0.070378 | −14.99 % |
| `augmentation-on` | −0.051234 (−0.052943) | −0.017546 (−0.018131) | **+0.084376** | — |
| `augmentation-on-root-off` | −0.033349 (−0.035671) | −0.011421 (−0.012216) | +0.188596 | **−7.75 %** |

- **Control gate: PASS** (`cp = −0.044809 ∈ [−0.0473, −0.0349]`).
- **Secondary sign signal: PASS** (`+0.084376 ≥ +0.02`).
- **U7 root-off ablation: PASS** (deficit shrunk to −7.75 %, inside ±15 %).
- **U13 primary integrated signal: FAIL** (`cp` and `ct` both negative; the
  harness exits 1 naming both).

U7 final-row `cp`: control `+0.309981`, augmentation-on `+0.309268`
(≈ control), augmentation-on-root-off `+0.336636` (**+8.6 %** vs control).

---

## 3. Requirement coverage

Legend: **MET** = implementation + runtime/structural evidence; **NOT MET** =
the spec scenario's physical/observable outcome does not hold; **PARTIAL** =
implementation present but evidence or scenario incomplete.

| # | Requirement (spec) | Evidence | Verdict |
|---|---|---|---|
| R1 | `rotational-augmentation` · Du–Selig correction in the shared load chain | hook `actuatorLineElement.C:911-919` (after `lookupCoefficients()` `:911`, before `dynamicStall_->correct` `:935`); `correctRotationalAugmentation()` `:289-328`; tests `test_correction_applied`, `test_order_relative_to_dynamic_stall`, `test_pre_stall_unchanged` | MET |
| R2 | `rotational-augmentation` · Equation form and paper constants | `:300-327` implements Eqs. 9–12 with exponents `(d_/lambda)*ROverR` / `(d_/(2.0*lambda))*ROverR`; `test_du_selig_reference_values` (`fL = 0.2036`, `CL,3D = 1.213`), `test_cpp_constants_and_config_pinned`; near-tip `fL → −1/(2π)` asserted | MET |
| R3 | `rotational-augmentation` · Per-element radial geometry interface | injection `actuatorLineSource.C:214-221,366-372`; read `actuatorLineElement.C:118-121`; tests `test_radial_geometry_keys`, `test_absent_keys_keep_old_dict`, `test_parallel_matches_serial`, `test_restart_reproduces_scalars` | MET |
| R4 | `rotational-augmentation` · Additive default-off switch | block read `actuatorLineElement.C:125-159`; unknown model `FatalIOError` `:139-146`; absent-geometry warn+skip `:148-158`; `test_default_off_byte_identical`, `test_unknown_model_rejected` | MET |
| R5 | `rotational-augmentation` · Single-chain inheritance (ALM, ASM, mesh surface) | no per-model augmentation code (grep: only AFTAL/`actuatorLineSource` forward the block); `bladeSurfaceSource.C:268` consumes `elements_[e].force()`; `test_all_models_inherit` covers **ALM + ASM only** | PARTIAL (mesh surface structurally inherited, not runtime-tested) |
| R6 | `rotational-augmentation` · Formulation documentation and claim boundary | `turbinesFoam/validation/phaseVI/README.md:328-424`, root `README.md:99-106`, `CHANGELOG.md:246-339` in `Files:`/`Problem:`/`Fix:` format | PARTIAL (docs state formulation/sensitivity/boundary but **do not record the proxy outcome**, see W-2) |
| R7 | `dynamic-stall-singularity-guard` · No abort on a singular fit matrix | guard `LeishmanBeddoes.C:322-347`; `test_guard_run_passes_crash_point` passes `t = 0.008`/`0.016` with no `Singular Matrix`; `test_singular_matrix_falls_back` | MET |
| R8 | `dynamic-stall-singularity-guard` · Documented, recorded fallback | `WarningInFunction` + `Info` record `:334-347`; `test_well_conditioned_matches_solve`, `test_blast_radius_one_method` (only `LeishmanBeddoes.C` carries the fallback; `profileData.C` `A.solve()` unchanged) | MET |
| R9 | `dynamic-stall-singularity-guard` · Fit-input review out of scope | `test_no_fit_retuning` pins `cmFitExponent`/`K0_`/fallback values unchanged | MET |
| R10 | `phasevi-proxy-verification` · Committed 0.25-rev D/32 harness | `proxyRotationalAugmentation.py:65-84,321-386`; serial chain `:274-285`; `--check` exit 0; `test_check_mode_reports_proxy_and_submits_nothing`, `test_serial_chain`, `test_prepare_isolates_variant_toggles`, `test_step_selector` | MET |
| R11 | `phasevi-proxy-verification` · Variant matrix and control gate | `VARIANTS` `:80-84`; control gate `:92-94,566-580`; `test_variant_matrix`; observed control PASS | MET |
| R12 | `phasevi-proxy-verification` · Fail-loud success criteria | `check_gates` `:561-643`; harness exits 1 on the unmet U13 criterion. **Scenario "Primary integrated signal" (U13 aug-on `cp`/`ct` positive) does not hold** | **NOT MET** (harness behaviour MET; physical scenario FAIL) |
| R13 | `phasevi-proxy-verification` · Prepared-only production boundary | `assert_dev_queue` `:288-297`; `PRODUCTION_QUEUE_MARKERS` `:78`; `test_no_production_submission`; no production job submitted/cancelled/modified during this verify | MET |
| R14 | `actuator-surface-element` · Inherited blade element force chain | `actuatorSurfaceElement` does not override `calculateForce`; `test_all_models_inherit` (ALM+ASM); mesh surface consumes `element.force()` | MET (runtime mesh-surface case = R5 gap) |
| R15 | `element-type-selection` · Config key plumbing | `actuatorLineSource.C:214-221,366-372` additive injection; `test_radial_geometry_keys`, `test_absent_keys_keep_old_dict`; existing `nChordwise`/`projectElementForce` tests unchanged | MET |
| R16 | `phasevi-validation-case` · YAML single source of truth | `case.yaml:205-215`; renderer `generate_case.py:545-567,604`; **but the CLI default `off` overrides YAML `active`** (W-1) | **PARTIAL / scenario "Augmentation switch rendered" NOT MET** |
| R17 | `phasevi-validation-case` · ALM and ASM fvOptions twins | committed `fvOptions.{ALM,ASM,ASM-MESH}:41-48` identical block; `diff ALM ASM` = element keys only; `test_twins_differ_only_in_blade_keys`, `test_generated_case_is_current`; `generate_case.py --check` exit 0 | MET |

---

## 4. Central question — does the proxy confirm the hypothesis?

**No. The design's hypothesis — that Du–Selig rotational augmentation flips the
deep-stall sign at U13 — is not confirmed by the proxy matrix.** The control
reproduces the diagnosed failure (so the proxy is qualitatively valid), but
`augmentation-on` makes the integrated U13 `cp`/`ct` *more* negative
(−0.0448 → −0.0512, i.e. ≈14 % worse) while it does flip the mid-span
`c_ref_t` sign (−0.070 → +0.084). The harness fails loudly and the criterion is
left unweakened.

Assessed against the three candidate explanations:

### 4.1 Proxy limitation? — only partly, and it does not rescue the criterion

- The control gate PASSES: proxy control `cp = −0.0448` vs converged baseline
  `−0.0411` (≈9 % more negative), inside the ±15 % gate. The proxy reproduces
  the 22/09 control (`cp −0.0459`, `ct −0.0157`, mid-span `c_ref_t ≈ −0.07`), so
  it is **qualitatively valid**.
- The 0.25-rev window carries an observed ≈11 % systematic bias (control vs
  converged). The `augmentation-on` vs control difference (≈14 %) is of the same
  order, so the **magnitude** of the U13 change is near the proxy noise floor.
- However, the criterion requires `cp`/`ct` **positive**. Observed `cp = −0.051`,
  `ct = −0.018`; even the full short-window spread cannot move these to positive.
  The **sign of the failure is decisive** and not a proxy artifact.
- The spanwise element data (final row) shows the mechanism is operating-point
  driven, not a transient: the correction raises inboard `cl` and lowers outboard
  `cl`/raises outboard `cd` from the first written rows onward.

### 4.2 Formulation/constants? — yes, this is the dominant mechanism (not a coding defect)

The implementation is exactly the literal Du–Selig Eqs. 9–12 with `a=b=d=1`
(`actuatorLineElement.C:300-327`), as the spec mandates ("Near-tip behavior is
recorded, not clamped"). Recomputing `fL`/`fD` from the committed geometry
(`data/geometry/phaseVI_blade.csv`) and the U13 operating point (`Λ = 0.946`),
against the observed element changes:

| `r/R` | `c/r` | `fL` (Eq. 11) | `fD` (Eq. 12) | Δ raw `CL` | Δ `cd` | `c_ref_t` control → aug |
|---|---|---|---|---|---|---|
| 0.453 | 0.278 | **+0.195** | −0.059 | +0.417 | −0.006 | −0.074 → **+0.108** |
| 0.585 | 0.192 | +0.071 | −0.122 | +0.152 | +0.053 | −0.124 → −0.108 |
| 0.706 | 0.142 | **−0.006** | −0.161 | −0.006 | +0.064 | −0.100 → −0.159 |
| 0.828 | 0.107 | −0.061 | −0.189 | −0.108 | +0.059 | −0.135 → −0.215 |
| 0.961 | 0.078 | −0.105 | −0.211 | −0.139 | +0.050 | −0.058 → −0.120 |

- Inboard (`r/R ≲ 0.65`): `fL > 0`, lift rises, `c_ref_t` becomes clearly
  positive — the intended effect.
- `fL` crosses zero near `r/R ≈ 0.71` (design §1.1 predicted ≈0.69) and is
  **negative outboard**; `fD` is negative outboard, so Eq. 10 *raises* drag.
- The outboard elements carry the largest torque lever arm, so their combined
  lift loss + drag gain **outweighs** the inboard gain on the integrated `cp`.
  The design's own §2.4 anticipated `fL < 0` outboard but the proposal's success
  criterion assumed the inboard gain would dominate; the proxy shows it does not.
- `CD,0` semantics (`zeroLiftDragCoeff()` = drag at `CL = 0`, not `α = 0`;
  `profileData.C:294`) is a documented mismatch but immaterial in deep stall
  (`cd,2D − CD,0 ≈ 0.5`), so it is **not** the driver.
- **Conclusion**: the U13 failure is a consequence of the chosen (spec-mandated,
  literal, unclamped) formulation, not of an implementation error. Whether the
  paper intends an outboard `fL` clamp or a different exponent is not resolvable
  from the committed repo (the source PDF is non-committed) and is a follow-up
  question.

### 4.3 Honest result: the root/end-effect treatment is at least co-dominant

- `rootEffects off` alone is the effective lever: the U7 ablation shrinks the
  power deficit from −14.99 % to **−7.75 %** (inside ±15 %), and at U13 it brings
  `cp` from −0.0448 to −0.0333 and mid-span `c_ref_t` from −0.070 to +0.189.
- But **even `augmentation-on + root-off` leaves the U13 integrated `cp`
  negative** (−0.033). No single tested lever (augmentation, root-off, or both)
  flips the U13 integrated sign.
- This matches the 22/09 diagnosis finding 2 ("rootEffects off … does not flip
  the sign") but contradicts the proposal's framing that missing augmentation is
  "the primary fix" that would flip the U13 sign.

**Plain statement**: what is established is that the correction is implemented
faithfully and is *locally* effective (inboard lift, mid-span sign), and that
the root/end-effect treatment is a large lever. What is **not** established is
that Du–Selig augmentation alone — or combined with root-off — resolves the U13
integrated failure. The change's central hypothesis is **unconfirmed**; the
validation claim remains unearned.

---

## 5. Findings

### CRITICAL

- **C-1 — U13 primary success criterion not met; validation claim unearned.**
  The delta spec `phasevi-proxy-verification` scenario "Primary integrated
  signal" requires U13 `augmentation-on` `cp`/`ct` positive; observed `cp =
  −0.051234`, `ct = −0.017546` (harness means), both negative. The proposal's
  Success Criteria list the same item unchecked. The harness correctly fails
  loudly (`--evaluate` exit 1) and the criterion was not weakened. Evidence:
  §2.2, §4, `proxyRotationalAugmentation.py:582-599`. No production campaign was
  run, so no power-curve claim exists; the change must not be represented as
  validating the Phase VI fix.

### WARNING

- **W-1 — the YAML augmentation switch does not drive the render (spec scenario
  "Augmentation switch rendered" fails).** `generate_case.py` defaults
  `--rotational-augmentation` to `off` (`:798-804`) and then unconditionally
  overwrites the YAML value (`:825-826`: `augmentation["active"] =
  args.rotational_augmentation == "on"`). Empirically, a YAML copy with
  `actuator.rotational_augmentation.active: true` and no CLI flag renders
  `active off`. `runPhaseVI.sh` never passes the flag (`runPhaseVI.sh:194,217`),
  so the standard runner cannot enable augmentation from YAML at all. Contrast
  `--root-effects` (`:805-811,827-829`), whose `None` default correctly falls
  back to YAML (verified: `root: false` → `rootEffects off`). The committed
  default is `active: false`, so no committed run is affected, and the proxy
  harness passes the value explicitly through `render_fv_options`. The renderer
  *function* honours YAML when called with `rotational_augmentation=None`; the
  CLI path does not.
- **W-2 — committed docs do not record the proxy outcome.** The honest claim
  boundary is generic ("trend, stall onset, band agreement"), but
  `turbinesFoam/validation/phaseVI/README.md:328-424`, root `README.md:99-106`
  and `CHANGELOG.md:246-339` never state that the U13 primary criterion failed
  and that augmentation made the integrated U13 `cp` worse. The honest outcome
  lives only in `tasks.md`/`apply-progress.md` (working artifacts). A reader of
  the committed package cannot learn the U13 sign flip was not achieved.
- **W-3 — mesh-backed surface inheritance not runtime-tested.** Spec
  `rotational-augmentation` "All models reflect the correction" names ALM, ASM
  **and ASM-mesh**; `test_all_models_inherit` covers only ALM + ASM. The mesh
  surface is structurally guaranteed (`bladeSurfaceSource.C:268` consumes
  `elements_[e].force()`, no per-model augmentation code), so the risk is low,
  but the runtime scenario is unverified.

### SUGGESTION

- **S-1 — design.md is stale on two W4 deviations.** `design.md:1047` still
  lists `profileData.{H,C}` as "Unchanged" and §4.4/§6.2 still describe the block
  at "element-key indentation", whereas the implementation renders it at the
  rotor-coeffs level (`generate_case.py:550-567`) and added
  `hasZeroLiftReference()` (`profileData.C:899-914`). The deviations are
  documented in `apply-progress.md` and `CHANGELOG.md`; the planning artifact was
  not updated.
- **S-2 — "default-off byte-identical to a pre-change run" is demonstrated
  internally, not against a pre-change binary.** `test_default_off_byte_identical`
  compares "block absent" vs "`active off`" element CSVs and asserts the default
  path equals the static polar (non-circular). Given the additive `if
  (rotationalAugmentationActive_)` gate and the unchanged default constructor
  path, this is adequate, but it is not a literal pre-change byte compare.
- **S-3 — proxy control `c_ref_t` reference constant is stale.**
  `MIDSPAN_C_REF_T_CONTROL_REF = -0.063` (`proxyRotationalAugmentation.py:100`)
  is the 22/09 diagnosis value; the observed proxy control mid-span is
  −0.0704. Informational only (not a gate threshold).

---

## 6. Gaps and unearned claims

- **No production campaign.** The change is prepared-only; the production
  arrays were not submitted, cancelled or modified. No power-curve or
  validation claim is earned. The proposal already scopes this out.
- **The U13 proxy criterion failed** (§4, C-1). The U7 root-off result
  (−7.75 %, inside band) is **proxy-window evidence at 0.25 rev**, not a
  converged validation, and the proxy control at U7 is already −14.99 %
  (inside the band), so the "shrink" is measured against a non-converged
  baseline.
- **Out-of-scope items correctly left unfixed**: the `c_ref_t` vs measured CT
  definitional ≈2× mismatch (documented caveat, no fix); the LB K1/K2 fit-input
  review (guard only); no new polar data / free-parameter calibration;
  end-effect model stays `Glauert`; S3/preCICE/adapter/`fsiOmega` untouched.
- **ASM-mesh runtime inheritance** (W-3) and the **pre-change byte compare**
  (S-2) are verification gaps, not implementation gaps.

---

## 7. What is and is not verified

**Verified (runtime or structural proof):**
- Build exits 0 and the library links cleanly (`ldd -r`, no undefined symbols).
- The full suite (154 passed) and the focused modules (53 passed) pass on the
  dev queue at `f2c69e7`; the only warning is pre-existing.
- Eqs. 9–12 are implemented with the pinned constants/exponents and reproduce
  the hand sample and the near-tip limit; the correction is applied in the
  shared chain after the static lookup and before dynamic stall/added
  mass/end-effect.
- Additive default-off: no block → no correction, no injected geometry; the
  default path equals the static polar; unknown model fails loudly.
- Radial geometry injection matches the comparison tool's `r/R` identity;
  parallel and restart reproduce the scalars.
- The LB determinant guard removes the `Singular Matrix` abort, preserves the
  well-conditioned fit, records the fallback, and is confined to `calcK1K2`.
- The proxy harness is committed, serial, self-contained, prepared-only, and
  fails loudly; its evaluation reproduces the apply matrix exactly.
- Committed twins differ only in blade keys and carry an identical
  augmentation block; `generate_case.py --check` is clean.
- No production job was submitted, cancelled or modified.

**Not verified / not established:**
- That Du–Selig augmentation (alone or with root-off) flips the U13 integrated
  sign or makes `cp`/`ct` positive — **it does not**.
- Any converged Phase VI validation claim (no production campaign).
- The mesh-backed surface receiving the correction at runtime (structural only).
- A literal pre-change byte comparison of default output.
- That the YAML augmentation switch drives the render through the CLI/runner.

---

## 8. Recommended next work

1. **Do not represent this change as validating the Phase VI fix.** Record the
   U13 failure in the committed docs (W-2).
2. **Scoped follow-up change** for the physics: decide the outboard treatment
   (the literal `fL < 0` / `fD < 0` behavior vs the paper's intent, and the
   root/end-effect lever) and re-run the proxy; the current evidence says no
   single tested lever flips U13, so the follow-up must combine levers or revisit
   the formulation. A converged run requires explicit HPC authorization.
3. **Fix W-1** in a follow-up apply: make the `--rotational-augmentation` CLI
   default fall back to the YAML value (as `--root-effects` does) and/or expose
   the toggle through `runPhaseVI.sh`, so the delta-spec scenario holds.
4. **Archive** (`sdd-archive`) may proceed to record the actual state; the code
   deliverable is complete, but the archive must carry this report and must not
   claim a validation success.

---

## 9. Verification-of-record note

The proxy matrix CSVs under
`turbinesFoam/validation/phaseVI/runs/proxy-{U7,U13}-{control,augmentation-on,augmentation-on-root-off}/postProcessing/`
were re-read and re-evaluated during this verify; the harness evaluation
(exit 1, the four gate results in §2.2) matches the apply-progress record. The
matrix is accepted as the verification of record, with the caveats in §4.

---

# Re-verification after the fidelity fix

> This section is the **current** verification of record. Everything above this
> line is the first-verify record at revision `f2c69e7` and is kept unchanged for
> history.

- **Change**: `rotational-augmentation` (of-plugins)
- **Date**: 2026-09-24
- **Verified revision**: `5325ecc` (`docs(validation): record the Du-Selig
  fidelity correction and the corrected proxy results`); parent fix `ea399ae`.
  Working tree clean except untracked `.atl/`, `.codegraph/`, `odd/`,
  `openspec/` (the change artifacts themselves are untracked).
- **Mode**: Standard (`strict_tdd: false`)
- **Overall status**: **partial** — the fidelity correction is implemented,
  tested and documented, and first-verify finding **W-2 is resolved**; but the
  change's own U13 primary criterion (`augmentation-on` `cp`/`ct` **positive**)
  still fails — now by a near-zero margin — so **C-1 is not resolved as a pass**.

## 10. Scope of this re-verification

Inspected: the corrected source (`actuatorLineElement.{H,C}`), the corrected
reference test, `research-formulation-fidelity.md`, the 6 delta specs (17 reqs /
43 scenarios), the committed docs (`README.md`, `turbinesFoam/README.md`,
`turbinesFoam/validation/phaseVI/README.md`, `CHANGELOG.md`), `design.md`, and
the corrected proxy runs under
`turbinesFoam/validation/phaseVI/runs/proxy-*`. Heavy checks ran on
`sequana_cpu_dev` via `sbatch`. No production job was submitted, cancelled or
modified; no source/test/spec/design edit was made by this verify.

## 11. Primary criterion — committed harness `--evaluate` (real output)

Command:

```sh
/scratch/leahk/eduardo.donestevez/venv/bin/python \
  turbinesFoam/validation/phaseVI/scripts/proxyRotationalAugmentation.py --evaluate
```

Exit: **1**. `stderr`:

```text
FAIL: U13 augmentation-on primary signal: cp is not positive (cp=-0.00008)
FAIL: U13 augmentation-on primary signal: ct is not positive (ct=-0.00003)
```

`stdout` (the `evaluate.json` payload, means over the 26 written rows; final row
`t = 0.208 s` in parentheses):

| U13 variant | `cp` mean (final row) | `ct` mean (final row) | mid-span `c_ref_t` |
|---|---|---|---|
| `control` | −0.044809 (−0.045859) | −0.015346 (−0.015705) | −0.070378 |
| `augmentation-on` | **−0.000080** (−0.002094) | **−0.000027** (−0.000717) | **+0.305817** |
| `augmentation-on + root-off` | **+0.021690** (+0.019482) | +0.007428 (+0.006672) | +0.436461 |

Gate results:

- **Control gate: PASS** — `cp = −0.044809 ∈ [−0.0473, −0.0349]` (converged
  baseline `−0.0411`); the control value is **byte-for-byte the same as the
  pre-fix run** in §2.2 (−0.044809 / −0.015346).
- **Secondary sign signal: PASS** — mid-span `c_ref_t = +0.305817 ≥ +0.02`
  (was +0.084376 pre-fix).
- **U7 root-off ablation: PASS** — control deficit `−14.99 %`, ablation
  `+1.79 %`, inside the ±15 % band; U7 final-row `cp` control / aug-on /
  root-off = `0.309981 / 0.344433 / 0.373306` (was `0.309981 / 0.309268 /
  0.336636`).
- **U13 primary integrated signal: FAIL** — `cp` and `ct` are strictly negative
  (`−0.000080`, `−0.000027`), so the harness exits 1 and the criterion is
  reported unweakened.

**Is C-1 resolved?** **No, not as a pass.** The original C-1 evidence
(`cp = −0.051234`, `ct = −0.017546`) is superseded: the fidelity correction
moved the augmentation-on values from clearly negative to **≈ 0** (a ~640×
reduction in magnitude), and the `augmentation-on + root-off` variant now has
positive `cp`/`ct`. But the spec scenario `phasevi-proxy-verification` "Primary
integrated signal" requires the `augmentation-on` `cp`/`ct` to be positive, and
they are not. The fail-loud gate is unchanged and still red; the validation claim
remains unearned (no production campaign).

## 12. The fidelity fix itself

### 12.1 Code matches the primary-source form

`correctRotationalAugmentation()` (`actuatorLineElement.C:376-379`) now computes:

```cpp
const scalar fL = (1.0/(2.0*pi))
    *((1.6*cOverR/0.1267)*((a_ - qL)/(b_ + qL)) - 1.0);
const scalar fD = (1.0/(2.0*pi))
    *((1.6*cOverR/0.1267)*((a_ - qD)/(b_ + qD)) - 1.0);
```

This is term-for-term the original Du & Selig (1998) prefactor form recommended
by `research-formulation-fidelity.md` §7 and now stated in the delta spec
`rotational-augmentation` Requirement "Equation form and paper constants". The
exponents `(d_/lambda)*ROverR` / `(d_/(2.0*lambda))*ROverR` (`:370-371`), the
hook order (`:972-980`, after `lookupCoefficients()`, before
`dynamicStall_->correct`), the constants `a=b=d=1` (`:135-137`) and the no-clamp
decision are unchanged.

### 12.2 Reference test values — analytic recomputation

`test_du_selig_reference_values` now pins the prefactor form. Recomputing the
hand sample in the spec (`c/r = 0.271`, `R/r = 2.27`, `Λ = 0.95`, `a=b=d=1`):

- `x_L = (1/0.95)·2.27 = 2.3895`; `q_L = 0.271^2.3895 = 0.04420`.
- `fL = (1/2π)·[(1.6·0.271/0.1267)·((1 − 0.04420)/(1 + 0.04420)) − 1]
  = 0.3394` → **matches the test's `0.3394`** (spec says ≈ 0.34).
- `CL,3D = 0.73 + 0.3394·(3.1 − 0.73) = 1.534` → **matches the test's `1.534`**
  (spec says ≈ 1.53). The rejected split form gives `fL = 0.2036`,
  `CL,3D = 1.213` — the values the test now explicitly distinguishes.

The near-tip limit (`fL → −1/(2π)`) and the "no clamp" assertions are retained.
The reference values are correct.

### 12.3 In-code / in-repo documentation (explicitly requested)

The `correctRotationalAugmentation()` header comment
(`actuatorLineElement.C:291-356`) and the declaration comment
(`actuatorLineElement.H:255-263`) cover, accurately:

| Requested item | Present | Location |
|---|---|---|
| Formulation (Eqs. 9–12) | ✅ | `.C:295-298`, `.H:255-259` |
| Primary source | ✅ Du & Selig 1998, AIAA-98-0021 | `.C:321-322` |
| Independent cross-checks | ✅ NREL AirfoilPrep.py, BYU CCBlade.jl, Munduate 2002, IOP 2024, Li/Liu/Yang 2022 | `.C:325-329` |
| arXiv mis-print note | ✅ split form marked a transcription error; points to `research-formulation-fidelity.md` | `.C:331-338` |
| Constants | ✅ `a=b=d=1` (no calibration) | `.C:315`, `.C:135-137` |
| Outboard behavior | ✅ `fL → −1/(2π)`, `fD` thin tip band, deliberately **not** clamped; α-taper is a separate change | `.C:340-347` |
| Geometry inputs | ✅ `c/r`, `R/r`, `Λ` symbols | `.C:309-314` |

The same content is reflected in `turbinesFoam/README.md`,
`turbinesFoam/validation/phaseVI/README.md` (formulation, prefactor, cross-checks,
mis-print, sensitivity, corrected outcome), root `README.md:99-106`,
`CHANGELOG.md` entry 12 (`Files:`/`Problem:`/`Fix:` + "Measured outcome"), and
`design.md` §1.1/§2.2. Documentation is present and accurate.

## 13. Finding status after the fidelity fix

| ID | First-verify finding | Status now | Evidence |
|---|---|---|---|
| **C-1** | U13 primary criterion not met; validation claim unearned | **Still open (downgraded)** | `--evaluate` exit 1; `cp = −0.000080`, `ct = −0.000027`. Original mechanism (transcription error) fixed; residual is ≈0 |
| **W-1** | YAML `rotational_augmentation.active` does not drive the CLI render | **Still open** | `generate_case.py:801` default `off`; `:826` unconditionally overwrites YAML. Reproduced in memory: YAML `active true` + no CLI flag renders `active off;`; the render *function* with `rotational_augmentation=None` renders `active on;`. `--root-effects` (`:808`) still correctly falls back |
| **W-2** | Committed docs did not record the proxy outcome | **RESOLVED** | `CHANGELOG.md` entry 12 "Measured outcome"; `phaseVI/README.md` "Corrected-form proxy outcome" table; both state the criterion still fails and augment-on was clearly negative → ≈0 |
| **W-3** | ASM-mesh inheritance not runtime-tested | **Still open** | `test_all_models_inherit` covers ALM + no-mesh ASM only; `test_blade_stage.py` is an STL-staging contract, not an augmentation run. Mesh surface remains structurally guaranteed (`bladeSurfaceSource` consumes `element.force()`) |
| **S-1** | `design.md` stale on two W4 deviations | **Still open** | `design.md:1072` still lists `profileData.{H,C}` as "Unchanged" although `hasZeroLiftReference()` exists (`profileData.C:899`, `.H:378`); `design.md:655` still says the block renders "at the same indentation as the element keys" although it renders at the rotor-coeffs level (`generate_case.py:550-567`) |
| **S-2** | Default-off byte-identity demonstrated internally, not vs a pre-change binary | **Still open (low risk)** | Control metrics are byte-identical to the pre-fix run; the fix lives inside the `if (rotationalAugmentationActive_)` gate (`:977`), so default-off is preserved structurally |
| **S-3** | Proxy control `c_ref_t` reference constant stale | **Still open** | `MIDSPAN_C_REF_T_CONTROL_REF = -0.063` (`proxyRotationalAugmentation.py:100`) vs observed control mid-span `−0.070378`. Informational (not a gate) |

New observations from this re-verify:

- **N-1 (SUGGESTION).** The U13 primary gate is a strict `> 0` with no noise
  tolerance. The corrected `−8.0e-5` is smaller than the 0.25-rev window's
  observed ≈11 % systematic bias, so the fail-loud gate cannot distinguish
  "≈0 within noise" from a genuine sign failure. Left unweakened by design; a
  converged campaign is what would settle it.
- **N-2 (environment note, not a code finding).** The full suite intermittently
  segfaults in the OpenMPI openib BTL at `MPI_Init` on `sdumont6060`
  (job `11600689`: 4 × `test_parallel`; job `11600707`: 1 ×
  `test_aftal_asm.py::test_parallel`). All four `test_parallel` tests pass in
  isolation on the same node (job `11600698`, 4 passed). No code regression.

## 14. Build / link / tests (dev queue)

Job **`11600689`** (`sequana_cpu_dev`, node `sdumont6060`, `--ntasks=4`,
OpenFOAM v2506 / OpenMPI 4.1.4 / GNU, GCC 14 `libstdc++` prepended):

| Gate | Command | Observed |
|---|---|---|
| Build | `cd turbinesFoam && ./Allwmake` | `ALLWMAKE_EXIT=0` |
| Link | `ldd -r $FOAM_USER_LIBBIN/libturbinesFoam.so` | `LDD_EXIT=0`; no `undefined`/`not found` |
| Focused modules (RA + LB guard + proxy + phase VI + nacelle) | `pytest -q tests/test_rotational_augmentation.py tests/test_leishman_beddoes_guard.py tests/test_phasevi_proxy.py tests/test_phasevi_case.py tests/test_nacelle.py` | **53 passed** in 94.36 s; `FOCUSED_EXIT=0` |
| Full suite | `pytest -q` | **150 passed, 4 failed** (all `test_parallel`, MPI-init segfault); `FULL_SUITE_EXIT=1` |

Full-suite reconciliation (jobs `11600698`, `11600707`): the 4 `test_parallel`
failures passed in isolation (4 passed), and a clean full-suite re-run scored
**153 passed, 1 failed** (same MPI flake). All 154 tests pass when the node's
MPI stack does not fault; the focused modules (which include the RA, LB-guard,
proxy and phase-VI suites) pass 53/53 in the same allocation. Light checks:
`proxyRotationalAugmentation.py --check` exit 0; `generate_case.py --check`
exit 0.

## 15. Requirement coverage (6 delta specs, 17 reqs / 43 scenarios)

Updated from §3 against the corrected implementation:

- **Fully compliant (40/43 scenarios).** `rotational-augmentation` (the
  hand-sample scenario now matches the prefactor form: `fL ≈ 0.34`,
  `CL,3D ≈ 1.53`), `dynamic-stall-singularity-guard` (5/5),
  `actuator-surface-element` (3/3), `element-type-selection` (5/5),
  `phasevi-proxy-verification` (8/9), `phasevi-validation-case` (7/8).
- **PARTIAL (1/43).** `rotational-augmentation` "All models reflect the
  correction": ALM + no-mesh ASM runtime-tested, ASM-mesh structural only
  (W-3).
- **NOT MET (2/43).**
  - `phasevi-proxy-verification` "Primary integrated signal" — U13
    `augmentation-on` `cp`/`ct` are not positive (≈0). **C-1**.
  - `phasevi-validation-case` "Augmentation switch rendered" — the CLI/runner
    path does not let the YAML switch drive the render. **W-1**.

Finding counts: **0 CRITICAL-code / 1 CRITICAL-validation (C-1, downgraded)**,
**2 WARNING (W-1, W-3)**, **3 SUGGESTION (S-1, S-2, S-3)** + N-1.

## 16. What is and is not verified (re-verify)

**Verified:**
- `./Allwmake` exits 0 and the library links cleanly (`ldd -r`, no undefined
  symbols) at `5325ecc`.
- Focused modules 53/53; full suite stable at 153–154 passed once the transient
  node MPI fault is excluded.
- The `fL`/`fD` code matches the primary-source prefactor form; the reference
  test values recompute correctly (`fL = 0.3394`, `CL,3D = 1.534`); the
  requested in-code and in-repo documentation is present and accurate.
- The committed `--evaluate` harness runs on the corrected runs, reproduces the
  corrected matrix, passes the control gate, the U13 secondary sign signal and
  the U7 root-off ablation, and fails loudly on the U13 primary signal.
- Control output is unchanged from the pre-fix run; default-off is preserved.

**Not verified / not established:**
- That U13 `augmentation-on` `cp`/`ct` are positive — **they are ≈0, still
  negative** (C-1).
- Any converged Phase VI validation claim (no production campaign; U7/U13 are
  0.25-rev proxy-window evidence only).
- The mesh-backed surface receiving the correction at runtime (structural only,
  W-3).
- That the YAML augmentation switch drives the render through the CLI/runner
  (W-1).
- The α-taper robustness safeguard — remains a **separate change**, per the
  fidelity research; no clamp was invented.

## 17. Re-verification verdict

**partial.** The fidelity correction is correct, tested and documented, and W-2
is resolved; the mechanism behind C-1 is fixed and the U13 augmentation-on signal
moved from clearly negative to ≈0. But the spec's own primary criterion — U13
`augmentation-on` `cp`/`ct` positive — still fails (strictly, by ≈8e-5), the
harness exits 1, and the validation claim remains unearned. W-1 and W-3 remain
open; S-1/S-2/S-3 remain stale/low-risk.

---

> **W-1 follow-up applied (2026-09-24, §8 recommendation 3).** The CLI
> `--rotational-augmentation` now falls back to the YAML `active` when the flag
> is absent and `runPhaseVI.sh` forwards it only when requested, so the
> `phasevi-validation-case` "Augmentation switch rendered" scenario now holds.
> W-1 above remains the finding-of-record at revision `5325ecc`; **C-1 is
> unchanged and still open.** See `apply-progress.md` "Follow-up fix — W-1".
