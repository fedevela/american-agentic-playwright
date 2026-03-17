from __future__ import annotations

import json
import os
from dataclasses import dataclass
from queue import Empty, Queue
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Any

from .config import (
    IMPLEMENTATION_PHASES,
    SESSION_STATE_PATH,
    WORKSPACE,
)
from .logging_utils import log_error, log_info, log_multiline
from .runner_utils import (
    MAX_VALIDATION_ATTEMPTS,
    MAX_VALIDATION_RETRIES,
    VALIDATION_COMMAND_CONTRACT,
    RunnerTargetContext,
    build_single_retry_fix_task,
    finalize_phase_delivery as utils_finalize_phase_delivery,
    prepare_branch_context,
    prepare_phase_execution_context,
    prepare_target_repo_checkout,
    run_phase_tests,
    summarize_test_output,
)

OPENHANDS_HEARTBEAT_SECONDS = 15
OPENHANDS_RUN_TIMEOUT_SECONDS = 600
VALIDATION_PHASES = set(IMPLEMENTATION_PHASES)

@dataclass(frozen=True)
class OpenHandsTargetContext:
    """Describe the verified local checkout and branch OpenHands should use for a phase run."""
    # Legacy wrapper around RunnerTargetContext
    local_path: Path
    branch: str

def resolve_openhands_model_connection() -> tuple[str, str]:
    """Return the effective OpenHands model name and connection target."""
    config_path = WORKSPACE / ".openhands" / "config.json"
    configured_model = ""
    if config_path.exists():
        try:
            config_payload = json.loads(config_path.read_text())
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid OpenHands config JSON at {config_path}: {exc}") from exc
        if not isinstance(config_payload, dict):
            raise SystemExit(f"Invalid OpenHands config payload at {config_path}: expected a JSON object.")
        configured_model = str(((config_payload.get("config") or {}).get("model")) or "").strip()

    env = openhands_env()
    model_name = env.get("LLM_MODEL") or configured_model or "(unset)"
    connection = env.get("LLM_BASE_URL") or env.get("DASHSCOPE_API_BASE") or "default"
    return model_name, connection


def openhands_env() -> dict[str, str]:
    """Build the environment used by headless OpenHands subprocesses."""
    conversations_dir = WORKSPACE / ".openhands" / "conversations"
    conversations_dir.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    env["OPENHANDS_CONVERSATIONS_DIR"] = str(conversations_dir)
    env["OPENHANDS_DISABLE_UPDATE_CHECK"] = "1"

    if env.get("DASHSCOPE_API_KEY") and not env.get("LLM_API_KEY"):
        env["LLM_API_KEY"] = env["DASHSCOPE_API_KEY"]
    if env.get("DASHSCOPE_API_BASE") and not env.get("LLM_BASE_URL"):
        env["LLM_BASE_URL"] = env["DASHSCOPE_API_BASE"]
    if env.get("DASHSCOPE_API_KEY") and not env.get("LLM_MODEL"):
        env["LLM_MODEL"] = "dashscope/qwen3-coder-plus"

    return env


def session_key(repo: str, issue: int) -> str:
    """Build the base conversation key for a repo/issue pair before any phase scoping is applied."""
    return f"{repo}#{issue}"


def load_session_state() -> dict[str, str]:
    """Load persisted issue -> conversation id mappings used to resume per-issue sessions."""
    if not SESSION_STATE_PATH.exists():
        return {}
    try:
        payload = json.loads(SESSION_STATE_PATH.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Session state file is invalid JSON at {SESSION_STATE_PATH}: {exc}") from exc

    if not isinstance(payload, dict):
        raise SystemExit(f"Session state file must contain a JSON object at {SESSION_STATE_PATH}.")
    return payload


def save_session_state(state: dict[str, str]) -> None:
    """Persist issue -> conversation id mappings so later phase runs can resume context."""
    SESSION_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SESSION_STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True))


def extract_conversation_id(output: str) -> str:
    """Extract the conversation id from OpenHands stdout so it can be reused on the next run."""
    marker = "Conversation ID:"
    for line in output.splitlines():
        if marker in line:
            return line.split(marker, 1)[1].strip()
    return ""


def openhands_session_key(repo: str, issue: int, session_scope: str) -> str:
    """Build the persisted session key for a run, including phase scoping when enabled."""
    base_key = session_key(repo, issue)
    return base_key if not session_scope else f"{base_key}:{session_scope}"


def create_issue_branches_for_child_issues(repo: str, parent_issue: int, issue_numbers: list[int]) -> None:
    """Create missing issue branches for Tiferet-created child issues, branching from the parent issue branch."""
    from .runner_utils import ensure_git_branch, branch_exists, git_run, resolve_target_repo_config
    config = resolve_target_repo_config(repo)
    _, local_path = prepare_target_repo_checkout(repo)
    
    # The parent issue branch name (e.g. issue/51)
    parent_branch = f"{config.issue_branch_prefix}{parent_issue}"
    
    if not branch_exists(local_path, parent_branch):
        log_info(f"Parent branch '{parent_branch}' does not exist; creating it from '{config.main_branch}'.")
        result = git_run(local_path, ["switch", "-c", parent_branch, config.main_branch], capture_output=True)
        if result.returncode != 0:
            raise SystemExit(f"Failed to create missing parent branch '{parent_branch}' from '{config.main_branch}'.")
        log_info(f"Pushing new parent branch '{parent_branch}' to origin...")
        git_run(local_path, ["push", "origin", parent_branch])

    ensure_git_branch(local_path, parent_branch, base_branch=config.main_branch)

    for issue_number in issue_numbers:
        branch_name = f"{config.issue_branch_prefix}{issue_number}"
        if branch_exists(local_path, branch_name):
            log_info(f"Issue branch already exists: {branch_name}")
            continue

        log_info(f"Creating child issue branch '{branch_name}' from '{parent_branch}'")
        result = git_run(local_path, ["switch", "-c", branch_name, parent_branch], capture_output=True)
        if result.returncode != 0:
            raise SystemExit(
                f"Failed to create child issue branch '{branch_name}' from '{parent_branch}' "
                f"in {local_path}."
            )

    ensure_git_branch(local_path, parent_branch, base_branch=config.main_branch)


def _run_openhands_command(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_seconds: int = OPENHANDS_RUN_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    """Run OpenHands and stream stdout/stderr lines live while collecting full output."""
    process = subprocess.Popen(  # noqa: S603 - command is static argv array, not shell-expanded
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        bufsize=1,
    )

    queue: Queue[tuple[str, str | None]] = Queue()

    def reader(stream_name: str, stream: Any) -> None:
        try:
            for line in stream:
                queue.put((stream_name, line))
        finally:
            queue.put((stream_name, None))
            stream.close()

    stdout_stream = process.stdout
    stderr_stream = process.stderr
    if stdout_stream is None or stderr_stream is None:
        raise SystemExit("Failed to open OpenHands process streams.")

    stdout_thread = threading.Thread(target=reader, args=("stdout", stdout_stream), daemon=True)
    stderr_thread = threading.Thread(target=reader, args=("stderr", stderr_stream), daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    started_at = time.monotonic()
    timeout_deadline = started_at + timeout_seconds
    heartbeat_deadline = started_at + OPENHANDS_HEARTBEAT_SECONDS
    finished_streams: set[str] = set()
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    while True:
        now = time.monotonic()
        if now >= timeout_deadline and process.poll() is None:
            process.kill()
            raise subprocess.TimeoutExpired(command, timeout_seconds, output="".join(stdout_lines), stderr="".join(stderr_lines))

        if len(finished_streams) == 2 and process.poll() is not None:
            break

        try:
            stream_name, line = queue.get(timeout=1)
        except Empty:
            if process.poll() is None and now >= heartbeat_deadline:
                elapsed_seconds = int(now - started_at)
                log_info(f"OpenHands still running... {elapsed_seconds}s elapsed")
                heartbeat_deadline = now + OPENHANDS_HEARTBEAT_SECONDS
            continue

        if line is None:
            finished_streams.add(stream_name)
            continue

        if stream_name == "stdout":
            stdout_lines.append(line)
            print(line, end="")
        else:
            stderr_lines.append(line)
            print(line, end="", file=sys.stderr)

    stdout_thread.join(timeout=1)
    stderr_thread.join(timeout=1)
    returncode = process.wait(timeout=5)
    return subprocess.CompletedProcess(
        args=command,
        returncode=returncode,
        stdout="".join(stdout_lines),
        stderr="".join(stderr_lines),
    )


def run_openhands(
    prompt: str,
    *,
    repo: str,
    issue: int,
    phase: str,
    branch_override: str | None = None,
    session_scope: str = "",
    issue_data: dict[str, Any] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run OpenHands headlessly and capture output in the configured target repository."""
    context = (
        prepare_phase_execution_context(repo, phase, issue, issue_data=issue_data)
        if branch_override is None
        else prepare_branch_context(repo, branch=branch_override, branch_log_label="Resolved explicit target branch", issue_data=issue_data)
    )

    if session_scope:
        log_info(f"OpenHands session scope metadata: {session_scope}")
    log_info("Session mode: start new conversation (resume disabled by policy)")
    log_info(f"OpenHands target repository loaded: {context.local_path}")
    log_info(f"OpenHands target branch loaded: {context.branch}")

    command = ["openhands"]
    command.extend(
        [
            "--task",
            prompt,
            "--headless",
            "--json",
            "--override-with-envs",
            "--exit-without-confirmation",
        ]
    )

    log_info("Launching OpenHands headless run")
    log_info("OpenHands execution in progress; streaming JSONL events live.")
    result = _run_openhands_command(
        command,
        cwd=context.local_path,
        env=openhands_env(),
    )
    log_info(f"OpenHands exit code: {result.returncode}")
    return result


def finalize_phase_delivery(
    *,
    repo: str,
    issue: int,
    phase: str,
    issue_title: str = "",
    branch_override: str | None = None,
    issue_data: dict[str, Any] | None = None,
) -> str:
    """Commit and push phase changes, then return a summary suitable for a GitHub issue comment."""
    return utils_finalize_phase_delivery(
        repo=repo,
        issue=issue,
        phase=phase,
        issue_title=issue_title,
        branch_override=branch_override,
        issue_data=issue_data,
    )


def extract_message_events(output: str) -> list[dict[str, Any]]:
    """Extract JSON event payloads from OpenHands stdout (marker-based and JSONL)."""
    events: list[dict[str, Any]] = []
    seen: set[str] = set()
    marker = "--JSON Event--"
    decoder = json.JSONDecoder()
    cursor = 0

    while True:
        marker_index = output.find(marker, cursor)
        if marker_index == -1:
            break

        search_index = marker_index + len(marker)
        brace_index = output.find("{", search_index)
        if brace_index == -1:
            break

        try:
            event, consumed = decoder.raw_decode(output[brace_index:])
        except json.JSONDecodeError:
            cursor = search_index
            continue

        if isinstance(event, dict):
            key = json.dumps(event, sort_keys=True, default=str)
            if key not in seen:
                seen.add(key)
                events.append(event)
        cursor = brace_index + consumed

    # Also consume plain JSONL event lines from `--json` output mode.
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped.startswith("{") or not stripped.endswith("}"):
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        key = json.dumps(event, sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            events.append(event)

    return events


def last_assistant_message(output: str) -> str:
    """Return the final assistant-authored message from parsed OpenHands events."""
    message = ""
    for event in extract_message_events(output):
        if event.get("kind") != "MessageEvent":
            continue
        llm_message = event.get("llm_message") or {}
        if llm_message.get("role") != "assistant":
            continue
        content = llm_message.get("content") or []
        chunks = [item.get("text", "") for item in content if isinstance(item, dict)]
        if chunks:
            message = "".join(chunks).strip()
    return message


def _truncate_for_log(value: str, limit: int = 140) -> str:
    """Trim long event text for concise trigger logs."""
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def action_observation_event_lines(output: str, *, max_events: int = 40) -> list[str]:
    """Render action/observation events from OpenHands JSON output for trigger logs."""
    lines: list[str] = []

    for event in extract_message_events(output):
        event_type = str(event.get("type") or "")
        event_kind = str(event.get("kind") or "")

        if event_type in {"action", "observation"}:
            if event_type == "action":
                action = event.get("action")
                if isinstance(action, dict):
                    action_name = str(action.get("command") or action.get("type") or "action")
                    path = str(action.get("path") or event.get("path") or "")
                    suffix = f" path={path}" if path else ""
                    lines.append(f"type=action action={_truncate_for_log(action_name)}{suffix}")
                else:
                    path = str(event.get("path") or "")
                    suffix = f" path={path}" if path else ""
                    lines.append(f"type=action action={_truncate_for_log(str(action))}{suffix}")
            else:
                content = _truncate_for_log(str(event.get("content") or ""))
                lines.append(f"type=observation content={content}")
            continue

        if event_kind == "ActionEvent":
            tool_name = str(event.get("tool_name") or "")
            summary = str(event.get("summary") or "")
            action = event.get("action") or {}
            command = str(action.get("command") or "")
            path = str(action.get("path") or "")
            details = " ".join(part for part in [f"command={command}" if command else "", f"path={path}" if path else ""] if part)
            details_suffix = f" {details}" if details else ""
            lines.append(
                f"kind=ActionEvent tool={tool_name or '(unknown)'} "
                f"summary={_truncate_for_log(summary)}{details_suffix}"
            )
            continue

        if event_kind == "ObservationEvent":
            tool_name = str(event.get("tool_name") or "")
            observation = event.get("observation") or {}
            content = ""
            if isinstance(observation, dict):
                content_items = observation.get("content")
                if isinstance(content_items, list) and content_items:
                    first_item = content_items[0]
                    if isinstance(first_item, dict):
                        content = str(first_item.get("text") or "")
            lines.append(
                f"kind=ObservationEvent tool={tool_name or '(unknown)'} "
                f"content={_truncate_for_log(content)}"
            )

    if len(lines) <= max_events:
        return lines
    overflow = len(lines) - max_events
    return [*lines[:max_events], f"... truncated {overflow} additional action/observation events"]


def run_openhands_comment_phase(
    prompt: str,
    *,
    repo: str,
    issue: int,
    phase: str,
    session_scope: str = "",
    issue_data: dict[str, Any] | None = None,
) -> str:
    """Run OpenHands and return the assistant reply text."""
    log_info("Requesting comment response from OpenHands")
    result = run_openhands(prompt, repo=repo, issue=issue, phase=phase, session_scope=session_scope, issue_data=issue_data)
    if result.returncode != 0:
        log_error(f"OpenHands failed for {repo}#{issue} with exit code {result.returncode}")
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        sys.exit(result.returncode)

    comment = last_assistant_message(result.stdout)
    if not comment:
        print(result.stdout)
        log_error("OpenHands returned no assistant message.")
        sys.exit(1)
    log_info(f"Assistant message extracted ({len(comment)} chars)")
    return comment


def run_openhands_json_phase(
    prompt: str,
    *,
    repo: str,
    issue: int,
    phase: str,
    session_scope: str = "",
    issue_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run OpenHands and parse the final assistant reply as JSON."""
    log_info("Requesting JSON response from OpenHands")
    content = run_openhands_comment_phase(prompt, repo=repo, issue=issue, phase=phase, session_scope=session_scope, issue_data=issue_data)
    log_info("Parsing JSON from assistant reply")
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        log_error("Assistant reply was not valid JSON for phase 4/Tiferet")
        print(content)
        raise SystemExit(f"OpenHands did not return valid JSON for phase 4/Tiferet: {exc}") from exc


def run_openhands_implementation_phase(
    task: str,
    *,
    repo: str,
    issue: int,
    phase: str,
    branch_override: str | None = None,
    session_scope: str = "",
    issue_data: dict[str, Any] | None = None,
) -> None:
    """Run an implementation or validation phase through OpenHands."""
    print("=" * 60)
    print("OpenHands Agent Execution")
    print("=" * 60)
    print(f"Task: {task[:200]}...")
    print("=" * 60)

    pending_task = task
    for attempt in range(1, MAX_VALIDATION_ATTEMPTS + 1):
        result = run_openhands(
            pending_task,
            repo=repo,
            issue=issue,
            phase=phase,
            branch_override=branch_override,
            session_scope=session_scope,
            issue_data=issue_data,
        )
        if result.returncode != 0:
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            sys.exit(result.returncode)

        assistant_message = last_assistant_message(result.stdout)
        event_lines = action_observation_event_lines(result.stdout or "")
        if event_lines:
            log_multiline("OpenHands action/observation events", "\n".join(event_lines))
        if assistant_message:
            log_multiline("Assistant message", assistant_message)
        elif result.stdout:
            log_info("OpenHands run completed with no parsed assistant message (raw output suppressed).")

        if phase not in VALIDATION_PHASES:
            log_info(
                f"Skipping automated validation for phase {phase}; validation is reserved for phases 5 through 9."
            )
            print("\nAgent execution complete.")
            return

        test_result = run_phase_tests(repo=repo, issue=issue, phase=phase, branch_override=branch_override, issue_data=issue_data)
        if test_result.stdout:
            print(test_result.stdout)
        if test_result.stderr:
            print(test_result.stderr, file=sys.stderr)

        if test_result.returncode == 0:
            print("\nAgent execution complete.")
            return

        if attempt >= MAX_VALIDATION_ATTEMPTS:
            raise SystemExit(f"Validation command contract failed ({VALIDATION_COMMAND_CONTRACT}).")

        retry_number = attempt
        log_error(
            "Validation failed; requesting a scoped OpenHands retry with test output context "
            f"(retry {retry_number}/{MAX_VALIDATION_RETRIES})."
        )
        pending_task = build_single_retry_fix_task(summarize_test_output(test_result), retry_number=retry_number)
