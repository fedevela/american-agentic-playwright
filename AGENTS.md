# Agent Notes: Swarm

This document captures the practical architecture and execution rules for working safely in this repository.

## Entry Point

- `trigger.py` should be called from the target repository root.
- It is a thin CLI shim that calls `trigger_workflow.cli.run_trigger_cli()`.

## Runtime Flow

`run_trigger_cli()` parses:
- `--label`: GitHub label triggering the phase.
- `--phase`: Canonical phase ID (alternative to --label).
- `--issue`: Issue number to process.
- `--repo`: Target repository (owner/repo).
- `--manual`: Preview mode (no agent execution or GitHub mutations).

Then delegates to `run_labeled_issue_phase_with_mode(...)`, which:
1. Ensures canonical labels exist (unless `--manual`)
2. Resolves issue + phase label (or auto-selects oldest phased issue)
3. Builds the persona + microagent_persona prompt stack
4. Fetches issue payload from GitHub
5. Verifies phase-label preconditions (relaxed in manual mode)
6. Dispatches by phase family

## Phase Families

- Discussion phases: `1`, `2A`, `2B`, `2C`, `3`
  - Agent generates comment text
  - Router posts wrapped phase comment
  - Router advances label to next phase

- Specification phase: `4` (Tiferet)
  - Agent returns JSON payload with:
    - parent `comment`
    - ordered `sub_issues`
  - Validation enforces schema + Gevurah traceability contract
  - Creates child issues with parent/sub-issue + dependency links
  - Posts summary comment
  - Removes parent Tiferet label

- Implementation phases: `5`, `6`, `7`, `8`, `9`, `10`
  - Agent runs against issue branch
  - Implementation phases run strict validation contract:
    - `npm run typecheck`
    - `npm run build`
    - `npm run test`
  - On success: finalize delivery with commit/push/PR and post summary
  - Advance issue label

## Module Map

- `trigger_workflow/cli.py`
  - CLI entry point and argument parsing (`run_trigger_cli`)
  - Maps phase IDs to canonical labels

- `trigger_workflow/orchestration.py`
  - Top-level workflow routing and phase dispatch (`route_labeled_signal_with_mode`)
  - Coordinates between context resolution and execution logic

- `trigger_workflow/context.py`
  - Exposes resolving logic via `SfiratPhaseSignal`

- `trigger_workflow/context_resolver/`
  - `models.py`: Core types like `SfiratPhaseSignal`
  - `policy.py`: Conversation scoping and repo detection
  - `resolution.py`: Context resolution (issue, label, repo)

- `trigger_workflow/execution.py`
  - Phase-specific execution logic:
    - `execute_comment_phase_handoff`
    - `manifest_specification_decomposition` (Tiferet)
    - `embody_implementation_contract` (Implementation)

- `trigger_workflow/execution_loop.py`
  - Validation retry loop for implementation phases (`run_agent_implementation_loop`)

- `trigger_workflow/preview.py`
  - Manual mode behavior and prompt-only previews

- `trigger_workflow/config.py`
  - Canonical phase/label maps
  - Successor mapping (`NEXT_LABEL_MAP`)

- `trigger_workflow/prompts.py`
  - Legacy facade for prompt building

- `trigger_workflow/prompts_engine/`
  - `discussion.py`: Prompts for early comment-based phases
  - `extraction.py`: Extracting contextual bodies from issues
  - `formatting.py`: Phase comment wrapper formatting
  - `implementation.py`: Code-editing phase prompts
  - `specification.py`: Phase 4 (Tiferet) spec prompts

- `trigger_workflow/domain.py`
  - Core types including `WorkflowPhase`

- `trigger_workflow/gh_client.py`
  - Low-level GitHub CLI execution

- `trigger_workflow/github/`
  - `comments.py`: Issue comment management
  - `constants.py`: Constants for the GitHub API
  - `discovery.py`: Issue lookup and label resolution
  - `hierarchy.py`: Sub-issue and dependency relations
  - `labels.py`: Phase label management

- `trigger_workflow/github_ops.py`
  - High-level facade for `github/` submodule operations

- `trigger_workflow/validation.py`
  - Tiferet JSON payload schema checks
  - Verbatim traceability checks to Gevurah canonical requirements

- `trigger_workflow/validation_runner.py`
  - Test execution framework for implementation validation

- `trigger_workflow/gemini_runner.py`
  - Gemini CLI subprocess execution.
  - Optimized for fast, single-turn or fixed-retry cycles.

- `trigger_workflow/git_client.py`
  - Version control operations and branch contexts

- `trigger_workflow/delivery.py`
  - Delivery finalization (commit/push/PR summary)

- `trigger_workflow/logging_utils.py`
  - Structured console logging helpers

## Operational Constraints

- Local execution policy:
  - Swarm runs directly in the current working directory.
  - The caller must ensure they are in the root of the target repository.
  - Managed clones and isolation folders are deprecated.

- Branch policy:
  - Phases before implementation run on configured main branch.
  - Implementation phases run on `issue/<number>` branch.
  - Missing implementation branch is a hard failure.

- Stateless conversation policy:
  - Runs do not resume prior conversations by default.
  - Conversation context is strictly scoped to the current phase.

- Delivery policy:
  - Refuses phase advancement without git changes.
  - Refuses fallback commit/PR titles when issue title is missing.
  - Push mismatch/rejection is hard-fail and requires human intervention.

## Tests Coverage

- CLI interactions: `tests/trigger_workflow/test_cli.py`
- Core Orchestration: `tests/trigger_workflow/test_orchestration.py`
- Github Base Ops: `tests/trigger_workflow/test_github_ops.py`, `test_github_labels.py`, `test_github_discovery.py`, `test_github_comments.py`
- Git Operations: `tests/trigger_workflow/test_git_client.py`
- Prompting engine: `tests/trigger_workflow/test_prompts.py`, `test_discussion_prompts.py`, `test_extraction.py`, `test_formatting.py`
- Resolution context: `tests/trigger_workflow/test_resolution.py`, `test_policy.py`
- Delivery & Execution: `tests/trigger_workflow/test_delivery.py`, `test_execution_loop.py`, `test_gemini_runner.py`, `test_validation_runner.py`, `test_preview.py`
- Tiferet payload shape checks: `tests/trigger_workflow/test_validation.py`

## MCP Integration Seam (for future work)

Best attachment point is to expose MCP tools that call:
- `run_labeled_issue_phase_with_mode(...)` for end-to-end phase execution/preview
- selected read/write functions in `github_ops.py` for fine-grained issue operations

This keeps current router logic as the source of truth and avoids duplicated orchestration logic.
