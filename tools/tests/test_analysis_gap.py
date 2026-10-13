# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the inline-analysis classifier in `tools/analysis_gap.py`.

The classifier is the heuristic part of the promotion detector, so it is the
part that must be pinned. It answers one question per bash command: "was this an
analysis computed inline instead of by a repository tool?" Getting that wrong in
either direction is costly — a false positive sends someone to write a tool that
is not needed, and a false negative hides exactly the duplication the detector
exists to find.

Run with:

    python3 -m pytest tools/tests -q
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
MODULE_PATH = TOOLS / "analysis_gap.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


analysis_gap = _load("analysis_gap", MODULE_PATH)


def test_inline_python_over_case_output_is_an_analysis_site() -> None:
    command = (
        "cd turbinesFoam/validation/phaseVI && python3 - <<'PY'\n"
        "import csv\n"
        "p='runs/alm-U7-coarse/postProcessing/turbines/0/turbine.csv'\n"
        "for r in csv.DictReader(open(p)): last=float(r['time'])\n"
        "print(last)\n"
        "PY"
    )

    signature = analysis_gap.classify(command)

    assert signature.inline is True
    assert signature.interpreter == "python3"
    assert "case-output" in signature.tags
    assert "turbine-csv" in signature.tags
    assert signature.areas == ("phaseVI",)
    assert signature.covered is False


def test_reading_a_file_without_an_interpreter_is_not_an_analysis_site() -> None:
    signature = analysis_gap.classify(
        "tail -1 runs/x/postProcessing/turbines/0/turbine.csv"
    )

    assert signature.inline is False
    assert analysis_gap.cluster_key(signature) is None


def test_version_control_and_queue_commands_are_not_analysis_sites() -> None:
    for command in ("git diff --stat", "squeue -j 11601372", "scancel 11601372"):
        signature = analysis_gap.classify(command)
        assert signature.inline is False, command


def test_experiment_reference_comparison_is_tagged_and_area_scoped() -> None:
    command = (
        "python3 -c \"import csv;"
        "rows=list(csv.DictReader(open('data/experiment/sequence_H_performance.csv')))\""
    )

    signature = analysis_gap.classify(command)

    assert "experiment-ref" in signature.tags
    assert signature.interpreter == "python3"


def test_pdf_page_rendering_is_detected() -> None:
    command = (
        "python3 -c \"import fitz;"
        "doc=fitz.open('/tmp/phasevi_29955.pdf');"
        "doc[71].get_pixmap(dpi=150).save('/tmp/p.png')\""
    )

    signature = analysis_gap.classify(command)

    assert signature.inline is True
    assert "pdf-page" in signature.tags


def test_a_command_already_calling_a_repository_tool_is_marked_covered() -> None:
    command = (
        "python3 turbinesFoam/validation/tools/case_state.py "
        "--mean-last 400 runs/alm-U7-coarse"
    )

    signature = analysis_gap.classify(command)

    assert signature.inline is False
    assert signature.covered is True


def test_awk_and_rscript_count_as_inline_interpreters() -> None:
    awk = analysis_gap.classify(
        "awk -F, 'NR>1{s+=$4} END{print s}' runs/x/postProcessing/turbines/0/turbine.csv"
    )
    rscript = analysis_gap.classify("Rscript -e 'x <- read.csv(\"runs/x/turbine.csv\")'")

    assert awk.interpreter == "awk"
    assert awk.inline is True
    assert rscript.interpreter == "Rscript"
    assert rscript.inline is True


def test_cluster_key_groups_by_tags_not_by_literal_text() -> None:
    first = analysis_gap.classify(
        "python3 -c \"import csv; csv.DictReader(open('runs/a/postProcessing/turbines/0/turbine.csv'))\""
    )
    second = analysis_gap.classify(
        "python3 -c \"import csv; csv.DictReader(open('runs/b/postProcessing/turbines/0/turbine.csv'))\""
    )

    assert analysis_gap.cluster_key(first) == analysis_gap.cluster_key(second)
    assert analysis_gap.cluster_key(first) is not None


def test_a_shape_already_answered_by_a_tool_is_not_a_candidate() -> None:
    # case_state.py exists to answer exactly this pair of tags.
    assert analysis_gap.covered_by(("case-output", "turbine-csv")) == "case_state.py"
    # One extra tag is enough to make it a genuine gap again: nothing owns PDFs.
    assert analysis_gap.covered_by(("case-output", "turbine-csv", "pdf-page")) is None
    assert analysis_gap.covered_by(("pdf-page", "pdf-render")) is None
    assert analysis_gap.covered_by(()) is None


def test_ranking_marks_a_solved_shape_as_covered() -> None:
    def site(command: str) -> object:
        signature = analysis_gap.classify(command)
        return analysis_gap.Site(command=command, signature=signature)

    solved = site("python3 -c \"open('runs/a/postProcessing/turbines/0/turbine.csv')\"")
    gap = site("python3 -c \"import fitz; fitz.open('/tmp/paper.pdf')[0].get_pixmap()\"")

    clusters = analysis_gap.rank([solved, solved, gap, gap], min_count=2)
    by_tags = {" ".join(c.tags): c for c in clusters}

    assert "case-output turbine-csv" in by_tags
    assert by_tags["case-output turbine-csv"].is_gap is False
    assert by_tags["case-output turbine-csv"].covered_by == "case_state.py"
    assert by_tags["pdf-page pdf-render"].is_gap is True
