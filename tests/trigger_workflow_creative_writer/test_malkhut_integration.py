"""The phase handler must not deliver until the performance engine accepts completion."""
from types import SimpleNamespace
import json
from pathlib import Path
import subprocess
import shutil

import pytest

from trigger_workflow_creative_writer import config, router
from trigger_workflow_creative_writer.models import PhaseExecutionRequest


def request():
    return PhaseExecutionRequest("phase:malkhut", 42, "owner/story", "Director", "9", {"title": "Story", "body": "", "comments": []})


def test_phase9_missing_materials_never_delivers(tmp_path, monkeypatch):
    from trigger_workflow_creative_writer import runner_utils
    monkeypatch.setattr(runner_utils, "prepare_phase_execution_context", lambda *a, **k: SimpleNamespace(local_path=tmp_path, branch="issue/42"))
    def unexpected(*a, **k):
        pytest.fail("Incomplete performance reached delivery or GitHub handoff")
    monkeypatch.setattr(router, "finalize_delivery", unexpected)
    monkeypatch.setattr(router, "post_phase_machine_comment", unexpected)
    monkeypatch.setattr(router, "advance_issue_label", unexpected)
    with pytest.raises((ValueError, SystemExit)):
        router.execute_malkhut_performance_phase(request())


def test_phase9_disabled_provider_rejected_before_any_checkout_or_handoff(monkeypatch):
    monkeypatch.setattr(config, "RUNNER_TYPE", "gemini")
    monkeypatch.setattr(router, "finalize_delivery", lambda **k: pytest.fail("Delivery attempted"))
    with pytest.raises(SystemExit, match="disabled"):
        router.execute_malkhut_performance_phase(request())


@pytest.fixture
def delivery_boundary(tmp_path, monkeypatch):
    from trigger_workflow_creative_writer import roundtable, runner_utils, scene_materials
    from trigger_workflow_creative_writer.artifact_validation import REQUIRED_ARTIFACTS
    from tests.trigger_workflow_creative_writer.test_roundtable import Model
    from tests.trigger_workflow_creative_writer.test_scene_materials import make_scene

    source = tmp_path / "source"
    (source / ".git").mkdir(parents=True)
    engine = tmp_path / "engine"
    story = engine / ".openhands" / "repos" / "owner__story"
    scene = make_scene(story)
    (story / ".git").mkdir()
    for relative in REQUIRED_ARTIFACTS:
        (story / relative).write_text("Established world material")
    monkeypatch.setitem(runner_utils.TARGET_REPO_CONFIG_MAP, "owner/story",
                        runner_utils.TargetRepoConfig(local_path=source, main_branch="main", issue_branch_prefix="issue/"))
    monkeypatch.setattr(runner_utils, "WORKSPACE", engine)
    monkeypatch.setattr(config, "WORKSPACE", engine)
    for name, value in {"SCENE_PATH": None, "PERFORMANCE_RUN": None, "NEW_PERFORMANCE": False,
                        "CODEX_MODEL": None, "MAX_ROLE_CALLS": 120, "ROLE_TIMEOUT": 1200,
                        "MAX_NO_PROGRESS": 6}.items():
        monkeypatch.setattr(config, name, value)
    model = Model()
    monkeypatch.setattr(roundtable, "call_codex", model)
    monkeypatch.setattr(roundtable, "codex_fingerprint", lambda *a, **k: {"cli": "fake-v1"})
    boundary = SimpleNamespace(story=story, scene=scene, engine=engine, model=model,
                               events=[], merges=0, change=None)

    def process(command, *, cwd, **kwargs):
        operation = " ".join(command[:3]) if command[0] == "gh" else command[1]
        boundary.events.append(operation)
        output = ""
        if operation == "branch":
            output = "issue/42\n"
        elif operation == "merge":
            boundary.merges += 1
            if boundary.change:
                boundary.change(boundary.merges, Path(cwd))
        elif operation == "status":
            output = " M Script/Season_01/Episode_01/script.md\n"
        elif operation == "rev-parse":
            output = "abc123\n"
        elif operation == "ls-remote":
            output = "abc123\trefs/heads/issue/42\n"
        elif operation == "gh pr list":
            output = '[{"number": 42, "title": "Story", "url": "https://github.com/owner/story/pull/42"}]'
        elif operation == "show":
            output = "Script/Season_01/Episode_01/script.md\n"
        elif operation not in {"fetch", "add", "commit", "push"}:
            pytest.fail(f"Unexpected external command: {command}")
        return subprocess.CompletedProcess(command, 0, output, "")

    monkeypatch.setattr(runner_utils.subprocess, "run", process)
    monkeypatch.setattr(router, "post_phase_machine_comment", lambda *a: boundary.events.append("comment"))
    monkeypatch.setattr(router, "advance_issue_label", lambda *a: boundary.events.append("advance"))
    original_load = scene_materials.load_scene
    def checked_scene(*args, **kwargs):
        boundary.events.append("validate-scene")
        return original_load(*args, **kwargs)
    monkeypatch.setattr(scene_materials, "load_scene", checked_scene)
    return boundary


@pytest.mark.parametrize("changed_file", ["continuity.md", "Script/Season_01/Episode_01/script.md"])
@pytest.mark.parametrize("merge_number", [2, 3])
def test_phase9_merge_changes_abort_before_staging_and_leave_delivery_pending(delivery_boundary, changed_file, merge_number):
    boundary = delivery_boundary
    def merge_change(count, checkout):
        if count == merge_number:
            path = checkout / changed_file
            path.write_text(path.read_text() + "\nUpstream changed accepted material")
    boundary.change = merge_change
    with pytest.raises(ValueError, match="fingerprint.*changed|script.*changed|Expected one scene handoff"):
        router.execute_malkhut_performance_phase(request())
    assert boundary.merges == 3
    assert not {"add", "commit", "push", "comment", "advance"}.intersection(boundary.events)
    manifests = list((boundary.engine / "workspace" / "roundtable").glob("*/*/*/manifest.json"))
    assert len(manifests) == 1
    state = json.loads(manifests[0].read_text())
    assert state["delivery"] == "pending"
    assert state["status"] == "completed"


def test_phase9_unchanged_merges_validate_before_staging_then_deliver(delivery_boundary):
    boundary = delivery_boundary
    router.execute_malkhut_performance_phase(request())
    events = boundary.events
    assert boundary.merges == 3
    last_merge = max(i for i, event in enumerate(events) if event == "merge")
    last_validation = max(i for i, event in enumerate(events) if event == "validate-scene")
    assert last_merge < last_validation < events.index("add") < events.index("commit") < events.index("push") < events.index("comment") < events.index("advance")
    manifests = list((boundary.engine / "workspace" / "roundtable").glob("*/*/*/manifest.json"))
    state = json.loads(manifests[0].read_text())
    assert state["delivery"] == "complete"
    assert state["status"] == "delivered"


@pytest.mark.parametrize("change", [None, "source", "script", "scene-id"])
def test_phase9_guard_uses_actual_delivery_checkout_and_scene_identity(delivery_boundary, monkeypatch, change):
    from trigger_workflow_creative_writer import runner_utils
    boundary = delivery_boundary
    other_engine = boundary.engine.parent / "other-engine"
    other_story = other_engine / ".openhands" / "repos" / "owner__story"
    (other_story / ".git").mkdir(parents=True)

    def relocate_after_performance(value, request):
        if value.get("status") == "complete":
            monkeypatch.setattr(runner_utils, "WORKSPACE", other_engine)
    boundary.model.mutate = relocate_after_performance

    def merge_into_actual_checkout(count, checkout):
        if count == 2:
            assert checkout == other_story
            shutil.copytree(boundary.story, checkout, dirs_exist_ok=True)
            if change == "source":
                (checkout / "continuity.md").write_text("Changed in actual delivery checkout")
            elif change == "script":
                path = checkout / "Script/Season_01/Episode_01/script.md"
                path.write_text(path.read_text() + "\nChanged in actual delivery checkout")
            elif change == "scene-id":
                for name in ("performance_context.json", "dramatic_action_brief.md"):
                    path = checkout / "Script/Season_01/Episode_01/scene_materials/locked-room" / name
                    path.write_text(path.read_text().replace("locked-room", "another-scene"))
                scene_dir = checkout / "Script/Season_01/Episode_01/scene_materials/locked-room"
                scene_dir.rename(scene_dir.with_name("another-scene"))
    boundary.change = merge_into_actual_checkout
    if change is None:
        router.execute_malkhut_performance_phase(request())
        assert boundary.events[-2:] == ["comment", "advance"]
    else:
        with pytest.raises(ValueError, match="fingerprint.*changed|script.*changed|Expected one scene handoff"):
            router.execute_malkhut_performance_phase(request())
        assert not {"add", "commit", "push", "comment", "advance"}.intersection(boundary.events)
    assert boundary.merges == 3
