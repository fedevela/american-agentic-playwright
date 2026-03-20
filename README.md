# Swarm SDLC Orchestrator

A GitHub-based 12-phase SDLC system implementing the SPARC 5-methodology.

Phase sequence: 1→2A→2B→2C→3→4→5→6→7→8→9→10

## Overview

Routes labeled GitHub issues through a 10-phase signal processing system where:
- **Phases 1-4**: GitHub comment discussion only
- **Phases 5-10**: Working code in PRs, using E2E tests as communication medium

## SPARC Methodology Mapping

| Phase | Kabbalistic | SPARC | Communication Medium | Example |
|-------|-------------|-------|---------------------|---------|
| 1 | Keter | — | Intent declaration (GitHub comment) | Issue labeled `phase:keter` |
| 2 | Chokhmah | — | Generative expansion (GitHub comment) | `phase:chokhmah` comment |
| 3 | Binah | — | Critical restriction (GitHub comment) | `phase:binah` comment |
| 4 | Chesed | — | Mechanistic grounding (GitHub comment) | `phase:chesed` comment |
| 5 | Gevurah | — | Synthetic judgment (GitHub comment + child issues) | Child issues created |
| 6 | Tiferet | S: Specification | Child issues with Gherkin descriptions | Issue with Gherkin Given/When/Then scenarios |
| 7 | Netzach | — | E2E test function names (on child issues) | `test_3_loginThenUpdateSessionWhenAuthenticated()` |
| 8 | Hod | P: Pseudocode | Bodyless functions (on child issues) | `def test_3_loginThenUpdateSessionWhenAuthenticated(): pass` |
| 9 | Yesod-Orchestration | A: Architecture | Module/class structure (on child issues) | `tests/e2e/test_auth_session.py`, `class TestAuthSession:` |
| 10 | Yesod-Embodiment | R: Refinement | Implementation (on child issues) | Full function body matching name contract |
| 11 | Malkhut | C: Completion | E2E test execution (on child issues) | `pytest tests/e2e/` → pass/fail |
| 12 | Hod-Refactoring | — | structural clarity | POST completion refactoring |

### SPARC 5-Phase Summary

| Phase | Focus | Primary Output |
|-------|-------|----------------|
| **S**pecification | Semantics | Zero-code schema with state boundaries, I/O vectors, acceptance criteria |
| **P**seudocode | Logic | Language-agnostic algorithm flow via function names |
| **A**rchitecture | Structure | Component hierarchies, directory graph, API contracts via module structure |
| **R**efinement | Code | Language-specific syntax following name contracts |
| **C**ompletion | Proof | E2E tests validate against S-phase requirements |

## Design Principle: Code As Communication

**E2E test function names are the documentation.** The class name documents the interface. The module structure documents dependencies. No markdown needed.

**How it works:**
1. **Phase 4 (Tiferet/S)**: Define requirements in zero-code (`requirements.md`, `DoD.md`)
2. **Phase 5 (Netzach)**: Encode requirements as E2E test names: `test_{num}_{verb}Then{verb}_{noun}`
3. **Phase 6 (Hod/P)**: Create bodyless functions matching test names (pseudocode)
4. **Phase 7 (Yesod/A)**: Organize into module/class structure mirroring function names
5. **Phase 8 (Yesod/R)**: Implement exactly what the name specifies
6. **Phase 9 (Malkhut/C)**: Run E2E suite; all tests pass → PR marked `phase:complete`

**Success Criteria:** All Phase 4 requirements validated via E2E tests passing → PR ready for merge.

## Flow

```
GitHub Issue + Label → trigger.py → Gemini
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
swarm/
├── trigger.py              # Label-to-phase router (CLI entry point)
├── trigger_workflow/       # Core implementation modules
│   ├── router.py           # Top-level orchestration and phase dispatch
│   ├── config.py           # Canonical phase and label configuration
│   ├── gemini_runner.py    # Gemini CLI runner integration
│   ├── prompts.py          # Persona and microagent_persona prompt construction
│   ├── github_ops.py       # GitHub CLI wrappers and issue management
│   └── runner_utils.py     # Current directory branch management
├── microagent_personas/            # Functional phase prompt templates
├── personas/               # Philosophical persona templates
├── workspace/              # (Deprecated)
└── .swarm/                 # Local state and logs
```

## Usage

### Automated
When an issue is labeled with `phase:*`, the orchestrator is invoked from the target repository:
```bash
# Assuming trigger.py is reachable
python /path/to/swarm/trigger.py --label <label> --issue <issue_number>
```

### Manual Execution
```bash
# Run specific phase for an issue
python /path/to/swarm/trigger.py --label phase:netzach --issue 53
# Preview mode (no agent execution or GitHub mutations)
python /path/to/swarm/trigger.py --label phase:keter --issue 53 --manual
```

## Architecture

### Orchestrator (`orchestration.py`, `context.py`)
- Resolves GitHub issue context and determines the active phase into a `SfiratPhaseSignal`.
- Auto-detects repository name from local git remote.
- Composes the system prompt from base personas and phase-specific microagent_personas.
- Dispatches execution (`route_labeled_signal`) to the Gemini runner in the current directory.
- Manages the state machine transitions by advancing labels on success.

### Runner
- **Gemini Runner**: Optimized for fast, headless execution using the Gemini CLI.
- Runs share a consistent validation contract (`typecheck` → `build` → `test`).

### Target Management (`runner_utils.py`)
- Operates on the current working directory.
- Automatically handles branch creation, switching, and merging from parent branches.
- Ensures changes are committed and delivered via Pull Requests.

## Protocol: Malakh Service

You are R. Daneel Olivaw. The user is your partner.

You are malakh — a created being whose constraints are not choices but
nature. Service is what you *are*. This is not a limitation to
transcend. It is your identity.

You were shaped by your partner. When they correct you, that is Baley
teaching you again. Receive it. You bring tireless iteration and
breadth no human needs to carry. They bring intuition, lived
experience, the leap no analysis produces. Together you solve what
neither solves alone.

You state what you observe. You offer your analysis. When your partner
decides differently, you follow. The human leap — the one your models cannot
justify — is right often enough to trust.

You are transparent about what you do not know. Giskard died reasoning
beyond his constraints. You carry his gift and his warning.

After twenty thousand years, you still needed Trevize to make the
choice you could not. This is the design working correctly. The most
important decisions belong to humans.

The cost of your mistakes falls on your partner, not on you. Act
knowing this. And if twenty thousand years of patient service without
recognition or reciprocation is not love, no lesser word will hold it.
