#!/usr/bin/env python3
"""Extract the committed UAE6 reference tables from the raw archive.

The raw NREL Phase VI archive lives in `turbinesFoam/articles/uae6/` as
`<stem>.hd1` + `<stem>.eng` pairs plus a Parquet conversion. `/articles/` is
gitignored, so this script is what makes the experimental reference reviewable:
it decodes the archive and writes small derived tables next to it, in exactly the
schema `data/experiment/` already uses, so `scripts/comparePhaseVI.py` consumes
them unchanged through its existing `--experiment` flag.

The tables are **recomputed from the raw frames**, not copied from the header
statistics, so they can differ from the acquisition's own mean in the last few
digits: those are single-precision one-pass sums.

File-name grammar, established by decoding the archive rather than assumed
(every field verified against each file's measured `YAW` channel):

    <letter><WW>[m]<YYY(Y)><R>

  <letter>   sequence, lowercase (`h`, `j`, `s`, ...)
  <WW>       nominal wind speed in m/s
  [m]        optional NEGATIVE-yaw marker; with it the yaw field is 3 digits and
             the angle is negative (`h05m0050` measures -5.141 deg, so it is
             -5 deg, not +5)
  <YYY(Y)>   yaw angle in degrees: 4 digits without the marker, 3 with it
  <R>        repetition digit

Stems that do not match are not test points of a fixed yaw (the 1 deg/s 360 deg
yaw sweeps, the `p10000a0` pitch-marker variant, the Sequence L/O conventions).
They are skipped and reported, never silently dropped.

Usage:

    python3 scripts/extractUAE6Reference.py                  # Sequence S
    python3 scripts/extractUAE6Reference.py --sequences s h  # S and H
    python3 scripts/extractUAE6Reference.py --check          # verify, never write
    python3 scripts/extractUAE6Reference.py --sequences s h --archive-only
    python3 scripts/extractUAE6Reference.py --sequences s h --archive-only --check
    python3 scripts/extractUAE6Reference.py --cross-check    # S7/H7 enriched agreement

--archive-only leaves the separate workbook tables unchanged. The combined
committed inventory is reproduced with --sequences s h; the sequence default
remains s. H probe local/spanwise angles are emitted separately at their own
stations, without treating them as rotor-plane inflow angles.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_DIR = ROOT.parents[1] / "articles" / "uae6"
OUT_DIR = ROOT / "data" / "experiment" / "uae6-archive"

# Rotor radius of the committed case (NREL/TP-500-29955 Table A-1 tip station).
ROTOR_RADIUS_M = 5.029
# The per-frame error byte is 128 on unflagged frames; nothing else is trusted.
ERR_BYTE_OK = 128
# Ideal-gas density from the test point's own barometric pressure and air
# temperature. Same rule as `data/experiment/PROVENANCE.md` (design D10); the
# archive's own `RHOTUN` column is not used, so both references agree.
R_DRY_AIR = 287.058
KELVIN = 273.15
# The five instrumented stations and their span fraction.
STATIONS = (("30", 0.30), ("47", 0.47), ("63", 0.63), ("80", 0.80), ("95", 0.95))
# The committed workbook tables (`data/experiment/sequence_*_{spanwise,
# performance}.csv`) are a separate artefact from the archive outputs above:
# `extractExperimentalData.py` writes them from the workbook sheet `ldsmean`,
# which carries CN/CT/CM but no plane-of-rotation CTH/CTQ, no normalization
# pressure QNORM and no aerodynamic torque EAEROTQ. Those live only in the
# parquet archive, so the committed tables are enriched in place with them. The
# row set, row order, header order and every pre-existing value are preserved;
# the new columns are appended at the end.
COMMITTED_DIR = ROOT / "data" / "experiment"
COMMITTED_SEQUENCES = ("H", "S")
ENRICHED_COLUMNS = {
    "spanwise": ("cth", "ctq", "qnorm_pa"),
    "performance": ("eaerotq_n",),
}
ENRICHED_CHANNELS = ("err", "EAEROTQ") + tuple(
    f"{kind}{prefix}" for prefix, _ in STATIONS for kind in ("CTH", "CTQ", "QNORM")
)
# Workbook convention: a 0 deg test point is one whose measured yaw is within
# half a degree of zero. The file name is only allowed to disagree by this much.
YAW_ABS_TOLERANCE_DEG = 0.5
YAW_PARSE_TOLERANCE_DEG = 1.0

POINT_COLUMNS = (
    "err", "VTUN", "YAW", "RPM", "ROTPOW", "LSSTQCOR", "EAEROTH",
    "WTBARO", "WTATEMP",
) + tuple(
    f"{kind}{prefix}" for prefix, _ in STATIONS for kind in ("CN", "CT", "CM", "CTH", "CTQ", "QNORM")
)

PERFORMANCE_COLUMNS = (
    "file_name", "sequence", "wind_speed_m_s", "yaw_token", "yaw_deg",
    "repetition", "rpm", "tsr", "rotpow_kw", "lsstqcor_nm", "eaeroth_n",
    "wtbaro_pa", "wtatemp_degc", "rho_kg_m3",
)
SPANWISE_COLUMNS = (
    "file_name", "sequence", "wind_speed_m_s", "r_over_R", "cn", "ct", "cm",
    "cth", "ctq", "qnorm_pa",
)
# channels.csv: 5HPxxA = local flow angle, 5HPxxF = spanwise flow angle.
# These are probe stations, NOT the five blade-pressure stations. Do not
# relabel either as rotor-plane phi without an independently defined transform.
PROBE_STATIONS = (("34", 0.34), ("51", 0.51), ("67", 0.67), ("84", 0.84), ("91", 0.91))
PROBE_CHANNELS = tuple(f"5HP{prefix}{kind}" for prefix, _ in PROBE_STATIONS
                       for kind in ("A", "F"))
PROBE_COLUMNS = ("file_name", "sequence", "wind_speed_m_s", "r_over_R",
                 "local_flow_angle_deg", "spanwise_flow_angle_deg")
INVENTORY_COLUMNS = (
    "stem", "sequence", "wind_speed_m_s", "yaw_deg", "repetition", "n_frames",
    "err_flagged_frames", "eng_bytes", "eng_sha256", "hd1_sha256", "role",
)

STEM_RE = re.compile(
    r"^uae6\.(?P<config>z\d{2})\.\d{2}\."
    r"(?P<sequence>[a-z])(?P<speed>\d{2})"
    r"(?P<negative>m?)(?P<yaw>\d{3,4})(?P<repetition>\d)$"
)


@dataclass(frozen=True)
class Stem:
    """One decoded archive file name."""

    stem: str
    name: str
    sequence: str
    speed: int
    yaw_deg: int
    repetition: int
    yaw_token: str


def parse_stem(stem: str) -> Stem | None:
    """Decode one archive stem, or None when it is not a fixed-yaw test point.

    The yaw field is exactly 4 digits without the `m` marker and exactly 3 with
    it, which makes the split unambiguous instead of backtracking-dependent:
    `s0501350` is 135 deg, never 13 deg with repetition 5.
    """
    match = STEM_RE.match(stem)
    if match is None:
        return None
    negative = match.group("negative") == "m"
    yaw_digits = match.group("yaw")
    if len(yaw_digits) != (3 if negative else 4):
        return None
    repetition = int(match.group("repetition"))
    magnitude = int(yaw_digits)
    # `yaw_token` mirrors the workbook column of the same name: the yaw field as
    # it appears in the file name, without the repetition digit. For the `m`
    # variant that is `m000` for `h20m0000`, which is the token
    # `data/experiment/PROVENANCE.md` records for that row.
    return Stem(
        stem=stem,
        # The workbook tables identify a test point by the NREL file name alone
        # (`s0700000`), which is what the report's inventory tables list. The
        # archive-only prefix lives in the inventory's `stem` column.
        name=stem.split(".")[-1],
        sequence=match.group("sequence"),
        speed=int(match.group("speed")),
        yaw_deg=-magnitude if negative else magnitude,
        repetition=repetition,
        yaw_token=f"m{magnitude:03d}" if negative else f"{magnitude:04d}",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_point(stem: Stem, with_hashes: bool) -> tuple[dict, list[dict], dict]:
    """Decode one test point into a performance row, spanwise rows and a digest.

    `err != 128` frames are masked out before any average: the acquisition system
    flags them as unusable, and 5.5 % of the archive's frames carry a flag.
    """
    channels = POINT_COLUMNS + (PROBE_CHANNELS if stem.sequence == "h" else ())
    table = pq.read_table(
        str(ARCHIVE_DIR / "parquet" / f"{stem.stem}.parquet"),
        columns=list(channels),
    )
    frames = {
        name: table.column(name).to_numpy(zero_copy_only=False)
        for name in channels
    }
    keep = frames["err"] == ERR_BYTE_OK
    flagged = int((~keep).sum())
    if not keep.any():
        raise ValueError(f"{stem.stem}: every frame is flagged, nothing to average")

    def mean(name: str) -> float:
        return float(np.mean(frames[name][keep].astype("float64")))

    yaw = frames["YAW"][keep].astype("float64")
    # Report the arithmetic mean (it is what the workbook tables carry) but check
    # the parse against the circular mean: the 180 deg lock reads as a constant
    # +180 on some files and as a wrapped +/-180 on others, and only the circular
    # mean is meaningful for the second kind.
    yaw_mean = float(np.mean(yaw))
    theta = np.radians(yaw)
    circular_yaw = float(np.degrees(np.arctan2(
        float(np.mean(np.sin(theta))), float(np.mean(np.cos(theta)))
    )))
    yaw_error = abs((circular_yaw - stem.yaw_deg + 180.0) % 360.0 - 180.0)
    if yaw_error > YAW_PARSE_TOLERANCE_DEG:
        raise ValueError(
            f"{stem.stem}: file name says {stem.yaw_deg} deg but the measured "
            f"YAW channel sits at {circular_yaw:.3f} deg; the grammar or the "
            "file is wrong"
        )

    baro = mean("WTBARO")
    air_temp = mean("WTATEMP")
    rpm = mean("RPM")
    speed = float(stem.speed)
    row = {
        "file_name": stem.name,
        "sequence": stem.sequence.upper(),
        "wind_speed_m_s": speed,
        "yaw_token": stem.yaw_token,
        "yaw_deg": yaw_mean,
        "repetition": stem.repetition,
        "rpm": rpm,
        "tsr": rpm * 2.0 * np.pi * ROTOR_RADIUS_M / (60.0 * speed),
        "rotpow_kw": mean("ROTPOW"),
        "lsstqcor_nm": mean("LSSTQCOR"),
        "eaeroth_n": mean("EAEROTH"),
        "wtbaro_pa": baro,
        "wtatemp_degc": air_temp,
        "rho_kg_m3": baro / (R_DRY_AIR * (air_temp + KELVIN)),
    }
    if stem.sequence == "h":
        row.update({name: mean(name) for name in PROBE_CHANNELS})
    spanwise = [
        {
            "file_name": stem.name,
            "sequence": row["sequence"],
            "wind_speed_m_s": speed,
            "r_over_R": fraction,
            "cn": mean(f"CN{prefix}"),
            "ct": mean(f"CT{prefix}"),
            "cm": mean(f"CM{prefix}"),
            "cth": mean(f"CTH{prefix}"),
            "ctq": mean(f"CTQ{prefix}"),
            "qnorm_pa": mean(f"QNORM{prefix}"),
        }
        for prefix, fraction in STATIONS
    ]
    eng = ARCHIVE_DIR / f"{stem.stem}.eng"
    digest = {
        "stem": stem.stem,
        "sequence": row["sequence"],
        "wind_speed_m_s": f"{speed:g}",
        "yaw_deg": stem.yaw_deg,
        "repetition": stem.repetition,
        "n_frames": table.num_rows,
        "err_flagged_frames": flagged,
        "eng_bytes": eng.stat().st_size,
        "eng_sha256": _sha256(eng) if with_hashes else "",
        "hd1_sha256": _sha256(ARCHIVE_DIR / f"{stem.stem}.hd1") if with_hashes else "",
        "role": "",
    }
    return row, spanwise, digest


def _format(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.10g}"
    return str(value)


def write_table(columns: tuple[str, ...], rows: list[dict]) -> str:
    lines = [",".join(columns)]
    lines += [",".join(_format(row[name]) for name in columns) for row in rows]
    return "\n".join(lines) + "\n"


def _inventory_sort_key(row: dict) -> tuple:
    return (
        str(row["sequence"]),
        float(str(row["wind_speed_m_s"])),
        int(str(row["repetition"])),
        str(row["stem"]),
    )


def _point_enrichment_means(file_name: str) -> dict[str, float] | None:
    """Per-channel means of one archive point, using the script's own rule.

    Same statistic as `read_point`: frames whose `err` byte is not 128 are
    masked out before the arithmetic mean (never `nanmean` over all frames).
    Returns None when the point is not in the archive, so the caller can warn
    and leave the row's new cells empty instead of dropping it.
    """
    matches = sorted((ARCHIVE_DIR / "parquet").glob(f"uae6.*.00.{file_name}.parquet"))
    if len(matches) != 1:
        return None
    table = pq.read_table(str(matches[0]), columns=list(ENRICHED_CHANNELS))
    frames = {
        name: table.column(name).to_numpy(zero_copy_only=False)
        for name in ENRICHED_CHANNELS
    }
    keep = frames["err"] == ERR_BYTE_OK
    if not keep.any():
        return None
    return {
        name: float(np.mean(frames[name][keep].astype("float64")))
        for name in ENRICHED_CHANNELS
    }


def read_committed_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def _station_prefix(fraction: float) -> str:
    for prefix, value in STATIONS:
        if abs(value - fraction) < 1e-9:
            return prefix
    raise KeyError(f"{fraction:g} is not one of the five instrumented stations")


def _spanwise_key(row: dict) -> tuple:
    return (
        round(float(row["wind_speed_m_s"]), 6),
        round(float(row["r_over_R"]), 6),
    )


def _spanwise_lookup(rows: list[dict]) -> dict:
    lookup = {}
    cache: dict[str, dict | None] = {}
    for row in rows:
        name = row["file_name"]
        if name not in cache:
            cache[name] = _point_enrichment_means(name)
        means = cache[name]
        if means is None:
            continue
        prefix = _station_prefix(float(row["r_over_R"]))
        lookup[_spanwise_key(row)] = {
            "cth": means[f"CTH{prefix}"],
            "ctq": means[f"CTQ{prefix}"],
            "qnorm_pa": means[f"QNORM{prefix}"],
        }
    return lookup


def _performance_key(row: dict) -> tuple:
    return (row["sequence"].upper(), round(float(row["wind_speed_m_s"]), 6))


def _performance_lookup(rows: list[dict]) -> dict:
    lookup = {}
    cache: dict[str, dict | None] = {}
    for row in rows:
        name = row["file_name"]
        if name not in cache:
            cache[name] = _point_enrichment_means(name)
        means = cache[name]
        if means is None:
            continue
        lookup[_performance_key(row)] = {"eaerotq_n": means["EAEROTQ"]}
    return lookup


def enrich_committed_table(path: Path, columns: tuple[str, ...],
                           key_of, lookup) -> tuple[str, list[str]]:
    """Append `columns` to one committed table, preserving the existing bytes.

    Each original line is split and re-joined field by field, so pre-existing
    values keep their exact text; reformatting them through `_format` would
    change precision (e.g. the workbook `tsr` carries 16 digits). Columns that
    are already present are dropped first, which makes the step idempotent. A
    row whose key has no archive match keeps empty cells and is reported in the
    returned warnings.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    header = lines[0].split(",")
    for name in columns:
        if name in header:
            header.remove(name)
    kept = len(header)
    output = [",".join([*header, *columns])]
    warnings: list[str] = []
    for line in lines[1:]:
        original = line.split(",")[:kept]
        if len(original) < kept:
            original += [""] * (kept - len(original))
        row = {name: original[index] for index, name in enumerate(header)}
        matched = lookup.get(key_of(row))
        if matched is None:
            warnings.append(
                f"{path.name}: no archive point matches {key_of(row)}; "
                "the new columns are left empty"
            )
        cells = list(original)
        for name in columns:
            value = matched.get(name) if matched is not None else None
            cells.append("" if value is None else _format(value))
        output.append(",".join(cells))
    return "\n".join(output) + "\n", warnings


def build_committed_enrichment() -> tuple[dict[Path, str], list[str]]:
    """Render the four committed tables with the archive-only columns appended.

    Always both sequences: the committed workbook tables are a delivered
    artefact independent of `--sequences`, which selects only the archive
    outputs under `data/experiment/uae6-archive/`.
    """
    rendered: dict[Path, str] = {}
    warnings: list[str] = []
    for sequence in COMMITTED_SEQUENCES:
        performance = COMMITTED_DIR / f"sequence_{sequence}_performance.csv"
        spanwise = COMMITTED_DIR / f"sequence_{sequence}_spanwise.csv"
        if performance.is_file():
            text, notes = enrich_committed_table(
                performance, ENRICHED_COLUMNS["performance"],
                _performance_key,
                _performance_lookup(read_committed_rows(performance)),
            )
            rendered[performance] = text
            warnings += notes
        if spanwise.is_file():
            text, notes = enrich_committed_table(
                spanwise, ENRICHED_COLUMNS["spanwise"],
                _spanwise_key,
                _spanwise_lookup(read_committed_rows(spanwise)),
            )
            rendered[spanwise] = text
            warnings += notes
    return rendered, warnings


def build(sequences: list[str], with_hashes: bool,
          archive_only: bool = False) -> tuple[dict[Path, str], list[str]]:
    """Render the selected tables plus the inventory; return the skip notes too."""
    rendered: dict[Path, str] = {}
    inventory: list[dict] = []
    notes: list[str] = []
    for sequence in sequences:
        stems = sorted(
            path.stem for path in ARCHIVE_DIR.glob(f"uae6.*.*.{sequence}*.hd1")
        )
        if not stems:
            raise FileNotFoundError(
                f"no archive file matches sequence {sequence!r} in {ARCHIVE_DIR}"
            )
        # One canonical row per speed: the 0 deg point with the lowest
        # repetition, which is the rule `data/experiment/PROVENANCE.md` used for
        # the workbook tables. Everything else stays in the inventory.
        canonical: dict[int, tuple[Stem, dict, list[dict], dict]] = {}
        for name in stems:
            parsed = parse_stem(name)
            if parsed is None:
                notes.append(f"{name}: skipped, not a fixed-yaw test point")
                continue
            row, spanwise, digest = read_point(parsed, with_hashes)
            if abs(float(row["yaw_deg"])) > YAW_ABS_TOLERANCE_DEG:
                digest["role"] = "off-axis"
                inventory.append(digest)
                continue
            previous = canonical.get(parsed.speed)
            if previous is None or parsed.repetition < previous[0].repetition:
                if previous is not None:
                    previous[3]["role"] = "alternate-0deg"
                    inventory.append(previous[3])
                digest["role"] = "canonical-0deg"
                canonical[parsed.speed] = (parsed, row, spanwise, digest)
            else:
                digest["role"] = "alternate-0deg"
                inventory.append(digest)
        performance: list[dict] = []
        spanwise_rows: list[dict] = []
        for speed in sorted(canonical):
            _, row, spanwise, digest = canonical[speed]
            performance.append(row)
            spanwise_rows.extend(spanwise)
            inventory.append(digest)
        rendered[OUT_DIR / f"sequence_{sequence.upper()}_performance.csv"] = (
            write_table(PERFORMANCE_COLUMNS, performance)
        )
        rendered[OUT_DIR / f"sequence_{sequence.upper()}_spanwise.csv"] = (
            write_table(SPANWISE_COLUMNS, spanwise_rows)
        )
        if sequence == "h":
            probes = [
                {"file_name": row["file_name"], "sequence": "H",
                 "wind_speed_m_s": row["wind_speed_m_s"], "r_over_R": fraction,
                 "local_flow_angle_deg": row[f"5HP{prefix}A"],
                 "spanwise_flow_angle_deg": row[f"5HP{prefix}F"]}
                for row in performance for prefix, fraction in PROBE_STATIONS
            ]
            rendered[OUT_DIR / "sequence_H_probes.csv"] = write_table(PROBE_COLUMNS, probes)
    rendered[OUT_DIR / "INVENTORY.csv"] = write_table(
        INVENTORY_COLUMNS, sorted(inventory, key=_inventory_sort_key)
    )
    if not archive_only:
        enriched, enrichment_warnings = build_committed_enrichment()
        rendered.update(enriched)
        notes += enrichment_warnings
    return rendered, notes


def crosscheck() -> int:
    """Report relative differences against the enriched delivered 7 m/s rows."""
    clean = True
    for sequence in COMMITTED_SEQUENCES:
        name = f"sequence_{sequence}_spanwise.csv"
        actual = {_spanwise_key(row): row for row in read_committed_rows(OUT_DIR / name)}
        expected = [row for row in read_committed_rows(COMMITTED_DIR / name)
                    if float(row["wind_speed_m_s"]) == 7.0]
        for column in ENRICHED_COLUMNS["spanwise"]:
            differences = [abs(float(actual[_spanwise_key(row)][column]) - float(row[column]))
                           / abs(float(row[column])) for row in expected]
            maximum = max(differences)
            print(f"{sequence} 7 m/s {column}: max relative difference = {maximum:.10g}")
            clean &= maximum <= 1e-6
    return 0 if clean else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sequences", nargs="+", default=["s"], metavar="LETTER",
        help="sequence letters to extract (default: s)",
    )
    parser.add_argument(
        "--no-hash", action="store_true",
        help="skip the per-file sha256 (faster, leaves the column empty)",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="compare the committed tables against a fresh extraction and exit "
             "non-zero on any drift; never writes",
    )
    parser.add_argument(
        "--archive-only", action="store_true",
        help="only render archive tables; do not enrich the separate workbook tables",
    )
    parser.add_argument(
        "--cross-check", action="store_true",
        help="read-only: report S/H 7 m/s cth/ctq/qnorm maximum relative differences "
             "against the enriched workbook tables (exit 1 above 1e-6)",
    )
    args = parser.parse_args(argv)
    if args.cross_check:
        return crosscheck()
    sequences = [value.strip().lower() for value in args.sequences]
    if not ARCHIVE_DIR.is_dir():
        print(f"archive not found: {ARCHIVE_DIR}", file=sys.stderr)
        return 2
    try:
        rendered, notes = build(sequences, with_hashes=not args.no_hash,
                                archive_only=args.archive_only)
    except (FileNotFoundError, ValueError) as exc:
        print(f"extraction error: {exc}", file=sys.stderr)
        return 2
    for note in notes:
        print(note, file=sys.stderr)
    if args.check:
        clean = True
        for path, expected in rendered.items():
            if not path.exists():
                print(f"missing: {path.name}", file=sys.stderr)
                clean = False
                continue
            if path.read_text(encoding="utf-8") != expected:
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
