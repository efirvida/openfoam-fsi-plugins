#!/usr/bin/env python3
"""Extract the yaw and blade-pitch reference tables from the raw UAE6 archive.

Companion of `extractUAE6Reference.py`, which it reuses for stem parsing, the
`err == 128` frame mask, the per-point decoding and the table formatting. Two
families of tables are written to `data/experiment/yaw-pitch/`:

  yaw_{H,S}_{performance,spanwise}.csv
      EVERY fixed-yaw test point of Sequence H (high-speed-stall free, 3 deg tip
      pitch) and Sequence S (also 3 deg), all repetitions, so the yaw sweeps
      (`h` / `s` files at -180..180 deg) can drive a yawed-inflow validation.
  pitch_{performance,spanwise}.csv
      The 0 deg yaw points of Sequences I, T, H, S, U, J, one canonical row per
      (sequence, speed) - the lowest repetition, the same rule as
      `extractUAE6Reference.py` - which differ by the nominal tip pitch.

The first columns are exactly the committed `sequence_H_*.csv` schema
(`PERFORMANCE_COLUMNS` + `eaerotq_n`, `SPANWISE_COLUMNS` + `cth, ctq, qnorm_pa`);
extra columns are appended. Performance adds the nominal yaw and pitch, the
measured `B1PITCH` / `B3PITCH` and the root flap bending `B1RFB`, `B3RFB`
(strain gauge) and `EAERORFB` (estimated aerodynamic). Spanwise adds the nominal
yaw, nominal pitch and repetition; `file_name` stays the join key.

Sign conventions (Hand et al. 2001, NREL/TP-500-29955):

  Pitch   PDF p.20: "blade pitch is defined as the angle between the blade tip
          chord line and the plane of the turbine disk", limits -15..95 deg with
          "90 deg is feathered into the wind", so positive pitch is toward
          feather. Fig. 19 (PDF p.48): channels #253 / #257 = B1PITCH / B3PITCH,
          "0 deg at tip".
  Yaw     Fig. B-25 caption (PDF p.142): "In positive yaw, the blade advances
          into the wind at 180 deg azimuth".

The nominal tip pitch of each sequence is I 0, T 2, H 3, S 3, U 4, J 6 deg
(CATALOG.md and the report, p.27). The measured pitch channels are printed next
to it, which is the empirical sign check.

Usage:

    python3 scripts/extractYawPitchReference.py                # write all
    python3 scripts/extractYawPitchReference.py --only yaw
    python3 scripts/extractYawPitchReference.py --check        # verify, never write
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extractUAE6Reference as extract  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "experiment" / "yaw-pitch"

# Nominal tip pitch per sequence letter, degrees (report p.27, CATALOG.md).
PITCH_NOMINAL_DEG = {"I": 0.0, "T": 2.0, "H": 3.0, "S": 3.0, "U": 4.0, "J": 6.0}
YAW_SEQUENCES = ("H", "S")
PITCH_SEQUENCES = ("I", "T", "H", "S", "U", "J")

EXTRA_CHANNELS = ("B1PITCH", "B3PITCH", "B1RFB", "B3RFB", "EAERORFB")
# channels.csv units: B1RFB / B3RFB "N-m", EAERORFB "Nm" - all newton-metres.
EXTRA_COLUMNS = {
    "B1PITCH": "b1pitch_deg", "B3PITCH": "b3pitch_deg",
    "B1RFB": "b1rfb_nm", "B3RFB": "b3rfb_nm", "EAERORFB": "eaerorfb_nm",
}
PERFORMANCE_COLUMNS = (
    extract.PERFORMANCE_COLUMNS + extract.ENRICHED_COLUMNS["performance"]
    + ("yaw_nominal_deg", "pitch_nominal_deg") + tuple(EXTRA_COLUMNS.values())
)
SPANWISE_COLUMNS = (
    extract.SPANWISE_COLUMNS + extract.ENRICHED_COLUMNS["spanwise"]
    + ("yaw_nominal_deg", "pitch_nominal_deg", "repetition")
)


def extra_means(stem: extract.Stem) -> dict[str, float]:
    """Means of the pitch and root-flap channels over `err == 128` frames."""
    columns = ["err", *EXTRA_CHANNELS]
    table = pq.read_table(
        str(extract.ARCHIVE_DIR / "parquet" / f"{stem.stem}.parquet"),
        columns=columns,
    )
    frames = {
        name: table.column(name).to_numpy(zero_copy_only=False) for name in columns
    }
    keep = frames["err"] == extract.ERR_BYTE_OK
    if not keep.any():
        raise ValueError(f"{stem.stem}: every frame is flagged, nothing to average")
    return {
        EXTRA_COLUMNS[name]: float(np.mean(frames[name][keep].astype("float64")))
        for name in EXTRA_CHANNELS
    }


def point_rows(stem: extract.Stem) -> tuple[dict, list[dict]]:
    """One performance row and its spanwise rows, fully enriched."""
    row, spanwise, _ = extract.read_point(stem, with_hashes=False)
    means = extract._point_enrichment_means(stem.name)
    if means is None:
        raise ValueError(f"{stem.stem}: enrichment channels unavailable")
    yaw_nominal = float(stem.yaw_deg)
    pitch_nominal = PITCH_NOMINAL_DEG[stem.sequence.upper()]
    row = dict(row)
    row["eaerotq_n"] = means["EAEROTQ"]
    row["yaw_nominal_deg"] = yaw_nominal
    row["pitch_nominal_deg"] = pitch_nominal
    row.update(extra_means(stem))
    rows = []
    for entry in spanwise:
        entry = dict(entry)
        prefix = extract._station_prefix(float(entry["r_over_R"]))
        entry["cth"] = means[f"CTH{prefix}"]
        entry["ctq"] = means[f"CTQ{prefix}"]
        entry["qnorm_pa"] = means[f"QNORM{prefix}"]
        entry["yaw_nominal_deg"] = yaw_nominal
        entry["pitch_nominal_deg"] = pitch_nominal
        entry["repetition"] = stem.repetition
        rows.append(entry)
    return row, rows


def discover(sequence: str, skipped: list[str]) -> list[extract.Stem]:
    """Fixed-yaw stems of one sequence that have a parquet file; log the rest."""
    found = []
    for path in sorted(extract.ARCHIVE_DIR.glob(f"uae6.*.*.{sequence.lower()}*.hd1")):
        parsed = extract.parse_stem(path.stem)
        if parsed is None:
            skipped.append(f"{path.stem}: not a fixed-yaw test point")
        elif not (extract.ARCHIVE_DIR / "parquet" / f"{path.stem}.parquet").is_file():
            skipped.append(f"{path.stem}: no parquet file")
        else:
            found.append(parsed)
    return found


def _read_all(stems: list[extract.Stem], skipped: list[str]):
    points = []
    for stem in stems:
        try:
            points.append((stem, *point_rows(stem)))
        except (ValueError, KeyError) as exc:
            skipped.append(f"{stem.stem}: read failed, {exc}")
    return points


def build_yaw(sequences=YAW_SEQUENCES, skipped: list[str] | None = None):
    """Every fixed-yaw stem, all repetitions, sorted (speed, yaw, repetition)."""
    skipped = [] if skipped is None else skipped
    tables = {}
    for sequence in sequences:
        points = _read_all(discover(sequence, skipped), skipped)
        points.sort(key=lambda p: (p[0].speed, p[0].yaw_deg, p[0].repetition))
        tables[sequence] = (
            [p[1] for p in points], [e for p in points for e in p[2]]
        )
    return tables


def select_pitch(stems: list[extract.Stem]) -> list[extract.Stem]:
    """0 deg yaw only, lowest repetition per (sequence, speed)."""
    best: dict[tuple[str, int], extract.Stem] = {}
    for stem in stems:
        if stem.yaw_deg != 0:
            continue
        key = (stem.sequence.upper(), stem.speed)
        if key not in best or stem.repetition < best[key].repetition:
            best[key] = stem
    return list(best.values())


def build_pitch(sequences=PITCH_SEQUENCES, skipped: list[str] | None = None):
    """Canonical 0 deg rows, sorted (pitch_nominal, sequence, speed)."""
    skipped = [] if skipped is None else skipped
    stems = []
    for sequence in sequences:
        stems += select_pitch(discover(sequence, skipped))
    points = _read_all(stems, skipped)
    points.sort(key=lambda p: (
        PITCH_NOMINAL_DEG[p[0].sequence.upper()], p[0].sequence, p[0].speed
    ))
    return [p[1] for p in points], [e for p in points for e in p[2]]


def pitch_summary(rows: list[dict]) -> list[str]:
    lines = ["sequence nominal_deg median_B1PITCH median_B3PITCH n_speeds"]
    for sequence in PITCH_SEQUENCES:
        sub = [r for r in rows if r["sequence"] == sequence]
        if not sub:
            continue
        b1 = float(np.median([r["b1pitch_deg"] for r in sub]))
        b3 = float(np.median([r["b3pitch_deg"] for r in sub]))
        lines.append(
            f"{sequence} {PITCH_NOMINAL_DEG[sequence]:g} {b1:.3f} {b3:.3f} {len(sub)}"
        )
    return lines


def build(only: str, skipped: list[str]):
    """Return ({path: text}, pitch performance rows)."""
    rendered: dict[Path, str] = {}
    pitch_rows: list[dict] = []
    if only in ("yaw", "all"):
        for sequence, (perf, span) in build_yaw(skipped=skipped).items():
            rendered[OUT_DIR / f"yaw_{sequence}_performance.csv"] = (
                extract.write_table(PERFORMANCE_COLUMNS, perf))
            rendered[OUT_DIR / f"yaw_{sequence}_spanwise.csv"] = (
                extract.write_table(SPANWISE_COLUMNS, span))
    if only in ("pitch", "all"):
        pitch_rows, span = build_pitch(skipped=skipped)
        rendered[OUT_DIR / "pitch_performance.csv"] = (
            extract.write_table(PERFORMANCE_COLUMNS, pitch_rows))
        rendered[OUT_DIR / "pitch_spanwise.csv"] = (
            extract.write_table(SPANWISE_COLUMNS, span))
    return rendered, pitch_rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=("yaw", "pitch", "all"), default="all")
    parser.add_argument(
        "--check", action="store_true",
        help="compare the committed tables against a fresh extraction and exit "
             "non-zero on any drift; never writes",
    )
    args = parser.parse_args(argv)
    if not extract.ARCHIVE_DIR.is_dir():
        print(f"archive not found: {extract.ARCHIVE_DIR}", file=sys.stderr)
        return 2
    skipped: list[str] = []
    try:
        rendered, pitch_rows = build(args.only, skipped)
    except (FileNotFoundError, ValueError) as exc:
        print(f"extraction error: {exc}", file=sys.stderr)
        return 2
    skipped = sorted(set(skipped))
    print(f"skipped stems: {len(skipped)}")
    for note in skipped[:40]:
        print(f"  {note}", file=sys.stderr)
    if len(skipped) > 40:
        print(f"  ... {len(skipped) - 40} more", file=sys.stderr)
    for line in pitch_summary(pitch_rows):
        print(line)
    if args.check:
        clean = True
        for path, expected in rendered.items():
            if not path.exists():
                print(f"missing: {path.name}", file=sys.stderr)
                clean = False
            elif path.read_text(encoding="utf-8") != expected:
                print(f"stale: {path.name}", file=sys.stderr)
                clean = False
        return 0 if clean else 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for path, text in rendered.items():
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)} ({text.count(chr(10)) - 1} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
