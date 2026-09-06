"""Reject incomplete handoffs before any character session is started."""
import json
import re
from pathlib import Path

import pytest


def make_scene(root: Path, issue=42):
    scene = root / "SEASON_1" / "SHORT_1"
    scene.mkdir(parents=True)
    source_paths = {}
    for role in ("bible", "continuity", "treatment", "constraints"):
        path = root / f"{role}.md"
        path.write_text(f"Established {role}")
        source_paths[role] = [path.name]
    skeleton = '<!-- RESOLVES [BEAT 1] -->\n<SCENE_HEADING>Room</SCENE_HEADING>\n<DIALOGUE character="alice" objective="leave" subtext="fear" tone="low">[INJECT HERE]</DIALOGUE>\n<ACTION focus="bob" intent="wait" />'
    (root / "skeleton.md").write_text(skeleton)
    source_paths["skeleton"] = ["skeleton.md"]
    characters = {}
    for character in ("alice", "bob"):
        persona = root / "agents_artifacts" / "characters" / character / "personality.md"
        persona.parent.mkdir(parents=True)
        persona.write_text(f"Own persona for {character}")
        for filename in ("appearance.md", "interiorvoice.md", "wants.md", "fears.md", "secrets.md", "lexicon.md"):
            (persona.parent / filename).write_text(f"{character} {filename} canon")
        characters[character] = {
            "persona_paths": [str(persona.relative_to(root))],
            "known_context": f"{character} knows the room is locked",
            "private_context": f"{character} private sentinel",
        }
    dramatic = {
        "scene_id": "locked-room", "sources": source_paths,
        "moments": [{"moment_id": "BEAT 1", "required_outcome": "An attempt to leave",
                     "shared_facts": "A locked room", "characters": [
                         {"character_id": c, "stimulus": "Locked door", "knows": "Door locked",
                          "misunderstands": "None established", "does_not_know": "Other's motive",
                          "conceals": "Own motive", "objective": "Leave", "emotion": "Wary",
                          "stakes": "Freedom", "relationships": "Distrust",
                          "possibilities": ["Try the handle", "Wait"], "dependencies": "None"}
                         for c in characters]}],
    }
    brief = "# Dramatic action brief\n\n```json\n" + json.dumps(dramatic) + "\n```\n"
    (root / "dramatic_action_brief.md").write_text(brief)
    (scene / "dramatic_action_brief.md").write_text(brief)
    (scene / "script.md").write_text(skeleton)
    (scene / "scene_skeleton.md").write_text(skeleton)
    (scene / "AGENTS.md").write_text("Context sources: " + json.dumps(source_paths))
    handoff = {"version": 1, "issue": issue, "scene_id": "locked-room",
               "required_moment_ids": ["BEAT 1"], "sources": source_paths,
               "characters": characters}
    (scene / "performance_context.json").write_text(json.dumps(handoff))
    return scene


def test_all_persona_assets_are_loaded_even_if_index_lists_only_one(tmp_path):
    from trigger_workflow_creative_writer.scene_materials import load_scene
    make_scene(tmp_path)
    loaded = load_scene(tmp_path, 42)
    assert "alice secrets.md canon" in loaded.character_contexts["alice"]
    assert "bob secrets.md canon" in loaded.director_context
    assert "bob secrets.md canon" not in loaded.character_contexts["alice"]
    assert "alice wants.md canon" in loaded.character_contexts["alice"]
    assert "alice fears.md canon" in loaded.character_contexts["alice"]
    assert "bob wants.md canon" not in loaded.character_contexts["alice"]
    assert "bob fears.md canon" in loaded.director_context


def test_load_includes_all_director_sources_but_keeps_character_bootstraps_separate(tmp_path):
    from trigger_workflow_creative_writer.scene_materials import load_scene
    scene = make_scene(tmp_path)
    loaded = load_scene(tmp_path, 42)
    assert loaded.directory == scene
    assert "alice private sentinel" in loaded.director_context
    assert "bob private sentinel" in loaded.director_context
    assert "Established continuity" in loaded.director_context
    assert "alice private sentinel" in loaded.character_contexts["alice"]
    assert "bob private sentinel" not in loaded.character_contexts["alice"]
    assert loaded.moment_ids == ["BEAT 1"]
    assert loaded.fingerprint


@pytest.mark.parametrize("mutation", ["missing-source", "escaping-source", "unknown-character", "missing-moment", "changed-skeleton", "missing-brief", "empty-context"])
def test_invalid_handoff_is_rejected(tmp_path, mutation):
    from trigger_workflow_creative_writer.scene_materials import load_scene
    scene = make_scene(tmp_path)
    index = scene / "performance_context.json"
    data = json.loads(index.read_text())
    if mutation == "missing-source":
        (tmp_path / "continuity.md").unlink()
    elif mutation == "escaping-source":
        data["sources"]["bible"] = ["../outside.md"]
    elif mutation == "unknown-character":
        data["characters"]["nobody"] = data["characters"].pop("bob")
    elif mutation == "missing-moment":
        data["required_moment_ids"] = ["BEAT 2"]
    elif mutation == "changed-skeleton":
        (scene / "scene_skeleton.md").write_text("Different scene")
    elif mutation == "missing-brief":
        (scene / "dramatic_action_brief.md").unlink()
    elif mutation == "empty-context":
        data["characters"]["alice"]["private_context"] = ""
    index.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_scene(tmp_path, 42)


def test_phase7_gate_requires_action_options_and_non_speaking_characters(tmp_path):
    from trigger_workflow_creative_writer.scene_materials import validate_phase_artifacts
    make_scene(tmp_path)
    validate_phase_artifacts(tmp_path, "7", 42)
    path = tmp_path / "dramatic_action_brief.md"
    path.write_text(path.read_text().replace('"possibilities": ["Try the handle", "Wait"]', '"possibilities": []'))
    with pytest.raises(ValueError, match="possibilities"):
        validate_phase_artifacts(tmp_path, "7", 42)


def test_phase8_gate_rejects_drafted_script(tmp_path):
    from trigger_workflow_creative_writer.scene_materials import validate_phase_artifacts
    scene = make_scene(tmp_path)
    (scene / "script.md").write_text("A finished draft instead of skeleton")
    with pytest.raises(ValueError, match="skeleton"):
        validate_phase_artifacts(tmp_path, "8", 42)


def test_phase7_does_not_reorder_canonical_moments(tmp_path):
    from trigger_workflow_creative_writer.scene_materials import validate_phase_artifacts
    import re
    make_scene(tmp_path)
    path = tmp_path / "dramatic_action_brief.md"
    data = json.loads(re.search(r"```json\n(.*?)\n```", path.read_text(), re.S)[1])
    second = {**data["moments"][0], "moment_id": "BEAT 2"}
    data["moments"].insert(0, second)
    path.write_text("```json\n" + json.dumps(data) + "\n```\n")
    skeleton = tmp_path / "skeleton.md"
    skeleton.write_text(skeleton.read_text() + "\n<!-- RESOLVES [BEAT 2] -->\n<ACTION focus=\"alice\" />")
    with pytest.raises(ValueError, match="order"):
        validate_phase_artifacts(tmp_path, "7", 42)


def test_mutable_script_cannot_be_indexed_as_immutable_source(tmp_path):
    from trigger_workflow_creative_writer.scene_materials import load_scene
    scene = make_scene(tmp_path)
    index = scene / "performance_context.json"
    data = json.loads(index.read_text())
    data["sources"]["skeleton"] = [str((scene / "script.md").relative_to(tmp_path))]
    index.write_text(json.dumps(data))
    brief = scene / "dramatic_action_brief.md"
    brief.write_text(brief.read_text().replace('"skeleton.md"', json.dumps(data["sources"]["skeleton"][0])))
    anchor = scene / "AGENTS.md"
    anchor.write_text(anchor.read_text().replace('"skeleton.md"', json.dumps(data["sources"]["skeleton"][0])))
    with pytest.raises(ValueError, match="mutable script"):
        load_scene(tmp_path, 42)


def test_phase8_rejects_matching_copies_that_change_source_whitespace(tmp_path):
    from trigger_workflow_creative_writer.scene_materials import validate_phase_artifacts
    scene = make_scene(tmp_path)
    for name in ("script.md", "scene_skeleton.md"):
        path = scene / name
        path.write_text(path.read_text() + "\n")
    with pytest.raises(ValueError, match="differs from phase 6"):
        validate_phase_artifacts(tmp_path, "8", 42)


@pytest.mark.parametrize("field,value,issue", [("version", True, 42), ("version", 1.0, 42),
                                               ("issue", True, 1), ("issue", 42.0, 42)])
def test_handoff_identifiers_require_json_integers(tmp_path, field, value, issue):
    from trigger_workflow_creative_writer.scene_materials import load_scene
    scene = make_scene(tmp_path, issue=issue)
    path = scene / "performance_context.json"
    data = json.loads(path.read_text())
    data[field] = value
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_scene(tmp_path, issue)


@pytest.mark.parametrize("quote", ['"', "'"])
def test_participant_must_be_in_the_corresponding_moment(tmp_path, quote):
    from trigger_workflow_creative_writer.scene_materials import read_brief
    make_scene(tmp_path)
    path = tmp_path / "dramatic_action_brief.md"
    data = json.loads(re.search(r"```json\n(.*?)\n```", path.read_text(), re.S)[1])
    first = data["moments"][0]
    bob = first["characters"].pop()
    data["moments"].append({**first, "moment_id": "BEAT 2", "characters": [bob]})
    path.write_text("```json\n" + json.dumps(data) + "\n```\n")
    skeleton = tmp_path / "skeleton.md"
    skeleton.write_text(skeleton.read_text().replace('"', quote) + "\n<!-- RESOLVES [BEAT 2] -->\n<ACTION focus='bob' />")
    with pytest.raises(ValueError, match="BEAT 1.*bob"):
        read_brief(tmp_path)
