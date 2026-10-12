# SPDX-License-Identifier: GPL-3.0-or-later
"""P1.5 E1/E2: the equispaced blade reaches the element tables, the profiles and the STL."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1] / "validation" / "phaseVI"
sys.path.insert(0, str(PACKAGE / "tools"))

from case_config import DEFAULT_CONFIG, load_config  # noqa: E402
from element_data import blade_element_count, blade_element_profiles, blade_element_rows  # noqa: E402

COMMITTED_AREA = 4.88423


@pytest.fixture()
def cfg():
    return load_config(DEFAULT_CONFIG)


def test_committed_layout_is_unchanged(cfg):
    assert blade_element_count(cfg) is None
    assert len(blade_element_rows(cfg)) == 26
    profiles = blade_element_profiles(cfg)
    assert len(profiles) == 50
    assert profiles.count("cylinder") == 8


def test_equispaced_rows_profiles_and_count_agree(cfg):
    cfg["turbine"]["blade_dz"] = 0.05
    rows = blade_element_rows(cfg)
    n = blade_element_count(cfg)
    assert n == len(rows) - 1 == 84
    profiles = blade_element_profiles(cfg)
    assert len(profiles) == n
    # first elements are cylinders, the rest S809, and the cylinder block ends where the
    # committed layout's does (1.0675 m)
    k = profiles.count("cylinder")
    assert profiles[:k] == ["cylinder"] * k
    assert rows[k][1] <= 1.0675 + 1e-9 < rows[k + 1][1] + 0.2
    outboard = [r[1] for r in rows if r[1] >= 1.0085]
    steps = [b - a for a, b in zip(outboard, outboard[1:])]
    assert max(steps) <= 0.05 + 1e-12


def test_generate_case_renders_matching_n_elements_and_rejects_conflict(tmp_path):
    case = tmp_path / "case"
    ok = subprocess.run(
        [sys.executable, str(PACKAGE / "tools" / "generate_case.py"), "--blade-dz", "0.05", "--case-dir", str(case)],
        capture_output=True, text=True,
    )
    assert ok.returncode == 0, ok.stderr
    for name in ("ALM", "ASM", "ASM-MESH"):
        text = (case / "system" / f"fvOptions.{name}").read_text()
        assert re.search(r"nElements\s+84;", text)
    clash = subprocess.run(
        [sys.executable, str(PACKAGE / "tools" / "generate_case.py"), "--blade-dz", "0.05", "--n-elements", "40", "--case-dir", str(tmp_path / "c2")],
        capture_output=True, text=True,
    )
    assert clash.returncode != 0
    assert "--n-elements" in clash.stderr


def test_equispaced_stl_keeps_the_surface_area(tmp_path):
    out = subprocess.run(
        [sys.executable, "-I", str(PACKAGE / "tools" / "make_equispaced_blade.py"), "--dz", "0.05", "--out-dir", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert out.returncode == 0, out.stderr
    meta = json.loads((tmp_path / "phaseVI_blade.json").read_text())
    assert meta["n_triangles"] == 120 * 84
    assert out.stdout.strip() == meta["stl_sha256"]
    area = float(re.search(r"area ([0-9.]+)", out.stderr).group(1))
    assert abs(area - COMMITTED_AREA) / COMMITTED_AREA < 1e-3


def test_runner_rejects_bad_blade_dz():
    runner = str(PACKAGE / "scripts" / "runPhaseVI.sh")
    for extra in (["--blade-dz", "-1"], ["--blade-dz", "0.05", "--n-elements", "40"]):
        result = subprocess.run(["sh", runner, "-m", "alm", "-u", "7", "-mesh", "coarse", *extra], capture_output=True, text=True)
        assert result.returncode == 2, result.stderr
