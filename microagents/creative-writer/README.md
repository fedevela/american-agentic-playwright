# Creative Writer Microagent

This microagent is a multi-phase, deterministic creative writing engine powered by the Gemini CLI. It operates on a dual-layer architecture: a static, immutable set of phases (The Engine) and a dynamic, stateless pool of character personas (The Workspace).

## The Dual-Layer Architecture

1.  **The Engine (Immutable):** A static sequence of phases (Keter through Malkhut) that constructs a fully realized, multi-disciplinary script. These phases dictate *how* the scene is built, separating structural planning from the final rendering of prose and dialogue.
2.  **The Workspace (Mutable):** An arbitrary collection of character persona files (e.g., `workspace/<CHARACTER_FILENAME>.md`) and project definitions, notably `agents_artifacts/dramatic_arcs.md` and `agents.md`. These files provide the state, established canon, and voices injected dynamically into the engine.

### The Required Local Context (The Law of the World)
The engine requires a formal, binding schema of prerequisite artifacts to exist in the workspace before generating scripts. This grounds the generative process in established truth, ensuring characters remain consistent and plot arcs are derived from documented rules rather than hallucinated out of necessity.

The following 11 artifacts must be provided by the script caller in the local folder context:
1. `agents.md`: High-level roster of primary characters.
2. `agents_artifacts/dramatic_arcs.md`: Arcs per character and explicit Plot Arc Colors.
3. `agents_artifacts/world_rules.md`: The physical, societal, and magical constraints.
4. `agents_artifacts/theme.md`: The central argument or thesis.
5. `agents_artifacts/relationships.drawio`: The established dynamics between characters.
6. `agents_artifacts/characters/<character_name>/appearance.md`
7. `agents_artifacts/characters/<character_name>/personality.md`
8. `agents_artifacts/characters/<character_name>/interiorvoice.md`
9. `agents_artifacts/characters/<character_name>/motivations_and_fears.md`
10. `agents_artifacts/characters/<character_name>/secrets.md`
11. `agents_artifacts/characters/<character_name>/lexicon.md`

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

## The Engine Execution Law (Recursion & Handoffs)

The Creative Writer is a fractal engine. It does not run linearly from 1 to 9; it loops based on the `[SIZE]` of the Story Beat it is processing.

*   **The Upstream Loop (Phases 1-4):** These phases operate recursively on `[XLARGE]`, `[LARGE]`, and `[MEDIUM]` beats. Their entire purpose is to fracture macro-narrative structures downward. Tiferet (Phase 4) breaks a `[LARGE]` beat into multiple `[MEDIUM]` beats, which are then fed back into the top of the loop to be broken down again.
*   **The Downstream Pipeline (Phases 5-9):** These phases are the execution engine. They **only awaken** when a beat has been fractured down to the `[SMALL]` atomic unit. You cannot write a `<CAMERA>` tag for a season-long arc; you can only write it for a `[SMALL]` atomic scene.

---

## The Dramaturgical Lexicon (The Mechanism of Transmission)

The engine passes deterministic intent down a rigid pipeline, translating abstract dramaturgical concepts into a physical script via a system of typed placeholder tags.

These tags form the "Typographical Skeleton" generated by the intermediate phases. They are the immutable boundaries of the script's execution, dictating exactly what element of the scene is being rendered. This prevents the engine from confusing dialogue with physical action, or ambiance with lighting, during the final generation.

### The Tags & Their Properties

To ensure deterministic control over the generation, these tags must strictly adhere to a bracketed format, utilizing specific "properties" to constrain the behavior of Phase 9.

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