# SPDX-License-Identifier: GPL-3.0-or-later
"""Registry validation of the `--tip-effects` variant flag in checkModelDefinition.py."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

PACKAGE = Path(__file__).resolve().parents[1] / "validation/phaseVI"
ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}


def _registry_with(tmp_path, flags):
    package = tmp_path / "phaseVI"
    shutil.copytree(PACKAGE, package, ignore=shutil.ignore_patterns(
        "runs", "results", "polyMesh", "__pycache__"))
    (tmp_path / "geometry").symlink_to(PACKAGE.parents[1] / "geometry")
    (package / "config/model-variants.yaml").write_text(
        "variants:\n  probe:\n    reference: 'probe'\n    flags:\n" + flags)
    return package


@pytest.mark.parametrize("value,returncode,stdout,stderr", [
    ("off", 0, "--tip-effects\noff\n", ""),
    ("maybe", 2, "", "error: invalid variant flag value: --tip-effects=maybe\n"),
])
def test_tip_effects_flag_is_validated(tmp_path, value, returncode, stdout, stderr):
    package = _registry_with(tmp_path, f"      --tip-effects: '{value}'\n")
    result = subprocess.run(
        [sys.executable, str(package / "scripts/checkModelDefinition.py"),
         "--variant", "probe", "--renderer-flags"],
        capture_output=True, text=True, env=ENV)
    assert (result.returncode, result.stdout, result.stderr) == (returncode, stdout, stderr)
