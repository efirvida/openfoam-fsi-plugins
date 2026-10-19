# NREL Phase VI uniform-inflow validation

Validation package for the NREL/NASA-Ames Phase VI rotor (10.058 m diameter,
standard 5.029 m tip, two blades, 3° pitch) coupled to three vendored
`turbinesFoam` models: the actuator line (ALM), the no-mesh actuator surface
(ASM) and the mesh-backed actuator surface (`fvOptions.ASM-MESH`, the imported
`phaseVI_blade` surface). The three variants differ only in the blade
subdictionary element/surface keys; see "Model variants and formulation" for
the formulation being validated, the sub-grid caveat and the pre-registered
hypothesis.

The case is a uniform-inflow free box (no atmospheric boundary layer, no Mann
turbulence, no external inflow preprocessing):

| Axis | Extent | Fallback (`--domain squat`) |
|---|---|---|
| x | −5D … 15D | −5D … 10D |
| y | ±4D | ±3D |
| z | hub ± 2.5D (hub 12.192 m) | hub ± 3D |

Boundary conditions: uniform velocity inlet, pressure outlet, symmetry far
field. Solver: `pimpleFoam` + `kOmegaSST` URANS, `adjustTimeStep off` with a
fixed time step (D/32 0.008 s, D/48 0.005 s, D/64 0.004 s) chosen so the blade
tip moves less than the hub-adjacent cell per step. The optional Stage 3
variant (`--solver iddes`) switches to LES `kOmegaSSTIDDES` with a fixed
0.0025 s step (see "IDDES variant"). The full design and
requirements live in `openspec/changes/phase-vi-validation/` of the
`of-plugins` repository; the data sources and their sha256 are recorded in the
per-directory `PROVENANCE.md` files.

## Layout

```
config/case.yaml          single source of truth (YAML)
tools/case_config.py      load/validate YAML; derived mesh/kinematics helpers
tools/generate_case.py    renderer + non-destructive --check
tools/element_data.py     blade/hub element rows, -(twist + pitch) convention
tools/stage_blade_stl.py  sha256-gated STL staging for asm-mesh run dirs
case/                     committed generated skeleton (ALM/ASM/ASM-MESH twins)
data/                     geometry, polars, experiment, s809 + PROVENANCE per dir
scripts/                  runners, mesh/stage tooling, comparison
  checkModelDefinition.py effective-value v1.2 conformance gate
  summarizeBands.py      pre-registered bands; refuses non-conforming evidence
  slurm/stage0.slurm      authorized development-queue job
  slurm/production.slurm  prepared-only long-queue array (do not submit)
  slurm/stage3.slurm      prepared-only IDDES + nChordwise array (do not submit)
  slurm/stage3-d64.slurm  prepared-only D/64 sensitivity array (do not submit)
  slurm/asm-mesh.slurm    prepared-only ASM-mesh D/32 gate + D/48 array (do not submit)
  slurm/campaign-rotational-augmentation.slurm
                          prepared-only two-arm aug/root power-curve array (do not submit)
runs/                     rendered run directories (gitignored)
results/                  comparison output (gitignored)
CAMPAIGN.md               prepared rotational-augmentation campaign (do not submit)
```

## Environment

Load the repository OpenFOAM toolchain and set the wmake identity variables
(see the root `AGENTS.md`; the SDumont `openfoam/v2506_*` module does not
export them):

```sh
module load openfoam/v2506_openmpi-4.1.4_gnu
export WM_ARCH=linux64 WM_COMPILER=Gcc WM_COMPILE_OPTION=Opt
export WM_PRECISION_OPTION=DP WM_LABEL_SIZE=64
export WM_OPTIONS=linux64GccDPInt64Opt
. "$WM_PROJECT_DIR/etc/bashrc"   # the module exports Int32 paths; this puts the Int64 binaries on PATH
export FOAM_USER_LIBBIN=$WM_PROJECT_USER_DIR/platforms/$WM_OPTIONS/lib
export LD_LIBRARY_PATH=$FOAM_USER_LIBBIN:$WM_PROJECT_DIR/platforms/$WM_OPTIONS/lib:$WM_PROJECT_DIR/platforms/$WM_OPTIONS/lib/sys-openmpi:$LD_LIBRARY_PATH
```

`scripts/check_environment.sh` accepts OpenFOAM **v2506 and v2412**, checks
`blockMesh`/`topoSet`/`checkMesh`/`pimpleFoam`/`decomposePar`/`mpirun`,
`libturbinesFoam.so` in `FOAM_USER_LIBBIN`, and then runs
`generate_case.py --check` (exit 3 environment, exit 4 stale case).

## Case generation

```sh
python3 tools/generate_case.py            # render the committed case/
python3 tools/generate_case.py --check    # exit 1 on missing/stale, never writes
```

`--mesh coarse|fine|ultra`, `--speed <7|10|13|15|20|25>`,
`--domain long|squat`, `--sequence H|S`, `--profile production|smoke`,
`--solver urans|iddes`, `--n-chordwise N`, `--ranks N`,
`--surface-kernel cosine|gaussian`, `--rotational-augmentation on|off`,
`--rotational-augmentation-model DuSelig|ChaviaropoulosHansen`,
`--root-effects on|off`, `--velocity-sample-radius R`, `--n-velocity-samples N`,
`--lift-re-corr-exp N`, `--case-dir DIR`,
`--end-revs FLOAT`, `--start-from startTime|latestTime`.

The last three flags expose the configuration the IEA 15 MW campaign validated.
Each of them renders **no key** at its source default, so the committed `case/`
is byte-identical and `--check` passes untouched:

| Flag | YAML key | Source default | Validated Phase VI value |
|---|---|---|---|
| `--velocity-sample-radius R` | `actuator.velocity_sampling.velocity_sample_radius` | `0.0` (no sampling) | `3.3` |
| `--n-velocity-samples N` | `actuator.velocity_sampling.n_velocity_samples` | `20` | `16` |
| `--lift-re-corr-exp N` | `profile.lift_re_corr_exp` | `0.23` | `0` |

`velocitySampleRadius`/`nVelocitySamples` are written at the rotor-coeffs level,
where `axialFlowTurbineALSource` reads them from `coeffs_`. `liftReCorrExp` is
written inside the `profileData/S809` subdict, beside the `Re 1e6;` statement it
modifies: `profileData` reads both from that same dictionary, and the declared
`Re` is what arms `profileData::updateRe`, whose `K = (Re/ReRef)^0.23` rescaling
rotates the polar about its zero-lift angle and inflates `cl`. The Phase VI
validation therefore sets the exponent to `0`.
Rendered files carry a "Generated from config/case.yaml" banner; `case/` is
the only committed copy and hand edits are detected by `--check`.

The measured per-speed TSR is selected through `tipSpeedRatio` (7 m/s → 5.408,
10 → 3.798, 13 → 2.920, 15 → 2.530, 20 → 1.898, 25 → 1.521; Sequence S 7 → 5.407).
The mesh ladder renders 18 blocks, 100 % hexahedra:

| Resolution | Cell size | Cells | Use |
|---|---|---|---|
| coarse (D/32) | 0.3143 m | 6,674,304 | Stage 0 / development |
| fine (D/48) | 0.2095 m | 22,525,776 | headline |
| ultra (D/64) | 0.1572 m | 53,394,432 | optional sensitivity |

The proposal's "≈40 M" D/64 estimate is superseded by 53,394,432 (the design
refines z like x/y); recorded in `design.md` §5 and `config/case.yaml`.

## Running

```sh
scripts/runPhaseVI.sh -m alm|asm|asm-mesh -u <speed> [-mesh coarse|fine|ultra]
                      [--domain long|squat] [-s H|S] [--solver urans|iddes]
                      [--nchordwise N] [--ranks N] [--run-label WORD]
                      [--stage0] [--restart] [--refine-level N] [--mesh-factor F] [--blade-dz DZ]
                      [--rotational-augmentation on|off] [--root-effects on|off]
                      [--rotational-augmentation-model DuSelig|ChaviaropoulosHansen]
                      [--run] [--submit]
```

The runner validates the (model, speed, mesh, sequence, solver) combination
through `tools/case_config.py`, renders the case into
`runs/<model>-U<speed>-<mesh>` (for example `runs/asm-U7-coarse-s0`),
installs the selected `fvOptions` twin as `system/fvOptions`, hardlinks the
shared `runs/mesh-<mesh>/constant/polyMesh`, and writes `run.json` (git
commit, OpenFOAM version, config sha256, variant, solver, `n_chordwise`,
`mesh_factor`, `ranks`, start time). The committed `case/` skeleton is never modified.

- `--restart` refuses (exit 2, nothing rendered or deleted) a run directory that
  already holds a written time: there is no true resume, because `--run`
  re-decomposes with `decomposePar -force` and the CSV writers truncate
  `postProcessing/<...>/0/`. On a fresh directory it warns and keeps `startTime`.
  Give a run a `--time` for its full length; to rerun from 0, remove
  `processor*/` and `postProcessing/` explicitly.
- `--stage0` caps `endTime` at 0.25 revolutions (spec bound ≤ 0.3) so a 48-rank
  job fits the 20-minute `sequana_cpu_dev` partition.
- `--solver iddes` renders the Stage 3 LES `kOmegaSSTIDDES` variant (see
  below) and appends `-iddes` to the run id.
- `--nchordwise N` overrides the ASM chordwise strip count (ASM only; rejected
  for ALM) and appends `-ncN`; the configured default is 5.
- `--refine-level N` selects the castellated refinement level of the rotor-disk
  cylinder (each level halves the cell there) and scales `meshFactor` by `2**N`
  so the projection width stays fixed in metres; the shared mesh is keyed on `N`.
- `--blade-dz DZ` (positive number, exit 2 otherwise; not combinable with `--n-elements`) renders the
  blade at constant spanwise spacing `DZ` metres outboard of 1.0085 m (root stations kept):
  `nElements` becomes one element per table segment and, for `asm-mesh`, the staged STL is lofted from
  the same table (`tools/make_equispaced_blade.py`). Rule: `DZ = min(0.05, h/2)`; see
  `scripts/scanEquispacedDz.py`. Recorded as `blade_dz` in `run.json`.
- `--mesh-factor F` (positive number, exit 2 otherwise) overrides
  `turbine.gaussian_mesh_factor` (1.0) so the ALM / no-mesh-ASM projection width
  `eps = 2*cbrt(V)*meshFactor` varies per run **without changing the mesh**: the
  shared mesh directory is the same for every factor. It is applied before the
  `--refine-level` scaling (`--mesh-factor 2 --refine-level 1` renders
  `meshFactor 4`); `run.json` records the effective value as `mesh_factor`. It
  does not alter the run id, so pair it with `--run-label`. It has no effect on
  the default ASM+mesh cosine kernel.
- `--run-label WORD` appends `-WORD` to the run id (`runs/<id>-WORD`) and records
  it in `run.json`; `WORD` must match `[A-Za-z0-9._-]+` and not start with `.`
  or `-`. It lets a campaign keep two render variants of the same `(model,
  speed, mesh)` — e.g. the augmentation/root arms — in separate, independently
  restartable directories. It is refused with `--submit`.
- `--ranks N` overrides `decomposition.number_of_subdomains` in the rendered
  `decomposeParDict` and for `mpirun -np`; inside a Slurm allocation the runner
  fails (exit 2) unless `N == SLURM_NTASKS`.
- `--run` executes `decomposePar -force` and
  `mpirun -np <ranks> pimpleFoam -parallel` (inside a Slurm allocation;
  48 subdomains by default).
- `--submit` with `--stage0` submits `slurm/stage0.slurm` to the development
  queue. Without `--stage0` it requires `TURBINE_LONG_QUEUE_AUTHORIZED=1`
  **and** a passing `results/U7-H/sign_gate.json`; otherwise it exits 5. It
  refuses to carry `--solver iddes`, `--nchordwise` or `--ranks` (Stage 3 has
  its own prepared arrays).
- `-m asm-mesh` selects the mesh-backed surface twin (`fvOptions.ASM-MESH`),
  produces the run id `asm-mesh-U<speed>-<mesh>`, and stages the committed
  `geometry/stl/phaseVI_blade.stl` into `constant/triSurface/` through
  `tools/stage_blade_stl.py` before the mesh link (sha256-checked against the
  geometry metadata; a missing source or a hash mismatch aborts with exit 3 and
  leaves no stale copy). The staged hash is recorded in `run.json` as
  `staged_stl_sha256`. `--nchordwise` is accepted (ASM family) and `--submit`
  is refused (exit 2) pointing at the prepared-only
  `scripts/slurm/asm-mesh.slurm`.

Exit codes: **2** unsupported input (including a `--ranks`/`SLURM_NTASKS`
mismatch), **3** environment/mesh/solver failure, **4** stale generated case,
**5** authorization or sign-gate failure.

### IDDES variant

`--solver iddes` switches `constant/turbulenceProperties` to
`simulationType LES` with `LESModel kOmegaSSTIDDES` and `delta IDDESDelta`
(`IDDESDeltaCoeffs { Cw 0.15; }`), the only LES delta `kOmegaSSTIDDES` accepts
in OpenFOAM.com v2506. The `iddes:` block of `config/case.yaml` also carries
the DES-appropriate `div(phi,U) Gauss linear` scheme, `wallDist { nRequired
true; }` (`IDDESDelta` reads the wall-normal vectors) and the fixed DES time
step **0.0025 s** on every mesh — still below the tip-displacement bound
(37.856 m/s × 0.0025 s = 0.0946 m < 0.1572 m, the D/64 hub-adjacent cell).
The tip-displacement assertion runs against the selected time step, so the
`--solver iddes` render is validated like the URANS one.

### Meshes and Stage 0

```sh
scripts/mesh.sh coarse [--domain long|squat]   # blockMesh + topoSet + checkMesh
scripts/mesh.sh fine
scripts/stage0.sh                              # print the stage plan only
scripts/stage0.sh --submit                     # sbatch the dev-queue job
scripts/slurm/stage0.slurm                     # 48 ranks, 20 min, sequana_cpu_dev
```

`mesh.sh` accepts a mesh only when `checkMesh` reports "Mesh OK", 100 %
hexahedra, non-orthogonality ≤ 1e-10 and the cell count inside the band from
`config/case.yaml` (6.60–6.80 M, 22.40–22.70 M, 53.0–53.8 M).

### Staged plan

| Stage | Content | Queue | Status |
|---|---|---|---|
| 0 | `checkMesh` D/32 + D/48; ALM+ASM 7 m/s D/32, ≤ 0.3 rev | `sequana_cpu_dev` | authorized |
| 1 | 7 m/s URANS ALM+ASM, D/32 first then D/48 | long | prepared |
| 2 | {10, 13, 15, 25} m/s ALM+ASM + Sequence S 7 m/s repeat | long | prepared |
| 3 | IDDES ALM+ASM D/32+D/48, ASM `nChordwise` {1, 3} D/48, D/64 ALM+ASM sensitivity | long | prepared |
| asm-mesh | Mesh-backed ASM 7 m/s: D/32 performance gate, then D/48 headline | long | prepared |

Stages 1–3 and the ASM-mesh array are prepared but **must not be submitted**
until the long-queue authorization is granted. 20 m/s stays renderable but is
deliberately not staged, so no blanket job array can pick it up.
`slurm/production.slurm` is a **prepared-only** array: one task per (model,
speed, mesh, sequence), 48 ranks, ≤ 96 h per task, restart from `latestTime`.
It refuses to run without `TURBINE_LONG_QUEUE_AUTHORIZED=1`, and no script
submits it automatically.

The rotational-augmentation candidate campaign (three models, the full staged
curve at D/32 plus a D/48 spot-check, in two physics arms — the candidate
`--rotational-augmentation on --root-effects off`, root-on `on/on`, plus the
ASM-mesh control `off/on`) is prepared in
`scripts/slurm/campaign-rotational-augmentation.slurm`. It groups its 47 runs
into **7 array tasks** (one per model×arm, each running all its speeds
sequentially with `--run-label`-separated run directories), so it fits the
association's `MaxSubmitJobs=24`. Its matrix, task→run table, resource
arithmetic (48 ranks vs the 30k cells/core heuristic), launch command, baseline
and gap notes, acceptance criteria and the association submit-limit caveat are
documented in `CAMPAIGN.md`. It is prepared only and refuses to run without
`TURBINE_LONG_QUEUE_AUTHORIZED=1`.

### Stage 3 arrays (prepared only)

Two prepared-only arrays cover Stage 3; both refuse to run without
`TURBINE_LONG_QUEUE_AUTHORIZED=1` and resolve the package from
`$SLURM_SUBMIT_DIR` (Slurm spools the script, so `BASH_SOURCE` is not usable —
same fix as `stage0.slurm`/`production.slurm`). Submit them from the package
directory with `sbatch scripts/slurm/stage3.slurm` (or `stage3-d64.slurm`).

| Job | Nodes / ranks | Wall time | Array |
|---|---|---|---|
| `slurm/stage3.slurm` | 4 / 192 | 96 h | 6 tasks: IDDES ALM+ASM on coarse and fine, plus ASM URANS `nChordwise` 1 and 3 on fine (7 m/s, `--restart`) |
| `slurm/stage3-d64.slurm` | 8 / 384 | 96 h | 2 tasks: ALM and ASM URANS on ultra (D/64) at 7 m/s, `--restart` so a task can be chained if the wall time is ever exhausted |

Every task passes `--ranks <ntasks>`, so the rendered `decomposeParDict` and
`mpirun -np` match the allocation (the runner fails otherwise). The multi-node
sizes are required by the mesh/step combination, not by throughput alone: the
D/48 IDDES runs and the D/64 URANS runs are roughly an order of magnitude
heavier than the 48-rank Stage 1 jobs. At 48 ranks a single D/64 run would need
about 194 h, so the D/64 array runs at 384 ranks (8×), which fits comfortably
in one 96 h task.

### ASM-mesh array (prepared only)

`slurm/asm-mesh.slurm` follows the `production.slurm` shape: 48 ranks on one
node, `--time=24:00:00` (the delta's at-most-24 h bound, stricter than the
untouched 96 h `production.slurm`), `--array=0-1`, both tasks `--restart --run`.
Task 0 is `asm-mesh:7:coarse:H` — the **D/32 performance measurement gate** —
and task 1 is `asm-mesh:7:fine:H`, the headline run. The script refuses to run
without `TURBINE_LONG_QUEUE_AUTHORIZED=1` (exit 5) and resolves the package from
`$SLURM_SUBMIT_DIR`, so it is **prepared only**: the D/32 task is executed and
reviewed (proceed / harden the candidate query / restrict the campaign) before
any D/48 preparation, and no automated step of this change submits it. The
queued `phaseVI-prod`, `phaseVI-stage3` and `phaseVI-stage3-d64` arrays are
read-only baselines.

#### D/32 performance measurement gate (prepared, not run)

The measurement is **prepared but not executed** by this change: it runs only
under explicit authorization, and no `sbatch` is issued here. When authorized,
task 0 is submitted alone and its output is reviewed before any D/48 job is
prepared.

The per-`addSup` instrumentation added by W4 (`logDistribution`, default
`true`) is the measurement source: the master rank prints one line per
`distribute()`,

```
Blade surface distribution 'turbine.blade1.surface': nodes <N>, candidates <C>,
mean <C/N>, max <max>, seconds <s>
```

and appends the matching row to
`postProcessing/bladeSurface/<owner>.surface_distribution.csv`
(`time,nodes,candidates,mean_candidates,max_candidates,seconds`). `candidates`
is the number of candidate cell entries visited in the call — the bounded-query
evidence, far below the naive `nodes × N_local cells` scan — and `seconds` is
the `addSup` wall time. The counters are observational only: the distributed
load is unchanged.

**Gate decision procedure** (recorded before any D/48 preparation):

| Outcome | When | Action |
|---|---|---|
| **proceed** | the measured per-step cost is within the practical budget | keep the prepared D/48 task; no code change |
| **harden** | the measured cost exceeds the budget | harden the candidate query (W4.4: mesh-tree/stencil) and re-measure task 0 |
| **restrict** | the campaign scope must shrink | restrict the authorized mesh/speed ladder; the scope choice stays with the user |

The gate is a **performance** gate only. The sub-grid caveat stands (D/32 cells
0.314 m vs chord 0.218–0.744 m; no resolved chordwise-physics claim) and the
kernel/width confound framing is unchanged.

## Model variants and formulation

Three `fvOptions` twins are rendered from the same configuration and differ
only in the blade subdictionary element/surface keys:

| Variant | Blade keys | Model |
|---|---|---|
| `fvOptions.ALM` | `elementType actuatorLineElement;` | actuator line (baseline) |
| `fvOptions.ASM` | `elementType actuatorSurfaceElement; nChordwise 5;` | no-mesh actuator surface |
| `fvOptions.ASM-MESH` | the surface keys plus `surfaceGeometry "constant/triSurface/phaseVI_blade.stl";` (and `kernel gaussian;` only for the ablation) | mesh-backed actuator surface |

**Formulation.** The mesh-backed variant implements the paper's chord-line blade
ASM (Yang & Sotiropoulos, arXiv:1702.02108v4) **extended to an imported
surface**: the blade load is mapped from the line elements onto the nodes of the
committed `phaseVI_blade` triangulation (element→patch association by radial
station, patch-area share per element) and distributed over the background cells
with the selected kernel (Eq. 18). It is explicitly **not a literal equation
port**: the paper's surface construction is replaced by the imported wetted
mesh, and the surface does not sample per-node inflow or recompute BEM loads
(the element BEM chain, chord-averaged inflow, dynamic stall, added mass and end
effects are unchanged). The surface is therefore a **distribution-only** model.

**Sub-grid caveat.** At D/32–D/64 the background cells are 0.314/0.210/0.157 m
while the blade chord is 0.218–0.744 m, so the imported surface is **sub-grid**:
the three-way comparison tests **model form** (how the load is distributed),
not resolved chordwise physics.

**Kernel/width confound and the Gaussian ablation.** The paper-cosine surface
(`kernel cosine`, default; support `2.5·h_i`) and the no-mesh ASM's mesh-only
Gaussian width (`kernel gaussian`; `ε_i = 2·cbrt(V_i)·meshFactor`) differ in
both kernel and width. `kernel gaussian` on the mesh-backed variant is the
**kernel-matched ablation** that narrows this confound (it does not eliminate
it: the no-mesh ASM uses one `ε` per element while the surface uses one per
node). It is an ablation, not a model, and is rendered only when selected.

**Pre-registered hypothesis.** Before the campaign, the expected direction and
approximate size of the geometry effect on the spanwise load are recorded here,
so the comparison tests a stated hypothesis rather than a post-hoc "the mesh is
better" claim:

- The imported-surface load is expected to shift the spanwise `c_ref_n` toward
  the blade **root transition and tip** first, where the chord-line element
  representation is coarsest, with the mid-span least affected.
- The expected size of the effect is of the order of the spanwise band
  (max(0.15, 20 % of measured)) or smaller, and **not** a resolved-chordwise
  redistribution; no agreement better than the documented band is promised a
  priori.
- The geometry effect is separated from the kernel/width confound by the
  Gaussian ablation above.

**MEXICO naming resolution.** The committed blade is the Phase VI
`phaseVI_blade` component; one STL serves both identical Phase VI blades
(azimuth is runtime). The retired `blade0/1/2` reservation encoded an un-sourced
per-blade assumption and is not re-used: a future MEXICO blade is a separate
`mexico_blade` component owned by the `mexico-validation` change, not by this
package.

**Prepared-only.** All prepared stages and arrays, including the ASM-mesh array,
are never submitted by this change; see the staged plan above.

### Rotational augmentation (Du–Selig) and the root-effect ablation

`actuator.rotational_augmentation` in `config/case.yaml` is rendered into every
`fvOptions` twin as an identical `rotationalAugmentation` block at the
**rotor-coeffs level**, mirroring `dynamicStall`. It is deliberately **not** a
blade key, so the three twins stay identical except for their element/surface
keys, and AFTAL forwards the block with the `rotorRadius`/`rootRadius` the
element needs:

```
        rotationalAugmentation
        {
            active off;
            model DuSelig;
            a 1;
            b 1;
            d 1;
        }
```

The committed default is **off**; the renderer turns it on only through
`--rotational-augmentation on`. The block is additive: with it absent or
`active off`, the element/line/turbine output is byte-identical to the
pre-change chain. A blade-level block would bypass AFTAL's forwarding and the
correction would be silently skipped (the proxy matrix caught exactly this), so
the block must stay at the rotor level.

**Formulation.** When active, the shared element chain applies the Du–Selig 3D
stall-delay correction in place, after the static coefficient lookup and before
dynamic stall (`turbinesFoam/src/fvOptions/actuatorLineSource/actuatorLineElement/`),
so the actuator line, the no-mesh surface and the mesh-backed surface all
inherit it with no per-model code:

```
CL,3D = CL,2D + fL (CL,p − CL,2D)
CD,3D = CD,2D − fD (CD,2D − CD,0)
fL = (1/2π)[ (1.6(c/r)/0.1267) · ((a − (c/r)^((d/Λ)(R/r))) / (b + (c/r)^((d/Λ)(R/r)))) − 1 ]
fD = (1/2π)[ (1.6(c/r)/0.1267) · ((a − (c/r)^((d/(2Λ))(R/r))) / (b + (c/r)^((d/(2Λ))(R/r)))) − 1 ]
```

with `CL,p = 2π(α − α0)`, `CD,0` the 2D drag at zero angle of attack,
`Λ = ΩR/√(U² + (ΩR)²)`, and `a = b = d = 1` (the paper defaults). The exponent
is `(d/Λ)(R/r)` for `fL` and `(d/(2Λ))(R/r)` for `fD`. This is the original
Du & Selig (1998) **prefactor** form: `1.6(c/r)/0.1267` multiplies the fraction
`(a − X)/(b + X)`, and `a`/`b` are the numerator/denominator constants, not an
exponent of `c/r`. It is reproduced by NREL `AirfoilPrep.py`, BYU `CCBlade.jl`,
Munduate (2002) Eq. 3.6, IOP 2024 Eq. (3) and Li/Liu/Yang (2022) *Energies*
15:6533. The split form printed by arXiv:1702.02108v4 Eqs. 11–12
(`(1.6(c/r)a − X)/(0.1267b + X) − 1`) is a transcription error and is **not**
implemented; see
`openspec/changes/rotational-augmentation/research-formulation-fidelity.md`.

**Sensitivity note and claim boundary.** The correction is applied **literally**
with no invented clamp and **no free-parameter calibration** (`a=b=d=1` only).
Near the tip the prefactor vanishes and `fL` tends to `−1/(2π)`, which reduces
the corrected outboard lift; `fD` is positive inboard and turns negative only in
a thin tip band (zero near `r/R ≈ 0.75` at the Phase VI `Λ`) — a
published-model characteristic that is recorded, not clamped. The end-effect
factor is applied **after** the augmentation hook (the paper's order), so the two
effects are not double-counted. Because the combined Du–Selig + dynamic-stall
model is not validated here and the affordable meshes are sub-grid, claims are
limited to trend, stall onset and agreement within the documented comparison
bands; no agreement better than those bands is promised a priori.

**Root-effect ablation.** `--root-effects off` renders `rootEffects off;` in
`GlauertCoeffs` as a **render-time** ablation, while the committed default keeps
`rootEffects on;` and `tipEffects on;`. It changes nothing in the committed case
or the primary fix; it exists so the end-effect confound is separated from the
augmentation attribution in the proxy matrix.

**Proxy matrix (W4).** The committed proxy harness
(`scripts/proxyRotationalAugmentation.py`, W4) renders three variants that differ
only in the augmentation switch and the root setting — `control` (off, root on),
`augmentation-on` (on, root on) and `augmentation-on + root-off` (on, root off) —
and chains them serially on the authorized development queue. The production
campaign stays **prepared-only**: no automated step of this change submits,
cancels or modifies a production job, and the committed case itself keeps the
augmentation off.

**Control gate and fail-loud criteria.** The harness evaluates the variants in a
fixed order and exits non-zero when a criterion is missed, naming the offending
variant and metric:

- *Control gate (mandatory, first).* The U13 `control` integrated `cp` must lie
  within 15 % of the converged baseline `cp = −0.0411`, i.e. in
  `[−0.0473, −0.0349]`. No other variant is interpreted until the control
  reproduces the failure.
- *Primary signal.* The integrated turbine `cp`/`ct`/torque over the short window.
  At U13 `augmentation-on` must make `cp` and `ct` **positive**; at U7 the
  `augmentation-on + root-off` ablation must **shrink** the −16 % power deficit
  toward or inside the ±15 % band.
- *Secondary signal.* The spanwise `c_ref_t` **sign** at 30/47/63/80/95 % span.
  At U13 mid-span `c_ref_t` must be `≥ +0.02` (above the `0.01` short-window
  drift tolerance), versus the control's `−0.063`.

**Comparison caveat (`c_ref_t` vs measured CT).** The simulated spanwise
`c_ref_t` runs ≈2× the measured `CT` while the integrated torque is low; this
definitional mismatch is recorded here and **not fixed** by this change. The
proxy therefore uses the integrated `cp`/`ct`/torque as the **primary** signal
and the `c_ref_t` **sign** only as secondary.

**Degenerate root profile.** The Phase VI blade's root elements use a two-point
`cylinder` placeholder (only ±180°). The Du–Selig correction is defined relative
to the profile's zero-lift reference, which does not exist for that table, so
`correctRotationalAugmentation()` skips any profile without a station in the
`[−10, 10]°` reference window rather than fabricating one (no invented clamp).
The lifting S809 sections are corrected as usual.

**Corrected-form proxy outcome (fidelity correction, 2026-09-24).** After
restoring the prefactor form (see **Formulation** above), the committed 0.25-rev
D/32 matrix was re-run on `sequana_cpu_dev` (build/test job `11600617`; proxy
jobs `11600623`, `11600630`, `11600635`). The control gate still passes (control
U13 `cp = −0.044809`, unchanged because augmentation is off), and the harness
still exits non-zero because the U13 augmentation-on `cp`/`ct` are not positive —
but the corrected form moves them from clearly negative to ≈0:

| U13 variant | `cp` mean (final row) | `ct` mean | mid-span `c_ref_t` |
|---|---|---|---|
| `control` | −0.044809 (−0.045859) | −0.015346 | −0.070378 |
| `augmentation-on` | **−0.000080** (−0.002094) | −0.000027 | **+0.305817** |
| `augmentation-on + root-off` | **+0.021690** (+0.019482) | +0.007428 | +0.436461 |

Before the correction (split form) the same variants gave U13 `cp` −0.051234 /
−0.033349 and mid-span `c_ref_t` +0.084376 / +0.188596. The U7 `cp` (final row)
was 0.309981 / 0.309268 / 0.336636 (control / augmentation-on / root-off); with
the corrected form it is **0.309981 / 0.344433 / 0.373306**, and the root-off
ablation shrinks the power deficit from −14.99 % (control) to +1.79 %, inside the
±15 % band.

The correction also moves the analytic factors to their primary-source shape at
`Λ ≈ 0.946`: `fL` now crosses zero at `r/R ≈ 0.90` (was `≈ 0.69`) and `fD` is
positive out to `r/R ≈ 0.75`, turning negative only in a thin tip band (was
`≈ 0.36`). Caveat: the U13 augmentation-on integrated signal is ≈0 — smaller
than the 0.25-rev window's observed ≈11 % systematic bias — so this short run
resolves only the sign shift (clearly negative → ≈0), not whether any residual
failure remains; the primary criterion is still reported unweakened.

## Model variants (A/B bench)

`config/model-variants.yaml` registers diagnostic arms as **v1.2 plus renderer
flag overrides**. No coefficient is fitted. Non-baseline variants are never of
record for v1.2; `summarizeBands.py` keeps its unchanged baseline-only gate.

| Variant | Exact renderer overrides | Reference / interpretation |
|---|---|---|
| `v1.2` | none | Model Definition v1.2 |
| `shen-tip` | `--end-effects-model Shen` | I10, Shen, Mikkelsen, Sorensen & Bak, *Wind Energy* 8:457–475 (2005); explicit `ShenCoeffs c1=0.125, c2=21` |
| `dag-sorensen-tip` | `--tip-correction on` | Dağ & Sørensen (2020), existing prescribed helical wake; other settings unchanged |
| `ring-sampling` | `--velocity-sample-radius 3.3 --n-velocity-samples 16` | v1.1 freeze: 16 equally spaced ring samples, radius **3.3 times local projection epsilon**, not 3.3 metres |
| `du-selig-ra` | `--rotational-augmentation on` | Du & Selig (1998); existing `DuSelig`, `a=b=d=1` |
| `ch-ra` | `--rotational-augmentation on --rotational-augmentation-model ChaviaropoulosHansen` | I7, original CH baseline `a=2.2, h=1, n=4`; Burgos Tafur et al. (2020), pp. 307–308 Eqs. (1)–(4); not yet A/B tested |

### Chaviaropoulos–Hansen rotational augmentation (I7)

Selecting `--rotational-augmentation-model ChaviaropoulosHansen` does **not**
activate RA: use `--rotational-augmentation on` as well, or select `ch-ra`.
The default render remains byte-identical, with inactive Du–Selig. Existing
Du–Selig and Lindenburg solver selections retain their arithmetic.

Source: Burgos Tafur, Daniele, Stoevesandt & Thomas, *On the calibration of
rotational augmentation models for wind turbine load estimation by means of CFD
simulations*, Acta Mechanica Sinica **36**, 306–319 (2020),
[DOI 10.1007/s10409-020-00949-0](https://doi.org/10.1007/s10409-020-00949-0).
Verified locally in `turbinesFoam/articles/Sci-Hub. _ 2,.pdf`, pp. 307–308:
Eqs. (1)–(2) give the additive lift/drag correction, Eqs. (3)–(4) give the factors,
and the next paragraph specifies the **original** CH constants (not the paper's
later calibrated tables). That paper cites Chaviaropoulos & Hansen (2000),
J. Fluids Eng. 122:330–336, DOI 10.1115/1.483261; the primary source itself was
not retrieved here. The implementation is:

```text
fL = fD = a*(c/r)^h*cos(theta)^n       a=2.2, h=1, n=4
Cl_inv = 2*pi*rad(alpha - alpha0)
Cl3D = Cl2D + fL*(Cl_inv - Cl2D)
Cd3D = Cd2D + fD*(Cd2D - Cd(alpha=0))
```

The inviscid lift deliberately uses Du–Selig's existing **fixed 2π slope** and
polar zero-lift angle, not a new attached-range slope fit. The drag increment
has a **plus** sign and uses the same polar interpolated at **zero angle**, unlike
Du–Selig's minus sign and zero-**lift** drag reference. Placeholder profiles
without a zero-lift reference are skipped, as for Du–Selig; there is no extra
radial or angle-of-attack taper/clamp.

`theta` is immutable local twist **without collective pitch**. The source calls
it “local twist angle” but the cited passage does not explicitly resolve pitch;
excluding pitch is the selected implementation convention. Phase VI's section
geometry stores `-(twist + pitch)`; the line's existing interpolation is reused,
then the signed `pitchOffset` is subtracted to recover `-twist`. For the fixed
integer exponent 4 this sign does not change the factor. The CH block explicitly
renders the literature coefficients and the geometry offset in all three twins:

```text
rotationalAugmentation
{
    active on;
    model ChaviaropoulosHansen;
    a 2.2;
    h 1;
    n 4;
    pitchOffset -3;  // degrees, signed geometry convention, not a fitted coefficient
}
```

Other actuator-line users must supply the signed collective `pitchOffset` if
section geometry includes it (default 0). Direct element dictionaries selecting
CH must supply `localTwist` in degrees. CH rejects nonfinite/negative `a` or `n`,
nonfinite/nonpositive `h`, and nonfinite twist or twist outside [-90,90] degrees
with a dictionary error. The baseline values above are the only registered arm;
no coefficient is fitted. The stateful polar/geometry hook's numerical reference
is pinned in `tests/test_rotational_augmentation_ch.py` (not a solver execution).

Build only into `runs/lib-flags` while production jobs use the installed library.
Set `LIB_DIR=$PWD/runs/lib-flags` when launching `variant-run.slurm` to prepend
that directory to `LD_LIBRARY_PATH`; it must contain `libturbinesFoam.so`.
Without `LIB_DIR`, library resolution is unchanged. This arm is implemented
behind a flag, **not yet A/B tested**; implementation is not a validation claim.

**Shen is not a pure tip substitution:** selecting the solver's Shen model also
replaces the hub/root loss formula. The on/off root and tip switches remain on.
`--end-effects-model Glauert|Shen|liftingLine` selects existing solver models;
the default Glauert render is byte-identical. `liftingLine` is available but is
not a registered arm in this first bench. Later C2–C4 arms belong in the same
registry only after their renderer switches exist.

From the Phase VI directory, validate an arm **before submitting**:

```sh
VARIANT=ring-sampling sh scripts/slurm/variant-run.slurm --check
# Submit manually only after preflight (84 tasks, no --nodes):
sbatch --export=ALL,VARIANT=ring-sampling,MODEL=alm,SPEED=7,SEQUENCE=S scripts/slurm/variant-run.slurm
python3 scripts/checkModelDefinition.py runs/alm-U7-coarse-seqS-var-ring-sampling --variant ring-sampling
python3 scripts/summarizeVariants.py results/cmp-baseline results/cmp-ring
```

Unknown variants are refused before module loading or case preparation. The
launcher accepts the v1-2-run environment (`MODEL`, `SPEED`, `SEQUENCE`, optional
`REFINE_LEVEL`, `DELTA_T`, `END_REVS`, `POLAR`, `LABEL`, `LIB_DIR`), defaulting `LABEL` to
`var-<variant>`. It passes explicit baseline switches plus the registry overrides
through `runPhaseVI.sh`; no rendered file is hand-edited. The runner also accepts
`--end-effects-model`, `--velocity-sample-radius`, `--n-velocity-samples`,
`--rotational-augmentation-model` directly;
legacy `--submit` refuses these rather than dropping them. Existing `--restart`
refusal on written state remains: use a fresh label for a new arm.

The summary prints one table per sequence/speed, with P, T and five c_n errors
in percent versus experiment; parentheses give the change from the same model's
v1.2 row in **percentage points**. Missing values or missing/ambiguous baselines
show `n/a`. Drifting baselines are not used as references. DRIFT and own-variant
NON-CONFORMING rows are marked; nonconformance exits 1. Identity comes from
`run.json`'s optional `variant`, the default `var-<variant>` label, or unique
conformance. With a custom label, record `variant` in run metadata if an invalid
arm must still be identifiable. No checker or summary writes run data.

## Definition conformance

```sh
python3 scripts/checkModelDefinition.py runs/alm-U7-coarse-d1-pdrag
python3 scripts/summarizeBands.py results/U7-H
```

### Numerical ladder (R1)

```sh
python3 scripts/compareLadder.py --reference /tmp/cmpH_d1 --runs /tmp/cmpH_dt05 /tmp/cmpH_l1
```

Read-only. Each argument is a `comparePhaseVI.py --out` directory; the run directory, speed,
sequence and averaging window come from its `metrics.json`. Prints P, banded thrust and the
dimensional F'n at r/R 0.47/0.63/0.80/0.95 (reusing `compareSectionLoads.py`) for every run and
their % change against the reference; exit 0 when every |change| < `--tolerance` (default 2 %),
1 otherwise, 2 on inputs that do not share speed, sequence or thrust scope.

`diagnoseElementResiduals.py` accepts `--revolutions DISCARD END`, `--allow-drift` and
`--allow-short-window` (the 4-revolution T4 lag run: `--revolutions 2 4 --allow-short-window`);
the defaults keep the configured window and both refusals.

### Uncertainty (R6)

```sh
python3 scripts/quantifyUncertainty.py --run-dir runs/alm-U7-coarse-d1-pdrag --sequence H --speed 7
# Sequence S away from 7 m/s: the committed S tables hold 7 m/s only, use the archive tables
python3 scripts/quantifyUncertainty.py --run-dir runs/alm-U5-coarse-seqS-v12 --sequence S --speed 5 \
    --experiment-dir data/experiment/uae6-archive
```

The run uses the nominal wind speed while the tunnel's measured speed (`VTUN`,
e.g. 7.049 m/s in `h0700000`) differs slightly; rpm and rho are already the measured
values. The report adds a `VTUN correction` block: the simulated value scaled by the
BEM response at fixed rpm to U x VTUN/U_nominal, beside the raw difference and judged
against the same combined uncertainty. The raw verdict stays the comparison of record.

`summarizeBands.py` marks a comparison whose window `comparePhaseVI.py` recorded as
drifting (`window: DRIFT ... -> NOT OF RECORD`, exit 1 unless `--allow-nonconforming`).

Read-only. For power, blade thrust and the chord-referenced c_n at r/R
0.30/0.47/0.63/0.80/0.95 (the `comparePhaseVI.py` definitions) it prints
`sim - exp` with its combined uncertainty: experiment repeatability (file-to-file
scatter of the raw UAE6 Parquet files `h0700000/h0700001/...`, read from
`turbinesFoam/articles/uae6/parquet` or `--archive-dir`; "not available" with the
searched path when absent; a single file falls back to the in-file
autocorrelation standard error of the per-revolution means), simulation
averaging window (definition window against the windows starting 2 and 4
revolutions later), and BEM-estimated blockage sensitivity for inflow +1 %/+2 %
(`bemPhaseVI.py` at the measured rpm; one-sided bound; U^3/U^2 bound if the BEM
is unusable). The verdict says "agrees within the combined numerical and
experimental uncertainty" only inside the quadrature sum (`--coverage k`,
default 1). Exit **1** for a non-conforming run unless `--allow-nonconforming`
(output then tagged `[not of record]`), **2** for missing input.

`config/model-definition.yaml` records v1.2 expected effective values and cited
solver defaults. An absent key uses its solver default; absence without a known
default is a mismatch. Point sampling (`velocitySampleRadius 0`) is frozen;
`nVelocitySamples` is inert and not checked. The checker accepts `--definition PATH`
and exits **0** when all runs conform, **1** for mismatches, **2** for unreadable or
malformed input. It never modifies runs.

For fixed-width refinement, `meshFactor` must be `2**level`. The checker reads
`refine_level` from `run.json` when present, otherwise the runner's `-r<N>` name
token (including before a label), otherwise level 0. `blade_dz` must be 0.05 when
recorded and non-null; missing layout metadata is not a geometry certification.

`summarizeBands.py` checks every run in `metrics.json`'s
`models.<model>.run_dir`, already written by `comparePhaseVI.py`. Missing provenance
is UNKNOWN and not of record. Non-conforming comparisons retain all diagnostic
band lines with `[not of record]` and exit **1**. `--allow-nonconforming` permits
exit 0 for diagnostics only; it does not remove the not-of-record labels.

## Comparison

```sh
scripts/comparePhaseVI.py --alm-dir runs/alm-U7-coarse-s0 \
                          --asm-dir runs/asm-U7-coarse-s0 \
                          --asm-mesh-dir runs/asm-mesh-U7-coarse \
                          --speed 7 --sequence H --sign-gate
```

Reads `postProcessing/turbines/0/turbine.csv` and
`postProcessing/actuatorLineElements/0/*.csv`, merges them with the committed
experimental CSVs, and writes `turbine_comparison.csv`,
`spanwise_comparison.csv`, `metrics.json`, `report.txt` and (with
`--sign-gate`) `sign_gate.json` into `--out` (default
`results/U<speed>-<sequence>/`). It averages revolutions 4–12 after discarding
revolutions 0–4, flags power/thrust drift above 1 %, and interpolates
`c_ref_n`/`c_ref_t` to 30/47/63/80/95 % span.

`spanwise_comparison.csv` carries **two reference frames**. The chord-line
`c_ref_n`/`c_ref_t` columns (against the measured `CN`/`CT`) are the
section-load comparison. The appended `c_ref_n_plane`/`c_ref_t_plane` columns
(against the measured `CTH`/`CTQ`) are the **plane-of-rotation** pair, which is
what produces the rotor thrust and torque, so the **power** comparison is read
from the plane columns. The archive-only plane channels (`CTH`/`CTQ`/`QNORM`)
are joined onto the committed workbook tables by `extractUAE6Reference.py`.
The extractor also writes enriched raw-archive S and H tables at every speed
5–25 m/s (including S 5/6/8 and H 5), plus H's measured five-hole-probe angles:

```sh
python3 scripts/extractUAE6Reference.py --sequences s h --archive-only
python3 scripts/extractUAE6Reference.py --sequences s h --archive-only --check
python3 scripts/extractUAE6Reference.py --cross-check
python3 scripts/compareSectionLoads.py --alm-dir runs/alm-U7-coarse-seqS-v12 \
    --sequence S --experiment-dir data/experiment/uae6-archive
```

`--archive-only` avoids changing the separate workbook tables; omitting it keeps
the previous enrichment behavior. Select both sequences when reproducing the
combined hash inventory. `--check` never writes; `--cross-check` prints maximum
relative differences for `cth`/`ctq`/`qnorm_pa` at S7 and H7 (all six are zero).
The S7 force-times-arm output is identical between reference directories; the
frame residuals differ because archive `cn`/`ct` retain more digits than the
workbook's four decimals (including `R_exp` 0.870 versus 0.871 at r/R 0.63).

`diagnoseElementResiduals.py` and `compareInflowAngle.py` also accept
`--experiment-dir`, with their previous defaults unchanged. The latter reads
`cth`/`ctq`: it compares a **force-direction proxy, not measured probe inflow**.
`sequence_H_probes.csv` retains the archive-described local and spanwise flow
angles at 34/51/67/84/91 % span, without an invented rotor-plane transform.
Do not use the inflow tool's historical H7 uninduced-angle column as an H5
kinematic prediction. Probe interpretation and H5 run/configuration are T13,
not part of this extraction. Details: [archive provenance](data/experiment/uae6-archive/PROVENANCE.md).


For the mesh-backed `asm-mesh` model the surface station table carries only the
plane decomposition, so its chord columns are a declared open defect while its
plane columns are exact.

With `--asm-mesh-dir` the comparison is **three-way**: it additionally reads the
window-filtered `postProcessing/bladeSurface/*.csv` station table (the
per-node `*_nodes.csv` output is not a station table), merges station rows by
station id, and maps each station's `root_dist` to r/R with the existing
element formula (no coefficient definition is redefined). Turbine metrics come
from the same `turbine.csv` (the surface moment is already in the AFTAL
torque). A missing or incomplete ASM-mesh directory fails loudly
(`EXIT_MISSING_INPUT`), never falling back to a two-model merge. `metrics.json`
records the staged STL hash (`staged_stl_sha256`) and the surface kernel
(`surface_kernel`, `cosine` default) for the fair-comparison check.

Metric definitions (F1-corrected, fixed against the NREL reports; printed in
every output):

```
q_dyn   = 1/2 * rho * A * Uinf^2          R = rotorRadius, A = pi R^2
Q       = ct * q_dyn * R                  shaft torque (ct = torque coefficient)
P       = cp * q_dyn * Uinf               cp = ct * TSR
T_blade = sum_blades cd_blade * q_dyn     blade-only thrust (headline)
T_rotor = cd * q_dyn                      hub included; labelled secondary
rho     = WTBARO / (287.058 * (WTATEMP + 273.15))   from the measured row
```

`--thrust-scope blade|rotor` selects the headline thrust (default blade) and
`--match-eaeroth-span` restricts the blade sum to `r/R ≥ 0.25` to match the
EAEROTH pressure integration. `--rho auto|<kg/m³>` selects the measured-row ideal-gas density (default) or a
user value.

Bands (fixed in code and reported with every result): turbine
power/torque/thrust ± 15 %; spanwise max(0.15, 20 % of measured). Claims are
limited to trend, stall onset and agreement within these bands; no sub-5 %
agreement is promised a priori.

Spanwise CM is **excluded**: the element CSV has no `cm` column (follow-up
change adds `momentCoefficient_` to the element writer). The measured CM
values are still written to `metrics.json` for reference.

Exit codes: **1** missing/incomplete input or failed sign gate, **2** averaging
window shorter than four revolutions without `--allow-short-window`, **3**
configured TSR does not match the run, **0** comparison produced (band and
drift flags are reported, not hidden).

The **sign gate** (`--sign-gate`, run on the Stage 0 D/32 7 m/s runs) requires
the run TSR to match the configured value, `cp`/`cd` > 0, and positive
`c_ref_n`/`c_ref_t` at all five stations. Production submission refuses without
a passing `results/U7-H/sign_gate.json`.

## Modelling limitations

- Sub-cell ASM chord strips: at every affordable mesh (D/32–D/64) the
  chordwise strips are sub-grid, so the comparison tests chord-averaged inflow
  and the ALM-vs-ASM load shift, not a chord-resolved surface.
- **Sub-grid imported surface**: the mesh-backed ASM is sub-grid too (cells
  0.314/0.210/0.157 m versus chord 0.218–0.744 m); the three-way comparison
  tests model form, not resolved chordwise physics.
- **Kernel/width confound**: the paper-cosine surface and the no-mesh Gaussian
  ASM differ in kernel and width; the `kernel gaussian` mesh-backed run is the
  kernel-matched ablation, not a model, and narrows but does not eliminate the
  confound.
- **Distribution-only**: the surface redistributes the element load; it does
  not sample per-node inflow or recompute BEM loads.
- URANS `kOmegaSST` cannot capture deep-stall unsteadiness or hysteresis; the
  separated high-speed points (13–25 m/s) are trend and stall-onset evidence
  only.
- The tower is not modelled (rotor + hub only); EAEROTH is a blade pressure
  integration and the measured loads include tower shadow.
- Blockage is not simulated (uniform free box versus the NASA-Ames test
  section); documented, not corrected.

## Data and tests

`data/geometry/` (TP-500-29955 Table A-1), `data/polars/` (TP-500-29955 A-3..A-8
and TP-442-7817 B1..B4), `data/experiment/` (WDH `wt_loads_statistics.xls`,
sheet `ldsmean`, 0° yaw) and `data/s809/` (Somers, NREL/SR-440-6918, Table 2)
each carry a `PROVENANCE.md` with DOI/URL, source sha256, sheet/table, row
selection, units and extraction date. No report PDF or workbook is committed.
The imported blade surface itself is the committed `phaseVI_blade` component in
`turbinesFoam/geometry/` (binary STL + §4.6 metadata + `PROVENANCE.md`), built
by the pure-Python loft from `data/geometry/phaseVI_blade.csv` and the committed
S809 coordinates; `runPhaseVI.sh -m asm-mesh` stages it, hash-checked, into each
run directory.

```sh
python3 -m pytest turbinesFoam/tests/test_phasevi_case.py \
                    turbinesFoam/tests/test_phasevi_data.py \
                    turbinesFoam/tests/test_phasevi_compare.py \
                    turbinesFoam/tests/test_blade_stage.py -q
python3 -m pytest turbinesFoam/tests/ -q   # solver-driven suites auto-skip without OpenFOAM
```

The Phase VI tests are pure Python (no OpenFOAM): the case/data contracts plus
the comparison tooling (F1 metric formulas, `root_dist`→r/R mapping, drift
flag, fail-loud exit codes, sign gate, three-way dry merge on synthetic
fixtures including the real `bladeSurface` CSV schema) and the STL staging
helper (hash match, mismatch/missing-source abort, run-directory layout). The
upstream turbinesFoam tutorial tests are skipped when `WM_PROJECT_VERSION` is
unset.

## Attribution and license

The case generator and tooling in this package are adapted from
[`mttbrbr/single-actuator-line`](https://github.com/mttbrbr/single-actuator-line)
(main `8284be8c...`), GPL-3.0-or-later. The adaptation retains that license:
this package is distributed under **GPL-3.0-or-later**, consistent with
`turbinesFoam` (see `turbinesFoam/LICENSE`).

Data: rotor geometry and S809 polars are derived from the public U.S. Government
reports NREL/TP-500-29955 (DOI 10.2172/15000240), NREL/TP-442-7817 and — for the
committed S809 blade coordinates (`data/s809/`) — Somers, NREL/SR-440-6918; the
measured load statistics come from the public NWTC WDH dataset
(DOI 10.21947/WDH-DAP/1910052). No report PDF or workbook is redistributed —
only derived numeric tables with per-directory `PROVENANCE.md` (source URL,
sha256, sheet/table, row selection, units, extraction date).

The mesh-backed surface model (`bladeSurfaceSampler` / `bladeSurfaceSource`) and
the `phaseVI_blade` geometry component are **fork extensions**, not part of
upstream `turbinesFoam`. This package is validated against the pinned `of-plugins`
commit `26a1f46d79ff1481bba8d7fe2866516c367de232` (*feat(turbinesFoam): add
actuator surface element type*), which carries the blade actuator-surface patch
(`elementType actuatorSurfaceElement;`); later S2 commits add the imported
surface distributor, the geometry component and the ASM-mesh variant.
