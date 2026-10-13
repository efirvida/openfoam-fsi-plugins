"""Contracts for the yaw and blade-pitch UAE6 reference tables.

The committed tables under `data/experiment/yaw-pitch/` are pinned without the
gitignored archive; the tests that need it skip cleanly when it is absent.

See `data/experiment/yaw-pitch/PROVENANCE.md`.
"""

from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

TESTS_DIR = Path(__file__).resolve().parent
TURBINESFOAM = TESTS_DIR.parent
PACKAGE = TURBINESFOAM / "validation" / "phaseVI"
DATA_DIR = PACKAGE / "data" / "experiment"
REFERENCE_DIR = DATA_DIR / "yaw-pitch"
ARCHIVE_DIR = TURBINESFOAM / "articles" / "uae6"
SCRIPTS = PACKAGE / "scripts"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(SCRIPTS))
yp = _load_module(SCRIPTS / "extractYawPitchReference.py", "extractYawPitchReference")
extract = yp.extract


def _read(name: str) -> list[dict[str, str]]:
    with (REFERENCE_DIR / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _header(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()[0].split(",")


def _stem(sequence: str, speed: int, yaw: int, repetition: int):
    token = f"{sequence}{speed:02d}{yaw:04d}{repetition}" if yaw >= 0 else (
        f"{sequence}{speed:02d}m{-yaw:03d}{repetition}"
    )
    parsed = extract.parse_stem(f"uae6.z07.00.{token}")
    assert parsed is not None
    return parsed


def test_extra_means_masks_flagged_frames(tmp_path, monkeypatch):
    (tmp_path / "parquet").mkdir()
    stem = _stem("h", 7, 0, 0)
    table = pa.table({
        "err": pa.array([128, 128, 0, 128, 5], type=pa.uint8()),
        "B1PITCH": [3.0, 3.2, 99.0, 3.1, 99.0],
        "B3PITCH": [2.9, 3.1, 99.0, 3.0, 99.0],
        "B1RFB": [100.0, 200.0, 1e6, 300.0, 1e6],
        "B3RFB": [-100.0, -200.0, 1e6, -300.0, 1e6],
        "EAERORFB": [10.0, 20.0, 1e6, 30.0, 1e6],
    })
    pq.write_table(table, str(tmp_path / "parquet" / f"{stem.stem}.parquet"))
    monkeypatch.setattr(extract, "ARCHIVE_DIR", tmp_path)
    means = yp.extra_means(stem)
    assert means["b1pitch_deg"] == pytest.approx(3.1)
    assert means["b3pitch_deg"] == pytest.approx(3.0)
    assert means["b1rfb_nm"] == pytest.approx(200.0)
    assert means["b3rfb_nm"] == pytest.approx(-200.0)
    assert means["eaerorfb_nm"] == pytest.approx(20.0)


def test_select_pitch_keeps_zero_yaw_lowest_repetition():
    stems = [
        _stem("h", 7, 0, 2), _stem("h", 7, 0, 1), _stem("h", 7, 30, 0),
        _stem("h", 7, -30, 0), _stem("h", 10, 0, 0), _stem("s", 7, 0, 3),
    ]
    picked = {(s.sequence, s.speed): s.repetition for s in yp.select_pitch(stems)}
    assert picked == {("h", 7): 1, ("h", 10): 0, ("s", 7): 3}


def test_pitch_nominal_map():
    assert yp.PITCH_NOMINAL_DEG == {
        "I": 0.0, "T": 2.0, "H": 3.0, "S": 3.0, "U": 4.0, "J": 6.0,
    }


@pytest.mark.parametrize("sequence", ["H", "S"])
def test_schema_prefix_matches_committed_sequence_tables(sequence):
    perf = _header(DATA_DIR / f"sequence_{sequence}_performance.csv")
    span = _header(DATA_DIR / f"sequence_{sequence}_spanwise.csv")
    assert _header(REFERENCE_DIR / "pitch_performance.csv")[: len(perf)] == perf
    assert _header(REFERENCE_DIR / "pitch_spanwise.csv")[: len(span)] == span
    assert _header(REFERENCE_DIR / f"yaw_{sequence}_performance.csv")[: len(perf)] == perf
    assert _header(REFERENCE_DIR / f"yaw_{sequence}_spanwise.csv")[: len(span)] == span
    assert _header(REFERENCE_DIR / "pitch_performance.csv") == list(yp.PERFORMANCE_COLUMNS)
    assert _header(REFERENCE_DIR / "pitch_spanwise.csv") == list(yp.SPANWISE_COLUMNS)


def test_pitch_table_covers_six_sequences_with_nominal_pitch():
    rows = _read("pitch_performance.csv")
    assert {r["sequence"] for r in rows} == set(yp.PITCH_SEQUENCES)
    assert all(float(r["yaw_nominal_deg"]) == 0.0 for r in rows)
    assert len({(r["sequence"], r["wind_speed_m_s"]) for r in rows}) == len(rows)
    medians = {}
    for sequence in yp.PITCH_SEQUENCES:
        sub = [r for r in rows if r["sequence"] == sequence]
        nominal = yp.PITCH_NOMINAL_DEG[sequence]
        assert {float(r["pitch_nominal_deg"]) for r in sub} == {nominal}
        medians[sequence] = float(np.median([float(r["b3pitch_deg"]) for r in sub]))
        assert medians[sequence] == pytest.approx(nominal, abs=0.5)
    assert medians["I"] < medians["T"] < medians["H"] < medians["U"] < medians["J"]
    assert medians["H"] == pytest.approx(medians["S"], abs=0.1)


def test_yaw_h_coverage():
    rows = _read("yaw_H_performance.csv")
    low = [r for r in rows if float(r["wind_speed_m_s"]) <= 7]
    high = [r for r in rows if float(r["wind_speed_m_s"]) >= 20]
    assert max(float(r["yaw_nominal_deg"]) for r in low) == 180.0
    assert min(float(r["yaw_nominal_deg"]) for r in low) == -30.0
    assert high
    assert all(abs(float(r["yaw_nominal_deg"])) <= 10 for r in high)
    assert all(float(r["pitch_nominal_deg"]) == 3.0 for r in rows)
    # `m0000` stems are measured 0 deg points with the negative marker, so
    # (speed, yaw, repetition) repeats; the file name does not.
    names = [r["file_name"] for r in rows]
    assert len(set(names)) == len(names)
    assert {"h0500000", "h05m0000"} <= set(names)


def test_spanwise_joins_performance():
    perf = {r["file_name"] for r in _read("yaw_S_performance.csv")}
    span = _read("yaw_S_spanwise.csv")
    assert {r["file_name"] for r in span} == perf
    assert len(span) == 5 * len(perf)


@pytest.mark.skipif(not ARCHIVE_DIR.is_dir(), reason="raw UAE6 archive not present")
def test_single_stem_rederives_committed_row():
    rows = _read("pitch_performance.csv")
    committed = next(r for r in rows if r["sequence"] == "J" and r["wind_speed_m_s"] == "10")
    stem = next(
        s for s in yp.select_pitch(yp.discover("J", []))
        if s.speed == 10
    )
    row, span = yp.point_rows(stem)
    text = extract.write_table(yp.PERFORMANCE_COLUMNS, [row]).splitlines()[1]
    assert text.split(",") == [committed[c] for c in yp.PERFORMANCE_COLUMNS]
    assert len(span) == 5
