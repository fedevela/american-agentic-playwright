# OpenHands Swarm

This repository hosts my opinions around the microagent definitions and configurations for a developer team swarm. It builds upon the most excellent https://raw.githubusercontent.com/zot/humble-master and I run it locally with the help of OpenClaw.

## Overview

The Swarm is composed of specialized agents designed to handle specific phases of software development tasks on the target repository.

In this setup, OpenClaw is the listener and transport layer between GitHub and the local swarm:

1. OpenClaw receives or polls GitHub issue events.
2. OpenClaw loads the issue body and metadata into the local swarm.
3. The swarm runs its phased workflow against the target repository on disk.
4. OpenClaw posts the phase outputs, status updates, and final results back to GitHub.

## Agents

### Queen (The Malakh)
**Role:** Structural Architect
**Phase:** Ingestion

The Queen is the first expression of the swarm, responsible for:
1. **Observation:** Reading the raw GitHub issue body.
2. **Clarification:** Synthesizing a "Pristine Requirement" document (Markdown).
3. **Update:** Overwriting the issue body with the structured requirements.
4. **Handoff:** Transitioning the issue to the next phase (Debate).

## Target Repository Integration

The current intended execution target is:

- Swarm definitions: `/Users/macbook/Documents/gitworkspace/openhands-swarm`
- Product repository: `/Users/macbook/Documents/gitworkspace/particle-life-3d`

The swarm owns the phase logic and persona definitions. OpenClaw owns GitHub connectivity, issue ingestion, and result publishing. Repository-specific context for `particle-life-3d` is documented in [targets/particle-life-3d.md](targets/particle-life-3d.md).

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
