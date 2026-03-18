import argparse
import io
import sys
from contextlib import redirect_stdout

from . import config
from .config import MICROAGENTS_DIR, WORKSPACE
from .logging_utils import log_info, log_section
from .openhands_runner import resolve_openhands_model_connection
from .core import (
    build_phase_execution_prompt,
    label_for_phase_id,
    render_prompt_only_output,
    resolve_phase_execution_request,
    run_labeled_issue_phase_with_mode,
    select_phase_prompt_builder,
)

def run_trigger_cli(mode: str = "creative-writer") -> None:
    """Main entry point."""
    log_info("Starting swarm phase router CLI")
    parser = argparse.ArgumentParser(description=f"Trigger Swarm Phase / GitHub workflow (Mode: {mode})")
    parser.add_argument("--mode", type=str, choices=["sdlc", "creative-writer"], default=mode, help="The operating mode of the swarm")
    parser.add_argument("--label", help="GitHub label triggering the phase")
    parser.add_argument("--phase", help="Canonical phase id (1, 2A, 2B, 2C, 3, 4, 5, 6, 7, 8, 9, 10)")
    parser.add_argument("--issue", type=int, help="Issue number")
    parser.add_argument("--repo", help="Repository owner/repo")
    parser.add_argument(
        "--runner",
        choices=["gemini", "openhands"],
        default=config.RUNNER_TYPE,
        help=f"Runner to use for phase execution (default: {config.RUNNER_TYPE})",
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
    config.RUNNER_TYPE = args.runner
    
    if config.RUNNER_TYPE == "openhands":
        sys.exit("Error: The 'creative-writer' mode currently only supports the 'gemini' runner.")

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
    log_info(f"Active runner: {config.RUNNER_TYPE}")
    
    if config.RUNNER_TYPE == "openhands":
        model_name, connection = resolve_openhands_model_connection()
        log_info(f"OpenHands model connection: {connection}")
        log_info(f"OpenHands model name: {model_name}")

    run_labeled_issue_phase_with_mode(resolved_label, args.issue, args.repo, manual=args.manual)
    log_section("PHASE EXECUTION COMPLETE")
