from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from .git_client import prepare_branch_context, prepare_phase_execution_context
from .logging_utils import log_error, log_info, log_multiline


def run_gemini(
    prompt: str,
    *,
    repo: str,
    issue: int,
    phase: str,
    branch_override: str | None = None,
    issue_data: dict[str, Any] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run Gemini CLI headlessly and capture output in the configured target repository."""
    context = (
        prepare_phase_execution_context(repo, phase, issue, issue_data=issue_data)
        if branch_override is None
        else prepare_branch_context(repo, branch=branch_override, branch_log_label="Resolved explicit target branch", issue_data=issue_data)
    )

    log_info(f"Gemini target repository loaded: {context.local_path}")
    log_info(f"Gemini target branch loaded: {context.branch}")

    # Use the requested "yolo" and "non-interactive" style
    # Always prepend local directory context and force the codebase_investigator tool
    full_prompt = f"@. @codebase_investigator\n\n{prompt}"

    command = [
        "gemini",
        "-p", full_prompt,
        "--debug",
        "--approval-mode", "yolo",
        "-o", "json"
    ]

    log_info(f"Launching Gemini headless run in {context.local_path}")
    log_info(f"Command: {' '.join(command)}")
    result = subprocess.run(
        command,
        cwd=context.local_path,
        text=True,
        capture_output=True,
        timeout=1200,
    )
    
    if result.returncode != 0:
        log_error(f"Gemini execution failed with exit code: {result.returncode}")
        if result.stdout:
            log_multiline("Gemini stdout", result.stdout)
        if result.stderr:
            log_multiline("Gemini stderr", result.stderr)
    else:
        log_info(f"Gemini execution succeeded (exit code: {result.returncode})")
        if result.stdout:
            log_multiline("Gemini stdout", result.stdout)
            
    return result

def extract_gemini_response(stdout: str) -> str:
    """Extract the response text from Gemini JSON output."""
    try:
        # First try: Find the first '{' and the last '}'
        start = stdout.find("{")
        end = stdout.rfind("}")
        
        if start != -1 and end != -1 and end > start:
            json_str = stdout[start:end+1]
            try:
                data = json.loads(json_str)
                if "response" in data:
                    return str(data["response"]).strip()
            except json.JSONDecodeError:
                pass # Fall through to line-by-line approach

        # Second try: Original line-by-line fallback
        lines = stdout.strip().splitlines()
        json_str = ""
        for i in range(len(lines)):
            if lines[i].strip().startswith("{"):
                json_str = "\n".join(lines[i:])
                break
        
        if not json_str:
            return ""
            
        data = json.loads(json_str)
        return str(data.get("response") or "").strip()
    except (json.JSONDecodeError, KeyError, IndexError):
        return ""

def extract_json_from_markdown(text: str) -> str:
    """Extract JSON block from markdown text."""
    marker = "```json"
    if marker in text:
        start = text.find(marker) + len(marker)
        end = text.find("```", start)
        if end != -1:
            return text[start:end].strip()
    return text.strip()

def run_gemini_comment_phase(
    prompt: str,
    *,
    repo: str,
    issue: int,
    phase: str,
    session_scope: str = "", # Gemini CLI handles sessions differently, ignoring for now
    issue_data: dict[str, Any] | None = None,
) -> str:
    """Run Gemini and return the assistant reply text."""
    log_info("Requesting comment response from Gemini")
    result = run_gemini(prompt, repo=repo, issue=issue, phase=phase, issue_data=issue_data)
    if result.returncode != 0:
        raise SystemExit(f"Gemini execution failed with exit code: {result.returncode}")

    response = extract_gemini_response(result.stdout)
    if not response:
        raise SystemExit("Gemini returned no response.")
    
    log_info(f"Assistant response extracted ({len(response)} chars)")
    return response

def run_gemini_json_phase(
    prompt: str,
    *,
    repo: str,
    issue: int,
    phase: str,
    session_scope: str = "",
    issue_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run Gemini and parse the final assistant reply as JSON."""
    log_info("Requesting JSON response from Gemini")
    content = run_gemini_comment_phase(prompt, repo=repo, issue=issue, phase=phase, issue_data=issue_data)
    log_info("Parsing JSON from assistant reply")
    json_content = extract_json_from_markdown(content)
    try:
        return json.loads(json_content)
    except json.JSONDecodeError as exc:
        log_error("Assistant reply was not valid JSON")
        print(content)
        raise SystemExit(f"Gemini did not return valid JSON: {exc}") from exc


