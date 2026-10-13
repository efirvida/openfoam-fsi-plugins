# Handoff prompts — P2 preparation that needs no cluster (written 2026-10-13)

Run each in its own fresh session (effort `medium`). Shared rules, valid for all three:
- Raw archive: `turbinesFoam/articles/uae6/` (gitignored; `uae6.zNN.NN.<stem>.{eng,hd1}`, Parquet in `parquet/`,
  `manifest.csv`, `channels.csv`, `README.md`). Zones: K = z10, R = z17, N = z13, I = z08, L/O/H/S already used.
  Committed index: `validation/phaseVI/data/experiment/uae6-archive/{CATALOG.md,INVENTORY.csv,PROVENANCE.md}`;
  decoder/extractor: `validation/phaseVI/scripts/extractUAE6Reference.py`.
- Evidence plan: `odd/tasks/validation-evidence-register.md` (axes A2-A5, section 4); plan: `odd/tasks/validation-master-plan.md`.
- Work on a new branch off `feat/phasevi-equispaced-blade` (name per prompt). Add files; do NOT edit
  existing scripts, `libturbinesFoam` sources, or anything under `runs/`. Do NOT rebuild `libturbinesFoam` (P2.1 jobs
  11614175-80 are queued). No Slurm submissions.
- Follow AGENTS.md: scripts in `validation/phaseVI/scripts/` (or `validation/tools/` if shared), a pytest per script
  (`python3 -m pytest turbinesFoam/tests tools/tests -q`), run `python3 tools/analysis_gap.py` before writing a new
  analysis, no inline analysis, bound all command output. Close with a work-unit commit and a short note in the
  matching `odd/tasks/` file. Do not push.

## Prompt 1 — branch `prep/p2-8-repeatability` (P2.8, register section 4)

Write `scripts/experimentRepeatability.py` + test. For every (sequence, speed, yaw) group in the archive that has
more than one repetition (e.g. `h0700000` vs `h0700001`), compute the file-to-file scatter of power, torque, thrust
and the five spanwise cn/ct stations, and the azimuthal spread inside one file (from the `.eng` frames). Output a
committed CSV under `data/experiment/` and a one-paragraph summary in `odd/tasks/validation-evidence-register.md`
section 4 (status column: "computed"). The number P2.9 will quadrature-sum with the numerical uncertainty is the
file-to-file standard deviation as a fraction of the mean; state it per quantity and per speed (7 and 10 m/s first).
Also state which groups have no repetition, so P2.9 does not quote a scatter it does not have.

## Prompt 2 — branch `prep/p2-6-p2-7-yaw-pitch` (P2.6 yaw, P2.7 pitch)

Write the experimental side only (no simulations exist yet). (a) Yaw: from sequences H and S build the reference
tables power/thrust/root-flap-moment-if-available and the five-station cn/ct versus yaw (0-180 deg low speed,
+-10 deg high speed), same schema as `sequence_H_*.csv`, via `extractUAE6Reference.py` conventions (note the `m`
negative-yaw file-name marker). (b) Pitch: tables of P and T versus blade pitch for T (2 deg), H/S (3), U (4), J (6)
and I (0, zone z08, now downloaded). Check the sign convention of the pitch angle against the NREL report text before
tabulating. Then write `scripts/compareYawPitch.py` (+ test with a synthetic run directory) that, given a run
directory and a yaw or pitch value, produces the same simulation-versus-experiment tables as `comparePhaseVI.py`.
Do not duplicate `comparePhaseVI.py`: import its functions. Report in `odd/tasks/p2-6-p2-7-yaw-pitch.md` the exact
`runPhaseVI.sh` flags needed to simulate a yaw and a pitch case (read the script; if it has no such flag, say so
and do not add one).

## Prompt 3 — branch `prep/p2-5-aoa-dynamic` (P2.5, axes A4-A5)

Experimental side of the 3D AoA and dynamic-stall axes, now that K, R, N, I, L, O are all on disk. Build reference
tables (sectional cn/ct/cm at the five stations versus AoA; for N and O the phase-averaged hysteresis loop over the
oscillation cycles) for L and K and R (step AOA: parked versus rotating) and O versus N (sin AOA: parked versus
rotating). Verify the zone/sequence mapping of K, R, N against `CATALOG.md` before trusting it, and record any
mismatch. Write `scripts/aoaDynamicReference.py` (+ test on a short synthetic frame set) and a
`odd/tasks/p2-5-aoa-dynamic.md` that states what the data can and cannot isolate (polar versus rotational
augmentation versus induction), and which of those a quasi-steady ALM/ASM can be judged on. Do not propose
simulation cases beyond a list of the Phase VI flags they would need.
