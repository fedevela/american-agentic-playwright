from __future__ import annotations

from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class SfiratPhaseSignal:
    """
    The immutable payload carrying the intent and context of a SPARC phase.
    
    This 'Signal' is the primary object moving through the orchestrator.
    It encapsulates the metadata (repo, issue, label) and the prompt content 
    (microagent_persona + personas) required for the Malakh (agent) to act.
    """

    label: str
    issue: int
    repo: str
    microagent_persona_content: str
    phase: str
    issue_data: dict[str, Any]