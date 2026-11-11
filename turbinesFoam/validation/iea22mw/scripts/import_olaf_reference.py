# SPDX-License-Identifier: GPL-3.0-or-later
"""Append/refresh the OpenFAST reference blocks in the IEA-22 spanwise reference store.

Counterpart of ``iea15mw/scripts/import_olaf_reference.py`` (whose store format,
idempotence and exit codes it reuses unchanged): one block per ``--source``,

* ``olaf-fvw``    -- AeroDyn OLAF free-vortex wake (no Prandtl/Glauert tip loss),
* ``openfast-bem`` -- AeroDyn BEMT (Prandtl tip/hub loss, ``Wake_Mod=1``).

Each block carries ``alpha_deg``, ``cn`` and ``ct`` per AeroDyn node, read from the
``spanwise.csv`` that ``openfast_iea22.py extract`` writes next to a case's
``metrics.json``. ``r_over_R`` is the radius over R = 142 m (not projected).
The provenance note records the operating point and the wake size of the case;
an OLAF case that is not converged per ``metrics.json`` is refused unless
``--allow-unconverged`` is given (smoke runs are not references).

    import_olaf_reference.py CASEDIR --source olaf-fvw|openfast-bem [--store FILE] [--dry-run]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
IEA15_IMPORTER = PACKAGE.parent / "iea15mw" / "scripts" / "import_olaf_reference.py"
DEFAULT_STORE = PACKAGE / "analysis" / "spanwise-references.csv"
SOURCES = {
    "olaf-fvw": "OpenFAST v5.0.0 OLAF free-vortex-wake, no Prandtl/Glauert tip loss",
    "openfast-bem": "OpenFAST v5.0.0 AeroDyn BEMT (Wake_Mod=1), Prandtl tip and hub loss",
}
EXIT_UNCONVERGED = 5


def _importer():
    spec = importlib.util.spec_from_file_location("_iea15_olaf_importer_for_iea22", IEA15_IMPORTER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build_note(source: str, metrics: dict, case: dict) -> str:
    text = (f"{SOURCES[source]}; IEA-22-280-RWT standalone rigid rotor, V={metrics['U']:.6g} m/s, "
            f"{metrics['rpm']:.6g} rpm, pitch {metrics['pitch']:.6g} deg, tower {'on' if metrics['tower'] else 'off'}, "
            f"shaft tilt {'6 deg' if metrics['tilt'] else '0'}; {metrics['revolutions_averaged']:g} revolution(s) averaged")
    if case["wake"] == "olaf":
        text += f"; {case['nNWPanels']} near-wake panels ({case['wake_revolutions']:.1f} rev)"
    return text + "; Cn/Ct are AeroDyn normal/tangential-to-chord coefficients"


def refresh(case_dir: Path, source: str, store: Path, dry_run: bool = False, allow_unconverged: bool = False) -> int:
    metrics = json.loads((case_dir / "metrics.json").read_text())
    case = json.loads((case_dir / "case.json").read_text())
    expected = "olaf" if source == "olaf-fvw" else "bem"
    if case["wake"] != expected:
        raise ValueError(f"source {source} needs a {expected} case, {case_dir} is {case['wake']}")
    if not metrics["converged"] and not allow_unconverged:
        raise ValueError(f"{case_dir} is not converged (metrics.json); smoke runs are not references")
    module = _importer()
    module.SOURCE = source
    module.NOTE = build_note(source, metrics, case)
    return module.refresh_reference(case_dir / "spanwise.csv", store, dry_run=dry_run)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("case", type=Path)
    parser.add_argument("--source", choices=sorted(SOURCES), required=True)
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-unconverged", action="store_true")
    args = parser.parse_args(argv)
    module = _importer()
    try:
        count = refresh(args.case, args.source, args.store, args.dry_run, args.allow_unconverged)
    except module.OlafImportError as error:
        print(f"error: {error}", file=sys.stderr)
        return error.code
    except (ValueError, FileNotFoundError) as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_UNCONVERGED
    print(f"{args.source}: {'would write' if args.dry_run else 'wrote'} {count} rows to {args.store}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
