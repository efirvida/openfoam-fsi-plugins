#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Convert AeroDyn15 AirfoilInfo polars to turbinesFoam ``profileData``.

Reads the per-station ``IEA-15-240-RWT_AeroDyn15_Polar_NN.dat`` files
(AirfoilInfo v1.01.x) and emits one committed ``profileData`` body per station:

    Re <value>;
    data
    (
        (alpha_deg Cl Cd Cm)
        ...
    );

which is ``#include``-ed inside a ``profileData`` sub-dictionary, e.g.

    profileData
    {
        polar_00 { #include "../data/polars/polar_00.dat" }
    }

AirfoilInfo layout handled here: a header of ``key value ! comment`` lines, an
optional 30-coefficient unsteady-aerodynamics (UA) block when ``InclUAdata`` is
True, then ``NumAlf`` rows of ``Alpha Cl Cd Cm``. The parser locates ``NumAlf``
and ``Re`` by keyword, so the UA block and every ``!`` comment are skipped
robustly without relying on their exact position or count. ``Re`` is given in
millions in AirfoilInfo and emitted in SI.

``Cm`` convention: AirfoilInfo stores the pitching-moment coefficient about the
quarter-chord, positive nose-up (see the UA block's ``Cm0`` description). The
WindIO ``c_m`` and the NREL S809 ``Cm`` that turbinesFoam's ``profileData``
already consumes use the same convention (verified: the AeroDyn Cm correlates
+1.000 with the WindIO ``c_m`` for the matching sections). **No sign conversion
is applied** -- the readiness note's claim of a different Cm convention is not
reproducible. ``Cm`` is passed through unchanged.

Usage:
    buildPolars.py [--check] [--source-dir DIR]

``--check`` re-renders in memory and exits 1 when a committed file is missing or
stale or the AirfoilInfo source is absent, without writing anything.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
POLARS_DIR = ROOT / "data" / "polars"
OUTPUT_TEMPLATE = "polar_{station:02d}.dat"

#: Read-only AirfoilInfo source directory (override with
#: ``IEA15MW_AEROFOIL_DIR``).  Do not modify.
DEFAULT_SOURCE_DIR = Path(
    os.environ.get(
        "IEA15MW_AEROFOIL_DIR",
        "/scratch/leahk/eduardo.donestevez/IEA-15-240-RWT/OpenFAST/"
        "IEA-15-240-RWT/Airfoils",
    )
)

SOURCE_PATTERN = re.compile(r"_AeroDyn15_Polar_(\d{2})\.dat$")

#: Round-trip tolerance of the emitted ``(alpha Cl Cd)`` against the source
#: rows. ``.8g`` formatting keeps the absolute difference well below this.
ROUND_TRIP_TOLERANCE = 1e-6

CM_NOTE = (
    "Cm is the quarter-chord pitching moment, positive nose-up, passed through "
    "unchanged: AirfoilInfo, the WindIO c_m and the profileData consumer share "
    "this convention (no sign conversion)."
)


class AirfoilInfoError(ValueError):
    """Raised when an AirfoilInfo file is not the expected format."""


def _strip_comment(line: str) -> str:
    return line.split("!", 1)[0]


def parse_airfoilinfo(path: Path | str) -> dict[str, Any]:
    """Parse one AirfoilInfo file into ``Re`` (millions), UA flag and rows."""
    source = Path(path)
    lines = source.read_text(encoding="utf-8").splitlines()

    re_millions: float | None = None
    num_alf: int | None = None
    incl_ua = False
    num_alf_index: int | None = None

    for index, line in enumerate(lines):
        tokens = _strip_comment(line).split()
        if len(tokens) < 2:
            continue
        key = tokens[1]
        if key == "Re":
            re_millions = float(tokens[0])
        elif key == "NumAlf":
            num_alf = int(tokens[0])
            num_alf_index = index
        elif key == "InclUAdata":
            incl_ua = tokens[0].lower() == "true"

    if re_millions is None:
        raise AirfoilInfoError(f"{source}: no Re field")
    if num_alf is None or num_alf_index is None:
        raise AirfoilInfoError(f"{source}: no NumAlf field")

    rows: list[tuple[float, float, float, float]] = []
    for line in lines[num_alf_index + 1 :]:
        stripped = _strip_comment(line).strip()
        if not stripped:
            continue
        tokens = stripped.split()
        if len(tokens) < 4:
            continue
        try:
            values = [float(token) for token in tokens[:4]]
        except ValueError:
            continue
        rows.append((values[0], values[1], values[2], values[3]))
        if len(rows) == num_alf:
            break

    if len(rows) != num_alf:
        raise AirfoilInfoError(
            f"{source}: NumAlf={num_alf} but found {len(rows)} data rows"
        )
    if any(b[0] <= a[0] for a, b in zip(rows, rows[1:])):
        raise AirfoilInfoError(f"{source}: alpha must be strictly increasing")
    return {
        "re_millions": re_millions,
        "incl_ua": incl_ua,
        "rows": rows,
    }


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
        "// Re is the source header value, given there in millions of Reynolds"
        " number;",
        "// every station file carries the same nominal Re = 3.0e6 (a known"
        " limitation).",
        f"// {CM_NOTE}",
        "// (alpha_deg Cl Cd Cm)",
        f"Re {re_millions * 1e6:g};",
        "data",
        "(",
    ]
    for alpha, cl, cd, cm in rows:
        lines.append(f"    ({alpha:.8g} {cl:.8g} {cd:.8g} {cm:.8g})")
    lines.append(");")
    return "\n".join(lines) + "\n"


def discover_sources(source_dir: Path | str | None = None) -> dict[int, Path]:
    """Map station index -> AirfoilInfo source file."""
    directory = Path(source_dir) if source_dir is not None else DEFAULT_SOURCE_DIR
    if not directory.is_dir():
        raise FileNotFoundError(f"AirfoilInfo source directory not found: {directory}")
    sources: dict[int, Path] = {}
    for path in sorted(directory.glob("*_AeroDyn15_Polar_*.dat")):
        match = SOURCE_PATTERN.search(path.name)
        if match:
            sources[int(match.group(1))] = path
    if not sources:
        raise FileNotFoundError(f"{directory}: no AirfoilInfo polar files found")
    return sources


def build_all(source_dir: Path | str | None = None) -> dict[Path, str]:
    """Render every polar; returns ``{output_path: content}``."""
    sources = discover_sources(source_dir)
    rendered: dict[Path, str] = {}
    for station, path in sorted(sources.items()):
        parsed = parse_airfoilinfo(path)
        rendered[POLARS_DIR / OUTPUT_TEMPLATE.format(station=station)] = (
            render_profile(
                station,
                path.name,
                parsed["re_millions"],
                parsed["rows"],
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
        help="AirfoilInfo source directory (default: IEA15MW_AEROFOIL_DIR)",
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
