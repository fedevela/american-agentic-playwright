# Label -> Phase Routing Guide

## Overview
When OpenClaw detects an issue with a specific label, it calls `trigger.py` which:
1. Maps the label to a phase number
2. Updates state in `.sdlc-state.json`
3. Executes `run_phase.sh` to run that phase
4. **Phases 1-4** only generate GitHub comments (no code)
5. **Phases 5-9** trigger OpenHands workflows (code, PRs, commits)

## Usage from OpenClaw

```bash
python trigger.py --label <label> --issue <issue_number>
```

### Examples

```bash
# Feature request - Discussion phase (comments only)
python trigger.py --label feature --issue 123

# Bug - Validation phase (triggers OpenHands workflow)
python trigger.py --label bug --issue 456

# Implementation - Code generation phase
python trigger.py --label implement --issue 789
```

## Supported Labels

### Discussion Phases (Phases 1-4) - GitHub Comments Only
| Label | Phase | Description |
|-------|-------|-------------|
| `feature` | 1 | Intent formation - discuss requirements in GitHub comments |
| `enhancement` | 2 | Spec discovery triad - discuss in GitHub comments |
| `documentation` | 1 | New docs need intent - discuss in GitHub comments |
| `experimental` | 2 | New features need spec - discuss in GitHub comments |

### OpenHands Workflow Phases (Phases 5-9) - PR/Code Generation
| Label | Phase | Description |
|-------|-------|-------------|
| `trace` | 5 | Spec-to-system mapping - triggers OpenHands workflow |
| `algorithm` | 6 | Derive logic - triggers OpenHands workflow |
| `codegen` | 7 | Architecture design - triggers OpenHands workflow |
| `implement` | 8 | Execute implementation - triggers PR with code/tests |
| `bug` | 9 | Final validation - triggers OpenHands workflow to verify/fix |
| `review` | 9 | Final validation - triggers OpenHands workflow |

## OpenClaw Configuration

OpenClaw should trigger for issues with these labels:

```
labels:
  - feature
  - enhancement
  - documentation
  - experimental
  - trace
  - algorithm
  - codegen
  - implement
  - bug
  - review
```

When any label is added, call:
```
python trigger.py --label <label> --issue <issue_number>
```

The output goes to GitHub comments or PRs depending on the phase.