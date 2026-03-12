#!/usr/bin/env python3
"""
GitHub Label -> SDLC Phase Router
Triggers OpenHands based on GitHub issue/PR labels.

Usage from OpenClaw:
    python trigger.py --label <label> [--issue <issue_number>] [--repo <owner/repo>]

Example:
    python trigger.py --label feature --issue 123
    python trigger.py --label bug --repo myorg/myrepo

PHASE-AGNOSTIC DESIGN:
This script only routes labels to phase numbers. The actual work is delegated
to phase-specific microagents (in .openhands/microagents/).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional


# Add workspace to path to import agent
WORKSPACE = Path(__file__).parent
sys.path.insert(0, str(WORKSPACE))

from agent import SDLCPhasedAgent


# Label -> Phase mapping (SPARC Methodology)
LABEL_PHASE_MAP = {
    # Discussion/Clarification phases (output to GitHub)
    "phase:keter": 1,              # Intent Formation - clarify and comment
    "phase:chokhmah": 2,          # Expansion - user stories
    "phase:binah": 2,             # Restriction - constraints
    "phase:chesed": 2,            # Grounding - feasibility
    "phase:gevurah": 3,           # Synthetic Judgment - converge
    # Specification phase (creates PR with docs)
    "phase:tiferet": 4,           # Specification - requirements.md, DoD, non-goals.md
    # Implementation phases (work on PR from Phase 4)
    "phase:netzach": 5,           # Traceability - E2E skeletons
    "phase:hod": 6,               # Pseudocode - algorithm comments
    "phase:yesod-orchestration": 7,  # Architecture - file structure
    "phase:yesod-embodiment": 8,     # Refinement - implementation
    "phase:malkhut": 9,           # Completion - validation
}

WORKSPACE = Path(__file__).parent
MICROAGENTS_DIR = WORKSPACE / ".openhands" / "microagents"


def trigger_phase(label: str, issue: Optional[int] = None, repo: Optional[str] = None) -> None:
    """
    Phase-agnostic router - maps label to phase, then triggers agentic work.
    
    This function does NOT do the work itself. It:
    1. Maps label → phase number
    2. Reads the phase microagent prompt
    3. Delegates to OpenHands or github-script based on phase type
    """
    phase = LABEL_PHASE_MAP.get(label)
    if not phase:
        print(f"Unknown label '{label}'. No phase configured.")
        print(f"Available labels: {', '.join(LABEL_PHASE_MAP.keys())}")
        return

    print(f"Label '{label}' -> Phase {phase}")
    
    # Read microagent prompt (the actual phase intelligence)
    microagent_pattern = f"phase_{phase:02d}*.md"
    microagent_files = list(MICROAGENTS_DIR.glob(microagent_pattern))
    
    if not microagent_files:
        print(f"No microagent found for Phase {phase} with pattern '{microagent_pattern}'")
        return
    
    microagent_file = microagent_files[0]
    print(f"Using microagent: {microagent_file}")
    
    with open(microagent_file) as f:
        microagent_content = f.read()
    
    # Phase 1-4: Discussion phases (GitHub comment only)
    # Phase 5-9: Code/PR phases (OpenHands workflow)
    if phase <= 4:
        run_discussion_phase(phase, label, issue, repo, microagent_content)
    else:
        run_workflow_phase(phase, label, issue, repo, microagent_content)


def run_discussion_phase(
    phase: int, label: str, issue: Optional[int], repo: Optional[str], microagent: str
) -> None:
    """Run discussion phase (1-4) - posts comment to GitHub issue."""
    if not issue:
        print(f"ERROR: --issue required for Phase {phase} discussion")
        return
    
    repo = repo or "fedevela/particle-life-3d"
    
    print(f"Phase {phase} is GitHub discussion phase")
    print("Routing to OpenHands agent for analysis...")
    
    # Build prompt with issue context
    prompt = f"""{microagent}

## Runtime Context
- Repository: {repo}
- Issue number: #{issue}
- Trigger label: {label}
- Mode: headless discussion

Please read the issue, perform the phase analysis, and post a single GitHub comment
with your thoughts and any changes made."""

    # For discussion phases, we could:
    # 1. Use OpenHands agent (if API configured)
    # 2. Use github-script to run local analysis
    
    # Current approach: generate comment placeholder
    # TODO: Integrate with actual agent for Phase 1-4 analysis
    print(f"Prompt prepared for Phase {phase} agent")
    print(f"Prompt preview: {prompt[:500]}...")
    print("Note: Full agent integration requires OpenHands API or local agent setup")


def run_workflow_phase(
    phase: int, label: str, issue: Optional[int], repo: Optional[str], microagent: str
) -> None:
    """Run workflow phase (5-9) - OpenHands PR work."""
    run_script = WORKSPACE / "run_phase.sh"
    if not run_script.exists():
        print(f"run_phase.sh not found at {run_script}")
        return
    
    cmd = [str(run_script), str(phase)]
    if issue:
        cmd.append(str(issue))
    
    print(f"Running OpenHands workflow for Phase {phase}...")
    print("The agent will:")
    print("1. Read Phase 4 requirements (child issues)")
    print("2. Create/modify PR with E2E tests, pseudocode, architecture")
    print("3. Post single GitHub comment with summary")
    
    result = subprocess.run(cmd, cwd=str(WORKSPACE), capture_output=True, text=True)
    
    print(result.stdout)
    if result.stderr:
        print(f"STDERR: {result.stderr}")
    print(f"Exit code: {result.returncode}")


def main():
    """Main entry point - phase-agnostic label routing."""
    parser = argparse.ArgumentParser(description="GitHub Label -> SDLC Phase Router")
    parser.add_argument("--label", required=True, help="GitHub label triggering the phase")
    parser.add_argument("--issue", type=int, help="Issue number (optional)")
    parser.add_argument("--repo", help="Repository owner/repo (optional)")
    
    args = parser.parse_args()
    
    trigger_phase(args.label, args.issue, args.repo)


if __name__ == "__main__":
    main()
