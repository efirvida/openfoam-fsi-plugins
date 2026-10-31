# SPDX-License-Identifier: GPL-3.0-or-later
"""IEA ASM+mesh: the staged blade surface carries the element chord angle.

Counterpart of `test_blade_pitch_reference.py` (Phase VI B1). The sampler applies no
element pitch, so the STL section chord angle must equal `-pitch` of the case's element
rows. The measured tolerance is the LE -> TE-midpoint bias on the thickest airfoil
section (0.29 deg); the Phase VI defect this guards against was 1.815 deg.
"""

from __future__ import annotations

import sys
from pathlib import Path

TURBINESFOAM = Path(__file__).resolve().parents[1]
TOOLS = TURBINESFOAM / "validation" / "iea15mw" / "tools"
sys.path.insert(0, str(TOOLS))

from check_stl_orientation import TOLERANCE_DEG, differences, main  # noqa: E402


def test_staged_surface_matches_element_chord_angle():
    rows = differences()
    assert len(rows) > 30
    assert max(abs(measured - expected) for _, measured, expected in rows) < TOLERANCE_DEG


def test_outboard_stations_agree_within_a_tenth_of_a_degree():
    rows = [row for row in differences() if row[0] >= 60.0]
    assert max(abs(measured - expected) for _, measured, expected in rows) < 0.1


def test_a_tip_twist_shift_would_be_detected():
    rows = differences()
    assert max(abs(measured - (expected + 1.815)) for _, measured, expected in rows) > 5 * TOLERANCE_DEG


def test_cli_exit_code_follows_tolerance(capsys):
    assert main([]) == 0
    assert "max |STL chord angle" in capsys.readouterr().out
    assert main(["--tolerance", "0.01"]) == 1
