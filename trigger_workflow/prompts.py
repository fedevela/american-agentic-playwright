from __future__ import annotations

from typing import Any, Optional

from .config import (
    BASE_PERSONA_FILE,
    DISCUSSION_PHASES,
    KETER_DERIVED_PHASES,
    LEGACY_MICROAGENT_FILE_MAP,
    LABEL_PHASE_MAP,
    MICROAGENTS_DIR,
    PERSONAS_DIR,
    PERSONA_FILE_MAP,
    PHASE_DISPLAY_NAME_MAP,
)
from .logging_utils import log_error, log_info


def determine_phase_from_label(label: str) -> Optional[str]:
    """Map a canonical phase label to its canonical phase id."""
    return LABEL_PHASE_MAP.get(label)


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
            start_marker = "<!-- phase:1:start"
            end_marker = "<!-- phase:1:end"
            if start_marker in body and end_marker in body:
                start_idx = body.find(start_marker)
                end_idx = body.find(end_marker, start_idx)
                if end_idx > start_idx:
                    content = body[start_idx:end_idx]
                    lines = content.split("\n")
                    for i, line in enumerate(lines):
                        if line.startswith("### Phase 1:"):
                            return "\n".join(lines[i + 2 :]).strip() if i + 2 < len(lines) else ""
                    return content
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
    if phase not in KETER_DERIVED_PHASES:
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


def phase_display_name(phase: str, label: str) -> str:
    """Build a stable display name for a phase comment boundary."""
    if phase in {"2a", "2b", "2c"}:
        return label.replace("phase:", "").capitalize()
    return PHASE_DISPLAY_NAME_MAP.get(phase, label.replace("phase:", "").capitalize())


def format_phase_comment(phase: str, label: str, body: str) -> str:
    """Wrap a posted comment with visible and machine-readable phase boundaries."""
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


def build_phase_four_summary(created: list[dict[str, Any]]) -> str:
    """Build the parent summary comment listing created child issues."""
    log_info("Building child-issue summary comment")
    lines = ["Spawned child issues:"]
    for item in created:
        lines.append(f"- {item['title']}: {item['url']}")
    return "\n".join(lines)

