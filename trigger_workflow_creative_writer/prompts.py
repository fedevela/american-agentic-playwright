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
    from .story_records import public_markdown
    body = public_markdown(issue_data.get("body", ""))
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
        body_text = public_markdown(str(comment.get("body") or ""))
        if not body_text:
            continue
        rendered_comments.append(f"### Comment {i}\n{body_text}")

    comments_block = "\n\n".join(rendered_comments) if rendered_comments else "(none)"
    return f"""{context}

## Issue Comments

{comments_block}
"""


def issue_conversation_context(issue_data: dict, parents: list[dict]) -> str:
    """Keep recent issue conversation ahead of earlier generated material."""
    from .story_records import ROOT, public_markdown
    comments = []
    for source in [issue_data, *parents]:
        number = source.get('number', source.get('issue'))
        for comment in source.get('comments', []):
            body = str(comment.get('body') or '')
            author = comment.get('author') or comment.get('user') or {}
            login = author.get('login', 'unknown')
            machine = comment.get('_workflow') or '<!-- phase:' in body or ROOT.search(body) or body.startswith('### Phase ')
            if machine or not body.strip():
                continue
            comments.append((comment.get('createdAt') or comment.get('created_at') or '',
                             f"### @{login} · issue #{number} · {comment.get('url') or comment.get('html_url') or ''}\n\n{public_markdown(body)}"))
    comments.sort(key=lambda item: item[0], reverse=True)
    return ("## Current issue conversation\n\n"
            "Apply the current direction in these comments when interpreting earlier proposals. "
            "Comments need no special format. Read questions and discussion in context.\n\n"
            + ('\n\n'.join(body for _, body in comments) or '(No additional comments.)'))



def build_phase_prompt_input_context(label: str, issue: int, repo: str, phase: str, issue_data: dict[str, Any]) -> str:
    """Use visible GitHub material once, with current conversation ahead of proposals."""
    from . import cycles, story_records
    from .github_ops import parent_story_context
    parents = parent_story_context()
    instructions = issue_conversation_context(issue_data, parents)
    if phase not in {'1', '2A', '2B', '2C', '3', '4'}:
        return instructions + '\n\n' + build_issue_runtime_context(label, issue, repo, phase, issue_data)
    cycle = cycles.current_cycle(issue_data)
    if cycle is None:
        require_phase = phase == '1'
        if not require_phase:
            raise SystemExit('Start a fresh Keter cycle to establish visible workflow output.')
        cycle = {'cycle_id': 'preview-cycle', 'scope': cycles.issue_scope(issue_data)}
    selected = {'1': (), '2A': ('1',), '2B': ('1',), '2C': ('1',),
                '3': ('1', '2A', '2B', '2C'), '4': ('3',)}[phase]
    accepted = cycles.accepted_results(issue_data)
    if any(p not in accepted for p in selected):
        raise SystemExit('Required visible phase output is missing; inspect the active issue.')
    comments = []
    ids = {accepted[p].get('_source', {}).get('comment') for p in selected}
    for comment in issue_data.get('comments', []):
        if comment.get('id') in ids:
            comments.append(story_records.public_markdown(comment.get('body', '')))
    runtime_data = issue_data if phase not in {'2A', '2B', '2C'} else {}
    runtime = build_issue_runtime_context(label, issue, repo, phase, runtime_data)
    if not runtime_data:
        runtime = runtime.split('## Issue Content', 1)[0]
    parts = [instructions, runtime, f"Current scope: {cycle['scope']}. Python supplies cycle ownership; do not return cycle_id."]
    if phase == '1':
        inherited = cycles.source_context(issue_data)
        if inherited.get('anchors'):
            parts.append('## Material to develop\n\n' + story_records.render({'kind': 'result', 'anchors': inherited['anchors']}))
        if cycle.get('prior_cycle'):
            parts.append('## Development direction\n\n' + cycle.get('development_question', '') + '\n\n' + cycle.get('return_reason', ''))
    parts.extend(comments)
    if phase in {'1', '2A', '2B', '2C', '3'}:
        from .reference_resolution import phase_source_beats, retained_beat_names, new_beat_prefix
        source_beats = phase_source_beats(issue_data, phase)
        prefix = new_beat_prefix(source_beats, phase)
        parts.append('## New beat IDs\n\n'
                     f'For every new event use {prefix}<positive beat number>, starting with {prefix}1. '
                     'Python reserved this stem outside the supplied ancestry. '
                     'This exact prefix overrides generic ID examples. Retained events keep their source IDs.')
        if source_beats:
            parts.append('## Exact source beat IDs\n\n'
                         'Copy an ID from this list when retaining an incoming beat. '
                         'Do not reconstruct its spelling from a display heading. '
                         'Readable alternatives in the list identify the same supplied sources.\n\n'
                         + json.dumps(retained_beat_names(source_beats), ensure_ascii=False))
    if phase in {'2A', '2B', '2C'}:
        parts.append('Explore Keter independently. Other phase-2 outputs are outside this perspective; current issue conversation still applies.')
    else:
        parts.extend(f"Earlier phase comment: {c.get('url') or c.get('html_url') or c.get('id')}" for c in issue_data.get('comments', [])
                     if c.get('id') not in ids and ('<!-- phase:' in c.get('body', '') or c.get('body', '').startswith('### Phase ')))
    if phase not in {'2A', '2B', '2C'}:
        for parent in parents:
            parts.append(f"## Parent issue #{parent['issue']}: {parent['title']}\n\n{parent['body']}")
            parts.extend(f"Parent comment: {c.get('url') or c.get('html_url') or c.get('id')}"
                         for c in parent['comments'] if c.get('_workflow'))
    parts.append('GitHub issues and repository files are the memory. Consult relevant linked comments and source files as needed; use current issue direction when interpreting earlier output.')
    return '\n\n'.join(parts)


def strip_microagent(microagent: str) -> str:
    """Normalize the microagent content before embedding."""
    microagent_stripped = microagent.strip()
    if microagent_stripped.endswith("EOF"):
        microagent_stripped = microagent_stripped[:-3].strip()
    return microagent_stripped


def build_phase_2_story_requirements() -> list[str]:
    """Return shared dramatic exploration instructions for level two."""
    return [
        "- Explore the accepted current Keter brief independently, with one short sentence on one line per item. Keep the narrative field to one short orienting sentence.",
        "- Give every artifact a structured scope: episode, act, scene, or undetermined; season scope belongs to the existing project root.",
        "- Let dramatic purpose establish the material. Use undetermined (scope to be discovered) while its form remains open; level two explores material and does not create issues.",
        "- Later assignments may create issues at episode, act, scene, or undetermined scope; every branch ultimately reaches ready scene leaves, with intermediate scopes or same-scope development as needed.",
        "- Offer premise-level possibilities, resistance, or grounding through this perspective; each artifact contains a single conceptual idea.",
        "- Maintain, transform, or create pivotal beats through this perspective. Every artifact carries pivotal_beats with stable BEAT-* IDs, one-sentence event/change content, source_beat_ids. Preserve incoming identity or link a new successor.",
        "- Explore divergent possibilities independently and state useful assumptions; carry open dramatic questions into development.",
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
        "1": "Receive the supplied intention and inherited material. Establish a broad narrative stroke with precise pursuit, opposition, pressure, change, and dramatic question. Preserve canon naturally in the writing. Give every anchor a one-sentence pivotal_beat describing an event and consequential change. Evaluate inherited pivotal beats and carry their identities forward.",
        "2A": "Discover premise-level possibilities through Chokhmah.",
        "2B": "Explore resistance, consequence, and dramatic structure through Binah.",
        "2C": "Explore causal conditions, relationships, material circumstances, and stakes through Chesed.",
        "3": "Synthesize all three current explorations into ordered elements for issue creation, supported by dramatic anchors and their relationships. Let each element express a milestone, circumstance, or dramatic change; exploration may discover its scene, act, or episode form later. Resolve divergent choices through independent dramatic judgment within the supplied intention and canon. Give each element exactly one is_pivotal=true beat, including undetermined elements; scene splits each receive a distinct pivotal change, with each pivotal beat expressed in one dramatic sentence.",
    }
    instructions = ['The character is the supreme writer of their own thoughts, dialogue, and actions. Every phase contributes conditions and opportunities for that authorship; the character gives them lived expression. Work independently from the supplied intention and established canon, making creative decisions within those constraints. Established character history remains context; new performance belongs to its character.', responsibilities[phase]]
    if phase in {"2A", "2B", "2C"}:
        instructions.extend(build_phase_2_story_requirements())
    return f"""{strip_microagent(microagent)}

{build_phase_prompt_input_context(label, issue, repo, phase, issue_data)}

{chr(10).join(instructions)}

Return raw structured JSON only, without code fences.
Python renders public comments, headings, identifiers, ancestry, and source-reference lines.
Keep narrative content separate from status, scope, references, and readiness.
Resolve creative uncertainty independently; express further exploration as development work with a specific question and reason.

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

The character is the supreme writer of their own thoughts, dialogue, and actions. Every phase contributes conditions and opportunities for that authorship; the character gives them lived expression. Work independently from the supplied intention and established canon, making creative decisions within those constraints. Established character history remains context; new performance belongs to its character.

Turn the accepted synthesis into concrete scene outlines and recursive assignments.
Preserve its ordered elements, source anchors, relationships, scope, and ancestry.
Create one assignment per accepted element, in order. Preserve its pivotal beat and
all supporting beats, is_pivotal markers, pivotal_beat_id identities and predecessor links. The child develops around that inherited
hypothesis and may revise it in Keter with an explanation. Undetermined elements keep
their dramatic purpose, prior outline and beat ideas, development_question and return_reason;
placement may remain null. Python gives them size:undetermined and routes them to Keter.
Keep the originating issue scope stable throughout its cycle. Its descendants may
discover concrete scopes or continue undetermined; it remains their development container.
A single result may contain ready scenes and material requiring further development.
A ready scene needs an established outline, ordered nonempty beats covering its assigned
anchors, episode ownership, act placement, and scene identity. Larger elements and unfinished
scenes receive a specific development brief, an unresolved question, and the reason for returning.
The same scope may need another cycle; do not force a sequence of smaller sizes.
Issues may exist at episode, act, scene, or undetermined scope, but every branch must ultimately
reach ready scene leaves. Larger and unfinished scene assignments continue development.
Generated artifacts use episode, act, scene, or undetermined scope. Season scope belongs to the existing project root.
Carry open structural choices in development assignments while preserving the accepted organization.

Return raw structured JSON only, without code fences.
Python renders public comments, headings, identifiers, ancestry, beat-reference lines,
child issue bodies, size labels, phase labels, and child summaries.
Python owns GitHub dependencies, parent membership, and completion rollup.
Supply dramatic assignments; the harness derives and maintains these GitHub relationships.
One script.md per episode contains all acts, scenes, and beats. Beats are never issues or files.
Use outcome=complete when every accepted element has its assignment, including when all elements need development.

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
    if phase != "9":
        from .cycles import ready_assignment
        from .story_records import clean
        from .github_ops import parent_story_context
        phase_requirements.extend(f"Parent issue #{p['issue']}: {p['title']}\n{p['body']}" for p in parent_story_context())
        phase_requirements.extend(f"Earlier phase comment: {c.get('url') or c.get('html_url') or c.get('id')}" for c in issue_data.get("comments", [])
                                  if "<!-- phase:" in c.get("body", "") or c.get("body", "").startswith("### Phase "))
        inherited = ready_assignment(issue_data)
        phase_requirements.append("- The active issue and its parent chain are the source of truth for this work; use their visible accepted material and source links. Canon and performance files remain the artifacts you consult and maintain.")
        if inherited:
            phase_requirements.append(json.dumps(clean({k: inherited[k] for k in ('element', 'anchors')}), ensure_ascii=False, indent=2))
    source_requirements = phase_requirements
    phase_requirements = []
    if phase == "5":
        from .cycles import ready_assignment

        ready_assignment(issue_data)
        phase_requirements = [
            "- Prepare the validated ready-scene assignment below, preserving ordered beats, BEAT-* pivotal identities and predecessor links, and source anchors.",
            "- Use one script.md per episode, containing all acts, scenes, and beats; keep preparation in scene_materials/<scene_id>/.",
            "- Preserve episode ownership, act placement, scene identity, and all neighboring scene regions.",

        ]
    elif phase == "7":
        phase_requirements = [
            "- Phase 7 (Dramatic-Action Preparation): write dramatic_action_brief.md.",
            "- Establish stimulus, sourced starting knowledge and emotion, stakes, relationships, and available affordances for each dramatic moment; character choices remain open.",
            "- Preserve canonical moment IDs and include non-speaking characters; do not predetermine discretionary responses or write final dialogue.",
            "- Use the microagent's JSON brief contract with existing source paths; missing context blocks completion.",
        ]
    elif phase == "8":
        phase_requirements = [
            "- Phase 8 (Performance Materials): preserve the attributed skeleton, do not draft dialogue or prose.",
            "- Create scene_materials/<scene_id>/ with AGENTS.md, scene_skeleton.md, scene_template.md, copied dramatic_action_brief.md and a version 3 performance_context.json.",
            "- Insert the bounded scene_template.md once into the episode script.md as <!-- SCENE scene-id BEGIN --> through END; preserve front matter, act headings and every other scene region.",
            "- Never append a duplicate scene ID or replace an existing differing region automatically. The handoff manuscript_path must name that episode script.md.",
            "- Prepare real numbered Script/Season_<digits>/Episode_<digits>/scene_materials/<scene_id>/ directories outside season_template; use a [A-Za-z0-9_-]+ scene ID.",
            "- Use an uppercase ### SCENE <digits> — <UPPERCASE TITLE> heading and established opening directions in scene_template.md.",
            "- Include full director source references, stable IDs with nonempty single-line display_name, and separate own-character starting contexts.",
            "- Explicitly nominate spoiler-free actor_safe_bible_paths (an empty list is valid); never include character folders or unreviewed omniscient sources.",
            "- Give every actor a scene_context describing their surrounding issue/scene and moment_contexts for each beat from their perspective; Python supplies only the current beat, without future developments or other characters' secrets.",
            "- Apply the completion gate: matching scenes, cast, moments and existing sources; preserve source brief, skeleton constraints and the initial manuscript region exactly.",
        ]
    elif phase == "9":
        phase_requirements = [
            "- Phase 9 (Director's Roundtable): Python orchestrates separate native sessions and writes the public script.",
            "- Actors return ordered items with category thought, dialogue or action and text; any number and order of their own contributions is allowed. Thoughts stay private; deliberate silence is an action.",
            "- The omniscient director receives complete fictional contributions and assigns previous_item_observers for every dialogue/action item by harness-issued item_id.",
            "- Python launches/resumes each actor from bible/characters/<character_id>/ and supplies own context, designated bible files, actor-facing issue/scene and current-beat context, and eligible observations. The director runs from the story root.",
            "- Return schema-valid role turns; explicit completion and performed moment coverage are required before Python delivery.",
        ]
    phase_requirements = source_requirements + phase_requirements
    requirements_block = ""
    requirement_lines = ['The character is the supreme writer of their own thoughts, dialogue, and actions. Every phase contributes conditions and opportunities for that authorship; the character gives them lived expression. Work independently from the supplied intention and established canon, making creative decisions within those constraints. Established character history remains context; new performance belongs to its character.', *terminal_discipline_requirements, *phase_requirements]
    if requirement_lines:
        requirements_block = f"\n\nPhase-specific requirements:\n{chr(10).join(requirement_lines)}"

    return f"""{issue_conversation_context(issue_data, parent_story_context()) if phase != "9" else ""}

{strip_microagent(microagent)}

{build_issue_runtime_context(label, issue, repo, phase, issue_data, include_comments=phase == "9")}

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
    return f"### Phase {phase.upper()}: {display_name}\n\n{normalized_body}"


def build_phase_four_summary(created: list[dict[str, Any]]) -> str:
    """Build the parent summary comment listing created child issues."""
    log_info("Building child-issue summary comment")
    lines = [f"Spawned {len(created)} dramatic assignments in organization order:"]
    for item in created:
        lines.append(f"- {item['title']}: {item['url']}")
    return "\n".join(lines)
