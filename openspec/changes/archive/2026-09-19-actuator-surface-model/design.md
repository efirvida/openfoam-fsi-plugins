# Design: Blade actuator surface model (ASM) for turbinesFoam

## Technical Approach

Complete the vestigial element run-time-selection table that `actuatorLineElement`
already declares (but never implements), then add `actuatorSurfaceElement` as a
run-time-selected subclass that overrides exactly the three hooks whose behavior
differs from the line model. The BEM force chain (`calculateForce`: coefficient
lookup, dynamic stall, added mass, end effects, CSV output) is inherited
untouched. This is **Option 2 (polymorphic element)** from `exploration.md`.

The ALM default path stays byte-identical: virtualization preserves the three
method bodies as unchanged defaults, and `createElements` switches from
`new actuatorLineElement(...)` to `actuatorLineElement::New(...)` with an
`elementType` default that constructs the base class directly.

## Architecture Decisions

### Decision: Element RTS constructor signature — redefine to `(name, dict, mesh)`

**Choice**: Change the `declareRunTimeSelectionTable` constructor signature from
the vestigial `(const dictionary& dict, const word& modelName)` to
`(const word& name, const dictionary& dict, const fvMesh& mesh)`, matching the
real constructor; replace the stale `New(const dictionary&)` selector with
`New(name, dict, mesh)`; keep `defineRunTimeSelectionTable(actuatorLineElement, dictionary)`
unchanged.
**Alternatives considered**:
- Keep `(dict, modelName)` and thread `name`/`mesh` separately — impossible: the
  element cannot be constructed without `name` and `mesh`, neither of which the
  declared signature carries. The signature was never wired (no `New` definition,
  no registrations), so it is free to correct.
- Self-register the base class in its own table (`addToRunTimeSelectionTable(base, base, ...)`).
**Rationale**: Matches the repo's own working idiom — `dynamicStallModel` declares
the table with the full constructor arg list and defines `New` manually in the `.C`.
`defineRunTimeSelectionTable(baseType, argNames)` is independent of the constructor
arg list (both `dynamicStallModel` and `actuatorLineElement` already pass `dictionary`
as `argNames`), so the `define` line does not change.

### Decision: `New` default branch constructs the base directly

**Choice**: In `New`, resolve `elementType = dict.lookupOrDefault<word>("elementType", typeName)`;
if it equals `actuatorLineElement::typeName`, return `autoPtr(new actuatorLineElement(name, dict, mesh))`;
otherwise look up the table and `FatalErrorInFunction` on unknown type.
**Alternatives considered**: Self-registration of the base type (rejected — unusual,
adds a table entry whose only job is the default); always table-lookup with no base fallback
(rejected — would require registering the base, same objection).
**Rationale**: The default (key absent) and the explicit `actuatorLineElement` case both
construct the concrete base with zero behavior change; only genuinely new derived types hit
the table. This satisfies the `element-type-selection` spec scenarios exactly
(default, explicit, unknown → RTS error).

### Decision: Three virtualized hooks, unchanged default bodies

**Choice**: Add `virtual` to `calculateInflowVelocity`, `applyForceField`,
`calcProjectionEpsilon` only. `read`, `calculateForce`, `lookupCoefficients`,
`writePerf` stay non-virtual.
**Alternatives considered**: Virtualize more (e.g. `read`, `calculateForce`) —
unnecessary; ASM reuses those wholesale. Inline `surfaceModel` branches (Option 1) —
rejected per exploration (flag sprawl, couples ALM code).
**Rationale**: These three are exactly the methods the surface model changes
(inflow sampling, force spreading, projection width). `addTurbulence` and both
`addSup` overloads already call `calcProjectionEpsilon()`/`applyForceField()`
through the base, so the surface epsilon/spreading overrides propagate to
turbulence injection and the compressible path with no further edits.

## Interfaces / Contracts

RTS table + selector (in `actuatorLineElement.H`):

```cpp
declareRunTimeSelectionTable
(
    autoPtr,
    actuatorLineElement,
    dictionary,
    (
        const word& name,
        const dictionary& dict,
        const fvMesh& mesh
    ),
    (name, dict, mesh)
);
// Selectors
static autoPtr<actuatorLineElement> New
(
    const word& name,
    const dictionary& dict,
    const fvMesh& mesh
);
```

`New` implementation (in `actuatorLineElement.C`), following `dynamicStallModel::New`:

```cpp
autoPtr<actuatorLineElement> actuatorLineElement::New
(
    const word& name, const dictionary& dict, const fvMesh& mesh
)
{
    const word elementType =
        dict.lookupOrDefault<word>("elementType", actuatorLineElement::typeName);

    if (elementType == actuatorLineElement::typeName)
    {
        return autoPtr<actuatorLineElement>
        (
            new actuatorLineElement(name, dict, mesh)
        );
    }

    auto cstrIter = dictionaryConstructorTablePtr_->find(elementType);
    if (cstrIter == dictionaryConstructorTablePtr_->end())
    {
        FatalErrorInFunction
            << "Unknown actuator element type " << elementType << nl << nl
            << "Valid element types are: " << nl
            << dictionaryConstructorTablePtr_->sortedToc()
            << exit(FatalError);
    }
    return cstrIter()(name, dict, mesh);
}
```

`actuatorSurfaceElement` members (only one new member; everything else inherited):

```cpp
class actuatorSurfaceElement : public actuatorLineElement
{
protected:
    label nChordwise_;
    vector chordPoint(label k) const;   // X_k (chord-strip midpoint)

    // Overrides (virtual in base, unchanged default bodies)
    scalar calcProjectionEpsilon() override;
    void calculateInflowVelocity(const volVectorField& Uin) override;
    void applyForceField(volVectorField& forceField) override;
public:
    TypeName("actuatorSurfaceElement");
    actuatorSurfaceElement(const word& name, const dictionary& dict, const fvMesh& mesh);
    virtual ~actuatorSurfaceElement() {}
};
```

Constructor: `actuatorLineElement(name, dict, mesh)` base init, then
`nChordwise_(dict.lookupOrDefault<label>("nChordwise", 5))`.

## Data Flow

```
createElements (actuatorLineSource.C)
  └─ builds per-element dict (+ elementType, nChordwise from coeffs_)
       └─ actuatorLineElement::New(name, dict, mesh)
            ├─ elementType == "actuatorLineElement" → new actuatorLineElement  (ALM, unchanged)
            └─ elementType == "actuatorSurfaceElement" → RTS table → new actuatorSurfaceElement
                 └─ calculateForce(Uin) [inherited]
                       ├─ calculateInflowVelocity()  → chord-averaged mean at X_k  [override]
                       └─ ... BEM chain (coeffs, stall, added mass, end effects) → forceVector_
                 └─ applyForceField() → strip-wise Gaussian at each X_k  [override]
                 └─ calcProjectionEpsilon() → 2·cbrt(V)·meshFactor  [override]
```

## Algorithms (paper → code)

| Paper (arXiv:1702.02108v4) | Code |
|---|---|
| Chord surface from radial stations | `chordPoint(k)`: `X_k = position_ + (chordMount_ - f_k)·c·unit(chordDirection_)`, `f_k = (k+0.5)/nChordwise_`, `k=0..nChordwise_-1` |
| Chord-averaged `u_x`,`u_theta` (Eqs. 5–6) | Arithmetic mean of `interpolationCellPoint<vector> UInterp(Uin).interpolate(X_k, cellI)` |
| `f(X) = (L+D)/c` uniform chordwise (Eq. 17) | `stripForce = forceVector_/nChordwise_` per strip |
| Delta kernel (Eq. 8, 5-cell cosine) | Existing 3D Gaussian (documented adaptation), `epsilon = 2·cbrt(V)·meshFactor` |
| Spreading (Eq. 18, area weights) | Per-strip Gaussian; total force preserved by construction (normalized kernel) |
| Tip/stall corrections | Inherited (end effects, dynamic stall, added mass) — unchanged |

**Chord-averaged inflow** (`calculateInflowVelocity` override): for each `k`,
sample with the existing `reduce(sampleVelocity, minOp<vector>())` sentinel and
`findCell` (bounding-box guarded) and `FatalErrorInFunction` when
`not (sampleVelocity[0] < VGREAT)` — byte-identical to the base circle-sampling
fatal-on-unreachable behavior.

**Strip-wise projection** (`applyForceField` override): one pass over cells with a
bounding-box prefilter around the chord line inflated by `sphereRadius` (=
`chordLength_ + projectionRadius`), and an inner loop over the `nChordwise_` chord
points; per-point `dis = mag(C[cellI] - X_k)`, Gaussian
`factor = exp(-(dis/epsilon)^2)/(epsilon^3·π^1.5)`, accumulating
`forceField[cellI] += -stripForce·factor`. `projectionRadius = epsilon·sqrt(log(1/0.001))`
as in the base. Cost bounded to `~nChordwise_ × candidates` (one cell pass).

**Mesh-only epsilon** (`calcProjectionEpsilon` override): replicate the mesh branch
of the base without the chord/drag threshold —
`epsilon = 2·cbrt(V[findCell(position_)])·meshFactor`, `reduce(epsilon, minOp<scalar>())`,
`FatalErrorInFunction` if `not (epsilon < VGREAT)`. `meshFactor` still read from
`profileData` `GaussianCoeffs`.

**Debug output**: `Info<<` chord points, per-strip epsilon, and strip count under
`debug`, matching base style (`actuatorSurfaceElement 1` in test `debugSwitches`).

## Config / Back-compat

`createElements` (after `dict.add("writePerf", ...)`, mirroring the
`velocitySampleRadius`/`nVelocitySamples` pass-through):

```cpp
dict.add("elementType", coeffs_.lookupOrDefault<word>("elementType", "actuatorLineElement"));
dict.add("nChordwise",  coeffs_.lookupOrDefault<label>("nChordwise", 5));
```

and replace the construction site with:

```cpp
autoPtr<actuatorLineElement> element = actuatorLineElement::New(name, dict, mesh_);
elements_.set(i, element);
```

AFTAL/CFTAL inject the user blade subdict unchanged, so `elementType`/`nChordwise`
reach every element with **zero turbine-class changes** (verified in exploration).
Existing cases (no new keys) construct `actuatorLineElement` via the `New` default
branch — the ALM path is byte-identical.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `.../actuatorLineElement/actuatorLineElement.H` | Modify | `virtual` on 3 hooks; RTS signature → `(name, dict, mesh)`; `New` selector → 3-arg |
| `.../actuatorLineElement/actuatorLineElement.C` | Modify | Define `New` (type-from-dict, base default branch, table lookup, fatal unknown) |
| `.../actuatorLineElement/actuatorSurfaceElement.{H,C}` | Create | ASM subclass: `nChordwise_`, `chordPoint`, 3 overrides, RTS registration |
| `.../actuatorLineSource/actuatorLineSource.C` | Modify | `createElements`: `New` + `elementType`/`nChordwise` pass-through |
| `turbinesFoam/src/Make/files` | Modify | Add `.../actuatorLineElement/actuatorSurfaceElement.C` after `actuatorLineElement.C` |
| `turbinesFoam/tutorials/axialFlowTurbineASM/` | Create | AFTAL copy + ASM blade config + truncated `controlDict` |
| `turbinesFoam/tutorials/axialFlowTurbineASM/compareALMvsASM.py` | Create | ALM-vs-ASM comparison script |
| `turbinesFoam/tests/test_asm.py` | Create | Static AL case, ALM-vs-ASM CSV checks |
| `turbinesFoam/tests/test_aftal_asm.py` | Create | HAWT ASM case test |
| `turbinesFoam/tests/axialFlowTurbineASMSource/` | Create | ASM test case dir (`getTutorialFiles.sh`, `debugSwitches`, `.gitignore`) |
| `turbinesFoam/README.md`, root `README.md`, root `CHANGELOG.md` | Modify | Config keys, tutorial, kernel-adaptation, HAWT-only, fork-divergence notes |

Deleted: none.

## Tutorial + Tests Design

**`tutorials/axialFlowTurbineASM/`**: copy of `axialFlowTurbineAL/`; add to the
`blade1` subdict in `system/fvOptions`:
`elementType actuatorSurfaceElement;` and `nChordwise 5;` (blades 2/3 inherit via
`$blade1`); reduce `controlDict` `endTime` (e.g. `0.1`) for bounded runtime. `Allrun`
(`bash`) is copied unchanged (deletes `reconstructPar` in tests, as today).

**`compareALMvsASM.py`**: inputs = two run dirs (`--alm ../axialFlowTurbineAL`,
`--asm .`); reads `postProcessing/turbines/0/turbine.csv` (Cp/CT/TSR vs angle) and
`postProcessing/actuatorLineElements/0/*.csv` (spanwise `cl`, `alpha_deg`, `rel_vel_mag`,
`root_dist`, `c_ref_t/n`, `f_ref_t/n`); prints side-by-side mean Cp/CT and spanwise
tables (optionally writes `comparison.csv` / PNG). Missing/incomplete dir → prints the
missing input and exits nonzero (spec scenario), never fabricates a comparison.

**`tests/test_asm.py`**: mirror `test_al.py` — reuse `tests/actuatorLineSource/`
static case, `sed` `elementType actuatorSurfaceElement;` + `nChordwise 5;` into
`fvOptions`, run, assert: `grep Selecting finite volume options`, element CSV exists,
force preserved (`Σ stripForce ≈ forceVector_` via line-CSV `f_ref_n/t` unchanged vs
ALM), and an optional Python expected-value check that chord-averaged `rel_vel_mag`
differs from single-point ALM on a known flow.

**`tests/test_aftal_asm.py` + `tests/axialFlowTurbineASMSource/`**: mirror
`test_aftal.py`/`axialFlowTurbineALSource` — `getTutorialFiles.sh` copies the ASM
tutorial, `sed` reduces `endTime` to `0.003`, appends `debugSwitches`
(`actuatorSurfaceElement 1`), asserts turbine + element CSVs exist and run reaches
`End` (serial) / `Finalising parallel run` (parallel). ALM regression gate =
existing `test_libs`, `test_al`, `test_aftal`, `test_cftal` unchanged.

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Build | `libturbinesFoam.so` links, no undefined symbols | `./Allwmake` + `ldd -r` (SDumont recipe) |
| Unit | None (no C++ framework) | Optional Python expected-value for chord-average in `test_asm.py` |
| Integration (ALM gate) | Existing `test_libs/al/aftal/cftal` unchanged | Full pytest suite passes byte-identical |
| Integration (ASM) | Element type selection, chord-average, force preservation | `test_asm.py` CSV/grep assertions |
| Integration (ASM HAWT) | Tutorial runs, writes CSVs, bounded runtime | `test_aftal_asm.py` serial + parallel |
| E2E | ALM-vs-ASM side-by-side | `compareALMvsASM.py` against both run dirs |

## Failure Modes, MPI, Performance

- **Unknown `elementType`** → `FatalErrorInFunction` listing `sortedToc()` of valid types.
- **Chord point outside mesh / unreachable processor** → existing `findCell` +
  `reduce(minOp)` sentinel; `FatalErrorInFunction` when `not (v[0] < VGREAT)` — same as base.
- **Position not found for epsilon** → `FatalErrorInFunction`, same as base.
- **MPI**: all reductions reuse the base `minOp<scalar|vector>` sentinels; chord points
  may live on a different rank than `position_` — each point is resolved independently
  via bounding-box `findCell`, so this is already handled by the existing pattern.
- **Performance**: one cell pass per element with bounding-box prefilter + inner chord
  loop bounds cost to `~nChordwise_ × candidates`; default `nChordwise_=5`.
- **Epsilon semantics**: mesh-only epsilon on coarse tutorial meshes makes ASM ≈ ALM
  (kernel ≈ cell size) — documented; benefits require finer mesh and Nε≥1–2 overlap.

## Threat Matrix

N/A — no routing, shell commands, subprocesses, VCS/PR automation,
executable-file classification, or process-integration boundary is introduced. The
change is pure C++ physics/geometry inside `libturbinesFoam`.

## Migration / Rollout

No migration required — additive, opt-in config. Rollback: remove/omit
`elementType`/`nChordwise` (behavior reverts without recompile), or `git revert`
the work units (no schema, no generated artifacts outside the new tutorial/tests).

## Delivery / Review-Budget Flag (record, not decided)

W1 (core) + W2 (tutorial/tests/docs) ≈ **850–1050 changed lines** vs the 400-line
review budget under `single-pr`. This is recorded for `sdd-tasks`/`sdd-apply`; the
delivery-shape decision (chained/stacked slices [W1 core] → [W2 tutorial/tests/docs]
vs explicit `size:exception`) belongs to the orchestrator/user before apply. **This
design does not choose.**

## Open Questions

1. **Delivery shape (BLOCKING, not decided here)**: chained PRs vs `size:exception` for W1+W2.
2. `nChordwise` default 5 (proposal commits) vs 8 (Zormpa Fig. A1 suggests convergence at N=8) — non-blocking; keep 5.
3. Comparison-script location/name (`tutorials/axialFlowTurbineASM/compareALMvsASM.py`) — confirm acceptable vs a shared `scripts/`.
