# SPDX-License-Identifier: GPL-3.0-or-later
"""The inflow force-direction proxy can select the archive reference."""
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "validation/phaseVI/scripts"
sys.path.insert(0, str(SCRIPTS))
import compareInflowAngle as inflow


@pytest.mark.parametrize("directory", [None, "archive-fixture"])
def test_experiment_directory_pass_through(monkeypatch, directory):
    monkeypatch.setattr(inflow, "converged_window", lambda *a, **k: (0, 1, {}))
    seen = []

    class Stop(Exception):
        pass

    def read(path):
        seen.append(str(path))
        raise Stop

    monkeypatch.setattr(inflow, "read_table", read)
    argv = ["compareInflowAngle.py", "--sequence", "H", "--speed", "5"]
    if directory:
        argv += ["--experiment-dir", directory]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(Stop):
        inflow.main()
    assert seen == [f"{directory or 'data/experiment'}/sequence_H_spanwise.csv"]
