"""Episode replacements preserve every byte outside the selected scene body."""
import pytest
from trigger_workflow_creative_writer import manuscript


EPISODE = ('# Title\n\nPlaywright\n\n## ACT I\n\n'
           '<!-- SCENE first BEGIN -->\n### SCENE 1 — Room\n\n<!-- RESOLVES [BEAT 1] -->\nFirst.\n<!-- SCENE first END -->\n\n'
           '<!-- SCENE second BEGIN -->\n### SCENE 2 — Garden\n\n<!-- RESOLVES [BEAT 2] -->\nSecond.\n<!-- SCENE second END -->\n')


@pytest.mark.parametrize('scene_id', ['first', 'second'])
def test_replace_only_selected_scene_body(scene_id):
    body = ('### SCENE 1 — Room\n\n<!-- RESOLVES [BEAT 1] -->\nFirst.\n' if scene_id == 'first'
            else '### SCENE 2 — Garden\n\n<!-- RESOLVES [BEAT 2] -->\nSecond.\n')
    rendered = '### SCENE 9 — Performed\n\nA performance.\n'
    assert manuscript.replace_scene(EPISODE, scene_id, rendered) == EPISODE.replace(body, rendered)
    assert manuscript.scene_body(EPISODE, scene_id) == body


@pytest.mark.parametrize('text,target', [
    (EPISODE, 'absent'),
    (EPISODE + EPISODE, 'first'),
    ('<!-- SCENE first BEGIN -->\nNo end\n', 'first'),
    ('<!-- SCENE first END -->\n', 'first'),
    ('<!-- SCENE first BEGIN -->\n<!-- SCENE second BEGIN -->\n<!-- SCENE second END -->\n<!-- SCENE first END -->\n', 'first'),
    ('<!-- SCENE first BEGIN -->\n<!-- SCENE second END -->\n', 'first'),
    (EPISODE, '../first'),
])
def test_ambiguous_or_invalid_boundaries_rejected(text, target):
    with pytest.raises(ValueError):
        manuscript.replace_scene(text, target, 'New.\n')


@pytest.mark.parametrize('fence', ['```', '~~~~'])
def test_fenced_examples_do_not_define_boundaries(fence):
    example = f'{fence}markdown\n{EPISODE}{fence}\n'
    text = example + EPISODE
    assert manuscript.replace_scene(text, 'first', 'New.\n').startswith(example)
    with pytest.raises(ValueError):
        manuscript.scene_body(example, 'first')


def test_inline_marker_examples_do_not_define_boundaries():
    text = '`<!-- SCENE first BEGIN -->`\n' + EPISODE
    assert manuscript.scene_body(text, 'first').startswith('### SCENE 1')


def test_crlf_outside_region_preserved():
    text = EPISODE.replace('\n', '\r\n')
    body = '### SCENE 2 — Garden\r\n\r\n<!-- RESOLVES [BEAT 2] -->\r\nSecond.\r\n'
    assert manuscript.replace_scene(text, 'second', 'New.\n') == text.replace(body, 'New.\n')


@pytest.mark.parametrize('rendered', ['<!-- SCENE injected BEGIN -->\n', 'text\n<!-- SCENE first END -->\n'])
def test_replacement_cannot_inject_boundaries(rendered):
    with pytest.raises(ValueError):
        manuscript.replace_scene(EPISODE, 'first', rendered)
