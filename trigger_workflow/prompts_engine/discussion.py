from __future__ import annotations

from typing import Any
from ..logging_utils import log_info
from .extraction import build_phase_prompt_input_context, strip_microagent_persona_persona

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
    microagent_persona_persona: str,
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

    return f"""{strip_microagent_persona_persona(microagent_persona_persona)}

{build_phase_prompt_input_context(label, issue, repo, phase, issue_data)}

## Practical Requirements
Return only the GitHub comment body for this phase.

Requirements:
{chr(10).join(requirements)}
"""