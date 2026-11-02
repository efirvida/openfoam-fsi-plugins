# SPDX-License-Identifier: GPL-3.0-or-later
"""The NASA-Ames 24.4 m x 36.6 m test section as a Phase VI domain (`tunnel`).

The free box ignores wall blockage (rotor/section area ~ 8.9 %). `--domain
tunnel` closes the lateral and vertical boundaries on the physical test
section (slip walls) while keeping the cell size around the rotor, so the
domain is the only change against the `long` reference: any load difference is
blockage, not discretisation.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
PACKAGE = TESTS_DIR.parent / "validation" / "phaseVI"
sys.path.insert(0, str(PACKAGE / "tools"))

import generate_case  # noqa: E402
from case_config import (  # noqa: E402
    axis_extents_D,
    blockage_ratio,
    cell_count,
    cell_sizes,
    domain_resolution,
    hub_cell_size,
    load_config,
    validate_config,
)

BLOCK = re.compile(
    r"^\s+hex \(([^)]*)\) \((\d+) (\d+) (\d+)\) simpleGrading \(([^)]*)\)",
    re.MULTILINE,
)


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def test_tunnel_extents_are_the_test_section(cfg):
    hub = cfg["turbine"]["hub_height"]
    y = axis_extents_D(cfg, "y", "tunnel")
    z = axis_extents_D(cfg, "z", "tunnel")
    x = axis_extents_D(cfg, "x", "tunnel")
    assert (y[0], y[-1]) == (-18.3, 18.3)
    assert (z[0], z[-1]) == (0.0, 24.4)
    assert hub in z
    assert x == axis_extents_D(cfg, "x", "long")
    assert len(y) == len(axis_extents_D(cfg, "y", "long"))
    assert len(z) == len(axis_extents_D(cfg, "z", "long"))


def test_blockage_ratio_is_rotor_over_section(cfg):
    assert blockage_ratio(cfg) == pytest.approx(0.0889, abs=5e-4)


def test_tunnel_block_mesh_is_18_blocks_and_smaller(cfg):
    text = generate_case.render_block_mesh(cfg, "coarse", "tunnel", "production")
    blocks = BLOCK.findall(text)
    assert len(blocks) == 18
    total = sum(int(nx) * int(ny) * int(nz) for _, nx, ny, nz, _ in blocks)
    assert total == cell_count(cfg, "coarse", "tunnel")
    assert total < cell_count(cfg, "coarse", "long")
    assert text.count("type symmetryPlane;") == 4


def test_tunnel_keeps_the_cell_size_next_to_the_rotor(cfg):
    """Core y block untouched; the cells beside it and at the hub keep size."""
    for mesh in ("coarse", "fine", "ultra"):
        long_res = cfg["mesh"]["resolutions"][mesh]
        tun_res = domain_resolution(cfg, mesh, "tunnel")
        assert tun_res["y"]["cells"][1] == long_res["y"]["cells"][1]
        assert tun_res["x"] == long_res["x"]
        ly = axis_extents_D(cfg, "y", "long")
        ty = axis_extents_D(cfg, "y", "tunnel")
        l_left = cell_sizes(ly[1] - ly[0], long_res["y"]["cells"][0], long_res["y"]["grading"][0])
        t_left = cell_sizes(ty[1] - ty[0], tun_res["y"]["cells"][0], tun_res["y"]["grading"][0])
        assert t_left[-1] == pytest.approx(l_left[-1], rel=1e-9)
        l_right = cell_sizes(ly[3] - ly[2], long_res["y"]["cells"][2], long_res["y"]["grading"][2])
        t_right = cell_sizes(ty[3] - ty[2], tun_res["y"]["cells"][2], tun_res["y"]["grading"][2])
        assert t_right[0] == pytest.approx(l_right[0], rel=1e-9)
        lz = axis_extents_D(cfg, "z", "long")
        tz = axis_extents_D(cfg, "z", "tunnel")
        l_up = cell_sizes(lz[2] - lz[1], long_res["z"]["cells"][1], long_res["z"]["grading"][1])
        t_up = cell_sizes(tz[2] - tz[1], tun_res["z"]["cells"][1], tun_res["z"]["grading"][1])
        assert t_up[0] == pytest.approx(l_up[0], rel=1e-9)
        l_lo = cell_sizes(lz[1] - lz[0], long_res["z"]["cells"][0], long_res["z"]["grading"][0])
        t_lo = cell_sizes(tz[1] - tz[0], tun_res["z"]["cells"][0], tun_res["z"]["grading"][0])
        assert t_lo[-1] == pytest.approx(l_lo[-1], rel=1e-9)
        assert hub_cell_size(cfg, mesh) == pytest.approx(
            max(t_up[0], t_lo[-1]), rel=1e-9
        )


def test_tunnel_blocks_fill_their_lengths(cfg):
    res = domain_resolution(cfg, "coarse", "tunnel")
    for axis in ("y", "z"):
        ext = axis_extents_D(cfg, axis, "tunnel")
        for i, (cells, grading) in enumerate(zip(res[axis]["cells"], res[axis]["grading"])):
            length = ext[i + 1] - ext[i]
            assert sum(cell_sizes(length, cells, grading)) == pytest.approx(length, rel=1e-9)


def test_long_domain_resolution_is_unchanged(cfg):
    assert domain_resolution(cfg, "coarse", "long") == cfg["mesh"]["resolutions"]["coarse"]
    assert domain_resolution(cfg, "coarse", "squat") == cfg["mesh"]["resolutions"]["coarse"]


def test_config_validates_with_tunnel(cfg):
    validate_config(cfg)
