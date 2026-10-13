# Yaw and blade-pitch reference tables

Derived from the raw NREL Phase VI archive (`turbinesFoam/articles/uae6/`,
gitignored; parquet conversion of the `.eng` frames). Written by
`scripts/extractYawPitchReference.py`, which reuses `extractUAE6Reference.py`
(stem grammar, `err == 128` frame mask, per-point decoding, `.10g` formatting).

```sh
python3 scripts/extractYawPitchReference.py            # write (about 40 s)
python3 scripts/extractYawPitchReference.py --check    # exit 1 on drift, 2 if no archive
```

## Files and selection rules

| File | Rows | Rule |
|---|---|---|
| `yaw_H_performance.csv` / `yaw_H_spanwise.csv` | 161 / 805 | every fixed-yaw stem of Sequence H, all repetitions, sorted (speed, nominal yaw, repetition) |
| `yaw_S_performance.csv` / `yaw_S_spanwise.csv` | 104 / 520 | same for Sequence S |
| `pitch_performance.csv` / `pitch_spanwise.csv` | 125 / 625 | Sequences I, T, H, S, U, J; nominal 0 deg yaw only; one row per (sequence, speed), lowest repetition; sorted (nominal pitch, sequence, speed) |

Spanwise has 5 rows (r/R 0.30, 0.47, 0.63, 0.80, 0.95) per performance row.
Yaw is selected by the file-name token, and `read_point` checks it against the
circular mean of the measured `YAW` channel (1 deg tolerance).
`h05m0000`-style stems (negative marker, 0 deg) exist; they are measured 0 deg
points, so `(speed, yaw_nominal, repetition)` is not unique in the yaw tables,
`file_name` is. For the pitch table the tie with `h0500000` resolves to the
first in sorted stem order, as in `extractUAE6Reference.py`.

## Columns

The first columns are exactly the committed `sequence_H_*.csv` schema
(see `../PROVENANCE.md`, `../uae6-archive/PROVENANCE.md`). Appended:

| Table | Column | Meaning |
|---|---|---|
| performance | `yaw_nominal_deg` | yaw from the file name, deg |
| performance | `pitch_nominal_deg` | nominal tip pitch of the sequence: I 0, T 2, H 3, S 3, U 4, J 6 deg |
| performance | `b1pitch_deg`, `b3pitch_deg` | mean of channels #253 `B1PITCH`, #257 `B3PITCH` (deg) |
| performance | `b1rfb_nm`, `b3rfb_nm` | mean strain-gauge root flap bending, #225 `B1RFB`, #233 `B3RFB` (channels.csv units `N-m`) |
| performance | `eaerorfb_nm` | mean `EAERORFB`, estimated aerodynamic root flap bending (channels.csv unit `Nm`, i.e. N·m) |
| spanwise | `yaw_nominal_deg`, `pitch_nominal_deg`, `repetition` | as above; `file_name` is the join key to performance |

`eaeroth_n` (thrust) is the acquisition system's *estimate* `EAEROTH`, not a
measured force.

## Sign conventions (Hand et al. 2001, NREL/TP-500-29955)

- Pitch, PDF p.20: "blade pitch is defined as the angle between the blade tip
  chord line and the plane of the turbine disk", limits -15..95 deg, "90 deg is
  feathered into the wind": positive pitch is toward feather. Fig. 19 (PDF p.48):
  #253 / #257 = B1PITCH / B3PITCH, "0 deg at tip".
- Yaw, Fig. B-25 caption (PDF p.142): "In positive yaw, the blade advances into
  the wind at 180 deg azimuth".
- Nominal tip pitch per sequence: CATALOG.md and report p.27.

## Measured vs nominal pitch (copied from the script's printed summary)

```
sequence nominal_deg median_B1PITCH median_B3PITCH n_speeds
I 0 -0.017 -0.010 20
T 2 2.021 2.021 21
H 3 2.987 2.989 21
S 3 2.986 2.986 21
U 4 3.941 3.955 21
J 6 5.983 5.979 21
```

Medians over speeds agree with nominal within 0.06 deg in sign and order
(I < T < H = S < U < J). Sequence I has 20 speeds (5-24 m/s; the others 5-25 m/s): the
25 m/s point is absent from the selected 0 deg stems, not dropped after reading.

## Skipped stems (printed by the script, never silently dropped)

Eight stems are not fixed-yaw test points (1 deg/s yaw sweeps, token `ys`):
`h07ys000`, `h10ys000`, `i07ys000`, `i10ys000`, `j07ys000`, `j10ys000`,
`s07ysu00`, `s10ysu00`. No stem raised in `read_point` and none lacked a parquet
file (stems the script cannot read are listed as `read failed` in its output).

## Notes

- Means exclude frames with `err != 128`, like the other UAE6 tables.
- The measured `yaw_deg` is an arithmetic mean: near +-180 deg it can read about
  -179.9 on files whose YAW channel wraps; use `yaw_nominal_deg` for selection.
