from __future__ import annotations

from typing import Any, Callable

from .config import (
    DISCUSSION_PHASES,
    PRE_IMPLEMENTATION_PHASES,
    SPECIFICATION_PHASE,
)
from .context import SfiratPhaseSignal, conversation_scope_for_phase, describe_phase_conversation_policy
from .github_ops import (
    advance_issue_label,
    create_child_issues,
    post_issue_comment,
    remove_issue_label,
    tag_issue_needs_human,
)
from .logging_utils import log_error, log_info, log_multiline, log_step
from .gemini_runner import (
    run_gemini_comment_phase,
    run_gemini_json_phase,
)
from .execution_loop import run_agent_implementation_loop as run_gemini_implementation_phase
from .delivery import finalize_phase_delivery
from .prompts import (
    build_implementation_phase_prompt,
    build_comment_phase_prompt,
    build_phase_four_summary,
    build_tiferet_specification_prompt,
    format_phase_comment,
    build_diff_summary_prompt,
)
from .git_client import create_issue_branches_for_child_issues
from .validation import validate_tiferet_specification_payload_structure


def run_comment_phase(prompt: str, repo: str, issue: int, phase: str, session_scope: str, issue_data: dict[str, Any] | None = None) -> str:
    """Invokes the Malakh for a discussion-only phase (Keter through Chesed)."""
    return run_gemini_comment_phase(prompt, repo=repo, issue=issue, phase=phase, session_scope=session_scope, issue_data=issue_data)


def run_json_phase(prompt: str, repo: str, issue: int, phase: str, session_scope: str, issue_data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Invokes the Malakh for a structured-output phase (Tiferet/Specification)."""
    return run_gemini_json_phase(prompt, repo=repo, issue=issue, phase=phase, session_scope=session_scope, issue_data=issue_data)


def run_implementation_phase(prompt: str, repo: str, issue: int, phase: str, session_scope: str, issue_data: dict[str, Any] | None = None) -> None:
    """Invokes the Malakh for code-modifying phases (Netzach through Yesod)."""
    run_gemini_implementation_phase(prompt, repo=repo, issue=issue, phase=phase, session_scope=session_scope, issue_data=issue_data)


def formalize_delivery_handoff(repo: str, issue: int, phase: str, issue_title: str, issue_data: dict[str, Any] | None = None) -> tuple[str, str]:
    """
    Commit and push changes, formalizing the handoff to the next phase.
    
    This marks the transition from 'work-in-progress' to a 'verifiable artifact'
    ready for the next Sfirat.
    """
    return finalize_phase_delivery(repo=repo, issue=issue, phase=phase, issue_title=issue_title, issue_data=issue_data)


def post_phase_signal_comment(signal: SfiratPhaseSignal, body: str) -> None:
    """
    Posts a wrapped phase comment back to the parent issue.
    
    These comments serve as the 'traceability anchor' for the entire workflow, 
    allowing humans to follow the generative logic of the system.
    """
    post_issue_comment(
        signal.repo,
        signal.issue,
        format_phase_comment(signal.phase, signal.label, body),
    )


def log_prompt_size_and_conversation_policy(prompt: str, phase: str) -> str:
    """Utility to log prompt metadata and session policy before agent invocation."""
    log_info(f"Prompt built ({len(prompt)} chars)")
    session_scope = conversation_scope_for_phase(phase)
    log_info(f"Session policy: {describe_phase_conversation_policy(phase, session_scope)}")
    return session_scope


def build_phase_prompt_and_conversation_scope(
    phase: str,
    builder: Callable[..., str],
    *args: Any,
) -> tuple[str, str]:
    """Orchestrates prompt building and session policy resolution."""
    prompt = builder(*args)
    return prompt, log_prompt_size_and_conversation_policy(prompt, phase)


def build_phase_execution_prompt(
    signal: SfiratPhaseSignal,
    prompt_builder: Callable[..., str],
) -> tuple[str, str]:
    """Builds the final system prompt for the Malakh using the active signal."""
    return build_phase_prompt_and_conversation_scope(
        signal.phase,
        prompt_builder,
        signal.label,
        signal.issue,
        signal.repo,
        signal.microagent_persona_content,
        signal.phase,
        signal.issue_data,
    )


def select_phase_prompt_builder(phase: str) -> Callable[..., str]:
    """Resolves the appropriate prompt construction strategy for the phase family."""
    if phase in DISCUSSION_PHASES:
        return build_comment_phase_prompt
    if phase == SPECIFICATION_PHASE:
        return build_tiferet_specification_prompt
    return build_implementation_phase_prompt


def execute_phase_with_needs_human_tagging(
    signal: SfiratPhaseSignal,
    executor: Callable[[SfiratPhaseSignal], None],
) -> None:
    """
    Executes a phase and ensures pre-implementation failures are flagged for humans.
    
    Before the workflow reaches the code-validation loop (Netzach), any failure 
    indicates a breakdown in discussion or specification that requires 
    explicit human intervention.
    """
    try:
        executor(signal)
    except SystemExit:
        if signal.phase in PRE_IMPLEMENTATION_PHASES:
            log_error(
                f"Phase {signal.phase.upper()} failed before Netzach; tagging issue for human intervention."
            )
            tag_issue_needs_human(signal.repo, signal.issue)
        raise


def execute_comment_phase_handoff(signal: SfiratPhaseSignal) -> None:
    """
    Orchestrates the comment-only loop for phases 1-3.
    
    Generates a philosophical or generative comment and advances the 
    issue label, signaling readiness for the next Sfirat.
    """
    log_info("Building discussion prompt...")
    prompt, session_scope = build_phase_execution_prompt(signal, build_comment_phase_prompt)

    log_info(f"Running agent for phase {signal.phase.upper()}...")
    comment = run_comment_phase(
        prompt,
        repo=signal.repo,
        issue=signal.issue,
        phase=signal.phase,
        session_scope=session_scope,
        issue_data=signal.issue_data,
    )
    log_info(f"Comment generated ({len(comment)} chars)")
    log_multiline("Generated comment", comment)

    log_info("Posting comment to GitHub...")
    post_phase_signal_comment(signal, comment)
    log_info("Comment posted")

    log_info("Advancing to next phase label...")
    advance_issue_label(signal.repo, signal.issue, signal.label)
    log_info("Label advanced")


def manifest_specification_decomposition(signal: SfiratPhaseSignal) -> None:
    """
    Manifests Phase 4 (Tiferet) by decomposing high-level intent into child issues.
    
    This is the 'Specification' phase of SPARC. It creates a hierarchy of 
    discrete tasks, each with its own Gherkin-style requirements, and 
    prepares the repository with implementation branches.
    """
    log_info("Building specification prompt...")
    prompt, session_scope = build_phase_execution_prompt(signal, build_tiferet_specification_prompt)

    log_info("Running agent for JSON payload...")
    payload = run_json_phase(
        prompt,
        repo=signal.repo,
        issue=signal.issue,
        phase=signal.phase,
        session_scope=session_scope,
        issue_data=signal.issue_data,
    )
    log_info("JSON payload received")

    log_info("Validating payload schema...")
    validate_tiferet_specification_payload_structure(payload)
    log_info("Validation passed")
    log_multiline("Generated parent comment", payload["comment"].strip())

    log_info("Posting parent comment...")
    post_phase_signal_comment(signal, payload["comment"].strip())
    log_info("Parent comment posted")

    # Decompose the parent intent into child issues.
    log_info(f"Creating {len(payload['sub_issues'])} ordered child issues with parent and dependency links...")
    created = create_child_issues(signal.repo, signal.issue, payload["sub_issues"])
    log_info(f"Created and linked {len(created)} child issues")
    
    # Pre-emptively create branches for each child task to ensure downstream traceability.
    child_issue_numbers = [int(item["number"]) for item in created]
    log_info("Creating child issue branches for downstream implementation phases...")
    create_issue_branches_for_child_issues(signal.repo, signal.issue, child_issue_numbers)
    log_info(f"Created/verified {len(child_issue_numbers)} child issue branches")

    log_info("Posting summary comment...")
    summary_comment = build_phase_four_summary(created)
    log_multiline("Generated summary comment", summary_comment)
    post_phase_signal_comment(signal, summary_comment)
    log_info("Summary comment posted")

    # Clear the parent label to signal that decomposition is complete.
    log_info("Completing Tiferet handoff: removing phase:tiferet label from parent issue...")
    remove_issue_label(signal.repo, signal.issue, signal.label)
    log_info("Parent issue label removed (handoff complete)")


def embody_implementation_contract(signal: SfiratPhaseSignal) -> None:
    """
    Embodies implementation phases (5-9) by translating intent into code.
    
    This follows the SPARC sequence: 
    -netzch (Traceability) 
    -hod (Pseudocode) 
    -yesod (Architecture/Refinement) 
    -malkhut (Completion/Validation).
    
    Each run includes an automated validation loop (build/test/lint).
    """
    log_info("Building agent prompt...")
    prompt, session_scope = build_phase_execution_prompt(signal, build_implementation_phase_prompt)

    log_info("Running agent...")
    run_implementation_phase(
        prompt,
        repo=signal.repo,
        issue=signal.issue,
        phase=signal.phase,
        session_scope=session_scope,
        issue_data=signal.issue_data,
    )
    log_info("Agent execution complete")
    
    # Delivery handoff formalizes the changes through a commit and push.
    log_info("Formalizing git delivery (commit + push)...")
    delivery_summary, diff_text = formalize_delivery_handoff(
        repo=signal.repo,
        issue=signal.issue,
        phase=signal.phase,
        issue_title=str(signal.issue_data.get("title") or ""),
        issue_data=signal.issue_data,
    )
    
    final_comment_body = delivery_summary
    if diff_text:
        log_info("Requesting LLM summary of committed code changes...")
        diff_prompt = build_diff_summary_prompt(diff_text)
        try:
            llm_summary = run_comment_phase(
                prompt=diff_prompt,
                repo=signal.repo,
                issue=signal.issue,
                phase=signal.phase,
                session_scope="Code summary pass",
                issue_data=None, # Keep context small
            )
            final_comment_body = f"{llm_summary}\n\n---\n\n{delivery_summary}"
        except SystemExit as e:
            log_error(f"Failed to generate LLM diff summary: {e}")
            # Fall back to just the delivery summary if the LLM fails here

    log_multiline("Final delivery summary", final_comment_body)
    
    # Posting the summary back to the issue preserves the traceability of the embodiment.
    log_info("Posting delivery summary comment...")
    post_phase_signal_comment(signal, final_comment_body)
    log_info("Delivery summary comment posted")
    
    # Move the signal to the next phase in the sequence.
    log_info("Advancing to next phase label...")
    advance_issue_label(signal.repo, signal.issue, signal.label)
    log_info("Label advanced")
