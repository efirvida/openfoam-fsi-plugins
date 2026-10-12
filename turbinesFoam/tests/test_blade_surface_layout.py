# SPDX-License-Identifier: GPL-3.0-or-later
"""Pin the spanwise layout of the committed Phase VI blade surface.

`validation/phaseVI/scripts/inspectBladeSurface.py` and `spanwiseDepositRipple.py`
quote two facts that motivate an equispaced loft (odd/tasks/p1-5-equispaced-blade.md):
the committed sections follow the NREL station table (segments 0.013 to 0.305 m), and
a deposit of that layout develops a spanwise comb once the cell size drops below the
node spacing. These tests keep the quoted numbers reproducible; they do not need
OpenFOAM.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1]
SCRIPTS = PACKAGE / "validation" / "phaseVI" / "scripts"
STL = PACKAGE / "geometry" / "stl" / "phaseVI_blade.stl"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def inspect_surface():
    return _load("inspectBladeSurface")


@pytest.fixture(scope="module")
def ripple_tool(inspect_surface):
    return _load("spanwiseDepositRipple")


@pytest.fixture(scope="module")
def tris(inspect_surface):
    return inspect_surface.read_binary_stl(STL)


def test_committed_layout_follows_the_station_table(inspect_surface, tris):
    rows = inspect_surface.segment_report(tris)
    dz = [r["dz"] for r in rows]
    assert len(tris) == 3000
    assert len(rows) == 25
    assert min(dz) == pytest.approx(0.013, abs=1e-4)
    assert max(dz) == pytest.approx(0.305, abs=1e-4)
    assert max(r["aspect_max"] for r in rows) > 200.0


def test_missing_file_exits_one(inspect_surface, tmp_path):
    assert inspect_surface.main([str(tmp_path / "absent.stl")]) == 1


def test_committed_layout_deposit_degrades_below_the_node_spacing(ripple_tool, tris):
    coarse = ripple_tool.ripple(tris, 0.31)["max"]
    fine = ripple_tool.ripple(tris, 0.039)["max"]
    assert coarse < 0.03
    assert fine > 1.0


def test_equispaced_nodes_keep_the_deposit_smooth(ripple_tool, tris):
    # spacing 0.05 m against h = 0.078 m (node spacing below the kernel width)
    assert ripple_tool.ripple(tris, 0.078, uniform_dz=0.05)["max"] < 0.06
    assert ripple_tool.ripple(tris, 0.078)["max"] > 0.4


def test_kernel_is_a_partition_of_unity(ripple_tool):
    import numpy as np

    x = np.linspace(0.0, 1.0, 11)
    total = sum(ripple_tool.kernel(x - k) for k in range(-4, 5))
    assert total == pytest.approx(np.ones_like(x), abs=1e-12)
