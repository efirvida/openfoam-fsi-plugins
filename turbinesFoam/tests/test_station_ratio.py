# SPDX-License-Identifier: GPL-3.0-or-later
"""station_ratio.py pools two spanwise profiles in r/R bands."""

import importlib.util
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[1] / "validation" / "iea15mw" / "scripts" / "station_ratio.py"
_spec = importlib.util.spec_from_file_location("station_ratio", _PATH)
station_ratio = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(station_ratio)


def _profile(scale):
    return [
        {"r/R": r, "alpha_deg": 5.0 * scale, "Fn_per_len": 10.0 * scale, "Ft_per_len": 2.0 * scale}
        for r in (0.05, 0.2, 0.6, 0.97)
    ]


def test_ratio_is_a_over_b_per_band():
    got = station_ratio.band_ratios(_profile(2.0), _profile(1.0), (0.0, 0.5, 1.0))
    assert [row["stations"] for row in got] == [2, 2]
    assert got[0]["fn_ratio"] == pytest.approx(2.0)
    assert got[0]["d_alpha"] == pytest.approx(5.0)


def test_empty_band_is_skipped():
    got = station_ratio.band_ratios(_profile(1.0), _profile(1.0), (0.0, 0.01, 1.0))
    assert len(got) == 1


def test_different_stations_are_rejected():
    other = _profile(1.0)
    other[0]["r/R"] = 0.06
    with pytest.raises(ValueError):
        station_ratio.band_ratios(_profile(1.0), other, (0.0, 1.0))
