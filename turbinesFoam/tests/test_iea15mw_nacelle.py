# SPDX-License-Identifier: GPL-3.0-or-later
"""IEA 15 MW nacelle on/off: generator option, geometry and regression guard.

Pure Python (no OpenFOAM). The WindIO yaml is read from ``IEA15MW_WINDIO``
(default documented in ``blade_geometry``); tests needing it skip when absent.
"""

from __future__ import annotations

import hashlib
import importlib.util
import math
import re
import struct
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
PACKAGE = TESTS_DIR.parent / "validation" / "iea15mw"


def _load(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(PACKAGE / "tools"))
gc = _load("iea15mw_nacelle_generate_case", PACKAGE / "tools" / "generate_case.py")

CASE = TESTS_DIR / "_iea_case"  # never created; only fixes relative paths

#: sha256 of every rendered file, captured BEFORE the nacelle option existed.
BASELINE = {
    "default": ({}, "56fc40064d6dea2468d9b2f66991196884b744e0d32664d1ed07f2ac396366b3"),
    "hub": ({"hub": True}, "7d3b9ca8d1b19f7018e3df1e63fff43823b222d74567276701a70aa268436a1e"),
    "notower": ({"tower": False}, "9e84602d5aabca599e95a91bb148992e29ac20daf8feb40e1cc527790990eb72"),
    "asm": ({"model": "asm"}, "375d00bedc89b534dce63e6b273f19b347b59530afd40dc9f9b2f0e8e10507f9"),
    "flowx": ({"flow_axis": "x"}, "8de58d0ba31dc4ae4188e204d348d0d5c32971ae7c6234fbedcdc67b23f083d2"),
}


def _render(**kwargs):
    return gc.outputs(domain=gc.domain_spec(), case_dir=CASE, **kwargs)


def _digest(rendered) -> str:
    text = "".join(
        f"{path.relative_to(CASE)}\0{content}\0" for path, content in sorted(rendered.items())
    )
    return hashlib.sha256(text.encode()).hexdigest()


def _windio_available() -> bool:
    return gc.blade_geometry.DEFAULT_WINDIO.exists()


needs_windio = pytest.mark.skipif(not _windio_available(), reason="WindIO yaml absent")


@pytest.mark.parametrize("name", sorted(BASELINE))
def test_nacelle_off_is_byte_identical(name):
    kwargs, expected = BASELINE[name]
    assert _digest(_render(**kwargs)) == expected
    assert _digest(_render(nacelle=False, **kwargs)) == expected


@needs_windio
def test_nacelle_geometry_from_windio():
    spec = gc.nacelle_spec("x")
    assert spec["overhang"] == pytest.approx(12.0313)
    assert spec["uptilt_deg"] == pytest.approx(6.0)
    assert spec["radius"] > 0.5 * gc.blade_geometry.HUB_DIAMETER
    assert spec["length"] > 0.0
    ax = spec["axis"]
    # Downwind (+x for flow_axis x) and tilted: the tail sits BELOW the hub.
    assert ax[0] == pytest.approx(math.cos(math.radians(6.0)))
    assert ax[2] == pytest.approx(-math.sin(math.radians(6.0)))
    # Flat cap starts at the hub surface, behind the hub centre.
    assert spec["start"][0] == pytest.approx(gc.blade_geometry.HUB_RADIUS * ax[0])
    # The yaw axis (overhang) lies inside the body.
    total = spec["length"] + spec["radius"]
    assert 0.0 < spec["overhang"] - gc.blade_geometry.HUB_RADIUS < total


@needs_windio
@pytest.mark.parametrize("flow_axis", ["x", "y"])
def test_nacelle_inside_refinement_box(flow_axis):
    spec = gc.nacelle_spec(flow_axis)
    tail = [spec["start"][i] + spec["axis"][i] * (spec["length"] + spec["radius"]) for i in range(3)]
    toposet = _render(flow_axis=flow_axis, nacelle=True)[CASE / "system" / "topoSetDict"]
    match = re.search(r"box \(([^)]*)\) \(([^)]*)\)", toposet)
    assert match is not None
    nums = [float(v) for v in match.group(1).split()]
    nums2 = [float(v) for v in match.group(2).split()]
    for i in range(3):
        for point in (spec["start"], tail):
            assert nums[i] + spec["radius"] < point[i] < nums2[i] - spec["radius"]


@needs_windio
def test_nacelle_on_renders_dictionary():
    rendered = _render(flow_axis="x", nacelle=True)
    on = rendered[CASE / "system" / "fvOptions.ALM"]
    off = _render(flow_axis="x")[CASE / "system" / "fvOptions.ALM"]
    assert re.search(r"^        nacelle\n", on, re.M)
    assert "nacelle" not in off
    assert "geometry" in on and "constant/triSurface/iea15mw_nacelle.stl" in on
    # Only the nacelle dictionary differs.
    assert on.replace(on[on.index("        nacelle\n"):on.index("        profileData")], "") == off


@needs_windio
def test_nacelle_stl_is_closed_and_oriented(tmp_path):
    out = gc.write_nacelle_stl(tmp_path, "x")
    assert out.name == "iea15mw_nacelle.stl"
    data = out.read_bytes()
    n = struct.unpack("<I", data[80:84])[0]
    assert n > 100 and len(data) == 84 + 50 * n
    spec = gc.nacelle_spec("x")
    xs = [struct.unpack("<3f", data[84 + 50 * k + 12 + 12 * j:][:12])[0] for k in range(n) for j in range(3)]
    assert min(xs) >= spec["start"][0] - spec["radius"] * math.sin(math.radians(6.0)) - 1e-3


@needs_windio
def test_cli_writes_stl_only_when_on(tmp_path):
    on, off = tmp_path / "on", tmp_path / "off"
    assert gc.main(["--case-dir", str(on), "--nacelle", "on"]) == 0
    assert gc.main(["--case-dir", str(off)]) == 0
    assert (on / "constant" / "triSurface" / "iea15mw_nacelle.stl").is_file()
    assert not (off / "constant" / "triSurface" / "iea15mw_nacelle.stl").exists()
