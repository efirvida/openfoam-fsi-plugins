# Archive Report — `rotational-augmentation`

- **Change**: `rotational-augmentation` — Du–Selig rotational augmentation (3D
  stall delay) in the shared actuator-element load chain, a Leishman–Beddoes
  singularity guard, the Phase VI config/render switch, and a committed 0.25-rev
  D/32 proxy harness.
- **Project**: `of-plugins`
- **Archived**: 2026-09-24 → `openspec/changes/archive/2026-09-24-rotational-augmentation/`
- **Artifact store**: `openspec` (authoritative) + Engram mirror, topic
  `sdd/rotational-augmentation/archive-report`
- **Branch**: `feat/nacelle-actuator-surface` (remote `efirvida/openfoam-fsi-plugins`);
  pushed through `f2c69e7`; the later RA commits (`ea399ae`, `5325ecc`,
  `47cb02e`) are **local only** — no push, no PR. `openspec/` remains untracked.
- **Report status**: terminal record of the SDD cycle. It ranks above
  `apply-progress.md` and `verify-report.md`, which are intermediate snapshots
  preserved in this folder for history.

## Final State at Close

- **Tasks**: all task checkboxes complete — **21 `[x]`, 0 `[ ]`** (W1.1–W1.7,
  W2.1–W2.2, W3.1–W3.5, W4.1–W4.4), mechanically counted from the archived
  `tasks.md` (`sha256 45c461fe4cdef7907c4c60f54a7db0a292aa369c6b4416ffeadddb9ef06f8018`).
- **Implementation**: **complete** for the delivered scope. The correction is
  additive and opt-in; with the `rotationalAugmentation` block absent or
  `active off` the chain is byte-identical (control output byte-for-byte identical
  pre/post fidelity fix).
- **Verification**: **partial.** Every functional and regression check passes and
  the fidelity correction is implemented, tested and documented. However the
  change's **own U13 primary criterion (`augmentation-on` `cp`/`ct` positive) is
  not met** — the corrected values are ≈0 but strictly negative — so the harness
  fails loudly and the criterion is **not formally closed**. The real gate is the
  later, explicitly authorized converged campaign.
- **No validation claim** is earned by this change.
- **No production job** was submitted, cancelled or modified.

## Work-Unit Ledger

| Unit | Deliverable | Commits | Final state |
|------|-------------|---------|-------------|
| W1 — Du–Selig in the shared chain | `rotationalAugmentation` block read (default off, `FatalIOError` on unknown model, warn-and-skip when geometry absent); `correctRotationalAugmentation()` hooked in `calculateForce` after `lookupCoefficients()` and before dynamic stall; `radius`/`rotorRadius` injection in `createElements` and AFTAL forwarding; pure-Python expected-value test + 10 solver-driven integration tests + fixture; turbinesFoam README | `a800be1`, `1130427` | Complete; build + `ldd -r` clean; default-off byte gate; radial-geometry, parallel and restart tests green |
| W2 — Leishman–Beddoes singularity guard | `calcK1K2` analytic 2×2 solve behind a scaled determinant guard (`mag(det) > 1e-12·scale`) with a recorded `K1_=K2_=0` fallback and `WarningInFunction`; no fit retuning; guard tests + fixture | `e56158a`, `904a201` | Complete; guarded run passes `t = 0.008 s`/`0.016 s` with no `Singular Matrix`; well-conditioned path unchanged to round-off; blast radius one method |
| W3 — Phase VI config/render | `case.yaml` `actuator.rotational_augmentation` + `end_effects.root`; `generate_case.py` renderer + CLI toggles; re-rendered committed twins (augmentation off, `rootEffects on`); case/render tests; Phase VI README | `8df345c` | Complete; `generate_case.py --check` clean; three twins differ only in blade keys; prepare-only runner gate green |
| W4 — Proxy verification harness | Committed 0.25-rev D/32 harness (serial dev queue, self-contained copies, control gate + fail-loud criteria); proxy tests; comparison caveat; README/CHANGELOG | `3a5feaf`…`f2c69e7` (incl. `cdddfca`, `2b20c15`, `4ca1957`, `f2c69e7`) | Complete (harness); matrix gate **not met** on the U13 primary criterion; harness exits 1 |
| Fidelity correction (post-apply) | Prefactor form of Eqs. 11–12 restored; in-code documentation of formulation/sources/cross-checks; tests + docs updated | `ea399ae` (docs `5325ecc`) | Complete; reference test pins the prefactor form and forbids the split form |
| Follow-up fix — W-1 | CLI `--rotational-augmentation` falls back to YAML when the flag is absent; `runPhaseVI.sh` forwards it only when requested; tests | `47cb02e` | **W-1 closed**; the `phasevi-validation-case` "Augmentation switch rendered" scenario now holds |

## The Fidelity Finding (dominant correction in this cycle)

- **Finding.** The first implementation (W1) matched arXiv:1702.02108v4 Eqs. 11–12
  **as printed** — `(1.6(c/r)^a − X)/(0.1267b + X) − 1`. That printed *split*
  form is a **transcription error** relative to the original Du–Selig
  formulation. `research-formulation-fidelity.md` establishes the material
  impact: the split form **inverts the drag-correction sign** over most of the
  blade and enlarges the outboard `fL < 0` region ~4× by span.
- **Correction.** `ea399ae` restores the primary-source **prefactor** form:
  `fL = (1/2π)[(1.6(c/r)/0.1267)·(a − X_L)/(b + X_L) − 1]` (and likewise `fD`,
  with `X_D` exponent `(d/(2Λ))(R/r)`); `a`/`b` are fraction constants, not an
  exponent of `c/r`. The exponent `(d/Λ)(R/r)`, `Λ`, the near-tip behaviour, the
  no-clamp decision and the default-off semantics are unchanged.
- **Five independent cross-checks** (`research-formulation-fidelity.md`, Engram
  #179): Du & Selig (1998) AIAA-98-0021 as reproduced by **NREL AirfoilPrep.py**,
  **BYU CCBlade.jl**, **Munduate (2002)** Eq. 3.6, **IOP 2024** Eq. (3), and Yang's
  own later peer-reviewed review **Li/Liu/Yang (2022), *Energies* 15:6533**
  Eqs. 21–22.
- **In-code documentation.** `correctRotationalAugmentation()` and its declaration
  state the formulation, every symbol, the primary source, the cross-checks, the
  transcription-error note, `a=b=d=1`, the unclamped outboard `fL < 0`/`fD < 0`
  behaviour, and the `c/r`/`R/r`/`Λ` inputs. Reference test: `fL = 0.3394`,
  `CL,3D = 1.534` at the hand sample; the split form (`fL ≈ 0.20`,
  `CL,3D ≈ 1.19`) is pinned as forbidden.

### Corrected proxy numbers (0.25-rev D/32 dev queue; harness `--evaluate`)

Means over the 26 written rows, final row (`t = 0.208 s`) in parentheses:

| U13 variant | `cp` mean (final row) | `ct` mean (final row) | mid-span `c_ref_t` |
|---|---|---|---|
| `control` | −0.044809 (−0.045859) | −0.015346 (−0.015705) | −0.070378 |
| `augmentation-on` | −0.000080 (−0.002094) | −0.000027 (−0.000717) | +0.305817 |
| `augmentation-on + root-off` | **+0.021690** (+0.019482) | +0.007428 (+0.006672) | +0.436461 |

U7 final-row `cp`: `0.309981` / `0.344433` / `0.373306`; root-off power deficit
−14.99 % → **+1.79 %**. Control output is **byte-for-byte identical** to the
pre-fix run (additive default-off preserved).

| Gate | Result |
|---|---|
| Control reproduces the converged failure (`cp ∈ [−0.0473, −0.0349]`) | **PASS** (−0.044809) |
| Secondary spanwise sign at U13 (mid-span `c_ref_t ≥ +0.02`) | **PASS** (+0.305817) |
| Primary U7 ablation (deficit toward/inside ±15 %) | **PASS** (+1.79 %) |
| Primary U13 integrated signal (`augmentation-on` `cp`/`ct` > 0) | **FAIL** (≈0, strictly negative; harness exit 1) |

## Partial Verdict (honest)

The implementation is faithful to the delta specs and every
functional/regression check passes; the committed proxy harness works and
**fails loudly as designed**. What is **not** established:

- That Du–Selig augmentation alone, or combined with `rootEffects off`, flips the
  U13 integrated sign. The corrected `augmentation-on` `cp`/`ct` are ≈0
  (−8.0e-5 / −2.7e-5) — a ~640× magnitude reduction from the pre-fix values, but
  still strictly negative. The `augmentation-on + root-off` variant does have
  positive `cp`/`ct`.
- **Why the criterion is not formally closed**: the 0.25-rev proxy carries an
  observed **≈11 % systematic bias** vs the converged baseline; the corrected
  ≈8e-5 residual is far inside that noise and the gate is a strict `> 0` with no
  tolerance. The proxy cannot resolve "≈0 within noise" from a genuine sign
  failure. The real gate is the **converged campaign** (ALM + ASM + ASM-MESH,
  `aug+root-off` candidate), **prepared-only** and requiring explicit
  authorization.
- No converged Phase VI validation claim exists (no production campaign).

## Finding Status at Close

| ID | Finding | Status at close | Evidence |
|---|---|---|---|
| **C-1** | U13 primary criterion not met; validation claim unearned | **Still open — downgraded, not a pass** | `--evaluate` exit 1; `cp = −0.000080`, `ct = −0.000027`; mechanism (transcription error) fixed, residual ≈0 |
| **W-1** | YAML augmentation switch did not drive the CLI render | **CLOSED** (`47cb02e`) | `--rotational-augmentation` defaults to `None` and honours the YAML `active`; runner forwards the flag only when requested; tests added |
| **W-2** | Committed docs did not record the proxy outcome | **RESOLVED** (`5325ecc`) | `CHANGELOG.md` "Measured outcome"; Phase VI README corrected-form table |
| **W-3** | ASM-mesh inheritance not runtime-tested | **Open** | `test_all_models_inherit` covers ALM + no-mesh ASM only; mesh surface structurally guaranteed (`bladeSurfaceSource` consumes `element.force()`) |
| **S-1** | `design.md` stale on the W4 render-level and `profileData` deviations | **Open** (planning artifact only) | design still lists `profileData` "Unchanged" and element-key indentation |
| **S-2** | Default-off byte-identity demonstrated internally, not vs a pre-change binary | **Open (low risk)** | control metrics byte-identical; gate is structural |
| **S-3** | Proxy control `c_ref_t` reference constant stale | **Open (informational)** | `-0.063` vs observed −0.070378 (not a gate) |
| **N-1** | U13 primary gate has no noise tolerance | **Open (by design)** | strict `> 0` left unweakened; converged campaign settles it |
| **N-2** | Full-suite intermittent OpenMPI openib `MPI_Init` segfault on some nodes | **Environmental, not code** | `test_parallel` passes in isolation; no regression |

**Out of scope, left unfixed (correctly):** `c_ref_t` vs measured CT ≈2×
definitional mismatch (documented caveat); LB K1/K2 fit-input review (guard only);
no new polar data / free-parameter calibration; end-effect model stays `Glauert`;
the α-taper robustness safeguard is a **separate change**; S3 / preCICE / adapter
/ `fsiOmega` / `modules/*` untouched.

## Prepared-Only Campaign (the next gate)

The converged campaign (ALM + ASM + ASM-MESH, `aug+root-off` candidate) is
**prepared-only**. No automated step of this change submits, cancels or modifies
a production job; the suspended production arrays remain **read-only baselines**.
Running it requires **explicit HPC authorization**.

## Specs Synced to Source of Truth

Three **new** capabilities and three **modified** capabilities. The modified main
specs were composed with the native `gentle-ai sdd-archive-compose` (exit 0 in
every case; requirement matched by name; unrelated requirements preserved
byte-for-byte; RENAMED → MODIFIED → REMOVED → ADDED order). The new capabilities
have no main spec, so the complete delta spec was copied mechanically (`cp` to a
staged temp, `diff -r` readback **empty**, atomic `mv`) — never through a model
Read/Write path.

| Domain | Action | Requirements | Scenarios | Resulting sha256 |
|---|---|---|---|---|
| `rotational-augmentation` | Created (6 added) | 6 | 13 | `9bb2e3f4a6d2277b8ab69167a34e559e138103b6da89ad17f4f51c90d6334629` |
| `dynamic-stall-singularity-guard` | Created (3 added) | 3 | 5 | `c5d9dc12faf809d5902a647c828240ca6d7aa8f16a04b4df6c88dfa1206859e3` |
| `phasevi-proxy-verification` | Created (4 added) | 4 | 9 | `0aab338abcda004ebebb8674188ef3e6b1d23fcaf96d7d407be0ea324348bc63` |
| `actuator-surface-element` | Updated (1 modified) | 1 | 3 | `63865518d41fc9eb9e3e4164164896d66073566cf23f6c3991bb35de082fc87f` |
| `element-type-selection` | Updated (1 modified) | 1 | 5 | `41bdae6249aa8b56389dbe9eae19a4801c4a86829796bef93337478f13d058dc` |
| `phasevi-validation-case` | Updated (2 modified) | 2 | 8 | `80d54b94506bef1a53a8312d0d5ef22fe916de11cdaf448cdd167d9f419ebe5d` |

Canonical source-of-truth paths:
`openspec/specs/{rotational-augmentation,dynamic-stall-singularity-guard,phasevi-proxy-verification,actuator-surface-element,element-type-selection,phasevi-validation-case}/spec.md`.

## Archive Contents and Readback

Archived with a mechanical move (`git mv` refused the untracked `openspec/` tree
with `source directory is empty`; the source was verified unchanged against a
pre-move recursive snapshot, then plain `mv` was used). The mandatory
snapshot-vs-archived `diff -r` was **empty (status 0)** — byte-identical.

Present in the archive: `proposal.md`, `exploration.md`, `design.md`,
`research-formulation-fidelity.md`, `tasks.md`, `apply-progress.md`,
`verify-report.md`, `specs/` (6 deltas), and this `archive-report.md`
(additive-only, excluded from the readback).

```
diff -r <snapshot>/source <archive-destination>
(no output — status 0, byte-identical)
```

Archived artifact sha256:

```
ff34f0cd75d8adac8d37094830cf074780a5da584c1d445644464602f896841a  apply-progress.md
0c1b5e1b8d71f04bb077548da50d2acc29a58c26131cb0733f0ad5c4944b104e  design.md
5636ce25927be86682a3505d883639e7ca58c449faad40d70db1f24329b27887  exploration.md
da02f8bac657616373edd4198f4ad0492949b6908235bd53e0195089b9aa51e3  proposal.md
948ee3f1f62d70c4a2aaa79e213fdb7809f76bfc7c685192e07a0fe644e8f333  research-formulation-fidelity.md
45c461fe4cdef7907c4c60f54a7db0a292aa369c6b4416ffeadddb9ef06f8018  tasks.md
2a4d8a6fed72f0640cd5c4d5587aa4f23ef8756413db9bd58ac95120dbd9eaff  verify-report.md
```

## Source Attribution

- **Du & Selig (1998)**, AIAA-98-0021 — the original rotational-augmentation
  formulation (primary source; closed access, established by triangulation).
- **Yang & Sotiropoulos**, *A new class of actuator surface models for wind
  turbines*, arXiv:1702.02108v4 — the reference for the shared chain; its printed
  Eqs. 11–12 carry the **documented transcription error**.
- **Independent cross-checks**: NREL `AirfoilPrep.py`, BYU `CCBlade.jl`,
  Munduate (2002), IOP 2024, Li/Liu/Yang (2022) *Energies* 15:6533.

## Next Recommended

1. **Authorize and run the converged campaign** (ALM + ASM + ASM-MESH,
   `aug+root-off` candidate) with explicit HPC authorization — this is the real
   gate for C-1, which the 0.25-rev proxy cannot resolve.
2. **Scoped follow-up** for the physics: decide the outboard treatment (literal
   unclamped `fL < 0` / `fD < 0` vs the paper's intent and the root/end-effect
   lever); a single tested lever does not flip U13.
3. **Close the remaining findings** in later changes: W-3 (ASM-mesh runtime
   inheritance test), S-1 (refresh `design.md`), S-2 (literal pre-change byte
   compare), S-3 (stale proxy reference constant), and the α-taper safeguard
   (separate change).

## SDD Cycle Complete

The change is archived. Implementation: complete for the delivered scope.
Verification: **partial** — engineering checks pass; the U13 primary criterion is
unclosed and no validation claim is made. Unfinished work and unresolved
findings: W-3, S-1/S-2/S-3, N-1; C-1 remains open pending the authorized
converged campaign.
