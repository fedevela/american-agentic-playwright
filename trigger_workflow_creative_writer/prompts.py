from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import (
    BASE_PERSONA_FILE,
    DISCUSSION_PHASES,
    FUNCTIONAL_MICROAGENT_FILE_MAP,
    KETER_DERIVED_PHASES,
    LABEL_PHASE_MAP,
    MICROAGENTS_DIR,
    PERSONAS_DIR,
    PERSONA_FILE_MAP,
    PHASE_DISPLAY_NAME_MAP,
    TIFERET_AUTO_ISSUE_PREFIX,
)
from .logging_utils import log_error, log_info


COMMENT_VISIBLE_PHASES = {"3", "4", "5", "6", "7", "8", "9"}


def determine_phase_from_label(label: str) -> str | None:
    """Map a canonical phase label to its canonical phase id."""
    return LABEL_PHASE_MAP.get(label)


def read_required_text_file(path: Path, *, missing_message: str, log_message: str) -> str:
    """Read a required prompt file with consistent logging and failure behavior."""
    if not path.exists():
        raise SystemExit(missing_message)
    log_info(log_message)
    return path.read_text().strip()


def read_microagent_for_label(label: str, phase: str | None, *, include_base_persona: bool = True) -> str:
    """Build the effective phase prompt from Daneel, the phase persona, and the microagent."""
    if not phase:
        raise SystemExit(f"Cannot load persona stack for label '{label}' without a resolved phase id.")

    sections: list[str] = []

    if include_base_persona:
        base_persona_path = PERSONAS_DIR.parent / BASE_PERSONA_FILE
        sections.append(
            read_required_text_file(
                base_persona_path,
                missing_message=f"Base persona file is missing: {base_persona_path.name}",
                log_message=f"Including base persona: {base_persona_path.name}",
            )
        )

    persona_filename = PERSONA_FILE_MAP.get(phase)
    if not persona_filename:
        raise SystemExit(f"No phase persona filename is configured for phase {phase.upper()}.")
    persona_path = PERSONAS_DIR / persona_filename
    log_info(f"Looking for phase persona file {persona_filename}")
    sections.append(
        read_required_text_file(
            persona_path,
            missing_message=f"Phase persona file is missing: {persona_filename}",
            log_message=f"Including phase persona: {persona_path.name}",
        )
    )

    microagent_content = read_functional_microagent(label, phase)
    sections.append(microagent_content.strip())

    return "\n\n".join(sections)


def read_functional_microagent(label: str, phase: str | None) -> str:
    """Read the functional `microagents/` prompt used alongside literary personas."""
    del label
    if not phase:
        raise SystemExit("Cannot load a functional microagent without a resolved phase id.")

    microagent_filename = FUNCTIONAL_MICROAGENT_FILE_MAP.get(phase)
    if not microagent_filename:
        raise SystemExit(f"No functional microagent filename is configured for phase {phase.upper()}.")

    microagent_path = MICROAGENTS_DIR / microagent_filename
    return read_required_text_file(
        microagent_path,
        missing_message=f"Functional microagent file is missing: {microagent_filename}",
        log_message=f"Including functional microagent: {microagent_path.name}",
    )


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

### Required Local Context (The Law of the World)
The creative engine requires the following 11 standardized artifacts to be present in the local file system. These form the binding constraints of the story, characters, and world. The caller must provide them, and you must rely on them for all foundational truth rather than inventing it:
1. `agents.md`
2. `agents_artifacts/dramatic_arcs.md`
3. `agents_artifacts/world_rules.md`
4. `agents_artifacts/theme.md`
5. `agents_artifacts/relationships.drawio`
6. `agents_artifacts/characters/[character_name]/appearance.md`
7. `agents_artifacts/characters/[character_name]/personality.md`
8. `agents_artifacts/characters/[character_name]/interiorvoice.md`
9. `agents_artifacts/characters/[character_name]/motivations_and_fears.md`
10. `agents_artifacts/characters/[character_name]/secrets.md`
11. `agents_artifacts/characters/[character_name]/lexicon.md`

**Memory Check Directive:** Before proceeding with any generation, you must verify that you have successfully read and loaded all of the above artifacts into your working memory. If they are not in your context, you must read them from the local file system now.

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
        "- Favor behaviors that are observable, automatable, and verifiable through end-to-end tests.",
        "- Write `then` clauses in measurable terms: concrete state changes, DOM/UI changes, emitted values, preserved controls, deterministic outputs, or other inspectable outcomes.",
        "- Do not rely on subjective human judgments such as 'feels natural', 'looks better', 'visibly improved', or 'responsive' unless those claims are tied to explicit, testable signals.",
        "- Do not mention other phases, personas, or handoff language.",
    ]


def build_comment_phase_prompt(
    label: str,
    issue: int,
    repo: str,
    microagent: str,
    phase: str,
    issue_data: dict[str, Any],
) -> str:
    log_info(f"Building comment-producing prompt for phase {phase.upper()}")
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
                "- Favor acceptance signals that are observable, automatable, and verifiable through end-to-end tests or other inspectable checks.",
                "- Do not rely on subjective human judgments such as 'feels natural', 'looks better', 'visibly improved', or 'responsive' unless they are translated into explicit, measurable signals.",
                "- `Phase 2 Handoff` must state that generative expansion can proceed.",
            ]
        )
    elif phase in {"2A", "2B", "2C"}:
        requirements.extend(build_phase_2_story_requirements())

    return f"""{strip_microagent(microagent)}

{build_phase_prompt_input_context(label, issue, repo, phase, issue_data)}

Return valid JSON only. No markdown fences. No explanation outside JSON.

Use this exact schema:
{{
  "response": "The complete GitHub comment body for this phase."
}}

Requirements:
{chr(10).join(requirements)}
"""


def build_tiferet_specification_prompt(
    label: str,
    issue: int,
    repo: str,
    microagent: str,
    phase: str,
    issue_data: dict[str, Any],
) -> str:
    """Build a prompt for phase 4/Tiferet, the child-issue specification phase."""
    return f"""{strip_microagent(microagent)}

{build_phase_prompt_input_context(label, issue, repo, phase, issue_data)}

Return valid JSON only. No markdown fences. No explanation outside JSON.

Use this exact schema:
{{
  "comment": "GitHub comment body for the parent issue explaining the decomposition rationale",
  "sub_issues": [
    {{
      "title": "{TIFERET_AUTO_ISSUE_PREFIX}Short actionable issue title",
      "body": "Child issue body beginning with a 'Resolves Beats:' traceability line copying the full Master Story Beat definitions verbatim, followed by a detailed Scene/Sequence Outline."
    }}
  ]
}}

Requirements:
- `comment` must summarize the specification and explain that child issues were spawned.
- `comment` must explicitly reconcile the provided Master Story Beats against the final child issue set.
- `comment` must explain the grouping logic for every child issue, ensuring the Scale/Size of the beat is accurately fractured down (e.g. from a [LARGE] episode beat into [MEDIUM] sequence beats, or [MEDIUM] down to [SMALL] scene beats).
- `comment` must state which Master Story Beats are covered by each child issue and why they belong together.
- `sub_issues` must contain one or more items.
- Order `sub_issues` from earliest required chronological step to the latest.
- Prefix every child issue title with `{TIFERET_AUTO_ISSUE_PREFIX}` so auto-created issues are visibly distinct from human-authored issues.
- Every child issue body must begin with a `Resolves Beats:` line listing every Master Story Beat (with its full bracketed definition) consolidated into that child issue.
- The beat list must be complete for that child issue; do not omit any covered beats.
- Copy the full canonical beat definitions verbatim. Do not paraphrase or compress them.
- Each child issue body must contain a detailed `Scene/Sequence Outline` explaining how the beats translate into visible action.
- Assume child issues will be created in listed order, attached as sub-issues to the parent issue.
- Do not mention tool limitations, environment limitations, or inability to post.
"""


def build_implementation_phase_prompt(
    label: str,
    issue: int,
    repo: str,
    microagent: str,
    phase: str,
    issue_data: dict[str, Any],
) -> str:
    """Build the prompt for phases 5-9 implementation and validation work."""
    terminal_discipline_requirements = [
        "- Terminal discipline (mandatory): favor bounded, deterministic commands (`rg`, targeted paths) and avoid broad recursive scans from repo root.",
        "- Exclude heavy/generated trees when searching (for example `node_modules`, `build`, `.git`) unless explicitly needed.",
        "- Always constrain potentially long-running commands (path filters and/or explicit command timeouts).",
        "- If terminal reports the previous command is still running and blocks new commands, immediately recover by interacting with the active process (`is_input=true`): first poll with empty input, then interrupt with `C-c` if needed, then continue with a narrower command.",
        "- Do not loop on blocked terminal state; recover deterministically and proceed with code edits.",
    ]
    phase_requirements: list[str] = []
    if phase == "7":
        phase_requirements = [
            "- This is Phase 7 (Act Assembly & Pacing). Deliver pacing and structural boundaries as actual document changes, not analysis-only notes.",
            "- First run a deterministic pacing-discovery pass: derive emotional pressures, map sequence loci, then select boundaries per locus.",
            "- Then implement the smallest coherent structural set that fully covers canonical beat IDs.",
            "- Keep artifacts requirement-traceable: each act break must map to one or more canonical beat IDs.",
            "- Do not stop at read-only analysis; leave a non-empty git diff with concrete structural edits.",
            "- Apply an explicit completion gate before finishing: if canonical beat coverage or non-empty diff conditions are not met, continue mapping.",
            "- Do not fully write the dialogue; focus on placement, act seams, rising action, and emotional boundaries.",
        ]
    elif phase == "8":
        phase_requirements = [
            "- This is Phase 8 (First Draft Execution).",
            "- First run a deterministic scene-discovery pass: identify dialogue and prose obligations from prior outlines.",
            "- Embody those outlines in flowing prose without deviating from the specified emotional intent.",
            "- Do not quietly rewrite the core plot to match easier prose; adjust prose to serve the outline.",
            "- Apply an explicit completion gate before finishing: verify working drafts exist for all assigned beat IDs before finishing.",
        ]
    elif phase == "9":
        phase_requirements = [
            "- This is Phase 9 (The Final Edit). Execute validation with evidence-first discipline.",
            "- Run a deterministic narrative-discovery pass: collect pacing flaws, map each failure to violated beat IDs, then apply minimal corrective deltas.",
            "- Keep corrections requirement-traceable and scope-bounded to observed violations.",
            "- Apply an explicit completion gate before finishing: do not terminate on narrative; finish only with evidence-backed readiness status.",
        ]

    requirements_block = ""
    requirement_lines = [*terminal_discipline_requirements, *phase_requirements]
    if requirement_lines:
        requirements_block = f"\n\nPhase-specific requirements:\n{chr(10).join(requirement_lines)}"

    return f"""{strip_microagent(microagent)}

{build_issue_runtime_context(label, issue, repo, phase, issue_data, include_comments=phase in COMMENT_VISIBLE_PHASES)}

Execute your phase logic now.{requirements_block}
"""


def phase_display_name(phase: str, label: str) -> str:
    """Build a stable display name for a phase comment boundary."""
    if phase in {"2A", "2B", "2C"}:
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
    lines = [f"Spawned {len(created)} auto-created child issues in implementation order:"]
    for item in created:
        lines.append(f"- {item['title']}: {item['url']}")
    return "\n".join(lines)
