#!/usr/bin/env python3
"""Deterministic Codex CLI stand-in used by adapter subprocess tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time


DEFAULT_SESSION_ID = "11111111-1111-4111-8111-111111111111"


def _option_value(arguments: list[str], option: str) -> str | None:
    try:
        return arguments[arguments.index(option) + 1]
    except (ValueError, IndexError):
        return None


def main() -> int:
    arguments = sys.argv[1:]
    if arguments == ["--version"]:
        print("codex-cli 99.0.0-fake")
        return 0

    mode = os.environ.get("FAKE_CODEX_MODE", "success")
    if mode == "never_read_stdin":
        time.sleep(2)
        return 0
    prompt = sys.stdin.read()
    if mode == "leader_exits_child_holds_pipes":
        marker_path = os.environ["FAKE_CODEX_DESCENDANT_MARKER"]
        child_code = (
            "import pathlib, sys, time; "
            "time.sleep(0.4); "
            "pathlib.Path(sys.argv[1]).write_text('descendant survived', encoding='utf-8')"
        )
        subprocess.Popen([sys.executable, "-c", child_code, marker_path])
        return 0
    record_path = os.environ.get("FAKE_CODEX_RECORD")
    if record_path:
        record = {
            "argv": arguments,
            "cwd": os.getcwd(),
            "prompt": prompt,
            "codex_home": os.environ.get("CODEX_HOME"),
        }
        Path(record_path).write_text(json.dumps(record), encoding="utf-8")

    resume_index = arguments.index("resume") if "resume" in arguments else -1
    requested_session = arguments[-2] if resume_index >= 0 else None
    session_id = requested_session or os.environ.get("FAKE_CODEX_SESSION_ID", DEFAULT_SESSION_ID)
    if mode == "changed_session":
        session_id = "22222222-2222-4222-8222-222222222222"

    if mode != "no_session":
        print(json.dumps({"type": "thread.started", "thread_id": session_id}), flush=True)

    if mode == "wait_after_started":
        release_path = Path(os.environ["FAKE_CODEX_RELEASE"])
        deadline = time.monotonic() + 5
        while not release_path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)

    if mode == "hang_no_newline":
        sys.stdout.write('{"type":"item.started"')
        sys.stdout.flush()
        time.sleep(30)
        return 0

    if mode == "malformed_event":
        print("not-json", flush=True)
    if mode == "error":
        print(json.dumps({"type": "error", "message": "fake failure"}), flush=True)
    elif mode == "turn_failed":
        print(json.dumps({"type": "turn.failed", "error": {"message": "fake failure"}}), flush=True)
    elif mode != "missing_completed":
        print(json.dumps({"type": "turn.completed", "usage": {}}), flush=True)

    print("fake stderr", file=sys.stderr, flush=True)
    output_path = _option_value(arguments, "--output-last-message")
    if output_path and mode != "missing_output":
        response = "" if mode == "empty_output" else os.environ.get("FAKE_CODEX_RESPONSE", "final response")
        Path(output_path).write_text(response, encoding="utf-8")

    return 7 if mode == "nonzero" else 0


if __name__ == "__main__":
    raise SystemExit(main())
