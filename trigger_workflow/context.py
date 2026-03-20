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
    read_microagent_persona_for_label,
)


@dataclass(frozen=True)
class SfiratPhaseSignal:
    """
    The immutable payload carrying the intent and context of a SPARC phase.
    
    This 'Signal' is the primary object moving through the orchestrator.
    It encapsulates the metadata (repo, issue, label) and the prompt content 
    (microagent_persona + personas) required for the Malakh (agent) to act.
    """

    label: str
    issue: int
    repo: str
    microagent_persona_content: str
    phase: str
    issue_data: dict[str, Any]


def conversation_scope_for_phase(phase: str) -> str:
    """
    Returns the session scope policy for the given phase.
    
    Phases marked as 'strictly independent' start with a fresh, empty session context. 
    Others share a persistent per-issue conversation.
    """
    if phase in STRICTLY_INDEPENDENT_PHASES:
        return f"phase-{phase}"
    return ""


def describe_phase_conversation_policy(phase: str, session_scope: str) -> str:
    """Provides a human-readable description of the session policy for logging."""
    if session_scope:
        return (
            f"strictly independent phase session '{session_scope}' "
            "(starts with empty conversation context)"
        )
    return "shared per-issue session policy"


def detect_local_repo_name() -> str:
    """
    Attempts to detect the owner/repo name from the local git remote.
    
    This ensures the swarm can be run from within any target repository without 
    manual repository name input.
    """
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
            # Handles both SSH (git@github.com:owner/repo.git) 
            # and HTTPS (https://github.com/owner/repo.git) formats.
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


def resolve_phase_signal(
    label: Optional[str] = None,
    issue: Optional[int] = None,
    repo: Optional[str] = None,
    *,
    manual: bool = False,
    include_base_persona: bool = True,
) -> SfiratPhaseSignal:
    """
    Resolves and validates the 'SfiratPhaseSignal' context for a phase.
    
    This is the 'Intent Formation' (Keter) step where we gather the necessary context
    to perform a phase handoff. It validates repository name, issue labels, and phase
    mappings before the Malakh is called.
    """
    # 1. Ensure we have a target repository.
    if not repo:
        repo = detect_local_repo_name()
    if not repo:
        raise SystemExit("Repository name could not be detected from git remote and was not provided via --repo.")
    
    log_section("STARTING PHASE EXECUTION")
    log_info(f"Repository: {repo}")

    # Step 0: Pre-sync label metadata. 
    # This prevents the workflow from failing on missing repository labels.
    if manual:
        log_step("Step 0: Manual mode enabled")
        log_info("Skipping canonical phase label synchronization to avoid GitHub mutations")
    else:
        log_step("Step 0: Ensuring canonical phase labels exist")
        ensure_phase_labels(repo)

    # Step 1: Resolve the specific issue and label to work on.
    log_step("Step 1: Resolving issue and label context")
    if issue is None and label is None:
        # Automatic discovery: pick the oldest issue waiting for attention.
        log_info("No issue or label provided; finding oldest phased issue...")
        issue, label = resolve_oldest_phased_issue(repo)
        log_info(f"Selected issue #{issue} with label '{label}'")
    elif issue is None and label is not None:
        # Search for any issue that carries this label.
        log_info(f"Label '{label}' provided; finding oldest issue carrying this label...")
        issue = resolve_issue_by_label(repo, label)
        log_info(f"Selected issue #{issue} for label '{label}'")
    elif issue is not None and label is None:
        # We have an issue but no label; resolve it from metadata.
        log_info(f"Issue #{issue} provided; resolving phase label from issue metadata...")
    else:
        # Manual selection: verify the label exists on the issue.
        log_info(f"Issue #{issue} and label '{label}' provided; will verify label on issue...")

    # Step 2: Fetch the core metadata for the issue.
    log_step("Step 2: Fetching issue data from GitHub")
    issue_data = fetch_issue_data(repo, issue)
    log_info(f"Issue #{issue} fetched: '{issue_data.get('title', 'Unknown')}'")

    # Step 2.1: Final label resolution.
    if label is None:
        # Ensure the issue has exactly one phase label.
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
        # Label verification ensures we don't accidentally process an issue 
        # that isn't ready for this phase.
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

    # Step 3: Determine the Phase ID.
    log_step("Step 3: Determining phase id")
    phase = determine_phase_from_label(label)
    if not phase:
        raise SystemExit(f"Unknown label '{label}'. Cannot determine phase.")
    log_info(f"Label '{label}' → Phase {phase.upper()} ({PHASE_DISPLAY_NAME_MAP.get(phase, 'Unknown')})")

    # Step 3.1: Log handoff context. 
    # This helps humans understand where the signal is in the sequence.
    log_step("Sequence Context")
    log_info(f"Current: Phase {phase.upper()}")
    next_phase_label = NEXT_LABEL_MAP.get(label, "")
    next_phase = determine_phase_from_label(next_phase_label) if next_phase_label else None
    if next_phase:
        log_info(f"Next: Phase {next_phase.upper()} ({PHASE_DISPLAY_NAME_MAP.get(next_phase, 'Unknown')})")
    else:
        log_info("Next: Final phase (no further handoff)")

    # Step 4: Compose the prompt for the Malakh.
    log_step("Step 4: Reading microagent_persona prompt")
    microagent_persona_content = read_microagent_persona_for_label(label, phase, include_base_persona=include_base_persona)
    log_info(f"MicroagentPersona prompt loaded ({len(microagent_persona_content)} bytes)")

    label_names = [l.get("name", "") for l in issue_data.get("labels", []) if l.get("name")]
    log_info(f"Current labels: {', '.join(label_names) if label_names else '(none)'}")

    # Build and return the completed SfiratPhaseSignal.
    signal = SfiratPhaseSignal(
        label=label,
        issue=issue,
        repo=repo,
        microagent_persona_content=microagent_persona_content,
        phase=phase,
        issue_data=issue_data,
    )
    return signal
