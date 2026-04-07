from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class WorkflowPhase:
    """Represents a discrete phase in the agentic workflow."""
    id: str
    label: str
    name: str
    description: str
    color: str
    persona_file: str
    microagent_persona_file: str
    next_phase_label: Optional[str]

    @property
    def is_discussion_phase(self) -> bool:
        return self.id in {"1", "2A", "2B", "2C", "3"}
        
    @property
    def is_implementation_phase(self) -> bool:
        return self.id in {"5", "6", "7", "8", "9", "10"}

@dataclass(frozen=True)
class IssueContext:
    """Encapsulates the context of a GitHub issue being processed."""
    number: int
    title: str
    body: str
    comments: list[dict]
    repository: str

@dataclass(frozen=True)
class DeliveryResult:
    """Represents the outcome of a phase delivery."""
    success: bool
    requires_human: bool
    message: str
    next_label: Optional[str] = None
    pr_url: Optional[str] = None
