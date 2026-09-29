# HANDOFF — Phase VI tip correction (Dağ & Sørensen 2020)

**Read this first. It is self-contained: a fresh session needs nothing else to
start.**

Repo root: `/scratch/leahk/eduardo.donestevez/simulations/tmp/of-plugins`
Package: `turbinesFoam/validation/phaseVI/`

---

## 1. The goal, in one line

**Implement the Dağ & Sørensen 2020 induced-velocity tip correction in the
turbinesFoam ALM, turn the Glauert tip loss off, and show that the 7 m/s Phase VI
power/torque closes from −7.6 % toward the measurement.**

## 2. Where the diagnosis ended (all measured, all recorded)

The Phase VI 7 m/s campaign (coarse D/32, Sequence H, revs 4→12, measured
reference = 5.95 kW / 789.9 Nm / 1132 N):

| polar | arm | %P | %T |
|---|---|---|---|
| OSU Re=1e6 | A (aug-on, tip-**ON**, root-off) | **−7.19** | +2.63 |
| OSU Re=1e6 | A′ (aug-on, tip-off) | +19.45 | +23.98 |
| OSU Re=1e6 | C′ (aug-off, tip-off) | +14.28 | +18.79 |
| CSU Re=0.65e6 | **A (tip-ON)** | **−7.61** | **−2.38** |
| CSU Re=0.65e6 | A′ (tip-off) | +16.76 | +18.40 |
| CSU Re=0.65e6 | C′ (aug-off, tip-off) | +8.63 | +11.64 |

**Root cause — the tip.** With the frame-fixed spanwise comparison (legitimate
now), our tangential loading **matches the experiment within ±6 % over
r/R = 0.47–0.80** and is **−16 % (cn) / −17 % (ct) at r/R = 0.95**, where `r` —
the torque lever — is largest. That is the −7.6 % torque deficit.

**Why**: the ALM Gaussian kernel is numerically identical to a Lamb–Oseen
viscous vortex core, so the induction at the blade is under-estimated near the
tip → the AoA is over-estimated → the loading is too strong. The BEM Glauert tip
loss is a crude, too-strong patch; removing it over-shoots (+19.5 %).

**Dağ & Sørensen measured the identical symptom on the identical case and
diagnosed it identically** (their Table 1: 2 blades, TSR 5.39, D = 10.058 m,
**pitch 3°**, cone 0°, 7 m/s, ε/Δ = 2; their Fig. 2):

> "at the tip region an **overestimation of the ALM loadings** is clearly
> visible… Correcting the load distribution by the Prandtl tip correction,
> however, **does not remedy the situation, as the loading becomes highly
> underestimated**."

Their remedy: **subtract the viscous part of the kernel's own induction
analytically and add it back.**

## 3. The formulation to implement (verified with vision, Eqs. 15–24)

Paper: `turbinesFoam/articles/Wind Energy - 2019 - Dağ - A new tip correction for actuator line computations.pdf`
(Wind Energy 23(2):148-160, 2020). Formulation on printed pages **153–157**
(PDF pages ~6–9).

```
Eq (15)  Lamb-Oseen:      w_i   = Γ/(4πr)·[1 − exp(−(r/r_vc)²)]
Eq (16)  the correction:  w_corr = Γ/(4πr)·exp(−(r/ε)²)          <- the core of it
Eq (17)  planar total:    w_corr(i) = Σ_j Γ_w(j)/(4π d_ij)·exp(−(d_ij/ε)²)
Eq (18)  wake strength:   Γ_w(j) = Γ(j) − Γ(j−1)     (tip vortices: Γ_w = Γ at each tip)
Eq (19)  Kutta-Joukowski: Γ(i) = ½·c(i)·C_L(i)·u_rel(i)
Eq (22)  per vortex line: w_corr = Γ/(4π)·(dl × d)/|d|³·exp(−(|d|/ε)²)
Eq (23)  rotor total:     w_corr^{N,m} = Σ_h Σ_p Σ_q Γ_w(h,p,q)/(4π)
                                        ·(d_{h,p,q} × d^{N,m}_{h,p,q})/|d^{N,m}_{h,p,q}|³
                                        ·exp(−(|d^{N,m}_{h,p,q}|/ε)²)
Eq (21)  apply:           α(i) = α_g − sin⁻¹((−u_x(i) + w_corr(i))/u_rel(i))
```
`h, p, q` = blade, span position, azimuthal position of the **wake** vortices;
`N, m` = blade, span position of the **actuator points**.

**Implementation licence from the paper (p. 155):** *"we **restrict the modeling
of the wake vortices to straight lines** in order to simplify the bookkeeping…
even a simple prescribed wake greatly improves the resulting circulation
distribution."* The correction is **iterative within each time step**.

**Their Phase VI validation is their Fig. 10 (printed p. 158)** — ALM with/without
the correction vs BEM, at Δ = R/5 and R/20, ε = 5Δ and 3Δ.

## 4. Where it goes in the code

- `turbinesFoam/src/fvOptions/axialFlowTurbineALSource/axialFlowTurbineALSource.C`
  — rotor-level, per-element correction. **`calcEndEffects()` (line ~582) is the
  precedent**: it already loops blades × elements, reads `rootDistance()`,
  `relativeVelocity()`, `velocity()`, and writes per-element state via
  `setEndEffectFactor()`. Do the same shape.
  - Note its **known staleness (finding H3b)**: it runs *before* the element
    `addSup` loop (call sites at `:859`, `:953`, `:1035`), so it reads the
    previous PIMPLE iteration. Acceptable (iterative by design), documented.
- `.../actuatorLineElement/actuatorLineElement.C`
  - `calculateInflowVelocity()` (~`:573-650`) — where the correction must be
    applied so it enters the AoA.
  - `calculateForce()` (~`:923-1045`) — the ordered pipeline; the end-effect
    factor is applied at `:1036` as `liftCoefficient_ *= endEffectFactor_`.
  - `inflowRefAngle()` (`:905`) returns the flow angle **phi** (not the AoA).
- `.../dynamicStallModels/` — the precedent for a pluggable model family.

## 5. Already done (do not redo)

| # | Done | Where |
|---|---|---|
| 1 | Bibliographic review + method evolution | `campaign-results/formulation-review.md` |
| 2 | Campaign results + full decomposition | `campaign-results/RESULTS.md` |
| 3 | SOWFA comparison | `campaign-results/SOWFA-6-crosscheck.md` |
| 4 | NREL report cross-check | `campaign-results/NREL-TP-500-29955-crosscheck.md` |
| 5 | **Frame bug fixed** (chord vs plane of rotation) | `scripts/comparePhaseVI.py` + 10/10 tests |
| 6 | `--tip-effects`, `--div-phi-u`, `--polar` switches | `tools/generate_case.py`, `scripts/runPhaseVI.sh`, campaign slurm |
| 7 | CSU Re=0.65e6 polar + `buildPolars.py` extension | `data/polars/S809_CSU_Re0.65M_total.dat` |
| 8 | MPI crash fix | `scripts/runPhaseVI.sh` (`--mca pml ucx --mca btl ^openib`) |
| 9 | SBATCH policy: never `--nodes`, never `--mem` | all 6 `scripts/slurm/*.slurm` |
| 10 | Run cleanup (freed ~184 GB) | quota 87 % |

## 6. Task plan (see `odd/tasks/phasevi-tip-correction-dagsorensen.md`)

1. Re-verify Eqs. (15)–(24) + the prescribed-wake recipe (printed pp. 155–157).
2. ODD design note: interfaces, wake geometry, iteration, MPI safety.
3. Implement per-element Γ + the prescribed helical wake.
4. Implement Eq. (23) accumulation + Eq. (21) application.
5. Config + render plumbing; **default-off byte-identical gate**.
6. Tests: planar-wing limit (their Figs. 3/4), default-off regression, parallel
   invariance.
7. **Launch arm A with the correction and the tip loss OFF at 7 m/s.**
8. Record the verdict in `RESULTS.md`.

## 7. Operational gotchas (learned the hard way — do not repeat)

- **Never edit a shell script while a Slurm job is executing it.** Bash re-reads
  by byte offset; mid-run edits corrupt execution and produce fake "unbound
  variable" failures. (A recompile of the `.so` is safe: running processes keep
  the mapped inode.)
- **Never cap `--nodes` and never set `--mem`** in the Slurm scripts: with the
  partition default `DefMemPerCPU=8000` a `--nodes` cap concentrates 375 GB onto
  one node and the job waits days (`idle total: 0`).
- The MPI `MPI_Init_thread` segfault (`btl_openib_connect_udcm` →
  `ibv_cmd_reg_dm_mr`, signal 11) is an **intermittent race**; excluding the
  openib BTL fixes it. Already in `runPhaseVI.sh`.
- **Environment**: `module load openfoam/v2506_openmpi-4.1.4_gnu gcc`, then the
  Int64 identity (`WM_ARCH=linux64 WM_COMPILER=Gcc WM_COMPILE_OPTION=Opt
  WM_PRECISION_OPTION=DP WM_LABEL_SIZE=64 WM_OPTIONS=linux64GccDPInt64Opt`) and
  `. "$WM_PROJECT_DIR/etc/bashrc"` with `set +eu` around it. Prepend
  `/scratch/app/gcc/14.2.0/lib64` to `LD_LIBRARY_PATH` (GCC-14 libstdc++).
- Python: `/scratch/leahk/eduardo.donestevez/venv/bin/python` (the `rtk` shim
  hijacks `python3`). Tests run from `turbinesFoam/`.
- **Quota is tight** (group `leahk`, 2 T, currently 87 %). The campaign script
  deletes `processor*/` after each run.
- Heavy work goes on the Slurm queue, not the login node. The paper's own grid
  (ε/Δ = 2, ours) matches.

## 9. Working tree state — READ BEFORE WRITING ANY CODE

**This session's work is UNCOMMITTED.** `git status --short` at handoff time:

- **Branch: `feat/nacelle-actuator-surface`**, HEAD `a68b5e9`. This session's
  work sits on top of the S1 nacelle branch — an unrelated line.
- **19 modified files, +555/−91**, including:
  - `turbinesFoam/validation/phaseVI/scripts/comparePhaseVI.py` (the **frame
    fix**)
  - `turbinesFoam/validation/phaseVI/tools/generate_case.py` (`--div-phi-u`,
    `--polar`, `--tip-effects`)
  - `turbinesFoam/validation/phaseVI/scripts/runPhaseVI.sh` (the MPI fix, the
    `render_args` **array** refactor, the new flags)
  - `turbinesFoam/validation/phaseVI/scripts/buildPolars.py` (CSU variant)
  - all six `scripts/slurm/*.slurm` (SBATCH policy: `--nodes` removed)
  - `turbinesFoam/tests/test_phasevi_case.py`, `test_phasevi_compare.py`
  - `config/case.yaml`, `case/system/controlDict`
- **Untracked**: `odd/` (this handoff + the two task docs),
  `turbinesFoam/validation/phaseVI/campaign-results/` (all four analysis
  documents), `data/polars/S809_CSU_Re0.65M_total.dat`, `openspec/`,
  `.codegraph/`, `.pi/`.

**Consequence**: a new session must **not** start writing the tip correction on
this dirty tree. Recommended first step, with the user's explicit go-ahead:

1. Cut a branch off `main` for the tip correction, **or** commit this session's
   work as its own work unit(s) on its own branch first.
2. Do not commit without the user saying so — but surface this immediately.

The changes above are **verified working** (10/10 compare tests pass;
`generate_case.py --check` exit 0; the campaign ran with them), so they are a
reviewable unit rather than half-finished work.

## 10. The exact prompt to paste in a new session

> Seguí con la implementación de la corrección de punta de Dağ & Sørensen 2020
> para la ALM de turbinesFoam. El handoff completo está en
> `odd/tasks/HANDOFF-dagsorensen-tip-correction.md`: leelo primero, es
> autocontenido. El diagnóstico ya está cerrado — la causa raíz es la punta
> (−16 % en cn/ct a r/R=0.95 con el tip-loss de Glauert encendido, que es
> demasiado fuerte), y la formulación a implementar son las Eqs. (15)–(24) del
> paper, con estela helicoidal prescrita en segmentos rectos.
>
> Arrancá por la tarea 1 del plan (`odd/tasks/phasevi-tip-correction-dagsorensen.md`):
> re-verificá las ecuaciones con visión y la receta de estela (pp. 155-157 del
> paper en `turbinesFoam/articles/`), después el diseño ODD, y seguí el plan.
>
> Memoria Engram del proyecto `of-plugins`: buscá
> `turbinesfoam/phasevi-root-cause-tip` (#225) y
> `turbinesfoam/phasevi-scheme-polar-ablation` (#223) para el contexto completo.
