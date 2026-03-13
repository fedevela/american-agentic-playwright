from __future__ import annotations

import re
from typing import Any

from .logging_utils import log_error, log_info


REQUIREMENT_IDS_LINE_RE = re.compile(r"^Requirement IDs:\s+.+$", re.MULTILINE)
GUID_RE = re.compile(r"[A-Z0-9_]+-\d{3}")
GEVURAH_CANONICAL_BLOCK_RE = re.compile(
    r"## Canonical Requirements\s*(.*?)\s*## Synthesis Decisions",
    re.DOTALL,
)
CANONICAL_REQUIREMENT_LINE_RE = re.compile(r"^- ([A-Z0-9_]+-\d{3}):\s+(.+)$", re.MULTILINE)
CANONICAL_REQUIREMENTS_SECTION_RE = re.compile(
    r"^(?:##\s+)?Canonical Requirements:?\s*(.*?)(?:\n(?:##\s+.+|[A-Z][A-Za-z ]+:)\s*|\Z)",
    re.DOTALL | re.MULTILINE,
)


def validate_tiferet_specification_payload_structure(payload: dict[str, Any]) -> None:
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


def extract_gevurah_canonical_requirement_lines(issue_data: dict[str, Any]) -> dict[str, str]:
    """Extract the canonical Gevurah requirement lines from the phase-3 comment."""
    comments = issue_data.get("comments") or []
    for comment in comments:
        if not isinstance(comment, dict):
            continue
        body = str(comment.get("body") or "")
        if "<!-- phase:3:start" not in body:
            continue
        match = GEVURAH_CANONICAL_BLOCK_RE.search(body)
        if not match:
            raise SystemExit("Phase 4/Tiferet requires a Gevurah `Canonical Requirements` section, but none was found.")
        requirements: dict[str, str] = {}
        for requirement_match in CANONICAL_REQUIREMENT_LINE_RE.finditer(match.group(1)):
            requirement_id = requirement_match.group(1)
            sentence = requirement_match.group(2).strip()
            requirements[requirement_id] = f"- {requirement_id}: {sentence}"
        if not requirements:
            raise SystemExit("Phase 4/Tiferet requires at least one canonical Gevurah requirement line.")
        return requirements
    raise SystemExit("Phase 4/Tiferet requires an existing Phase 3/Gevurah comment, but none was found.")


def validate_tiferet_requirement_traceability(payload: dict[str, Any], issue_data: dict[str, Any]) -> None:
    """Ensure Tiferet child issues copy the full covered Gevurah requirement lines verbatim."""
    canonical_requirements = extract_gevurah_canonical_requirement_lines(issue_data)

    for i, item in enumerate(payload["sub_issues"]):
        body = str(item["body"]).strip()
        requirement_line_match = REQUIREMENT_IDS_LINE_RE.search(body)
        assert requirement_line_match is not None
        requirement_ids = GUID_RE.findall(requirement_line_match.group(0))

        section_match = CANONICAL_REQUIREMENTS_SECTION_RE.search(body)
        if not section_match:
            raise SystemExit(
                "Each phase 4/Tiferet child issue body must include a `Canonical Requirements:` section "
                "containing the full covered Gevurah requirement lines."
            )

        section_text = section_match.group(1)
        for requirement_id in requirement_ids:
            canonical_line = canonical_requirements.get(requirement_id)
            if canonical_line is None:
                raise SystemExit(
                    f"Phase 4/Tiferet referenced unknown Gevurah requirement id `{requirement_id}` in sub_issues[{i}]."
                )
            if canonical_line not in section_text:
                raise SystemExit(
                    f"Each phase 4/Tiferet child issue must copy the full Gevurah requirement line for `{requirement_id}` verbatim."
                )
