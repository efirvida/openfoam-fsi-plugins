#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Render the IEA 22-280-RWT rated-point case from the committed data.

Counterpart of ``validation/iea15mw/tools/generate_case.py``. The renderer is
*not* copied: the IEA-15 generator (mesh, solver, ALM/ASM/ASM-MESH ``fvOptions``,
snappyHexMesh, nacelle, every ``--flag`` and ``TURBINE_*`` environment bridge) is
loaded from its source file into a private module in which

- ``import blade_geometry`` resolves to the IEA-22 geometry module
  (``tools/blade_geometry.py``: 59 stations, R = 142 m, hub 4.2 m, WindIO-2.0
  readers), and
- the module-level turbine constants are replaced by the IEA-22 values below
  (operating point, rotor radius/diameter, hub height, element count, data and
  output paths, castellated-mesh extents scaled with R).

Only the CLI defaults, the geometry source and the mesh extents differ from
IEA-15; no solver, model or force-kernel setting is changed, so a fix in the
IEA-15 generator reaches this case as well. The domain extents are multiples of
``ROTOR_DIAMETER`` and rescale automatically.

Operating point (WISDEM rated row of ``IEA-22-280-RWT_tabular.xlsx``, sheet
"Rotor Performance - WISDEM"): ``V = 11.134927 m/s``, ``Omega = 6.853997 rpm``,
collective pitch ``4.127462 deg`` (peak-shaved above the optimum pitch, see
PROVENANCE.md); TSR = ``Omega*R/V = 9.153`` = the reference design TSR.

Precone: ``elementData`` radius is the along-blade radius (``HubRad + BlSpn``,
tip 142.0 m) and the rotor is rendered with ``coneAngle 4`` (blade geometry, kept).
No shaft tilt anywhere (owner decision 2026-11-02): the rotor axis is horizontal
and the optional nacelle body is horizontal too; ``--shaft-tilt on`` opts into the
6 deg WindIO uptilt for the nacelle STL only.

Mesh proportions: the castellated extents, the tower box and the near-ground cell
are the IEA-15 constants times ``R22/R15`` (identical in units of R), see README.

Usage: same flags as ``iea15mw/tools/generate_case.py`` (``--help``); defaults
are the IEA-22 values. ``--check`` re-renders in memory and fails when a file on
disk is missing or stale, without writing anything.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
PACKAGE = TOOLS_DIR.parent
_IEA15_GENERATOR = PACKAGE.parent / "iea15mw" / "tools" / "generate_case.py"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


blade_geometry = _load_module("_iea22mw_blade_geometry", TOOLS_DIR / "blade_geometry.py")

# --- IEA-22 turbine constants (single source of truth for this package) -------
RATED_SPEED = 11.134927
RATED_RPM = 6.853997
RATED_PITCH_DEG = 4.127462
#: 59 stations -> 58 segments; 174 = 3 elements per segment.
N_ELEMENTS = 174
#: Mesh proportions (owner decision 2026-11-02): every castellated extent and the
#: near-ground cell are the IEA-15 values multiplied by ``R22/R15``, i.e. identical
#: in rotor-radius units. They are computed from the IEA-15 generator constants in
#: ``_build_module`` (single source of truth, nothing re-typed); the domain
#: extents, base cell (``D/32``) and time step already scale with R / D.
SNAPPY_SCALED = (
    "SNAPPY_DISK_RADIUS",
    "SNAPPY_DISK_HALF_THICKNESS",
    "SNAPPY_WAKE_RADIUS",
    "SNAPPY_WAKE_UPSTREAM",
    "SNAPPY_WAKE_DOWNSTREAM",
    "SNAPPY_TOWER_UPSTREAM",
    "SNAPPY_TOWER_DOWNSTREAM",
    "SNAPPY_TOWER_Z_MIN",
    "SNAPPY_TOWER_Z_MAX",
    "Z_GROUND_CELL",
    "ASM_TOWER_LATERAL_FACTOR",
)
#: Shaft tilt is off by default (owner decision); ``--shaft-tilt on`` opts in.
DEFAULT_SHAFT_TILT = "off"


def _build_module():
    """Load the IEA-15 generator bound to the IEA-22 geometry and constants."""
    previous = sys.modules.get("blade_geometry")
    sys.modules["blade_geometry"] = blade_geometry
    try:
        module = _load_module("_iea22mw_generate_case_impl", _IEA15_GENERATOR)
    finally:
        if previous is None:
            sys.modules.pop("blade_geometry", None)
        else:
            sys.modules["blade_geometry"] = previous

    module.PACKAGE = PACKAGE
    module.BLADE_CSV = blade_geometry.BLADE_CSV
    module.POLARS_DIR = PACKAGE / "data" / "polars"
    module.DEFAULT_CASE_DIR = PACKAGE / "case"
    module.RATED_SPEED = RATED_SPEED
    module.RATED_RPM = RATED_RPM
    module.RATED_PITCH_DEG = RATED_PITCH_DEG
    module.ROTOR_RADIUS = blade_geometry.ROTOR_RADIUS_PUBLISHED
    module.ROTOR_DIAMETER = 2.0 * module.ROTOR_RADIUS
    module.HUB_HEIGHT = blade_geometry.HUB_HEIGHT
    module.N_ELEMENTS = N_ELEMENTS
    module.PRECONE_DEG = blade_geometry.PRECONE_DEG
    module.DEFAULT_DOMAIN_TOP = 2.5 * module.ROTOR_DIAMETER
    module.Z_HUB_CELL = module.ROTOR_DIAMETER / 32.0
    module.SURFACE_GEOMETRY = "constant/triSurface/iea22mw_blade.stl"
    module.NACELLE_STL = "constant/triSurface/iea22mw_nacelle.stl"
    # R-proportional extents: IEA-15 value / R15 * R22 (read before any patching).
    iea15_geometry = _load_module(
        "_iea15mw_blade_geometry_ref", _IEA15_GENERATOR.parent / "blade_geometry.py"
    )
    scale = module.ROTOR_RADIUS / iea15_geometry.ROTOR_RADIUS_PUBLISHED
    for key in SNAPPY_SCALED:
        setattr(module, key, getattr(module, key) * scale)
    module.DEFAULT_SHAFT_TILT = DEFAULT_SHAFT_TILT
    module.EXPECTED_CELL_COUNT = module.cell_count()
    return module


_impl = _build_module()

#: Public surface: everything of the IEA-15 generator, rebound to IEA-22.
globals().update(
    {k: v for k, v in vars(_impl).items() if not k.startswith("__")}
)
impl = _impl


def outputs(*args, **kwargs):
    """``outputs`` with the IEA-22 defaults (the IEA-15 defaults are bound at
    function-definition time and cannot be rebound by patching the module)."""
    if args:
        raise TypeError("outputs() takes keyword arguments only")
    kwargs.setdefault("speed", RATED_SPEED)
    kwargs.setdefault("rpm", RATED_RPM)
    kwargs.setdefault("pitch_deg", RATED_PITCH_DEG)
    kwargs.setdefault("case_dir", PACKAGE / "case")
    kwargs.setdefault("n_elements", N_ELEMENTS)
    kwargs.setdefault("cone_angle", blade_geometry.PRECONE_DEG)
    for key in SNAPPY_SCALED[:9]:  # IEA-15 defaults are bound at definition time
        kwargs.setdefault(key.lower(), getattr(_impl, key))
    kwargs.setdefault("snappy_tower_lateral_factor", _impl.ASM_TOWER_LATERAL_FACTOR)
    return _impl.outputs(**kwargs)


def main(argv: list[str] | None = None) -> int:
    return _impl.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
