# turbinesFoam modularization — architecture analysis and refactor plan

**Repository:** `efirvida/openfoam-fsi-plugins` (the old `efirvida/of-plugins` name redirects).
**Status:** plan only. No source change is authorized by this document; it is the
recoverable artifact for the analysis requested in L1.
**Published:** [efirvida/openfoam-fsi-plugins#3](https://github.com/efirvida/openfoam-fsi-plugins/issues/3).
**Target of the refactor:** `origin/feat/nacelle-actuator-surface` (67 commits ahead of
`main`, no divergence — see "Where the code is").
**Constraint:** behaviour-preserving. No physics formula, coefficient, weighting kernel,
partition rule, or operation order changes (S5).

## Specs

- **S1** — Deliverable is analysis + plan, not implementation:
  > "ahora solo necesito hacer un analisis y planificar su refactor."
- **S2** — The premise to be verified against the code, not assumed:
  > "al codigo original el cual solo implementaba modelo ALM para calculo aerodinamico de
  > turbina, se le colgaron en la misma clase ASM, ASM+MESH, nacelle usando IBM, y todo
  > son fisicas diferentes estructuradas como si fueran la misma fisica."
- **S3** — Plus an FSI/coupling preparation:
  > "Ademas de la preparacion para usar el adapter de openfoam para PreCICE para hacer FSI"
- **S4** — Goal of the refactor:
  > "necesitamos una refactorizacion que separe bien las responsailidades, y sea mucho mas
  > facil de mantener"
- **S5** — Hard constraint:
  > "sin tener que alterar la fisica ya que eso es responsabilidad de otro equipo de trabajo"
- **S6** — The prior plan was lost and must survive re-reads:
  > "parece que perdi un trabajo que habia hecho sobre un plan de refactor de @turbinesFoam/"
- **S7** — `fsiOmega` is a separate plugin and must not be modified:
  > "fsi omega es un plugin separado de turbineFOAM no debe ser modificado, ya que el es
  > usado independientemente de turineFOAM e incluso es utilizado por los demas plugins en
  > el repo a demanda. Es el encargado de pasa velocidad angular entre los dominios FSI
  > entonces no forma parte del refactor/"

## Where the code is

The lost artifact was a *plan*; the code was never lost. Findings:

| Fact | Evidence |
| --- | --- |
| `main` = vendored fork + ALM + one additive ASM element | `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/actuatorSurfaceElement.{H,C}`; commit `26a1f46` |
| The described mixed-physics code is on `origin/feat/nacelle-actuator-surface` | `git log --oneline main..origin/feat/nacelle-actuator-surface` → 67 commits |
| The branch is not lost work-in-progress: it is a clean descendant of `main` | `git merge-base main origin/feat/nacelle-actuator-surface` = `93da696` = `main` tip; `git log origin/...main` is empty |
| Not checked out locally | `git branch` lists only `main`; no stashes |
| No refactor/plan document exists in any commit, and none in Engram | `git log --all --diff-filter=A --name-only` grepped for plan/refactor/architect → only `.agent/skills/architect-review/SKILL.md` (removed in `5cdbe1a`) |

So S2–S3 describe the **branch**, and the branch is the refactor target. `main` does not
contain the problem.

## Diagnosis

### The two axes that were glued together

An actuator method has two independent choices, and the branch collapsed them into one
inheritance chain:

| Axis | Meaning | Implementations in the tree |
| --- | --- | --- |
| **A — force model** (what force) | sectional coefficients → force per body | A1 ALM BEM chain; A2 ASM chord-strip element; A3 ASM-MESH redistribution over an imported triangulation; A4 nacelle/hub surface tractions; A5 hub/tower/nacelle as actuator lines |
| **B — projection** (how it reaches the field) | node/strip force → `volVectorField` | B1 Gaussian-ε strip projection; B2 uniform chord-strip distribution; B3 Eq. 18 cosine-kernel distribution over candidate cells |

Today A and B live in the same objects, so every new model had to be threaded through the
ALM classes.

### What was bolted onto the ALM core

| ALM core object | What it now carries | Evidence |
| --- | --- | --- |
| `turbineALSource` (rotor base) | FSI coupling: registry omega override + persisted azimuth | `turbineALSource.H:+32` — `hasOmegaOverride_`, `omegaOverrideField_`, `omegaOverrideFieldPtr_`, `angleDegField_`, `angleDeg()`, `createAngleDegField()`, `createOmegaOverrideField()`, `azimuth(t)` |
| `actuatorLineSource` (blade line) | owns an ASM-MESH distributor; ALM now `#include`s the surface module | `actuatorLineSource.H:+10` — `#include "bladeSurfaceSource.H"`, `surfaceGeometry_`, `autoPtr<bladeSurfaceSource> surface_` |
| `actuatorLineElement` (BEM element) | (a) Du-Selig rotational augmentation inside the shared load chain; (b) a routing flag; (c) getters that exist only for the surface sampler | `actuatorLineElement.H:+44` — `rotationalAugmentation*`, `radius_`, `rotorRadius_`, `projectElementForce_`, `chordDirection()`, `chordMount()`, `spanDirection()`, `profileDict()`; `actuatorLineElement.C` calls `correctRotationalAugmentation()` inside `calculateForce()` |
| `axialFlowTurbineALSource` (rotor option) | a *concrete* nacelle type, replacing the line model | `axialFlowTurbineALSource.H` — `autoPtr<actuatorLineSource> nacelle_` → `autoPtr<nacelleSurfaceSource> nacelle_`; `axialFlowTurbineALSource.C:+107` builds the surface construction frame and forwards `nRotationalAugmentation` into every blade subdict |

### Why this is "different physics structured as the same physics" (S2)

1. **Inheritance used as composition.** `actuatorSurfaceElement` is an
   `actuatorLineElement` whose only real difference is inflow sampling, projection width and
   force distribution (its own header says so). A3 (`bladeSurfaceSource`) is not an element
   at all, yet it is owned by `actuatorLineSource` as if it were part of the line.
2. **A boolean standing in for a design decision.** `projectElementForce_` exists so the
   element can be told *not* to project, because a different object will. That flag is not
   physics; it is a missing interface (B1 vs B3) expressed as a per-element switch, plumbed
   through `actuatorLineSource::createElements()` with a precedence rule
   (`surface injection > blade-subdict value > element default`).
3. **Leaked internals as an API.** `chordDirection()`, `chordMount()`, `spanDirection()`,
   `profileDict()` are public getters whose only consumer is `bladeSurfaceSampler`'s
   node→element partition. The ALM element's private frame became public API for a foreign
   model.
4. **Inconsistent option-ness.** `bladeSurfaceSource` is deliberately *not* an `fv::option`
   ("not an `fv::option` and is not added to the option run-time selection table (D1)"),
   while `nacelleSurfaceSource` *is* `TypeName("nacelleSurfaceSource")` **and** an owned
   member of `axialFlowTurbineALSource`. One of the two is wrong either way; the reason is
   that the nacelle is used both standalone and composed.
5. **Sizes are a symptom.** `axialFlowTurbineALSource.C` 1121 lines,
   `actuatorLineElement.C` 1364, `actuatorLineSource.C` 917 — while `main` has 1016 / 1221 /
   799. The refactor did not add a model; it added responsibilities to existing files.

### The FSI seam is implemented three times (S3), and one of the three is frozen (S7)

The coupling contract is a name-keyed `uniformDimensionedScalarField` in the `Time` registry:

| Component | Role in the contract | In scope? | Evidence |
| --- | --- | --- | --- |
| preCICE adapter | **producer**: writes the coupled omega and creates its own field when absent | no — read-only reference | `modules/generic/Generic.C:66,123`, `ReadWrite.C:425,445` |
| `fsiOmega` | **canonical consumer**: exposes it as a `Function1` for `solidBodyMotion` | **no — frozen (S7)** | `fsiOmega/preciceOmega.C:103` |
| `turbineALSource` | **second consumer** of the same field, plus a producer of a *different* field (`angleDeg.<name>`) | yes | `turbineALSource.C` — `createOmegaOverrideField()`, `createAngleDegField()`, `updateTSROmega()` override branch |

The field name string is the entire contract, and it is not declared anywhere. Three
independent readers mean three independent ownership rules, and the divergence is
observable:

| | adapter (`ReadWrite.C:445`) | turbinesFoam (`turbineALSource.C`) |
| --- | --- | --- |
| IOobject | `runTime_.constant()`, `NO_READ`, `NO_WRITE` | `time_.constant()`, `NO_READ`, `AUTO_WRITE` |
| field absent | creates and owns an in-memory field | creates and owns an `AUTO_WRITE` field |
| field present | binds through `lookupObjectRef` | returns early and binds by name |

So whoever constructs first decides whether the coupled omega field is ever written to
disk: adapter first → memory-only; turbinesFoam first → auto-written. That is an
ordering-dependent lifecycle, not a physics difference. The contract itself belongs to the
adapter and `fsiOmega`, so any correction is on the turbinesFoam side only.

### A known open defect lives in the code this plan moves

[`efirvida/openfoam-fsi-plugins#2`](https://github.com/efirvida/openfoam-fsi-plugins/issues/2)
records that the `angleDeg.<name>` checkpoint is written on every timestep (ignoring
`writeInterval`, which creates field-less time directories and breaks `startFrom latestTime`
on a decomposed restart) and that its value is in degrees while its dimensions are
`dimensionless`, i.e. radians by OpenFOAM convention. That code is moved by F1 and F6, so
the refactor must **preserve it as-is** and leave the fix to the issue: if a phase changes
the write cadence or the units, the golden comparison for F6 is expected to fail, which is
the intended signal that a behaviour change slipped in.

## Target architecture

Three layers, one direction of dependency (`turbine` → `projection` → `aero`), plus an
explicit coupling boundary. Directory layout mirrors the layers.

```text
turbinesFoam/src/
  aero/                # A — forces. No mesh projection, no IO, no lifetime tricks.
    profileData/                     (moved, unchanged)
    dynamicStallModels/              (moved, unchanged)
    addedMassModel/                  (moved, unchanged)
    rotationalAugmentation/          NEW: model + DuSelig, extracted from the element
    sectionalLoad.{H,C}              NEW: lookup -> augmentation -> dynamic stall
                                     -> added mass -> end-effect factor
  projection/          # B — force -> field. No aerodynamics.
    forceProjector.H                 NEW: virtual project(forceField, nodes, forces)
    gaussianStripProjector.{H,C}     B1, extracted from the element
    chordStripProjector.{H,C}        B2, extracted from actuatorSurfaceElement
    surfaceGeometry.{H,C}            from surfaceSamplerBase: triSurface, nodes,
                                     normals, areas, body frame, cell size
    kernelProjector.{H,C}            B3: Eq. 8 kernel, Eq. 18 distribution,
                                     candidate bin grid + prefilter
  turbine/             # composition + kinematics. No physics.
    actuatorLineSource/              line of elements; no surface ownership
    actuatorSurfaceElement/          A2 line element (kept: it is a real line element)
    bladeModel/                      NEW: {sectional load chain, optional
                                     surfaceGeometry + projector}
    turbineComponent.H               NEW: addSup/force/forceField/rotate/moment
    nacelleActuatorLineModel/        A5 as a component
    nacelleSurfaceModel/             A4 as a component
    axialFlowTurbineALSource/        rotor kinematics + components + drag accounting
    turbineALSource/                 rotor base; no FSI fields
  coupling/            # the FSI boundary, declared once
    turbineCoupling.{H,C}            NEW: reads omegaOverrideField, publishes
                                     angleDeg.<name>, documents name+units
  interpolations/                    (moved, unchanged)
  Make/{files,options}
```

Non-C++ content leaves the plugin tree: `geometry/` (the Python loft + gmsh + STL + JSON
metadata) and `validation/` (Slurm campaigns, digitized reference data) are inputs and
harnesses, not part of `libturbinesFoam`. Keep `turbinesFoam/tests/` as the regression
corpus.

**Composition replaces the flag.** With the layers in place,
`bladeModel` is constructed as either {elements + `gaussianStripProjector`} (ALM) or
{elements + `surfaceGeometry` + `kernelProjector`} (ASM-MESH) or
{`actuatorSurfaceElement` + `chordStripProjector`} (ASM). `projectElementForce_` and the
public frame getters disappear from `actuatorLineElement`; the projector is chosen at
construction, not by a dict key.

## Out of scope

| Surface | Reason |
| --- | --- |
| `fsiOmega/` | **S7.** Separate plugin. It carries angular velocity between the FSI domains, works without turbinesFoam, and is loaded on demand by the other plugins in this repository. The refactor must not modify it, its entries, or the field contract it reads. |
| `precice-openfoam-adapter/` | Separate plugin, and the producer of the coupling contract. Read-only reference: turbinesFoam adapts to the adapter's existing contract, never the reverse. |
| `solidBodyDisplacementLaplacianZone/`, `dynamicOversetZoneDisplacementFvMesh/` | Separate plugins in the same FSI stack; not part of this refactor. |
| Physics content (below) | Another team owns it (**S5**). |

Consequences for the design: `coupling/turbineCoupling` is turbinesFoam-internal; the omega
field is consumed **read-only**, because turbinesFoam must not claim ownership of a field
another plugin produces; the azimuth publisher is a separate, turbinesFoam-owned field.
Whether turbinesFoam may keep creating the omega field at all is open decision 4.

## Frozen physics (S5 — do not touch)

These files/blocks may **move** but every formula, coefficient, constant, tolerance and
statement order is frozen. A diff that changes any of them is out of scope.

- `profileData.{H,C}` — polar tables, `hasZeroLiftReference()`, `zeroLiftAngleOfAttack()`,
  `zeroLiftDragCoeff()`.
- `dynamicStallModels/**` — all four Leishman–Beddoes variants and the base.
- `addedMassModel.{H,C}`.
- The Du-Selig block — `a_`, `b_`, `d_`, `qL/qD`, `fL/fD`, `CLp`, `CD0`, and the skip on a
  degenerate zero-lift profile. Moved verbatim out of `actuatorLineElement.C`.
- The order inside `calculateForce()`: `lookupCoefficients` → augmentation → dynamic stall →
  added mass → end-effect factor.
- `calcProjectionEpsilon()` and the Gaussian-ε formulas.
- Yang & Sotiropoulos items: cosine kernel Eq. 8 (support `|r| <= 2.5`), velocity Eq. 7,
  distribution Eq. 18, normal Eq. 19, tangential Eqs. 21–23, the candidate bin size
  (`max(min_i support_i, small)`), the axis-aligned prefilter, the 1-D Voronoi station
  partition, the chord-fraction definition, patch-area assertions.
- `surfaceSamplerBase`'s "all local cells when `candidates == nullptr`" nacelle path.

## Migration plan

Each phase is one work unit on the branch, one commit, with its own gate. No phase may be
started before the previous gate passes. Deleting nothing: A1–A5 all remain available.

| Phase | Content | Gate |
| --- | --- | --- |
| **F0** | Baseline capture. Build the branch; run the C++ integration cases under `turbinesFoam/tests/{bladeSurface,bladeSurfaceAFTAL,nacelleSurface,rotationalAugmentation,leishmanBeddoes}`; archive every `postProcessing/**/*.csv` and the `nm -D` symbol set of `libturbinesFoam.so`. No source change. | Baseline artifacts on disk and committed as fixtures |
| **F1** | Layout only: create `aero/`, `projection/`, `turbine/`, `coupling/`; `git mv` files; update `Make/files`, includes, `lnInclude` paths. Zero logic edits. | Build 0 errors; tests green; symbol set identical; `postProcessing` CSVs byte-identical |
| **F2** | Extract `rotationalAugmentation/DuSelig` from `actuatorLineElement`; element keeps the call site and the order. | Same as F1, plus the rotational-augmentation case CSVs byte-identical |
| **F3** | Split `surfaceSamplerBase` into `surfaceGeometry` + `kernelProjector` (finish what `5f357c8` started); `bladeSurfaceSampler`/`nacelleSurfaceSampler` become thin force models over them. | Same as F1; the nacelle `candidates == nullptr` path unchanged |
| **F4** | Introduce `bladeModel`; remove `surfaceGeometry_`, `surface_`, `projectElementForce_` and the four leaked getters from the ALM classes; projector chosen at construction. | Same as F1; ALM (no surface) and ASM-MESH cases byte-identical |
| **F5** | `turbineComponent` interface; nacelle becomes `nacelleActuatorLineModel` or `nacelleSurfaceModel`; `axialFlowTurbineALSource` holds a component pointer, not a concrete type. | Both nacelle configurations run; CSVs identical to F0 |
| **F6** | Extract `turbineCoupling`; `turbineALSource` keeps no FSI field; document the omega/azimuth contract (names + units) as a turbinesFoam-side declaration that references the adapter's contract. Reduce the omega side to read-only consumption. | Restart/rollback case reproduces the same azimuth series; override case reproduces the same omega; `angleDeg.<name>` output identical, including the behaviour recorded in issue #2 |
| **F7** | Move `geometry/` and `validation/` out of the plugin source tree; update the docs that reference them. | Docs updated; plugin build unaffected |
| **F8** | Optional: split `libturbinesFoam` into a core library and a surface library. Only if F1–F6 left a clean seam, because it changes every case's `libs (...)` list. | Decided with the maintainer, not unilaterally |

## Verification strategy

The branch already ships the best possible refactor oracle: the CSV writers. Per-station,
per-node and per-distribution CSVs are written at 12 significant digits
(`c53711d` "write blade surface CSVs at 12 significant digits"). So:

1. **Golden CSVs** — for every F0 fixture case, `diff` the post-refactor
   `postProcessing/**` output against the archived baseline. Byte equality is the claim.
2. **Symbol set** — `nm -D libturbinesFoam.so` before/after each phase; the run-time
   selection registrations (`defineTypeNameAndDebug` + `addToRunTimeSelectionTable`) must be
   conserved, and any moved `TypeName` string is a documented dict-compatibility break.
3. **Build** — `cd turbinesFoam && ./Allwmake` exits 0 (`src/Make/files` must list every new
   `.C`; a forgotten file is a silent missing symbol).
4. **Dict compatibility** — every key currently read must still be read, with the same
   default: `elementType`, `nChordwise`, `surfaceGeometry`, `projectElementForce`,
   `rotationalAugmentation`, `radius`, `rotorRadius`, `omegaOverrideField`, `geometry`,
   `cfModel`, `cf`, `rho`, `nu`, `referenceArea`, `logDistribution`, `writeNodePerf`.
   Removal of `projectElementForce` in F4 is the single intentional break and must be
   recorded in `CHANGELOG.md`.

No automated test suite exists for the C++ side per `AGENTS.md`; the fixtures under
`turbinesFoam/tests/**` are the harness, and `turbinesFoam/tests/` also holds the Python
integration tests. Anything that cannot be verified by 1–4 is not refactored in that phase.

## Open decisions (need a human answer before F1)

1. **Target branch.** Refactor on `origin/feat/nacelle-actuator-surface` (recommended: it is
   the only place the problem exists), or land the branch on `main` first and refactor there.
2. **F8 library split.** One library with clear directories, or separate shared libraries.
3. **`geometry/` and `validation/` destination.** Move to a sibling directory in
   `openfoam-fsi-plugins` (they are Python/harness code, not plugin code), or keep them in
   `turbinesFoam/`.
4. **Omega-field ownership.** F6 proposes reducing turbinesFoam to a read-only consumer of
   the adapter's omega field (dropping `createOmegaOverrideField()`'s creation and its
   `AUTO_WRITE`). If turbinesFoam is intentionally the field's creator so the adapter can
   bind to it early, F6 must keep creating it and the divergence with `ReadWrite.C:445`
   becomes a documented contract instead of a fix. This is a behaviour question, not a
   style one, and it needs an answer before F6.
5. ~~Where the plan is published.~~ **Resolved.** `.github/ISSUE_TEMPLATE/refactor.yml` landed on
   `main` (`18d3b45`) and the plan is published as
   [#3](https://github.com/efirvida/openfoam-fsi-plugins/issues/3).

## Risks

- **Silent physics drift.** The whole plan rests on "no formula changes". Mitigation: the
  frozen list above, the golden CSVs, and one reviewer per phase comparing the moved block
  against `git show <F0>:<file>`.
- **Dict compatibility.** Moving `TypeName` strings or dropping a key silently changes case
  behaviour for the other team. Mitigation: item 4 above.
- **Wide diff, low value.** F1 on its own is a large `git mv` with no behaviour change; it is
  justified only as the precondition for F2–F6. If the maintainer prefers, F1 can be folded
  into F2/F3/F4 per layer.
- **Test-size risk.** `turbinesFoam/tests/` is 119 files and the campaign adds 102 more under
  `validation/`. Reviewing this refactor requires the harness to be runnable, which is F0's
  real job.

## Tasks

| ID | S# | Task | Route | Commit |
| --- | --- | --- | --- | --- |
| T0 | S1, S6 | Write this plan (analysis + phases + gates) | inline | none (untracked) |
| T1 | S2, S3 | Baseline capture F0: build, run fixtures, archive CSVs + symbol set | delegate (writer) | pending |
| T2 | S1 | Confirm the three open decisions | human | — |
| T3 | S4 | F1 layout move only | delegate (writer) | pending |
| T4 | S2, S5 | F2 extract rotational augmentation | delegate (writer) | pending |
| T5 | S2, S4 | F3 split `surfaceSamplerBase` | delegate (writer) | pending |
| T6 | S2, S4 | F4 `bladeModel`, remove the routing flag and leaked getters | delegate (writer) | pending |
| T7 | S2, S4 | F5 `turbineComponent` + nacelle models | delegate (writer) | pending |
| T8 | S3, S4 | F6 `turbineCoupling` seam | delegate (writer) | pending |
| T9 | S4 | F7 move `geometry/` and `validation/`; update docs | delegate (writer) | pending |
| T10 | S5 | Independent verification of the frozen-physics list against F0 | delegate (verifier) | pending |
| T11 | S1, S6, S7 | Publish this plan (all code findings) as a repository issue | form added in `18d3b45`, issue published and read back | [#3](https://github.com/efirvida/openfoam-fsi-plugins/issues/3) |

## Log

- **L1** (user, verbatim):
  > "parece que perdi un trabajo que habia hecho sobre un plan de refactor de @turbinesFoam/
  > ahora solo necesito hacer un analisis y planificar su refactor. la preimsa es que al
  > codigo original el cual solo implementaba modelo ALM para calculo aerodinamico de
  > turbina, se le colgaron en la misma clase ASM, ASM+MESH, nacelle usando IBM, y todo son
  > fisicas diferentes estructuradas como si fueran la misma fisica. Ademas de la
  > preparacion para usar el adapter de openfoam para PreCICE para hacer FSI, entonces a modo
  > de arquitectura de software creo que necesitamos una refactorizacion que separe bien las
  > responsailidades, y sea mucho mas facil de mantener, sin tener que alterar la fisica ya
  > que eso es responsabilidad de otro equipo de trabajo"
- **L2** (parent, evidence): the code was not lost — it is `origin/feat/nacelle-actuator-surface`,
  67 commits above `main`, merge-base equal to the `main` tip. Verified with `git log`,
  `git merge-base`, `git branch`, and `git log --all --diff-filter=A` (no plan doc in history).
- **L3** (parent, correction to the premise): the "nacelle usar IBM" is not immersed-boundary
  in this tree. The nacelle is (a) an `actuatorLineSource` on `main` and (b) an actuator
  *surface* with normal/tangential tractions and a smoothed cosine kernel on the branch
  (`nacelleSurfaceSource`, Yang & Sotiropoulos Sec. 2.2). The immersed-boundary resemblance is
  in the sampling/distribution scheme, not in a mesh-immersed boundary method.
- **L4** (user, verbatim):
  > "Ahora no vamos a hacer nada, solo escribir el plan de refactorizar tal vez en un issue
  > con todos los findings de codigo. Una acotacion fsi omega es un plugin separado de
  > turbineFOAM no debe ser modificado, ya que el es usado independientemente de turineFOAM e
  > incluso es utilizado por los demas plugins en el repo a demanda. Es el encargado de pasa
  > velocidad angular entre los dominios FSI entonces no forma parte del refactor/"
- **L5** (parent, evidence): canonical repository identity is `efirvida/openfoam-fsi-plugins`
  (`gh api repos/efirvida/of-plugins` → `full_name`), default branch `main`, issues and
  discussions enabled, no `.github/ISSUE_TEMPLATE` (API 404). Duplicate search over the whole
  issue list (`--state all`, queries: refactor, modularization, nacelle, actuator, surface,
  architecture) returns exactly one issue, #2, which is a defect report on the
  `angleDeg.<name>` checkpoint and not a duplicate of this plan. `fsiOmega` in the design is
  therefore fixed as an external contract (S7) and the only files this plan edits are under
  `turbinesFoam/`. No write to GitHub has occurred.
- **L6** (parent, delivery): added `.github/ISSUE_TEMPLATE/refactor.yml` to the default branch
  (commit `18d3b45`, pushed) so the plan has a format authority, then published this plan as
  [#3](https://github.com/efirvida/openfoam-fsi-plugins/issues/3) with the label
  `enhancement`, and verified it by target-host read-back: title and body match, state `OPEN`.
  Duplicate search (open and closed) found no equivalent; #2 is a related defect report and is
  referenced as F8. No source file under `turbinesFoam/` was modified.
