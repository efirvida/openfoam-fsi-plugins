# P2.6 (yaw) and P2.7 (pitch) — experimental side

Branch `prep/p2-6-p2-7-yaw-pitch` from `feat/phasevi-equispaced-blade`. Evidence axes A2 (yaw) and
A3 (pitch) of `odd/tasks/validation-evidence-register.md`. No simulation exists yet; this unit
prepares the reference tables and the comparison script only.

Rules for this unit: new files only (no edits to existing scripts, libturbinesFoam or `runs/`),
no libturbinesFoam rebuild, no Slurm submission, no push.

## Tasks

- [x] 1. Yaw reference tables from sequences H and S (every fixed-yaw point, all speeds):
      P, T, root flap moment, cn/ct at the 5 stations, same schema as `sequence_H_*.csv`.
- [x] 2. Pitch reference tables for I (0), T (2), H/S (3), U (4), J (6) at 0 deg yaw, with the
      pitch sign checked against the NREL report text and the measured pitch channel.
- [ ] 3. `scripts/compareYawPitch.py` + test on a synthetic run dir, importing `comparePhaseVI.py`.
- [ ] 4. `runPhaseVI.sh` flags for one yaw case and one pitch case (below).
- [ ] 5. Full test suite, Conventional commit.

## Sign conventions (verified from Hand et al. 2001, NREL/TP-500-29955, `turbinesFoam/articles/29955.pdf`)

- Pitch, PDF p.20 (report p.10): "blade pitch is defined as the angle between the blade tip chord
  line and the plane of the turbine disk"; limits "-15 deg to 95 deg (90 deg is feathered into the
  wind)". Positive pitch is toward feather. Figure 19 (PDF p.48): "Blade pitch angle measurement
  convention, 0 deg at tip", channels #253, #257 (`B1PITCH`, `B3PITCH`).
- The case applies pitch as `-(twist + pitch_deg)` with the report twist positive toward feather
  (`tools/element_data.py`, `scripts/makeElementData.py:47`): same sign as the report.
- Yaw, Figure B-25 caption (PDF p.142): "In positive yaw, the blade advances into the wind at
  180 deg azimuth for both configurations". Yaw error = YAW + TABLE (Eq. 21, PDF p.67); the
  turntable was at zero for the sequences used here. File names carry negative yaw with the `m`
  marker (`h05m0050` = -5 deg, see `extractUAE6Reference.parse_stem`).

## Simulating a yaw case and a pitch case with `runPhaseVI.sh`

**There is no flag for either.** `runPhaseVI.sh` accepts `-m`, `-u`, `--mesh`, `--domain`,
`-s|--sequence` (H or S), `--solver`, `--nchordwise`, `--n-elements`, `--ranks`,
`--rotational-augmentation`, `--root-effects`, `--tip-effects`, `--tip-correction`,
`--div-phi-u`, `--polar`, `--refine-level`, `--mesh-factor`, `--blade-dz`, `--delta-t`,
`--end-revs`, `--run-label`, `--stage0`, `--restart`, `--run`, `--submit`, `-h`
(case block, lines 105-129); a case-insensitive grep for `yaw|pitch|azimuthalOffset|freeStreamVelocity`
in the script returns nothing. Not added, per the rules of this unit.

- Yaw: the templates `case/system/fvOptions.{ALM,ASM,ASM-MESH}` hard-code `axis (-1 0 0)` and
  `freeStreamVelocity (7 0 0)`; a yawed run needs the inflow (or the axis) rotated, which no flag
  or config key does today. The closest existing invocation, at 0 deg yaw, is
  `runPhaseVI.sh -m ALM -u 7 -s H` (wind speed and sequence only).
- Pitch: pitch is baked into the element tables from `config/case.yaml` `turbine.pitch_deg`, and
  `tools/case_config.py:88` refuses any value other than 3.0. `-s` accepts only H and S, so the
  T/U/J/I rotor speeds are not selectable either.
- `run.json` records neither yaw nor pitch; `compareYawPitch.py` audits the run yaw (magnitude)
  from `system/fvOptions` and states that the run pitch is unaudited.

## Evidence log

- Data on disk (2026-10-13): parquet for H 163, I 51, J 55, S 106, T 21, U 21 stems. The register
  line "I (0) missing" is stale: z08 is downloaded and converted.
- Tasks 1-2: `scripts/extractYawPitchReference.py` (imports `extractUAE6Reference`), tables in
  `data/experiment/yaw-pitch/` (yaw_H 161/805, yaw_S 104/520, pitch 125/625 performance/spanwise
  rows), `--check` rc 0, `tests/test_phasevi_yaw_pitch_reference.py` 9 passed. Measured pitch
  medians (B3PITCH) I -0.010, T 2.021, H 2.989, S 2.986, U 3.955, J 5.979 deg: sign and order
  match nominal. 8 yaw-sweep stems skipped (`*ys*`). Negative-zero stems (`h05m0000`) exist, so
  `file_name` is the unique key, not (speed, yaw_nominal, repetition).
