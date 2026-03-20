from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .config import (
    PHASE_DISPLAY_NAME_MAP,
    STRICTLY_INDEPENDENT_PHASES,
    NEXT_LABEL_MAP,
)
from .github_ops import (
    ensure_phase_labels,
    fetch_issue_data,
    issue_has_label,
    issue_phase_labels,
    resolve_issue_by_label,
    resolve_oldest_phased_issue,
)
from .logging_utils import log_error, log_info, log_section, log_step
from .prompts import (
    determine_phase_from_label,
    read_microagent_for_label,
)


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
    """Return the session scope policy for the given phase."""
    if phase in STRICTLY_INDEPENDENT_PHASES:
        return f"phase-{phase}"
    return ""


def describe_phase_conversation_policy(phase: str, session_scope: str) -> str:
    """Describe whether the phase starts from an empty session or the shared per-issue session."""
    if session_scope:
        return (
            f"strictly independent phase session '{session_scope}' "
            "(starts with empty conversation context)"
        )
    return "shared per-issue session policy"


def detect_local_repo_name() -> str:
    """Attempt to detect the owner/repo name from the local git remote."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            text=True,
            capture_output=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout:
            url = result.stdout.strip()
            # Handle git@github.com:owner/repo.git or https://github.com/owner/repo.git
            if url.endswith(".git"):
                url = url[:-4]
            
            if "github.com" in url:
                url = url.split("github.com")[-1]
            if url.startswith(":") or url.startswith("/"):
                url = url[1:]
            
            parts = url.split("/")
            if len(parts) >= 2:
                return f"{parts[-2]}/{parts[-1]}"
    except Exception:
        pass
    return ""


def resolve_phase_execution_request(
    label: Optional[str] = None,
    issue: Optional[int] = None,
    repo: Optional[str] = None,
    *,
    manual: bool = False,
    include_base_persona: bool = True,
) -> PhaseExecutionRequest:
    """Resolve and validate issue/label context into a reusable phase execution request."""
    if not repo:
        repo = detect_local_repo_name()
    if not repo:
        raise SystemExit("Repository name could not be detected from git remote and was not provided via --repo.")
    
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
