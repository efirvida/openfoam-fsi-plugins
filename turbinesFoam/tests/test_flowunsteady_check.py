# SPDX-License-Identifier: GPL-3.0-or-later
"""FLOWUnsteady run checker (`validation/phaseVI/flowunsteady/check_smoke.py`).

Pins the per-revolution means and the convergence gate used before any
comparison: CT and CQ change < 1 % per revolution over the last 2 revolutions.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[1] / "validation" / "phaseVI" / "flowunsteady"
sys.path.insert(0, str(TOOL))
checker = pytest.importorskip("check_smoke")


def _rows(values_by_rev, steps=4):
    """Monitor rows at `steps` samples per revolution, rev 0 included."""
    rows = [dict(rev=0.0, CT=values_by_rev[0][0], CQ=values_by_rev[0][1])]
    for index, (ct, cq) in enumerate(values_by_rev):
        for step in range(1, steps + 1):
            rows.append(dict(rev=index + step / steps, CT=ct, CQ=cq))
    return rows


def test_revolution_means_use_samples_inside_each_revolution():
    rows = _rows([(0.6, 0.08), (0.5, 0.07), (0.4, 0.06)])
    means = checker.revolution_means(rows, ("CT", "CQ"))
    assert [round(m["CT"], 12) for m in means] == [0.6, 0.5, 0.4]
    assert [round(m["CQ"], 12) for m in means] == [0.08, 0.07, 0.06]
    assert [m["rev"] for m in means] == [1, 2, 3]


def test_partial_last_revolution_is_not_reported():
    rows = _rows([(0.6, 0.08), (0.5, 0.07)])[:-2]
    assert [m["rev"] for m in checker.revolution_means(rows, ("CT",))] == [1]


def test_gate_passes_below_one_percent_over_last_two_revolutions():
    means = [dict(rev=1, CT=0.70, CQ=0.09), dict(rev=2, CT=0.600, CQ=0.0800),
             dict(rev=3, CT=0.597, CQ=0.0796), dict(rev=4, CT=0.595, CQ=0.0795)]
    gate = checker.convergence_gate(means, ("CT", "CQ"))
    assert gate["converged"] is True
    assert gate["max_change_percent"]["CT"] == pytest.approx(100 * 0.003 / 0.597)


def test_gate_fails_when_one_coefficient_drifts():
    means = [dict(rev=1, CT=0.600, CQ=0.080), dict(rev=2, CT=0.600, CQ=0.078),
             dict(rev=3, CT=0.600, CQ=0.0779)]
    gate = checker.convergence_gate(means, ("CT", "CQ"))
    assert gate["converged"] is False
    assert gate["max_change_percent"]["CT"] == 0.0


def test_gate_needs_three_complete_revolutions():
    means = [dict(rev=1, CT=0.6, CQ=0.08), dict(rev=2, CT=0.6, CQ=0.08)]
    assert checker.convergence_gate(means, ("CT", "CQ"))["converged"] is False
