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

Use `--scene Script/Season_01/Episode_01/scene_materials/locked-room` when an issue has multiple scene handoffs.
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

5 identifies the dramatic and production constraints for the assigned canonical
beats. 6 preserves these as an internal attributed skeleton; its tags are preparation
language, not the public play format.

8 creates `Episode_N/scene_materials/<scene_id>/` with `AGENTS.md`, a copied brief,
byte-preserved `scene_skeleton.md`, immutable public `scene_template.md`, and the
version-3 context index below. The template contains one Markdown scene heading,
established opening directions, canonical beat markers and neutral speech placeholders.
It has no front matter, act heading or boundary lines. The episode's `script.md`
contains front matter and acts once, and a unique bounded region for every scene.
Phase-8 readiness requires the selected region to equal its scene template exactly;
other scenes may be blank, prepared or performed. Preserve other regions and never
automatically overwrite a differing region or append a duplicate scene ID.

9 is an omniscient director's roundtable. Python selects one native session per
participant, queues observations, validates role outputs, and replaces only the selected region in the episode manuscript.
Characters choose an ordered succession of thought, dialogue and action items,
including deliberate silence as action. The director receives every complete contribution;
other characters receive only eligible external observations. Phase 10 remains
the separately triggered editorial stage, writing scene-scoped revision notes while preserving performed text and canonical beat traceability.

## Phase 7 brief contract

`dramatic_action_brief.md` contains human-readable notes and exactly one fenced
`json` block with this structure (replace example values with established sources):

```json
{
  "scene_id": "locked-room",
  "sources": {
    "bible": ["bible/characters.md", "bible/world_rules.md"],
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

Character IDs match directory names under `bible/characters/`, including
non-speaking characters. Include every assigned moment and participant. Unknown
facts must be flagged, not manufactured. When prior-phase material exists only in
issue comments, preserve an attributed source snapshot in the checkout and point
to it. All source paths are checkout-relative, nonempty, and must exist.

Use exactly one `<!-- RESOLVES [BEAT …] -->` marker per ordered dramatic moment
in the canonical skeleton. A single marker may precede multiple tag groups;
repeated markers are rejected before participant sessions are allocated.

## Phase 8 context index

Each real `scene_materials/<scene_id>/` directory contains `performance_context.json`:

```json
{
  "version": 3,
  "issue": 42,
  "scene_id": "locked-room",
  "manuscript_path": "Script/Season_01/Episode_01/script.md",
  "required_moment_ids": ["BEAT 1"],
  "actor_safe_bible_paths": ["bible/public_world.md"],
  "sources": {
    "bible": ["bible/characters.md", "bible/world_rules.md"],
    "continuity": ["continuity.md"],
    "treatment": ["treatment.md"],
    "constraints": ["dramaturgical_checklist.md"],
    "skeleton": ["skeleton.md"]
  },
  "characters": {
    "alice": {
      "display_name": "Alice",
      "persona_paths": ["bible/characters/alice/objective.md", "bible/characters/alice/hidden_objective.md"],
      "scene_context": "The surrounding issue concerns your attempt to leave this room.",
      "moment_contexts": {"BEAT 1": "You perceive that the door is locked."},
      "known_context": "Own established knowledge and perceived starting situation",
      "private_context": "Own secret, immediate objective, emotion, stakes and constraints"
    }
  }
}
```

Index sources and scene/moment/cast identifiers must agree with the brief.
`AGENTS.md` must identify every indexed source path. Include all relevant persona
assets, not just the two shown. The runtime always loads all seven dimensions:
`objective.md`, `hidden_objective.md`, `conflict_with_others.md`,
`conflict_with_self.md`, `conflict_with_environment.md`, `line_of_thought.md`, and
`line_of_images.md`. Each `display_name` is established, nonempty single-line text;
stable folder IDs drive sessions and working directories. Actor bootstraps contain
their own persona, surrounding issue/scene context and explicitly nominated safe bible files; future private situations from unperformed moments are not
injected as memories. The director gets the full brief and all indexed sources. Every character has
nonempty `scene_context` and `moment_contexts` covering exactly the required beat IDs.
Python supplies only the current beat context on each actor turn, including resumed
turns. It does not forward the raw issue or the future beat context map.

`actor_safe_bible_paths` explicitly nominates material suitable for all actors, free
of secrets and spoilers; `[]` is valid. Paths must remain within `bible/` and outside
`bible/characters/`, including after symlink resolution. Python validates paths and
fingerprints content; literary preparation is responsible for its meaning and safety.
Never infer safe content merely from a filename.

The manuscript path is checkout-relative, remains inside the checkout after resolving
symlinks, and names `script.md` in the same episode that owns `scene_materials`.
It is mutable output and must never appear in immutable source roles. Templates
under any `season_template` directory are excluded from discovery and explicit
selection. `--scene` continues to select a preparation-directory path.

Scene IDs use only `[A-Za-z0-9_-]+`. The manuscript wraps each scene body with unique,
balanced, non-nested complete marker lines outside fenced examples:

```markdown
<!-- SCENE locked-room BEGIN -->
### SCENE 1 — ROOM

<!-- RESOLVES [BEAT 1] -->
**ALICE**\
I heard the lock. *(listens)* Did you?

> *(BOB: deliberate silence.)*
<!-- SCENE locked-room END -->
```

Speaker cues use uppercase display names and a hard line break immediately before
speech. Speech has no renderer-added quotation marks; intentionally quoted words
and inline `*(parenthetical)*` directions remain. Public actions, stage events and
silence become blockquoted italic parentheticals. Established CAMERA/LIGHTING/AUDIO
cues become labeled directions in their own moments; transitions close those moments.
No production cue is invented. Private direction, inner monologues, objectives,
subtext and raw skeleton tags do not enter the manuscript. Public plain text is
escaped against Markdown/HTML structure; reserved scene/beat markers and unresolved
placeholders are rejected. Canonical beat markers appear once in order.

See the [complete neutral manuscript template](../examples/creative-project/Script/README.md).

## Ordered role contract

Actors return `turn_id`, `character_id`, and a nonempty `items` array:

```json
{"turn_id":"provided turn ID","character_id":"alice","items":[
  {"category":"dialogue","text":"Did you hear that?"},
  {"category":"thought","text":"I recognize the footsteps."},
  {"category":"action","text":"Steps away from the door."},
  {"category":"dialogue","text":"Stay here."}
]}
```

Each text is nonempty; categories may repeat or be omitted without a prescribed
order or count. All contributions belong to the selected actor. Python assigns
stable `item_id` values from the accepted turn and item position, and records one
private canonical stream plus derived public events. Thought-only interventions
are valid but do not establish external beat performance.

The next director response includes `previous_item_observers`, with exactly one
`{item_id, observers}` entry for every preceding dialogue/action item. Empty witness
lists are valid. Unknown, duplicate, missing and thought-item references are rejected.
Python routes observations in authored item order, even if routing entries arrive
in a different order, including on the final director turn. The manuscript receives
only dialogue/action items in their original order. Thought records never enter
observation queues or public delivery summaries.

## Recovery and boundaries

Application manifests, original source snapshots, request journals and private
responses live under this engine's ignored
`workspace/roundtable/<repo-slug>/<issue>/<run-UUID>/`, outside the delivered story.
Codex maintains its own conversation history in its normal location. A run lock
serializes calls and delivery. Explicit resumption checks source/config identity.
The harness also holds the shared season checkout lock through the entire tick.
An explicit resume may retain only the manuscript bytes authorized by its saved
rendered hash; unrelated dirty files must be reconciled first. Fresh work updates
from main before performance, while delivery reuses the shared season branch.

The existing script hash guards cover the whole episode manuscript; external edits
to any region during an unfinished run require reconciliation. Perform scenes
sequentially; this change adds no concurrent episode-write protocol.

Scene inputs are checked against the original snapshot again after role calls,
before rendering. Delivery rechecks that input fingerprint and the accepted
rendered episode manuscript in the actual delivery checkout after preparation,
before staging, committing, or pushing. Changed material stops delivery
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

Python launches and resumes actors with their own `bible/characters/<id>/` folder
as cwd; the director uses the story root. Configuration and instruction fingerprints
are tracked separately for each role. No additional sandbox is configured.
Normal repository access is retained. Session separation and explicit routing
enforce the application boundary, **not filesystem secrecy**. Characters are
reminded on every initial and resumed turn that, within `bible/characters/`,
only their own character-ID folder is permitted. They must not read, list, search,
or access sibling folders, including indirectly through tools or alternate paths.
This prompt guardrail does not grant tool use or file writes; actors still return
only their role response. The director retains the full briefing. Characters are
instructed to distinguish author-visible canon from in-story knowledge. Inner
monologue means authored fictional text, never model hidden reasoning. Semantic
leaks through a director's narration and artistic fidelity still need review.
Native compaction handles context windows; there is no promise of infinite
verbatim recall. Cross-scene continuity comes from artifacts, not reused actors.

Validation for phases 7–9 checks artifacts, identifiers, explicit completion and
performed moment coverage. It does not use npm tests. Phases 5–6 and 10 retain
their existing validation contract; changing those is separate work.

## Migration

Version-1 and version-2 scene handoffs are rejected with a version-3 preparation instruction.
Editorially redistribute existing appearance, personality, interior voice, wants,
fears, secrets and lexicon material into the seven dimensions; semantically different
sheets must not be blindly renamed. This requires preserving established character
meaning, voice and imagery, not just satisfying filenames.

Instantiate the neutral episode scaffold with real numbers outside `season_template`.
Preserve the full canonical beat definitions and ordered IDs. Prepare fresh version-3
scene materials with established display names, an immutable Markdown scene template,
an explicit episode manuscript destination and unique destination boundaries. Do not
copy story content from the reference template or fabricate a ready handoff. An empty
or placeholder manuscript is not ready for automated performance. New performance checkpoints use version 2 for ordered items. Legacy version-1
checkpoints remain readable as history but cannot resume under the new response
contract: start an intentional new performance. Existing checkpoints are never
rewritten or automatically replayed.

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

## Authorship and phase domains

The character is the supreme writer of their own thoughts, dialogue, and actions.
Preparation contributes circumstances, source-grounded context, dramatic purposes,
and open performance vessels. The director supplies environmental events and invites
responses; each character supplies their own expression. Phase 2 contributes one-line
conceptual ideas, one short sentence per item, with a single orienting narrative sentence.
Phase 10 writes scene-scoped revision_notes.md with editorial observations and questions
for the originating characters, preserving performed script text. A separately requested
character performance supplies any revised thoughts, dialogue, or actions.
