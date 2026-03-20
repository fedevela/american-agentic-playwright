from __future__ import annotations

import sys
from typing import Any

from .gemini_runner import run_gemini, extract_gemini_response
from .config import IMPLEMENTATION_PHASES
from .logging_utils import log_error, log_info, log_multiline
from .validation_runner import (
    MAX_VALIDATION_ATTEMPTS,
    MAX_VALIDATION_RETRIES,
    VALIDATION_COMMAND_CONTRACT,
    build_single_retry_fix_task,
    run_phase_tests,
    summarize_test_output,
)

VALIDATION_PHASES = set(IMPLEMENTATION_PHASES)

def run_agent_implementation_loop(
    task: str,
    *,
    repo: str,
    issue: int,
    phase: str,
    branch_override: str | None = None,
    session_scope: str = "",
    issue_data: dict[str, Any] | None = None,
) -> None:
    """Run an implementation phase loop with automated validation/retry cycles."""
    print("=" * 60)
    print("Agent Execution Loop")
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
            raise SystemExit(f"Agent execution failed with exit code: {result.returncode}")

        response = extract_gemini_response(result.stdout)
        if response:
            log_multiline("Assistant response", response)
        else:
            log_info("Agent run completed with no parsed response.")

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
            "Validation failed; requesting a scoped agent retry with test output context "
            f"(retry {retry_number}/{MAX_VALIDATION_RETRIES})."
        )
        pending_task = build_single_retry_fix_task(summarize_test_output(test_result), retry_number=retry_number)