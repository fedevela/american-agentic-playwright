# Agent Notes: Swarm

This document captures the practical architecture and execution rules for working safely in this repository.

## Entry Point

- `trigger.py` should be called from the target repository root.
- It is a thin CLI shim that calls `trigger_workflow.router.run_trigger_cli()`.

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
3. Builds the persona + microagent prompt stack
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

- `trigger_workflow/config.py`
  - Canonical phase/label maps
  - Successor mapping (`NEXT_LABEL_MAP`)

- `trigger_workflow/router.py`
  - Top-level orchestration + phase dispatch
  - Manual preview mode behavior
  - Needs-human tagging for pre-implementation failures
  - Local repository detection

- `trigger_workflow/prompts.py`
  - Prompt construction and context shaping
  - Persona + functional microagent composition
  - Phase comment wrapper formatting

- `trigger_workflow/github_ops.py`
  - GitHub CLI wrappers (`gh issue/label/api`)
  - Label handoff operations
  - Child issue creation/linking/dependency wiring

- `trigger_workflow/validation.py`
  - Tiferet JSON payload schema checks
  - Verbatim traceability checks to Gevurah canonical requirements

- `trigger_workflow/gemini_runner.py`
  - Gemini CLI subprocess execution.
  - Optimized for fast, single-turn or fixed-retry cycles.

- `trigger_workflow/runner_utils.py`
  - Current directory branch verification and resolution
  - Validation retry loop for implementation phases
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

- Router behavior: `tests/trigger_workflow/test_router.py`
- GitHub operations: `tests/trigger_workflow/test_github_ops.py`
- Prompt contracts: `tests/trigger_workflow/test_prompts.py`
- Tiferet validation rules: `tests/trigger_workflow/test_validation.py`

## MCP Integration Seam (for future work)

Best attachment point is to expose MCP tools that call:
- `run_labeled_issue_phase_with_mode(...)` for end-to-end phase execution/preview
- selected read/write functions in `github_ops.py` for fine-grained issue operations

This keeps current router logic as the source of truth and avoids duplicated orchestration logic.
