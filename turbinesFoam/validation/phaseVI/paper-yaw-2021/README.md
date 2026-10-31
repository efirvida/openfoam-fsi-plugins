# Prepare the Phase VI paper-like ALM comparison

**Preparation only: `execution_ready=false`, even when the audit passes.** This
package prepares exactly four isolated cases: 7 and 13 m/s, each with a
numerically matched control and a paper-like aerodynamic arm. It never calls a
runner, mesher, solver, environment setup or scheduler. No execution is approved.

> **NOT identical paper topology.** The proposed blockMesh + nested-box
> snappyHexMesh castellation is conformal and has transition cells. It reconstructs
> reported resolution criteria, not the article's nonconformal cubic topology.
> No polyMesh exists from this preparation. Counts and widths are planned, not
> measured. Approximately 400k cells is a reported value, **not a tuning target**.

Reference: Arabgolarcheh et al. (2021), DOI 10.1155/2021/9978134,
[local paper](../../../articles/Numerical_Study_of_a_Horizontal_Wind_Turbine_under.pdf).

## Quick path

From the repository root (use an absent or empty output directory).
`runs/paper-yaw-2021-v2` supersedes the preserved, unexecuted original
`runs/paper-yaw-2021`; do not overwrite or execute the old artifact:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 turbinesFoam/validation/phaseVI/paper-yaw-2021/prepare.py --prepare --output turbinesFoam/validation/phaseVI/runs/paper-yaw-2021-v2
PYTHONDONTWRITEBYTECODE=1 python3 turbinesFoam/validation/phaseVI/paper-yaw-2021/prepare.py --check --output turbinesFoam/validation/phaseVI/runs/paper-yaw-2021-v2
PYTHONDONTWRITEBYTECODE=1 python3 turbinesFoam/validation/phaseVI/paper-yaw-2021/prepare.py --report --output turbinesFoam/validation/phaseVI/runs/paper-yaw-2021-v2
```

| Interface | Result |
|---|---|
| `--prepare` | Writes `U7-control`, `U7-paper-like`, `U13-control`, `U13-paper-like`, `report.json` and `preparation-config.json`; stdout `Prepared 4 cases; execution_ready=false.` |
| `--check` | Read-only exact byte audit of all expected files and rejection of extra files/symlinks; stdout `Configuration audit passed; execution_ready=false.` |
| `--report` | Same read-only audit, then sorted, indented JSON on stdout, identical to retained `report.json` |
| `--output DIR` | Required isolated target; symlink output paths are rejected |
| `--config FILE` | Defaults to adjacent `config.json`; only byte-identical copies of this frozen specification are supported; no silent parameter overrides |
| `--help` | Usage and all options; no `--run`, `--submit` or `--force` capability |

Success exits 0 with empty stderr. Audit failures exit 1 with empty stdout and
`error: missing or changed output: RELATIVE_PATH` or
`error: unexpected output entries` on stderr. Input/path errors exit 2 with empty
stdout and `error: MESSAGE`: `config does not match the supported preparation specification`,
`cannot read config: PATH`, `output must be absent or an empty directory`,
`symlink output paths are not allowed`, or the underlying input I/O error.
Argparse usage/unknown-option errors also exit 2. Rejected inputs and conflicting
nonempty targets cause no writes; preparation renders and validates all inputs
before writing. Files are exclusively created, never overwritten. Filesystem
failure during writing is not a transactional rollback guarantee; use a fresh
writable target. Re-preparing an existing output is deliberately rejected.

## Matched numerics and distinct aerodynamic arms

All four meshing dictionaries are byte-identical. All four fvSchemes,
fvSolution, turbulence and transport dictionaries are byte-identical. Inflow
field values necessarily differ with wind speed, but use the same intensity
0.005 and mixing length 0.07D. Angular velocity is 71.63 rpm through the
**effective TSR** `rpm*2*pi*R/(60*U)`, not by changing informational RPM alone.
Both arms select Sequence S, zero yaw, 3-degree pitch and dt=0.001 s.

| Condition | Both arms / distinction |
|---|---|
| Turbulence | realizableKE, k and epsilon (no omega); epsilon=0.09^0.75*k^1.5/(0.07D), k=1.5*(0.005U)^2; unspecified paper inflow epsilon is an assumption |
| Transport | Newtonian, published nu=1.46e-5 m2/s in transportProperties; published rho=1.23 kg/m3 retained as reference metadata and fvOptions rhoRef, not an incompressible force multiplier |
| Time / space | CrankNicolson **0.9 blend**, explicit reconstruction choice (1=pure CN, 0=Euler); linearUpwind U, upwind k/epsilon; corrected nonorthogonal operators for castellation transitions |
| Linear solve | Published PBiCG for U, compatible DILU; same solver for k/epsilon, GAMG pressure; 2 nonorthogonal corrections |
| Far boundaries | sideMinus/sidePlus/top/bottom symmetryPlane in mesh **and fields**, following human-selected figure interpretation despite contradictory no-slip prose |
| Control | v1.2 aerodynamic switches: Glauert tip+root, dynamic stall off, centre sampling; **NUMERICALLY MATCHED CONTROL, not baseline-certified**, because mesh/numerics/RPM/sequence differ |
| Paper-like | Shen **c1=0.125** (not 1.125), c2=21, tip-only; active LeishmanBeddoesSGC; 16 displaced velocity samples, radius=1 epsilon |
| Both off | Dağ–Sørensen, rotational augmentation, added mass, flow curvature; no invented per-profile dynamic-stall override |
| Geometry/polars | Existing helper-generated geometry and cylinder root unchanged; OSU Re1M pressure-drag S809 include resolved relative to each isolated system directory |

**Polar limitation:** `liftReCorrExp=0` does **not** remove drag Reynolds
correction. This single-Re polar is not the article's multi-Re interpolation.
Use existing `scripts/comparePhaseVI.py` for later P/Q/Cp comparisons; this tool
owns configuration arithmetic only and duplicates no calibrated metric.

### Density and viscosity: effective locations

The shared schema/renderer reads `inflow.kinematic_viscosity`; each isolated
configuration overrides it to 1.46e-5 m2/s before transport rendering. The shared
schema has no incompressible density setting, so the isolated snapshot adds
`inflow.reference_density_kg_m3=1.23`, retained in report `fluid` metadata and
as `rhoRef 1.23` in the turbine coefficients. Source inspection confirms that
only the compressible `addSup(rho, ...)` overload reads that `rhoRef` key for
coefficient normalization. The selected incompressible `pimpleFoam`/ALM path
uses kinematic pressure and forces per unit density: **it does not consume rhoRef
or multiply the momentum source by 1.23**. Density is available for later
physical-unit/report normalization, not an invented active solver setting.
No calibrated performance is computed here.

### SGC assumptions and root blocker

`LeishmanBeddoesSGCCoeffs` is emitted inside `dynamicStall`, the subdictionary
forwarded to elements. Explicit inherited/default constants are A1=0.165,
A2=0.335, A3=0.5, b1=0.14, b2=0.53, T1=20, T2=4.5, Tp=1.7, Tf=3,
Tv=11, Tvl=9, eta=0.975, cmFitExponent=2, TAlpha=6.3, r0=0.01,
B1=0.5, B2=0.2, E0=0.15, alphaDS0DiffDeg=3.6, speedOfSound=1e12 m/s
(incompressible approximation). `calcAlphaEquiv=true` enables equivalent
incidence for article equation 5's alpha-X-Y-Z form. The repository's inherited
3G implementation is a Sheng-family counterpart, **not equation-for-equation
proof** of the article formulation. Static-fit parameters are still derived
from the polars. These coefficients remain assumptions, not calibrated or
verified article values.

**Source inspection identified potentially unsafe cylinder static-fit paths
under SGC. NO runtime failure was reproduced.** The root polar is not changed,
and no profile-specific opt-out is invented. Root SGC compatibility remains an
actionable execution blocker, not a solver fix hidden in preparation.

## Mesh reconstruction assumptions

Section orientation is assumed y=24.4 m, z=36.6 m, centred on hub height
12.192 m. Axial bounds are -2D to +8D, D=10.058 m. The maximum base width is
0.8 m, rounded upward to integer counts per axis. Three dyadic nested boxes
produce four planned spacing zones, with nominal finest widths near 0.1 m,
strictly below 0.125 m in every axis.

**All nested bounds below are ASSUMPTIONS; the paper does not publish them.**
Coordinates are metres relative to the hub, not rotor diameters:

| Level | Minimum x,y,z | Maximum x,y,z |
|---|---|---|
| 1 | -10,-10,-10 | 40,10,10 |
| 2 | -5,-8,-8 | 20,8,8 |
| 3 (finest) | -3,-7,-7 | 12,7,7 |

The full rotor and displaced sampling envelope fit inside level 3 under the
explicit assumed abs(Cd)<=2 bound. Projection epsilon [m] is the maximum of
0.25*chord (lift floor), Cd*chord/2 (drag floor), and
2*cbrt(cellVolume)*meshFactor (mesh floor), meshFactor=1. Thus radius=1 means
one epsilon, **not one metre**; it equals 2dx only for mesh-dominated epsilon
on cubic cells. The report records the conservative assumed sampling envelope;
actual dynamic Cd, epsilon and containment still require runtime verification.

Nominal count integrates rectangular shell volumes at each dyadic density. It
ignores grid alignment, buffering and conformal transition cells; it is not an
actual castellation count or a measured mesh-quality statement. No AMI framework
or geometry is introduced. No mesh utility is invoked.

## Audit and readiness boundary

The retained report records per-axis zone widths, nominal count, bounds,
common mesh/numerical hashes, each generated dictionary hash, and SHA-256 input
provenance (frozen preparation specification, source case configuration, polar,
geometry, the four imported shared helper files and this tool). Only actual
rendering inputs are hashed: baseline-case dictionaries, incidental logs/caches,
unused helpers and the model-definition document are not input dependencies. Per-case JSON snapshots isolate
all overrides without mutating the source YAML. Source input drift makes the
exact output audit fail; checks never refresh outputs or silently bless drift.

Report arithmetic: angular step=rpm*6*dt [degrees], tip displacement=Omega*R*dt
[m], displacement/minimum planned rotor spacing, and
**nominal advective Co=Uinf*dt/min(h), NOT measured Co**. The legacy helper's
internal guard uses its original nonuniform mesh because its cell-size helper
does not handle unit grading; the retained tool independently checks the actual
planned minimum spacing. This does not change rendered kinematics.

Three blockers always keep `execution_ready=false`:

1. Actual blockMesh/snappyHexMesh/checkMesh evidence, measured cell count,
   spacing, topology and quality are absent.
2. Measured Courant/time stability and temporal-convergence evidence are absent;
   a small nominal estimate does not validate dt.
3. Root SGC compatibility and the assumed epsilon/sampling envelope are unverified.

## Verification

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest turbinesFoam/tests/test_phasevi_paper_yaw_2021.py -q
```

Tests use only harness-owned temporary directories and the public CLI. Existing
baseline config/case/helpers/data bytes must remain unchanged. No full suite,
mesh or solver invocation is part of this package's preparation command.
