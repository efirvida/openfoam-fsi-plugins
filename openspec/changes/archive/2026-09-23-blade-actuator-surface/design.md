# Design: Blade actuator surface model over an imported blade mesh (S2)

Change: `blade-actuator-surface` — slice **S2** of a staged program
(S1 = `nacelle-actuator-surface`, archived 2026-09-20; S3 = preCICE FSI,
deferred). Reference: Yang & Sotiropoulos, *A new class of actuator surface
models for wind turbines*, arXiv:1702.02108v4; equation numbers below are the
paper's own (Sec. 2.1 = blade ASM, Sec. 2.2 = nacelle ASM).

Status note: this document was produced from the proposal, the eight delta
specs, `exploration.md`, and a direct read of the cited sources. Every code
claim carries a `file:line` reference into the tree at the time of writing.
The S809 source facts (PDF hashes, table locations, point counts) were verified
live during design; they are recorded in §3 D11 and §7.4.

---

## 1. Technical Approach

S2 replaces the **geometry of the force distribution** of the delivered blade
ASM, nothing else. The BEM chain, the chord-averaged inflow, dynamic stall,
added mass and end effects stay exactly as delivered
(`actuatorLineElement.C:726-849`, `actuatorSurfaceElement.C:154-205`); the
surface does **not** sample per-node inflow and does **not** recompute BEM loads
(spec `blade-surface-source`, "Distribution-only model"). What changes is where
each element's force lands in the momentum field: on the triangle centroids of
an imported, committed blade triangulation instead of on `nChordwise` chord
strips around the element position.

The change is built from four pieces:

1. **A shared surface-sampling base** (`surfaceSamplerBase`) extracted from S1's
   `nacelleSurfaceSampler` (`nacelleSurfaceSampler.H:100-283`): `triSurface`
   load, centroid node set, body-frame transform, `cellSize()`, the paper's
   cosine kernel and the kernel distribution helper. The nacelle keeps its
   direct-forcing/friction force model and static frame; its observable behavior
   is regression-gated.
2. **A per-blade distributor** (`bladeSurfaceSource`, a helper owned by the
   blade `actuatorLineSource`, not an independent `fv::option`; §3 D1) that
   reads the committed blade STL, associates each node with its radial station
   and chord fraction, computes the node→element partition once per blade,
   consumes the elements' BEM forces after the element loop, distributes them
   with a bounded candidate-cell query, follows the blade's rotate/pitch/
   translate calls, and emits the per-station/per-node CSV and the SI
   `positions()/forces()` contract.
3. **An additive suppression key** (`projectElementForce`, default `true`)
   injected by `actuatorLineSource::createElements()` only when
   `surfaceGeometry` is configured, guarding the two
   `applyForceField(...)` call sites (`actuatorLineElement.C:1074-1075`,
   `:1113-1114`) so the strip projection never reaches the field while
   `calculateForce()` and `writePerf()` keep running.
4. **A deterministic blade geometry component** (`phaseVI_blade`) in the shared
   `turbinesFoam/geometry/` pipeline: committed S809 coordinates extracted from
   the verified Somers PDF, a pure-Python structured loft over all 26 committed
   stations, a canonical binary STL, per-node `radial_station`/`chord_fraction`
   metadata, and a byte-identical `--check` that needs no gmsh.

Phase VI consumes the result as a third model twin `fvOptions.ASM-MESH`
(`-m asm-mesh`), staged into self-contained run directories, with a three-way
comparison that reuses the existing bands and sign gate, and a prepared-only
Slurm array. Nothing is submitted by this change.

### 1.1 Formulation being implemented (explicit)

The paper's blade ASM is **chord-line based**: "the blade geometry is
represented by a surface formed by the chord lines at different radial
locations" (Sec. 2.1); the force per unit area is uniform chordwise,
`f(X) = (L + D)/c` (Eq. 17), and it is spread by the smoothed kernel (Eq. 18).
S2 replaces the chord lines with a triangulated surface — the same move S1 made
for the nacelle ("the nacelle geometry is represented by the actual surface",
Sec. 2.2). This is an **extension of the paper's blade ASM**, not a literal
equation port. The BEM content (Eqs. 1-16) is unchanged, and the distribution
law (Eq. 18) with the paper's cosine kernel is the default. §2 records the
mapping.

### 1.2 Work decomposition (delivery forecast)

| Unit | Content | Est. lines |
|------|---------|-----------|
| W1 | Shared base extraction, `bladeSurfaceSource` + `bladeSurfaceSampler`, suppression plumbing, bounded distribution, rotation lockstep, CSV, `Make/files`, `test_blade_surface.py` + `tests/bladeSurface/`, turbinesFoam README | ~600–900 |
| W2 | S809 dataset + PROVENANCE, `phaseVI_blade` builder, canonical STL + metadata, builder registry, `test_blade_data.py`, `test_nacelle_data.py` update, geometry README/PROVENANCE | ~400–600 |
| W3 | `fvOptions.ASM-MESH` twin, `case.yaml`/renderer/`--select`, runner + STL staging, three-way compare, prepared-only array, case/compare tests, README/CHANGELOG | ~400–600 |
| W4 | Performance measurement gate: prepared measurement case/array; conditional candidate-query hardening only if the gate demands it | ~150–350 |

Forecast total **~1550–2450 changed lines**, far over the 400-line `single-pr`
review budget. This is a **delivery-shape decision for the orchestrator/user
before `sdd-apply`** (chained PR slices W1→W2→W3→W4 vs an explicit
`size:exception`), recorded in the proposal; the design makes every unit
independently testable and revertable (§9).

---

## 2. Paper → Code Mapping

The config rule (`openspec/config.yaml` `rules.design`) requires a paper → code
table. S2 implements **distribution geometry only**, so the table covers the
distribution equations plus the BEM chain entry points S2 consumes without
modifying. Units and signs are restated once, authoritatively, for the new
surface path.

### 2.1 Dimensional chain and sign conventions

The existing element force is computed per unit density: `forceVector_` is
`0.5*area*CL*|V|²`-based (`actuatorLineElement.C:833-841`) and
`actuatorLineSource::force_` is documented as "per unit density"
(`actuatorLineSource.C:710`). The nacelle source distributes the same kind of
per-unit-density quantity (`nacelleSurfaceSource.C:119,149`). The blade
distributor therefore works in the same chain:

| Step | Quantity | Units | Where it lives |
|------|----------|-------|----------------|
| 1 | Element BEM force per unit density | m⁴/s² (N/ρ) | `actuatorLineElement::forceVector_` (`:115`), public `force()` (`:1032-1035`) |
| 2 | Node share of the element force (patch area weighting) | m⁴/s² | `bladeSurfaceSource` patch share (§4.3) |
| 3 | Distributed body force | m/s² | `bladeSurfaceSource::distribute()` into the blade `forceField_` |
| 4 | Field storage | `dimForce/dimVolume` | `actuatorLineSource::forceField_` (`actuatorLineSource.C:518-535`) |
| 5 | SI contract | N | `bladeSurfaceSampler::forces()`, `rhoRef_ * F_i` (S1 convention, `nacelleSurfaceSource.C:150-151`) |

**Sign**: the element's `force()` is the force **on the blade** (its lift/drag
are computed from the relative velocity, `actuatorLineElement.C:833-841`). The
field receives the reaction, exactly as `applyForceField` does
(`forceField[cellI] += -forceVector_*factor`, `:395`) and as the nacelle
distribution does (`ff[cellI] -= F*(w/mesh_.V()[cellI])`,
`nacelleSurfaceSource.C:205`). The blade distributor reuses the S1 distribution
sign; the contract lists keep the force-on-blade sign.

**Conservation**: the kernel is volume-normalised, so
`Σ_c δ_h·V_c = 1` and the field integral equals the sum of the distributed node
forces; the node→element partition is a partition (every node in exactly one
patch), and each element's force is shared over its patch proportionally to
patch area **and then spread with the same kernel**; therefore the field
integral equals the summed element forces exactly once. The integration test of
§8 asserts this on a real solver run (partition-of-unity / no-double-count).

### 2.2 Equation → code table

| Paper Eq. | Meaning | S2 code location | Notes |
|-----------|---------|------------------|-------|
| **Eq. 17** — `f(X) = (L + D)/c`, uniform chordwise | Blade surface force density | Not re-implemented | The element force is the BEM `forceVector_`; the distributor only changes *where* it is applied. No chordwise non-uniform model is added. |
| **Eq. 18** — `f(x) = −Σ f(X)·δ_h(x−X)·A(X)` | Surface → grid distribution | `surfaceSamplerBase::kernel()` (moved from `nacelleSurfaceSampler.C:374-404`) + `bladeSurfaceSource::distribute()` | Same separable kernel and `−F·(1/V_c)·φφφ` expression as S1 (`nacelleSurfaceSource.C:194-205`), evaluated over a **bounded candidate list** (§3 D6) instead of all local cells. |
| **Eq. 8** — `φ(r)` smoothed 4-point cosine, `|r| ≤ 2.5` | Default kernel | `surfaceSamplerBase::kernel()` | Default `kernel cosine`; support `2.5·h_i` per axis. |
| **Eq. 7** — `u(X) = Σ u(x)·δ_h·V(x)` | Kernel velocity interpolation | `surfaceSamplerBase::interpolateVelocity()` (moved verbatim from `nacelleSurfaceSampler.C:407-463`) | **Not called by the blade path** (distribution-only); kept in the base for the nacelle and as the S3 seam. |
| **Eqs. 1-16** — BEM chain | Coefficient lookup, dynamic stall, added mass, end effects, chord-averaged inflow | Unchanged: `actuatorLineElement::calculateForce` (`:726-849`), `actuatorSurfaceElement::calculateInflowVelocity` (`:154-205`) | The distributor consumes the result; it never recomputes it. |
| **S1 Gaussian analogue** — `ε = 2·cbrt(V)·meshFactor` | No-mesh ASM projection width | `actuatorSurfaceElement::calcProjectionEpsilon` (`:61-100`) | Reimplemented for the surface as the `kernel gaussian` ablation mode, per node, with the same `meshFactor` default source (§3 D7). |

---

## 3. Architecture Decisions

### D1 — Per-blade distributor owned by the blade source (proposal Decision 1)

**Choice**: One `bladeSurfaceSource` per blade, constructed by
`actuatorLineSource` when its subdictionary carries `surfaceGeometry`, over the
shared sampling base. The distributor consumes `elements_[i].force()` after the
element loop of `actuatorLineSource::addSup` (`actuatorLineSource.C:704-708`)
and writes into that blade's `forceField_`/`force_`. AFTAL's composition is
untouched; the per-blade surface inherits the existing transform forwarding
(`actuatorLineSource.C:577-647`).

**C++ shape of the "source"**: `bladeSurfaceSource` is a **plain helper class**
(the `bladeSurfaceSampler` + partition + CSV owner), not an `fv::option`, and it
is **not** added to the option RTS. Its force input is the owning blade's
`PtrList<actuatorLineElement>` and its sink is that blade's `forceField_`, so it
has no independent dictionary lifecycle, selection mode or `addSup(eqn, fieldI)`
semantics to expose; the `cellSetOption` machinery already lives in the owning
`actuatorLineSource`. S1's `cellSetOption`/RTS skeleton
(`nacelleSurfaceSource.C:280-431`) is reused **as a pattern** for the CSV and
`read()` plumbing only. Rejected alternative: registering
`bladeSurfaceSource` as a standalone `type bladeSurfaceSource;` option — it
could not construct a meaningful force without the blade elements, so the
registration would advertise a configuration that cannot run.

**Alternatives considered**:

- **New element type `bladeSurfaceElement`** (exploration 1B): the element owns
  its slice of the imported surface. Rejected because each of the 50 elements
  would need a consistent view of the same blade triangulation (shared cache),
  the patch edges would have to agree across 50 objects, and the double-count
  hazard is multiplied rather than removed. Kept as the documented fallback.
- **Generalized source with a force-model switch** (exploration 1C): rejected —
  the nacelle's direct-forcing/friction model and the BEM-element distribution
  share only geometry and kernel; a single parameterized class would be a
  conditional god-class and would re-open the archived S1 code for no
  functional gain.

**Rationale**: the BEM element forces already exist and are already validated;
the only new physics is "where does each force land". One owner per blade makes
the partition a single object's invariant (patch areas sum to the blade area),
keeps the element CSV and public `force()` untouched, and gives S3 a single
per-blade sampling contract object to consume.

### D2 — Shared base extraction, nacelle byte-identical (proposal Decision 1)

**Choice**: Extract the generic assets of `nacelleSurfaceSampler` into
`surfaceSamplerBase`; `nacelleSurfaceSampler` becomes a subclass that keeps its
force model and static body frame; `bladeSurfaceSampler` subclasses it for the
rotating frame. Exact split:

| Asset (current location) | Moves to base | Stays in nacelle | Notes |
|---|---|---|---|
| `mesh_`, `surface_`, `positions_`, `normals_`, `areas_` (`nacelleSurfaceSampler.H:108-120`) | yes | — | centroid node set, stable face order |
| `positionsBody_`, `normalsBody_`, `bodyOrigin_`, `bodyToGlobal_`, `identityBodyFrame_` (`:122-143`) | yes | — | body-frame transform, `createBodyFrame` (`:36-93`) |
| `cellSize()` (`:269-292`) | yes | — | `findCell` + `reduce(minOp)` sentinel |
| `kernel()` (`:374-404`) | yes | — | paper Eq. 8 |
| `interpolateVelocity()` (`:407-463`) | yes | — | kept for the nacelle and the S3 seam; not called by the blade path |
| distribution helper (`nacelleSurfaceSource::distributeForce`, `:163-209`) | yes → `distributeForce(ff, nodeForces, nodeH, candidates)` | — | candidate list optional; `nullptr` means "all local cells", which reproduces the S1 loop exactly |
| `referenceVelocity_`, `nu_`, `cfOverride_` (`:145-152`) | — | yes | nacelle force model only |
| `rhoRef_` (`:154-155`) | yes | — | shared SI-contract conversion |
| `streamwiseDirection_`, `noseStreamwise_`, `streamwiseCoords_` (`:157-164`) | — | yes | Schultz-Grunow friction only |
| `normalForce`, `tangentialForce`, `frictionCoefficient`, `tangentialDirection`, `readViscosity` (`:96-142,295-371`) | — | yes | nacelle force model only |
| `forces_`, `nodeForces_` (`:128-134`) | — | yes | per-node lists owned by each concrete sampler (the blade keeps its own) |

**Alternatives considered**: duplicate the machinery into a parallel blade class
(rejected: two copies of the kernel/MPI code, drift risk); one parameterized
source (rejected in D1).

**Byte-identical gate**: the base's distribution iterates the same local cells
in the same order and evaluates the same expression `ff[cellI] -= F*(w/V)`
(`nacelleSurfaceSource.C:205`). The nacelle source calls the base helper with
"all local cells"; the full existing nacelle suite plus the byte-comparable CSVs
of `test_nacelle.py` are the gate. Any deviation in arithmetic order that
changes the CSV is a regression, not a refactor.

### D3 — Suppression key `projectElementForce` (proposal Decision 1, double-count control)

**Choice**: `actuatorLineElement` gains a protected `bool projectElementForce_`
read in `read()` after `writePerf_` (`actuatorLineElement.C:140-141`) with
`lookupOrDefault("projectElementForce", true)`. The two `addSup` overloads guard
**only** the `applyForceField` call:

```cpp
calculateForce(Uin);
if (projectElementForce_)
{
    applyForceField(forceFieldI);
}
forceField += forceFieldI;          // adds zero when suppressed
```

at `actuatorLineElement.C:1074-1075` (incompressible) and `:1113-1114`
(compressible; `multiplyForceRho` at `:1117` still runs, preserving the existing
`force()` semantics). `calculateForce` and `writePerf` are untouched, so the
element CSV, `force()` and the BEM state remain valid — exactly what the
distributor consumes.

`actuatorLineSource::read()` stores `surfaceGeometry_` when present
(`actuatorLineSource.C:55-101`). In `createElements()`, a user-supplied
`projectElementForce` in the blade subdictionary is plumbed through to every
element dict exactly like `elementType`/`nChordwise`
(`actuatorLineSource.C:337-346`); when `surfaceGeometry` is also present the
source overrides it to `false` for every element of that blade. When
`surfaceGeometry` is absent and the user did not set the key, it is never added
and the element default `true` applies. Precedence: surface injection >
blade-subdict value > element default (spec `element-type-selection`, "Config
key plumbing").

**Alternatives considered**: suppress by zeroing `forceVector_` before
`applyForceField` (breaks the CSV and `force()`); suppress in
`actuatorLineSource::addSup` by not calling the element at all (breaks
`calculateForce`/CSV); no suppression and subtract the strip contribution later
(depends on identical kernel evaluation and is fragile).

**Gate**: full existing suite unchanged; a default-path test confirms the strip
projection still happens with the key absent; the new partition-of-unity test
confirms a surface-enabled blade applies its force once (§8).

### D4 — Node set, station/chord association and the element patch partition

**Choice**:

- **Node set**: one node per triangle centroid, in `triSurface` face order
  (`surface_->faceCentres()`, `faceNormals()`, `magFaceAreas()`), inherited from
  the S1 pattern (`nacelleSurfaceSampler.C:212-215`).
- **Station/chord association at runtime**: the STL is a blade in a canonical
  generation frame (§4.4). For node `X`, the distributor computes its **blade
  radial coordinate** `s(X) = (X − surfaceOrigin_)·spanAxis_` (the injected
  rotor origin and construction span direction, §3 D5; for a straight blade
  this is the absolute radius `r`) and its **chord fraction** from its assigned
  element's frame:
  `c(X) = chordMount_i − ((X − position_i)·unit(chordDirection_i))/chordLength_i`
  (fraction from the **leading edge**, §4.4: 0 at the LE, 1 at the TE, the same
  LE-based convention as `actuatorSurfaceElement::chordPoint`, `.C:51-58`). The
  chord direction accessor
  is added to `actuatorLineElement` (`chordDirection()`, next to
  `chordLength()` at `actuatorLineElement.H:302-303`).
- **Element station**: `s_i = (position_i − surfaceOrigin_)·spanAxis_`. For the
  straight Phase VI blade the chord displacement is perpendicular to the span
  axis, so `s_i` equals the element's radial station; this is the same monotone
  coordinate for every element and node. (For a coned/curved blade the
  projection compresses stations by `cos(cone)`; the partition stays monotone
  and is documented as an approximation.)
- **Partition**: node `X` belongs to the element whose station is nearest,
  i.e. patch boundaries at the midpoints `(s_i + s_{i+1})/2`; the first/last
  patches are open at the root/tip ends. This is a 1-D Voronoi partition along
  the span: every node is in exactly one patch, the patches are contiguous, and
  the patch areas sum to the total surface area by construction.
- **Patch force**: element `i`'s force is shared over its patch nodes
  proportionally to node area:
  `F_node = F_element · A_node / Σ_{patch} A_node`, then spread with the
  kernel. The area-weighted share preserves the element total exactly
  (`Σ F_node = F_element`), so the patch partition and the kernel partition of
  unity together give exactly-once application.

**Alternatives considered**: 3-D nearest element position (badly skewed inboard,
where chord ≫ element spacing); metadata-sidecar association from
`geometry/metadata/phaseVI_blade.json` (couples the run to a second staged file
and does not generalize to an arbitrary imported STL); area-weighted splitting
across neighbouring patches (breaks the "exactly one patch" invariant and makes
the accounting harder to test).

**Validation**: constructor-time assertions (fatal on failure) that every node
is assigned, every element has a non-empty patch, and the patch area sum equals
the total `triSurface` area to a relative tolerance; a unit-level test in
`test_blade_surface.py` (solver-driven) checks the same invariants from the
written CSVs.

### D5 — Rotating frame and transform lockstep (spec `blade-surface-source`, "Rotating-frame lockstep")

**Choice**: the distributor keeps a canonical node list, a global-frame node
list, and a body-frame node list, and mirrors every geometric transform the
blade forwards to its elements:

- **Construction placement**: AFTAL injects the blade's **construction frame**
  into the blade subdictionary when `surfaceGeometry` is present —
  `surfaceOrigin` (`origin_`), `surfaceSpanDirection` and `surfaceChordDirection`,
  all taken after the same cone/azimuth rotations `createBlades()` already
  applied (`axialFlowTurbineALSource.C:179-194,202,211-228`):
  `unit(elementGeometry[0][3])` is the reference chord (trailing → leading,
  before the element pitch), and `surfaceSpanDirection` is the root → tip
  construction direction
  `unit(elementGeometry[nGeomPoints-1][0] − elementGeometry[0][0])` — the
  **outward** span that is the generation frame's `+z` (§4.4). The element
  pitch axis `unit(elementGeometry[0][1])` is deliberately not used for the
  frame: for the Phase VI orientation it points radially inward
  (`axis (-1 0 0)` × `verticalDirection (0 0 1)`, `:202-208`) while the stations
  run `+z`, so using it would mirror the surface across the rotor plane. The
  distributor maps each canonical node
  `X_global = surfaceOrigin + z_gen·spanDir + y_gen·chordDir + x_gen·(chordDir × spanDir)`.
  Baking the cone and `azimuthalOffset` into the injected directions makes the
  placement exact for both blades (blade2's `azimuthalOffset 180` is already in
  its `elementGeometry`), with no separate user-facing
  `surfaceAxis`/`surfaceConeAngle` key and no double-applied rotation. At the
  Phase VI `coneAngle = 0` the injected directions are orthogonal; a non-zero
  cone uses the element frame's own (slightly non-orthogonal) span/chord
  vectors and is outside this change's validation scope.
- **Runtime**: `actuatorLineSource::rotate(point, axis, radians)` also calls
  `surface_->rotate(...)`; `translate()` also calls `surface_->translate(...)`;
  `pitch(radians[, chordFraction])` rotates the surface rigidly about the
  **element pitch axis** `elements_[0].spanDirection()` (the axis the elements
  themselves use, `actuatorLineElement.C:937-940`; accessor added next to
  `chordDirection()`) through the root chord pitch-axis point. The element pitch
  axis is anti-parallel to the outward `surfaceSpanDirection` in the Phase VI
  orientation, so forwarding the raw `radians` about the frame axis would
  invert the pitch. Documented rigid approximation; harmonic pitching is not
  used by Phase VI.
  `setSpeed()`/`scaleVelocity()`/`setOmega()` do not move the geometry.
- **Body frame (contract)**: `bodyOrigin_` = `surfaceOrigin` (rotor centre),
  `bodyAxis` = the construction span direction (outward root → tip); the S1
  `createBodyFrame` completion (`nacelleSurfaceSampler.C:36-93`) is reused. `positions()`
  returns `bodyToGlobal_.T() & (positionsGlobal_ − bodyOrigin_)`, so the node
  coordinates **change with azimuth** (the node set is rigidly rotating in the
  world while the mount basis is fixed at construction) and the ordering is
  fixed at initialization — satisfying the delta's body-frame and stable-order
  scenarios. User-set `bodyOrigin`/`bodyAxis` override the injected defaults.
- **Restart**: no surface-specific file state. Restarts resume the S1
  time-derived azimuth (`turbineALSource.C:312-347`, `angleDeg()` `:430-433`);
  the surface is reconstructed at the same azimuth because the same rotate
  calls are replayed from the same `angleDeg_`.

**Alternatives considered**: making the body frame blade-attached (coordinates
constant across azimuth — simpler for S3 but contradicts the delta scenario
"positions() ... reflect the azimuth"); fitting the placement transform from
element positions (fragile, chord-offset dependent).

### D6 — Bounded distribution and the D/32 measurement gate

**Choice**: a **per-node precomputed candidate list** built once, on top of a
per-rank uniform bin index of the local cells:

1. At construction, for each node `i` compute `h_i = cellSize(X_i)` (inherited;
   fatal if unreachable) and `support_i` = `2.5·h_i` (cosine) or
   `ε_i·sqrt(ln(1000))` with `ε_i = 2·cbrt(V_i)·meshFactor` (Gaussian, mirroring
   `actuatorSurfaceElement.C:110`).
2. Build a uniform bin grid over the local cell centres: bin size
   `max(min_i support_i, small)` over the local mesh bounding box; each local
   cell label is appended to its bin. This is O(N_local cells) once.
3. For each node, query the bins overlapping `[X_i − support_i, X_i + support_i]`
   (27 bins in the typical uniform case) and store the local cell labels whose
   centre passes the same axis-aligned prefilter used by
   `nacelleSurfaceSampler::interpolateVelocity` (`:424-433`) and
   `nacelleSurfaceSource::distributeForce` (`:183-192`). The candidate list is
   fixed for the run because the background mesh and `h_i` are static.
4. Each `addSup` iterates only the node's candidate list, so per-`addSup` cost
   is `O(Σ_i |candidates_i|)`, not `O(N_nodes · N_local cells)`.

MPI follows the S1 replicated-node/local-cell design: every rank holds the full
node list and builds candidates over its own local cells only; every local cell
is written exactly once by its owner; `cellSize()` keeps the `reduce(minOp)`
sentinel for unreachable nodes.

**Instrumentation** (spec requirement; owned by W4, the measurement gate): after
each `addSup`, one `Info` line on master and an optional CSV row carry node
count, total candidate entries, mean/max candidates per node, and `addSup` wall
seconds (`clockTime`/`std::chrono`). The counters are added in W4 inside
`bladeSurfaceSource::distribute()` (§9 W4), matching the proposal's Work-Unit
Plan; W1 ships the bounded query without them. W4 owns the prepared measurement
case/array and only hardens the query if the gate demands it.

**Complexity target**: at D/32 the local cell count is ~139 k per rank
(6.67 M cells / 48) and the blade has ~3 000 triangles per blade × 2 blades;
cosine candidates are ≈ 5³ = 125 cells/node worst case, so ~7.5×10⁵ candidate
updates per `addSup` versus the naive ~4×10¹⁰. The D/32 measurement must pass
(practical per-step budget) before the D/48/D/64 campaign is prepared.

**Alternatives considered**: scanning all local cells per node (S1 behavior;
rejected by the spec requirement); `meshSearch`/octree cell stencils (correct
but heavier API surface; kept as the W4 hardening fallback); lazy per-step
queries (recompute cost per step; rejected — `h_i` is static).

### D7 — Kernel and width (spec "Selectable kernel and width")

**Choice**: `kernel cosine` is the default (paper Eq. 8, support `|r| ≤ 2.5`,
the S1 kernel moved to the base). `kernel gaussian` selects the no-mesh ASM's
mesh-only width per node: `ε_i = 2·cbrt(V_i)·meshFactor` and a truncated
support `ε_i·sqrt(ln(1/0.001))`, matching
`actuatorSurfaceElement::calcProjectionEpsilon` (`:61-100`) and its
`applyForceField` truncation (`:110`). `meshFactor` is read from the surface
subdict; when absent it is read from the blade's `profileData` GaussianCoeffs
(the same `meshFactor 1` the Phase VI twin uses, `case/config` generation at
`generate_case.py:583-597`), falling back to `2.0` (the element default,
`actuatorLineElement.C:249`). The Gaussian mode is the **ablation** that
isolates the geometry effect from the kernel/width confound; it is documented as
an ablation, not as a model.

**Residual confound**: the no-mesh ASM uses one `ε` per element (at the element
position) while the surface uses one `ε` per node; at D/32–D/64 the cell sizes
inside one element patch differ, so the matched ablation narrows but does not
eliminate the width difference. Documented in the case README and in the
comparison limitations.

### D8 — Blade moment: the surface moment replaces the element moment when active

**Choice**: `actuatorLineSource::moment(point)` (`actuatorLineSource.C:668-683`)
adds the surface node moment **instead of** the element moment when the
distributor is active:

```
moment = sum_i elements_[i].moment(point)        // inactive
moment = surface_->moment(point)                 // active: moment of the load
                                                 // actually applied to the field
```

The surface node moment uses the per-node force shares with the same
force-on-blade sign and the node positions in the global frame. AFTAL's torque
projection (`axialFlowTurbineALSource.C:784-785,820`) then reflects the
distributed application points.

**Alternatives considered**: adding element and surface moments (double counts
the same load; torque would grow artificially); leaving the element moment
(torque inconsistent with the applied field).

**Rationale**: partition of unity keeps the force total identical, so the only
physical difference between element and surface moments is the application
point; reporting the applied load's moment is the consistent convention. The
source CSV documents the convention so the difference is auditable.

### D9 — CSV outputs and the compare-compatible conversion

**Choice**: two machine-readable outputs under
`postProcessing/bladeSurface/` (mirroring `postProcessing/nacelle/`,
`nacelleSurfaceSource.C:50-78`):

- **Per-station (default, `writePerf true`)**: one row per element (the
  element's patch is its radial bin), with
  `time,station,root_dist,area,force_x,force_y,force_z,c_ref_n,c_ref_t,f_ref_n,f_ref_t`.
  `force_*` is the patch's distributed force on the blade in SI newtons (i.e.
  `rhoRef_`-scaled); `c_ref_*`/`f_ref_*` are the area-weighted means of the
  element's public `normalRefCoefficient()`/`tangentialRefCoefficient()` and
  `normalRefForce()`/`tangentialRefForce()` (`actuatorLineElement.C:672-705`),
  i.e. the same definitions the element CSV writes
  (`actuatorLineElement.C:539-541`). `root_dist` uses the element `rootDistance()`
  convention, which is exactly what `comparePhaseVI.py` maps to r/R
  (`comparePhaseVI.py:259-275`). The conversion is therefore a column read,
  not a new formula: the existing definitions are not changed.
- **Per-node (opt-in `writeNodePerf false`)**: per-node time rows in the blade
  body frame with `node,x,y,z,nx,ny,nz,fx,fy,fz,area,station,chord_fraction`
  (mirrors `nacelleSurfaceSource::writeNodePerf`, `:259-275`, plus the node
  metadata).

Both are written on master only (`Pstream::master()`, S1 convention) and the
per-station file header documents that the surface moment (D8) is the torque
convention.

**Alternatives considered**: expose only the per-node CSV and let the compare
tooling aggregate (rejected: the element-convention conversion would move into
the Python tooling and duplicate the element coefficient definitions); report
the per-station rows from the element strip convention instead of the
distributed node shares (rejected: the CSV must document the load actually
applied to the field, D8).

### D10 — Pure-Python deterministic loft for `phaseVI_blade` (proposal Decision 2)

**Choice**: a builder registry in `makeGeometry.py`; `phaseVI_blade` is built by
a committed Python function, nacelle stays gmsh-pinned. The loft:

- **Inputs**: `validation/phaseVI/data/geometry/phaseVI_blade.csv` (26 stations,
  `radius_m,chord_m,twist_deg_report,chord_mount`, `data/geometry/PROVENANCE.md:13-24`),
  the committed S809 CSV (§3 D11), and a declared `PITCH_DEG = 3.0` asserted
  against `config/case.yaml` `turbine.pitch_deg` by `test_blade_data.py` (the
  runtime pitches every element by `-(twist + pitch)`,
  `element_data.py:32-51`).
- **Sections**: exactly the 26 committed stations, in order. For each station
  build a closed N-point polygon (N fixed, equal for every section), in
  section-local coordinates `(u, w)`: `u` = LE-based chord fraction (0 at the
  LE, 1 at the TE, §4.4) and `w` = S809 ordinate `z/c`:
  - `r ≤ 0.8835`: **circle** of radius `chord/2` centred on the chord line at
    mid-chord (the cylinder stations have `chord_mount 0.5`), points placed at
    the same fixed perimeter fractions as the S809 polygon and in the same
    order — starting at the first upper-surface LE point, over the TE and back
    along the lower surface — so the circle and airfoil rings correspond 1:1.
  - `r ≥ 1.0085`: **S809** scaled to `chord`, with `u = x/c` taken from the
    table (already LE-based) and `w = z/c`.
  The section is mapped to the generation frame (§4.4) as
  `y = (0.25 − u)·chord`, `x = w·chord`, `z = r`, rotated about `+z` by
  `σ·(−(twist_report + pitch_deg))` (`σ = −1` for Phase VI) and translated so
  the quarter-chord point (`u = 0.25`) lies on the radial reference line
  `x = y = 0` at the station. The point at chord fraction `chord_mount` then
  lands at `y = −(chord_mount − 0.25)·chord`, exactly the element placement
  (`axialFlowTurbineALSource.C:166-168`), so the imported surface and the BEM
  stick model share one LE-based orientation convention (§4.4).
  - The single segment `0.8835 → 1.0085` is the **cylinder→airfoil
    transition** (lofted circle-to-S809); the report's transition description
    ("cylindrical section 0.508–0.883 m; transition 0.883–1.257 m",
    `29955_fitz.txt` Table A-2 preamble, verified locally) is consistent with
    the committed stations.
- **Trailing edge**: the S809 table's shared trailing-edge point appears once in
  the closed polygon, giving a sharp closed TE; the data contains no explicit
  leading-edge point, so the polygon closes across the small blunt LE gap
  between the first upper (`x/c = 0.00037`) and first lower (`x/c = 0.00140`)
  point. No coordinate is invented, and the closure is documented in
  PROVENANCE.
- **Root/tip**: **wetted surface only**, no caps — the loft is an open shell
  with exactly two boundary rings (root at `r = 0.5083`, tip at `r = 5.029`).
  Tip force zeroing, end effects and the inboard `chord_mount` transition stay
  BEM-side. The shell is edge-manifold (every edge has 1 or 2 incident
  triangles; interior edges exactly 2, with opposite orientation).
- **Triangulation**: for consecutive rings `(i, i+1)` and point indices
  `(j, j+1)`, two triangles with fixed winding; N-point rings give
  `2·N·(26−1)` triangles (N = 60 → 3 000 triangles per blade).
- **Canonical output**: reuse `canonical_triangles` and `write_binary_stl`
  (`makeGeometry.py:194-219`) with a fixed per-component header and recomputed
  facet normals. Regeneration is byte-identical because all arithmetic is
  deterministic Python over committed inputs and the triangle order is
  canonicalized.
- **Metadata**: `metadata/phaseVI_blade.json` populated per node with
  `radial_station` (the triangle centroid's span coordinate, m) and
  `chord_fraction` (the mean of the three vertices' construction-time LE-based
  chord fractions `u = x/c`, §4.4), replacing the reserved null placeholders
  (`makeGeometry.py:371-373`);
  `_reserved` is dropped for this component. Component/format/inputs/STL hash
  fields are the existing schema (`makeGeometry.py:355-378`,
  `geometry/README.md:60-88`).

**Alternatives considered**: gmsh loft (uncontrolled triangle counts and
sliver/non-manifold risk at the thin TE; canonicalization only reorders, it
cannot repair a non-reproducible tessellation — proposal Decision 2); Phase VI
local generator (rejected: contradicts the shared pipeline intent and duplicates
what a future MEXICO blade needs).

### D11 — S809 dataset home, extraction recipe and cross-check

**Choice**: the canonical committed dataset lives once, under the Phase VI
validation package as the delta requires: `validation/phaseVI/data/s809/`
(`s809_somers_nlr.csv` + `PROVENANCE.md`). The geometry builder consumes it by a
fixed relative path and records its sha256 in the component metadata/provenance.
No second copy is committed.

**Extraction recipe** (recorded in PROVENANCE.md, repeatable):

- Tool: PyMuPDF (verified available on this host: PyMuPDF 1.27.2.3); the host
  has no `pdftotext`.
- Source: `s809_somers_nlr.pdf` (Somers, NREL/SR-440-6918), verified during
  design with **sha256 `a7496aad5680d9d4001e36cf8b13d9603ea31956093cded60976dd8fcaffeeb3`**.
  Table 2 ("S809 Airfoil Coordinates") is on PDF page index 19 (printed page 15).
- Method: extract that page's text, take the numeric tokens with
  `-?(?:\d+\.\d+|\.\d+)`, group them row-wise as
  `(upper x/c, upper z/c, lower x/c, lower z/c)`; the final row carries the
  shared trailing edge. Verified during design: 31 upper and 30 lower points
  ending at `(1.0000, 0.0000)`.
- Committed format: long CSV `surface,x_over_c,z_over_c` with `upper` rows
  LE→TE then `lower` rows LE→TE, plus header comments naming the source, table,
  tool/version and date.

**Cross-checks** (both recorded in PROVENANCE.md):

1. **Independent transcription**: TP-500-29955 Table A-2, "Airfoil profile
   coordinates" (verified locally: PDF page index 74, printed page 65; PDF
   sha256 `822ee980e97780599ad4ec1dc8b4cc8ad41131b0cbbdffa19999d571f6ce4958`,
   matching the already-committed provenance
   `data/geometry/PROVENANCE.md:10`). The two reports publish the same design
   coordinates; the extraction must agree to all published digits.
2. **Independent measurement**: Ramsay, *Effects of Grit Roughness and Pitch
   Oscillations on the S809 Airfoil*, Table A1 "S809 Measured Model
   Coordinates, 18-inch Desired Cord" (verified locally: PDF pages 33–40, PDF
   sha256 `9b5d151f7361ce11aef1bfce25447d1f7e4f34c961e1266064310945e42cf825`).
   The recipe normalizes the inch ordinates by the 18-inch desired chord and
   compares them against the committed design ordinates at common `x/c`, with a
   stated tolerance of 1 % chord outside the last 10 % of chord; the documented
   upper-surface thickness addition over the last 10 % chord
   (`phasevi_research/verified/s809_ramsay.txt:356-360`) is excluded from the
   gate and reported. The
   measured maximum deviation is recorded in PROVENANCE.md; failure aborts the
   extraction (exit non-zero).

**Alternatives considered**: committing the local text dump as authoritative
(rejected: unverified, recipe not recorded); a web-sourced coordinate file
(rejected: no verified local copy, weaker provenance).

### D12 — Builder registry and naming (proposal Decision 2, spec `turbine-geometry-pipeline`)

**Choice**: `makeGeometry.py` keeps a per-component builder registry:
`COMPONENTS = ("nacelle", "phaseVI_blade")`, a `BUILDERS` mapping
(`nacelle → gmsh builder`, `phaseVI_blade → Python builder`), and
`RESERVED_COMPONENTS = ()` — the `blade0/1/2` reservation is retired. The
CLI error/help text, the README component table and the PROVENANCE source rows
are all derived from the registry
(current code: `makeGeometry.py:86-88,522-547`, `geometry/README.md:49-58`,
`geometry/PROVENANCE.md:10-13`). One STL serves both Phase VI blades (azimuth is
runtime, blade2 is `$blade1;` + `azimuthalOffset 180`,
`validation/phaseVI/case/system/fvOptions.ASM:95-101`). A future MEXICO blade
is a separate `mexico_blade` component owned by the active `mexico-validation`
change; this change does not touch it.

**Alternatives considered**: keep the `blade0/1/2` reservation alongside
`phaseVI_blade` (rejected: it encodes an un-sourced per-blade assumption and
would keep advertising components that cannot be built); route the blade
through the gmsh builder like the nacelle (rejected: determinism and
tessellation risk, D10); commit per-blade duplicate STLs (rejected: byte
duplicates, D12 above); name the component generically `blade` (rejected by the
proposal's naming decision in favour of the rotor-qualified `phaseVI_blade`;
component name confirmation is proposal open question 1).

### D13 — Phase VI integration shape (proposal Decision 3)

**Choice**: the third model twin `fvOptions.ASM-MESH` in the existing package
(§6): ASM element keys + `surfaceGeometry` (+ optional kernel keys) in each
blade subdictionary, `-m asm-mesh`, `case_config.py --select` whitelist
extended, STL staged at `constant/triSurface/phaseVI_blade.stl` and referenced
case-relative, three-way comparison with the existing bands/sign gate, a new
prepared-only array, and a prepared-only D/32 measurement gate. The
`--surface-geometry` option on `-m asm` was rejected (a second configuration
axis with run-id permutations, less legible for the campaign).

---

## 4. Interfaces / Contracts

### 4.1 Class layout

Files: `turbinesFoam/src/fvOptions/nacelleSurface/surfaceSamplerBase.{H,C,I.H}`
(the base is physically next to its first consumer; it stays frame- and
force-model-agnostic), `nacelleSurfaceSampler.{H,C}` updated to derive from it,
and `turbinesFoam/src/fvOptions/bladeSurface/bladeSurfaceSampler.{H,C}` +
`bladeSurfaceSource.{H,C}`. `Make/files` gains the three new `.C` entries
(after the nacelle lines, `turbinesFoam/src/Make/files:15-16`).

```
class surfaceSamplerBase
{
protected:
    const fvMesh& mesh_;
    autoPtr<triSurface> surface_;
    List<point>  positions_;        // global frame, triangle centroids, face order
    List<vector> normals_;          // global frame, outward unit normals
    List<scalar> areas_;            // magFaceAreas()

    List<point>  positionsBody_;    // body-frame contract positions
    List<vector> normalsBody_;
    vector bodyOrigin_;
    tensor bodyToGlobal_;           // columns: body axes in global frame
    bool identityBodyFrame_;
    scalar rhoRef_;

    void createBodyFrame(const dictionary& dict);           // moved from S1
    scalar cellSize(const point& X) const;                  // moved from S1
    static scalar kernel(const scalar r);                   // moved from S1
    vector interpolateVelocity(const point& X, const volVectorField& U,
                               const scalar h) const;       // moved from S1

    // Distribution math (Eq. 18). candidates == nullptr reproduces the S1
    // "all local cells" loop byte-for-byte.
    void distributeForce(volVectorField& ff,
                         const List<vector>& nodeForcesGlobal,
                         const List<scalar>& nodeH,
                         const List<List<label>>* candidates) const;
public:
    surfaceSamplerBase(const dictionary& dict, const fvMesh& mesh);
    virtual ~surfaceSamplerBase();
    label nNodes() const;
    const List<point>& positions() const;      // body frame (contract)
    const List<vector>& normals() const;
    const List<scalar>& areas() const;
    const List<point>& positionsGlobal() const;
    const List<vector>& normalsGlobal() const;
    const tensor& bodyToGlobal() const;
    scalar rhoRef() const;
};
```

```
class nacelleSurfaceSampler : public surfaceSamplerBase
{
    // S1 force model, unchanged: referenceVelocity_, nu_, cfOverride_,
    // streamwiseDirection_, noseStreamwise_, streamwiseCoords_,
    // forces_, nodeForces_, normalForce(), tangentialForce(),
    // frictionCoefficient(), tangentialDirection(), readViscosity()
public:
    const List<vector>& forces() const;   // SI N, body frame, on-body
};
```

```
class bladeSurfaceSampler : public surfaceSamplerBase
{
    // Rotating frame + station/chord association (D4/D5)
    List<point>  canonicalNodes_;     // generation frame (span +z, chord +y)
    List<scalar> station_;            // span coordinate s(X)
    List<scalar> chordFraction_;      // LE-based fraction (§4.4)
    List<label>  patch_;              // owning element index per node
    List<scalar> patchAreaShare_;     // A_node / patch area
    List<vector> nodeForces_;         // per-unit-density, global frame (D2)
    List<vector> forces_;             // rhoRef_*F_i, body frame (contract)
    List<List<label>> candidates_;    // bounded query (D6)
    // injected/optional construction frame (D5); pitchAxis_ =
    // elements_[0].spanDirection() for the pitch forwarding
    vector surfaceOrigin_, spanAxis_, chordAxis_, normalAxis_, pitchAxis_;
public:
    const List<vector>& forces() const;                 // SI N, body frame
    const List<scalar>& station() const;
    const List<scalar>& chordFraction() const;
    const List<label>& patch() const;
    void rotate(vector point, vector axis, scalar radians);
    void translate(vector translation);
    void pitch(scalar radians);
};
```

```
class bladeSurfaceSource                      // helper, NOT an fv::option (D1)
{
    bladeSurfaceSampler sampler_;
    const PtrList<actuatorLineElement>& elements_;   // owning blade elements
    label  nElements_;
    bool   writePerf_, writeNodePerf_, logDistribution_;
    OFstream* stationFile_; OFstream* nodeFile_;
    // per-addSup instrumentation (D6, added in W4)
    label  lastCandidateTotal_;
    scalar lastSeconds_;

    void buildPartition();                 // D4, constructor
    void buildCandidates();                // D6, constructor
    void writeStationCsv();                // D9
    void writeNodeCsv();
public:
    bladeSurfaceSource(const dictionary& dict, const fvMesh& mesh,
                       const PtrList<actuatorLineElement>& elements);
    // Called by actuatorLineSource::addSup after the element loop:
    void distribute(volVectorField& bladeForceField, vector& bladeForce,
                    const volScalarField* rhoPtr = nullptr);
    vector moment(vector point) const;
    const bladeSurfaceSampler& sampler() const;
    bool active() const;
};
```

### 4.2 Config keys (blade subdictionary)

```
surfaceGeometry     "constant/triSurface/phaseVI_blade.stl";  // required; presence activates
kernel              cosine;        // | gaussian (D7)
meshFactor          1.0;           // gaussian only; default from profileData
                                   // GaussianCoeffs.meshFactor, else 2.0
rho                 1.0;           // reference density for the SI contract/CSV
referenceVelocity   1.0;           // accepted for shared-template parity; unused
                                   // by the distribution-only path
nu                  -1.0;          // accepted for shared-template parity; unused
bodyOrigin          (injected);    // optional override (D5)
bodyAxis            (injected);    // optional override (D5)
writePerf           true;          // per-station CSV
writeNodePerf       false;         // per-node CSV
logDistribution     true;          // per-addSup instrumentation line
```

Injected (authoritative, `createBlades()` when `surfaceGeometry` is present):
`surfaceOrigin`, `surfaceSpanDirection`, `surfaceChordDirection` — the blade's
construction frame after cone/azimuth, with `surfaceSpanDirection` outward
root → tip, §3 D5. The twin does **not** render
`projectElementForce` — the blade source injects it into the element dicts
(§3 D3).

### 4.3 Partition and distribution data

- `patch_[i] ∈ {0..nElements−1}`: node index → element index (1-D Voronoi along
  `station_`).
- `patchAreaShare_[i] = A_i / Σ_{j∈patch(i)} A_j`; by construction
  `Σ_{j∈patch(i)} patchAreaShare_[j] = 1`.
- Per `addSup`: `F_node = patchAreaShare_[i] · elements_[patch_[i]].force()`
  (per unit density, force on blade); the field receives
  `−F_node·(1/V_c)·φφφ` over the node's candidates. The per-station CSV reports
  `Σ_{patch(i)} F_node · rhoRef_` (SI newtons).

### 4.4 Canonical STL generation frame and the chord-fraction convention (documented in geometry PROVENANCE)

Origin at the rotor centre on the rotor axis; `+z` = blade span at zero azimuth,
**outward** (root → tip, the construction direction AFTAL injects as
`surfaceSpanDirection`, D5); `+y` = reference chord direction (trailing edge →
leading edge before twist/pitch); `+x = y × z` = section normal, which is the
suction side for the Phase VI orientation (the element lift
`relativeVelocity_ ^ spanDirection_`, `actuatorLineElement.C:838`, points along
`+x` at azimuth 0, and the S809 upper surface is the suction side at the positive
BEM angle of attack). Units are metres. The runtime placement transform is §3 D5;
the geometry test asserts that a node's `radial_station` metadata equals its `z`
coordinate and that the blade tip is at `z = 5.029 m` / the root at
`z = 0.5083 m`.

**Chord-fraction convention (authoritative; referenced by D4, D9, D10 and
§7.3)**: chord fraction `u` is measured **from the leading edge** — 0 at the LE,
1 at the TE — in every chord-fraction quantity of this design (the station/chord
association of D4, the loft of §7.3, the metadata `chord_fraction` and the
per-node CSV column). This is the codebase convention:

- `chordDirection_` points trailing → leading (`actuatorLineElement.H:81`), and
  `chordMount` is the LE-based fraction of the element mount point: `position_`
  sits at that fraction on the element chord line
  (`axialFlowTurbineALSource.C:166-168`,
  `point -= (chordMount - 0.25)*chordLength*chordUnit`; the Phase VI airfoil
  stations mount at 0.30, i.e. 30 % chord from the LE).
- `actuatorSurfaceElement::chordPoint(k)` returns the chord point at the
  LE-based fraction `(k + 0.5)/nChordwise_` (`actuatorSurfaceElement.C:51-58`).
- The element pitch/mounting rotation is about the chord point at LE-based
  fraction 0.25 (the quarter-chord; `pitch` default `chordFraction = 0.25`,
  `actuatorLineElement.C:937-940`), which is the radial reference line.

In the generation frame a section point at chord fraction `u` and ordinate
`w = z/c` is therefore placed at

    y = (0.25 − u)·chord,   x = w·chord,   z = r

before the section's twist/pitch rotation about `+z`; the point at chord
fraction `chord_mount` sits at `y = −(chord_mount − 0.25)·chord`, exactly the
element placement of `axialFlowTurbineALSource.C:166-168`, and the quarter-chord
point (`u = 0.25`) is the radial reference line at station `r`.

**Twist sign**: the runtime pitches each element by
`−(twist_report + pitch_deg)` about the element pitch axis (`element_data.py:40`,
`actuatorLineSource.C:371`), which is `elementGeometry[j][1]` — for the
Phase VI/twin orientation anti-parallel to the outward span (`axis (-1 0 0)`
with `verticalDirection (0 0 1)` gives `(0 0 −1)`,
`axialFlowTurbineALSource.C:202-208`, while the stations run `+z`). In the
generation frame the equivalent rotation is therefore about `+z` by
`σ·(−(twist_report + pitch_deg))` with `σ = −1` for Phase VI, i.e.
`+(twist_report + pitch_deg)` (§7.3). The committed `phaseVI_blade` is
Phase VI-specific: `σ = −1` is recorded in PROVENANCE, and a rotor whose element
pitch axis is outward would need `σ = +1`.

### 4.5 CSV schemas

```
postProcessing/bladeSurface/<name>.csv                  # per-station (D9)
time,station,root_dist,area,force_x,force_y,force_z,c_ref_n,c_ref_t,f_ref_n,f_ref_t

postProcessing/bladeSurface/<name>_nodes.csv            # opt-in per-node (D9)
time,node,x,y,z,nx,ny,nz,fx,fy,fz,area,station,chord_fraction
```

`<name>` is the owning blade source name plus `.surface` (e.g.
`turbine.blade1.surface`), matching the `postProcessing/<dir>/<name>.csv`
convention (`nacelleSurfaceSource.C:50-78`).

### 4.6 Metadata schema (`geometry/metadata/phaseVI_blade.json`)

```json
{
  "component": "phaseVI_blade",
  "format_version": 1,
  "generator": {"script": "src/makeGeometry.py", "builder": "phaseVI_blade"},
  "inputs": {
    "blade_csv": "validation/phaseVI/data/geometry/phaseVI_blade.csv",
    "blade_csv_sha256": "...",
    "s809_csv": "validation/phaseVI/data/s809/s809_somers_nlr.csv",
    "s809_csv_sha256": "...",
    "pitch_deg": 3.0
  },
  "input_sha256": "<sha256 over all input bytes + canonical parameter block>",
  "units": "m",
  "n_triangles": 3000,
  "stl_sha256": "...",
  "nodes": [
    {"index": 0, "normal": [nx, ny, nz], "area": 1.2e-4,
     "radial_station": 0.5083, "chord_fraction": 0.42}
  ]
}
```

No `_reserved` block for this component (spec: no reserved-null blade mapping).

### 4.7 Compare-side converter

`comparePhaseVI.py` gains `--asm-mesh-dir` and a `read_surface_stations(run_dir)`
helper that reads `postProcessing/bladeSurface/*.csv`, filters on the averaging
window (reusing the `start <= time <= end` pattern of
`spanwise_profile`, `comparePhaseVI.py:259-275`) and returns
`(root_dist, c_ref_n, c_ref_t)` tuples; the existing `interpolate` (`:278-289`)
maps them to the five r/R stations. No coefficient formula is redefined.

---

## 5. Data Flow

```
geometry pipeline (W2)                                runtime (W1)
------------------------                              --------------------------------------------
validation/phaseVI/data/geometry/phaseVI_blade.csv
validation/phaseVI/data/s809/s809_somers_nlr.csv  ──►  bladeSurfaceSampler
            │                                             │  triSurface::New(surfaceGeometry)
            ▼                                             │  centroids/normals/areas (D4)
   pure-Python structured loft                            │  station/chord association (D4)
   (26 rings, fixed N, fixed winding)                     │  patch partition (D4, once)
            │                                             │  candidates (D6, once)
            ▼                                             ▼
   stl/phaseVI_blade.stl ──► staged copy ─────►  bladeSurfaceSource::distribute()
   metadata/phaseVI_blade.json (radial_station,             ▲
   chord_fraction, hashes)                                  │  elements_[i].force()  (after loop)
                                                            │
  actuatorLineSource::addSup (per PIMPLE iteration)         │
  ┌─────────────────────────────────────────────────────────┴───────────────┐
  │ zero forceField_, force_                                                │
  │ for each element: element.addSup(eqn, forceField_)                      │
  │     ├─ calculateForce(eqn.psi())          (BEM chain, unchanged)        │
  │     ├─ if (projectElementForce_) applyForceField(forceFieldI)           │
  │     │      suppressed when the surface is active (D3)                   │
  │     ├─ forceField += forceFieldI  (zero when suppressed)                │
  │     └─ writePerf() (element CSV unchanged)                              │
  │ force_ += element.force()                                               │
  │ if (surface_): surface_->distribute(forceField_, force_, rho?)          │
  │     └─ F_node = share_i * element[patch_i].force(); forceField_[c] -=    │
  │        F_node*(w/V_c) over candidates_i   (Eq. 18)                      │
  │ eqn += forceField_                                                      │
  └──────────────────────────────────────────────────────────────────────────┘
        │                                    │
        ▼                                    ▼
  momentum field sees the imported            postProcessing/bladeSurface/<name>.csv
  surface distribution exactly once           (per-station + optional per-node)

rotation lockstep (every time the turbine rotates, axialFlowTurbineALSource.C:671-690):
  turbine rotate() ──► blades_[i].rotate(origin_,axis_,radians) ──► actuatorLineSource
        └─ surface_->rotate(same point/axis/radians)  ⇒ nodes stay on the elements
  setSpeed() → element velocities only (surface geometry unchanged)
  pitch()    → rigid surface rotation about the element pitch axis (D5, documented)
```

Phase VI (W3):

```
runPhaseVI.sh -m asm-mesh -u 7 -mesh coarse
   ├─ case_config.py --select 7 coarse asm-mesh           (whitelist extended)
   ├─ generate_case.py --case-dir runs/asm-mesh-U7-coarse  → system/fvOptions.ASM-MESH
   ├─ install twin as system/fvOptions
   ├─ stage geometry/stl/phaseVI_blade.stl → constant/triSurface/phaseVI_blade.stl
   │     (sha256 checked against metadata/phaseVI_blade.json; mismatch aborts)
   └─ write run.json (model, staged STL hash, n_chordwise, ranks, ...)

comparePhaseVI.py --alm-dir A --asm-dir B --asm-mesh-dir C --speed 7 --sequence H
   ├─ turbine.csv  → turbine-level metrics (existing F1 formulas, ±15 % bands)
   ├─ actuatorLineElements/0/*.csv → spanwise for alm/asm (unchanged)
   ├─ bladeSurface/*.csv           → spanwise for asm-mesh (root_dist → r/R)
   └─ one turbine table + one spanwise table (three models) + sign gate
```

---

## 6. Phase VI Integration Design

### 6.1 Third `fvOptions` twin

`tools/generate_case.py`:

- `render_fv_options(...)` (`:475-505`) gains optional
  `surface_geometry: str | None = None` and `surface_kernel: str | None = None`.
  When set, the blade subdictionary gains, at the same indentation as the
  element keys (`:503-505`):

  ```
  surfaceGeometry "constant/triSurface/phaseVI_blade.stl";
  kernel gaussian;    // only when the ablation is selected; cosine is the default
  ```

  `projectElementForce` is **not** rendered (the blade source injects it, §3 D3).
  `blade2` keeps `$blade1;` + `azimuthalOffset 180` (`:564-570`), so the surface
  keys propagate to both identical blades.
- `outputs()` (`:603-640`) adds
  `system / "fvOptions.ASM-MESH": render_fv_options(..., ASM_ELEMENT, surface_geometry="constant/triSurface/phaseVI_blade.stl", surface_kernel=...)`.
  The twin is rendered on every run so `--check` covers it
  (`check_outputs`, `:643-662`).
- CLI: `--surface-kernel {cosine,gaussian}` (default `cosine`) feeds the ablation;
  `--check` is clean for the committed case.

`config/case.yaml` gains the model entry inside a new prepared stage (the
stages are consumed by `stages()`/`--stage`, not model-validated; the only model
whitelist is in the CLI, §6.3):

```yaml
  asm-mesh:
    description: three-way comparison (ASM over the imported blade surface)
    queue: sequana_cpu_long
    models: [asm-mesh]
    meshes: [coarse, fine]
    speeds: [7]
    executes: false
```

### 6.2 STL staging in `runPhaseVI.sh`

With `-m asm-mesh`, after the twin install (`:211-216`) and before `run.json`:

1. `stl_src="$root/../../geometry/stl/phaseVI_blade.stl"`,
   `meta="$root/../../geometry/metadata/phaseVI_blade.json"`.
2. The runner calls the committed helper `tools/stage_blade_stl.py` (W3, tested
   by `tests/test_blade_stage.py`): it reads `meta.stl_sha256`, hashes
   `stl_src`, creates `constant/triSurface/`, copies the STL to
   `constant/triSurface/phaseVI_blade.stl` and **aborts with exit 3** on a hash
   mismatch or a missing source (spec: a mismatch aborts; a staged run is
   self-contained).
3. `run.json` records `staged_stl_sha256` (the helper also echoes the staged
   hash) so the comparison can assert the fair-comparison input hash.

`surfaceGeometry` is case-relative, and the base sampler already resolves a
case-relative path (`mesh_.time().path()/geometryPath`,
`nacelleSurfaceSampler.C:183-192`), so restarts and relocated runs stay
self-contained.

### 6.3 Runner and config tooling

- `case_config.py:585-586`: whitelist becomes `("alm", "asm", "asm-mesh")`, and
  the error text lists the three.
- `runPhaseVI.sh:80-83`: accept `alm|asm|asm-mesh`.
- `runPhaseVI.sh:101-113`: `--nchordwise` stays ASM-family-only; the existing
  `if [ "$model" = "alm" ]` rejection already allows `asm-mesh` once the model
  case accepts it (message updated to "ASM-family").
- Run id: `asm-mesh-U<speed>-<mesh>` via the existing
  `run_id="$model-U${speed_token}-$mesh"` (`:164-178`); the twin mapping
  (`:211-214`) gains `asm-mesh) twin="fvOptions.ASM-MESH" ;;`.
- `--submit` with `-m asm-mesh` refuses (exit 2) and points at
  `scripts/slurm/asm-mesh.slurm`, mirroring the Stage 3 refusal block
  (`:123-129`): the production array does not contain the model and no
  ASM-mesh job may be submitted by this change.

### 6.4 Three-way comparison

`scripts/comparePhaseVI.py`:

- New `--asm-mesh-dir` argument (`main`, `:517-540`); the directory is analysed
  as model `asm-mesh` in the `directories` map (`:542-551`). A missing/incomplete
  ASM-mesh directory fails loudly with `EXIT_MISSING_INPUT = 1` (existing
  `analyse_model` `FileNotFoundError` path, `:586-587`).
- For `asm-mesh`, the spanwise profile comes from
  `postProcessing/bladeSurface/*.csv` (per-station rows, §4.5): read the rows in
  the averaging window, take `(root_dist, c_ref_n, c_ref_t)` and map to r/R with
  the same formula as the element path (`:259-275`). Turbine-level metrics read
  the same `postProcessing/turbines/0/turbine.csv` (`:54`) — the surface moment
  is already inside AFTAL's torque (D8).
- Outputs stay one `turbine_comparison.csv` and one `spanwise_comparison.csv`
  with all three models, the existing ±15 % / max(0.15, 20 %) bands and the sign
  gate (`:487-514`); `metrics.json` gains the model's `staged_stl_sha256` and
  the kernel selection for auditability.
- `LIMITATIONS` (`:73-87`) is extended: the imported surface is **sub-grid** at
  D/32–D/64 (cells 0.314/0.210/0.157 m vs chord 0.218–0.744 m), the
  kernel/width confound and its Gaussian ablation, and the distribution-only
  framing (the BEM chain and chord-averaged inflow are unchanged).

### 6.5 Prepared-only HPC

- New `scripts/slurm/asm-mesh.slurm`: same shape as `production.slurm`
  (`:1-85`) — guard `PHASEVI_LONG_QUEUE_AUTHORIZED=1`, module/setup preamble,
  package resolved from `$SLURM_SUBMIT_DIR`, array with one task per
  `(model, speed, mesh)`: task 0 `asm-mesh:7:coarse:H` is the **D/32 measurement
  gate**; task 1 `asm-mesh:7:fine:H` is the headline run. 48 ranks,
  `--restart`, `--run` inside the allocation.
- **Wall time**: the delta spec's "Slurm job preparation" scenario bounds each
  task at **at most 24 h**; the ASM-mesh array therefore requests
  `--time=24:00:00` (stricter than the existing 96 h `production.slurm`
  baseline, which is left untouched) and relies on `--restart` from the latest
  written time for requeues. The D/32 measurement task fits in one 24 h task;
  the D/48 headline task may need several restarts, which the script header
  documents.
- The D/32 measurement task must be executed (under explicit authorization)
  and reviewed **before** the D/48 task is submitted. The script header and the
  README state this; neither script is launched by this change.
- The existing `phaseVI-prod`, `phaseVI-stage3` and `phaseVI-stage3-d64` arrays
  (`squeue`-verified in exploration §7) are read-only baselines: not submitted,
  cancelled or modified.

### 6.6 Documentation

- `validation/phaseVI/README.md`: three models; the formulation being
  implemented (the paper's chord-line blade ASM extended to an imported
  surface — explicitly not a literal equation port); the sub-grid caveat; the
  kernel/width confound and the Gaussian ablation; the MEXICO naming
  resolution; the prepared-only arrays; the pre-registered hypothesis; the
  attribution block (SAL adaptation credit, NREL citations including
  NREL/SR-440-6918 for the S809 profile, and the pinned `of-plugins` commit
  with the ASM patch note — spec `phasevi-data-provenance`, "Source attribution
  and provenance pinning").
- `turbinesFoam/README.md` and root `README.md`: the `surfaceGeometry` key, the
  `projectElementForce` suppression semantics, the kernel modes and the geometry
  pipeline component.
- `turbinesFoam/geometry/README.md` + `PROVENANCE.md`: `phaseVI_blade`, the
  S809 dataset, the retired `blade0/1/2` reservation.
- Root `CHANGELOG.md`: one entry per work unit in the repository's
  `Files:` / `Problem:` / `Fix:` format.

---

## 7. Geometry Pipeline Design

### 7.1 Layout after S2

```
turbinesFoam/geometry/
├── README.md             # component table: nacelle + phaseVI_blade; naming resolution
├── PROVENANCE.md         # per-component source/generator/hashes incl. S809 inputs
├── src/
│   ├── nacelle.geo       # unchanged (gmsh, pinned)
│   ├── blade_phasevi.py  # new: S809 CSV parse + structured loft + metadata helpers
│   └── makeGeometry.py   # builder registry; gmsh path only for `nacelle`
├── stl/
│   ├── nacelle.stl       # unchanged bytes
│   └── phaseVI_blade.stl # new, committed binary STL
└── metadata/
    ├── nacelle.json      # unchanged bytes
    └── phaseVI_blade.json

turbinesFoam/validation/phaseVI/data/
├── geometry/             # unchanged (phaseVI_blade.csv + PROVENANCE)
├── polars/               # unchanged
├── experiment/           # unchanged
└── s809/                 # new
    ├── s809_somers_nlr.csv
    └── PROVENANCE.md
```

### 7.2 `makeGeometry.py` changes (exact touch points)

| Location | Change |
|---|---|
| `:63-88` (`Component`, `COMPONENTS`, `RESERVED_COMPONENTS`) | `Component` gains `builder: str`; `COMPONENTS = ("nacelle", "phaseVI_blade")`; `RESERVED_COMPONENTS = ()`; add `BUILDERS = {"nacelle": build_gmsh_component, "phaseVI_blade": build_blade_component}` |
| `:319-388` (`build_component`) | Keep the gmsh implementation as `build_gmsh_component`; add `build_blade_component(target)` that imports `blade_phasevi`, builds canonical triangles + metadata, writes STL/metadata and returns `(metadata_text, summary)`; both return the same shape so `generate`/`check` are route-agnostic |
| `:399-427` (`generate`) | Resolve the builder from the registry; only the gmsh route resolves/validates a gmsh executable |
| `:430-502` (`check`) | Same dispatch: the blade route regenerates into a temp dir with no gmsh lookup at all (spec: `--check --component phaseVI_blade` works without gmsh); the provenance-hash check is shared |
| `:508-560` (`main`) | Move the `shutil.which("gmsh")` lookup (`:549-556`) behind the route check; `--component` help and the reserved/unknown error messages (`:522-547`) derive from the registry |
| `:56` (`STL_HEADER`) | Header becomes per-component (`... - nacelle ...`, `... - phaseVI_blade (S809, wetted)`); the nacelle header bytes must not change |

### 7.3 `blade_phasevi.py` algorithm (deterministic, pure Python)

```
INPUTS
  stations  = parse(phaseVI_blade.csv)          # 26 rows, strictly increasing r
  s809      = parse(s809_somers_nlr.csv)        # upper/lower (x/c, z/c), LE->TE
  pitch_deg = 3.0                               # asserted == case.yaml turbine.pitch_deg

CLOSED PROFILE (shared by all sections; §4.4 frame and LE-based chord fraction)
  upper = s809.upper                            # 31 pts, LE->TE, ends at the shared TE (1,0)
  lower = reversed(s809.lower[:-1])             # 29 pts after dropping the TE duplicate
  profile = upper + lower                       # 60 pts, starts at the first upper LE
                                                # point, over the TE, back along the lower
                                                # surface; closes over the LE gap
  frac[k] = cumulative perimeter fraction of profile[k]   # 0.0 at the first upper LE point
  N = len(profile) = 60

SECTION at station (r, chord, twist_report, mount)
  # Section-local axes: u[k] = LE-based chord fraction (0 at LE, 1 at TE, §4.4);
  # w[k] = S809 ordinate z/c. Generation frame (§4.4): y = reference chord T->L,
  # x = y x z = section normal, z = outward span; the section is built in the
  # x-y plane at z = r with the chord-line quarter-chord point at the origin.
  if r <= 0.8835:                                # cylinder / transition root
      phi[k] = pi - 2*pi*frac[k]                 # LE at frac 0
      (u[k], w[k]) = (0.5 + 0.5*cos(phi[k]), 0.5*sin(phi[k]))  # radius 1/2, mid-chord centre
  else:                                          # S809 from 1.0085 outward
      (u[k], w[k]) = profile[k]                  # (x/c, z/c), both LE-based
  x[k] = w[k]*chord                              # ordinate along the section normal
  y[k] = (0.25 - u[k])*chord                     # quarter-chord at y = 0
  rotate (x, y) about +z by sigma*(-(twist_report + pitch_deg)); sigma = -1 for
      the Phase VI/twin orientation (the element pitch axis is radially inward,
      element_data.py:40, actuatorLineSource.C:371, §4.4)
  set z = r: the chord-line quarter-chord point (u = 0.25) is then on the
  radial reference line (x = y = 0) at the station, and the point at chord
  fraction `mount` sits at y = -(mount - 0.25)*chord, matching the element
  placement (axialFlowTurbineALSource.C:166-168) and the element pitch axis
  (actuatorLineElement.C:937-940)

LOFT
  for i in 0..24:                                # 25 segments, 26 rings
      for k in 0..N-1:
          a,b = ring i [k], ring i [k+1 mod N]
          c,d = ring i+1 [k], ring i+1 [k+1 mod N]
          emit triangles (a,b,c) and (b,d,c)     # fixed winding (outward)
  total triangles = 2*N*25 = 3000

NODES / METADATA (one entry per canonical triangle)
  radial_station = mean z of the three vertices in the generation frame
  chord_fraction = mean of the three vertices' construction-time LE-based
                   chord fractions u = x/c (§4.4)
  normal/area  = triangle_normal_area (makeGeometry.py:185-191)

OUTPUT
  canonical_triangles(...) -> write_binary_stl(..., STL_HEADER, target.stl)
  render_metadata(...) with the populated node entries and no _reserved block
```

Determinism: fixed iteration order, no RNG, no gmsh, float64 Python arithmetic,
float32 packing at write time (as the existing writer), canonical triangle
re-serialization (`makeGeometry.py:194-209`). `--check` regenerates into a
temporary directory and byte-compares (`makeGeometry.py:452-495`). A stale
artifact is reported and the tree is never modified (spec "`--check`
regenerability").

### 7.4 S809 dataset and provenance

`validation/phaseVI/data/s809/PROVENANCE.md` records, in the same field style
as `data/geometry/PROVENANCE.md`: source (Somers, NREL/SR-440-6918), source PDF
sha256 `a7496aad…feeb3`, table id "Table 2, S809 Airfoil Coordinates" (PDF page
index 19), extraction tool/version (PyMuPDF 1.27.2.3), extraction date, the
regex/row recipe, the committed CSV sha256, and both cross-checks of §3 D11
including the measured maximum deviation and the excluded last-10 %-chord
region. No PDF is committed (`phasevi-data-provenance` MODIFIED "Derived
artifacts only"). `data/s809/` is added to the "per-directory provenance"
listing and the pure-Python data-sanity tests.

### 7.5 `mexico-validation` boundary

This change retires the `blade0/1/2` reservation and documents the Phase VI/S809
blade component; it does **not** create or modify any `mexico_blade` component,
and it does not touch `openspec/changes/mexico-validation/**`. A future MEXICO
blade is a separate component name owned by that change; the registry/policy
introduced here is the extension point.

---

## 8. Test Design

C++ has no unit framework in this repository; the C++ path is verified through
solver-driven integration tests plus pure-Python expected-value checks, exactly
as S1 did (`archive/2026-09-20-nacelle-actuator-surface/design.md` §9). New
solver-driven modules are added to `tests/conftest.py`'s `SOLVER_DRIVEN` tuple
(`conftest.py:17-25`) so they skip cleanly without OpenFOAM.

### 8.1 W1 — C++ distributor, suppression, bounded query, lockstep

| Artifact | Kind | What it verifies |
|---|---|---|
| `tests/bladeSurface/` (new case dir, mirroring `tests/nacelleSurface/`) | Case fixture | 0.1 m cubic mesh, uniform inflow, a minimal standalone `actuatorLineSource` with one cylinder element and a two-triangle plate STL; `system/fvOptions` (no surface) and `system/fvOptions.surface` (with `surfaceGeometry`, plus a Gaussian variant) with a `forceIntegral` functionObject |
| `tests/test_blade_surface.py::test_serial_surface` | Integration (solver-driven) | Surface case runs, logs the distributor summary; the `force.<blade>` volume integral equals the element CSV total (`Σ element force`) exactly once — the **partition-of-unity / no-double-count** gate |
| `::test_default_path_projects_strips` | Integration | Without `surfaceGeometry`, the field integral is non-zero and equals the element total; `projectElementForce` is never injected (log/echo inspection) — the ALM/no-mesh ASM default gate |
| `::test_suppressed_element_still_reports` | Integration | With the surface active, the element CSV is present and finite; its **first** row (first PIMPLE solve of the first step, where the momentum field is still identical to the default run) equals the default run's first row exactly, while later rows are only required to be finite and physical because the surface changes the inflow; the field integral of the surface run equals the surface total, not surface + strips |
| `::test_station_and_node_csv` | Integration | Per-station CSV parses, has one row per element, `root_dist` strictly increasing, `c_ref_n/c_ref_t` finite; per-node CSV (opt-in) has stable node count and `chord_fraction ∈ [0,1]`; node `station` values are monotone in radius |
| `::test_partition_invariants_from_csv` | Integration | Patch areas sum to the total surface area and every element owns at least one node (the constructor assertions are mirrored on the written output) |
| `::test_rotation_lockstep` | Integration | The small AFTAL fixture (below) with `surfaceGeometry` and a rotating rotor: per-node positions at two time steps rotate by the azimuth delta reported in `turbine.csv`; element CSV and node count unchanged |
| `::test_surface_moment_in_torque` | Integration | The fixture's `turbine.csv` torque coefficient must reconstruct (`ct·0.5·frontalArea·rotorRadius·\|V∞\|²`) to the rotor-axis projection of the surface node moment `Σ_nodes X_i × F_i` read from the opt-in per-node CSV (`rho 1.0` so the CSV forces are the per-unit-density forces used by `moment()`; node positions and forces mapped from the body frame to the global frame with the D5 construction basis; `rtol 1e-6`) — the moment of the load actually applied (D8). The plate nodes are offset from the element position, so the element-position moment falls outside that band: the D8 replacement convention is asserted, not merely "a moment exists" |
| `::test_parallel_total_preserved` | Integration | `mpirun -np 2`: field integral equals the serial total (cross-rank candidate/ownership path); a node whose support straddles the processor boundary is exercised by the plate placement |
| `::test_kernel_gaussian_conserves` | Integration | Gaussian ablation mode still conserves the total (width change only) |
| `::test_missing_empty_corrupt_stl_aborts` | Integration | Missing/empty/unparseable `surfaceGeometry` raises `FatalError` (mirrors `test_nacelle.py:283-308`) |
| Regression gates | Existing suite | `test_al`, `test_asm`, `test_aftal`, `test_aftal_asm`, `test_cftal`, `test_libs`, `test_nacelle` pass unchanged; `./Allwmake` exits 0; `ldd -r` clean |

The two AFTAL-based tests (`::test_rotation_lockstep`,
`::test_surface_moment_in_torque`) use a dedicated minimal fixture
(`tests/bladeSurfaceAFTAL/`), **not** the multi-element tutorial turbine: one
blade whose `elementData` has two geometry rows (one segment) and `nElements` a
multiple of the segment count (`actuatorLineSource.C:140-145`), i.e. one
element, no hub/tower, `writeNodePerf true`, `rho 1.0`. The STL is generated by
the test as a small multi-triangle plate at the element station in the canonical
generation frame (rotated by the element mounting angle expressed in that frame,
§4.4), so the single element owns a non-empty patch (D4) and its nodes are
offset from the element position (needed by the moment test). The two-triangle
plate of `tests/bladeSurface/` cannot be paired with the tutorial turbine: every
element must own nodes, and the plate's nodes all fall in one patch.

Commands: `cd turbinesFoam && ./Allwmake && ldd -r $FOAM_USER_LIBBIN/libturbinesFoam.so`;
`cd turbinesFoam && pytest -q tests/test_blade_surface.py tests/test_nacelle.py tests/test_asm.py tests/test_al.py tests/test_aftal.py tests/test_aftal_asm.py tests/test_libs.py`.

### 8.2 W2 — geometry data and builder

| Artifact | Kind | What it verifies |
|---|---|---|
| `tests/test_blade_data.py::test_s809_provenance_complete` | Pure Python | PROVENANCE records report, PDF sha256, table id, tool/version/date, cross-check, committed CSV sha256 |
| `::test_s809_parses_as_airfoil` | Pure Python | Upper/lower `x/c, z/c` pairs, shared TE at `(1.0000, 0.0000)`, numeric and monotone in x per surface |
| `::test_blade_metadata_complete` | Pure Python | Every node entry has numeric `radial_station` and `chord_fraction`; component/inputs/hashes present; no `_reserved` null blade mapping |
| `::test_stl_manifold_wetted_only` | Pure Python | Every edge has 1 or 2 incident triangles, interior edges exactly 2 with opposite orientation; exactly two boundary rings (no caps); no duplicate/degenerate triangles; root/tip `z` values match the CSV |
| `::test_check_byte_identical_without_gmsh` | Pure Python | `makeGeometry.py --check --component phaseVI_blade` exits 0 without a runnable gmsh, regenerates byte-identically in a temp tree, and leaves the tree unchanged (copy-and-corrupt pattern of `test_nacelle_data.py:370-412`) |
| `::test_builder_registry_and_retired_reservation` | Pure Python | `phaseVI_blade` accepted through the Python route; `blade0/1/2` no longer advertised as deferred; unknown components rejected listing the registry; nacelle route still requires the pinned gmsh |
| `test_nacelle_data.py` updates | Pure Python | `_reserved` assertion (`:217-219`), README token list (`:272-286`) and the deferred-blade rejection test (`:292-301`) updated to the new policy while nacelle bytes/hashes stay pinned |
| `test_phasevi_data.py` updates | Pure Python | `data/s809/` is included in the provenance-dir checks (`:192-205`) and the no-artefacts walk still passes (`:208-219`) |

Commands: `cd turbinesFoam && pytest -q tests/test_blade_data.py tests/test_nacelle_data.py tests/test_phasevi_data.py`;
`cd turbinesFoam/geometry && python3 src/makeGeometry.py --check --component phaseVI_blade`
(and the gmsh-dependent nacelle checks, which skip when gmsh is not runnable).

### 8.3 W3 — Phase VI integration

| Artifact | Kind | What it verifies |
|---|---|---|
| `tests/test_phasevi_case.py::test_twins_differ_only_in_blade_keys` (extended) | Pure Python | Three twins; `BLADE_KEYS` (`:59`) extended with `surfaceGeometry`/kernel keys; after stripping, all three renders and the committed files are identical; `fvOptions.ASM-MESH` carries `surfaceGeometry` in both blades |
| `::test_asm_mesh_selection` | Pure Python | `case_config.py --select 7 coarse asm-mesh` succeeds and an unconfigured model still fails; run id `asm-mesh-U7-coarse` |
| `::test_stage_matrix` (extended) | Pure Python | New prepared stage present, `executes` false, only `stage0` executes (keeps `:225-226`) |
| `tests/test_blade_stage.py` (new, pure Python) | Pure Python | `tools/stage_blade_stl.py` stages into `constant/triSurface/`, reports the committed sha256, and aborts on a hash mismatch or a missing source (spec staging scenarios) |
| `tests/test_phasevi_compare.py` (extended) | Pure Python | Three-way dry merge on synthetic fixtures including a `bladeSurface` CSV; surface rows convert to the five r/R stations with the existing definitions; `--asm-mesh-dir` missing/incomplete exits non-zero; sign gate covers three models |
| `tests/test_phasevi_case.py::test_generated_case_is_current` | Pure Python | Committed `case/system/fvOptions.ASM-MESH` matches the renderer |

Commands: `cd turbinesFoam && pytest -q tests/test_phasevi_case.py tests/test_phasevi_data.py tests/test_phasevi_compare.py tests/test_blade_stage.py`;
`python3 validation/phaseVI/tools/generate_case.py --check`;
`scripts/runPhaseVI.sh -m asm-mesh -u 7 -mesh coarse` (prepares only; no `--run`/`--submit`).

### 8.4 W4 — measurement gate

| Artifact | Kind | What it verifies |
|---|---|---|
| `tests/test_blade_surface.py::test_instrumentation_line` | Integration (solver-driven) | The per-`addSup` line reports nodes, candidate entries and seconds (D6); the candidate count is far below `nNodes × N_local cells` (bounded-query evidence) |
| Instrumented D/32 run (prepared-only; executed only with authorization) | Manual/authorized | Nodes, candidate cells/node and seconds per `addSup`; the gate decision (proceed / harden / restrict campaign) is recorded before any D/48 preparation |
| `scripts/slurm/asm-mesh.slurm` + README | Review | The measurement task is prepared-only, guarded by `PHASEVI_LONG_QUEUE_AUTHORIZED=1`, and documented as the gate for the D/48 task |
| Conditional hardening (only if the gate demands) | Integration | Same partition-of-unity and MPI totals after the candidate-query change; default distribution unchanged |

The instrumentation (counters, `Info` line and optional CSV row) is added in W4
inside `bladeSurfaceSource::distribute()`; `::test_instrumentation_line` pins the
line format and no separate parser is added.

### 8.5 Fair-comparison and determinism gates (cross-unit)

- **Full-suite regression**: `cd turbinesFoam && pytest -q` passes; solver-driven
  modules auto-skip without OpenFOAM (`conftest.py:28-36`).
- **ALM/no-mesh byte-identical**: no `surfaceGeometry` → no distributor, no
  injected key; the existing element/turbine CSVs are the baseline.
- **Dataset/STL determinism**: S809 CSV sha256 pinned in provenance; STL and
  metadata byte-identical under `--check` on a clean tree and non-destructive on
  a stale tree.
- **Staged-STL integrity**: staged copy hash equals the committed STL sha256;
  `run.json` records it, and the comparison asserts it for the fair-comparison
  check.

---

## 9. Work Units (delivery forecast)

Line counts are change totals (additions + deletions, including moves). Each
unit ends with its own tests and docs, has a single reviewable purpose, and
reverts cleanly on its own.

### W1 — Blade surface distributor (C++)

| Field | Value |
|---|---|
| Deliverable | `surfaceSamplerBase` extraction + `nacelleSurfaceSampler` re-basing (byte-identical), `bladeSurfaceSampler`/`bladeSurfaceSource`, `projectElementForce` plumbing, `surfaceGeometry` read, bounded candidates, rotation/pitch/translate forwarding, per-station/per-node CSV, `Make/files`, integration case + tests, turbinesFoam README |
| Files | `src/fvOptions/nacelleSurface/surfaceSamplerBase.{H,C,I.H}` (new), `nacelleSurface/nacelleSurfaceSampler.{H,C}` + `nacelleSurfaceSource.{H,C}` (modified), `src/fvOptions/bladeSurface/bladeSurfaceSampler.{H,C}` + `bladeSurfaceSource.{H,C}` (new), `actuatorLineSource/actuatorLineSource.{H,C}`, `actuatorLineSource/actuatorLineElement/actuatorLineElement.{H,C}`, `src/Make/files`, `tests/conftest.py`, `tests/test_blade_surface.py`, `tests/bladeSurface/**` |
| Est. lines | ~600–900 |
| Focused verification | `./Allwmake`; `ldd -r`; `pytest -q tests/test_blade_surface.py tests/test_nacelle.py tests/test_asm.py tests/test_al.py tests/test_aftal.py tests/test_aftal_asm.py tests/test_libs.py`; partition-of-unity / no-double-count integration checks; `mpirun -np 2` total preserved |
| Rollback | `git revert` W1: removes the new source tree and the base extraction; `nacelleSurfaceSampler`/element/source restored; default paths byte-identical. Configuration rollback = delete `surfaceGeometry` from a case. |
| Boundary | Ends before any geometry data or Phase VI change. No S1 observable behavior may change (nacelle CSVs byte-comparable). |

### W2 — Blade geometry

| Field | Value |
|---|---|
| Deliverable | S809 CSV + PROVENANCE (extraction + two cross-checks), `blade_phasevi.py` loft, `phaseVI_blade` STL + metadata + PROVENANCE/README rows, builder registry and retired reservation, tests |
| Files | `validation/phaseVI/data/s809/{s809_somers_nlr.csv,PROVENANCE.md}` (new), `geometry/src/blade_phasevi.py` (new), `geometry/src/makeGeometry.py`, `geometry/stl/phaseVI_blade.stl` (new), `geometry/metadata/phaseVI_blade.json` (new), `geometry/{README.md,PROVENANCE.md}`, `tests/test_blade_data.py` (new), `tests/test_nacelle_data.py`, `tests/test_phasevi_data.py` |
| Est. lines | ~400–600 |
| Focused verification | `pytest -q tests/test_blade_data.py tests/test_nacelle_data.py tests/test_phasevi_data.py`; `python3 geometry/src/makeGeometry.py --check --component phaseVI_blade` byte-identical, no gmsh; nacelle artifacts unchanged |
| Rollback | `git revert` W2: removes the blade component artifacts, builder and test updates; nacelle component untouched; Phase VI case unaffected (W3 stages the file at run time). |
| Boundary | No Phase VI case/runner change; only the s809 data dir is added inside the validation package. |

### W3 — Phase VI third variant

| Field | Value |
|---|---|
| Deliverable | `fvOptions.ASM-MESH` twin, `case.yaml` stage entry, `case_config.py` whitelist, `--surface-kernel`, runner model + staging helper, three-way compare, prepared-only array, case/compare/staging tests, README/CHANGELOG |
| Files | `config/case.yaml`, `tools/generate_case.py`, `tools/case_config.py`, `tools/stage_blade_stl.py` (new), `case/system/fvOptions.ASM-MESH` (new), `scripts/runPhaseVI.sh`, `scripts/comparePhaseVI.py`, `scripts/slurm/asm-mesh.slurm` (new), `tests/test_phasevi_case.py`, `tests/test_phasevi_compare.py`, `tests/test_blade_stage.py` (new), `validation/phaseVI/README.md`, root `README.md`, `CHANGELOG.md` |
| Est. lines | ~400–600 |
| Focused verification | `pytest -q tests/test_phasevi_case.py tests/test_phasevi_data.py tests/test_phasevi_compare.py tests/test_blade_stage.py`; `generate_case.py --check`; `runPhaseVI.sh -m asm-mesh -u 7 -mesh coarse` renders/prepares without `--run`/`--submit` |
| Rollback | `git revert` W3: removes twin/staging/compare/array additions; `-m alm`/`-m asm` behavior unchanged. `case.yaml` reverts with the unit. |
| Boundary | Prepared-only: no submission, no changes to the queued baseline arrays. |

### W4 — Performance measurement gate (conditional hardening)

| Field | Value |
|---|---|
| Deliverable | Per-`addSup` timing/candidate-count instrumentation in `bladeSurfaceSource` + `::test_instrumentation_line`, prepared D/32 measurement setup (case/array entry + documentation), and **only if the gate demands** a mesh-tree/stencil candidate query |
| Files | `src/fvOptions/bladeSurface/bladeSurfaceSource.{H,C}` (instrumentation; conditional candidate-query hardening), `tests/test_blade_surface.py`, `scripts/slurm/asm-mesh.slurm` (measurement task/documentation), `validation/phaseVI/README.md` |
| Est. lines | ~150–350 |
| Focused verification | `pytest -q tests/test_blade_surface.py::test_instrumentation_line`; instrumented run reports nodes, candidate cells/node and seconds per `addSup`; the measurement run is prepared and executed only with explicit authorization; if hardened, W1's integration tests must still pass |
| Rollback | `git revert` W4: removes instrumentation/measurement additions (and any optimized query); W1 default distribution unchanged |
| Boundary | No measurement result may change model defaults; the campaign-scope decision stays with the user (Q2). |

### Delivery shape

The session strategy is `single-pr`; the forecast (~1550–2450 lines) exceeds the
400-line budget, so under `single-pr` **apply requires an explicit
`size:exception` before it starts**. The W1→W2→W3→W4 chain is prepared as the
alternative: every unit is independently testable, independently revertable, and
W2/W3/W4 do not change W1 semantics. This mirrors S1's W1/W2/W4a/W4b precedent.

```
Decision needed before apply: Yes
Chained PRs recommended: Yes
400-line budget risk: High
```

---

## 10. Threat Matrix

N/A — the change introduces no routing, shell-command, VCS/PR-automation, or
executable-file-classification boundary. The subprocess surfaces are the same
class S1 assessed: `makeGeometry.py` invoking `gmsh` for the **nacelle**
component only (pinned version, fixed inputs, sha256-verified output,
non-destructive `--check`); the pure-Python blade builder, which invokes no
subprocess at all; `runPhaseVI.sh` staging a committed file read-only and
refusing `--submit` for `-m asm-mesh`; and the **prepared-only** Slurm array,
which refuses to run without `PHASEVI_LONG_QUEUE_AUTHORIZED=1` and is never
launched by this change. None of these is an autonomous path with adversarial
inputs, so the matrix's boundaries (documentation-like paths, git repository
selection, commit state, push state, PR commands) do not apply and no rows are
marked applicable. The comparison tooling remains a local, human-invoked script.

## 11. Migration / Rollout

No data migration or schema changes to existing artifacts. The change is
opt-in and additive:

- **Configuration**: without `surfaceGeometry`, no distributor is constructed,
  no `projectElementForce` is injected, and ALM/no-mesh ASM behavior is
  unchanged. Rollback from an adopting case = delete the key (no recompile).
- **Code**: `git revert` per work unit (§9); the nacelle base extraction is
  covered by the S1 regression gate.
- **Data**: the S809 dataset and blade STL revert with W2; a staged STL in a run
  directory is a copy and can be deleted without affecting other models.
- **Rollout gates**: `./Allwmake` exit 0 + `ldd -r` clean; full pytest suite
  unchanged; `makeGeometry.py --check` clean for the remaining components;
  `generate_case.py --check` clean for the committed case.
- **HPC**: the ASM-mesh array and the D/32 measurement are prepared only;
  execution requires explicit authorization, and the queued ALM/ASM baselines
  (`phaseVI-prod`, `phaseVI-stage3`, `phaseVI-stage3-d64`) stay untouched.

## 12. Risks and Open Items

**Risks**

1. **Double counting (high)**: mitigated by one distributing owner per blade,
   the additive `projectElementForce` default-true injection, and the explicit
   partition-of-unity integration test (§8.1).
2. **Shared-base refactor regresses the nacelle (medium)**: mitigated by moving
   only generic assets (§3 D2), keeping the distribution expression and cell
   iteration order identical, and gating on the existing nacelle suite
   (byte-comparable CSVs).
3. **Sub-grid imported surface (high, scope honesty)**: at D/32–D/64 the blade
   is 1–2 cells wide; the three-way comparison tests **model form**, not
   resolved chordwise physics. Stated in the README, the comparison
   limitations, and the pre-registered hypothesis; the Gaussian ablation
   separates geometry from the kernel/width confound.
4. **Performance (high)**: bounded candidate query in W1 plus the D/32
   measurement gate before the D/48 preparation (W4). Fallbacks: octree/stencil
   hardening, campaign restricted to D/32+D/48, or deferral (Q2, user decision).
5. **Geometry determinism/tessellation (medium-high)**: fixed-topology pure
   Python loft, canonical triangle ordering, byte-identical `--check`;
   manifoldness and no-caps asserted by tests.
6. **S809 provenance (medium)**: extraction from the verified Somers PDF with a
   recorded recipe, plus two cross-checks (TP-500-29955 Table A-2 transcription
   and Ramsay Table A1 measured model); the text dump alone is not authoritative.
7. **Torque convention (medium)**: the surface node moment replaces the element
   moment when active (D8); documented in the CSV header, README and comparison
   limitations so the difference is auditable.
8. **Momentum-consistent kinematics (medium)**: the surface follows
   rotate/translate and a rigid pitch approximation; harmonic pitching with an
   active surface is documented (not used by Phase VI). The committed loft bakes
   the Phase VI twist sign `σ = −1` about the outward span (§4.4); the W1
   task-level check confirms the placement and twist on a running case, and
   PROVENANCE records the convention.
9. **Review budget (blocking)**: `size:exception` or the chained W1→W4 units
   must be resolved before apply (§9).
10. **HPC authorization (medium)**: prepared-only artifacts; existing arrays
    read-only; measurement/campaign only under explicit authorization.

**Open items (task-level verification)**

- Confirm the corrected orientation end to end on a running case (W1): the
  injected outward `surfaceSpanDirection` (D5), the σ twist sign of the loft
  (§4.4/D10) and the LE-based chord association place every surface section on
  its element's chord line (`position_i` along `chordDirection_i`) for both
  blades (blade2 azimuth 180) — a mirrored span, a flipped twist or an inverted
  chord association must fail the integration case.
- Confirm the `bodyAxis` basis completion produces the documented blade mount
  frame for both blades (blade2 azimuth 180) on the OpenFOAM toolchain.
- Confirm `pitch()` forwarding for an active surface against a harmonic-pitching
  case (documented rigid approximation).
- Confirm the Ramsay Table A1 parser tolerance (last-10 %-chord exclusion) on
  the real table; record the measured max deviation in PROVENANCE.
- Confirm the D/32 instrumentation overhead is negligible relative to the
  momentum solve.

---

## 13. File Changes

| File | Action | Description |
|------|--------|-------------|
| `turbinesFoam/src/fvOptions/nacelleSurface/surfaceSamplerBase.{H,C}` and `surfaceSamplerBaseI.H` | Create | Generic geometry/kernel/distribution base extracted from S1 (D2): triSurface load, centroids/normals/areas, body frame, `cellSize`, `kernel`, `interpolateVelocity`, `distributeForce` with optional candidate list, `rhoRef` |
| `turbinesFoam/src/fvOptions/nacelleSurface/nacelleSurfaceSampler.{H,C}` | Modify | Derive from the base; keep the nacelle force model, static frame, streamwise/friction state; unchanged observable behavior |
| `turbinesFoam/src/fvOptions/nacelleSurface/nacelleSurfaceSource.{H,C}` | Modify | Call the base distribution helper with "all local cells"; CSV/`read()`/RTS unchanged |
| `turbinesFoam/src/fvOptions/bladeSurface/bladeSurfaceSampler.{H,C}` | Create | Rotating-frame sampler: canonical/global/body node lists, station/chord association, patch partition, candidate lists, SI contract |
| `turbinesFoam/src/fvOptions/bladeSurface/bladeSurfaceSource.{H,C}` | Create | Per-blade distributor: `surfaceGeometry` read, activation, Eq. 18 distribution into the blade field, moment, per-station/per-node CSV; W4 adds the instrumentation counters |
| `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineSource.{H,C}` | Modify | Read `surfaceGeometry`; inject `projectElementForce false` in `createElements()`; construct/own the distributor; forward rotate/translate/pitch; distribute after the element loop; surface moment in `moment()`; pass the injected construction frame from AFTAL |
| `turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/actuatorLineElement.{H,C}` | Modify | `projectElementForce_` key (default true) guarding the two `applyForceField` calls; `chordDirection()` accessor for the node association and `spanDirection()` for the surface pitch forwarding (D4/D5) |
| `turbinesFoam/src/fvOptions/axialFlowTurbineALSource/axialFlowTurbineALSource.C` | Modify | Inject `surfaceOrigin`/`surfaceSpanDirection`/`surfaceChordDirection` (outward root→tip span and reference chord from the post-cone/post-azimuth geometry) into blade subdicts when `surfaceGeometry` is present |
| `turbinesFoam/src/Make/files` | Modify | Register `surfaceSamplerBase.C`, `bladeSurfaceSampler.C`, `bladeSurfaceSource.C` (`-lsurfMesh` already linked by S1, `src/Make/options:13`) |
| `turbinesFoam/geometry/src/blade_phasevi.py` | Create | Pure-Python S809 parse + structured loft + metadata (D10) |
| `turbinesFoam/geometry/src/makeGeometry.py` | Modify | Builder registry, route-aware `generate`/`check` (gmsh only for nacelle), retired reservation, per-component header (D12, §7.2) |
| `turbinesFoam/geometry/stl/phaseVI_blade.stl`, `metadata/phaseVI_blade.json` | Create | Committed blade component (canonical binary STL + populated metadata) |
| `turbinesFoam/geometry/README.md`, `PROVENANCE.md` | Modify | Component table, builder route, inputs/hashes, naming resolution |
| `turbinesFoam/validation/phaseVI/data/s809/s809_somers_nlr.csv`, `PROVENANCE.md` | Create | Committed S809 design coordinates + extraction/cross-check provenance (D11) |
| `turbinesFoam/validation/phaseVI/config/case.yaml` | Modify | `asm-mesh` prepared stage entry |
| `turbinesFoam/validation/phaseVI/tools/generate_case.py` | Modify | `fvOptions.ASM-MESH` render path, `--surface-kernel` |
| `turbinesFoam/validation/phaseVI/tools/case_config.py` | Modify | `--select` whitelist extended to `asm-mesh` |
| `turbinesFoam/validation/phaseVI/tools/stage_blade_stl.py` | Create | Testable STL staging + sha256 verification helper used by the runner |
| `turbinesFoam/validation/phaseVI/case/system/fvOptions.ASM-MESH` | Create | Committed third twin |
| `turbinesFoam/validation/phaseVI/scripts/runPhaseVI.sh` | Modify | `-m asm-mesh`, twin mapping, STL staging call, `--submit` refusal for the model |
| `turbinesFoam/validation/phaseVI/scripts/comparePhaseVI.py` | Modify | `--asm-mesh-dir`, surface-station reader/conversion, three-way tables, extended limitations |
| `turbinesFoam/validation/phaseVI/scripts/slurm/asm-mesh.slurm` | Create | Prepared-only array (D/32 measurement + D/48 headline) |
| `turbinesFoam/validation/phaseVI/README.md` | Modify | Three models, formulation extension, sub-grid caveat, kernel confound/ablation, naming resolution, pre-registered hypothesis, prepared-only plan |
| `turbinesFoam/tests/test_blade_surface.py`, `tests/bladeSurface/**`, `tests/test_blade_data.py`, `tests/test_blade_stage.py` | Create | New solver-driven and pure-Python coverage (§8) |
| `turbinesFoam/tests/conftest.py`, `tests/test_nacelle_data.py`, `tests/test_phasevi_case.py`, `tests/test_phasevi_compare.py`, `tests/test_phasevi_data.py` | Modify | SOLVER_DRIVEN registration; updated reserved-policy and three-way contracts |
| `turbinesFoam/README.md`, root `README.md`, root `CHANGELOG.md` | Modify | Config keys, suppression semantics, kernel modes, geometry component, formulation/limitations, changelog entries |
| `openspec/changes/mexico-validation/**`, `openspec/changes/archive/**`, `openspec/specs/**` | Untouched | Out of scope |
| `precice-openfoam-adapter/**`, `fsiOmega/**` | Untouched | S3 deferred (spec "Seam only") |

## 14. Open Questions

1. **Delivery shape before apply**: explicit `size:exception` under `single-pr`
   vs the prepared chained units W1→W2→W3→W4 — user decision required before
   `sdd-apply` (proposal open question 4).
2. **Campaign scope after the performance gate**: if the D/32 measurement
   exceeds the practical budget, choose (a) bounded-query hardening, (b)
   campaign restricted to D/32 + D/48, or (c) deferral — needs the measured
   numbers.
3. **Kernel-matched ablation in the first campaign**: embed the Gaussian
   ASM-mesh configuration in the prepared array or hold it for a follow-up
   (cheap configuration, no new code). The design supports either; the canonical
   twin stays paper-cosine.
4. **Acceptance semantics**: are the existing bands a merge gate for the
   ASM-mesh variant or a reported comparison? (Engineering recommendation:
   report, with engineering-only merge criteria — proposal open question 3.)
5. **Component name confirmation**: `phaseVI_blade` is used throughout; only
   naming/ownership is open, the MEXICO conflict is resolved either way
   (proposal open question 1).
6. **Section construction details**: the design fixes the wetted-surface loft,
   the sharp closed TE, the blunt-LE closure and the two-ring open shell; any
   later change to the section topology is a W2 design revision, not a user
   input.
