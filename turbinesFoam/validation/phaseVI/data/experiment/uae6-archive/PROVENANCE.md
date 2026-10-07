# Provenance — UAE6 raw-archive reference tables

## Source

| Field | Value |
|---|---|
| Dataset | NREL Unsteady Aerodynamics Experiment Phase VI (UAE6), **Sequence S** |
| Definition | NREL/TP-500-29955, local copy `turbinesFoam/articles/29955.pdf` |
| Definition sha256 | `822ee980e97780599ad4ec1dc8b4cc8ad41131b0cbbdffa19999d571f6ce4958` |
| Raw archive | `turbinesFoam/articles/uae6/` — `<stem>.hd1` + `<stem>.eng`, 106 Sequence S test points |
| Converted | `turbinesFoam/articles/uae6/parquet/` (produced by `eng2parquet.py`, the only writer) |
| Channel table | `turbinesFoam/articles/uae6/channels.csv` — 285 channels |
| Extract date | 2026-10-07 |

`/articles/` is gitignored, so **the archive is not versioned**. These derived
tables, this file and the extractor are what the repository keeps. No report PDF
and no archive binary is redistributed, matching the rule already recorded in
`data/experiment/PROVENANCE.md`.

## Extractor

`scripts/extractUAE6Reference.py` (committed). It reads the Parquet conversion,
decodes the file names, masks unusable frames and writes the tables.

```sh
python3 scripts/extractUAE6Reference.py                 # Sequence S (default)
python3 scripts/extractUAE6Reference.py --sequences s h # S and H
python3 scripts/extractUAE6Reference.py --check         # verify only, never writes
```

Requires `numpy` and `pyarrow`. It exits 2 with a message when the archive is
absent, when no file matches the requested sequence, or when a file name
disagrees with the data.

## File-name grammar

```
<letter><WW>[m]<YYY(Y)><R>
```

| Field | Meaning |
|---|---|
| `<letter>` | sequence, lowercase (`s`) |
| `<WW>` | nominal wind speed in m/s |
| `[m]` | optional **negative-yaw** marker; with it the yaw field is 3 digits and the angle is negative |
| `<YYY(Y)>` | yaw angle in degrees: 4 digits without the marker, 3 with it |
| `<R>` | repetition digit |

The grammar was **established by decoding the archive, not assumed**, and the
`m` marker is the trap: `h05m0050` measures **−5.141°**, so it is −5°, not +5°.
Reading the yaw field by position (`suffix[:4]`) turns `s0501350` into 13° with
repetition 5 instead of 135°.

Every decoded yaw is therefore asserted against that file's measured `YAW`
channel, and the extractor aborts when they disagree by more than 1°. The check
uses the **circular** mean: the 180° lock reads as a constant `+180` on some
files (`s0701800`, 179.82…179.91°) and as a wrapped ±180 on others
(`s0501800`), and only the circular mean is meaningful for both.

## Row selection

**One canonical row per speed**: the 0°-yaw test point with the **lowest
repetition**. This is the rule the workbook tables already record in
`data/experiment/PROVENANCE.md`, so the two sources are directly comparable.

| Rule | Value |
|---|---|
| 0° yaw | measured `YAW` within ±0.5° |
| Repetition | lowest available for that speed |
| Frames | `err != 128` frames masked out before averaging |

Result: **21 rows**, one per speed from 5 to 25 m/s, and 105 spanwise rows (21 ×
5 stations). Every other Sequence S file lands in `INVENTORY.csv` with a `role`:

| `role` | Count | Meaning |
|---|---|---|
| `canonical-0deg` | 21 | the row used in the performance table |
| `alternate-0deg` | 16 | same condition, higher repetition |
| `off-axis` | 67 | yaw ≠ 0, kept for a future yaw study |

The two 6-minute files (`s07ysu00`, `s10ysu00`) are the 1°/s 360° yaw sweeps.
They are **not** fixed-yaw test points, so the extractor reports them as skipped.
21 + 16 + 67 + 2 = 106, the whole sequence.

## Recomputation caveat

The tables are **recomputed from the raw frames**, not copied from the `.hd1`
header statistics. Those statistics are single-precision one-pass sums, so the
last digits can differ. `hd1_std` in particular is unreliable for nearly constant
channels; nothing here uses it.

## Verification

The derived table was crossed against the workbook-derived table already
committed in `data/experiment/`, which comes from a different encoding (the WDH
`wt_loads_statistics.xls` workbook) of the same measurements.

| Quantity (`s0700000`) | Raw archive | Workbook | Relative |
|---|---|---|---|
| `rpm` | 71.86668729 | 71.8667 | < 1e-5 |
| `tsr` | 5.40679421 | 5.406795165688964 | < 1e-5 |
| `rotpow_kw` | 6.030433149 | 6.0304 | < 1e-5 |
| `lsstqcor_nm` | 801.2650412 | 801.265 | < 1e-5 |
| `eaeroth_n` | 1149.528802 | 1149.5288 | < 1e-5 |
| `wtbaro_pa` | 102209.988 | 102209.9844 | < 1e-5 |
| `wtatemp_degc` | 11.13177536 | 11.1318 | < 1e-5 |
| `rho_kg_m3` | 1.252491143 | 1.252490990875888 | < 1e-5 |
| `yaw_deg` | 0.01102339844 | 0.011 | 2.1e-3 (the workbook rounds to 3 decimals) |
| `yaw_token` | `0000` | `0000` | exact |
| `repetition` | `0` | `0` | exact |

Spanwise `cn`/`ct`/`cm` at the five stations (`s0700000`): **identical** to the
workbook to every printed digit.

`h0700000` was crossed the same way when the H sequence was catalogued
(5.9458 kW / 789.8572 Nm / 1132.0692 N, `cn` at 30 % span 0.8139), which is why
Sequence H is a usable confirmation later.

## Files and units

| File | Content | Units |
|---|---|---|
| `sequence_S_performance.csv` | 21 canonical Sequence S rows | as `data/experiment/PROVENANCE.md` |
| `sequence_S_spanwise.csv` | 21 rows × 5 stations | `r_over_R` fraction, `cn`/`ct`/`cm` non-dimensional |
| `INVENTORY.csv` | one row per Sequence S archive file | see below |

`INVENTORY.csv` columns: `stem` (the archive file name, including its
`uae6.<config>.00.` prefix), `sequence`, `wind_speed_m_s`, `yaw_deg` (decoded
from the file name), `repetition`, `n_frames`, `err_flagged_frames`,
`eng_bytes`, `eng_sha256`, `hd1_sha256`, `role`.

`file_name` in the two table files is the **NREL file name** (`s0700000`), which
is what the report's inventory tables and the workbook use. The archive-only
prefix is kept in the inventory, so the archive remains the sha256-pinned anchor.

## Deliberate formatting differences from the workbook tables

- `wind_speed_m_s` is written `7` where the workbook writes `7.0`; both parse as
  the same float.
- `yaw_deg` carries full precision instead of the workbook's 3 decimals.

Neither changes what `cases_config`/`comparePhaseVI.py` read.

## Adding a sequence

The extractor is sequence-driven, not Sequence-S-specific:

```sh
python3 scripts/extractUAE6Reference.py --sequences s h
```

That emits `sequence_H_*.csv` alongside, with the same row rule. The choice of
which sequences to validate is recorded in `CATALOG.md`.
