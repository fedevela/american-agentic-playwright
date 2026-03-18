from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class PhaseExecutionRequest:
    """Bundle the runtime inputs shared by all phase execution paths."""

    label: str
    issue: int
    repo: str
    microagent_content: str
    phase: str
    issue_data: dict[str, Any]
