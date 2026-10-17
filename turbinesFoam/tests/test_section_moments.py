# SPDX-License-Identifier: GPL-3.0-or-later
"""Force x arm helpers of `validation/phaseVI/scripts/compareSectionLoads.py`.

The table ranks station deficits by their share of the blade-root moments and
of the shaft torque (owner priority: the tangential force matters structurally,
so deficits are ranked by force x arm, not by percent). These tests pin the
two pure pieces: the trapezoidal station widths and the arm weighting.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "validation" / "phaseVI" / "scripts"
sys.path.insert(0, str(SCRIPTS))
compareSectionLoads = pytest.importorskip("compareSectionLoads")


def test_station_widths_use_half_the_gap_between_neighbours_and_the_span_ends() -> None:
    r = compareSectionLoads.R
    widths = compareSectionLoads.station_widths((0.5, 0.6, 0.9), 1.0, r)
    assert widths[0] == pytest.approx((0.6 * r - 1.0) / 2.0)
    assert widths[1] == pytest.approx((0.9 * r - 0.5 * r) / 2.0)
    assert widths[2] == pytest.approx((r - 0.6 * r) / 2.0)


def test_station_widths_on_a_uniform_grid_equal_the_spacing() -> None:
    widths = compareSectionLoads.station_widths((0.2, 0.4, 0.6), 0.0, 4.0)
    # R is the module constant: stations sit at 0.2R, 0.4R, 0.6R
    r = compareSectionLoads.R
    assert widths[1] == pytest.approx(0.2 * r)


def test_arm_contributions_weight_flap_edge_by_root_arm_and_torque_by_radius() -> None:
    flap, edge, torque = compareSectionLoads.arm_contributions(
        r=3.0, d_r=0.5, f_n=100.0, f_t=20.0, r_cut=1.0
    )
    assert flap == pytest.approx(100.0 * 2.0 * 0.5)
    assert edge == pytest.approx(20.0 * 2.0 * 0.5)
    assert torque == pytest.approx(20.0 * 3.0 * 0.5)


EXPERIMENT = SCRIPTS.parent / "data" / "experiment"


def test_experiment_defaults_to_sequence_h() -> None:
    assert compareSectionLoads.read_experiment(str(EXPERIMENT), 7.0)[0.3][0] == pytest.approx(0.8139)
    assert compareSectionLoads.read_density(str(EXPERIMENT), 7.0) == pytest.approx(1.2337256249087292)


def test_experiment_reads_the_requested_sequence() -> None:
    assert compareSectionLoads.read_experiment(str(EXPERIMENT), 7.0, "S")[0.3][0] == pytest.approx(0.8034)
    assert compareSectionLoads.read_density(str(EXPERIMENT), 7.0, "S") == pytest.approx(1.252490990875888)
