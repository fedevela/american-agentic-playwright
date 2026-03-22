from __future__ import annotations

import subprocess
from typing import Any

from .git_client import prepare_branch_context, prepare_phase_execution_context
from .logging_utils import log_info

MAX_VALIDATION_RETRIES = 3
MAX_VALIDATION_ATTEMPTS = 1 + MAX_VALIDATION_RETRIES
TEST_OUTPUT_MAX_CHARS = 12000
VALIDATION_COMMAND_CONTRACT = "`make build` -> `make test`"
VALIDATION_COMMANDS = (
    ["make", "build"],
    ["make", "test"],
)

def get_coverage_context(
    *,
    repo: str,
    issue: int,
    phase: str,
    branch_override: str | None = None,
    issue_data: dict[str, Any] | None = None,
) -> str:
    """Run `make cov` and return the coverage report filtered of 100% covered lines."""
    context = (
        prepare_phase_execution_context(repo, phase, issue, issue_data=issue_data)
        if branch_override is None
        else prepare_branch_context(repo, branch=branch_override, branch_log_label="Resolved explicit target branch", issue_data=issue_data)
    )

    log_info("Running pre-phase coverage command: make cov")
    result = subprocess.run(
        ["make", "cov"],
        cwd=context.local_path,
        text=True,
        capture_output=True,
        timeout=1200,
    )
    
    if result.returncode != 0:
        log_info(f"`make cov` returned non-zero exit code {result.returncode}")
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr)
        raise SystemExit("Pre-phase coverage command failed.")
        
    lines = result.stdout.splitlines()
    filtered_lines = []
    for line in lines:
        if "100%" not in line:
            filtered_lines.append(line)
            
    if not filtered_lines:
        return "(No coverage data or all files are 100% covered)"
        
    return "\n".join(filtered_lines)


def run_phase_tests(
    *,
    repo: str,
    issue: int,
    phase: str,
    branch_override: str | None = None,
    issue_data: dict[str, Any] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run repository validation commands for a phase using the same checkout/branch context."""
    context = (
        prepare_phase_execution_context(repo, phase, issue, issue_data=issue_data)
        if branch_override is None
        else prepare_branch_context(repo, branch=branch_override, branch_log_label="Resolved explicit target branch", issue_data=issue_data)
    )
    combined_stdout: list[str] = []
    combined_stderr: list[str] = []

    for command in VALIDATION_COMMANDS:
        command_preview = " ".join(command)
        log_info(f"Running validation command: {command_preview}")
        result = subprocess.run(
            command,
            cwd=context.local_path,
            text=True,
            capture_output=True,
            timeout=1200,
        )
        if result.stdout:
            combined_stdout.append(f"$ {command_preview}\n{result.stdout}")
        if result.stderr:
            combined_stderr.append(f"$ {command_preview}\n{result.stderr}")
        if result.returncode != 0:
            return subprocess.CompletedProcess(
                args=command,
                returncode=result.returncode,
                stdout="\n".join(combined_stdout),
                stderr="\n".join(combined_stderr),
            )

    return subprocess.CompletedProcess(
        args=["validation"],
        returncode=0,
        stdout="\n".join(combined_stdout),
        stderr="\n".join(combined_stderr),
    )

def summarize_test_output(result: subprocess.CompletedProcess[str]) -> str:
    """Build a bounded combined test output payload suitable for prompt feedback."""
    parts: list[str] = []
    if result.stdout:
        parts.append(result.stdout)
    if result.stderr:
        parts.append(result.stderr)
    combined = "\n".join(parts).strip() or "(no test output captured)"
    if len(combined) <= TEST_OUTPUT_MAX_CHARS:
        return combined
    return combined[-TEST_OUTPUT_MAX_CHARS:]

def build_single_retry_fix_task(test_output: str, *, retry_number: int) -> str:
    """Build a scoped retry task sent to the runner after a failed validation run."""
    return (
        "Your previous changes were applied, but required repository validation failed.\n\n"
        "Run and satisfy exactly this command contract:\n"
        f"- {VALIDATION_COMMAND_CONTRACT}\n\n"
        f"This is retry attempt {retry_number} of {MAX_VALIDATION_RETRIES}.\n\n"
        "Failure output:\n"
        "```text\n"
        f"{test_output}\n"
        "```\n\n"
        "Do not expand scope beyond fixing these validation failures.\n"
        f"Apply minimal code changes to make {VALIDATION_COMMAND_CONTRACT} pass, then finish."
    )
