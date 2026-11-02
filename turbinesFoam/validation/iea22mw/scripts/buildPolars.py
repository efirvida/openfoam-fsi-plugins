#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Convert IEA 22-280-RWT AeroDyn15 AirfoilInfo polars to ``profileData``.

Counterpart of ``validation/iea15mw/scripts/buildPolars.py``: the AirfoilInfo
parser (``parse_airfoilinfo``), the source discovery and the ``Cm`` convention
are *reused* from that module (loaded by path). Only the output location, the
default source directory and the header notes are IEA-22 specific.

Reads the 59 per-station ``IEA-22-280-RWT_AeroDyn15_Polar_NN.dat`` files
(``NN`` = 00..58; ``BlAFID = NN + 1``) and emits one committed ``profileData``
body per station, ``data/polars/polar_NN.dat``::

    Re <value>;
    liftReCorrExp 0;
    data ( (alpha_deg Cl Cd Cm) ... );

``Cm`` is the quarter-chord moment, positive nose-up, passed through unchanged
(same convention as the IEA-15 package). No coefficient is modified.

Usage:
    buildPolars.py [--check] [--source-dir DIR]

``--check`` re-renders in memory and exits 1 when a committed file is missing or
stale, when the number of polars differs from 59 or the source is absent,
without writing anything.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
POLARS_DIR = ROOT / "data" / "polars"
OUTPUT_TEMPLATE = "polar_{station:02d}.dat"
#: Number of AeroDyn polars (one per blade station).
N_POLARS = 59

#: Read-only AirfoilInfo source directory (override with ``IEA22MW_AEROFOIL_DIR``).
DEFAULT_SOURCE_DIR = Path(
    os.environ.get(
        "IEA22MW_AEROFOIL_DIR",
        "/scratch/leahk/eduardo.donestevez/simulations/tmp/iea22-src/repo/"
        "OpenFAST/IEA-22-280-RWT/Airfoils",
    )
)

LIFT_RE_CORR_NOTE = (
    "liftReCorrExp 0 disables ONLY the lift rescaling of profileData::updateRe"
    " (cl_new(alpha) = K*cl_org(alpha/K), K = (Re/ReRef)^0.23), which shifts the"
    " geometric zero-lift angle; only the drag half of the Re correction stays"
    " active. Same convention as the IEA-15 polars (equal-polar comparison).",
)


def _load_iea15():
    name = "_iea15mw_build_polars_shared"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, ROOT.parent / "iea15mw" / "scripts" / "buildPolars.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_base = _load_iea15()

AirfoilInfoError = _base.AirfoilInfoError
parse_airfoilinfo = _base.parse_airfoilinfo
CM_NOTE = _base.CM_NOTE


def render_profile(
    station: int,
    source_name: str,
    re_millions: float,
    rows: list[tuple[float, float, float, float]],
) -> str:
    """Render one committed ``profileData`` body."""
    lines = [
        f"// AeroDyn15 AirfoilInfo polar -> profileData, station {station:02d}.",
        f"// Source: {source_name} (read-only; see PROVENANCE.md).",
        "// Re is the source header value (given there in millions of Reynolds"
        " number);",
        "// every station file carries the same nominal Re = 3.0e6 (a known"
        " limitation).",
        f"// {CM_NOTE}",
        "// (alpha_deg Cl Cd Cm)",
        f"Re {re_millions * 1e6:g};",
        *[f"// {note_line}" for note_line in LIFT_RE_CORR_NOTE],
        "liftReCorrExp 0;",
        "data",
        "(",
    ]
    for alpha, cl, cd, cm in rows:
        lines.append(f"    ({alpha:.8g} {cl:.8g} {cd:.8g} {cm:.8g})")
    lines.append(");")
    return "\n".join(lines) + "\n"


def discover_sources(source_dir: Path | str | None = None) -> dict[int, Path]:
    """Map station index -> AirfoilInfo source file; exactly 59 contiguous."""
    directory = Path(source_dir) if source_dir is not None else DEFAULT_SOURCE_DIR
    sources = _base.discover_sources(directory)
    if sorted(sources) != list(range(N_POLARS)):
        raise AirfoilInfoError(
            f"{directory}: expected polars 00..{N_POLARS - 1:02d}, "
            f"found {len(sources)} files"
        )
    return sources


def build_all(source_dir: Path | str | None = None) -> dict[Path, str]:
    """Render every polar; returns ``{output_path: content}``."""
    rendered: dict[Path, str] = {}
    for station, path in sorted(discover_sources(source_dir).items()):
        parsed: dict[str, Any] = parse_airfoilinfo(path)
        rendered[POLARS_DIR / OUTPUT_TEMPLATE.format(station=station)] = (
            render_profile(
                station, path.name, parsed["re_millions"], parsed["rows"]
            )
        )
    return rendered


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT.parent.parent))
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail (exit 1) if the committed polar files are missing or stale",
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=None,
        help="AirfoilInfo source directory (default: IEA22MW_AEROFOIL_DIR)",
    )
    args = parser.parse_args(argv)

    try:
        rendered = build_all(args.source_dir)
    except (FileNotFoundError, AirfoilInfoError) as error:
        print(str(error), file=sys.stderr)
        return 1

    stale = False
    for path, content in rendered.items():
        if args.check:
            if not path.exists():
                print(f"missing polar file: {path}", file=sys.stderr)
                stale = True
            elif path.read_text(encoding="utf-8") != content:
                print(f"stale polar file: {path}", file=sys.stderr)
                stale = True
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            print(f"wrote {_display_path(path)}")

    if args.check:
        if stale:
            return 1
        print(f"{len(rendered)} polar files up to date")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
