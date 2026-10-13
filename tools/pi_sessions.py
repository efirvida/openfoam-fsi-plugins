#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read Pi's session transcripts for one project.

Pi writes one JSONL transcript per session under
``$PI_CODING_AGENT_DIR/sessions/``. The directory name encodes the working
directory with slashes replaced by dashes, and each transcript's first record
repeats it as ``cwd``. That layout is the only place where the agent's own
behaviour — token cost, inline analysis, tool usage — is recorded, so more than
one tool needs to read it.

This module exists so that reading it is written once. It knows the layout; it
does not decide what the records mean.

Consumers:
- `tools/session_cost.py` — what a session costs.
- `tools/analysis_gap.py` — which analyses keep being re-derived inline.
"""

from __future__ import annotations

import glob
import json
import os
from collections.abc import Iterator

#: Set by Pi to the agent directory; ``~/.pi/agent`` when unset.
AGENT_DIR_ENV = "PI_CODING_AGENT_DIR"


def sessions_root() -> str:
    """Return the directory holding this machine's session transcripts."""
    base = os.environ.get(AGENT_DIR_ENV)
    if base:
        return os.path.join(base, "sessions")
    return os.path.expanduser("~/.pi/agent/sessions")


def encoded_dir_name(project_dir: str) -> str:
    """Return the session directory name Pi derives from ``project_dir``."""
    return "--" + os.path.realpath(project_dir).strip("/").replace("/", "-") + "--"


def read_cwd(path: str) -> str | None:
    """Return the project directory recorded in a transcript's session header."""
    for record in iter_records(path):
        if record.get("type") == "session":
            return record.get("cwd")
    return None


def find_transcripts(project_dir: str, prefix: str | None = None) -> list[str]:
    """Return the transcripts belonging to ``project_dir``, oldest first.

    Matching prefers the ``cwd`` recorded inside each transcript, so a moved or
    renamed project directory is still found by content. When no header carries
    a readable ``cwd``, the encoded directory name is used as a fallback.
    """
    project = os.path.realpath(project_dir)
    candidates = sorted(glob.glob(os.path.join(sessions_root(), "*", "*.jsonl")))

    matched = [path for path in candidates if read_cwd(path) == project]
    if not matched:
        matched = sorted(
            glob.glob(os.path.join(sessions_root(), encoded_dir_name(project), "*.jsonl"))
        )

    if prefix:
        matched = [path for path in matched if os.path.basename(path).startswith(prefix)]
    return matched


def iter_records(path: str) -> Iterator[dict]:
    """Yield each parseable JSONL record, skipping malformed lines silently.

    A transcript is appended to while a session runs, so a torn final line is
    normal rather than an error.
    """
    with open(path, errors="replace") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if isinstance(record, dict):
                yield record


def iter_messages(path: str) -> Iterator[dict]:
    """Yield only the message records of a transcript."""
    for record in iter_records(path):
        if record.get("type") == "message":
            message = record.get("message")
            if isinstance(message, dict):
                yield message


def iter_tool_calls(path: str) -> Iterator[tuple[str, dict]]:
    """Yield ``(tool_name, arguments)`` for every tool call, in order."""
    for message in iter_messages(path):
        if message.get("role") != "assistant":
            continue
        for block in message.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "toolCall":
                arguments = block.get("arguments")
                yield block.get("name") or "?", arguments if isinstance(arguments, dict) else {}


def iter_assistant_usage(path: str) -> Iterator[dict]:
    """Yield the ``usage`` object of every assistant message that reported one."""
    for message in iter_messages(path):
        if message.get("role") != "assistant":
            continue
        usage = message.get("usage")
        if isinstance(usage, dict) and usage.get("totalTokens"):
            yield usage
