"""Public play-script rendering; private role fields never enter this projection."""
from __future__ import annotations

import html
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .scene_materials import SceneMaterials

_MARKER = re.compile(r'<!--\s*RESOLVES\s*\[(BEAT\s+[^\]]+)\]\s*-->')
_INLINE = re.compile(r'\*\(([^\n]*?)\)\*')
_SCENE_TEMPLATE_HEADING = re.compile(r'^###[ \t]+SCENE[ \t]+([0-9]+)[ \t]+—[ \t]+([^\r\n]+)\r?$')
_INTERNAL_SKELETON_TAG = re.compile(
    r'</?(?:SCENE_HEADING|DIALOGUE|ACTION|PARENTHETICAL|CAMERA|LIGHTING|AUDIO|TRANSITION)(?=[\s/>])', re.I)
_CANONICAL_TEMPLATE_PLACEHOLDER = re.compile(r'''\[\s*(?:
    INJECT\s+HERE|TODO|TBD|PLAY\s+TITLE|PLAYWRIGHT\s+NAME|CONTACT\s+NAME|
    EMAIL\s+ADDRESS|ADDITIONAL\s+CONTACT\s+INFORMATION|CHARACTER\s+NAME|
    AGE\s+DESCRIPTION|GENDER,\s+AS\s+ESTABLISHED|RELEVANT\s+TRAITS|
    WHERE\s+THE\s+PLAY\s+TAKES\s+PLACE\.|WHEN\s+THE\s+PLAY\s+TAKES\s+PLACE\.|
    NUMBER|SCENE\s+TITLE|SETTING\s+AT\s+THE\s+OPENING\s+OF\s+THE\s+SCENE\.|BEAT\s+ID|
    STAGE\s+DIRECTION:\s+ACTION\s+OR\s+MOVEMENT\.|DIALOGUE\s+IN\s+NORMAL\s+SENTENCE\s+CASE\.|
    DIALOGUE\s+BEFORE\s+AN\s+INLINE\s+DIRECTION\.|BRIEF\s+ACTION\s+OR\s+EMOTIONAL\s+CUE\.|
    DIALOGUE\s+CONTINUES\.|STAGE\s+DIRECTION\s+BETWEEN\s+SPEECHES\.|DIALOGUE[^\]]*|
    STAGE\s+DIRECTION[^\]]*|BRIEF\s+ACTION[^\]]*
)\s*\]''', re.I | re.X)
_PUBLIC_PROPERTIES = {
    'CAMERA': {'shot', 'movement', 'target'},
    'LIGHTING': {'mood', 'source'},
    'AUDIO': {'mood', 'source'},
    'TRANSITION': {'type'},
    'SCENE_HEADING': {'location', 'time'},
}


def normalize_scene_heading(heading: str) -> str:
    """Validate one template heading and return its safe Markdown normalization."""
    match = _SCENE_TEMPLATE_HEADING.fullmatch(heading)
    if not match or match[2] != match[2].upper():
        raise ValueError('scene template requires an uppercase Markdown scene heading')
    return f'### SCENE {match[1]} — {match[2]}'


def validate_public_text(text: str) -> None:
    """Reject reserved structural markers and known unfilled template vessels."""
    if re.search(r'<!--\s*(?:SCENE\b|RESOLVES\b)', text, re.I):
        raise ValueError('Reserved scene/beat marker in public performance')
    if (_CANONICAL_TEMPLATE_PLACEHOLDER.search(text)
            or re.search(r'^\s*(?:TODO|TBD)(?:\s*:.*)?\s*$', text, re.M)):
        raise ValueError('Unresolved placeholder in public performance')
    if _INTERNAL_SKELETON_TAG.search(text):
        raise ValueError('Internal skeleton tag in public performance')


def _plain(text: str) -> str:
    validate_public_text(text)
    # Collapse newlines so a model response remains one Markdown paragraph.
    text = ' '.join(text.splitlines()).strip()
    if re.fullmatch(r'-+|=+', text):
        return '\\' + text
    text = html.escape(text, quote=False)
    text = re.sub(r'([\\`*_{}\[\]#!|~])', r'\\\1', text)
    return re.sub(r'^(\d{1,9})([.)])(?=\s)|^([-+])(?=\s)',
                  lambda m: (m[1] + '\\' + m[2]) if m[1] else '\\' + m[3], text)


def _dialogue(text: str) -> str:
    pieces = []
    start = 0
    validate_public_text(text)
    for match in _INLINE.finditer(text):
        # Preserve spacing surrounding an inline direction, but escape its body.
        pieces.append(_plain(text[start:match.start()]))
        if match.start() > start and text[match.start() - 1].isspace():
            pieces.append(' ')
        pieces.append('*(' + _plain(match[1]) + ')*')
        if match.end() < len(text) and text[match.end()].isspace():
            pieces.append(' ')
        start = match.end()
    pieces.append(_plain(text[start:]))
    return ''.join(pieces)


def _direction(text: str) -> str:
    return '> *(' + _plain(text) + ')*'


def _fixed_constraints(skeleton: str) -> tuple[list[str], dict[str, list[str]], dict[str, list[str]]]:
    # Remove private vessels before looking for public tags, including nested text.
    skeleton = re.sub(r'<(DIALOGUE|ACTION|PARENTHETICAL)\b[^>]*(?:/\s*>|>.*?</\1\s*>)',
                      '', skeleton, flags=re.I | re.S)
    public_tags = '|'.join(_PUBLIC_PROPERTIES)
    token = re.compile(_MARKER.pattern + rf'|<({public_tags})\b([^>]*?)(?:/\s*>|>(.*?)</\2\s*>)', re.I | re.S)
    opening, per_moment, transitions = [], {}, {}
    moment = None
    for match in token.finditer(skeleton):
        if match[1] is not None:
            moment = match[1]
            continue
        tag, attributes, content = match[2].upper(), match[3], match[4] or ''
        values = [f'{name}: {html.unescape(value)}' for name, _, value in
                  re.findall(r'''([\w]+)\s*=\s*(["'])(.*?)\2''', attributes, re.S)
                  if name.lower() in _PUBLIC_PROPERTIES[tag]]
        if content.strip():
            values.append(html.unescape(re.sub(r'<[^>]*>', '', content).strip()))
        if not values:
            continue
        text = '; '.join(values)
        # Preserve internal setting changes as directions; the template owns
        # the single public Markdown scene heading.
        if tag != 'SCENE_HEADING':
            text = f'{tag}: {text}'
        destination = opening if moment is None else (transitions if tag == 'TRANSITION' else per_moment).setdefault(moment, [])
        destination.append(_direction(text))
    return opening, per_moment, transitions


def render_scene(scene: SceneMaterials, state: dict) -> str:
    """Return only the selected Markdown scene body with ordered canonical beats."""
    if (state['status'] not in {'completed', 'delivered'}
            or set(state['completed_moment_ids']) != set(scene.moment_ids)
            or set(state['performed_moment_ids']) != set(scene.moment_ids)):
        raise ValueError('Scene is incomplete: explicit completion and actual moment performance required')
    parts = _MARKER.split(scene.scene_template)
    opening = parts[0].strip()
    heading = re.match(r'[^\r\n]*', opening)[0]
    opening = normalize_scene_heading(heading) + opening[len(heading):]
    validate_public_text(opening)
    cues, per_moment, transitions = _fixed_constraints(scene.skeleton)
    lines = [opening, *cues]
    events = {mid: [] for mid in scene.moment_ids}
    previous_index = -1
    for event in state['public_events']:
        mid = event['moment_id']
        if mid not in events or scene.moment_ids.index(mid) < previous_index:
            raise ValueError('Public events must follow canonical moment order')
        previous_index = scene.moment_ids.index(mid)
        events[mid].append(event)
    for mid in scene.moment_ids:
        lines.append(f'<!-- RESOLVES [{mid}] -->')
        lines.extend(per_moment.get(mid, []))
        for event in events[mid]:
            if event['kind'] == 'stage':
                lines.append(_direction(event['text']))
                continue
            name = scene.display_names[event['character_id']].upper()
            outer = event['outer_response']
            if outer['action'].strip():
                lines.append(_direction(f'{name}: {outer["action"]}'))
            if outer['dialogue'].strip():
                lines.append(f'**{_plain(name)}**  \n{_dialogue(outer["dialogue"])}')
            if outer['silence']:
                lines.append(_direction(f'{name}: deliberate silence.'))
        lines.extend(transitions.get(mid, []))
    return '\n\n'.join(lines).strip() + '\n'
