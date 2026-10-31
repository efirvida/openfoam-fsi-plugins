# SPDX-License-Identifier: GPL-3.0-or-later
"""summarizeBands.py acceptance criteria: R3 (uniform 10 %, default) and R2 (frozen).

R2 (P 10 %, T 15 %, c_n 15 % at r/R 0.30 and 10 % at 0.47-0.80, 0.95 report-only)
stays reproducible with ``--criteria r2``; R3 bands P, T and c_n at all five
stations at |error| <= 10 % (owner S11/S12, 2026-10-30).
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR.parent / "validation" / "phaseVI" / "scripts"))

import summarizeBands as sb  # noqa: E402

STATIONS = (0.30, 0.47, 0.63, 0.80, 0.95)


def write_cmp(root: Path, power: float, thrust: float, cn: dict) -> Path:
    """A comparison directory; `power`/`thrust`/`cn` values are signed fractions."""
    root.mkdir(parents=True)
    (root / "metrics.json").write_text(json.dumps({"models": {"alm": {"run_dir": "x"}}}))
    with (root / "turbine_comparison.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["model", "quantity", "sim", "experiment", "delta_frac"])
        writer.writerow(["alm", "power", 100 * (1 + power), 100, power])
        writer.writerow(["alm", "torque", 100, 100, 0.0])
        writer.writerow(["alm", "thrust", 100 * (1 + thrust), 100, thrust])
    with (root / "spanwise_comparison.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["model", "r_over_R", "c_ref_n", "cn_exp", "dcn_frac"])
        for station in STATIONS:
            writer.writerow(["alm", f"{station:.2f}", 1 + cn[station], 1.0, cn[station]])
    return root


def run(capsys, monkeypatch, directory: Path, *extra: str) -> list[str]:
    monkeypatch.setattr(sb, "definition_status", lambda d, definition: ("definition vT: CONFORMS", True))
    monkeypatch.setattr(sb, "load_definition", lambda: {"version": "vT"})
    assert sb.main([str(directory), *extra]) == 0
    return capsys.readouterr().out.splitlines()


def cn_tags(lines: list[str]) -> dict:
    tags = {}
    for line in lines:
        if line.strip().startswith("c_n r/R"):
            parts = line.split()
            tags[float(parts[2])] = parts[-1]
    return tags


def test_r3_is_the_default_and_bands_the_tip(tmp_path, capsys, monkeypatch):
    cn = {0.30: -0.09, 0.47: 0.0, 0.63: 0.0, 0.80: 0.0, 0.95: 0.262}
    lines = run(capsys, monkeypatch, write_cmp(tmp_path / "a", 0.05, -0.12, cn))
    assert cn_tags(lines) == {0.30: "PASS", 0.47: "PASS", 0.63: "PASS", 0.80: "PASS", 0.95: "FAIL"}
    assert any(line.startswith("  thrust") and line.endswith("band 10 %  FAIL") for line in lines)
    assert any(line.startswith("  power") and line.endswith("band 10 %  PASS") for line in lines)


def test_r3_tip_passes_at_plus_8_4_percent(tmp_path, capsys, monkeypatch):
    cn = {s: 0.0 for s in STATIONS} | {0.95: 0.084}
    lines = run(capsys, monkeypatch, write_cmp(tmp_path / "a", 0.0, 0.0, cn))
    assert cn_tags(lines)[0.95] == "PASS"


def test_r3_boundary_is_inclusive_at_exactly_10_percent(tmp_path, capsys, monkeypatch):
    cn = {s: 0.10 for s in STATIONS}
    lines = run(capsys, monkeypatch, write_cmp(tmp_path / "a", 0.10, 0.10, cn))
    assert set(cn_tags(lines).values()) == {"PASS"}
    assert all(line.endswith("PASS") for line in lines if line.startswith(("  power", "  thrust")))
    over = {s: 0.1001 for s in STATIONS}
    lines = run(capsys, monkeypatch, write_cmp(tmp_path / "b", 0.1001, 0.1001, over))
    assert set(cn_tags(lines).values()) == {"FAIL"}


def test_r3_tightens_the_old_thrust_and_station_030_bands(tmp_path, capsys, monkeypatch):
    cn = {0.30: -0.12, 0.47: 0.0, 0.63: 0.0, 0.80: 0.0, 0.95: 0.0}
    cmp_dir = write_cmp(tmp_path / "a", 0.0, 0.12, cn)
    r3 = run(capsys, monkeypatch, cmp_dir)
    r2 = run(capsys, monkeypatch, cmp_dir, "--criteria", "r2")
    assert cn_tags(r3)[0.30] == "FAIL" and cn_tags(r2)[0.30] == "PASS"
    assert next(l for l in r3 if l.startswith("  thrust")).endswith("band 10 %  FAIL")
    assert next(l for l in r2 if l.startswith("  thrust")).endswith("band 15 %  PASS")


def test_r2_is_unchanged_and_reports_the_tip(tmp_path, capsys, monkeypatch):
    cn = {0.30: -0.17, 0.47: -0.10, 0.63: -0.1001, 0.80: 0.0, 0.95: 0.262}
    lines = run(capsys, monkeypatch, write_cmp(tmp_path / "a", 0.11, -0.15, cn), "--criteria", "r2")
    assert cn_tags(lines) == {0.30: "FAIL", 0.47: "PASS", 0.63: "FAIL", 0.80: "PASS", 0.95: "report"}
    assert lines[:2] == ["== a", "  definition vT: CONFORMS"]
    assert lines[2] == "  power  sim    111.00 exp    100.00  +11.0 %  band 10 %  FAIL"
    assert lines[3] == "  thrust sim     85.00 exp    100.00  -15.0 %  band 15 %  PASS"
    assert not any("criteria" in line for line in lines)


def test_unknown_criteria_is_rejected(tmp_path):
    with pytest.raises(SystemExit):
        sb.main([str(tmp_path), "--criteria", "r9"])
