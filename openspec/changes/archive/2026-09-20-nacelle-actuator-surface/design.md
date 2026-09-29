# Design: Nacelle/hub actuator surface model (ASM) + geometry pipeline + FSI seams

Change: `nacelle-actuator-surface` — slice **S1** of a staged program (S2 = blade STL
surface option, S3 = preCICE FSI wiring; both deferred).

Reference: Yang & Sotiropoulos, *A new class of actuator surface models for wind
turbines*, arXiv:1702.02108v4. All equation numbers below are the paper's own
numbers, verified against the arXiv HTML (v4). Equations 7, 8, 17, 18 belong to
Sec. 2.1 (blade); 19–23 to Sec. 2.2 (nacelle); the governing momentum equation is
Eq. 25 (Sec. 3).

---

## 1. Technical Approach

The paper's nacelle model is a **bluff-body force model with no blade-element
(BEM) content**: no coefficient lookup, no angle of attack, no dynamic stall, no
added mass. Forcing it through the existing element API
(`actuatorLineSource`/`actuatorSurfaceElement`) or inline in
`axialFlowTurbineALSource` entrenches the wrong abstraction (exploration
Approach 1). The design therefore adds a **dedicated `fv::option` source** —
`nacelleSurfaceSource` (deriving `cellSetOption`, registered as
`type nacelleSurfaceSource;`) — that owns a **reusable surface-sampling object**
(`nacelleSurfaceSampler`), and maps Sec. 2.2 one-to-one:

1. **Read** the nacelle surface as an STL triangulation (`triSurface::New`).
2. **Compute** per-node geometry (triangle centroid position, outward unit normal,
   area weight) in a deterministic, stable order.
3. **Compute** per-node forces: normal via the direct-forcing IBM closure (Eq. 19),
   tangential via the friction model (Eq. 21 with Schultz–Grunow Eq. 22, direction
   Eq. 23).
4. **Distribute** the per-node forces onto the `cellSet` with the paper's smoothed
   4-point cosine kernel (Eq. 18), preserving the total force.
5. **Expose** the stable `positions()`/`forces()`/`normals()`/`areas()` sampling
   contract (the S3 FSI seam host) and register `force.<name>` (the existing
   `turbineALSource.C:199-223` precedent).
6. **Compose** via `axialFlowTurbineALSource::createNacelle()` (the same
   `autoPtr`-child pattern as `hub_`/`tower_`), closing the existing null-deref
   additively.

The change is **additive**: with no `nacelle {}`/geometry configured,
`hasNacelle_ == false` and all three `addSup` bodies skip the nacelle block, so the
ALM default is byte-identical.

The change also delivers three supporting assets: (a) **idempotent time-derived
kinematics** (`angleDeg_` as an integral of the omega law, not an accumulator, with
an optional omega override and registry persistence), (b) a **deterministic
geometry pipeline** (`turbinesFoam/geometry/`, gmsh + `makeGeometry.py`) that
produces the nacelle STL, and (c) the **paper-faithful validation case**
(`turbinesFoam/validation/nacelle-asn/`), staged on HPC.

### Work decomposition (delivery forecast)

| Unit | Content | Est. lines |
|------|---------|-----------|
| W1 | Core source: `nacelleSurfaceSampler` + `nacelleSurfaceSource`, `Make/*`, `createNacelle()`, `test_nacelle.py` | ~600–800 |
| W2 | Geometry pipeline: `geometry/` (gmsh + `makeGeometry.py` + metadata + PROVENANCE), `test_nacelle_data.py` | ~400–600 |
| W3 | Kinematics seam: time-derived `angleDeg_` + omega override + registry field | ~100–200 |
| W4 | Validation package: `validation/nacelle-asn/` (case, digitized LES profiles, compare, slurm) | ~400–600 |

Forecast total **~1500–2200 changed lines**, far over the 400-line `single-pr`
review budget. This is a **delivery-shape decision for the orchestrator/user after
`sdd-tasks`** (chained PR slices W1→W2→W3→W4 vs an explicit `size:exception`),
**not pre-decided here** (recorded in the proposal; see §12).

---

## 2. Paper → Code Mapping (the `rules.design` requirement)

The config rule (`openspec/config.yaml` `rules.design`) requires a paper → code
table. The table below maps every equation the source implements to its
class/member with **explicit units, the area-weight entry point, and the sign
convention**. The dimensional chain is resolved first, because every entry depends
on it.

### 2.1 Dimensional chain (resolved unambiguously)

The paper works throughout in **density-divided ("kinematic") form**: in its
momentum equation (Eq. 25) the body-force term `f_l` carries **no** `1/ρ` factor,
unlike every other term. Consequently **`f_n` and `f_τ` are force *per unit area
per unit density*** (dimension m²/s²), and the distributed `f(x)` is force *per
unit volume per unit density* (m/s²). This is exactly the convention of
OpenFOAM's incompressible `fv::option` sources — cf. `turbineALSource::forceField_`
which is dimensioned `dimForce/dimVolume/dimDensity` (= m/s²,
`turbineALSource.C:213`).

| Step | Quantity | Symbol | Units | Where it lives |
|------|----------|--------|-------|----------------|
| 1 | Kinematic traction (per unit area per unit density) | `f_n`, `f_τ` | m²/s² | `nacelleSurfaceSampler::normalForce()`, `tangentialForce()` |
| 2 | Per-node kinematic force (**area weight enters here**) | `F_i = (f_n + f_τ)_i · A_i` | m⁴/s² | `nacelleSurfaceSampler::nodeForce()` |
| 3 | Distributed kinematic body force | `Su[c] = Σ_i F_i · δ_h(x_c − X_i)` | m/s² | `nacelleSurfaceSource::distributeForce()` |
| 4 | OpenFOAM field storage | `force.<name>` | `dimForce/dimVolume/dimDensity` | `nacelleSurfaceSource::forceField_` |
| 5 | Physical force on the body (contract) | `F = ρ_ref · Σ_i F_i` | N | `nacelleSurfaceSampler::forces()` |

**Is `f_n`/`f_τ` a force density or a per-node force?** It is a **traction**
(force per unit area per unit density) at a **surface node**. It becomes a
per-node force only after multiplication by the node's area weight `A_i` (Step 2).
The distributed field is a **body-force density** (Step 3).

**Where does the node area weight enter?** Exactly once, in Step 2:
`F_i = f_i · A_i`. The kernel (Step 3) is **area-agnostic** — it only spreads a
given `F_i`, so it cannot re-introduce an area error.

**How does the kernel preserve total force?** The discrete delta kernel is
volume-normalised (`δ_h = (1/V_c)·φφφ`, Eq. 7/18), which gives it the partition of
unity `Σ_c δ_h(x_c − X_i)·V_c = 1`. Therefore

```
Σ_c Su[c]·V_c = Σ_c Σ_i F_i·δ_h(x_c−X_i)·V_c = Σ_i F_i·(Σ_c δ_h·V_c) = Σ_i F_i
```

i.e. the volume integral of the distributed field equals the sum of the per-node
forces — the spec's *total force preserved* requirement is satisfied **by
construction**, and is asserted by a RED test (`test_nacelle.py` expected-value
check, §9).

**ρ factor.** There is **no ρ in the S1 incompressible path** — the source is
per-unit-density, matching the paper and the existing `cellSetOption` convention.
The compressible `addSup(rho, …)` overload multiplies the per-cell field by the
local `rho` before `eqn +=` (mirroring `actuatorLineElement::addSup(rho,…)` at
`actuatorLineElement.C:1117-1120`), and multiplies the reported total force by the
local `rho` (mirroring `multiplyForceRho`, `actuatorLineElement.C:357-372`). For
the **sampling contract** `forces()` (which must return SI newtons), the sampler
multiplies its per-unit-density result by `rhoRef_` (config key `rho`, default
`1.0`). This key is **distinct** from the AFTAL `rhoRef` key: `turbineALSource::rhoRef_`
is hardcoded `1.0` at construction (`turbineALSource.C:194`) and is **never read
from a dictionary**, whereas `rhoRef` is a compulsory key read only in the
compressible AFTAL `addSup` for coefficient normalisation
(`axialFlowTurbineALSource.C:889`). The nacelle source does **not** read `rhoRef`;
its `rho` key is its own reference density for the SI-newton conversion in
`forces()` and the CSV, and the name is chosen to avoid collision/confusion with
the existing `rhoRef` key.

**Interpolation: point vs cell.** The paper interpolates `u(X)` at the Lagrangian
node from the surrounding background nodes via the **same smoothed kernel** (Eq. 7),
not a first-order point interpolation. We implement the kernel interpolation
exactly (see §2.2 Eq. 7 row). The OpenFOAM `interpolationCellPoint` scheme (used by
`actuatorSurfaceElement::calculateInflowVelocity`, `actuatorSurfaceElement.C:163`)
is **rejected**: its stencil does not match the paper's smoothed kernel support
(5 cells per axis, `|r| ≤ 2.5` — a 5×5×5 = 125-cell stencil in 3D), so
reusing it would silently change the model's force-distribution width — a parameter
the paper singles out as physically important (Sec. 2.2 last paragraph).

**`Δt`.** `mesh_.time().deltaT().value()` (the current time step), read at each
`addSup`. **`h`.** `cbrt(mesh_.V()[cellI])` of the node's containing cell — the
OpenFOAM analogue of `(hx·hy·hz)^(1/3)` for a general polyhedron. The paper states
`h` is insensitive ("different values of h have been tested without noticing any
significant differences", Sec. 2.2), so the cbrt approximation is safe.

**`ũ` (Eq. 20 adaptation).** The paper's `ũ(x) = u^n(x) + rhs^n(x)·Δt` is a
fractional-step *predicted* velocity. In OpenFOAM's PIMPLE loop there is no exposed
`rhs^n`; we approximate `ũ` with the **current iterand velocity** `eqn.psi()` (the
`U` field at the point `addSup` is called). This is a documented, standard
adaptation (the same value `actuatorLineElement` already uses via
`eqn.psi()` at `actuatorLineElement.C:1073`). Flagged as a design note in §12.

### 2.2 Equation → code table

| Paper Eq. | Meaning | Code location | Units / notes |
|-----------|---------|---------------|---------------|
| **Eq. 7** — `u(X) = Σ_{x∈g_x} u(x)·δ_h(x−X)·V(x)` | Smoothed velocity interpolation at a surface node | `nacelleSurfaceSampler::interpolateVelocity(point, Uin)` | Returns m/s. Evaluated as `Σ_c U_c·φ((x_c−X)/h)·φ((y_c−Y)/h)·φ((z_c−Z)/h)` over the 5³-cell stencil (`δ_h·V = φφφ`), normalised by the kernel sum. Used for `ũ` (Eq. 19) and the probe (Eq. 23). |
| **Eq. 8** — `φ(r)` smoothed 4-point cosine, `|r| ≤ 2.5` | Kernel function | `nacelleSurfaceSampler::kernel(r)` (static) | Dimensionless, support `[−2.5, 2.5]` **per axis** → 5 cells per direction (the paper's "closest five cells" refers to this per-direction width; in 3D the full stencil is 5×5×5 = 125 cells). Shared by interpolation (Eq. 7) and distribution (Eq. 18). |
| **Eq. 18** — `f(x) = −Σ f(X)·δ_h(x−X)·A(X)` | Force distribution, surface → background grid | `nacelleSurfaceSource::distributeForce(forceField)` | m/s² per cell. Implemented per node as `Su[c] += F_i·(1/V_c)·φφφ` over the 5×5×5 = 125-cell stencil (`|r| ≤ 2.5` in each of 3 axes); total preserved by partition of unity (§2.1). The **negative sign** is applied in `addSup` (force ON flow = −force ON body). |
| **Eq. 19** — `f_n = h(−u^d + ũ)·e_n/Δt · e_n` | Direct-forcing normal traction | `nacelleSurfaceSampler::normalForce(i, ũ, h, dt)` | m²/s² (per unit area per unit density). `u^d = 0` (stationary). Returns `h·(ũ·e_n)/Δt · e_n`. |
| **Eq. 20** — `ũ(x) = u^n + rhs^n·Δt` | Predicted velocity | `nacelleSurfaceSource::addSup` (`eqn.psi()`) | Adapted to the PIMPLE iterand (§2.1). |
| **Eq. 21** — `f_τ = ½·cf·U²·e_τ` | Tangential traction | `nacelleSurfaceSampler::tangentialForce(i, cf, U, e_tau)` | m²/s². `U` = config `referenceVelocity` (magnitude of incoming streamwise velocity). |
| **Eq. 22** — `cf = 0.37·(log Rex)^(−2.584)` | Schultz–Grunow friction | `nacelleSurfaceSampler::frictionCoefficient(i)` | Dimensionless. `Rex = U·dist_i/ν`; `dist_i` = streamwise distance of node `i` behind the nose; `ν` from `transportProperties` (or config `nu`). Override: config `cf` (constant) replaces the relation. |
| **Eq. 23** — `e_τ = u(X+h·e_n)/|u(X+h·e_n)|` | Tangential direction | `nacelleSurfaceSampler::tangentialDirection(i, Uin)` | Unit vector. Probe `X + h·e_n`; `e_τ = 0` when `|u(probe)| < SMALL` (stagnation guard). |

**Sign convention (documented once, authoritative):**

- The sampler computes `f_n`/`f_τ` with the paper's signs **as written**, giving the
  force **the surface exerts on the flow** (Eq. 19 points along the outward `e_n`,
  opposing the inflow normal component).
- `nacelleSurfaceSource::addSup` applies `Su[c] += −F_i·kernel(...)` to the flow
  (force ON flow), matching `actuatorLineElement::applyForceField`'s
  `forceField[cellI] += −forceVector_·factor` (`actuatorLineElement.C:395`) and the
  paper's Eq. 18 negative sign.
- `nacelleSurfaceSampler::forces()` returns the **reaction** — the force **ON the
  body** — `+ρ_ref·Σ_i (f_n + f_τ)_i·A_i`, in the body frame, in SI newtons. This is
  what a structure solver (S3) would apply back to the body.

---

## 3. Architecture Decisions

### Decision 1: Dedicated `nacelleSurfaceSource` + reusable sampler (vs element API / inline)

**Choice**: A new `cellSetOption`-derived `nacelleSurfaceSource` owning a
`nacelleSurfaceSampler`, registered in the `option` RTS as
`type nacelleSurfaceSource;`.

**Alternatives considered**: (B) nacelle as an `actuatorLineSource` with a new
`nacelleSurfaceElement` type (reuses selection/CSV/MPI wholesale); (C) inline in
`axialFlowTurbineALSource`.

**Rationale**: The nacelle model has no BEM content, so the element API (B) forces
a 2-D surface through a 1-D line-oriented interface (`createElements` interpolates
a line, `actuatorLineSource.C:131-374`) — semantic abuse that piles overrides onto
the BEM-shaped API. Inline (C) bloats the turbine class and cannot host the
standalone rotor-less validation case (which the paper itself runs, Sec. 4.1) or the
S3 FSI seam. (A) maps 1:1 to Sec. 2.2, gives the validation case a natural home,
gives S3 a contract-stable object, and fixes the null-deref additively. Effort is
comparable to (B) but with no per-line wrestling.

### Decision 2: Triangle centroids as the node set (vs vertices)

**Choice**: One sample per **triangle centroid** (position = `faceCentres()`,
normal = `faceNormals()`, area = `magFaceAreas()` of the `triSurface`), in the
surface's own face order.

**Alternatives considered**: Vertex-based samples with angle-weighted vertex normals
and `A_v = Σ(adjacent triangle area)/3`.

**Rationale**: The paper distributes from "actuator surface grid cells" with area
`A(X)` being "the area of the actuator surface grid cell" (Eq. 18 text), and
Sec. 4.1 specifies **2652 surface triangular cells** — a triangle count, not a
vertex count. Centroids give a 1:1 node↔triangle mapping with **unambiguous** area
and outward normal (no averaging), and the "2652 triangles" target maps directly.
Vertex samples would need normal/area averaging, introducing a scheme-dependent
definition and fewer samples. Stable ordering = `triSurface` face order, which is
deterministic for a fixed input STL.

### Decision 3: Smoothed cosine kernel for BOTH interpolation and distribution (vs `interpolationCellPoint`)

**Choice**: Implement the paper's φ(r) (Eq. 8) once as a static helper and use it
for velocity interpolation (Eq. 7) **and** force distribution (Eq. 18).

**Alternatives considered**: Reuse OpenFOAM `interpolationCellPoint` for velocity
(as `actuatorSurfaceElement` does).

**Rationale**: The paper uses the **same** smoothed kernel in Eqs. 7 and 18; its
5-cell width is a physically significant model parameter (Sec. 2.2 last paragraph
discusses the distribution width explicitly). `interpolationCellPoint` is a
first-order cell-point scheme with a different stencil — reusing it would silently
change the effective force width. One kernel implementation serves both paths and
is cheap (separable, support |r| ≤ 2.5).

### Decision 4: Omega override = registry `uniformDimensionedScalarField` (vs Function1)

**Choice**: An optional registry `uniformDimensionedScalarField` (config key
`omegaOverrideField`, default unset) that `turbineALSource::updateTSROmega()` reads
in place of the TSR law.

**Alternatives considered**: A generic `Function1<scalar>` for `omega(t)`.

**Rationale**: No `Function1` hook exists in `turbinesFoam` today (exploration §3),
and the S3 adapter writes a **scalar field**, not a Function1. The
`fsiOmega/preciceOmega` precedent is exactly a Function1 that wraps a
`uniformDimensionedScalarField` "omega" in the registry
(`preciceOmega.C:81-144`) — the **field is the seam**, the Function1 is just the
motion-solver's access shim. For the turbine, reading the field directly is the
simplest, most faithful seam: it is the exact shape the adapter's `globalData`
ReadWrite already exchanges (`modules/generic/Generic.C:29-66`, exploration §3/§4),
and where `Adapter.C:935` will add checkpoint coverage. A generic Function1 would
add an unused abstraction and a new dependency with no S3 benefit. When unset, the
existing TSR law runs byte-identical.

### Decision 5: Time-derived `angleDeg_` as an integral (vs persisted accumulator)

**Choice**: `angleDeg_` becomes a pure function of `(t0, angle0, t)` — `ω0·(t−t0)`
for constant TSR, the closed-form separable integral for the `tsrAmplitude`
oscillation — with `angle0`/`t0` seeded from the persisted
`uniformDimensionedScalarField` on restart.

**Alternatives considered**: (a) keep `angleDeg_ += ω·dt` but read the persisted
value on restart (accumulator, merely restart-safe); (b) leave the accumulator
untouched.

**Rationale**: The spec (§time-derived-kinematics) requires the azimuth to be a
**pure function of time and initial state**, not an accumulator — the accumulator
cannot be made idempotent under preCICE rollback (a rollback to time `t` needs
`angleDeg_(t)` exactly, which only a pure function of `t` provides). The closed form
exists (§5) and is separable. (a) is rejected as it does not satisfy the
rollback-idempotency requirement; (b) leaves the known restart bug. The default path
stays byte-identical because for `tsrAmplitude == 0` the integral degenerates to
`ω0·(t−t0)` and the offset rotation stays a separate geometric transform (§5).

### Decision 6: Shared `turbinesFoam/geometry/` pipeline (vs validation-local geometry)

**Choice**: A top-level `turbinesFoam/geometry/` tree (gmsh `.geo` + `makeGeometry.py`
→ per-component STL + metadata JSON + PROVENANCE).

**Alternatives considered**: Geometry under `validation/nacelle-asn/data/geometry/`
only.

**Rationale**: The pipeline is S2's input (blade STLs) as well as S1's; a
validation-local home would be re-factored out in S2. The layout (per-component STL,
metadata schema reserving blade radial-station/chord-fraction fields) is designed to
accept blades with no rework. `makeGeometry.py --check` mirrors the established
`makeElementData.py` stale-detection pattern.

### Decision 7: Validation turbulence closure — LES WALE headline (vs dynamic SGS / URANS)

**Choice**: pimpleFoam + LES with **WALE** as the headline closure; URANS k-ω SST as
an optional, documented smoke fallback (weaker claim).

**Alternatives considered**: reproduce the paper's dynamic SGS model (not available
in standard OpenFOAM); Smagorinsky; URANS-only.

**Rationale**: The paper validates against wall-resolved LES with a dynamic SGS
model (Sec. 4.1, Eq. 25's `τ_ij`) that standard OpenFOAM does not ship. WALE is
deterministic (no model-coefficient averaging), is the standard OpenFOAM choice for
bluff-body wake LES, and is the closest comparable closure. The adaptation is
documented. Per-station acceptance (coarse ≠ medium in the paper) is enforced so
coarse-grid agreement is not over-promised.

### Decision 8: `cf` — Schultz–Grunow default + constant override

**Choice**: `cfModel schultzGrunow` (Eq. 22) by default, with an optional
user-supplied constant `cf` (key `cf`) that overrides it node-by-node.

**Alternatives considered**: Schultz–Grunow only.

**Rationale**: The constant override is cheap and directly serves the validation
case's drag-coefficient comparison; the paper itself notes the zero-pressure-gradient
relation is invalid in the hemisphere nose region, so a calibration knob is
warranted (documented).

---

## 4. `nacelleSurfaceSource` + `nacelleSurfaceSampler` Design

### 4.1 `nacelleSurfaceSampler` (the reusable sampling object)

Files: `turbinesFoam/src/fvOptions/nacelleSurface/nacelleSurfaceSampler.{H,C}`.

```
class nacelleSurfaceSampler
{
    // Owned geometry
    triSurface surface_;            // triSurface::New(geometryPath)
    List<point> positions_;         // triangle centroids, face order
    List<vector> normals_;          // outward unit face normals
    List<scalar> areas_;            // magFaceAreas()

    // Per-node force ON the body, SI newtons, body frame (the contract)
    List<vector> forces_;           // rhoRef_ * (f_n + f_tau)_i * A_i  [N]

    // Body frame transform (positions()/forces() contract)
    vector bodyOrigin_;             // default (0 0 0)
    tensor bodyToGlobal_;           // optional rotation; default identity

    // Reference state
    scalar referenceVelocity_;      // U (m/s)
    scalar nu_;                     // kinematic viscosity (m^2/s)
    scalar cfOverride_;             // -1 = use Schultz-Grunow
    scalar rhoRef_;                 // for forces() in N

    // Nose (most-upstream point, streamwise projection)
    scalar noseStreamwise_;

public:
    nacelleSurfaceSampler(const dictionary& dict, const fvMesh& mesh);
    const List<point>& positions() const;
    const List<vector>& forces() const;     // SI N, body frame, on-body
    const List<vector>& normals() const;
    const List<scalar>& areas() const;

    // Force model (per-node, per unit density), called from the source each step
    vector normalForce(label i, const vector& uTilde, scalar h, scalar dt) const;
    vector tangentialForce(label i, const vector& uProbe, scalar cf) const;
    scalar frictionCoefficient(label i) const;      // Eq. 22 or override
    vector tangentialDirection(label i, const volVectorField& U) const; // Eq. 23

    // Kernel + interpolation (Eqs. 7, 8)
    static scalar kernel(scalar r);                 // phi(r)
    vector interpolateVelocity(const point& X, const volVectorField& U) const;
};
```

Constructor: `triSurface::New(geometryPath)` (auto-detects ASCII/binary,
`triSurfaceNew.C:86-97`); `FatalError` on missing/empty/unparseable STL (spec
requirement). Then `positions_ = surface_.faceCentres()`,
`normals_ = surface_.faceNormals()`, `areas_ = surface_.magFaceAreas()`. The body
frame defaults to identity (global frame); optional `bodyOrigin`/`bodyAxis` config
keys rotate positions/normals into a body frame (used by S3 when the nacelle is
offset/rotated relative to the mesh).

`forces()` returns `const List<vector>&` over the per-node forces **on the body**
already converted to SI newtons: `forces_[i] = rhoRef_ · (f_n + f_τ)_i · A_i` (body
frame, force-on-body). The source re-populates `forces_` each `addSup` before this
is read. The **per-unit-density** node force `(f_n + f_τ)_i · A_i` (m⁴/s²) used by
the distribution step (§4.2) is kept separate from the SI contract list — the SI
list is what `forces()` returns, and it is **not** the quantity that is distributed
onto the grid.

### 4.2 `nacelleSurfaceSource` (the `fv::option`)

Files: `turbinesFoam/src/fvOptions/nacelleSurface/nacelleSurfaceSource.{H,C}`.

```
namespace Foam { namespace fv {
    defineTypeNameAndDebug(nacelleSurfaceSource, 0);
    addToRunTimeSelectionTable(option, nacelleSurfaceSource, dictionary);
}}

class nacelleSurfaceSource : public cellSetOption
{
    nacelleSurfaceSampler sampler_;
    volVectorField forceField_;        // "force." + name_, AUTO_WRITE
    vector force_;                     // total force on body (per unit density)
    bool writePerf_;  OFstream* outputFile_;
    bool writeNodePerf_; OFstream* nodeFile_;

    void distributeForce(volVectorField& ff);      // Eq. 18
    void writePerf();                              // total CSV
public:
    nacelleSurfaceSource(const word& name, const word& modelType,
                         const dictionary& dict, const fvMesh& mesh);
    virtual void addSup(fvMatrix<vector>& eqn, const label fieldI) override;
    virtual void addSup(const volScalarField& rho, fvMatrix<vector>& eqn,
                        const label fieldI) override;
    virtual void addSup(fvMatrix<scalar>& eqn, const label fieldI) override;
    const nacelleSurfaceSampler& sampler() const;
    const vector& force() const;
    const volVectorField& forceField() const;
};
```

`addSup` (incompressible momentum) sequence, per time step:

1. `const volVectorField& U = eqn.psi();`
2. Zero `forceField_`, `force_`.
3. For each node `i` (replicated on every rank, §10): `dt = time.deltaT().value()`;
   `ũ = sampler_.interpolateVelocity(X_i, U)` (kernel sum, `returnReduce(..., sumOp)`, §10);
   `h = cbrt(V[cell])` resolved via `findCell` + `reduce(minOp)` sentinel (§10);
   `f_n = sampler_.normalForce(i, ũ, h, dt)`; `cf = sampler_.frictionCoefficient(i)`;
   `e_τ = sampler_.tangentialDirection(i, U)`;
   `f_τ = sampler_.tangentialForce(i, cf, e_τ)` (Eq. 21);
   `F_i = (f_n + f_τ)·A_i` (per unit density); `sampler_.forces_[i] = rhoRef_·F_i` (SI N, contract).
4. `distributeForce(forceField_)` — every rank loops over **all** nodes and applies
   the kernel to its **local** cells only (§10); per cell
   `forceField_[c] += −F_i·(1/V_c)·φφφ` over the node's 5×5×5 = 125-cell stencil
   (Eq. 18, sign §2.2).
5. `force_ = Σ_i F_i` (reduce `sumOp<vector>` across ranks).
6. Reset `forceField_.dimensions()` to `eqn.dimensions()/dimVolume` if needed
   (mirrors `actuatorLineSource.C:713-717`); `eqn += forceField_`.
7. `writePerf()` on master.

The compressible overload additionally multiplies `forceField_` and `force_` by
`rho` (per §2.1). The scalar-turbulence overload is a **no-op** (the nacelle model
injects no TKE — unlike `actuatorLineElement::addTurbulence`, the paper's model has
no turbulence source term); it is present for interface completeness so that AFTAL's
`nacelle_->addSup(eqn, fieldI)` (`axialFlowTurbineALSource.C:944-948`) compiles and
runs without effect. Documented in §12 as a deliberate deviation from the
element path.

### 4.3 Config dictionary keys

```
type            nacelleSurfaceSource;
active          true;
nacelleSurfaceSourceCoeffs
{
    geometry            "geometry/nacelle.stl";   // required (triSurface path)
    selectionMode       cellSet;                  // inherited (cellSetOption)
    cellSet             nacelleCells;
    fieldNames          (U);                      // inherited

    referenceVelocity   1.0;                      // U (m/s), Eq. 21/22
    rho                 1.0;                      // reference density (SI conversion in forces()/CSV); distinct from AFTAL rhoRef
    nu                  -1.0;                     // if >=0 use it; else transportProperties.nu

    cfModel             schultzGrunow;            // default; | constant
    cf                  -1.0;                     // constant override when cfModel constant (or set for calibration)

    bodyOrigin          (0 0 0);                  // optional, sampling contract
    bodyAxis            (1 0 0);                  // optional

    writeForceField     true;                     // register force.<name> (AUTO_WRITE)
    writePerf           true;                     // total-force CSV
    writeNodePerf       false;                    // per-node CSV (opt-in)
}
```

### 4.4 CSV output format

Total CSV at `postProcessing/nacelle/<name>.csv` (mirrors the
`postProcessing/turbines`/`actuatorLines` directory convention,
`actuatorLineSource.C:104-128`):

```
time,fx,fy,fz,f_n_mag,f_tau_mag,cd
```

- `fx,fy,fz` — total force **on the body** (N, i.e. `rhoRef_·force_`).
- `f_n_mag, f_tau_mag` — `|Σ f_n A|`, `|Σ f_τ A|` (N), split for the validation
  diagnostic.
- `cd` — `|F|/(0.5·rhoRef_·U²·πR²)` with `R` = config `referenceArea` radius (or
  `referenceArea` scalar directly). Default reference area = `πR²` for a config
  radius `R`; for the standalone case `R` is the nacelle radius.

Per-node CSV (when `writeNodePerf true`) at `postProcessing/nacelle/<name>_nodes.csv`:

```
time,node,x,y,z,nx,ny,nz,fx,fy,fz,area
```

### 4.5 `Make/files` + `Make/options`

`turbinesFoam/src/Make/files` — add two lines (after the actuator lines):

```
fvOptions/nacelleSurface/nacelleSurfaceSampler.C
fvOptions/nacelleSurface/nacelleSurfaceSource.C
```

`turbinesFoam/src/Make/options` — add the surfMesh include and link:

```
EXE_INC = ... -I$(LIB_SRC)/surfMesh/lnInclude
LIB_LIBS = ... -lsurfMesh
```

`triSurface`/`triSurface::New` live in **libsurfMesh** (`src/surfMesh/Make/files`);
the `triSurfaceSearch` utilities are already in `-lmeshTools`. **Symbol hygiene is a
task-level verification item**: build with `./Allwmake` and confirm `ldd -r` reports
no undefined symbols and no duplicate-symbol link error between `-lsurfMesh` and
`-lmeshTools` (the proposal's risk is tracked here; the two libraries provide
disjoint symbols, but this must be proven on the toolchain, not assumed).

---

## 5. Kinematics Design (time-derived `angleDeg_`)

Files: `turbinesFoam/src/fvOptions/turbineALSource/turbineALSource.{H,C}`.

### 5.1 State and call sites

Replace the accumulator at `turbineALSource.C:152-160` (`rotate()`). The new state
added to `turbineALSource.H`:

```
scalar t0_;          // start time of the current azimuth interval
scalar angle0_;      // azimuth (deg) at t0_
bool hasOmegaOverride_;  word omegaOverrideField_;
autoPtr<uniformDimensionedScalarField> angleDegField_;  // "angleDeg.<name>"
```

`updateTSROmega()` (`turbineALSource.C:143-149`) changes to: if
`hasOmegaOverride_`, read `omega_` from the registry field
`mesh_.time().lookupObject<uniformDimensionedScalarField>(omegaOverrideField_)`
and `tipSpeedRatio_ = omega_*rotorRadius_/mag(freeStreamVelocity_)`; else the
existing TSR law (unchanged). `read()` (`turbineALSource.C:302-340`) reads the two
new optional keys: `omegaOverrideField` and `tsrAmplitude`/`tsrPhase` (already
there, `:316-317`).

`rotate()` (`turbineALSource.C:152-160`) becomes (azimuth stored in **degrees**;
`rotate(scalar)` and the omega law are in **radians/rad·s⁻¹**):

```cpp
void rotate()
{
    scalar t = time_.value();
    scalar anglePrev = angleDeg_;              // degrees, last applied azimuth
    angleDeg_ = azimuth(t);                    // degrees, pure function of (t0, angle0, t)
    scalar deltaRad = degToRad(angleDeg_ - anglePrev);   // radians
    rotate(deltaRad);                          // rotate blades/hub by delta (radians)
    // (rotate(scalar) is defined per turbine type; base keeps no-op)
    lastRotationTime_ = t;
    updateTSROmega();
    if (angleDegField_.valid()) { angleDegField_->value() = angleDeg_; angleDegField_->write(); }
}
```

The delta `angleDeg_ − anglePrev` is computed **before** overwriting `angleDeg_`, so
no separate "last-applied" symbol is needed. `azimuth(t)` computes internally in
radians and returns degrees:

- **Constant TSR** (`tsrAmplitude_ == 0`): `ω0 = meanTSR_·|U∞|/R` [rad/s];
  `azimuth(t) = angle0_ + radToDeg(ω0·(t − t0_))` [deg] (mod 360).
- **`tsrAmplitude` oscillation**: `ω(θ) = ω0·(1 + m·cos(nB·(θ − φ)))` [rad/s] with
  `ω0 = meanTSR_·|U∞|/R`, `m = tsrAmplitude_/meanTSR_`, `nB = nBlades_`,
  `φ = tsrPhase_`; `θ` in radians. Separable: `dθ/dt = ω(θ)` →
  `∫ dθ/(1 + m·cos(nB(θ−φ))) = ω0·(t−t0)` (both sides dimensionless/rad·s⁻¹·s = rad).
  With `u = nB(θ−φ)`, the closed form is
  `(2/√(1−m²))·atan(√((1−m)/(1+m))·tan(u/2)) = nB·ω0·(t−t0) + C`, inverted for
  `θ(t)` [rad] with `C` fixed by `θ(t0) = degToRad(angle0_)`. Branch/`atan`
  unwrapping keeps `θ(t)` monotonic and continuous; `azimuth(t) = radToDeg(θ(t))`
  [deg] reduced mod 360.

**The exact inversion and its floating-point agreement with the existing
accumulator for the phaseVI cases is a task-level verification item** (§12): a RED
test must confirm the new `angle_deg` CSV column matches the baseline accumulator
"to floating point" (spec acceptance), not bit-for-bit (the accumulator sums `ω·dt`
per step, which differs from a single closed-form evaluation by floating-point
rounding).

**`azimuthalOffset` stays a separate geometric rotation.** The constructor's
`rotate(degToRad(azimuthalOffset))` (`axialFlowTurbineALSource.C:616-617`) rotates
the physical blades/hub but does **not** touch `angleDeg_`; the time-derived law
reproduces this exactly (`angle0_ = 0` at `t0_ = startTime` for fresh runs). The
existing `time_.value() != lastRotationTime_` guard in the three AFTAL `addSup`
overloads (`axialFlowTurbineALSource.C:726-729, :820-823, :915-918`) is **unchanged**
— it only decides *when* `rotate()` runs; `rotate()` is now idempotent.

### 5.2 Registry persistence and restart

`angleDegField_` is a `uniformDimensionedScalarField` named `angleDeg.<name>`,
dimension `dimless`, units **degrees**, `IOobject::AUTO_WRITE` (so it lands in each
time directory), registered in the mesh (Time) registry. On construction:

- If the Time/mesh registry already contains the field (restart via
  `startFrom latestTime` reads it from the latest time directory), seed
  `angle0_ = field.value()`, `t0_ = time_.value()`.
- Else create it at `angle0_ = 0`, `t0_ = startTime`, `IOobject::NO_READ`.

The **exact read-back mode** (`MUST_READ` vs explicit lookup for the restart path,
and which registry — `mesh_` vs `Time` — hosts the field so the adapter's
`globalData` can find it) is a task-level verification item against the OpenFOAM
toolchain and the adapter's `Generic.C:29-66` convention (§12).

The omega override field (when used) is likewise registered
(`uniformDimensionedScalarField`, `IOobject::AUTO_WRITE`, dimension
`dimensionSet(0,0,-1,0,0,0,0)` rad/s), named `omega.<name>`, matching the
`fsiOmega` "omega" field the adapter already exchanges.

`angleDeg()` accessor: `scalar angleDeg() const { return angleDeg_; }` (degrees).

### 5.3 Byte-identical default gate

With no `omegaOverrideField`, `tsrAmplitude_ == 0`, and no restart, the
time-derived `ω0·(t−t0)` reproduces the accumulator's `angle_deg` column **to
floating point** (the only observable output is the CSV `angle_deg` column at
`turbineALSource.C:273` and the debug print at `:171`). The proposal's
"byte-identical" success wording is stricter than the spec's normative
"to floating point" — the design adopts the **spec** acceptance and records the
tension in §12.

---

## 6. AFTAL Wiring (`createNacelle`)

Files: `turbinesFoam/src/fvOptions/axialFlowTurbineALSource/axialFlowTurbineALSource.{H,C}`.

`nacelle_` changes type from `autoPtr<actuatorLineSource>` to
`autoPtr<nacelleSurfaceSource>` (`axialFlowTurbineALSource.H:76`; `#include
"nacelleSurfaceSource.H"`). `createNacelle()` (`axialFlowTurbineALSource.C:471-474`)
is implemented to mirror `createHub()`/`createTower()` (`:294-380`, `:383-468`):

```cpp
void Foam::fv::axialFlowTurbineALSource::createNacelle()
{
    dictionary nacelleSubDict = nacelleDict_;
    nacelleSubDict.add("fieldNames", coeffs_.lookup("fieldNames"));
    nacelleSubDict.add("selectionMode", coeffs_.lookup("selectionMode"));
    nacelleSubDict.add("cellSet", coeffs_.lookup("cellSet"));
    nacelleSubDict.add("referenceVelocity", mag(freeStreamVelocity_));
    nacelleSubDict.lookupOrAddDefault("writeForceField", false);

    dictionary dict;
    dict.add("nacelleSurfaceSourceCoeffs", nacelleSubDict);
    dict.add("type", "nacelleSurfaceSource");
    dict.add("active", dict_.lookup("active"));

    nacelle_.reset(new nacelleSurfaceSource(name_ + ".nacelle",
                   "nacelleSurfaceSource", dict, mesh_));
}
```

- **Static nacelle**: `rotate(scalar)` (`:643-662`) and
  `rotateBladesAndHub` (`:664-696`) touch only `blades_` and `hub_` — the nacelle is
  **not** rotated, tilted (`tilt`, `:698-706`), or yawed (`yaw`, `:708-716`). No
  change needed; verified against `axialFlowTurbineALSource.H`'s member set (no
  nacelle in `rotateBladesAndHub`).
- **Null-deref closed additively**: the three `addSup` blocks
  (`:780-789`, `:874-883`, `:944-948`) already guard on `hasNacelle_`; they now call
  a valid `nacelle_`. With `hasNacelle_ == false` they are skipped — byte-identical.
- **`includeNacelleDrag_`/`includeInTotalDrag` semantics preserved**
  (`:989-993`): `nacelle_->forceField()` is always added to `forceField_`; the total
  `force_` (and thus `dragCoefficient_`) includes the nacelle only when
  `includeNacelleDrag_` is true. `createNacelle` does not alter this.
- **`FatalError` on missing/invalid STL**: the sampler constructor raises
  `FatalError` (§4.1), satisfying the spec; no silent fallback.

`read()` (`:958-1013`) is unchanged (the `nacelle {}` subdict detection already
exists at `:984-988`).

---

## 7. Geometry Pipeline Design (`turbinesFoam/geometry/`)

```
turbinesFoam/geometry/
├── README.md             # usage, component list, S2 deferral note
├── PROVENANCE.md         # source refs (paper Sec. 4.1 + Fig. 3), generator version, input sha256
├── src/
│   ├── nacelle.geo       # gmsh: hemisphere (upstream) + cylinder, radius R
│   └── makeGeometry.py   # CLI: generate | --check | --component
├── stl/
│   └── nacelle.stl       # committed binary STL (~2652 triangles target)
└── metadata/
    └── nacelle.json      # per-node normals + areas; schema reserves blade fields
```

**gmsh `.geo` approach.** A hemisphere (radius `R`, facing upstream) capped by a
cylinder (radius `R`), meshed with `Mesh.CharacteristicLengthFactor` chosen to hit
the paper's **~2652 triangles**. The generator parameterises `R`, `L` (cylinder
length), and a mesh-resolution seed. **The paper's Sec. 4.1 text gives `R` but not
the cylinder length `L`** — this is a **data-sourcing item** resolved from Fig. 3
(the nacelle schematic) with a documented assumption and provenance (see §12; the
task digitizes/measures Fig. 3, defaults to a documented aspect ratio if Fig. 3 is
ambiguous, and records it in `PROVENANCE.md`).

**`makeGeometry.py` CLI.**

```
makeGeometry.py                 # generate all components → stl/ + metadata/
makeGeometry.py --check         # regenerate to temp, sha256-compare; exit non-zero on mismatch; non-destructive
makeGeometry.py --component nacelle   # S1 component (future: blade0..2)
makeGeometry.py --gmsh ~/venv/bin/gmsh
```

Determinism: gmsh is pinned (version recorded in PROVENANCE) and invoked with fixed
options; `--check` regenerates and compares the committed STL's sha256 (mirroring
`makeElementData.py`'s stale detection, `validation/phaseVI/scripts/makeElementData.py`).
`--check` **never** modifies committed artifacts.

**Metadata JSON schema** (per component):

```json
{
  "component": "nacelle",
  "format_version": 1,
  "generator": {"script": "src/nacelle.geo", "gmsh_version": "4.x.y"},
  "input_sha256": "<sha256 of nacelle.geo + parameters>",
  "units": "m",
  "n_triangles": 2652,
  "nodes": [
    {"index": 0, "normal": [nx, ny, nz], "area": 3.14e-4},
    "..."
  ],
  "_reserved": {
    "blade": {"radial_station": null, "chord_fraction": null}
  }
}
```

`PROVENANCE.md` records: the paper's Sec. 4.1/Fig. 3 source for the nacelle, the
MEXICO rotor tables as the (deferred) blade source, the generator version, and the
sha256 of the `.geo` inputs. Blade STL generation is **not** performed in S1
(layout/schema reserve it for S2).

---

## 8. Validation Case Design (`turbinesFoam/validation/nacelle-asn/`)

The paper-faithful periodic-nacelle benchmark anchors the nacelle ASM rotor-less
against the paper's wall-resolved-LES reference (Sec. 4.1). It consumes the
pipeline's `geometry/stl/nacelle.stl` and mirrors the Phase VI package pattern:
`config/case.yaml` single source of truth → `tools/generate_case.py` (non-destructive
`--check`), a compare script, slurm `stage0`/`production`, a committed `case/`
skeleton, gitignored `runs/`/`results/`, and pure-Python pytest coverage.

**Canonical parameterization (Re = 1000).** `U∞ = 1 m/s`, `R = 1 m`,
`ν = 1e-3 m²/s` → Re = `U∞·R/ν = 1000` (the paper's Reynolds number is based on the
cylinder radius `R`). The nacelle is a hemisphere (upstream) + cylinder (downstream)
of radius `R`. The cylinder length `L` is the §12 data-sourcing item (resolved from
Fig. 3 with provenance, defaulting to a documented aspect ratio if Fig. 3 is
ambiguous). The standalone `nacelleSurfaceSource` `fvOptions` entry points `geometry`
at the pipeline STL. All profiles are normalised by `U∞`/`R` in the compare script,
so the exact dimensional choice is convenience only.

**Domain and boundary conditions.** `30R × 20R × 20R`, with the downstream end of the
nacelle at the streamwise origin. Periodic in the streamwise direction (`cyclic`),
free-slip in the crosswise directions (`symmetry`). The background mesh is a uniform
blockMesh; the nacelle is represented **only** by the `nacelleSurfaceSource` (no
body-fitted mesh) — the ASM distributes force onto the background grid.

**Grids.** Two run grids plus a reference-only grid (never generated):

| Grid | Nx×Ny×Nz | Δx | Δy = Δz | Δt | ~cells |
|------|-----------|----|---------|-----|--------|
| Coarse | 153×80×80 | R/2.5 | R/5 | 0.1 R/U | ~1M |
| Medium | 115×151×151 | R/3.75 | R/7.5 | 0.1 R/U | ~2.6M |
| Reference (wall-resolved LES) | 502×348×348 | R/8 | R/33 | 0.01 R/U | ~60M (not generated) |

The surface is the pipeline's ~2652-triangle nacelle STL (the paper's triangle count).

**Numerics.** `pimpleFoam` + LES with the **WALE** subgrid model — the paper's
dynamic SGS model (Eq. 25's `τ_ij`) is not in standard OpenFOAM, and the adaptation
is documented in the case README. Second-order central differencing, CrankNicolson
1.0 time scheme. A URANS k-ω SST configuration is provided as an optional,
documented smoke fallback (a weaker claim), not the headline.

**Run length / statistics.** One flow-through time `T_ft = Lx/U∞ = 30R/U = 30 s`.
Design default: transient wash-out `2·T_ft` (60 s) discarded, then time-averaging over
`5·T_ft` (150 s) at Δt = 0.1 s (~1500 samples). The averaging window and discard are
`config/case.yaml` knobs. `force.<nacelle>` (the registered AUTO_WRITE
`volVectorField`) is time-averaged for the drag coefficient.

**Metrics and acceptance.** Time-averaged `⟨u⟩(z)` and `k(z)` vertical profiles at
`x = 1R, 3R, 5R, 7R` (+ a `10R` stretch) through the axis, and the drag coefficient
`CD = F_drag / (0.5·ρ·U∞²·πR²)` (freestream + frontal area `πR²`, the paper's
definition). Acceptance is **per-station/per-grid**: the medium grid must agree at all
stations; the coarse grid only at `1R` and the far wake (the paper reports coarse
deficits too large at 3R–7R — do not over-promise). The paper's permeable-disk
`CD = 0.48` is a **datum, not a target**.

**Digitization + PROVENANCE.** Fig. 5 (`⟨u⟩`) and Fig. 6 (`k`) profiles are digitized
from the arXiv v4 images into per-station CSVs under `data/reference/`, with a
`PROVENANCE.md` recording the source figure, the digitization method, and a two-source
cross-check (two independent digitizations compared to within a stated tolerance). The
reference is documented as the paper's 502×348×348 wall-resolved LES with a dynamic
SGS model unavailable in standard OpenFOAM.

**Slurm staging.** `scripts/slurm/stage0.slurm` (dev partition) runs `blockMesh`,
`checkMesh`, and a short stability run — mesh generation and sanity now.
`scripts/slurm/production.slurm` (long queue) runs the full averaging — **prepared
only, never submitted before explicit authorization**. Nothing is launched on the
long queue in S1.

**Spec requirement mapping.**

| `nacelle-validation-case` requirement | Where covered |
|---|---|
| Paper-faithful geometry (30R×20R×20R, periodic + free-slip, Re=1000, ~2652 triangles, consumes pipeline STL) | §8 Domain/parameterization/surface |
| Coarse 153×80×80 and medium 115×151×151 grids; 502×348×348 reference-only | §8 Grids |
| Digitized wall-resolved-LES reference + provenance + dynamic-SGS limitation | §8 Digitization + PROVENANCE |
| Per-station acceptance with coarse/medium differentiation | §8 Metrics and acceptance |
| Metric definitions (`⟨u⟩`/`k` at 1R/3R/5R/7R + 10R, CD; permeable-disk datum not target) | §8 Metrics and acceptance |
| Turbulence closure adaptation (WALE headline, URANS fallback) | §8 Numerics |
| Staged HPC (dev partition now, long queue after authorization) | §8 Slurm staging |
| Case-package tooling mirroring phaseVI (`config/case.yaml` → `generate_case.py --check`, compare, slurm, skeleton, gitignored `runs/`/`results/`, pytest, `pimpleFoam`) | §8 purpose + §13 File Changes |
| Case documentation + attribution (case README + root README/CHANGELOG) | §8 Numerics/purpose + §13 File Changes |

---

## 9. Test Design

| File | Kind | What it verifies |
|------|------|------------------|
| `tests/test_nacelle.py` | Integration (solver-driven, skipped without OpenFOAM via `tests/conftest.py`) | A standalone `nacelleSurfaceSource` case runs rotor-less and writes the force CSV. Includes a **Python expected-value check**: a known (uniform) velocity field fed to a simple surface → the expected normal force `Σ h·U/Δt·A_i` (per §2.1) within tolerance; asserts **total-force preservation** (Σ cell force·V == Σ node force). A **parallel case** (`mpirun -np 2`) exercises node→cell MPI resolution. |
| `tests/test_nacelle_data.py` | Pure-Python (CI-safe, no OpenFOAM) | `makeGeometry.py --check` regenerates the committed nacelle STL (sha256 match, mirroring `GEOMETRY_SHA256` in `test_phasevi_data.py:34-36`); metadata JSON schema present (normals/areas per node, `_reserved.blade` fields); `PROVENANCE.md` present with source refs + input sha256. |
| `tests/test_nacelle_compare.py` (recommended, mirrors `test_phasevi_compare.py`) | Pure-Python | The validation compare script loads the digitized reference profiles and computes ⟨u⟩/k/CD metrics without a solver. |
| Regression gates | Existing suite unchanged | `test_libs` (gates the `-lsurfMesh` link change), `test_al`, `test_aftal`, `test_aftal_asm`, `test_cftal` — the ALM default path stays byte-identical. |

The expected-value check makes the nacelle force math (Eq. 19 direct-forcing, Eq. 21
friction, Eq. 18 distribution) verifiable despite there being **no C++ unit
framework** in the repo — the integration CSV plus the analytic Python expectation
replaces the missing C++ tests.

---

## 10. MPI Design

The distribution is **replicated-node / local-cell**: every rank holds the full,
identical node list (positions/normals/areas from the deterministic `triSurface`
read, and the per-node force `F_i` computed identically everywhere), and every rank
loops over **all** nodes applying the kernel to its **local** cells only. This is the
same shape as `actuatorSurfaceElement::applyForceField`
(`actuatorSurfaceElement.C:117-150`) and `actuatorLineElement::applyForceField`
(`actuatorLineElement.C:375-403`), which loop `forAll(mesh_.cells(), cellI)` over
local cells and test every source against the local cell distance — so each receiving
cell accumulates every in-range node contribution, and is written **exactly once**, by
the rank that owns it. The previous owner-only design was wrong: a node's 5×5×5
stencil spans cells owned by several ranks, so owner-only distribution silently drops
contributions to non-owner cells and breaks total-force preservation.

1. **Node geometry + force replication.** `positions_`/`normals_`/`areas_` are
   identical on all ranks (same `triSurface` file). Per-node velocity interpolation is
   a **kernel sum**: each rank sums `U_c·φφφ` over its local cells in the stencil, then
   `returnReduce(partial, sumOp<vector>())` yields the global `ũ(X_i)` — the `sumOp`
   analogue of `actuatorSurfaceElement::calculateInflowVelocity`'s
   `reduce(sampleVelocity, minOp<vector>())` (`actuatorSurfaceElement.C:181-182`),
   where `minOp` works only because `interpolationCellPoint` returns a single-cell
   value. `F_i` is then computed identically on every rank.
2. **Reachability.** `h` uses the `findCell` + `reduce(minOp)` sentinel of
   `actuatorSurfaceElement::calcProjectionEpsilon` (`:73-92`); if a node is found on no
   rank, `FatalErrorInFunction << "nacelle sample " << i << " not found in mesh"` — the
   spec's *unreachable sample* scenario.
3. **Distribution.** Every rank applies `forceField_[c] += −F_i·(1/V_c)·φφφ` for every
   node `i` over its **local** cells within the node's kernel support, using a
   `boundBox` prefilter (surface box inflated by `2.5·h`) mirroring the `chordBox`
   prefilter (`actuatorSurfaceElement.C:117-122`). Each cell is touched once, by its
   owner rank; every node contributes to every cell in its stencil regardless of rank
   boundary.
4. **Total force.** `returnReduce(force_, sumOp<vector>())` for the reported total.
5. **Output.** `forceField_` is a normal `volVectorField` (each rank writes its own
   local cells); the CSV is written on `Pstream::master()` (existing convention).

**Parallel acceptance test.** Run the standalone case at `mpirun -np 1` and
`mpirun -np 4`; assert (a) `Σ_c forceField_[c]·V_c == Σ_i F_i` on every rank count
(total force preserved), and (b) the N-rank total equals the serial total within
tolerance. Include a **partition-boundary case**: a surface whose nodes are placed so
their 5×5×5 stencils straddle a processor boundary, verifying no cell in a
cross-rank stencil is missed or double-counted.

---

## 11. Backward Compatibility & Rollback

Byte-identical guarantees and their gates:

| Guarantee | Gate |
|-----------|------|
| No `nacelle {}` → `hasNacelle_ == false` → the three `addSup` bodies skip the block; ALM default unchanged | Existing pytest suite (`test_al`, `test_aftal`, `test_aftal_asm`, `test_cftal`) passes unchanged |
| `-lsurfMesh` link change does not break any other turbinesFoam build | `test_libs.py` + `./Allwmake` + `ldd -r` clean |
| Kinematics refactor: no `omegaOverrideField`/`tsrAmplitude` → `angle_deg` CSV column matches baseline to floating point | `test_aftal`/`test_aftal_asm` CSV comparison |
| Nacelle path is opt-in and static; rotate/tilt/yaw untouched for blades/hub | `test_aftal` (blade/hub behavior) |

Rollback = revert (§proposal): remove the `nacelle {}` subdict from any adopting case
(behavior returns without recompiling); `git revert` the W1–W4 units to restore the
prior code, `Make/*`, and the deleted `createNacelle` stub. The kinematics refactor
is independently revertible (W3). Registering `angleDeg_`/`omega` as
`uniformDimensionedScalarField` adds harmless field directories under time steps; a
revert leaves files OpenFOAM ignores (no schema migration).

---

## 12. Risks and Open Items (design-level; none block tasks)

**Risks**

1. **Delivery shape (blocking for apply, not for design):** ~1500–2200 lines vs the
   400-line `single-pr` budget → chained PR slices W1→W2→W3→W4 or `size:exception`.
   Resolved by the orchestrator/user after `sdd-tasks`.
2. **`tsrAmplitude` closed form + floating-point agreement:** the exact inversion and
   its "to floating point" agreement with the accumulator must be verified as a
   task-level RED test; a mismatch would surface in `test_aftal` CSV columns.
3. **Nacelle cylinder length `L` unstated in Sec. 4.1:** resolved from Fig. 3 with
   provenance; a documented assumption is acceptable if Fig. 3 is ambiguous.
4. **`-lsurfMesh` symbol hygiene:** must be proven (`ldd -r` clean, no duplicate
   symbols) on the toolchain; not assumed.
5. **`uniformDimensionedScalarField` restart read-back mode + registry host**
   (mesh vs Time, for the adapter's `globalData`): verified as a task item.
6. **`ũ` = `eqn.psi()` adaptation** (vs the paper's `u^n + rhs^n·Δt` predicted
   velocity): a documented approximation; the validation case is the acceptance.
7. **`h = cbrt(V)` for anisotropic cells:** the paper reports `h` insensitivity, so
   low risk; documented.
8. **Scalar-turbulence `addSup` is a no-op** (the nacelle injects no TKE, unlike the
   element path): documented deviation; acceptable for the bluff-body model.
9. **"byte-identical" (proposal) vs "to floating point" (spec) for kinematics CSV:**
   the design adopts the spec's "to floating point"; the proposal wording is the
   stricter, unresolved parent.

**Open Questions (none block tasks)**

- [ ] Confirm the nacelle cylinder length `L` from Fig. 3 (or adopt a documented default).
- [ ] Confirm the exact `uniformDimensionedScalarField` registry host (mesh vs Time) for the adapter `globalData` seam.
- [ ] Confirm the CSV `angle_deg` floating-point tolerance the existing `test_aftal` comparison will accept for the `tsrAmplitude` cases.

---

## 13. File Changes

| File | Action | Description |
|------|--------|-------------|
| `turbinesFoam/src/fvOptions/nacelleSurface/nacelleSurfaceSampler.{H,C}` | Create | Reusable surface-sampling object: triSurface read, node positions/normals/areas, per-node normal/tangential forces (Eqs. 19, 21, 22, 23), kernel + interpolation (Eqs. 7, 8), `positions()/forces()/normals()/areas()` contract |
| `turbinesFoam/src/fvOptions/nacelleSurface/nacelleSurfaceSource.{H,C}` | Create | `fv::option` source (`type nacelleSurfaceSource;`), derives `cellSetOption`, owns the sampler, kernel distribution (Eq. 18), `force.<name>` registration, CSV, three `addSup` overloads, MPI |
| `turbinesFoam/src/Make/files` | Modify | Register the two new `.C` files |
| `turbinesFoam/src/Make/options` | Modify | Add `-I$(LIB_SRC)/surfMesh/lnInclude` + `-lsurfMesh` |
| `turbinesFoam/src/fvOptions/axialFlowTurbineALSource/axialFlowTurbineALSource.{H,C}` | Modify | `nacelle_` → `autoPtr<nacelleSurfaceSource>`; implement `createNacelle()`; close null-deref additively |
| `turbinesFoam/src/fvOptions/turbineALSource/turbineALSource.{H,C}` | Modify | Time-derived `angleDeg_`; optional omega override; registry `angleDeg`/`omega` fields; `angleDeg()` accessor |
| `turbinesFoam/geometry/` (README.md, PROVENANCE.md, src/nacelle.geo, src/makeGeometry.py, stl/nacelle.stl, metadata/nacelle.json) | Create | Deterministic gmsh + Python geometry pipeline (S1 = nacelle STL + metadata + provenance) |
| `turbinesFoam/validation/nacelle-asn/` (README, config/case.yaml, tools/generate_case.py, scripts/compareNacelle.py, scripts/runNacelle.sh, scripts/slurm/stage0.slurm, scripts/slurm/production.slurm, case/, data/reference/ + PROVENANCE.md) | Create | Paper-faithful periodic-nacelle validation case, staged HPC |
| `turbinesFoam/tests/test_nacelle.py`, `tests/test_nacelle_data.py` | Create | Integration + pure-Python tests (§9) |
| `turbinesFoam/tests/test_nacelle_compare.py` | Create (recommended) | Pure-Python compare-script coverage (mirrors `test_phasevi_compare.py`) |
| `turbinesFoam/README.md`, root `README.md`, root `CHANGELOG.md` | Modify | Config keys, geometry pipeline, closure adaptation (WALE vs dynamic SGS), fork-divergence note, attribution |

Untouched: `actuatorLineElement`/`actuatorSurfaceElement`, `profileData`, dynamic
stall, added mass, end effects, `crossFlowTurbineALSource`, the adapter
(`modules/*`), `fsiOmega`.

---

## 14. Data Flow

```
                  +--------------------------- nacelleSurfaceSource ---------------------------+
                  |                                                                           |
 STL (triSurface::New)                                                                    |
        |                                                                                    |
        v                                                                                    |
 nacelleSurfaceSampler --- positions/normals/areas (triangle centroids, stable order)       |
        |                                                                                    |
 addSup: U = eqn.psi()                                                                      |
        |                                                                                    |
        +--> interpolateVelocity(X_i)      (Eq. 7, kernel Eq. 8)  --> ũ                      |
        |         |                                                                          |
        |         +--> normalForce        (Eq. 19: h·(ũ·e_n)/Δt·e_n)  --> f_n                |
        |                                                                                    |
        +--> tangentialDirection(X_i + h·e_n)  (Eq. 23) --> e_τ                              |
        |         +--> frictionCoefficient (Eq. 22) + tangentialForce (Eq. 21: ½·cf·U²·e_τ)  |
        |                                                                                    |
        +--> F_i = (f_n + f_τ)·A_i     (area weight)                                         |
                  |                                                                          |
                  +--> distributeForce (Eq. 18: Su[c] += -F_i·δ_h)  --> force.<name> field   |
                              |                                                              |
                              v                                                              |
                  eqn += forceField_      (incompressible: per-unit-density;                |
                                           compressible: ×rho)                               |
                              |                                                              |
                              v                                                              |
                  force_ (reduce sumOp) --> CSV (master)  +  forces()/positions() (contract)|
```

---

## 15. Threat Matrix

N/A — the change introduces no routing, shell-command, VCS/PR-automation, or
executable-file-classification boundary. The only subprocess invocations are
deterministic, human/test-driven build tooling: `makeGeometry.py` invoking `gmsh`
(fixed inputs, sha256-verified output, non-destructive `--check`) and the
**prepared-only** slurm `production.slurm` job (never launched before explicit
authorization). Neither is an autonomous path with adversarial inputs, so the
matrix's boundaries (documentation-like paths, git repository selection, commit
state, push state, PR commands) do not apply and no rows are marked applicable.

---

## 16. Migration / Rollout

No data migration or schema changes to existing artifacts. The change is opt-in and
additive (§11). Rollout is gated by: `cd turbinesFoam && ./Allwmake` (exit 0,
`ldd -r` clean) and the full existing pytest suite passing unchanged. HPC rollout is
staged: `validation/nacelle-asn/scripts/slurm/stage0.slurm` (dev partition: mesh +
stability) now; `production.slurm` (long queue: averaging) **prepared only**, launched
after authorization.
