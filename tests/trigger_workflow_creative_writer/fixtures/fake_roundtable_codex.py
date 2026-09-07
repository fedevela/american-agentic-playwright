#!/usr/bin/env python3
"""Offline native CLI stand-in with durable, distinct participant sessions."""
import json
import os
from pathlib import Path
import sys
import uuid

if sys.argv[1:] == ["--version"]:
    print("codex-cli fake-roundtable-1")
    raise SystemExit(0)

argv = sys.argv[1:]
store = Path(os.environ["FAKE_ROUNDTABLE_STORE"])
store.mkdir(parents=True, exist_ok=True)
request = json.loads(sys.stdin.read())
role = request["role"]
resume = len(argv) > 1 and argv[1] == "resume"
sid = argv[-2] if resume else str(uuid.uuid4())
session_path = store / f"{sid}.json"
if resume:
    if not session_path.exists():
        print("native session missing", file=sys.stderr)
        raise SystemExit(9)
    session = json.loads(session_path.read_text())
    assert session["role"] == role
    assert "bootstrap" not in request
else:
    assert "bootstrap" in request
    session = {"role": role, "count": 0}
assert "--last" not in argv
print(json.dumps({"type": "thread.started", "thread_id": sid}), flush=True)
count = session["count"]
record = {"argv": argv, "request": request, "session_id": sid, "resume": resume, "cwd": str(Path.cwd())}
with (store / "requests.jsonl").open("a") as stream:
    stream.write(json.dumps(record) + "\n")
if role == "director":
    response = {"turn_id": request["turn_id"], "status": "complete" if count >= 4 else "continue",
                "moment_id": "BEAT 1", "private_direction": "director private sentinel",
                "stage_events": [] if count >= 4 else [{"text": "The lock clicks.", "observers": ["alice", "bob"]}],
                "next_speaker": None if count >= 4 else ("alice", "bob")[count % 2],
                "character_prompt": "Choose your next action." if count < 4 else "",
                "completed_moment_ids": ["BEAT 1"] if count >= 4 else [],
                "previous_item_observers": [{"item_id": item["item_id"], "observers": ["alice", "bob"]}
                                            for item in (request.get("latest_response") or {}).get("items", [])
                                            if item["category"] != "thought"]}
else:
    response = {"turn_id": request["turn_id"], "character_id": role,
                "items": [{"category": "thought", "text": role + " inner sentinel"},
                          {"category": "action", "text": "Tries the handle." if role == "alice" else "deliberate silence."}]}
    if role == "alice" and count:
        response["items"].append({"category": "dialogue", "text": "I choose to stay."})
session["count"] += 1
session_path.write_text(json.dumps(session))
Path(argv[argv.index("--output-last-message") + 1]).write_text(json.dumps(response))
print(json.dumps({"type": "turn.completed"}), flush=True)
