"""Validated, source-backed phase 7/8 handoff. Never infer identities from prose."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re

from .artifact_validation import REQUIRED_ARTIFACTS, REQUIRED_CHARACTER_ARTIFACTS
from .manuscript import scene_body, validate_scene_id
from .play_format import normalize_scene_heading, validate_public_text


SOURCE_ROLES = ("bible", "continuity", "treatment", "constraints", "skeleton")
CHARACTER_FIELDS = ("stimulus", "knows", "misunderstands", "does_not_know", "conceals",
                    "objective", "emotion", "stakes", "relationships", "dependencies")
EXCLUDED_DIRS = {".git", ".openhands", ".venv", "node_modules", "workspace", ".superpowers"}
_RAW_SKELETON_TAG = re.compile(r"</?(?:SCENE_HEADING|DIALOGUE|ACTION|PARENTHETICAL|CAMERA|LIGHTING|AUDIO|TRANSITION)\b", re.I)
_FENCE = re.compile(r" {0,3}(`{3,}|~{3,})(.*)")
_TEMPLATE_MARKER = re.compile(r"\s*<!--\s*RESOLVES\s*\[(BEAT\s+[^\]]+)\]\s*-->\s*", re.I)
_INJECT_PLACEHOLDER = re.compile(r"\[\s*INJECT\s+HERE\s*\]", re.I)


def nonempty(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing or empty {name}")
    return value


def read_source(root: Path, relative: str) -> str:
    nonempty(relative, "source path")
    path = (root / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(root.resolve()):
        raise ValueError(f"Source must be inside story checkout: {relative}")
    try:
        return nonempty(path.read_bytes().decode("utf-8"), relative)
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"Missing source: {relative}") from exc


def read_manuscript(root: Path, relative: str) -> tuple[Path, str]:
    """Read an episode manuscript without normalizing line endings."""
    nonempty(relative, "manuscript_path")
    declared = Path(relative)
    path = (root / declared).resolve()
    if declared.is_absolute() or not path.is_relative_to(root.resolve()):
        raise ValueError(f"manuscript_path must be inside story checkout: {relative}")
    try:
        return path, path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"Missing or invalid UTF-8 manuscript: {relative}") from exc


def read_sources(root: Path, sources: dict) -> dict[str, str]:
    if not isinstance(sources, dict) or set(sources) != set(SOURCE_ROLES):
        raise ValueError(f"sources must identify {', '.join(SOURCE_ROLES)}")
    result = {}
    for role, paths in sources.items():
        if not isinstance(paths, list) or not paths:
            raise ValueError(f"Missing {role} sources")
        for path in paths:
            result[path] = read_source(root, path)
    return result


def moment_references(skeleton: str) -> list[str]:
    references = re.findall(r"<!--\s*RESOLVES\s*\[(BEAT\s+[^\]]+)\]\s*-->", skeleton)
    seen = set()
    for reference in references:
        if reference in seen:
            raise ValueError(f"Repeated canonical marker: {reference}; use one marker per ordered dramatic moment")
        seen.add(reference)
    return references


def _template_moment_references(template: str) -> list[str]:
    """Return canonical marker lines outside fenced Markdown examples."""
    references = []
    fence = None
    for line in template.splitlines():
        fence_match = _FENCE.fullmatch(line)
        if fence is not None:
            if (fence_match and fence_match[1][0] == fence[0]
                    and len(fence_match[1]) >= len(fence) and not fence_match[2].strip()):
                fence = None
            continue
        if fence_match and not (fence_match[1][0] == "`" and "`" in fence_match[2]):
            fence = fence_match[1]
            continue
        marker = _TEMPLATE_MARKER.fullmatch(line)
        if marker:
            references.append(marker[1])
    return references


def _validate_scene_template(template: str, moment_ids: list[str]) -> None:
    """Ensure the public preparation template has only scene-level Markdown."""
    heading = re.match(r"[^\r\n]*", template)[0]
    normalize_scene_heading(heading)
    if re.search(r"^---\s*$", template, re.M):
        raise ValueError("scene_template.md cannot contain front matter")
    if re.search(r"^#{1,6}\s*ACT\b", template, re.I | re.M):
        raise ValueError("scene_template.md cannot contain an act heading")
    if re.search(r"<!--\s*SCENE\b", template, re.I):
        raise ValueError("scene_template.md cannot contain scene boundaries")
    if _RAW_SKELETON_TAG.search(template):
        raise ValueError("scene_template.md cannot contain raw internal skeleton tags")
    if re.search(r"<(?!\!--\s*RESOLVES\b)[^>]+>", template, re.I):
        raise ValueError("scene_template.md cannot contain raw HTML")
    first_marker = _TEMPLATE_MARKER.search(template)
    opening = template[:first_marker.start() if first_marker else len(template)]
    validate_public_text(opening)
    if _INJECT_PLACEHOLDER.search(opening):
        raise ValueError("scene_template.md cannot place a dialogue placeholder before a beat marker")
    references = _template_moment_references(template)
    # Every RESOLVES occurrence must be one of those real marker lines. Public
    # templates have no inline/fenced traceability examples for the renderer to
    # mistake for scene structure. Skeleton and renderer use uppercase markers.
    occurrences = re.findall(r"<!--\s*RESOLVES\b", template, re.I)
    if (len(occurrences) != len(references)
            or moment_references(template) != references):
        raise ValueError("scene_template.md contains a noncanonical beat marker")
    if references != moment_ids:
        raise ValueError("scene_template.md beat markers must match the brief and skeleton in order")


def read_brief(root: Path, relative="dramatic_action_brief.md") -> tuple[dict, dict[str, str]]:
    text = read_source(root, relative)
    blocks = re.findall(r"```json\s*\n(.*?)\n```", text, re.DOTALL)
    if len(blocks) != 1:
        raise ValueError("dramatic_action_brief.md requires one JSON contract block")
    try:
        brief = json.loads(blocks[0])
        nonempty(brief["scene_id"], "scene_id")
        sources = read_sources(root, brief["sources"])
        moments = brief["moments"]
        if not isinstance(moments, list) or not moments:
            raise ValueError("Missing dramatic moments")
        seen = set()
        cast = set()
        for moment in moments:
            mid = nonempty(moment["moment_id"], "moment_id")
            if mid in seen:
                raise ValueError(f"Duplicate moment: {mid}")
            seen.add(mid)
            nonempty(moment["required_outcome"], "required_outcome")
            nonempty(moment["shared_facts"], "shared_facts")
            if not isinstance(moment["characters"], list) or not moment["characters"]:
                raise ValueError(f"Missing participants for {mid}")
            moment_cast = set()
            for character in moment["characters"]:
                cid = nonempty(character["character_id"], "character_id")
                if not re.fullmatch(r"[a-zA-Z0-9_-]+", cid) or cid == "director" or cid in moment_cast:
                    raise ValueError(f"Invalid/duplicate character ID: {cid}")
                if not (root / "bible" / "characters" / cid).is_dir():
                    raise ValueError(f"Unknown bible character: {cid}")
                cast.add(cid)
                moment_cast.add(cid)
                for field in CHARACTER_FIELDS:
                    nonempty(character[field], f"{cid}.{field}")
                possibilities = character["possibilities"]
                if not isinstance(possibilities, list) or not possibilities:
                    raise ValueError(f"Missing possibilities for {cid}")
                for option in possibilities:
                    nonempty(option, "possibilities")
        skeleton = "\n".join(sources[p] for p in brief["sources"]["skeleton"])
        if moment_references(skeleton) != [m["moment_id"] for m in moments]:
            raise ValueError("Brief moments do not match canonical skeleton references and order")
        # ACTION focus may be an object; character attributes are always cast references.
        def participants(segment):
            named = set()
            for tag, attributes in re.findall(r'<([A-Z_]+)\b([^>]*)>', segment):
                for field, _, value in re.findall(r'''\b(character|focus)\s*=\s*(["'])(.*?)\2''', attributes):
                    if field == "character" or (tag == "ACTION" and field == "focus" and
                            (root / "bible" / "characters" / value).is_dir()):
                        named.add(value)
            return named

        named = participants(skeleton)
        if not named <= cast:
            raise ValueError(f"Brief omits skeleton participants: {sorted(named - cast)}")
        segments = re.split(r"<!--\s*RESOLVES\s*\[BEAT\s+[^\]]+\]\s*-->", skeleton)[1:]
        for moment, segment in zip(moments, segments):
            missing = participants(segment) - {c["character_id"] for c in moment["characters"]}
            if missing:
                raise ValueError(f"Brief moment {moment['moment_id']} omits skeleton participants: {sorted(missing)}")
        return brief, {**sources, relative: text}
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid dramatic-action brief: {exc}") from exc


@dataclass(frozen=True)
class SceneMaterials:
    directory: Path
    scene_id: str
    moment_ids: list[str]
    director_context: str
    character_contexts: dict[str, str]
    skeleton: str
    manuscript_path: Path
    scene_template: str
    display_names: dict[str, str]
    snapshots: dict[str, str]
    fingerprint: str


def discover_handoffs(root: Path) -> list[Path]:
    found = []
    for directory, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRS and d != "season_template")
        if "performance_context.json" in files:
            found.append(Path(directory) / "performance_context.json")
    return found


def load_scene(root: Path, issue: int, scene_path: str | None = None) -> SceneMaterials:
    root = Path(root).resolve()
    if scene_path:
        selected = Path(scene_path)
        if selected.is_absolute() or "season_template" in selected.parts:
            raise ValueError("--scene must select a real scene_materials directory, not season_template")
    candidates = []
    for path in discover_handoffs(root):
        if scene_path and path.parent != (root / scene_path).resolve():
            continue
        try:
            data = json.loads(read_source(root, str(path.relative_to(root))))
            if type(data.get("issue")) is not int:
                raise ValueError(f"Scene handoff issue must be an integer: {path.relative_to(root)}")
            if data.get("issue") == issue:
                candidates.append((path, data))
        except (json.JSONDecodeError, AttributeError) as exc:
            raise ValueError(f"Invalid scene handoff: {path.relative_to(root)}") from exc
    if len(candidates) != 1:
        raise ValueError(f"Expected one scene handoff for issue {issue}, found {len(candidates)}; use --scene for multiple scenes")
    path, data = candidates[0]
    scene = path.parent
    relative = lambda name: str((scene / name).relative_to(root))
    try:
        if type(data["version"]) is not int or data["version"] != 2:
            raise ValueError("performance_context version 2 migration is required; migrate version 1 handoffs")
        validate_scene_id(data["scene_id"])
        if scene.name != data["scene_id"] or scene.parent.name != "scene_materials":
            raise ValueError("Scene handoff must live in scene_materials/<scene_id>")
        episode = scene.parent.parent.resolve()
        if (episode.parent.parent != root / "Script"
                or not re.fullmatch(r"Episode_[0-9]+", episode.name)
                or not re.fullmatch(r"Season_[0-9]+", episode.parent.name)):
            raise ValueError("Scene handoff must belong to a numbered Script/Season_*/Episode_* directory")
        manuscript_path, manuscript = read_manuscript(root, data["manuscript_path"])
        if manuscript_path.name != "script.md" or manuscript_path.parent != episode:
            raise ValueError("manuscript_path must name this episode's script.md")
        brief, sources = read_brief(root, relative("dramatic_action_brief.md"))
        if any((root / p).resolve() == manuscript_path for p in sources):
            raise ValueError("The mutable script manuscript cannot be an immutable source; reference scene_skeleton.md or the phase-6 source")
        if data["sources"] != brief["sources"] or data["scene_id"] != brief["scene_id"]:
            raise ValueError("Brief and scene handoff disagree on sources/scene")
        mids = [m["moment_id"] for m in brief["moments"]]
        if data["required_moment_ids"] != mids:
            raise ValueError("Brief and handoff disagree on dramatic moments")
        skeleton = read_source(root, relative("scene_skeleton.md"))
        original = "\n".join(sources[p] for p in data["sources"]["skeleton"])
        if skeleton != original:
            raise ValueError("Preserved skeleton differs from phase 6 source")
        scene_template = read_source(root, relative("scene_template.md"))
        _validate_scene_template(scene_template, mids)
        # This validates every boundary in the manuscript. A performed selected
        # region is legitimate after phase 8, so equality is enforced only by
        # the phase-8 readiness gate below.
        scene_body(manuscript, data["scene_id"])
        anchor = read_source(root, relative("AGENTS.md"))
        if any(p not in anchor for paths in data["sources"].values() for p in paths):
            raise ValueError("AGENTS.md must reference all director source paths")
        cast = {c["character_id"] for m in brief["moments"] for c in m["characters"]}
        if set(data["characters"]) != cast:
            raise ValueError("Brief and handoff disagree on participating characters")
        contexts = {}
        display_names = {}
        for cid, character in data["characters"].items():
            known = nonempty(character["known_context"], f"{cid}.known_context")
            private = nonempty(character["private_context"], f"{cid}.private_context")
            display_name = nonempty(character["display_name"], f"{cid}.display_name")
            if display_name.splitlines() != [display_name]:
                raise ValueError(f"{cid}.display_name must be single-line text")
            display_names[cid] = display_name
            paths = character["persona_paths"]
            if not isinstance(paths, list) or not paths:
                raise ValueError(f"Missing persona assets for {cid}")
            own = {}
            paths = list(dict.fromkeys([*paths, *(f"bible/characters/{cid}/{name}" for name in REQUIRED_CHARACTER_ARTIFACTS)]))
            for persona_path in paths:
                expected = root / "bible" / "characters" / cid
                if not (root / persona_path).resolve().is_relative_to(expected.resolve()):
                    raise ValueError(f"Persona path belongs to another character: {cid}")
                own[persona_path] = read_source(root, persona_path)
            sources.update(own)
            contexts[cid] = json.dumps({"character_id": cid, "persona": own,
                                       "known_context": known, "private_context": private}, ensure_ascii=False)
        # The runner enforces the world's required-artifact gate. Include all of
        # those sources when present, even if the index accidentally omits one.
        for name in REQUIRED_ARTIFACTS:
            if (root / name).is_file():
                sources[name] = read_source(root, name)
        sources.update({relative("AGENTS.md"): anchor, relative("scene_skeleton.md"): skeleton,
                        relative("scene_template.md"): scene_template,
                        relative("performance_context.json"): path.read_bytes().decode("utf-8")})
        context = json.dumps({"handoff": data, "sources": sources}, ensure_ascii=False)
        fingerprint = hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest()
        return SceneMaterials(scene, data["scene_id"], mids, context, contexts, skeleton,
                              manuscript_path, scene_template, display_names, sources, fingerprint)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f"Incomplete scene handoff: {exc}") from exc


def validate_phase_artifacts(root: Path, phase: str, issue: int) -> None:
    if phase == "7":
        read_brief(Path(root))
    elif phase == "8":
        from . import config
        scene = load_scene(root, issue, getattr(config, "SCENE_PATH", None))
        _, manuscript = read_manuscript(Path(root), str(scene.manuscript_path.relative_to(Path(root).resolve())))
        if scene_body(manuscript, scene.scene_id) != scene.scene_template:
            raise ValueError("Phase 8 manuscript scene template must be preserved exactly, without drafting")
        if (Path(root) / "dramatic_action_brief.md").read_bytes() != (scene.directory / "dramatic_action_brief.md").read_bytes():
            raise ValueError("Phase 8 must preserve and copy the source brief unchanged")
    else:
        raise ValueError(f"No artifact-only completion gate for phase {phase}")
