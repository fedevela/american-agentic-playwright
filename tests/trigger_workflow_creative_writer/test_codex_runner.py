from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import threading
import time
from types import SimpleNamespace

import pytest


FAKE_CODEX_SOURCE = Path(__file__).parent / "fixtures" / "fake_codex.py"
SESSION_ID = "11111111-1111-4111-8111-111111111111"


def _install_fake_codex(tmp_path: Path, monkeypatch) -> Path:
    executable = tmp_path / "fake-codex"
    executable.write_bytes(FAKE_CODEX_SOURCE.read_bytes())
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("CODEX_BIN", str(executable))
    return executable


def _create_required_artifacts(repo: Path) -> None:
    from trigger_workflow_creative_writer.artifact_validation import (
        REQUIRED_ARTIFACTS,
        REQUIRED_CHARACTER_ARTIFACTS,
    )

    for relative in REQUIRED_ARTIFACTS:
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture\n", encoding="utf-8")
    character = repo / "bible" / "characters" / "ada"
    character.mkdir(parents=True)
    for name in REQUIRED_CHARACTER_ARTIFACTS:
        (character / name).write_text("fixture\n", encoding="utf-8")


def test_call_codex_initial_call_uses_stdin_and_absolute_artifacts(tmp_path: Path, monkeypatch) -> None:
    from trigger_workflow_creative_writer.codex_runner import call_codex

    executable = _install_fake_codex(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    repo.mkdir()
    turn_dir = tmp_path / "turn"
    record_path = tmp_path / "invocation.json"
    monkeypatch.setenv("FAKE_CODEX_RECORD", str(record_path))
    monkeypatch.setenv("FAKE_CODEX_RESPONSE", "the final file wins")
    observed_sessions: list[str] = []
    schema = {"type": "object", "required": ["answer"]}

    response = call_codex(
        "A prompt with $(shell) and `ticks`",
        cwd=repo,
        turn_dir=turn_dir,
        schema=schema,
        on_session=observed_sessions.append,
        model="test-model",
        timeout=5,
    )

    assert response == "the final file wins"
    assert observed_sessions == [SESSION_ID]
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["cwd"] == str(repo.resolve())
    assert record["prompt"] == "A prompt with $(shell) and `ticks`"
    assert record["argv"] == [
        "exec",
        "--json",
        "-c",
        'sandbox_mode="workspace-write"',
        "--output-schema",
        str((turn_dir / "schema.json").resolve()),
        "--output-last-message",
        str((turn_dir / "response.txt").resolve()),
        "--model",
        "test-model",
        "-",
    ]
    assert (turn_dir / "request.txt").read_text(encoding="utf-8") == record["prompt"]
    assert json.loads((turn_dir / "schema.json").read_text(encoding="utf-8")) == schema
    assert '"type": "thread.started"' in (turn_dir / "stdout.jsonl").read_text(encoding="utf-8")
    assert (turn_dir / "stderr.log").read_text(encoding="utf-8") == "fake stderr\n"
    assert record["codex_home"] == os.environ.get("CODEX_HOME")
    assert str(executable) not in record["prompt"]


def test_call_codex_resume_uses_exact_uuid_without_fallback(tmp_path: Path, monkeypatch) -> None:
    from trigger_workflow_creative_writer.codex_runner import call_codex

    _install_fake_codex(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    repo.mkdir()
    turn_dir = tmp_path / "resume-turn"
    record_path = tmp_path / "resume-invocation.json"
    monkeypatch.setenv("FAKE_CODEX_RECORD", str(record_path))

    assert call_codex("continue", cwd=repo, turn_dir=turn_dir, session_id=SESSION_ID, timeout=5) == "final response"

    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["argv"] == [
        "exec",
        "resume",
        "--json",
        "-c",
        'sandbox_mode="workspace-write"',
        "--output-last-message",
        str((turn_dir / "response.txt").resolve()),
        SESSION_ID,
        "-",
    ]
    assert "--last" not in record["argv"]
    assert "--ephemeral" not in record["argv"]
    assert "dangerously-bypass-approvals-and-sandbox" not in record["argv"]


@pytest.mark.parametrize(
    ("mode", "message"),
    [
        ("no_session", "thread.started"),
        ("changed_session", "session mismatch"),
        ("error", "failure event error"),
        ("turn_failed", "failure event turn.failed"),
        ("missing_completed", "turn.completed"),
        ("missing_output", "final response file"),
        ("empty_output", "empty final response"),
        ("nonzero", "exit code 7"),
        ("malformed_event", "malformed JSONL"),
    ],
)
def test_call_codex_rejects_incomplete_or_failed_turns(
    tmp_path: Path,
    monkeypatch,
    mode: str,
    message: str,
) -> None:
    from trigger_workflow_creative_writer.codex_runner import call_codex

    _install_fake_codex(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv("FAKE_CODEX_MODE", mode)

    with pytest.raises(SystemExit, match=message):
        call_codex(
            "continue",
            cwd=repo,
            turn_dir=tmp_path / "turn",
            session_id=SESSION_ID if mode == "changed_session" else None,
            timeout=5,
        )


def test_call_codex_rejects_invalid_resume_uuid_before_launch(tmp_path: Path, monkeypatch) -> None:
    from trigger_workflow_creative_writer.codex_runner import call_codex

    _install_fake_codex(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    repo.mkdir()
    record_path = tmp_path / "invocation.json"
    monkeypatch.setenv("FAKE_CODEX_RECORD", str(record_path))

    noncanonical_uuid = "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"
    with pytest.raises(SystemExit, match="canonical UUID"):
        call_codex("continue", cwd=repo, turn_dir=tmp_path / "turn", session_id=noncanonical_uuid)

    assert not record_path.exists()


def test_call_codex_delivers_session_callback_before_process_completion(tmp_path: Path, monkeypatch) -> None:
    from trigger_workflow_creative_writer.codex_runner import call_codex

    _install_fake_codex(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    repo.mkdir()
    release_path = tmp_path / "release"
    callback_happened = threading.Event()
    monkeypatch.setenv("FAKE_CODEX_MODE", "wait_after_started")
    monkeypatch.setenv("FAKE_CODEX_RELEASE", str(release_path))

    def on_session(session_id: str) -> None:
        assert session_id == SESSION_ID
        callback_happened.set()
        release_path.touch()

    assert call_codex(
        "start",
        cwd=repo,
        turn_dir=tmp_path / "turn",
        on_session=on_session,
        timeout=5,
    ) == "final response"
    assert callback_happened.is_set()


def test_call_codex_timeout_is_bounded_without_stdout_newline(tmp_path: Path, monkeypatch) -> None:
    from trigger_workflow_creative_writer.codex_runner import call_codex

    _install_fake_codex(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv("FAKE_CODEX_MODE", "hang_no_newline")
    started = time.monotonic()

    with pytest.raises(SystemExit, match="timed out"):
        call_codex("hang", cwd=repo, turn_dir=tmp_path / "turn", timeout=0.2)

    assert time.monotonic() - started < 3


def test_call_codex_large_prompt_timeout_is_bounded_when_child_never_reads_stdin(
    tmp_path: Path, monkeypatch
) -> None:
    from trigger_workflow_creative_writer.codex_runner import call_codex

    _install_fake_codex(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv("FAKE_CODEX_MODE", "never_read_stdin")
    started = time.monotonic()

    with pytest.raises(SystemExit, match="timed out"):
        call_codex("x" * 2_000_000, cwd=repo, turn_dir=tmp_path / "turn", timeout=0.2)

    assert time.monotonic() - started < 1.5


def test_call_codex_timeout_kills_descendant_after_leader_exits(tmp_path: Path, monkeypatch) -> None:
    from trigger_workflow_creative_writer.codex_runner import call_codex

    _install_fake_codex(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    repo.mkdir()
    marker_path = tmp_path / "descendant-work"
    monkeypatch.setenv("FAKE_CODEX_MODE", "leader_exits_child_holds_pipes")
    monkeypatch.setenv("FAKE_CODEX_DESCENDANT_MARKER", str(marker_path))

    with pytest.raises(SystemExit, match="timed out"):
        call_codex("spawn", cwd=repo, turn_dir=tmp_path / "turn", timeout=0.1)

    time.sleep(0.5)
    assert not marker_path.exists()


def test_call_codex_missing_executable_fails_without_fallback(tmp_path: Path, monkeypatch) -> None:
    from trigger_workflow_creative_writer.codex_runner import call_codex

    monkeypatch.setenv("CODEX_BIN", str(tmp_path / "does-not-exist"))
    repo = tmp_path / "repo"
    repo.mkdir()

    with pytest.raises(SystemExit, match="executable was not found"):
        call_codex("start", cwd=repo, turn_dir=tmp_path / "turn", timeout=1)


def test_call_codex_does_not_read_native_history(tmp_path: Path, monkeypatch) -> None:
    from trigger_workflow_creative_writer.codex_runner import call_codex

    _install_fake_codex(tmp_path, monkeypatch)
    fake_home = tmp_path / "codex-home"
    sessions = fake_home / "sessions"
    sessions.mkdir(parents=True)
    (sessions / "poison.jsonl").write_text("not valid history", encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(fake_home))
    repo = tmp_path / "repo"
    repo.mkdir()

    assert call_codex("start", cwd=repo, turn_dir=tmp_path / "turn", timeout=5) == "final response"


def test_codex_fingerprint_hashes_effective_config_and_agents(tmp_path: Path, monkeypatch) -> None:
    from trigger_workflow_creative_writer.codex_runner import codex_fingerprint

    executable = _install_fake_codex(tmp_path, monkeypatch)
    user_home = tmp_path / "home"
    user_codex = user_home / ".codex"
    user_codex.mkdir(parents=True)
    (user_codex / "config.toml").write_text('model = "user-model"\n', encoding="utf-8")
    (user_codex / "AGENTS.md").write_text("global guidance\n", encoding="utf-8")
    # These are deliberately malformed: a fingerprint must not inspect auth or native histories.
    (user_codex / "auth.json").write_text("not-json", encoding="utf-8")
    (user_codex / "sessions").mkdir()
    (user_codex / "sessions" / "native.jsonl").write_text("not-json", encoding="utf-8")
    monkeypatch.setenv("HOME", str(user_home))

    repo = tmp_path / "repo"
    nested = repo / "scenes"
    nested.mkdir(parents=True)
    (repo / ".git").mkdir()
    (repo / ".codex").mkdir()
    (repo / ".codex" / "config.toml").write_text('model = "project-model"\n', encoding="utf-8")
    (repo / "AGENTS.md").write_text("project guidance\n", encoding="utf-8")
    (nested / "AGENTS.md").write_text("scene guidance\n", encoding="utf-8")

    fingerprint = codex_fingerprint(nested)

    assert fingerprint["executable"] == str(executable.resolve())
    assert fingerprint["version"] == "codex-cli 99.0.0-fake"
    assert fingerprint["effective_model"] == "project-model"
    assert fingerprint["model_source"] == str((repo / ".codex" / "config.toml").resolve())
    assert fingerprint["config_overrides"] == ['sandbox_mode="workspace-write"']
    assert set(fingerprint["config_files"]) == {
        str((user_codex / "config.toml").resolve()),
        str((repo / ".codex" / "config.toml").resolve()),
    }
    assert set(fingerprint["agents_files"]) == {
        str((user_codex / "AGENTS.md").resolve()),
        str((repo / "AGENTS.md").resolve()),
        str((nested / "AGENTS.md").resolve()),
    }
    assert len(fingerprint["configuration_sha256"]) == 64

    before = fingerprint["configuration_sha256"]
    (nested / "AGENTS.md").write_text("changed scene guidance\n", encoding="utf-8")
    assert codex_fingerprint(nested)["configuration_sha256"] != before


def test_codex_fingerprint_explicit_model_wins_and_default_stays_unresolved(tmp_path: Path, monkeypatch) -> None:
    from trigger_workflow_creative_writer.codex_runner import codex_fingerprint

    _install_fake_codex(tmp_path, monkeypatch)
    user_home = tmp_path / "home"
    user_home.mkdir()
    monkeypatch.setenv("HOME", str(user_home))
    repo = tmp_path / "repo"
    repo.mkdir()

    unresolved = codex_fingerprint(repo)
    assert unresolved["effective_model"] is None
    assert unresolved["model_source"] == "cli-default-unresolved"

    explicit = codex_fingerprint(repo, model="pinned-model")
    assert explicit["effective_model"] == "pinned-model"
    assert explicit["model_source"] == "argument"


def test_codex_fingerprint_honors_inherited_codex_home_without_reading_state(
    tmp_path: Path, monkeypatch
) -> None:
    from trigger_workflow_creative_writer.codex_runner import codex_fingerprint

    _install_fake_codex(tmp_path, monkeypatch)
    codex_home = tmp_path / "native-home"
    codex_home.mkdir()
    config_path = codex_home / "config.toml"
    config_path.write_text('model = "native-home-model"\n', encoding="utf-8")
    (codex_home / "auth.json").write_text("not valid json", encoding="utf-8")
    (codex_home / "sessions").mkdir()
    (codex_home / "sessions" / "history.jsonl").write_text("not valid jsonl", encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    repo = tmp_path / "repo"
    repo.mkdir()

    fingerprint = codex_fingerprint(repo)

    assert fingerprint["effective_model"] == "native-home-model"
    assert fingerprint["model_source"] == str(config_path.resolve())


def test_comment_phase_starts_fresh_guarded_turn_in_ignored_workspace(tmp_path: Path, monkeypatch) -> None:
    from trigger_workflow_creative_writer import codex_runner

    _install_fake_codex(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    repo.mkdir()
    _create_required_artifacts(repo)
    workspace = tmp_path / "application"
    record_path = tmp_path / "ordinary.json"
    monkeypatch.setenv("FAKE_CODEX_RECORD", str(record_path))
    monkeypatch.setattr(codex_runner.config, "WORKSPACE", workspace)
    monkeypatch.setenv("FAKE_CODEX_RESPONSE", '{"response":"## Intent\\n\\nRed’s **choice**.\\n\\n- Keep the threshold open."}')
    monkeypatch.setattr(
        codex_runner,
        "prepare_phase_execution_context",
        lambda *args, **kwargs: SimpleNamespace(local_path=repo, branch="main"),
        raising=False,
    )

    response = codex_runner.run_codex_comment_phase(
        "Write the analysis.",
        repo="owner/story",
        issue=8,
        phase="2A",
        session_scope="must-not-resume",
    )

    assert response == "## Intent\n\nRed’s **choice**.\n\n- Keep the threshold open."
    from trigger_workflow_creative_writer.prompts import format_phase_comment
    assert format_phase_comment("1", "phase:keter", response) == (
        "<!-- phase:1:start label=phase:keter name=Keter -->\n"
        "### Phase 1: Keter\n\n## Intent\n\nRed’s **choice**.\n\n"
        "- Keep the threshold open.\n\n"
        "<!-- phase:1:end label=phase:keter name=Keter -->"
    )
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert "--output-schema" in record["argv"]
    assert "resume" not in record["argv"]
    assert "Python owns commit, push, pull request, GitHub comment, and label operations" in record["prompt"]
    response_path = Path(record["argv"][record["argv"].index("--output-last-message") + 1])
    assert response_path.is_relative_to((workspace / "workspace" / "codex").resolve())


@pytest.mark.parametrize("response", ['not json', '[]', '{}', '{"response": null}', '{"response": 3}', '{"response": "  "}', '{"response": "ok", "extra": true}'])
def test_comment_phase_rejects_invalid_payload_before_publication(tmp_path: Path, monkeypatch, response: str) -> None:
    from trigger_workflow_creative_writer import codex_runner

    _install_fake_codex(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    repo.mkdir()
    _create_required_artifacts(repo)
    monkeypatch.setenv("FAKE_CODEX_RESPONSE", response)
    monkeypatch.setattr(codex_runner.config, "WORKSPACE", tmp_path / "app")
    monkeypatch.setattr(codex_runner, "prepare_phase_execution_context", lambda *args, **kwargs: SimpleNamespace(local_path=repo, branch="main"))

    with pytest.raises(SystemExit, match="comment response"):
        codex_runner.run_codex_comment_phase("analysis", repo="owner/story", issue=1, phase="1")


def test_disabled_provider_is_rejected_before_checkout(tmp_path: Path, monkeypatch) -> None:
    from trigger_workflow_creative_writer import codex_runner

    monkeypatch.setattr(codex_runner.config, "RUNNER_TYPE", "gemini")
    checkout_called = False

    def checkout(*args, **kwargs):
        nonlocal checkout_called
        checkout_called = True
        raise AssertionError("checkout must not run")

    monkeypatch.setattr(codex_runner, "prepare_phase_execution_context", checkout, raising=False)

    with pytest.raises(SystemExit, match="Provider 'gemini' is disabled"):
        codex_runner.run_codex_comment_phase("prompt", repo="owner/story", issue=1, phase="1")
    assert checkout_called is False


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ('```json\n{"comment": "ok", "sub_issues": []}\n```', {"comment": "ok", "sub_issues": []}),
        ('```\n{"comment": "ok"}\n```', {"comment": "ok"}),
        ('{"outcome":"complete","narrative":"A sign reads [ERROR:REJECT_BEAT]"}', {"outcome":"complete","narrative":"A sign reads [ERROR:REJECT_BEAT]"}),
    ],
)
def test_json_phase_parses_fences_without_routing_on_quoted_error_prose(
    tmp_path: Path,
    monkeypatch,
    response: str,
    expected: dict,
) -> None:
    from trigger_workflow_creative_writer import codex_runner

    _install_fake_codex(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    repo.mkdir()
    _create_required_artifacts(repo)
    monkeypatch.setenv("FAKE_CODEX_RESPONSE", response)
    monkeypatch.setattr(codex_runner.config, "WORKSPACE", tmp_path / "app")
    monkeypatch.setattr(
        codex_runner,
        "prepare_phase_execution_context",
        lambda *args, **kwargs: SimpleNamespace(local_path=repo, branch="main"),
        raising=False,
    )

    assert codex_runner.run_codex_json_phase("json", repo="owner/story", issue=4, phase="4") == expected


def test_json_phase_rejects_malformed_or_non_object_json(tmp_path: Path, monkeypatch) -> None:
    from trigger_workflow_creative_writer import codex_runner

    _install_fake_codex(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    repo.mkdir()
    _create_required_artifacts(repo)
    monkeypatch.setattr(codex_runner.config, "WORKSPACE", tmp_path / "app")
    monkeypatch.setattr(
        codex_runner,
        "prepare_phase_execution_context",
        lambda *args, **kwargs: SimpleNamespace(local_path=repo, branch="main"),
        raising=False,
    )
    monkeypatch.setenv("FAKE_CODEX_RESPONSE", "[]")

    with pytest.raises(SystemExit, match="JSON object"):
        codex_runner.run_codex_json_phase("json", repo="owner/story", issue=4, phase="4")


def test_phase_7_uses_scene_artifact_gate_without_npm(tmp_path: Path, monkeypatch) -> None:
    from trigger_workflow_creative_writer import codex_runner, scene_materials

    _install_fake_codex(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    repo.mkdir()
    _create_required_artifacts(repo)
    monkeypatch.setattr(codex_runner.config, "WORKSPACE", tmp_path / "app")
    monkeypatch.setattr(
        codex_runner,
        "prepare_phase_execution_context",
        lambda *args, **kwargs: SimpleNamespace(local_path=repo, branch="issue/7"),
        raising=False,
    )
    validated: list[tuple[Path, str, int]] = []
    monkeypatch.setattr(scene_materials, "validate_phase_artifacts", lambda *args: validated.append(args))
    monkeypatch.setattr(
        codex_runner,
        "run_phase_tests",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("npm validation must not run")),
        raising=False,
    )

    assert codex_runner.run_codex_implementation_phase(
        "Create handoff", repo="owner/story", issue=7, phase="7"
    ) is None
    assert validated == [(repo, "7", 7)]


def test_phase_9_direct_implementation_requires_roundtable_before_checkout(monkeypatch) -> None:
    from trigger_workflow_creative_writer import codex_runner

    monkeypatch.setattr(
        codex_runner,
        "prepare_phase_execution_context",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("checkout must not run")),
        raising=False,
    )

    with pytest.raises(SystemExit, match="roundtable"):
        codex_runner.run_codex_implementation_phase(
            "Perform scene", repo="owner/story", issue=9, phase="9"
        )


def _ready_scene_issue():
    from tests.trigger_workflow_creative_writer.test_dramaturgy import base, established
    from trigger_workflow_creative_writer.cycles import child_assignments
    from trigger_workflow_creative_writer.validation import validate_result

    accepted = established()
    result = validate_result(
        {**base("4"), "assignments": [{"element_id": "cycle-one:e1", "outline": "She opens the door."}]},
        phase="4", cycle_id="cycle-one", scope="season", accepted=accepted,
    )
    child = child_assignments(result, parent_issue=1, accepted=accepted)[0]
    return {"title": child["title"], "body": child["body"], "labels": [{"name": "size:scene"}], "comments": []}


@pytest.mark.parametrize("fetch", [False, True])
def test_phase_5_rejects_legacy_assignment_before_checkout_or_agent(monkeypatch, fetch) -> None:
    from trigger_workflow_creative_writer import codex_runner, github_ops

    legacy = {"title": "Legacy [SMALL] scene", "body": "Requirement IDs: CH-001", "labels": [{"name": "size:scene"}]}
    monkeypatch.setattr(github_ops, "fetch_issue_data", lambda repo, issue: legacy)
    def forbidden(*args, **kwargs):
        raise AssertionError("Legacy assignment must fail before checkout or agent execution")
    monkeypatch.setattr(codex_runner, "_prepare_context", forbidden)
    monkeypatch.setattr(codex_runner, "_call_ordinary_turn", forbidden)
    with pytest.raises(SystemExit, match="assignment|Keter|legacy"):
        codex_runner.run_codex_implementation_phase(
            "Prepare scene", repo="owner/story", issue=5, phase="5",
            issue_data=None if fetch else legacy,
        )


def test_phase_5_validation_retry_uses_fresh_sessions_and_bounded_contract(tmp_path: Path, monkeypatch) -> None:
    from trigger_workflow_creative_writer import codex_runner

    repo = tmp_path / "repo"
    repo.mkdir()
    _create_required_artifacts(repo)
    monkeypatch.setattr(codex_runner.config, "WORKSPACE", tmp_path / "app")
    monkeypatch.setattr(
        codex_runner,
        "prepare_phase_execution_context",
        lambda *args, **kwargs: SimpleNamespace(local_path=repo, branch="issue/5"),
        raising=False,
    )
    calls: list[dict] = []

    def fake_call(prompt, **kwargs):
        calls.append({"prompt": prompt, **kwargs})
        return "done"

    monkeypatch.setattr(codex_runner, "call_codex", fake_call)
    validation_results = iter(
        [
            subprocess.CompletedProcess(["validation"], 1, "test failed", ""),
            subprocess.CompletedProcess(["validation"], 0, "ok", ""),
        ]
    )
    monkeypatch.setattr(codex_runner, "run_phase_tests", lambda **kwargs: next(validation_results), raising=False)

    codex_runner.run_codex_implementation_phase(
        "Implement constraints",
        repo="owner/story",
        issue=5,
        phase="5",
        session_scope="ignored",
        issue_data=_ready_scene_issue(),
    )

    assert len(calls) == 2
    assert all(call["session_id"] is None for call in calls)
    assert calls[0]["turn_dir"] != calls[1]["turn_dir"]
    assert "required repository validation failed" in calls[1]["prompt"]
    assert all("Python owns commit, push" in call["prompt"] for call in calls)


def test_finalize_phase_delivery_delegates_after_provider_gate(monkeypatch) -> None:
    from trigger_workflow_creative_writer import codex_runner

    received = {}

    def finalize(**kwargs):
        received.update(kwargs)
        return "summary"

    monkeypatch.setattr(codex_runner, "utils_finalize_phase_delivery", finalize, raising=False)
    kwargs = {"repo": "owner/story", "issue": 5, "phase": "5", "issue_title": "Title"}
    assert codex_runner.finalize_phase_delivery(**kwargs) == "summary"
    assert received == kwargs
