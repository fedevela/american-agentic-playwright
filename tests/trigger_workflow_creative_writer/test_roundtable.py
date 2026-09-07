"""Persistent orchestration tests; model calls are replaced at the external boundary."""
import copy
import fcntl
import json
from pathlib import Path
import uuid

import pytest

from tests.trigger_workflow_creative_writer.test_scene_materials import make_scene


def direction(turn_id, speaker="alice", complete=False, observers=None):
    return {"turn_id": turn_id, "status": "complete" if complete else "continue",
            "moment_id": "BEAT 1", "private_direction": "director private sentinel",
            "stage_events": [] if complete else [{"text": "The lock clicks.", "observers": ["alice", "bob"]}],
            "next_speaker": None if complete else speaker,
            "character_prompt": "Choose whether to try the door." if not complete else "",
            "completed_moment_ids": ["BEAT 1"] if complete else [],
            "previous_response_observers": observers or []}


class Model:
    def __init__(self):
        self.calls = []
        self.counts = {}
        self.mutate = None
        self.fail = False
        self.collision = False

    def __call__(self, prompt, *, session_id=None, on_session, turn_dir, **kwargs):
        request = json.loads(prompt)
        role = request["role"]
        sid = session_id or str(uuid.uuid4())
        if self.collision and self.calls:
            sid = self.calls[0]["session"]
        on_session(sid)
        self.calls.append({"role": role, "session": sid, "resume": session_id, "request": request})
        if self.fail:
            raise RuntimeError("native session missing")
        count = self.counts.get(sid, 0)
        self.counts[sid] = count + 1
        if role == "director":
            value = direction(request["turn_id"], ("alice", "bob", "alice", "bob")[count % 4],
                              complete=count >= 4, observers=[] if count == 0 else ["alice", "bob"])
        else:
            value = {"turn_id": request["turn_id"], "character_id": role,
                     "inner_monologue": role + " inner sentinel",
                     "outer_response": {"action": "Tries the handle." if role == "alice" else "",
                                        "dialogue": "", "silence": role == "bob"}}
        if self.mutate:
            self.mutate(value, request)
        turn_dir.mkdir(parents=True, exist_ok=True)
        (turn_dir / "response.txt").write_text(json.dumps(value))
        return json.dumps(value)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    from trigger_workflow_creative_writer import roundtable
    root = tmp_path / "story"
    scene = make_scene(root)
    model = Model()
    monkeypatch.setattr(roundtable, "call_codex", model)
    monkeypatch.setattr(roundtable, "codex_fingerprint", lambda cwd, model=None: {"model": model, "cli": "fake-v1"})
    arguments = {"repo": "owner/story", "issue": 42, "cwd": root,
                 "state_root": tmp_path / "private"}
    return roundtable, arguments, model, scene


def manifest(arguments):
    paths = list(arguments["state_root"].glob("*/*/*/manifest.json"))
    assert len(paths) == 1
    return paths[0], json.loads(paths[0].read_text())


def test_character_folder_guardrail_reaches_fresh_and_resumed_actor_turns(setup):
    runtime, args, model, scene = setup
    runtime.perform_scene(**args)
    for role in ("alice", "bob"):
        turns = [call for call in model.calls if call["role"] == role]
        assert turns[0]["resume"] is None
        assert turns[1]["resume"] is not None
        for call in turns:
            rule = call["request"]["character_folder_guardrail"]
            assert f"bible/characters/{role}/" in rule
            assert "Do not read, list, search, or access any sibling character folder" in rule
            assert "does not authorize tool use" in rule
    for call in model.calls:
        if call["role"] == "director":
            assert "character_folder_guardrail" not in call["request"]


def test_persistent_sessions_route_only_observable_deltas_and_render_public_script(setup):
    runtime, args, model, scene = setup
    original = (scene / "scene_skeleton.md").read_text()
    result = runtime.perform_scene(**args)
    assert result["status"] == "completed"
    assert [c["role"] for c in model.calls] == ["director", "alice", "director", "bob", "director", "alice", "director", "bob", "director"]
    sessions = {}
    for call in model.calls:
        role = call["role"]
        if role in sessions:
            assert call["resume"] == sessions[role]
            assert "bootstrap" not in call["request"]
        else:
            sessions[role] = call["session"]
            assert call["resume"] is None
    assert len(set(sessions.values())) == 3
    assert "bob private sentinel" in json.dumps(model.calls[0]["request"])
    actors = [c for c in model.calls if c["role"] != "director"]
    for call in actors:
        text = json.dumps(call["request"])
        sibling = "bob" if call["role"] == "alice" else "alice"
        assert sibling + " private sentinel" not in text
        assert sibling + " inner sentinel" not in text
        assert "director private sentinel" not in text
    assert "alice inner sentinel" in json.dumps(model.calls[2]["request"])
    assert len(actors[1]["request"]["observations"]) >= 3
    script = (scene.parent.parent / "script.md").read_text()
    assert script.count("Tries the handle.") == 2
    assert "silence" in script.lower()
    assert "<!-- RESOLVES [BEAT 1] -->" in script
    assert "Room" in script and 'objective="leave"' not in script
    assert "sentinel" not in script and "INJECT HERE" not in script
    assert (scene / "scene_skeleton.md").read_text() == original
    path, state = manifest(args)
    assert state["pending"] is None
    assert len(state["accepted_turn_ids"]) == 9
    assert (path.parent / "snapshots.json").is_file()


def test_limit_checkpoint_resumes_exact_next_role_and_delivers_once(setup):
    runtime, args, model, scene = setup
    with pytest.raises(ValueError, match="limit"):
        runtime.perform_scene(**args, max_calls=3)
    _, state = manifest(args)
    assert state["next_role"] == "bob"
    first_director_session = model.calls[0]["session"]
    with pytest.raises(ValueError, match=state["run_id"]):
        runtime.perform_scene(**args)
    deliveries = []
    result = runtime.perform_scene(**args, run_id=state["run_id"], deliver=lambda: deliveries.append("published") or "summary")
    assert result["status"] == "delivered"
    assert result["summary"] == "summary"
    assert model.calls[4]["resume"] == first_director_session
    before = len(model.calls)
    again = runtime.perform_scene(**args, run_id=state["run_id"], deliver=lambda: deliveries.append("duplicate"))
    assert again["summary"] == "summary" and len(model.calls) == before
    assert deliveries == ["published"]


@pytest.mark.parametrize("failure", ["native", "malformed", "collision"])
def test_uncertain_pending_turn_never_replays(setup, failure):
    runtime, args, model, _ = setup
    if failure == "native":
        model.fail = True
    elif failure == "malformed":
        model.mutate = lambda value, request: value.update(unexpected=True)
    else:
        model.collision = True
    with pytest.raises((ValueError, RuntimeError)):
        runtime.perform_scene(**args)
    _, state = manifest(args)
    assert state["pending"]
    assert state["sessions"]["director"]
    before = len(model.calls)
    with pytest.raises(ValueError, match="reconcil"):
        runtime.perform_scene(**args, run_id=state["run_id"])
    assert len(model.calls) == before


@pytest.mark.parametrize("mutation", ["unknown-observer", "duplicate-observer", "bad-turn", "bad-actor", "extra-inner", "wrong-type", "early-complete", "unknown-moment", "placeholder", "empty-outer"])
def test_invalid_structured_turn_is_not_accepted_or_delivered(setup, mutation):
    runtime, args, model, scene = setup
    initial = (scene.parent.parent / "script.md").read_text()
    def mutate(value, request):
        if request["role"] == "director":
            if mutation == "unknown-observer": value["stage_events"][0]["observers"] = ["nobody"]
            if mutation == "duplicate-observer": value["stage_events"][0]["observers"] = ["alice", "alice"]
            if mutation == "bad-turn": value["turn_id"] = "invented"
            if mutation == "wrong-type": value["stage_events"][0]["text"] = 9
            if mutation == "early-complete": value.update(status="complete", next_speaker=None, completed_moment_ids=["BEAT 1"])
            if mutation == "unknown-moment": value["moment_id"] = "BEAT 9"
            if mutation == "placeholder": value["stage_events"][0]["text"] = "TODO"
        else:
            if mutation == "bad-actor": value["character_id"] = "bob"
            if mutation == "extra-inner": value["outer_response"]["inner_monologue"] = "leak"
            if mutation == "empty-outer": value["outer_response"] = {"action": "", "dialogue": "", "silence": False}
    model.mutate = mutate
    deliveries = []
    with pytest.raises(ValueError):
        runtime.perform_scene(**args, deliver=lambda: deliveries.append(True))
    assert not deliveries and (scene.parent.parent / "script.md").read_text() == initial
    _, state = manifest(args)
    assert state["pending"]


def test_changed_inputs_config_and_output_fail_closed(setup):
    runtime, args, model, scene = setup
    with pytest.raises(ValueError, match="limit"):
        runtime.perform_scene(**args, max_calls=1)
    _, state = manifest(args)
    with pytest.raises(ValueError, match="fingerprint"):
        runtime.perform_scene(**args, run_id=state["run_id"], model="different")
    source = args["cwd"] / "continuity.md"
    original = source.read_text()
    source.write_text("changed source")
    with pytest.raises(ValueError, match="fingerprint"):
        runtime.perform_scene(**args, run_id=state["run_id"])
    source.write_text(original)
    manuscript = scene.parent.parent / "script.md"
    manuscript.write_text(manuscript.read_text() + "\nhuman draft")
    with pytest.raises(ValueError, match="script.*changed"):
        runtime.perform_scene(**args, run_id=state["run_id"])


def test_repeated_canonical_marker_rejected_before_session_allocation(setup):
    runtime, args, model, scene = setup
    skeleton = (scene / "scene_skeleton.md").read_text()
    skeleton += '\n<CAMERA>Hold on the door.</CAMERA>\n<!-- RESOLVES [BEAT 1] -->\n<AUDIO>Clock ticks.</AUDIO>'
    for path in (args["cwd"] / "skeleton.md", scene / "scene_skeleton.md"):
        path.write_text(skeleton)
    with pytest.raises(ValueError, match="Repeated canonical marker.*BEAT 1"):
        runtime.perform_scene(**args)
    assert model.calls == []
    assert not args["state_root"].exists()
    assert (scene / "scene_skeleton.md").read_text() == skeleton


def test_source_changed_during_role_call_is_rejected_before_render_and_delivery(setup):
    runtime, args, model, scene = setup
    original_script = (scene.parent.parent / "script.md").read_text()
    def change_source(value, request):
        if value.get("status") == "complete":
            (args["cwd"] / "continuity.md").write_text("Changed during performance")
    model.mutate = change_source
    deliveries = []
    with pytest.raises(ValueError, match="fingerprint.*changed"):
        runtime.perform_scene(**args, deliver=lambda: deliveries.append(True))
    assert deliveries == []
    assert (scene.parent.parent / "script.md").read_text() == original_script
    _, state = manifest(args)
    assert state["rendered_script_hash"] is None
    assert state["delivery"] is None


def test_stagnation_is_checkpointed_and_can_resume_with_larger_limit(setup):
    runtime, args, _, _ = setup
    with pytest.raises(ValueError, match="progress"):
        runtime.perform_scene(**args, max_no_progress=2)
    _, state = manifest(args)
    assert state["pending"] is None
    assert runtime.perform_scene(**args, run_id=state["run_id"], max_no_progress=9)["status"] == "completed"


def test_pending_delivery_requires_reconciliation(setup):
    runtime, args, _, _ = setup
    calls = []
    def fail():
        calls.append("external write")
        raise RuntimeError("connection lost")
    with pytest.raises(RuntimeError):
        runtime.perform_scene(**args, deliver=fail)
    _, state = manifest(args)
    with pytest.raises(ValueError, match="reconcil"):
        runtime.perform_scene(**args, run_id=state["run_id"], deliver=fail)
    assert calls == ["external write"]


def test_run_lock_is_held_through_delivery(setup):
    runtime, args, _, _ = setup
    def delivery():
        _, state = manifest(args)
        with pytest.raises(ValueError, match="lock|running"):
            runtime.perform_scene(**args, run_id=state["run_id"])
        return "ok"
    assert runtime.perform_scene(**args, deliver=delivery)["summary"] == "ok"


@pytest.mark.parametrize("options", [{"run_id": "../escape"}, {"run_id": str(uuid.uuid4())}, {"max_calls": 0}, {"timeout": 0}, {"max_no_progress": -1}])
def test_invalid_run_or_limits_launch_nothing(setup, options):
    runtime, args, model, _ = setup
    with pytest.raises(ValueError):
        runtime.perform_scene(**args, **options)
    assert model.calls == []


def test_new_performance_retains_unfinished_run(setup):
    runtime, args, _, _ = setup
    with pytest.raises(ValueError, match="limit"):
        runtime.perform_scene(**args, max_calls=1)
    first_path, _ = manifest(args)
    first_contents = first_path.read_bytes()
    with pytest.raises(ValueError, match="limit"):
        runtime.perform_scene(**args, new_performance=True, max_calls=1)
    assert first_path.read_bytes() == first_contents
    assert len(list(args["state_root"].glob("*/*/*/manifest.json"))) == 2


def test_effective_configured_model_is_pinned_on_native_calls(setup, monkeypatch):
    runtime, args, model, _ = setup
    monkeypatch.setattr(runtime, "codex_fingerprint", lambda cwd, model=None: {"effective_model": "configured-model"})
    received = []
    def call(prompt, **kwargs):
        received.append(kwargs["model"])
        return model(prompt, **kwargs)
    monkeypatch.setattr(runtime, "call_codex", call)
    runtime.perform_scene(**args)
    assert received == ["configured-model"] * 9


def test_duplicate_acceptance_does_not_append_public_events(setup):
    runtime, args, _, _ = setup
    runtime.perform_scene(**args)
    path, state = manifest(args)
    last = state["accepted_turn_ids"][-1]
    response = json.loads((path.parent / "turns" / last / "parsed_response.json").read_text())
    before = copy.deepcopy(state)
    with pytest.raises(ValueError, match="Duplicate"):
        runtime._accept(state, response)
    assert state == before


def test_registry_lock_prevents_selecting_any_run(setup):
    runtime, args, model, _ = setup
    with pytest.raises(ValueError, match="limit"):
        runtime.perform_scene(**args, max_calls=1)
    path, state = manifest(args)
    before = len(model.calls)
    with (path.parent.parent / ".registry.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match="lock"):
            runtime.perform_scene(**args, new_performance=True)
    assert len(model.calls) == before


@pytest.mark.parametrize("corruption", ["snapshot", "missing-snapshot", "identity", "unknown-participant", "duplicate-turn", "missing-native-id"])
def test_corrupt_checkpoint_is_not_resumed(setup, corruption):
    runtime, args, model, _ = setup
    with pytest.raises(ValueError, match="limit"):
        runtime.perform_scene(**args, max_calls=3)
    path, state = manifest(args)
    if corruption == "snapshot": (path.parent / "snapshots.json").write_text("{}")
    elif corruption == "missing-snapshot": (path.parent / "snapshots.json").unlink()
    elif corruption == "identity": state["issue"] = 43
    elif corruption == "unknown-participant": state["sessions"]["nobody"] = str(uuid.uuid4())
    elif corruption == "duplicate-turn": state["accepted_turn_ids"].append(state["accepted_turn_ids"][0])
    elif corruption == "missing-native-id": del state["sessions"]["director"]
    path.write_text(json.dumps(state))
    before = len(model.calls)
    with pytest.raises(ValueError):
        runtime.perform_scene(**args, run_id=state["run_id"])
    assert len(model.calls) == before


def test_schema_failure_preserves_parsed_private_response(setup):
    runtime, args, model, _ = setup
    model.mutate = lambda value, request: value.update(extra="invalid")
    with pytest.raises(ValueError):
        runtime.perform_scene(**args)
    path, state = manifest(args)
    turn = path.parent / "turns" / state["pending"]["turn_id"]
    assert json.loads((turn / "parsed_response.json").read_text())["extra"] == "invalid"
    assert "director private sentinel" in (turn / "raw_response.txt").read_text()


def test_second_scene_is_not_blocked_by_first_unfinished_run(setup):
    runtime, args, model, scene = setup
    second = add_second_scene(args['cwd'], scene)
    with pytest.raises(ValueError, match="limit"):
        runtime.perform_scene(**args, scene_path=str(scene.relative_to(args['cwd'])), max_calls=1)
    model.mutate = lambda value, request: value.update(moment_id='BEAT 2')
    with pytest.raises(ValueError, match="limit"):
        runtime.perform_scene(**args, scene_path=str(second.relative_to(args['cwd'])), max_calls=1)
    assert len(model.calls) == 2


@pytest.mark.parametrize("change", ["regress", "shrink", "skip", "unperformed"])
def test_multiple_moments_reject_invalid_progression(setup, change):
    from types import SimpleNamespace
    runtime, args, _, _ = setup
    runtime.perform_scene(**args)
    _, state = manifest(args)
    turn = str(uuid.uuid4())
    state.update(next_role="director", pending={"turn_id": turn}, moment_id="BEAT 2",
                 completed_moment_ids=["BEAT 1"], performed_moment_ids=["BEAT 1", "BEAT 2"])
    scene = SimpleNamespace(moment_ids=["BEAT 1", "BEAT 2", "BEAT 3", "BEAT 4"], character_contexts={"alice": "", "bob": ""})
    value = direction(turn, observers=["bob"])
    value.update(moment_id="BEAT 2", completed_moment_ids=["BEAT 1"])
    if change == "regress": value["moment_id"] = "BEAT 1"
    elif change == "shrink": value["completed_moment_ids"] = []
    elif change == "skip": value["moment_id"] = "BEAT 4"
    elif change == "unperformed": value["completed_moment_ids"] = ["BEAT 1", "BEAT 3"]
    with pytest.raises(ValueError):
        runtime._validate_turn(value, state, scene)


def test_renderer_keeps_public_production_cues_but_not_unperformed_vessels(setup):
    from types import SimpleNamespace
    runtime, args, _, _ = setup
    runtime.perform_scene(**args)
    _, state = manifest(args)
    skeleton = '''<!-- RESOLVES [BEAT 1] -->
<SCENE_HEADING>Room</SCENE_HEADING>
<CAMERA>Close on the handle.</CAMERA>
<LIGHTING>Blue.</LIGHTING><AUDIO>Low hum.</AUDIO>
<DIALOGUE character="alice" objective="secret objective sentinel" subtext="private subtext sentinel">[INJECT HERE]</DIALOGUE>
<ACTION focus="alice">Unperformed prescribed leap.</ACTION>
<PARENTHETICAL>private parenthetical sentinel</PARENTHETICAL>
<TRANSITION>Cut.</TRANSITION>'''
    scene = SimpleNamespace(moment_ids=["BEAT 1"], skeleton=skeleton,
                            scene_template='### SCENE 1 — ROOM\n\n<!-- RESOLVES [BEAT 1] -->\n[INJECT HERE]\n',
                            display_names={'alice': 'Alice', 'bob': 'Bob'})
    script = runtime._render(scene, state)
    assert "sentinel" not in script
    assert "Unperformed prescribed leap" not in script
    for public in ("Room", "Close on the handle", "Blue.", "Low hum.", "Cut."):
        assert public in script


@pytest.fixture
def native_setup(tmp_path, monkeypatch):
    from trigger_workflow_creative_writer import roundtable
    executable = tmp_path / "fake-codex"
    executable.write_bytes((Path(__file__).parent / "fixtures" / "fake_roundtable_codex.py").read_bytes())
    executable.chmod(0o700)
    store = tmp_path / "native-sessions"
    monkeypatch.setenv("CODEX_BIN", str(executable))
    monkeypatch.setenv("FAKE_ROUNDTABLE_STORE", str(store))
    root = tmp_path / "story"
    scene = make_scene(root)
    args = {"repo": "owner/story", "issue": 42, "cwd": root,
            "state_root": tmp_path / "private", "timeout": 5, "model": "fake-model"}
    return roundtable, args, store, scene


def test_fake_native_cli_end_to_end_resumes_private_sessions_and_queued_observations(native_setup):
    runtime, args, store, scene = native_setup
    with pytest.raises(ValueError, match="limit"):
        runtime.perform_scene(**args, max_calls=4)
    _, state = manifest(args)
    result = runtime.perform_scene(**args, run_id=state["run_id"])
    assert result["status"] == "completed"
    records = [json.loads(line) for line in (store / "requests.jsonl").read_text().splitlines()]
    assert len(records) == 9
    initial = {r["request"]["role"]: r["session_id"] for r in records if not r["resume"]}
    assert len(initial) == len(set(initial.values())) == 3
    assert [r["request"]["role"] for r in records[4:]] == ["director", "alice", "director", "bob", "director"]
    for record in records:
        role = record["request"]["role"]
        if record["resume"]:
            assert record["argv"][-2] == initial[role]
        if role != "director":
            sibling = "bob" if role == "alice" else "alice"
            assert sibling + " private sentinel" not in json.dumps(record)
            assert sibling + " inner sentinel" not in json.dumps(record)
            assert "director private sentinel" not in json.dumps(record)
    assert "alice private sentinel" in json.dumps(records[0])
    assert "bob private sentinel" in json.dumps(records[0])
    assert "alice inner sentinel" in json.dumps(records[2])
    assert "bob inner sentinel" in json.dumps(records[4])
    assert len(records[3]["request"]["observations"]) == 3
    assert len(records[7]["request"]["observations"]) == 4
    script = (scene.parent.parent / "script.md").read_text()
    assert "sentinel" not in script
    assert script.count("Tries the handle.") == 2
    assert script.count("deliberate silence") == 2
    assert "I choose to stay." in script


def test_deleted_native_session_pauses_without_replacement(native_setup):
    runtime, args, store, scene = native_setup
    initial_script = (scene.parent.parent / "script.md").read_text()
    with pytest.raises(ValueError, match="limit"):
        runtime.perform_scene(**args, max_calls=2)
    _, state = manifest(args)
    director_id = state["sessions"]["director"]
    (store / f"{director_id}.json").unlink()
    with pytest.raises(SystemExit, match="exit code 9"):
        runtime.perform_scene(**args, run_id=state["run_id"])
    _, paused = manifest(args)
    assert paused["pending"]["session_id"] == director_id
    assert paused["sessions"] == state["sessions"]
    with pytest.raises(ValueError, match="reconcil"):
        runtime.perform_scene(**args, run_id=state["run_id"])
    assert (scene.parent.parent / "script.md").read_text() == initial_script


def test_disabled_provider_rejected_before_creating_private_registry(setup, monkeypatch):
    from trigger_workflow_creative_writer import config
    runtime, args, model, _ = setup
    monkeypatch.setattr(config, "RUNNER_TYPE", "gemini")
    with pytest.raises(SystemExit, match="disabled"):
        runtime.perform_scene(**args)
    assert not args["state_root"].exists()
    assert model.calls == []


def test_intentional_new_run_can_bypass_preserved_partial_initialization(setup):
    runtime, args, _, _ = setup
    with pytest.raises(ValueError, match="limit"):
        runtime.perform_scene(**args, max_calls=1)
    path, state = manifest(args)
    path.unlink()
    snapshots = (path.parent / "snapshots.json").read_bytes()
    with pytest.raises(ValueError, match=state["run_id"]):
        runtime.perform_scene(**args)
    with pytest.raises(ValueError, match="limit"):
        runtime.perform_scene(**args, new_performance=True, max_calls=1)
    assert (path.parent / "snapshots.json").read_bytes() == snapshots


def test_multi_moment_performance_requires_actual_action_in_each_and_preserves_transition_order(setup):
    runtime, args, model, scene = setup
    # Extend the handoff and both canonical skeleton references together.
    skeleton = (scene / "scene_skeleton.md").read_text() + '\n<TRANSITION>Beat one cut.</TRANSITION>\n<!-- RESOLVES [BEAT 2] -->\n<SCENE_HEADING>Hallway</SCENE_HEADING>'
    for path in (args["cwd"] / "skeleton.md", scene / "scene_skeleton.md"):
        path.write_text(skeleton)
    for path in (args["cwd"] / "dramatic_action_brief.md", scene / "dramatic_action_brief.md"):
        text = path.read_text()
        brief = json.loads(text.split("```json\n")[1].split("\n```")[0])
        moment = copy.deepcopy(brief["moments"][0])
        moment["moment_id"] = "BEAT 2"
        brief["moments"].append(moment)
        path.write_text("# Dramatic action brief\n\n```json\n" + json.dumps(brief) + "\n```\n")
    template = scene / "scene_template.md"
    template.write_text(template.read_text() + "\n<!-- RESOLVES [BEAT 2] -->\n[INJECT HERE]\n")
    index = scene / "performance_context.json"
    handoff = json.loads(index.read_text())
    handoff["required_moment_ids"] = ["BEAT 1", "BEAT 2"]
    index.write_text(json.dumps(handoff))
    def mutate(response, request):
        if request["role"] == "director" and request["latest_response"]:
            response["moment_id"] = "BEAT 2"
            response["completed_moment_ids"] = ["BEAT 1", "BEAT 2"] if response["status"] == "complete" else ["BEAT 1"]
    model.mutate = mutate
    result = runtime.perform_scene(**args)
    assert result["performed_moment_ids"] == ["BEAT 1", "BEAT 2"]
    script = (scene.parent.parent / "script.md").read_text()
    assert script.index("Tries the handle.") < script.index("Beat one cut.") < script.index("<!-- RESOLVES [BEAT 2] -->")


def test_legitimate_spanish_todo_is_not_a_placeholder(setup):
    runtime, args, model, scene = setup
    def mutate(response, request):
        if request["role"] != "director":
            response["outer_response"]["dialogue"] = "todo está bien"
    model.mutate = mutate
    runtime.perform_scene(**args)
    assert "todo está bien" in (scene.parent.parent / "script.md").read_text()


@pytest.mark.parametrize("placeholder", ["[TODO]", "[TBD]", "[INJECT HERE]", "TODO", "TBD", "TODO: fill this"])
def test_explicit_placeholder_markers_are_rejected(setup, placeholder):
    runtime, _, _, _ = setup
    with pytest.raises(ValueError, match="placeholder"):
        runtime._public_text(placeholder)


def add_second_scene(root, scene):
    """Create independent preparation with its own skeleton and beat in one episode."""
    import shutil
    second = scene.parent / 'second-room'
    shutil.copytree(scene, second)
    skeleton = (second / 'scene_skeleton.md').read_text().replace('BEAT 1', 'BEAT 2')
    (root / 'second_skeleton.md').write_text(skeleton)
    (second / 'scene_skeleton.md').write_text(skeleton)
    template = (second / 'scene_template.md').read_text().replace('SCENE 1', 'SCENE 2').replace('BEAT 1', 'BEAT 2')
    (second / 'scene_template.md').write_text(template)
    for name in ('performance_context.json', 'dramatic_action_brief.md', 'AGENTS.md'):
        path = second / name
        path.write_text(path.read_text().replace('locked-room', 'second-room').replace('BEAT 1', 'BEAT 2').replace('"skeleton.md"', '"second_skeleton.md"'))
    manuscript = scene.parent.parent / 'script.md'
    with manuscript.open('a') as stream:
        stream.write('\n<!-- SCENE second-room BEGIN -->\n' + template + '<!-- SCENE second-room END -->\n')
    return second


def test_two_scene_performances_preserve_one_episode_and_each_other(setup):
    from trigger_workflow_creative_writer.manuscript import scene_body
    runtime, args, model, first = setup
    second = add_second_scene(args['cwd'], first)
    manuscript = first.parent.parent / 'script.md'
    original = manuscript.read_text()
    first_initial = scene_body(original, 'locked-room')
    second_initial = scene_body(original, 'second-room')
    runtime.perform_scene(**args, scene_path=str(first.relative_to(args['cwd'])))
    after_first = manuscript.read_text()
    first_rendered = scene_body(after_first, 'locked-room')
    assert first_rendered != first_initial
    assert scene_body(after_first, 'second-room') == second_initial
    assert after_first == original.replace(first_initial, first_rendered)
    def second_moment(response, request):
        if request['role'] == 'director':
            response['moment_id'] = 'BEAT 2'
            response['completed_moment_ids'] = ['BEAT 2'] if response['status'] == 'complete' else []
    model.mutate = second_moment
    runtime.perform_scene(**args, scene_path=str(second.relative_to(args['cwd'])))
    final = manuscript.read_text()
    second_rendered = scene_body(final, 'second-room')
    assert second_rendered != second_initial
    assert scene_body(final, 'locked-room') == first_rendered
    assert final == after_first.replace(second_initial, second_rendered)
    assert final.count('<!-- RESOLVES [BEAT 1] -->') == 1
    assert final.count('<!-- RESOLVES [BEAT 2] -->') == 1
    assert 'sentinel' not in final and '[INJECT HERE]' not in final
    assert not (first / 'script.md').exists() and not (second / 'script.md').exists()


def test_episode_crlf_front_matter_and_neighbor_survive_performance(setup):
    from trigger_workflow_creative_writer.manuscript import scene_body
    runtime, args, _, first = setup
    add_second_scene(args['cwd'], first)
    manuscript = first.parent.parent / 'script.md'
    original = manuscript.read_text().replace('\n', '\r\n')
    manuscript.write_bytes(original.encode())
    initial_body = scene_body(original, 'locked-room')
    runtime.perform_scene(**args, scene_path=str(first.relative_to(args['cwd'])))
    final = manuscript.read_bytes().decode()
    assert final == original.replace(initial_body, scene_body(final, 'locked-room'))
