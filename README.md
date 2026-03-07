# OpenHands Swarm

This repository hosts my opinions around the microagent definitions and configurations for a developer team swarm. It builds upon the most excellent https://raw.githubusercontent.com/zot/humble-master and I run it locally with the help of OpenClaw.

## Overview

The Swarm is composed of specialized agents designed to handle specific phases of software development tasks.

## Agents

### Queen (The Malakh)
**Role:** Structural Architect
**Phase:** Ingestion

The Queen is the first expression of the swarm, responsible for:
1. **Observation:** Reading the raw GitHub issue body.
2. **Clarification:** Synthesizing a "Pristine Requirement" document (Markdown).
3. **Update:** Overwriting the issue body with the structured requirements.
4. **Handoff:** Transitioning the issue to the next phase (Debate).

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
