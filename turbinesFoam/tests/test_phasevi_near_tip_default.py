# SPDX-License-Identifier: GPL-3.0-or-later
"""Model Definition v1.4: the renderer default is the record (near-tip correction on).

v1.4 = v1.3 + `nearTipCorrection` (Trigaux 2024 F_Cl). A plain `generate_case.py`
render carries the block and stages the table; `--near-tip-correction off` is the
frozen v1.3 render, and the v1.2/v1.3 launchers pin it.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "validation" / "phaseVI"
ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
BLOCK = [
    "nearTipCorrection", "active on;", "model TrigauxVirtualCamber;", 'table "system/trigaux2024_tableC.csv";',
    'kernel "3D";', "sigmaOverC 0.25;",
]
LAUNCHERS = ["v1-2-evaluation", "v1-2-lag", "v1-2-run", "v1-2-small-eps", "variant-run"]


def _render(tmp_path, name, *flags):
    case = tmp_path / name
    result = subprocess.run(
        [sys.executable, str(PACKAGE / "tools/generate_case.py"), "--case-dir", str(case), *flags],
        capture_output=True, text=True, env=ENV)
    assert result.returncode == 0, result.stderr
    return case


def test_plain_render_is_v14_with_the_block_and_the_table(tmp_path):
    case = _render(tmp_path, "plain")
    text = (case / "system/fvOptions.ALM").read_text()
    for token in BLOCK:
        assert token in text
    assert (case / "system/trigaux2024_tableC.csv").is_file()


def test_off_renders_v13_without_block_or_table(tmp_path):
    case = _render(tmp_path, "off", "--near-tip-correction", "off")
    assert "nearTipCorrection" not in (case / "system/fvOptions.ALM").read_text()
    assert not (case / "system/trigaux2024_tableC.csv").exists()


def test_committed_twins_are_the_v14_render():
    result = subprocess.run([sys.executable, str(PACKAGE / "tools/generate_case.py"), "--check"],
                            capture_output=True, text=True, env=ENV)
    assert (result.returncode, result.stderr) == (0, "")
    for twin in ("ALM", "ASM", "ASM-MESH"):
        assert "nearTipCorrection" in (PACKAGE / f"case/system/fvOptions.{twin}").read_text()


def test_older_launchers_pin_the_near_tip_correction_off():
    for launcher in LAUNCHERS:
        text = (PACKAGE / f"scripts/slurm/{launcher}.slurm").read_text()
        assert "--near-tip-correction off" in text, launcher
