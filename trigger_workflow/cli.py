from __future__ import annotations

import argparse
import io
import sys
from contextlib import redirect_stdout
from typing import Optional

from .config import LABEL_PHASE_MAP, MICROAGENT_PERSONAS_DIR, WORKSPACE
from .context import resolve_phase_signal
from .execution import build_phase_execution_prompt, select_phase_prompt_builder
from .logging_utils import log_info, log_section
from .preview import render_prompt_only_output
from .orchestration import route_labeled_signal_with_mode


def label_for_phase_id(phase: str) -> str:
    """
    Resolves the canonical GitHub label for a given phase ID (e.g., '1', '2A', '10').
    
    This handles case-insensitive normalization for sub-phases (like 2A/2B/2C) 
    to ensure consistent mapping.
    """
    raw_phase = phase.strip()
    # Normalize sub-phase casing (2a -> 2A) to match config keys.
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


def run_trigger_cli() -> None:
    """
    Main CLI entry point for the swarm orchestrator.
    
    Parses arguments, resolves the target issue/label context, and routes
     the resulting signal to the appropriate SPARC phase workflow.
    """
    try:
        _run_trigger_cli_impl()
    except SystemExit as exc:
        if exc.args and isinstance(exc.args[0], str):
            from .logging_utils import log_error
            log_error(exc.args[0])
        raise


def _run_trigger_cli_impl() -> None:
    log_info("Starting swarm phase router CLI")
    parser = argparse.ArgumentParser(description="Trigger Swarm Phase / GitHub workflow")
    parser.add_argument("--label", help="GitHub label triggering the phase")
    parser.add_argument("--phase", help="Canonical phase id (1, 2A, 2B, 2C, 3, 4, 5, 6, 7, 8, 9, 10)")
    parser.add_argument("--issue", type=int, help="Issue number")
    parser.add_argument("--repo", help="Repository owner/repo")
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
    
    log_info(
        f"CLI arguments: label={args.label}, phase={args.phase}, issue={args.issue}, "
        f"repo={args.repo}, manual={args.manual}, prompt-only={args.prompt_only}"
    )
    
    # Allow users to specify either the label or the phase ID.
    resolved_label = args.label
    if args.phase:
        phase_label = label_for_phase_id(args.phase)
        # Prevent conflicting inputs if both are provided.
        if resolved_label and resolved_label != phase_label:
            raise SystemExit(
                f"Conflicting inputs: --label '{resolved_label}' does not match --phase '{args.phase}' "
                f"(expected label '{phase_label}')."
            )
        log_info(f"Mapped phase argument '{args.phase}' to label '{phase_label}'")
        resolved_label = phase_label

    # Prompt-only mode is used for debugging or manual execution of the agent 
    # outside of the orchestrated CLI.
    if args.prompt_only:
        log_info("Prompt-only mode: generating and outputting the phase prompt without running agent or mutating GitHub.")
        captured_logs = io.StringIO()
        try:
            # Capture logs to stderr so stdout only contains the prompt content.
            with redirect_stdout(captured_logs):
                log_info("Resolving phase execution request for prompt generation...")
                signal = resolve_phase_signal(
                    label=resolved_label,
                    issue=args.issue,
                    repo=args.repo,
                    manual=True,
                    include_base_persona=True,
                )
                prompt, _ = build_phase_execution_prompt(signal, select_phase_prompt_builder(signal.phase))
        except SystemExit:
            # Preserve log visibility on failure.
            print(captured_logs.getvalue(), file=sys.stderr)
            raise

        # Output prompt to stdout for piping or redirection.
        print(captured_logs.getvalue(), file=sys.stderr)
        print(render_prompt_only_output(signal, prompt))
        log_info("Prompt-only output generated")
        return

    log_section("SWARM PHASE ROUTER")
    log_info(f"Working directory: {WORKSPACE}")
    log_info(f"MicroagentPersonas directory: {MICROAGENT_PERSONAS_DIR}")

    # Dispatch to the orchestration layer.
    route_labeled_signal_with_mode(resolved_label, args.issue, args.repo, manual=args.manual)
    log_section("PHASE EXECUTION COMPLETE")
