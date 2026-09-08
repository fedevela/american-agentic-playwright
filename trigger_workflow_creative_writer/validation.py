"""Pivotal beat continuity and readiness, independent of narrative wording."""
from __future__ import annotations

from copy import deepcopy
import json
import re
from typing import Any

SCOPES = {'season', 'episode', 'act', 'scene', 'undetermined'}
GENERATED_SCOPES = SCOPES - {'season'}
AXES = ('pursuit', 'opposition', 'pressure', 'change', 'dramatic_question')


GEVURAH_SYNTHESIS_RULE = (
    'Incoming hypotheses are source material, not a mandatory list of final pivots. '
    'When several hypotheses become one element, synthesize one consequential event with a new '
    'BEAT-G ID and source_beat_ids naming every hypothesis it combines. '
    'Keep only the resulting pivots in anchors[].pivotal_beats; merged predecessors belong '
    'in ancestry, not as additional unassigned pivots. Explain the dramatic choice in the anchor. '
    'Supporting actions have is_pivotal=false and pivotal_beat_id=null. '
    'Every final pivot must be selected by an element, including developing elements; '
    'every incoming identity must still be retained or covered by successor ancestry. '
    'Do not add scenes merely to satisfy a count, or silently drop hypotheses.'
)


class SynthesisCoverageError(SystemExit):
    """A complete synthesis needs a model-authored correction before publication."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f'Creative contract: {message}')


def text(value: Any, name: str) -> str:
    require(isinstance(value, str) and bool(value.strip()), f'{name} must be nonempty text')
    return value


def references(value: Any, allowed: set[str], name: str, *, empty: bool = False) -> set[str]:
    require(isinstance(value, list) and all(isinstance(v, str) for v in value), f'{name} must be BEAT references')
    require(empty or bool(value), f'{name} needs BEAT references')
    require(set(value) <= allowed,
            f'{name} contains unknown BEAT references: {sorted(set(value) - allowed)}; '
            f'allowed BEAT IDs: {sorted(allowed)}')
    return set(value)


def validate_element(element: dict, *, require_pivotal: bool = False) -> None:
    require(isinstance(element, dict), 'element must be an object')
    require(isinstance(element.get('scope'), str) and element['scope'] in GENERATED_SCOPES, 'generated scope must be episode, act, scene, or undetermined; season scope belongs to the existing project root')
    text(element.get('title'), 'element title')
    text(element.get('content'), 'element content')
    context = f'element {element["title"]!r}'
    require(isinstance(element.get('readiness'), str) and element['readiness'] in {'ready','develop'}, 'element readiness must be ready or develop')
    require(isinstance(element.get('outline', ''), str), 'outline must be text')
    require(isinstance(element.get('beats', []), list), 'beats must be an ordered list')
    beats = element.get('beats', [])
    # Legacy elements without markers retain their original shape. Once present,
    # markers must be complete and identify exactly one pivotal beat.
    if require_pivotal or any(isinstance(beat, dict) and 'is_pivotal' in beat for beat in beats):
        require(all(isinstance(beat, dict) and type(beat.get('is_pivotal')) is bool for beat in beats),
                f'{context}: every beat requires boolean is_pivotal')
        require(sum(beat['is_pivotal'] for beat in beats) == 1,
                f'{context}: exactly one pivotal beat is required')
    if element['readiness'] == 'develop':
        text(element.get('development_question'), f'{context}, readiness=develop: development_question')
        text(element.get('return_reason'), f'{context}, readiness=develop: return_reason')
        placement = element.get('placement')
        require(placement is None or (isinstance(placement, dict) and all(isinstance(placement.get(k), str) and placement[k].strip() for k in ('episode','act','scene_id'))), 'development placement must be null or explicit episode/act/scene identity')
        for number, beat in enumerate(element.get('beats', []), 1):
            require(isinstance(beat, dict), 'beat must be an object')
            text(beat.get('content'), 'beat content')
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
    for number, beat in enumerate(beats, 1):
        require(isinstance(beat, dict), 'beat must be an object')
        text(beat.get('content'), 'beat content')


def validate_reference_prefix(prefix: Any) -> None:
    require(isinstance(prefix, dict) and set(prefix) == {'code', 'meaning'},
            'reference prefix requires code and meaning')
    require(isinstance(prefix['code'], str) and bool(re.fullmatch(r'[A-Z]{2,12}', prefix['code'])),
            'reference prefix code must contain 2–12 uppercase letters')
    meaning = text(prefix['meaning'], 'reference prefix meaning')
    require(len(meaning) <= 160 and not any(c in meaning for c in '\r\n<>'),
            'reference prefix meaning must be a short, neutral single-line description')


def validate_pivotal_identities(items: list, sources: list, *, cycle_id: str, phase: str,
                               source_aliases: dict | None = None) -> None:
    """Keep beat identity separate from phase-local material and scene-beat IDs."""
    from .beat_ids import PHASE_LETTERS, legacy_readable_id, source_names
    known = {beat['id'] for source in sources for beat in source.get('pivotal_beats', [])}
    lineage = known | {ref for source in sources for beat in source.get('pivotal_beats', [])
                       for ref in beat.get('source_beat_ids', [])}
    candidates = {}
    for identifier in lineage:
        for alias in source_names(identifier):
            candidates.setdefault(alias, set()).add(identifier)
    # Published beat headings show BEAT-K1 while their link targets carry
    # the full identity. Accept that visible spelling as a source reference,
    # without making it a new beat identity or guessing between source cycles.
    reference_candidates = {alias: set(ids) for alias, ids in candidates.items()}
    for identifier in lineage:
        alias = legacy_readable_id(identifier)
        if alias:
            display = alias.rsplit('-', 2)[0]
            reference_candidates.setdefault(display, set()).add(identifier)
    # Explicit published link labels take precedence over inferred shorthand.
    # Retain every target so a label used differently in two source comments
    # is rejected instead of being resolved by accident.
    for alias, identifiers in (source_aliases or {}).items():
        if alias.startswith('BEAT-'):
            reference_candidates[alias] = set(identifiers)
    emitted = set()
    for item in items:
        beats = item.get('pivotal_beats')
        require(isinstance(beats, list) and bool(beats), 'every dramatic artifact requires pivotal_beats')
        for beat in beats:
            require(isinstance(beat, dict), 'pivotal beat must be an object')
            emitted.add(text(beat.get('id'), 'pivotal beat identity'))

    def original(identifier):
        if identifier in lineage or identifier not in reference_candidates:
            return identifier
        require(len(reference_candidates[identifier]) == 1,
                f'ambiguous readable pivotal identity {identifier}; use the exact source ID')
        return next(iter(reference_candidates[identifier]))

    migrations = {identifier: original(identifier) for identifier in emitted
                  if identifier not in known and identifier in candidates}
    require(all(old in known for old in migrations.values()),
            'new pivotal identity cannot reuse an ancestor name')
    require(len(set(migrations.values())) == len(migrations),
            'one source beat cannot acquire two different readable names in one result')
    require(not (set(migrations.values()) & emitted),
            'one result cannot publish both cycle-qualified and readable names for the same pivotal beat')
    allowed = lineage | set(migrations)
    ancestry = {}
    for source in sources:
        for beat in source.get('pivotal_beats', []):
            ancestry.setdefault(beat['id'], set()).update(beat.get('source_beat_ids', []))
    for identifier, old in migrations.items():
        ancestry[identifier] = ancestry[old] | {old}

    def ancestors(parents):
        expanded = set(parents)
        pending = list(parents)
        while pending:
            for predecessor in ancestry.get(pending.pop(), ()):
                if predecessor not in expanded:
                    expanded.add(predecessor)
                    pending.append(predecessor)
        return expanded

    accounted = set()
    definitions = {}
    for item in items:
        beats = item.get('pivotal_beats')
        require(isinstance(beats, list) and bool(beats), 'every dramatic artifact requires pivotal_beats')
        local_ids = set()
        for beat in beats:
            require(isinstance(beat, dict), 'pivotal beat must be an object')
            identifier = text(beat.get('id'), 'pivotal beat identity')
            require(bool(re.fullmatch(r'BEAT-[A-Za-z0-9_-]+', identifier)), 'pivotal identity must use BEAT-*')
            require(identifier not in local_ids, 'duplicate pivotal identity in artifact')
            local_ids.add(identifier)
            text(beat.get('content'), 'pivotal event and consequential change')
            raw_parents = beat.get('source_beat_ids')
            require(isinstance(raw_parents, list) and all(isinstance(ref, str) for ref in raw_parents),
                    'pivotal beat ancestry must be a list of IDs')
            beat['source_beat_ids'] = [ref if ref in migrations else original(ref) for ref in raw_parents]
            parents = references(beat['source_beat_ids'], allowed, 'pivotal beat ancestry', empty=True)
            # Repeated ancestry links describe the same predecessor relationship.
            beat['source_beat_ids'] = sorted(parents)
            canonical = migrations.get(identifier, identifier)
            if canonical in known:
                established = {ref for source in sources for prior in source.get('pivotal_beats', [])
                               if prior['id'] == canonical for ref in prior.get('source_beat_ids', [])}
                supplied = {original(ref) for ref in parents}
                if identifier in migrations:
                    supplied.discard(canonical)
                require(supplied == established or (identifier in migrations and supplied == ancestors(established)),
                        'retained pivotal identities preserve established predecessor links')
                if identifier in migrations:
                    # Publish the rename's provenance so the next tick can trace it.
                    beat['source_beat_ids'] = sorted(ancestors(established | {canonical}))
            else:
                require(identifier not in lineage, 'new pivotal identity cannot reuse an ancestor name')
                readable = rf'BEAT-{PHASE_LETTERS[phase]}[1-9][0-9]*-{phase}-[1-9][0-9]*'
                legacy = re.escape(f'BEAT-{cycle_id}-{phase}-') + r'[1-9][0-9]*'
                require(bool(re.fullmatch(readable, identifier) or re.fullmatch(legacy, identifier)),
                        f'new pivotal identity must use a readable ID such as BEAT-{PHASE_LETTERS[phase]}1-{phase}-1')
                # Carry ancestry forward so later cycles cannot recycle a short
                # name merely because its original event is several steps back.
                beat['source_beat_ids'] = sorted(ancestors(parents))
            require(identifier not in parents, 'retained identity must not reference itself as a predecessor')
            if identifier in definitions:
                from .story_records import clean
                require(clean(definitions[identifier]) == clean(beat), 'one pivotal identity has conflicting definitions within a result')
            definitions[identifier] = beat
            accounted.update(original(ref) for ref in parents)
            if canonical in known:
                accounted.add(canonical)
    require(known <= accounted, 'missing pivotal beat identity coverage; retain or explicitly derive from each source beat')


def validate_result(payload: dict, *, phase: str, cycle_id: str, scope: str,
                    accepted: dict, inherited: list | None = None) -> dict:
    """Validate model data, assign stable identifiers, and materialize Tiferet outlines."""
    require(isinstance(payload, dict), 'result must be an object')
    result = deepcopy(payload)
    require_identities = require_pivotal = True
    require(result.get('cycle_id') == cycle_id, 'result belongs to another cycle')
    require(isinstance(scope, str) and scope in SCOPES and result.get('scope') == scope, 'result scope must match current issue')
    require(isinstance(result.get('outcome'), str) and result['outcome'] in {'complete','develop','failure'}, 'unknown structured outcome')
    text(result.get('narrative'), 'narrative')
    questions = result.get('questions')
    require(isinstance(questions, list) and all(isinstance(q, str) and q.strip() for q in questions), 'questions must be a list of nonempty text')
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
    require(not questions, 'resolve creative choices within the current issue direction')
    if result['outcome'] == 'failure':
        return result
    if result['outcome'] == 'develop':
        text(result.get('development_question'), 'top-level outcome=develop: development_question')
        text(result.get('return_reason'), 'top-level outcome=develop: return_reason')
        return result
    inherited = inherited or []
    from .reference_resolution import published_aliases, resolve_reference
    if phase == '1':
        axes = result.get('axes')
        require(isinstance(axes, dict) and set(axes) == set(AXES), 'Keter requires the five dramaturgical axes')
        for axis in AXES:
            text(axes.get(axis), axis)
        items = result.get('anchors')
    elif phase in {'2A','2B','2C'}:
        require('1' in accepted, 'current accepted Keter brief is required; restart through Keter')
        items = result.get('artifacts')
    elif phase == '3':
        require(all(p in accepted for p in ('2A','2B','2C')), 'all three current explorations are required')
        items = result.get('anchors')
    elif phase == '4':
        require('3' in accepted, 'accepted current Gevurah organization is required')
        organization = accepted['3']
        assignments = result.get('assignments')
        require(isinstance(assignments, list), 'Tiferet requires assignments')
        expected = [e['id'] for e in organization['elements']]
        require(all(isinstance(a,dict) for a in assignments), 'assignments must be objects')
        aliases = published_aliases([organization])
        for assignment in assignments:
            assignment['element_id'] = resolve_reference(assignment.get('element_id'), set(expected), aliases)
        require([a.get('element_id') for a in assignments] == expected, 'assignments must preserve every accepted element in order')
        result['anchors'] = deepcopy(organization['anchors'])
        result['elements'] = deepcopy(organization['elements'])
        for assignment, element in zip(assignments, result['elements']):
            require(set(assignment) == {'element_id','outline','scope'}, 'Tiferet assignments require identity, outline, and estimated scope')
            require(assignment['scope'] in {'episode', 'act', 'scene'}, 'child assignments need an estimated episode, act, or scene scope')
            require(element['scope'] == 'undetermined' or assignment['scope'] == element['scope'],
                    'Tiferet preserves an already established scope')
            element['scope'] = assignment['scope']
            if element['readiness'] == 'ready':
                element['outline'] = text(assignment.get('outline'), 'scene outline')
            else:
                require(assignment.get('outline') == element.get('outline',''), 'development assignments preserve prior work')
        return result
    else:
        raise SystemExit(f'Unknown creative phase {phase}')
    require(isinstance(items, list) and bool(items), 'nonempty dramatic material is required')
    for index, item in enumerate(items, 1):
        require(isinstance(item, dict), 'dramatic material must be an object')
        text(item.get('content'), 'dramatic content')
        if phase == '1' and (require_pivotal or 'pivotal_beat' in item):
            text(item.get('pivotal_beat'), 'Keter anchor pivotal_beat')
        if phase in {'2A','2B','2C'}:
            require(isinstance(item.get('scope'), str) and item['scope'] in GENERATED_SCOPES, 'artifact scope must be episode, act, scene, or undetermined; season scope belongs to the existing project root')
        item['id'] = f'{cycle_id}:{phase}:a{index}'
    if require_identities:
        sources = (inherited if phase == '1' else accepted['1']['anchors'] if phase in {'2A','2B','2C'}
                   else [a for p in ('2A','2B','2C') for a in accepted[p]['artifacts']])
        source_records = (inherited if phase == '1' else [accepted['1']] if phase in {'2A','2B','2C'}
                          else [accepted[p] for p in ('1','2A','2B','2C')])
        aliases = published_aliases(source_records)
        validate_pivotal_identities(items, sources, cycle_id=cycle_id, phase=phase, source_aliases=aliases)
    if phase == '3':
        elements = result.get('elements')
        require(isinstance(elements, list) and bool(elements), 'Gevurah requires organized elements')
        locations = set()
        scene_pivots = set()
        selected_pivots = set()
        pivotal_ids = {b['id'] for a in items for b in a.get('pivotal_beats', [])}
        source_pivotal_ids = {b['id'] for a in sources for b in a.get('pivotal_beats', [])}
        for index, element in enumerate(elements, 1):
            validate_element(element, require_pivotal=require_pivotal)
            element['id'] = f'{cycle_id}:e{index}'
            for number, beat in enumerate(element.get('beats') or [], 1):
                beat['id'] = f'{element["id"]}:b{number}'
                if require_identities:
                    identity = beat.get('pivotal_beat_id')
                    if beat.get('is_pivotal'):
                        identity = resolve_reference(identity, pivotal_ids, aliases)
                        if isinstance(identity, str) and identity not in pivotal_ids and identity in source_pivotal_ids:
                            from .beat_ids import source_names
                            renamed = {b['id'] for a in items for b in a.get('pivotal_beats', [])
                                       if b['id'] in source_names(identity) and identity in b.get('source_beat_ids', [])}
                            require(len(renamed) <= 1, 'ambiguous readable pivotal selection; use the selected beat ID')
                            if renamed:
                                identity = next(iter(renamed))
                        beat['pivotal_beat_id'] = identity
                        require(isinstance(identity, str) and identity in pivotal_ids,
                                'element pivotal beat must name an identity from the synthesis pivotal beats')
                        selected_pivots.add(identity)
                        if element['scope'] == 'scene':
                            require(identity not in scene_pivots, 'split scenes require distinct pivotal identities')
                            scene_pivots.add(identity)
                    else:
                        require(identity is None, 'supporting beats must have null pivotal_beat_id')
            if element['readiness'] == 'ready':
                location = (element['placement']['episode'],element['placement']['scene_id'])
                require(location not in locations, 'duplicate scene placement')
                locations.add(location)
        missing = pivotal_ids - selected_pivots
        if missing:
            raise SynthesisCoverageError(
                'Creative contract: every synthesized pivotal beat must travel into an element. '
                f'Unassigned IDs: {", ".join(sorted(missing))}. '
                + GEVURAH_SYNTHESIS_RULE
            )
    return result


def validate_tiferet_specification_payload_structure(payload: dict[str, Any]) -> None:
    """Reject legacy decomposition; callers must validate against the accepted synthesis."""
    require(payload.get('kind') == 'result' and payload.get('phase') == '4' and payload.get('elements'),
            'legacy work must be re-established through Keter before decomposition')
    for element in payload['elements']:
        validate_element(element, require_pivotal=True)


def result_contract(phase: str) -> str:
    from .beat_ids import PHASE_LETTERS
    common = {'scope':'copy current issue scope',
              'outcome':'complete | develop | failure', 'narrative':'concise phase-domain summary',
              'questions':[],
              'development_question':'specific question for the whole work when outcome=develop; otherwise empty',
              'return_reason':'reason the whole work needs a new Keter cycle when outcome=develop; otherwise empty'}
    if phase == '1':
        common.update(reference_prefix={'code':'2–12 uppercase letters chosen meaningfully for this specific project',
                                        'meaning':'neutral description of what those letters refer to'},
                      axes={axis:'precise dramatic axis' for axis in AXES},
                      anchors=[{'content':'dramatic anchor', 'pivotal_beat':'one sentence describing a concrete event and its consequential dramatic change; a revisable hypothesis'}])
    elif phase in {'2A','2B','2C'}:
        common['narrative'] = 'one short orienting sentence'
        common['artifacts'] = [{'scope':'episode | act | scene | undetermined', 'content':'one short sentence on one line per item: a premise-level idea in this phase’s domain'}]
    elif phase == '3':
        common['outcome'] = ('complete for an established synthesis, including a mixture of ready and develop elements | '
                             'develop to return the whole work to Keter | failure')
        common.update(anchors=[{'content':'synthesized anchor and relationships'}],
            elements=[{'title':'dramatic element', 'scope':'episode | act | scene | undetermined', 'readiness':'ready | develop',
                       'content':'dramatic purpose: a milestone, circumstance, or change and its relationships','outline':'established scene outline, or prior work',
                       'development_question':'specific question for this element when readiness=develop; empty when readiness=ready',
                       'return_reason':'reason this element needs exploration when readiness=develop; empty when readiness=ready',
                       'placement':{'episode':'Script/Season_01/Episode_01','act':'1','scene_id':'safe-scene-id'},
                       'beats':[{'content':'ordered dramatic purpose and situation; expression belongs to the character', 'is_pivotal':True}]}])
    elif phase == '4':
        common['assignments'] = [{'element_id':'accepted element ID, in accepted order','outline':'concrete scene outline; preserve prior work for develop',
                                  'scope':'episode | act | scene; estimate when the accepted scope is undetermined, otherwise preserve it'}]
    if phase in {'1', '2A', '2B', '2C', '3'}:
        key = 'artifacts' if phase in {'2A', '2B', '2C'} else 'anchors'
        common[key][0]['pivotal_beats'] = [{'id': f'retained BEAT-* ID or BEAT-{PHASE_LETTERS[phase]}1-{phase}-1 (positive stem and beat numbers)',
            'content': 'exactly one dramatic sentence describing an event and its consequential change', 'source_beat_ids': ['preserve established predecessor IDs when retaining; name source BEAT-* IDs when deriving; empty for an original event']}]
        if phase == '3':
            common['elements'][0]['beats'][0]['pivotal_beat_id'] = 'BEAT-* identity from synthesis pivotal beats; null for supporting beats'
    return ((GEVURAH_SYNTHESIS_RULE + '\n\n' if phase == '3' else '')
            + (f'For new pivotal IDs use BEAT-{PHASE_LETTERS[phase]}<positive stem number>-{phase}-<positive beat number>, '
             f'for example BEAT-{PHASE_LETTERS[phase]}1-{phase}-1. ' if phase in PHASE_LETTERS else '')
            + 'Python supplies cycle and issue ownership; do not return cycle_id. '
            'Keep names unique within a result; do not reuse an incoming beat or ancestor name for a new event. '
            'Retain existing IDs exactly. For cycle-qualified IDs, a readable rename such as BEAT-K1-1-1 for BEAT-<cycle>-1-1 is allowed only when it identifies one supplied source beat. '
            'Copy its established predecessor links; Python adds the original source ID as rename ancestry. '
            'Python also carries transitive predecessor IDs onto derived beats to prevent later name reuse. '
            'If that readable name is ambiguous, use the exact source ID.\n'
            'Visible labels such as BEAT-K1 may be used in source_beat_ids when they identify exactly one supplied source; Python resolves them to full source IDs. '
            'Use full readable IDs, such as BEAT-K1-1-1, for beat id fields.\n'
            'For source_beat_ids, pivotal_beat_id, and assignment element_id, copy the full source ID or its exact displayed link label. '
            'Python resolves unique displayed labels from the supplied source comments; ambiguous labels require the full ID.\n'
            'Return one JSON object, no fences. Python assigns material IDs and renders public headings, size labels, BEAT links.\n'
            + json.dumps(common, ensure_ascii=False, indent=2)
            + '\nKeter chooses the reference prefix from the specific project and describes its meaning neutrally; it is a reference label, not a slogan or dramatic interpretation. Reuse an established project prefix when appropriate. Other phases inherit it from accepted Keter; do not choose or override it. Keep internal IDs out of narrative prose. '
            'The output schema defines the required fields. Resolve creative choices independently within the supplied intention and canon; keep questions empty. '
            'For outcomes failure or develop, represent unused phase-specific arrays as [], nullable objects as null, and unused text as an empty string. '
            'For failure, describe the execution failure in narrative. '
            'For top-level outcome=develop, supply top-level development_question and return_reason alongside outcome; this returns the whole current work to a new Keter cycle. '
            'Use grounded judgment and stated working assumptions for creative uncertainty. Complete requires all phase-specific fields and no questions. '
            'Write every pivotal-beat description as exactly one dramatic sentence, including pivotal_beats content, Keter pivotal_beat, and the selected element beat content. '
            'Public prose states the event and consequential change directly. '
            'Every anchor and phase-2 artifact carries nonempty pivotal_beats. Keep each BEAT-* identity through retention and transformation. '
            'New or split pivotal events get readable BEAT-<phase letters><positive stem number>-<phase>-<positive beat number> IDs and source_beat_ids naming their predecessors. '
            'For a retained identity, copy its established source_beat_ids exactly, including an empty list. Never put a beat’s own ID in source_beat_ids: retaining an ID already records continuity. Only a new successor names the earlier beat as a predecessor. '
            'Preserve or derive from every incoming pivotal identity. Use the same definition wherever an identity repeats within a result. '
            'For legacy sources without BEAT-* IDs, establish IDs now; historical records remain unchanged. '
            'Keter pivotal_beat repeats its first pivotal_beats content exactly; storage keeps that sentence once. Gevurah anchors carry the resulting identities, and each element pivotal beat selects one with pivotal_beat_id. '
            'Tiferet and child cycles preserve these identities and ancestry. '
            'Preserve or derive from every incoming BEAT identity across the exploration. '
            'Only scenes with episode/act/scene placement, established outline and ordered beats with one identified pivotal event may be ready. '
            'Develop elements require a specific question and reason; placement may be null. Every new element has exactly one beat with is_pivotal=true; mark all supporting beats false. '
            'Keter gives every anchor a pivotal_beat: a concrete event and consequential change, not a theme or question. '
            'Evaluate any inherited pivotal beat; retain it or revise it independently. '
            'Gevurah carries BEAT identities from the explorations into its elements. When splitting material into scenes, '
            'give each scene its own distinct pivotal change and explain how it develops or revises the parent hypothesis. '
            'Tiferet preserves every accepted beat and its pivotal marker. A pivotal beat alone does not establish readiness. '
            'Let dramatic purpose establish an element and exploration discover its form. '
            'Use undetermined (scope to be discovered) while form remains open, with readiness=develop, '
            'a specific development_question and return_reason. Preserve prior outlines and beat ideas; placement may be null. '
            'Keep the owning issue scope unchanged throughout its cycle; later synthesis establishes child scopes. '
            'Season scope belongs to the existing project root; generated artifacts/elements use episode, act, scene or undetermined. '
            'Tiferet preserves accepted organization and established scopes. Estimate episode, act, or scene for undetermined elements; never create size:undetermined children. A scene is one encounter, an act groups scenes, and an episode contains a substantial arc; choose the smallest plausible scope. Use outcome=complete when every element has a sized assignment, even when all have readiness=develop. Preserve development outlines exactly. Open form is explored in child issues. Only a structural contradiction preventing faithful assignment warrants returning the whole organization through outcome=develop.')
