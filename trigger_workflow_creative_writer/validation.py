"""Dramatic source coverage and readiness, independent of narrative wording."""
from __future__ import annotations

from copy import deepcopy
import json
import re
from typing import Any

SCOPES = {'season', 'episode', 'act', 'scene', 'undetermined'}
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
    require(set(value) <= allowed,
            f'{name} contains unknown source references: {sorted(set(value) - allowed)}; '
            f'allowed anchor IDs: {sorted(allowed)}')
    return set(value)


def validate_element(element: dict, anchor_ids: set[str], *, reconcile_scene_refs: bool = False) -> None:
    require(isinstance(element, dict), 'element must be an object')
    require(isinstance(element.get('scope'), str) and element['scope'] in GENERATED_SCOPES, 'generated scope must be episode, act, scene, or undetermined; seasons are human-created')
    text(element.get('title'), 'element title')
    text(element.get('content'), 'element content')
    context = f'element {element["title"]!r}'
    assigned = references(element.get('source_refs'), anchor_ids, context)
    require(isinstance(element.get('readiness'), str) and element['readiness'] in {'ready','develop'}, 'element readiness must be ready or develop')
    require(isinstance(element.get('outline', ''), str), 'outline must be text')
    require(isinstance(element.get('beats', []), list), 'beats must be an ordered list')
    if reconcile_scene_refs and element['scope'] == 'scene':
        # Preserve declared assignments and append valid beat sources in first-use order.
        # validate_result works on a deep copy, keeping the original response intact.
        additions = []
        for number, beat in enumerate(element.get('beats', []), 1):
            beat_context = f'{context}, beat {number}'
            require(isinstance(beat, dict), f'{beat_context} must be an object')
            references(beat.get('source_refs'), anchor_ids, beat_context)
            for ref in beat['source_refs']:
                if ref not in assigned:
                    additions.append(ref)
                    assigned.add(ref)
        element['source_refs'].extend(additions)
    if element['readiness'] == 'develop':
        text(element.get('development_question'), f'{context}, readiness=develop: development_question')
        text(element.get('return_reason'), f'{context}, readiness=develop: return_reason')
        placement = element.get('placement')
        require(placement is None or (isinstance(placement, dict) and all(isinstance(placement.get(k), str) and placement[k].strip() for k in ('episode','act','scene_id'))), 'development placement must be null or explicit episode/act/scene identity')
        for number, beat in enumerate(element.get('beats', []), 1):
            require(isinstance(beat, dict), 'beat must be an object')
            text(beat.get('content'), 'beat content')
            references(beat.get('source_refs'), assigned, f'{context}, beat {number}')
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
    for number, beat in enumerate(beats, 1):
        require(isinstance(beat, dict), 'beat must be an object')
        text(beat.get('content'), 'beat content')
        covered |= references(beat.get('source_refs'), assigned, f'{context}, beat {number}')
    require(covered == assigned,
            f'{context}: missing beat coverage of assigned dramatic anchors: {sorted(assigned - covered)}')


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
        text(result.get('development_question'), 'top-level outcome=develop: development_question')
        text(result.get('return_reason'), 'top-level outcome=develop: return_reason')
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
            require(isinstance(item.get('scope'), str) and item['scope'] in GENERATED_SCOPES, 'artifact scope must be episode, act, scene, or undetermined; seasons are human-created')
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
            validate_element(element, pool, reconcile_scene_refs=True)
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
              'outcome':'complete | develop | question | failure', 'narrative':'concise phase-domain summary',
              'questions':[], 'canon_refs':['relevant canon paths; preserve inherited references'],
              'development_question':'specific question for the whole work when outcome=develop; otherwise empty',
              'return_reason':'reason the whole work needs a new Keter cycle when outcome=develop; otherwise empty'}
    if phase == '1':
        common.update(reference_prefix={'code':'2–12 uppercase letters chosen meaningfully for this specific project',
                                        'meaning':'neutral description of what those letters refer to'},
                      axes={axis:'precise dramatic axis' for axis in AXES},
                      anchors=[{'content':'dramatic anchor','source_refs':['source_material.anchors IDs (including development.sources); empty only when no inherited/developed sources']}])
    elif phase in {'2A','2B','2C'}:
        common['narrative'] = 'one short orienting sentence'
        common['artifacts'] = [{'scope':'episode | act | scene | undetermined', 'content':'one short sentence on one line per item: a premise-level idea in this phase’s domain',
                                'source_refs':['accepted Keter anchor IDs']}]
    elif phase == '3':
        common['outcome'] = ('complete for an established synthesis, including a mixture of ready and develop elements | '
                             'develop to return the whole work to Keter | question | failure')
        common.update(anchors=[{'content':'synthesized anchor and relationships','source_refs':['current exploration artifact IDs']}],
            elements=[{'title':'dramatic element', 'scope':'episode | act | scene | undetermined', 'readiness':'ready | develop',
                       'source_refs':['IDs of this result\'s anchors: <cycle_id>:3:a1, a2, ...; include every anchor used by this element\'s beats'],
                       'content':'dramatic purpose: a milestone, circumstance, or change and its relationships','outline':'established scene outline, or prior work',
                       'development_question':'specific question for this element when readiness=develop; empty when readiness=ready',
                       'return_reason':'reason this element needs exploration when readiness=develop; empty when readiness=ready',
                       'placement':{'episode':'Script/Season_01/Episode_01','act':'1','scene_id':'safe-scene-id'},
                       'beats':[{'content':'ordered dramatic purpose and situation; expression belongs to the character','source_refs':['anchor IDs declared in this parent element\'s source_refs; cover every declared anchor across a ready scene\'s beats']}]}])
    elif phase == '4':
        common['assignments'] = [{'element_id':'accepted element ID, in accepted order','outline':'concrete scene outline; preserve prior work for develop'}]
    return ('Return one JSON object, no fences. Python assigns IDs and renders public headings, size labels, ancestry and source lines.\n'
            + json.dumps(common, ensure_ascii=False, indent=2)
            + '\nKeter chooses the reference prefix from the specific project and describes its meaning neutrally; it is a reference label, not a slogan or dramatic interpretation. Reuse an established project prefix when appropriate. Other phases inherit it from accepted Keter; do not choose or override it. Keep internal IDs out of narrative prose. '
            'The output schema defines the required fields. For question, supply questions and pause. '
            'For outcomes question, failure, or develop, represent unused phase-specific arrays as [], nullable objects as null, and unused text as an empty string. '
            'For failure, describe the execution failure in narrative. '
            'For top-level outcome=develop, supply top-level development_question and return_reason alongside outcome; this returns the whole current work to a new Keter cycle. '
            'Unresolved human choices require question, never complete or develop. Complete requires all phase-specific fields and no questions. '
            'Every accepted source must be accounted for; combine/divide via source_refs without losing ancestry. '
            'Only scenes with episode/act/scene placement, established outline and ordered beats covering every assigned anchor may be ready. '
            'Develop elements require a specific question and reason; placement may be null and beats empty. '
            'Let dramatic purpose establish an element and exploration discover its form. '
            'Use undetermined (scope to be discovered) while form remains open, with readiness=develop, '
            'a specific development_question and return_reason. Preserve prior outlines and beat ideas; placement may be null. '
            'Keep the owning issue scope unchanged throughout its cycle; later synthesis establishes child scopes. '
            'Season scope is human-created only; generated artifacts/elements use episode, act, scene or undetermined. '
            'Tiferet preserves accepted organization; structural problems use develop or question instead of rewriting it.')
