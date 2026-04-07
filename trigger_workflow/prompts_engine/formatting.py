from __future__ import annotations

from typing import Any
from ..config import PHASE_DISPLAY_NAME_MAP
from ..logging_utils import log_info

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
        lines.append(f"- {item['title']}: {item.get('html_url', item.get('url'))}")
    return "\n".join(lines)