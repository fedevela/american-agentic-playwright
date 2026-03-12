# OpenClaw SDLC Workflow

OpenClaw is the GitHub cron that monitors issues and triggers the 9-Phase SDLC decoder system.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        OpenClaw Cron (GitHub Actions)                    │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  Listens for: issues.labeled                                      │  │
│  │  Filters: label starts with "phase:"                              │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                    │                                     │
│                                    ▼                                     │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  trigger.py                                                        │  │
│  │  - Maps label to SDLC phase (1-9)                                 │  │
│  │  - Updates workspace/.sdlc-state.json                             │  │
│  │  - Calls agent.py with phase context                              │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                    │                                     │
│                                    ▼                                     │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  agent.py (SDLCPhasedAgent)                                       │  │
│  │  - Reads workspace context                                        │  │
│  │  - Executes phase-specific logic                                  │  │
│  │  - Phases 1-4: GitHub comment                                     │  │
│  │  - Phases 5-9: OpenHands workflow                                 │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                    │                                     │
│                                    ▼                                     │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  OpenHands (phases 5-9 only)                                      │  │
│  │  - Generates code                                                 │  │
│  │  - Runs tests                                                     │  │
│  │  - Creates PRs                                                    │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

## Trigger File: trigger.py

**Location:** `openhands-swarm/trigger.py`

**Called by:** OpenClaw cron when issue is labeled

**Signature:**
```bash
python trigger.py --label <label> --issue <issue_number>
```

**Labels:**
- `phase:keter` → Phase 1
- `phase:chokhmah` → Phase 2A
- `phase:binah` → Phase 2B
- `phase:chesed` → Phase 2C
- `phase:gevurah` → Phase 3
- `phase:tiferet` → Phase 4
- `phase:netzach` → Phase 5
- `phase:hod` → Phase 6
- `phase:yesod-orchestration` → Phase 7
- `phase:yesod-embodiment` → Phase 8
- `phase:malkhut` → Phase 9

## Phase Files

**Location:** `openhands-swarm/.openhands/microagents/phase_XX_*.md`

11 phase files with persona definitions:
- `phase_01.1_keter.md`
- `phase_02.1_chokhmah.md`
- `phase_02.2_binah.md`
- `phase_02.3_chesed.md`
- `phase_03_gevurah.md`
- `phase_04_tiferet.md`
- `phase_05_netzach.md`
- `phase_06_hod.md`
- `phase_07_yesod.md`
- `phase_08_yesod.md`
- `phase_09_malkhut.md`

## Workflow Labels

| Phase | Label | Type | Action |
|-------|-------|------|--------|
| 1 | `phase:keter` | Discussion | GitHub comment |
| 2 | `phase:chokhmah` | Discussion | GitHub comment |
| 2 | `phase:binah` | Discussion | GitHub comment |
| 2 | `phase:chesed` | Discussion | GitHub comment |
| 3 | `phase:gevurah` | Discussion | GitHub comment |
| 4 | `phase:tiferet` | Discussion | GitHub comment |
| 5 | `phase:netzach` | Workflow | OpenHands |
| 6 | `phase:hod` | Workflow | OpenHands |
| 7 | `phase:yesod-orchestration` | Workflow | OpenHands |
| 8 | `phase:yesod-embodiment` | Workflow | OpenHands (PR) |
| 9 | `phase:malkhut` | Workflow | OpenHands |

## OpenHands Integration

For phases 5-9, OpenHands:
1. Reads workspace content from `workspace/`
2. Executes phase-specific microagents
3. Generates code/tests/PRs
4. Updates workspace state

## Repository Structure

```
openhands-swarm/
├── trigger.py            # OpenClaw entry point
├── agent.py              # SDLCPhasedAgent
├── run_phase.sh          # Manual phase runner
├── ARCHITECTURE.md       # System architecture
├── SETUP.md             # Setup guide
├── workspace/            # Runtime state
│   └── .sdlc-state.json
└── .openhands/
    ├── config.json       # OpenHands config
    └── microagents/      # Phase persona files
```

## OpenClaw Configuration Example

```yaml
- name: SDLC Phase Router
  repo: your-org/openhands-swarm
  cron: "*/5 * * * *"
  commands:
    - name: sdnc-trigger
      trigger: "When label starts with phase:"
      command: |
        python trigger.py --label ${label} --issue ${issue}
```