"""Read and write visible workflow Markdown; no hidden story storage or resolver."""
from __future__ import annotations

import re
from copy import deepcopy

from .validation import require

# These are presentation fields, not an encoded copy of the story. Prose is read
# from the same paragraphs a person reads and edits on GitHub.
FIELDS = {
    'cycle_id': 'Cycle', 'phase': 'Phase', 'scope': 'Scope', 'outcome': 'Outcome',
    'readiness': 'Readiness', 'narrative': 'Narrative', 'content': 'Dramatic purpose',
    'title': 'Title', 'outline': 'Outline', 'development_question': 'Development question',
    'return_reason': 'Return reason', 'source_refs': 'Sources',
    'source_beat_ids': 'Predecessor beats', 'pivotal_beat_id': 'Pivotal beat',
    'is_pivotal': 'Is pivotal', 'element_id': 'Element', 'issue': 'Issue',
    'summary': 'Summary', 'episode': 'Episode', 'act': 'Act', 'scene_id': 'Scene',
    'code': 'Code', 'meaning': 'Meaning', 'prior_cycle': 'Previous cycle',
    'parent_issue': 'Parent issue', 'source_comment': 'Source comment',
}
from .validation import AXES
FIELDS.update({axis: axis.replace('_', ' ').capitalize() for axis in AXES})
COLLECTIONS = {'anchors': 'Supporting dramatic anchors', 'artifacts': 'Exploration',
               'elements': 'Elements for issue creation', 'beats': 'Beats',
               'pivotal_beats': 'Pivotal beats', 'assignments': 'Assignments'}
OBJECTS = {'axes': 'Dramatic axes', 'reference_prefix': 'Reference prefix', 'placement': 'Placement'}
LIST_FIELDS = {'source_refs', 'source_beat_ids'}
OMIT = {'version', 'kind', 'id', 'questions', 'pivotal_beat', 'canon_refs', 'source_refs',
        'inputs', 'inherited_anchors', 'inherited_ancestry', 'ancestry', 'accepted',
        'issue_ref', 'parent_ref', 'season_ref', 'beat_identity_version', 'pivotal_contract_version'}
ROOT = re.compile(r'^## Workflow (cycle|result|assignment|final-delivery)\s*$', re.MULTILINE)
PHASE_HEADING = re.compile(r'^### Phase (1|2A|2B|2C|3|4):[^\n]*$', re.MULTILINE)
SECTION = re.compile(r'^(#{3,6}) (.+)$')
FIELD = re.compile(r'^\*\*([^*]+):\*\*\s*$')
LINK = re.compile(r'^\[([^\]]+)\]\(#([^\s)]+)\)$')
STATUS_HEADINGS = {'### Further development': 'develop', '### Execution failure': 'failure'}


def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items() if not k.startswith('_')}
    if isinstance(value, list):
        return [clean(v) for v in value]
    return value


def source(value):
    require(isinstance(value.get('_source'), dict), 'material has no published issue comment')
    return deepcopy(value['_source'])


def source_url(locator):
    return f"https://github.com/{locator['repo']}/issues/{locator['issue']}#issuecomment-{locator['comment']}"


def render(record, aliases=None):
    """Publish only this phase's material, with visible routing and identity fields."""
    aliases = aliases or {}
    if record['kind'] == 'cycle':
        return ''
    lines = [] if record['kind'] == 'result' else [f"## Workflow {record['kind']}", '']
    for heading, outcome in STATUS_HEADINGS.items():
        if record.get('outcome') == outcome:
            lines.extend([heading, ''])

    def identifier(value):
        return f'[{aliases[value]}](#{value})' if value in aliases else value

    def walk(value, level):
        names = sorted(value, key=lambda n: (n in COLLECTIONS or n in OBJECTS,
                       {'narrative': -8, 'content': -7, 'cycle_id': -6, 'phase': -5, 'scope': -4, 'outcome': -3,
                        'elements': -1, 'anchors': 1}.get(n, 0)))
        for name in names:
            child = value[name]
            if value is record and record['kind'] == 'result' and name in {'cycle_id', 'phase', 'scope', 'outcome', 'reference_prefix'}:
                continue
            if value is not record and name in {'title', 'is_pivotal'}:
                continue
            if (name == 'change' and 'source_beat_ids' in value) or name in OMIT or name.startswith('_') or child is None or child == '' or child == []:
                continue
            if name in COLLECTIONS:
                collapse = name == 'anchors' and record.get('phase') == '3'
                if collapse:
                    lines.extend(['<details>', '<summary>Supporting dramatic anchors</summary>', ''])
                if not collapse:
                    lines.extend(['#' * level + ' ' + COLLECTIONS[name], ''])
                if name == 'elements':
                    lines.extend(['E means element. Each accepted element becomes one issue.', ''])
                for index, item in enumerate(child, 1):
                    item_id = item.get('id') or item.get('element_id') or str(index)
                    title = ' — ' + item['title'] if item.get('title') else ''
                    require('\n' not in title and '\r' not in title, 'item title must be one line')
                    lines.extend(['#' * (level + 1) + ' Item ' + identifier(item_id) + title, ''])
                    walk(item, level + 2)
                if collapse:
                    lines.extend(['</details>', ''])
            elif name in OBJECTS:
                lines.extend(['#' * level + ' ' + OBJECTS[name], ''])
                walk(child, level + 1)
            elif name in FIELDS:
                if name not in {'narrative', 'content'}:
                    lines.extend(['**' + FIELDS[name] + ':**', ''])
                if name in LIST_FIELDS:
                    lines.extend('- ' + identifier(ref) for ref in child)
                else:
                    text = ('yes' if child else 'no') if isinstance(child, bool) else str(child)
                    if name == 'scope' and text == 'undetermined':
                        text = 'scope to be discovered'
                    if name in {'pivotal_beat_id', 'element_id'}:
                        text = identifier(text)
                    # Reserve our small Markdown vocabulary, not arbitrary prose headings.
                    require(not any(line in STATUS_HEADINGS or PHASE_HEADING.match(line) or ROOT.match(line) or (FIELD.match(line) and FIELD.match(line)[1] in FIELDS.values())
                                    or (SECTION.match(line) and (SECTION.match(line)[2] in set(COLLECTIONS.values()) | set(OBJECTS.values())
                                        or SECTION.match(line)[2].startswith('Item '))) for line in text.splitlines()),
                            'prose uses a reserved workflow heading; rephrase that heading')
                    lines.append(text)
                lines.append('')
    walk(record, 3)
    return '\n'.join(lines).rstrip()


def public_markdown(body):
    """Old annotations may remain in history; they are never interpreted as memory."""
    return re.sub(r'<!--.*?-->', '', str(body), flags=re.DOTALL).strip()


def prompt_value(value):
    if isinstance(value, dict):
        return {k: prompt_value(v) for k, v in value.items()
                if not k.startswith('_') and k not in OMIT - {'id', 'pivotal_beat'}}
    if isinstance(value, list):
        return [prompt_value(v) for v in value]
    return value


def read(body, *, location=None):
    """Parse visible field labels and headings. Human comments need no structure."""
    body = public_markdown(body)
    starts = list(ROOT.finditer(body))
    phase_heading = PHASE_HEADING.search(body) if not starts else None
    if phase_heading:
        starts = [phase_heading]
    records = []
    fields = {label: name for name, label in FIELDS.items()}
    sections = {label: name for name, label in {**COLLECTIONS, **OBJECTS}.items()}

    def identity(text):
        match = LINK.fullmatch(text)
        if match:
            targets = record.setdefault('_reference_aliases', {}).setdefault(match[1], [])
            if match[2] not in targets:
                targets.append(match[2])
        return match[2] if match else text

    for index, start in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(body)
        record = {'kind': 'result' if phase_heading else start[1], 'version': 1}
        stack = [(2, record)]
        pending = (record, 'narrative') if phase_heading else None
        buffer = []

        def flush():
            nonlocal pending, buffer
            if pending:
                target, name = pending
                text = '\n'.join(buffer).strip()
                if not text and name in {'narrative', 'content'}:
                    pending, buffer = None, []
                    return
                require(name not in target, f'duplicate visible workflow field: {name}')
                if name in LIST_FIELDS:
                    target[name] = [identity(line[2:]) for line in text.splitlines() if line.startswith('- ')]
                elif name == 'is_pivotal':
                    require(text in {'yes', 'no'}, 'Is pivotal must be yes or no')
                    target[name] = text == 'yes'
                elif name in {'parent_issue', 'source_comment', 'issue'}:
                    require(text.isdigit(), f'{name} must be an issue/comment number')
                    target[name] = int(text)
                elif name == 'scope' and text == 'scope to be discovered':
                    target[name] = 'undetermined'
                else:
                    target[name] = identity(text) if name in {'element_id', 'pivotal_beat_id'} else text
            pending, buffer = None, []

        for line in body[start.end():end].splitlines():
            if line in STATUS_HEADINGS:
                flush()
                record['outcome'] = STATUS_HEADINGS[line]
                pending = (record, 'narrative')
                continue
            if line == '<summary>Supporting dramatic anchors</summary>':
                # Older comments also contain the collection heading inside the
                # disclosure; let that heading handle those records.
                if '### Supporting dramatic anchors' in body[start.end():end]:
                    continue
                line = '### Supporting dramatic anchors'
            if line in {'<details>', '</details>'}:
                continue
            heading, field = SECTION.match(line), FIELD.match(line)
            if heading and (heading[2] in sections or heading[2].startswith('Item ')):
                flush()
                level, label = len(heading[1]), heading[2]
                while stack[-1][0] >= level:
                    stack.pop()
                parent = stack[-1][1]
                if label.startswith('Item '):
                    require(isinstance(parent, list), 'workflow item has no collection')
                    item_label, separator, title = label[5:].partition(' — ')
                    node = {'id': identity(item_label)}
                    link = LINK.fullmatch(item_label)
                    if link:
                        # Preserve the displayed name when an anchor/beat is
                        # copied into a child's inherited source material.
                        node['_reference_aliases'] = {link[1]: [link[2]]}
                    if separator:
                        node['title'] = title
                    alias = LINK.fullmatch(item_label)
                    if alias and re.fullmatch(r'[A-Z]{2,12}-K[1-9][0-9]*', alias[1]):
                        record.setdefault('reference_prefix', {'code': alias[1].split('-')[0], 'meaning': 'Project reference'})
                    parent.append(node)
                    pending = (node, 'content')
                else:
                    require(isinstance(parent, dict), 'workflow section has no parent')
                    name = sections[label]
                    require(name not in parent, f'duplicate workflow section: {name}')
                    node = [] if name in COLLECTIONS else {}
                    parent[name] = node
                stack.append((level, node))
            elif field and field[1] in fields:
                flush()
                require(isinstance(stack[-1][1], dict), 'workflow field has no item')
                pending = (stack[-1][1], fields[field[1]])
            elif pending:
                buffer.append(line)
        flush()
        if phase_heading:
            record['phase'] = phase_heading[1]
            if 'outcome' not in record and not any(k in record for k in ('anchors', 'artifacts', 'assignments')):
                continue  # Earlier prose and delivery summaries are not results.
            record.setdefault('outcome', 'complete')
        if record['kind'] == 'result':
            record.setdefault('questions', [])
            record.setdefault('development_question', '')
            record.setdefault('return_reason', '')
            for name in ('anchors', 'artifacts'):
                for item in record.get(name, []):
                    for beat in item.get('pivotal_beats', []):
                        beat.setdefault('source_beat_ids', [])
                    if record.get('phase') == '1' and item.get('pivotal_beats'):
                        item['pivotal_beat'] = item['pivotal_beats'][0]['content']
            for item in record.get('elements', []):
                for name in ('outline', 'development_question', 'return_reason'):
                    item.setdefault(name, '')
                item.setdefault('placement', None)
                for beat in item.get('beats', []):
                    beat.setdefault('pivotal_beat_id', None)
                    beat.setdefault('is_pivotal', beat['pivotal_beat_id'] is not None)
            for item in record.get('assignments', []):
                item.pop('id', None)
                item.setdefault('outline', '')
        if location:
            record['_source'] = dict(location)
        records.append(record)
    return records
