# SPDX-License-Identifier: GPL-3.0-or-later
"""Append/refresh the OLAF free-vortex-wake block in the reference store.

``analysis/spanwise-references.csv`` is the committed long-format reference
store (``source,quantity,r_over_R_or_radius_m,value,unit,note``) that every
spanwise comparison reads. The campaign's non-circular tip reference is the
OpenFAST **OLAF** free-vortex wake, which resolves the wake with Lagrangian
vortex filaments and therefore carries **no Prandtl/Glauert tip loss** -- unlike
the BEM path, whose tip loss is the circular ansatz we are trying to avoid.

The OLAF spanwise profile lives only in the gitignored ``reference/`` directory
(OpenFAST outputs), so it must be transformed by this committed, re-runnable
producer rather than transcribed by hand. This script appends (or refreshes)
one ``olaf-fvw`` block with three quantities per node:

* ``alpha_deg`` (unit ``deg``) from the source ``Alpha`` column,
* ``cn`` (unit ``-``) from ``Cn``,
* ``ct`` (unit ``-``) from ``Ct``.

The ``r_over_R`` coordinate is written from the source ``r_over_R`` column and
stays dimensionless, matching the ``ccblade-bem`` convention. The store column
is named ``r_over_R_or_radius_m`` because it carries *either* a dimensionless
r/R *or* a radius in metres depending on the source, and the plot scripts rely
on knowing which.

The induction and ``Vrel`` columns are deliberately **not** imported: the store
stays minimal, and the source CSV keeps them.

Idempotent: running twice does not duplicate rows, and every row of any other
source is preserved byte for byte. The script is a small importer, not a general
store writer, and fails loudly with a distinct exit code when the source CSV is
absent or a required column is missing.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path

#: Campaign root (``turbinesFoam/validation/iea15mw``); the defaults below are
#: resolved against it so the script can be run from anywhere.
CASE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_CSV = CASE_ROOT / "reference" / "olaf-rated" / "spanwise_olaf.csv"
DEFAULT_STORE = CASE_ROOT / "analysis" / "spanwise-references.csv"

#: Source tag written into the store for every imported row.
SOURCE = "olaf-fvw"

#: Store field order, kept identical to the existing file.
REFERENCE_HEADER = (
    "source",
    "quantity",
    "r_over_R_or_radius_m",
    "value",
    "unit",
    "note",
)

#: (store quantity, source column, store unit), in the order written per node.
QUANTITIES = (
    ("alpha_deg", "Alpha", "deg"),
    ("cn", "Cn", "-"),
    ("ct", "Ct", "-"),
)

#: Source columns this importer needs; absent ones fail loudly.
REQUIRED_COLUMNS = ("node", "r_over_R", "Alpha", "Cn", "Ct")

#: Provenance note repeated on every imported row.
NOTE = (
    "OpenFAST v5.0.0 OLAF free-vortex-wake, no Prandtl/Glauert tip loss; "
    "IEA-15-240-RWT-Monopile rated point V=10.659 m/s, 7.518 rpm; converged "
    "15-revolution run; derived from reference/olaf-rated/spanwise_olaf.csv "
    "(job 11605824); Cn/Ct are AeroDyn normal/tangential-to-chord coefficients"
)

EXIT_SOURCE_MISSING = 2
EXIT_COLUMN_MISSING = 3
EXIT_STORE_HEADER = 4


class OlafImportError(Exception):
    """A typed failure carrying the process exit code to use."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def _format_value(value: float) -> str:
    """Render a float with ten significant digits (round-trips the source)."""
    return f"{value:.10g}"


def read_source(source_csv: Path) -> list[dict[str, str]]:
    """Read and validate the OLAF spanwise CSV; never invent a column."""
    if not source_csv.exists():
        raise OlafImportError(
            EXIT_SOURCE_MISSING,
            f"source CSV not found: {source_csv}",
        )
    with source_csv.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        fieldnames = reader.fieldnames
        if fieldnames is None:
            raise OlafImportError(
                EXIT_COLUMN_MISSING,
                f"source CSV has no header row: {source_csv}",
            )
        missing = [name for name in REQUIRED_COLUMNS if name not in fieldnames]
        if missing:
            raise OlafImportError(
                EXIT_COLUMN_MISSING,
                f"source CSV {source_csv} is missing required column(s): "
                + ", ".join(missing),
            )
        return list(reader)


def build_rows(source_rows: list[dict[str, str]]) -> list[list[str]]:
    """Map source stations to ``source,quantity,x,value,unit,note`` rows."""
    rows: list[list[str]] = []
    for source_row in source_rows:
        x = _format_value(float(source_row["r_over_R"]))
        for quantity, column, unit in QUANTITIES:
            rows.append(
                [
                    SOURCE,
                    quantity,
                    x,
                    _format_value(float(source_row[column])),
                    unit,
                    NOTE,
                ]
            )
    return rows


def _format_line(fields: list[str], newline: str) -> str:
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator=newline).writerow(fields)
    return buffer.getvalue()


def _source_of(line: str) -> str | None:
    """First CSV field of a raw store line, or ``None`` if it has no fields."""
    stripped = line.rstrip("\r\n")
    if not stripped:
        return None
    try:
        row = next(csv.reader([stripped]))
    except csv.Error:
        return None
    return row[0] if row else None


def detect_newline(store: Path) -> str:
    """Match the store's existing line ending (the real file uses CRLF)."""
    if store.exists() and b"\r\n" in store.read_bytes():
        return "\r\n"
    return "\n"


def _check_header(header_line: str) -> None:
    fields = next(csv.reader([header_line]))
    if tuple(fields) != REFERENCE_HEADER:
        raise OlafImportError(
            EXIT_STORE_HEADER,
            f"store header is not {','.join(REFERENCE_HEADER)}: "
            f"{header_line.strip()!r}",
        )


def _render(store: Path, block: list[list[str]], newline: str) -> str:
    """Header + every retained raw line + the new block, end to end."""
    if store.exists():
        # newline="" keeps CRLF endings on the retained raw lines (the real
        # store is CRLF); universal-newline mode would rewrite every line.
        with store.open(encoding="utf-8", newline="") as stream:
            text = stream.read()
        lines = text.splitlines(keepends=True)
    else:
        lines = []
    if lines:
        header = lines[0]
        _check_header(header)
        # Drop any previous block; keep every foreign line exactly as written.
        kept = [line for line in lines[1:] if _source_of(line) != SOURCE]
    else:
        header = _format_line(list(REFERENCE_HEADER), newline)
        kept = []
    if kept and not kept[-1].endswith(("\n", "\r")):
        kept[-1] += newline
    body = "".join(kept) + "".join(_format_line(row, newline) for row in block)
    return header + body


def refresh_reference(source_csv: Path, store: Path, dry_run: bool = False) -> int:
    """Append/refresh the ``olaf-fvw`` block; return the number of rows written."""
    block = build_rows(read_source(source_csv))
    if dry_run:
        return len(block)
    newline = detect_newline(store)
    text = _render(store, block, newline)
    store.parent.mkdir(parents=True, exist_ok=True)
    with store.open("w", encoding="utf-8", newline="") as stream:
        stream.write(text)
    return len(block)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Append/refresh the 'olaf-fvw' block in analysis/spanwise-references.csv "
            "from the OpenFAST OLAF spanwise CSV."
        )
    )
    parser.add_argument("--source-csv", type=Path, default=DEFAULT_SOURCE_CSV)
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would be written and touch no file",
    )
    args = parser.parse_args(argv)

    try:
        count = refresh_reference(args.source_csv, args.store, dry_run=args.dry_run)
    except OlafImportError as error:
        print(f"error: {error}", file=sys.stderr)
        return error.code

    if args.dry_run:
        print(f"{SOURCE}: would write {count} rows to {args.store}")
    else:
        print(f"{SOURCE}: wrote {count} rows to {args.store}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
