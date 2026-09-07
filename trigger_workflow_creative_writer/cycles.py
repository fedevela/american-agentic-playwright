"""Issue-backed exploration cycles and attributed recursive scene assignments."""
from __future__ import annotations

import base64
from copy import deepcopy
import json
import re
from uuid import uuid4

from .validation import SCOPES, require, validate_result, validate_element

RECORD = re.compile(r'<!-- creative-record:([A-Za-z0-9_=-]+) -->')
PHASES = ('1','2A','2B','2C','3','4')


def encode_record(record: dict) -> str:
    data = json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
    return '<!-- creative-record:' + base64.urlsafe_b64encode(data).decode() + ' -->'


def decode_records(body: str) -> list[dict]:
    records = []
    for match in RECORD.finditer(body):
        try:
            value = json.loads(base64.urlsafe_b64decode(match.group(1)).decode())
        except (ValueError, UnicodeError) as exc:
            raise SystemExit('Malformed creative record; reconcile before continuing') from exc
        require(isinstance(value, dict) and value.get('version') == 1, 'unsupported creative record version')
        records.append(value)
    return records


def issue_records(issue_data: dict) -> list[dict]:
    return [r for comment in issue_data.get('comments', []) for r in decode_records(str(comment.get('body') or ''))]


def issue_scope(issue_data: dict) -> str:
    sizes = [label['name'][5:] for label in issue_data.get('labels', [])
             if isinstance(label, dict) and str(label.get('name','')).startswith('size:')]
    require(len(sizes) == 1 and sizes[0] in SCOPES, 'issue needs exactly one size:season/episode/act/scene label; re-establish through Keter')
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


def check_issue_reference(record: dict, issue_data: dict) -> None:
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
        development = deepcopy(development)
        work = development.get('prior_work', {})
        if '3' in work:
            sources = work['3']['anchors']
        elif any(p in work for p in ('2A','2B','2C')):
            sources = [a for p in ('2A','2B','2C') for a in work.get(p,{}).get('artifacts',[])]
        else:
            sources = work.get('1',{}).get('anchors',[])
        prior = source_context(issue_data)
        development['sources'] = deepcopy(sources or prior['anchors'])
        development['ancestry'] = prior['ancestry'] + [deepcopy(a) for r in work.values() for a in r.get('anchors',[]) + r.get('artifacts',[])]
        development['canon_refs'] = sorted({c for r in work.values() for c in r.get('canon_refs',[])} | set(prior['canon_refs']))
    result = {'kind':'cycle','version':1,'cycle_id':str(uuid4()),'scope':issue_scope(issue_data),
              'development':development}
    owner = issue_reference(issue_data)
    if owner is not None:
        result['issue_ref'] = owner
    return result


def source_context(issue_data: dict) -> dict:
    cycle = current_cycle(issue_data)
    development = cycle.get('development') if cycle else None
    if development:
        return {'anchors':development.get('sources',[]), 'ancestry':development.get('ancestry',[]),
                'canon_refs':development.get('canon_refs',[])}
    inherited = inherited_assignment(issue_data)
    return inherited or {'anchors':[], 'ancestry':[], 'canon_refs':[]}


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


def inherited_assignment(issue_data: dict) -> dict | None:
    records = [r for r in decode_records(str(issue_data.get('body') or '')) if r.get('kind') == 'assignment']
    require(len(records) <= 1, 'ambiguous recursive assignment')
    if not records:
        return None
    assignment = validate_assignment(records[0])
    require(issue_scope(issue_data) == assignment['element']['scope'], 'child size label differs from accepted assignment scope')
    parent = assignment.get('parent_ref')
    if parent and issue_data.get('_repo') is not None:
        require(parent['repo'] == issue_data['_repo'], 'recursive assignment belongs to another repository')
        require(parent['number'] != issue_data.get('number'), 'issue cannot own its own recursive assignment')
    return assignment


def accepted_results(issue_data: dict) -> dict:
    cycle = current_cycle(issue_data)
    if not cycle:
        return {}
    inherited = source_context(issue_data)
    sources = inherited['anchors']
    accepted = {}
    for phase in PHASES:
        result = current_result(issue_data, phase)
        if result:
            check_issue_reference(result, issue_data)
        if result and result.get('outcome') == 'complete':
            if phase == '1':
                require(set(inherited['canon_refs']) <= set(result.get('canon_refs', [])), 'inherited canon references must be preserved')
            accepted[phase] = validate_result(result, phase=phase, cycle_id=cycle['cycle_id'], scope=cycle['scope'],
                                               accepted=accepted, inherited=sources)
            owner = issue_reference(issue_data)
            if owner is not None:
                accepted[phase]['issue_ref'] = owner
    return accepted


def partner_replies(issue_data: dict, phase: str) -> list[dict]:
    latest = current_result(issue_data, phase)
    if not latest or latest.get('outcome') != 'question':
        return []
    after = False
    replies = []
    for comment in issue_data.get('comments', []):
        body = str(comment.get('body') or '')
        records = decode_records(body)
        if latest in records:
            after = True
            replies = []
            continue
        author = comment.get('author') or {}
        login = str(author.get('login') or '')
        if after and body.strip() and not records and '<!-- phase:' not in body and login and not login.endswith('[bot]') and author.get('type') != 'Bot':
            replies.append({'author':login, 'body':body, 'url':comment.get('url','')})
    return replies


def waiting_for_partner(issue_data: dict, phase: str) -> bool:
    result = current_result(issue_data, phase)
    return bool(result and result.get('outcome') == 'question' and not partner_replies(issue_data, phase))


def prompt_context(issue_data: dict, phase: str) -> dict:
    cycle = current_cycle(issue_data)
    if cycle is None:
        require(phase == '1', 'legacy work requires a new Keter cycle before exploration or scene preparation')
        cycle = {'cycle_id':'preview-cycle','scope':issue_scope(issue_data)}
    accepted = accepted_results(issue_data)
    context = {'cycle_id':cycle['cycle_id'],'scope':cycle['scope']}
    owner = issue_reference(issue_data)
    if owner is not None:
        context['issue_ref'] = owner
    if phase in {'2A','2B','2C'}:
        require('1' in accepted, 'current accepted Keter brief is required; restart through Keter')
        context['keter'] = accepted['1']
    else:
        # History stays explicitly attributed and separate from the accepted current inputs.
        context['history'] = [{'author':(c.get('author') or {}).get('login','unknown'),
                               'body': c.get('body','')} for c in issue_data.get('comments', [])
                              if not any(r.get('cycle_id') == cycle['cycle_id'] for r in decode_records(str(c.get('body') or '')))]
        if phase == '1':
            context.update(intention={'title':issue_data.get('title',''),'body':issue_data.get('body','')},
                           inherited=inherited_assignment(issue_data), development=cycle.get('development'),
                           source_material=source_context(issue_data))
        elif phase == '3':
            require(all(p in accepted for p in ('1','2A','2B','2C')), 'Gevurah requires Keter and all three current explorations')
            context.update(keter=accepted['1'], explorations={p:accepted[p] for p in ('2A','2B','2C')})
        elif phase == '4':
            require('3' in accepted, 'Tiferet requires the accepted current Gevurah synthesis; restart through Keter')
            context['synthesis'] = accepted['3']
    latest = current_result(issue_data, phase)
    if latest and latest.get('outcome') == 'question':
        context.update(prior_attempt=latest, partner_replies=partner_replies(issue_data, phase))
    return context


REFERENCE_ID = re.compile(r'([A-Za-z0-9_-]+):(?:(1|2A|2B|2C|3):a([1-9][0-9]*)|e([1-9][0-9]*)(?::b([1-9][0-9]*))?)')
REFERENCE_PHASES = {'1': 'K', '2A': 'CH', '2B': 'B', '2C': 'C', '3': 'G'}


def public_reference_map(result: dict, ancestry: list | None = None) -> dict[str, str]:
    """Local display aliases; encoded canonical identities remain authoritative."""
    prefix = (result.get('reference_prefix') or {}).get('code', 'Reference')
    matches = list(REFERENCE_ID.finditer(json.dumps([result, ancestry or []], ensure_ascii=False)))
    earlier = sorted({m[1] for m in matches} - {result['cycle_id']})
    labels = {result['cycle_id']: prefix}
    labels.update({identity: f'{prefix}-H{index}' for index, identity in enumerate(earlier, 1)})
    aliases = {}
    for match in matches:
        suffix = (REFERENCE_PHASES[match[2]] + match[3]) if match[2] else 'E' + match[4]
        if match[5]:
            suffix += '-B' + match[5]
        aliases[match[0]] = labels[match[1]] + '-' + suffix
    # Also hide bare internal exploration identities in model-authored prose.
    aliases.update({identity: f'{label} exploration' for identity, label in labels.items()})
    return aliases


def readable_references(content: str, aliases: dict[str, str]) -> str:
    if not aliases:
        return content
    pattern = '|'.join(re.escape(key) for key in sorted(aliases, key=len, reverse=True))
    return re.sub(r'(?<![A-Za-z0-9_-])(?:' + pattern + r')(?![A-Za-z0-9_-]|:[A-Za-z0-9])',
                  lambda match: aliases[match[0]], content)


def render_result(result: dict, *, reference_map: dict[str, str] | None = None, issue_label: str = "Issue") -> str:
    aliases = reference_map if reference_map is not None else public_reference_map(result)
    prefix = result.get('reference_prefix')
    lines = [result['narrative'], '', f"Exploration: size:{result['scope']} · {result['outcome']}"]
    if result.get('issue_ref'):
        owner = result['issue_ref']
        lines += [f"{issue_label}: {owner['repo']}#{owner['number']} · size:{owner['scope']}"]
    if prefix:
        lines += [f"Reference prefix: {prefix['code']} — {prefix['meaning']}"]
    if any(re.search(r'-H[0-9]+-', alias) for alias in aliases.values()):
        lines += ['Earlier exploration references: H1, H2, … distinguish earlier explorations locally in this comment.']
    for key in ('axes',):
        for name, content in result.get(key, {}).items():
            lines += ['', f'**{name.replace("_"," ").capitalize()}**', content]
    for item in result.get('anchors', []) + result.get('artifacts', []):
        scope = f" · size:{item['scope']}" if 'scope' in item else ''
        lines += ['', f"#### {item['id']}{scope}", item['content']]
        if item['source_refs']:
            lines.append('Source anchors: ' + ', '.join(item['source_refs']))
    for item in result.get('elements', []):
        lines += ['', f"#### {item['id']}: {item['title']} · size:{item['scope']} · {item['readiness']}",
                  item['content']]
        if item['source_refs']:
            lines.append('Source anchors: ' + ', '.join(item['source_refs']))
        lines.append(item.get('outline',''))
        for beat in item.get('beats') or []:
            lines += [f"- {beat['id']}: {beat['content']}", '  Beat references: ' + ', '.join(beat['source_refs'])]
        if item.get('development_question'):
            lines += ['Development question: ' + item['development_question'], 'Return reason: ' + item['return_reason']]
    if result.get('development_question'):
        lines += ['Development question: ' + result['development_question'], 'Return reason: ' + result['return_reason']]
    lines += ['', *[f'Question for the partner: {q}' for q in result.get('questions',[])], '']
    return readable_references('\n'.join(lines), aliases) + '\n' + encode_record(result)


def child_assignments(result: dict, *, parent_issue: int, accepted: dict, inherited: dict | None = None) -> list[dict]:
    require(result.get('phase') == '4' and result.get('outcome') == 'complete', 'only accepted Tiferet creates assignments')
    owner = result.get('issue_ref')
    if owner is not None:
        require(owner.get('number') == parent_issue and owner.get('scope') == result['scope'], 'parent issue differs from accepted result owner')
    ancestry = deepcopy(inherited.get('ancestry', []) if inherited else [])
    ancestry += [deepcopy(a) for r in accepted.values() for a in r.get('anchors',[]) + r.get('artifacts',[])]
    aliases = public_reference_map(result, ancestry)
    children = []
    for element in result['elements']:
        assignment = {'kind':'assignment', 'version':1, 'cycle_id':result['cycle_id'], 'parent_issue':parent_issue,
                      'element':deepcopy(element), 'anchors':[deepcopy(a) for a in result['anchors'] if a['id'] in element['source_refs']],
                      'canon_refs':result['canon_refs'], 'ancestry':ancestry,
                      'accepted':deepcopy({**accepted,'4':result}), 'inherited':deepcopy(inherited['anchors'] if inherited else [])}
        if owner is not None:
            assignment['parent_ref'] = deepcopy(owner)
        public = render_result({**result,'anchors':assignment['anchors'],'elements':[element]}, reference_map=aliases, issue_label='Source issue')
        public = f"Assignment scope: size:{element['scope']} · {element['readiness']}\n\n" + public
        # Body contains one assignment record; phase results belong to comments on their source issue.
        public = public.rsplit('\n',1)[0]
        placement = element.get('placement')
        if placement:
            public += f"\nEpisode manuscript: `{placement['episode']}/script.md`\nAct: {placement['act']}\nScene: {placement['scene_id']}"
        public += '\nAncestry: ' + ', '.join(aliases.get(a['id'], a['id']) for a in ancestry)
        public += '\nCanon references: ' + ', '.join(result['canon_refs'])
        children.append({'title':element['title'],'body':public + '\n\n' + encode_record(assignment),
                         'scope':element['scope'],'readiness':element['readiness'],
                         'delivery_key':f"{parent_issue}:{element['id']}"})
    return children


def validate_assignment(assignment: dict) -> dict:
    """Both development and ready assignments must retain their accepted provenance."""
    element = assignment.get('element')
    require(isinstance(element, dict), 'assignment lacks an accepted element; re-establish through Keter')
    parent = assignment.get('parent_ref')
    if parent is not None:
        require(isinstance(parent, dict) and parent.get('number') == assignment.get('parent_issue'), 'assignment parent identity mismatch')
    # Recheck the source cycle; a pasted prose label or a tampered ready flag is insufficient.
    accepted = {}
    for phase in PHASES:
        original = assignment.get('accepted',{}).get(phase)
        require(isinstance(original,dict), 'assignment lacks accepted source cycle; re-establish through Keter')
        require(original.get('outcome') == 'complete' and original.get('phase') == phase, 'assignment source cycle must contain accepted complete phase results')
        require(original.get('scope') == assignment['accepted']['1'].get('scope'), 'accepted source cycle scope mismatch')
        if parent is not None:
            require(original.get('issue_ref') == parent, 'accepted source issue differs from assignment parent')
        accepted[phase] = validate_result(original,phase=phase,cycle_id=assignment['cycle_id'],scope=original.get('scope'),
                                           accepted=accepted,inherited=assignment.get('inherited',[]))
    matches = [e for e in accepted['4']['elements'] if e['id'] == element.get('id')]
    require(matches == [element], 'assignment differs from accepted organization')
    anchors = [a for a in accepted['4']['anchors'] if a['id'] in element['source_refs']]
    require(assignment.get('anchors') == anchors, 'assignment source anchors differ from accepted organization')
    validate_element(element, {a['id'] for a in anchors})
    ancestry = assignment.get('ancestry')
    require(isinstance(ancestry, list), 'assignment ancestry must be preserved')
    nodes = {}
    for node in ancestry:
        require(isinstance(node, dict) and isinstance(node.get('id'), str), 'invalid ancestry node')
        require(node['id'] not in nodes or nodes[node['id']] == node, 'conflicting ancestry node')
        nodes[node['id']] = node
    required_nodes = [a for r in accepted.values() for a in r.get('anchors', []) + r.get('artifacts', [])]
    required_nodes += assignment.get('inherited', [])
    require(all(nodes.get(a['id']) == a for a in required_nodes), 'assignment lost accepted source ancestry')
    # Follow the whole source chain, not only the immediate parent's anchors.
    checked, visiting = set(), set()
    def visit(identifier: str) -> None:
        require(identifier in nodes, 'assignment ancestry has a missing source')
        require(identifier not in visiting, 'assignment ancestry contains a reference cycle')
        if identifier in checked:
            return
        visiting.add(identifier)
        refs = nodes[identifier].get('source_refs')
        require(isinstance(refs, list) and all(isinstance(ref, str) for ref in refs), 'invalid ancestry source references')
        for ref in refs:
            visit(ref)
        visiting.remove(identifier)
        checked.add(identifier)
    for node in required_nodes:
        visit(node['id'])
    return assignment


def ready_assignment(issue_data: dict) -> dict:
    assignment = inherited_assignment(issue_data)
    require(assignment is not None, 'legacy work must be re-established through Keter before scene preparation')
    require(issue_scope(issue_data) == 'scene', 'ready assignment requires size:scene')
    require(assignment['element'].get('readiness') == 'ready', 'issue needs a validated ready-scene assignment; return through Keter')
    return assignment
