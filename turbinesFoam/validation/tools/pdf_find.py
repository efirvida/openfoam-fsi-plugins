#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Find text in a PDF and print the matching lines with their page number.

Why this exists
---------------
Reference papers and reports live in `articles/` and are consulted for definitions
(test sequences, tables, equations). Extracting their text through an inline snippet was
repeated dozens of times (`tools/analysis_gap.py`, class `pdf-page`); this reader does it
once. It reads text only: scanned PDFs with no text layer return nothing and are reported
as such, never guessed.

Usage
-----
    python3 validation/tools/pdf_find.py articles/29955.pdf "Sequence [A-Z]\\b" --context 1
    python3 validation/tools/pdf_find.py articles/29955.pdf --page 31      # whole page text

Exit codes
----------
    0  at least one match (or the page was printed)
    1  file unreadable, page out of range, or no text layer
    2  no match
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from pypdf import PdfReader


def page_texts(path: Path) -> list[str]:
    return [(page.extract_text() or "") for page in PdfReader(str(path)).pages]


def find(texts: list[str], pattern: str, context: int = 0, ignore_case: bool = True) -> list[tuple[int, int, list[str]]]:
    """(page, line number, lines incl. context) for every matching line; pages are 1-based."""
    regex = re.compile(pattern, re.IGNORECASE if ignore_case else 0)
    hits = []
    for number, text in enumerate(texts, start=1):
        lines = text.splitlines()
        for index, line in enumerate(lines):
            if regex.search(line):
                lo, hi = max(index - context, 0), min(index + context + 1, len(lines))
                hits.append((number, index + 1, lines[lo:hi]))
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("pdf", type=Path)
    parser.add_argument("pattern", nargs="?", help="regular expression, case-insensitive by default")
    parser.add_argument("--context", type=int, default=0, help="lines of context around a match")
    parser.add_argument("--case-sensitive", action="store_true")
    parser.add_argument("--page", type=int, help="print the text of this 1-based page and exit")
    parser.add_argument("--max-hits", type=int, default=60)
    args = parser.parse_args(argv)
    try:
        texts = page_texts(args.pdf)
    except Exception as err:  # pypdf raises several unrelated types on a bad file
        print(f"ERROR: cannot read {args.pdf}: {err}", file=sys.stderr)
        return 1
    if not any(t.strip() for t in texts):
        print(f"ERROR: {args.pdf} has no text layer (scanned?)", file=sys.stderr)
        return 1
    if args.page is not None:
        if not 1 <= args.page <= len(texts):
            print(f"ERROR: page {args.page} outside 1..{len(texts)}", file=sys.stderr)
            return 1
        print(texts[args.page - 1])
        return 0
    if not args.pattern:
        parser.error("a pattern or --page is required")
    hits = find(texts, args.pattern, args.context, not args.case_sensitive)
    for page, line, block in hits[: args.max_hits]:
        print(f"p.{page}:{line}")
        for text in block:
            print(f"    {text}")
    if len(hits) > args.max_hits:
        print(f"... {len(hits) - args.max_hits} more hits (raise --max-hits)")
    return 0 if hits else 2


if __name__ == "__main__":
    raise SystemExit(main())
