# OpenHands Swarm

This repository hosts the microagent definitions and configurations for the OpenHands Swarm architecture. It defines the roles and behaviors of agents operating within the OpenHands environment.

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