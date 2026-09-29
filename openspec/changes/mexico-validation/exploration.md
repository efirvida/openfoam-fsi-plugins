# Exploration: MEXICO rotor experimental validation (ALM vs ASM)

## Current State

`turbinesFoam/` is a vendored fork with a newly delivered, additive **actuator
surface model (ASM)** (`actuatorSurfaceElement`, selected per blade via
`elementType actuatorSurfaceElement; nChordwise 5;`; archived change
`2026-09-19-actuator-surface-model`). The ALM (`actuatorLineElement`,
collocation-point sampling at the quarter chord) is the unchanged default.

- Tutorials `axialFlowTurbineAL`/`axialFlowTurbineASM` are **small HAWT smoke
  cases**: 0.45 m rotor (S826 polars), 32×96×24 blockMesh (~74k cells before
  snappy), pimpleFoam + kEpsilon, Euler + linearUpwind, `endTime` 0.1–0.5 s.
  Comparison script `compareALMvsASM.py` reads
  `postProcessing/turbines/0/turbine.csv` (`time,angle_deg,tsr,cp,cd,ct`) and
  `postProcessing/actuatorLineElements/0/*.csv`
  (`time,root_dist,...,cl,cd,fx,fy,fz,end_effect_factor,c_ref_t,c_ref_n,f_ref_t,f_ref_n`).
- Tests: pytest integration suite that copies tutorials and runs real cases
  (`Alltest` = `Allwmake` + `pytest`); nothing beyond that; validation is
  manual/on-demand HPC per repo `AGENTS.md`.
- `tutorials/resources/foilData/` has `NACA64_A17`, `DU21/25/30/35/40_A17`,
  `S826*` but **not the MEXICO set** (`DU91-W2-250`, `RISØ-A1-21`, `NACA 64-418`).
- HPC (Engram `config/hpc-launch-sequana`): Slurm `sequana_cpu_dev` (20-min
  limit, usable now) and `sequana_cpu` (infinite; **user authorization
  pending**). Verified pattern: sbatch `runAll.srm` (`module load
  openfoam/v2506_openmpi-4.1.4_gnu gcc`, `. .../etc/bashrc`, payload on
  `$SLURM_PROCID -eq 0`) + `RunFunctions` case runner.

### Reference facts (Zormpa 2025, Wind Energy 28:e2965; MEXICO experiment)

| Item | Value |
|---|---|
| Rotor | MEXICO wind rotor, D = 4.5 m, 3 blades, hub Ø 0.54 m (root r/R ≈ 0.12) |
| Airfoils | DU91-W2-250 (20–45.6% span), RISØ-A1-21 (54.4–65.6%), NACA 64-418 (74.4%–tip); transitions between |
| Design | TSR 6.67 (U∞ = 15 m/s @ 424.5 rpm), root pitch −2.3° |
| Paper run | λ = 10, U∞ = 10 m/s, Re75% ≈ 0.6e6 (no separation at this TSR) |
| Paper numerics | OpenFOAM v2006 URANS PISO k-ω SST, 2nd-order backward, blended central; domain 15D×8D×8D (~1.2% blockage); snappyHexMesh hexcore, background D/10, 4 halvings → Nx=160 (Δx = 2.8e-2 m); 100 cosine-spaced collocation points |
| Sampling | CPS / VAS / LAS, Nε = ε/Δx ∈ {2,4,8}; **turbinesFoam ALM ≈ CPS**; ASM = chord-averaged (its own adaptation, not LAS) |
| Time step | ALM constraint Nt ≥ π·Nx (Δs/Δx ≤ 1); streamwise CFL (Cox,max=0.5, λ=10) → Nt ≥ 100 |
| Acceptance | \|εrel(CP)\| < 5% needs Nt=800 (CPS)/400 (VAS)/100 (LAS) at Nx=160 (Sec. 6.1); Nx=80 within 6% CP / 1.5% CT of Nx=160 (Sec. 5.3; Conclusions say <5%/<2% — paper inconsistency, use Sec. 5.3) |
| Polars (paper) | RANS blade-resolved, span-dependent ⇒ **no tip correction** (endEffects OFF); 2D measured polars ⇒ tip/root correction REQUIRED (endEffects ON) |
| Experiment | DNW LLF 9.5×9.5 m open jet; 148 Kulite sensors at 5 stations (25/35/60/82/92% span); 424.5 rpm (tip ≈ 100 m/s, Re_c ≈ 0.6–0.8e6, tripped 5% chord) and 324.5 rpm; U∞ 10–30 m/s ⇒ TSR 3.3–10; thrust (balance) + power (shaft torque) ⇒ CT, CP vs TSR; CP,max ≈ 0.38 (torque-derived; viscous-drag caveat, Mexnext) |
| Data access | Database password-protected / on request; geometry+polars+loads appear as tables/figures in Snel 2007, Schepers 2012 (ECN-E-12-004), Nilsson 2015, Shen 2012, Zhang 2016; Zormpa polars figure-only (Fig. B1), on request |

## Affected Areas

- `turbinesFoam/tutorials/` — untouched; no pytest `getTutorialFiles.sh`
  references the new case unless a test is deliberately added.
- `turbinesFoam/tutorials/resources/foilData/` — untouched (MEXICO polars live
  in `validation/mexico/data/polars/`, not foilData, per provenance design).
- `turbinesFoam/tests/` — optionally one cheap pure-Python data-sanity test
  (no solver); nothing else changes.
- `turbinesFoam/src/` — **no source changes expected** (`elementType`/
  `nChordwise` already shipped).
- New `turbinesFoam/validation/mexico/` — case, data, scripts (see Location).
- Root `README.md` / `CHANGELOG.md` — document the validation case.

## 1. Validation-case design options with tradeoffs

### 1.1 Domain and mesh

| Approach | Pros | Cons | Effort |
|---|---|---|---|
| **A. Rotor-only 15D×8D×8D, snappyHexMesh hexcore (paper-faithful)** | Matches the paper's grid family and ~1.2% blockage; reuses the tutorial mesh pipeline (blockMesh → snappyHexMesh → topoSet); clean rotor-only physics | 36 m wide vs 9.5×9.5 m DNW open jet — experiment had ~18% open-jet blockage, not replicated; document as inherent | Med |
| B. Smaller 8D×4D×4D box | Cheaper | ~5% blockage, less wake room; breaks comparability with Zormpa values | Low |
| C. Tunnel-mimicking domain (9.5×9.5 m section) | Would reproduce open-jet blockage | Non-standard boundary treatment (shear layers); not justified for first validation | High |

**Recommendation: A**, with a **scalable `Nx` parameter** so the same case
files generate Nx=80 and Nx=160 (levels derived from Nx). Background D/10
(blockMesh 150×80×80 ≈ 0.96M cells), box region [15D×4D×4D] at 1 halving,
finest-cell cylinder [2D × 1.2D Ø] around the hub; `topoSet` cylinderToCell
for the `turbine` cellSet (as in the tutorial). Estimated totals: **Nx=80 ≈
3–5M cells; Nx=160 ≈ 15–25M cells**.

### 1.2 Solver setup

Paper: **pimpleFoam (PISO), URANS k-ω SST, backward 2nd-order, blended
central**. Repo tutorials: pimpleFoam + **kEpsilon**, Euler, linearUpwind.
For genuine validation: keep `pimpleFoam`, switch to **k-ω SST** (`kOmegaSST`
on ESI v2506, add `omega` to 0.org), `backward` time, `bounded Gauss linear`
convection; keep 1 outer / 2 p correctors / 0 non-ortho (snappy hex). LES
(WALE) is higher-fidelity but costs more and needs inflow turbulence handling —
**primary = URANS k-ω SST**; LES deferred (paper already confirmed its
conclusions for ALM-LES of MEXICO with laminar inflow).

### 1.3 Time step, revolutions, metrics

- λ=10, U∞=10 m/s ⇒ T_rev = 0.1414 s. **Nt = 400 (Nx=80)** (≥ π·80 ≈ 251) and
  **Nt = 800 (Nx=160)** (≥ 503) ⇒ Δt ≈ 3.5e-4 / 1.8e-4 s (Δs/Δx = 0.63);
  streamwise CFL ≈ 0.06.
- **Revolutions**: 5–6 total; discard first 2–3 (transient); average last 2–3.
  Convergence gate: |⟨ct⟩_rev_k − ⟨ct⟩_rev_{k−1}| < 1% (and |⟨cp⟩|), evaluated
  from `turbine.csv`.
- **Metrics**: (a) **CP and CT vs TSR** — sweep {4.17, 6.67, 8.34, 10} at
  424.5 rpm (U∞ = 24/15/12/10 m/s; matches the experimental matrix; 6.67
  design, 10 the paper's no-separation point); (b) **spanwise Cn(r/R)** at the
  5 instrumented stations from element CSV `c_ref_n`/`f_ref_n` — the classic
  MEXICO load comparison (Shen 2012, Nilsson 2015); (c) stretch: rotor-plane
  axial induction / PIV planes (±0.5D, ±1D) and the paper's Lamb–Oseen vortex
  metrics (Table 3), only if data allows.
- **Averaging window**: time ≥ t_start + 2 revs to endTime; report mean ±
  temporal std.

### 1.4 ALM vs ASM on the SAME case

One shared case skeleton with **two fvOptions variants**
(`system/fvOptions.ALM`, `system/fvOptions.ASM`) differing ONLY in the blade
subdict (`elementType actuatorLineElement;` vs
`elementType actuatorSurfaceElement; nChordwise 5;`). Runner
`scripts/runMEXICO.sh -m alm|asm -tsr 10` copies the variant into the run dir
(`run-ALM-tsr10/`, `run-ASM-tsr10/`); `compareMEXICO.py` reads both + the
experiment. Mirrors the delivered `compareALMvsASM.py` pattern.

**endEffects trap (critical)**:
- **2D measured polars** (MEXICO "best set", or XFOIL at matching Re/trip):
  `endEffects { active on; endEffectsModel Glauert; }` (Shen alternative) —
  the standard MEXICO ALM practice.
- **RANS-BR span-dependent polars** (Zormpa's approach): `endEffects { active
  off; }` — 3D effects are already inside the polars; leaving Glauert on
  **double-counts** the tip correction.
- Document in fvOptions comments + README; the compare script prints the active
  endEffects setting for provenance.

## 2. Data requirements checklist

Repo has: geometry pipeline (`elementData`: `axialDistance radius azimuth
chord chordMount twist`), `profileData` single-Re and multi-Re (`ReList`)
formats. Repo **lacks**: MEXICO geometry, MEXICO polars, experimental tables.

| Data | Needed | Repo now | Source / action |
|---|---|---|---|
| Blade geometry c(r), twist(r), section boundaries, root pitch | r/R 0.12–1.0 tables; −2.3° root pitch convention | None | Snel 2007 (J.Phys.Conf.Ser. 75:012014), Schepers 2012 (ECN-E-12-004), Zhang 2016 Fig. 2; cross-check ≥2 sources; generate `elementData` with N cosine-spaced elements via `scripts/makeElementData.py` (verify turbinesFoam twist sign + root-pitch handling in implementation) |
| Polars DU91-W2-250 | CL/CD vs α, Re ≈ 5e5–8e5, tripped | No | MEXICO 2D measurements; fallback XFOIL at matching Re/trip (documented) |
| Polars RISØ-A1-21 | same | No | **NOT measured at condition** in MEXICO — Mexnext "best set" used CFD/panel; Risø-R-1353 has A1-21. Highest-risk item |
| Polars NACA 64-418 | same | No | MEXICO 2D measurements (Re ≈ 5e5) |
| Experimental CP(TSR), CT(TSR) | TSR 3.3–10 @ 424.5 rpm | No | Snel 2007; Schepers 2012; Nilsson 2015; Shen 2012 — digitize with provenance |
| Experimental spanwise Cn @ 5 stations | 25/35/60/82/92% vs TSR | No | Schepers 2012 / Shen 2012 / Nilsson 2015 tables |
| (stretch) PIV axial velocity planes | ±0.5D, ±1D, rotor plane | No | Mexnext reports (password site) — optional |

**Design**: data arrive as files under `turbinesFoam/validation/mexico/data/`
(`geometry/`, `polars/`, `experiment/`), each with a `PROVENANCE.md` (source,
license, digitization method/date, caveats: tripped vs free, Re, measured vs
CFD vs XFOIL, measured-CP friction correction question). A separate
`sdd-research` task sources them. **Nothing hard-codes a number**: fvOptions
`profileData` `#include`s the polar files, `elementData` is generated from
`data/geometry/`, the compare script reads `data/experiment/`.

## 3. Location and tooling

- **Recommendation**: new **`turbinesFoam/validation/mexico/`** (not
  `tutorials/`, not repo root): keeps the pytest-run tutorials lean, groups
  case + data + scripts, natural home for an on-demand HPC case. Layout:
  `case/` (0.org, constant, system with fvOptions.{ALM,ASM}),
  `data/{geometry,polars,experiment}/` (+PROVENANCE.md), `scripts/`
  (`makeElementData.py`, `runMEXICO.sh`, `compareMEXICO.py`), `README.md`.
- **Postprocessing**: `compareMEXICO.py` — (1) CP/CT-vs-TSR table: mean ± std
  over the averaging window per model, merged with `data/experiment/` into one
  printed/CSV/PNG table; (2) spanwise Cn at the 5 stations vs experiment;
  (3) optional rotor-plane ⟨Ux⟩disc. Reuses `compareALMvsASM.py` loading
  conventions (missing input → nonzero exit, never fabricate).
- **Testing strategy**: NOT CI — real runs are on-demand HPC. Cheap checks
  possible: (a) pure-Python pytest `test_mexico_data.py` (polars parse to the
  `profileData` column format, geometry monotone and in r/R range, experimental
  tables non-empty) — seconds, CI-safe; (b) mesh-only dry check (blockMesh +
  checkMesh + topoSet on Nx=80, no solver) on the dev partition, not in pytest.
  No solver runs in CI (turbinesFoam has no GitHub CI; adapter CI is separate).

## 4. Compute estimate and Slurm strategy

Assumptions: pimpleFoam URANS k-ω SST, ~4k cell·step/s/core (conservative);
λ=10/U∞=10; T_rev = 0.1414 s; 6 revs total.

| Case | Cells (est.) | Nt | Δt (s) | Steps (6 rev) | Ranks | Wall (6 rev) | Core-h |
|---|---|---|---|---|---|---|---|
| Nx=80 (dev/quick) | 3–5M (~4M) | 400 | 3.5e-4 | 2400 | 128–256 | 1.5–4 h | ~300–1000 |
| Nx=160 (production) | 15–25M (~20M) | 800 | 1.8e-4 | 4800 | 256–512 | 6–20 h | ~3000–10000 |

- One TSR point, one model, Nx=80: ~300–1000 core-h ⇒ 3-TSR × 2-model sweep
  at Nx=80 ≈ **2000–6000 core-h**; Nx=160 confirmation at 1–2 points adds
  ≈ 5–20 k core-h. Ranges, not point values (throughput uncertainty ×0.5–×2).
- **`sequana_cpu_dev` (20 min) fits**: mesh generation (blockMesh + snappy
  3 levels, Nx=80) on ≥128 ranks (~5–20 min, borderline), checkMesh/topoSet
  (seconds), and **stability checks** (0.2–0.5 rev runs) — NOT full production
  revs (1 rev @ Nx=80 ≈ 26 min @ 256 ranks > 20 min).
- **Long queue (`sequana_cpu`, authorization pending)**: production runs.
  sbatch per the verified `runAll.srm` pattern; use a **job array**
  (`--array=1-6` → model × TSR matrix) so each combination is one array task;
  `RunFunctions` case runner. Nx=160 mesh gen may also need the long queue.
- **Prepared while authorization is pending (no launch)**: all case files
  (blockMesh/snappy/fvOptions.{ALM,ASM}/controlDict/fvSchemes/fvSolution/
  decomposeParDict/0.org with k+omega), `makeElementData.py` + generated
  elementData as geometry arrives, polar/experiment ingestion + PROVENANCE
  files, `runMEXICO.sh` + `compareMEXICO.py` (dry mode with placeholder-but-
  parseable tables), Nx=80 mesh + checkMesh + 0.2-rev stability run on the dev
  partition, README. **Nothing launched on the long queue until authorization.**

## 5. Risks and open questions

1. **Data licensing/provenance** — MEXICO database is password-protected /
   on-request; paper polars (Zormpa Fig. B1) are figure-only. Every digitized
   table needs PROVENANCE.md (source, license, method, date); prefer published
   tables over figure digitization; two-source cross-check for geometry.
2. **Polars: RISØ-A1-21 not measured at condition** — Mexnext "best set" used
   CFD/panel data; risk of a polar that does not match the tripped experiment.
   Fallback XFOIL at Re/trip matching; document. Re matching: Re75% ≈ 0.6e6 at
   the λ=10 condition vs the 2D measured Re ≈ 5e5 (DU91/NACA 64-418) —
   `profileData` multi-Re or nearest-Re, decide and document.
3. **Measured CP definition** — MEXICO torque-derived CP has a known
   viscous-drag/friction treatment caveat (CP,max ≈ 0.38); use the Mexnext-
   recommended reduction and state which experimental values are compared.
4. **Mesh generation cost at Nx=160** — snappy 4 levels on 20M cells likely
   exceeds the 20-min dev partition; needs the long queue (or staged snappy).
5. **Convergence criteria** — define the periodic-state gate (rolling ⟨ct⟩/⟨cp⟩
   < 1%) and averaging window in the script, not ad hoc; paper's Nt=800 target
   (CPS) is the time-step reference.
6. **Paper URANS vs repo conventions** — repo tutorials use kEpsilon/Euler/
   linearUpwind; switching to k-ω SST/backward/linear is a deliberate departure
   to match the paper; verify `kOmegaSST` naming and omega BCs on ESI v2506.
7. **TSR-sweep cost** — staged: Nx=80 λ=10 first (both models), then λ=6.67,
   then Nx=160 confirmation; the sweep is the main cost driver.
8. **Data arriving later** — case is designed so files land in `data/` with
   provenance; production runs start only after data is present (scripts fail
   loudly on missing inputs); dry runs possible with placeholder tables.
9. **ASM expectations** — the delivered ASM is the chord-strip adaptation
   (mesh-only epsilon, Gaussian kernel), not Zormpa's LAS; ASM-vs-experiment
   differences are expected and are the point of the validation. On Nx=80/160
   with default `meshFactor 2`, mesh epsilon gives Nε = 4 for both models;
   `GaussianCoeffs.meshFactor` is the knob for Nε = 2 if desired.
10. **Blockage mismatch** — 15D×8D×8D (~1.2%) vs DNW open jet (~18%): document;
    largest at high CT/low TSR; prefer λ = 6.67–10 for the headline comparison.

## Approaches

1. **Paper-faithful rotor-only case (Option A above)** — 15D×8D×8D, Nx param,
   URANS k-ω SST, fvOptions.{ALM,ASM} twins, TSR sweep, compare script.
   - Pros: comparable to Zormpa acceptance values; reuses tutorial pipeline;
     ALM≈CPS/ASM both validated against the same experiment.
   - Cons: biggest cost; needs long queue for production.
   - Effort: Medium-High.
2. **Minimal case (smaller domain, kEpsilon kept, Nx=80 only)** — quickest
   first numbers.
   - Pros: cheap, fast first pass.
   - Cons: not comparable to the paper; kEpsilon not the paper's closure; weak
     "genuine validation" claim; ASM mesh-only epsilon untested at scale.
   - Effort: Low.
3. **Tunnel-mimicking domain** — reproduce open-jet blockage.
   - Pros: physically closest to the experiment.
   - Cons: non-standard BCs, high effort, little precedent; not needed for an
     ALM-vs-experiment headline.
   - Effort: High.

## Recommendation

**Option 1, staged**: build the full paper-faithful case in
`turbinesFoam/validation/mexico/` with a scalable Nx, URANS k-ω SST, fvOptions
ALM/ASM twins, and the TSR sweep. Stage runs: (0) everything prepared and dry-
checked on the dev partition while authorization is pending; (1) Nx=80, λ=10,
both models, on the long queue; (2) λ=6.67 (design); (3) Nx=160 confirmation at
λ=10; (4) extend to Cn spanwise comparison and, if data allows, rotor-plane
induction. Use 2D measured polars + Glauert endEffects ON as the primary
configuration; keep the RANS-BR-polars + endEffects OFF variant documented for
when Zormpa's data arrive. Do NOT launch production jobs until the long-queue
authorization is granted; dev-partition mesh gen and stability checks are fine.

## Risks

- Data sourcing (polars RISØ-A1-21, measured CP definition, digitization
  errors, licensing) is the biggest schedule risk — start the `sdd-research`
  sourcing task before/alongside case assembly.
- Cost: full sweep at Nx=160 can reach tens of thousands of core-hours; the
  staged plan bounds this (Nx=80 first, confirmation only at 1–2 points).
- Numerical: k-ω SST/backward/linear on the snappy mesh needs a stability
  check before production; ASM mesh-only epsilon must be verified to give Nε ≥
  the resolved grid (no spurious streaks).
- Review budget: the case is config-heavy (geometry, polars, mesh dicts,
  scripts) — likely far over 400 changed lines; flag for delivery shaping
  (chained slices: [case skeleton + geometry] → [data + scripts] → [docs]).

## Ready for Proposal

**Yes.** The orchestrator should tell the user: the exploration is complete;
the recommended design is a paper-faithful rotor-only MEXICO case
(15D×8D×8D, Nx=80/160, pimpleFoam URANS k-ω SST, ALM/ASM twins via the
`elementType` switch, TSR sweep {4.17, 6.67, 8.34, 10}) living under
`turbinesFoam/validation/mexico/` with data files + provenance, on-demand HPC
(dev partition now for mesh/stability; long queue after the pending
authorization, nothing launched before). Two user decisions to surface:
(1) **data sourcing** — start the separate research task to obtain MEXICO
geometry/polars/experimental tables (RISØ-A1-21 is the riskiest), and
(2) **delivery shape** — the case will exceed the 400-line review budget under
`single-pr`; approve a `size:exception` or plan chained slices.