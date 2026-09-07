"""Reject incomplete handoffs before any character session is started."""
import json
import re
from pathlib import Path

import pytest


def make_scene(root: Path, issue=42):
    episode = root / "Script" / "Season_01" / "Episode_01"
    scene = episode / "scene_materials" / "locked-room"
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
        persona = root / "bible" / "characters" / character / "objective.md"
        persona.parent.mkdir(parents=True)
        for filename in (
            "objective.md",
            "hidden_objective.md",
            "conflict_with_others.md",
            "conflict_with_self.md",
            "conflict_with_environment.md",
            "line_of_thought.md",
            "line_of_images.md",
        ):
            (persona.parent / filename).write_text(f"{character} {filename} canon")
        characters[character] = {
            "persona_paths": [str(persona.relative_to(root))],
            "known_context": f"{character} knows the room is locked",
            "private_context": f"{character} private sentinel",
            "scene_context": f"{character} arrived to retrieve a coat",
            "moment_contexts": {"BEAT 1": f"{character} hears the door lock"},
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
    (scene / "scene_skeleton.md").write_text(skeleton)
    template = ('### SCENE 1 — ROOM\n\n'
                '<!-- RESOLVES [BEAT 1] -->\n'
                '[INJECT HERE]\n')
    (scene / "scene_template.md").write_text(template)
    (episode / "script.md").write_text(
        '# Locked Room\n\nPlaywright\n\n## ACT I\n\n'
        '<!-- SCENE locked-room BEGIN -->\n' + template +
        '<!-- SCENE locked-room END -->\n'
    )
    (scene / "AGENTS.md").write_text("Context sources: " + json.dumps(source_paths))
    handoff = {"version": 3, "issue": issue, "scene_id": "locked-room",
               "manuscript_path": "Script/Season_01/Episode_01/script.md",
               "required_moment_ids": ["BEAT 1"], "sources": source_paths,
               "actor_safe_bible_paths": [],
               "characters": characters}
    for cid, character in handoff["characters"].items():
        character["display_name"] = cid.title()
    (scene / "performance_context.json").write_text(json.dumps(handoff))
    return scene


def test_all_persona_assets_are_loaded_even_if_index_lists_only_one(tmp_path):
    from trigger_workflow_creative_writer.scene_materials import load_scene
    make_scene(tmp_path)
    loaded = load_scene(tmp_path, 42)
    for filename in (
        "objective.md",
        "hidden_objective.md",
        "conflict_with_others.md",
        "conflict_with_self.md",
        "conflict_with_environment.md",
        "line_of_thought.md",
        "line_of_images.md",
    ):
        assert f"alice {filename} canon" in loaded.character_contexts["alice"]
        assert f"bob {filename} canon" in loaded.director_context
        assert f"bob {filename} canon" not in loaded.character_contexts["alice"]


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
    assert loaded.manuscript_path == scene.parent.parent / "script.md"
    assert loaded.scene_template.startswith("### SCENE 1")
    assert loaded.display_names == {"alice": "Alice", "bob": "Bob"}
    assert loaded.fingerprint


@pytest.mark.parametrize("mutation", ["missing-source", "escaping-source", "unknown-character", "missing-moment", "changed-skeleton", "missing-brief", "empty-context", "multiline-display-name"])
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
    elif mutation == "multiline-display-name":
        data["characters"]["alice"]["display_name"] = "Alice\u2028Alias"
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


def test_phase8_gate_rejects_performed_scene_before_roundtable(tmp_path):
    from trigger_workflow_creative_writer.scene_materials import validate_phase_artifacts
    scene = make_scene(tmp_path)
    manuscript = scene.parent.parent / "script.md"
    manuscript.write_text(manuscript.read_text().replace("[INJECT HERE]", "A finished draft."))
    with pytest.raises(ValueError, match="scene template"):
        validate_phase_artifacts(tmp_path, "8", 42)


def test_load_allows_a_performed_scene_after_phase8_has_completed(tmp_path):
    from trigger_workflow_creative_writer.scene_materials import load_scene
    scene = make_scene(tmp_path)
    manuscript = scene.parent.parent / "script.md"
    manuscript.write_text(manuscript.read_text().replace("[INJECT HERE]", "A finished draft."))
    assert load_scene(tmp_path, 42).scene_template.endswith("[INJECT HERE]\n")


@pytest.mark.parametrize("path", [
    "/tmp/elsewhere/script.md",
    "Script/Season_01/Episode_02/script.md",
    "Script/Season_01/Episode_01/scene_materials/locked-room/script.md",
])
def test_handoff_manuscript_must_be_the_own_episode_script(tmp_path, path):
    from trigger_workflow_creative_writer.scene_materials import load_scene
    scene = make_scene(tmp_path)
    index = scene / "performance_context.json"
    data = json.loads(index.read_text())
    data["manuscript_path"] = path
    index.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="manuscript"):
        load_scene(tmp_path, 42)


@pytest.mark.parametrize("mutation", [
    lambda text: "---\ntitle: wrong\n---\n" + text,
    lambda text: text.replace("### SCENE", "## ACT I\n\n### SCENE"),
    lambda text: "<!-- SCENE extra BEGIN -->\n" + text + "<!-- SCENE extra END -->\n",
    lambda text: text.replace("[INJECT HERE]", '<DIALOGUE character="alice">[INJECT HERE]</DIALOGUE>'),
    lambda text: text.replace("BEAT 1", "BEAT 2"),
    lambda text: text.replace("ROOM", "Room"),
    lambda text: text.replace("[INJECT HERE]", "<script>unsafe</script>"),
    lambda text: text.replace("\n\n<!-- RESOLVES", "\n\n[INJECT HERE]\n\n<!-- RESOLVES"),
    lambda text: text.replace("<!-- RESOLVES [BEAT 1] -->", "```markdown\n<!-- RESOLVES [BEAT 1] -->\n```"),
])
def test_public_scene_template_rejects_nonpublic_or_mismatched_structure(tmp_path, mutation):
    from trigger_workflow_creative_writer.scene_materials import load_scene
    scene = make_scene(tmp_path)
    template = scene / "scene_template.md"
    template.write_text(mutation(template.read_text()))
    with pytest.raises(ValueError):
        load_scene(tmp_path, 42)


def test_load_scene_rejects_neutral_heading_and_opening_placeholders(tmp_path):
    from trigger_workflow_creative_writer.scene_materials import load_scene
    scene = make_scene(tmp_path)
    template = scene / "scene_template.md"
    template.write_text('### SCENE 1 — [SCENE TITLE]\n\n'
                        '> *([Setting at the opening of the scene.])*\n\n'
                        '<!-- RESOLVES [BEAT 1] -->\n[INJECT HERE]\n')
    with pytest.raises(ValueError, match="placeholder"):
        load_scene(tmp_path, 42)


@pytest.mark.parametrize("version", [1, 2])
def test_legacy_handoff_explains_required_migration(tmp_path, version):
    from trigger_workflow_creative_writer.scene_materials import load_scene
    scene = make_scene(tmp_path)
    index = scene / "performance_context.json"
    data = json.loads(index.read_text())
    data["version"] = version
    index.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="version 3.*migration"):
        load_scene(tmp_path, 42)


def test_discovery_ignores_the_neutral_season_template_even_when_selected(tmp_path):
    from trigger_workflow_creative_writer.scene_materials import load_scene
    template_scene = tmp_path / "Script" / "season_template" / "Season_N" / "Episode_N" / "scene_materials" / "locked-room"
    template_scene.mkdir(parents=True)
    (template_scene / "performance_context.json").write_text(json.dumps({"issue": 42}))
    make_scene(tmp_path)
    loaded = load_scene(tmp_path, 42)
    assert "season_template" not in str(loaded.directory)
    with pytest.raises(ValueError, match="season_template"):
        load_scene(tmp_path, 42, str(template_scene.relative_to(tmp_path)))


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
    data["sources"]["skeleton"] = [str((scene.parent.parent / "script.md").relative_to(tmp_path))]
    index.write_text(json.dumps(data))
    brief = scene / "dramatic_action_brief.md"
    brief.write_text(brief.read_text().replace('"skeleton.md"', json.dumps(data["sources"]["skeleton"][0])))
    anchor = scene / "AGENTS.md"
    anchor.write_text(anchor.read_text().replace('"skeleton.md"', json.dumps(data["sources"]["skeleton"][0])))
    with pytest.raises(ValueError, match="mutable script"):
        load_scene(tmp_path, 42)


def test_phase8_rejects_preserved_skeleton_that_changes_source_whitespace(tmp_path):
    from trigger_workflow_creative_writer.scene_materials import validate_phase_artifacts
    scene = make_scene(tmp_path)
    path = scene / "scene_skeleton.md"
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


@pytest.mark.parametrize('extra', ['`<!-- RESOLVES [BEAT 99] -->`\n', '```markdown\n<!-- RESOLVES [BEAT 99] -->\n```\n', '<!-- resolves [BEAT 99] -->\n'])
def test_template_cannot_hide_extra_marker_from_public_renderer(tmp_path, extra):
    from trigger_workflow_creative_writer.scene_materials import load_scene
    scene = make_scene(tmp_path)
    template = scene / 'scene_template.md'
    template.write_text(template.read_text().replace('\n\n', '\n\n' + extra, 1))
    with pytest.raises(ValueError, match='marker'):
        load_scene(tmp_path, 42)


@pytest.mark.parametrize('name', ['Alice\n', 'Alice\r', 'Alice\r\n', 'Alice\u2028'])
def test_display_name_rejects_trailing_line_break(tmp_path, name):
    from trigger_workflow_creative_writer.scene_materials import load_scene
    scene = make_scene(tmp_path)
    index = scene / 'performance_context.json'
    data = json.loads(index.read_text())
    data['characters']['alice']['display_name'] = name
    index.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='single-line'):
        load_scene(tmp_path, 42)


def test_phase8_rejects_line_ending_changes_to_preserved_skeleton(tmp_path):
    from trigger_workflow_creative_writer.scene_materials import validate_phase_artifacts
    make_scene(tmp_path)
    source = tmp_path / 'skeleton.md'
    source.write_bytes(source.read_bytes().replace(b'\n', b'\r\n'))
    with pytest.raises(ValueError, match='differs from phase 6'):
        validate_phase_artifacts(tmp_path, '8', 42)


def test_phase8_rejects_line_ending_changes_to_copied_brief(tmp_path):
    from trigger_workflow_creative_writer.scene_materials import validate_phase_artifacts
    make_scene(tmp_path)
    source = tmp_path / 'dramatic_action_brief.md'
    source.write_bytes(source.read_bytes().replace(b'\n', b'\r\n'))
    with pytest.raises(ValueError, match='brief unchanged'):
        validate_phase_artifacts(tmp_path, '8', 42)


def test_phase8_accepts_exact_crlf_template_and_region(tmp_path):
    from trigger_workflow_creative_writer.scene_materials import validate_phase_artifacts
    scene = make_scene(tmp_path)
    for path in (scene / 'scene_template.md', scene.parent.parent / 'script.md'):
        path.write_bytes(path.read_bytes().replace(b'\n', b'\r\n'))
    validate_phase_artifacts(tmp_path, '8', 42)


def test_episode_preparation_must_be_under_script(tmp_path):
    from trigger_workflow_creative_writer.scene_materials import load_scene
    make_scene(tmp_path)
    (tmp_path / 'Script').rename(tmp_path / 'misc')
    index = tmp_path / 'misc/Season_01/Episode_01/scene_materials/locked-room/performance_context.json'
    index.write_text(index.read_text().replace('Script/', 'misc/'))
    with pytest.raises(ValueError, match='Script'):
        load_scene(tmp_path, 42)


def test_existing_other_episode_cannot_be_the_manuscript_destination(tmp_path):
    from trigger_workflow_creative_writer.scene_materials import load_scene
    scene = make_scene(tmp_path)
    other = scene.parent.parent.parent / 'Episode_02/script.md'
    other.parent.mkdir()
    other.write_bytes((scene.parent.parent / 'script.md').read_bytes())
    index = scene / 'performance_context.json'
    data = json.loads(index.read_text())
    data['manuscript_path'] = str(other.relative_to(tmp_path))
    index.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="this episode's script"):
        load_scene(tmp_path, 42)


def test_manuscript_symlink_cannot_escape_story_checkout(tmp_path):
    from trigger_workflow_creative_writer.scene_materials import load_scene
    root = tmp_path / 'story'
    scene = make_scene(root)
    manuscript = scene.parent.parent / 'script.md'
    outside = tmp_path / 'script.md'
    manuscript.rename(outside)
    manuscript.symlink_to(outside)
    with pytest.raises(ValueError, match='inside story checkout'):
        load_scene(root, 42)


def test_handoff_persona_cannot_read_a_sibling_character(tmp_path):
    from trigger_workflow_creative_writer.scene_materials import load_scene
    scene = make_scene(tmp_path)
    index = scene / 'performance_context.json'
    data = json.loads(index.read_text())
    data['characters']['alice']['persona_paths'] = ['bible/characters/bob/hidden_objective.md']
    index.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='another character'):
        load_scene(tmp_path, 42)


def test_actor_bootstrap_has_only_nominated_bible_and_surrounding_context(tmp_path):
    from trigger_workflow_creative_writer.scene_materials import load_scene
    scene = make_scene(tmp_path)
    safe = tmp_path / "bible/public_world.md"
    safe.write_text("The city closes its gates at dusk.")
    (tmp_path / "bible/plot.md").write_text("FUTURE SECRET")
    index = scene / "performance_context.json"
    data = json.loads(index.read_text())
    data["actor_safe_bible_paths"] = ["bible/public_world.md"]
    index.write_text(json.dumps(data))
    loaded = load_scene(tmp_path, 42)
    actor = json.loads(loaded.character_contexts["alice"])
    assert actor["issue"] == 42
    assert actor["scene_id"] == "locked-room"
    assert actor["manuscript_path"] == data["manuscript_path"]
    assert actor["scene_context"] == "alice arrived to retrieve a coat"
    assert actor["actor_safe_bible"] == {"bible/public_world.md": safe.read_text()}
    assert "alice hears the door lock" not in loaded.character_contexts["alice"]
    assert "Established continuity" not in loaded.character_contexts["alice"]
    assert "FUTURE SECRET" not in loaded.character_contexts["alice"]
    assert loaded.character_moment_contexts["alice"] == {"BEAT 1": "alice hears the door lock"}
    assert loaded.character_directories["alice"] == tmp_path / "bible/characters/alice"
    assert loaded.snapshots["bible/public_world.md"] == safe.read_text()
    safe.write_text("The city gates now remain open.")
    assert load_scene(tmp_path, 42).fingerprint != loaded.fingerprint


@pytest.mark.parametrize("field,value", [
    ("scene_context", ""), ("scene_context", None),
    ("moment_contexts", {}), ("moment_contexts", {"BEAT 1": ""}),
    ("moment_contexts", {"BEAT 1": "Current", "BEAT 2": "Unexpected"}),
    ("moment_contexts", ["Current"]),
])
def test_actor_facing_context_requires_scene_and_exact_moment_coverage(tmp_path, field, value):
    from trigger_workflow_creative_writer.scene_materials import load_scene
    scene = make_scene(tmp_path)
    index = scene / "performance_context.json"
    data = json.loads(index.read_text())
    data["characters"]["alice"][field] = value
    index.write_text(json.dumps(data))
    with pytest.raises(ValueError, match=field):
        load_scene(tmp_path, 42)


@pytest.mark.parametrize("paths", [None, "bible/public.md", [None],
    ["continuity.md"], ["bible/characters/bob/hidden_objective.md"]])
def test_actor_safe_bible_requires_explicit_noncharacter_bible_paths(tmp_path, paths):
    from trigger_workflow_creative_writer.scene_materials import load_scene
    scene = make_scene(tmp_path)
    index = scene / "performance_context.json"
    data = json.loads(index.read_text())
    data["actor_safe_bible_paths"] = paths
    index.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_scene(tmp_path, 42)


@pytest.mark.parametrize("target", ["continuity.md", "bible/characters/bob/hidden_objective.md"])
def test_actor_safe_bible_rejects_symlink_to_unapproved_location(tmp_path, target):
    from trigger_workflow_creative_writer.scene_materials import load_scene
    scene = make_scene(tmp_path)
    (tmp_path / "bible/public.md").symlink_to(tmp_path / target)
    index = scene / "performance_context.json"
    data = json.loads(index.read_text())
    data["actor_safe_bible_paths"] = ["bible/public.md"]
    index.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="actor_safe_bible"):
        load_scene(tmp_path, 42)


@pytest.mark.parametrize("destination", ["bible/characters/bob", "elsewhere"])
def test_character_directory_cannot_alias_other_context(tmp_path, destination):
    from trigger_workflow_creative_writer.scene_materials import load_scene
    make_scene(tmp_path)
    own = tmp_path / "bible/characters/alice"
    own.rename(tmp_path / "alice-original")
    target = tmp_path / destination
    if destination == "elsewhere":
        (tmp_path / "alice-original").rename(target)
    own.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="character directory"):
        load_scene(tmp_path, 42)


def test_future_beat_context_stays_out_of_every_actor_bootstrap(tmp_path):
    from trigger_workflow_creative_writer.scene_materials import load_scene
    scene = make_scene(tmp_path)
    index = scene / "performance_context.json"
    data = json.loads(index.read_text())
    data["required_moment_ids"].append("BEAT 2")
    for cid, character in data["characters"].items():
        character["moment_contexts"]["BEAT 2"] = f"{cid} future situation sentinel"
    index.write_text(json.dumps(data))
    brief_path = scene / "dramatic_action_brief.md"
    brief = json.loads(re.search(r"```json\n(.*?)\n```", brief_path.read_text(), re.S)[1])
    brief["moments"].append({**brief["moments"][0], "moment_id": "BEAT 2"})
    brief_path.write_text("```json\n" + json.dumps(brief) + "\n```\n")
    for path in (tmp_path / "skeleton.md", scene / "scene_skeleton.md"):
        path.write_text(path.read_text() + "\n<!-- RESOLVES [BEAT 2] -->\n<ACTION focus='alice' />")
    template = scene / "scene_template.md"
    template.write_text(template.read_text() + "\n<!-- RESOLVES [BEAT 2] -->\n[INJECT HERE]\n")
    loaded = load_scene(tmp_path, 42)
    assert list(loaded.character_moment_contexts["alice"]) == ["BEAT 1", "BEAT 2"]
    assert loaded.character_moment_contexts["alice"]["BEAT 2"] == "alice future situation sentinel"
    assert all("future situation sentinel" not in context for context in loaded.character_contexts.values())
    assert "alice future situation sentinel" in loaded.director_context
    previous = loaded.fingerprint
    data["characters"]["alice"]["moment_contexts"]["BEAT 2"] = "A changed future situation"
    index.write_text(json.dumps(data))
    assert load_scene(tmp_path, 42).fingerprint != previous


@pytest.mark.parametrize("missing", ["actor_safe_bible_paths", "scene_context", "moment_contexts"])
def test_actor_context_fields_cannot_be_implicitly_defaulted(tmp_path, missing):
    from trigger_workflow_creative_writer.scene_materials import load_scene
    scene = make_scene(tmp_path)
    index = scene / "performance_context.json"
    data = json.loads(index.read_text())
    container = data if missing == "actor_safe_bible_paths" else data["characters"]["alice"]
    del container[missing]
    index.write_text(json.dumps(data))
    with pytest.raises(ValueError, match=missing):
        load_scene(tmp_path, 42)
