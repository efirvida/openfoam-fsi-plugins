"""Tests for the OpenFAST case builders and the FLOWUnsteady Fig. A4 reader."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR.parent / "validation" / "iea15mw" / "scripts"))
sys.path.insert(0, str(TESTS_DIR.parent / "validation" / "phaseVI" / "scripts"))

import openfast_gust  # noqa: E402
import openfast_sweep  # noqa: E402

MEHR_PDF = TESTS_DIR.parent / "articles" / "Wind Energy - 2024 - Mehr - Interactional Aerodynamics Analysis of a Multirotor Energy Kite.pdf"


def test_set_value_replaces_only_the_named_key():
    text = "7.5   RotSpeed   - rpm\n0.0   BlPitch(1)  - deg\n0.0   BlPitch(10) - other\n"
    out = openfast_sweep.set_value(text, "BlPitch(1)", "3.0")
    assert "3.0   BlPitch(1)" in out and "0.0   BlPitch(10)" in out
    with pytest.raises(KeyError):
        openfast_sweep.set_value(text, "Missing", "1")


def test_merge_keeps_template_layout_and_takes_values():
    template = "1  NewKey  - only in template\n5.0  RotSpeed  - rpm\n"
    other = "9.9  RotSpeed  - rpm\n"
    merged = openfast_gust.merge_fst(template, other)
    assert "NewKey" in merged and "9.9  RotSpeed" in merged


def test_eog_is_a_mexican_hat_around_the_hub_speed():
    v = 10.66
    assert openfast_gust.eog_speed(v, -1.0) == v and openfast_gust.eog_speed(v, 11.0) == v
    samples = [openfast_gust.eog_speed(v, t / 10) for t in range(0, 106)]
    assert min(samples) < v < max(samples)
    assert abs(min(samples) - 9.59) < 0.05 and abs(max(samples) - 13.61) < 0.05


@pytest.mark.skipif(not MEHR_PDF.exists(), reason="Mehr 2024 PDF not in articles/")
def test_figA4_reader_recovers_axes_and_bars():
    import digitizeFlowUnsteadyFigA4 as fig
    from pdfminer.high_level import extract_pages
    page = next(extract_pages(str(MEHR_PDF), page_numbers=[fig.PAGE_INDEX]))
    objects = list(fig._walk(page))
    curve, exp = fig.read_panel(objects, "CQ")
    assert len(exp) == 20
    sim = fig.interp(curve, 5.37)
    assert 0.068 < sim < 0.072
    ct_curve, _ = fig.read_panel(objects, "CT")
    assert 0.45 < fig.interp(ct_curve, 5.37) < 0.47
