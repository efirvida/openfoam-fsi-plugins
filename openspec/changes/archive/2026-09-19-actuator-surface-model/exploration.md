# Exploration: Blade actuator surface model (ASM) for turbinesFoam

Change: `actuator-surface-model` — project: `of-plugins` — date: 2026-09-18
Scope: `turbinesFoam/` only. Reference: Yang & Sotiropoulos, arXiv:1702.02108v4 (Sec. 2.1).
Input context: `odd/tasks/actuator-surface-blades.md` (prior organic exploration; not an SDD artifact).

## Current State

### turbinesFoam composition (verified against source)

- `fv::option` RTS → `turbineALSource` (`PtrList<actuatorLineSource> blades_`, `bladesDict_` from user `blades` subdict) →
  `axialFlowTurbineALSource` / `crossFlowTurbineALSource` (build one `bladeSubDict` per blade, `new actuatorLineSource`, `axialFlowTurbineALSource.C:75-291`, `crossFlowTurbineALSource.C:65-248`) →
  `actuatorLineSource` (`PtrList<actuatorLineElement> elements_`; `createElements()` interpolates `elementGeometry` and does
  `new actuatorLineElement(name, dict, mesh_)`, `actuatorLineSource.C:354`) →
  `actuatorLineElement` (the physics core, `actuatorLineElement.C`, 1181 lines).
- Element force pipeline (`calculateForce`, `actuatorLineElement.C:686-809`): planform normal →
  `calculateInflowVelocity` (single point or `velocitySampleRadius`/`nVelocitySamples` circle, `.C:367-457`) →
  spanwise velocity subtraction → relative velocity + Re → AoA → optional flow-curvature correction →
  `lookupCoefficients()` (profileData cl/cd/cm) → optional dynamic stall → optional added mass →
  end-effect factor → lift+drag `forceVector_` (force per unit density). `applyForceField` (`.C:336-364`)
  spreads `forceVector_` with a 3D Gaussian over a sphere of radius `chordLength_ + projectionRadius`;
  `calcProjectionEpsilon` (`.C:201-273`) = `max(max(0.25·c, cd·c/2), 2·cbrt(V)·meshFactor)`.
- Config plumbing: `actuatorLineSource::createElements` copies `velocitySampleRadius`, `nVelocitySamples`,
  `dynamicStall`, `flowCurvature`, `addedMass` from the line/blade `coeffs_` into each element dict
  (`.C:312-335`). AFTAL/CFTAL inject the user blade subdict **unchanged** and only add turbine-level keys
  (`freeStreamVelocity`, `fieldNames`, `profileData`, `velocitySampleRadius`, `nVelocitySamples`, `selectionMode`, `cellSet`, `writeForceField`).
  A new per-element key therefore reaches every element with **zero turbine-class changes** — verified in both AFTAL and CFTAL.
- CSV output: element-level `postProcessing/actuatorLineElements/.../{name}.csv` (`createOutputFile`/`writePerf`),
  line-level `postProcessing/actuatorLines/.../{name}.csv` (area-weighted), turbine-level `postProcessing/turbines/.../{name}.csv` (Cp/Cd/Ct + per-blade).
- RTS state (key finding): `actuatorLineElement` declares an element RTS table
  (`declareRunTimeSelectionTable`, `actuatorLineElement.H:250-261`) and defines it (`defineRunTimeSelectionTable`,
  `.C:40`), but `New` is **declared only — never implemented** and **no `addToRunTimeSelectionTable` registration exists**;
  `createElements` hard-codes the concrete class. Verified the same holds in upstream
  turbinesFoam master (GitHub API: no `actuatorSurfaceElement` directory, no `New` definition). The element RTS is vestigial.
- Virtual surface: only `createOutputFile`, `addSup` (×3), `addTurbulence`, destructor are virtual.
  The methods the ASM must change — `read`, `calculateForce`, `calculateInflowVelocity`, `applyForceField`,
  `calcProjectionEpsilon`, `lookupCoefficients`, `writePerf` — are **non-virtual**.
- Tests (no C++ unit framework; pytest integration/E2E only, `config.yaml`): `test_libs.py` (build smoke),
  `test_al.py` (static AL 2D/3D/parallel/pitching/alpha-sweep; greps `log.simpleFoam`, reads CSVs),
  `test_aftal.py` (HAWT serial/parallel; asserts CSV values incl. hardcoded `max(crn)=1.063`, `max(crt)=0.429`,
  `max(frn)=37.179`, `max(frt)=7.150`, `0.4<cp<1.0`, `0.5<cd<1.0`), `test_cftal.py`. Tutorials
  (`actuatorLine/{static,pitching}`, `axialFlowTurbineAL`, `crossFlowTurbineAL`) are copied into
  `tests/` via `getTutorialFiles.sh`; shared polars in `tutorials/resources/foilData`.
- Constraints: OpenFOAM v2506 module (Int64, SDumont recipe in AGENTS.md); single `libturbinesFoam` via wmake;
  integration-only verification; 400-line review budget; delivery strategy `single-pr` (preflight).

### What the ASM change needs (paper Sec. 2.1, as mapped in `odd/tasks/actuator-surface-blades.md`)

- Per radial element: `nChordwise` chord-line strips (midpoint rule at `X_k = position_ + (chordMount_ - f_k)·c·unit(chordDirection_)`,
  `f_k=(k+0.5)/n` — formula verified consistent: mid-chord lands at +0.25c toward TE from the quarter-chord point).
- Chord-averaged inflow (`u_x`, `u_theta`): arithmetic mean of `interpolationCellPoint` samples at the `X_k`.
- Uniform chordwise force: each strip carries `forceVector_/nChordwise`, spread by its own Gaussian;
  total force preserved by construction (normalized kernel).
- Surface-mode epsilon: mesh-based only (`2·cbrt(V)·meshFactor`), never chord-based (a chord threshold would
  prevent resolving the chord on fine meshes — the point of the model).
- One cell pass per element with an inner chord-point loop (cost ~×nChordwise candidates).
- Out of scope (per input doc): nacelle ASM, the paper's 5-cell cosine kernel (reuse Gaussian, document adaptation),
  root-loss model, MEXICO geometry from the paper (not in it).

### Zormpa 2024 (validation source 1) — feasibility notes

- Paper is CC BY (open access; attribution required). Two rotors: **MEXICO** (D=4.5 m, λ=10, U∞=10 m/s, Re75%≈0.6e6)
  and **Sch15b** tidal (D=20 m, λ=4.8, U∞=4.5 m/s, Re75%≈27e6). Setup: URANS (PISO, k-ω SST with updated coefficients),
  OpenFOAM v2006, snappyHexMesh hexcore, Nx=160/180 cells-per-diameter, domain 15D×8D×8D (~1.2% blockage),
  100 cosine-distributed collocation points/blade, spherical Gaussian kernel, Nε ∈ {2,4,8}, Nt ∈ {100..1600} steps/rotation.
- Reference data: MEXICO experimental data (public, extensively studied); polars derived from blade-resolved RANS
  (paper Appendix B, tabular — would need transcription into `profileData` format).
- Run cost: research-scale (MEXICO Nt=1600 × Nε sweep); even a single MEXICO case is minutes-to-hours at Nx=80-160 →
  **not CI-suitable**; usable as an on-demand validation case with truncated settings.
- Methodological trap (verified from text): the paper used RANS-BR polars with **no tip correction** → a validation case
  using these polars must disable turbinesFoam end-effects (Glauert/Shen), or double-count.
- Relevance to ASM: the paper's **LAS (line average sampling, Jost et al.)** samples flow at multiple points along the
  chord line outside the kernel — the direct ancestor of ASM chord-averaged inflow; Fig. A1 shows CP/CT convergence vs
  number of line-sampling points (N=8 typical), evidence for choosing `nChordwise`.

### HPC offshorewindpark (validation source 2) — feasibility notes

- Westermost Rough: 35 × Siemens SWT-6.0-154 (154 m rotor, 102 m hub), pimpleFoam LES,
  `turbulentDigitalFilterInlet`, grids 12M or 103M cells, 5000 steps (~2500 s) per direction, 6 directions for
  validation vs Nygaard et al. 2020 experimental power data (`validation/Allvalidate.py` ships in-repo).
- **Uses `fcgaleazzo/turbinesFoam` fork** (power-in-W output, dynamic inflow response) — dict/behavior compatibility
  with **our upstream-based vendored fork is unverified**; our unmodified fork may not reproduce their runs.
- License: **CC BY-SA 4.0** — vendoring case files into the GPL-3.0 tree mixes licenses (BY-SA→GPLv3 is one-way
  compatible with attribution, but legally subtle); prefer linking/attribution + optional external fetch script.
- Scale: HPC-class (12M-103M cells × 5000 steps × 6 dirs) — never CI. ALM-only: no ASM variant exists in the case.

## Affected Areas

- `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/actuatorLineElement.{H,C}` — virtualize 3 hooks
  (`calculateInflowVelocity`, `applyForceField`, `calcProjectionEpsilon`) + implement `New` (options b/d); or add
  surface branches inline (option a).
- `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/actuatorSurfaceElement.{H,C}` — NEW class
  (options b/d): chord-averaged sampling, per-strip spreading, mesh-only epsilon, `nChordwise` config.
- `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineSource.C` — `createElements` selects element type via
  `New` and passes `elementType`/`nChordwise` into element dicts (options b/d only).
- `turbinesFoam/src/Make/files` — register the new `.C`.
- `turbinesFoam/tutorials/axialFlowTurbineASM/` — NEW tutorial (AFTAL copy + ASM blade config + truncated controlDict).
- `turbinesFoam/tests/test_asm.py`, `tests/test_aftal_asm.py` — NEW integration tests; `tests/axialFlowTurbineASMSource/`
  case dir; `test_al.py`/`test_aftal.py`/`test_cftal.py` must pass unchanged (regression gate).
- `turbinesFoam/tutorials/resources/foilData/` — MEXICO polars if Zormpa validation is packaged (option V-A).
- `turbinesFoam/README.md`, root `README.md`, root `CHANGELOG.md` — config keys, tutorial, validation references, licensing/attribution.
- Untouched: `turbineALSource`, AFTAL/CFTAL turbine classes, profileData, dynamicStallModels, addedMassModel, interpolation utils.

## Approaches

### 1. In-place extension of `actuatorLineElement` (input doc's option)

`surfaceModel` bool + `nChordwise` label; branch inside `calculateInflowVelocity` (chord-average), `applyForceField`
(strip loop), `calcProjectionEpsilon` (mesh-only). Default off → ALM path byte-identical.

- Pros: smallest diff (~250-350 lines); zero new files; no RTS/`createElements` churn; CSV/tests untouched;
  AFTAL/CFTAL pass-through works immediately; lowest migration risk.
- Cons: answers the user's architecture concern poorly — the surface model is bolted onto ALM code
  ("metiendo mano al código de ALM"); each future flow-sampling method (Zormpa CPS/VAS/LAS) adds another branch set
  to the same three methods (flag sprawl); nacelle ASM later bloats the same class; `actuatorLineSource` name becomes a misnomer.
- Effort: Low-Medium. Extensibility: poor (branch proliferation). Nacelle/ASM later: poor.

### 2. Polymorphic element: virtualized hooks + RTS `New` + `actuatorSurfaceElement` subclass (recommended)

Complete the RTS the class already declares: implement `actuatorLineElement::New(dict)` (type from dict, default
`actuatorLineElement`), add `addToRunTimeSelectionTable(actuatorSurfaceElement, dictionary)`, virtualize only the
three differing methods (`calculateInflowVelocity`, `applyForceField`, `calcProjectionEpsilon`) with unchanged
default bodies, switch `createElements` to `actuatorLineElement::New(dict)` passing `elementType` (default
`actuatorLineElement`) and `nChordwise`. `actuatorSurfaceElement` derives and overrides the three hooks; the whole
BEM chain (`calculateForce`, coefficients, dynamic stall, added mass, end effects, CSV) is inherited untouched.

- Pros: ALM path untouched except 3 virtual keywords + one construction-site switch (default behavior identical);
  ASM lives in its own class (~250-350 lines new code); matches upstream's intended design (RTS already declared there);
  future sampling methods (CPS/VAS/LAS) become additional element types or a sampler strategy later — no ALM churn;
  nacelle ASM slots in as another subclass; `addTurbulence` automatically uses the surface epsilon override.
- Cons: touches the shared construction path (`createElements`) — regression risk for every existing case, mitigated
  by defaulting to `actuatorLineElement` and the existing integration suite as gate; `elementType` key replaces the
  input doc's `surfaceModel` bool (docs/decision change); diff slightly larger than option 1 (~450-550 lines).
- Effort: Medium. Extensibility: good. Migration risk: low (additive config; default path identical).

### 3. Shared force engine + pluggable sampling/projection strategies (full refactor)

Extract BEM force computation into a base/engine; make flow sampling (CPS/VAS/LAS/chord-average) and force projection
(line vs surface) strategy objects; rebuild the element as a thin composition.

- Pros: cleanest long-term architecture; directly maps the Zormpa sampling taxonomy to interchangeable strategies;
  nacelle = another strategy set; testable in isolation (if a C++ unit framework existed).
- Cons: largest diff (~800+ lines); refactors the entire element pipeline including the shared ALM path;
  regression risk highest with only integration tests as a safety net (no C++ unit tests, `config.yaml`); diverges
  further from upstream (harder future syncs); exceeds the 400-line budget by a wide margin even chained.
- Effort: High. Extensibility: excellent. Migration risk: highest.

## Validation / Tutorial Strategy Options

- **V-A — Zormpa MEXICO as ALM validation case (truncated, on-demand).** Package `validation/zormpa-mexico/`:
  snappyHexMesh case at Nx≈80 (or reuse AFTAL-case scale), MEXICO geometry (chord/twist: public MEXICO dataset or
  digitize Fig. 4), polars transcribed from Appendix B, **endEffects off** (paper used RANS-BR polars, no tip
  correction), run a few rotations at Nt≥400, postprocess Cp/CT vs MEXICO experimental data and the paper's
  published values (CC BY, cite). Never CI. Also exercises the LAS-adjacent chord-averaged sampling as a bridge to ASM.
  Effort: Medium (polars transcription + geometry sourcing are the cost drivers; research phase must confirm a public
  data source — do not assume the paper's tables are machine-readable).
- **V-B — HPC offshorewindpark as documented external ALM reference.** Do NOT vendor (CC BY-SA × GPL-3.0 mixing;
  fcgaleazzo-fork incompatibility unverified; HPC-scale cost). Document in README: link, attribution, methodology
  (farm power vs Nygaard 2020), and the fork-compatibility caveat. Optional `scripts/getExternalCase.sh` fetch helper
  outside the repo. Effort: Low (docs only).
- **V-C — dedicated in-repo `axialFlowTurbineASM` tutorial (mandatory).** AFTAL copy with
  `elementType actuatorSurfaceElement; nChordwise 5;` in the blade subdict, truncated controlDict, ALM-vs-ASM
  comparison script (run both dirs, side-by-side Cp/CT/spanwise CSV), `tests/test_aftal_asm.py` + `tests/test_asm.py`.
  This is the CI-level coverage and user-facing documentation of the new config; the external cases cannot replace it.
  Effort: Medium.

Recommended package: **V-C (in-scope, mandatory) + V-A (in-scope if polars/geometry sourcing is feasible — else
follow-up) + V-B (docs-only, in-scope)**.

## Recommendation

**Option 2 (polymorphic element)** with the **V-C + V-A + V-B validation package**.

Rationale: the user's concern is architectural, and the evidence supports option 2 over option 1: the class was
*designed* to be extended this way (RTS + virtuals already declared, both here and upstream), the three hooks are
exactly the methods whose behavior differs, and virtualization with unchanged defaults keeps the ALM path
byte-identical for every existing case (guarded by the full existing pytest suite). Option 1 works but entrenches
the very coupling the user flagged. Option 3 is over-engineered for a vendored fork with no unit-test safety net.

Rough work decomposition (not tasks — see sdd-tasks):

- **W1 — Core surface mode (option 2):** virtualize 3 hooks; implement `New`; `actuatorSurfaceElement.{H,C}`
  (chord-average sampling, per-strip spreading, mesh-only epsilon, `nChordwise`); `createElements` → `New` +
  `elementType`/`nChordwise` pass-through; `Make/files`; `tests/test_asm.py` (static AL case, ALM-vs-ASM CSV checks);
  regression: full pytest + build. ~450-550 lines.
- **W2 — ASM tutorial + tests + docs:** `tutorials/axialFlowTurbineASM/` + comparison script +
  `tests/test_aftal_asm.py` + `tests/axialFlowTurbineASMSource/` + README/CHANGELOG. ~400-500 lines.
- **W3 — Validation packaging:** `validation/zormpa-mexico/` (geometry, polars, setup, postprocessing vs experiment)
  + README section + HPC offshorewindpark external reference docs (V-B). ~300-400 lines (mostly data/scripts).
- Forecast: W1+W2 ≈ 850-1050 changed lines → **exceeds the 400-line review budget**; natural PR slices [W1], [W2],
  [W3] if chaining is allowed. Flag for sdd-tasks/apply; the preflight `single-pr` strategy may need an exception.

## Open Questions

1. **Delivery shape (BLOCKING):** change is ~850-1050 changed lines vs the 400-line policy under `single-pr`.
   Chained PRs [W1 core] → [W2 tutorial] → [W3 validation], or explicit `size:exception`? Orchestrator/user decision before apply.
2. **Zormpa MEXICO packaging in scope? (BLOCKING for W3 sizing):** requires polars transcription (Appendix B) and
   geometry sourcing (public dataset vs Fig. 4 digitization). Confirm in-scope now vs follow-up once the research
   phase confirms a data source. If unfindable, drop to Cp/CT-vs-publication comparison only.
3. **Config key (NON-BLOCKING):** replace the input doc's `surfaceModel` bool with `elementType actuatorSurfaceElement;`
   + `nChordwise` (explicit type, OpenFOAM-idiomatic, scales to CPS/VAS/LAS). Confirm.
4. **CFTAL/VAWT ASM (NON-BLOCKING):** the element change is turbine-agnostic; keep HAWT-only (input doc scope) and
   document "works in principle, untested" for CFTAL? 
5. **nChordwise default (NON-BLOCKING):** input doc says 5; Zormpa Fig. A1 shows CP/CT converged by N=8 at
   quarter-chord. Keep 5 or move to 8?

## Risks

- Shared-path regression: virtualization + `createElements` switch touch the ALM construction path; gate = full
  existing pytest suite + `test_libs.py`; default `elementType actuatorLineElement` preserves behavior.
- Review budget: W1+W2 exceed 400 lines (forecast above); unresolved delivery shape blocks apply.
- No C++ unit tests: correctness of chord-point geometry/chord-average verified only via integration CSVs and the
  ALM-vs-ASM comparison; consider a Python-side expected-value check in `test_asm.py` for the chord-averaged velocity
  of a known flow.
- MPI: chord points may fall on different processors than `position_`; reuse the existing `reduce(minOp)` sentinel
  pattern per sample; decide fatal-vs-clamp when a sample lands outside the mesh (existing code fatals — keep that).
- Epsilon semantics: mesh-only epsilon on the existing tutorial mesh may make ASM ≈ ALM (kernel ~ cell size);
  document that ASM benefits require finer mesh, and that kernel overlap needs Nε≥1-2.
- Tip-correction double-count in the MEXICO validation case (RANS-BR polars ⇒ endEffects off) — documented trap.
- Licensing: Zormpa CC BY (attribution/citation); HPC case CC BY-SA × GPL-3.0 — keep external (link + attribution),
  no vendoring without legal review.
- Fork divergence: new element class + `elementType` increase divergence from upstream turbinesFoam (manual syncs);
  acceptable, document in README fork notes.
- v2506 API constraints apply to new code (`get<word>`, no `List` from iterators, `Pstream` — see AGENTS.md).

## Ready for Proposal

**Yes.** Evidence base is complete: code map verified against source, RTS/vestigial-`New` finding confirmed
(upstream included), config pass-through verified in AFTAL+CFTAL, both validation sources assessed with
feasibility constraints. The proposal must resolve open questions 1 (delivery shape) and 2 (MEXICO packaging
scope) — tell the user these two decisions gate the apply phase.