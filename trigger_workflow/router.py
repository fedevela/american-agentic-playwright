from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .config import (
    DEFAULT_REPO,
    DISCUSSION_PHASES,
    MICROAGENTS_DIR,
    NEXT_LABEL_MAP,
    PHASE_DISPLAY_NAME_MAP,
    PRE_IMPLEMENTATION_PHASES,
    SPECIFICATION_PHASE,
    STRICTLY_INDEPENDENT_PHASES,
    WORKSPACE,
)
from .github_ops import (
    advance_issue_label,
    create_child_issues,
    ensure_phase_labels,
    fetch_issue_data,
    issue_has_label,
    post_issue_comment,
    remove_issue_label,
    resolve_issue_by_label,
    resolve_oldest_phased_issue,
    tag_issue_needs_human,
)
from .logging_utils import log_error, log_info, log_multiline, log_section, log_step
from .openhands_runner import (
    create_issue_branches_for_child_issues,
    resolve_openhands_model_connection,
    run_openhands_comment_phase,
    run_openhands_json_phase,
    run_openhands_implementation_phase,
)
from .prompts import (
    build_implementation_phase_prompt,
    build_comment_phase_prompt,
    build_phase_four_summary,
    build_tiferet_specification_prompt,
    determine_phase_from_label,
    format_phase_comment,
    read_microagent_for_label,
)
from .validation import validate_tiferet_specification_payload_structure, validate_tiferet_requirement_traceability


@dataclass(frozen=True)
class PhaseExecutionRequest:
    """Bundle the runtime inputs shared by all phase execution paths."""

    label: str
    issue: int
    repo: str
    microagent_content: str
    phase: str
    issue_data: dict[str, Any]


def conversation_scope_for_phase(phase: str) -> str:
    """Return the OpenHands session scope policy for the given phase."""
    if phase in STRICTLY_INDEPENDENT_PHASES:
        return f"phase-{phase}"
    return ""


def describe_phase_conversation_policy(phase: str, session_scope: str) -> str:
    """Describe whether the phase starts from an empty session or the shared per-issue session."""
    if session_scope:
        return (
            f"strictly independent phase session '{session_scope}' "
            "(starts with empty OpenHands conversation context)"
    )
    return "shared per-issue session policy (OpenHands runs start fresh by runner policy)"


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


def post_phase_machine_comment(request: PhaseExecutionRequest, body: str) -> None:
    """Post a wrapped phase comment back to the parent issue."""
    post_issue_comment(
        request.repo,
        request.issue,
        format_phase_comment(request.phase, request.label, body),
    )


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


def run_labeled_issue_phase(label: Optional[str] = None, issue: Optional[int] = None, repo: Optional[str] = None) -> None:
    """Route the label to the correct phase workflow."""
    repo = repo or DEFAULT_REPO
    log_section("STARTING PHASE EXECUTION")
    log_info(f"Repository: {repo}")

    log_step("Step 0: Ensuring canonical phase labels exist")
    ensure_phase_labels(repo)

    log_step("Step 1a: Resolving issue and label")
    if label is None:
        log_info("No label provided, finding oldest phased issue...")
        issue, label = resolve_oldest_phased_issue(repo)
        log_info(f"Selected issue #{issue} with label '{label}'")

    log_step("Step 1b: Determining phase id")
    phase = determine_phase_from_label(label)
    if not phase:
        raise SystemExit(f"Unknown label '{label}'. Cannot determine phase.")
    log_info(f"Label '{label}' → Phase {phase.upper()} ({PHASE_DISPLAY_NAME_MAP.get(phase, 'Unknown')})")

    log_step("Step 1c: Resolving issue number")
    if issue is None:
        log_info(f"Finding issue with label '{label}'...")
        issue = resolve_issue_by_label(repo, label)
    log_info(f"Issue number: #{issue}")

    log_step("Sequence Context")
    log_info(f"Current: Phase {phase.upper()}")
    next_phase = determine_phase_from_label(NEXT_LABEL_MAP.get(label, ""))
    if next_phase:
        log_info(f"Next: Phase {next_phase.upper()} ({PHASE_DISPLAY_NAME_MAP.get(next_phase, 'Unknown')})")
    else:
        log_info("Next: Final phase (no further handoff)")

    log_step("Step 2: Reading microagent prompt")
    microagent_content = read_microagent_for_label(label, phase)
    log_info(f"Microagent prompt loaded ({len(microagent_content)} bytes)")

    log_step("Step 3: Fetching issue data from GitHub")
    issue_data = fetch_issue_data(repo, issue)
    log_info(f"Issue #{issue} fetched: '{issue_data.get('title', 'Unknown')}'")
    label_names = [l.get("name", "") for l in issue_data.get("labels", []) if l.get("name")]
    log_info(f"Current labels: {', '.join(label_names) if label_names else '(none)'}")

    if not issue_has_label(issue_data, label):
        log_error(f"Issue #{issue} in {repo} is not labeled '{label}'. Skipping phase execution.")
        raise SystemExit(1)
    log_info("Label verification: PASSED")

    log_step("Step 4: Executing phase workflow")
    if phase in DISCUSSION_PHASES:
        log_info(f"Running discussion workflow for phase {phase.upper()}")
        execute_phase_with_needs_human_tagging(
            PhaseExecutionRequest(
                label=label,
                issue=issue,
                repo=repo,
                microagent_content=microagent_content,
                phase=phase,
                issue_data=issue_data,
            ),
            execute_comment_phase_handoff,
        )
        return

    if phase == SPECIFICATION_PHASE:
        log_info("Running specification workflow for phase 4")
        execute_phase_with_needs_human_tagging(
            PhaseExecutionRequest(
                label=label,
                issue=issue,
                repo=repo,
                microagent_content=microagent_content,
                phase=phase,
                issue_data=issue_data,
            ),
            execute_tiferet_specification_phase,
        )
        return

    log_info(f"Running implementation workflow for phase {phase.upper()}")
    execute_implementation_phase_task(
        PhaseExecutionRequest(
            label=label,
            issue=issue,
            repo=repo,
            microagent_content=microagent_content,
            phase=phase,
            issue_data=issue_data,
        )
    )


def execute_comment_phase_handoff(request: PhaseExecutionRequest) -> None:
    """Execute comment-only phases by generating and posting a phase comment."""
    log_info("Building discussion prompt...")
    prompt, session_scope = build_phase_execution_prompt(request, build_comment_phase_prompt)

    log_info(f"Running OpenHands for phase {request.phase.upper()}...")
    comment = run_openhands_comment_phase(
        prompt,
        repo=request.repo,
        issue=request.issue,
        phase=request.phase,
        session_scope=session_scope,
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

    log_info("Running OpenHands for JSON payload...")
    payload = run_openhands_json_phase(
        prompt,
        repo=request.repo,
        issue=request.issue,
        phase=request.phase,
        session_scope=session_scope,
    )
    log_info("JSON payload received")

    log_info("Validating payload schema...")
    validate_tiferet_specification_payload_structure(payload)
    validate_tiferet_requirement_traceability(payload, request.issue_data)
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
    create_issue_branches_for_child_issues(request.repo, child_issue_numbers)
    log_info(f"Created/verified {len(child_issue_numbers)} child issue branches")

    log_info("Posting summary comment...")
    summary_comment = build_phase_four_summary(created)
    log_multiline("Generated summary comment", summary_comment)
    post_phase_machine_comment(request, summary_comment)
    log_info("Summary comment posted")

    log_info("Completing Tiferet handoff by removing parent phase label...")
    remove_issue_label(request.repo, request.issue, request.label)
    log_info("Parent Tiferet label removed")


def execute_implementation_phase_task(request: PhaseExecutionRequest) -> None:
    """Execute phases 5-9 headlessly in OpenHands."""
    log_info("Building agent prompt...")
    prompt, session_scope = build_phase_execution_prompt(request, build_implementation_phase_prompt)

    log_info("Running OpenHands agent...")
    run_openhands_implementation_phase(
        prompt,
        repo=request.repo,
        issue=request.issue,
        phase=request.phase,
        session_scope=session_scope,
    )
    log_info("Agent execution complete")
    log_info("Advancing to next phase label...")
    advance_issue_label(request.repo, request.issue, request.label)
    log_info("Label advanced")


def run_trigger_cli() -> None:
    """Main entry point."""
    log_section("OPENHANDS SWARM PHASE ROUTER")
    log_info(f"Working directory: {WORKSPACE}")
    log_info(f"Microagents directory: {MICROAGENTS_DIR}")
    model_name, connection = resolve_openhands_model_connection()
    log_info(f"OpenHands model connection: {connection}")
    log_info(f"OpenHands model name: {model_name}")

    parser = argparse.ArgumentParser(description="Trigger OpenHands / GitHub phase workflow")
    parser.add_argument("--label", help="GitHub label triggering the phase")
    parser.add_argument("--issue", type=int, help="Issue number")
    parser.add_argument("--repo", help="Repository owner/repo")
    args = parser.parse_args()

    run_labeled_issue_phase(args.label, args.issue, args.repo)
    log_section("PHASE EXECUTION COMPLETE")
