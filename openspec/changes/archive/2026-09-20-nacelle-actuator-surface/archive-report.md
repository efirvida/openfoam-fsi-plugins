# Archive Report — `nacelle-actuator-surface`

- Change: `nacelle-actuator-surface` — S1: nacelle/hub actuator surface model (ASM) + deterministic geometry pipeline + FSI-readiness seams + periodic-nacelle validation package
- Project: `of-plugins`
- Archived: 2026-09-20 → `openspec/changes/archive/2026-09-20-nacelle-actuator-surface/`
- Artifact store: hybrid — repo-local OpenSpec artifacts are authoritative; the Engram mirror is persisted additionally. The native dispatcher reports the repo-local planning home as `openspec`.
- Branch: `feat/nacelle-actuator-surface`, base `93da696`, head `9dad3ab` — **local commits only; nothing pushed, no PR opened**
- Reference: Yang & Sotiropoulos, *A new class of actuator surface models for wind turbines*, arXiv:1702.02108v4 — Sec. 2.2 (nacelle model, Eqs. 19–23) and Sec. 4.1 (periodic-nacelle validation case; reference figures 5 and 6)
- Report status: terminal record of the SDD cycle; ranks above `apply-progress.md` (intermediate snapshot). `sdd-verify` was not run — see Verification.

## Final State at Close

- **Tasks: 24/24 complete** (W1.1–W1.7, W2.1–W2.5, W3.1–W3.4, W4.1–W4.8), per the persisted `tasks.md`, mechanically counted at archive time: 24 `[x]`, 0 `[ ]`. The archived `tasks.md` bytes are unchanged (`sha256 0d7167e252cc15f27c12e9399c025f084464d8b9011b547e156931788635d5c6`). The W4b batch finished 2026-09-20.
- **Implementation: complete** for the S1 scope (W1–W4b). It is additive and opt-in: with no `nacelle {}`/geometry configured, the actuator-line default path is unchanged.
- **Verification: `sdd-verify` was NOT run as a separate phase** and no `verify-report.md` exists (native status: `verifyReport: missing`, `verify: ready`). This report therefore records the apply-phase verification evidence and the orchestrator-supplied final-state facts; it does not claim a separate verification certificate.
- **16 commits on the branch** from base `93da696` to head `9dad3ab` (all local):
  `7acbc5a`, `7179851`, `fd18565`, `83f991d` (W1) · `6a38f2e`, `cb9f010` (W2) · `ad15f96` (W3) · `a052d0d`, `bb72be7` (W4a) · `7cb1f3c`, `951525a`, `e70f8ec`, `002106a`, `29c6ce1`, `1b6636a`, `9dad3ab` (W4b).
- `openspec/` remains untracked, as in every previous SDD batch. No `git add`/`commit`/`push` was performed by this archive, and no Slurm job was submitted.

## What Shipped per Work Unit

| Unit | Scope | Commits | Final state |
|------|-------|---------|-------------|
| W1 — core nacelle source | `nacelleSurfaceSampler` + `nacelleSurfaceSource` (STL triangulation, direct-forcing normal force Eq. 19, friction/tangential force Eqs. 21–23, smoothed kernel Eq. 18, MPI, CSV); `Make/files` + `Make/options` (`-lsurfMesh`); `axialFlowTurbineALSource::createNacelle()` and the null-deref fix; standalone rotor-less case; integration tests; README | `7acbc5a`, `7179851`, `fd18565`, `83f991d` | Complete and built; ALM default path unchanged; 53 nacelle symbols exported; `ldd -r` clean |
| W2 — geometry pipeline | `turbinesFoam/geometry/`: `src/nacelle.geo` (hemisphere + `6R` cylinder, `L` resolved from Fig. 3), `src/makeGeometry.py` (canonical binary-STL writer + metadata + non-destructive `--check`), committed `stl/nacelle.stl` (2616 triangles, −1.4 % vs the paper's ~2652), `metadata/nacelle.json`, `PROVENANCE.md`, `README.md`, `tests/test_nacelle_data.py` (14 tests) | `6a38f2e`, `cb9f010` | Complete; `--check` byte-identical in both plain and OpenFOAM environments; blade STL generation deferred to S2 (layout/schema reserve it) |
| W3 — kinematics seam | `turbineALSource` azimuth as a time-derived integral (constant-TSR linear + closed-form `tsrAmplitude` separable integral), `angleDeg.<name>` registry persistence, optional `omega.<name>` override, `angleDeg()` accessor | `ad15f96` | Complete; existing-suite regression green; AFTAL (constant TSR) CSV byte-identical to the accumulator; CFTAL oscillation deviation quantified as explicit-Euler truncation of the old accumulator (new value matches RK4) |
| W4a — validation skeleton | `validation/nacelle-asn/config/case.yaml` single source of truth; `tools/generate_case.py` renderer with non-destructive `--check`; committed 14-file `case/` skeleton; package README; `.gitignore`; `tests/test_nacelle_case.py` (14 tests at W4a) | `a052d0d`, `bb72be7` | Complete; renders clean, `--check` exit 0; pure-Python and CI-safe |
| W4b — validation package, docs, fixes | Digitized wall-resolved-LES reference profiles (`data/reference/`, odd stations 1R…19R) with `PROVENANCE.md` + two-source `digitization.json`; `scripts/compareNacelle.py` + `scripts/runNacelle.sh`; `scripts/slurm/stage0.slurm` + prepared-only `production.slurm`; `tests/test_nacelle_compare.py`; root `README.md`/`CHANGELOG.md` + `turbinesFoam/README.md`; W1-scope reduction bugfix and two script repairs | `7cb1f3c`, `951525a`, `e70f8ec`, `002106a`, `29c6ce1`, `1b6636a`, `9dad3ab` | Complete; focused tests 28 passed; full suite 95 passed; stage0 executed on the dev partition; production never submitted |

## W4b Validation Finding and Fix: Rank-Local Kernel Sums (W1-scope bug)

The W4b validation run found a real correctness bug in W1 code, which was fixed as its own work unit:

- **Root cause:** OpenFOAM v2506 `returnReduce()` in `PstreamReduceOps.H` takes `const T&` and returns a reduced copy. `nacelleSurfaceSampler::interpolateVelocity()` called `returnReduce(sumW, …)` / `returnReduce(sumU, …)` and **discarded the return values**, leaving `sumW`/`sumU` rank-local partial sums. A rank holding no cell in a node's 5³ stencil then returned a zero velocity; ranks with cells used a subset average instead of the paper's Eq. 7 global kernel average.
- **Observed symptom:** on the real coarse stage0 run before the fix, the nacelle force CSV was all zero (`0.1,0,0,0,0,0,0`); after the fix (commit `29c6ce1`) the same run reports fx = 12.035 N at t = 0.1, decaying to 5.214 N at t = 2 s.
- **Fix:** `sumW`/`sumU` assigned from `returnReduce()` (commit `29c6ce1`, `fix(turbinesFoam): reduce nacelle kernel sums on every rank`).
- **Regression coverage:** `test_parallel_master_without_stencil` in `tests/test_nacelle.py` translates the test plate to `x = 0.85`, so the whole kernel support lies in the second rank's half of the `x = 0.5` split (the master has no stencil cell). **Negative control:** with the discarded-return version rebuilt, the test fails (`DESIRED: array(0.0402)`); with the fix it passes. The six pre-existing W1 tests could not see the bug because a uniform test flow makes partial averages exact.
- This is a W1-scope defect found by W4b validation; it is reported here as a distinct, confirmed cause with first-hand evidence, not merged into any other finding.

## Verification Evidence (final numbers)

| Check | Command | Result |
|-------|---------|--------|
| Focused case/compare tests (plain env, no OpenFOAM) | `python3 -m pytest -q tests/test_nacelle_case.py tests/test_nacelle_compare.py` | **28 passed** (case 15 + compare 13) |
| Case render | `python3 tools/generate_case.py --check` | exit 0, no output (clean tree) |
| Nacelle integration tests (OpenFOAM env) | `python3 -m pytest -q tests/test_nacelle.py` | 7 passed (6 existing + the new parallel regression) |
| Build | `cd turbinesFoam && ./Allwmake` | exit 0, **0 errors, 0 warnings** |
| Link hygiene | `ldd -r $FOAM_USER_LIBBIN/libturbinesFoam.so` | clean (no undefined symbols; `libsurfMesh` resolves) |
| Full suite | `python3 -m pytest -q` (OpenFOAM env) | **95 passed, 1 warning in 230.32s** — the only warning is the pre-existing `pytest.mark.timeout` unknown-mark warning at `tests/test_al.py:131`. Suite grew 66 → 95 over the change. |

**Stage 0 execution (real submission, dev partition only):**

| Item | Value |
|------|-------|
| Job | `11597925` (`scripts/slurm/stage0.slurm`, 48 ranks) |
| Partition | `sequana_cpu_dev` |
| State / ExitCode / Elapsed | COMPLETED / `0:0` / `00:01:39` (verified with `sacct`) |
| Fixed-run force (coarse) | fx = 12.035 N (t = 0.1) → 5.214 N (t = 2) |
| Compare tool | runs end-to-end on the real run: 120 probe points, 20 samples; exits **3** (acceptance FAIL at 1R/10R) |

The compare exit 3 is **expected and is not a validation result**: it is the per-grid acceptance gate operating on a 2 s unconverged stability run whose averaging window is far shorter than required. **No validation claim is made.** The production averaging run was **never submitted**.

**Production staging:** `scripts/slurm/production.slurm` is prepared-only and keeps its `NACELLE_LONG_QUEUE_AUTHORIZED` gate. Only `sbatch --test-only` was ever run against it; partition `sequana_cpu_long` was confirmed `up` by `sinfo`. No long-queue launch occurred before explicit authorization, and none is performed by this archive.

## Specs Synced to Source of Truth

All five domains are new capabilities; no main spec existed, so each complete spec was copied mechanically (`cp` to a staged temp, `diff -r` readback, atomic `mv`) — never through a model Read/Write path. No `ADDED`/`MODIFIED`/`REMOVED`/`RENAMED` sections were present; each source file is a complete spec.

| Domain | Action | Requirements | Scenarios | sha256 |
|---|---|---|---|---|
| `nacelle-surface-source` | Created | 11 | 26 | `32cf3ca14f0947f30acb0ee67e53612cb64a80ac4dadf6ae182c47fe7d119563` |
| `nacelle-validation-case` | Created | 9 | 19 | `f35f0fb831127eab3384eb5fdd23c9defde0bb522a1d2ea510daab3c2271103e` |
| `surface-sampling-contract` | Created | 7 | 9 | `8278cb0515ec72e6f6d80ac66fc3f747ef9691077c2bd9b9c07f097b4ba99f96` |
| `time-derived-kinematics` | Created | 6 | 10 | `b7f3b3891810eca4d0bf935d1cf24eccf2cbc1c5682a1f8f6aeae7fc5dc8eb46` |
| `turbine-geometry-pipeline` | Created | 7 | 11 | `60c5a6663c48934b9b6b40a8eab0b342664a989e5d5b849b0768bea47e2464b2` |

Total: **40 requirements, 75 scenarios**. The six pre-existing main specs (`actuator-surface-element`, `element-type-selection`, `axial-flow-turbine-asm-tutorial`, `phasevi-data-provenance`, `phasevi-run-and-compare`, `phasevi-validation-case`) were **not modified** by this archive (none was written today).

Main spec paths now current:

- `openspec/specs/nacelle-surface-source/spec.md`
- `openspec/specs/nacelle-validation-case/spec.md`
- `openspec/specs/surface-sampling-contract/spec.md`
- `openspec/specs/time-derived-kinematics/spec.md`
- `openspec/specs/turbine-geometry-pipeline/spec.md`

## Reconciliation of Intermediate Artifacts (Final-State Authority)

- `tasks.md` (highest-ranked source) is 24/24 checked; `apply-progress.md` is the W1–W4b snapshot and its W4b section is current with the final state. No stale pending/blocked claim was carried as a present-tense fact.
- **Recorded deviations where the implementation intentionally differs from the synced spec wording** (specs were copied byte-for-byte and were **not** rewritten by archive; all are documented in `apply-progress.md`):
  1. `time-derived-kinematics` scenario says the azimuth is `ω·(t−t0) (modulo 360°)`; the implementation keeps the integral continuous and monotonic (unwrapped). Rationale: the stronger normative requirement is CSV identity with the accumulator, which wrapping would break past one revolution; the unwrapped value equals the same angle modulo 360°.
  2. `time-derived-kinematics` allows an omega override as "a `Function1` or a registry `uniformDimensionedScalarField`"; the implementation provides the registry `uniformDimensionedScalarField` (`omega.<name>`) only — the shape the S3 adapter actually exchanges. Unset → byte-identical TSR law.
  3. `nacelle-validation-case` "Coarse and medium grids" carries the proposal-derived Δx wording (`R/2.5` coarse, `R/3.75` medium). The rendered **cell counts** (153×80×80, 115×151×151) are authoritative; the package README documents spacings derived from those counts (`Δx ≈ R/5.1` coarse, `≈ R/3.8` medium) and supersedes the exploration Δ values. No rendered file or script asserts `R/2.5` or `R/3.75`.
  4. Station reconciliation: the paper's profile panels are at **odd** multiples of `R` (1R…19R); there is no 10R panel, so the declared 10R stretch is bracketed by the **9R/11R** profiles judged against the worse of the two. No 10R profile was invented.
  5. `surface-sampling-contract` body-frame requirement: a frame bug (SI force list stored in the global frame) was corrected inside the W1 close-out batch by rotating with `bodyToGlobal().T()`; the identity body frame of the W1 case means no CSV change.
- `proposal.md` success-criteria checkboxes were left untouched (historical artifact). Criteria covered by the commits and the evidence above are delivered; the production/validation criteria remain deferred (see Delivery and Deferred).

## Archive Contents

Present (10 pre-move files; bytes preserved; `archive-report.md` additive):

- `proposal.md`
- `exploration.md`
- `design.md`
- `tasks.md` (24/24 complete, 0 unfinished)
- `apply-progress.md`
- `specs/nacelle-surface-source/spec.md`
- `specs/nacelle-validation-case/spec.md`
- `specs/surface-sampling-contract/spec.md`
- `specs/time-derived-kinematics/spec.md`
- `specs/turbine-geometry-pipeline/spec.md`

Absent: `verify-report.md` (verify phase not run), `state.yaml` (none was created), `research.md` (none was created). No artifact was dropped during the move: the hash manifest of the pre-move source matches the archived tree exactly (additive `archive-report.md` excluded).

## Delivery, Deferred, and Open Follow-ups

- **Delivery not performed.** Nothing was pushed and no PR was opened. The session delivery strategy is `single-pr` with an **already-recorded `size:exception`** (W1/W2/W4a/W4b each exceeded the 400-line review budget). Push/PR is an explicit user decision, not an archive action.
- **Production run not submitted.** Only stage0 ran (dev partition). The production averaging run (`sequana_cpu_long`, array coarse/medium) requires explicit long-queue authorization; `production.slurm` is prepared-only.
- **S2 (blade STL generation/consumption and the MEXICO surface case) and S3 (preCICE FSI wiring) are deferred by design.** The sampling contract (`positions()`/`forces()`/`normals()`/`areas()`) and the registry fields are the S1 seams they will consume.
- **Carried follow-ups (out of S1 scope, unchanged):**
  1. Zero-omega override is degenerate: `axialFlowTurbineALSource::calcEndEffects()` divides by `mag(elementVel)` unguarded → SIGFPE for a parked rotor. Pre-existing, documented.
  2. Per-step `angleDeg.<name>` writes create checkpoint-only time directories (no `U`/`p`) for cases whose write interval never lands; a `startFrom latestTime` restart can pick such a directory as "latest". Documented for a follow-up decision.
  3. `startFrom latestTime` is azimuth-idempotent but not solver-bit-identical for ALM cases (element internal state is not persisted) — pre-existing.
  4. The stage0 run directory keeps a stale `postProcessing/profileSamples/` directory from a pre-fix run (gitignored); `runNacelle.sh` could clean `postProcessing/` on re-render.
  5. `shellcheck` is not installed on the host, so the new shell scripts were only syntax-checked (`sh -n`/`bash -n`), not shellcheck-linted.

## Attribution

The nacelle actuator surface model, the friction closure, and the periodic-nacelle validation benchmark are from:

> Yang, X. and Sotiropoulos, F., *A new class of actuator surface models for wind turbines*, arXiv:1702.02108v4 — Sec. 2.2 (nacelle/hub model, Eqs. 19–23) and Sec. 4.1 (validation case, Re = 1000, 30R×20R×20R, ~2652-triangle surface).

Digitized reference profiles are derived from the paper's Figs. 5 and 6 (wall-resolved LES), with provenance and a two-source cross-check recorded in `turbinesFoam/validation/nacelle-asn/data/reference/PROVENANCE.md`. The headline closure is LES WALE; the paper's dynamic SGS model is not available in standard OpenFOAM, and the adaptation is documented in the case README (URANS k-ω SST is a documented smoke fallback, not the headline).

## Byte-Preservation Evidence (verbatim mechanical readback)

Spec sync (per domain, `diff -r` output empty in all cases):

```text
==== [nacelle-surface-source] diff -r (source vs staged temp) ====
[diff exit 0 -> byte-identical]
==== [nacelle-surface-source] diff -r (source vs installed main spec) ====
[diff exit 0 -> byte-identical]
==== [nacelle-validation-case] diff -r (source vs staged temp) ====
[diff exit 0 -> byte-identical]
==== [nacelle-validation-case] diff -r (source vs installed main spec) ====
[diff exit 0 -> byte-identical]
==== [surface-sampling-contract] diff -r (source vs staged temp) ====
[diff exit 0 -> byte-identical]
==== [surface-sampling-contract] diff -r (source vs installed main spec) ====
[diff exit 0 -> byte-identical]
==== [time-derived-kinematics] diff -r (source vs staged temp) ====
[diff exit 0 -> byte-identical]
==== [time-derived-kinematics] diff -r (source vs installed main spec) ====
[diff exit 0 -> byte-identical]
==== [turbine-geometry-pipeline] diff -r (source vs staged temp) ====
[diff exit 0 -> byte-identical]
==== [turbine-geometry-pipeline] diff -r (source vs installed main spec) ====
[diff exit 0 -> byte-identical]
```

Archive move (snapshot taken before the move; `openspec/` is untracked, so `git mv` failed without changes and the guarded plain-`mv` fallback ran):

```text
--- git mv attempt (openspec/ is untracked) ---
fatal: source directory is empty, source=openspec/changes/nacelle-actuator-surface, destination=openspec/changes/archive/2026-09-20-nacelle-actuator-surface
[git mv exit 128 -> fallback path]
[source still present after failed git mv]
--- diff -r (snapshot vs source after failed git mv) ---
[diff exit 0 -> source unchanged by failed git mv]
[plain mv exit 0]
[source absent after move]
--- MANDATORY READBACK: diff -r (pre-move snapshot vs archived destination) ---
[diff exit 0 -> EMPTY OUTPUT: archived bytes identical to pre-move snapshot]
```

Post-move sha256 manifest of the archived tree (excluding the additive `archive-report.md`) vs the pre-move manifest: `diff` empty — all 10 files byte-identical. Archived `tasks.md` sha256 `0d7167e252cc15f27c12e9399c025f084464d8b9011b547e156931788635d5c6` equals the pre-move value.

## Persistence (hybrid store)

- Filesystem: **complete** — the five main specs are synced, the change is moved to `openspec/changes/archive/2026-09-20-nacelle-actuator-surface/`, and this report is persisted.
- Engram: **saved** — topic key `sdd/nacelle-actuator-surface/archive-report`, type `architecture`, project `of-plugins`, observation id `#127` (CLI: `engram save … --project of-plugins --type architecture --topic sdd/nacelle-actuator-surface/archive-report`, exit 0; `capture_prompt: false` semantics — automated SDD artifact). The MCP `mem_save` path was not used because omitted-session writes are ambiguous in this environment; the CLI path does not depend on session selection.
- Mirror read-back: the observation is retrievable under the same topic key (see phase result). The filesystem copy is authoritative; the Engram copy is the hybrid mirror.
