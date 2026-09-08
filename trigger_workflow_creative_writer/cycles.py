"""Issue-backed exploration cycles and attributed recursive scene assignments."""
from __future__ import annotations

from copy import deepcopy
import json
import re
from uuid import uuid4

from .validation import SCOPES, require, validate_result, validate_element

from . import story_records

PHASES = ('1','2A','2B','2C','3','4')


def encode_record(record: dict) -> str:
    return story_records.render(record)


def decode_records(body: str, *, location: dict | None = None) -> list[dict]:
    return story_records.read(body, location=location)


def issue_records(issue_data: dict) -> list[dict]:
    result = []
    active = None
    for comment in issue_data.get('comments', []):
        location = None
        if issue_data.get('_repo') and type(comment.get('id')) is int:
            location = {'repo': issue_data['_repo'], 'issue': issue_data['number'], 'comment': comment['id']}
        for record in decode_records(str(comment.get('body') or ''), location=location):
            if record['kind'] == 'cycle':
                active = record
            elif record['kind'] == 'result' and 'cycle_id' not in record:
                record.setdefault('scope', issue_scope(issue_data))
                if record.get('phase') == '1':
                    # The Keter comment starts the run. Reuse its existing anchor
                    # namespace for validators; no separate cycle record is stored.
                    anchors = record.get('anchors', [])
                    namespace = anchors[0]['id'].split(':', 1)[0] if anchors else f"comment-{comment['id']}"
                    active = {'kind': 'cycle', 'cycle_id': namespace, 'scope': record['scope']}
                    result.append(active)
                require(active is not None, 'phase output has no preceding Keter comment')
                record['cycle_id'] = active['cycle_id']
            result.append(record)
            if record['kind'] == 'result' and record.get('outcome') == 'develop':
                # The development direction already lives in this result. Its
                # GitHub comment provides a stable restart boundary on retries.
                active = {'kind': 'cycle', 'cycle_id': f"comment-{comment['id']}-next",
                          'scope': record['scope'], 'prior_cycle': record['cycle_id'],
                          'development_question': record['development_question'],
                          'return_reason': record['return_reason']}
                result.append(active)
    return result


def issue_scope(issue_data: dict) -> str:
    sizes = [label['name'][5:] for label in issue_data.get('labels', [])
             if isinstance(label, dict) and str(label.get('name','')).startswith('size:')]
    require(len(sizes) == 1 and sizes[0] in SCOPES, 'issue needs exactly one size:season/episode/act/scene/undetermined label; re-establish through Keter')
    return sizes[0]


def issue_reference(issue_data: dict) -> dict | None:
    """GitHub ownership is harness metadata, separate from dramatic references."""
    repo, number = issue_data.get('_repo'), issue_data.get('number')
    if repo is None or number is None:
        return None  # Read-only legacy fixtures/records may predate ownership metadata.
    require(isinstance(repo, str) and repo.count('/') == 1, 'invalid owning repository')
    require(isinstance(number, int) and not isinstance(number, bool) and number > 0, 'invalid owning issue number')
    return {'repo':repo, 'number':number, 'scope':issue_scope(issue_data)}


def bind_issue(issue_data: dict, repo: str, number: int) -> None:
    require(issue_data.get('number', number) == number, 'fetched issue number differs from requested issue')
    require(issue_data.get('_repo', repo) == repo, 'fetched repository differs from requested repository')
    issue_data.update(number=number, _repo=repo)
    from .github_ops import ensure_story_source_root
    ensure_story_source_root(repo, number)


def check_issue_reference(record: dict, issue_data: dict) -> None:
    season = record.get('season_ref')
    if season is not None and issue_data.get('_season_ref') is not None:
        require(season == issue_data['_season_ref'], 'record belongs to another season')
    owner = record.get('issue_ref')
    if owner is not None:
        actual = issue_reference(issue_data)
        require(isinstance(owner, dict) and set(owner) == {'repo','number','scope'}, 'invalid issue ownership metadata')
        require(owner.get('scope') == record.get('scope'), 'issue ownership scope differs from record scope')
        if actual is not None:
            require(owner == actual, 'record belongs to another issue or repository')


def current_cycle(issue_data: dict) -> dict | None:
    cycles = [r for r in issue_records(issue_data) if r.get('kind') == 'cycle']
    cycle = issue_data.get('_pending_cycle') or issue_data.get('_preview_cycle') or (cycles[-1] if cycles else None)
    if cycle:
        check_issue_reference(cycle, issue_data)
        require(isinstance(cycle.get('cycle_id'), str) and bool(re.fullmatch(r'[A-Za-z0-9_-]+', cycle['cycle_id'])), 'invalid cycle identity')
        require(cycle.get('scope') == issue_scope(issue_data), 'cycle scope changed; explicitly restart through Keter')
    return cycle


def new_cycle(issue_data: dict, *, development: dict | None = None) -> dict:
    if development:
        development = {'prior_cycle': development['prior_result']['cycle_id'],
                       'development_question': development['development_question'],
                       'return_reason': development['return_reason']}
    result = {'kind':'cycle','version':1,'cycle_id':uuid4().hex[:12],'scope':issue_scope(issue_data),
              **(development or {})}
    owner = issue_reference(issue_data)
    if owner is not None:
        result['issue_ref'] = owner
    if issue_data.get('_season_ref') is not None:
        result['season_ref'] = deepcopy(issue_data['_season_ref'])
    return result


def source_context(issue_data: dict) -> dict:
    cycle = current_cycle(issue_data)
    if cycle and cycle.get('prior_cycle'):
        prior = [r for r in issue_records(issue_data) if r.get('kind') == 'result'
                 and r.get('cycle_id') == cycle['prior_cycle'] and r.get('outcome') == 'complete']
        sources = next((r['anchors'] for r in reversed(prior) if r.get('phase') == '3'), None)
        if sources is None:
            sources = [a for r in prior if r.get('phase') in {'2A', '2B', '2C'} for a in r.get('artifacts', [])]
        if not sources:
            sources = next((r['anchors'] for r in reversed(prior) if r.get('phase') == '1'), [])
        if sources:
            return {'anchors': sources}
        # A development return before any completed local phase still inherits
        # the assigned parent event; restarting must not erase that source.
    inherited = inherited_assignment(issue_data)
    return inherited or {'anchors': []}


def current_result(issue_data: dict, phase: str) -> dict | None:
    cycle = current_cycle(issue_data)
    if not cycle:
        return None
    results = [r for r in issue_records(issue_data) if r.get('kind') == 'result'
               and r.get('cycle_id') == cycle['cycle_id'] and r.get('phase') == phase]
    result = results[-1] if results else None
    if result is not None:
        check_issue_reference(result, issue_data)
    return result


def assignment_reference(body: str) -> dict | None:
    links = re.findall(r'\[Parent assignment\]\(https://github\.com/([^/]+/[^/]+)/issues/(\d+)\?element=([A-Za-z0-9_.:-]+)#issuecomment-(\d+)\)', body)
    require(len(links) <= 1, 'ambiguous parent assignment link')
    if not links:
        return None
    repo, parent, element, comment = links[0]
    return {'parent_issue': int(parent), 'source_comment': int(comment),
            'element_id': element, '_repo': repo}


def assignment_keys(body: str) -> list[str]:
    reference = assignment_reference(body)
    if reference:
        return [f"{reference['parent_issue']}:{reference['element_id']}"]
    return re.findall(r'^Assignment key: ([A-Za-z0-9_.:-]+)$', body, re.MULTILINE)


def inherited_assignment(issue_data: dict) -> dict | None:
    records = [r for r in decode_records(str(issue_data.get('body') or '')) if r.get('kind') == 'assignment']
    require(len(records) <= 1, 'ambiguous recursive assignment')
    link = assignment_reference(str(issue_data.get('body') or ''))
    if not records and link is None:
        return None
    assignment = link or records[0]
    if link:
        require(link['_repo'].lower() == str(issue_data.get('_repo', '')).lower(),
                'parent assignment must belong to this repository')
    from .github_ops import fetch_assignment_source
    parent_data = fetch_assignment_source(issue_data, assignment['parent_issue'])
    all_results = [r for r in issue_records(parent_data) if r.get('kind') == 'result']
    deliveries = [r for r in all_results if r.get('phase') == '4'
                  and r.get('_source', {}).get('comment') == assignment['source_comment']]
    require(len(deliveries) == 1, 'parent assignment source is missing or ambiguous')
    assignment['cycle_id'] = deliveries[0]['cycle_id']
    results = [r for r in all_results if r.get('cycle_id') == assignment['cycle_id']]
    synthesis = next((r for r in reversed(results) if r.get('phase') == '3' and r.get('outcome') == 'complete'), None)
    delivery = next((r for r in reversed(results) if r.get('phase') == '4' and r.get('outcome') == 'complete'
                     and r.get('_source', {}).get('comment') == assignment['source_comment']), None)
    require(synthesis is not None and delivery is not None, 'assignment source is missing; inspect the parent issue')
    matches = [e for e in synthesis.get('elements', []) if e['id'] == assignment['element_id']]
    outlines = [a for a in delivery.get('assignments', []) if a['element_id'] == assignment['element_id']]
    require(len(matches) == len(outlines) == 1, 'assignment element is missing or ambiguous in parent issue')
    element = deepcopy(matches[0])
    element['outline'] = outlines[0]['outline']
    element['scope'] = outlines[0].get('scope', element['scope'])
    require(issue_scope(issue_data) == element['scope'], 'child size differs from its parent element')
    selected = {b.get('pivotal_beat_id') for b in element.get('beats', []) if b.get('is_pivotal')}
    anchors = []
    for original in synthesis['anchors']:
        beats = [b for b in original.get('pivotal_beats', []) if b['id'] in selected]
        if beats:
            anchor = deepcopy(original)
            anchor['pivotal_beats'] = deepcopy(beats)
            anchors.append(anchor)
    assignment.update(element=element, anchors=anchors)
    assignment.update(scope=element['scope'], readiness=element['readiness'])
    return validate_assignment(assignment)


def accepted_results(issue_data: dict) -> dict:
    cycle = current_cycle(issue_data)
    if not cycle:
        return {}
    accepted = {}
    for phase in PHASES:
        result = current_result(issue_data, phase)
        if result and result.get('outcome') == 'complete':
            # Published prose is the working material. Do not replay historical
            # validations or reconstruct a provenance graph at every tick.
            result['issue_ref'] = issue_reference(issue_data)
            if issue_data.get('_season_ref') is not None:
                result['season_ref'] = deepcopy(issue_data['_season_ref'])
            if phase != '1' and '1' in accepted:
                result['reference_prefix'] = accepted['1'].get('reference_prefix')
            if phase == '4':
                require('3' in accepted, 'Tiferet needs visible Gevurah elements')
                result['anchors'] = deepcopy(accepted['3']['anchors'])
                result['elements'] = deepcopy(accepted['3']['elements'])
                outlines = {a['element_id']: a['outline'] for a in result.get('assignments', [])}
                require(list(outlines) == [e['id'] for e in result['elements']], 'Tiferet assignments differ from visible elements')
                for element in result['elements']:
                    element['outline'] = outlines[element['id']]
                    assignment = next(a for a in result['assignments'] if a['element_id'] == element['id'])
                    element['scope'] = assignment.get('scope', element['scope'])
            accepted[phase] = result
    return accepted


REFERENCE_ID = re.compile(r'([A-Za-z0-9_-]+):(?:(1|2A|2B|2C|3):a([1-9][0-9]*)|e([1-9][0-9]*)(?::b([1-9][0-9]*))?)')
PIVOTAL_REFERENCE_ID = re.compile(r'(?<![A-Za-z0-9_-])BEAT-([A-Za-z0-9_-]+)-(1|2A|2B|2C|3)-([1-9][0-9]*)(?![A-Za-z0-9_-])')
REFERENCE_PHASES = {'1': 'K', '2A': 'CH', '2B': 'B', '2C': 'C', '3': 'G'}


def public_reference_map(result: dict, ancestry: list | None = None) -> dict[str, str]:
    """Compact display labels link to canonical identifiers in visible Markdown."""
    from .beat_ids import is_readable
    prefix = (result.get('reference_prefix') or {}).get('code', 'Reference')
    serialized = json.dumps([result, ancestry or []], ensure_ascii=False)
    matches = list(REFERENCE_ID.finditer(serialized))
    pivotal_matches = [match for match in PIVOTAL_REFERENCE_ID.finditer(serialized)
                       if not is_readable(match[0])]
    earlier = sorted({m[1] for m in matches + pivotal_matches} - {result['cycle_id']})
    labels = {result['cycle_id']: prefix}
    labels.update({identity: f'{prefix}-H{index}' for index, identity in enumerate(earlier, 1)})
    aliases = {}
    for match in matches:
        suffix = (REFERENCE_PHASES[match[2]] + match[3]) if match[2] else 'E' + match[4]
        if match[5]:
            suffix += '-B' + match[5]
        aliases[match[0]] = labels[match[1]] + '-' + suffix
    for match in pivotal_matches:
        history = f'H{earlier.index(match[1]) + 1}-' if match[1] != result['cycle_id'] else ''
        aliases[match[0]] = f'BEAT-{history}{REFERENCE_PHASES[match[2]]}{match[3]}'
    # Also hide bare internal exploration identities in model-authored prose.
    aliases.update({identity: f'{label} exploration' for identity, label in labels.items()})
    return aliases


def readable_references(content: str, aliases: dict[str, str]) -> str:
    if not aliases:
        return content
    pattern = '|'.join(re.escape(key) for key in sorted(aliases, key=len, reverse=True))
    return re.sub(r'(?<![A-Za-z0-9_-])(?:' + pattern + r')(?![A-Za-z0-9_-]|:[A-Za-z0-9])',
                  lambda match: aliases[match[0]], content)


def display_scope(scope: str) -> str:
    return 'scope to be discovered' if scope == 'undetermined' else f'size:{scope}'


def render_result(result: dict, *, reference_map: dict[str, str] | None = None, issue_label: str = "Issue") -> str:
    aliases = reference_map if reference_map is not None else public_reference_map(result)
    wire = deepcopy(result)
    if wire.get('phase') == '4' and wire.get('outcome') == 'complete':
        wire.pop('anchors', None)
        wire.pop('elements', None)
    return story_records.render(wire, aliases)


def child_description(element: dict) -> str:
    """Describe the assigned story work before the routing record."""
    lines = [f"## {element['title']}", '', element['content'], '',
             '### Story outline', '', element['outline'], '', '### Assigned beats', '']
    for number, beat in enumerate(element['beats'], 1):
        pivotal = f" **Pivotal — {beat['pivotal_beat_id']}.**" if beat['is_pivotal'] else ''
        lines.extend([f"{number}.{pivotal} {beat['content']}", ''])
    for field, heading in (('development_question', 'Question to develop'),
                           ('return_reason', 'Why further development is needed')):
        if element.get(field):
            lines.extend([f'### {heading}', '', element[field], ''])
    return '\n'.join(lines)


def child_assignments(result: dict, *, parent_issue: int, accepted: dict, inherited: dict | None = None) -> list[dict]:
    require(result.get('phase') == '4' and result.get('outcome') == 'complete', 'only accepted Tiferet creates assignments')
    children = []
    locator = story_records.source(result)
    for element in result['elements']:
        require(element['scope'] in {'episode', 'act', 'scene'}, 'child assignments require an estimated size below season')
        url = story_records.source_url(locator).replace('#issuecomment-', f"?element={element['id']}#issuecomment-")
        public = (child_description(element) + '\n'
                  f"[Parent assignment]({url})\n")
        children.append({'title': element['title'], 'body': public,
                         'scope': element['scope'], 'readiness': element['readiness'],
                         'delivery_key': f"{parent_issue}:{element['id']}"})
    return children


def validate_assignment(assignment: dict) -> dict:
    """Check the immediate visible parent element, not its whole creative history."""
    element = assignment.get('element')
    require(isinstance(element, dict), 'assignment needs its visible parent element')
    validate_element(element, require_pivotal=True)
    known = {b['id'] for a in assignment.get('anchors', []) for b in a.get('pivotal_beats', [])}
    require(all(b.get('pivotal_beat_id') in known for b in element['beats'] if b['is_pivotal']),
            'assignment pivotal beat is missing from the parent synthesis')
    return assignment


def is_ready_scene_result(result: dict) -> bool:
    elements = result.get('elements', [])
    return (result.get('scope') == 'scene' and result.get('phase') == '4'
            and result.get('outcome') == 'complete' and len(elements) == 1
            and elements[0].get('scope') == 'scene' and elements[0].get('readiness') == 'ready')


def ready_assignment(issue_data: dict) -> dict:
    local = accepted_results(issue_data).get('4')
    if local is not None:
        require(is_ready_scene_result(local), 'local Tiferet material must resolve to one ready scene before preparation')
        assignment = validate_assignment({'element': deepcopy(local['elements'][0]),
                                         'anchors': deepcopy(local['anchors']),
                                         '_source': story_records.source(local)})
    else:
        assignment = inherited_assignment(issue_data)
    require(assignment is not None, 'legacy work must be re-established through Keter before scene preparation')
    require(issue_scope(issue_data) == 'scene', 'ready assignment requires size:scene')
    require(assignment['element'].get('readiness') == 'ready', 'issue needs a validated ready-scene assignment; return through Keter')
    return assignment
