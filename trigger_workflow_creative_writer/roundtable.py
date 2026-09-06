"""Serial native-session performance with durable, fail-closed checkpoints.

The private registry belongs outside the story checkout. Native calls and external
delivery cannot be transacted with local files: an outstanding journal entry must
be reconciled by an operator, never automatically replayed.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Callable
import uuid

from . import config
from .codex_runner import call_codex, codex_fingerprint
from .scene_materials import load_scene


def _object(properties):
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


STRING = {"type": "string"}
IDS = {"type": "array", "items": STRING}
DIRECTOR_SCHEMA = _object({
    "turn_id": STRING, "status": {"type": "string", "enum": ["continue", "complete"]},
    "moment_id": STRING, "private_direction": STRING,
    "stage_events": {"type": "array", "items": _object({"text": STRING, "observers": IDS})},
    "next_speaker": {"type": ["string", "null"]}, "character_prompt": STRING,
    "completed_moment_ids": IDS, "previous_response_observers": IDS,
})
ACTOR_SCHEMA = _object({
    "turn_id": STRING, "character_id": STRING, "inner_monologue": STRING,
    "outer_response": _object({"action": STRING, "dialogue": STRING, "silence": {"type": "boolean"}}),
})

DIRECTOR_RULES = """You are the omniscient fictional scene director. Your native session persists.
Return ONLY the requested JSON object; do not write files, run tools, or perform delivery.
Use the full story canon, character secrets, and latest complete character response
(including authored fictional inner monologue) to decide a playable next stimulus.
Do not force dialogue: action, refusal, restraint and deliberate silence are valid.
Your private_direction is private. Public narration and addressed prompts must not
imply unrevealed secrets are already known in-story; reveal them explicitly through
an observable in-scene event when justified. Assign each stage event its actual
observers. previous_response_observers routes only the preceding character's outer
response to its witnesses; do not repeat that action in stage_events. Use [] before
the first actor response. Sleeping characters are not called until selected.
Advance canonical moments in order. Completed moment IDs may only grow and must
already have an actual external character performance. Complete only with all
required moments covered and next_speaker=null. A continue needs a known speaker
and nonempty character_prompt. Preserve production and dramatic constraints.
Never output placeholders or empty dialogue vessels. Echo the provided turn_id.
"""
ACTOR_RULES = """You perform one fictional character in one persistent native session.
Return ONLY the requested JSON object; do not write files, run tools, or deliver.
Author inner_monologue as fictional character text and outer_response in the same
turn. Only the outer response reaches other characters and the script. Author-visible
canon is not automatically your character's in-story knowledge. Use only your own
known context and the supplied perceivable observations to update your state.
Keep accumulated emotions, relationships, and decisions; do not reset to your initial
state. Choose your own action: dialogue is optional, deliberate silence is valid.
Provide a nonempty action or dialogue, or silence=true. Do not narrate another
character's private knowledge. Preserve addressed constraints and echo turn_id.
"""


def _validate_schema(value, schema, path="response"):
    """Validate the small, explicit JSON Schema subset used by both role contracts."""
    types = schema["type"]
    types = types if isinstance(types, list) else [types]
    actual = ("null" if value is None else "boolean" if type(value) is bool else
              "string" if isinstance(value, str) else "array" if isinstance(value, list) else
              "object" if isinstance(value, dict) else "number")
    if actual not in types:
        raise ValueError(f"{path} must have type {types}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"Invalid {path}")
    if actual == "object":
        if set(value) != set(schema["required"]):
            raise ValueError(f"Missing or extra fields in {path}")
        for name, child in value.items():
            _validate_schema(child, schema["properties"][name], f"{path}.{name}")
    if actual == "array":
        for index, child in enumerate(value):
            _validate_schema(child, schema["items"], f"{path}[{index}]")
        if schema is IDS and len(set(value)) != len(value):
            raise ValueError(f"Duplicate identifiers in {path}")


def _uuid(value):
    if not isinstance(value, str):
        raise ValueError("Missing canonical UUID")
    try:
        valid = str(uuid.UUID(value)) == value
    except ValueError:
        valid = False
    if not valid:
        raise ValueError(f"Invalid canonical UUID: {value!r}")
    return value


def _hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _atomic(path: Path, value, *, raw=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = value if raw else json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)
    fd, temporary = tempfile.mkstemp(prefix=".checkpoint-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def _lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError(f"Performance registry/run lock is held: {path}") from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def _read(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Invalid/incomplete checkpoint {path}; reconcile before continuing") from exc


def _script_check(scene, state):
    script = scene.directory / "script.md"
    try:
        current = _hash(script.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError("Scene script unexpectedly changed or is missing") from exc
    allowed = {state["initial_script_hash"]}
    if state.get("rendered_script_hash"):
        allowed.add(state["rendered_script_hash"])
    if current not in allowed:
        raise ValueError("Scene script unexpectedly changed; reconcile the external edit")


def _public_text(text):
    if (re.search(r"\[\s*(?:INJECT\s+HERE|TODO|TBD)\s*\]", text, re.I)
            or re.search(r"^\s*(?:TODO|TBD)(?:\s*:.*)?\s*$", text, re.M)):
        raise ValueError("Unresolved placeholder in public performance")
    if re.search(r"<DIALOGUE\b[^>]*(?:/\s*>|>\s*</DIALOGUE\s*>)", text, re.I):
        raise ValueError("Empty dialogue vessel in public performance")


def _validate_turn(response, state, scene):
    role = state["next_role"]
    _validate_schema(response, DIRECTOR_SCHEMA if role == "director" else ACTOR_SCHEMA)
    turn_id = response["turn_id"]
    if turn_id != state["pending"]["turn_id"] or turn_id in state["accepted_turn_ids"]:
        raise ValueError("Wrong or duplicate accepted turn_id")
    if role != "director":
        if response["character_id"] != role:
            raise ValueError("Invalid character_id for pending participant")
        outer = response["outer_response"]
        if not (outer["action"].strip() or outer["dialogue"].strip() or outer["silence"]):
            raise ValueError("Character must perform an external action, dialogue, or deliberate silence")
        _public_text(outer["action"])
        _public_text(outer["dialogue"])
        return
    mid = response["moment_id"]
    if mid not in scene.moment_ids:
        raise ValueError("Unknown moment_id")
    index = scene.moment_ids.index(mid)
    previous_index = scene.moment_ids.index(state["moment_id"]) if state["moment_id"] else 0
    if index < previous_index or index > previous_index + 1 or (state["moment_id"] is None and index != 0):
        raise ValueError("Moment progression must follow canonical order without regression")
    completed = set(response["completed_moment_ids"])
    if not set(state["completed_moment_ids"]) <= completed:
        raise ValueError("Completed moment set cannot shrink")
    if not completed <= set(scene.moment_ids) or not completed <= set(state["performed_moment_ids"]):
        raise ValueError("Cannot complete an unknown or unperformed moment")
    if index > previous_index and scene.moment_ids[previous_index] not in completed:
        raise ValueError("Previous moment must be performed and completed before advancement")
    cast = set(scene.character_contexts)
    observer_lists = [response["previous_response_observers"]]
    if state["latest_response"] is None and response["previous_response_observers"]:
        raise ValueError("First director turn has no previous response observers")
    for event in response["stage_events"]:
        if not event["text"].strip():
            raise ValueError("Stage event must be nonempty")
        _public_text(event["text"])
        observer_lists.append(event["observers"])
    for observers in observer_lists:
        if not set(observers) <= cast:
            raise ValueError("Unknown observer ID")
    if response["status"] == "complete":
        if response["next_speaker"] is not None or completed != set(scene.moment_ids):
            raise ValueError("Complete requires null speaker and complete moment coverage")
    elif response["next_speaker"] not in cast or not response["character_prompt"].strip():
        raise ValueError("Continue requires known next speaker and addressed prompt")
    _public_text(response["character_prompt"])


def _request(state, scene):
    role = state["next_role"]
    request = {"role": role, "turn_id": state["pending"]["turn_id"]}
    if role not in state["sessions"]:
        request["bootstrap"] = {"rules": DIRECTOR_RULES if role == "director" else ACTOR_RULES,
                                "context": scene.director_context if role == "director" else scene.character_contexts[role]}
    request["checkpoint"] = {"moment_id": state["moment_id"], "completed_moment_ids": state["completed_moment_ids"]}
    if role == "director":
        request["latest_response"] = state["latest_response"]
        request["public_current_state"] = state["public_events"][-8:]
    else:
        request["observations"] = state["observations"][role][state["observation_cursors"][role]:]
        request["addressed_instruction"] = state["character_prompt"]
    return request


def _accept(state, response):
    """Build a complete next checkpoint; caller publishes it in one atomic replace."""
    result = copy.deepcopy(state)
    role = state["next_role"]
    turn_id = response["turn_id"]
    if turn_id in state["accepted_turn_ids"]:
        raise ValueError("Duplicate accepted turn_id")
    if role == "director":
        latest = state["latest_response"]
        if latest is not None:
            observed = {"kind": "character", "turn_id": latest["turn_id"],
                        "moment_id": latest["moment_id"], "character_id": latest["character_id"],
                        "outer_response": latest["outer_response"]}
            for observer in response["previous_response_observers"]:
                result["observations"][observer].append(observed)
        for event in response["stage_events"]:
            public = {"kind": "stage", "moment_id": response["moment_id"], "turn_id": turn_id, "text": event["text"]}
            result["public_events"].append(public)
            for observer in event["observers"]:
                result["observations"][observer].append(public)
        progressed = state["moment_id"] != response["moment_id"] or set(state["completed_moment_ids"]) != set(response["completed_moment_ids"])
        result["no_progress"] = 0 if progressed else state["no_progress"] + 1
        result["moment_id"] = response["moment_id"]
        result["completed_moment_ids"] = response["completed_moment_ids"]
        result["next_role"] = response["next_speaker"]
        result["character_prompt"] = response["character_prompt"]
        if response["status"] == "complete":
            result["status"] = "completed"
    else:
        latest = dict(response, moment_id=state["moment_id"])
        result["latest_response"] = latest
        result["public_events"].append({"kind": "character", "moment_id": state["moment_id"],
                                        "turn_id": turn_id, "character_id": role,
                                        "outer_response": response["outer_response"]})
        if state["moment_id"] not in result["performed_moment_ids"]:
            result["performed_moment_ids"].append(state["moment_id"])
        result["observation_cursors"][role] = len(state["observations"][role])
        result["next_role"] = "director"
    result["accepted_turn_ids"].append(turn_id)
    result["accepted_turns"].append({"turn_id": turn_id, "participant": role,
                                      "session_id": state["sessions"][role]})
    result["pending"] = None
    return result


def _production_constraints(skeleton):
    # Actor objectives/subtext and unperformed prescribed choices remain available
    # in immutable source snapshots, but are not part of the public performance.
    skeleton = re.sub(r"<(DIALOGUE|ACTION|PARENTHETICAL)\b[^>]*(?:/\s*>|>.*?</\1\s*>)", "", skeleton, flags=re.I | re.S)
    allowed = "SCENE_HEADING|CAMERA|LIGHTING|AUDIO|TRANSITION"
    pattern = rf"<!--\s*RESOLVES\s*\[BEAT\s+[^\]]+\]\s*-->|<({allowed})\b[^>]*(?:/\s*>|>.*?</\1\s*>)"
    public = "\n".join(match.group(0) for match in re.finditer(pattern, skeleton, re.I | re.S))
    _public_text(public)
    return public


def _render(scene, state):
    if state["status"] not in {"completed", "delivered"} or set(state["completed_moment_ids"]) != set(scene.moment_ids) or set(state["performed_moment_ids"]) != set(scene.moment_ids):
        raise ValueError("Scene is incomplete: explicit completion and actual moment performance required")
    constraints = _production_constraints(scene.skeleton)
    # Place each original moment's production constraints where that moment starts.
    pieces = re.split(r"<!--\s*RESOLVES\s*\[(BEAT\s+[^\]]+)\]\s*-->", constraints)
    per_moment = {pieces[i]: pieces[i + 1].strip() for i in range(1, len(pieces), 2)}
    transition_pattern = r"<TRANSITION\b[^>]*(?:/\s*>|>.*?</TRANSITION\s*>)"
    transitions = {mid: re.findall(transition_pattern, value, re.I | re.S) for mid, value in per_moment.items()}
    per_moment = {mid: re.sub(transition_pattern, "", value, flags=re.I | re.S).strip() for mid, value in per_moment.items()}
    lines = [pieces[0].strip()] if pieces[0].strip() else []
    emitted = set()
    previous_moment = None
    for event in state["public_events"]:
        mid = event["moment_id"]
        if mid not in emitted:
            if previous_moment is not None:
                lines.extend(transitions.get(previous_moment, []))
            lines.append(f"<!-- RESOLVES [{mid}] -->")
            if per_moment.get(mid):
                lines.append(per_moment[mid])
            emitted.add(mid)
            previous_moment = mid
        if event["kind"] == "stage":
            lines.append(event["text"])
        else:
            outer = event["outer_response"]
            if outer["action"].strip():
                lines.append(f"{event['character_id']}: {outer['action']}")
            if outer["dialogue"].strip():
                lines.append(f"{event['character_id']}: “{outer['dialogue']}”")
            if outer["silence"]:
                lines.append(f"{event['character_id']}: [deliberate silence]")
    if previous_moment is not None:
        lines.extend(transitions.get(previous_moment, []))
    rendered = "\n\n".join(lines).strip() + "\n"
    _public_text(rendered)
    return rendered


def perform_scene(*, repo: str, issue: int, cwd: Path, state_root: Path,
                  scene_path: str | None = None, run_id: str | None = None,
                  new_performance=False, model=None, max_calls=120, timeout=1200,
                  max_no_progress=6, deliver: Callable[[], str] | None = None) -> dict:
    """Run/resume one performance. Failures preserve private evidence and never deliver."""
    config.require_enabled_provider()
    for name, value in (("max_calls", max_calls), ("timeout", timeout), ("max_no_progress", max_no_progress)):
        if type(value) is not int or value <= 0:
            raise ValueError(f"{name} must be a positive integer")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) or type(issue) is not int or issue <= 0:
        raise ValueError("Invalid repository/issue identity")
    if run_id is not None:
        _uuid(run_id)
    if run_id and new_performance:
        raise ValueError("Explicit run_id and new_performance are mutually exclusive")
    cwd, state_root = Path(cwd).resolve(), Path(state_root).resolve()
    if state_root.is_relative_to(cwd):
        raise ValueError("Private performance state must live outside the delivered checkout")
    scene = load_scene(cwd, issue, scene_path)
    relative_scene = str(scene.directory.relative_to(cwd))
    fingerprint = {"scene": scene.fingerprint, "codex": codex_fingerprint(cwd, model=model)}
    effective_model = fingerprint["codex"].get("effective_model") or model
    slug = repo.replace("/", "__") + "-" + _hash(repo)[:10]
    registry = state_root / slug / str(issue)
    lock_context = None
    try:
        with _lock(registry / ".registry.lock"):
            if run_id is None:
                unfinished = []
                for entry in (() if new_performance else registry.iterdir()):
                    if not entry.is_dir() or entry.name.startswith("."):
                        continue
                    saved = _read(entry / "manifest.json")
                    if saved["scene_path"] == relative_scene and saved["status"] != "delivered":
                        unfinished.append(saved["run_id"])
                if unfinished and not new_performance:
                    raise ValueError("Unfinished performance exists; explicitly resume run UUID: " + ", ".join(unfinished))
                run_id = str(uuid.uuid4())
                fresh = True
            else:
                fresh = False
            run = registry / run_id
            if not fresh and not (run / "manifest.json").is_file():
                raise ValueError(f"Missing performance run UUID: {run_id}")
            lock_context = _lock(run / ".run.lock")
            lock_context.__enter__()
            if fresh:
                run.chmod(0o700)
                snapshots = json.dumps(scene.snapshots, sort_keys=True, ensure_ascii=False)
                _atomic(run / "snapshots.json", snapshots, raw=True)
                _atomic(run / "skeleton.md", scene.skeleton, raw=True)
                state = {"version": 1, "repo": repo, "issue": issue, "scene_path": relative_scene,
                         "scene_id": scene.scene_id, "run_id": run_id, "fingerprint": fingerprint,
                         "snapshot_hash": _hash(snapshots), "skeleton_hash": _hash(scene.skeleton),
                         "initial_script_hash": _hash((scene.directory / "script.md").read_text(encoding="utf-8")),
                         "rendered_script_hash": None, "status": "running", "delivery": None,
                         "summary": None, "pending": None, "sessions": {}, "next_role": "director",
                         "moment_id": None, "completed_moment_ids": [], "performed_moment_ids": [],
                         "accepted_turn_ids": [], "accepted_turns": [], "calls": 0, "no_progress": 0,
                         "latest_response": None, "character_prompt": "", "public_events": [],
                         "observations": {cid: [] for cid in scene.character_contexts},
                         "observation_cursors": {cid: 0 for cid in scene.character_contexts}}
                _atomic(run / "manifest.json", state)
            else:
                state = _read(run / "manifest.json")
        if (state["repo"], state["issue"], state["scene_path"], state["run_id"]) != (repo, issue, relative_scene, run_id):
            raise ValueError("Performance registry identity mismatch")
        if state["fingerprint"] != fingerprint:
            raise ValueError("Input or CLI/config/model fingerprint changed; start an intentional new performance")
        for filename, key in (("snapshots.json", "snapshot_hash"), ("skeleton.md", "skeleton_hash")):
            try:
                valid = _hash((run / filename).read_text(encoding="utf-8")) == state[key]
            except OSError:
                valid = False
            if not valid:
                raise ValueError("Incomplete or changed source snapshot; reconciliation required")
        sessions = state["sessions"]
        if not set(sessions) <= {"director", *scene.character_contexts} or len(set(sessions.values())) != len(sessions):
            raise ValueError("Invalid participant/session registry")
        for sid in sessions.values():
            _uuid(sid)
        if len(set(state["accepted_turn_ids"])) != len(state["accepted_turn_ids"]):
            raise ValueError("Duplicate accepted turn IDs in checkpoint")
        if [turn["turn_id"] for turn in state.get("accepted_turns", [])] != state["accepted_turn_ids"]:
            raise ValueError("Missing accepted turn/session bindings; reconciliation required")
        for turn in state["accepted_turns"]:
            if sessions.get(turn["participant"]) != turn["session_id"]:
                raise ValueError("Missing or changed native session ID for accepted participant")
        if state["pending"] or state["delivery"] == "pending":
            raise ValueError(f"Run {run_id} has an uncertain pending operation; manual reconciliation required; do not replay")
        _script_check(scene, state)
        if state["status"] == "delivered":
            return state
        while state["status"] == "running":
            if state["calls"] >= max_calls:
                raise ValueError(f"Total role call limit exhausted; resume run {run_id} with a larger limit")
            if state["no_progress"] >= max_no_progress:
                raise ValueError(f"Director no-progress limit exhausted; resume run {run_id} with a larger limit")
            role = state["next_role"]
            turn_id = str(uuid.uuid4())
            state["pending"] = {"turn_id": turn_id, "participant": role, "session_id": state["sessions"].get(role)}
            state["calls"] += 1
            _atomic(run / "manifest.json", state)
            request = _request(state, scene)
            turn_dir = run / "turns" / turn_id
            _atomic(turn_dir / "request.json", request)

            def register(session_id):
                _uuid(session_id)
                existing = state["sessions"].get(role)
                if existing and existing != session_id:
                    raise ValueError("Native session ID changed; replacement forbidden")
                if any(cid != role and sid == session_id for cid, sid in state["sessions"].items()):
                    raise ValueError("Native session UUID collision between participants")
                state["sessions"][role] = session_id
                state["pending"]["session_id"] = session_id
                _atomic(run / "manifest.json", state)

            raw = call_codex(json.dumps(request, ensure_ascii=False), cwd=cwd, turn_dir=turn_dir,
                             schema=DIRECTOR_SCHEMA if role == "director" else ACTOR_SCHEMA,
                             session_id=state["sessions"].get(role), on_session=register,
                             model=effective_model, timeout=timeout)
            _atomic(turn_dir / "raw_response.txt", raw, raw=True)
            if role not in state["sessions"]:
                raise ValueError("Native session ID missing; reconciliation required")
            try:
                response = json.loads(raw)
            except ValueError as exc:
                raise ValueError("Malformed role JSON; pending turn requires reconciliation") from exc
            _atomic(turn_dir / "parsed_response.json", response)
            _validate_turn(response, state, scene)
            state = _accept(state, response)
            _atomic(run / "manifest.json", state)
        if load_scene(cwd, issue, relative_scene).fingerprint != scene.fingerprint:
            raise ValueError("Scene input fingerprint changed during performance; start an intentional new performance")
        rendered = _render(scene, state)
        _script_check(scene, state)
        state["rendered_script_hash"] = _hash(rendered)
        # Journal the permitted final hash before rendering, so either side of the
        # atomic script replacement remains recoverable after a process crash.
        _atomic(run / "manifest.json", state)
        _atomic(scene.directory / "script.md", rendered, raw=True)
        if deliver is not None:
            state["delivery"] = "pending"
            _atomic(run / "manifest.json", state)
            summary = deliver()
            state["delivery"] = "complete"
            state["status"] = "delivered"
            state["summary"] = summary
            _atomic(run / "manifest.json", state)
        return state
    finally:
        if lock_context is not None:
            lock_context.__exit__(None, None, None)
