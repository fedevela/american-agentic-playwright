# Creative Writer Character Profiles and Episode Manuscripts Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task by task. Check off the steps as evidence is collected. Implementation is a separate task; this document authorizes no story writing, external delivery, or historical-run migration.

**Goal:** Align the creative-writer runtime and canonical project template with the director’s seven English character dimensions and one Markdown manuscript per episode containing all scenes and beats.

**Architecture:** Keep performance sessions and preparation scoped to one scene. Give each scene handoff an explicit destination region within the episode manuscript. Render the completed public performance as Markdown in the episode manuscript, keeping its front matter and other scenes in place.

**Tech Stack:** Existing Python runtime, pytest, Markdown, JSON handoffs and checkpoints, native Codex CLI. No new runtime dependencies.

**Spec:** The partner’s approved project structure and formatting decisions in this conversation, embodied in the sibling Little Red Riding Hood project’s `Script/README.md` and `Script/season_template/Season_N/Episode_N/script.md`. This plan makes the runtime-specific decisions below explicit.

## Global Constraints and Defaults

- Character filenames and authored documentation use English. Keep the lyrical persona voices while updating their artifact responsibilities.
- One `Episode_N/script.md` contains front matter, acts, scenes, and all beats. No scene manuscript files or beat documents/folders.
- Preserve canonical beat definitions and ordered `<!-- RESOLVES [BEAT …] -->` identifiers. A beat remains a dramatic and traceability unit.
- Default: scene preparation files live under `Episode_N/scene_materials/<scene_id>/`. These are director/runtime inputs, not separate manuscripts. This was proposed during planning; the partner may revise this storage preference before implementation.
- Retain internal phase-6 attributed skeleton tags and existing role JSON schemas. This change concerns the public Markdown manuscript and its destination, not replacing the whole dramaturgical preparation language.
- Retain scene-scoped persistent director/actor sessions, eligible-observation routing, response-only actors, character-folder boundaries, and private state outside the story checkout.
- Codex remains the sole enabled creative-writer provider. SDLC behavior, GitHub beat decomposition, and phase progression remain unchanged.
- Source filenames change by explicit migration, not aliases. The handoff advances to version 2 for its new manuscript destination. Existing recovery and delivery machinery is outside this change; update its file references only as needed.
- The canonical template is neutral and empty. Do not copy the sibling project’s characters, GSA concepts, or story material into the runtime repository.
- No commits, pushes, live Codex calls, issue comments, or story generation are part of plan execution unless separately requested. Preserve existing user changes.

## Target Structure and Contracts

```text
examples/creative-project/
├── bible/characters/character_id/
│   ├── objective.md
│   ├── hidden_objective.md
│   ├── conflict_with_others.md
│   ├── conflict_with_self.md
│   ├── conflict_with_environment.md
│   ├── line_of_thought.md
│   └── line_of_images.md
└── Script/
    ├── README.md
    └── season_template/Season_N/
        ├── README.md
        └── Episode_N/
            ├── README.md
            └── script.md
```

A prepared real episode additionally has `scene_materials/<scene_id>/` containing `AGENTS.md`, `dramatic_action_brief.md`, `scene_skeleton.md`, `scene_template.md`, and `performance_context.json`. Do not place fake ready-to-run handoffs in the blank reference implementation.

`scene_skeleton.md` remains the byte-preserved phase-6 source. `scene_template.md` is the canonical public scene layout before performance: its scene heading, established opening directions, canonical beat markers, and neutral dialogue placeholders. It contains no front matter or act heading; those belong outside the replaceable scene region. It is an immutable preparation input, not a second manuscript. Actual performance replaces the region initially copied from this template.

Version-2 `performance_context.json` retains the existing issue, scene ID, sources, character contexts, and required moment IDs, and adds:

```json
{
  "version": 2,
  "manuscript_path": "Script/Season_01/Episode_01/script.md"
}
```

Scene boundaries are derived from `scene_id`, using a validated `[A-Za-z0-9_-]+` identifier:

```markdown
<!-- SCENE scene-id BEGIN -->
### SCENE 1 — Scene title

<!-- RESOLVES [BEAT 1] -->
...
<!-- SCENE scene-id END -->
```

Boundaries are unique, balanced, non-nested, and recognized only as complete marker lines outside fenced code examples. Public output cannot inject scene boundaries or beat markers. Scene identity comes from the handoff, not the title or scene number.

Extend `SceneMaterials` with resolved `manuscript_path`, immutable `scene_template`, and explicit display names for cast IDs. Add required `display_name` to each version-2 character entry; names come from the established cast and must be single-line, nonempty text. Stable folder IDs continue to drive session identity and access checks.

Keep `--scene` selecting a preparation-directory path. Document its new example path; do not overload it with manuscript titles or add a second selector.

## Task 1 — Character File Contract and Neutral Reference Bible

**Modify:** `trigger_workflow_creative_writer/artifact_validation.py`, `prompts.py`, `examples/creative-project/bible/`, relevant microagent reference lists.

**Tests:** `tests/trigger_workflow_creative_writer/test_artifact_validation.py`, `test_prompts.py`, `test_scene_materials.py`.

- [ ] Add failures demonstrating acceptance of all seven new names and rejection of an old-only profile or any missing new dimension.
- [ ] Replace `REQUIRED_CHARACTER_ARTIFACTS` with the exact seven names above. Generate the prompt’s character artifact list from this constant instead of maintaining a second hardcoded list. Preserve existing foundation gate scope and semantics.
- [ ] Replace the reference character sheets with seven empty structured files. Redistribute guidance for appearance, speech, fears, secrets, and traits among the new dimensions; remove duplicate legacy sheets and update the bible guide.
- [ ] Update fixture character assets and verify `load_scene` loads all seven even when the handoff explicitly lists only one. Preserve path containment and sibling-context rejection tests for fresh and resumed actor sessions.
- [ ] Run the three targeted test modules and inspect every failure before continuing.

## Task 2 — Episode Manuscript Location

**Create:** `trigger_workflow_creative_writer/manuscript.py`, `tests/trigger_workflow_creative_writer/test_manuscript.py`.

- [ ] Add a small helper that locates a scene by the boundary comments specified above and substitutes its rendered text inside the episode manuscript.
- [ ] Keep front matter, act headings, other scenes, and their beats in place. Require an unambiguous target scene rather than infer its location from its title.
- [ ] Test a two-scene episode: writing either scene leaves the other scene and front matter unchanged. Test a missing or duplicate target identifier.

## Task 3 — Version-2 Scene Preparation and Canonical Markdown Scene Template

**Modify:** `scene_materials.py`, phase-8 prompt requirements, `microagents/creative-writer/phase_8_yesod_embodiment.md`.

**Tests:** `test_scene_materials.py`, `test_prompts.py`.

- [ ] Introduce the version-2 handoff fields and `SceneMaterials` fields specified above. Resolve the manuscript inside the checkout, require the basename `script.md`, and require its parent to be the episode containing the handoff’s `scene_materials` directory. Reject absolute paths, escaping symlinks, and mismatched episode destinations.
- [ ] Preserve original brief/skeleton equality, source-role checks, ordered moments, cast validation, and own-character context loading. Add `scene_template.md` to immutable snapshots; exclude the mutable episode manuscript from immutable source roles.
- [ ] Validate scene-template beat markers against the brief and skeleton. Require a Markdown scene heading and forbid front matter, act headings, boundary markers, and raw internal skeleton tags in the public scene template. Phase-8 readiness requires the selected manuscript region to equal `scene_template.md` exactly; other scenes can be blank, prepared, or already performed.
- [ ] Update phase-8 instructions to create the scene-preparation directory and insert one bounded scene template into an existing or newly scaffolded episode. Preserve front matter, act headings, and other scene regions. Never append a duplicate scene ID or overwrite an existing differing region automatically.
- [ ] Exclude any `season_template` directory from handoff discovery, including explicit selection. Require real IDs/numbers when preparing actual episodes.
- [ ] Test that the neutral blank example is not performance-ready and that version-1 handoffs fail with an actionable migration message.

## Task 4 — Public Play-Script Rendering

**Create:** `trigger_workflow_creative_writer/play_format.py`, `tests/trigger_workflow_creative_writer/test_play_format.py`.

**Modify:** roundtable rendering helpers and role instructions where necessary.

**Interface:** `render_scene(scene: SceneMaterials, state: dict) -> str` returns only the selected scene body, with canonical markers and no boundary lines.

- [ ] Add tests for the accepted play format: uppercase Markdown scene heading; bold uppercase display-name cue; hard line break followed immediately by dialogue; no renderer-added quotation marks; blockquoted italic parenthetical stage directions; inline italic parentheticals preserved within speech.
- [ ] Keep actor JSON shape unchanged. Actor dialogue may contain Markdown inline `*(...)*` directions; separate `action` remains a standalone direction. Specify that regular speech is returned without wrapper quotes. Preserve quoted words intentionally within speech.
- [ ] Render director public stage events, actor action, and deliberate silence as stage directions. Silence is explicit and requires no fabricated speech. Render each canonical beat marker once in established order.
- [ ] Preserve the scene heading and fixed constraints from the skeleton in their proper moments; translate established CAMERA/LIGHTING/AUDIO constraints to labeled parenthetical directions and transitions at the end of their moment. Do not invent production cues. Keep objectives, subtext attributes, private direction, and inner monologues out of public output.
- [ ] Escape structural Markdown/HTML in public plain text so speaker names, actions, or model responses cannot introduce headings, boundaries, or hidden executable markup. Allow only the specified inline-direction convention within dialogue; reject reserved scene/beat markers and unresolved template placeholders in public responses.
- [ ] Test multilingual dialogue, punctuation, embedded quotes, parentheses, special Markdown characters, silent characters, malicious marker text, and absence of legacy XML tags/private sentinels.

## Task 5 — Connect the Episode Output Path

**Modify:** `roundtable.py`, `router.py`.

**Tests:** `test_roundtable.py`, `test_malkhut_integration.py`.

- [ ] Replace scene-local `script.md` references with `SceneMaterials.manuscript_path`. Use the manuscript helper to place the rendered scene in that episode document.
- [ ] Point existing script checks and delivery callbacks at the episode file. Keep existing session, checkpoint, recovery, and delivery behavior; introduce no new locks, checkpoint format, recovery protocol, or delivery workflow.
- [ ] Update fixtures and assertions for the episode path and Markdown output. Test two scene performances contributing to the same episode manuscript.

## Task 6 — Canonical Example and Cycle Instructions

**Modify:** `examples/creative-project/`, `microagents/creative-writer/README.md`, relevant phase 5–10 microagents, relevant lyrical personas, `docs/creative-writing-roundtable.md`, root `AGENTS.md` where its creative-mode description needs clarification.

- [ ] Replace the example’s numbered scene/beat directory scaffold with `Script/season_template/Season_N/Episode_N/{README.md,script.md}`. Add generic `Script/README.md` containing the complete reusable Markdown template and export-layout guidance.
- [ ] Keep title, playwright/contact, character age/gender/traits, setting/time, act/scene, dialogue, stage direction, inline direction, and repeatable scene/beat placeholders. Use hidden canonical boundary/beat examples instead of the sibling template’s informal `Beat [ID]` comment. Explain that real preparation substitutes validated IDs and preserves full beat definitions.
- [ ] Link the episode outline’s scene index to headings inside its manuscript. Clarify that the separately preserved scene template is runtime preparation material, while one episode script is the publication source.
- [ ] Revise phase 5–8 responsibilities to distinguish internal attributed skeletons from the Markdown destination. Revise phase 9 delivery and phase 10 revision instructions to target episode regions and retain traceability. Preserve persona lyricism; keep schemas and strict technical details in microagents/runtime documentation.
- [ ] Document migration: editorially redistribute old character profiles into the seven dimensions; instantiate the neutral episode scaffold; prepare version-2 scene materials and destination boundaries. Redistributing existing character prose is an editorial task; do not blindly rename semantically different sheets. Historical performance migration is outside this plan.
- [ ] Search active code, docs, examples, and tests for stale character filenames, per-scene `script.md` contracts, and Beat folders. Keep historical plans unchanged; retain old strings only in explicit migration/rejection tests and documentation.
- [ ] Verify the sibling story bible with the new artifact contract read-only. Do not change its story content or claim that its placeholder manuscript is ready for automated performance.

## Final Verification and Acceptance

Run targeted tests after each task, then:

```bash
python3 -m pytest tests/trigger_workflow_creative_writer -q
python3 -m pytest tests/trigger_workflow -q
git diff --check
```

Use the repository’s existing Python environment if required. Do not install dependencies or initiate live model/GitHub operations merely to validate this refactor.

Acceptance requires: all seven new character files are used consistently; a two-scene episode receives independent scene performances in one Markdown script; front matter and neighboring scenes are preserved; emitted prose follows the requested play format; public output excludes private actor material and internal tags; actor access boundaries remain intact; blank templates are excluded from discovery; the new handoff identifies its episode destination; SDLC tests remain green. Review all canonical template links and rendering of a synthetic manuscript. Report any environment-blocked checks precisely rather than treating them as passes.
