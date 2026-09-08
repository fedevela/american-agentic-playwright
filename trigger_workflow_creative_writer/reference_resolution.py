"""Resolve model references using the labels actually shown in source material."""


def published_aliases(records):
    aliases = {}

    def collect(value):
        if isinstance(value, dict):
            for label, targets in value.get('_reference_aliases', {}).items():
                aliases.setdefault(label, set()).update(targets)
            for key, child in value.items():
                if not key.startswith('_'):
                    collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    for record in records:
        collect(record)
        if '_reference_aliases' not in record and record.get('cycle_id'):
            from .cycles import public_reference_map
            for target, label in public_reference_map(record).items():
                aliases.setdefault(label, set()).add(target)
    return aliases


def resolve_reference(value, allowed, aliases):
    from .validation import require
    if not isinstance(value, str) or value in allowed:
        return value
    targets = aliases.get(value)
    if targets:
        require(len(targets) == 1, f'ambiguous displayed reference {value}; use the exact source ID')
        return next(iter(targets))
    return value


def phase_source_beats(issue_data, phase):
    """The same immediate source beats used by phase validation."""
    from . import cycles
    if phase == '1':
        sources = cycles.source_context(issue_data).get('anchors', [])
    else:
        accepted = cycles.accepted_results(issue_data)
        if phase in {'2A', '2B', '2C'}:
            sources = accepted.get('1', {}).get('anchors', [])
        elif phase == '3':
            sources = [a for p in ('2A', '2B', '2C') for a in accepted.get(p, {}).get('artifacts', [])]
        else:
            return []
    return [beat for source in sources for beat in source.get('pivotal_beats', [])]


def retained_beat_names(beats):
    """Enumerate source identities and only unambiguous readable renames."""
    from .beat_ids import source_names
    known = {beat['id'] for beat in beats}
    lineage = known | {ref for beat in beats for ref in beat.get('source_beat_ids', [])}
    candidates = {}
    for identifier in lineage:
        for alias in source_names(identifier):
            candidates.setdefault(alias, set()).add(identifier)
    return sorted(known | {alias for alias, targets in candidates.items()
                           if len(targets) == 1 and targets <= known and alias not in lineage})


def new_beat_prefix(beats, phase):
    """Reserve a fresh readable stem outside the supplied identities and ancestry."""
    import re
    from .beat_ids import PHASE_LETTERS, source_names
    lineage = {beat['id'] for beat in beats} | {ref for beat in beats for ref in beat.get('source_beat_ids', [])}
    names = lineage | {alias for identifier in lineage for alias in source_names(identifier)}
    letter = PHASE_LETTERS[phase]
    stems = [int(match[1]) for name in names
             if (match := re.fullmatch(rf'BEAT-{letter}([1-9][0-9]*)-{phase}-[1-9][0-9]*', name))]
    return f'BEAT-{letter}{max(stems, default=0) + 1}-{phase}-'
