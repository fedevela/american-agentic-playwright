from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from .config import (
    IMPLEMENTATION_PHASES,
)
from .logging_utils import log_error, log_info, log_multiline
from .runner_utils import (
    MAX_VALIDATION_ATTEMPTS,
    MAX_VALIDATION_RETRIES,
    VALIDATION_COMMAND_CONTRACT,
    build_single_retry_fix_task,
    finalize_phase_delivery as utils_finalize_phase_delivery,
    prepare_branch_context,
    prepare_phase_execution_context,
    run_phase_tests,
    summarize_test_output,
)

VALIDATION_PHASES = set(IMPLEMENTATION_PHASES)

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
    # Prepend '@. ' to ensure Gemini reads the current folder context
    full_prompt = prompt if prompt.startswith("@.") else f"@. {prompt}"

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
            
    return result

def extract_gemini_response(stdout: str) -> str:
    """Extract the response text from Gemini JSON output."""
    try:
        # Gemini might output some lines before the JSON
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
        sys.exit(result.returncode)

    response = extract_gemini_response(result.stdout)
    if not response:
        log_error("Gemini returned no response.")
        sys.exit(1)
    
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

def run_gemini_implementation_phase(
    task: str,
    *,
    repo: str,
    issue: int,
    phase: str,
    branch_override: str | None = None,
    session_scope: str = "",
    issue_data: dict[str, Any] | None = None,
) -> None:
    """Run an implementation or validation phase through Gemini."""
    print("=" * 60)
    print("Gemini Agent Execution")
    print("=" * 60)
    print(f"Task: {task[:200]}...")
    print("=" * 60)

    pending_task = task
    for attempt in range(1, MAX_VALIDATION_ATTEMPTS + 1):
        result = run_gemini(
            pending_task,
            repo=repo,
            issue=issue,
            phase=phase,
            branch_override=branch_override,
            issue_data=issue_data,
        )
        if result.returncode != 0:
            sys.exit(result.returncode)

        response = extract_gemini_response(result.stdout)
        if response:
            log_multiline("Assistant response", response)
        else:
            log_info("Gemini run completed with no parsed response.")

        if phase not in VALIDATION_PHASES:
            log_info(
                f"Skipping automated validation for phase {phase}; validation is reserved for phases 5 through 9."
            )
            print("\nAgent execution complete.")
            return

        test_result = run_phase_tests(repo=repo, issue=issue, phase=phase, branch_override=branch_override, issue_data=issue_data)
        if test_result.stdout:
            print(test_result.stdout)
        if test_result.stderr:
            print(test_result.stderr, file=sys.stderr)

        if test_result.returncode == 0:
            print("\nAgent execution complete.")
            return

        if attempt >= MAX_VALIDATION_ATTEMPTS:
            raise SystemExit(f"Validation command contract failed ({VALIDATION_COMMAND_CONTRACT}).")

        retry_number = attempt
        log_error(
            "Validation failed; requesting a scoped Gemini retry with test output context "
            f"(retry {retry_number}/{MAX_VALIDATION_RETRIES})."
        )
        pending_task = build_single_retry_fix_task(summarize_test_output(test_result), retry_number=retry_number)

def finalize_phase_delivery(
    *,
    repo: str,
    issue: int,
    phase: str,
    issue_title: str = "",
    branch_override: str | None = None,
    issue_data: dict[str, Any] | None = None,
) -> str:
    """Commit and push phase changes, then return a summary suitable for a GitHub issue comment."""
    return utils_finalize_phase_delivery(
        repo=repo,
        issue=issue,
        phase=phase,
        issue_title=issue_title,
        branch_override=branch_override,
        issue_data=issue_data,
    )
