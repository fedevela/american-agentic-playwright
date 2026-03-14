# Agent Notes: OpenHands Swarm

This document captures the practical architecture and execution rules for working safely in this repository.

## Entry Point

- `trigger.py` is a thin CLI shim that calls `trigger_workflow.router.run_trigger_cli()`.

## Runtime Flow

`run_trigger_cli()` parses:
- `--label`
- `--issue`
- `--repo`
- `--manual`

Then delegates to `run_labeled_issue_phase_with_mode(...)`, which:
1. Ensures canonical labels exist (unless `--manual`)
2. Resolves issue + phase label (or auto-selects oldest phased issue)
3. Builds the persona + microagent prompt stack
4. Fetches issue payload from GitHub
5. Verifies phase-label preconditions (relaxed in manual mode)
6. Dispatches by phase family

## Phase Families

- Discussion phases: `1`, `2a`, `2b`, `2c`, `3`
  - OpenHands generates comment text
  - Router posts wrapped phase comment
  - Router advances label to next phase

- Specification phase: `4` (Tiferet)
  - OpenHands returns JSON payload with:
    - parent `comment`
    - ordered `sub_issues`
  - Validation enforces schema + Gevurah traceability contract
  - Creates child issues with parent/sub-issue + dependency links
  - Creates child issue branches
  - Posts summary comment
  - Removes parent Tiferet label

- Implementation phases: `5`, `6`, `7`, `8`, `9`
  - OpenHands runs against issue branch
  - Phases `6-9` run strict validation contract:
    - `npm run typecheck`
    - `npm run build`
    - `npm run test`
  - On success: finalize delivery with commit/push/PR and post summary
  - Advance issue label

## Module Map

- `trigger_workflow/config.py`
  - Canonical phase/label maps
  - Successor mapping (`NEXT_LABEL_MAP`)
  - Repo checkout config (`TARGET_REPO_CONFIG_MAP`)

- `trigger_workflow/router.py`
  - Top-level orchestration + phase dispatch
  - Manual preview mode behavior
  - Needs-human tagging for pre-implementation failures

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

- `trigger_workflow/openhands_runner.py`
  - Managed checkout setup under `.openhands/repos`
  - Branch verification and phase branch resolution
  - OpenHands subprocess execution + event extraction
  - Validation retry loop for phases `6-9`
  - Delivery finalization (commit/push/PR summary)

- `trigger_workflow/logging_utils.py`
  - Structured console logging helpers

## Operational Constraints

- Managed checkout policy:
  - OpenHands must run in `.openhands/repos/<owner__repo>`
  - Refuses running in source checkout path

- Branch policy:
  - Phases before implementation run on configured main branch
  - Implementation phases run on `issue/<number>` branch
  - Missing implementation branch is a hard failure

- Stateless conversation policy:
  - Runs do not resume prior OpenHands conversations
  - Conversation IDs are not persisted for reuse

- Delivery policy:
  - Refuses phase advancement without git changes
  - Refuses fallback commit/PR titles when issue title is missing
  - Push mismatch/rejection is hard-fail and requires human intervention

## Tests Coverage

- Router behavior: `tests/trigger_workflow/test_router.py`
- GitHub operations: `tests/trigger_workflow/test_github_ops.py`
- Prompt contracts: `tests/trigger_workflow/test_prompts.py`
- Runner/process/branch policies: `tests/trigger_workflow/test_openhands_runner.py`
- Tiferet validation rules: `tests/trigger_workflow/test_validation.py`

## MCP Integration Seam (for future work)

Best attachment point is to expose MCP tools that call:
- `run_labeled_issue_phase_with_mode(...)` for end-to-end phase execution/preview
- selected read/write functions in `github_ops.py` for fine-grained issue operations

This keeps current router logic as the source of truth and avoids duplicated orchestration logic.
