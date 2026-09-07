# Agent Notes: OpenHands Swarm

This document captures the practical architecture and execution rules for working safely in this repository.

## Creative-writing mode

The older module map below describes the SDLC engine. `trigger.py --mode creative-writer`
selects `trigger_workflow_creative_writer`, whose sole enabled provider is Codex CLI.
Gemini/OpenHands workflow/session integration is unimplemented and disabled there;
SDLC providers/defaults are unchanged.

- Phases 7/8 prepare dramatic action and preserve performance materials; phase 9 is
  the director's roundtable, not validation-only. Phase 10 remains separate revision.
- `codex_runner.py` owns native CLI calls; ordinary phases always start fresh.
- `scene_materials.py` validates the phase-7 brief and version-2 phase-8 context index.
- One episode `script.md` contains every scene and beat; scene-scoped preparation
  lives in `scene_materials/<scene_id>/`. `manuscript.py` locates bounded regions
  and `play_format.py` renders public Markdown without private actor fields.
- `roundtable.py` owns separate persistent director/character sessions for a specific
  scene/run, observation routing, checkpoints, completion and guarded delivery.
- Director receives all fictional inner monologues; actors receive only own context
  and eligible observations. Normal repository access remains; no filesystem secrecy claim.
- Use `--performance-run UUID` for explicit recovery, `--new-performance` for a deliberate
  restart, and `--scene` to disambiguate scene directories. Ambiguous interrupted turns
  or delivery require reconciliation, never blind replay.
- Phases 7–9 use writing-specific gates, not npm. Other creative phases retain their gates.
- Upstream exploration uses versioned cycle results and structured readiness; see
  [recursive dramatic development](docs/creative-writing-exploration.md).
- Season scope is human-created only. Generated artifacts use episode/act/scene;
  every issue branch ends in ready scene leaves. Python maintains ownership,
  parent-blocked-by-child dependencies, and completion rollup.
- Legacy prose must restart through Keter; `--new-cycle --phase 1` preserves history.
- See [creative-writing contracts and operation](docs/creative-writing-roundtable.md).

## Entry Point

- `trigger.py` is a thin CLI shim that calls `trigger_workflow.router.run_trigger_cli()`.

## Runtime Flow

`run_trigger_cli()` parses:
- `--label`: GitHub label triggering the phase.
- `--phase`: Canonical phase ID (alternative to --label).
- `--issue`: Issue number to process.
- `--repo`: Target repository (owner/repo).
- `--runner`: Agent engine to use (`gemini` or `openhands`).
- `--working-dir`: Local directory to use as the target repository (bypasses managed checkout).
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
  - Creates child issue branches
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

- `trigger_workflow/gemini_runner.py`
  - Gemini CLI subprocess execution.
  - Optimized for fast, single-turn or fixed-retry cycles.

- `trigger_workflow/openhands_runner.py`
  - OpenHands subprocess execution + event extraction.
  - Supports complex, multi-turn coding and debugging.

- `trigger_workflow/runner_utils.py`
  - Managed checkout setup under `.openhands/repos`
  - Branch verification and phase branch resolution
  - Validation retry loop for implementation phases
  - Delivery finalization (commit/push/PR summary)

- `trigger_workflow/logging_utils.py`
  - Structured console logging helpers

## Operational Constraints

- Managed checkout policy:
  - Agent must run in `.openhands/repos/<owner__repo>` unless `--working-dir` is provided.
  - Refuses running in source checkout path to prevent local pollution.

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
- Runner/process/branch policies: `tests/trigger_workflow/test_openhands_runner.py`
- Tiferet validation rules: `tests/trigger_workflow/test_validation.py`

## MCP Integration Seam (for future work)

Best attachment point is to expose MCP tools that call:
- `run_labeled_issue_phase_with_mode(...)` for end-to-end phase execution/preview
- selected read/write functions in `github_ops.py` for fine-grained issue operations

This keeps current router logic as the source of truth and avoids duplicated orchestration logic.
