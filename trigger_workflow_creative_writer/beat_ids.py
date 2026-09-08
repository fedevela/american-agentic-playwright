"""Readable beat names; owning cycle and issue remain on their result records."""
import re


PHASE_LETTERS = {'1': 'K', '2A': 'CH', '2B': 'B', '2C': 'C', '3': 'G'}
READABLE_ID = re.compile(r'BEAT-(K|CH|B|C|G)[1-9][0-9]*-(1|2A|2B|2C|3)-[1-9][0-9]*')
LEGACY_ID = re.compile(r'BEAT-([A-Za-z0-9_-]+)-(1|2A|2B|2C|3)-([1-9][0-9]*)')


def is_readable(identifier):
    match = READABLE_ID.fullmatch(identifier)
    return bool(match and match[1] == PHASE_LETTERS[match[2]])


def legacy_readable_id(identifier):
    """A display label plus its origin phase and number, never a new cycle ID."""
    if is_readable(identifier):
        return None
    match = LEGACY_ID.fullmatch(identifier)
    if match:
        return f'BEAT-{PHASE_LETTERS[match[2]]}{match[3]}-{match[2]}-{match[3]}'
    return None


def source_names(identifier):
    """Accepted readable spellings of a cycle-qualified source beat."""
    alias = legacy_readable_id(identifier)
    if not alias:
        return set()
    match = LEGACY_ID.fullmatch(identifier)
    return {alias, f'BEAT-{PHASE_LETTERS[match[2]]}1-{match[2]}-{match[3]}'}
