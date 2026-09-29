# Proposal: Blade actuator surface model (ASM) for turbinesFoam

## Intent

`turbinesFoam`'s actuator line model (ALM) resolves blade forces from a single
collocation point per radial station and ties the projection width to the chord
(`epsilon = max(0.25·c, mesh)`). It cannot resolve chordwise flow features, and
on fine meshes the chord-based floor prevents the model from resolving the chord
geometry at all. This change adds an optional **blade actuator surface model
(ASM)** (Yang & Sotiropoulos, arXiv:1702.02108v4, Sec. 2.1) that computes the
same BEM loads but averages the relative velocity over the chord line and
distributes the force uniformly across `nChordwise` chordwise strips, so the load
width is mesh-based and the model couples to finer meshes.

The change must land cleanly as an additive, opt-in capability: the existing ALM
path stays byte-identical by default, every existing case and test keeps working,
and a user-facing HAWT tutorial demonstrates the new mode with an ALM-vs-ASM
comparison.

## Scope

### In Scope
- Core blade ASM element: chord-averaged inflow sampling (midpoint rule over
  `nChordwise` equal chord strips), uniform chordwise force distribution
  (`forceVector_/nChordwise` per strip), and mesh-only projection epsilon
  (`2·cbrt(V)·meshFactor`), reusing the existing Gaussian projection kernel.
- Polymorphic element architecture: complete the vestigial element runtime
  selection (implement `actuatorLineElement::New`, register
  `actuatorSurfaceElement` via `addToRunTimeSelectionTable`, virtualize the three
  differing hooks with unchanged default bodies) and switch `createElements` to
  `New`.
- Config plumbing: `elementType actuatorSurfaceElement;` and `nChordwise 5;` keys
  in the line/blade subdicts, passed through to each element.
- In-repo HAWT ASM tutorial `tutorials/axialFlowTurbineASM/` (axial-flow, based on
  the existing `tutorials/axialFlowTurbineAL`) with an ALM-vs-ASM comparison
  script.
- Integration tests: `tests/test_asm.py` (static AL case, ALM-vs-ASM checks) and
  `tests/test_aftal_asm.py` (HAWT ASM case), plus the ASM case directory.
- Documentation: `turbinesFoam/README.md`, root `README.md`, root `CHANGELOG.md`.
- Verification: `./Allwmake` build + full existing pytest suite
  (`test_libs`, `test_al`, `test_aftal`, `test_cftal`) as the ALM regression gate.

### Out of Scope
- Zormpa et al. MEXICO validation case — deferred to a follow-up change; requires
  polars transcription (Appendix B) and geometry sourcing (public dataset vs.
  figure digitization) that a research step must confirm before it can be packaged.
- HPC `offshorewindpark` external reference — deferred to a follow-up change; it is
  ALM-only, HPC-scale (never CI), uses an incompatible `fcgaleazzo` fork, and mixes
  CC BY-SA × GPL-3.0 licensing (docs-only external link + attribution).
- Nacelle ASM (paper Sec. 2.2) and the empty `createNacelle` path of AFTAL.
- The paper's exact 3D smoothed-cosine delta kernel (Yang et al. 2009) — the
  existing Gaussian projection is reused and the adaptation documented.
- Root-loss model.
- CFTAL/VAWT ASM support — the element change is turbine-agnostic in principle but
  will be documented as untested; HAWT-only is the supported surface.

## Capabilities

> This section is the CONTRACT between proposal and specs phases.
> The sdd-spec agent reads this to know exactly which spec files to create or update.
> `openspec/specs/` is currently empty — there is no existing capability to modify.

### New Capabilities
- `actuator-surface-element`: the ASM element subclass — chord-averaged inflow
  sampling, uniform chordwise force distribution across `nChordwise` strips,
  mesh-only projection epsilon, inheriting the full BEM chain (coefficients,
  dynamic stall, added mass, end effects, CSV output).
- `element-type-selection`: completion of the vestigial element runtime selection —
  `actuatorLineElement::New`, `addToRunTimeSelectionTable` registration, and the
  `elementType`/`nChordwise` config keys plumbed through `createElements` so a
  line/blade can instantiate any registered element type (default unchanged).
- `axial-flow-turbine-asm-tutorial`: the in-repo HAWT ASM tutorial case and the
  ALM-vs-ASM comparison workflow (run both case dirs, side-by-side Cp/CT/spanwise
  output).

### Modified Capabilities
- None. No existing capability in `openspec/specs/` changes at the spec level: the
  ALM behavior is preserved byte-identical by default (the virtualization and
  `createElements` switch are internal implementation changes, not requirement
  changes).

## Approach

Adopt **Option 2: polymorphic element** (recommended by exploration). The element
class already declares an RTS table and virtual surface but never implements `New`
and hard-codes the concrete class in `createElements`; this change completes the
extension point the class was designed for, instead of bolting surface branches
onto the ALM code.

1. **Virtualize three hooks** on `actuatorLineElement` — `calculateInflowVelocity`,
   `applyForceField`, `calcProjectionEpsilon` — with their current bodies as the
   unchanged defaults. These are exactly the methods whose behavior differs for ASM.
2. **Implement `actuatorLineElement::New(dict)`** (type from dict, default
   `actuatorLineElement`) and register `actuatorSurfaceElement` with
   `addToRunTimeSelectionTable`.
3. **Add `actuatorSurfaceElement.{H,C}`** as a subclass that overrides the three
   hooks: chord-averaged inflow (arithmetic mean of `interpolationCellPoint`
   samples at the midpoint of each chord strip, `X_k = position_ +
   (chordMount_ - f_k)·c·unit(chordDirection_)`, `f_k=(k+0.5)/n`), uniform
   strip-wise force (`forceVector_/nChordwise` per strip, own Gaussian each), and
   mesh-only epsilon (`2·cbrt(V)·meshFactor`). The whole BEM chain (coefficients,
   dynamic stall, added mass, end effects, CSV) is inherited untouched.
4. **Switch `createElements`** to `actuatorLineElement::New(...)` passing
   `elementType` (default `actuatorLineElement`) and `nChordwise` (default 5) into
   each element dict — the same pass-through pattern already used for
   `velocitySampleRadius`/`nVelocitySamples`, so AFTAL/CFTAL reach the new keys with
   zero turbine-class changes.
5. **Register the new `.C` in `src/Make/files`**, add the HAWT ASM tutorial and
   comparison script, and add the integration tests.

MPI patterns are preserved from the existing element code (`reduce(minOp)`
sentinels, bounding-box `findCell`, fatal on unreachable samples), with the same
one-cell-pass-per-element + inner chord-point loop to bound the cost to
~`nChordwise`× candidates.

**Delivery note (decision required before apply, NOT pre-decided here):** the
forecast work (W1 core + W2 tutorial/tests/docs) is ~850–1050 changed lines, which
exceeds the 400-line review budget under the `single-pr` strategy. The
review-workload guard must be resolved by the orchestrator/user before
`sdd-apply` (chained/stacked PR slices vs. an explicit `size:exception`); this
proposal records the flag but does not choose for the user.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/actuatorLineElement.{H,C}` | Modified | Virtualize 3 hooks (unchanged default bodies); implement `New`; RTS registration |
| `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/actuatorSurfaceElement.{H,C}` | New | ASM subclass: chord-averaged sampling, strip-wise spreading, mesh-only epsilon, `nChordwise` |
| `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineSource.C` | Modified | `createElements` → `New`, pass `elementType`/`nChordwise` |
| `turbinesFoam/src/Make/files` | Modified | Register `actuatorSurfaceElement.C` |
| `turbinesFoam/tutorials/axialFlowTurbineASM/` | New | HAWT ASM tutorial (AFTAL copy + ASM blade config + truncated controlDict) + comparison script |
| `turbinesFoam/tests/test_asm.py`, `tests/test_aftal_asm.py`, `tests/axialFlowTurbineASMSource/` | New | Integration tests + ASM case dir |
| `turbinesFoam/README.md`, root `README.md`, root `CHANGELOG.md` | Modified | Config keys, tutorial, comparison, fork-divergence and kernel-adaptation notes |
| Untouched | — | `turbineALSource`, AFTAL/CFTAL turbine classes, profileData, dynamicStallModels, addedMassModel, interpolation utils |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Shared ALM construction path regression (virtualization + `createElements` switch) | Medium | Default `elementType actuatorLineElement` preserves behavior; full existing pytest suite + `test_libs.py` as gate |
| Review budget exceeded (W1+W2 ≈ 850–1050 lines vs. 400-line policy) | High | Record the flag here; require delivery-shape resolution (chained PRs or `size:exception`) before apply |
| No C++ unit framework — chord geometry/chord-average correctness unverifiable in isolation | Medium | Integration CSVs + ALM-vs-ASM comparison; optional Python expected-value check for chord-averaged velocity of a known flow in `test_asm.py` |
| MPI: chord points land on other processors / outside the mesh | Low | Reuse `reduce(minOp)` sentinel + bounding-box `findCell`; keep existing fatal-on-unreachable behavior |
| Mesh-only epsilon on the existing tutorial mesh makes ASM ≈ ALM (kernel ≈ cell size) | Medium | Document that ASM benefits require finer mesh and Nε≥1–2 kernel overlap |
| OpenFOAM v2506 API constraints in new code | Medium | Follow AGENTS.md gotchas (`get<word>`, no `List` from STL iterators, `Pstream` replacements) |
| Fork divergence from upstream turbinesFoam grows | Low | Document new element class + `elementType` in README fork notes; acceptable for a vendored fork |

## Rollback Plan

The change is additive and opt-in: with `elementType` unset, every existing case
instantiates `actuatorLineElement` and the ALM path is byte-identical. To revert:
1. Remove the `elementType`/`nChordwise` keys (or set `elementType
   actuatorLineElement`) from any case that adopted ASM — behavior returns to
   baseline without recompiling.
2. To roll back the code itself, `git revert` the change work units; the ALM class,
   `createElements`, and `Make/files` return to their prior state with no data or
   case migration required (no schema, no generated artifacts outside the new
   tutorial/tests, which are reverted with the change).
3. Verify with `cd turbinesFoam && ./Allwmake` and `pytest` (the existing suite
   must pass unchanged).

## Dependencies

- Loaded OpenFOAM v2506 module environment (SDumont recipe in AGENTS.md).
- No new external libraries; `libturbinesFoam` builds via the existing `wmake`
  recipe. `$WM_PROJECT_DIR/platforms/$WM_OPTIONS/lib` must be on
  `LD_LIBRARY_PATH` (documented build-recipe gap).

## Success Criteria

- [ ] `cd turbinesFoam && ./Allwmake` exits 0 with no new warnings/errors and
      produces `libturbinesFoam.so`.
- [ ] Full existing pytest suite passes unchanged: `test_libs`, `test_al`,
      `test_aftal`, `test_cftal` (ALM default path byte-identical — regression gate).
- [ ] `elementType actuatorSurfaceElement;` + `nChordwise 5;` are accepted in the
      line/blade subdict and produce element CSVs.
- [ ] `tests/test_asm.py` passes, including an ALM-vs-ASM check confirming the ASM
      path samples chord-averaged velocity and preserves total force.
- [ ] `tests/test_aftal_asm.py` passes against `tutorials/axialFlowTurbineASM/`.
- [ ] The ALM-vs-ASM comparison script produces side-by-side Cp/CT/spanwise output
      from the two tutorial run directories.
- [ ] Docs updated: config keys, tutorial usage, kernel adaptation vs. the paper,
      HAWT-only support note (CFTAL/VAWT documented as untested), fork-divergence note.
