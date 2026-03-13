#!/usr/bin/env python3
"""
GitHub Label -> Phase Router

Workflow:
- Phases 1, 2A, 2B, 2C, and 3: ask OpenHands for a phase response, then post
  that response as a GitHub issue comment.
- Phase 4: ask OpenHands for a JSON payload containing a parent comment and one
  or more child issues, post the comment, then create the child issues.
- Phases 5-9: run OpenHands headlessly for implementation/validation work.

Phase sequence: 1→2a→2b→2c→3→4→5→6→7→8→9
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

WORKSPACE = Path(__file__).parent
MICROAGENTS_DIR = WORKSPACE / ".openhands" / "microagents"
PERSONAS_DIR = WORKSPACE / "personas"
DEFAULT_REPO = "fedevela/particle-life-3d"
SESSION_STATE_PATH = WORKSPACE / "workspace" / ".session-state.json"
PHASE_DISPLAY_NAME_MAP = {
    "1": "Keter",
    "2a": "Chokhmah",
    "2b": "Binah",
    "2c": "Chesed",
    "3": "Gevurah",
    "4": "Tiferet",
    "5": "Netzach",
    "6": "Hod",
    "7": "Yesod-Orchestration",
    "8": "Yesod-Embodiment",
    "9": "Malkhut",
}
PHASE_LABEL_METADATA = {
    "phase:keter": {
        "description": "Phase 1 Keter: Intent Formation",
        "color": "6E7781",
    },
    "phase:chokhmah": {
        "description": "Phase 2A Chokhmah: Generative Expansion",
        "color": "A0522D",
    },
    "phase:binah": {
        "description": "Phase 2B Binah: Critical Restriction",
        "color": "B65C00",
    },
    "phase:chesed": {
        "description": "Phase 2C Chesed: Mechanistic Grounding",
        "color": "C2A000",
    },
    "phase:gevurah": {
        "description": "Phase 3 Gevurah: Synthetic Judgment",
        "color": "BF8700",
    },
    "phase:tiferet": {
        "description": "Phase 4 Tiferet: SPARC Specification",
        "color": "1A7F37",
    },
    "phase:netzach": {
        "description": "Phase 5 Netzach: Traceability",
        "color": "0E8A16",
    },
    "phase:hod": {
        "description": "Phase 6 Hod: SPARC Pseudocode",
        "color": "0969DA",
    },
    "phase:yesod-orchestration": {
        "description": "Phase 7 Yesod-Orchestration: SPARC Architecture",
        "color": "5319E7",
    },
    "phase:yesod-embodiment": {
        "description": "Phase 8 Yesod-Embodiment: SPARC Refinement",
        "color": "8250DF",
    },
    "phase:malkhut": {
        "description": "Phase 9 Malkhut: SPARC Completion",
        "color": "D1242F",
    },
}
NEXT_LABEL_MAP = {
    "phase:keter": "phase:chokhmah",
    "phase:chokhmah": "phase:binah",
    "phase:binah": "phase:chesed",
    "phase:chesed": "phase:gevurah",
    "phase:gevurah": "phase:tiferet",
    "phase:tiferet": "phase:netzach",
    "phase:netzach": "phase:hod",
    "phase:hod": "phase:yesod-orchestration",
    "phase:yesod-orchestration": "phase:yesod-embodiment",
    "phase:yesod-embodiment": "phase:malkhut",
    "phase:malkhut": None,
}
PHASE_LABELS = tuple(NEXT_LABEL_MAP.keys())
PERSONA_FILE_MAP = {
    "1": "phase_01.1_keter.md",
    "2a": "phase_02.1_chokhmah.md",
    "2b": "phase_02.2_binah.md",
    "2c": "phase_02.3_chesed.md",
    "3": "phase_03_gevurah.md",
    "4": "phase_04_tiferet.md",
    "5": "phase_05_netzach.md",
    "6": "phase_06_hod.md",
    "7": "phase_07_yesod.md",
    "8": "phase_08_yesod.md",
    "9": "phase_09_malkhut.md",
}
LEGACY_MICROAGENT_FILE_MAP = {
    "1": "phase_01_keter.md",
    "2a": "phase_02_chokhmah.md",
    "2b": "phase_03_binah.md",
    "2c": "phase_04_chesed.md",
    "3": "phase_05_gevurah.md",
    "4": "phase_06_tiferet.md",
    "5": "phase_07_netzach.md",
    "6": "phase_08_hod.md",
    "7": "phase_09_yesod_orchestration.md",
    "8": "phase_10_yesod_embodiment.md",
    "9": "phase_11_malkhut.md",
}
BASE_PERSONA_FILE = "daneel.md"


def log_section(title: str) -> None:
    """Print a visible section divider for the console."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def log_step(step: str) -> None:
    """Print a step marker for the console."""
    print(f"\n[✓] {step}")


def log_info(msg: str) -> None:
    """Print an info message."""
    print(f"    → {msg}")


def log_error(msg: str) -> None:
    """Print an error message."""
    print(f"    ! {msg}")


def trigger_agent(label: Optional[str] = None, issue: Optional[int] = None, repo: Optional[str] = None) -> None:
    """Route the label to the correct phase workflow."""
    repo = repo or DEFAULT_REPO
    log_section("STARTING PHASE EXECUTION")
    log_info(f"Repository: {repo}")

    log_step("Step 0: Ensuring canonical phase labels exist")
    ensure_phase_labels(repo)

    # Resolve the target issue/label pair before any phase-specific work begins.
    log_step("Step 1a: Resolving issue and label")
    if label is None:
        log_info("No label provided, finding oldest phased issue...")
        issue, label = resolve_oldest_phased_issue(repo)
        log_info(f"Selected issue #{issue} with label '{label}'")

    # Convert the GitHub label into the canonical phase identifier.
    log_step("Step 1b: Determining phase id")
    phase = determine_phase_from_label(label)
    if not phase:
        log_error(f"Unknown label '{label}'. Cannot determine phase.")
        sys.exit(1)
    log_info(f"Label '{label}' → Phase {phase.upper()} ({PHASE_DISPLAY_NAME_MAP.get(phase, 'Unknown')})")

    # When only a label is provided, the workflow requires exactly one matching issue.
    log_step("Step 1c: Resolving issue number")
    if issue is None:
        log_info(f"Finding issue with label '{label}'...")
        issue = resolve_issue_by_label(repo, label)
    log_info(f"Issue number: #{issue}")

    # Show the current handoff position before any remote calls are made.
    log_step("Sequence Context")
    log_info(f"Current: Phase {phase.upper()}")
    next_phase = determine_phase_from_label(NEXT_LABEL_MAP.get(label, ""))
    if next_phase:
        log_info(f"Next: Phase {next_phase.upper()} ({PHASE_DISPLAY_NAME_MAP.get(next_phase, 'Unknown')})")
    else:
        log_info("Next: Final phase (no further handoff)")

    # Load the persona prompt that will shape this phase's output.
    log_step("Step 2: Reading microagent prompt")
    microagent_content = read_microagent_for_label(label, phase)
    if not microagent_content:
        log_error(f"No microagent found for label '{label}'.")
        sys.exit(1)
    log_info(f"Microagent prompt loaded ({len(microagent_content)} bytes)")

    # Fetch the issue state once so downstream helpers can work from one payload.
    log_step("Step 3: Fetching issue data from GitHub")
    issue_data = fetch_issue_data(repo, issue)
    if not issue_data:
        log_error(f"Could not fetch issue #{issue} from {repo}.")
        sys.exit(1)
    log_info(f"Issue #{issue} fetched: '{issue_data.get('title', 'Unknown')}'")
    label_names = [l.get("name", "") for l in issue_data.get("labels", []) if l.get("name")]
    log_info(f"Current labels: {', '.join(label_names) if label_names else '(none)'}")

    # Abort if the live issue state no longer matches the triggering label.
    if not issue_has_label(issue_data, label):
        log_error(f"Issue #{issue} in {repo} is not labeled '{label}'. Skipping phase execution.")
        sys.exit(1)
    log_info("Label verification: PASSED")

    # Delegate to the workflow implementation for the resolved phase.
    log_step("Step 4: Executing phase workflow")

    if phase in {"1", "2a", "2b", "2c", "3"}:
        log_info(f"Running discussion workflow for phase {phase.upper()}")
        _execute_discussion_phase(label, issue, repo, microagent_content, phase, issue_data)
        return

    if phase == "4":
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

    log_info(f"Running OpenHands for phase {phase}...")
    comment = run_openhands_for_comment(prompt, repo=repo, issue=issue)
    log_info(f"Comment generated ({len(comment)} chars)")

    log_info("Posting comment to GitHub...")
    post_issue_comment(repo, issue, format_phase_comment(phase, label, comment))
    log_info("Comment posted")

    log_info("Advancing to next phase label...")
    advance_issue_label(repo, issue, label, phase)
    log_info("Label advanced")


def _execute_specification_phase(
    label: str, issue: int, repo: str, microagent_content: str, phase: str, issue_data: dict[str, Any]
) -> None:
    """Execute phase 4/Tiferet by generating a parent comment and child issues."""
    log_info("Building specification prompt...")
    prompt = build_spec_prompt(label, issue, repo, microagent_content, phase, issue_data)
    log_info(f"Prompt built ({len(prompt)} chars)")

    log_info("Running OpenHands for JSON payload...")
    payload = run_openhands_for_json(prompt, repo=repo, issue=issue)
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
    run_openhands_task(prompt, repo=repo, issue=issue)
    log_info("Agent execution complete")


def fetch_issue_data(repo: str, issue_number: int) -> dict[str, Any]:
    """Fetch the issue payload used by prompt construction and label checks."""
    log_info(f"Fetching issue #{issue_number} with labels and comments")
    result = run_gh(
        ["issue", "view", str(issue_number), "--repo", repo, "--json", "id,title,body,number,labels,comments"],
        capture_output=True,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        details = stderr or stdout or "gh returned no output"
        raise SystemExit(f"Failed to fetch issue #{issue_number} from {repo}: {details}")
    if not result.stdout:
        raise SystemExit(f"Failed to fetch issue #{issue_number} from {repo}: gh returned empty output.")
    return json.loads(result.stdout)


def fetch_repo_labels(repo: str) -> list[dict[str, Any]]:
    """Fetch repository label metadata from GitHub."""
    log_info("Fetching repository label metadata")
    result = run_gh(
        ["label", "list", "--repo", repo, "--json", "name,description,color"],
        capture_output=True,
    )
    if result.returncode != 0 or not result.stdout:
        raise SystemExit(f"Could not query labels in {repo}.")

    labels = json.loads(result.stdout)
    if not isinstance(labels, list):
        raise SystemExit(f"Invalid label payload for {repo}.")
    return labels


def ensure_phase_labels(repo: str) -> None:
    """Create or repair the canonical phase labels required by the workflow."""
    existing_labels = fetch_repo_labels(repo)
    existing_by_name = {
        item["name"]: item
        for item in existing_labels
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    created = 0
    updated = 0

    for label_name in PHASE_LABELS:
        expected = PHASE_LABEL_METADATA[label_name]
        current = existing_by_name.get(label_name)

        if current is None:
            log_info(f"Creating missing canonical label '{label_name}'")
            result = run_gh(
                [
                    "label",
                    "create",
                    label_name,
                    "--repo",
                    repo,
                    "--description",
                    expected["description"],
                    "--color",
                    expected["color"],
                ]
            )
            if result.returncode != 0:
                raise SystemExit(f"Failed to create label '{label_name}' in {repo}.")
            created += 1
            continue

        current_description = (current.get("description") or "").strip()
        current_color = (current.get("color") or "").strip().lstrip("#").upper()
        expected_description = expected["description"]
        expected_color = expected["color"].upper()
        if current_description == expected_description and current_color == expected_color:
            continue

        log_info(f"Repairing canonical label metadata for '{label_name}'")
        result = run_gh(
            [
                "label",
                "edit",
                label_name,
                "--repo",
                repo,
                "--description",
                expected_description,
                "--color",
                expected_color,
            ]
        )
        if result.returncode != 0:
            raise SystemExit(f"Failed to update label '{label_name}' in {repo}.")
        updated += 1

    log_info(f"Canonical labels ensured: {len(PHASE_LABELS)} total, {created} created, {updated} updated")


def resolve_issue_by_label(repo: str, label: str) -> int:
    """Resolve a single open issue by label."""
    log_info(f"Looking up open issue for label '{label}'")
    result = run_gh(
        ["issue", "list", "--repo", repo, "--label", label, "--state", "open", "--json", "number,title"],
        capture_output=True,
    )
    if result.returncode != 0 or not result.stdout:
        raise SystemExit(f"Could not query open issues labeled '{label}' in {repo}.")

    issues = json.loads(result.stdout)
    if not isinstance(issues, list) or not issues:
        raise SystemExit(f"No open issues labeled '{label}' found in {repo}.")
    if len(issues) > 1:
        issue_refs = ", ".join(f"#{item['number']}" for item in issues if isinstance(item, dict) and "number" in item)
        raise SystemExit(
            f"Multiple open issues labeled '{label}' found in {repo}: {issue_refs}. "
            "Pass --issue to select one."
        )

    issue = issues[0]
    if not isinstance(issue, dict) or "number" not in issue:
        raise SystemExit(f"Invalid issue payload while resolving label '{label}' in {repo}.")
    return int(issue["number"])


def issue_has_label(issue_data: dict[str, Any], label: str) -> bool:
    """Return True when the issue currently carries the requested label."""
    labels = issue_data.get("labels") or []
    found = any(item.get("name") == label for item in labels if isinstance(item, dict))
    return found


def issue_phase_labels(issue_data: dict[str, Any]) -> list[str]:
    """Return known phase labels attached to an issue."""
    labels = issue_data.get("labels") or []
    return [
        item["name"]
        for item in labels
        if isinstance(item, dict) and item.get("name") in PHASE_LABELS
    ]


def extract_phase_1_comment(issue_data: dict[str, Any]) -> Optional[str]:
    """Extract the normalized Keter comment body from machine-marked issue comments."""
    comments = issue_data.get("comments") or []
    for comment in comments:
        if not isinstance(comment, dict):
            continue
        body = comment.get("body", "")
        if not body:
            continue
        if "<!-- phase:1:start" in body:
            start_marker = f"<!-- phase:1:start"
            end_marker = "<!-- phase:1:end"
            if start_marker in body and end_marker in body:
                start_idx = body.find(start_marker)
                end_idx = body.find(end_marker, start_idx)
                if end_idx > start_idx:
                    content = body[start_idx:end_idx]
                    lines = content.split("\n")
                    for i, line in enumerate(lines):
                        if line.startswith("### Phase 1:"):
                            return "\n".join(lines[i + 2:]).strip() if i + 2 < len(lines) else ""
                    return content
    return None


def resolve_oldest_phased_issue(repo: str) -> tuple[int, str]:
    """Resolve the oldest open issue carrying exactly one known phase label."""
    log_info("Looking up the oldest open issue carrying a canonical phase label")
    result = run_gh(
        ["issue", "list", "--repo", repo, "--state", "open", "--json", "number,title,createdAt,labels"],
        capture_output=True,
    )
    if result.returncode != 0 or not result.stdout:
        raise SystemExit(f"Could not query open issues in {repo}.")

    issues = json.loads(result.stdout)
    if not isinstance(issues, list):
        raise SystemExit(f"Invalid issue list payload for {repo}.")

    phased_issues: list[dict[str, Any]] = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        labels = issue_phase_labels(issue)
        if labels:
            phased_issues.append(issue)

    if not phased_issues:
        raise SystemExit(f"No open issues with a phase label found in {repo}.")

    log_info(f"Found {len(phased_issues)} phased issues; sorting by creation date")
    phased_issues.sort(key=lambda item: item.get("createdAt", ""))
    selected = phased_issues[0]
    labels = issue_phase_labels(selected)
    if len(labels) != 1:
        issue_number = selected.get("number", "?")
        raise SystemExit(
            f"Issue #{issue_number} in {repo} has multiple phase labels: {', '.join(labels)}. "
            "Pass --label and --issue explicitly."
        )

    log_info(f"Selected oldest: issue #{selected['number']} with label '{labels[0]}'")
    return int(selected["number"]), labels[0]


def determine_phase_from_label(label: str) -> Optional[str]:
    """Map a canonical phase label to its canonical phase id."""
    label_phase_map = {
        "phase:keter": "1",
        "phase:chokhmah": "2a",
        "phase:binah": "2b",
        "phase:chesed": "2c",
        "phase:gevurah": "3",
        "phase:tiferet": "4",
        "phase:netzach": "5",
        "phase:hod": "6",
        "phase:yesod-orchestration": "7",
        "phase:yesod-embodiment": "8",
        "phase:malkhut": "9",
    }
    return label_phase_map.get(label)


def read_microagent_for_label(label: str, phase: Optional[str]) -> Optional[str]:
    """Build the effective phase prompt from Daneel, the phase persona, and the microagent."""
    sections: list[str] = []

    base_persona_path = PERSONAS_DIR / BASE_PERSONA_FILE
    if base_persona_path.exists():
        log_info(f"Including base persona: {base_persona_path.name}")
        sections.append(base_persona_path.read_text().strip())
    else:
        log_info("Base persona file not found; continuing without it")

    if phase:
        persona_filename = PERSONA_FILE_MAP.get(phase)
        if persona_filename:
            persona_path = PERSONAS_DIR / persona_filename
            log_info(f"Looking for phase persona file {persona_filename}")
            if persona_path.exists():
                log_info(f"Including phase persona: {persona_path.name}")
                sections.append(persona_path.read_text().strip())
            else:
                log_info(f"Phase persona file not found: {persona_filename}")

    microagent_content = read_legacy_microagent(label, phase)
    if microagent_content:
        sections.append(microagent_content.strip())

    if not sections:
        log_info("No persona or microagent content found for this phase")
        return None

    return "\n\n".join(sections)


def read_legacy_microagent(label: str, phase: Optional[str]) -> Optional[str]:
    """Read the functional `.openhands/microagents` prompt used alongside literary personas."""
    if phase:
        microagent_filename = LEGACY_MICROAGENT_FILE_MAP.get(phase)
        if microagent_filename:
            microagent_path = MICROAGENTS_DIR / microagent_filename
            if microagent_path.exists():
                log_info(f"Including functional microagent: {microagent_path.name}")
                return microagent_path.read_text()

    log_info("No filename match in .openhands/microagents; searching contents for the label name")
    label_name = label.replace("phase:", "")
    for md_file in MICROAGENTS_DIR.glob("*.md"):
        content = md_file.read_text()
        if label_name in content.lower():
            log_info(f"Including functional microagent by content: {md_file.name}")
            return content

    log_info("No functional microagent found")
    return None


def build_runtime_context(
    label: str,
    issue: int,
    repo: str,
    phase: str,
    issue_data: dict[str, Any],
) -> str:
    """Build prompt context from the live issue payload."""
    title = issue_data.get("title", "Untitled")
    body = issue_data.get("body", "").strip()
    return f"""## Runtime Context
- Repository: {repo}
- Trigger label: {label}
- Issue number: #{issue}
- Phase: {phase}

## Issue Content

**Title:** {title}

**Body:**
{body}
"""


def build_phase_input_context(
    label: str,
    issue: int,
    repo: str,
    phase: str,
    issue_data: dict[str, Any],
) -> str:
    """Build prompt context, restricting phases 2A-2C to the extracted Keter clarification."""
    if phase not in {"2a", "2b", "2c"}:
        log_info(f"Prompt input source: original issue body for phase {phase.upper()}")
        return build_runtime_context(label, issue, repo, phase, issue_data)

    phase_1_comment = extract_phase_1_comment(issue_data)
    if not phase_1_comment:
        log_error(f"Phase {phase.upper()} requires an existing Phase 1/Keter comment, but none was found on the issue.")
        raise SystemExit(f"Phase {phase.upper()} requires a Phase 1 clarification comment, but none was found.")

    title = issue_data.get("title", "Untitled")
    log_info(f"Prompt input source: Phase 1/Keter comment only for phase {phase.upper()}")
    log_info(f"Extracted Keter clarification length: {len(phase_1_comment)} chars")
    return f"""## Runtime Context
- Repository: {repo}
- Trigger label: {label}
- Issue number: #{issue}
- Phase: {phase}

## Issue Title

**Title:** {title}

## Phase 1 Input

Use only this Keter clarification as the task content for this phase.
Do not derive requirements directly from the original issue body.

{phase_1_comment}
"""


def strip_microagent(microagent: str) -> str:
    """Normalize the microagent content before embedding."""
    microagent_stripped = microagent.strip()
    if microagent_stripped.endswith("EOF"):
        microagent_stripped = microagent_stripped[:-3].strip()
    return microagent_stripped


def build_phase_2_story_requirements() -> list[str]:
    """Return shared requirements for phase-2 semaphored user-story comments."""
    return [
        "- Emit semaphored user stories only; do not add headings, preamble, summary, or commentary.",
        "- Format every line as `[COLOR] Given ..., when ..., then ...`.",
        "- Use only these semaphore tags: `[RED]`, `[ORANGE]`, and `[GREEN]`.",
        "- Keep the output shape consistent across all phase 2 variants: a flat list of semaphored user stories.",
        "- Derive every story exclusively from the Keter clarification provided in the prompt.",
        "- Do not mention other phases, personas, or handoff language.",
    ]


def build_discussion_prompt(
    label: str,
    issue: int,
    repo: str,
    microagent: str,
    phase: str,
    issue_data: dict[str, Any],
) -> str:
    """Build a prompt for comment-producing phases."""
    requirements = [
        "- Be concise and authoritative.",
        "- Do not mention tool limitations, environment limitations, or inability to post.",
        "- Do not describe yourself as unable to act.",
        "- Do not wrap the answer in code fences.",
        "- Keep the content appropriate for a single GitHub issue comment.",
    ]

    if phase == "1":
        requirements.extend(
            [
                "- Produce a comprehensive clarification comment, not an ACK.",
                "- Start with a short statement that the requirement has been clarified.",
                "- Include these exact section headings: `Clarified Requirement`, `Constraints and Invariants`, `Acceptance Signals`, and `Phase 2 Handoff`.",
                "- `Clarified Requirement` must describe the feature behavior in one coherent paragraph.",
                "- `Constraints and Invariants` must be a flat bullet list covering preserved behavior, determinism/seed expectations, UI placement, and boundary behavior when applicable.",
                "- `Acceptance Signals` must be a flat bullet list of observable outcomes a reviewer can verify.",
                "- `Phase 2 Handoff` must state that generative expansion can proceed.",
            ]
        )
    elif phase in {"2a", "2b", "2c"}:
        requirements.extend(build_phase_2_story_requirements())
    return f"""{strip_microagent(microagent)}

{build_phase_input_context(label, issue, repo, phase, issue_data)}

Return only the GitHub comment body for this phase.

Requirements:
{chr(10).join(requirements)}
"""


def build_spec_prompt(
    label: str,
    issue: int,
    repo: str,
    microagent: str,
    phase: str,
    issue_data: dict[str, Any],
) -> str:
    """Build a prompt for phase 4/Tiferet, the child-issue specification phase."""
    return f"""{strip_microagent(microagent)}

{build_phase_input_context(label, issue, repo, phase, issue_data)}

Return valid JSON only. No markdown fences. No explanation outside JSON.

Use this exact schema:
{{
  "comment": "GitHub comment body for the parent issue",
  "sub_issues": [
    {{
      "title": "Short actionable issue title",
      "body": "Gherkin-oriented child issue body with Given/When/Then scenarios"
    }}
  ]
}}

Requirements:
- `comment` must summarize the specification and explain that child issues were spawned.
- `sub_issues` must contain one or more items.
- Order `sub_issues` from earliest required implementation step to latest dependent step.
- Each child issue body must use Gherkin language with explicit `Given`, `When`, and `Then` sections.
- Assume child issues will be created in listed order, attached as sub-issues to the parent issue, and each later child issue blocked by the immediately preceding child issue.
- Do not mention tool limitations, environment limitations, or inability to post.
"""


def build_agent_prompt(
    label: str,
    issue: int,
    repo: str,
    microagent: str,
    phase: str,
    issue_data: dict[str, Any],
) -> str:
    """Build the prompt for phases 5-9 implementation and validation work."""
    return f"""{strip_microagent(microagent)}

{build_runtime_context(label, issue, repo, phase, issue_data)}

Execute your phase logic now.
"""


def openhands_env() -> dict[str, str]:
    """Build the environment used by headless OpenHands subprocesses."""
    conversations_dir = WORKSPACE / ".openhands" / "conversations"
    conversations_dir.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    env["OPENHANDS_CONVERSATIONS_DIR"] = str(conversations_dir)
    env["OPENHANDS_DISABLE_UPDATE_CHECK"] = "1"

    if env.get("DASHSCOPE_API_KEY") and not env.get("LLM_API_KEY"):
        env["LLM_API_KEY"] = env["DASHSCOPE_API_KEY"]
    if env.get("DASHSCOPE_API_BASE") and not env.get("LLM_BASE_URL"):
        env["LLM_BASE_URL"] = env["DASHSCOPE_API_BASE"]
    if env.get("DASHSCOPE_API_KEY") and not env.get("LLM_MODEL"):
        env["LLM_MODEL"] = "dashscope/qwen3-coder-plus"

    return env


def session_key(repo: str, issue: int) -> str:
    """Build a stable key so each issue can resume its own OpenHands conversation."""
    return f"{repo}#{issue}"


def load_session_state() -> dict[str, str]:
    """Load persisted issue -> conversation id mappings used to resume per-issue sessions."""
    if not SESSION_STATE_PATH.exists():
        return {}
    try:
        return json.loads(SESSION_STATE_PATH.read_text())
    except json.JSONDecodeError:
        log_error("Session state file is invalid JSON; starting with an empty session map")
        return {}


def save_session_state(state: dict[str, str]) -> None:
    """Persist issue -> conversation id mappings so later phase runs can resume context."""
    SESSION_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SESSION_STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True))


def extract_conversation_id(output: str) -> str:
    """Extract the conversation id from OpenHands stdout so it can be reused on the next run."""
    marker = "Conversation ID:"
    for line in output.splitlines():
        if marker in line:
            return line.split(marker, 1)[1].strip()
    return ""


def run_openhands(prompt: str, *, repo: str, issue: int) -> subprocess.CompletedProcess[str]:
    """Run OpenHands headlessly and capture output."""
    state = load_session_state()
    conversation_id = state.get(session_key(repo, issue), "")

    log_info(f"Session mode: {'resume existing conversation' if conversation_id else 'start new conversation'}")

    command = ["openhands"]
    if conversation_id:
        command.extend(["--resume", conversation_id])
        log_info(f"Resuming conversation {conversation_id[:8]}...")
    command.extend(
        [
            "--task",
            prompt,
            "--headless",
            "--json",
            "--override-with-envs",
            "--exit-without-confirmation",
        ]
    )

    log_info("Launching OpenHands headless run")
    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
        timeout=600,
        env=openhands_env(),
    )
    log_info(f"OpenHands exit code: {result.returncode}")
    new_conversation_id = extract_conversation_id(result.stdout)
    if new_conversation_id:
        state[session_key(repo, issue)] = new_conversation_id
        save_session_state(state)
        log_info(f"Saved conversation ID {new_conversation_id[:8]}...")
    return result


def extract_message_events(output: str) -> list[dict[str, Any]]:
    """Extract JSON event payloads from OpenHands stdout.

    OpenHands emits structured event objects in stdout, each preceded by a
    sentinel marker. We scan for those markers and decode each JSON object so
    later helpers can inspect assistant messages without relying on plain-text
    formatting.
    """
    events: list[dict[str, Any]] = []
    marker = "--JSON Event--"
    decoder = json.JSONDecoder()
    cursor = 0

    while True:
        marker_index = output.find(marker, cursor)
        if marker_index == -1:
            break

        search_index = marker_index + len(marker)
        brace_index = output.find("{", search_index)
        if brace_index == -1:
            break

        try:
            event, consumed = decoder.raw_decode(output[brace_index:])
        except json.JSONDecodeError:
            cursor = search_index
            continue

        if isinstance(event, dict):
            events.append(event)
        cursor = brace_index + consumed

    return events


def last_assistant_message(output: str) -> str:
    """Return the final assistant-authored message from parsed OpenHands events."""
    message = ""
    for event in extract_message_events(output):
        if event.get("kind") != "MessageEvent":
            continue
        llm_message = event.get("llm_message") or {}
        if llm_message.get("role") != "assistant":
            continue
        content = llm_message.get("content") or []
        chunks = [item.get("text", "") for item in content if isinstance(item, dict)]
        if chunks:
            message = "".join(chunks).strip()
    return message


def run_openhands_for_comment(prompt: str, *, repo: str, issue: int) -> str:
    """Run OpenHands and return the assistant reply text."""
    log_info("Requesting comment response from OpenHands")
    result = run_openhands(prompt, repo=repo, issue=issue)
    if result.returncode != 0:
        log_error(f"OpenHands failed for {repo}#{issue} with exit code {result.returncode}")
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        sys.exit(result.returncode)

    comment = last_assistant_message(result.stdout)
    if not comment:
        print(result.stdout)
        log_error("OpenHands returned no assistant message.")
        sys.exit(1)
    log_info(f"Assistant message extracted ({len(comment)} chars)")
    return comment


def run_openhands_for_json(prompt: str, *, repo: str, issue: int) -> dict[str, Any]:
    """Run OpenHands and parse the final assistant reply as JSON."""
    log_info("Requesting JSON response from OpenHands")
    content = run_openhands_for_comment(prompt, repo=repo, issue=issue)
    log_info("Parsing JSON from assistant reply")
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        log_error("Assistant reply was not valid JSON for phase 4/Tiferet")
        print(content)
        raise SystemExit(f"OpenHands did not return valid JSON for phase 4/Tiferet: {exc}") from exc


def run_openhands_task(task: str, *, repo: str, issue: int) -> None:
    """Run an implementation or validation phase through OpenHands."""
    print("=" * 60)
    print("OpenHands Agent Execution")
    print("=" * 60)
    print(f"Task: {task[:200]}...")
    print("=" * 60)

    result = run_openhands(task, repo=repo, issue=issue)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    if result.returncode != 0:
        sys.exit(result.returncode)

    print("\nAgent execution complete.")


def validate_phase_four_payload(payload: dict[str, Any]) -> None:
    """Validate the minimal schema for the phase 4/Tiferet child-issue payload."""
    log_info("Validating payload structure...")
    if not isinstance(payload, dict):
        raise SystemExit("Phase 4/Tiferet payload must be a JSON object.")
    if not isinstance(payload.get("comment"), str) or not payload["comment"].strip():
        raise SystemExit("Phase 4/Tiferet payload must include a non-empty `comment`.")
    log_info("✓ Payload has valid 'comment' field")

    sub_issues = payload.get("sub_issues")
    if not isinstance(sub_issues, list) or not sub_issues:
        raise SystemExit("Phase 4/Tiferet payload must include at least one `sub_issues` entry.")
    log_info(f"✓ Payload has {len(sub_issues)} sub_issues")

    for i, item in enumerate(sub_issues):
        if not isinstance(item, dict):
            log_error(f"sub_issues[{i}] is not a JSON object")
            raise SystemExit("Each phase 4/Tiferet child issue must be an object.")
        if not isinstance(item.get("title"), str) or not item["title"].strip():
            log_error(f"sub_issues[{i}] is missing a non-empty title")
            raise SystemExit("Each phase 4/Tiferet child issue must include a non-empty `title`.")
        if not isinstance(item.get("body"), str) or not item["body"].strip():
            log_error(f"sub_issues[{i}] is missing a non-empty body")
            raise SystemExit("Each phase 4/Tiferet child issue must include a non-empty `body`.")
    log_info("✓ All sub_issues have valid structure")


def run_gh(args: list[str], *, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    """Run a GitHub CLI command with a short preview log."""
    preview = " ".join(args[:5])
    log_info(f"GitHub CLI: gh {preview}{' ...' if len(args) > 5 else ''}")
    return subprocess.run(
        ["gh", *args],
        text=True,
        capture_output=capture_output,
        timeout=120,
    )


def phase_display_name(phase: str, label: str) -> str:
    """Build a stable display name for a phase comment boundary."""
    if phase in {"2a", "2b", "2c"}:
        return label.replace("phase:", "").capitalize()
    return PHASE_DISPLAY_NAME_MAP.get(phase, label.replace("phase:", "").capitalize())


def format_phase_comment(phase: str, label: str, body: str) -> str:
    """Wrap a posted comment with visible and machine-readable phase boundaries.

    The HTML comment markers are later used to recover prior phase output, most
    importantly the Phase 1/Keter clarification that feeds phases 2A-2C.
    """
    display_name = phase_display_name(phase, label)
    normalized_body = body.strip()
    return "\n".join(
        [
            f"<!-- phase:{phase}:start label={label} name={display_name} -->",
            f"### Phase {phase.upper()}: {display_name}",
            "",
            normalized_body,
            "",
            f"<!-- phase:{phase}:end label={label} name={display_name} -->",
        ]
    )


def post_issue_comment(repo: str, issue_number: int, body: str) -> None:
    """Post a GitHub comment to the target issue."""
    log_info(f"Posting issue comment to #{issue_number}")
    result = run_gh(["issue", "comment", str(issue_number), "--repo", repo, "--body", body])
    if result.returncode != 0:
        log_error(f"Failed to post comment to {repo}#{issue_number}")
        raise SystemExit(f"Failed to post comment to {repo}#{issue_number}.")


def advance_issue_label(repo: str, issue_number: int, current_label: str, phase: str) -> None:
    """Advance the issue from its current phase label to the configured next label."""
    next_label = NEXT_LABEL_MAP.get(current_label)
    if not next_label:
        log_info("No next label defined (final phase)")
        return

    log_info(f"Removing label '{current_label}'")
    log_info(f"Adding label '{next_label}'")

    result = run_gh(
        [
            "issue",
            "edit",
            str(issue_number),
            "--repo",
            repo,
            "--remove-label",
            current_label,
            "--add-label",
            next_label,
        ]
    )
    if result.returncode != 0:
        raise SystemExit(
            f"Posted the phase comment to {repo}#{issue_number}, but failed to hand off label "
            f"from '{current_label}' to '{next_label}'."
        )
    log_info("Label handoff complete")


def parse_repo(repo: str) -> tuple[str, str]:
    """Split an owner/repo string into owner and repository name."""
    owner, repo_name = repo.split("/", 1)
    return owner, repo_name


def create_issue_via_api(repo: str, title: str, body: str) -> dict[str, Any]:
    """Create an issue through the REST API and return its full metadata."""
    owner, repo_name = parse_repo(repo)
    result = run_gh(
        [
            "api",
            f"repos/{owner}/{repo_name}/issues",
            "--method",
            "POST",
            "-f",
            f"title={title}",
            "-f",
            f"body={body}",
        ],
        capture_output=True,
    )
    if result.returncode != 0 or not result.stdout:
        raise SystemExit(f"Failed to create child issue '{title}'.")
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict):
        raise SystemExit(f"Invalid payload returned while creating child issue '{title}'.")
    return payload


def add_sub_issue_relationship(repo: str, parent_issue_number: int, sub_issue_id: int) -> None:
    """Attach a child issue to its parent using GitHub's sub-issue relationship."""
    owner, repo_name = parse_repo(repo)
    result = run_gh(
        [
            "api",
            f"repos/{owner}/{repo_name}/issues/{parent_issue_number}/sub_issues",
            "--method",
            "POST",
            "-f",
            f"sub_issue_id={sub_issue_id}",
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        raise SystemExit(f"Failed to attach sub-issue id {sub_issue_id} to parent issue #{parent_issue_number}.")
    log_info(f"  → Attached as sub-issue under parent #{parent_issue_number}")


def add_blocked_by_dependency(repo: str, issue_number: int, blocking_issue_id: int) -> None:
    """Mark an issue as blocked by another issue using GitHub's issue dependency API."""
    owner, repo_name = parse_repo(repo)
    result = run_gh(
        [
            "api",
            f"repos/{owner}/{repo_name}/issues/{issue_number}/dependencies/blocked_by",
            "--method",
            "POST",
            "-f",
            f"issue_id={blocking_issue_id}",
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        raise SystemExit(f"Failed to mark issue #{issue_number} as blocked by issue id {blocking_issue_id}.")
    log_info(f"  → Added blocked-by dependency to issue #{issue_number}")


def create_child_issues(
    repo: str,
    parent_issue: int,
    sub_issues: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Create ordered child issues, attach them to the parent, and wire predecessor dependencies."""
    log_info(f"Creating {len(sub_issues)} child issues in implementation order...")
    created: list[dict[str, Any]] = []

    for i, item in enumerate(sub_issues, 1):
        log_info(f"Creating ordered child issue #{i}: {item['title'][:50]}")
        body = item["body"].strip()
        auto_created_marker = f"Automatically created by Phase 4/Tiferet from parent issue #{parent_issue}."
        parent_marker = f"Parent issue: #{parent_issue}"
        prefix_lines: list[str] = []
        if auto_created_marker not in body:
            prefix_lines.append(auto_created_marker)
        if parent_marker not in body:
            prefix_lines.append(parent_marker)
        if prefix_lines:
            body = "\n".join(prefix_lines) + f"\n\n{body}"

        payload = create_issue_via_api(repo, item["title"].strip(), body)
        issue_number = int(payload["number"])
        issue_id = int(payload["id"])
        url = str(payload["html_url"]).strip()
        log_info(f"  → Created issue #{issue_number}: {url}")
        created.append({"title": item["title"].strip(), "url": url, "number": issue_number, "id": issue_id})

    for i, item in enumerate(created, 1):
        issue_number = int(item["number"])
        issue_id = int(item["id"])
        log_info(f"Linking child issue #{issue_number} to parent #{parent_issue} as a sub-issue")
        add_sub_issue_relationship(repo, parent_issue, issue_id)

        if i > 1:
            previous_issue = created[i - 2]
            previous_number = int(previous_issue["number"])
            previous_id = int(previous_issue["id"])
            log_info(f"Linking child issue #{issue_number} as blocked by preceding issue #{previous_number}")
            add_blocked_by_dependency(repo, issue_number, previous_id)

    log_info(f"All {len(created)} child issues created, attached, and dependency-linked successfully")
    return created


def build_phase_four_summary(created: list[dict[str, str]]) -> str:
    """Build the parent summary comment listing created child issues."""
    log_info("Building child-issue summary comment")
    lines = ["Spawned child issues:"]
    for item in created:
        lines.append(f"- {item['title']}: {item['url']}")
    return "\n".join(lines)


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


if __name__ == "__main__":
    main()
