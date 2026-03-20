from __future__ import annotations

from typing import Optional

from .config import (
    DISCUSSION_PHASES,
    SPECIFICATION_PHASE,
)
from .context import resolve_phase_signal
from .execution import (
    embody_implementation_contract,
    execute_comment_phase_handoff,
    execute_phase_with_needs_human_tagging,
    manifest_specification_decomposition,
)
from .logging_utils import log_info, log_step
from .preview import preview_phase_execution_plan


def route_labeled_signal(label: Optional[str] = None, issue: Optional[int] = None, repo: Optional[str] = None) -> None:
    """
    Primary entry point for routing a labeled GitHub issue through the Sfirat phase sequence.
    
    This is the production path where the Malakh (agent) is invoked to process the 
    intent signal and move the workflow forward.
    """
    route_labeled_signal_with_mode(label=label, issue=issue, repo=repo, manual=False)


def route_labeled_signal_with_mode(
    label: Optional[str] = None,
    issue: Optional[int] = None,
    repo: Optional[str] = None,
    *,
    manual: bool = False,
) -> None:
    """
    Routes the labeled signal to its corresponding SPARC phase workflow.
    
    This function acts as the central dispatcher, resolving the runtime context 
    into a SfiratPhaseSignal and then delegating to the appropriate execution strategy.
    """
    # Formulate the intent signal by resolving repository, issue, and microagent context.
    # This represents the "Intent Formation" (Keter) of the orchestration itself.
    signal = resolve_phase_signal(
        label=label,
        issue=issue,
        repo=repo,
        manual=manual,
    )

    log_step("Step 4: Executing phase workflow")
    
    # Manual mode allows for a 'safe preview' where no mutations occur on GitHub 
    # and no LLM costs are incurred. It's used for structural validation of the plan.
    if manual:
        log_info("Manual mode: previewing prompt and planned actions only")
        preview_phase_execution_plan(signal)
        return

    # Phase Family 1: Discussion Phases (1-3)
    # These are comment-only loops used for Generative Expansion (Chokhmah) 
    # and Critical Restriction (Binah).
    if signal.phase in DISCUSSION_PHASES:
        log_info(f"Running discussion workflow for phase {signal.phase.upper()}")
        execute_phase_with_needs_human_tagging(
            signal,
            execute_comment_phase_handoff,
        )
        return

    # Phase Family 2: Specification (Phase 4 / Tiferet)
    # This is the "Mechanistic Grounding" where a high-level intent is decomposed
    # into a concrete set of child issues (SPARC: Specification).
    if signal.phase == SPECIFICATION_PHASE:
        log_info("Running specification workflow for phase 4")
        execute_phase_with_needs_human_tagging(
            signal,
            manifest_specification_decomposition,
        )
        return

    # Phase Family 3: Implementation (Phases 5-9)
    # This is where the signal is "Embodied" into the codebase. 
    # It follows the SPARC sequence: Traceability -> Pseudocode -> Architecture -> Refinement -> Completion.
    log_info(f"Running implementation workflow for phase {signal.phase.upper()}")
    embody_implementation_contract(signal)
