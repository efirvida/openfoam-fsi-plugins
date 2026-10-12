# SPDX-License-Identifier: GPL-3.0-or-later
"""Contract of the equispaced blade resampling (odd/tasks/p1-5-equispaced-blade.md, E1/E2)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "validation" / "phaseVI" / "tools"
sys.path.insert(0, str(TOOLS))

from blade_resample import AIRFOIL_RADIUS, deviation, resample_blade  # noqa: E402
from case_config import read_blade  # noqa: E402


@pytest.fixture(scope="module")
def blade():
    return read_blade()


def test_root_stations_are_kept_verbatim(blade):
    out = resample_blade(blade, 0.1)
    root = [s for s in blade if s["radius"] < AIRFOIL_RADIUS]
    assert out[: len(root)] == root


def test_outboard_spacing_is_constant_and_spans_root_to_tip(blade):
    out = resample_blade(blade, 0.1)
    outboard = [s["radius"] for s in out if s["radius"] >= AIRFOIL_RADIUS]
    assert outboard[0] == pytest.approx(AIRFOIL_RADIUS)
    assert outboard[-1] == pytest.approx(blade[-1]["radius"])
    steps = [b - a for a, b in zip(outboard, outboard[1:])]
    assert max(steps) - min(steps) < 1e-9
    assert max(steps) <= 0.1 + 1e-12


def test_exact_at_surviving_original_stations(blade):
    out = resample_blade(blade, 0.1)
    by_r = {round(s["radius"], 9): s for s in out}
    for s in (blade[3], blade[-1]):
        got = by_r[round(s["radius"], 9)]
        for key in ("chord", "twist", "mount"):
            assert got[key] == pytest.approx(s[key])


def test_deviation_shrinks_with_dz(blade):
    coarse = deviation(blade, resample_blade(blade, 0.1))
    fine = deviation(blade, resample_blade(blade, 0.025))
    assert fine["chord"] < coarse["chord"]
    assert fine["twist"] < coarse["twist"]
    assert fine["chord_area"] < 0.01


def test_rejects_nonpositive_dz(blade):
    with pytest.raises(ValueError):
        resample_blade(blade, 0.0)
