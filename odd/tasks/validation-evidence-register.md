# Evidence register — what lets the solver be presented as robust, with published reliability ranges

Owner request 2026-10-12: record anything that lets us present the solver (ALM, ASM, ASM+mesh)
as a robust solution and publish its reliability ranges with as much evidence against
experiment as possible. Plan: `odd/tasks/validation-master-plan.md`. This file is a register of
evidence axes, data, uncertainty and honesty rules; it creates no result by itself. Every
number quoted from it must come from a committed script, never from this text.

## 1. What a reviewer will ask, and where the answer lives

| Question | Evidence | Status |
|---|---|---|
| Does the code do what it claims? | conservation tests per method (force, moment), momentum closure, kernel truncation regression | P1.1 done, P1.2 ALM done (ASM arms open) |
| Is the answer independent of the free numerical choices? | `eps/h` sweep, mesh ladder, time step, averaging window | P1.4 submitted; mesh ladder blocked by the blade-surface layout (P1.5) |
| Is it right against measurement? | Phase VI, calibrate on H, evaluate frozen on S, pre-registered bands | Phase 2, not started |
| Where does it stop being right? | validity envelope: wind speed (attached to deep stall), yaw, pitch, AoA 3D, dynamic | below, axes A1-A8 |
| Is it right on the thesis rotor? | IEA 15 MW against OLAF / BEM | Phase 3 (cp band open, root polar P3.1) |
| Is it reproducible? | `run.json` provenance, committed scripts, pinned data, tests | partly; section 5 |
| How does it compare with other codes? | NREL blind comparison of Phase VI (Simms et al. 2001) and published CFD / actuator results | the comparison report is NOT in `articles/`; to obtain |

## 2. Evidence axes against the experiment (UAE Phase VI, same rotor)

| Axis | What varies | Quantities | Data | Method |
|---|---|---|---|---|
| A1 wind speed | 5-25 m/s, attached to deep stall | P, T, root flap, spanwise load at 5 stations | S, H (on disk) | P2.1 / P2.2; deep stall reported as a limit, not a criterion |
| A2 yaw | 0-180 deg at low speed, +-10 deg at high speed | same, skewed wake | H, S (on disk, 18-51 yaw files) | **new: P2.6** |
| A3 blade pitch | 0, 2, 3, 4, 6 deg | P, T versus pitch (sensitivity of the model to a pure geometry change) | T (2), H/S (3), U (4), J (6) on disk; **I (0) missing** | **new: P2.7** |
| A4 3D AoA, static | blade pitch ramps and steps, rotating versus parked | sectional cn / ct versus AoA | L (parked, on disk), **K and R (rotating) missing** | **new: P2.5**; isolates polar and rotational augmentation from induction |
| A5 dynamic | sinusoidal AoA, rotating versus parked | hysteresis loops, Leishman-Beddoes envelope | O (parked, on disk), **N (rotating) missing** | **new: P2.5** |
| A6 wake response | pitch step, dynamic inflow | time-resolved induction | **Q missing** (12 files) | optional, FSI transients |
| A7 transition | leading-edge tripped | polar sensitivity | **M missing** (49 files) | optional |
| A8 TSR at fixed wind | elevated rpm | tip-speed-ratio axis | **X missing** (45 files) | optional |
| Wake geometry | helical wake | tip-vortex position | P (on disk, flow visualisation) | inspect Appendix J first; qualitative unless numeric |

Sequence L (parked, 20 and 30 m/s, step AoA) is the cheapest strong test available today: with the
rotor stopped there is no induction, so the measured sectional cn versus AoA is a direct check of
the S809 polar and the element lift lookup, separated from the wake.

## 3. Data to download (owner downloads; mapping verified on the 8 sequences already on disk)

WDH folder number `zNN` = (letter index, A = 1) - 1: H=z07, J=z09, L=z11, O=z14, P=z15, S=z18,
T=z19, U=z20 all match the repo. Same pattern for the rest (INFERRED, check the first `.hd1`):
`https://wdh.energy.gov/data/uae6/uae6.zNN.00`. Put files next to the existing ones in
`turbinesFoam/articles/uae6/` and run `./eng2parquet.py --force --jobs 8`.

| Priority | Sequence | zNN | Files (report) | Why |
|---|---|---|---|---|
| must | **K** Step AOA, probes, rotating | z10 | 18 | rotating counterpart of L (A4) |
| must | **R** Step AOA, no probes | z17 | 21 | same without probe interference (A4) |
| must | **N** Sin AOA, rotating | z13 | 121 | rotating counterpart of O (A5) |
| must | **I** Upwind low pitch (0 deg) | z08 | 49 + 2 | completes the pitch axis (A3) |
| nice | **Q** Dynamic inflow | z16 | 12 | A6 |
| nice | **M** Transition fixed | z12 | 46 + 3 | A7 |
| nice | **X** Elevated rpm | z23 | 45 | A8 |
| later | V tip plate (z21), W extended blade (z22) | | 21, 17 | tip-loss physics, needs geometry changes |
| skip | B-F downwind / cone, E yaw releases, G teetered, 3-9 tower, shroud, sonics | | | not our configuration (upwind, rigid, 0 deg cone) |

Cost: the repo holds 522 files / 16 GB. 30-second files are about 17 MB raw plus 11 MB parquet; K, N, Q, R
are longer, so budget 10-20 GB. The `leahk` group quota is 1.53 of 2 TB: convert, then keep only what is used.
Converter work to expect: `eng2parquet.py` leaves `sequence` empty for L and O (file-name convention
differs); K, N, R use the K/L naming (`K<speed><yaw><RU|RD|ST>`) and a time-varying pitch channel.

## 4. Uncertainty: every comparison is quoted with both

| Source | How it is measured | Status |
|---|---|---|
| iterative / averaging | revolutions in the window, drift per revolution (4 revs drift about 0.7 %/rev) | per run, `rev_history.py` |
| mesh | refinement ladder, fixed ranks (the current 84/84/231/231 ladder confounds mesh and partitioning) | open; needs P1.5 for ASM+mesh |
| projection width | `eps/h` sweep | P1.4 |
| time step | Courant-limited ladder | open |
| experiment repeatability | repeated files (`H0700000` vs `H0700001`), file-to-file scatter and the azimuthal spread inside a file | to compute with a script |
| experiment closure | stations integrate to their own totals within 1.0 / 1.4 % | done (2026-10-10) |
| tunnel blockage | NREL: below 2 % in velocity, below 1 % for most points (Glauert method, Simms 2001). The case is a free box. Power scales with U^3, so 1-2 % in U is about 3-6 % in power: **the same order as the 10 % band** | **new: P2.8**, quantify with a +1 % and +2 % inflow sensitivity run, do not just document |
| tower shadow | measured loads include it; the tower is not modelled | documented limit |
| URANS | cannot capture deep-stall unsteadiness | reported limit |

Acceptance wording to use: "agrees within the combined numerical and experimental uncertainty" only when
the difference is inside the quadrature sum; otherwise report the difference and its likely cause.

## 5. Honesty and reproducibility rules (what makes the claim credible)

- Bands are fixed in the Model Definition BEFORE the run; calibrate on H, evaluate on S unchanged.
- Negative and retracted results stay on record (three retractions are in Engram; the plan log keeps the corrections).
- Every table in a paper is produced by a committed script from data with a hash; `run.json` stores the
  commit, config hash, ranks, `mesh_factor`; runs whose fields were deleted say so in the plan log.
- Pin the environment (module versions, `WM_OPTIONS`, library commit) and publish the tests that pin behaviour.
- A reliability table per method and regime is the deliverable: rows = regime (attached, transition, deep
  stall; yaw range; pitch range), columns = quantity, band, result with uncertainty, evidence link, verdict
  (inside / outside / not claimed). Regimes with no data are listed as "not claimed".
- Positioning: obtain the NREL blind-comparison report (Simms et al. 2001, NREL/TP-500-29494) and the published
  actuator-line / CFD Phase VI studies, and place our S results beside theirs; do not claim a ranking without it.

## 6. Tasks this adds to the master plan

- **P2.5** AoA 3D and dynamic stall: K, L, R (static) and N, O (dynamic), rotating versus parked. L and O first (on disk).
- **P2.6** Yaw envelope on H and S (data on disk).
- **P2.7** Pitch axis: T, U, H/S, J, and I once downloaded.
- **P2.8** Blockage sensitivity (+1 %, +2 % inflow) and the experiment repeatability script.
- **P2.9** Reliability table per method and regime, with the combined uncertainty; positioning against the blind comparison.
