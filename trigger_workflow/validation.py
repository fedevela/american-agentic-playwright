from __future__ import annotations

import re
from typing import Any

from .logging_utils import log_error, log_info


REQUIREMENT_IDS_LINE_RE = re.compile(r"^Requirement IDs:\s+.+$", re.MULTILINE)
GUID_RE = re.compile(r"[A-Z0-9_]+-\d{3}")


def validate_phase_four_payload(payload: dict[str, Any]) -> None:
    """Validate the minimal schema for the phase 4/Tiferet child-issue payload."""
    log_info("Validating payload structure...")
    if not isinstance(payload, dict):
        raise SystemExit("Phase 4/Tiferet payload must be a JSON object.")
    if not isinstance(payload.get("comment"), str) or not payload["comment"].strip():
        raise SystemExit("Phase 4/Tiferet payload must include a non-empty `comment`.")
    log_info("✓ Payload has valid 'comment' field")

    sub_issues = payload.get("sub_issues")
    if not isinstance(sub_issues, list) or not sub_issues:
        raise SystemExit("Phase 4/Tiferet payload must include at least one `sub_issues` entry.")
    log_info(f"✓ Payload has {len(sub_issues)} sub_issues")

    for i, item in enumerate(sub_issues):
        if not isinstance(item, dict):
            log_error(f"sub_issues[{i}] is not a JSON object")
            raise SystemExit("Each phase 4/Tiferet child issue must be an object.")
        if not isinstance(item.get("title"), str) or not item["title"].strip():
            log_error(f"sub_issues[{i}] is missing a non-empty title")
            raise SystemExit("Each phase 4/Tiferet child issue must include a non-empty `title`.")
        if not isinstance(item.get("body"), str) or not item["body"].strip():
            log_error(f"sub_issues[{i}] is missing a non-empty body")
            raise SystemExit("Each phase 4/Tiferet child issue must include a non-empty `body`.")
        body = item["body"].strip()
        if not REQUIREMENT_IDS_LINE_RE.search(body):
            log_error(f"sub_issues[{i}] is missing a Requirement IDs traceability line")
            raise SystemExit("Each phase 4/Tiferet child issue body must begin with a `Requirement IDs:` line.")
        requirement_line = REQUIREMENT_IDS_LINE_RE.search(body)
        assert requirement_line is not None
        if not GUID_RE.search(requirement_line.group(0)):
            log_error(f"sub_issues[{i}] Requirement IDs line does not contain any GUIDs")
            raise SystemExit("Each phase 4/Tiferet child issue must list at least one Gevurah GUID in `Requirement IDs:`.")
    log_info("✓ All sub_issues have valid structure")
