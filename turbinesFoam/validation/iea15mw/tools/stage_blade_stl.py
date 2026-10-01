#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Stage the committed IEA 15 MW blade STL into a prepared run directory.

`run_iea15mw_case.sh --model asm-mesh` calls this to copy the committed STL to
``constant/triSurface/iea15mw_blade.stl`` (the case-relative path the
``fvOptions.ASM-MESH`` twin references as ``surfaceGeometry``), verifying the
sha256 against the committed ``geometry/metadata/iea15mw_blade.json``. Staging
keeps a restarted/relocated run self-contained: it resolves the surface inside
its own directory, and a mismatch aborts preparation instead of running with a
stale surface.

Usage:
    stage_blade_stl.py --run-dir DIR [--stl PATH] [--metadata PATH]

Exit codes:
    0  the STL was staged and its sha256 matches the metadata
    3  staging failure (missing source/metadata or sha256 mismatch)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STL = ROOT.parents[1] / "geometry" / "stl" / "iea15mw_blade.stl"
DEFAULT_METADATA = ROOT.parents[1] / "geometry" / "metadata" / "iea15mw_blade.json"
# Case-relative destination: what the ASM-mesh twin references.
STAGED_RELATIVE = Path("constant") / "triSurface" / "iea15mw_blade.stl"
EXIT_STAGING = 3


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--stl", type=Path, default=DEFAULT_STL)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    args = parser.parse_args(argv)

    if not args.stl.is_file():
        print(f"staging failure: blade STL not found: {args.stl}", file=sys.stderr)
        return EXIT_STAGING
    if not args.metadata.is_file():
        print(f"staging failure: metadata not found: {args.metadata}", file=sys.stderr)
        return EXIT_STAGING

    expected = json.loads(args.metadata.read_text(encoding="utf-8")).get("stl_sha256")
    actual = sha256_file(args.stl)
    if not expected or actual != expected:
        print(
            f"staging failure: sha256 mismatch ({actual} != {expected})",
            file=sys.stderr,
        )
        return EXIT_STAGING

    destination = args.run_dir / STAGED_RELATIVE
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.stl, destination)
    print(actual)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
