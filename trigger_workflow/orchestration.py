from __future__ import annotations

from typing import Optional

from .config import (
    DISCUSSION_PHASES,
    SPECIFICATION_PHASE,
)
from .context import resolve_phase_execution_request
from .execution import (
    execute_comment_phase_handoff,
    execute_implementation_phase_task,
    execute_phase_with_needs_human_tagging,
    execute_tiferet_specification_phase,
)
from .logging_utils import log_info, log_step
from .preview import preview_phase_execution_plan


def run_labeled_issue_phase(label: Optional[str] = None, issue: Optional[int] = None, repo: Optional[str] = None) -> None:
    """Route the label to the correct phase workflow."""
    run_labeled_issue_phase_with_mode(label=label, issue=issue, repo=repo, manual=False)


def run_labeled_issue_phase_with_mode(
    label: Optional[str] = None,
    issue: Optional[int] = None,
    repo: Optional[str] = None,
    *,
    manual: bool = False,
) -> None:
    """Route the label to the correct phase workflow with optional manual preview mode."""
    request = resolve_phase_execution_request(
        label=label,
        issue=issue,
        repo=repo,
        manual=manual,
    )

    log_step("Step 4: Executing phase workflow")
    if manual:
        log_info("Manual mode: previewing prompt and planned actions only")
        preview_phase_execution_plan(request)
        return

    if request.phase in DISCUSSION_PHASES:
        log_info(f"Running discussion workflow for phase {request.phase.upper()}")
        execute_phase_with_needs_human_tagging(
            request,
            execute_comment_phase_handoff,
        )
        return

    if request.phase == SPECIFICATION_PHASE:
        log_info("Running specification workflow for phase 4")
        execute_phase_with_needs_human_tagging(
            request,
            execute_tiferet_specification_phase,
        )
        return

    log_info(f"Running implementation workflow for phase {request.phase.upper()}")
    execute_implementation_phase_task(request)
