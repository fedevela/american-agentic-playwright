# particle-life-3d Target Playbook

## Purpose

This document defines how the local swarm should work GitHub issues against the `particle-life-3d` repository when OpenClaw acts as the listener.

## Roles

- `OpenClaw`: listens for GitHub issue activity, loads issue context, invokes the swarm locally, and writes results back to GitHub.
- `openhands-swarm`: provides the phase model, personas, and output contracts.
- `particle-life-3d`: the codebase where analysis, implementation, and verification happen.

## Repositories

- Swarm repo: `/Users/macbook/Documents/gitworkspace/openhands-swarm`
- Target repo: `/Users/macbook/Documents/gitworkspace/particle-life-3d`

## Operating Model

1. OpenClaw receives an issue or explicit command tied to `particle-life-3d`.
2. Phase 1 ingests the raw issue text and produces a clarified requirement.
3. Phases 2-7 turn that requirement into constraints, mechanism options, acceptance criteria, technical mapping, pseudocode, and an implementation plan.
4. Phase 8 performs the code changes in `particle-life-3d`.
5. Phase 9 validates the result against the acceptance contract and reports pass/fail status back through OpenClaw.

## Branch Policy

- Phases 1-4 run against the target repository on `main`.
- Phases 5-9 run against an issue-specific branch named `issue/<issue-number>`.
- If the issue branch does not already exist locally, it is created from `main` before OpenHands starts.
- OpenHands should be launched from the target repository checkout, not from the swarm repository.

## Required Repository Context

Before implementation, the swarm should read these files in `particle-life-3d`:

- `README.md`
- `ARCHITECTURE.md`
- `package.json`
- relevant `tests/*.spec.ts`
- any file directly referenced by the issue

## Repository Facts

- Stack: React 19, React Router v7, TypeScript, Vite, React Three Fiber, Drei, Zustand.
- Persistence: SQLite WASM in a Web Worker with OPFS-backed storage.
- Main route entry: `app/routes.ts`
- Main 3D feature area: `app/features/3d/`
- Persistence layer: `app/db/client-bridge/` and `app/db/worker/`
- Existing validation style: contract specs and Playwright UI tests under `tests/`

## Definition of Done

For a `particle-life-3d` issue, work is not done until all applicable items hold:

- acceptance criteria are explicit
- code changes are made in the target repository, not the swarm repo
- affected tests are updated or added
- `npm run typecheck` passes
- relevant test commands pass
- OpenClaw has enough structured output to update the GitHub issue or PR

## Preferred Validation Commands

Run from `/Users/macbook/Documents/gitworkspace/particle-life-3d`:

```bash
npm run typecheck
npm run build
```

When the issue affects behavior already covered by tests, also run the relevant specs, for example:

```bash
npx playwright test
```

Use narrower test selection when possible to keep issue turnaround fast.

## Output Contract Back to OpenClaw

Each completed issue should produce, at minimum:

- clarified requirement
- acceptance criteria
- implementation summary
- validation summary
- explicit pass/fail judgment
- unresolved risks or follow-up issues

## Constraints

- Do not duplicate `particle-life-3d` domain documentation inside persona files unless the persona genuinely needs permanent product-specific behavior.
- Keep GitHub transport logic in OpenClaw, not in this repo.
- Keep repository-specific workflow notes here under `targets/` so new target repos can be added without rewriting the swarm model.
