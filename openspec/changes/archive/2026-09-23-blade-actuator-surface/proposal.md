# Proposal: Blade actuator surface model over a real imported blade mesh (S2)

## Intent

`turbinesFoam` now has a delivered blade ASM (`actuator-surface-model`,
archived 2026-09-19) and a delivered nacelle ASM with a reusable surface
sampler and geometry pipeline (`nacelle-actuator-surface`, S1, archived
2026-09-20). The blade ASM's "surface" is still a **flat chord line per radial
element**, spread over `nChordwise` strips with the Gaussian projection
(`actuatorSurfaceElement.C:51-205`); no blade geometry is committed anywhere
(`geometry/PROVENANCE.md:13` defers it to S2, MEXICO-flavoured). This change
(slice **S2**) is the blade counterpart of S1: it applies the BEM blade load
over a **real imported blade triangulation**, validated on the NREL Phase VI
rotor, and extends the validation to a three-way comparison
**ALM vs ASM (no mesh) vs ASM (real mesh)**.

**Formulation being implemented (explicit).** The paper's blade ASM is
chord-line based: "the blade geometry is represented by a surface formed by the
chord lines at different radial locations" (arXiv:1702.02108v4 Sec. 2.1), force
per unit area `f(X) = (L + D)/c` uniform chordwise (Eq. 17), spread by the
smoothed kernel (Eq. 18). Replacing the chord lines with an imported
triangulated surface is an **extension of the paper's blade ASM in the S1
direction** (the nacelle model already used "the actual surface",
Sec. 2.2) — not a literal equation port. The BEM content (Eqs. 1-16), the
element force chain, dynamic stall, end effects and added mass are unchanged.

The change must stay additive: with no blade surface configured, the ALM and
no-mesh ASM paths are byte-identical, no new state enters the restart path, and
the queued Phase VI jobs are **not** touched (verified live in `squeue`;
exploration §7). S3 (preCICE FSI) stays deferred; the S1 kinematics seam
(`angleDeg`/`omega` override, `turbineALSource.C:315-345,430-432`) is the
integration point for rotation.

## Scope

### In Scope

- **Per-blade imported-surface force distributor (C++)**: read the committed
  blade STL (`triSurface`), use triangle centroids as nodes with areas and
  station metadata, map each BEM element's force to its surface patch, spread
  with the S1 kernel (Eq. 18), aggregate into the blade `force_`/`forceField_`,
  per-station and optional per-node CSV, MPI handling, and an **additive
  suppression of the element strip spread** so the blade force is applied
  exactly once.
- **Shared surface-sampling base**: extract the generic assets from S1's
  `nacelleSurfaceSampler` (triSurface load, centroid node set, `cellSize`,
  `kernel`, distribution loop, MPI reduce patterns) into a frame- and
  force-model-agnostic base; `nacelleSurfaceSampler` keeps its behavior
  (regression-gated).
- **Kernel/width selection** on the surface distributor: paper cosine default
  (S1, support 2.5), Gaussian mode matching the no-mesh ASM
  (`2*cbrt(V)*meshFactor`) so the geometry effect can be isolated from the
  kernel/width confound.
- **Deterministic blade geometry**: commit the S809 profile coordinates
  extracted from the locally verified Somers PDF with recorded method and
  hashes; a pure-Python structured loft generator producing one wetted-surface
  binary STL covering the full 26-station span (root cylinder/transition and
  S809), metadata with per-node `radial_station`/`chord_fraction`, PROVENANCE,
  deterministic `--check`.
- **Phase VI integration**: a third model twin (`fvOptions.ASM-MESH`), the
  `asm-mesh` model entry in `case.yaml`/renderer/`--select`/runner, STL staging
  into run dirs, the three-way compare extension, a prepared-only Slurm array,
  README updates.
- **Tests + docs**: C++-driven integration tests, pure-Python geometry and
  case-tooling tests, the formulation statement, the sub-grid caveat, the
  MEXICO naming resolution, and `CHANGELOG.md` entries.

### Out of Scope

- **Surface-sampled BEM** (exploration approach 2.2): the surface does not
  recompute BEM loads from per-node inflow. Distribution-only (2.1) keeps the
  three-way comparison interpretable; 2.2 is a future change.
- **No-mesh ASM behavior changes**: `actuatorSurfaceElement`'s chord-averaged
  inflow and Gaussian strips stay as delivered; the new kernel option lives on
  the surface distributor only.
- **S3 / preCICE / adapter / `fsiOmega`**: no coupling, no point-cloud mesh
  source, no adapter changes. The S1 `positions()`/`forces()` contract gains a
  second (rotating) implementation, nothing more.
- **MEXICO geometry or validation**: the active `mexico-validation` change owns
  its own data and component naming; this change only resolves the shared
  pipeline's naming policy and does not modify that change.
- **Mesh ladder or physics closures**: no finer meshes, no wall resolution, no
  root-loss model, no CFTAL/VAWT support.
- **HPC execution**: no submission, cancellation or resubmission. The ASM-mesh
  arrays are prepared-only until explicit authorization; queued ALM/ASM arrays
  are read-only baselines.

## Capabilities

> This section is the CONTRACT between proposal and specs phases.
> Existing capabilities in `openspec/specs/`: `actuator-surface-element`,
> `element-type-selection`, `axial-flow-turbine-asm-tutorial`,
> `nacelle-surface-source`, `nacelle-validation-case`,
> `phasevi-data-provenance`, `phasevi-run-and-compare`,
> `phasevi-validation-case`, `surface-sampling-contract`,
> `time-derived-kinematics`, `turbine-geometry-pipeline`.

### New Capabilities

- `blade-surface-source`: the per-blade distributing source over an imported
  blade triangulation — STL load, node areas and per-node station/chord
  metadata, element-force-to-patch mapping, additive strip suppression,
  selectable kernel/width, rotating-frame lockstep with the blade transform
  calls, per-station/per-node CSV, SI `positions()`/`forces()` contract.
- `blade-geometry-generation`: the deterministic blade component generator —
  committed S809 coordinates with extraction provenance, pure-Python structured
  loft over the full station span, binary STL + metadata (populated
  `radial_station`/`chord_fraction`) + PROVENANCE, byte-identical `--check`.

### Modified Capabilities

- `turbine-geometry-pipeline`: the blade component is populated; component
  naming becomes rotor-qualified (`phaseVI_blade`) instead of the reserved
  `blade0/1/2`; a non-gmsh builder entry is added to the generator registry.
- `surface-sampling-contract`: a second implementation exists on a **rotating**
  frame (blade-local body frame, azimuth-dependent positions), and the stable
  ordering requirement must be stated against rotation.
- `element-type-selection`: a new additive per-element key
  (`projectElementForce`, default true) is plumbed through `createElements` so
  the surface distributor can suppress strip projection.
- `phasevi-validation-case`: a third model twin (`fvOptions.ASM-MESH`) with the
  surface keys; the "twins differ only in blade element keys" requirement is
  extended to three models.
- `phasevi-run-and-compare`: `-m asm-mesh` model, STL staging, three-way
  comparison inputs, per-station surface-output conversion, prepared-only array.
- `phasevi-data-provenance`: the S809 profile coordinates become a committed
  Phase VI derived dataset under the same provenance rules.

## Approach

### Decision 1 — C++ shape and double-counting control

**Chosen: per-blade `bladeSurfaceSource` owned by the blade
`actuatorLineSource`, over a shared surface-sampling base, with an additive
`projectElementForce` suppression key.**

- Ownership: the blade subdict already reaches `actuatorLineSource` unchanged
  (`axialFlowTurbineALSource.C:90,252,276`), and rotation/pitch/translate/
  setSpeed forwarding already lives there (`actuatorLineSource.C:577-647`).
  The distributor is constructed from `surfaceGeometry` inside the blade
  source, follows the same transform calls as the elements, computes the
  node-to-element partition once per blade (patch areas sum to the blade area),
  distributes `elements_[i].force()` after the element loop into the blade
  `forceField_`/`force_`, and exposes a node `moment()` so AFTAL's torque/CP
  includes the distributed loads. AFTAL's `addSup` and rotation paths are
  untouched.
- Reuse: extract the generic parts of `nacelleSurfaceSampler` into a reusable
  base; the nacelle force model and its static body frame stay in S1's classes.
  This is a **base extraction**, not exploration's option C (a single source
  parameterized by force model and frame): the two concrete owners keep their
  own physics, only geometry/kernel/distribution is shared.

  | S1 asset | S2 use | Note |
  |---|---|---|
  | `triSurface` load, centroid node set/normals/areas, stable order | Reuse | `nacelleSurfaceSampler.C:201-220` |
  | `cellSize` + `kernel` + `returnReduce` MPI patterns | Reuse | `.C:269-292,374-463` |
  | Distribution loop (Eq. 18), CSV/`cellSetOption`/RTS skeleton | Reuse as pattern | `nacelleSurfaceSource.C:163-209,280-431` |
  | `interpolateVelocity` (Eq. 7) | Not used initially | Distribution-only keeps the element's chord-averaged inflow; stays where the design places it |
  | `positions()/forces()/normals()/areas()` contract shape | Reuse, frame changes | Blade body frame rotates; no new restart state |
  | Nacelle force model (Eqs. 19, 21-23), static body frame | Not reused | Blade load comes from the BEM elements |
- Double-counting control (the high risk): `surfaceGeometry` on the blade
  subdict activates the distributor; `createElements()` then injects
  `projectElementForce false` into every element dict (default `true`).
  `actuatorLineElement::addSup` guards its `applyForceField(...)` call
  (`actuatorLineElement.C:1074-1075`, `:1113-1114`) with that flag, so
  `calculateForce` and `writePerf` still run — the element CSV and the public
  `force()` stay valid for the distributor to consume — but the strip
  projection never reaches the field. Key absent → default `true` →
  byte-identical ALM/ASM. Gate: the full existing suite plus a new
  partition-of-unity test (summed field force equals the summed element forces,
  not twice) and a default-path test confirming the key absent still projects
  the strip force.
- Alternatives: **new element type** (`bladeSurfaceElement`, exploration 1B) —
  no suppression switch needed, but the per-element patch partition must be
  recomputed consistently in 50 elements with shared geometry caching, which
  puts the partition/double-count hazard in many objects and scatters the S3
  sampling contract; kept as the documented fallback. **Generalized source**
  (exploration 1C) — rejected: the BEM-distribution and direct-forcing models
  share nothing beyond geometry and kernel, and a broad refactor re-opens the
  archived-and-tested nacelle code for no functional gain.

### Decision 2 — Blade geometry pipeline and S809 provenance

**Chosen: extend the shared `turbinesFoam/geometry/` pipeline with a
rotor-qualified `phaseVI_blade` component, generated by a deterministic
pure-Python structured loft, covering the full wetted span; commit S809
coordinates from the verified Somers PDF.**

- Naming/ownership (MEXICO conflict resolved): retire the `blade0/1/2`
  reservation, which encoded the un-sourced MEXICO per-blade assumption
  (`geometry/PROVENANCE.md:13`, `geometry/README.md:54`, `makeGeometry.py:86-88`).
  The first populated blade component is Phase VI-specific (`phaseVI_blade`);
  blades of a rotor are identical, so **one STL** serves both Phase VI blades
  (azimuth is runtime) and a future MEXICO blade is a separate component
  (`mexico_blade`) owned by the `mexico-validation` change. The reserved-name
  rejection message, README table, PROVENANCE source row and the assertions in
  `tests/test_nacelle_data.py:217-219,292-301` are updated accordingly.
- Generator: a pure-Python structured loft (fixed section point counts, fixed
  loft triangulation, reuse of `canonical_triangles`/`write_binary_stl`/fixed
  header/recomputed normals, `makeGeometry.py:194-219`) gives byte-identical
  regeneration **and** exact per-node `radial_station`/`chord_fraction`
  metadata, and adds no gmsh dependency for blades. A gmsh loft is rejected:
  meshing a twisted, tapered, thin blade yields uncontrolled triangle counts
  and sliver/non-manifold risk at the trailing edge, and S1's canonicalization
  only reorders triangles — it cannot repair a non-reproducible tessellation.
  A builder registry lets `nacelle` stay gmsh-driven while `phaseVI_blade` is
  Python-driven.
- Coverage: the loft spans all 26 committed stations (`phaseVI_blade.csv`,
  r = 0.5083 m → 5.029 m), including the circular root/transition stations
  (r ≤ 0.8835 m), because 8 of the 50 blade elements are cylinder elements
  (`case/system/fvOptions.ASM:63`); an airfoil-only surface would strand their
  force once the strips are suppressed. The surface is the **wetted surface
  only** (no root/tip caps); tip force zeroing, end effects, and the inboard
  `chord_mount` transition stay BEM-side. Section construction (cylinder →
  transition → S809) and trailing-edge closure are design details.
- S809 coordinates: extract Table 2 from the locally verified
  `phasevi_research/verified/s809_somers_nlr.pdf` (NREL/SR-440-6918) with a
  recorded, repeatable method (PyMuPDF — `pdftotext` is absent on this host),
  cross-check against at least one independent source, and commit
  `s809_somers_nlr.csv` + PROVENANCE (PDF sha256, table id, extraction
  recipe/tool version/date, committed sha256). The convenient local text dump
  is not treated as authoritative until cross-checked.
- Alternatives: **Phase VI-local generator** (exploration 3C) — contradicts
  the S1 spec/README intent and duplicates the machinery a future MEXICO blade
  would use; **gmsh loft** (exploration 3B) — zero generator refactor but the
  determinism/tessellation risk above; **per-blade `blade0/1/2` STLs** —
  byte-identical duplicates and drags the naming conflict forward.

### Decision 3 — Phase VI integration shape and delivery slicing

**Chosen: third model variant `-m asm-mesh` (twin `fvOptions.ASM-MESH`) in the
existing package; STL staged into each run dir; new array prepared-only.**

- The twin preserves the existing contract that models "differ only in the
  blade element keys" (`generate_case.py:484-505`): ASM-mesh = ASM element keys
  + `surfaceGeometry` (+ optional kernel keys) in each blade subdict. The
  run-id becomes `asm-mesh-U<speed>-<mesh>`, `case_config.py:585` whitelist and
  `runPhaseVI.sh:80-83` accept the new model, and `--nchordwise` remains
  ASM-family-only.
- STL staging: the deterministic committed STL is copied into the run dir (e.g.
  `constant/triSurface/phaseVI_blade.stl`) and referenced by a case-relative
  path, so runs/restarts are self-contained; a pure-Python test asserts the
  staged copy matches the committed sha256.
- Compare: `comparePhaseVI.py` gains the third input directory and a
  surface-output converter that maps per-station surface forces to the existing
  `c_ref_n`/`c_ref_t` conventions and r/R stations, producing one three-way
  table with the existing bands and sign gate.
- Slurm: a new prepared-only ASM-mesh array is generated; nothing is submitted.
  The live `phaseVI-prod` (`11597195_[2-8]`, `11597349_[9-13]`),
  `phaseVI-stage3` and `phaseVI-stage3-d64` arrays are baselines and must not
  be disturbed.
- Alternative: `--surface-geometry` option on `-m asm` — one fewer top-level
  model but a second configuration axis, extra run-id suffixes and permutation
  growth; rejected as less legible for the comparison campaign.
- **Delivery slicing**: the session strategy is `single-pr`; S1 set the
  precedent that oversized work units can land under an explicit
  `size:exception` (W1/W2/W4a/W4b). The forecast below (~1550–2450 lines)
  exceeds the 400-line budget, so under `single-pr` **apply requires an
  explicit `size:exception` before it starts**; the W1→W4 chain is prepared as
  the alternative and every unit is independently testable and revertable.

## Work-Unit Plan

Each unit ends with its own tests and docs, has a single reviewable purpose,
and reverts cleanly on its own. Line counts are change totals (additions +
deletions, including moves).

| Unit | Deliverable | Likely PR | Est. lines | Focused verification | Rollback boundary |
|------|-------------|-----------|------------|----------------------|-------------------|
| W1 | Blade surface distributor C++: shared sampler base extraction, `bladeSurfaceSource`, `surfaceGeometry`/`projectElementForce` plumbing, rotation lockstep, kernel/width, CSV, `Make/files`, integration tests, turbinesFoam README | PR 1 | ~600–900 | `cd turbinesFoam && pytest -q tests/test_blade_surface.py tests/test_nacelle.py tests/test_nacelle_data.py tests/test_libs.py`; `./Allwmake`; `ldd -r`; partition-of-unity + double-count integration checks | `git revert` W1: removes the new source tree and the base extraction; `nacelleSurfaceSampler`/element/source restored; default paths byte-identical |
| W2 | Blade geometry: S809 coordinates + PROVENANCE, `phaseVI_blade` Python loft builder, STL + metadata, builder registry, pipeline tests, README/PROVENANCE updates | PR 2 | ~400–600 | `cd turbinesFoam && pytest -q tests/test_blade_data.py tests/test_nacelle_data.py`; `makeGeometry.py --check --component phaseVI_blade` byte-identical, non-destructive | `git revert` W2: removes the blade component artifacts, builder and test updates; nacelle component untouched |
| W3 | Phase VI third variant: `fvOptions.ASM-MESH`, `case.yaml`/renderer, runner + STL staging, `--select` whitelist, three-way compare, prepared-only Slurm, case/compare tests, README/CHANGELOG | PR 3 | ~400–600 | `cd turbinesFoam && pytest -q tests/test_phasevi_case.py tests/test_phasevi_data.py tests/test_phasevi_compare.py`; `generate_case.py --check`; `runPhaseVI.sh -m asm-mesh -u <speed>` renders/prepares without `--run`/`--submit` | `git revert` W3: removes twin/staging/compare/array additions; `-m asm` and `-m alm` behavior unchanged |
| W4 | Performance measurement gate and, only if the gate demands it, bounded-distribution hardening: per-`addSup` timing/candidate-count instrumentation, prepared measurement run, mesh-tree/stencil candidate query | PR 4 (conditional) | ~150–350 | Instrumented run shows nodes, candidate cells/node and seconds per `addSup`; measurement run prepared (executed only with authorization) | `git revert` W4: removes instrumentation (and any optimized query); W1 default distribution unchanged |

`tests/test_blade_surface.py` and `tests/test_blade_data.py` are new names
(design may place them in the existing test files). C++ has no unit framework;
the C++ path is verified through solver-driven integration tests plus
pure-Python expected-value/geometry checks, as in S1.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | W1 ~600–900 · W2 ~400–600 · W3 ~400–600 · W4 ~150–350 — **total ~1550–2450** |
| 400-line budget risk | **High** |
| Chained PRs recommended | **Yes** |
| Suggested split | W1 → W2 → W3 → W4 |
| Delivery strategy | `single-pr` (session strategy — recorded, not decided here) |
| Size exception | Required before apply if `single-pr` stands (S1 precedent: W1/W2/W4a/W4b) |

```
Decision needed before apply: Yes
Chained PRs recommended: Yes
400-line budget risk: High
```

## Validation Program

- **Variants**: three models on the identical case configuration —
  `alm` (`elementType actuatorLineElement`), `asm` no mesh
  (`elementType actuatorSurfaceElement; nChordwise 5`), `asm-mesh`
  (that twin + `surfaceGeometry` + `projectElementForce false`). All other
  keys (`case.yaml` mesh, fixed time step, solver, schemes,
  `endEffects`/`dynamicStall`, averaging window) are shared and must not
  diverge. A kernel-matched ASM-mesh configuration (Gaussian width/epsilon
  matching the no-mesh ASM) is the ablation that isolates geometry from the
  kernel/width confound; the paper-cosine surface configuration is the
  headline.
- **Baselines**: the queued `phaseVI-prod` / `phaseVI-stage3` runs are the ALM
  and no-mesh ASM references (verified in `squeue`; not resubmitted, not
  cancelled). No new job is submitted by this change.
- **Metrics**: turbine-level CP/CT/torque/thrust from `turbine.csv` with the
  fixed F1 formulas and ±15 % bands; spanwise CN/CT at
  r/R = 0.30/0.47/0.63/0.80/0.95 with the max(0.15, 20 %) band; the sign gate.
  The surface source additionally emits per-station forces converted to the
  same `c_ref_n`/`c_ref_t` element conventions so the existing compare logic
  consumes it unchanged.
- **Sub-grid caveat (scope honesty)**: at D/32–D/64 the background cells are
  0.314/0.210/0.157 m and the blade chord is 0.218–0.744 m, so the blade is
  1–2 cells wide at every affordable resolution; the imported surface is
  **sub-grid**. The three-way comparison therefore tests **model form** (how the
  load is distributed) and cannot demonstrate resolved chordwise physics.
  This is stated in the README and in the acceptance framing below.
- **Pre-registered hypothesis**: before the campaign, the README records the
  expected direction and approximate size of the geometry effect on the
  spanwise load (root-transition and tip sensitivity first), so the comparison
  is a test of a stated hypothesis rather than a post-hoc "mesh is better"
  claim.
- **Performance gate**: the S1 distribution loops all local cells per node
  (`nacelleSurfaceSource.C:163-209`), i.e. O(10⁹–10¹⁰) prefilter checks per
  `addSup` at 6.7 M–53 M cells. W1 uses a bounded candidate query (mesh cell
  tree / cached stencil sized for the kernel support) and W4 instruments nodes,
  candidate cells per node and seconds per `addSup`. **The D/32 measurement
  must pass before the D/48/D/64 campaign is committed**; the measurement run
  is prepared but executed only after explicit authorization.
- **Acceptance framing**: engineering acceptance is build + full pytest +
  partition-of-unity/no-double-count + fair-comparison integrity (identical
  config, staged-STL hash match, same averaging window). Scientific acceptance
  is the reported three-way comparison against the existing bands; a band
  miss is a documented finding about model form, not a merge blocker.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `turbinesFoam/src/fvOptions/bladeSurface/` | New | `bladeSurfaceSource` (load, patch mapping, kernel spread, suppression consumption, CSV, rotation) |
| `turbinesFoam/src/fvOptions/nacelleSurface/nacelleSurfaceSampler.{H,C}` | Modified | Extract the shared geometry/kernel/distribution base; nacelle behavior regression-gated |
| `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/actuatorLineElement.{H,C}` | Modified | Guard `applyForceField` with the additive `projectElementForce` flag (default true) |
| `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineSource.{H,C}` | Modified | Construct/own the distributor from `surfaceGeometry`; forward transforms; add surface moment; distribute after the element loop |
| `turbinesFoam/src/Make/files` | Modified | Register the new `.C` |
| `turbinesFoam/geometry/src/` | Modified | Builder registry; `phaseVI_blade` pure-Python loft; `COMPONENTS`/`RESERVED_COMPONENTS` policy |
| `turbinesFoam/geometry/stl/phaseVI_blade.stl`, `metadata/phaseVI_blade.json`, `data/` (S809 csv), `PROVENANCE.md`, `README.md` | New/Modified | Blade component artifacts, S809 coordinates + extraction provenance, naming policy |
| `turbinesFoam/validation/phaseVI/data/s809/` | New | Committed S809 coordinates + provenance |
| `turbinesFoam/validation/phaseVI/config/case.yaml`, `tools/generate_case.py`, `tools/case_config.py` | Modified | Third model variant and surface keys |
| `turbinesFoam/validation/phaseVI/scripts/runPhaseVI.sh`, `scripts/comparePhaseVI.py`, `scripts/slurm/` | Modified/New | `-m asm-mesh`, STL staging, three-way compare, prepared-only array |
| `turbinesFoam/tests/` | New/Modified | Blade surface, blade data, case/compare tests; updated geometry assertions |
| `turbinesFoam/README.md`, root `README.md`, root `CHANGELOG.md` | Modified | Formulation, sub-grid framing, kernel option, naming resolution |
| `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/actuatorSurfaceElement.{H,C}` | Untouched | The no-mesh ASM stays the reference variant |
| `openspec/changes/mexico-validation/**`, `openspec/changes/archive/**` | Untouched | Not modified by this change |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Blade force applied twice (suppression missing/leaking) | High | Single distributing owner per blade; `projectElementForce` default true, injected only with `surfaceGeometry`; gate = existing suite + explicit partition-of-unity/no-double-count integration test |
| Sub-grid surface makes the "real mesh" claim unsupportable | High | Frame as model form in README/acceptance; pre-registered hypothesis; kernel-matched ablation to separate geometry from kernel; no resolved-physics claims |
| Performance: naive all-cells-per-node distribution impractical at 22–53 M cells | High | Bounded candidate query from W1; per-`addSup` instrumentation and a D/32 measurement gate before the campaign; campaign scope decision after the gate |
| Geometry determinism/tessellation (twisted thin loft) | Medium-High | Pure-Python structured loft with fixed topology; `canonical_triangles` + `--check`; no gmsh for blades |
| S809 coordinate provenance | Medium | Extract from the verified PDF with a recorded, repeatable method; cross-check; commit hashes with the data; text dump not authoritative alone |
| Shared-base refactor regresses nacelle (S1) | Medium | Base extraction only for generic assets; nacelle force model/frame untouched; gate = nacelle tests + byte-comparable CSVs; default paths unchanged |
| Torque/CP reported from element moments while the field sees node-distributed loads | Medium | Add the surface node moment to the blade moment; document the convention in the source CSV/README |
| Kernel/width confound in the three-way comparison | Medium | Selectable kernel/width on the surface distributor; kernel-matched ASM-mesh ablation documented as an ablation, not a model |
| MEXICO naming/ownership rework | Medium | Resolved now: `phaseVI_blade` component; `blade0/1/2` reservation retired; MEXICO component owned by `mexico-validation` |
| Review budget exceeded | High (blocking) | Recorded above; `size:exception` or chained PRs resolved before apply |
| HPC authorization scope | Medium | Prepared-only arrays; existing queued jobs untouched; measurement/campaign only with explicit authorization |

## Rollback Plan

The change is additive and opt-in; absent keys leave ALM and no-mesh ASM
byte-identical.

1. Remove `surfaceGeometry` (and optional kernel keys) from the blade subdict —
   the element keeps its own strip projection and behavior returns to the
   no-mesh ASM without recompiling. The suppression key is never present
   unless `surfaceGeometry` was configured.
2. Code rollback is per work unit via `git revert`: W1 removes the surface
   source and the base extraction (nacelle restored); W2 removes the blade
   component artifacts and builder; W3 removes the Phase VI variant, staging,
   compare and array additions; W4 removes instrumentation. No case schema
   migration is required.
3. Committed geometry data reverts with W2; the STL staged into run dirs is a
   copy and can be deleted without affecting other models.
4. Verify with `cd turbinesFoam && ./Allwmake` and `pytest`; the existing suite
   must pass unchanged, and `makeGeometry.py --check` must exit 0 for the
   remaining components.

## Dependencies

- Loaded OpenFOAM v2506 module environment (SDumont recipe in AGENTS.md);
  `-lsurfMesh` already linked by S1.
- No new external CFD/FSI libraries; preCICE is not a dependency.
- PyMuPDF (available — it produced the local dump) for the recorded S809
  extraction; the committed CSV must be reproducible from the verified PDF.
- Committed Phase VI inputs: `phaseVI_blade.csv` (sha256-pinned) and the S809
  polars; the verified Somers PDF is a local, non-committed source (hash
  recorded in provenance).
- HPC authorization for the measurement gate and campaign (prepared-only
  otherwise); existing Phase VI arrays are read-only baselines.

## Open Questions

1. **Component name confirmation**: `phaseVI_blade` vs a generic `blade`
   (engineering recommendation: rotor-qualified). Only naming/ownership is
   open; the MEXICO conflict is resolved either way.
2. **Campaign scope after the performance gate**: if the D/32 measurement
   exceeds the practical budget, the fallback is (a) bounded-query
   optimization, (b) campaign restricted to D/32 + D/48, or (c) deferral —
   needs a user decision once measured numbers exist.
3. **Acceptance semantics**: are the existing bands a merge gate for the
   ASM-mesh variant, or a reported comparison? (Recommendation: report, with
   engineering-only merge criteria.)
4. **Delivery**: explicit `size:exception` under `single-pr` vs the prepared
   chained PRs W1→W4 — user decision required before apply.
5. **Kernel ablation in the first campaign**: include the kernel-matched
   ASM-mesh configuration in the initial prepared array, or hold it for a
   follow-up (it is cheap configuration, not new code).
6. **Section construction details** (cylinder/transition profile, trailing-edge
   closure, root/tip treatment) are engineering decisions for design, not user
   input; the proposal fixes only wetted-surface, full-span coverage.

## Success Criteria

- [ ] `cd turbinesFoam && ./Allwmake` exits 0; `ldd -r` clean; full existing
      pytest suite passes unchanged (ALM and no-mesh ASM byte-identical).
- [ ] A case with `surfaceGeometry` on a blade distributes the BEM element
      force over the imported surface exactly once: partition-of-unity and
      no-double-count integration checks pass, and the element CSV/`force()`
      remain valid.
- [ ] The surface follows the blade rotation/pitch/translate path with no new
      restart state (S1 `angleDeg`/`omega` seam), and the reported blade moment
      includes the surface contribution.
- [ ] `makeGeometry.py --check` regenerates `phaseVI_blade` byte-identically
      and non-destructively; S809 coordinates are committed with recorded
      extraction method and hashes; metadata carries per-node
      `radial_station`/`chord_fraction`.
- [ ] `runPhaseVI.sh -m asm-mesh -u <speed>` renders the third twin, installs
      `system/fvOptions` and stages the STL (no `--run`/`--submit`);
      `case_config.py --select` accepts the model; `--check` is clean; **no job
      is submitted**.
- [ ] `comparePhaseVI.py` produces the three-way turbine + spanwise comparison
      with the existing bands and sign gate (surface output converted to the
      element conventions).
- [ ] Performance instrumentation reports nodes/candidate cells/time per
      `addSup`; the D/32 measurement gate is prepared and executed only under
      explicit authorization; queued ALM/ASM arrays are undisturbed.
- [ ] Docs state the formulation being implemented (chord-line paper extension,
      not a literal port), the sub-grid caveat, the kernel confound and its
      ablation, and the MEXICO naming resolution; root `CHANGELOG.md` updated.
- [ ] S3/preCICE remains deferred and untouched (`adapter`, `fsiOmega`,
      `modules/*` unchanged).
