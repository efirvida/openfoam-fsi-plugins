# Plugin rename: cost analysis and deprecation options

**Status:** analysis only. No rename is authorised by this document. Plugin names are
unchanged, by decision.
**Published:** [efirvida/openfoam-fsi-plugins#4](https://github.com/efirvida/openfoam-fsi-plugins/issues/4).
**Question it answers:** what does it actually cost to rename a plugin here, at each level of
the name, and how do existing cases survive it?

## Why this document exists

The repository name already changed: `of-plugins` → `openfoam-fsi-plugins` (GitHub redirects
the old URL, and the stale references in `AGENTS.md` and `turbinesFoam/README.md` are fixed).
Plugin names were deliberately left alone, because unlike the repository name they are part of
the **case contract**: they appear inside `controlDict`, `dynamicMeshDict` and `fvOptions`
dictionaries that users have already written. This document measures that contract so the
rename can be decided with the cost visible instead of by taste.

## Level 0 — the name contract

Every level is a separate decision with a different blast radius.

| Level | Current value | Consumed by | Renaming breaks |
| --- | --- | --- | --- |
| Directory | `solidBodyDisplacementLaplacianZone/`, `dynamicOversetZoneDisplacementFvMesh/`, `fsiOmega/`, `precice-openfoam-adapter/`, `turbinesFoam/` | build scripts, docs, CI paths | nothing at run time |
| Library | `libsolidBodyDisplacementLaplacianZoneFvMotionSolver.so`, `libdynamicOversetZoneDisplacementFvMesh.so`, `libfsiOmega.so`, `libpreciceAdapterFunctionObject.so`, `libturbinesFoam.so` | `motionSolverLibs` and `libs (...)` in every case | every existing case, at load time |
| `dynamicFvMesh` type | `dynamicOversetZoneDisplacementFvMesh` | `dynamicMeshDict` | every overset case |
| `motionSolver` type | `solidBodyDisplacementLaplacianZone` | `dynamicMeshDict` | every motion case, **and** the coeffs dictionary name |
| Coeffs dictionary | `solidBodyDisplacementLaplacianZoneCoeffs`, `preciceOmegaCoeffs` | `dynamicMeshDict` | derived from the type name, so it changes with it |
| `Function1` type | `preciceOmega` | `omega preciceOmega;` | every FSI rotation case |
| `fvOptions` types | `axialFlowTurbineALSource`, `crossFlowTurbineALSource`, `actuatorLineElement`, `actuatorSurfaceElement`, `nacelleSurfaceSource`, the four `LeishmanBeddoes*` models | `type`, `elementType`, `dynamicStallModel` keys | every turbine case |
| Registry field | `omega` | `preciceOmegaCoeffs { fieldName }` **and** `preciceDict { nameOmegaField }` | the adapter boundary, **not this repository alone** |

## Level 1 — measured blast radius

Measured with `grep -rIl` over the repository (excluding `node_modules`):

- **20 files** reference a library `.so` name: the two `Make/files`, six tutorial
  `controlDict`s, the Phase VI case `controlDict` and its tooling
  (`tools/generate_case.py`, `scripts/check_environment.sh`), `turbinesFoam/tests/conftest.py`,
  `turbinesFoam/tests/test_libs.py`, and the documentation.
- **25 files** reference the dictionary keys or type names.
- **No CI impact from a directory rename.** The adapter's workflows live under
  `precice-openfoam-adapter/.github/workflows/`, which GitHub never executes (workflows are
  only read from the repository root), and they contain no `working-directory` and no reference
  to the directory name. The repository root has no workflows either.

## Level 2 — the three tiers

| Tier | Scope | Breaking? | Work |
| --- | --- | --- | --- |
| **T1** | directory names only | no | `git mv` + docs + the `Make/files` paths. Historical references in `validation/**/PROVENANCE.md` stay as the historical record they are |
| **T2** | directories + library names, dict keys untouched | yes, at load time | rewrite `libs (...)` / `motionSolverLibs` in every case, or ship the old filename as a symlink/shim for one release |
| **T3** | type and dictionary keys (`dynamicFvMesh`, `motionSolver`, `...Coeffs`, `type`, `elementType`, `dynamicStallModel`) | yes, in the case files | the T2 work plus every dict key, plus a documented migration |

**Out of bounds regardless of tier:** the `omega` registry field name and anything under
`fsiOmega/`. That name is the coupling contract between the preCICE adapter, `fsiOmega` and the
motion solver; `fsiOmega` is a separate plugin and frozen, so renaming `omega` would require
all three to move together.

## Level 3 — deprecation mechanism, if T2 or T3 is chosen

- OpenFOAM's run-time selection tables support an alias:
  `addNamedToRunTimeSelectionTable(base, Class, dictionary, "legacyName")` registers the same
  implementation under a second dictionary key, so old cases keep loading.
- The coeffs dictionary name is **derived from the type name**, so an alias keeps the legacy
  key working but a case written with the new name needs the new `...Coeffs` dictionary. A
  compatibility shim must therefore accept both keys, not only both names.
- For a library rename, ship the new `.so` and keep the old filename as a symlink (or a thin
  copy) for one release; the root `Allwmake`/`Allclean` have to create and remove it.
- A hard break is defensible for a research repository with few external cases; if it is
  chosen, a documented `sed` migration over `system/*Dict` is the cheapest honest path.

## Level 4 — open decisions

1. Which tier: directories only (T1), directories plus libraries (T2), or everything (T3)?
2. Which names. `dynamicOversetZoneDisplacementFvMesh` is the longest and the least
   self-descriptive of the five.
3. One release with aliases, or a hard break with a migration script?
4. Does the new naming scheme want a common prefix (`foamFsi*`), or the current descriptive
   style kept?

## Recommendation (a plan, not an authorisation)

T1 is cheap, breaks nothing and can be done as its own work unit whenever the names are
settled. T2 should wait until the names stop moving, because it rewrites every case. T3 should
never touch `omega`.
