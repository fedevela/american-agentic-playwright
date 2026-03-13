from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
from typing import Any

from .config import (
    IMPLEMENTATION_PHASES,
    PRE_IMPLEMENTATION_PHASES,
    SESSION_STATE_PATH,
    TARGET_REPO_CONFIG_MAP,
    WORKSPACE,
    TargetRepoConfig,
)
from .logging_utils import log_error, log_info, log_multiline

TEST_FIX_MAX_ATTEMPTS = 3
TEST_OUTPUT_MAX_CHARS = 12000


@dataclass(frozen=True)
class OpenHandsTargetContext:
    """Describe the verified local checkout and branch OpenHands should use for a phase run."""

    local_path: Path
    branch: str


def managed_repo_root() -> Path:
    """Return the directory that stores isolated OpenHands-managed repository checkouts."""
    return WORKSPACE / ".openhands" / "repos"


def managed_repo_slug(repo: str) -> str:
    """Normalize owner/repo into a filesystem-safe stable directory name."""
    return repo.replace("/", "__")


def managed_repo_path(repo: str) -> Path:
    """Return the isolated checkout path for a repository."""
    return managed_repo_root() / managed_repo_slug(repo)


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


def resolve_target_repo_config(repo: str) -> TargetRepoConfig:
    """Resolve the configured local checkout and branch policy for a GitHub repository."""
    config = TARGET_REPO_CONFIG_MAP.get(repo)
    if config is None:
        raise SystemExit(
            f"No local target repository config exists for {repo}. "
            "Add it to TARGET_REPO_CONFIG_MAP before running this phase."
        )
    return config


def ensure_managed_repo_checkout(repo: str, source_path: Path) -> Path:
    """Create or reuse an isolated managed clone used exclusively by OpenHands runs."""
    managed_path = managed_repo_path(repo)
    if (managed_path / ".git").exists():
        log_info(f"Using existing OpenHands managed checkout: {managed_path}")
        return managed_path

    if managed_path.exists():
        raise SystemExit(f"OpenHands managed checkout path exists but is not a git checkout: {managed_path}")

    managed_path.parent.mkdir(parents=True, exist_ok=True)
    log_info(f"Creating OpenHands managed checkout from source: {source_path} -> {managed_path}")
    clone_result = subprocess.run(
        ["git", "clone", "--no-hardlinks", str(source_path), str(managed_path)],
        text=True,
        capture_output=True,
        timeout=300,
    )
    if clone_result.returncode != 0:
        raise SystemExit(
            "Failed to create OpenHands managed checkout for "
            f"{repo}.\nstdout:\n{clone_result.stdout}\nstderr:\n{clone_result.stderr}"
        )

    source_origin_result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=source_path,
        text=True,
        capture_output=True,
        timeout=60,
    )
    source_origin = (source_origin_result.stdout or "").strip()
    if source_origin_result.returncode == 0 and source_origin:
        set_origin_result = subprocess.run(
            ["git", "remote", "set-url", "origin", source_origin],
            cwd=managed_path,
            text=True,
            capture_output=True,
            timeout=60,
        )
        if set_origin_result.returncode != 0:
            raise SystemExit(
                "Failed to set managed checkout origin URL from source repository.\n"
                f"stdout:\n{set_origin_result.stdout}\nstderr:\n{set_origin_result.stderr}"
            )
    else:
        raise SystemExit(
            "Failed to read source repository origin URL; cannot initialize managed checkout deterministically.\n"
            f"stdout:\n{source_origin_result.stdout}\nstderr:\n{source_origin_result.stderr}"
        )

    return managed_path


def resolve_phase_execution_branch(repo: str, phase: str, issue: int) -> str:
    """Return the branch that should back this phase run."""
    config = resolve_target_repo_config(repo)
    if phase in PRE_IMPLEMENTATION_PHASES:
        return config.main_branch
    if phase in IMPLEMENTATION_PHASES:
        return f"{config.issue_branch_prefix}{issue}"
    raise SystemExit(f"Unknown phase '{phase}' for branch resolution.")


def git_run(local_path: Path, args: list[str], *, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    """Run a git command inside the target repository with consistent logging."""
    preview = " ".join(args[:4])
    log_info(f"Git: {preview}{' ...' if len(args) > 4 else ''}")
    return subprocess.run(
        ["git", *args],
        cwd=local_path,
        text=True,
        capture_output=capture_output,
        timeout=120,
    )


def current_branch(local_path: Path) -> str:
    """Read the currently checked-out git branch for the target repository."""
    result = git_run(local_path, ["branch", "--show-current"], capture_output=True)
    if result.returncode != 0:
        raise SystemExit(f"Failed to determine current branch in {local_path}.")
    return (result.stdout or "").strip()


def branch_exists(local_path: Path, branch: str) -> bool:
    """Return True when the named branch already exists locally."""
    result = git_run(local_path, ["rev-parse", "--verify", branch], capture_output=True)
    return result.returncode == 0


def ensure_git_branch(local_path: Path, branch: str, *, base_branch: str) -> None:
    """Switch to the requested branch, requiring non-base branches to exist already."""
    active_branch = current_branch(local_path)
    if active_branch == branch:
        log_info(f"Git branch already active: {branch}")
        return

    if branch_exists(local_path, branch):
        log_info(f"Switching target repository to existing branch '{branch}'")
        result = git_run(local_path, ["switch", branch], capture_output=True)
        if result.returncode != 0:
            raise SystemExit(f"Failed to switch {local_path} to branch '{branch}'.")
        return

    if branch == base_branch:
        raise SystemExit(f"Base branch '{base_branch}' does not exist locally in {local_path}.")

    raise SystemExit(
        f"Required branch '{branch}' does not exist in {local_path}. "
        "Phase 4/Tiferet must create child issue branches before downstream phase execution."
    )


def create_issue_branches_for_child_issues(repo: str, issue_numbers: list[int]) -> None:
    """Create missing issue branches for Tiferet-created child issues in the managed checkout."""
    config, local_path = prepare_target_repo_checkout(repo)
    ensure_git_branch(local_path, config.main_branch, base_branch=config.main_branch)

    for issue_number in issue_numbers:
        branch_name = f"{config.issue_branch_prefix}{issue_number}"
        if branch_exists(local_path, branch_name):
            log_info(f"Issue branch already exists: {branch_name}")
            continue

        # Always branch from the configured main branch for deterministic child issue roots.
        ensure_git_branch(local_path, config.main_branch, base_branch=config.main_branch)
        log_info(f"Creating child issue branch '{branch_name}' from '{config.main_branch}'")
        result = git_run(local_path, ["switch", "-c", branch_name, config.main_branch], capture_output=True)
        if result.returncode != 0:
            raise SystemExit(
                f"Failed to create child issue branch '{branch_name}' from '{config.main_branch}' "
                f"in {local_path}."
            )

    ensure_git_branch(local_path, config.main_branch, base_branch=config.main_branch)


def prepare_target_repo_checkout(repo: str) -> tuple[TargetRepoConfig, Path]:
    """Resolve the configured source checkout and return the isolated managed checkout path."""
    config = resolve_target_repo_config(repo)
    log_info(
        "Loaded target repository config: "
        f"repo={repo}, path={config.local_path}, main_branch={config.main_branch}, "
        f"issue_branch_prefix={config.issue_branch_prefix}"
    )
    local_path = config.local_path
    if not local_path.exists():
        raise SystemExit(f"Configured target repository path does not exist for {repo}: {local_path}")
    if not (local_path / ".git").exists():
        raise SystemExit(f"Configured target repository path is not a git checkout: {local_path}")
    log_info(f"Verified source repository path exists: {local_path}")

    managed_path = ensure_managed_repo_checkout(repo, local_path)
    if not managed_path.exists() or not (managed_path / ".git").exists():
        raise SystemExit(f"OpenHands managed checkout is missing or invalid after setup: {managed_path}")
    log_info(f"Verified managed repository path exists: {managed_path}")
    return config, managed_path


def prepare_branch_context(repo: str, *, branch: str, branch_log_label: str) -> OpenHandsTargetContext:
    """Resolve and verify the target repository checkout for the requested branch."""
    config, local_path = prepare_target_repo_checkout(repo)
    log_info(f"{branch_log_label}: {branch}")
    ensure_git_branch(local_path, branch, base_branch=config.main_branch)
    verified_branch = current_branch(local_path)
    if verified_branch != branch:
        raise SystemExit(
            f"Target repository branch verification failed for {repo}: "
            f"expected '{branch}', found '{verified_branch}'."
        )
    log_info(f"Verified target repository branch loaded: {verified_branch}")
    return OpenHandsTargetContext(local_path=local_path, branch=verified_branch)


def prepare_phase_execution_context(repo: str, phase: str, issue: int) -> OpenHandsTargetContext:
    """Resolve and verify the target repository checkout OpenHands should use."""
    branch = resolve_phase_execution_branch(repo, phase, issue)
    return prepare_branch_context(repo, branch=branch, branch_log_label=f"Resolved target branch for phase {phase.upper()}")


def run_openhands(
    prompt: str,
    *,
    repo: str,
    issue: int,
    phase: str,
    branch_override: str | None = None,
    session_scope: str = "",
) -> subprocess.CompletedProcess[str]:
    """Run OpenHands headlessly and capture output in the configured target repository."""
    context = (
        prepare_phase_execution_context(repo, phase, issue)
        if branch_override is None
        else prepare_openhands_branch_context(repo, branch_override)
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
    result = subprocess.run(
        command,
        cwd=context.local_path,
        text=True,
        capture_output=True,
        timeout=600,
        env=openhands_env(),
    )
    log_info(f"OpenHands exit code: {result.returncode}")
    return result


def prepare_openhands_branch_context(repo: str, branch: str) -> OpenHandsTargetContext:
    """Resolve and verify the target repository checkout for a specific explicit branch."""
    return prepare_branch_context(repo, branch=branch, branch_log_label="Resolved explicit target branch")


def run_phase_tests(
    *,
    repo: str,
    issue: int,
    phase: str,
    branch_override: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run repository validation command for a phase using the same checkout/branch context as OpenHands."""
    context = (
        prepare_phase_execution_context(repo, phase, issue)
        if branch_override is None
        else prepare_openhands_branch_context(repo, branch_override)
    )
    log_info("Running validation command: npm run test")
    return subprocess.run(
        ["npm", "run", "test"],
        cwd=context.local_path,
        text=True,
        capture_output=True,
        timeout=1200,
    )


def summarize_test_output(result: subprocess.CompletedProcess[str]) -> str:
    """Build a bounded combined test output payload suitable for prompt feedback."""
    parts: list[str] = []
    if result.stdout:
        parts.append(result.stdout)
    if result.stderr:
        parts.append(result.stderr)
    combined = "\n".join(parts).strip() or "(no test output captured)"
    if len(combined) <= TEST_OUTPUT_MAX_CHARS:
        return combined
    return combined[-TEST_OUTPUT_MAX_CHARS:]


def build_test_failure_fix_task(test_output: str, *, attempt: int, max_attempts: int) -> str:
    """Build a follow-up task that asks OpenHands to fix failing tests based on captured output."""
    return (
        "Your previous changes were applied, but required repository validation failed.\n\n"
        "Run and satisfy exactly this command contract:\n"
        "- `npm run test`\n\n"
        f"Current fix attempt: {attempt} of {max_attempts}.\n\n"
        "Failure output:\n"
        "```text\n"
        f"{test_output}\n"
        "```\n\n"
        "Apply minimal code changes to make `npm run test` pass, then finish."
    )


def extract_message_events(output: str) -> list[dict[str, Any]]:
    """Extract JSON event payloads from OpenHands stdout."""
    events: list[dict[str, Any]] = []
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
            events.append(event)
        cursor = brace_index + consumed

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


def run_openhands_comment_phase(
    prompt: str,
    *,
    repo: str,
    issue: int,
    phase: str,
    session_scope: str = "",
) -> str:
    """Run OpenHands and return the assistant reply text."""
    log_info("Requesting comment response from OpenHands")
    result = run_openhands(prompt, repo=repo, issue=issue, phase=phase, session_scope=session_scope)
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
) -> dict[str, Any]:
    """Run OpenHands and parse the final assistant reply as JSON."""
    log_info("Requesting JSON response from OpenHands")
    content = run_openhands_comment_phase(prompt, repo=repo, issue=issue, phase=phase, session_scope=session_scope)
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
) -> None:
    """Run an implementation or validation phase through OpenHands."""
    print("=" * 60)
    print("OpenHands Agent Execution")
    print("=" * 60)
    print(f"Task: {task[:200]}...")
    print("=" * 60)

    pending_task = task
    for attempt in range(1, TEST_FIX_MAX_ATTEMPTS + 1):
        result = run_openhands(
            pending_task,
            repo=repo,
            issue=issue,
            phase=phase,
            branch_override=branch_override,
            session_scope=session_scope,
        )
        if result.returncode != 0:
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            sys.exit(result.returncode)

        assistant_message = last_assistant_message(result.stdout)
        if assistant_message:
            log_multiline("Assistant message", assistant_message)
        elif result.stdout:
            log_info("OpenHands run completed with no parsed assistant message (raw output suppressed).")

        test_result = run_phase_tests(repo=repo, issue=issue, phase=phase, branch_override=branch_override)
        if test_result.stdout:
            print(test_result.stdout)
        if test_result.stderr:
            print(test_result.stderr, file=sys.stderr)

        if test_result.returncode == 0:
            print("\nAgent execution complete.")
            return

        if attempt >= TEST_FIX_MAX_ATTEMPTS:
            raise SystemExit(
                f"Validation command `npm run test` failed after {TEST_FIX_MAX_ATTEMPTS} attempts."
            )

        log_error("Validation command failed; requesting OpenHands to apply a targeted fix.")
        pending_task = build_test_failure_fix_task(
            summarize_test_output(test_result),
            attempt=attempt + 1,
            max_attempts=TEST_FIX_MAX_ATTEMPTS,
        )
