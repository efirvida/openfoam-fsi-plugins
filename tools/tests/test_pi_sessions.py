# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for `tools/pi_sessions.py`, the shared Pi transcript reader.

Both `tools/session_cost.py` and `tools/analysis_gap.py` depend on this module,
and the part they depend on is the fragile part: Pi's on-disk session layout.
These tests pin that layout so a Pi upgrade that moves it fails here instead of
silently reporting zero.

Run with:

    python3 -m pytest tools/tests -q
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
MODULE_PATH = TOOLS / "pi_sessions.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


pi_sessions = _load("pi_sessions", MODULE_PATH)


@pytest.fixture()
def agent_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An isolated agent directory wired up through the real env variable."""
    root = tmp_path / "agent"
    (root / "sessions").mkdir(parents=True)
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(root))
    return root


def _transcript(path: Path, cwd: str | None, lines: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        if cwd is not None:
            handle.write(json.dumps({"type": "session", "version": 3, "cwd": cwd}) + "\n")
        for line in lines:
            handle.write(json.dumps(line) + "\n")
    return path


def _assistant(text: str, calls: list[tuple[str, dict]] | None = None, usage: dict | None = None):
    content: list[dict] = [{"type": "text", "text": text}]
    for index, (name, arguments) in enumerate(calls or []):
        content.append(
            {"type": "toolCall", "id": f"c{index}", "name": name, "arguments": arguments}
        )
    message: dict = {"role": "assistant", "content": content, "model": "m"}
    if usage is not None:
        message["usage"] = usage
    return {"type": "message", "message": message}


def test_sessions_root_honors_the_agent_directory(agent_dir: Path) -> None:
    assert pi_sessions.sessions_root() == str(agent_dir / "sessions")


def test_find_transcripts_matches_on_the_recorded_cwd(agent_dir: Path) -> None:
    wanted = _transcript(
        agent_dir / "sessions" / "--a--" / "2026-01-01T00-00-00-000Z_x.jsonl",
        "/a",
        [_assistant("hi")],
    )
    _transcript(
        agent_dir / "sessions" / "--b--" / "2026-01-01T00-00-01-000Z_y.jsonl",
        "/b",
        [_assistant("other")],
    )

    assert pi_sessions.find_transcripts("/a") == [str(wanted)]


def test_find_transcripts_falls_back_to_the_encoded_directory_name(agent_dir: Path) -> None:
    # No session header: the cwd can only be recovered from the directory name.
    encoded = agent_dir / "sessions" / "--scratch-me-tmp-of-plugins--"
    wanted = _transcript(encoded / "2026-01-01T00-00-00-000Z_z.jsonl", None, [_assistant("hi")])

    assert pi_sessions.find_transcripts("/scratch/me/tmp/of-plugins") == [str(wanted)]


def test_find_transcripts_returns_empty_when_nothing_matches(agent_dir: Path) -> None:
    _transcript(
        agent_dir / "sessions" / "--a--" / "2026-01-01T00-00-00-000Z_x.jsonl",
        "/a",
        [_assistant("hi")],
    )

    assert pi_sessions.find_transcripts("/elsewhere") == []


def test_find_transcripts_filters_by_name_prefix(agent_dir: Path) -> None:
    _transcript(
        agent_dir / "sessions" / "--a--" / "2026-01-01T00-00-00-000Z_x.jsonl",
        "/a",
        [_assistant("hi")],
    )
    later = _transcript(
        agent_dir / "sessions" / "--a--" / "2026-02-02T00-00-00-000Z_y.jsonl",
        "/a",
        [_assistant("hi")],
    )

    assert pi_sessions.find_transcripts("/a", prefix="2026-02-02") == [str(later)]


def test_iter_records_skips_malformed_lines(tmp_path: Path) -> None:
    path = tmp_path / "t.jsonl"
    path.write_text('{"type": "session"}\nnot json\n{"type": "message"}\n')

    assert [r["type"] for r in pi_sessions.iter_records(path)] == ["session", "message"]


def test_iter_tool_calls_yields_name_and_arguments_in_order(tmp_path: Path) -> None:
    path = _transcript(
        tmp_path / "t.jsonl",
        "/a",
        [
            _assistant("one", [("bash", {"command": "ls"}), ("read", {"path": "x"})]),
            _assistant("two", [("bash", {"command": "pwd"})]),
        ],
    )

    assert list(pi_sessions.iter_tool_calls(path)) == [
        ("bash", {"command": "ls"}),
        ("read", {"path": "x"}),
        ("bash", {"command": "pwd"}),
    ]


def test_iter_assistant_usage_skips_calls_without_totals(tmp_path: Path) -> None:
    path = _transcript(
        tmp_path / "t.jsonl",
        "/a",
        [
            _assistant("no usage"),
            _assistant("zero", usage={"totalTokens": 0}),
            _assistant("real", usage={"totalTokens": 10, "input": 7}),
        ],
    )

    usages = list(pi_sessions.iter_assistant_usage(path))

    assert [u["input"] for u in usages] == [7]
