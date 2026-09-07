"""Dramatic source coverage and readiness, independent of narrative wording."""
from __future__ import annotations

from copy import deepcopy
import json
import re
from typing import Any

SCOPES = {'season', 'episode', 'act', 'scene'}
GENERATED_SCOPES = SCOPES - {'season'}
AXES = ('pursuit', 'opposition', 'pressure', 'change', 'dramatic_question')


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f'Creative contract: {message}')


def text(value: Any, name: str) -> str:
    require(isinstance(value, str) and bool(value.strip()), f'{name} must be nonempty text')
    return value


def references(value: Any, allowed: set[str], name: str, *, empty: bool = False) -> set[str]:
    require(isinstance(value, list) and all(isinstance(v, str) for v in value), f'{name} must be source references')
    require(len(value) == len(set(value)), f'{name} has duplicate source references')
    require(empty or bool(value), f'{name} needs source references')
    require(set(value) <= allowed, f'{name} contains unknown source references: {set(value) - allowed}')
    return set(value)


def validate_element(element: dict, anchor_ids: set[str]) -> None:
    require(isinstance(element, dict), 'element must be an object')
    require(isinstance(element.get('scope'), str) and element['scope'] in GENERATED_SCOPES, 'generated scope must be episode, act, or scene; seasons are human-created')
    text(element.get('title'), 'element title')
    text(element.get('content'), 'element content')
    assigned = references(element.get('source_refs'), anchor_ids, 'element')
    require(isinstance(element.get('readiness'), str) and element['readiness'] in {'ready','develop'}, 'element readiness must be ready or develop')
    require(isinstance(element.get('outline', ''), str), 'outline must be text')
    require(isinstance(element.get('beats', []), list), 'beats must be an ordered list')
    if element['readiness'] == 'develop':
        text(element.get('development_question'), 'development question')
        text(element.get('return_reason'), 'return reason')
        placement = element.get('placement')
        require(placement is None or (isinstance(placement, dict) and all(isinstance(placement.get(k), str) and placement[k].strip() for k in ('episode','act','scene_id'))), 'development placement must be null or explicit episode/act/scene identity')
        for beat in element.get('beats', []):
            require(isinstance(beat, dict), 'beat must be an object')
            text(beat.get('content'), 'beat content')
            references(beat.get('source_refs'), assigned, 'beat')
        return
    require(element['scope'] == 'scene', 'only a scene can be ready')
    require(not element.get('development_question') and not element.get('return_reason'), 'ready scene cannot have unresolved development questions')
    text(element.get('outline'), 'ready scene outline')
    placement = element.get('placement')
    require(isinstance(placement, dict), 'ready scene needs episode ownership and act placement')
    require(bool(re.fullmatch(r'Script/Season_\d+/Episode_\d+', str(placement.get('episode', '')))), 'episode must name Script/Season_<digits>/Episode_<digits>')
    text(placement.get('act'), 'act placement')
    require(bool(re.fullmatch(r'[A-Za-z0-9_-]+', str(placement.get('scene_id', '')))), 'scene identity must be a safe scene ID')
    beats = element.get('beats')
    require(isinstance(beats, list) and bool(beats), 'ready scene requires ordered nonempty beats')
    covered = set()
    for beat in beats:
        require(isinstance(beat, dict), 'beat must be an object')
        text(beat.get('content'), 'beat content')
        covered |= references(beat.get('source_refs'), assigned, 'beat')
    require(covered == assigned, 'missing beat coverage of assigned dramatic anchors')


def validate_reference_prefix(prefix: Any) -> None:
    require(isinstance(prefix, dict) and set(prefix) == {'code', 'meaning'},
            'reference prefix requires code and meaning')
    require(isinstance(prefix['code'], str) and bool(re.fullmatch(r'[A-Z]{2,12}', prefix['code'])),
            'reference prefix code must contain 2–12 uppercase letters')
    meaning = text(prefix['meaning'], 'reference prefix meaning')
    require(len(meaning) <= 160 and not any(c in meaning for c in '\r\n<>'),
            'reference prefix meaning must be a short, neutral single-line description')


def validate_result(payload: dict, *, phase: str, cycle_id: str, scope: str,
                    accepted: dict, inherited: list | None = None) -> dict:
    """Validate model data, assign stable identifiers, and materialize Tiferet outlines."""
    require(isinstance(payload, dict), 'result must be an object')
    result = deepcopy(payload)
    require(result.get('cycle_id') == cycle_id, 'result belongs to another cycle')
    require(isinstance(scope, str) and scope in SCOPES and result.get('scope') == scope, 'result scope must match current issue')
    require(isinstance(result.get('outcome'), str) and result['outcome'] in {'complete','develop','question','failure'}, 'unknown structured outcome')
    text(result.get('narrative'), 'narrative')
    questions = result.get('questions')
    require(isinstance(questions, list) and all(isinstance(q, str) and q.strip() for q in questions), 'questions must be a list of nonempty text')
    canon = result.get('canon_refs')
    require(isinstance(canon, list) and all(isinstance(c, str) and c.strip() for c in canon), 'canon_refs must be a list of references')
    source_phases = {'1': (), '2A': ('1',), '2B': ('1',), '2C': ('1',), '3': ('1','2A','2B','2C'), '4': ('3',)}.get(phase, ())
    inherited_canon = {c for p in source_phases for c in accepted.get(p, {}).get('canon_refs', [])}
    require(inherited_canon <= set(canon), 'established canon references must be preserved')
    # Old durable results remain revalidatable; only new complete Keter output
    # must establish the project reference vocabulary.
    if phase == '1':
        prefix = result.get('reference_prefix')
        legacy = payload.get('kind') == 'result' and payload.get('version') == 1
        if prefix is not None or (result['outcome'] == 'complete' and not legacy):
            validate_reference_prefix(prefix)
    else:
        result.pop('reference_prefix', None)
        if accepted.get('1', {}).get('reference_prefix') is not None:
            prefix = accepted['1']['reference_prefix']
            validate_reference_prefix(prefix)
            result['reference_prefix'] = deepcopy(prefix)
    result.update(kind='result', version=1, phase=phase)
    if result['outcome'] == 'question':
        require(bool(questions), 'question outcome requires questions for the partner')
        return result
    require(not questions, 'pending questions must use the question outcome')
    if result['outcome'] == 'failure':
        return result
    if result['outcome'] == 'develop':
        text(result.get('development_question'), 'development question')
        text(result.get('return_reason'), 'return reason')
        return result
    inherited = inherited or []
    if phase == '1':
        axes = result.get('axes')
        require(isinstance(axes, dict) and set(axes) == set(AXES), 'Keter requires the five dramaturgical axes')
        for axis in AXES:
            text(axes.get(axis), axis)
        pool = {a['id'] for a in inherited}
        items = result.get('anchors')
    elif phase in {'2A','2B','2C'}:
        require('1' in accepted, 'current accepted Keter brief is required; restart through Keter')
        pool = {a['id'] for a in accepted['1']['anchors']}
        items = result.get('artifacts')
    elif phase == '3':
        require(all(p in accepted for p in ('2A','2B','2C')), 'all three current explorations are required')
        pool = {a['id'] for p in ('2A','2B','2C') for a in accepted[p]['artifacts']}
        items = result.get('anchors')
    elif phase == '4':
        require('3' in accepted, 'accepted current Gevurah organization is required')
        organization = accepted['3']
        assignments = result.get('assignments')
        require(isinstance(assignments, list), 'Tiferet requires assignments')
        expected = [e['id'] for e in organization['elements']]
        require(all(isinstance(a,dict) for a in assignments), 'assignments must be objects')
        require([a.get('element_id') for a in assignments] == expected, 'assignments must preserve every accepted element in order')
        result['anchors'] = deepcopy(organization['anchors'])
        result['elements'] = deepcopy(organization['elements'])
        for assignment, element in zip(assignments, result['elements']):
            require(set(assignment) == {'element_id','outline'}, 'Tiferet may only establish the outline; structural changes return for development')
            if element['readiness'] == 'ready':
                element['outline'] = text(assignment.get('outline'), 'scene outline')
            else:
                require(assignment.get('outline') == element.get('outline',''), 'development assignments preserve prior work')
        return result
    else:
        raise SystemExit(f'Unknown creative phase {phase}')
    require(isinstance(items, list) and bool(items), 'nonempty dramatic material is required')
    covered = set()
    for index, item in enumerate(items, 1):
        require(isinstance(item, dict), 'dramatic material must be an object')
        text(item.get('content'), 'dramatic content')
        if phase in {'2A','2B','2C'}:
            require(isinstance(item.get('scope'), str) and item['scope'] in GENERATED_SCOPES, 'artifact scope must be episode, act, or scene; seasons are human-created')
        covered |= references(item.get('source_refs'), pool, 'dramatic material', empty=not pool)
        item['id'] = f'{cycle_id}:{phase}:a{index}'
    require(covered == pool, 'missing source coverage of accepted current-cycle material')
    if phase == '3':
        elements = result.get('elements')
        require(isinstance(elements, list) and bool(elements), 'Gevurah requires organized elements')
        pool = {a['id'] for a in items}
        covered = set()
        locations = set()
        for index, element in enumerate(elements, 1):
            validate_element(element, pool)
            covered.update(element['source_refs'])
            element['id'] = f'{cycle_id}:e{index}'
            for number, beat in enumerate(element.get('beats') or [], 1):
                beat['id'] = f'{element["id"]}:b{number}'
            if element['readiness'] == 'ready':
                location = (element['placement']['episode'],element['placement']['scene_id'])
                require(location not in locations, 'duplicate scene placement')
                locations.add(location)
        require(covered == pool, 'missing element coverage of dramatic anchors')
    return result


def validate_tiferet_specification_payload_structure(payload: dict[str, Any]) -> None:
    """Reject legacy decomposition; callers must validate against the accepted synthesis."""
    require(payload.get('kind') == 'result' and payload.get('phase') == '4' and payload.get('elements'),
            'legacy work must be re-established through Keter before decomposition')
    pool = {a['id'] for a in payload.get('anchors', [])}
    for element in payload['elements']:
        validate_element(element, pool)


def result_contract(phase: str) -> str:
    common = {'cycle_id':'copy current cycle_id','scope':'copy current issue scope',
              'outcome':'complete | develop | question | failure', 'narrative':'dramatic prose',
              'questions':[], 'canon_refs':['relevant canon paths; preserve inherited references']}
    if phase == '1':
        common.update(reference_prefix={'code':'2–12 uppercase letters chosen meaningfully for this specific project',
                                        'meaning':'neutral description of what those letters refer to'},
                      axes={axis:'precise dramatic axis' for axis in AXES},
                      anchors=[{'content':'dramatic anchor','source_refs':['source_material.anchors IDs (including development.sources); empty only when no inherited/developed sources']}])
    elif phase in {'2A','2B','2C'}:
        common['artifacts'] = [{'scope':'episode | act | scene', 'content':'independent lyrical possibility with scenes and internal beats',
                                'source_refs':['accepted Keter anchor IDs']}]
    elif phase == '3':
        common.update(anchors=[{'content':'synthesized anchor and relationships','source_refs':['current exploration artifact IDs']}],
            elements=[{'title':'dramatic element', 'scope':'episode | act | scene', 'readiness':'ready | develop',
                       'source_refs':['IDs of this result\'s anchors: <cycle_id>:3:a1, a2, ...'],
                       'content':'dramatic action and relationships','outline':'established scene outline, or prior work',
                       'development_question':'required for develop, empty for ready', 'return_reason':'required for develop, empty for ready',
                       'placement':{'episode':'Script/Season_01/Episode_01','act':'1','scene_id':'safe-scene-id'},
                       'beats':[{'content':'ordered action','source_refs':['assigned anchor IDs']}]}])
    elif phase == '4':
        common['assignments'] = [{'element_id':'accepted element ID, in accepted order','outline':'concrete scene outline; preserve prior work for develop'}]
    return ('Return one JSON object, no fences. Python assigns IDs and renders public headings, size labels, ancestry and source lines.\n'
            + json.dumps(common, ensure_ascii=False, indent=2)
            + '\nKeter chooses the reference prefix from the specific project and describes its meaning neutrally; it is a reference label, not a slogan or dramatic interpretation. Reuse an established project prefix when appropriate. Other phases inherit it from accepted Keter; do not choose or override it. Keep internal IDs out of narrative prose. '
            'For question, supply questions and pause; omit phase-specific fields. For failure, describe the execution failure in narrative. '
            'For develop, supply development_question and return_reason; this returns current work to a new Keter cycle. '
            'Unresolved human choices require question, never complete or develop. Complete requires all phase-specific fields and no questions. '
            'Every accepted source must be accounted for; combine/divide via source_refs without losing ancestry. '
            'Only scenes with episode/act/scene placement, established outline and ordered beats covering every assigned anchor may be ready. '
            'Develop elements require a specific question and reason; placement may be null and beats empty. '
            'Season scope is human-created only; generated artifacts/elements use episode, act or scene. '
            'Tiferet preserves accepted organization; structural problems use develop or question instead of rewriting it.')
