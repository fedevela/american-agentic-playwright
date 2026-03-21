from __future__ import annotations

from .config import LABEL_PHASE_MAP
from .prompts_engine.extraction import build_phase_prompt_input_context
from .prompts_engine.discussion import build_comment_phase_prompt, build_phase_2_story_requirements
from .prompts_engine.specification import build_tiferet_specification_prompt
from .prompts_engine.implementation import build_implementation_phase_prompt
from .prompts_engine.formatting import format_phase_comment, build_phase_four_summary

def determine_phase_from_label(label: str) -> str | None:
    """Map a canonical phase label to its canonical phase id."""
    return LABEL_PHASE_MAP.get(label)

__all__ = [
    "determine_phase_from_label",
    "build_phase_prompt_input_context",
    "build_comment_phase_prompt",
    "build_phase_2_story_requirements",
    "build_tiferet_specification_prompt",
    "build_implementation_phase_prompt",
    "format_phase_comment",
    "build_phase_four_summary",
]