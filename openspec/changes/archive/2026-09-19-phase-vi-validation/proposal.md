# Proposal: NREL Phase VI validation of turbinesFoam ALM and ASM

## Intent

`turbinesFoam/` now carries the additive actuator surface model (ASM) next to
the default actuator line model (ALM), but neither has ever been compared
against measured turbine data inside this repository. The repo's own testing
policy is manual/on-demand HPC validation, and the ASM README explicitly asks
for re-validation on a mesh fine enough to give the projection kernel 1–2 cells
of overlap. This change creates that validation basis.

NREL Phase VI (NASA Ames Unsteady Aerodynamics Experiment) is the chosen case
because its measured data is **public and complete**: geometry (NREL/TP-500-29955
Table A-1), S809 polars (TP-500-29955 A-3..A-8, TP-442-7817), and the measured
loads statistics (NWTC WDH statistics workbooks: public DOI, 0° yaw rows) are
all available without registration. MEXICO's experimental data is
password-protected/on-request, so MEXICO validation is deferred. Phase VI also
lets ALM and ASM run the **same case, mesh, and inflow**, so their agreement or
divergence is attributable to the element model, not to the setup.

What "validation" means here, precisely:

- **Integral loads** (turbine power, shaft torque, rotor thrust) compared
  against the measured WDH anchors, and **spanwise CN/CT** at the five measured
  stations (30/47/63/80/95 % span).
- **Documented tolerance bands**, fixed against the NREL report definitions
  before any result is claimed. The expectation is a qualitative-to-semi-
  quantitative claim (correct trend, stall onset, loads within a documented
  few–15 % band), never a promise of <5 % agreement.
- It is **not** a repository regression gate and there is no solver run in CI.
  The artifacts are reproducible run inputs, documented data provenance, and a
  comparison tool that fails loudly instead of reporting a misleading match.

Results are reported as a validation basis in this repo's docs and outputs —
no published report or committed PDF/workbook is part of this change.

## Scope

### In Scope

- `turbinesFoam/validation/phaseVI/` — the new validation case package:
  - **Case generator + skeleton**: YAML single source of truth adapted from the
    SAL scaffold (`mttbrbr/single-actuator-line`, GPL-3.0-or-later, attributed);
    re-centred 20D×8D×5D free box on the hub (no ground, no ABL/Mann),
    slip/symmetry far field, uniform velocity inlet, pressure outlet.
  - **Mesh**: 18-block `blockMeshDict` renderer at **D/32** (dev/sweep) and
    **D/48** (headline); D/64 only as an optional URANS sensitivity point.
  - **`system/fvOptions.ALM` and `system/fvOptions.ASM` twins** differing only
    in the blade subdictionary (`elementType actuatorLineElement` vs
    `actuatorSurfaceElement; nChordwise 5;`).
  - **`data/`** with derived CSVs and per-directory `PROVENANCE.md`:
    - `geometry/` — `phaseVI_blade.csv` (TP-500-29955 Table A-1), attributed.
    - `polars/` — S809 polars **rebuilt from the NREL tables** (TP-500-29955
      A-3..A-8; TP-442-7817), not the scaffold's `S809_Re1M_extended` (it has
      four flipped Cm signs and two unexplained Cd values). Single-Re OSU
      Re 1 M total-drag baseline + multi-Re set as sensitivity variant.
    - `experiment/` — Sequence H/S performance and spanwise CSVs extracted from
      the WDH workbook `ldsmean` sheet, 0°-yaw rows only, with the verified
      anchors (e.g. h0700000: 5.946 kW / 789.86 Nm / 1132.07 N;
      h2500000: 11.951 kW / 1580.41 Nm / 4028.63 N).
  - **`scripts/`** — `makeElementData.py`, `runPhaseVI.sh`
    (`-m alm|asm -u <speed> [-mesh coarse|fine]`), `comparePhaseVI.py`
    (turbine + spanwise simulation-vs-experiment merge, fail-loud, reusing the
    `compareALMvsASM.py` conventions).
  - **`README.md`** — case setup, run stages, metric definitions, limitations.
- **Staged run plan**: Stage 0 (mesh + `checkMesh` + ≤0.3 rev stability for
  both models at 7 m/s on `sequana_cpu_dev`, authorized, now); Stage 1 7 m/s
  URANS ALM+ASM on D/32 then D/48; Stage 2 wind-speed extension
  {10, 13, 15, 25} m/s + Sequence S repeat; Stage 3 optional IDDES,
  nChordwise {1,3,5} sweep, D/64. Stages 1–3 are **prepared but not launched**
  until the long-queue authorization is granted.
- **Cheap pure-Python data-sanity tests** in `turbinesFoam/tests/` (polar/CSV
  parse, geometry monotonicity, TSR mapping, experimental anchors, provenance
  presence) — no solver, no OpenFOAM in CI.
- Root `README.md` / `CHANGELOG.md` notes documenting the validation package.

### Out of Scope

- Any `turbinesFoam/src/` change. The missing spanwise `cm` element-CSV column
  is a documented follow-up (separate opt-in change).
- The MEXICO case (`openspec/changes/mexico-validation/` stays historical).
- The SAL scaffold's ABL + Mann inflow, `hipersim` dependency, and
  `snappyHexMesh` path.
- Tunnel-replica walls (36.6 m × 24.4 m); blockage (~2 % vs measured) is
  documented, not simulated.
- IDDES as the headline model (optional Stage 3 confirmation only).
- Yaw sweeps (2–180°) and chordwise Cp tap comparisons — stretch work.
- Committing report PDFs or the 44 MB WDH workbooks; only derived numeric CSVs
  plus provenance.

## Capabilities

> This section is the CONTRACT between proposal and specs phases.

### New Capabilities

- `phasevi-validation-case`: the case-generation capability — a YAML single
  source of truth renders the uniform-inflow Phase VI case (geometry, 18-block
  blockMesh at D/32/D/48, boundary conditions, solver/time settings, decompose,
  ALM/ASM fvOptions twins) and detects stale generated files.
- `phasevi-data-provenance`: the input-data capability — derived geometry,
  polar, and experimental CSVs plus `PROVENANCE.md` and extraction/sanity
  checks binding every committed number to a specific NREL table or WDH
  workbook row, sheet, and unit.
- `phasevi-run-and-compare`: the execution-and-evaluation capability — staged
  Slurm run preparation with tip-constrained fixed Δt and restart, and the
  comparison tool that merges simulation turbine/spanwise output with the
  experimental anchors and reports metrics with documented definitions.

### Modified Capabilities

- None — this change adds validation artifacts and docs; it modifies no
  existing spec-level behavior. (`actuator-surface-element`,
  `element-type-selection`, and `axial-flow-turbine-asm-tutorial` remain as-is.)

## Approach

Scaffold-derived uniform-inflow URANS program (exploration Approach 1,
staged). One shared case is rendered from `config/case.yaml`; ALM and ASM
results come from the fvOptions twin selection, not from divergent setups.

- **Inflow/domain**: uniform inlet replicating the tunnel approach flow;
  re-centred 20D×8D×5D box (x ∈ [−5D, 15D], y ∈ ±4D, z ∈ hub ± 2.5D; hub at
  12.192 m) so all far boundaries are slip/symmetry. A tighter 15D×6D×6D
  fallback (~0.6× cells) is available if the budget demands it.
- **Mesh**: SAL 18-block Cartesian `blockMeshDict` renderer, fully hexahedral,
  non-orthogonality ≈ 0, minutes to generate. D/32 = 6.67 M cells,
  D/48 = 22.5 M cells, D/64 ≈ 40 M (optional).
- **Solver/timestep**: `pimpleFoam` + `kOmegaSST`, `adjustTimeStep off`;
  fixed Δt chosen so the ALM tip displacement per step stays below the cell
  size — D/32 Δt = 0.008 s, D/48 Δt = 0.005 s, D/64 Δt = 0.004 s. Run 12 revs
  (discard 0–4, average 4–12 with a rolling <1 % gate on Cp/Ct). The scaffold's
  Δt = 0.03 s / Co 1.0 must NOT be copied (fails the constraint at 72 rpm).
- **Kinematics**: per-speed measured TSR (5.408 / 3.798 / 2.920 / 2.530 /
  1.898 / 1.521 for 7/10/13/15/20/25 m/s, Sequence H) — the rotor speed is set
  through `tipSpeedRatio`, so the fixed 5.3894 is only valid at 7 m/s. Pitch 3°,
  axis (−1,0,0), `-(twist + pitch)` convention re-verified against the measured
  CN/CT signs before production.
- **Models**: 2D-measured S809 polars + `endEffects` ON with Glauert; dynamic
  stall OFF for the 7 m/s headline, optional Leishman–Beddoes for 13–25 m/s.
  ASM variant uses `nChordwise 5`; a {1,3,5} sweep runs at D/48 / 7 m/s as the
  meaningful resolution sensitivity instead of claiming chord-resolved forces.
- **Comparison**: dimensional power/torque/thrust (with the reference density
  stated) plus spanwise `c_ref_n`/`c_ref_t` at the five measured stations; CM
  dropped from the headline unless the follow-up CSV column lands.
- **SAL adaptation**: reuse the generator/18-block renderer structure, run
  scripts, and test layout; rebuild all polar/experimental data from NREL
  sources; drop Mann/`hipersim`/snappy; make the environment check accept the
  repo's OpenFOAM v2506 (keep v2412 compatible). Credit "adapted from
  mttbrbr/single-actuator-line (main `8284be8c...`)".
- **Upstream pinning**: record `of-plugins` commit `52fd258...` plus the ASM
  patch note in the case README/PROVENANCE.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `turbinesFoam/validation/phaseVI/` | New | Case skeleton, generator, data (`+PROVENANCE.md`), scripts, README. |
| `turbinesFoam/tests/` | Modified (files added) | Pure-Python data-sanity tests; no solver runs. |
| `turbinesFoam/src/` | Unchanged | ASM/ALM behavior ships already; CM column is follow-up. |
| `README.md` (root) | Modified | Document the validation case and staged run plan. |
| `CHANGELOG.md` (root) | Modified | `Files:` / `Problem:` / `Fix:` entry for the validation package. |
| `openspec/changes/phase-vi-validation/` | New | This proposal and downstream spec/design/tasks/verify. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| ASM chordwise strips are **sub-cell** at every affordable mesh (strip 0.071–0.147 m vs cell 0.16–0.31 m), so chord-resolved force distribution is sub-grid | High | Document the limitation; headline mesh D/48; run the nChordwise {1,3,5} sensitivity sweep; frame the claim as chord-averaged inflow + projection behavior, not surface resolution. |
| URANS k-ω SST cannot capture deep-stall unsteadiness/hysteresis; 13–25 m/s become trend/onset evidence | High | State the fidelity boundary per speed; optional IDDES confirmation at Stage 3; compare trend and stall-onset ordering, not pointwise loads at separated speeds. |
| Comparison definitions (density convention, EAEROTH friction-free pressure integration, hub/tower inclusion, ROTPOW/LSSTQCOR drivetrain correction) are unresolved and can silently bias results | High | Design phase must fix each definition against TP-500-29955 and write it into the comparison output; dimensional comparison with stated density as default. |
| Spanwise CM has no simulation output (`cm` absent from element CSV) | Certain | Drop CM from the headline; record the small element-writer addition as an explicit follow-up change outside this scope. |
| TSR / rotation-sign / pitch-convention error silently mirrors loads | Med | Verification gate: per-speed measured TSR values, axis (−1,0,0) handedness, `-(twist + pitch)` must reproduce measured CN/CT signs at 7 m/s before any production run. |
| Tower geometry provenance missing in the scaffold; tower shadow is in measured loads | Med | Source tower element data from the test report or run rotor+hub only and document the difference; decide in design. |
| Licensing/attribution drift when adapting SAL-derived files | Med | GPL-3.0-or-later compatible; explicit attribution line and upstream commit in README/PROVENANCE; never commit report PDFs/workbooks. |
| Delivery far exceeds the 400-line single-PR budget (case + data + scripts + docs + tests) | High | Recommend chained slices (generator/case → data/provenance → scripts/docs/tests) or an explicit `size:exception`; flagged for the tasks phase forecast. |
| Long-queue authorization still pending; production campaign cannot start | Med | Stage 0 fully executable on `sequana_cpu_dev` now; Stages 1–3 prepared but not submitted; nothing in design/spec/tasks is blocked. |
| Data extraction error (wrong sheet/rows, yaw rows mixed in) | Med | Extract only `ldsmean` 0°-yaw rows; cross-check against the verified anchor table; anchor tests in `turbinesFoam/tests/`; PROVENANCE with sheet, row IDs, units, sha256. |
| Fork has no upstream history; unreproducible provenance | Low | Pin the `of-plugins` commit hash and the ASM patch note in the case README/PROVENANCE. |

## Rollback Plan

- **No source risk**: no `turbinesFoam/src/` file is touched, so no library
  rebuild or behavior regression is possible from this change.
- **Filesystem revert**: delete `turbinesFoam/validation/phaseVI/`, the added
  data-sanity tests, and revert the root `README.md` / `CHANGELOG.md` notes —
  a single `git revert` of the change commits, since everything is additive.
- **Running work**: no Stage 1+ job is launched; if a Stage 0 job diverges,
  `scancel` it and delete the `run-*` directory (inputs live in version
  control, so nothing is lost).
- **Engram**: the proposal/spec/design/tasks entries use stable `topic_key`s;
  a superseded proposal upserts rather than duplicating, and artifacts can be
  re-generated from the git-tracked OpenSpec files.

## Dependencies

- OpenFOAM v2506 module plus the verified `WM_*` export recipe; no preCICE.
- Public NREL sources: TP-500-29955 (DOI 10.2172/15000240), TP-442-7817, WDH
  workbooks (DOI 10.21947/WDH-DAP/1910052) — local verified copies already
  exist at `$SCRATCH/tmp/phasevi_research/`.
- SAL scaffold `mttbrbr/single-actuator-line` (main `8284be8c...`),
  GPL-3.0-or-later, as adaptation source with attribution.
- `sequana_cpu_dev` (authorized now) for Stage 0; `sequana_cpu_long`
  authorization **pending** for Stages 1–3.
- Python 3 with pytest for the data-sanity tests; comparison script shares the
  `compareALMvsASM.py` dependency set.

## Decisions To Surface (recorded, not decided)

1. **Long-queue authorization** — `sequana_cpu`/`_long` still pending; Stage 0
   proceeds now, production waits for explicit authorization.
2. **Fidelity/cost mix** — confirm URANS headline + optional IDDES, and the
   mesh ladder D/32 → D/48 (D/64 only if affordable).
3. **Delivery shape** — chained PR slices vs explicit `size:exception`.
4. **Comparison definitions** — density convention, sim-side thrust hub/tower
   inclusion, and whether spanwise CM is required (needs the follow-up element
   CSV addition).

## Success Criteria

- [ ] Generator renders D/32 and D/48 cases; `blockMesh` + `checkMesh` clean
      on both; ALM and ASM fvOptions twins differ only in the blade
      `elementType` / `nChordwise` keys (verified by diff).
- [ ] Stage 0 stability runs of both models at 7 m/s on D/32 reach ≥0.3 rev on
      `sequana_cpu_dev` without divergence; no job submitted to the long queue.
- [ ] TSR/rotation gate passes: per-speed measured TSR values are in the case
      config (not the fixed 5.3894), and 7 m/s reproduces measured CN/CT signs
      before production.
- [ ] `data/` contains geometry, polars, and experimental CSVs with
      `PROVENANCE.md` (URL, sha256, sheet/table, row selection, units,
      extraction date) and the anchor values match the verified exploration
      table exactly.
- [ ] `pytest` data-sanity checks pass with no solver or OpenFOAM required.
- [ ] `comparePhaseVI.py` produces turbine-level and spanwise sim-vs-experiment
      output with explicitly documented definitions (density, thrust scope, CM
      treatment) and fails loudly on missing input.
- [ ] 7 m/s headline results reported against documented tolerance bands with
      an honest limitation statement (ASM sub-cell chord strips, URANS
      deep-stall limits) — no claim stronger than the evidence.
- [ ] Root README/CHANGELOG updated; `turbinesFoam/src/` untouched; derived
      data only (no PDFs or workbooks) committed.
