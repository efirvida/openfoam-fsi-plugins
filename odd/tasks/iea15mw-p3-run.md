# Feature: IEA 15-240-RWT P3 — first rated-point physics run

- **Status:** in progress
- **Branch:** `feat/dagsorensen-tip-correction`
- **Created:** 2026-10-01
- **Plan:** `odd/tasks/iea15mw-case-readiness.md` (P0–P6, §5)
- **Package:** `turbinesFoam/validation/iea15mw/`

## Objective

Execute and analyse **P3** — the first real-physics run of the IEA 15-240-RWT
turbinesFoam case: neutral baseline (endEffects off, no tipCorrection, no
rotational augmentation, no dynamic stall) at the rated point
`V = 10.659 m/s`, `Omega = 7.518 rpm`, pitch 0, coarse D/32, 48 ranks, 3 revs.

Acceptance: rotor power/thrust/Cp/Ct inside the cross-code band
[WISDEM 2.457 MN / 19.91 MN·m / Ct 0.7718 / Cp 0.4618 ↔
OpenFAST-BEM 2.748 MN / 19.51 MN·m / Ct 0.803 / Cp 0.482], plus the spanwise
`Cn/Ct` trend against the OpenFAST `AB1N*` channels and the OLAF free-vortex
wake reference. **Cross-code, not measurement** — the IEA 15 MW has no
measurements.

## Why — the failed first attempt (job 11604860)

`blockMesh`, `topoSet`, `checkMesh`, `decomposePar` all exited 0; `pimpleFoam`
died *before physics* with an OpenMPI topology error:

```
Your job has requested more processes than the ppr for this topology can support:
  App: pimpleFoam   Number of procs: 48   PPR: 8:node
```

Slurm allocated **3 nodes × 16 cores** (`sacct`: `NNodes=3`); the runner's
`--map-by ppr:8:node` requires 6 nodes. The ppr flag was a guess at the earlier
intermittent PMIx race, not a proven fix.

**Second, latent blocker found while diagnosing**: the runner never creates the
`0/` time directory from the rendered `0.org/`, so `decomposePar` produced only
`processor*/constant/polyMesh` with **no fields**, and `pimpleFoam` could not
have read `0/U` even with working MPI. The Phase VI runner does
`cp -r 0.org 0`; the IEA runner omitted it.

## Constraints

- **Production queue saturated** → run on `sequana_cpu_dev` (20-min wall limit,
  48 cores) and **self-requeue** (`scontrol requeue`) to continue from the last
  written time. P3 is ~75 min wall (Phase VI D/32 was 4:48:35 for 12 revs ⇒
  ~24 min/rev).
- Never cap `--nodes`, never set `--mem` (cores only).
- Submit Slurm scripts **from the package directory** (`$SLURM_SUBMIT_DIR`).
- The `0.org` template stays the committed source of truth so `--check` is
  clean; the run directory gets the real `0/`.
- **Never edit a shell script while a job is executing it.**

## Tasks

1. [ ] Add `--start-from startTime|latestTime` to `tools/generate_case.py`
       (mirror the Phase VI renderer) + a render test.
2. [ ] Create the `0/` directory from `0.org/` in the run path (fix the latent
       blocker).
3. [ ] Fix the MPI mapping: pack ranks onto the **allocated** nodes
       (`ppr = ceil(ranks / SLURM_NNODES)`) so it can never conflict with the
       allocation; keep the proven `--mca pml ucx --mca btl ^openib`.
4. [ ] Add resume + self-requeue: run under a Slurm-aware wall budget, and
       `scontrol requeue` when the budget is hit without reaching `endTime`.
       Factor the body into one helper shared by the production and dev wrappers.
5. [ ] Add the `sequana_cpu_dev` wrapper (`coarse-dev.slurm`).
6. [ ] Run the test suite + `shellcheck`; commit.
6b. [x] **Blade-orientation audit (blocking the physics run).** Done: the case
       now maps `BlCrvAC`/`BlSwpAC`/`BlCrvAng` (`odd/tasks/iea15mw-blade-geometry-mapping.md`),
       verified against the AeroDyn node locus.
6c. [x] **Configurable flow/rotor axis.** The IEA case default is now the
       Aeroelast/FSI frame (`--flow-axis y`: fluid +Y, rotor axis about Y, blade
       axis +Z, profiles in XY); `--flow-axis x` keeps the OpenFAST frame. The
       domain is the `R_z(+90°)` image. blockMesh+checkMesh clean at 6,674,304
       cells. Needed so the fluid and structural meshes coincide for FSI.
6d. [x] **Fixed two latent blockers exposed by the first physics run:** the
       circular-root polar constant-Cl SIGFPE in `profileData::interpolate`, and
       the restart blocker (the ALM's per-step `angleDeg.<name>` field-less time
       dirs). See the evidence below.
7. [ ] Submit P3 to the dev queue and monitor to completion.
8. [ ] Analyse P3 against the cross-code band + spanwise vs OpenFAST/OLAF;
       record in `RESULTS`/task note.
9. [ ] Persist the completed OLAF reference note (`odd/tasks/iea15mw-olaf-reference.md`).

## Evidence log

### 2026-10-01 — blade orientation: prebend/sweep/curve angle are dropped

The maintainer flagged the IEA 15 MW blade orientation (Aeroelast builds the
blade with the span along one axis and the profiles in the section plane).
Audit result: the case reproduces **only the radial position, chord and twist**
of the blade; it drops the out-of-plane and in-plane shape.

**What AeroDyn/OpenFAST actually uses** (`openfast-src/.../AeroDyn.f90:1323-1331`):

```fortran
positionL(1) = BlCrvAC(j)   ! prebend  (out-of-plane), |max| = 3.999 m (tip)
positionL(2) = BlSwpAC(j)   ! sweep    (in-plane),     |max| = 0.435 m
positionL(3) = BlSpn(j)     ! span
position = root + matmul(positionL, RefOrientation)   ! RefOrientation holds PreCone
theta(1) = 0 ; theta(2) = BlCrvAng(j) ; theta(3) = -BlTwist(j)
orientationL = EulerConstruct(theta)                  ! R_z(t3)*R_y(t2)*R_x(t1)
```

So per node: the position is `(prebend, sweep, span)` in the root-local frame and
the orientation carries the **curve angle** `BlCrvAng` (|max| = 5.765° at the
tip) as a rotation about the sweep axis, plus `-BlTwist` about the span.

**What the case does** (`tools/blade_geometry.py::element_rows`):

```
(axialDistance=0, radius=HubRad+BlSpn, azimuth=0, chord, chordMount, -BlTwist)
```

and `axialFlowTurbineALSource.C:137-225` maps `axialDistance→axis_` (prebend
slot) and `azimuth→` tangential rotation (sweep slot). Both are zero for every
station.

**Consequences.**

| quantity | AeroDyn | case | status |
|---|---|---|---|
| span | `BlSpn` | `radius = 3.97 + BlSpn` | ✓ |
| twist | `-BlTwist` | `-BlTwist` | ✓ (signs match AeroDyn) |
| prebend | `BlCrvAC` to −4.00 m | 0 | **dropped** |
| sweep | `BlSwpAC` to ±0.44 m | 0 | **dropped** |
| curve angle | `BlCrvAng` to −5.77° | 0 | **dropped** |

The projected radius is unaffected (prebend is along the rotor axis), so the
P0 `R = 120.675 m` / `coneAngle 4` decision stands. But the outboard blade sits
~4 m off-axis and the tip section orientation is off by ~5.8°, which matters
precisely for the P4 tip study. `pitch` in the ALM is a pure rotation about the
span (`actuatorLineElement.C:1275-1283`), so `BlCrvAng` (a rotation about the
sweep axis) cannot be folded in exactly — it needs an element-orientation term
or a documented approximation.

**Sign mapping is not yet derived** (prebend into `axis_`, sweep into the
tangential rotation, and the cone handedness). It must be verified
numerically against AeroDyn's own node positions rather than assumed.

