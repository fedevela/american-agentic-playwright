from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .git_client import prepare_branch_context, prepare_phase_execution_context
from .logging_utils import log_info

MAX_VALIDATION_RETRIES = 3
MAX_VALIDATION_ATTEMPTS = 1 + MAX_VALIDATION_RETRIES
TEST_OUTPUT_MAX_CHARS = 12000
VALIDATION_COMMAND_CONTRACT = "`npm run typecheck` -> `npm run build` -> `npm run test` -> `npm run tests:e2e`"
VALIDATION_COMMANDS = (
    ["npm", "run", "typecheck"],
    ["npm", "run", "build"],
    ["npm", "run", "test"],
    ["npm", "run", "tests:e2e"],
)

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
    ensure_playwright_test_prerequisites(context.local_path)
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

def ensure_playwright_test_prerequisites(local_path: Path) -> None:
    """Ensure the repository has local dependencies installed for Playwright test runs."""
    local_playwright = local_path / "node_modules" / ".bin" / "playwright"
    if local_playwright.exists():
        return

    log_info("Playwright CLI unavailable; running npm ci to install test dependencies")
    install_result = subprocess.run(
        ["npm", "ci"],
        cwd=local_path,
        text=True,
        capture_output=True,
        timeout=1200,
    )
    if install_result.returncode != 0:
        raise SystemExit(
            "Failed to install npm dependencies required for tests.\n"
            f"stdout:\n{install_result.stdout}\n"
            f"stderr:\n{install_result.stderr}"
        )

    if not local_playwright.exists():
        playwright_version_result = subprocess.run(
            ["npx", "playwright", "--version"],
            cwd=local_path,
            text=True,
            capture_output=True,
            timeout=120,
        )
        raise SystemExit(
            "Playwright CLI is still unavailable in node_modules after `npm ci`.\n"
            f"stdout:\n{playwright_version_result.stdout}\n"
            f"stderr:\n{playwright_version_result.stderr}"
        )
