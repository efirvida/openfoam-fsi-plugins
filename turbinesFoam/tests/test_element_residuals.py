# SPDX-License-Identifier: GPL-3.0-or-later
"""Deterministic offline element-residual diagnostics."""
import math
from pathlib import Path
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]/"validation"/"phaseVI"/"scripts"
sys.path.insert(0, str(SCRIPTS))

from diagnoseElementResiduals import (  # noqa: E402
    bracket, element_data, glauert_factor, normalisation_ratio, polar_cl, station_values,
)


def test_glauert_hand_value():
    # B=2, rootDist=1/2, sin(phi)=1/2: exponent=-2.
    expected = 2 / math.pi * math.acos(math.exp(-2))
    assert glauert_factor(0.5, math.pi / 6) == pytest.approx(expected)
    assert glauert_factor(1.0, math.pi / 6) == 0.0
    hub = 2 / math.pi * math.acos(math.exp(-2 * (2.75 - 0.5) / 0.5))
    assert glauert_factor(0.5, math.pi / 6, root_effects=True,
                          radius=5.0, cut=0.5) == pytest.approx(expected * hub)


def test_bracket_and_station_interpolation():
    profile = [(0.29, 1.0, 0.8), (0.31, 3.0, 0.6), (0.96, 7.0, 0.2)]
    assert bracket(profile, 0.30) == (profile[0], profile[1])
    assert station_values(profile, 0.30) == pytest.approx((2.0, 0.7))
    assert bracket(profile, 0.95) == (profile[1], profile[2])
    assert station_values(profile, 0.29) == pytest.approx((1.0, 0.8))
    with pytest.raises(ValueError, match="outside element span"):
        bracket(profile, 0.99)


def test_element_reader_reuses_rowwise_chord_frame(tmp_path):
    directory = tmp_path / "postProcessing/actuatorLineElements/0"
    directory.mkdir(parents=True)
    # A non-binary root distance catches inconsistent radius mean arithmetic.
    header = "time,root_dist,cl,cd,alpha_deg,c_ref_n,c_ref_t,rel_vel_mag,end_effect_factor\n"
    rows = "".join(f"{i},0.2041234567,1,0,0,1,0,10,0.5\n" for i in range(15))
    (directory / "turbine.blade1.element12.csv").write_text(header + rows)
    profile, samples = element_data(tmp_path, 0, 14)
    assert len(profile) == 1
    assert profile[0][1:] == pytest.approx((1, 0, 0, 0.5, 1, 10, 0, 2))
    assert samples[profile[0][0]][0] == 12


def test_normalisation_ratio():
    assert normalisation_ratio(104.0, 1.3, 10.0) == pytest.approx(1.6)


def test_polar_cl_between_rows(tmp_path):
    polar = tmp_path / "polar.dat"
    polar.write_text("// (alpha cl cd cm)\n(0 0.1 0.01 0)\n(10 1.1 0.02 0)\n")
    assert polar_cl(polar, 2.5) == pytest.approx(0.35)
