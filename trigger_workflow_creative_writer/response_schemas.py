"""Structured Codex output for creative exploration phases."""

from .validation import AXES, GENERATED_SCOPES, SCOPES


def _object(properties):
    return {'type': 'object', 'properties': properties,
            'required': list(properties), 'additionalProperties': False}


def _array(items):
    return {'type': 'array', 'items': items}


def _nullable(schema):
    return {'anyOf': [schema, {'type': 'null'}]}


def phase_response_schema(phase: str) -> dict:
    """Constrain response shape; validate_result checks meaning and source coverage."""
    string = {'type': 'string'}
    refs = _array(string)
    material = {'content': string, 'source_refs': refs}
    properties = {
        'cycle_id': string,
        'scope': {'type': 'string', 'enum': sorted(SCOPES)},
        'outcome': {'type': 'string', 'enum': ['complete', 'develop', 'question', 'failure']},
        'narrative': string, 'questions': refs, 'canon_refs': refs,
        'development_question': string, 'return_reason': string,
    }
    if phase == '1':
        properties.update(
            reference_prefix=_nullable(_object({'code': string, 'meaning': string})),
            axes=_nullable(_object({axis: string for axis in AXES})),
            anchors=_array(_object(material)),
        )
    elif phase in {'2A', '2B', '2C'}:
        properties['artifacts'] = _array(_object({
            **material, 'scope': {'type': 'string', 'enum': sorted(GENERATED_SCOPES)},
        }))
    elif phase == '3':
        properties['anchors'] = _array(_object(material))
        properties['elements'] = _array(_object({
            'title': string, 'scope': {'type': 'string', 'enum': sorted(GENERATED_SCOPES)},
            'readiness': {'type': 'string', 'enum': ['ready', 'develop']},
            **material, 'outline': string,
            'development_question': string, 'return_reason': string,
            'placement': _nullable(_object({
                'episode': string, 'act': string, 'scene_id': string,
            })),
            'beats': _array(_object(material)),
        }))
    elif phase == '4':
        properties['assignments'] = _array(_object({'element_id': string, 'outline': string}))
    else:
        raise ValueError(f'Unsupported structured creative phase: {phase}')
    return _object(properties)
