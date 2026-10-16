"""Tests for the IEA 15 MW stall-margin analysis (stall_margin.py)."""

from __future__ import annotations

import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR.parent / "validation" / "iea15mw" / "scripts"))

import stall_margin  # noqa: E402


def _table():
    """Linear lift 0.1/deg from -3 deg to 10 deg, peak 1.3 at 13 deg, then a drop."""
    table = []
    for a in range(-10, 41):
        if a <= 10:
            cl = 0.1 * (a + 3.0)
        elif a <= 13:
            cl = 1.3 - 0.0 * (a - 10) + 0.0
        else:
            cl = 1.3 - 0.05 * (a - 13)
        table.append((float(a), cl))
    return table


def test_polar_metrics_find_zero_lift_and_peak():
    m = stall_margin.polar_metrics(_table())
    assert abs(m["alpha0"] + 3.0) < 1e-6
    assert abs(m["slope"] - 0.1) < 1e-6
    assert m["alpha_clmax"] is not None and 10.0 <= m["alpha_clmax"] <= 13.0
    assert m["alpha_dev"] is not None and m["alpha_dev"] > 10.0 - 1e-6


def test_cylinder_like_polar_is_skipped():
    flat = [(float(a), 0.01 * a / 40.0) for a in range(-180, 181, 5)]
    assert stall_margin.polar_metrics(flat) is None


def test_classify_orders_ok_near_nonlin_stall():
    m = {"alpha_dev": 10.0, "alpha_clmax": 13.0}
    assert stall_margin.classify(4.0, m, 3.0) == "ok"
    assert stall_margin.classify(8.0, m, 3.0) == "NEAR"
    assert stall_margin.classify(11.0, m, 3.0) == "NONLIN"
    assert stall_margin.classify(14.0, m, 3.0) == "STALL"
    assert stall_margin.classify(5.0, None, 3.0) == "n/a"


def test_committed_snapshot_has_attached_outer_blade():
    profile = stall_margin.read_profile(stall_margin.DEFAULT_CSV, "alm")
    rows = stall_margin.analyse(profile, stall_margin.read_blade())
    outer = [r for r in rows if r["r_R"] > 0.5]
    assert outer and all(r["flag"] != "STALL" for r in outer)
