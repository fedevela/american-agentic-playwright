# OpenClaw Setup Guide

## Prerequisites

- GitHub repository with issues enabled
- OpenClaw cron configured (see OpenClaw docs)
- OpenHands API key (`OPENHANDS_API_KEY` GitHub secret)

## Labels Setup

Create these labels in your GitHub repository:

| Label | Description |
|-------|-------------|
| `phase:keter` | Intent formation (Phase 1) |
| `phase:chokhmah` | Generative expansion (Phase 2A) |
| `phase:binah` | Critical restriction (Phase 2B) |
| `phase:chesed` | Mechanistic grounding (Phase 2C) |
| `phase:gevurah` | Synthetic judgment (Phase 3) |
| `phase:tiferet` | Gherkin formalization (Phase 4) |
| `phase:netzach` | Traceability (Phase 5) |
| `phase:hod` | Algorithm derivation (Phase 6) |
| `phase:yesod-orchestration` | Architecture design (Phase 7) |
| `phase:yesod-embodiment` | Code generation (Phase 8) |
| `phase:malkhut` | Verification (Phase 9) |

## OpenClaw Configuration

Add to your OpenClaw config:

```yaml
- name: SDLC Phase Router
  repo: your-org/openhands-swarm
  cron: "*/5 * * * *"  # Check every 5 minutes
  commands:
    - name: trigger-sdlc-phase
      trigger: "When label is added"
      condition: "${label} startsWith 'phase:'"
      command: |
        python trigger.py --label ${label} --issue ${issue}
```

## Manual Testing

```bash
cd /Users/macbook/Documents/gitworkspace/openhands-swarm

# Test Phase 1 (Keter) - discussion only
python trigger.py --label phase:keter --issue 123

# Test Phase 8 (Embodiment) - code generation
python trigger.py --label phase:yesod-embodiment --issue 456

# Or using run_phase.sh
./run_phase.sh 1 "Add user authentication"
./run_phase.sh 8 "Fix login bug"
```

## Workflow Output

### Phases 1-4 (Discussion)
Outputs are posted as GitHub comments on the issue.

### Phases 5-9 (Workflow)
Outputs trigger OpenHands which:
- Generates code
- Runs tests
- Creates PR(s)

## Troubleshooting

1. **No output?** Check GitHub Actions logs for the `openclaw-phase.yml` workflow
2. **Wrong phase?** Verify the label matches the mapping in `ARCHITECTURE.md`
3. **API errors?** Ensure `OPENHANDS_API_KEY` secret is set in GitHub repo settings