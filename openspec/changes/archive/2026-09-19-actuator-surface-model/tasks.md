# Tasks: Blade actuator surface model (ASM) for turbinesFoam

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 850–1050 (W1 core ≈ 450–550; W2 tutorial/tests/docs ≈ 400–500) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | W1 core → W2 tutorial/tests/docs (only if user opts out of `single-pr`) |
| Delivery strategy | single-pr |
| Chain strategy | size-exception |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: size-exception
400-line budget risk: High

> `single-pr` delivery strategy means the only compliant resolution is an explicit
> `size:exception` accepted by the maintainer before `sdd-apply`. W1/W2 below are
> the natural slice boundaries if the user instead chooses chained/stacked PRs.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Element RTS (`New` + virtual hooks + registration), `actuatorSurfaceElement.{H,C}`, `createElements` switch, `Make/files`, `tests/test_asm.py` | PR 1 | `cd turbinesFoam && pytest tests/test_asm.py tests/test_al.py tests/test_libs.py` | `./Allwmake` + real simpleFoam run via `test_asm.py` | `git revert` W1 → no `elementType` key means base class, ALM byte-identical |
| 2 | `tutorials/axialFlowTurbineASM/`, `compareALMvsASM.py`, `tests/test_aftal_asm.py` + `tests/axialFlowTurbineASMSource/`, README/CHANGELOG | PR 2 | `cd turbinesFoam && pytest tests/test_aftal_asm.py` | `./Allwmake` + real pimpleFoam run via `test_aftal_asm.py` | revert W2 → removes only new tutorial/tests/docs; core untouched |

## Mandatory corrections (encode in apply — override any stale wording in design.md)

1. **`test_asm.py` patches the template, not `system/fvOptions`.** The static case
   regenerates `system/fvOptions` at run time via `scripts/set_alpha.py`
   (`txt.format(n_elements=…, semispan=…, alpha_deg=…)`), which overwrites any
   pre-run sed of `system/fvOptions`. Patch
   `tutorials/actuatorLine/static/system/fvOptions.template` instead (or extend
   `set_alpha.py` — state which). The added plain lines
   `elementType actuatorSurfaceElement;` and `nChordwise 5;` contain no `{`/`}` and
   therefore survive `str.format`; they MUST be literal plain lines (no braces).
2. **No "Σ stripForce ≈ forceVector_" CSV assertion; no "line-CSV `f_ref_n/t`
   unchanged vs ALM".** Those columns live in the element CSV, `Σ stripForce` is
   never exported, and `f_ref_*` depend on `relativeVelocity_`, which chord-averaging
   changes. Assert instead: element-CSV exists and `fx,fy,fz`/`f_ref_t,n` are finite;
   verify chord-averaging with an explicit Python expected-value check on a known
   linear flow (chord average ≠ single-point sample); for any ALM-vs-ASM force
   comparison use a stated tolerance, or emit a debug total-force line from the
   surface element.
3. **Only the epsilon override propagates to `addTurbulence`.** Strip-wise spreading
   applies to the momentum/force path only; turbulence injection keeps the inherited
   single-point kernel (no turbulence-spreading scope).
4. **Force preservation is inherited-ALM approximate, discrete.** The shared Gaussian
   kernel is evaluated at cell centres and not renormalized; do NOT plan a discrete
   normalization of the shared kernel.

## Phase 1: Foundation — Element run-time selection (`actuatorLineElement.{H,C}`)

- [x] 1.1 In `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/actuatorLineElement.H`, add `virtual` to `calcProjectionEpsilon()` (L223), `applyForceField(volVectorField& forceField)` (L232), and `calculateInflowVelocity(const volVectorField& Uin)` (L235) — bodies unchanged (element-type-selection / "Default actuator line behavior preserved").
- [x] 1.2 In `actuatorLineElement.H`, redefine the `declareRunTimeSelectionTable` constructor signature from `(const dictionary& dict, const word& modelName)` → `(const word& name, const dictionary& dict, const fvMesh& mesh)` (L251–261) and replace `New(const dictionary&)` (L267) with `New(const word& name, const dictionary& dict, const fvMesh& mesh)`; keep `defineRunTimeSelectionTable(actuatorLineElement, dictionary)` unchanged.
- [x] 1.3 In `actuatorLineElement.C`, implement `actuatorLineElement::New`: `lookupOrDefault<word>("elementType", typeName)`; base-default branch `new actuatorLineElement(name, dict, mesh)`; else table lookup and `FatalErrorInFunction` listing `sortedToc()` on unknown type (spec "Default element type" / "Explicit element type selection" / "Unknown element type").

## Phase 2: Core — `actuatorSurfaceElement.{H,C}`

- [x] 2.1 Create `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/actuatorSurfaceElement.H`: subclass of `actuatorLineElement`; `label nChordwise_`; `vector chordPoint(label k) const`; the three overrides; `TypeName("actuatorSurfaceElement")`; ctor `(name, dict, mesh)`; dtor. GPL-3.0 header (spec "Inherited blade element force chain" — BEM chain inherited untouched).
- [x] 2.2 Create `actuatorSurfaceElement.C`: ctor base-init + `nChordwise_(dict.lookupOrDefault<label>("nChordwise", 5))`; `defineTypeNameAndDebug`; `addToRunTimeSelectionTable(actuatorSurfaceElement, dictionary)` in `namespace Foam` (spec "Actuator surface element registration" / "nChordwise default").
- [x] 2.3 Implement `calculateInflowVelocity(const volVectorField& Uin)` override: arithmetic mean of `interpolationCellPoint<vector> UInterp(Uin).interpolate(X_k, cellI)` at `X_k = position_ + (chordMount_ - f_k)·c·unit(chordDirection_)`, `f_k=(k+0.5)/nChordwise_`; reuse `reduce(sampleVelocity, minOp<vector>())` sentinel + bounding-box `findCell`; `FatalErrorInFunction` when `not (v[0] < VGREAT)` (spec "Chord-averaged inflow over equal strips" / "Single-strip element samples the chord midpoint" / "Unreachable chord sample").
- [x] 2.4 Implement `applyForceField(volVectorField& forceField)` override: one cell pass with bounding-box prefilter inflated by `sphereRadius = chordLength_ + projectionRadius`; inner loop over `nChordwise_` points; per-strip `stripForce = forceVector_/nChordwise_`; per-point `factor = exp(-(dis/epsilon)^2)/(epsilon^3·π^1.5)`; `forceField[cellI] += -stripForce·factor`; `projectionRadius = epsilon·sqrt(log(1/0.001))` (spec "Uniform strip-wise force projection" / "Force preservation is independent of strip count"; correction #3 — momentum/force path only).
- [x] 2.5 Implement `calcProjectionEpsilon()` override: `epsilon = 2·cbrt(V[findCell(position_)])·meshFactor` (mesh-only, NO chord/drag term); `reduce(epsilon, minOp<scalar>())`; fatal when `not (epsilon < VGREAT)`; `meshFactor` still from `profileData` `GaussianCoeffs` (spec "Epsilon independent of chord length" / "Fine mesh with a large chord resolves chord geometry").

## Phase 3: Integration — wiring + build registration

- [x] 3.1 In `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineSource.C` `createElements()`, after the `dict.add("writePerf", …)` at L335 add `dict.add("elementType", coeffs_.lookupOrDefault<word>("elementType", "actuatorLineElement"))` and `dict.add("nChordwise", coeffs_.lookupOrDefault<label>("nChordwise", 5))`, then replace `new actuatorLineElement(name, dict, mesh_)` (L354–357) with `actuatorLineElement::New(name, dict, mesh_)` (spec "Config key plumbing" / "No new keys present").
- [x] 3.2 In `turbinesFoam/src/Make/files`, register `fvOptions/actuatorLineSource/actuatorLineElement/actuatorSurfaceElement.C` immediately after `actuatorLineElement.C` (L6).
- [x] 3.3 Build gate: `cd turbinesFoam && ./Allwmake` exits 0, produces `libturbinesFoam.so`, no undefined symbols (proposal success criteria 1).

## Phase 4: Tests — `test_asm.py` + `test_aftal_asm.py`

- [x] 4.1 Create `turbinesFoam/tests/test_asm.py` mirroring `test_al.py`: reuse `tests/actuatorLineSource/` static case; per correction #1 patch `tutorials/actuatorLine/static/system/fvOptions.template` (plain `elementType actuatorSurfaceElement;` + `nChordwise 5;`); run; assert `Selecting finite volume options`, element CSV `foil.element0.csv` exists, finite `fx,fy,fz`/`f_ref_t,n`; Python expected-value check that chord-averaged `rel_vel_mag` differs from single-point ALM on a known flow (spec "Element CSV output" + correction #2).
- [x] 4.2 Create `turbinesFoam/tests/test_aftal_asm.py` + `turbinesFoam/tests/axialFlowTurbineASMSource/` (`getTutorialFiles.sh`, `debugSwitches` with `actuatorSurfaceElement 1`, `.gitignore`) mirroring `test_aftal.py`/`axialFlowTurbineALSource`: `sed` `endTime`→`0.003`, assert turbine + element CSVs exist and run reaches `End` (serial) / `Finalising parallel run` (parallel) (spec "Tutorial case runs and writes output" / "bounded time").

## Phase 5: Tutorial + comparison + docs

- [x] 5.1 Create `turbinesFoam/tutorials/axialFlowTurbineASM/` as a copy of `tutorials/axialFlowTurbineAL/` (read-only) with: `elementType actuatorSurfaceElement;` + `nChordwise 5;` added to the `blade1` subdict of `system/fvOptions` (blades 2/3 inherit via `$blade1`), and `system/controlDict` `endTime` truncated (e.g. `0.1`); `Allrun`/`Allclean` copied unchanged (spec "Tutorial case configured for the surface element").
- [x] 5.2 Create `turbinesFoam/tutorials/axialFlowTurbineASM/compareALMvsASM.py`: args `--alm ../axialFlowTurbineAL --asm .`; read `postProcessing/turbines/0/turbine.csv` (Cp/CT/TSR) and `postProcessing/actuatorLineElements/0/*.csv` (spanwise `cl`, `alpha_deg`, `rel_vel_mag`, `root_dist`, `c_ref_t/n`, `f_ref_t/n`); print side-by-side mean Cp/CT + spanwise tables; missing/incomplete dir → print missing input, exit nonzero (spec "Side-by-side comparison output" / "Missing run directory").
- [x] 5.3 Update `turbinesFoam/README.md`, root `README.md`, root `CHANGELOG.md`: `elementType`/`nChordwise` keys, tutorial usage, Gaussian-kernel adaptation vs the paper's 5-cell cosine kernel, HAWT-only note (CFTAL/VAWT documented as untested), fork-divergence note (proposal success criteria 7).

## Phase 6: Verification / regression gate

- [x] 6.1 Full regression: `cd turbinesFoam && ./Allwmake` and `pytest` — existing `test_libs`, `test_al`, `test_aftal`, `test_cftal` pass unchanged (ALM default path byte-identical), plus new `test_asm.py` and `test_aftal_asm.py` pass (spec "Existing case regression"; proposal success criteria 2–5).
- [x] 6.2 E2E ALM-vs-ASM: run both tutorial dirs, then `python3 tutorials/axialFlowTurbineASM/compareALMvsASM.py --alm ../axialFlowTurbineAL --asm .` produces side-by-side Cp/CT + spanwise output (proposal success criteria 6).
