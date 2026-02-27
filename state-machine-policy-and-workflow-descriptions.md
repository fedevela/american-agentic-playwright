# OpenHands Swarm — State Machine Policy + Workflow Descriptions (No YAML Code)

This document defines the canonical issue-state machine and the expected behavior of each workflow.

It includes two additional operational constraints requested for execution safety:

1. A **`lock` label** for single-issue leasing.
2. **Agent staggering / controlled fan-out** so multiple agents do not race on the same issue.

---

## 1) Labels

### 1.1 Phase labels (exactly one active at a time)

#### Epic loop
- `phase:queen`
- `phase:triad`
- `phase:arbiter`

#### Story loop
- `phase:contract`
- `sparc:spec`
- `sparc:pseudo`
- `sparc:arch`
- `sparc:refine`
- `sparc:done`
- `sparc:completed` (optional terminal)

### 1.2 Meta labels (can coexist with one phase label)
- `needs:human`
- `blocked`
- `restart:contract`
- `restart:spec`
- `restart:pseudo`
- `restart:arch`
- `lock`  ← **new** concurrency-control label

---

## 2) Core Invariants

1. **Single phase invariant**: each issue has exactly one active phase label.
2. **Human-stop invariant**: if `needs:human` exists, no automatic phase advancement.
3. **Lease invariant**: if an issue has `lock`, only the lock owner workflow run may mutate phase artifacts.
4. **Idempotency invariant**: re-running a workflow must update canonical outputs, not duplicate them.

If invariant #1 is violated (0 or >1 phase labels), workflow adds `needs:human` and exits.

---

## 3) Concurrency & Race Prevention Policy

### 3.1 Why `lock` exists

To prevent two agents from processing the same issue at the same time (double comments, duplicate transitions, conflicting label edits).

### 3.2 Lock acquisition protocol (conceptual)

For any phase workflow:

1. Triggered on target phase label.
2. Preflight checks pass.
3. Attempt to acquire lease by adding `lock` with ownership marker (run id / actor) in a canonical comment.
4. Re-read issue state:
   - If lock already owned by another active run → exit gracefully (no mutation).
   - If owned by current run → continue.
5. Perform phase actions.
6. Apply transition labels atomically where possible.
7. Remove `lock` on success/failure exit paths.

### 3.3 Stale lock policy

If a lock remains past TTL (e.g., canceled runner), mark `blocked` and request unlock by maintenance workflow or human intervention.

### 3.4 Agent staggering / controlled fan-out

To avoid thundering herd behavior:

- **Triad** may run 3 personas in parallel, but each persona has deterministic `max-parallel: 1` per epic.
- Cross-issue processing should use controlled concurrency (small queue/batch size) rather than global full fan-out.
- Optional startup jitter/backoff before lock attempt reduces simultaneous acquisitions.

---

## 4) Allowed Transitions

### 4.1 Epic
- `phase:queen -> phase:triad -> phase:arbiter -> epic:ready`

### 4.2 Story
- `phase:contract -> sparc:spec -> sparc:pseudo -> sparc:arch -> sparc:refine -> sparc:done -> sparc:completed`

### 4.3 Restart semantics
- `restart:*` indicates a backward jump request requiring contract/human resolution.
- After restart handling, one valid forward phase label is re-applied.

---

## 5) Workflow Descriptions (No YAML)

## 01 — `01-queen.yml`
**Trigger**: `phase:queen`

**Does**:
- Normalize epic body into: Goals, Non-Goals, Constraints, Assumptions, Open Questions, DoD.

**Entry criteria**:
- Epic has `phase:queen`
- Single phase label invariant holds
- Lock acquired

**Exit criteria**:
- Structured epic spec present.

**Transitions**:
- If Open Questions exist: remove `phase:queen`, add `needs:human`, release `lock`.
- Else: remove `phase:queen`, add `phase:triad`, release `lock`.

---

## 02 — `02-triad.yml`
**Trigger**: `phase:triad`

**Does**:
- Runs Advocate / Pragmatist / Skeptic persona analyses.
- Each posts candidate stories, risks, and priorities.

**Entry criteria**:
- Structured epic output from Queen exists
- Single phase label invariant
- Lock acquired

**Exit criteria**:
- 3 persona outputs present and parseable.

**Transitions**:
- On persona failure: add `blocked`, keep `phase:triad`, release `lock`.
- On success: remove `phase:triad`, add `phase:arbiter`, release `lock`.

**Concurrency note**:
- Personas are parallel **within** this epic, but staggered lock attempts and bounded matrix parallelism prevent race collisions.

---

## 03 — `03-arbiter.yml`
**Trigger**: `phase:arbiter`

**Does**:
- Synthesizes Queen + Triad output.
- Produces final prioritized story index.
- Spawns child story issues labeled `phase:contract`.

**Entry criteria**:
- Triad artifacts found
- Single phase label invariant
- Lock acquired

**Exit criteria**:
- Epic updated with story index and links
- Child issues created with correct initial labels and backlinks.

**Transitions**:
- Epic: remove `phase:arbiter`, add `epic:ready`, release `lock`.
- On failure: add `blocked`, keep `phase:arbiter`, release `lock`.

---

## 04 — `04-contract.yml`
**Trigger**: `phase:contract` (story)

**Does**:
- Appends strict BDD scenarios (Given/When/Then).
- Includes happy path + negative path + relevant edge cases.

**Entry criteria**:
- Story narrative + constraints present
- Single phase label invariant
- Lock acquired

**Exit criteria**:
- Objectively testable BDD and explicit story DoD.

**Transitions**:
- If ambiguity remains: add `needs:human`, keep `phase:contract`, release `lock`.
- Else: remove `phase:contract`, add `sparc:spec`, release `lock`.

---

## 05 — `05-sparc-spec.yml`
**Trigger**: `sparc:spec`

**Does**:
- Maps each BDD scenario to concrete responsibilities (UI/API/data), I/O, constraints.
- Flags contradictions/undefined terms.

**Entry criteria**:
- Contract exists
- No `needs:human`
- Single phase label invariant
- Lock acquired

**Exit criteria**:
- Full scenario-to-responsibility mapping with no unresolved undefined nouns.

**Transitions**:
- If contract flawed: remove `sparc:spec`, add `restart:contract` + `needs:human`, release `lock`.
- Else: remove `sparc:spec`, add `sparc:pseudo`, release `lock`.

---

## 06 — `06-sparc-pseudo.yml`
**Trigger**: `sparc:pseudo`

**Does**:
- Creates language-agnostic logic flows per scenario (validation, branching, state transitions, failure modes).

**Entry criteria**:
- Spec mapping exists
- Single phase label invariant
- Lock acquired

**Exit criteria**:
- Complete per-scenario flows including edge/failure handling.

**Transitions**:
- If mapping insufficient: remove `sparc:pseudo`, add `restart:spec`, release `lock`.
- Else: remove `sparc:pseudo`, add `sparc:arch`, release `lock`.

---

## 07 — `07-sparc-arch.yml`
**Trigger**: `sparc:arch`

**Does**:
- Produces repo-aware diff surface: files to touch/create, integration contracts, rollout/migration notes, observability hooks.

**Entry criteria**:
- Pseudocode artifacts exist
- Single phase label invariant
- Lock acquired

**Exit criteria**:
- Concrete, implementable change plan with dependencies explicit.

**Transitions**:
- If scope/contract must change: remove `sparc:arch`, add `restart:contract` + `needs:human`, release `lock`.
- Else: remove `sparc:arch`, add `sparc:refine`, release `lock`.

---

## 08 — `08-sparc-refine.yml` (Consolidated)
**Trigger**: `sparc:refine`

**Does**:
1. Implement architecture-defined changes.
2. Add/update unit tests.
3. Add/update Playwright E2E tests against BDD.
4. Run unit + E2E verification suite.
5. Perform dual conformance checks:
   - code vs BDD/testing spec
   - BDD/testing spec vs observed behavior
6. Post traceability report: Scenario -> Test(s) -> pass/fail evidence.

**Entry criteria**:
- Architecture plan exists
- No `needs:human`
- Single phase label invariant
- Lock acquired

**Exit criteria (hard gate)**:
- Test suite green with evidence
- Traceability matrix complete
- Conformance status = aligned

**Transitions**:
- Fixable failures without semantic contract changes: keep `sparc:refine`, rerun (retain/reacquire lock).
- Semantic contract change required: remove `sparc:refine`, add `restart:contract` + `needs:human`, release `lock`.
- All aligned: remove `sparc:refine`, add `sparc:done`, release `lock`.

---

## 09 — `09-completion.yml`
**Trigger**: `sparc:done`

**Does**:
- Final packaging: docs/changelog updates, PR creation/update, acceptance checklist and evidence in PR body, status comment on story.

**Entry criteria**:
- Phase 8 report exists and aligned
- No `needs:human` and no `blocked`
- Single phase label invariant
- Lock acquired

**Exit criteria**:
- PR exists and references story
- Required docs updates present
- Story ready for human review/merge.

**Transitions**:
- Remove `sparc:done`, add `sparc:completed`, release `lock`.

---

## 6) Shared Implementation Rules for All Workflows

1. **Preflight first**: validate phase label cardinality, lock ownership, predecessor artifacts.
2. **Atomic transition intent**: add next label and remove current label in one guarded operation sequence.
3. **Canonical artifacts**: every phase writes a stable marker block used by the next phase.
4. **Retry safety**: reruns must update existing markers/comments rather than append duplicates.
5. **Backpressure**: bounded concurrent runs and optional jitter/backoff before lock operations.
6. **Observability**: each run posts concise status (started, acquired lock, completed, blocked, human-needed).

---

## 7) Operational Notes

- `lock` is a coordination mechanism, not a business-state phase.
- If both `lock` and `needs:human` are present, automation should prioritize release of `lock` and halt.
- Maintenance workflow can safely clear stale `lock` labels after TTL and annotate reason.
