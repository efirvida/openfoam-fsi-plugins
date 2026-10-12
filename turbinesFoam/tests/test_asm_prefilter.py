# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit check of the actuator surface element's cell prefilter box.

Builds and runs `tests/asmPrefilterBox`, which links `libturbinesFoam` and
asserts that every chord strip keeps its Gaussian kernel inside the box that
`actuatorSurfaceElement::chordPrefilterBox` returns, with a margin of exactly
`projectionRadius` metres (the v2506 `boundBox::inflate` takes a span
fraction, `grow` takes metres).
"""

import os
import subprocess

import pytest


@pytest.fixture(scope="module")
def app_dir():
    return os.path.join(os.path.dirname(__file__), "asmPrefilterBox")


def test_prefilter_box_keeps_the_kernel(app_dir):
    subprocess.check_call(["wmake"], cwd=app_dir)
    appbin = os.environ.get("FOAM_USER_APPBIN", "")
    exe = os.path.join(appbin, "asmPrefilterBox") if appbin else "asmPrefilterBox"
    out = subprocess.run([exe], cwd=app_dir, capture_output=True, text=True)
    assert out.returncode == 0, "\n".join(
        line for line in out.stdout.splitlines() if line.startswith("FAIL")
    )
    assert "0 failing cases" in out.stdout
