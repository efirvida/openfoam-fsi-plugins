#!/usr/bin/env python3
"""Compact literature search over OpenAlex.

Usage: lit_search.py QUERY [QUERY ...] [--top K] [--since YEAR] [--abstract N]

Prints one line per hit: year, citations, first author, title, DOI. With
--abstract N it appends the first N characters of the reconstructed abstract.
Output is bounded so it can be read without loading papers.
"""
import argparse
import json
import urllib.parse
import urllib.request


def abstract_text(inverted: dict | None) -> str:
    if not inverted:
        return ""
    words = {pos: word for word, positions in inverted.items() for pos in positions}
    return " ".join(words[i] for i in sorted(words))


def search(query: str, top: int, since: int) -> list[dict]:
    params = urllib.parse.urlencode({
        "search": query,
        "filter": f"from_publication_date:{since}-01-01,type:article|preprint|proceedings-article",
        "per-page": top,
        "select": "title,publication_year,cited_by_count,doi,authorships,abstract_inverted_index",
        "mailto": "efirvida@gmail.com",
    })
    with urllib.request.urlopen(f"https://api.openalex.org/works?{params}", timeout=30) as response:
        return json.load(response)["results"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("queries", nargs="+")
    parser.add_argument("--top", type=int, default=6)
    parser.add_argument("--since", type=int, default=2000)
    parser.add_argument("--abstract", type=int, default=0)
    args = parser.parse_args()
    for query in args.queries:
        print(f"## {query}")
        for work in search(query, args.top, args.since):
            authors = work["authorships"]
            first = authors[0]["author"]["display_name"] if authors else "?"
            doi = (work.get("doi") or "").replace("https://doi.org/", "")
            print(f"{work['publication_year']} c={work['cited_by_count']:<4} {first}: {work['title']} [{doi}]")
            if args.abstract:
                print("    " + abstract_text(work.get("abstract_inverted_index"))[: args.abstract])


if __name__ == "__main__":
    main()
