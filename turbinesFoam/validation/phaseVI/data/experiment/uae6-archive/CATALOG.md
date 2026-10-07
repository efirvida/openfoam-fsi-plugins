# UAE6 (NREL Phase VI) experimental archive — sequence catalog

What experimental campaigns this repository holds, verified against the defining
report, and which of them the ALM validation should use.

## Source and definition

| Field | Value |
| --- | --- |
| Raw archive | `turbinesFoam/articles/uae6/` — **522 test points**, `<stem>.hd1` + `<stem>.eng` |
| Converted | `turbinesFoam/articles/uae6/parquet/` — 522 Parquet files (one per test point) |
| Converter | `turbinesFoam/articles/uae6/eng2parquet.py` (the only writer) |
| Channel table | `turbinesFoam/articles/uae6/channels.csv` — 285 channels, same layout in all 522 files |
| Definition | NREL/TP-500-29955, local copy `turbinesFoam/articles/29955.pdf`, sha256 `822ee980e97780599ad4ec1dc8b4cc8ad41131b0cbbdffa19999d571f6ce4958` |
| Format | 285 × float32 + 1 × uint8 error byte per frame, little endian; 1.92 ms per frame |
| Fetch method | A2E/WDH REST client — a `downloader-<hash>` binary (ELF x86-64, statically linked, 7.3 MB) calling `https://70d76sxu18.execute-api.us-west-2.amazonaws.com/prod`. **The tool was deleted on 2026-10-07 at the user's request**, so it is recorded here instead: the archive is public at WDH, and what this repository relies on is the per-file inventory check against the report tables above, not the fetch tool. |

`/articles/` is gitignored, so **none of the archive is versioned**. This
catalog and the derived numeric tables are what the repository keeps; the same
rule the existing `data/experiment/PROVENANCE.md` follows ("no report PDF or
workbook is redistributed — only derived numeric tables").

## Inventory cross-check

Every sequence's local file count was compared against its own inventory table
in Appendix C of the report. **All eight match, 522 = 522.**

| Seq | Config token | Report table (PDF p.) | Report inventory | Local `.hd1` | Match |
| --- | --- | --- | --- | --- | --- |
| H | `uae6.z07.00` | C-7 (p. 193) | 161 × 30 s + 2 × 6 min | 163 | ✅ |
| J | `uae6.z09.00` | C-9 (p. 195) | 53 × 30 s + 2 × 6 min | 55 | ✅ |
| L | `uae6.z11.00` | C-11 (p. 199) | 6 of varying duration | 6 | ✅ |
| O | `uae6.z14.00` | C-14 (p. 205) | 131 of varying duration | 131 | ✅ |
| P | `uae6.z15.00` | C-15 (p. 209) | 19 of 3-minute duration | 19 | ✅ |
| S | `uae6.z18.00` | C-18 (p. 212) | 104 × 30 s + 2 × 6 min | 106 | ✅ |
| T | `uae6.z19.00` | C-19 (p. 213) | 21 × 30 s | 21 | ✅ |
| U | `uae6.z20.00` | C-20 (p. 214) | 21 × 30 s | 21 | ✅ |
| | | | **522** | **522** | |

`(F)` / `(P)` below is the report's own legend (Table 1, PDF p. 24):

> (F) — Test conditions representative of field operation
> (P) — Test conditions designed to explore specific flow physics phenomena

## Coverage

Counts derived from the file names, with the yaw field decoded (see the grammar
below). Two 6-minute files per sequence are the 1°/s 360° yaw sweeps.

| Seq | (F)/(P) | Parked/Rotating | Tip pitch | Blade press. | Probe press. | Speeds at 0° yaw | Distinct yaw values |
| --- | --- | --- | --- | --- | --- | --- | --- |
| H | (F) | Rotating 72 rpm | 3° | X | X | 21 | 16 (0…180, both signs) |
| J | (F) | Rotating 72 rpm | 6° | X | X | 21 | 3 (0/10/30) |
| S | (F) | Rotating 72 rpm | 3° | X | — | 21 | 11 (0…180) |
| T | (F) | Rotating 72 rpm | 2° | X | X | 21 | 1 (0) |
| U | (F) | Rotating 72 rpm | 4° | X | X | 21 | 1 (0) |
| P | (P) | Rotating 72 rpm | 3°, 12° | *visualize* | — | 4 | 1 (0) |
| L | (P) | **Parked** (rotor lock) | ramp/step | X | X | — | — |
| O | (P) | **Parked** (rotor lock) | sinusoidal | X | X | — | — |

Sequences L and O do not use the `YYYY` yaw field at all: L is
`l<WW>00<RU|RD|ST>0` (20/30 m/s × ramp-up / ramp-down / step) and O is a
sinusoidal AOA campaign indexed sequentially. Their counts are file counts, not
speed counts.

The decoded `manifest.csv` columns confirm it: **144 of the 522 names carry no
fixed-yaw field** — all of L (6) and O (131), the six 6-minute sweeps (two each
in H, J and S), and P's pitch-marker variant `p10000a0`. They are left empty
rather than guessed. The same columns also confirm the `m` sign rule outside H:
P carries 14 names with a negative yaw (`p05m0450` → −45°).

## File-name grammar (verified against the data, not assumed)

```text
<letter><WW>[m]<YYYY><R>
```

| Field | Meaning |
| --- | --- |
| `<letter>` | sequence, lowercase in the archive (`h`, `j`, `l`, `o`, `p`, `s`, `t`, `u`) |
| `<WW>` | nominal wind speed in m/s |
| `[m]` | optional campaign marker, e.g. `h05m0001` (yaw `0000`, repetition `1`) |
| `<YYYY>` | yaw angle in degrees, zero-padded; a leading `M` is negative (`M030` = −30°) |
| `<R>` | repetition digit |

**The parse is never trusted on its own.** Every stem's yaw was checked against
that file's measured `YAW` channel:

| Stem | Parsed yaw | Measured `YAW` mean | Result |
| --- | --- | --- | --- |
| `s0500050` | 5° | 5.048° | ✅ |
| `s0500100` | 10° | 10.021° | ✅ |
| `s0500200` | 20° | 20.015° | ✅ |
| `s0500300` | 30° | 29.947° | ✅ |
| `s0500450` | 45° | 44.982° | ✅ |
| `s0500600` | 60° | 59.983° | ✅ |
| `s0500750` | 75° | 75.036° | ✅ |
| `s0500900` | 90° | 90.038° | ✅ |
| `s0501350` | 135° | 135.061° | ✅ |
| `s0501800` | 180° | ±180° (encoder wrap at the 180° lock) | ✅ |

A silently wrong yaw parse would corrupt the reference table without any visible
symptom, so the extractor must assert the parsed yaw against the channel mean
and abort on a mismatch.

## Cross-source corroboration

The raw archive and the WDH-workbook-derived tables already committed in
`data/experiment/` are **independent encodings of the same measurements**. Where
they overlap, they agree to every published digit:

| Test point | Quantity | Raw archive (decoded here) | Committed workbook CSV |
| --- | --- | --- | --- |
| `s0700000` | rpm | 71.8667 | 71.8667 |
| `s0700000` | `rotpow_kw` | 6.0304 | 6.0304 |
| `s0700000` | `lsstqcor_nm` | 801.265 | 801.265 |
| `s0700000` | `eaeroth_n` | 1149.53 | 1149.5288 |
| `s0700000` | `cn` at 30/47/63/80/95 % | 0.8034 / 0.9114 / 0.8653 / 0.7707 / 0.5064 | identical |
| `h0700000` | `rotpow_kw` | 5.9458 | 5.9458 |
| `h0700000` | `lsstqcor_nm` | 789.86 | 789.8572 |
| `h0700000` | `eaeroth_n` | 1132.07 | 1132.0692 |
| `h0700000` | `cn` at 30 % | 0.8139 | 0.8139 |

Consequence: the workbook is **corroborated**, not merely trusted, for both
sequences. And the earlier objection that Sequence H had no raw backup is gone —
H is now present with its full 163-point inventory.

## Which sequence should the ALM validation use?

The committed case is an upwind, rigid rotor, 0° cone, 3° tip pitch, rotating at
the measured TSR, with two blades. An ALM validation candidate must therefore be:

1. **Rotating** at 72 rpm — a parked rotor cannot validate power, torque or thrust.
2. **3° tip pitch**, to match `turbine.pitch_deg: 3.0` without re-tuning the case.
3. **Blade pressure data**, because the spanwise `c_n` criterion needs the five
   instrumented stations.
4. **A 0° yaw point per speed**, for the axisymmetric headline comparison.

| Seq | 1 | 2 | 3 | 4 | Verdict |
| --- | --- | --- | --- | --- | --- |
| **H** | ✅ | ✅ 3° | ✅ | ✅ 21 speeds | **Primary candidate.** The report's field-representative upwind baseline, the canonical Phase VI comparison set, and the broadest yaw grid (16 values) if a yaw study is ever wanted |
| **S** | ✅ | ✅ 3° | ✅ | ✅ 21 speeds | **Primary candidate.** Same rig and pitch as H, but the five-hole probes were **removed and the holes plugged and taped smooth** (report, PDF p. 31) — the cleaner blade for a force comparison. This is the sequence the issue currently targets |
| **T** | ✅ | ✗ 2° | ✅ | ✅ 21 | **Pitch sensitivity.** 21 speeds at 0° yaw; a cheap extra validation axis if the case is rendered at 2° |
| **U** | ✅ | ✗ 4° | ✅ | ✅ 21 | **Pitch sensitivity**, same as T at 4° |
| **J** | ✅ | ✗ 6° | ✅ | ✅ 21 | Deep pitch; URANS is weakest exactly there, and only 3 yaw values. Low value |
| **P** | ✅ | 3°/12° | ✗ *visualize* | ✅ | **Rejected**: no quantitative loads, so it cannot feed the spanwise or power criteria |
| **L** | ✗ parked | ramp | ✅ | — | **Rejected**: no rotation, so the ALM is the wrong instrument. This is a 3-D static-AOA dataset |
| **O** | ✗ parked | sinusoidal | ✅ | — | **Rejected** for the same reason; it is a dynamic-airfoil dataset (sinusoidal AOA emulating OSU 2-D dynamic data), the natural input for validating the dynamic-stall model in isolation |

**Recommendation: validate on S, and use H as the independent confirmation.**
They share the rig, the pitch and the 21-speed 0°-yaw grid, so the same rendered
case serves both — only the comparison reference changes. S is the
probe-free blade; H is the canonical field-representative set and is the only one
that also carries the probe-pressure channels. If exactly one is wanted, S is the
better force comparison and H the better-known reference.

**T and U are the cheap extras**: the same case rendered at 2° and 4° pitch turns
two already-downloaded sequences into a pitch-sensitivity check with no new
physics and no new data.

**L and O are a different validation, not this one.** They would validate the
airfoil/dynamic-stall chain with the rotor parked. Worth recording as a future
capability, out of scope for the ALM campaign.
