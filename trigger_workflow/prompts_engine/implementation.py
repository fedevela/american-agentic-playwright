from __future__ import annotations

from typing import Any
from .extraction import build_issue_runtime_context, strip_microagent_persona_persona
from .extraction import COMMENT_VISIBLE_PHASES


def build_diff_summary_prompt(diff_text: str) -> str:
    """Build a prompt asking the LLM to summarize a set of code changes."""
    return (
        "@codebase_investigator You are an expert software engineer.\n"
        "Please provide a concise, high-level summary of the following code changes.\n"
        "Focus on the 'why' and 'what', not line-by-line details. Keep it under 5 sentences if possible.\n\n"
        f"```diff\n{diff_text}\n```\n"
    )

def build_implementation_phase_prompt(
    label: str,
    issue: int,
    repo: str,
    microagent_persona_persona: str,
    phase: str,
    issue_data: dict[str, Any],
) -> str:
    """Build the prompt for phases 5-9 implementation and validation work."""
    terminal_discipline_requirements = [
        "- Terminal discipline (mandatory): favor bounded, deterministic commands (`rg`, targeted paths) and avoid broad recursive scans from repo root.",
        "- Exclude heavy/generated trees when searching (for example `node_modules`, `build`, `.git`) unless explicitly needed.",
        "- Always constrain potentially long-running commands (path filters and/or explicit command timeouts).",
        "- If terminal reports the previous command is still running and blocks new commands, immediately recover by interacting with the active process (`is_input=true`): first poll with empty input, then interrupt with `C-c` if needed, then continue with a narrower command.",
        "- Do not loop on blocked terminal state; recover deterministically and proceed with code edits.",
    ]
    
    discovery_procedure = [
        "1. Discovery: Read canonical requirement IDs and restate each as a phase-appropriate obligation (Traceability, Pseudocode, Architecture, or Implementation).",
        "2. Mapping: Map each obligation to an owning locus (file, module, or component).",
        "3. Planning: For each mapped locus, define the smallest artifact delta that preserves requirement traceability.",
        "4. Execution: Apply the smallest coherent artifact set that covers all mapped obligations.",
        "5. Verification: Before finishing, verify there is a non-empty diff and that changed files remain requirement-traceable.",
    ]

    phase_requirements: list[str] = []
    if phase == "5":
        phase_requirements = [
            "- This is Phase 5 (Netzach Traceability). Encode contracts into durable verification names (E2E tests).",
            "- Encode specification requirements into durable, self-describing verification names and traceable structure.",
            "- Use explicit no-op pass bodies (e.g. `assert True` or equivalent) while preserving traceability-oriented test names.",
            "- Do not introduce real behavioral assertions in this phase; those belong to later implementation phases.",
        ]
    elif phase == "6":
        phase_requirements = [
            "- This is Phase 6 (Hod Pseudocode). Turn the verification contract into procedural structure and bodyless logic placeholders.",
            "- Express logic through signatures, structure, and sequencing without prematurely implementing full behavior.",
            "- Keep the artifacts implementation-ready for the next phase.",
        ]
    elif phase == "7":
        phase_requirements = [
            "- This is Phase 7 (Yesod Architecture). Deliver architecture artifacts as code changes, not analysis-only notes.",
            "- Implement the smallest coherent architecture artifact set that fully covers canonical requirement IDs:",
            "  1) contract/type artifacts,",
            "  2) structural placement artifacts,",
            "  3) ownership-boundary artifacts,",
            "  4) dependency-direction artifacts,",
            "  5) integration-seam artifacts.",
            "- Keep artifacts requirement-traceable: each artifact must map to one or more canonical requirement IDs in the issue.",
            "- Do not stop at read-only analysis; leave a non-empty git diff with concrete architectural edits. DO NOT commit these changes.",
            "- Apply an explicit completion gate before finishing: if canonical requirement coverage or non-empty diff conditions are not met, continue implementing artifacts.",
            "- Do not fully implement end-user behavior; focus on placement, boundaries, contracts, and dependency direction.",
        ]
    elif phase == "8":
        phase_requirements = [
            "- This is Phase 8 (Yesod Refinement). Deliver implementation artifacts as code changes, not analysis-only notes.",
            "- Implement the smallest coherent set of contract-faithful deltas that covers all mapped implementation obligations.",
            "- Keep changes requirement-traceable: changed files and deltas must map to canonical requirement IDs.",
            "- Apply an explicit completion gate before finishing: if obligations are not covered or the implementation diff is empty, continue implementing.",
            "- Preserve prior contracts and boundaries; do not expand scope beyond required implementation obligations.",
        ]
    elif phase == "9":
        phase_requirements = [
            "- This is Phase 9 (Malkhut Completion). Execute validation with evidence-first discipline.",
            "- Run a deterministic validation-discovery pass: collect failing evidence, map each failure to violated requirement IDs and ownership loci, then apply minimal corrective deltas.",
            "- Keep corrections requirement-traceable and scope-bounded to observed violations.",
            "- Apply an explicit completion gate before finishing: do not terminate on narrative; finish only with evidence-backed readiness status.",
        ]
    elif phase == "10":
        phase_requirements = [
            "- This is Phase 10 (Hod Refactoring). Expose the system's architecture clearly and re-encode it into the code.",
            "- Model core domain entities as stable nouns (types/modules/objects) with clear ownership boundaries.",
            "- Model domain actions and process transitions as explicit verbs (functions/methods/use-cases).",
            "- Preserve behavior unless the partner explicitly asks for a behavior change.",
            "- PROPAGATE renames across production code, tests, and AGENTS.md in the same change.",
            "- Refactor duplicated orchestration and structure using DRY and SOLID boundaries.",
        ]

    requirements_block = ""
    requirement_lines = [*terminal_discipline_requirements, *phase_requirements]
    
    requirements_block = f"""
## Practical Context
You are working directly in a git repository. Your changes must be traceable.
**DO NOT RUN `git commit` OR `git push`.** The automated workflow will commit and push your changes after you finish.

## Discovery and Execution Procedure
{chr(10).join(discovery_procedure)}

## Operational Constraints and Requirements
{chr(10).join(requirement_lines)}
"""

    return f"""{strip_microagent_persona_persona(microagent_persona_persona)}

{build_issue_runtime_context(label, issue, repo, phase, issue_data, include_comments=phase in COMMENT_VISIBLE_PHASES)}

{requirements_block}

Execute your phase logic now.
"""