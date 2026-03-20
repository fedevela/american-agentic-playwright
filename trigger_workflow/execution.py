from __future__ import annotations

from typing import Any, Callable

from .config import (
    DISCUSSION_PHASES,
    PRE_IMPLEMENTATION_PHASES,
    SPECIFICATION_PHASE,
)
from .context import PhaseExecutionRequest, conversation_scope_for_phase, describe_phase_conversation_policy
from .github_ops import (
    advance_issue_label,
    create_child_issues,
    post_issue_comment,
    remove_issue_label,
    tag_issue_needs_human,
)
from .logging_utils import log_error, log_info, log_multiline, log_step
from .gemini_runner import (
    finalize_phase_delivery as gemini_finalize_delivery,
    run_gemini_comment_phase,
    run_gemini_json_phase,
    run_gemini_implementation_phase,
)
from .prompts import (
    build_implementation_phase_prompt,
    build_comment_phase_prompt,
    build_phase_four_summary,
    build_tiferet_specification_prompt,
    format_phase_comment,
)
from .runner_utils import create_issue_branches_for_child_issues
from .validation import validate_tiferet_specification_payload_structure


def run_comment_phase(prompt: str, repo: str, issue: int, phase: str, session_scope: str, issue_data: dict[str, Any] | None = None) -> str:
    return run_gemini_comment_phase(prompt, repo=repo, issue=issue, phase=phase, session_scope=session_scope, issue_data=issue_data)


def run_json_phase(prompt: str, repo: str, issue: int, phase: str, session_scope: str, issue_data: dict[str, Any] | None = None) -> dict[str, Any]:
    return run_gemini_json_phase(prompt, repo=repo, issue=issue, phase=phase, session_scope=session_scope, issue_data=issue_data)


def run_implementation_phase(prompt: str, repo: str, issue: int, phase: str, session_scope: str, issue_data: dict[str, Any] | None = None) -> None:
    run_gemini_implementation_phase(prompt, repo=repo, issue=issue, phase=phase, session_scope=session_scope, issue_data=issue_data)


def finalize_delivery(repo: str, issue: int, phase: str, issue_title: str, issue_data: dict[str, Any] | None = None) -> str:
    return gemini_finalize_delivery(repo=repo, issue=issue, phase=phase, issue_title=issue_title, issue_data=issue_data)


def post_phase_machine_comment(request: PhaseExecutionRequest, body: str) -> None:
    """Post a wrapped phase comment back to the parent issue."""
    post_issue_comment(
        request.repo,
        request.issue,
        format_phase_comment(request.phase, request.label, body),
    )


def log_prompt_size_and_conversation_policy(prompt: str, phase: str) -> str:
    """Log the prompt size and session behavior, then return the resolved session scope."""
    log_info(f"Prompt built ({len(prompt)} chars)")
    session_scope = conversation_scope_for_phase(phase)
    log_info(f"Session policy: {describe_phase_conversation_policy(phase, session_scope)}")
    return session_scope


def build_phase_prompt_and_conversation_scope(
    phase: str,
    builder: Callable[..., str],
    *args: Any,
) -> tuple[str, str]:
    """Build a phase prompt and return it with the resolved session-scope policy."""
    prompt = builder(*args)
    return prompt, log_prompt_size_and_conversation_policy(prompt, phase)


def build_phase_execution_prompt(
    request: PhaseExecutionRequest,
    prompt_builder: Callable[..., str],
) -> tuple[str, str]:
    """Build a phase prompt using the common execution request payload."""
    return build_phase_prompt_and_conversation_scope(
        request.phase,
        prompt_builder,
        request.label,
        request.issue,
        request.repo,
        request.microagent_content,
        request.phase,
        request.issue_data,
    )


def select_phase_prompt_builder(phase: str) -> Callable[..., str]:
    """Resolve which prompt builder is used for the given phase family."""
    if phase in DISCUSSION_PHASES:
        return build_comment_phase_prompt
    if phase == SPECIFICATION_PHASE:
        return build_tiferet_specification_prompt
    return build_implementation_phase_prompt


def execute_phase_with_needs_human_tagging(
    request: PhaseExecutionRequest,
    executor: Callable[[PhaseExecutionRequest], None],
) -> None:
    """Execute a phase and mark pre-Netzach failures for explicit human intervention."""
    try:
        executor(request)
    except SystemExit:
        if request.phase in PRE_IMPLEMENTATION_PHASES:
            log_error(
                f"Phase {request.phase.upper()} failed before Netzach; tagging issue for human intervention."
            )
            tag_issue_needs_human(request.repo, request.issue)
        raise


def execute_comment_phase_handoff(request: PhaseExecutionRequest) -> None:
    """Execute comment-only phases by generating and posting a phase comment."""
    log_info("Building discussion prompt...")
    prompt, session_scope = build_phase_execution_prompt(request, build_comment_phase_prompt)

    log_info(f"Running agent for phase {request.phase.upper()}...")
    comment = run_comment_phase(
        prompt,
        repo=request.repo,
        issue=request.issue,
        phase=request.phase,
        session_scope=session_scope,
        issue_data=request.issue_data,
    )
    log_info(f"Comment generated ({len(comment)} chars)")
    log_multiline("Generated comment", comment)

    log_info("Posting comment to GitHub...")
    post_phase_machine_comment(request, comment)
    log_info("Comment posted")

    log_info("Advancing to next phase label...")
    advance_issue_label(request.repo, request.issue, request.label)
    log_info("Label advanced")


def execute_tiferet_specification_phase(request: PhaseExecutionRequest) -> None:
    """Execute phase 4/Tiferet by generating parent/child issues and clearing the parent phase label."""
    log_info("Building specification prompt...")
    prompt, session_scope = build_phase_execution_prompt(request, build_tiferet_specification_prompt)

    log_info("Running agent for JSON payload...")
    payload = run_json_phase(
        prompt,
        repo=request.repo,
        issue=request.issue,
        phase=request.phase,
        session_scope=session_scope,
        issue_data=request.issue_data,
    )
    log_info("JSON payload received")

    log_info("Validating payload schema...")
    validate_tiferet_specification_payload_structure(payload)
    log_info("Validation passed")
    log_multiline("Generated parent comment", payload["comment"].strip())

    log_info("Posting parent comment...")
    post_phase_machine_comment(request, payload["comment"].strip())
    log_info("Parent comment posted")

    log_info(f"Creating {len(payload['sub_issues'])} ordered child issues with parent and dependency links...")
    created = create_child_issues(request.repo, request.issue, payload["sub_issues"])
    log_info(f"Created and linked {len(created)} child issues")
    child_issue_numbers = [int(item["number"]) for item in created]
    log_info("Creating child issue branches for downstream implementation phases...")
    create_issue_branches_for_child_issues(request.repo, request.issue, child_issue_numbers)
    log_info(f"Created/verified {len(child_issue_numbers)} child issue branches")

    log_info("Posting summary comment...")
    summary_comment = build_phase_four_summary(created)
    log_multiline("Generated summary comment", summary_comment)
    post_phase_machine_comment(request, summary_comment)
    log_info("Summary comment posted")

    log_info("Completing Tiferet handoff: removing phase:tiferet label from parent issue...")
    remove_issue_label(request.repo, request.issue, request.label)
    log_info("Parent issue label removed (handoff complete)")


def execute_implementation_phase_task(request: PhaseExecutionRequest) -> None:
    """Execute phases 5-9 headlessly in the configured runner."""
    log_info("Building agent prompt...")
    prompt, session_scope = build_phase_execution_prompt(request, build_implementation_phase_prompt)

    log_info("Running agent...")
    run_implementation_phase(
        prompt,
        repo=request.repo,
        issue=request.issue,
        phase=request.phase,
        session_scope=session_scope,
        issue_data=request.issue_data,
    )
    log_info("Agent execution complete")
    log_info("Finalizing git delivery (commit + push)...")
    delivery_summary = finalize_delivery(
        repo=request.repo,
        issue=request.issue,
        phase=request.phase,
        issue_title=str(request.issue_data.get("title") or ""),
        issue_data=request.issue_data,
    )
    log_multiline("Delivery summary", delivery_summary)
    log_info("Posting delivery summary comment...")
    post_phase_machine_comment(request, delivery_summary)
    log_info("Delivery summary comment posted")
    log_info("Advancing to next phase label...")
    advance_issue_label(request.repo, request.issue, request.label)
    log_info("Label advanced")
