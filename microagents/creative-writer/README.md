# Creative Writer Microagent

This is a multi-phase creative-writing engine powered by Codex CLI. Gemini and OpenHands are disabled: their new workflow/session integrations are unimplemented. Preparation phases start fresh conversations; phase 9 uses one persistent native session for the omniscient director and one per character.

Phases 7–9 prepare dramatic action, preserve performance materials, and perform the scene. Characters can act, speak, or remain deliberately silent. See [execution, handoff and recovery contracts](../../docs/creative-writing-roundtable.md). Phase 10 remains separately triggered revision; the SDLC engine is unchanged.

## Identity, Creative Attention, and Execution

[Daneel](../../personas/daneel.md) supplies the enduring identity: service to the human partner, humility about uncertainty, and respect for the showrunner's decisions. The twelve [creative-writing personas](../../personas/creative-writer/) give that identity a different mode of attention at each phase. Their lyrical language describes how to approach the work; the functional microagents specify its tasks, boundaries, and products.

[Prompt construction](../../trigger_workflow_creative_writer/prompts.py) composes the base identity (when enabled), the selected phase persona, and its functional microagent, then supplies issue context and response requirements. The character bible is a separate source of fictional identities: an actor's knowledge, wants, fears, secrets, and voice belong to the character being performed.

[Python orchestration](../../trigger_workflow_creative_writer/router.py), with [phase dispatch](../../trigger_workflow_creative_writer/core.py) and [provider dispatch](../../trigger_workflow_creative_writer/execution.py), owns phase selection, prompts, Codex calls, validation, GitHub handoffs, and delivery. The [roundtable](../../trigger_workflow_creative_writer/roundtable.py) also owns phase-9 sessions, observation routing, checkpoints, and public script rendering. Persona language does not implement these mechanisms.

The workspace supplies mutable canon and production artifacts. Ordinary phases start fresh conversations, drawing on supplied issue material and repository files. Phase 9 retains one director session and one session per character for a specific scene/run. The director receives all fictional inner monologues; actors receive their own context and eligible observations. This is controlled prompt routing, not filesystem secrecy.

## The Complete Creative Cycle

The table describes narrative responsibilities and completion conditions. Runtime gates and routing limits are distinguished below. Each row links the lyrical persona and its functional contract; the two Yesod phases and the two Hod phases have separate responsibilities.

| Phase and persona | Functional contract | Incoming material | Responsibility and outcome | Narrative completion condition |
| --- | --- | --- | --- | --- |
| 1 — [Keter: intent](../../personas/creative-writer/keter_intentformation.md) | [Intent formation](phase_1_keter.md) | Human premise or show bible and established artifacts | Translate intent into a Narrative Brief, logline, theme, and sized Master Story Beats without inventing canon. | Sources exist and scope is clear enough for ideation; uncertainty requires clarification. |
| 2A — [Chokhmah: expansion](../../personas/creative-writer/chokhmah_generativeexpansion.md) | [Generative expansion](phase_2A_chokhmah.md) | Keter's clarification only as task content | Expand plausible events, possibilities, and character arcs into semaphored beats. | Structured possibilities preserve the brief and established arc colors. |
| 2B — [Binah: containment](../../personas/creative-writer/binah_criticalrestriction.md) | [Critical restriction](phase_2B_binah.md) | Keter's clarification only as task content | Express world rules, genre exclusions, and boundaries as Master Story Beats. | A structured list states what must remain true and what must be excluded. |
| 2C — [Chesed: grounding](../../personas/creative-writer/chesed_mechanisticgrounding.md) | [Mechanistic grounding](phase_2C_chesed.md) | Keter's clarification only as task content | Ground the premise in wants, actions, reactions, pressures, and consequences. | Structured beats supply workable causes and conflict drivers. |
| 3 — [Gevurah: judgment](../../personas/creative-writer/gevurah_syntheticjudgment.md) | [Synthetic judgment](phase_3_gevurah.md) | Prior ideation outputs and available issue context | Converge the perspectives into chronological, numbered Master Story Beats; present divergent choices to the showrunner. | Retained beats preserve all four properties; unresolved yellow choices remain pending rather than silently becoming canon. |
| 4 — [Tiferet: treatment](../../personas/creative-writer/tiferet_specificationharmony.md) | [Specification](phase_4_tiferet.md) | Authoritative Master Story Beats and available issue context | Decompose and group beats into a scene/sequence treatment and ordered child issues with verbatim parent traceability and pacing rationale. | Every assigned beat is accounted for in the treatment and child payload; structural flaws require feedback. |
| 5 — [Netzach: endurance](../../personas/creative-writer/netzach_traceabilityendurance.md) | [Dramaturgical traceability](phase_5_netzach.md) | Scene treatment and assigned beat definitions | Map emotional and sensory requirements to camera, light, sound, action, and character objective/subtext constraints. | The dramaturgical checklist supports every assigned beat without drafting final prose. |
| 6 — [Hod: articulation](../../personas/creative-writer/hod_analyticalarticulation.md) | [Scene skeleton](phase_6_hod.md) | Netzach's dramaturgical checklist | Build the chronological eight-tag skeleton with attributed properties and `RESOLVES` references. | Scene structure accounts for its beats; dialogue vessels contain no performed speech. |
| 7 — [Yesod: dramatic preparation](../../personas/creative-writer/yesod_integrationfoundation.md) | [Dramatic-action brief](phase_7_yesod_orchestration.md) | Bible, continuity, treatment, constraints, and phase-6 skeleton | Prepare stimuli, knowledge, wants, concealment, stakes, relationships, and possible actions for all participants, including non-speaking characters. | `dramatic_action_brief.md` identifies existing sources and ordered moments, preserves the skeleton, and leaves discretionary responses unchosen. |
| 8 — [Yesod: preservation](../../personas/creative-writer/yesod_transmissionembodiment.md) | [Performance materials](phase_8_yesod_embodiment.md) | Phase-7 brief, unchanged skeleton, source and character assets | Assemble the scene folder, source index, initial script, and each actor's own starting context. | `AGENTS.md`, `performance_context.json`, and sources agree; the copied brief is unchanged and `script.md` initially equals `scene_skeleton.md`. |
| 9 — [Malkhut: performance](../../personas/creative-writer/malkhut_completionsovereignty.md) | [Director's roundtable](phase_9_malkhut.md) | Validated scene materials, preserved skeleton, and performance history within the run | Direct a many-turn performance in which characters act, speak, or choose silence; Python routes observations and renders public material. | All assigned moments are explicitly completed and the public script passes preservation checks before guarded delivery. Limits and malformed turns are failures. |
| 10 — [Hod: revision](../../personas/creative-writer/hod_refactoringstructuralclarity.md) | [Editorial revision](phase_10_hod_refactoring.md) | Drafted script, continuity, and available issue context | Clarify pacing, character voice, emotional architecture, and subtext through stronger action and dialogue. | Revised pages stand alone while preserving the core story, inciting incident, climax, and thematic resolution unless the partner requests a plot change. |

### The Required Local Context (The Law of the World)
The engine requires a formal, binding schema of prerequisite artifacts to exist in the workspace before generating scripts. This grounds the generative process in established truth, ensuring characters remain consistent and plot arcs are derived from documented rules rather than hallucinated out of necessity.

The following 12 artifact types must be provided by the script caller in the local folder context. Items 6–12 are required for each character directory:
1. `agents.md`: High-level roster of primary characters.
2. `agents_artifacts/dramatic_arcs.md`: Arcs per character and explicit Plot Arc Colors.
3. `agents_artifacts/world_rules.md`: The physical, societal, and magical constraints.
4. `agents_artifacts/theme.md`: The central argument or thesis.
5. `agents_artifacts/relationships.drawio`: The established dynamics between characters.
6. `agents_artifacts/characters/<character_name>/appearance.md`
7. `agents_artifacts/characters/<character_name>/personality.md`
8. `agents_artifacts/characters/<character_name>/interiorvoice.md`
9. `agents_artifacts/characters/<character_name>/wants.md`
10. `agents_artifacts/characters/<character_name>/fears.md`
11. `agents_artifacts/characters/<character_name>/secrets.md`
12. `agents_artifacts/characters/<character_name>/lexicon.md`

Existing story repositories must split their combined motivations-and-fears sheet into
`wants.md` (primary want and deep need) and `fears.md` (greatest fear and avoidance
tactics). Both are required; the old combined sheet is not a substitute. Update any
explicit persona paths in scene handoffs and start a new performance after migration,
since the canonical context has changed.

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

The narrative design is recursive. Phases 1–4 clarify, explore, judge, and decompose `[XLARGE]`, `[LARGE]`, and `[MEDIUM]` material until it yields `[SMALL]` scenes. A child sequence may need another upstream cycle before the scene-making responsibilities of phases 5–9. Production duration informs decomposition without defining dramatic size by itself.

The implemented [label map](../../trigger_workflow_creative_writer/config.py) orders ordinary handoffs as `1 → 2A → 2B → 2C → 3 → 4`, then `5 → 6 → 7 → 8 → 9`. Each invocation executes one phase. Ideation runs sequentially by label, but [its task inputs](../../trigger_workflow_creative_writer/prompts.py) are isolated: 2A, 2B, and 2C each receive the extracted Keter clarification rather than the preceding ideator's output. Gevurah receives available issue comments to bring those perspectives together.

Tiferet is a special handoff, not a normal parent transition from 4 to 5. It returns a JSON parent comment and ordered child issues. Python validates the payload, creates child issues with parent/dependency links and branches, posts the summary, and clears the parent's labels except `phase:needsHuman`. In [child creation](../../trigger_workflow_creative_writer/github_ops.py), a literal `[SMALL]` anywhere in the child body assigns `phase:netzach`; otherwise the child receives `phase:keter`. This text check also matches parent beat quotations; it is not a semantic size parser. No general runtime size gate prevents a separately labeled non-small issue from entering phase 5.

Malkhut has no automatic successor. Phase 10 is separately triggered editorial revision and also has no successor. Ordinary phases use fresh native conversations; only a phase-9 scene/run has the persistent director/actor roundtable.

Some creative gates remain model instructions rather than runtime guarantees. [Codex](../../trigger_workflow_creative_writer/codex_runner.py) checks prerequisite existence, and explicit error/rejection responses in discussion/specification paths halt and mark the issue for human intervention. Tiferet rejection does not automatically relabel it to Keter. The [discussion handoff](../../trigger_workflow_creative_writer/core.py) does not recognize Keter's `[ACTION: ASK_QUESTION]` or Gevurah's pending yellow choices as pause signals; these remain unfinished creative work even if a label advances. Keter's functional file also retains a stale reference to eleven artifacts; the twelve types listed here match the required files.

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
*   **`<ACTION>`:** The macro physical choreography of the characters.
    *   *Properties:* `focus` (required), `intent` (optional).
    *   *Example:* `<ACTION focus="<CHARACTER_NAME>" intent="<PHYSICAL_INTENT>">The character takes a described physical action.</ACTION>`
*   **`<PARENTHETICAL/>`:** The micro-performance beats. This is a self-closing tag.
    *   *Properties:* `character` (required), `action` (required).
    *   *Example:* `<PARENTHETICAL character="<CHARACTER_NAME>" action="<MICRO_ACTION>" />`
*   **`<DIALOGUE>`:** The vessel for the character's voice. This is the most complex tag and must remain empty until Phase 9.
    *   *Properties:* `character` (required - maps to the workspace persona), `objective` (required), `subtext` (required), `tone` (optional).
    *   *Example:* `<DIALOGUE character="<CHARACTER_NAME>" objective="<NARRATIVE_GOAL>" subtext="<EMOTIONAL_UNDERCURRENT>" tone="<VOCAL_TONE>"> [INJECT HERE] </DIALOGUE>`
