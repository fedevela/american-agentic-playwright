# Codex Native Sessions: The Omniscient Director

Status: implemented in the current worktree, with offline tests and independent review. Live Codex acceptance remains opt-in and unverified. Gemini and OpenHands remain disabled/unimplemented for this workflow. See [operating contracts](../docs/creative-writing-roundtable.md).

## Goal and relationship to the earlier plan

Make Codex CLI the only enabled harness for the creative-writing engine and use its native persisted sessions for the Malkhut round table: one director session and one session per character, each containing that character's inner dialogue and outward responses. Gemini and OpenHands are disabled for now and explicitly marked unimplemented for this workflow.

| Provider | Planned availability in creative-writing mode | Implementation status |
|---|---|---|
| Codex CLI | Enabled by default; sole execution provider | Adapter and round table implemented; live smoke test opt-in |
| Gemini | Disabled across all creative-writing phases; no fallback | New workflow/session integration unimplemented; legacy code retained |
| OpenHands | Disabled across all creative-writing phases; no fallback | New workflow/session integration unimplemented; legacy code retained |

These provider decisions apply to creative-writing mode. Existing SDLC providers remain unchanged.

This complements [Yesod to Malkhut: The Director's Round Table](2026-09-06-yesod-to-malkhut-directors-roundtable.md). It supersedes that plan's session-design deferral and its restriction on sharing new interior reactions with the director. The director is omniscient: it receives established secrets AND every newly generated character inner monologue. Other characters receive only what they can perceive. The earlier phase 7–8 artifact and handoff alignment remains required.

“Inner monologue” means deliberately authored fictional character text in the final structured response. It does not mean the model's hidden reasoning or reasoning-event output.

## Verified capabilities and limits

Inspected locally on 2026-09-06: `codex-cli 0.153.4`, `codex exec --help`, `codex exec resume --help`, and `codex features list`. No model inference or live session creation was performed.

Codex supports persistent noninteractive runs, explicit-ID resumption, JSONL events including `thread.started`, and schema-constrained final responses. These are the primitives for the adapter. [Official noninteractive documentation](https://learn.chatgpt.com/docs/non-interactive-mode).

The installed CLI advertises stdin prompts, `--json`, `--output-schema`, and `--output-last-message` for both initial execution and resume. Read-only execution and configurable permissions are documented, but read-only access does not itself isolate readable information. [CLI reference](https://learn.chatgpt.com/docs/developer-commands?surface=cli), [security documentation](https://learn.chatgpt.com/docs/security).

Native sessions provide conversation continuity. They do not supply our participant registry, fictional knowledge boundaries, round-table scheduling, or transactional recovery. Python must implement those. Do not read or rewrite Codex's internal session database or rollout format as an application API.

## Harness integration

- Add a creative-writer `codex_runner.py` implementing the existing comment, JSON, implementation, and delivery interfaces. Register explicit runner dispatch; do not let an unrecognized runner fall through to OpenHands.
- Make `codex` the creative-writer default and expose `--runner codex`. Mark Gemini and OpenHands disabled/unimplemented in help and documentation. Explicit requests for either return a clear error such as `Provider 'gemini' is disabled: creative-writing workflow/session integration is unimplemented. Use --runner codex.` Reject them before label synchronization, checkout preparation, session allocation, or any execution.
- Enforce provider availability in both CLI and programmatic entrypoints, including direct execution dispatch, so callers cannot bypass the CLI check. Do not silently fall back if Codex is missing, unauthenticated, or fails. Retain legacy provider modules without exposing them as available execution paths. Keep the SDLC mode and its default unchanged.
- Ordinary phases remain conversation-independent. Native resumption is deliberately enabled only inside a particular phase 9 performance. Do not resume phase 7 or 8 conversations as the director: they contain preparation-agent instructions rather than the director role.
- Reuse checkout, branch verification, artifact prerequisites, and Python-owned delivery. Codex must not independently post comments, advance labels, push, or create PRs. Adopt the earlier plan's writing-specific validation for phases 7–9 instead of copying npm gates into the new performance path.
- Use the existing authenticated Codex installation. Do not copy credentials or change the user's global Codex configuration. Allow a configured model override; otherwise retain the user's configured model, record the effective choice, and keep it stable within a performance.
- Preview and prompt-only modes resolve and show context without launching Codex, allocating sessions, or creating performance state.

## Session identity and invocation

The application registry key is `(repository, issue, scene-relative-path, performance-run-UUID, participant-ID)`. Participant IDs are `director` and stable bible character identifiers, not ambiguous display names. A new performance gets new sessions; resuming an interrupted performance uses the same recorded UUIDs. Never select a session with `--last`, fork the director into a character, or share a session between characters.

Initial call shape, supplied as a Python subprocess argument list with the prompt on stdin:

```text
codex exec --json --output-schema <role-schema> --output-last-message <turn-output> -
```

Read `thread.started.thread_id` from the JSONL stream and durably register it as soon as it arrives. Subsequent calls use:

```text
codex exec resume --json --output-schema <role-schema> --output-last-message <turn-output> <session-UUID> -
```

Both shapes also receive the configured permissions and model selected for the run. Use subprocess `cwd` to run all participants in the same verified managed story checkout, including on resume. Never use `--ephemeral`. Do not construct shell commands by interpolating prompts. Store stdout events and stderr separately; parse the final response file, not commentary or reasoning events. Require successful process and turn completion plus valid role output.

Python switches context by selecting the registry entry and invoking `exec resume` with its exact UUID. It sends new observations and the current turn request, rather than resending a synthetic transcript in place of the native history. One character session produces both the inner and outer response in one turn; no second “outer-only” session is needed.

## Context access and memory separation

| Recipient | Initial context | Turn updates |
|---|---|---|
| Director | Relevant bible, all participating character sheets and secrets, continuity, treatment, phase 5 constraints, skeleton, full phase 7 brief | Every character's inner monologue and outward response; all stage events |
| Character | Own sheet and private situation, personal objectives, known world facts and perceived starting situation | Director's addressed prompt and observations this character can perceive; own prior responses persist natively |
| Final script | No conversation history | Public narration, physical actions, spoken dialogue, and deliberately rendered silence only |

Start character sessions lazily on their first selected turn, including accumulated eligible observations in their bootstrap prompt. Queue subsequent observations in Python until that character is called again; resuming a CLI session creates an LLM turn, so there is no invented “append without inference” command.

Use normal repository access and the existing Codex permission model. Do not introduce dedicated participant filesystems, tool-free profiles, filesystem access controls, or an isolation acceptance gate. Keep native auth/session storage in its existing Codex-managed location; do not repurpose or overwrite `CODEX_HOME`, copy native histories into the story repository, or inject one participant's transcript into another's prompt.

The agreed initial boundary is separate native session IDs plus explicit message routing. Respecting what a fictional character knows is a role/prompt rule: access to the shared story bible does not mean the character knows every fact it contains. Instruct characters to distinguish author-visible canon from their own in-story knowledge. This plan does not claim filesystem-level secrecy or test resistance to deliberate cross-session file access. It also does not add a shared memory store or global summary that merges character histories.

## Round-table protocol

Define JSON Schemas for final role responses and validate them again in Python. Every response echoes an application `turn_id` and uses established character and dramatic-moment IDs.

- Director response: `status` (`continue` or `complete`), `moment_id`, `private_direction`, `stage_events` (text plus eligible observer IDs), `next_speaker` (character ID or null), `character_prompt` (addressed only to the selected character), and `completed_moment_ids`. Continue requires a known participant; complete requires null and sufficient coverage.
- Character response: `character_id`, `inner_monologue`, and `outer_response` containing `action`, `dialogue`, and `silence` fields. Allow action without speech and deliberate silence without forcing filler dialogue. Validate that some external response or deliberate silence is present.

The director's public and addressed channels must not reveal omniscient knowledge as a fact the character already knows. Secrets can become known through an explicit in-scene revelation; record that event. Semantic fidelity still requires review even when field routing is correct.

Loop: resume director with the latest complete character response; record public stage events and the selected character's addressed instruction; call that character; save inner and outer output; relay both to the director. Before another character acts, the director determines which observers can perceive the prior external manifestation. Record and queue those observations without duplicating them in the script. Never include inner monologue or `private_direction` in witness queues or final script rendering.

Only Python writes the performance record and rendered script. Preserve the input skeleton and check the final output against its required moments before the existing delivery path runs.

## Persistence, recovery, and context limits

Store application state under the already ignored `workspace/roundtable/<repo-slug>/<issue>/<run-UUID>/`, outside delivered story files. Persist a manifest with participant-to-session mappings, input hashes, CLI/config/model fingerprint, scene ID, observation cursors, pending turn, and completion/delivery status. Keep private role outputs and the public script record separate. Never print whole private prompts into routine console or GitHub summaries.

Take a run-level lock and issue one role call at a time. Journal each request before launch; preserve raw output before accepting a turn; atomically checkpoint acceptance and observation cursors. Deduplicate accepted events by application turn ID. Native CLI resumption is not an exactly-once transaction: if a crash leaves it uncertain whether a session consumed a request, stop for reconciliation rather than blindly replaying it or silently creating a replacement session.

Expose `--performance-run <UUID>` for explicit recovery and `--new-performance` for a deliberate restart. A normal phase 9 invocation creates a run only when no unfinished run exists for that scene; otherwise report the run ID and require explicit recovery or restart. A missing native session, changed input fingerprint, or incompatible configuration blocks recovery with a specific explanation.

Default limits: 120 total role calls per scene, 1,200 seconds per call, and 6 consecutive director turns without advancement of the current moment or completed-moment set. Make them configurable and checkpoint before reporting exhaustion. Do not interpret exhaustion as scene completion. Failed or malformed role calls pause the performance without blind automatic replay.

Let Codex manage its native context window and compaction. Preserve source snapshots and concise structured current-state checkpoints, scoped to each recipient, and include relevant constraints in turn requests. Do not promise infinite verbatim recall or manually mutate native transcripts. Start a fresh set of sessions for a new scene/performance; cross-scene continuity comes from the story artifacts rather than reusing an actor's entire previous scene history.

## Verification and rollout

1. Unit-test command construction and JSONL parsing with fixtures from the pinned CLI contract: creation UUID capture, exact-ID resume, schema output, failures, and missing identifiers. Assert no `--last`, `--ephemeral`, or shell-interpolated prompts.
2. Test Codex-only defaults, dispatch, and previews. Assert that Gemini and OpenHands fail as disabled/unimplemented for every creative-writing phase through CLI and programmatic paths before side effects. Verify that missing or failing Codex never falls back, and that SDLC behavior remains unchanged.
3. Use a fake Codex executable to run a director and two characters through multiple turns. Prove unique persistent IDs, lazy initialization, queued observations, action/silence support, and complete private feedback to the director with no private leakage into witnesses or script.
4. Test crash boundaries, locks, duplicate events, missing sessions, changed inputs, malformed outputs, and completion limits. Verify no successful delivery for incomplete performances and no duplicate delivery when resuming completed runs.
5. Run an opt-in live three-session smoke test using fictional sentinel facts: each actor recalls their own fact after resume, Python does not route the other's private fact to them, and the director receives both inner responses. All sessions use normal repository access. This verifies session continuity and message routing, not filesystem isolation. The test exercises real authentication and model usage and has not been run while preparing this plan.
6. Combine the harness with the earlier phase-alignment work, replace the phase 9 placeholder with the tested loop, and validate one small scene before enabling Codex as the sole creative-writing provider. Gemini and OpenHands remain disabled until a future implementation explicitly adds and tests their workflow/session adapters.

## Deliverables

Codex runner and native-session adapter; Codex-only provider availability checks; persistent performance registry/journal; role schemas and omniscient director prompts; executable Python round table; CLI selection/recovery options; focused tests and operating documentation. The earlier plan remains the source for phase 7–8 content and artifact requirements, with this plan taking precedence on session behavior, provider availability, normal repository access, and the director's access to inner monologue.
