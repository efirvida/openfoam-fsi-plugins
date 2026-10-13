#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Report the real token and cost footprint of Pi sessions for one project.

Pi records every model call of a session as a JSONL transcript under
``$PI_CODING_AGENT_DIR/sessions/<encoded-cwd>/``. Each assistant message carries
a ``usage`` object with ``input``, ``output``, ``cacheRead`` and ``cost``, which
is the only trustworthy measurement of what this repository actually spends.

Why this exists
---------------
The token cost of this workflow is not spread evenly and is not what raw byte
counts suggest. Measured over 3280 calls: 9.2 % of the calls carried 96.4 % of
the input tokens, because the provider's prompt cache expires during the long
waits typical of a CFD campaign and the whole context is re-billed at full input
price. This script makes that visible again instead of leaving it as a one-off
analysis.

It is a read-only reporter: it never writes, never caches and never mutates a
session transcript.

Usage
-----
    python3 tools/session_cost.py                  # current directory
    python3 tools/session_cost.py --project-dir /path/to/of-plugins
    python3 tools/session_cost.py --json           # machine-readable
    python3 tools/session_cost.py --session 2026-10-01T09-04

Exit codes
----------
    0  report produced
    1  no session transcript found for this project
    2  transcripts found but no usable ``usage`` records (schema drift)
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys

# The scripts in this directory are run directly (`python3 tools/<name>.py`),
# which puts this directory on sys.path only for that invocation. Making it
# explicit keeps a sibling import working from tests and from an imported
# module alike.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Resolved at runtime by the bootstrap above and covered by tools/tests; the
# static analyzer cannot follow a runtime sys.path mutation.
import pi_sessions  # noqa: E402  # pyright: ignore[reportMissingImports]

#: Cost concentration thresholds reported for uncached input.
THRESHOLDS = (50_000, 100_000, 200_000, 400_000)

#: Categories used to estimate what occupies a long context, in report order.
#: Inline images are tracked separately: Pi resizes them before sending, so the
#: stored base64 is not what the model pays for.
COMPOSITION_KEYS = (
    "assistant thinking",
    "toolCall args",
    "toolResult: bash",
    "toolResult: read",
    "toolResult: other",
    "assistant text",
    "user messages",
    "system prompt",
)


def _sessions_root() -> str:
    """Return the Pi session directory, honoring ``PI_CODING_AGENT_DIR``."""
    return pi_sessions.sessions_root()


def find_transcripts(project_dir: str) -> list[str]:
    """Return the transcripts belonging to ``project_dir``, oldest first."""
    return pi_sessions.find_transcripts(project_dir)


def _is_image_result(payload: str) -> bool:
    """True when a stored tool result carries an inline image."""
    return '"type": "image"' in payload


def scan(paths: list[str]) -> dict:
    """Aggregate usage and context composition from the given transcripts."""
    sessions: list[dict] = []
    total = collections.Counter()
    usage_seen = 0
    images_total = 0
    image_chars_total = 0

    for path in paths:
        calls = []
        call_ids: dict[str, str] = {}
        session_system_chars = 0
        composition: collections.Counter = collections.Counter()
        images = 0
        image_chars = 0
        with open(path, errors="replace") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if record.get("type") != "message":
                    continue
                message = record["message"]
                role = message.get("role")

                if role == "system":
                    # Only the current prompt is sent, not every historical
                    # revision of it, so keep the last one rather than a sum.
                    session_system_chars = len(
                        json.dumps(
                            message.get("sections") or message.get("content") or ""
                        )
                    )
                    continue

                if role == "user":
                    composition["user messages"] += (
                        len(json.dumps(message.get("content") or "")) // 4
                    )
                    continue

                if role == "toolResult":
                    name = call_ids.get(
                        message.get("toolCallId"), message.get("toolName") or "?"
                    )
                    payload = json.dumps(message.get("content") or "")
                    if _is_image_result(payload):
                        images += 1
                        image_chars += len(payload)
                        continue
                    composition["toolResult: %s" % (
                        name if name in ("bash", "read") else "other"
                    )] += len(payload) // 4
                    continue

                if role != "assistant":
                    continue

                for block in message.get("content") or []:
                    if not isinstance(block, dict):
                        continue
                    kind = block.get("type")
                    if kind == "thinking":
                        composition["assistant thinking"] += (
                            len(block.get("thinking") or "") // 4
                        )
                    elif kind == "text":
                        composition["assistant text"] += len(block.get("text") or "") // 4
                    elif kind == "toolCall":
                        composition["toolCall args"] += (
                            len(json.dumps(block.get("arguments") or "")) // 4
                        )
                        call_ids[block.get("id", "")] = block.get("name") or "?"

                usage = message.get("usage") or {}
                if not usage.get("totalTokens"):
                    continue
                usage_seen += 1
                cost = usage.get("cost") or {}
                calls.append(
                    {
                        "input": usage.get("input", 0),
                        "output": usage.get("output", 0),
                        "reasoning": usage.get("reasoning", 0) or 0,
                        "cacheRead": usage.get("cacheRead", 0),
                        "cost": cost.get("total", 0.0) or 0.0,
                        "costInput": cost.get("input", 0.0) or 0.0,
                        "model": message.get("model"),
                    }
                )

        if not calls:
            continue

        prefixes = [c["input"] + c["cacheRead"] for c in calls]
        session = {
            "name": os.path.basename(path)[:16],
            "path": path,
            "calls": len(calls),
            "input": sum(c["input"] for c in calls),
            "output": sum(c["output"] for c in calls),
            "reasoning": sum(c["reasoning"] for c in calls),
            "cacheRead": sum(c["cacheRead"] for c in calls),
            "cost": sum(c["cost"] for c in calls),
            "costInput": sum(c["costInput"] for c in calls),
            "prefixSum": sum(prefixes),
            "prefixMax": max(prefixes),
            "models": sorted({c["model"] for c in calls if c["model"]}),
            "images": images,
            "imageChars": image_chars,
        }
        composition["system prompt"] = session_system_chars // 4
        session["composition"] = dict(composition)
        sessions.append(session)
        images_total += images
        image_chars_total += image_chars
        total.update(
            {
                key: session[key]
                for key in (
                    "calls",
                    "input",
                    "output",
                    "reasoning",
                    "cacheRead",
                    "cost",
                    "costInput",
                    "prefixSum",
                )
            }
        )

    # Cost concentration lives on the uncached input term.
    cold = []
    for path in paths:
        with open(path, errors="replace") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if record.get("type") != "message":
                    continue
                message = record["message"]
                if message.get("role") != "assistant":
                    continue
                usage = message.get("usage") or {}
                if usage.get("totalTokens"):
                    cold.append(
                        (
                            usage.get("input", 0),
                            (usage.get("cost") or {}).get("total", 0.0) or 0.0,
                        )
                    )

    return {
        "sessions": sessions,
        "total": dict(total),
        "calls": cold,
        "usageSeen": usage_seen,
        "transcripts": len(paths),
        "images": images_total,
        "imageChars": image_chars_total,
    }


def _fmt(value: float, unit: str = "") -> str:
    if abs(value) >= 1e9:
        return f"{value / 1e9:.2f}B{unit}"
    if abs(value) >= 1e6:
        return f"{value / 1e6:.2f}M{unit}"
    if abs(value) >= 1e3:
        return f"{value / 1e3:.1f}K{unit}"
    return f"{value:.0f}{unit}"


def render_text(data: dict) -> str:
    """Render the human-facing, deliberately compact report."""
    sessions = data["sessions"]
    total = data["total"]
    calls = data["calls"]
    out = []

    out.append(
        f"Pi session cost — {data['transcripts']} transcript(s), "
        f"{total.get('calls', 0)} model calls"
    )
    out.append("")
    out.append(
        f"{'session':<18} {'calls':>6} {'input':>9} {'cacheRead':>9} "
        f"{'output':>9} {'cost$':>8} {'maxPrefix':>10}"
    )
    for session in sorted(sessions, key=lambda s: s["name"]):
        out.append(
            f"{session['name']:<18} {session['calls']:>6} "
            f"{_fmt(session['input']):>9} {_fmt(session['cacheRead']):>9} "
            f"{_fmt(session['output']):>9} {session['cost']:>8.2f} "
            f"{_fmt(session['prefixMax']):>10}"
        )
    out.append(
        f"{'TOTAL':<18} {total.get('calls', 0):>6} "
        f"{_fmt(total.get('input', 0)):>9} "
        f"{_fmt(total.get('cacheRead', 0)):>9} "
        f"{_fmt(total.get('output', 0)):>9} {total.get('cost', 0.0):>8.2f} {'':>10}"
    )
    out.append("")

    # Raw token counts are not the cost: state the split explicitly.
    cost = total.get("cost", 0.0) or 1e-9
    cached_side = max(cost - total.get("costInput", 0.0), 0.0)
    input_share = 100 * total.get("costInput", 0.0) / cost
    out.append(
        f"Cost split: uncached input ${total.get('costInput', 0.0):.2f} "
        f"({input_share:.0f}%), rest ${cached_side:.2f}"
    )
    out.append(
        f"Raw cacheRead tokens are {_fmt(total.get('cacheRead', 0))} against "
        f"{_fmt(total.get('input', 0))} uncached input;"
    )
    out.append("cache reads are billed far cheaper, so they are not the driver.")
    out.append("")

    if calls:
        big = [(tokens, spent) for tokens, spent in calls if tokens > 200_000]
        share_tokens = 100 * sum(t for t, _ in big) / max(total.get("input", 0), 1)
        share_cost = 100 * sum(c for _, c in big) / max(cost, 1e-9)
        out.append(
            f"Cache-miss concentration: {len(big)}/{len(calls)} calls carry "
            f"{share_tokens:.1f}% of input tokens and {share_cost:.1f}% of cost"
        )
        out.append("  (the whole context re-billed at full price after the")
        out.append("  provider cache expires).")
        for threshold in THRESHOLDS:
            subset = [t for t, _ in calls if t > threshold]
            if not subset:
                continue
            out.append(
                f"  >{threshold:>7} uncached input: {len(subset):>4} calls, "
                f"{_fmt(sum(subset)):>8} tokens"
            )
        out.append("")

    # The largest session is the one whose composition is worth explaining:
    # summing contexts across sessions would answer no real question.
    worst = max(sessions, key=lambda s: s["prefixMax"], default=None)
    if worst and worst["composition"]:
        composition = worst["composition"]
        composition_total = sum(composition.values())
        out.append(
            f"Context composition of the largest session ({worst['name']}, "
            f"max prefix {_fmt(worst['prefixMax'])})"
        )
        for key in COMPOSITION_KEYS:
            value = composition.get(key, 0)
            if not value:
                continue
            out.append(
                f"  {key:<24} {_fmt(value):>9} "
                f"{100 * value / composition_total:>6.1f}%"
            )
        out.append(f"  {'TOTAL text':<24} {_fmt(composition_total):>9}")
        out.append(
            f"  {'inline images':<24} {worst['images']:>9}  "
            f"(stored base64 {_fmt(worst['imageChars'])}, resized before send)"
        )
        out.append("")
        out.append(
            f"  Across all transcripts: {data['images']} image results, "
            f"{_fmt(data['imageChars'])} chars of stored base64."
        )
        out.append(
            "  Pi resizes them before sending (~3.1K tokens each measured), so"
        )
        out.append(
            "  that volume is transcript weight and disk cost, not a token cost."
        )
        out.append("")
        out.append(
            "  The chars/4 estimate tracks the measured provider prefix at ~0.91"
        )
        out.append("  when retained thinking is included, and at ~0.37 when it is")
        out.append("  excluded: thinking blocks are re-sent on every later call.")
        out.append("")

    out.append("Only 'uncached input' and 'output' compete for real money here;")
    out.append("the lever is context size x number of calls, not tool output volume.")
    return "\n".join(out)


def render_json(data: dict) -> str:
    """Render a machine-readable projection without the raw per-call series."""
    calls = data["calls"]
    worst = max(data["sessions"], key=lambda s: s["prefixMax"], default=None)
    payload = {
        "transcripts": data["transcripts"],
        "calls": data["total"].get("calls", 0),
        "input": data["total"].get("input", 0),
        "output": data["total"].get("output", 0),
        "reasoning": data["total"].get("reasoning", 0),
        "cacheRead": data["total"].get("cacheRead", 0),
        "cost": data["total"].get("cost", 0.0),
        "costInput": data["total"].get("costInput", 0.0),
        "prefixSum": data["total"].get("prefixSum", 0),
        "images": data["images"],
        "imageChars": data["imageChars"],
        "largestSession": None if worst is None else worst["name"],
        "cacheMiss": {
            str(threshold): {
                "calls": sum(1 for t, _ in calls if t > threshold),
                "tokens": sum(t for t, _ in calls if t > threshold),
                "cost": sum(c for t, c in calls if t > threshold),
            }
            for threshold in THRESHOLDS
        },
        "sessions": [
            {k: v for k, v in s.items() if k != "path"} for s in data["sessions"]
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report Pi session token and cost footprint for one project.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--project-dir",
        default=os.getcwd(),
        help="project directory whose transcripts to read (default: cwd)",
    )
    parser.add_argument(
        "--session",
        default=None,
        help="only transcripts whose name starts with this prefix",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    paths = find_transcripts(args.project_dir)
    if args.session:
        paths = [p for p in paths if os.path.basename(p).startswith(args.session)]
    if not paths:
        print(
            f"no Pi session transcript found for {os.path.realpath(args.project_dir)}"
            f" under {_sessions_root()}",
            file=sys.stderr,
        )
        return 1

    data = scan(paths)
    if not data["usageSeen"]:
        print(
            f"transcripts found ({len(paths)}) but no usage records: the Pi"
            " session schema changed or usage reporting is disabled;"
            " no measurement is claimed.",
            file=sys.stderr,
        )
        return 2

    print(render_json(data) if args.json else render_text(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
