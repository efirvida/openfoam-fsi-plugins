#!/usr/bin/env python3
"""Dump the text of PDFs to a scratch directory so they can be grepped.

Usage: pdf_to_text.py OUTDIR PDF [PDF ...]

Writes OUTDIR/<n>.txt per PDF (page breaks marked '=== page N ===') and prints
the mapping, so articles are read with grep/sed instead of loaded whole.
"""
import logging
import sys
from pathlib import Path

from pypdf import PdfReader

logging.getLogger("pypdf").setLevel(logging.ERROR)


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    outdir = Path(sys.argv[1])
    outdir.mkdir(parents=True, exist_ok=True)
    for index, name in enumerate(sys.argv[2:], 1):
        reader = PdfReader(name)
        target = outdir / f"{index}.txt"
        with target.open("w") as handle:
            for number, page in enumerate(reader.pages, 1):
                handle.write(f"\n=== page {number} ===\n{page.extract_text() or ''}\n")
        print(f"{target}  <-  {name}  ({len(reader.pages)} pages)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
