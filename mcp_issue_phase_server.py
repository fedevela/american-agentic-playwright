#!/usr/bin/env python3
"""MCP stdio server exposing phase-prompt generation tools."""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any

# Ensure local package imports resolve no matter the process working directory.
REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from trigger_workflow.config import DEFAULT_REPO, LABEL_PHASE_MAP, PHASE_DISPLAY_NAME_MAP, PHASE_LABEL_METADATA
from trigger_workflow.router import build_phase_prompt_for_issue, label_for_phase_id

SERVER_NAME = "openhands-swarm-phase-prompt"
SERVER_VERSION = "0.1.0"
PROTOCOL_VERSION = "2024-11-05"
TOOL_NAME = "get_phase_prompt"
LIST_PHASE_LABELS_TOOL_NAME = "list_phase_labels"


def write_message(payload: dict[str, Any]) -> None:
    """Write a single JSON-RPC payload over MCP stdio framing."""
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    sys.stdout.buffer.write(header + body)
    sys.stdout.buffer.flush()


def read_message() -> dict[str, Any] | None:
    """Read one framed JSON-RPC message from stdin."""
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        text = line.decode("ascii", errors="replace").strip()
        if ":" not in text:
            continue
        key, value = text.split(":", 1)
        headers[key.strip().lower()] = value.strip()

    length_text = headers.get("content-length")
    if not length_text:
        return None
    length = int(length_text)
    body = sys.stdin.buffer.read(length)
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


def jsonrpc_ok(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    """Build a JSON-RPC success response."""
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def jsonrpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    """Build a JSON-RPC error response."""
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _resolve_label(phase: str | None, label: str | None) -> str | None:
    """Resolve canonical label from optional phase/label inputs."""
    resolved_label = label
    if phase:
        phase_label = label_for_phase_id(phase)
        if resolved_label and resolved_label != phase_label:
            raise ValueError(
                f"Conflicting inputs: label '{resolved_label}' does not match phase '{phase}' "
                f"(expected '{phase_label}')."
            )
        resolved_label = phase_label
    return resolved_label


def _tool_get_phase_prompt(arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute the get_phase_prompt tool."""
    issue = arguments.get("issue")
    if not isinstance(issue, int):
        raise ValueError("`issue` is required and must be an integer.")

    phase = arguments.get("phase")
    if phase is not None and not isinstance(phase, str):
        raise ValueError("`phase` must be a string when provided.")

    label = arguments.get("label")
    if label is not None and not isinstance(label, str):
        raise ValueError("`label` must be a string when provided.")

    repo = arguments.get("repo", DEFAULT_REPO)
    if repo is not None and not isinstance(repo, str):
        raise ValueError("`repo` must be a string when provided.")

    resolved_label = _resolve_label(phase=phase, label=label)
    prompt = build_phase_prompt_for_issue(
        label=resolved_label,
        issue=issue,
        repo=repo,
        manual=True,
    )

    structured = {
        "issue": issue,
        "phase": phase,
        "label": resolved_label,
        "repo": repo,
        "prompt": prompt,
    }
    return {
        "content": [{"type": "text", "text": prompt}],
        "structuredContent": structured,
        "isError": False,
    }


def _tool_list_phase_labels() -> dict[str, Any]:
    """Return canonical phase labels and their metadata for LLM discovery."""
    labels: list[dict[str, str]] = []
    for label_name, phase_id in sorted(LABEL_PHASE_MAP.items(), key=lambda item: item[1]):
        metadata = PHASE_LABEL_METADATA.get(label_name) or {}
        labels.append(
            {
                "label": label_name,
                "phase": phase_id,
                "phase_name": PHASE_DISPLAY_NAME_MAP.get(phase_id, phase_id),
                "description": str(metadata.get("description") or ""),
            }
        )
    return {
        "content": [
            {
                "type": "text",
                "text": "\n".join(
                    f"- {item['label']} ({item['phase']} / {item['phase_name']}): {item['description']}"
                    for item in labels
                ),
            }
        ],
        "structuredContent": {"labels": labels},
        "isError": False,
    }


def _tools_list_result() -> dict[str, Any]:
    """Return MCP tool registration metadata."""
    return {
        "tools": [
            {
                "name": TOOL_NAME,
                "description": "Build the exact OpenHands phase prompt for a GitHub issue/phase without running workflows.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "issue": {"type": "integer", "description": "GitHub issue number."},
                        "phase": {
                            "type": "string",
                            "description": "Canonical phase id: 1, 2a, 2b, 2c, 3, 4, 5, 6, 7, 8, or 9.",
                        },
                        "label": {"type": "string", "description": "Canonical GitHub phase label such as phase:tiferet."},
                        "repo": {"type": "string", "description": "Repository in owner/repo form."},
                    },
                    "required": ["issue"],
                    "additionalProperties": False,
                },
            },
            {
                "name": LIST_PHASE_LABELS_TOOL_NAME,
                "description": "List canonical phase labels with phase ids, phase names, and descriptions.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
        ]
    }


def handle_request(message: dict[str, Any]) -> dict[str, Any] | None:
    """Dispatch supported JSON-RPC methods."""
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}

    if method == "initialize":
        return jsonrpc_ok(
            request_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        )

    if method == "notifications/initialized":
        return None

    if method == "ping":
        return jsonrpc_ok(request_id, {})

    if method == "tools/list":
        return jsonrpc_ok(request_id, _tools_list_result())

    if method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments") or {}
        if tool_name == LIST_PHASE_LABELS_TOOL_NAME:
            return jsonrpc_ok(request_id, _tool_list_phase_labels())
        if tool_name != TOOL_NAME:
            return jsonrpc_error(request_id, -32602, f"Unknown tool '{tool_name}'.")
        if not isinstance(arguments, dict):
            return jsonrpc_error(request_id, -32602, "`arguments` must be an object.")
        try:
            result = _tool_get_phase_prompt(arguments)
        except Exception as exc:  # noqa: BLE001
            return jsonrpc_ok(
                request_id,
                {
                    "content": [{"type": "text", "text": f"Tool error: {exc}"}],
                    "isError": True,
                },
            )
        return jsonrpc_ok(request_id, result)

    if request_id is None:
        return None
    return jsonrpc_error(request_id, -32601, f"Method '{method}' not found.")


def main() -> int:
    """Run MCP stdio loop."""
    try:
        while True:
            message = read_message()
            if message is None:
                return 0
            response = handle_request(message)
            if response is not None:
                write_message(response)
    except KeyboardInterrupt:
        return 0
    except Exception:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
