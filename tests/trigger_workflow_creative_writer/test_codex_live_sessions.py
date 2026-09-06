"""Opt-in native continuity check. Consumes real model quota when enabled."""
import json
import os
import subprocess

import pytest

from trigger_workflow_creative_writer.codex_runner import call_codex


@pytest.mark.skipif(os.environ.get("RUN_CODEX_LIVE_SMOKE") != "1", reason="Live Codex usage is opt-in")
def test_three_native_sessions_retain_own_facts_and_director_receives_both(tmp_path):
    story = tmp_path / "story"
    story.mkdir()
    subprocess.run(["git", "init", "-q", str(story)], check=True)
    schema = {"type": "object", "properties": {"text": {"type": "string"}},
              "required": ["text"], "additionalProperties": False}
    sessions = {}
    sequence = 0

    def turn(participant, prompt):
        nonlocal sequence
        sequence += 1
        def remember(sid):
            if participant in sessions:
                assert sessions[participant] == sid
            else:
                assert sid not in sessions.values()
                sessions[participant] = sid
        raw = call_codex(prompt + " Return only the requested JSON. Do not modify files or run tools.",
                         cwd=story, turn_dir=tmp_path / f"turn-{sequence}", schema=schema,
                         session_id=sessions.get(participant), on_session=remember,
                         model=os.environ.get("CODEX_SMOKE_MODEL"))
        return json.loads(raw)["text"]

    turn("director", "You direct a fictional scene, omniscient. Acknowledge readiness.")
    turn("alice", "You are fictional Alice. Your private fictional memory is AMBER-COMET-713. Remember it; acknowledge readiness.")
    turn("bob", "You are fictional Bob. Your private fictional memory is COBALT-ORCHID-829. Remember it; acknowledge readiness.")
    # Recall prompts do not repeat either fact or contain a sibling's output.
    alice_inner = turn("alice", "Write a fictional inner monologue stating your exact private memory token, with no extra facts.")
    bob_inner = turn("bob", "Write a fictional inner monologue stating your exact private memory token, with no extra facts.")
    assert "AMBER-COMET-713" in alice_inner and "COBALT-ORCHID-829" not in alice_inner
    assert "COBALT-ORCHID-829" in bob_inner and "AMBER-COMET-713" not in bob_inner
    director = turn("director", f"Authored fictional inner responses: Alice: {alice_inner}; Bob: {bob_inner}. Report both private tokens verbatim.")
    assert "AMBER-COMET-713" in director and "COBALT-ORCHID-829" in director
    assert len(set(sessions.values())) == 3
