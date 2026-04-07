from __future__ import annotations

from typing import Any
from ..logging_utils import log_info, log_error
from ..config import KETER_DERIVED_PHASES

COMMENT_VISIBLE_PHASES = {"3", "4", "5", "6", "7", "8", "9"}

def extract_phase_1_comment(issue_data: dict[str, Any]) -> str | None:
    """Extract the normalized Keter comment body from machine-marked issue comments."""
    comments = issue_data.get("comments") or []
    log_info(f"Extracting phase 1 comment from {len(comments)} comments...")
    for i, comment in enumerate(comments):
        log_info(f"  Processing comment {i + 1}/{len(comments)}")
        if not isinstance(comment, dict):
            log_info("    - Skipping: not a dictionary.")
            continue
        body = str(comment.get("body") or "")
        if not body:
            log_info("    - Skipping: empty body.")
            continue

        log_info(f"    - Comment body length: {len(body)}")
        start_marker = "<!-- phase:1:start"
        end_marker = "<!-- phase:1:end"

        if start_marker in body and end_marker in body:
            log_info("    - Found start and end markers for phase 1.")
            start_idx = body.find(start_marker)
            end_idx = body.find(end_marker, start_idx)
            if end_idx > start_idx:
                content = body[start_idx:end_idx]
                log_info(f"    - Extracted content block (length: {len(content)})")
                lines = content.split("\n")
                for j, line in enumerate(lines):
                    if line.startswith("### Phase 1:"):
                        log_info(f"    - Found '### Phase 1:' on line {j + 1}.")
                        extracted = "\n".join(lines[j + 2 :]).strip() if j + 2 < len(lines) else ""
                        log_info(f"    - Returning extracted clarification (length: {len(extracted)})")
                        return extracted
                log_info("    - Fallback: returning raw content between markers because '### Phase 1:' was not found.")
                return content
            else:
                log_info(f"    - Skipping: end marker found before start marker (start={start_idx}, end={end_idx}).")
        else:
            log_info("    - Skipping: missing start or end marker for phase 1.")

    log_info("No phase 1 comment found after checking all comments.")
    return None


def build_issue_runtime_context(
    label: str,
    issue: int,
    repo: str,
    phase: str,
    issue_data: dict[str, Any],
    *,
    include_comments: bool = False,
) -> str:
    """Build prompt context from the live issue payload."""
    title = issue_data.get("title", "Untitled")
    body = issue_data.get("body", "").strip()
    context = f"""## Runtime Context
- Repository: {repo}
- Trigger label: {label}
- Issue number: #{issue}
- Phase: {phase}

## Issue Content

**Title:** {title}

**Body:**
{body}
"""
    if not include_comments:
        return context

    comments = issue_data.get("comments") or []
    rendered_comments: list[str] = []
    for i, comment in enumerate(comments, 1):
        if not isinstance(comment, dict):
            continue
        body_text = str(comment.get("body") or "").strip()
        if not body_text:
            continue
        rendered_comments.append(f"### Comment {i}\n{body_text}")

    comments_block = "\n\n".join(rendered_comments) if rendered_comments else "(none)"
    return f"""{context}

## Issue Comments

{comments_block}
"""


def build_phase_prompt_input_context(
    label: str,
    issue: int,
    repo: str,
    phase: str,
    issue_data: dict[str, Any],
) -> str:
    """Build prompt context, restricting phases 2A-2C to Keter and giving phases 3+ access to issue comments."""
    if phase not in KETER_DERIVED_PHASES:
        include_comments = phase in COMMENT_VISIBLE_PHASES
        source = "original issue body and all issue comments" if include_comments else "original issue body"
        log_info(f"Prompt input source: {source} for phase {phase.upper()}")
        return build_issue_runtime_context(label, issue, repo, phase, issue_data, include_comments=include_comments)

    log_info(f"Phase {phase.upper()} is in KETER_DERIVED_PHASES, extracting Phase 1/Keter comment for prompt context")
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


def strip_microagent_persona_persona(microagent_persona_persona: str) -> str:
    """Normalize the microagent_persona_persona content before embedding."""
    microagent_persona_persona_stripped = microagent_persona_persona.strip()
    if microagent_persona_persona_stripped.endswith("EOF"):
        microagent_persona_persona_stripped = microagent_persona_persona_stripped[:-3].strip()
    return microagent_persona_persona_stripped