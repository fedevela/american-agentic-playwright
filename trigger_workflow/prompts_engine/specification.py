from __future__ import annotations

from typing import Any
from ..config import TIFERET_AUTO_ISSUE_PREFIX
from .extraction import build_phase_prompt_input_context, strip_microagent_persona_persona

def build_tiferet_specification_prompt(
    label: str,
    issue: int,
    repo: str,
    microagent_persona_persona: str,
    phase: str,
    issue_data: dict[str, Any],
) -> str:
    """Build a prompt for phase 4/Tiferet, the child-issue specification phase."""
    return f"""{strip_microagent_persona_persona(microagent_persona_persona)}

{build_phase_prompt_input_context(label, issue, repo, phase, issue_data)}

## Practical Requirements
Return valid JSON only. No markdown fences. No explanation outside JSON.

Use this exact schema:
{{
  "comment": "GitHub comment body for the parent issue explaining the decomposition rationale",
  "sub_issues": [
    {{
      "title": "{TIFERET_AUTO_ISSUE_PREFIX}Short actionable issue title",
      "body": "Child issue body beginning with a requirement-id traceability line, then a Canonical Requirements section copying full Gevurah requirement sentences verbatim, then Gherkin-oriented Given/When/Then scenarios"
    }}
  ]
}}

Requirements:
- `comment` must summarize the specification and explain that child issues were spawned.
- `comment` must explicitly reconcile the Gevurah input against the final child issue set.
- `comment` must explain the grouping logic for every child issue, not only the final counts.
- `comment` must state which requirement IDs are covered by each child issue and why those IDs belong together.
- If multiple Gevurah requirements were merged, collapsed as duplicates, absorbed into another issue, or deferred, explain that in the `comment`.
- If the number of child issues differs from the number of Gevurah suggestions, explain why the counts differ in the `comment`.
- `sub_issues` must contain one or more items.
- Order `sub_issues` from earliest required implementation step to latest dependent step.
- Prefix every child issue title with `{TIFERET_AUTO_ISSUE_PREFIX}` so auto-created issues are visibly distinct from human-authored issues.
- Every child issue body must begin with a `Requirement IDs:` line listing every Gevurah GUID consolidated into that child issue.
- The requirement-id list must be complete for that child issue; do not omit any covered Gevurah requirement IDs.
- Every child issue body must contain a `Canonical Requirements` section immediately after the requirement-id line.
- In that section, include one bullet per listed requirement ID in the exact Gevurah form `- CH-001: ...`.
- Copy the full canonical requirement sentences verbatim from the Gevurah `Canonical Requirements` section. Do not paraphrase or compress them.
- Each child issue body must use Gherkin language with explicit `Given`, `When`, and `Then` sections.
- Assume child issues will be created in listed order, attached as sub-issues to the parent issue, and each later child issue blocked by the immediately preceding child issue.
- Do not mention tool limitations, environment limitations, or inability to post.
"""