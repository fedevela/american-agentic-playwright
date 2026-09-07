"""Ordered performance and filtered views through the real orchestration loop."""
import json
import pytest

from tests.trigger_workflow_creative_writer.test_roundtable import setup, manifest


def test_ordered_items_and_per_item_witnesses(setup):
    runtime, args, model, scene = setup
    def mutate(value, request):
        if request["role"] == "alice":
            value["items"] = [
                {"category": "dialogue", "text": "First whisper."},
                {"category": "thought", "text": "Secret decision."},
                {"category": "action", "text": "Raises a hand."},
                {"category": "dialogue", "text": "Second whisper."},
            ]
        elif request["role"] == "director" and request.get("latest_response"):
            for route in value["previous_item_observers"]:
                route["observers"] = ["bob"] if route["item_id"].endswith(":3") else []
    model.mutate = mutate
    state = runtime.perform_scene(**args)
    script = (scene.parent.parent / "script.md").read_text()
    assert script.index("First whisper.") < script.index("Raises a hand.") < script.index("Second whisper.")
    assert "Secret decision." not in script
    bob = next(call for call in model.calls if call["role"] == "bob")
    observed = json.dumps(bob["request"])
    assert "Raises a hand." in observed
    assert "First whisper." not in observed and "Second whisper." not in observed
    assert "Secret decision." not in observed
    assert "Secret decision." in json.dumps(state["private_events"])
    assert "Secret decision." not in json.dumps(state["public_events"])
    ids = [item["item_id"] for event in state["private_events"] if event["kind"] == "character" for item in event["items"]]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("invalid", ["missing", "duplicate", "unknown", "thought"])
def test_invalid_item_routing_never_completes(setup, invalid):
    runtime, args, model, scene = setup
    def mutate(value, request):
        if request["role"] != "director" or not request.get("latest_response"):
            return
        routes = value["previous_item_observers"]
        if invalid == "missing": routes.clear()
        elif invalid == "duplicate": routes.append(dict(routes[0]))
        elif invalid == "unknown": routes[0]["item_id"] = "invented"
        else: routes[0]["item_id"] = request["latest_response"]["items"][0]["item_id"]
    model.mutate = mutate
    original = (scene.parent.parent / "script.md").read_bytes()
    with pytest.raises(ValueError, match="item"):
        runtime.perform_scene(**args)
    assert (scene.parent.parent / "script.md").read_bytes() == original


def test_thought_only_does_not_perform_a_beat(setup):
    runtime, args, model, _ = setup
    def mutate(value, request):
        if request["role"] != "director":
            value["items"] = [{"category": "thought", "text": "I hesitate."}]
    model.mutate = mutate
    with pytest.raises(ValueError, match="unperformed"):
        runtime.perform_scene(**args)
    _, state = manifest(args)
    assert state["performed_moment_ids"] == []
    assert all(event["kind"] == "stage" for event in state["public_events"])


def test_actor_cwd_and_current_context_on_fresh_and_resumed_turns(setup):
    runtime, args, model, _ = setup
    runtime.perform_scene(**args)
    for call in model.calls:
        role = call["role"]
        assert call["cwd"] == (args["cwd"] if role == "director" else args["cwd"] / "bible" / "characters" / role)
        if role != "director":
            assert call["request"]["scene_context"]["issue"] == 42
            assert call["request"]["scene_context"]["scene_id"] == "locked-room"
            assert call["request"]["current_moment_context"]


def test_legacy_performance_requires_explicit_restart(setup):
    runtime, args, model, _ = setup
    with pytest.raises(ValueError, match="limit"):
        runtime.perform_scene(**args, max_calls=1)
    path, state = manifest(args)
    state["version"] = 1
    path.write_text(json.dumps(state))
    before = len(model.calls)
    with pytest.raises(ValueError, match="legacy|Legacy"):
        runtime.perform_scene(**args, run_id=state["run_id"])
    assert len(model.calls) == before


def test_changed_actor_configuration_stops_before_next_native_call(setup, monkeypatch):
    runtime, args, model, _ = setup
    changed = False
    monkeypatch.setattr(runtime, "codex_fingerprint", lambda cwd, model=None: {
        "cli": "new" if changed and cwd.name == "alice" else "old"})
    def mutate(value, request):
        nonlocal changed
        if request["role"] == "alice":
            changed = True
    model.mutate = mutate
    with pytest.raises(ValueError, match="fingerprint"):
        runtime.perform_scene(**args)
    assert len(model.calls) == 2


def test_many_items_keep_order_even_when_director_reverses_routes(setup):
    runtime, args, model, scene = setup
    def mutate(value, request):
        if request["role"] == "alice":
            value["items"] = [{"category": "dialogue", "text": f"Line {i:03d}."} for i in range(40)]
        elif request["role"] == "director":
            value["previous_item_observers"].reverse()
    model.mutate = mutate
    runtime.perform_scene(**args)
    bob = next(call for call in model.calls if call["role"] == "bob")
    lines = [item["text"] for item in bob["request"]["observations"] if item["kind"] == "character"]
    assert lines == [f"Line {i:03d}." for i in range(40)]
    script = (scene.parent.parent / "script.md").read_text()
    assert script.index("Line 000.") < script.index("Line 039.")


@pytest.mark.parametrize("item", [
    {"category": "dialogue", "text": "  "},
    {"category": "thought", "text": ""},
    {"category": "stage", "text": "Invented category"},
    {"category": "action", "text": "Waves.", "character_id": "bob"},
])
def test_invalid_actor_item_is_not_accepted(setup, item):
    runtime, args, model, _ = setup
    def mutate(value, request):
        if request["role"] == "alice":
            value["items"] = [item]
    model.mutate = mutate
    with pytest.raises(ValueError):
        runtime.perform_scene(**args)
    _, state = manifest(args)
    assert not state["performed_moment_ids"]
    assert len(state["accepted_turn_ids"]) == 1


def test_recovery_allows_only_journaled_rendered_manuscript(setup):
    runtime, args, _, scene = setup
    with pytest.raises(ValueError, match="limit"):
        runtime.perform_scene(**args, max_calls=1)
    _, state = manifest(args)
    assert runtime.recovery_paths(**args, run_id=state["run_id"]) == set()
    runtime.perform_scene(**args, run_id=state["run_id"])
    script = scene.parent.parent / "script.md"
    assert runtime.recovery_paths(**args, run_id=state["run_id"]) == {str(script.relative_to(args["cwd"]))}
    script.write_text(script.read_text() + "\nUnjournaled text")
    with pytest.raises(ValueError, match="journal"):
        runtime.recovery_paths(**args, run_id=state["run_id"])


def test_recovery_before_journaled_manuscript_replacement_keeps_initial_bytes(setup):
    runtime, args, _, scene = setup
    script = scene.parent.parent / "script.md"
    initial = script.read_bytes()
    state = runtime.perform_scene(**args)
    script.write_bytes(initial)
    assert runtime.recovery_paths(**args, run_id=state["run_id"]) == set()
    runtime.perform_scene(**args, run_id=state["run_id"])
    assert script.read_bytes() != initial
