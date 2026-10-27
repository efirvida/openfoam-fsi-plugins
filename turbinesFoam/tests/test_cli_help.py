# SPDX-License-Identifier: GPL-3.0-or-later
"""Every validation command-line tool must print its ``--help``.

argparse expands ``%`` in help strings as a format, so a literal ``1%`` makes
``--help`` crash with ``ValueError: incomplete format`` while the tool itself
still runs. This test pins ``--help`` for every argparse CLI in ``validation/``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

VALIDATION = Path(__file__).resolve().parents[1] / "validation"
SCRIPT_DIRS = ("phaseVI/scripts", "phaseVI/tools", "phaseVI/openfast", "tools", "iea15mw/scripts")

CLIS = sorted(
    path
    for directory in SCRIPT_DIRS
    for path in (VALIDATION / directory).glob("*.py")
    if "ArgumentParser" in path.read_text(errors="replace")
)


def test_cli_inventory_is_not_empty() -> None:
    assert len(CLIS) > 20


def test_aerodyn_pipeline_clis_are_inventoried() -> None:
    names = {path.name for path in CLIS}
    assert {"buildAeroDynCase.py", "compareAeroDyn.py", "verifyAeroDyn.py", "rtestAeroDyn.py", "comparePrecision.py"} <= names


@pytest.mark.parametrize("script", CLIS, ids=lambda path: path.relative_to(VALIDATION).as_posix())
def test_help_exits_zero_and_prints_usage(script: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr[-400:]
    assert result.stdout.startswith("usage:")
    assert result.stderr == ""
