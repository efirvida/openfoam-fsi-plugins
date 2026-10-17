# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for `tools/lit_search.py` (OpenAlex literature search).

The network is never touched: `urllib.request.urlopen` is replaced by a fake that
records the requested URL and returns a canned OpenAlex payload. What is pinned
is the part that can silently go wrong: reconstructing the abstract from
OpenAlex's inverted index, the query parameters sent, and the printed line format
that the agent workflow greps.

Run with:

    python3 -m pytest tools/tests -q
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import urllib.parse
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


lit_search = _load("lit_search", TOOLS / "lit_search.py")

WORK = {
    "title": "Actuator line with pressure drag",
    "publication_year": 2020,
    "cited_by_count": 12,
    "doi": "https://doi.org/10.1000/xyz",
    "authorships": [{"author": {"display_name": "Ada Lovelace"}}],
    "abstract_inverted_index": {"the": [0, 3], "blade": [1], "stalls": [2], "tip": [4]},
}


def _fake_urlopen(captured: list[str], results: list[dict]):
    def urlopen(url, timeout=None):
        captured.append(url)
        return io.StringIO(json.dumps({"results": results}))

    return urlopen


def test_abstract_is_rebuilt_in_position_order() -> None:
    assert lit_search.abstract_text(WORK["abstract_inverted_index"]) == "the blade stalls the tip"


def test_missing_abstract_is_an_empty_string() -> None:
    assert lit_search.abstract_text(None) == ""
    assert lit_search.abstract_text({}) == ""


def test_search_sends_query_date_filter_and_page_size(monkeypatch) -> None:
    captured: list[str] = []
    monkeypatch.setattr(lit_search.urllib.request, "urlopen", _fake_urlopen(captured, [WORK]))

    results = lit_search.search("actuator line", top=3, since=2015)

    assert results == [WORK]
    params = urllib.parse.parse_qs(urllib.parse.urlparse(captured[0]).query)
    assert params["search"] == ["actuator line"]
    assert params["per-page"] == ["3"]
    assert params["filter"][0].startswith("from_publication_date:2015-01-01")


def test_main_prints_year_citations_author_title_and_bare_doi(monkeypatch, capsys) -> None:
    monkeypatch.setattr(lit_search.urllib.request, "urlopen", _fake_urlopen([], [WORK]))
    monkeypatch.setattr(sys, "argv", ["lit_search.py", "actuator line"])

    lit_search.main()

    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "## actuator line"
    assert lines[1] == "2020 c=12   Ada Lovelace: Actuator line with pressure drag [10.1000/xyz]"
    assert len(lines) == 2


def test_main_truncates_abstract_and_tolerates_missing_author_and_doi(monkeypatch, capsys) -> None:
    bare = dict(WORK, authorships=[], doi=None)
    monkeypatch.setattr(lit_search.urllib.request, "urlopen", _fake_urlopen([], [bare]))
    monkeypatch.setattr(sys, "argv", ["lit_search.py", "q", "--abstract", "8"])

    lit_search.main()

    lines = capsys.readouterr().out.splitlines()
    assert "?: Actuator line with pressure drag []" in lines[1]
    assert lines[2] == "    the blad"
