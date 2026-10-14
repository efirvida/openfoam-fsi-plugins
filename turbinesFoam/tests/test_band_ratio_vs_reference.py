# SPDX-License-Identifier: GPL-3.0-or-later
"""Contract for `band_ratio_vs_reference.py` on synthetic profiles."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "validation" / "iea15mw" / "scripts"))

import band_ratio_vs_reference as tool  # noqa: E402


def test_chord_pair_is_rebuilt_from_cl_cd_alpha_and_ratioed_per_band(tmp_path):
    profiles = tmp_path / "p.csv"
    with profiles.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["model", "r_over_R", "alpha_deg", "cl", "cd"])
        for r in (0.35, 0.45, 0.75):
            writer.writerow(["alm", r, 0.0, 1.2, 0.1])  # cn = cl, ct = -cd
    models = tool.read_models(profiles)
    assert models["alm"][0][1] == pytest.approx(1.2)
    assert models["alm"][0][2] == pytest.approx(-0.1)
    reference = [(0.0, 1.0), (1.0, 1.0)]
    ratios = {(lo, hi): ratio for lo, hi, ratio, _ in tool.band_ratios(models["alm"], reference, 1)}
    assert ratios[(0.3, 0.5)] == pytest.approx(1.2)
    assert ratios[(0.7, 0.9)] == pytest.approx(1.2)
    assert ratios[(0.5, 0.7)] != ratios[(0.5, 0.7)]  # no stations: NaN
