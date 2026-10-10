# IEA 15 MW ALM — platform FROZEN (2026-10-09)

Single starting point for the ASM solver analysis, the ALM/ASM/ASM-mesh
comparison (issue #9) and the FSI project. Everything here is measured; nothing is
extrapolated without saying so.

## What the platform is

| piece | frozen value |
| --- | --- |
| mesh | snappy, `TURBINE_SNAPPY_LEVEL=2` (L2), finest cell **1.87 m**, **2 363 760 cells** |
| domain | upstream 3D, downstream 7D, lateral ±3D (D = 2R = 241.35 m) |
| ranks | **96**, `method simple`, `n (4 6 4)` — 96 `processor*` directories |
| rotor | 7.518 rpm, R = 120.67532 m, TSR **8.9131856**, cone 4°, pitch 0° |
| inflow | 10.659 m/s uniform, rhoRef 1.225 |
| time step | **0.0187 s** (0.95 × finest cell / tip speed). The `dt/2` run used 0.00935 s and changed nothing |
| horizon | **20 revolutions** (159.623 s); the plateau is readable from rev 13 |
| writing | every 60° (1.330141 s) |
| model | `actuatorLineElement`, 147 elements, sampling radius 3.3, 16 velocity samples |
| tip loss | `endEffects` **Glauert, tip + root on** |
| off | `dynamicStall`, `rotationalAugmentation` (both `active off`) |

## The converged and validated numbers

| quantity | value |
| --- | --- |
| **converged cp** | **0.5344** (dt) / 0.5335 (dt/2, extrapolated) → use **0.534** |
| cd (thrust) at rev 20 | 0.7711 |
| ct (torque) at rev 20 | 0.0602 |
| spanwise integration (internal control) | C_T 0.7755, C_Q 0.0600, C_P 0.5345 — reproduces the module to 0.4 % |

Both axes are closed:

- **spatial**: four screening points (D/32 7.50 m → L2 1.87 m), steps
  −2.59 / −0.95 / −0.29 %, fit `cp(h) = cp∞ + C·h^p` → **p = 2.82**, `cp∞ = 0.5770`
  (at 4 revolutions), rms 0.00055; the mesh residual at L2 is **+0.14 %**, so L3
  (~50 h) buys ~0.1 %.
- **temporal**: the dt plateau 0.53633 against the dt/2 plateau 0.53444. The direct
  difference (−0.35 %) is almost all convergence the dt run still owed (its
  extrapolated remaining drop is 0.40 %); at their asymptotes they read 0.5342
  against 0.5335, i.e. **−0.13 %, inside the 0.3 % criterion**. The time step does
  not carry the result.

**Validation**: cp 0.534 against the **OLAF free wake 0.5312 is +0.6 %**.
Against CCBlade/BEM 0.4910 it is **+8.8 %**, and that is the **model** residual:
our `c_t` over the BEM is 1.085 / 1.108 / **1.129** (r/R 0.3-0.5 / 0.5-0.7 /
0.7-0.9), growing outboard, with `c_n` +2.7 % and Δα +0.43°.

## How to read a run (and the traps)

1. **A resumed run splits its history** into `postProcessing/turbines/<timeName>/`,
   named after the run's start time. Union them with
   `turbinesFoam/validation/tools/rev_history.py` (numeric order, revolution
   rebuilt from the cumulative `angle_deg`, and the one-row `endTime` stub
   discarded). The names sort wrongly as text: `"31.9209"` after `"159.6232"`.
2. For the spanwise: `scripts/compare_spanwise.py --run-dir <dir> --time <timeName>
   --revs 2`. Without `--time` it reads the history *from before the resume* and
   lies.
3. `turbinesFoam/validation/tools/case_state.py <dir>` answers "how far did it get".

## What is NOT established

- **ASM**: MEASURED on this platform (2026-10-09) — see
  `odd/tasks/iea15mw-asm-l2-validation.md`: cp 0.57431 against the ALM's 0.53651,
  **+7.05 %**, produced by the surface seeing +0.30 deg of local alpha with the
  load following the section lift curve (no unexplained multiplier, no tip
  artifact, no bookkeeping defect). The old ALM/ASM pair (0.871-0.903) is not the
  platform answer, and the free-wake comparison is a shape oracle, not a truth
  ordering. Still open: the stalled root's `cl = 0.0000` in the polar table, on
  BOTH arms, and the ASM+mesh arm. The deposit fix (`5026c97`) stays mandatory and
  as of `c7eda86` the L2 runner can no longer substitute ALM for a requested ASM
  (it did until then); ASM+mesh values from before `5026c97` cannot be cited: the
  flow received 33 % → 0.1 % → 0 % of the blade load. The ASM's `moment()` also
  omits the pitching moment (~0.1 %).
- **rotationalAugmentation**: switching it on with `a=b=d=1` raises cp by +0.74 %
  and acts almost entirely at the deep-stall root (α 52-56° at r/R < 0.1); it does
  **not** reproduce the +49…+71 % of inboard tangential force the URANS-vs-BEM
  paper pairs show. It needs **coefficients fitted per profile**.
- The **outboard tangential excess** over the BEM (+10-13 %) is not explained by
  the BEM's known deficiency, which is inboard and reverses outboard.

## Starting point for the ASM

Same platform, same L2 mesh, same domain, ranks, horizon and configuration; only
the element type changes. `run_iea15mw_case.sh` reads `TURBINE_MODEL` (default
`alm`), so nothing in the runner needs editing:

```sh
TURBINE_MODEL=asm TURBINE_N_CHORDWISE=5 \
  TURBINE_RUN_DIR=runs/iea15mw-asm-l2 TURBINE_TOTAL_REVS=20 \
  sbatch --time=08:00:00 scripts/slurm/l2-long.slurm
```

(`l2-long.slurm` re-states mesh, snappy level, domain, decomposition and write
interval to the frozen values. `asm` does not default to snappy, hence the
explicit level inside the script.)

> **Fixed on 2026-10-09 (`c7eda86`).** This recipe was silently broken when it was
> written: `l2-long.slurm` exported `TURBINE_MODEL=alm` unconditionally, which
> overrides the value passed on the submit line, so an ASM submission produced a
> second **ALM** run under `runs/iea15mw-asm-l2` — same exit code, wrong physics.
> The model is now overridable (`${TURBINE_MODEL:-alm}`) and the ASM recipe lives
> in the script header. Check the run's `system/fvOptions` for
> `elementType actuatorSurfaceElement` before trusting any ASM number.
> Tracked in `odd/tasks/iea15mw-asm-l2-validation.md`.

First two things to verify, in this order:

1. the deposit partition-of-unity test (serial and 2-rank) — it is the check that
   catches the rotation bug the fix closed;
2. the ASM cp against the ALM **on this same mesh**. The old ALM/ASM pair
   (0.871-0.903 of the ALM) was measured on a different mesh and with a different
   sampling argument, so it is not the platform answer.

## Where everything is

- `odd/tasks/iea15mw-alm-convergence-series.md` — both axes, the screening, the
  dt/2 and RA verdicts, the disk cleanup
- `odd/tasks/iea15mw-references.md` — the validated configuration and references
- `odd/tasks/iea15mw-asm-mesh-cp-diagnosis.md` — issue #5 and the deposit fix
- `odd/issues/asm-mesh-residual-vs-alm.md` — issue #9
- `analysis/spanwise-references.csv`, `scripts/compare_spanwise.py`
- on disk: `runs/iea15mw-screen-m3-l2` — **note it currently holds the dt/2
  continuation** (25 revolutions, `deltaT 0.00935`, `endTime 199.52`; the dt
  revolutions 1-20 are in `postProcessing/turbines/{0,31.9209}`) — and
  `runs/iea15mw-l2-ra` (the rotational-augmentation A/B).
