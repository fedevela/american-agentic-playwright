"""Structured Codex output for creative exploration phases."""

from .validation import AXES, GENERATED_SCOPES, SCOPES


def _object(properties):
    return {'type': 'object', 'properties': properties,
            'required': list(properties), 'additionalProperties': False}


def _array(items):
    return {'type': 'array', 'items': items}


def _nullable(schema):
    return {'anyOf': [schema, {'type': 'null'}]}


def phase_response_schema(phase: str, *, retained_ids: list[str] | None = None, new_prefix: str | None = None) -> dict:
    """Constrain response shape; validate_result checks readiness and pivotal beat continuity."""
    string = {'type': 'string'}
    refs = _array(string)
    material = {'content': string}
    beat_id = {'type': 'string', 'pattern': r'^BEAT-[A-Za-z0-9_-]+-(1|2A|2B|2C|3)-[1-9][0-9]*$'}
    if retained_ids is not None and phase in {'1', '2A', '2B', '2C', '3'}:
        from .beat_ids import PHASE_LETTERS
        new_id = {'type': 'string', 'pattern': rf'^BEAT-{PHASE_LETTERS[phase]}[1-9][0-9]*-{phase}-[1-9][0-9]*$'}
        if new_prefix is not None:
            import re
            new_id['pattern'] = '^' + re.escape(new_prefix) + '[1-9][0-9]*$'
        beat_id = {'anyOf': [{'type': 'string', 'enum': retained_ids}, new_id]} if retained_ids else new_id
    pivotal_beats = _array(_object({
        'id': beat_id,
        'content': string, 'source_beat_ids': refs,
    }))
    tracked_material = {**material, 'pivotal_beats': pivotal_beats}
    properties = {
        'scope': {'type': 'string', 'enum': sorted(SCOPES)},
        'outcome': {'type': 'string', 'enum': ['complete', 'develop', 'failure']},
        'narrative': string, 'questions': refs,
        'development_question': string, 'return_reason': string,
    }
    if phase == '1':
        properties.update(
            reference_prefix=_nullable(_object({'code': string, 'meaning': string})),
            axes=_nullable(_object({axis: string for axis in AXES})),
            anchors=_array(_object({**tracked_material, 'pivotal_beat': string})),
        )
    elif phase in {'2A', '2B', '2C'}:
        properties['artifacts'] = _array(_object({
            **tracked_material, 'scope': {'type': 'string', 'enum': sorted(GENERATED_SCOPES)},
        }))
    elif phase == '3':
        properties['anchors'] = _array(_object(tracked_material))
        properties['elements'] = _array(_object({
            'title': string, 'scope': {'type': 'string', 'enum': sorted(GENERATED_SCOPES)},
            'readiness': {'type': 'string', 'enum': ['ready', 'develop']},
            **material, 'outline': string,
            'development_question': string, 'return_reason': string,
            'placement': _nullable(_object({
                'episode': string, 'act': string, 'scene_id': string,
            })),
            'beats': _array(_object({**material, 'is_pivotal': {'type': 'boolean'},
                                     'pivotal_beat_id': _nullable(string)})),
        }))
    elif phase == '4':
        properties['assignments'] = _array(_object({'element_id': string, 'outline': string,
            'scope': {'type': 'string', 'enum': ['episode', 'act', 'scene']}}))
    else:
        raise ValueError(f'Unsupported structured creative phase: {phase}')
    return _object(properties)
