#!/usr/bin/env python3
"""
GitHub Label -> SDLC Phase Router
Triggers OpenHands based on GitHub issue/PR labels.

Usage from OpenClaw:
    python trigger.py --label <label> [--issue <issue_number>] [--repo <owner/repo>]

Example:
    python trigger.py --label feature --issue 123
    python trigger.py --label bug --repo myorg/myrepo
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional


# Label -> Phase mapping (SPARC Methodology)
# Phases 1-4: GitHub discussion phases (no OpenHands workflow)
# Phase 4: Creates PR with requirements documents
# Phases 5-9: All work on same PR created in Phase 4
LABEL_PHASE_MAP = {
    # Discussion phases (GitHub comments only)
    "phase:keter": 1,
    "phase:chokhmah": 2,
    "phase:binah": 2,
    "phase:chesed": 2,
    "phase:gevurah": 3,
    # Specification phase (creates PR with requirements.md, DoD, non-goals.md)
    "phase:tiferet": 4,
    # Implementation phases (work on PR from Phase 4)
    "phase:netzach": 5,   # Traceability - Map specs to system
    "phase:hod": 6,       # Pseudocode - Derive logic flow
    "phase:yesod-orchestration": 7,  # Architecture - File structure & schemas
    "phase:yesod-embodiment": 8,     # Refinement - Implementation
    "phase:malkhut": 9,   # Completion - Verification & validation
}

WORKSPACE = Path(__file__).parent


def trigger_phase(label: str, issue: Optional[int] = None) -> None:
    """Trigger the appropriate OpenHands phase."""
    phase = LABEL_PHASE_MAP.get(label)
    if not phase:
        print(f"Unknown label '{label}'. No phase configured.")
        print(f"Available labels: {', '.join(LABEL_PHASE_MAP.keys())}")
        return

    print(f"Label '{label}' -> Phase {phase}")
    run_openhands(phase, issue)


def get_openhands_cmd(phase: int, issue: Optional[int] = None) -> list[str]:
    """Build the OpenHands command."""
    run_script = WORKSPACE / "run_phase.sh"
    cmd = [str(run_script), str(phase)]
    if issue:
        cmd.append(str(issue))
    return cmd


def run_openhands(phase: int, issue: Optional[int] = None) -> None:
    """Execute OpenHands with the given phase."""
    run_script = WORKSPACE / "run_phase.sh"
    if not run_script.exists():
        print(f"run_phase.sh not found at {run_script}")
        return

    # Read state file from config
    config_file = WORKSPACE / ".openhands" / "config.json"
    state_file = "workspace/.sdlc-state.json"

    try:
        with open(config_file) as f:
            config = json.load(f)
            state_file = config.get("state_file", "workspace/.sdlc-state.json")
    except Exception:
        pass

    # Update state before running
    state_path = WORKSPACE / state_file
    state_path.parent.mkdir(parents=True, exist_ok=True)
    
    state = {
        "current_phase": phase,
        "current_step": 0,
        "last_issue": issue,
        "artifacts": {},
    }
    
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)

    print(f"Updated state file: {state_path}")

    # Execute the phase
    cmd = get_openhands_cmd(phase, issue)
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(WORKSPACE), capture_output=True, text=True)
    
    print(result.stdout)
    if result.stderr:
        print(f"STDERR: {result.stderr}")
    print(f"Exit code: {result.returncode}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="GitHub Label -> SDLC Phase Router")
    parser.add_argument("--label", required=True, help="GitHub label triggering the phase")
    parser.add_argument("--issue", type=int, help="Issue number (optional)")
    parser.add_argument("--repo", help="Repository owner/repo (optional)")
    
    args = parser.parse_args()
    
    trigger_phase(args.label, args.issue)


if __name__ == "__main__":
    main()