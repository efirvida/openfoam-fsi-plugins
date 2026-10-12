#!/usr/bin/env python3
"""Rank the PDFs of a directory by how often they mention given terms.

Usage: find_in_articles.py DIR TERM [TERM ...] [--pages N] [--top K]

Counts case-insensitive occurrences of each TERM in the first N pages of every
PDF, so "which article formulates X" is answered without opening each file.
"""
import argparse
import logging
import re
import sys
from pathlib import Path

from pypdf import PdfReader

logging.getLogger("pypdf").setLevel(logging.ERROR)


def count_terms(path: Path, terms: list[str], pages: int) -> dict[str, int]:
    counts = dict.fromkeys(terms, 0)
    try:
        reader = PdfReader(str(path))
        for page in reader.pages[:pages]:
            text = (page.extract_text() or "").lower()
            for term in terms:
                counts[term] += len(re.findall(term.lower(), text))
    except Exception as error:  # unreadable or encrypted file: report zeros
        print(f"warning: {path.name}: {error}", file=sys.stderr)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("terms", nargs="+")
    parser.add_argument("--pages", type=int, default=30)
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()
    rows = []
    for pdf in sorted(args.directory.glob("*.pdf")):
        counts = count_terms(pdf, args.terms, args.pages)
        rows.append((sum(counts.values()), counts, pdf.name))
    for total, counts, name in sorted(rows, key=lambda r: -r[0])[: args.top]:
        if total:
            print(f"{total:5d}  {dict(counts)}  {name}")


if __name__ == "__main__":
    main()
