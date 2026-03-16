from __future__ import annotations

import argparse
import io
import sys
from contextlib import redirect_stdout
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .config import (
    DEFAULT_REPO,
    DISCUSSION_PHASES,
    LABEL_PHASE_MAP,
    MICROAGENTS_DIR,
    NEXT_LABEL_MAP,
    PHASE_DISPLAY_NAME_MAP,
    PRE_IMPLEMENTATION_PHASES,
    RUNNER_TYPE,
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
    issue_phase_labels,
    post_issue_comment,
    remove_issue_label,
    resolve_issue_by_label,
    resolve_oldest_phased_issue,
    tag_issue_needs_human,
)
from .logging_utils import log_error, log_info, log_multiline, log_section, log_step
from .openhands_runner import (
    create_issue_branches_for_child_issues,
    finalize_phase_delivery as openhands_finalize_delivery,
    resolve_openhands_model_connection,
    run_openhands_comment_phase,
    run_openhands_json_phase,
    run_openhands_implementation_phase,
)
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
    determine_phase_from_label,
    format_phase_comment,
    read_microagent_for_label,
)
from .validation import validate_tiferet_specification_payload_structure, validate_tiferet_requirement_traceability

def run_comment_phase(prompt: str, repo: str, issue: int, phase: str, session_scope: str) -> str:
    if RUNNER_TYPE == "gemini":
        return run_gemini_comment_phase(prompt, repo=repo, issue=issue, phase=phase, session_scope=session_scope)
    return run_openhands_comment_phase(prompt, repo=repo, issue=issue, phase=phase, session_scope=session_scope)

def run_json_phase(prompt: str, repo: str, issue: int, phase: str, session_scope: str) -> dict[str, Any]:
    if RUNNER_TYPE == "gemini":
        return run_gemini_json_phase(prompt, repo=repo, issue=issue, phase=phase, session_scope=session_scope)
    return run_openhands_json_phase(prompt, repo=repo, issue=issue, phase=phase, session_scope=session_scope)

def run_implementation_phase(prompt: str, repo: str, issue: int, phase: str, session_scope: str) -> None:
    if RUNNER_TYPE == "gemini":
        run_gemini_implementation_phase(prompt, repo=repo, issue=issue, phase=phase, session_scope=session_scope)
    else:
        run_openhands_implementation_phase(prompt, repo=repo, issue=issue, phase=phase, session_scope=session_scope)

def finalize_delivery(repo: str, issue: int, phase: str, issue_title: str) -> str:
    if RUNNER_TYPE == "gemini":
        return gemini_finalize_delivery(repo=repo, issue=issue, phase=phase, issue_title=issue_title)
    return openhands_finalize_delivery(repo=repo, issue=issue, phase=phase, issue_title=issue_title)


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


def resolve_phase_execution_request(
    label: Optional[str] = None,
    issue: Optional[int] = None,
    repo: Optional[str] = None,
    *,
    manual: bool = False,
    include_base_persona: bool = True,
) -> PhaseExecutionRequest:
    """Resolve and validate issue/label context into a reusable phase execution request."""
    repo = repo or DEFAULT_REPO
    log_section("STARTING PHASE EXECUTION")
    log_info(f"Repository: {repo}")

    if manual:
        log_step("Step 0: Manual mode enabled")
        log_info("Skipping canonical phase label synchronization to avoid GitHub mutations")
    else:
        log_step("Step 0: Ensuring canonical phase labels exist")
        ensure_phase_labels(repo)

    log_step("Step 1: Resolving issue and label context")
    if issue is None and label is None:
        log_info("No issue or label provided; finding oldest phased issue...")
        issue, label = resolve_oldest_phased_issue(repo)
        log_info(f"Selected issue #{issue} with label '{label}'")
    elif issue is None and label is not None:
        log_info(f"Label '{label}' provided; finding oldest issue carrying this label...")
        issue = resolve_issue_by_label(repo, label)
        log_info(f"Selected issue #{issue} for label '{label}'")
    elif issue is not None and label is None:
        log_info(f"Issue #{issue} provided; resolving phase label from issue metadata...")
    else:
        log_info(f"Issue #{issue} and label '{label}' provided; will verify label on issue...")

    log_step("Step 2: Fetching issue data from GitHub")
    issue_data = fetch_issue_data(repo, issue)
    log_info(f"Issue #{issue} fetched: '{issue_data.get('title', 'Unknown')}'")

    if label is None:
        # Resolve label from issue_data
        labels = issue_phase_labels(issue_data)
        if not labels:
            log_error(f"Issue #{issue} in {repo} has no phase labels. Cannot determine phase.")
            raise SystemExit(1)
        if len(labels) > 1:
            log_error(
                f"Issue #{issue} in {repo} has multiple phase labels: {', '.join(labels)}. "
                "Pass --label explicitly to select one."
            )
            raise SystemExit(1)
        label = labels[0]
        log_info(f"Resolved label '{label}' from issue #{issue}")
    else:
        # Verify label on issue_data
        if not issue_has_label(issue_data, label):
            if manual:
                log_info(
                    f"Manual mode label override: issue #{issue} is not labeled '{label}', "
                    "but continuing with the requested label for preview."
                )
            else:
                log_error(f"Issue #{issue} in {repo} is not labeled '{label}'. Skipping phase execution.")
                raise SystemExit(1)
        else:
            log_info("Label verification: PASSED")

    log_step("Step 3: Determining phase id")
    phase = determine_phase_from_label(label)
    if not phase:
        raise SystemExit(f"Unknown label '{label}'. Cannot determine phase.")
    log_info(f"Label '{label}' → Phase {phase.upper()} ({PHASE_DISPLAY_NAME_MAP.get(phase, 'Unknown')})")

    log_step("Sequence Context")
    log_info(f"Current: Phase {phase.upper()}")
    next_phase_label = NEXT_LABEL_MAP.get(label, "")
    next_phase = determine_phase_from_label(next_phase_label) if next_phase_label else None
    if next_phase:
        log_info(f"Next: Phase {next_phase.upper()} ({PHASE_DISPLAY_NAME_MAP.get(next_phase, 'Unknown')})")
    else:
        log_info("Next: Final phase (no further handoff)")

    log_step("Step 4: Reading microagent prompt")
    microagent_content = read_microagent_for_label(label, phase, include_base_persona=include_base_persona)
    log_info(f"Microagent prompt loaded ({len(microagent_content)} bytes)")

    label_names = [l.get("name", "") for l in issue_data.get("labels", []) if l.get("name")]
    log_info(f"Current labels: {', '.join(label_names) if label_names else '(none)'}")

    request = PhaseExecutionRequest(
        label=label,
        issue=issue,
        repo=repo,
        microagent_content=microagent_content,
        phase=phase,
        issue_data=issue_data,
    )
    return request


def select_phase_prompt_builder(phase: str) -> Callable[..., str]:
    """Resolve which prompt builder is used for the given phase family."""
    if phase in DISCUSSION_PHASES:
        return build_comment_phase_prompt
    if phase == SPECIFICATION_PHASE:
        return build_tiferet_specification_prompt
    return build_implementation_phase_prompt


def build_phase_prompt_for_issue(
    label: Optional[str] = None,
    issue: Optional[int] = None,
    repo: Optional[str] = None,
    *,
    manual: bool = True,
) -> str:
    """Resolve issue context and return only the generated phase prompt text."""
    request = resolve_phase_execution_request(
        label=label,
        issue=issue,
        repo=repo,
        manual=manual,
    )
    prompt, _ = build_phase_execution_prompt(request, select_phase_prompt_builder(request.phase))
    return prompt


def render_prompt_only_output(request: PhaseExecutionRequest, prompt: str) -> str:
    """Return prompt-only output including next-action instructions by phase family."""
    if request.phase in DISCUSSION_PHASES:
        actions = [
            "1. Prepare a commit message with the above prompt.",
            "5. Generate the gh command to post the comment to the issue in md format.",
            "3. Generate the issue label to the next phase.",
        ]
    elif request.phase == SPECIFICATION_PHASE:
        actions = [
            "1. Prepare a commit message with the above prompt.",
            "2. Validate JSON payload structure and requirement traceability.",
            "3. Post the parent phase comment from `payload.comment`.",
            "4. Create ordered child issues from `payload.sub_issues` and create child branches.",
            "5. Generate the gh command to post the comment to the issue in md format.",
            "6. Remove the parent phase label from the parent issue.",
        ]
    else:
        actions = [
            "1. Prepare a commit message with the above prompt.",
            "2. Generate a commit message and keep the trigger format: "
            f"`phase:{request.phase} issue #{request.issue}: <short summary>`.",
            "3. Generate a phase delivery comment body summarizing changes and validation.",
            "4. Commit and push the branch updates.",
            "5. Generate the gh command to post the comment to the issue in md format.",
            "6. Advance the issue label to the next phase.",
        ]

    return "\n\n".join(
        [
            prompt,
            "Prompt-only planned actions:\n" + "\n".join(actions),
        ]
    )


def label_for_phase_id(phase: str) -> str:
    """Resolve canonical label for a canonical phase id."""
    raw_phase = phase.strip()
    normalized_phase = {
        "2a": "2A",
        "2b": "2B",
        "2c": "2C",
    }.get(raw_phase.lower(), raw_phase.upper() if raw_phase.lower() in {"2a", "2b", "2c"} else raw_phase)
    for label_name, phase_id in LABEL_PHASE_MAP.items():
        if phase_id == normalized_phase:
            return label_name
    expected = ", ".join(sorted(set(LABEL_PHASE_MAP.values())))
    raise SystemExit(f"Unknown phase '{phase}'. Expected one of: {expected}.")


def preview_phase_execution_plan(request: PhaseExecutionRequest) -> None:
    """Render manual-mode instructions without running agent or mutating GitHub."""
    phase = request.phase
    if phase in DISCUSSION_PHASES:
        prompt, session_scope = build_phase_execution_prompt(request, build_comment_phase_prompt)
        log_multiline(f"Manual mode prompt for {RUNNER_TYPE} (discussion)", prompt)
        log_info(f"Session scope metadata: '{session_scope or '(shared issue scope)'}'")
        log_multiline(
            "Manual mode planned actions",
            "\n".join(
                [
                    f"1. Run {RUNNER_TYPE} with the prompt above and capture the final assistant message.",
                    "2. Post that message to the issue as a phase comment wrapper.",
                    "3. Advance the issue label to the next phase.",
                ]
            ),
        )
        return

    if phase == SPECIFICATION_PHASE:
        prompt, session_scope = build_phase_execution_prompt(request, build_tiferet_specification_prompt)
        log_multiline(f"Manual mode prompt for {RUNNER_TYPE} (specification JSON)", prompt)
        log_info(f"Session scope metadata: '{session_scope or '(shared issue scope)'}'")
        log_multiline(
            "Manual mode planned actions",
            "\n".join(
                [
                    f"1. Run {RUNNER_TYPE} with the prompt above and capture the final assistant message as JSON.",
                    "2. Validate JSON payload structure and requirement traceability.",
                    "3. Post the parent phase comment from `payload.comment`.",
                    "4. Create ordered child issues from `payload.sub_issues` and create child branches.",
                    "5. Post the generated child issue summary comment.",
                    "6. Remove the parent phase label from the parent issue.",
                ]
            ),
        )
        return

    prompt, session_scope = build_phase_execution_prompt(request, build_implementation_phase_prompt)
    log_multiline(f"Manual mode prompt for {RUNNER_TYPE} (implementation)", prompt)
    log_info(f"Session scope metadata: '{session_scope or '(shared issue scope)'}'")
    log_multiline(
        "Manual mode planned actions",
        "\n".join(
            [
                f"1. Run {RUNNER_TYPE} with the prompt above on the resolved issue branch.",
                "2. Run trigger validation flow for phases 6-9 (`typecheck -> build -> test:e2e`).",
                "3. Finalize delivery (git add/commit/push and PR create/lookup).",
                "4. Post the delivery summary as a wrapped phase comment.",
                "5. Advance the issue label to the next phase.",
            ]
        ),
    )


def execute_comment_phase_handoff(request: PhaseExecutionRequest) -> None:
    """Execute comment-only phases by generating and posting a phase comment."""
    log_info("Building discussion prompt...")
    prompt, session_scope = build_phase_execution_prompt(request, build_comment_phase_prompt)

    log_info(f"Running {RUNNER_TYPE} for phase {request.phase.upper()}...")
    comment = run_comment_phase(
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

    log_info(f"Running {RUNNER_TYPE} for JSON payload...")
    payload = run_json_phase(
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
    """Execute phases 5-9 headlessly in the configured runner."""
    log_info("Building agent prompt...")
    prompt, session_scope = build_phase_execution_prompt(request, build_implementation_phase_prompt)

    log_info(f"Running {RUNNER_TYPE} agent...")
    run_implementation_phase(
        prompt,
        repo=request.repo,
        issue=request.issue,
        phase=request.phase,
        session_scope=session_scope,
    )
    log_info("Agent execution complete")
    log_info("Finalizing git delivery (commit + push)...")
    delivery_summary = finalize_delivery(
        repo=request.repo,
        issue=request.issue,
        phase=request.phase,
        issue_title=str(request.issue_data.get("title") or ""),
    )
    log_multiline("Delivery summary", delivery_summary)
    log_info("Posting delivery summary comment...")
    post_phase_machine_comment(request, delivery_summary)
    log_info("Delivery summary comment posted")
    log_info("Advancing to next phase label...")
    advance_issue_label(request.repo, request.issue, request.label)
    log_info("Label advanced")


def run_trigger_cli() -> None:
    """Main entry point."""
    global RUNNER_TYPE
    log_info("Starting swarm phase router CLI")
    parser = argparse.ArgumentParser(description="Trigger Swarm Phase / GitHub workflow")
    parser.add_argument("--label", help="GitHub label triggering the phase")
    parser.add_argument("--phase", help="Canonical phase id (1, 2A, 2B, 2C, 3, 4, 5, 6, 7, 8, 9, 10)")
    parser.add_argument("--issue", type=int, help="Issue number")
    parser.add_argument("--repo", help="Repository owner/repo")
    parser.add_argument(
        "--runner",
        choices=["gemini", "openhands"],
        default=RUNNER_TYPE,
        help=f"Runner to use for phase execution (default: {RUNNER_TYPE})",
    )
    parser.add_argument(
        "--manual",
        action="store_true",
        help="Preview trigger prompt + algorithmic actions without running agent or mutating GitHub",
    )
    parser.add_argument(
        "--prompt-only",
        action="store_true",
        help="Return only the generated phase prompt text for the requested issue/label",
    )
    args = parser.parse_args()
    
    # Override global RUNNER_TYPE with CLI argument
    RUNNER_TYPE = args.runner

    log_info(
        f"CLI arguments: label={args.label}, phase={args.phase}, issue={args.issue}, "
        f"repo={args.repo}, runner={args.runner}, manual={args.manual}, prompt-only={args.prompt_only}"
    )
    resolved_label = args.label
    if args.phase:
        phase_label = label_for_phase_id(args.phase)
        if resolved_label and resolved_label != phase_label:
            raise SystemExit(
                f"Conflicting inputs: --label '{resolved_label}' does not match --phase '{args.phase}' "
                f"(expected label '{phase_label}')."
            )
        log_info(f"Mapped phase argument '{args.phase}' to label '{phase_label}'")
        resolved_label = phase_label

    if args.prompt_only:
        log_info("Prompt-only mode: generating and outputting the phase prompt without running OpenHands or mutating GitHub.")
        captured_logs = io.StringIO()
        try:
            with redirect_stdout(captured_logs):
                log_info("Resolving phase execution request for prompt generation...")
                request = resolve_phase_execution_request(
                    label=resolved_label,
                    issue=args.issue,
                    repo=args.repo,
                    manual=True,
                    include_base_persona=True,
                )
                prompt, _ = build_phase_execution_prompt(request, select_phase_prompt_builder(request.phase))
        except SystemExit:
            print(captured_logs.getvalue(), file=sys.stderr)
            raise

        print(captured_logs.getvalue(), file=sys.stderr)
        print(render_prompt_only_output(request, prompt))
        log_info("Prompt-only output generated")
        return

    log_section("SWARM PHASE ROUTER")
    log_info(f"Working directory: {WORKSPACE}")
    log_info(f"Microagents directory: {MICROAGENTS_DIR}")
    log_info(f"Active runner: {RUNNER_TYPE}")
    
    if RUNNER_TYPE == "openhands":
        model_name, connection = resolve_openhands_model_connection()
        log_info(f"OpenHands model connection: {connection}")
        log_info(f"OpenHands model name: {model_name}")

    run_labeled_issue_phase_with_mode(resolved_label, args.issue, args.repo, manual=args.manual)
    log_section("PHASE EXECUTION COMPLETE")
