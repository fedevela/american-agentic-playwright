# Creative Writer Microagent

This is a multi-phase creative-writing engine powered by Codex CLI. Gemini and OpenHands are disabled: their new workflow/session integrations are unimplemented. Preparation phases start fresh conversations; phase 9 uses one persistent native session for the omniscient director and one per character.

Phases 7–9 prepare dramatic action, preserve performance materials, and perform the scene. Characters can act, speak, or remain deliberately silent. See [execution, handoff and recovery contracts](../../docs/creative-writing-roundtable.md). Phase 10 remains separately triggered revision; the SDLC engine is unchanged.

## Identity, Creative Attention, and Execution

[Daneel](../../personas/creative-writer/daneel.md) supplies the enduring identity: care for the supplied intention, honesty about uncertainty, and independent creative judgment. The twelve [creative-writing personas](../../personas/creative-writer/) give that identity a different mode of attention at each phase. Their lyrical language describes how to approach the work; the functional microagents specify its tasks, boundaries, and products.

[Prompt construction](../../trigger_workflow_creative_writer/prompts.py) composes the base identity (when enabled), the selected phase persona, and its functional microagent, then supplies issue context and response requirements. The character bible is a separate source of fictional identities: an actor's knowledge, wants, fears, secrets, and voice belong to the character being performed.

[Python orchestration](../../trigger_workflow_creative_writer/router.py), with [phase dispatch](../../trigger_workflow_creative_writer/core.py) and [provider dispatch](../../trigger_workflow_creative_writer/execution.py), owns phase selection, prompts, Codex calls, validation, GitHub handoffs, and delivery. The [roundtable](../../trigger_workflow_creative_writer/roundtable.py) also owns phase-9 sessions, observation routing, checkpoints, and public script rendering. Persona language does not implement these mechanisms.

The workspace supplies mutable canon and production artifacts. Ordinary phases start fresh conversations, drawing on supplied issue material and repository files. Phase 9 retains one director session and one session per character for a specific scene/run. The director receives all fictional inner monologues; actors receive their own context and eligible observations. This is controlled prompt routing, not filesystem secrecy.

## The Complete Creative Cycle

The table describes narrative responsibilities and completion conditions. Runtime gates and routing limits are distinguished below. Each row links the lyrical persona and its functional contract; the two Yesod phases and the two Hod phases have separate responsibilities.

| Phase and persona | Functional contract | Incoming material | Responsibility and outcome | Narrative completion condition |
| --- | --- | --- | --- | --- |
| 1 — [Keter: intent](../../personas/creative-writer/keter_intentformation.md) | [Intent formation](phase_1_keter.md) | Human premise or show bible and established artifacts | Translate intent into a Narrative Brief, logline, theme, and sized Master Story Beats without inventing canon. | The supplied intention and sources support ideation; useful assumptions and development questions carry uncertainty forward. |
| 2A — [Chokhmah: expansion](../../personas/creative-writer/chokhmah_generativeexpansion.md) | [Generative expansion](phase_2A_chokhmah.md) | Keter's clarification only as task content | Offer premise-level possibilities, one short sentence per item. | Structured possibilities preserve the brief and established arc colors. |
| 2B — [Binah: containment](../../personas/creative-writer/binah_criticalrestriction.md) | [Critical restriction](phase_2B_binah.md) | Keter's clarification only as task content | Offer resistance, limits, and costs, one short sentence per item. | Each idea identifies a distinct pressure within established canon. |
| 2C — [Chesed: grounding](../../personas/creative-writer/chesed_mechanisticgrounding.md) | [Mechanistic grounding](phase_2C_chesed.md) | Keter's clarification only as task content | Offer causal conditions, material circumstances, and stakes, one short sentence per item. | Concise ideas supply plausible conditions for later character discovery. |
| 3 — [Gevurah: judgment](../../personas/creative-writer/gevurah_syntheticjudgment.md) | [Synthetic judgment](phase_3_gevurah.md) | Prior ideation outputs and available issue context | Converge the perspectives into chronological, numbered Master Story Beats; present divergent choices to the showrunner. | Retained beats preserve all four properties; unresolved yellow choices remain pending rather than silently becoming canon. |
| 4 — [Tiferet: treatment](../../personas/creative-writer/tiferet_specificationharmony.md) | [Specification](phase_4_tiferet.md) | Authoritative Master Story Beats and available issue context | Decompose and group beats into a scene/sequence treatment and ordered child issues with verbatim parent traceability and pacing rationale. | Every assigned beat is accounted for in the treatment and child payload; structural flaws require feedback. |
| 5 — [Netzach: endurance](../../personas/creative-writer/netzach_traceabilityendurance.md) | [Dramaturgical traceability](phase_5_netzach.md) | Scene treatment and assigned beat definitions | Map emotional and sensory requirements to camera, light, sound, action, and character objective/subtext constraints. | The dramaturgical checklist supports every assigned beat without drafting final prose. |
| 6 — [Hod: articulation](../../personas/creative-writer/hod_analyticalarticulation.md) | [Scene skeleton](phase_6_hod.md) | Netzach's dramaturgical checklist | Build the chronological eight-tag skeleton with attributed properties and `RESOLVES` references. | Scene structure accounts for its beats; dialogue vessels contain no performed speech. |
| 7 — [Yesod: dramatic preparation](../../personas/creative-writer/yesod_integrationfoundation.md) | [Dramatic-action brief](phase_7_yesod_orchestration.md) | Bible, continuity, treatment, constraints, and phase-6 skeleton | Prepare stimuli, knowledge, wants, concealment, stakes, relationships, and available affordances for all participants, including non-speaking characters. | `dramatic_action_brief.md` identifies existing sources and ordered moments, preserves the skeleton, and leaves discretionary responses unchosen. |
| 8 — [Yesod: preservation](../../personas/creative-writer/yesod_transmissionembodiment.md) | [Performance materials](phase_8_yesod_embodiment.md) | Phase-7 brief, unchanged skeleton, source and character assets | Assemble scene preparation, the public scene template, its bounded episode destination, and each actor's own starting context. | `AGENTS.md`, `performance_context.json`, and sources agree; the copied brief is unchanged and the selected episode region initially equals `scene_template.md`; `scene_skeleton.md` preserves phase 6. |
| 9 — [Malkhut: performance](../../personas/creative-writer/malkhut_completionsovereignty.md) | [Director's roundtable](phase_9_malkhut.md) | Validated scene materials, preserved skeleton, and performance history within the run | Direct a many-turn performance in which characters act, speak, or choose silence; Python routes observations and renders public material. | All assigned moments are explicitly completed and the public script passes preservation checks before guarded delivery. Limits and malformed turns are failures. |
| 10 — [Hod: revision](../../personas/creative-writer/hod_refactoringstructuralclarity.md) | [Editorial revision](phase_10_hod_refactoring.md) | Drafted script, continuity, and available issue context | Write scene-scoped editorial notes and revision questions for the originating characters. | Performed text stays verbatim; notes preserve the core story and identify any pending character revision. |

### The Required Local Context (The Law of the World)

The story bible lives in `bible/`. Its `characters.md` is the cast overview;
`characters/<character_id>/` holds each character's detailed profile. The bible's README is
navigation; the required canon files are listed below. Treatments, skeletons, and
performed scripts live outside the bible. Reserve `AGENTS.md` for agent instructions.

The canonical template is the [creative-project reference](../../examples/creative-project/README.md).
Copy its contents into a story repository, or copy only its `bible/` directory
when adding a bible to an existing project.
It includes the bible and a neutral `Script/season_template/Season_N/Episode_N/` scaffold
with one blank episode manuscript. Populate canon before running the writing workflow.

To migrate an existing story, rename `agents_artifacts/` to `bible/` and move the
root cast roster `agents.md` to `bible/characters.md`. Update paths in source indexes,
dramatic-action briefs, performance contexts, and local instructions. Rebuild the
phase-8 handoff and start a new performance: existing recovery records retain the
old source paths and must not be rewritten to impersonate the original run.
The legacy paths are no longer accepted as substitutes for the canonical layout.

The engine requires a formal, binding schema of prerequisite artifacts to exist in the workspace before generating scripts. This grounds the generative process in established truth, ensuring characters remain consistent and plot arcs are derived from documented rules rather than hallucinated out of necessity.

The following 12 artifact types must be provided by the script caller in the local folder context. Items 6–12 are required for each character directory:
1. `bible/characters.md`: High-level roster of primary characters.
2. `bible/dramatic_arcs.md`: Arcs per character and explicit Plot Arc Colors.
3. `bible/world_rules.md`: The physical, societal, and magical constraints.
4. `bible/theme.md`: The central argument or thesis.
5. `bible/relationships.drawio`: The established dynamics between characters.
6. `bible/characters/<character_name>/objective.md`
7. `bible/characters/<character_name>/hidden_objective.md`
8. `bible/characters/<character_name>/conflict_with_others.md`
9. `bible/characters/<character_name>/conflict_with_self.md`
10. `bible/characters/<character_name>/conflict_with_environment.md`
11. `bible/characters/<character_name>/line_of_thought.md`
12. `bible/characters/<character_name>/line_of_images.md`

Existing story repositories must editorially redistribute their character material
across these seven dimensions. The legacy appearance, personality, interior voice,
wants, fears, secrets, and lexicon files are not substitutes and should not be blindly
renamed because their meanings overlap multiple dimensions. Update any explicit persona
paths in scene handoffs and start a new performance after migration, since the canonical
context has changed.

Phase 1 (Keter) will halt execution via an Artifact Validation Gate if it cannot locate these established constraints.

---

## The Master Story Beats

The fundamental unit of narrative currency within the engine is the **Master Story Beat**. From Phase 2 (Ideation) through Phase 9 (Execution), the story is tracked, evaluated, and rendered using these beats.

Every Master Story Beat must contain the following deterministic properties:

1.  **Importance Semaphore:**
    *   **`[RED]`**: Fundamental dramaturgical artifacts (Core plot pillars, absolute world rules).
    *   **`[YELLOW]`**: Divergent paths (Important elements where multiple valid options exist, requiring later synthesis).
    *   **`[GREEN]`**: Side plots, flavor, or non-critical tonal refinements.
2.  **Plot Arc Color:** A thematic identifier linking the beat to a specific storyline (e.g., `[ARC: <PRIMARY_COLOR>]` for the main plot, `[ARC: <SECONDARY_COLOR>]` for a subplot).
3.  **Timeline Location:** The chronological reality of the beat: `[PAST]`, `[PRESENT]`, or `[FUTURE]`.
4.  **Size (Dramaturgical Scope):**
    *   `[XLARGE]`: A Structural Paradigm Shift (alters overarching reality, long-term character destiny, or core world state).
    *   `[LARGE]`: A Major Narrative Resolution (resolves a central conflict or decisively answers a primary dramatic question for a storyline).
    *   `[MEDIUM]`: A Significant Escalation or Reversal (a sequence of events that permanently changes the immediate tactical situation).
    *   `[SMALL]`: An Atomic Dramatic Unit (a single, unbroken chain of action/dialogue where a character pursues one immediate objective within a continuous space).

*Format Example:*
`[BEAT <NUMBER>] [<IMPORTANCE_SEMAPHORE>] [ARC: <COLOR_IDENTIFIER>] [<TIMELINE>] [<SIZE>] - <Description of the narrative event or outcome>.`

---

## The Production Reality (Temporal Structure)

While the `[SIZE]` property measures *dramaturgical* weight, the swarm must remain aware of the physical production constraints when breaking down narrative structures or calculating pacing. The target informative structural math is:

*   **Season:** 8 Episodes.
*   **Episode:** 45 minutes total.
*   **Development (Act/Sequence):** 3 per episode (15 minutes each).
*   **Short/Scene:** 150 seconds (2.5 minutes) each. (Approximately 6 shorts per development).

---

## Narrative Recursion and Implemented Handoffs

The narrative design is recursive. Existing project roots use `size:season`; generated
artifacts and issues use `size:episode`, `size:act`, `size:scene`, or `size:undetermined`. All issue trees
ultimately yield ready scene leaves. Python validates structured scope, source
coverage and readiness; quoted size words never control routing.

The label order is `1 → 2A → 2B → 2C → 3 → 4`, then ready scenes enter
`5 → 6 → 7 → 8 → 9`. Each exploration reads its current accepted Keter brief
independently. Gevurah receives all three current explorations and Tiferet preserves
its organization. Agents resolve creative choices independently and carry open form into development assignments.

Tiferet creates ready scenes and/or recursive development assignments. Python owns
parent links, dependencies, retry reconciliation and completion rollup; it removes
only the active parent phase label. Phase 5 requires a validated ready scene.
All descendants share the season root's Git branch and PR to main.
See [exploration contracts](../../docs/creative-writing-exploration.md).

Malkhut has no automatic successor. Phase 10 is separately triggered editorial
revision. Ordinary phases use fresh conversations; only a phase-9 scene/run has
persistent director/actor sessions. Actor turns contain ordered thought, dialogue
and action items; Python routes witnesses per public item and renders the scene.
Actors run from their own character folders with actor-facing scene/beat context
and explicitly nominated safe bible sources. Thoughts stay private.

Phases 7 and 8 have writing-specific artifact validators; phase 9 validates scene inputs, role responses, completion, and the public script against the preserved skeleton. Phases 5, 6, and 10 currently retain the [repository validation contract](../../trigger_workflow_creative_writer/runner_utils.py) (`npm run typecheck`, `npm run build`, `npm run test`, `npm run tests:e2e`). These are execution checks, not proof of narrative quality. See the [execution and recovery contract](../../docs/creative-writing-roundtable.md) for scene selection, explicit recovery, and delivery reconciliation.

---

## The Dramaturgical Lexicon (The Mechanism of Transmission)

The preparation phases translate dramaturgical intent into a scene skeleton through typed placeholder tags. Performance supplies situated action and dialogue within that structure.

These tags form the preserved "Typographical Skeleton" generated by the intermediate phases. It distinguishes dialogue, action, camera, lighting, and sound without predetermining every discretionary response. The immutable source skeleton and rendered public script serve different purposes: rendering omits private objective/subtext instructions and unperformed dialogue vessels while preserving the required scene structure and beat references.

### The Tags & Their Properties

The source tags use the bracketed format and properties below. Phase 6 establishes the structure; phases 7 and 8 preserve it for phase 9. `[INJECT HERE]` is an unperformed placeholder, not dialogue.

*   **`<SCENE_HEADING>`:** The foundational anchor (e.g., `<SCENE_HEADING>INT. <LOCATION> - <TIME></SCENE_HEADING>`).
*   **`<TRANSITION>`:** The grammar of passage between scenes (e.g., `<TRANSITION><TRANSITION_TYPE>:</TRANSITION>`).
*   **`<CAMERA>`:** Dictates framing, movement, and focus.
    *   *Properties:* `shot` (required), `movement` (optional), `target` (optional).
    *   *Example:* `<CAMERA shot="<SHOT_TYPE>" movement="<MOVEMENT_TYPE>" target="<TARGET_SUBJECT>">The camera describes the visual framing.</CAMERA>`
*   **`<LIGHTING>` & `<AUDIO>`:** Governs visual texture, illumination, and the auditory layer.
    *   *Properties:* `mood` (required), `source` (optional).
    *   *Example:* `<LIGHTING mood="<MOOD_DESCRIPTION>" source="<LIGHT_SOURCE>">The visual atmosphere is established.</LIGHTING>`
*   **`<ACTION>`:** Environmental conditions and open vessels for character movement.
    *   *Properties:* `focus` (required), `intent` (optional).
    *   *Example:* `<ACTION focus="<CHARACTER_NAME>" intent="<PHYSICAL_INTENT>">[INJECT HERE]</ACTION>`
*   **`<PARENTHETICAL/>`:** A reserved character delivery vessel. Use a neutral placeholder during preparation. This is a self-closing tag.
    *   *Properties:* `character` (required), `action` (required).
    *   *Example:* `<PARENTHETICAL character="<CHARACTER_NAME>" action="[INJECT HERE]" />`
*   **`<DIALOGUE>`:** The vessel for the character's voice. This is the most complex tag and must remain empty until Phase 9.
    *   *Properties:* `character` (required - maps to the workspace persona), `objective` (required), `subtext` (required), `tone` (optional).
    *   *Example:* `<DIALOGUE character="<CHARACTER_NAME>" objective="<NARRATIVE_GOAL>" subtext="<EMOTIONAL_UNDERCURRENT>" tone="<VOCAL_TONE>"> [INJECT HERE] </DIALOGUE>`

Each episode has one Markdown `script.md` for all scenes and beats. Scene-scoped
preparation lives under `scene_materials/<scene_id>/`; the version-3 handoff names
its episode destination. See the [canonical blank format](../../examples/creative-project/Script/README.md)
and [runtime contracts and migration](../../docs/creative-writing-roundtable.md).

### Character authorship across phases

The character is the supreme writer of their own thoughts, dialogue, and actions.
Keter contributes intention; Chokhmah possibilities; Binah resistance; Chesed grounding;
Gevurah synthesis; Tiferet assignments; Netzach continuity and sensory context; Hod
spatial and temporal structure; Yesod playable context and faithful preparation;
Malkhut environmental stimuli, turn selection, and observation routing. Revision Hod
contributes editorial notes for the originating characters.

All three phase-2 explorations use one short sentence on one line per item and one
short orienting sentence in the narrative field. Each artifact retains its scope and pivotal BEAT identity. Outlines and beats express circumstances and dramatic purposes; characters
create their expression. Character action and delivery tags remain neutral vessels
until performance. Existing canon supplies context, while newly authored character
performance originates in character turns. Revision notes live in
scene_materials/<scene_id>/revision_notes.md; character changes await a separately
requested performance, with the current episode script preserved verbatim.


## Pivotal beats and open scope

Each Keter anchor and exploration artifact carries a one-sentence pivotal event,
its stable `BEAT-*` identity, and predecessor references where applicable. The same
event keeps its identity through transformation; a new or split event names its
predecessors. Gevurah gives each element exactly one pivotal beat. Ready scenes
also require concrete placement, an outline, ordered beats, and an identified pivotal event.

Public references use compact labels such as `BEAT-K1`, linked to canonical IDs
in the Markdown. There is no private beat-evolution explanation or stored history
of earlier definitions. Earlier issue comments remain available as ordinary history.

## Issue and repository memory

The active issue, its GitHub parents, and repository files are the memory. Recent
issue conversation appears ahead of generated proposals without a special comment
format or a reply-waiting mechanism. Phase 2 keeps independent Keter-only generated
inputs while receiving current conversation. Roundtable session boundaries remain.

Phase output is visible Markdown with a small vocabulary of headings and field
labels. Python reads those same paragraphs and identifiers. There are no hidden
creative records, text locators, JSON ancestry graphs, or recursive record resolver.
Structured model responses are transient input for validation and rendering.
Anchor source-reference lists are omitted; BEAT identities and predecessor links
carry pivotal continuity. Parent assignments select supporting material by the
element’s pivotal BEAT ID. Every synthesized pivotal identity enters an element.

Phase prose appears directly below its heading. Titles appear in element headings,
and purpose sentences appear directly below their item. Routine outcome, repeated
phase scope, reference-prefix explanations, and boolean pivotal labels are omitted.
Element scope/readiness and placement remain visible. A development or execution
failure heading appears only when needed. Older visible field labels remain readable.

The Keter comment starts each run; phase headings and comment order identify its
later outputs. Separate workflow cycle/result blocks are not published. Scope and
readiness route work. Sources and BEAT references preserve immediate relationships. Elements appear
before collapsible supporting anchors. Child bodies link to the parent assignment
and name their element, cycle, scope, and readiness. Scene entry reads the immediate
parent element and outline, without replaying the whole exploration history.

Visible assignment keys prevent duplicate child creation. GitHub child issues,
parent relationships, and blocking dependencies govern completion. Existing
issue edits are not rejected merely because their prose differs from creation.

Historical comments are not rewritten or migrated. Older hidden records are not
read; begin a fresh Keter cycle before using the visible format. No live execution
is part of this code change. Verification follows the instruction to run no tests:
syntax parsing, source review, and `git diff --check` only.
# Readable pivotal beat identities

New beats use names such as `BEAT-K1-1-1` (Keter) or `BEAT-CH1-2A-1`
(Chokhmah). The first number distinguishes a stem and the last distinguishes
beats under that stem. Both are positive integers. Phase letters are K, CH, B,
C, and G for 1, 2A, 2B, 2C, and 3. Cycle and issue ownership remain on the
containing result; a beat name alone is not a global lookup key.

Retain existing names across phases and inherited work. New events must not
reuse source or ancestor names. Cycle-qualified IDs remain valid. A unique
source may acquire its readable name (for example,
`BEAT-4d6a1d8707fe-1-1` becomes `BEAT-K1-1-1`); Python preserves the original source
ID in predecessor links. Ambiguous readable names require the exact source ID.
Derived beats also carry transitive predecessor IDs so later cycles cannot
reuse the name of a distant ancestor. Published history remains intact.

Source references may use an exact full ID or an unambiguous label from the
published source link. This applies to predecessor beats, Gevurah's selected
pivotal beat, and Tiferet's assigned element. Python reads the actual link
targets, including historical qualifiers, and stores full IDs after resolution.
If source comments use the same label for different targets, use the full ID.
