"""Locate and replace bounded scene bodies without changing surrounding text."""
from __future__ import annotations

import re


SCENE_ID = re.compile(r"[A-Za-z0-9_-]+")
_BOUNDARY = re.compile(r"<!-- SCENE ([A-Za-z0-9_-]+) (BEGIN|END) -->")
_FENCE = re.compile(r" {0,3}(`{3,}|~{3,})(.*)")


def validate_scene_id(scene_id: str) -> str:
    if not isinstance(scene_id, str) or not SCENE_ID.fullmatch(scene_id):
        raise ValueError("scene_id must contain only letters, numbers, underscores or hyphens")
    return scene_id


def _scene_regions(text: str) -> dict[str, tuple[int, int]]:
    regions = {}
    active = None
    fence = None
    offset = 0
    for line in text.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        fence_match = _FENCE.fullmatch(content)
        if fence is not None:
            if (fence_match and fence_match[1][0] == fence[0]
                    and len(fence_match[1]) >= len(fence) and not fence_match[2].strip()):
                fence = None
        elif fence_match and not (fence_match[1][0] == '`' and '`' in fence_match[2]):
            fence = fence_match[1]
        else:
            match = _BOUNDARY.fullmatch(content)
            if match:
                scene_id, kind = match.groups()
                if kind == "BEGIN":
                    if active is not None or scene_id in regions:
                        raise ValueError(f"Nested or duplicate scene boundary: {scene_id}")
                    active = (scene_id, offset + len(line))
                else:
                    if active is None or active[0] != scene_id:
                        raise ValueError(f"Unbalanced scene boundary: {scene_id}")
                    regions[scene_id] = (active[1], offset)
                    active = None
        offset += len(line)
    if active is not None:
        raise ValueError(f"Missing END scene boundary: {active[0]}")
    return regions


def _region(text: str, scene_id: str) -> tuple[int, int]:
    validate_scene_id(scene_id)
    regions = _scene_regions(text)
    if scene_id not in regions:
        raise ValueError(f"Missing scene boundary for {scene_id}")
    return regions[scene_id]


def scene_body(manuscript: str, scene_id: str) -> str:
    """Return the exact text between the selected scene's complete marker lines."""
    start, end = _region(manuscript, scene_id)
    return manuscript[start:end]


def replace_scene(manuscript: str, scene_id: str, rendered: str) -> str:
    """Replace a unique scene body, preserving both markers and all outside text."""
    start, end = _region(manuscript, scene_id)
    if re.search(r"<!--\s*SCENE\b", rendered, re.I):
        raise ValueError("Rendered public text cannot introduce scene boundaries")
    if rendered and not rendered.endswith('\n'):
        raise ValueError("Rendered scene must end with a newline before its END boundary")
    result = manuscript[:start] + rendered + manuscript[end:]
    _region(result, scene_id)
    return result
