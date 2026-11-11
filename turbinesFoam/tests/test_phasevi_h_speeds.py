# SPDX-License-Identifier: GPL-3.0-or-later
"""Sequence H archive speeds 6 and 8 m/s (phasevi-validation-extension S3, T4).

5, 6 and 8 m/s are optional kinematics rows next to the six required campaign speeds; an
unconfigured speed must still be rejected by the renderer.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
PACKAGE = TESTS_DIR.parent / "validation" / "phaseVI"
GENERATOR = PACKAGE / "tools" / "generate_case.py"


def render(tmp_path: Path, sequence: str, speed: str):
    case = tmp_path / f"{sequence}{speed}"
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--sequence", sequence, "--speed", speed,
         "--mesh", "coarse", "--case-dir", str(case)],
        capture_output=True, text=True, check=False,
    )
    return result, case


@pytest.mark.parametrize("speed,tsr", [("6", 6.299), ("8", 4.739), ("7", 5.408)])
def test_h_speed_renders_with_measured_tsr(tmp_path, speed, tsr):
    result, case = render(tmp_path, "H", speed)
    assert result.returncode == 0, result.stderr
    text = (case / "system" / "fvOptions.ALM").read_text()
    match = re.search(r"tipSpeedRatio\s+([0-9.eE+-]+)", text)
    assert match is not None
    assert float(match.group(1)) == pytest.approx(tsr, abs=1e-9)


def test_unknown_h_speed_still_fails(tmp_path):
    result, _ = render(tmp_path, "H", "9")
    assert result.returncode != 0
    assert "unsupported wind speed" in result.stderr + result.stdout
