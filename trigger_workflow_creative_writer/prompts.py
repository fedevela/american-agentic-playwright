from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .artifact_validation import REQUIRED_CHARACTER_ARTIFACTS
from .config import (
    BASE_PERSONA_FILE,
    FUNCTIONAL_MICROAGENT_FILE_MAP,
    LABEL_PHASE_MAP,
    MICROAGENTS_DIR,
    PERSONAS_DIR,
    PERSONA_FILE_MAP,
    PHASE_DISPLAY_NAME_MAP,
)
from .logging_utils import log_info


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
    """Return the accepted Keter result for the current exploration cycle."""
    from .cycles import current_result

    result = current_result(issue_data, "1")
    return json.dumps(result, ensure_ascii=False, indent=2) if result else None


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
    character_artifact_lines = "\n".join(
        f"{number}. `bible/characters/[character_name]/{filename}`"
        for number, filename in enumerate(REQUIRED_CHARACTER_ARTIFACTS, start=6)
    )
    context = f"""## Runtime Context
- Repository: {repo}
- Trigger label: {label}
- Issue number: #{issue}
- Phase: {phase}

### Established Canon
Use these local references for the established story, characters, and world:
1. `bible/characters.md`
2. `bible/dramatic_arcs.md`
3. `bible/world_rules.md`
4. `bible/theme.md`
5. `bible/relationships.drawio`
{character_artifact_lines}

Read the relevant canon references and preserve established dramatic facts. Let them inform the writing without announcing prerequisite verification.

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
    """Use cycle-owned inputs upstream, preserving independent exploration contexts."""
    if phase not in {"1", "2A", "2B", "2C", "3", "4"}:
        return build_issue_runtime_context(
            label, issue, repo, phase, issue_data, include_comments=phase in COMMENT_VISIBLE_PHASES
        )
    from .cycles import prompt_context

    context = prompt_context(issue_data, phase)
    # Avoid raw title/body/comments here: cycle context determines precisely what
    # the current perspective can see, including its own pending human answer.
    runtime = build_issue_runtime_context(label, issue, repo, phase, {})
    runtime = runtime.split("## Issue Content", 1)[0].strip()
    return f"{runtime}\n\n## Current Exploration Cycle\n\n{json.dumps(context, ensure_ascii=False, indent=2)}"


def strip_microagent(microagent: str) -> str:
    """Normalize the microagent content before embedding."""
    microagent_stripped = microagent.strip()
    if microagent_stripped.endswith("EOF"):
        microagent_stripped = microagent_stripped[:-3].strip()
    return microagent_stripped


def build_phase_2_story_requirements() -> list[str]:
    """Return shared dramatic exploration instructions for level two."""
    return [
        "- Develop an independent lyrical exploration of the accepted current Keter brief.",
        "- Give every artifact a structured scope: episode, act, or scene; season is assigned only by the partner.",
        "- Scope describes the artifact's dramatic reach; level two explores material and does not create issues.",
        "- Later assignments may create issues at episode, act, or scene scope; every branch ultimately reaches ready scene leaves, with intermediate scopes or same-scope development as needed.",
        "- Explore possibility, resistance, motivation, visible action, imagery, scenes, and beats through this perspective.",
        "- Preserve source references and ancestry; keep beats inside scenes.",
        "- Leave unresolved divergent choices to the partner using a structured question outcome.",
    ]


def build_comment_phase_prompt(
    label: str,
    issue: int,
    repo: str,
    microagent: str,
    phase: str,
    issue_data: dict[str, Any],
) -> str:
    """Build the literary phase prompt with the harness-owned result contract."""
    from .validation import result_contract

    responsibilities = {
        "1": "Receive the human intention and inherited material. Establish a broad narrative stroke with precise pursuit, opposition, pressure, change, and dramatic question. Preserve canon naturally in the writing.",
        "2A": "Discover generative possibilities and surprising action through Chokhmah.",
        "2B": "Explore resistance, consequence, and dramatic structure through Binah.",
        "2C": "Explore motivation, relationships, emotional generosity, and imagery through Chesed.",
        "3": "Synthesize all three current explorations into dramatic anchors, their relationships, possible scenes, ordered beat coverage, and material needing further development. Preserve the partner's authority over divergent choices.",
    }
    instructions = [responsibilities[phase]]
    if phase in {"2A", "2B", "2C"}:
        instructions.extend(build_phase_2_story_requirements())
    return f"""{strip_microagent(microagent)}

{build_phase_prompt_input_context(label, issue, repo, phase, issue_data)}

{chr(10).join(instructions)}

Return raw structured JSON only, without code fences.
Python renders public comments, headings, identifiers, ancestry, and source-reference lines.
Keep narrative content separate from status, scope, references, and readiness.
Questions for the partner pause advancement; use the structured outcome instead of declaring an execution failure.

{result_contract(phase)}
"""


def build_tiferet_specification_prompt(
    label: str,
    issue: int,
    repo: str,
    microagent: str,
    phase: str,
    issue_data: dict[str, Any],
) -> str:
    """Turn accepted dramatic organization into ready scenes and recursive work."""
    from .validation import result_contract

    return f"""{strip_microagent(microagent)}

{build_phase_prompt_input_context(label, issue, repo, phase, issue_data)}

Turn the accepted synthesis into concrete scene outlines and recursive assignments.
Preserve its organization, source anchors, relationships, scope, and ancestry.
A single result may contain ready scenes and material requiring further development.
A ready scene needs an established outline, ordered nonempty beats covering its assigned
anchors, episode ownership, act placement, and scene identity. Larger elements and unfinished
scenes receive a specific development brief, an unresolved question, and the reason for returning.
The same scope may need another cycle; do not force a sequence of smaller sizes.
Issues may exist at episode, act, or scene scope, but every branch must ultimately
reach ready scene leaves. Larger and unfinished scene assignments continue development.
Generated artifacts use episode, act, or scene scope. Season is created only by the partner.
Unresolved structural choices return for development or a question to the partner; do not silently rewrite them.

Return raw structured JSON only, without code fences.
Python renders public comments, headings, identifiers, ancestry, beat-reference lines,
child issue bodies, size labels, phase labels, and child summaries.
Python owns GitHub dependencies, parent membership, and completion rollup.
Supply dramatic assignments; the harness derives and maintains these GitHub relationships.
One script.md per episode contains all acts, scenes, and beats. Beats are never issues or files.
Questions for the partner pause advancement and child creation.

{result_contract(phase)}
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
        "- If a command remains active, use the available process/session tool to inspect or interrupt it before retrying a narrower command.",
        "- Do not loop on blocked terminal state; recover and continue the requested writing artifacts.",
    ]
    phase_requirements: list[str] = []
    if phase == "5":
        from .cycles import ready_assignment

        assignment = ready_assignment(issue_data)
        phase_requirements = [
            "- Prepare the validated ready-scene assignment below, preserving ordered beats and source anchors.",
            "- Use one script.md per episode, containing all acts, scenes, and beats; keep preparation in scene_materials/<scene_id>/.",
            "- Preserve episode ownership, act placement, scene identity, and all neighboring scene regions.",
            json.dumps(assignment, ensure_ascii=False, indent=2),
        ]
    elif phase == "7":
        phase_requirements = [
            "- Phase 7 (Dramatic-Action Preparation): write dramatic_action_brief.md.",
            "- Establish stimulus, knowledge, ignorance, concealment, objectives, emotion, stakes, relationships and available actions for each dramatic moment.",
            "- Preserve canonical moment IDs and include non-speaking characters; do not predetermine discretionary responses or write final dialogue.",
            "- Use the microagent's JSON brief contract with existing source paths; missing context blocks completion.",
        ]
    elif phase == "8":
        phase_requirements = [
            "- Phase 8 (Performance Materials): preserve the attributed skeleton, do not draft dialogue or prose.",
            "- Create scene_materials/<scene_id>/ with AGENTS.md, scene_skeleton.md, scene_template.md, copied dramatic_action_brief.md and a version 2 performance_context.json.",
            "- Insert the bounded scene_template.md once into the episode script.md as <!-- SCENE scene-id BEGIN --> through END; preserve front matter, act headings and every other scene region.",
            "- Never append a duplicate scene ID or replace an existing differing region automatically. The handoff manuscript_path must name that episode script.md.",
            "- Prepare real numbered Script/Season_<digits>/Episode_<digits>/scene_materials/<scene_id>/ directories outside season_template; use a [A-Za-z0-9_-]+ scene ID.",
            "- Use an uppercase ### SCENE <digits> — <UPPERCASE TITLE> heading and established opening directions in scene_template.md.",
            "- Include full director source references, stable IDs with nonempty single-line display_name, and separate own-character starting contexts.",
            "- Apply the completion gate: matching scenes, cast, moments and existing sources; preserve source brief, skeleton constraints and the initial manuscript region exactly.",
        ]
    elif phase == "9":
        phase_requirements = [
            "- Phase 9 (Director's Roundtable): Python orchestrates separate native sessions and writes the public script.",
            "- The omniscient director receives all prior context plus each fictional inner_monologue and outer_response.",
            "- Characters receive only their own context and eligible observations; they choose action, dialogue or silence.",
            "- Return schema-valid role turns; explicit completion and performed moment coverage are required before Python delivery.",
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
    lines = [f"Spawned {len(created)} dramatic assignments in organization order:"]
    for item in created:
        lines.append(f"- {item['title']}: {item['url']}")
    return "\n".join(lines)
