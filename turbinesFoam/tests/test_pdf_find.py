# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for `validation/tools/pdf_find.py` (text search in the reference PDFs)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1]
TOOL = PACKAGE / "validation" / "tools" / "pdf_find.py"
REPORT = PACKAGE / "articles" / "29955.pdf"


@pytest.fixture(scope="module")
def pdf_find():
    spec = importlib.util.spec_from_file_location("pdf_find", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["pdf_find"] = module
    spec.loader.exec_module(module)
    return module


def test_find_reports_page_line_and_context(pdf_find):
    texts = ["intro\nSequence S: no probes\nend", "nothing here", "tail\nsequence H baseline"]
    hits = pdf_find.find(texts, r"sequence [HS]\b", context=1)
    assert [(p, n) for p, n, _ in hits] == [(1, 2), (3, 2)]
    assert hits[0][2] == ["intro", "Sequence S: no probes", "end"]


def test_find_is_case_sensitive_on_request(pdf_find):
    assert pdf_find.find(["Sequence S"], "sequence", ignore_case=False) == []
    assert len(pdf_find.find(["Sequence S"], "sequence")) == 1


def test_unreadable_file_exits_one(pdf_find, tmp_path):
    bad = tmp_path / "not-a.pdf"
    bad.write_text("plain text, not a PDF")
    assert pdf_find.main([str(bad), "x"]) == 1
    assert pdf_find.main([str(tmp_path / "absent.pdf"), "x"]) == 1


@pytest.mark.skipif(not REPORT.is_file(), reason="reference report not present in this checkout")
def test_finds_the_sequence_definitions_in_the_nrel_report(pdf_find, capsys):
    assert pdf_find.main([str(REPORT), r"Wake Flow Visualization", "--max-hits", "3"]) == 0
    assert "p." in capsys.readouterr().out
    assert pdf_find.main([str(REPORT), "zzzz-no-such-text-zzzz"]) == 2
