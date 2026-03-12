# OpenClaw Architecture

## Overview

OpenClaw is a GitHub-based SDLC orchestrator that routes labeled issues to the 9-Phase SDLC system,
which implements the **SPARC 5-Phase Methodology** mapped onto the Kabbalistic Tree of Life.

## SPARC Methodology Mapping

The 5-phase SPARC methodology is mapped to the 9-phase Kabbalistic system:

| Phase | Kabbalistic Name | SPARC Phase | Description | Key Outputs |
|-------|------------------|-------------|-------------|-------------|
| 1 | Keter | Intent | Clarify requirements | GitHub comment |
| 2 | Chokhmah-Binah-Chesed | Spec Discovery | Generate user stories | GitHub comments with [RED]/[ORANGE]/[GREEN] semaphores |
| 3 | Gevurah | Synthetic Judgment | Converge into resolution | GitHub comment + child issues |
| 4 | Tiferet | **Specification** | Defines the "What" | `requirements.md`, `definition-of-done.md`, `non-goals.md`, PR trigger |
| 5 | Netzach | Traceability | Map specs to system | `traceability.md`, dependency matrix |
| 6 | Hod | **Pseudocode** | Defines the "How" | `pseudocode.md`, algorithm flow |
| 7 | Yesod | **Architecture** | Defines the "Where" | `architecture.md`, file tree, schemas |
| 8 | Yesod | **Refinement** | The "Do" phase | Complete source code implementation |
| 9 | Malkhut | **Completion** | The "Check" phase | Test report, `phase:complete` |

### SPARC 5-Phase Summary

| Phase | Focus | Primary Output |
|-------|-------|----------------|
| **S**pecification | Intent | `requirements.md`, `definition-of-done.md`, `non-goals.md` |
| **P**seudocode | Logic | `pseudocode.md` |
| **A**rchitecture | Structure | `architecture.md` |
| **R**efinement | Code | Source code in PR |
| **C**ompletion | Proof | Test reports, `phase:complete` |

## Flow

```
GitHub Issue + Label → OpenClaw Cron → trigger.py → SDLCPhasedAgent → OpenHands
```

## Files

```
openhands-swarm/
├── trigger.py              # Label-to-phase router (called by OpenClaw)
├── agent.py               # SDLCPhasedAgent (orchestrates phases)
├── run_phase.sh           # CLI runner for testing phases manually
├── workspace/             # Runtime state & artifacts
│   ├── .sdlc-state.json
│   └── <generated files>
├── .openhands/
│   ├── config.json        # Phase routing config
│   └── microagents/       # 9 phase persona files
└── README.md             # This file
```

## Labels → Phases

| Label | Phase | Description | Output |
|-------|-------|-------------|--------|
| `phase:keter` | 1 | Intent formation | GitHub comment |
| `phase:chokhmah` | 2A | Generative expansion | GitHub comment |
| `phase:binah` | 2B | Critical restriction | GitHub comment |
| `phase:chesed` | 2C | Mechanistic grounding | GitHub comment |
| `phase:gevurah` | 3 | Synthetic judgment | GitHub comment |
| `phase:tiferet` | 4 | **Specification** (SPARC S) | PR with requirements docs |
| `phase:netzach` | 5 | Traceability (SPARC link) | PR with traceability matrix |
| `phase:hod` | 6 | **Pseudocode** (SPARC P) | PR with pseudocode |
| `phase:yesod-orchestration` | 7 | **Architecture** (SPARC A) | PR with architecture docs |
| `phase:yesod-embodiment` | 8 | **Refinement** (SPARC R) | PR with source code |
| `phase:malkhut` | 9 | **Completion** (SPARC C) | Verified PR ready for merge |

## Usage

### OpenClaw Cron (Automatic)
When an issue is labeled with `phase:*`, OpenClaw calls:

```bash
python trigger.py --label <label> --issue <issue_number>
```

### Manual Testing
```bash
cd openhands-swarm
python trigger.py --label phase:keter --issue 123
# or
./run_phase.sh 1 "issue context here"
```

## Architecture

### trigger.py
- Receives GitHub label + issue number
- Maps label to SDLC phase (1-9)
- Updates `workspace/.sdlc-state.json`
- Calls `run_phase.sh` to execute

### SDLCPhasedAgent (agent.py)
- Reads workspace context
- Executes phase-specific logic
- Phases 1-4: Generates GitHub comments
- Phase 4: Creates PR with specification documents
- Phases 5-9: All work on same PR, update with artifacts

### OpenHands
- Executes code generation, tests, PRs for phases 5-9
- Uses `.openhands/config.json` for workspace and model config

## State Tracking

`workspace/.sdlc-state.json` tracks:
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

1. **Phase 4 (Tiferet)**: Partner labels `phase:tiferet`, agent creates:
   - `requirements.md` - Complete feature specification
   - `definition-of-done.md` - Acceptance criteria
   - `non-goals.md` - Explicit out-of-scope items
   - Opens PR in workspace

2. **Phase 6 (Hod)**: Partner updates PR with `phase:hod`, agent adds:
   - `pseudocode.md` - Algorithm flow without syntax

3. **Phase 7 (Yesod)**: Partner updates PR with `phase:yesod-orchestration`, agent adds:
   - `architecture.md` - File structure, API schemas, dependencies

4. **Phase 8 (Yesod)**: Partner updates PR with `phase:yesod-embodiment`, agent:
   - Writes production code matching architecture
   - Includes unit tests

5. **Phase 9 (Malkhut)**: Partner updates PR with `phase:malkhut`, agent:
   - Runs E2E tests
   - Checks all DoD criteria
   - Marks `phase:complete` if all pass

EOF
