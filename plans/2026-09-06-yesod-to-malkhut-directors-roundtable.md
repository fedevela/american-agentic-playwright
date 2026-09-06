# Yesod to Malkhut: The Director's Round Table

Status: implemented in the current worktree together with [Codex Native Sessions: The Omniscient Director](2026-09-06-codex-native-sessions-omniscient-director.md). That companion plan supersedes the historical session deferral and director privacy restriction below. Offline tests and independent review completed; live Codex acceptance remains opt-in and unverified. See [operating contracts](../docs/creative-writing-roundtable.md).

## Goal

Align the creative-writing workflow's latter stages so that phase 7 prepares actionable dramatic situations, phase 8 preserves the performance materials, and phase 9 produces a script through a director-and-characters round table. Characters can respond through physical action, dialogue, or deliberate silence.

Assume the director and each character have separate conversations that persist during a performance. This plan defines their responsibilities and information boundaries, not how sessions are created, resumed, stored, switched, or compacted. Stop after this planning deliverable until the partner resumes the work or requests the separate session-design plan.

## Current problems

- Phase 7's microagent requests persona-file mapping and CLI instructions, while its persona and generated prompt request act assembly and pacing changes. Neither captures the agreed responsibility: establish what each character can perceive and act upon in a specific dramatic moment.
- Phase 8's microagent saves an unfinished skeleton, but its persona and generated prompt request finished prose.
- Phase 9's microagent describes a Stage Master and Character Souls, while its persona and generated prompt describe editorial validation.
- The phase 9 Python handler contains a commented performance-loop sketch and proceeds directly to delivery without generating a script.
- Creative-writing implementation phases inherit npm validation from the SDLC engine. Those checks do not establish whether the required writing artifacts or a completed performance exist.

## Phase 7: Prepare the dramatic situation

Align the phase persona, functional microagent, generated prompt, and documentation around dramatic-action preparation. Keep the existing phase ID and label.

Inputs are the relevant story bible, established continuity, treatment, phase 5 objectives and subtext, and phase 6 scene skeleton. The bible supplies established character identities; phase 7 specifies their situation at this point in the story.

Save `dramatic_action_brief.md` in the target checkout. Organize it by dramatic moment, retaining existing story-beat IDs for traceability, then by participating character. Include:

- The concrete stimulus: an event, another person's behavior, an obstacle, or an opportunity the character can perceive and act upon.
- What the character knows, misunderstands, and does not know; what they conceal and from whom.
- Their immediate objective, emotional state, stakes, and relevant relationship or power pressures.
- Available physical and conversational possibilities grounded in the setting, objects, circumstances, and the character's capabilities.
- The scene's required outcome and structural constraints, distinguished from possibilities left open to performance.

Separate shared stage facts from private character information. Reference the source context so the director can distinguish established facts from interpretation. Flag missing or contradictory context rather than inventing prior events. Cover characters who act without dialogue as well as those named in dialogue slots.

Preserve canon, scene order, and prescribed objectives/subtext. Do not write final dialogue, predetermine discretionary responses, redesign act boundaries, or generate CLI orchestration commands. Where a later situation depends on an unperformed choice, describe that dependency instead of claiming the choice has already happened.

## Phase 8: Assemble the performance materials

Align all phase 8 instructions around preparation and persistence. Create the existing story hierarchy and its contextual `AGENTS.md`, save the attributed skeleton as `script.md`, and carry `dramatic_action_brief.md` into the same scene directory. Preserve the source brief until successful delivery.

The scene's contextual anchor must identify the source materials for the director's briefing: relevant bible entries and continuity, treatment, phase 5 constraints, phase 6 skeleton, and phase 7 brief. Preserve required story-beat references, tag properties, and empty dialogue vessels. No finished prose or dialogue is generated in this phase.

Completion requires the scene materials to exist and agree on the scene, participating characters, and assigned dramatic moments. Missing required context is reported as an incomplete handoff, not silently filled in.

## Phase 9: Perform through the director's round table

Align the Malkhut persona, microagent, generated prompt, and Python handler around scene performance. The Stage Master is the director. Phase 10 retains the separate editorial-revision role and remains separately triggered.

### Context and authority

The director receives all relevant context assembled by prior phases, including each character's established secrets and private starting situation. The director also receives the accumulating public performance so decisions reflect what has actually happened.

Each character receives their own persona, private starting situation, objectives, and perceivable events. A character must not receive another character's private information merely because the director knows it. Default: newly generated private interior reactions remain in the originating character's conversation; only external manifestations return to the director and eligible witnesses. Changing that default requires a separate product decision.

The director controls stage narration, progression through the dramatic moments, and selection of the next participant. Characters choose their response within canon and scene constraints. `next_speaker` means the next character to act; it does not require spoken dialogue. Use the existing name consistently in the initial implementation.

### Logical turn sequence

1. Load and check the scene materials before starting the performance. Preserve the original skeleton as an input artifact so completion can be checked against it after rendering.
2. Ask the director to establish or update the dramatic situation and designate the next character, or explicitly report scene completion.
3. Make the director's public narration available to characters who can perceive it. An observation update need not invoke an LLM response.
4. Invoke the selected character with their own context and current observations. Their response distinguishes private interior reaction from external manifestation: physical action, dialogue, or deliberate silence.
5. Append public narration and external manifestation to the ordered performance record. Relay the manifestation to the director and eligible witnesses. Keep private interior material out of the public script.
6. Continue from the changed situation. The brief establishes the starting conditions; actual responses update them. Do not reset participants to their initial emotional state each turn.
7. When the director reports completion, check coverage and unresolved placeholders, render the finished `script.md`, and only then attempt delivery and label completion.

Python owns turn ordering, information routing, the script buffer, and file writes. LLM calls produce bounded role responses rather than managing loops or writing files themselves. The provider/CLI/session adapter is intentionally unspecified pending the separate session plan.

### Completion and failures

- Require explicit director completion and coverage of assigned dramatic moments; an absent or unknown participant is not implicit success.
- Reject malformed role responses and unknown next-character selections without appending them to the script or advancing the label.
- Add configurable turn and repeated-no-progress limits when implementing the runtime. Exhausting either produces an incomplete performance requiring intervention, never a successful delivery. Exact limits belong to the deferred runtime/session design.
- Preserve partial work on failure and report the missing context, unresolved moment, or failed turn. Do not commit an unfinished scene as completed phase 9 work.
- Check that the final script contains the required scene content and no unresolved skeleton placeholders or private interior response fields. These checks establish structural completion, not artistic quality.

## Validation and integration

Keep changes within the creative-writing engine. Preserve phase IDs, labels, and GitHub delivery conventions. Do not change the SDLC engine or implement session infrastructure under this plan.

Replace inherited npm checks for the changed creative-writing phases 7–9 with artifact and performance checks appropriate to their outputs. Keep that change scoped to these stages; evaluating phases 5–6 and 10 is separate work. Ensure failure prevents delivery or phase advancement and produces a useful explanation.

Update tests for assembled persona/microagent/generated prompts, including removal of conflicting phase 7 casting and act-pacing requirements, phase 8 drafting requirements, and phase 9 validation-only requirements.

For the eventual round-table implementation, use a fake conversation interface to verify:

- The director receives the complete relevant briefing; each character receives only their permitted context.
- A selected character can act physically or remain deliberately silent without producing dialogue.
- Public events reach the director and eligible witnesses; private reactions do not leak into other character contexts or the script.
- Successive turns build on prior public actions and retain per-character continuity.
- Invalid responses, unknown participants, incomplete scene coverage, and turn-limit exhaustion prevent successful delivery.
- A valid completed performance renders the script and invokes the existing delivery/handoff once.

## Implementation order and pause boundary

1. Align phase 7 instructions and its artifact contract.
2. Align phase 8 preparation and the full-context director handoff.
3. Align phase 9 role instructions and document the logical round-table contract.
4. Design session mechanics with the partner before implementing the actual LLM conversation adapter or executable performance loop.
5. Implement and test the loop and creative-writing validation once the session design is agreed.

The immediate deliverable is this saved plan. No phase instructions, runtime code, or session behavior have been changed as part of saving it.
