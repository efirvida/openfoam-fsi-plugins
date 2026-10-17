# Phase VI FLOWUnsteady diagnostic — NOT validated for production

> **Status update (supersedes the `turbine_flag=true` evidence and the "sign unresolved" conclusion below).**
> The working configuration is `turbine_flag=false`, pitch = -(twist+3 deg), `Vinf=[-7,0,0]`, `CW=false`, positive RPM, torque reported as -torque.
> `signScan.jl` (wake-free scan of 16 combinations) shows only this one gives a physically consistent global blade force; with `turbine_flag=true` the tangential
> component of `DistributedLoad` is flipped (drag/lift 0.74 instead of ~0.1; force.velocity < 0). `rotationProbe.jl` confirms the rotation sense. Smoke 11617359 (2 rev,
> 48 threads): force.velocity 7306 W vs monitor 7334 W, both positive. Production runs use `scripts/slurm/flowunsteady-production.slurm`
> (`--nodes=1 --ntasks=24 --time=10:00:00`, owner exception: with `--ntasks` alone Slurm spreads the tasks over several nodes). The rest of this file is kept as the history of the first smoke.

The driver completed a two-revolution UVLM + rVPM smoke test, but **did not
establish a valid extracting-turbine convention**. Do not use it as the external
reference or launch the four production combinations yet. No turbinesFoam model
or installed Julia package was changed.

## Reproduce the smoke check

From the repository root:

```sh
python3 turbinesFoam/validation/phaseVI/scripts/buildFlowUnsteadyDatabase.py \
  turbinesFoam/validation/phaseVI/flowunsteady/runs/db-total --drag total
# Use --drag pressure and a different database directory for the other polar.
sbatch --output=turbinesFoam/validation/phaseVI/flowunsteady/runs/%j.out \
  --error=turbinesFoam/validation/phaseVI/flowunsteady/runs/%j.err \
  turbinesFoam/validation/phaseVI/scripts/slurm/flowunsteady.slurm \
  turbinesFoam/validation/phaseVI/flowunsteady/runs/db-total ds=on 2 UNIQUE_TAG
python3 turbinesFoam/validation/phaseVI/flowunsteady/check_smoke.py \
  turbinesFoam/validation/phaseVI/flowunsteady/runs/UNIQUE_TAG
```

Arguments to `phaseVI.jl`: `DB_DIR ds=on|off NREVS TAG`. Tags cannot contain path
separators; an existing run is rejected. The repository already ignores `runs/`.
The Slurm launcher uses 48 tasks as 48 Julia threads, not MPI processes, and
refuses multi-node allocations. Always check the actual allocation with
`sacct -j JOB_ID --format=NodeList`.

`check_smoke.py` is read-only: it reports the last-revolution means from
`power.csv`, cross-checks CT/CQ against the native convergence CSV, and exits 1
if the geometry or physical extraction sign fails. A coefficient-band miss is
reported separately; even passing this diagnostic would not establish wake
convergence.

## Observed evidence (2026-10-16)

Both jobs used 48 allocated CPUs on **sdumont6050**, confirmed by `sacct`.

| Job / tag | Result |
| --- | --- |
| 11617318 / `smoke-total-ds` | +x inflow; PyCall/NumPy finalizer SIGSEGV at 0.306 rev; Slurm FAILED, exit 0:11, elapsed 3:13 |
| 11617324 / `smoke-total-ds-minusx` | -x inflow; completed 2 rev, Slurm COMPLETED 0:0, elapsed 11:51; extraction check FAILED |

The retry uses automatic GC disabled during threaded VPM kernels and explicitly
collects between steps on the calling thread. This avoids the observed PyCall
finalizer crash in this smoke, but is not a general thread-safety guarantee.

Second-run last-revolution means (total drag, Du–Selig on):

| Quantity | Value |
| --- | ---: |
| TSR from measured 71.878 rpm, R=5.029 m, U=7 m/s | 5.40765 |
| Native turbine-normalized CT | 0.601370 |
| Native turbine-normalized CQ | 0.080770 |
| CP = TSR × CQ | 0.436775 |
| Native Q | +975.50 N m |
| Monitor-derived Q × omega | +7342.67 W |
| Independent global force · rotational velocity diagnostic | -7314.73 W |
| Global Fx | -1444.24 N |

The native rotor monitor receives `V_inf=7.0, turbine=true`; without these it
would report propeller-normalized coefficients. Its `eta` column remains the
propeller efficiency formula and **is not turbine CP**. Physical motion direction
is measured with a finite `vlm.rotate` probe, not inferred from the `CW` label.
The force/position runtime phase introduces about a cos(5 deg) magnitude offset
in the work diagnostic; it cannot explain or reverse the negative sign.

CT/CQ are above the requested 0.45–0.47 / 0.065–0.070 band and positive native Q
does **not** agree with positive physical rotor work. These are short, still
fountain-suppressed wakes, not converged literature comparisons. No successful
sign combination is claimed. Further package-level turbine force/kinematics
investigation needs a separate scoped decision; do not silently invert the
reported coefficients to match the targets.

## Geometry and recorded settings

Tested combination: `CW=false`, positive RPM, `turbine_flag=true`, zero precone,
freestream `[-7,0,0]` in the retry (FLOWVLM initializes the shaft along -x).
The database remains untouched. The driver reads it using FLOWUnsteady readers
and converts the two distributions before generating the rotor:

- Input pitch = **−(twist + 3 deg)**: `FLOWVLM2OCCBlade` negates it in turbine
  mode, so the lookup angle is `phi − (twist + 3 deg)`.
- Input sweep = **+chord_mount × chord**: `_generate_blade` negates sweep.
  The original negative database sweep would put LE aft of the axis. Assertions
  on the actual generated blade verify LE x < 0 < TE x; `geometry.csv` archives
  those actual endpoints. This verifies the **sweep sign**, not an exact
  pitch-axis rotation of all section coordinates at nonzero twist.

Each run archives the untouched database, transformed geometry, `settings.toml`,
the driver via `save_code`, native FLOWVPM settings, and both monitor CSVs.
The driver uses n=50, 72 steps/rev, 2 particles/step, RK3, SFS_none, inviscid VPM,
R/10 surface smoothing, relaxation 0.5, Viterna on, Prandtl off, unsteady shedding
on, starting vortex off, and rotorhover's fountain suppression through 3 revs.
All case constants follow the supplied measured H0700000 values; 71.878 rpm is
also the measured entry in `config/case.yaml`, not the spec's nominal 72 rpm.
Neither DS/drag choice is claimed to be Mehr's unspecified reference setting.

## Timing estimate — not permission for production

Solver + monitor time was **663.52 s / 2 rev = 331.76 s/rev**. Revolution 1 cost
177.09 s and revolution 2 cost 486.31 s, so multiplying the average by five is
not credible. Linear growth of per-revolution cost with wake age extrapolates to
**15685.8 s = 4.36 h for 10 rev**, excluding import/startup. This two-point
extrapolation is uncertain (GC, FMM and wake growth may change the scaling).
For a future, separately approved run, a provisional allocation is 48 tasks,
`--partition=sequana_cpu --time=08:00:00`, with the single-node guard retained.
Do not use the 18-minute dev launcher default for 10 revolutions.

## Scope handoff

S1/S2 respected; S4 inputs and S5 smoke provenance covered. S3/T2 has runnable
diagnostic infrastructure, but S3/T3's turbine sign/target check is unresolved.
T4's four production runs and T5's station comparisons were not attempted.
Repository-wide changelog/tool registration and tests outside this directory
were intentionally not edited: they are outside the authorized surface.
