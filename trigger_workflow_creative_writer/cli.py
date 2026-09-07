import argparse
import io
import sys
from contextlib import redirect_stdout

from . import config
from .config import MICROAGENTS_DIR, WORKSPACE
from .logging_utils import log_info, log_section
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
        choices=["codex", "gemini", "openhands"],
        default=config.RUNNER_TYPE,
        help="Codex only (default); Gemini/OpenHands disabled, integration unimplemented",
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
    parser.add_argument("--new-cycle", action="store_true", help="Explicitly restart Keter; preserve earlier cycles as history")
    recovery = parser.add_mutually_exclusive_group()
    recovery.add_argument("--performance-run", help="Resume an explicit performance UUID")
    recovery.add_argument("--new-performance", action="store_true", help="Start fresh sessions intentionally")
    parser.add_argument("--scene", help="Scene directory relative to target checkout (required for ambiguous issues)")
    parser.add_argument("--codex-model", help="Optional model override, pinned within a performance")
    parser.add_argument("--max-role-calls", type=int, default=120)
    parser.add_argument("--role-timeout", type=int, default=1200)
    parser.add_argument("--max-no-progress", type=int, default=6)
    args = parser.parse_args()
    
    # Override global RUNNER_TYPE with CLI argument
    config.RUNNER_TYPE = args.runner
    
    config.require_enabled_provider()
    if min(args.max_role_calls, args.role_timeout, args.max_no_progress) < 1:
        parser.error("Performance limits must be positive")
    config.PERFORMANCE_RUN = args.performance_run
    config.NEW_CYCLE = args.new_cycle
    config.NEW_PERFORMANCE = args.new_performance
    config.SCENE_PATH = args.scene
    config.CODEX_MODEL = args.codex_model
    config.MAX_ROLE_CALLS = args.max_role_calls
    config.ROLE_TIMEOUT = args.role_timeout
    config.MAX_NO_PROGRESS = args.max_no_progress

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
        log_info("Prompt-only mode: generating the phase prompt without running Codex or mutating GitHub.")
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
    
    run_labeled_issue_phase_with_mode(resolved_label, args.issue, args.repo, manual=args.manual)
    log_section("PHASE EXECUTION COMPLETE")
