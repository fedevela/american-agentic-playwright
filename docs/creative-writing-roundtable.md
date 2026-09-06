# Creative-writing execution and sessions

Creative-writing mode uses **Codex CLI only**. Gemini and OpenHands are disabled;
their new workflow/session integrations are unimplemented. There is no fallback.
SDLC mode retains its existing providers and defaults.

Use the existing authenticated Codex installation (`CODEX_BIN` optionally selects
the executable). No credentials or native session files are copied into the story.
The adapter uses `codex exec --json` for a fresh session and `codex exec resume`
with the recorded UUID for later turns. Both accept structured-output schemas and
stdin prompts. Verified against local CLI 0.153.4 and
[official noninteractive documentation](https://learn.chatgpt.com/docs/non-interactive-mode).

Both initial and resumed calls explicitly use the normal `workspace-write` sandbox
so preparation phases can save artifacts. Existing approval settings still apply;
no sandbox-bypass flags or global configuration changes are used.

```bash
python trigger.py --mode creative-writer --phase 7 --repo owner/story --issue 42 --manual
python trigger.py --mode creative-writer --phase 8 --repo owner/story --issue 42
python trigger.py --mode creative-writer --phase 9 --repo owner/story --issue 42
python trigger.py --mode creative-writer --phase 9 --repo owner/story --issue 42 --performance-run RUN_UUID
```

Use `--scene SEASON_1/EPISODE_1/SHORT_1` when an issue has multiple scene handoffs.
`--new-performance` deliberately starts fresh sessions; it does not erase earlier
performances. `--performance-run` and `--new-performance` are mutually exclusive.
`--codex-model` overrides the configured model. Limits are `--max-role-calls 120`,
`--role-timeout 1200` seconds, and `--max-no-progress 6` director turns.
Manual/prompt-only requests do not invoke Codex or create performance state.

## Phase responsibilities

7 prepares **what a character can act upon in each dramatic moment**: stimulus,
knowledge, misunderstandings, ignorance, concealment, objective, emotion, stakes,
relationship pressures, available physical/conversational possibilities, and
dependencies. Canonical `[BEAT …]` identifiers remain traceability keys; they do
not prescribe discretionary responses. No final dialogue or changed act seams.

8 creates the scene hierarchy and its `AGENTS.md`, copies the brief, and saves the
phase-6 skeleton unchanged as both `scene_skeleton.md` and `script.md`. It creates
the machine-readable context index below. No finished prose or dialogue.

9 is an omniscient director's roundtable. Python selects one native session per
participant, queues observations, validates role outputs, and writes the script.
Characters choose physical action, dialogue, or deliberate silence. The director
receives every character's authored fictional inner monologue and outer response;
other characters receive only eligible external observations. Phase 10 remains
the separately triggered editorial revision stage.

## Phase 7 brief contract

`dramatic_action_brief.md` contains human-readable notes and exactly one fenced
`json` block with this structure (replace example values with established sources):

```json
{
  "scene_id": "locked-room",
  "sources": {
    "bible": ["agents.md", "agents_artifacts/world_rules.md"],
    "continuity": ["continuity.md"],
    "treatment": ["treatment.md"],
    "constraints": ["dramaturgical_checklist.md"],
    "skeleton": ["skeleton.md"]
  },
  "moments": [{
    "moment_id": "BEAT 1",
    "required_outcome": "A genuine attempt to leave",
    "shared_facts": "The door is locked",
    "characters": [{
      "character_id": "alice",
      "stimulus": "The handle resists",
      "knows": "The door is locked",
      "misunderstands": "None established",
      "does_not_know": "Who locked it",
      "conceals": "Her fear, from Bob",
      "objective": "Leave the room",
      "emotion": "Wary",
      "stakes": "Freedom",
      "relationships": "Distrust of Bob",
      "possibilities": ["Try the handle", "Ask Bob for help", "Inspect the window"],
      "dependencies": "Later reaction depends on Bob's unperformed choice"
    }]
  }]
}
```

Character IDs match directory names under `agents_artifacts/characters/`, including
non-speaking characters. Include every assigned moment and participant. Unknown
facts must be flagged, not manufactured. When prior-phase material exists only in
issue comments, preserve an attributed source snapshot in the checkout and point
to it. All source paths are checkout-relative, nonempty, and must exist.

Use exactly one `<!-- RESOLVES [BEAT …] -->` marker per ordered dramatic moment
in the canonical skeleton. A single marker may precede multiple tag groups;
repeated markers are rejected before participant sessions are allocated.

## Phase 8 context index

Each scene directory contains `performance_context.json`:

```json
{
  "version": 1,
  "issue": 42,
  "scene_id": "locked-room",
  "required_moment_ids": ["BEAT 1"],
  "sources": {
    "bible": ["agents.md", "agents_artifacts/world_rules.md"],
    "continuity": ["continuity.md"],
    "treatment": ["treatment.md"],
    "constraints": ["dramaturgical_checklist.md"],
    "skeleton": ["skeleton.md"]
  },
  "characters": {
    "alice": {
      "persona_paths": ["agents_artifacts/characters/alice/personality.md", "agents_artifacts/characters/alice/secrets.md"],
      "known_context": "Own established knowledge and perceived starting situation",
      "private_context": "Own secret, immediate objective, emotion, stakes and constraints"
    }
  }
}
```

Index sources and scene/moment/cast identifiers must agree with the brief.
`AGENTS.md` must identify every indexed source path. Include all relevant persona
assets, not just the two shown. Actor bootstraps contain their own persona and
starting context only; future private situations from unperformed moments are not
injected as memories. The director gets the full brief and all indexed sources.

## Recovery and boundaries

Application manifests, original source snapshots, request journals and private
responses live under this engine's ignored
`workspace/roundtable/<repo-slug>/<issue>/<run-UUID>/`, outside the delivered story.
Codex maintains its own conversation history in its normal location. A run lock
serializes calls and delivery. Explicit resumption checks source/config identity.

Scene inputs are checked against the original snapshot again after role calls,
before rendering. Delivery rechecks that input fingerprint and the accepted
rendered script in the actual delivery checkout after preparation and upstream
merges, before staging, committing, or pushing. Changed material stops delivery
and leaves its journal pending for reconciliation; comments and phase advancement
remain inside the same run lock.

A pending request after a crash means the native session might have consumed it.
Execution stops for reconciliation; it never silently replays or creates a
replacement session. The same fail-closed rule applies to uncertain delivery:
inspect git/GitHub before deciding how to recover. Starting a new performance
does not undo an earlier push. Limits and malformed output never count as
completion. Partial output and private diagnostics remain available locally.

The rendered script includes accepted public performance and public production
cues. Original actor objectives/subtext and unperformed action vessels remain in
`scene_skeleton.md` and the director briefing, not the public script.

Normal repository access is retained. Session separation and explicit routing
enforce the application boundary, **not filesystem secrecy**. Characters are
instructed to distinguish author-visible canon from in-story knowledge. Inner
monologue means authored fictional text, never model hidden reasoning. Semantic
leaks through a director's narration and artistic fidelity still need review.
Native compaction handles context windows; there is no promise of infinite
verbatim recall. Cross-scene continuity comes from artifacts, not reused actors.

Validation for phases 7–9 checks artifacts, identifiers, explicit completion and
performed moment coverage. It does not use npm tests. Phases 5–6 and 10 retain
their existing validation contract; changing those is separate work.

## Verification

Focused offline tests use a fake Codex process and temporary story repositories;
they do not require authentication. A live smoke test must be explicitly enabled
and uses real model quota. Offline tests establish application routing and
recovery, not artistic quality or resistance to deliberate cross-file access.

```bash
.venv/bin/python -m pytest tests/trigger_workflow_creative_writer/ -q
RUN_CODEX_LIVE_SMOKE=1 .venv/bin/python -m pytest tests/trigger_workflow_creative_writer/test_codex_live_sessions.py -q
```

The opt-in smoke test uses six real turns across three native sessions and leaves
their histories in Codex's normal storage. `CODEX_SMOKE_MODEL` is an optional override.
