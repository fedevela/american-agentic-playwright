from __future__ import annotations

import argparse
import sys
from typing import Any, Optional

from .config import (
    DEFAULT_REPO,
    DISCUSSION_PHASES,
    MICROAGENTS_DIR,
    NEXT_LABEL_MAP,
    PHASE_DISPLAY_NAME_MAP,
    SPECIFICATION_PHASE,
    WORKSPACE,
)
from .github_ops import (
    advance_issue_label,
    create_child_issues,
    ensure_phase_labels,
    fetch_issue_data,
    issue_has_label,
    post_issue_comment,
    resolve_issue_by_label,
    resolve_oldest_phased_issue,
)
from .logging_utils import log_error, log_info, log_section, log_step
from .openhands_runner import run_openhands_for_comment, run_openhands_for_json, run_openhands_task
from .prompts import (
    build_agent_prompt,
    build_discussion_prompt,
    build_phase_four_summary,
    build_spec_prompt,
    determine_phase_from_label,
    format_phase_comment,
    read_microagent_for_label,
)
from .validation import validate_phase_four_payload


def trigger_agent(label: Optional[str] = None, issue: Optional[int] = None, repo: Optional[str] = None) -> None:
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
        log_error(f"Unknown label '{label}'. Cannot determine phase.")
        sys.exit(1)
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
    if not microagent_content:
        log_error(f"No microagent found for label '{label}'.")
        sys.exit(1)
    log_info(f"Microagent prompt loaded ({len(microagent_content)} bytes)")

    log_step("Step 3: Fetching issue data from GitHub")
    issue_data = fetch_issue_data(repo, issue)
    if not issue_data:
        log_error(f"Could not fetch issue #{issue} from {repo}.")
        sys.exit(1)
    log_info(f"Issue #{issue} fetched: '{issue_data.get('title', 'Unknown')}'")
    label_names = [l.get("name", "") for l in issue_data.get("labels", []) if l.get("name")]
    log_info(f"Current labels: {', '.join(label_names) if label_names else '(none)'}")

    if not issue_has_label(issue_data, label):
        log_error(f"Issue #{issue} in {repo} is not labeled '{label}'. Skipping phase execution.")
        sys.exit(1)
    log_info("Label verification: PASSED")

    log_step("Step 4: Executing phase workflow")
    if phase in DISCUSSION_PHASES:
        log_info(f"Running discussion workflow for phase {phase.upper()}")
        _execute_discussion_phase(label, issue, repo, microagent_content, phase, issue_data)
        return

    if phase == SPECIFICATION_PHASE:
        log_info("Running specification workflow for phase 4")
        _execute_specification_phase(label, issue, repo, microagent_content, phase, issue_data)
        return

    log_info(f"Running implementation workflow for phase {phase.upper()}")
    _execute_agent_phase(label, issue, repo, microagent_content, phase, issue_data)


def _execute_discussion_phase(
    label: str, issue: int, repo: str, microagent_content: str, phase: str, issue_data: dict[str, Any]
) -> None:
    """Execute comment-only phases by generating and posting a phase comment."""
    log_info("Building discussion prompt...")
    prompt = build_discussion_prompt(label, issue, repo, microagent_content, phase, issue_data)
    log_info(f"Prompt built ({len(prompt)} chars)")

    log_info(f"Running OpenHands for phase {phase.upper()}...")
    comment = run_openhands_for_comment(prompt, repo=repo, issue=issue, phase=phase)
    log_info(f"Comment generated ({len(comment)} chars)")

    log_info("Posting comment to GitHub...")
    post_issue_comment(repo, issue, format_phase_comment(phase, label, comment))
    log_info("Comment posted")

    log_info("Advancing to next phase label...")
    advance_issue_label(repo, issue, label)
    log_info("Label advanced")


def _execute_specification_phase(
    label: str, issue: int, repo: str, microagent_content: str, phase: str, issue_data: dict[str, Any]
) -> None:
    """Execute phase 4/Tiferet by generating a parent comment and child issues."""
    log_info("Building specification prompt...")
    prompt = build_spec_prompt(label, issue, repo, microagent_content, phase, issue_data)
    log_info(f"Prompt built ({len(prompt)} chars)")

    log_info("Running OpenHands for JSON payload...")
    payload = run_openhands_for_json(prompt, repo=repo, issue=issue, phase=phase)
    log_info("JSON payload received")

    log_info("Validating payload schema...")
    validate_phase_four_payload(payload)
    log_info("Validation passed")

    log_info("Posting parent comment...")
    post_issue_comment(repo, issue, format_phase_comment(phase, label, payload["comment"].strip()))
    log_info("Parent comment posted")

    log_info(f"Creating {len(payload['sub_issues'])} ordered child issues with parent and dependency links...")
    created = create_child_issues(repo, issue, payload["sub_issues"])
    log_info(f"Created and linked {len(created)} child issues")

    log_info("Posting summary comment...")
    post_issue_comment(repo, issue, format_phase_comment(phase, label, build_phase_four_summary(created)))
    log_info("Summary comment posted")


def _execute_agent_phase(
    label: str, issue: int, repo: str, microagent_content: str, phase: str, issue_data: dict[str, Any]
) -> None:
    """Execute phases 5-9 headlessly in OpenHands."""
    log_info("Building agent prompt...")
    prompt = build_agent_prompt(label, issue, repo, microagent_content, phase, issue_data)
    log_info(f"Prompt built ({len(prompt)} chars)")

    log_info("Running OpenHands agent...")
    run_openhands_task(prompt, repo=repo, issue=issue, phase=phase)
    log_info("Agent execution complete")


def main() -> None:
    """Main entry point."""
    log_section("OPENHANDS SWARM PHASE ROUTER")
    log_info(f"Working directory: {WORKSPACE}")
    log_info(f"Microagents directory: {MICROAGENTS_DIR}")

    parser = argparse.ArgumentParser(description="Trigger OpenHands / GitHub phase workflow")
    parser.add_argument("--label", help="GitHub label triggering the phase")
    parser.add_argument("--issue", type=int, help="Issue number")
    parser.add_argument("--repo", help="Repository owner/repo")
    args = parser.parse_args()

    trigger_agent(args.label, args.issue, args.repo)
    log_section("PHASE EXECUTION COMPLETE")
