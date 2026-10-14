# SPDX-License-Identifier: GPL-3.0-or-later
"""Contract for `make_nacelle_stl.py`: closed, outward-oriented, deterministic."""

from __future__ import annotations

import math
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "validation" / "tools"))

import make_nacelle_stl as tool  # noqa: E402


def read(path):
    data = path.read_bytes()
    count = struct.unpack("<I", data[80:84])[0]
    return [struct.unpack("<12fH", data[84 + 50 * i:134 + 50 * i]) for i in range(count)]


def test_volume_matches_analytic_and_normals_point_outward(tmp_path):
    out = tmp_path / "n.stl"
    assert tool.main([str(out), "--radius", "0.5", "--length", "2.0", "--axis", "0", "1", "0"]) == 0
    tris = read(out)
    volume = 0.0
    for rec in tris:
        a, b, c = rec[3:6], rec[6:9], rec[9:12]
        volume += sum(a[i] * (b[(i + 1) % 3] * c[(i + 2) % 3] - b[(i + 2) % 3] * c[(i + 1) % 3])
                      for i in range(3)) / 6.0
    analytic = math.pi * 0.25 * 2.0 + 2.0 / 3.0 * math.pi * 0.5 ** 3
    assert volume == pytest.approx(analytic, rel=0.03)
    assert volume > 0.0  # positive signed volume = outward normals
    ys = [v for rec in tris for v in (rec[4], rec[7], rec[10])]
    assert min(ys) == pytest.approx(0.0) and max(ys) == pytest.approx(2.5)


def test_output_is_deterministic(tmp_path):
    args = ["--radius", "1", "--length", "3", "--start", "1", "2", "3"]
    tool.main([str(tmp_path / "a.stl"), *args])
    tool.main([str(tmp_path / "b.stl"), *args])
    assert (tmp_path / "a.stl").read_bytes() == (tmp_path / "b.stl").read_bytes()
