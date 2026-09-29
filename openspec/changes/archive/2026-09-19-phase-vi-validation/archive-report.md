# Archive Report — `phase-vi-validation`

- Change: `phase-vi-validation` — NREL Phase VI validation of turbinesFoam ALM and ASM
- Project: `of-plugins`
- Archived: 2026-09-19 → `openspec/changes/archive/2026-09-19-phase-vi-validation/`
- Artifact store: hybrid — filesystem artifacts are complete and authoritative; the Engram mirror was unavailable to the executor in this runtime (see Persistence)
- Branch: `feat/phase-vi-validation`, base `52fd258`
- Report status: terminal record of the SDD cycle; ranks above `apply-progress.md` (intermediate snapshot) and any unrun optional reports

## Final State at Close

- **Tasks: 17/17 complete** (phases 1–5), per the persisted `tasks.md`. Mechanically counted at archive time: 17 `[x]`, 0 `[ ]`. The archived `tasks.md` bytes are unchanged (`sha256 63baf52794a11b63c366789d459de43a504037ae8608e7b9172f43e3f147d911`).
- **Implementation: complete** for the 17-task scope. No `turbinesFoam/src/` change was made; the change is purely additive (validation package, data, tooling, tests, docs).
- **Verification: `sdd-verify` was NOT run** — it is an optional diagnostics phase and no `verify-report.md` exists. Report that as unrun, not as passed.
- **Apply-phase fresh-context validation: PASS WITH FINDINGS** — one LOW documentation inconsistency (see Reconciliation), no blocking findings.
- 12 phase commits on the branch from base `52fd258`:
  `472c8ae`, `223099b`, `567b16f`, `747c171`, `16ff6ab`, `d5088b4`, `afaebbd`, `786f0f1`, `9e80a16`, `24b1fa6`, `28de14e`, `d5bb7bc`.

## Reconciliation of Intermediate Artifacts (Final-State Authority)

- **LOW inconsistency (confirmed):** `apply-progress.md` ("Remaining tasks", Batch C) states "all 21 tasks complete". The change has **17 tasks** (5 + 4 + 5 + 2 + 1); the persisted, mechanically counted `tasks.md` is the higher-ranked source. The count "21" is a stale/wrong number; the completion claim itself is correct. `apply-progress.md` was left unmodified per the archive contract (historical bytes preserved).
- `apply-progress.md` (Batch C) is a snapshot of the state at its write time. Its Stage 0 claims (jobs, mesh results, stability) are corroborated by the final-state facts supplied by the orchestrator and were carried forward, not re-attributed as present-tense snapshot claims.
- The design's open questions are resolved or explicitly deferred as follows:
  - 20 m/s canonical row correction (`h2000002` → `h20m0000`): resolved in implementation per `design.md` §7 and `apply-progress.md` Batch A.
  - D/64 count correction (spec "≈40 M" → design/implementation `53,394,432`): recorded in `design.md` §5, task 1.3, and the `case.yaml` comment. The synced `phasevi-validation-case` spec still carries the proposal-derived "≈ 40 M" wording — archived as-is, listed as an open documentation follow-up below (it is a `MAY` / optional Stage 3 item; no behavior defect).
  - Long-queue authorization, inflow TI/ℓ choices, and the derived hub model: recorded decisions/deferrals, not blockers.
- `proposal.md` success-criteria checkboxes were left untouched (historical artifact). Criteria covering the generator, mesh checks, TSR gate, data/provenance, pure-Python tests, comparison tooling, docs, and Stage 0 are evidenced by the commits and Stage 0 results. The criterion "7 m/s headline results reported against documented tolerance bands" depends on Stages 1–3 and **is not claimed as delivered by this change** (see Deferred).

## Stage 0 Execution Evidence (final state)

Executed on `sequana_cpu_dev` (user-authorized), per `tasks.md` task 5.1. No long-queue submission was made.

| Job | Step | State | Exit | Elapsed |
|---|---|---|---|---|
| `11597164` | `stage0.slurm --mesh-only` | COMPLETED | 0 | 5:39 |
| `11597169` | `stage0.slurm --runs-only` | COMPLETED | 0 | 10:06 |

- `checkMesh` clean on both meshes: D/32 = 6,674,304 hexahedra, non-orthogonality 0; D/48 = 22,525,776 hexahedra, non-orthogonality 0; "Mesh OK".
- Stability runs at 7 m/s D/32: ALM and ASM both reached 0.25 rev (26 steps to `Time = 0.208` s; stage-0 configured bound 0.25 rev, spec bound ≤ 0.3 rev) with no NaN/Fatal/bounding; final `cp` ≈ 0.310 (ALM) / 0.309 (ASM).
- Earlier failed attempts were diagnosed and fixed in later commits: `11597160` (exit 1, `WM_PROJECT_SITE` unbound under `set -eu`; fixed in `28de14e`) and `11597161` (exit 127, spooled-script path; fixed in `d5bb7bc`).
- Environment constraint recorded: `sequana_cpu_dev` allows one job, max 20 min wall, so Stage 0 ran as two serial jobs; the payload is unchanged.

## Tests

- `python3 -m pytest turbinesFoam/tests/ -q` → **28 passed** (no OpenFOAM required). Final count from the test run, not from an earlier snapshot.

## Specs Synced to Source of Truth

All three domains are new capabilities; no main spec existed, so each complete spec was copied mechanically (`cp` + atomic `mv`) and verified with `diff -r` (empty) and sha256 equality.

| Domain | Action | Requirements | Scenarios | sha256 |
|---|---|---|---|---|
| `phasevi-validation-case` | Created | 11 | 23 | `77fd026ffb1e8803275b164d668f5b30c9aae7e9ecd0c3bf16285877cb729b22` |
| `phasevi-data-provenance` | Created | 7 | 16 | `2ed2f0c3c0413d420d552e8dd121d461120d7cf506cb5af497227695436c49b1` |
| `phasevi-run-and-compare` | Created | 12 | 27 | `af25fe37d29b0e239b6a8f5b60d664254ec5146ae7385a30c9d45fa82f1f7be0` |

Total: 30 requirements, 66 scenarios. No delta sections (`ADDED`/`MODIFIED`/`REMOVED`/`RENAMED`) were present; each source file is a complete spec.

Main spec paths now current:
- `openspec/specs/phasevi-validation-case/spec.md`
- `openspec/specs/phasevi-data-provenance/spec.md`
- `openspec/specs/phasevi-run-and-compare/spec.md`

## Archive Contents

Present (8 pre-move files; bytes preserved):
- `proposal.md`
- `exploration.md`
- `design.md`
- `tasks.md` (17/17 complete, 0 unfinished)
- `apply-progress.md`
- `specs/phasevi-validation-case/spec.md`
- `specs/phasevi-data-provenance/spec.md`
- `specs/phasevi-run-and-compare/spec.md`

Absent: `verify-report.md` (verify phase not run), `state.yaml` (none was created). No artifacts were dropped during the move: the sha256 manifest of the pre-move source matches the archived tree exactly (additive `archive-report.md` excluded).

## Deferred / Out of Scope (prepared only)

- **Stages 1–3 (production runs)**: blocked on the pending long-queue authorization. `scripts/slurm/production.slurm` is prepared only; no auto-submit path was exercised. The sign gate (`comparePhaseVI.py --sign-gate`) MUST pass before any production submission.
- **MEXICO validation**: remains a separate deferred change at `openspec/changes/mexico-validation/`; untouched by this archive.
- No source, test, case, or data file was modified by this archive operation; no commit, push, or PR was made; `openspec/` remains untracked.

## Open Follow-ups (documented, not part of this change)

1. `run.json` records `git_commit: "unknown"` inside batch jobs — provenance gap; follow-up should read `.git/HEAD` as fallback or surface the git error.
2. Spec `phasevi-validation-case` D/64 wording says "≈ 40 M" while the design/implementation arithmetic is 53,394,432 cells. Optional (`MAY`) item; fix wording in a future spec touch.
3. Spanwise CM comparison requires a `cm` column in the element CSV — separate future source change; CM is excluded from the headline and documented in the comparison output.
4. The `apply-progress.md` "21 tasks" wording (LOW) is preserved as historical; no correction was made to archived bytes.

## Byte-Preservation Evidence (verbatim mechanical readback)

Spec sync (per domain, `diff -r` output empty in all cases):

```text
--- diff -r (source spec vs staged temp) ---
[diff exit 0 -> byte-identical]
--- diff -r (source spec vs installed main spec) ---
[diff exit 0 -> byte-identical]
```

Archive move (snapshot taken before move; `openspec/` is untracked, so `git mv` failed without changes and the guarded plain-`mv` fallback ran):

```text
[git mv exit 128 -> fallback path (openspec/ is untracked)]
[source still present after failed git mv]
--- diff -r (snapshot vs source before fallback) ---
[diff exit 0 -> source unchanged by failed git mv]
[plain mv exit 0]
[source absent after move]
--- MANDATORY READBACK: diff -r (pre-move snapshot vs archived destination) ---
[diff exit 0 -> EMPTY OUTPUT: archived bytes identical to pre-move snapshot]
```

Post-move sha256 manifest of the archived tree (excluding the additive `archive-report.md`) vs the pre-move manifest: `diff` empty — all 8 files byte-identical. Archived `tasks.md` sha256 `63baf52794a11b63c366789d459de43a504037ae8608e7b9172f43e3f147d911` equals the pre-move value.

## Persistence (hybrid store)

- Filesystem: complete — main specs synced, change moved to `openspec/changes/archive/2026-09-19-phase-vi-validation/`, this report persisted.
- Engram: **outstanding** — MCP tools (`mem_save` / `mem_search`) were unavailable in this runtime. The intended mirror is topic key `sdd/phase-vi-validation/archive-report` (`type: architecture`, `capture_prompt: false`). No observation IDs were read or written; partial hybrid persistence is reported rather than claimed complete.
