# Archive Report — `blade-actuator-surface`

- Change: `blade-actuator-surface` — S2: per-blade actuator surface over a real
  imported blade mesh + deterministic `phaseVI_blade` geometry + the Phase VI
  three-way (ALM / no-mesh ASM / ASM-mesh) validation variant
- Project: `of-plugins`
- Archived: 2026-09-23 → `openspec/changes/archive/2026-09-23-blade-actuator-surface/`
- Artifact store: hybrid — repo-local OpenSpec artifacts are authoritative; the
  Engram mirror is persisted additionally (observation `#163`, topic
  `sdd/blade-actuator-surface/archive-report`)
- Branch: `feat/nacelle-actuator-surface`, base `d4496ae`, head `4fb3b11` —
  **local commits only; nothing pushed, no PR opened**
- Reference: Yang, X. and Sotiropoulos, F., *A new class of actuator surface
  models for wind turbines*, arXiv:1702.02108v4 — Sec. 2.1 (chord-line blade
  ASM) and Sec. 2.2 (actual-surface nacelle model). The imported-triangulation
  blade surface is an extension of the paper's chord-line blade ASM in the S1
  direction, not a literal equation port. S809 profile coordinates from Somers,
  NREL/SR-440-6918, Table 2.
- Report status: terminal record of the SDD cycle; ranks above
  `apply-progress.md` and `verify-report.md` (intermediate snapshots).

## Final State at Close

- **Tasks: 22/23 complete** (W1.1–W1.8, W2.1–W2.5, W3.1–W3.6, W4.1–W4.3), per
  the persisted `tasks.md`, mechanically counted at archive time: 22 `[x]`,
  1 `[ ]`. The single unchecked task is **W4.4 (conditional candidate-query
  hardening) — NOT triggered**: no D/32 measurement evidence exists, so the
  performance gate cannot demand hardening. The archived `tasks.md` bytes are
  unchanged (`sha256 3f5fba7ceb8fc222c64bf6d2de864f3e0b5156eecc48b4c679b927cd6a590892`).
- **Implementation: complete** for the S2 scope. It is additive and opt-in:
  with no `surfaceGeometry` key in a blade subdictionary, ALM and no-mesh ASM
  behavior is unchanged; no new state enters the restart path.
- **Verification: engineering PASS.** `sdd-verify` ran and initially reported
  `partial` because one test failed *inside the required Slurm execution
  environment* — a test-harness robustness gap, not a production defect. That
  gap was fixed in `4fb3b11` and re-verified on `sequana_cpu_dev` (job
  `11599987`, COMPLETED `0:0`, `6:32`): `./Allwmake` exit 0, `ldd -r` clean,
  **full suite `124 passed, 1 warning`**, focused files `66 passed`. The
  engineering verdict is PASS.
- **Scientific acceptance is unearned by design.** No ASM-mesh production or
  campaign run was executed; the ASM-mesh array and the D/32 measurement gate
  are prepared-only and require explicit authorization. No resolved-chordwise
  physics is claimed (see the sub-grid caveat).
- **24 commits on the branch** from base `d4496ae` to head `4fb3b11` (all
  local), in work-unit order:
  - W1a: `5d1acad`, `5f357c8`
  - W1b: `6789953`, `02d18f5`
  - W1c1: `6e6719d`
  - W1c2: `648e21a`, `c53711d`, `c787ed2`, `bd450c8`
  - W2a: `64d9cb8`, `98444eb`
  - W2b: `67708d4`, `7c3d7e2`, `bbd143f`
  - W2c: `b567d26`
  - W3a: `e7f8dd7`, `6474bdc`
  - W3b: `d92c63d`, `94c8898`
  - W3c: `00f60d4`, `a901c3c`
  - W4: `4452fed`, `fc136b4`
  - Post-verify harness fix: `4fb3b11`
  - Diffstat `d4496ae..HEAD`: **82 files changed, 11280 insertions(+), 754 deletions(-)**.
- `openspec/` remains untracked, as in every previous SDD batch. No
  `git add`/`commit`/`push` was performed by this archive, and no Slurm job was
  submitted.

## What Shipped per Work Unit

| Unit | Scope | Commits | Final state |
|------|-------|---------|-------------|
| W1 — blade surface distributor (C++) | `surfaceSamplerBase` extraction (frame/force-model-agnostic) with the nacelle sampler re-based byte-comparably; `bladeSurfaceSampler` (rotating frame, 1-D Voronoi element-patch partition, bounded bin-grid candidates, cosine/Gaussian kernel); `bladeSurfaceSource` (Eq. 18 distribution, surface moment, SI accessors, per-station/per-node CSV, compressible rho path); additive `projectElementForce` suppression key (guards only the two `applyForceField` sites); `actuatorLineSource`/AFTAL plumbing and transform lockstep; `Make/files`; integration fixtures and `tests/test_blade_surface.py` (10 tests); turbinesFoam README | `5d1acad`, `5f357c8`, `6789953`, `02d18f5`, `6e6719d`, `648e21a`, `c53711d`, `c787ed2`, `bd450c8` | Complete; build + `ldd -r` clean; partition-of-unity, no-double-count, lockstep, surface-moment, MPI and Gaussian-conservation tests green; nacelle CSV/`forceIntegral` byte-identical to the S1 baseline |
| W2 — blade geometry (`turbinesFoam/geometry/`) | Committed S809 coordinates (`data/s809/s809_somers_nlr.csv`) with full extraction provenance and two independent cross-checks; `geometry/src/blade_phasevi.py` pure-Python structured loft (3000 wetted triangles, no caps) with populated `radial_station`/`chord_fraction`; builder registry (`nacelle` gmsh / `phaseVI_blade` python), `blade0/1/2` reservation retired; committed STL + metadata; geometry README/PROVENANCE; `tests/test_blade_data.py` (6 tests) + updated nacelle/Phase VI data tests | `64d9cb8`, `98444eb`, `67708d4`, `7c3d7e2`, `bbd143f`, `b567d26` | Complete; `--check --component phaseVI_blade` byte-identical and non-destructive with no gmsh; nacelle path unchanged; STL sha256 `77def499…`, metadata `01f75d17…`, S809 CSV `861f3fe5…` |
| W3 — Phase VI ASM-mesh variant | `fvOptions.ASM-MESH` third twin (surface keys only); `case.yaml` `asm-mesh` stage; `case_config.py` `--select` whitelist + runner `-m asm-mesh` with STL staging helper and `--submit` refusal (exit 2); three-way `comparePhaseVI.py` (surface-output conversion to `c_ref_n`/`c_ref_t`, sub-grid caveat, kernel confound + Gaussian ablation); prepared-only `asm-mesh.slurm`; case/compare/staging tests; README/CHANGELOG | `e7f8dd7`, `6474bdc`, `d92c63d`, `94c8898`, `00f60d4`, `a901c3c` | Complete; prepare-only staging stages STL `77def499…`; `generate_case.py --check` clean; three-way tooling and prepared-only array verified; no job submitted |
| W4 — performance measurement gate | Per-`addSup` instrumentation (`logDistribution`, node/candidate/second counters + `_distribution.csv`); `test_instrumentation_line`; prepared-only D/32 measurement gate documentation. **W4.4 (candidate-query hardening) conditional — not triggered** | `4452fed`, `fc136b4` | Complete (W4.1–W4.3); instrumentation observational (distribution math unchanged); no measurement executed |

## Verification Evidence (final numbers)

All heavy checks ran on the `sequana_cpu_dev` partition via `sbatch` (user
policy: builds, solver-driven tests and the full suite run on the dev
partition). The Slurm script lives under `$SCRATCH/tmp/verify-slurm/` and is
**not** a repo artifact.

| Check | Command | Result |
|-------|---------|--------|
| Build | `./Allwmake` | exit 0 |
| Link hygiene | `ldd -r $FOAM_USER_LIBBIN/libturbinesFoam.so` | clean (no undefined symbols) |
| Full suite | `pytest -q` | **124 passed, 1 warning** |
| Focused files | `pytest -q tests/test_blade_surface.py tests/test_blade_data.py tests/test_blade_stage.py tests/test_phasevi_case.py tests/test_phasevi_compare.py tests/test_phasevi_data.py tests/test_nacelle.py` | **66 passed** |
| Blade geometry check | `makeGeometry.py --check --component phaseVI_blade` (no gmsh) | exit 0, byte-identical |
| Nacelle geometry check | `makeGeometry.py --check --component nacelle` (pinned gmsh) | exit 0 |
| Case render check | `generate_case.py --check` | exit 0 (clean) |
| Prepare-only staging | `runPhaseVI.sh -m asm-mesh -u 7 -mesh coarse` | exit 0; staged STL `77def499…` |
| Submit refusal | `runPhaseVI.sh -m asm-mesh … --submit` | exit 2 |
| Array guard | `bash asm-mesh.slurm` (no env) | exit 5 (prepared-only) |
| Array shape | `sbatch --test-only asm-mesh.slurm` | exit 0; no job created |

**Final verification job:** `11599987` (`sequana_cpu_dev`, COMPLETED `0:0`,
`6:32`). The earlier job `11599975` (log
`$SCRATCH/tmp/verify-slurm/verify_11599975.log`) recorded the pre-fix harness
failure; the post-fix job is authoritative.

**No validation array was submitted.** `squeue` has no ASM-mesh job; the only
`sbatch` calls are inside guarded `--submit` branches, and the read-only
baselines (`phaseVI-prod`, `phaseVI-stage3`, `phaseVI-stage3-d64`) were not
submitted, cancelled or modified.

## Specs Synced to Source of Truth

Two new capabilities and six modified capabilities. The six existing main specs
were composed with the native `gentle-ai sdd-archive-compose` (exit 0 in every
case; requirement matched by name; unrelated requirements preserved
byte-for-byte; RENAMED → MODIFIED → REMOVED → ADDED order). The two new
capabilities have no main spec, so the complete delta spec was copied
mechanically (`cp` to a staged temp, `diff -r` readback, atomic `mv`) — never
through a model Read/Write path.

| Domain | Action | Requirements | Scenarios | sha256 |
|---|---|---|---|---|
| `blade-surface-source` | Created (12 added) | 12 | 22 | `3de525f3e918999c027d4289e691518e7d9cd59c2773127b6ec8d0c9077edcec` |
| `blade-geometry-generation` | Created (7 added) | 7 | 16 | `d84f533c11c65bb0b5528c7c5c16473986de855a5a68ba330b65dca7f2af9c5b` |
| `turbine-geometry-pipeline` | Updated (6 modified, 1 added, 1 removed) | 7 | 17 | `4b5d4b207c7f590cc38dbe27b4538a856a30c9b0ceec9b5c8d1f60336b8fa9c5` |
| `surface-sampling-contract` | Updated (3 modified, 1 added) | 8 | 13 | `540bd12306ecc710aefd7dd7911418231dd1b8dc5afe8879a28010d9bdbabfc1` |
| `element-type-selection` | Updated (2 modified, 1 added) | 5 | 11 | `9e641600fa5f2610e9223cc205cc6508aead28534e222946f80e7d15b4590950` |
| `phasevi-validation-case` | Updated (2 modified) | 11 | 26 | `618402c9b9baf5ae3be1cadf5ce04d7b94f7433f25ec075012f74e998f4059a7` |
| `phasevi-run-and-compare` | Updated (5 modified, 1 added) | 13 | 38 | `44f8d190c76241e2204b9fb27a633a0ec2786eabc09c1d8ec27aca73c91d216e` |
| `phasevi-data-provenance` | Updated (4 modified, 1 added) | 8 | 19 | `60bc917a86e377e5566ce28df33f765c06bec26322feda9c5585d810b39de76b` |

Removed requirement (only removal in this change):
`turbine-geometry-pipeline` — "Blade STL accommodation with S2 deferral"
(superseded by "Component builder registry" and the modified "Per-component STL
output").

The unrelated requirements in each existing main spec were preserved; the
composition output was additionally checked to confirm every removed name is
absent, every added name appears exactly once, and every modified name is
present.

**Composition deviation (recorded).** `sdd-archive-compose` requires the
`(Reason: ...)` note of a REMOVED requirement to sit on a single line (its
matcher is `(?m)^\(Reason:.+\)[ \t]*$`). The `turbine-geometry-pipeline` delta
wrapped that note across three lines, so the tool refused with
`unapplied REMOVED delta for requirement "Blade STL accommodation with S2
deferral": missing required "(Reason: ...)" note` even though the note is
present. Composition for that one domain was therefore run against a
byte-preserving **temp copy** whose only change is collapsing the note's line
wrapping (the parenthetical text is identical); the archived delta retains its
original three-line bytes. No manual Read/Edit merge was performed — the native
compose command produced the output. This is a tool-input formatting constraint,
not a content defect; future delta authoring should keep `(Reason: ...)` on one
line.

**New-capability heading note.** The two new capabilities were authored as
delta specs (`## ADDED Requirements`) rather than as complete specs
(`## Requirements`, the canonical convention used by every existing main spec).
They were copied mechanically to preserve bytes, so the two new main specs
retain the `## ADDED Requirements` section heading. `sdd-archive-compose`
parses `### Requirement:` headings regardless of the enclosing section name
(verified), so this is a cosmetic consistency difference, not a functional one.

## Reconciliation of Intermediate Artifacts (Final-State Authority)

- **`verify-report.md` (intermediate snapshot).** Its top-level status is
  `partial` and its WARNING records `test_asm_mesh_selection` failing inside a
  Slurm allocation (`--ranks 48 does not match SLURM_NTASKS=4`). This is stale
  as a current-state claim: per the orchestrator's final-state facts and the
  report's own "Post-verify resolution" section, the harness gap was fixed in
  `4fb3b11` and re-verified on job `11599987` (full suite `124 passed`). The
  final state is engineering PASS. The verify report's SUGGESTIONS (no fresh
  byte-level ALM/ASM `cmp`; scientific claims unearned; W4.4 open) stand.
- **`apply-progress.md` (intermediate snapshot).** Its per-batch status tables
  are a valid history; its early "remaining tasks (W1c and later)" and
  "Next (W4)" lines are stale and are superseded by the final 22/23 state.
- **Intentional, spec-relevant deviations recorded in `apply-progress.md`**
  (specs were composed from the deltas and were not rewritten by archive):
  1. W1.5 was split by batch scope — only `surfaceSamplerBase.C` was registered
     in W1a; the two `bladeSurface/*.C` lines followed in W1b once the files
     existed.
  2. The shared base's diagnostic text is generalized (`Surface sampler: …`)
     because it serves two consumers; the nacelle observable output (CSVs,
     `forceIntegral`) remains byte-identical and the S1 test substrings still
     match.
  3. `surfaceSamplerBase` takes an optional `geometryKey` constructor parameter
     (default `"geometry"`) so the blade sampler can pass `surfaceGeometry`
     without dict translation.
  4. The base helpers are protected and reached through a `friend` declaration
     (W1b adds the equivalent for the blade source), per design §4.1.
  5. `streamwiseDirection_` moved out of `createBodyFrame`; the nacelle subclass
     recomputes it from the same `bodyAxis` entry, preserving exact
     floating-point coordinates.
  6. The pre-registered hypothesis in the Phase VI README is qualitative on
     direction and size bound (root-transition/tip first, mid-span least; at or
     below the spanwise band) rather than inventing station numbers the design
     does not fix.
  7. The attribution commit pin is `26a1f46…` (*feat(turbinesFoam): add actuator
     surface element type*), the in-history commit that adds the blade
     actuator-surface patch, with a note that later S2 commits extend it.
  8. `size:exception` is recorded per work unit (the change is far over the
     400-line budget; the session strategy is `single-pr` with the
     pre-authorized S1 `size:exception`).
  The full per-batch deviation list is in `apply-progress.md`.
- No contradiction between ranked sources was left unresolved.

## Archive Contents

Present (10 pre-move files; bytes preserved; `archive-report.md` additive):

- `proposal.md`
- `exploration.md`
- `design.md`
- `tasks.md` (22/23 complete, 1 conditional unfinished)
- `apply-progress.md`
- `verify-report.md`
- `specs/blade-surface-source/spec.md`
- `specs/blade-geometry-generation/spec.md`
- `specs/turbine-geometry-pipeline/spec.md`
- `specs/surface-sampling-contract/spec.md`
- `specs/element-type-selection/spec.md`
- `specs/phasevi-validation-case/spec.md`
- `specs/phasevi-run-and-compare/spec.md`
- `specs/phasevi-data-provenance/spec.md`

Absent: `state.yaml` (none was created), `research.md` (none was created). No
artifact was dropped during the move: the pre-move recursive snapshot matches
the archived tree exactly (`archive-report.md` excluded as additive).

## Delivery, Deferred, and Open Follow-ups

- **Delivery not performed.** Nothing was pushed and no PR was opened. The
  session delivery strategy is `single-pr` with a recorded, pre-authorized
  `size:exception` (W1–W4 each exceed the 400-line review budget). Push/PR is an
  explicit user decision, not an archive action.
- **No production/campaign run.** Only the engineering checks ran (dev
  partition). The ASM-mesh array (`asm-mesh.slurm`, tasks `asm-mesh:7:coarse:H`
  = D/32 measurement gate and `asm-mesh:7:fine:H` = D/48 headline) is
  prepared-only and requires explicit long-queue authorization; the read-only
  baselines are untouched.
- **W4.4 (candidate-query hardening) is open and conditional** — correctly not
  triggered, because no D/32 measurement evidence exists. If a future authorized
  measurement exceeds the practical per-step budget, the uniform-bin query would
  be replaced/extended by a mesh-tree/stencil query with the default
  distribution unchanged.
- **Sub-grid caveat.** At D/32–D/64 the background cells are 0.314 / 0.210 /
  0.157 m while the blade chord is 0.218–0.744 m, so the imported surface is
  sub-grid at every affordable resolution. The three-way comparison tests
  **model form** (how the load is distributed) and cannot demonstrate resolved
  chordwise physics. This is stated in the README and the comparison
  `LIMITATIONS`.
- **Kernel/width confound.** The paper-cosine surface vs the no-mesh Gaussian
  differ in kernel/width; the kernel-matched Gaussian ASM-mesh configuration is
  prepared as an **ablation** to separate geometry from the confound — it is not
  a model.
- **S3 / preCICE / adapter / `fsiOmega` untouched.** `git diff d4496ae..HEAD --
  precice-openfoam-adapter fsiOmega` is empty; `mexico-validation` and
  `openspec/changes/archive/**` were not modified.
- **Carried S1 follow-ups (unchanged, out of S2 scope):** the zero-omega
  override degeneracy (`calcEndEffects()` divides by `mag(elementVel)`
  unguarded); per-step `angleDeg.<name>` checkpoint-only time directories; the
  `startFrom latestTime` solver-bit-identity caveat; a stale
  `postProcessing/profileSamples/` directory left by a pre-fix run; and
  `shellcheck` not installed on the host (new shell scripts syntax-checked only).
- **Tooling note for future deltas:** keep a REMOVED requirement's
  `(Reason: ...)` note on a single line (see the composition deviation above).

## Attribution

- **Model:** Yang, X. and Sotiropoulos, F., *A new class of actuator surface
  models for wind turbines*, arXiv:1702.02108v4 — Sec. 2.1 (chord-line blade
  ASM; the imported-triangulation surface is an S1-direction extension) and
  Sec. 2.2 (actual-surface nacelle model). The BEM content (Eqs. 1–16), dynamic
  stall, end effects and added mass are unchanged (distribution-only).
- **S809 profile:** Somers, D. M., *Design and Experimental Results for the
  S809 Airfoil*, NREL/SR-440-6918, Table 2 — committed as a derived CSV with
  recorded extraction recipe (PyMuPDF), PDF sha256, table id and two independent
  cross-checks.
- **Phase VI data:** NREL/TP-500-29955 (DOI 10.2172/15000240), TP-442-7817, and
  the WDH workbooks (DOI 10.21947/WDH-DAP/1910052), under the existing
  provenance rules.
- **Adaptation credit:** `mttbrbr/single-actuator-line` (main `8284be8c…`) under
  GPL-3.0-or-later, with the pinned `of-plugins` commit and the ASM patch note.

## Byte-Preservation Evidence (verbatim mechanical readback)

Spec sync — modified capabilities, native composition (only a zero exit is
composition evidence):

```text
--- surface-sampling-contract
compose exit=0
installed
--- element-type-selection
compose exit=0
installed
--- phasevi-validation-case
compose exit=0
installed
--- phasevi-run-and-compare
compose exit=0
installed
--- phasevi-data-provenance
compose exit=0
installed
--- turbine-geometry-pipeline (normalized temp delta)
compose exit=0
installed
```

Spec sync — new capabilities, mechanical copy (`diff -r` empty is the only
passing evidence):

```text
===== [blade-surface-source] mechanical copy =====
[diff -r source vs staged temp: EMPTY -> byte-identical]
[installed] 3de525f3e918999c027d4289e691518e7d9cd59c2773127b6ec8d0c9077edcec
===== [blade-geometry-generation] mechanical copy =====
[diff -r source vs staged temp: EMPTY -> byte-identical]
[installed] d84f533c11c65bb0b5528c7c5c16473986de855a5a68ba330b65dca7f2af9c5b

=== readback: source vs installed main spec (diff -r) ===
--- blade-surface-source
[EMPTY -> byte-identical]
--- blade-geometry-generation
[EMPTY -> byte-identical]
```

Archive move (snapshot taken before the move; `openspec/` is untracked, so
`git mv` failed without changes and the guarded plain-`mv` fallback ran):

```text
--- git mv attempt (openspec/ is untracked) ---
fatal: source directory is empty, source=openspec/changes/blade-actuator-surface, destination=openspec/changes/archive/2026-09-23-blade-actuator-surface
[git mv exit 128 -> fallback path]
[diff -r snapshot vs source after failed git mv: EMPTY -> source unchanged]
[plain mv exit 0]
[source absent after move]
--- MANDATORY READBACK: diff -r (pre-move snapshot vs archived destination) ---
[diff exit 0 -> EMPTY OUTPUT: archived bytes identical to pre-move snapshot]
```

Archived `tasks.md` sha256
`3f5fba7ceb8fc222c64bf6d2de864f3e0b5156eecc48b4c679b927cd6a590892` equals the
pre-move value; the archived `turbine-geometry-pipeline` delta retains its
original three-line `(Reason: ...)` note.

## Persistence (hybrid store)

- Filesystem: **complete** — the eight main specs are synced, the change is
  moved to `openspec/changes/archive/2026-09-23-blade-actuator-surface/`, and
  this report is persisted.
- Engram: **saved** — topic key `sdd/blade-actuator-surface/archive-report`,
  type `architecture`, project `of-plugins`, observation id **`#163`** (CLI:
  `engram save … --project of-plugins --type architecture --topic
  sdd/blade-actuator-surface/archive-report`, exit 0). The filesystem copy is
  authoritative; the Engram copy is the hybrid mirror.
