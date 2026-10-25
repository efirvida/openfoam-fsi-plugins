#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Find the analyses that keep being recomputed inline instead of by a tool.

The problem this detects
------------------------
Over the recorded sessions of this repository, 862 of 2250 `bash` calls invoked
an interpreter, and 348 of those touched project data. Each one was written from
scratch, stayed in the agent's context for the rest of the session, and often
re-typed constants that already live in `data/experiment/`. That is a token cost
and, worse, a reproducibility hazard.

The detector answers one question from evidence rather than from a hunch: which
analysis shapes recur often enough that they should exist as a repository tool?

What it does and does not do
----------------------------
It **detects and ranks**. It never generates analysis code. Auto-writing an
analysis for a scientific workflow is exactly the failure mode being fixed here:
a generated snippet cannot know that `cp` is defined against the NREL report by
`scripts/comparePhaseVI.py`, and a plausible-looking wrong metric is worse than
an obvious manual step. Promotion stays a reviewed act; this tool makes the
candidate list visible and cheap to act on.

How it classifies
-----------------
A command is a *promotion candidate site* when it runs an inline program
(`python3 -c`, a heredoc, `awk`, `Rscript -e`, or a scratch script under `/tmp/`)
against data belonging to this project. Classification is heuristic and
deliberately transparent: every candidate carries the evidence tags that matched,
so a wrong call can be seen and corrected rather than trusted.

Usage
-----
    python3 tools/analysis_gap.py                    # current repository
    python3 tools/analysis_gap.py --min-count 5
    python3 tools/analysis_gap.py --json
    python3 tools/analysis_gap.py --project-dir /path/to/of-plugins

Exit codes
----------
    0  report produced
    1  no Pi session transcript found for this project
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# The scripts in this directory are run directly (`python3 tools/<name>.py`),
# which puts this directory on sys.path only for that invocation. Making it
# explicit keeps a sibling import working from tests and from an imported
# module alike.
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Resolved at runtime by the bootstrap above and covered by tools/tests; the
# static analyzer cannot follow a runtime sys.path mutation.
import pi_sessions  # noqa: E402  # pyright: ignore[reportMissingImports]

#: Interpreters whose presence in a `bash` call means a program was written inline.
INTERPRETER_PATTERNS: tuple[tuple[str, str], ...] = (
    ("python3", r"\bpython3(?:\.\d+)?\b"),
    ("python", r"\bpython\b"),
    ("awk", r"(?<![\w.-])awk\b"),
    ("Rscript", r"\bRscript\b"),
    ("perl", r"(?<![\w.-])perl\b"),
    ("ruby", r"\bruby\b"),
)

#: Flags that mean the program arrived inline rather than as a committed script.
INLINE_PROGRAM_PATTERNS: tuple[str, ...] = (
    r"(?:^|\s)-c(?:\s|$)",
    r"(?:^|\s)-e(?:\s|$)",
    r"<<\s*-?\s*[\"']?\w+",
)

#: Evidence tags, matched against the command text. Order defines report order.
EVIDENCE_TAGS: tuple[tuple[str, str], ...] = (
    ("case-output", r"postProcessing"),
    ("turbine-csv", r"turbine\.csv"),
    ("element-csv", r"\.element\w*\.csv"),
    ("blade-surface", r"bladeSurface"),
    ("experiment-ref", r"data/experiment"),
    ("run-json", r"run\.json"),
    ("slurm-queue", r"\b(?:squeue|sacct|sinfo|scancel|sbatch)\b"),
    ("slurm-log", r"slurm[-_]?\d+\.out|\b\d{7,}\.out\b"),
    ("solver-log", r"\blog\.\w+|\bfoamRun\b|CourantNo|residuals"),
    ("pdf-page", r"\.pdf\b"),
    ("pdf-render", r"\bfitz\b|get_pixmap|pdftoppm|pdftocairo|PyMuPDF"),
    ("val-doc", r"(?:\bodd/|\bopenspec/)"),
)

#: A scratch script is one written to a temporary location rather than committed.
SCRATCH_SCRIPT_PATTERN = r"(?:^|\s)/tmp/[\w./-]+\.(?:py|sh|R)"

#: Repository analysis entry points. A command that calls one of these is covered.
KNOWN_TOOLS: tuple[str, ...] = (
    "case_state.py",
    "run_diff.py",
    "comparePhaseVI.py",
    "compare_spanwise.py",
    "compareNacelle.py",
    "generate_case.py",
    "case_config.py",
    "element_data.py",
    "stage_blade_stl.py",
    "extractExperimentalData.py",
    "extractUAE6Reference.py",
    "proxyRotationalAugmentation.py",
    "plotPhaseVIDiagnosis.py",
    "makeElementData.py",
    "make_olaf_reference.py",
)

#: Which evidence tags each repository tool already answers. A cluster whose tags
#: are all inside one tool's set is not a candidate: it is a solved shape. Keep
#: these narrow — over-claiming coverage hides the gap the detector exists to
#: find. Adding a tool means adding one line here.
TOOL_COVERAGE: dict[str, frozenset[str]] = {
    "case_state.py": frozenset({"case-output", "turbine-csv"}),
    "run_diff.py": frozenset({"case-output", "turbine-csv"}),
    "compare_spanwise.py": frozenset({"case-output", "turbine-csv", "blade-surface"}),
    "comparePhaseVI.py": frozenset({"experiment-ref", "turbine-csv"}),
    "compareNacelle.py": frozenset({"experiment-ref", "case-output"}),
}

#: `validation/<area>` identifies which campaign a command belongs to.
AREA_PATTERN = r"validation/([\w-]+)"

#: Commands that are never analysis, checked only once an interpreter was found.
#: Shell builtins (``cd``, ``ls``, ``echo``, ...) are deliberately absent: in this
#: repository the dominant shape is ``cd <case-dir> && python3 - <<'PY'``, so a
#: prefix match on ``cd`` would discard most real sites.
EXCLUDED_COMMAND_PATTERN = r"^\s*(?:git|gh|glab|squeue|scancel|sinfo|sacct|sbatch)\b"


@dataclass(frozen=True)
class Signature:
    """What one bash command turned out to be, with the evidence attached."""

    inline: bool
    interpreter: str | None = None
    tags: tuple[str, ...] = ()
    areas: tuple[str, ...] = ()
    covered: bool = False
    scratch: bool = False


@dataclass
class Site:
    """One observed inline-analysis invocation."""

    command: str
    signature: Signature
    session: str = ""
    timestamp: str = ""


@dataclass
class Cluster:
    """A recurring analysis shape, ranked as a promotion candidate."""

    key: tuple
    count: int = 0
    areas: set[str] = field(default_factory=set)
    sessions: set[str] = field(default_factory=set)
    first: str = ""
    last: str = ""
    examples: list[str] = field(default_factory=list)
    covered_by: str | None = None

    @property
    def is_gap(self) -> bool:
        """True when no existing repository tool answers this shape."""
        return self.covered_by is None

    @property
    def interpreter(self) -> str:
        return self.key[0]

    @property
    def tags(self) -> tuple[str, ...]:
        return self.key[1]


def _first_match(patterns: tuple[str, ...], text: str) -> str | None:
    for pattern in patterns:
        if re.search(pattern, text):
            return pattern
    return None


def classify(command: str) -> Signature:
    """Classify one bash command. Heuristic, and transparent about its evidence."""
    tags = tuple(name for name, pattern in EVIDENCE_TAGS if re.search(pattern, command))
    areas = tuple(sorted(set(re.findall(AREA_PATTERN, command))))

    if any(tool in command for tool in KNOWN_TOOLS):
        return Signature(inline=False, tags=tags, areas=areas, covered=True)

    interpreter = None
    for name, pattern in INTERPRETER_PATTERNS:
        if re.search(pattern, command):
            interpreter = name
            break

    if interpreter is None:
        return Signature(inline=False, tags=tags, areas=areas)

    if re.match(EXCLUDED_COMMAND_PATTERN, command, re.IGNORECASE):
        return Signature(inline=False, interpreter=interpreter, tags=tags, areas=areas)

    scratch = bool(re.search(SCRATCH_SCRIPT_PATTERN, command))
    inline_program = bool(_first_match(INLINE_PROGRAM_PATTERNS, command))
    # `awk` carries its program as the first argument, so it is inline by nature.
    inline = inline_program or interpreter == "awk" or scratch

    return Signature(
        inline=inline,
        interpreter=interpreter,
        tags=tags,
        areas=areas,
        scratch=scratch,
    )


def cluster_key(signature: Signature) -> tuple | None:
    """Return the grouping key for a site, or ``None`` when it is not a candidate.

    Keying on the matched evidence rather than on the command text is what makes
    the detector useful: two snippets reading the same source with different code
    are the same missing tool.
    """
    if not signature.inline or not signature.tags:
        return None
    return (signature.interpreter, tuple(sorted(signature.tags)))


def collect(paths: list[str]) -> tuple[list[Site], int, int]:
    """Return candidate sites plus the raw inline and covered counts."""
    sites: list[Site] = []
    inline_seen = 0
    covered_seen = 0

    for path in paths:
        session = Path(path).name[:16]
        for record in pi_sessions.iter_records(path):
            if record.get("type") != "message":
                continue
            message = record.get("message") or {}
            if message.get("role") != "assistant":
                continue
            timestamp = record.get("timestamp") or ""
            for block in message.get("content") or []:
                if not isinstance(block, dict) or block.get("type") != "toolCall":
                    continue
                if block.get("name") != "bash":
                    continue
                arguments = block.get("arguments") or {}
                command = arguments.get("command") or ""
                if not command:
                    continue
                signature = classify(command)
                if signature.covered:
                    covered_seen += 1
                    continue
                if not signature.inline:
                    continue
                inline_seen += 1
                if cluster_key(signature) is None:
                    continue
                sites.append(
                    Site(command=command, signature=signature, session=session, timestamp=timestamp)
                )

    return sites, inline_seen, covered_seen


def covered_by(tags: tuple[str, ...]) -> str | None:
    """Return the repository tool that already answers this shape, if any."""
    wanted = set(tags)
    for tool, covered in TOOL_COVERAGE.items():
        if wanted and wanted <= covered:
            return tool
    return None


def rank(sites: list[Site], min_count: int) -> list[Cluster]:
    """Group sites into clusters, keeping only recurring ones, most frequent first."""
    clusters: dict[tuple, Cluster] = {}
    for site in sites:
        key = cluster_key(site.signature)
        if key is None:
            continue
        cluster = clusters.setdefault(key, Cluster(key=key))
        cluster.count += 1
        cluster.areas.update(site.signature.areas)
        cluster.sessions.add(site.session)
        if not cluster.first or site.timestamp < cluster.first:
            cluster.first = site.timestamp
        if site.timestamp > cluster.last:
            cluster.last = site.timestamp
        cluster.examples.append(" ".join(site.command.split()))

    ranked = [c for c in clusters.values() if c.count >= min_count]
    for cluster in ranked:
        cluster.examples = sorted(set(cluster.examples), key=len)[:3]
        cluster.covered_by = covered_by(cluster.tags)
    return sorted(ranked, key=lambda c: (-c.count, c.tags))


def render_text(clusters: list[Cluster], inline_seen: int, covered_seen: int) -> str:
    """Render the promotion-candidate report."""
    out = [
        "Inline analysis sites: "
        f"{inline_seen} inline interpreter calls, {covered_seen} already calling a "
        "repository tool"
    ]
    if not clusters:
        out.append("")
        out.append("No recurring analysis shape reached the reporting threshold.")
        return "\n".join(out)

    out.append("")
    gaps = [c for c in clusters if c.is_gap]
    solved = [c for c in clusters if not c.is_gap]

    if not gaps:
        out.append("No uncovered shape reached the reporting threshold: every "
                   "recurring shape is already answered by a repository tool.")
    else:
        out.append("Promotion candidates (a candidate is a missing tool, not a "
                   "missing patch):")
    for cluster in gaps:
        out.append("")
        out.append(_render_cluster(cluster))

    if solved:
        out.append("")
        out.append("Already answered by an existing tool (no action):")
        for cluster in solved:
            areas = ", ".join(sorted(cluster.areas)) or "repo-wide"
            out.append(
                f"  x{cluster.count:<4} {cluster.interpreter:<8} "
                f"{cluster.covered_by:<20} [{areas}] {' '.join(cluster.tags)}"
            )

    if gaps:
        out.append("")
        out.append(
            "Promotion is a reviewed act: a tool's metric definitions must come "
            "from the reference (see scripts/comparePhaseVI.py), never from the "
            "snippet being replaced. After adding a tool, add its line to "
            "TOOL_COVERAGE in this script."
        )
    return "\n".join(out)


def _render_cluster(cluster: Cluster) -> str:
    """Render one promotion candidate."""
    areas = ", ".join(sorted(cluster.areas)) or "repo-wide"
    lines = [
        f"  x{cluster.count:<4} {cluster.interpreter:<8} [{areas}] "
        f"{' '.join(cluster.tags)}",
        f"        sessions={len(cluster.sessions)}  "
        f"{cluster.first[:10]} .. {cluster.last[:10]}",
    ]
    lines.extend(f"        {example[:150]}" for example in cluster.examples)
    return "\n".join(lines)


def render_json(clusters: list[Cluster], inline_seen: int, covered_seen: int) -> str:
    """Render a machine-readable projection of the report."""
    return json.dumps(
        {
            "inlineSites": inline_seen,
            "coveredSites": covered_seen,
            "clusters": [
                {
                    "interpreter": cluster.interpreter,
                    "tags": list(cluster.tags),
                    "areas": sorted(cluster.areas),
                    "count": cluster.count,
                    "sessions": len(cluster.sessions),
                    "coveredBy": cluster.covered_by,
                    "first": cluster.first,
                    "last": cluster.last,
                    "examples": cluster.examples,
                }
                for cluster in clusters
            ],
        },
        indent=2,
        sort_keys=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Find analyses that are recomputed inline instead of by a tool.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--project-dir",
        default=str(Path(__file__).resolve().parents[1]),
        help="project directory whose transcripts to read (default: this repository)",
    )
    parser.add_argument(
        "--session",
        default=None,
        help="only transcripts whose name starts with this prefix",
    )
    parser.add_argument(
        "--min-count",
        type=int,
        default=3,
        help="only report shapes seen at least this many times (default: 3)",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    paths = pi_sessions.find_transcripts(args.project_dir, prefix=args.session)
    if not paths:
        print(
            f"no Pi session transcript found for {args.project_dir} under "
            f"{pi_sessions.sessions_root()}",
            file=sys.stderr,
        )
        return 1

    sites, inline_seen, covered_seen = collect(paths)
    clusters = rank(sites, max(args.min_count, 1))
    if args.json:
        print(render_json(clusters, inline_seen, covered_seen))
    else:
        print(render_text(clusters, inline_seen, covered_seen))
    return 0


if __name__ == "__main__":
    sys.exit(main())
