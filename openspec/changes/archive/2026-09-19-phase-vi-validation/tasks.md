# Tasks: NREL Phase VI validation (`phase-vi-validation`)

## Review Workload Forecast

Estimated changed lines: 2,800–4,200.

```text
Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High
```

`single-pr` + High ⇒ sdd-apply blocked until `size:exception` or re-scope to the PR1–PR3 units: config+generator+case; data+provenance; tooling+tests+docs.

AC slugs = requirement order in each domain's `spec.md`: V1–V11 case; D1–D7 data; R1–R12 run/compare.

## Phase 1: Config + generator

- [x] 1.1 `turbinesFoam/validation/phaseVI/config/case.yaml`: `rotor_speed_rpm` (F4); `domain_D` 20D×8D×5D + 15D×6D×6D fallback (F2); TSR 5.408/3.798/2.920/2.530/1.898/1.521. AC: V1,V7.
- [x] 1.2 `tools/case_config.py` + `tools/element_data.py` + `scripts/makeElementData.py`: validate YAML; derive Ω/T_rev/Δt; assert `ΩRΔt < Δ_hub`, reject 0.03 s; TSR ±0.002; elementData rows (`-(twist+pitch)`, hub 1.0166 m). AC: V6,V7,V8.
- [x] 1.3 `tools/generate_case.py`: 18-block hex `blockMeshDict` (coarse/fine/ultra + fallback), BCs, `controlDict` (pimpleFoam/kOmegaSST, `adjustTimeStep off`), `decomposeParDict`, `topoSetDict`; D/64 = 53.4 M per design (spec ≈40 M; record correction). AC: V3,V4,V6,V9.
- [x] 1.4 Render `case/system/fvOptions.ALM|ASM` from one function; differ only in `elementType`/`nChordwise 5`. AC: V5. Verify: `diff case/system/fvOptions.ALM case/system/fvOptions.ASM`.
- [x] 1.5 Add non-destructive `--check` (exit 1 stale/missing; no writes); commit `case/`; gitignore meshes/`processor*`/`runs/`. AC: V1,V2. Verify: `python turbinesFoam/validation/phaseVI/tools/generate_case.py --check` exits 0.

## Phase 2: Data + provenance

- [x] 2.1 `data/geometry/phaseVI_blade.csv` (TP-500-29955 A-1) + `PROVENANCE.md`. AC: D1.
- [x] 2.2 `data/polars/raw/*.csv` (A-3..A-8, TP-442-7817) + `scripts/buildPolars.py` → `S809_OSU_Re1M_total.dat`, `S809_multiRe.dat`; never cite scaffold polar. AC: D2.
- [x] 2.3 `scripts/extractExperimentalData.py` (`ldsmean`, 0° yaw, rows `h0700000`…`h2500000`/`s0700000`, 20 m/s=`h20m0000`) → 4 CSVs; anchors 5.946/789.86/1132.07, 11.951/1580.41/4028.63. AC: D3.
- [x] 2.4 Per-directory `PROVENANCE.md`: DOI/URL, sha256, table/sheet, rows, units, date; SAL credit `8284be8c…`; NREL citations; pinned `52fd258…` + ASM note; no PDF/XLS. AC: D4,D5,D7.

## Phase 3: Run + compare

- [x] 3.1 `scripts/runPhaseVI.sh -m alm|asm -u <speed> [-mesh coarse|fine|ultra] [--stage0] [--restart] [--submit]`: select twin/mesh/TSR; run dirs; exits 2/3/4/5; `--submit` needs dev queue or `PHASEVI_LONG_QUEUE_AUTHORIZED=1`. AC: R1,R3.
- [x] 3.2 `scripts/{mesh.sh,stage0.sh,check_environment.sh}` + `slurm/stage0.slurm` + prepared-only `slurm/production.slurm` (≤24 h array, restart `latestTime`); env accepts v2506+v2412. AC: V10,R4,R5. Verify: `blockMesh`+`checkMesh` clean D/32, D/48.
- [x] 3.3 Stage matrix (F3) in `scripts/stage0.sh` + config: S0 mesh+`checkMesh` D/32+D/48, ≤0.3 rev 7 m/s ALM+ASM dev queue; S1 7 m/s D/32 then D/48 both models; S2 {10,13,15,25}+Sequence S 7 m/s; S3 optional IDDES, nChordwise {1,3,5} D/48, D/64. 20 m/s renderable but NOT staged (no blanket array). AC: R2,R3. Only Stage 0 executes.
- [x] 3.4 `scripts/comparePhaseVI.py`: merge turbine+element+experiment; revs 4–12 (discard 0–4); 1 % drift flag; exits 1/2/3; `c_ref_n`/`c_ref_t` at five stations; CM excluded + follow-up; limitations; `--sign-gate` (TSR match, cp/cd>0, c_ref>0) → `sign_gate.json`; production blocked without PASS. AC: R6,R7,R9,R10,R11.
- [x] 3.5 Metric definitions (F1): `Q = ct·½ρA·R·U∞²`, `R = rotorRadius` (src `axialFlowTurbineALSource.C:794-795,890-891`; `turbineALSource.C:286-287`); `P = cp·½ρA·U∞³`, `cp = ct·TSR`; blade-only thrust + labelled rotor secondary; ρ from `WTBARO`/`WTATEMP` printed. AC: R8.

## Phase 4: Tests + docs

- [x] 4.1 `turbinesFoam/tests/test_phasevi_case.py` (schema, cell counts 6,674,304/22,525,776, 18 blocks, twins diff, TSR, tip assert, fallback) and `test_phasevi_data.py` (anchors, TSR ±0.002, geometry, polars, provenance, no PDF/XLS); `test_phasevi_compare.py` covers the design's tooling layer (F1 formulas, mapping, drift, exit codes, sign gate). AC: D6,V1–V9. Verify: `python -m pytest turbinesFoam/tests/ -q` without OpenFOAM.
- [x] 4.2 `validation/phaseVI/README.md` (setup, staged plan, metrics, limitations) + root `README.md`/`CHANGELOG.md` (`Files:`/`Problem:`/`Fix:`). AC: V11,D7.

## Phase 5: Stage 0 execution (authorized queue only)

- [x] 5.1 Run `scripts/stage0.sh` on `sequana_cpu_dev`: `checkMesh` clean D/32+D/48; ALM+ASM 7 m/s D/32 ≤0.3 rev without divergence; NO long-queue submission (authorization pending; Stages 1–3 prepared only). AC: R2,R3. Evidence: jobs `11597164` (`--mesh-only`, COMPLETED 5:39) and `11597169` (`--runs-only`, COMPLETED 10:06); D/32 6,674,304 cells / D/48 22,525,776 cells, 100% hex, non-orth 0, "Mesh OK"; both 7 m/s runs 26 steps to 0.208 s = 0.25 rev (stage0 bound ≤0.3 rev), no NaN/bounding/fatal, cp ≈0.310/0.309.
