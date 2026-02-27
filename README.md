# OpenClaw SDLC Orchestrator

A GitHub-based 12-phase SDLC system implementing the SPARC 5-methodology mapped onto the Kabbalistic Tree of Life.

- Phase/state machine policy
- Transition guards
- `lock`-based lease semantics
- In-memory issue orchestration service
- Executor with preflight artifact gating
- Orchestrator for staggered batch processing and duplicate-grab prevention
- Workflow engine implementing the full 9-phase behavior contract
- CLI for validation and transition simulation
- Unit tests for invariants and transitions

## Overview

```text
src/openhands_swarm/
  __init__.py
  cli.py
  config.py
  domain.py
  executor.py
  orchestrator.py
  policy.py
  prompts.py
  queue.py
  service.py
  workflows.py
tests/
  test_executor.py
  test_orchestrator.py
  test_policy.py
  test_service.py
  test_workflows.py
state-machine-policy-and-workflow-descriptions.md
```

## Label → Phase Mapping

| Label | Phase | Description |
|-------|-------|-------------|
| `phase:keter` | 1 | Intent formation (GitHub comment) |
| `phase:chokhmah` | 2A | Generative expansion (GitHub comment) |
| `phase:binah` | 2B | Critical restriction (GitHub comment) |
| `phase:chesed` | 2C | Mechanistic grounding (GitHub comment) |
| `phase:gevurah` | 3 | Synthetic judgment (GitHub comment + child issues) |
| `phase:tiferet` | 4 | SPARC S: Specification (creates child issues with Gherkin, no PR) |
| `phase:netzach` | 5 | Traceability (child issues, E2E test names) |
| `phase:hod` | 6 | SPARC P: pseudocode (child issues, bodyless functions) |
| `phase:yesod-orchestration` | 7 | SPARC A: Architecture (child issues, module structure) |
| `phase:yesod-embodiment` | 8 | SPARC R: Refinement (child issues, implementation) |
| `phase:malkhut` | 9 | SPARC C: Completion (child issues, validation) |
| `phase:hod-refactoring` | 10 | Structural Clarity (post-completion refinement) |

## Files

```
openhands-swarm/
├── trigger.py              # Label-to-phase router (CLI entry point)
├── trigger_workflow/       # Core implementation modules
│   ├── router.py           # Top-level orchestration and phase dispatch
│   ├── config.py           # Canonical phase and label configuration
│   ├── gemini_runner.py    # Gemini CLI runner integration
│   ├── openhands_runner.py # OpenHands runner integration
│   ├── prompts.py          # Persona and microagent prompt construction
│   ├── github_ops.py       # GitHub CLI wrappers and issue management
│   └── runner_utils.py     # Shared checkout and branch management
├── microagents/            # Functional phase prompt templates
├── personas/               # Philosophical persona templates
├── workspace/              # Persistent session and artifact state
└── .openhands/             # Managed checkouts and conversation logs
```

## Usage

### Automated (OpenClaw Cron)
When an issue is labeled with `phase:*`, the orchestrator is invoked:
```bash
python trigger.py --label <label> --issue <issue_number>
```

### Manual Execution
```bash
cd openhands-swarm
# Run specific phase for an issue
python trigger.py --label phase:netzach --issue 53
# Select a specific runner (default: gemini)
python trigger.py --runner openhands --phase 5 --issue 53
# Use current directory as workspace (bypass managed checkout)
python trigger.py --working-dir . --issue 53
# Preview mode (no agent execution or GitHub mutations)
python trigger.py --label phase:keter --issue 53 --manual
```

## Architecture

### Router (`router.py`)
- Resolves GitHub issue context and determines the active phase.
- Composes the system prompt from base personas and phase-specific microagents.
- Dispatches execution to the appropriate runner (Gemini or OpenHands).
- Manages the state machine transitions by advancing labels on success.

### Runners
- **Gemini Runner**: Optimized for fast, headless execution using the Gemini CLI.
- **OpenHands Runner**: Supports complex, multi-turn coding tasks with interactive feedback.
- Both runners share a consistent validation contract (`typecheck` → `build` → `test`).

### Target Management (`runner_utils.py`)
- Maintains isolated, managed clones of target repositories under `.openhands/repos/`.
- Automatically handles branch creation, switching, and merging from parent branches.
- Ensures changes are committed and delivered via Pull Requests.

## State Tracking

`workspace/.sdlc-state.json`:
```json
{
  "current_phase": 1,
  "current_step": 0,
  "last_issue": 123,
  "artifacts": {},
  "pr_url": null
}
```

## SPARC Flow Example

For a new feature request:

Refine with failing-but-fixable checks (remain in `sparc:refine`):

```bash
openhands-swarm transition \
  --phase sparc:refine \
  --tests-green false \
  --conformance-aligned false \
  --fixable-in-refine true
```

Acquire and release lock in simulation:

```bash
openhands-swarm lock --owner run-123
openhands-swarm unlock --owner run-123
```

## GitHub phase automation

- Every workflow phase regenerates its LLM prompt at runtime via `.github/scripts/phase_runner.py prompt --phase <phase>`.
- Prompt text is built in `src/openhands_swarm/prompts.py` and includes:
  - current issue context
  - required predecessor artifacts
  - explicit output contract + canonical artifact marker requirement (`<!-- openhands-swarm:artifact:<name> -->`)
- Workflows call the OpenHands GitHub action with the generated prompt, then finalize with `.github/scripts/phase_runner.py finalize --phase <phase>` to persist the returned artifact and perform transitions.
- If OpenHands output is unavailable (for local runs/tests), finalize uses deterministic fallback artifact content so phase logic remains testable.

### Workflow env/secrets

- Required: `GITHUB_TOKEN` (provided by GitHub Actions)
- Required for live LLM generation: `LLM_API_KEY` (used by the OpenHands action in workflows)
