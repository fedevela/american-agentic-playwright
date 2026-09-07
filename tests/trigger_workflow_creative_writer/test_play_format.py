"""Public Markdown contains only performed speech/action and fixed directions."""
from types import SimpleNamespace
import pytest
from trigger_workflow_creative_writer import play_format


def performance(dialogue='He said "wait" — ¿por qué? *(softly)* 我在这里。', action='Opens the door.', silence=False):
    scene = SimpleNamespace(
        scene_template='### SCENE 1 — THE ROOM\n\n> *(A locked room.)*\n\n<!-- RESOLVES [BEAT 1] -->\n[INJECT HERE]\n\n<!-- RESOLVES [BEAT 2] -->\n[INJECT HERE]\n',
        moment_ids=['BEAT 1', 'BEAT 2'], display_names={'alice': 'Alice Doe', 'bob': 'Bob'},
        skeleton='''<SCENE_HEADING>THE ROOM</SCENE_HEADING>
<!-- RESOLVES [BEAT 1] -->
<CAMERA>Close on the door.</CAMERA><LIGHTING>Blue.</LIGHTING><AUDIO>Wind.</AUDIO>
<DIALOGUE character="alice" objective="private objective sentinel" subtext="private subtext sentinel">[INJECT HERE]</DIALOGUE>
<ACTION focus="alice">Unperformed leap.</ACTION>
<PARENTHETICAL>private parenthetical sentinel</PARENTHETICAL>
<TRANSITION>Cut.</TRANSITION>
<!-- RESOLVES [BEAT 2] -->
<AUDIO>Birdsong.</AUDIO>''')
    state = dict(status='completed', completed_moment_ids=scene.moment_ids, performed_moment_ids=scene.moment_ids,
                 inner_monologue='private inner sentinel', private_direction='private direction sentinel',
                 public_events=[
                     dict(kind='stage', moment_id='BEAT 1', text='The lock clicks.'),
                     dict(kind='character', moment_id='BEAT 1', character_id='alice',
                          outer_response=dict(dialogue=dialogue, action=action, silence=silence)),
                     dict(kind='character', moment_id='BEAT 2', character_id='bob',
                          outer_response=dict(dialogue='', action='', silence=True))])
    return scene, state


def test_requested_markdown_play_format_and_private_exclusion():
    scene, state = performance()
    result = play_format.render_scene(scene, state)
    assert result.startswith('### SCENE 1 — THE ROOM\n\n> *(A locked room.)*\n')
    assert '**ALICE DOE**  \nHe said "wait" — ¿por qué? *(softly)* 我在这里。' in result
    assert '> *(ALICE DOE: Opens the door.)*' in result
    assert '> *(The lock clicks.)*' in result
    assert '> *(BOB: deliberate silence.)*' in result
    assert 'sentinel' not in result and 'Unperformed leap' not in result
    assert '[INJECT HERE]' not in result and '<DIALOGUE' not in result
    assert '<SCENE_HEADING' not in result and '<CAMERA' not in result
    assert '“' not in result
    for marker in scene.moment_ids:
        assert result.count(f'<!-- RESOLVES [{marker}] -->') == 1
    assert result.index('BEAT 1') < result.index('CAMERA: Close') < result.index('Opens the door')
    assert result.index('Opens the door') < result.index('Cut.') < result.index('BEAT 2') < result.index('AUDIO: Birdsong')


def test_renderer_rejects_neutral_template_heading_and_opening_placeholders():
    scene, state = performance()
    scene.scene_template = ('### SCENE 1 — [SCENE TITLE]\n\n'
                            '> *([Setting at the opening of the scene.])*\n\n'
                            '<!-- RESOLVES [BEAT 1] -->\n[INJECT HERE]\n\n'
                            '<!-- RESOLVES [BEAT 2] -->\n[INJECT HERE]\n')
    opening = scene.scene_template.split('<!-- RESOLVES', 1)[0]
    with pytest.raises(ValueError, match='placeholder'):
        play_format.validate_public_text(opening)
    with pytest.raises(ValueError, match='placeholder'):
        play_format.render_scene(scene, state)


def test_renderer_rejects_an_unresolved_opening_placeholder():
    scene, state = performance()
    scene.scene_template = scene.scene_template.replace('\n<!-- RESOLVES', '\n\nTODO: describe the opening\n<!-- RESOLVES', 1)
    with pytest.raises(ValueError, match='placeholder'):
        play_format.render_scene(scene, state)


@pytest.mark.parametrize('placeholder', [
    '[PLAY TITLE]', '[Playwright name]', '[Contact name]', '[Email address]',
    '[Additional contact information]', '[Age description]', '[gender, as established]',
    '[relevant traits]', '[Where the play takes place.]', '[When the play takes place.]',
    '[NUMBER]', '[BEAT ID]', '[Setting at the opening of the scene.]',
])
def test_known_neutral_manuscript_placeholders_cannot_be_public(placeholder):
    with pytest.raises(ValueError, match='placeholder'):
        play_format.validate_public_text(placeholder)


@pytest.mark.parametrize('placeholder', [
    '[Dialogue unfinished line.]', '[Stage direction: a generic movement.]',
    '[Brief action under pressure.]',
])
def test_known_dialogue_and_action_placeholder_variants_cannot_be_public(placeholder):
    with pytest.raises(ValueError, match='placeholder'):
        play_format.validate_public_text(placeholder)


def test_renderer_normalizes_a_valid_tab_separated_scene_heading():
    scene, state = performance()
    scene.scene_template = scene.scene_template.replace('### SCENE 1 — THE ROOM', '###\tSCENE  \t1\t— \tTHE ROOM')
    assert play_format.render_scene(scene, state).startswith('### SCENE 1 — THE ROOM\n')


@pytest.mark.parametrize('text', ['<!-- SCENE evil BEGIN -->', '<!-- RESOLVES [BEAT 99] -->', '[INJECT HERE]', '[TODO]', 'TODO: draft', '[Dialogue in normal sentence case.]', '[CHARACTER NAME]'])
def test_reserved_markers_and_placeholders_cannot_become_public(text):
    scene, state = performance(dialogue=text)
    with pytest.raises(ValueError):
        play_format.render_scene(scene, state)


def test_structural_markdown_and_html_are_escaped():
    scene, state = performance(dialogue='# heading\n<script>alert(1)</script> [link](https://example.org) **bold** & _text_ `code`', action='> quote\n## heading')
    scene.display_names['alice'] = '[Alice](url)<script>'
    result = play_format.render_scene(scene, state)
    assert '<script>' not in result and '</script>' not in result
    assert '\n# heading' not in result and '\n## heading' not in result
    assert '&lt;script&gt;' in result and '\\[link\\]' in result
    assert '\\*\\*bold\\*\\*' in result and '&amp;' in result


def test_generic_html_that_only_shares_a_skeleton_tag_prefix_is_escaped():
    scene, state = performance(dialogue='<audio-file>recording</audio-file>')
    assert '&lt;audio-file&gt;recording&lt;/audio-file&gt;' in play_format.render_scene(scene, state)


def test_inline_parentheses_are_preserved_without_allowing_nested_markup():
    scene, state = performance(dialogue='(Really?) *(moves <b>closer</b>)* "yes"')
    result = play_format.render_scene(scene, state)
    assert '(Really?) *(moves &lt;b&gt;closer&lt;/b&gt;)* "yes"' in result


def test_silence_never_fabricates_speech():
    scene, state = performance(dialogue='', action='', silence=True)
    result = play_format.render_scene(scene, state)
    assert '> *(ALICE DOE: deliberate silence.)*' in result
    assert '**ALICE DOE**' not in result


def test_incomplete_performance_is_rejected():
    scene, state = performance()
    state['performed_moment_ids'] = ['BEAT 1']
    with pytest.raises(ValueError, match='incomplete'):
        play_format.render_scene(scene, state)


def test_attributed_production_constraints_retain_only_public_properties():
    scene, state = performance()
    scene.skeleton = scene.skeleton.replace('<CAMERA>Close on the door.</CAMERA>', '<CAMERA shot="close-up" movement="still" target="door" objective="private sentinel" />')
    result = play_format.render_scene(scene, state)
    assert 'CAMERA: shot: close-up; movement: still; target: door' in result
    assert 'sentinel' not in result


def test_events_cannot_regress_or_invent_moments():
    scene, state = performance()
    state['public_events'].append(state['public_events'][0])
    with pytest.raises(ValueError, match='order'):
        play_format.render_scene(scene, state)


@pytest.mark.parametrize('dialogue,escaped', [('- list', '\\- list'), ('+ list', '\\+ list'), ('1. list', '1\\. list'), ('2) list', '2\\) list')])
def test_dialogue_cannot_start_markdown_list(dialogue, escaped):
    scene, state = performance(dialogue=dialogue)
    assert '**ALICE DOE**  \n' + escaped in play_format.render_scene(scene, state)


def test_later_skeleton_setting_is_retained_in_its_moment():
    scene, state = performance()
    scene.skeleton += '\n<SCENE_HEADING>Hallway</SCENE_HEADING>'
    result = play_format.render_scene(scene, state)
    assert result.index('BEAT 2') < result.index('> *(Hallway)*')


@pytest.mark.parametrize('dialogue', ['---', '===', '- - -', '--'])
def test_dialogue_cannot_turn_speaker_cue_into_setext_heading(dialogue):
    scene, state = performance(dialogue=dialogue)
    result = play_format.render_scene(scene, state)
    assert '**ALICE DOE**  \n' + dialogue not in result
    assert '**ALICE DOE**  \n\\' + dialogue in result
