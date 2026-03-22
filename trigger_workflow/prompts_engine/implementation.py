from __future__ import annotations

from typing import Any
from .extraction import build_issue_runtime_context, strip_microagent_persona_persona
from .extraction import COMMENT_VISIBLE_PHASES


PHASE_10_PASSES = [
    (
        "Purging Transient Scaffolding",
        "Remove leftover temporary traceability markers (like MRCO-003, MRCO-006, 'Phase 5 - Netzach', and 'Phase 8 - Yesod') or other phases (or names of phases) leftovers or user stories guids... while leaving the useful comments.",
    ),
    (
        "Pruning Superfluous & Unused Code",
        "Prune any superfluous/redundant/unused/unnecessarily complex code or unnecessary fallbacks or retries where we can fail fast, also check imports we can safely remove. use ruff. Simplify test names that sounded overly academic (e.g., changing contract and domain_payload to more literal domain names).",
    ),
    (
        "Removing Clutter & Assessing Bloat",
        "Identify and purge all leftover execution/phase/llm artifacts, such as @patch_ensure.py files and transient session shims, to ensure a clean environment. Audit the codebase for files exceeding a ~500-line threshold or those conflating multiple concerns; these must be aggressively modularized. When splitting these 'bloated' files, extract secondary logic into shared .py seams to enforce single-responsibility boundaries and eliminate redundant complexity.",
    ),
    (
        "Applying DRY & SOLID Principles",
        "Enforce strict SOLID and DRY principles by extracting duplicated validation and configuration logic into shared, centralized seams. Prioritize the Dependency Inversion Principle by injecting providers for environmental configurations rather than relying on hardcoded strings or internal constants. Identify and resolve handler collisions or hidden race conditions within the logic.",
    ),
    (
        "Updating Operational Maps (AGENTS.md & README.md)",
        "Update all AGENTS.md and README.md files with the relevant information from changes that have been done in this branch. Also, create agents files where source folders are lacking them and fill them up with relevant info.",
    ),
    (
        "Encoding Architecture into Executable Names",
        "Update the codebase's names (e.g. functions, variables, tests) to reflect the domain language from agents and readmes.",
    ),
    (
        "Updating Documentation",
        "Update the codebase's documentation (e.g. functions headers, variables comments, tests, inline 'why' comments) to reflect the domain language from agents and readmes.",
    ),
]


def build_implementation_phase_prompt(
    label: str,
    issue: int,
    repo: str,
    microagent_persona_persona: str,
    phase: str,
    issue_data: dict[str, Any],
    pass_instruction: tuple[str, str] | None = None,
) -> str:
    """Build the prompt for phases 5-9 implementation and validation work, and phase 10 passes."""
    terminal_discipline_requirements = [
        "- Terminal discipline (mandatory): favor bounded, deterministic commands (`rg`, targeted paths) and avoid broad recursive scans from repo root.",
        "- Exclude heavy/generated trees when searching (for example `node_modules`, `build`, `.git`) unless explicitly needed.",
        "- Always constrain potentially long-running commands (path filters and/or explicit command timeouts).",
        "- If terminal reports the previous command is still running and blocks new commands, immediately recover by interacting with the active process (`is_input=true`): first poll with empty input, then interrupt with `C-c` if needed, then continue with a narrower command.",
        "- Do not loop on blocked terminal state; recover deterministically and proceed with code edits.",
        "- When you have completed all validation and code changes, your final text response MUST be a clear, high-level semantic summary of the implementation you just performed (what files were touched, what logic was added/changed). This summary will be posted directly to the GitHub issue.",
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
            "- This is Phase 9 (Malkhut Completion). The system must cease to be a model and become a fact.",
            "- Actively complete the implementation: find what is missing and make it exist.",
            "- Expand verification boundaries: you must actively expand testing coverage where possible, especially for edge cases.",
            "- Truth is derived from observable outcomes: run the tests, fix the implementation, and repeat until the work lives in the world as intended.",
            "- ALWAYS produce a final text message summarizing the completed implementation, expanded tests, and readiness status.",
        ]
    elif phase == "10":
        if not pass_instruction:
            raise ValueError("Phase 10 requires a pass_instruction to be provided.")
        
        # Override the standard discovery procedure for Phase 10
        discovery_procedure = [
            "1. Discovery: Search the codebase to identify areas relevant to your current pass instruction.",
            "2. Planning: Define the exact refactoring edits required to satisfy the instruction.",
            "3. Execution: Apply the refactoring changes.",
            "4. Verification: Run the test suite and resolve any breakages caused by your refactoring.",
        ]
        
        phase_requirements = [
            "- This is Phase 10 (Hod Refactoring). Expose the system's architecture clearly and re-encode it into the code.",
            f"- CURRENT PASS: {pass_instruction[0]}",
            f"- INSTRUCTION: {pass_instruction[1]}",
            "- ONLY execute the logic required for this current pass. DO NOT expand scope into other refactoring tasks.",
            "- Run the validation tests (`make test` or equivalent) to ensure your refactoring did not break the system.",
            "- Return a final text message summarizing the refactoring work you completed.",
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

    runtime_context = (
        "" if phase == "10"
        else build_issue_runtime_context(label, issue, repo, phase, issue_data, include_comments=phase in COMMENT_VISIBLE_PHASES)
    )

    return f"""{strip_microagent_persona_persona(microagent_persona_persona)}

{runtime_context}

{requirements_block}

Execute your phase logic now.
"""