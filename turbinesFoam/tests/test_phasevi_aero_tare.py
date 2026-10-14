"""Tests for extractAeroTare.py (UAE aerodynamic tares, NREL/TP-500-29955 Appendix I)."""

from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
PACKAGE = TESTS_DIR.parent / "validation" / "phaseVI"
PDF = TESTS_DIR.parent / "articles" / "29955.pdf"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


tare = _load_module(PACKAGE / "scripts" / "extractAeroTare.py", "extractAeroTare")

HEADER = """286
Table I-4. Aerodynamic Tare Run 056 with Tower and Nacelle (Blades Removed)
DATE/TIME TEST NAME TURBINE_YAW RHO_DIG Q_DIG VFPS_DIG LIFT,W_S DRAG,W_S SIDE,W_S PTCH,W_S ROLL,W_S YAW,W_S
445 440 450 611 612 613 614 615 616
deg slug/ft^3 psf ft/s lb lb lb lb lb lb
"""
HEADER_058 = HEADER.replace("Table I-4. Aerodynamic Tare Run 056 with Tower and Nacelle (Blades Removed)",
                            "Table I-5. Aerodynamic Tare Run 058 with Tower Only").replace("286", "290")


def _row(stamp: str, name: str, yaw: float, q_psf: float, v_fps: float, drag_lb: float) -> str:
    values = [yaw, 2.36e-3, q_psf, v_fps, 7.0, drag_lb, 1.0, -400.0, -70.0, -70.0]
    body = " ".join(f"{value:.2E}" for value in values)
    return f"{stamp} {name} {body}".replace("  ", " ")


def test_parses_named_and_wind_off_rows_with_their_run():
    page = HEADER + "152:08:33:08 0.00E+00 2.37E-03 0.00E+00 0.00E+00 2.16E+00 -1.96E+00 6.06E-01 7.29E+01 -8.37E+00 -2.34E+01\n" \
        + "152:08:48:10 AT0500000 0.00E+00 2.36E-03 3.15E-01 1.64E+01 7.24E+00 2.03E+01 2.13E+00 -4.10E+02 -7.87E+01 -7.72E+01\n" \
        + "152:08:52:32 AT05M0050 -5.00E+00 2.36E-03 3.15E-01 1.64E+01 9.38E+00 2.17E+01 -6.19E-01 -3.84E+02 3.74E+02 -3.26E+01\n"
    rows = tare.parse_pages([page])
    assert [row["run"] for row in rows] == ["056", "056", "056"]
    assert [row["name"] for row in rows] == ["", "AT0500000", "AT05M0050"]
    assert rows[1]["yaw_deg"] == 0.0 and rows[2]["yaw_deg"] == -5.0
    assert rows[1]["q_psf"] == pytest.approx(0.315)
    assert rows[1]["drag_lb"] == pytest.approx(20.3)
    assert rows[1]["yaw_lbft"] == pytest.approx(-77.2)


def test_page_without_a_tare_table_title_is_ignored():
    assert tare.parse_pages(["Appendix J: Wake Flow Visualization\n152:08:48:10 AT0500000 " + "1.00E+00 " * 10]) == []


def test_si_conversion():
    row = tare.parse_pages([HEADER + _row("152:08:48:10", "AT0500000", 0.0, 1.0, 10.0, 1.0) + "\n"])[0]
    si = tare.to_si(row)
    assert si["q_pa"] == pytest.approx(47.880258888889)
    assert si["drag_n"] == pytest.approx(4.4482216152605, rel=1e-3)
    assert si["speed_m_s"] == pytest.approx(3.048, rel=1e-3)


def _synthetic(cda_tower: float, cda_nacelle: float, offset_056: float, offset_058: float) -> list[dict]:
    """Yaw-0 points at 5, 10, 15 m/s with drag = CdA*q + offset, plus yawed and low-q noise."""
    lines_056, lines_058 = [HEADER], [HEADER_058]
    for speed in (5.0, 10.0, 15.0):
        q_pa = 0.5 * 1.2 * speed**2
        q_psf = q_pa / tare.PSF_TO_PA
        v_fps = speed / tare.FT_TO_M
        for cda, offset, lines in ((cda_tower + cda_nacelle, offset_056, lines_056),
                                   (cda_tower, offset_058, lines_058)):
            drag_lb = (cda * q_pa + offset) / tare.LB_TO_N
            lines.append(_row("152:08:48:10", f"AT{int(speed):02d}00000", 0.0, q_psf, v_fps, drag_lb))
            lines.append(_row("152:08:49:10", f"AT{int(speed):02d}00900", 90.0, q_psf, v_fps, 5 * drag_lb))
    lines_058.append(_row("158:16:15:42", "ATT000000", 0.0, 0.038, 5.71, 999.0))
    return tare.parse_pages(["\n".join(lines_056) + "\n", "\n".join(lines_058) + "\n"])


def test_drag_area_by_speed_recovers_the_nacelle_without_offsets():
    table = tare.drag_area_by_speed(_synthetic(2.0, 0.4, 0.0, 0.0))
    assert [round(entry["speed_m_s"]) for entry in table] == [5, 10, 15]
    for entry in table:
        assert entry["cda_056_m2"] == pytest.approx(2.4, rel=1e-2)  # rows carry 3 significant digits
        assert entry["cda_058_m2"] == pytest.approx(2.0, rel=1e-2)
        assert entry["cda_nacelle_m2"] == pytest.approx(0.4, rel=1e-2)


def test_fit_slope_removes_a_constant_balance_offset():
    rows = _synthetic(2.0, 0.4, 9.0, -60.0)
    fit_056 = tare.drag_area_fit(rows, "056")
    fit_058 = tare.drag_area_fit(rows, "058")
    assert fit_056["cda_m2"] == pytest.approx(2.4, rel=1e-2)
    assert fit_058["cda_m2"] == pytest.approx(2.0, rel=1e-2)
    assert fit_058["offset_n"] == pytest.approx(-60.0, rel=1e-2)
    assert fit_056["points"] == 3


def test_main_writes_rows_and_summary_from_csv(tmp_path):
    rows = _synthetic(2.0, 0.4, 0.0, 0.0)
    source = tmp_path / "rows.csv"
    tare.write_rows(rows, source)
    out = tmp_path / "summary.csv"
    assert tare.main(["--from-csv", str(source), "--out", str(out)]) == 0
    with out.open() as handle:
        summary = list(csv.DictReader(handle))
    assert [round(float(row["speed_m_s"])) for row in summary[:3]] == [5, 10, 15]
    assert [row["basis"] for row in summary] == ["per-speed"] * 3 + ["fit"]
    assert float(summary[-1]["cda_nacelle_m2"]) == pytest.approx(0.4, rel=1e-2)
    assert summary[-1]["basis"] == "fit"


def test_main_exits_1_when_a_run_is_missing(tmp_path):
    rows = [row for row in _synthetic(2.0, 0.4, 0.0, 0.0) if row["run"] == "056"]
    source = tmp_path / "rows.csv"
    tare.write_rows(rows, source)
    assert tare.main(["--from-csv", str(source), "--out", str(tmp_path / "s.csv")]) == 1


@pytest.mark.skipif(not PDF.exists(), reason="report PDF not on disk")
def test_report_tables_parse_completely():
    rows = tare.parse_pages(tare.read_pages(PDF, tare.DEFAULT_PAGES))
    runs = {run: [row for row in rows if row["run"] == run] for run in ("056", "058")}
    assert runs["056"] and runs["058"]
    yaw0_056 = {round(tare.to_si(row)["speed_m_s"]) for row in runs["056"]
                if row["yaw_deg"] == 0.0 and tare.to_si(row)["q_pa"] > tare.Q_MIN_PA}
    assert {5, 7, 10, 15, 20, 25} <= yaw0_056
