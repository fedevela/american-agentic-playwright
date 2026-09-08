"""Native Codex CLI adapter for the creative-writing workflow."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from queue import Empty, Queue
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
from typing import Any, BinaryIO, Callable
import uuid

from . import config
from .artifact_validation import validate_required_artifacts
from .logging_utils import log_error, log_multiline
from .runner_utils import (
    MAX_VALIDATION_ATTEMPTS,
    MAX_VALIDATION_RETRIES,
    VALIDATION_COMMAND_CONTRACT,
    build_single_retry_fix_task,
    finalize_phase_delivery as utils_finalize_phase_delivery,
    prepare_branch_context,
    prepare_phase_execution_context,
    run_phase_tests,
    summarize_test_output,
)


PYTHON_OWNED_OPERATIONS = """

Execution boundary: Python owns commit, push, pull request, GitHub comment, and label operations.
Never perform any of those operations. Do not create or switch branches. Work only within the
requested phase scope in the already prepared checkout; Python will validate and deliver afterward.
""".strip()
REPOSITORY_VALIDATION_PHASES = {"6", "10"}
CODEX_CONFIG_OVERRIDES = ('sandbox_mode="workspace-write"',)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repository_root(cwd: Path) -> Path:
    resolved = cwd.resolve()
    for candidate in (resolved, *resolved.parents):
        if (candidate / ".git").exists():
            return candidate
    return resolved


def _path_chain(root: Path, cwd: Path) -> list[Path]:
    relative = cwd.resolve().relative_to(root.resolve())
    chain = [root.resolve()]
    current = root.resolve()
    for part in relative.parts:
        current /= part
        chain.append(current)
    return chain


def _model_from_config(path: Path) -> str | None:
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise SystemExit(f"Unable to read Codex config at {path}: {exc}") from exc
    configured = payload.get("model")
    profile_name = payload.get("profile")
    profiles = payload.get("profiles")
    if isinstance(profile_name, str) and isinstance(profiles, dict):
        profile = profiles.get(profile_name)
        if isinstance(profile, dict) and isinstance(profile.get("model"), str):
            configured = profile["model"]
    if not isinstance(configured, str) or not configured.strip():
        return None
    return configured.strip()


def codex_fingerprint(cwd: Path, model: str | None = None) -> dict[str, Any]:
    """Fingerprint the CLI and non-secret configuration relevant to a native session."""
    config.require_enabled_provider()
    cwd = cwd.resolve()
    requested_executable = os.environ.get("CODEX_BIN", "codex")
    resolved_executable = shutil.which(requested_executable)
    if resolved_executable is None:
        raise SystemExit(f"Codex executable was not found: {requested_executable}")
    executable_path = Path(resolved_executable).resolve()
    try:
        version_result = subprocess.run(  # noqa: S603 - resolved executable, fixed version argument
            [str(executable_path), "--version"],
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(f"Unable to determine Codex CLI version: {exc}") from exc
    version = (version_result.stdout or version_result.stderr or "").strip()
    if version_result.returncode != 0 or not version:
        raise SystemExit(
            f"Unable to determine Codex CLI version (exit code {version_result.returncode})."
        )

    repository_root = _repository_root(cwd)
    directory_chain = _path_chain(repository_root, cwd)
    inherited_codex_home = os.environ.get("CODEX_HOME")
    user_codex_dir = (
        Path(inherited_codex_home).expanduser().resolve()
        if inherited_codex_home
        else (Path.home() / ".codex").resolve()
    )
    config_candidates = [user_codex_dir / "config.toml"]
    config_candidates.extend(directory / ".codex" / "config.toml" for directory in directory_chain)
    agents_candidates = [user_codex_dir / "AGENTS.md", user_codex_dir / "AGENTS.override.md"]
    for directory in directory_chain:
        agents_candidates.extend([directory / "AGENTS.md", directory / "AGENTS.override.md"])

    config_files: dict[str, str] = {}
    configured_model: str | None = None
    configured_model_source: str | None = None
    for path in config_candidates:
        if not path.is_file():
            continue
        resolved_path = path.resolve()
        config_files[str(resolved_path)] = _sha256(resolved_path)
        candidate_model = _model_from_config(resolved_path)
        if candidate_model is not None:
            configured_model = candidate_model
            configured_model_source = str(resolved_path)

    agents_files: dict[str, str] = {}
    for path in agents_candidates:
        if path.is_file():
            resolved_path = path.resolve()
            agents_files[str(resolved_path)] = _sha256(resolved_path)

    effective_model = model.strip() if isinstance(model, str) and model.strip() else configured_model
    if isinstance(model, str) and model.strip():
        model_source = "argument"
    elif configured_model is not None:
        model_source = configured_model_source
    else:
        model_source = "cli-default-unresolved"

    fingerprint: dict[str, Any] = {
        "executable": str(executable_path),
        "executable_sha256": _sha256(executable_path),
        "version": version,
        "effective_model": effective_model,
        "model_source": model_source,
        "config_overrides": list(CODEX_CONFIG_OVERRIDES),
        "config_files": config_files,
        "agents_files": agents_files,
    }
    encoded = json.dumps(fingerprint, sort_keys=True, separators=(",", ":")).encode("utf-8")
    fingerprint["configuration_sha256"] = hashlib.sha256(encoded).hexdigest()
    return fingerprint


def _validated_session_id(value: object, *, label: str) -> str:
    if not isinstance(value, str):
        raise SystemExit(f"Codex {label} session identifier is missing or invalid.")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise SystemExit(f"Codex {label} session identifier is missing or invalid: {value!r}.") from exc
    if str(parsed) != value:
        raise SystemExit(f"Codex {label} session identifier must be a canonical UUID: {value!r}.")
    return value


def _kill_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        if process.poll() is None:
            process.kill()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def call_codex(
    prompt: str,
    *,
    cwd: Path,
    turn_dir: Path,
    schema: dict | None = None,
    session_id: str | None = None,
    on_session: Callable[[str], None] | None = None,
    model: str | None = None,
    timeout: int = 1200,
) -> str:
    """Run one Codex turn and return the final response file contents."""
    config.require_enabled_provider()
    if timeout <= 0:
        raise ValueError("Codex timeout must be positive.")

    expected_session = (
        _validated_session_id(session_id, label="resume") if session_id is not None else None
    )
    cwd = cwd.resolve()
    turn_dir = turn_dir.resolve()
    turn_dir.mkdir(parents=True, exist_ok=True)
    request_path = turn_dir / "request.txt"
    stdout_path = turn_dir / "stdout.jsonl"
    stderr_path = turn_dir / "stderr.log"
    response_path = turn_dir / "response.txt"
    schema_path = turn_dir / "schema.json"

    request_path.write_text(prompt, encoding="utf-8")
    if schema is not None:
        schema_path.write_text(json.dumps(schema, indent=2, sort_keys=True), encoding="utf-8")

    executable = os.environ.get("CODEX_BIN", "codex")
    command = [executable, "exec"]
    if expected_session is not None:
        command.append("resume")
    command.append("--json")
    for override in CODEX_CONFIG_OVERRIDES:
        command.extend(["-c", override])
    if schema is not None:
        command.extend(["--output-schema", str(schema_path)])
    command.extend(["--output-last-message", str(response_path)])
    if model is not None:
        command.extend(["-m", model])
    if expected_session is not None:
        command.append(expected_session)
    command.append("-")

    deadline = time.monotonic() + timeout
    try:
        with request_path.open("rb") as prompt_input:
            process = subprocess.Popen(  # noqa: S603 - explicit argv, never shell-expanded
                command,
                cwd=cwd,
                stdin=prompt_input,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
    except FileNotFoundError as exc:
        stdout_path.touch()
        stderr_path.write_text(str(exc), encoding="utf-8")
        raise SystemExit(f"Codex executable was not found: {executable}") from exc

    if process.stdout is None or process.stderr is None:
        _kill_process_group(process)
        raise SystemExit("Failed to open Codex process streams.")

    queue: Queue[tuple[str, bytes | None]] = Queue()

    def read_stream(name: str, stream: BinaryIO) -> None:
        try:
            while True:
                read1 = getattr(stream, "read1", stream.read)
                chunk = read1(4096)
                if not chunk:
                    break
                queue.put((name, chunk))
        finally:
            queue.put((name, None))
            stream.close()

    threads = [
        threading.Thread(target=read_stream, args=("stdout", process.stdout), daemon=True),
        threading.Thread(target=read_stream, args=("stderr", process.stderr), daemon=True),
    ]
    for thread in threads:
        thread.start()

    finished_streams: set[str] = set()
    stdout_buffer = b""
    observed_session: str | None = None
    completed = False
    event_error: str | None = None

    def accept_event(raw_line: bytes) -> None:
        nonlocal observed_session, completed, event_error
        if not raw_line.strip():
            return
        try:
            event = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            event_error = f"Codex emitted malformed JSONL: {exc}"
            return
        if not isinstance(event, dict):
            event_error = "Codex emitted a non-object JSONL event."
            return
        event_type = event.get("type")
        if event_type == "thread.started":
            try:
                candidate = _validated_session_id(event.get("thread_id"), label="observed")
            except SystemExit as exc:
                event_error = str(exc)
                return
            if observed_session is not None and candidate != observed_session:
                event_error = "Codex emitted conflicting thread.started session identifiers."
                return
            if expected_session is not None and candidate != expected_session:
                event_error = (
                    f"Codex resume session mismatch: requested {expected_session}, observed {candidate}."
                )
                return
            if observed_session is None:
                observed_session = candidate
                if on_session is not None:
                    on_session(candidate)
        elif event_type == "turn.completed":
            completed = True
        elif event_type in {"error", "turn.failed"}:
            event_error = f"Codex emitted failure event {event_type}: {event}"

    try:
        with stdout_path.open("wb") as stdout_file, stderr_path.open("wb") as stderr_file:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    _kill_process_group(process)
                    raise SystemExit(f"Codex timed out after {timeout} seconds.")
                if len(finished_streams) == 2 and process.poll() is not None:
                    break
                try:
                    stream_name, chunk = queue.get(timeout=min(0.05, remaining))
                except Empty:
                    continue
                if chunk is None:
                    finished_streams.add(stream_name)
                    continue
                if stream_name == "stderr":
                    stderr_file.write(chunk)
                    stderr_file.flush()
                    continue
                stdout_file.write(chunk)
                stdout_file.flush()
                stdout_buffer += chunk
                while b"\n" in stdout_buffer:
                    line, stdout_buffer = stdout_buffer.split(b"\n", 1)
                    accept_event(line)
            if stdout_buffer:
                accept_event(stdout_buffer)
    except BaseException:
        _kill_process_group(process)
        raise
    finally:
        for thread in threads:
            thread.join(timeout=1)

    returncode = process.wait(timeout=5)
    if returncode != 0:
        raise SystemExit(f"Codex execution failed with exit code {returncode}.")
    if event_error is not None:
        raise SystemExit(event_error)
    if observed_session is None:
        raise SystemExit("Codex did not emit a thread.started session identifier.")
    if not completed:
        raise SystemExit("Codex did not emit a turn.completed event.")
    if not response_path.exists():
        raise SystemExit(f"Codex did not write the final response file: {response_path}")
    response = response_path.read_text(encoding="utf-8").strip()
    if not response:
        raise SystemExit("Codex wrote an empty final response.")
    return response


def _prepare_context(
    *,
    repo: str,
    issue: int,
    phase: str,
    branch_override: str | None,
    issue_data: dict[str, Any] | None,
) -> Any:
    config.require_enabled_provider()
    if branch_override is None:
        return prepare_phase_execution_context(repo, phase, issue, issue_data=issue_data)
    return prepare_branch_context(
        repo,
        branch=branch_override,
        branch_log_label="Resolved explicit target branch",
        issue_data=issue_data,
    )


def _new_turn_dir(phase: str) -> Path:
    output_root = config.WORKSPACE / "workspace" / "codex"
    output_root.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=f"phase-{phase.lower()}-", dir=output_root))


def _guarded_prompt(prompt: str) -> str:
    return f"{prompt.rstrip()}\n\n{PYTHON_OWNED_OPERATIONS}\n"


def _call_ordinary_turn(prompt: str, *, cwd: Path, phase: str, schema: dict | None = None) -> str:
    return call_codex(
        _guarded_prompt(prompt),
        cwd=cwd,
        turn_dir=_new_turn_dir(phase),
        session_id=None,
        schema=schema,
        model=getattr(config, "CODEX_MODEL", None),
        timeout=getattr(config, "ROLE_TIMEOUT", 1200),
    )


def _run_preparation_phase(
    prompt: str,
    *,
    repo: str,
    issue: int,
    phase: str,
    session_scope: str = "",
    issue_data: dict[str, Any] | None = None,
    schema: dict | None = None,
) -> str:
    """Run a conversation-independent Codex phase and return its final response."""
    del session_scope
    context = _prepare_context(
        repo=repo,
        issue=issue,
        phase=phase,
        branch_override=None,
        issue_data=issue_data,
    )
    validate_required_artifacts(context.local_path)
    return _call_ordinary_turn(prompt, cwd=context.local_path, phase=phase, schema=schema)


COMMENT_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {"response": {"type": "string"}},
    "required": ["response"],
    "additionalProperties": False,
}


def decode_comment_response(content: str) -> str:
    """Decode the transport envelope before Python renders the public comment."""
    try:
        payload = json.loads(_strip_optional_json_fence(content))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid Codex comment response: {exc}") from exc
    if (
        not isinstance(payload, dict)
        or set(payload) != {"response"}
        or not isinstance(payload["response"], str)
        or not payload["response"].strip()
    ):
        raise SystemExit("Invalid Codex comment response: expected one nonempty 'response' string.")
    return payload["response"]


def run_codex_comment_phase(
    prompt: str,
    *,
    repo: str,
    issue: int,
    phase: str,
    session_scope: str = "",
    issue_data: dict[str, Any] | None = None,
) -> str:
    """Return validated Markdown; JSON serialization belongs to the harness."""
    content = _run_preparation_phase(
        prompt, repo=repo, issue=issue, phase=phase,
        session_scope=session_scope, issue_data=issue_data,
        schema=COMMENT_RESPONSE_SCHEMA,
    )
    return decode_comment_response(content)


def _strip_optional_json_fence(content: str) -> str:
    stripped = content.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if (
        len(lines) >= 3
        and lines[0].strip().lower() in {"```", "```json"}
        and lines[-1].strip() == "```"
    ):
        return "\n".join(lines[1:-1]).strip()
    return stripped


def run_codex_json_phase(
    prompt: str,
    *,
    repo: str,
    issue: int,
    phase: str,
    session_scope: str = "",
    issue_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run a fresh Codex phase and parse its final response as a JSON object."""
    from .response_schemas import phase_response_schema
    from .reference_resolution import phase_source_beats, retained_beat_names, new_beat_prefix
    source_beats = phase_source_beats(issue_data, phase) if issue_data is not None else []
    retained_ids = retained_beat_names(source_beats) if issue_data is not None else None
    new_prefix = new_beat_prefix(source_beats, phase) if issue_data is not None and phase in {'1', '2A', '2B', '2C', '3'} else None

    content = _run_preparation_phase(
        prompt,
        repo=repo,
        issue=issue,
        phase=phase,
        session_scope=session_scope,
        issue_data=issue_data,
        schema=phase_response_schema(phase, retained_ids=retained_ids, new_prefix=new_prefix),
    )
    try:
        payload = json.loads(_strip_optional_json_fence(content))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Codex did not return valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("Codex JSON response must be a JSON object.")
    return payload


def run_codex_implementation_phase(
    task: str,
    *,
    repo: str,
    issue: int,
    phase: str,
    branch_override: str | None = None,
    session_scope: str = "",
    issue_data: dict[str, Any] | None = None,
) -> None:
    """Run an ordinary implementation phase with its phase-appropriate completion gate."""
    del session_scope
    config.require_enabled_provider()
    if phase == "9":
        raise SystemExit(
            "Phase 9 direct Codex implementation is disabled; use the native-session roundtable."
        )
    if phase == "5":
        from .cycles import ready_assignment, bind_issue
        from .github_ops import fetch_issue_data

        if issue_data is None:
            issue_data = fetch_issue_data(repo, issue)
        bind_issue(issue_data, repo, issue)
        ready_assignment(issue_data)
    context = _prepare_context(
        repo=repo,
        issue=issue,
        phase=phase,
        branch_override=branch_override,
        issue_data=issue_data,
    )
    validate_required_artifacts(context.local_path)

    pending_task = task
    for attempt in range(1, MAX_VALIDATION_ATTEMPTS + 1):
        response = _call_ordinary_turn(pending_task, cwd=context.local_path, phase=phase)
        if response:
            log_multiline("Assistant response", response)

        if phase == '5':
            scene = ready_assignment(issue_data)['element']
            preparation = context.local_path / 'scene_materials' / scene['placement']['scene_id'] / 'preparation.md'
            if not preparation.is_file() or not preparation.read_text().strip():
                raise SystemExit('Netzach must produce nonempty scene preparation.md before delivery.')
            validate_required_artifacts(context.local_path)
            return
        if phase in {"7", "8"}:
            from .scene_materials import validate_phase_artifacts

            validate_phase_artifacts(context.local_path, phase, issue)
            return
        if phase not in REPOSITORY_VALIDATION_PHASES:
            return

        test_result = run_phase_tests(
            repo=repo,
            issue=issue,
            phase=phase,
            branch_override=branch_override,
            issue_data=issue_data,
        )
        if test_result.stdout:
            print(test_result.stdout)
        if test_result.stderr:
            print(test_result.stderr, file=sys.stderr)
        if test_result.returncode == 0:
            return
        if attempt >= MAX_VALIDATION_ATTEMPTS:
            raise SystemExit(f"Validation command contract failed ({VALIDATION_COMMAND_CONTRACT}).")

        retry_number = attempt
        log_error(
            "Validation failed; requesting a scoped Codex retry with test output context "
            f"(retry {retry_number}/{MAX_VALIDATION_RETRIES})."
        )
        pending_task = build_single_retry_fix_task(
            summarize_test_output(test_result), retry_number=retry_number
        )


def finalize_phase_delivery(**kwargs: Any) -> str:
    """Delegate all commit, push, and pull-request ownership to Python delivery utilities."""
    config.require_enabled_provider()
    return utils_finalize_phase_delivery(**kwargs)
