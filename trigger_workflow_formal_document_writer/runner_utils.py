from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import (
    IMPLEMENTATION_PHASES,
    PHASE_DISPLAY_NAME_MAP,
    PRE_IMPLEMENTATION_PHASES,
    TIFERET_AUTO_ISSUE_PREFIX,
    TARGET_REPO_CONFIG_MAP,
    WORKSPACE,
    TargetRepoConfig,
)
from .logging_utils import log_error, log_info

@dataclass(frozen=True)
class RunnerTargetContext:
    """Describe the verified local checkout and branch a runner should use for a phase run."""
    local_path: Path
    branch: str

def managed_repo_root() -> Path:
    """Return the directory that stores isolated OpenHands-managed repository checkouts."""
    # Keeping the same path for now to avoid confusion, though it's now shared
    return WORKSPACE / ".openhands" / "repos"

def managed_repo_slug(repo: str) -> str:
    """Normalize owner/repo into a filesystem-safe stable directory name."""
    return repo.replace("/", "__")

def managed_repo_path(repo: str) -> Path:
    """Return the isolated checkout path for a repository."""
    return managed_repo_root() / managed_repo_slug(repo)

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
    """Create or reuse an isolated managed clone used exclusively by runner runs."""
    managed_path = managed_repo_path(repo)
    if (managed_path / ".git").exists():
        log_info(f"Using existing managed checkout: {managed_path}")
        return managed_path

    if managed_path.exists():
        raise SystemExit(f"Managed checkout path exists but is not a git checkout: {managed_path}")

    managed_path.parent.mkdir(parents=True, exist_ok=True)
    log_info(f"Creating managed checkout from source: {source_path} -> {managed_path}")
    clone_result = subprocess.run(
        ["git", "clone", "--no-hardlinks", str(source_path), str(managed_path)],
        text=True,
        capture_output=True,
        timeout=300,
    )
    if clone_result.returncode != 0:
        raise SystemExit(
            "Failed to create managed checkout for "
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
            # If switch failed due to local changes, perform a reset and clean in the managed repo.
            log_info(f"Initial switch to '{branch}' failed (dirty state); attempting reset and clean to recover.")
            git_run(local_path, ["reset", "--hard", "HEAD"], capture_output=True)
            git_run(local_path, ["clean", "-fd"], capture_output=True)
            # Second attempt to switch after cleanup.
            result = git_run(local_path, ["switch", branch], capture_output=True)
            if result.returncode != 0:
                log_error(f"Failed to switch {local_path} to branch '{branch}' even after cleanup: {result.stderr or result.stdout or 'no output'}")
                raise SystemExit(f"Failed to switch {local_path} to branch '{branch}'.")
        return

    if branch == base_branch:
        raise SystemExit(f"Base branch '{base_branch}' does not exist locally in {local_path}.")

    raise SystemExit(
        f"Required branch '{branch}' does not exist in {local_path}. "
        "Phase 4/Tiferet must create child issue branches before downstream phase execution."
    )

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
    expected_managed_path = managed_repo_path(repo)
    if managed_path.resolve() != expected_managed_path.resolve():
        raise SystemExit(
            "Managed checkout path mismatch. "
            f"Expected managed clone at {expected_managed_path}, got {managed_path}. "
            "Refusing to run phases outside the managed checkout."
        )
    if managed_path.resolve() == local_path.resolve():
        raise SystemExit(
            "Managed checkout resolved to source repository path. "
            "Refusing to run phases in the source checkout."
        )
    if not managed_path.exists() or not (managed_path / ".git").exists():
        raise SystemExit(f"Managed checkout is missing or invalid after setup: {managed_path}")
    log_info(f"Verified managed repository path exists: {managed_path}")
    return config, managed_path

def prepare_branch_context(
    repo: str,
    *,
    branch: str,
    branch_log_label: str,
    issue_data: dict[str, Any] | None = None,
) -> RunnerTargetContext:
    """Resolve and verify the target repository checkout for the requested branch, including auto-merge from base."""
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

    # Auto-merge from base branch as requested for phases after Tiferet
    parent_issue = extract_parent_issue(str(issue_data.get("body") or "")) if issue_data else None
    base_branch = f"{config.issue_branch_prefix}{parent_issue}" if parent_issue else config.main_branch

    if branch != base_branch:
        log_info(f"Checking for updates from base branch '{base_branch}' to merge into '{branch}'")
        git_run(local_path, ["fetch", "origin"])
        
        # Verify base branch exists on origin
        origin_branch = f"origin/{base_branch}"
        check_base = git_run(local_path, ["rev-parse", "--verify", origin_branch], capture_output=True)
        if check_base.returncode != 0:
            log_error(f"Base branch '{base_branch}' does not exist on origin. Cannot merge.")
            raise SystemExit(f"Missing required base branch '{base_branch}' for issue #{issue}.")

        merge_result = git_run(local_path, ["merge", origin_branch], capture_output=True)
        if merge_result.returncode != 0:
            log_error(f"Automatic merge from '{base_branch}' failed; human intervention required.")
            if "CONFLICT" in (merge_result.stdout or "") or "CONFLICT" in (merge_result.stderr or ""):
                log_error("Merge conflicts detected during branch setup.")
            raise SystemExit(f"Failed to auto-merge '{base_branch}' into '{branch}'. Check for conflicts.")

    return RunnerTargetContext(local_path=local_path, branch=verified_branch)

def prepare_phase_execution_context(repo: str, phase: str, issue: int, issue_data: dict[str, Any] | None = None) -> RunnerTargetContext:
    """Resolve and verify the target repository checkout runner should use."""
    branch = resolve_phase_execution_branch(repo, phase, issue)
    return prepare_branch_context(
        repo,
        branch=branch,
        branch_log_label=f"Resolved target branch for phase {phase.upper()}",
        issue_data=issue_data,
    )

def extract_parent_issue(issue_body: str) -> int | None:
    """Parse the parent issue number from an issue body if it contains the parent-marker."""
    import re
    match = re.search(r"Parent issue: #(\d+)", issue_body)
    if match:
        return int(match.group(1))
    return None

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
    context = (
        prepare_phase_execution_context(repo, phase, issue)
        if branch_override is None
        else prepare_branch_context(repo, branch=branch_override, branch_log_label="Resolved explicit target branch")
    )
    branch = context.branch
    local_path = context.local_path
    config = resolve_target_repo_config(repo)

    # Determine PR base branch. If this is a child issue, PR into the parent issue branch.
    parent_issue = extract_parent_issue(str(issue_data.get("body") or "")) if issue_data else None
    pr_base = f"{config.issue_branch_prefix}{parent_issue}" if parent_issue else config.main_branch

    log_info(f"Preparing delivery for issue #{issue} on branch '{branch}' (PR base: '{pr_base}')")

    # Step: Merge from updated parent/base branch before delivery as requested.
    log_info(f"Merging latest changes from base branch '{pr_base}' into '{branch}' before delivery")
    git_run(local_path, ["fetch", "origin"])
    
    # Verify base branch exists on origin
    origin_base = f"origin/{pr_base}"
    check_base = git_run(local_path, ["rev-parse", "--verify", origin_base], capture_output=True)
    if check_base.returncode != 0:
        log_error(f"Base branch '{pr_base}' does not exist on origin. Cannot merge before delivery.")
        raise SystemExit(f"Missing required base branch '{pr_base}' for delivery of issue #{issue}.")

    merge_result = git_run(local_path, ["merge", origin_base], capture_output=True)
    if merge_result.returncode != 0:
        log_error(f"Automatic merge from '{pr_base}' failed; human intervention required before delivery.")
        if "CONFLICT" in (merge_result.stdout or "") or "CONFLICT" in (merge_result.stderr or ""):
             log_error("Merge conflicts detected during delivery auto-merge.")
        raise SystemExit(f"Failed to auto-merge '{pr_base}' into '{branch}' before delivery. Check for conflicts.")

    status_result = subprocess.run(
        ["git", "status", "--short"],
        cwd=local_path,
        text=True,
        capture_output=True,
        timeout=120,
    )
    if status_result.returncode != 0:
        raise SystemExit(f"Failed to inspect git status before delivery finalization in {local_path}.")
    status_lines = [line.rstrip() for line in (status_result.stdout or "").splitlines() if line.strip()]
    if not status_lines:
        raise SystemExit(
            f"Phase {phase.upper()} finished without repository changes. "
            "Refusing to advance phase without a commit."
        )

    add_result = subprocess.run(
        ["git", "add", "-A"],
        cwd=local_path,
        text=True,
        capture_output=True,
        timeout=120,
    )
    if add_result.returncode != 0:
        raise SystemExit(f"Failed to stage changes for phase {phase.upper()} delivery in {local_path}.")

    normalized_title = " ".join(issue_title.split()).strip()
    if normalized_title.startswith(TIFERET_AUTO_ISSUE_PREFIX):
        normalized_title = normalized_title[len(TIFERET_AUTO_ISSUE_PREFIX) :].strip()
    if not normalized_title:
        raise SystemExit(
            f"Issue title is required for phase {phase.upper()} delivery metadata. "
            "Fallback commit/PR titles are disabled by policy."
        )
    phase_display = PHASE_DISPLAY_NAME_MAP.get(phase, f"Phase {phase}")
    pr_title_tail = normalized_title[:120]
    commit_title_tail = normalized_title[:72]
    commit_message = f"phase:{phase} issue #{issue}: {commit_title_tail}"
    commit_result = subprocess.run(
        ["git", "commit", "-m", commit_message],
        cwd=local_path,
        text=True,
        capture_output=True,
        timeout=120,
    )
    if commit_result.returncode != 0:
        raise SystemExit(
            f"Failed to commit changes for phase {phase.upper()} delivery in {local_path}.\n"
            f"stdout:\n{commit_result.stdout}\n"
            f"stderr:\n{commit_result.stderr}"
        )

    push_result = subprocess.run(
        ["git", "push", "origin", branch],
        cwd=local_path,
        text=True,
        capture_output=True,
        timeout=180,
    )
    if push_result.returncode != 0:
        raise SystemExit(
            f"Failed to push branch '{branch}' for phase {phase.upper()} delivery.\n"
            "Human intervention required; automatic rebase/retry is disabled by policy.\n"
            f"stdout:\n{push_result.stdout}\n"
            f"stderr:\n{push_result.stderr}"
        )
    if (push_result.stdout or "").strip():
        log_info(f"Push output: {(push_result.stdout or '').strip()}")
    if (push_result.stderr or "").strip():
        log_info(f"Push diagnostics: {(push_result.stderr or '').strip()}")

    head_sha_result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=local_path,
        text=True,
        capture_output=True,
        timeout=60,
    )
    if head_sha_result.returncode != 0:
        raise SystemExit(f"Failed to resolve HEAD sha after push for branch '{branch}'.")
    head_sha = (head_sha_result.stdout or "").strip()

    remote_sha_result = subprocess.run(
        ["git", "ls-remote", "--heads", "origin", f"refs/heads/{branch}"],
        cwd=local_path,
        text=True,
        capture_output=True,
        timeout=120,
    )
    if remote_sha_result.returncode != 0:
        raise SystemExit(
            f"Failed to verify remote head for branch '{branch}' after push.\n"
            f"stdout:\n{remote_sha_result.stdout}\n"
            f"stderr:\n{remote_sha_result.stderr}"
        )
    remote_line = (remote_sha_result.stdout or "").strip().splitlines()
    remote_sha = remote_line[0].split()[0].strip() if remote_line else ""
    if not remote_sha:
        raise SystemExit(f"Remote branch '{branch}' was not found after push.")
    if remote_sha != head_sha:
        raise SystemExit(
            f"Push verification failed for branch '{branch}': local HEAD {head_sha} "
            f"does not match origin/{branch} {remote_sha}."
        )

    pr_lookup_result = subprocess.run(
        ["gh", "pr", "list", "--repo", repo, "--head", branch, "--state", "open", "--json", "number,title,url"],
        cwd=local_path,
        text=True,
        capture_output=True,
        timeout=120,
    )
    if pr_lookup_result.returncode != 0:
        raise SystemExit(
            f"Failed to query PRs for branch '{branch}' in {repo}.\n"
            f"stdout:\n{pr_lookup_result.stdout}\n"
            f"stderr:\n{pr_lookup_result.stderr}"
        )
    pr_payload = json.loads(pr_lookup_result.stdout or "[]")
    pr_url = ""
    pr_title = f"Issue #{issue} [{phase_display}]: {pr_title_tail}"
    if isinstance(pr_payload, list) and pr_payload:
        first = pr_payload[0]
        if isinstance(first, dict):
            pr_url = str(first.get("url") or "").strip()

    if not pr_url:
        pr_body = (
            f"Automated phase delivery PR for issue #{issue}.\n\n"
            f"Branch: `{branch}`\n"
            f"Phase: `{phase}` ({phase_display})\n\n"
            f"Closes #{issue}"
        )
        pr_create_result = subprocess.run(
            [
                "gh",
                "pr",
                "create",
                "--repo",
                repo,
                "--base",
                pr_base,
                "--head",
                branch,
                "--title",
                pr_title,
                "--body",
                pr_body,
            ],
            cwd=local_path,
            text=True,
            capture_output=True,
            timeout=120,
        )
        if pr_create_result.returncode != 0:
            raise SystemExit(
                f"Failed to create PR for branch '{branch}' in {repo}.\n"
                f"stdout:\n{pr_create_result.stdout}\n"
                f"stderr:\n{pr_create_result.stderr}"
            )
        pr_url = (pr_create_result.stdout or "").strip()
        if not pr_url:
            raise SystemExit(f"PR creation returned no URL for branch '{branch}' in {repo}.")

    sha_result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=local_path,
        text=True,
        capture_output=True,
        timeout=60,
    )
    if sha_result.returncode != 0:
        raise SystemExit(f"Failed to resolve HEAD sha after delivery push for branch '{branch}'.")
    short_sha = (sha_result.stdout or "").strip()

    changed_files_result = subprocess.run(
        ["git", "show", "--name-only", "--pretty=format:", "HEAD"],
        cwd=local_path,
        text=True,
        capture_output=True,
        timeout=60,
    )
    if changed_files_result.returncode != 0:
        raise SystemExit("Failed to read committed file list for delivery summary.")
    changed_files = [line.strip() for line in changed_files_result.stdout.splitlines() if line.strip()]

    files_block = "\n".join(f"- `{path}`" for path in changed_files) if changed_files else "- `(no file list available)`"
    file_count = len(changed_files)
    return (
        "Implementation delivery summary:\n\n"
        f"- Phase: `{phase}`\n"
        f"- Phase name: `{phase_display}`\n"
        f"- Branch: `{branch}`\n"
        f"- PR base: `{pr_base}`\n"
        f"- PR: {pr_url}\n"
        f"- Commit: `{short_sha}`\n"
        f"- Commit message: `{commit_message}`\n"
        f"- Changed files count: `{file_count}`\n\n"
        "Changed files:\n"
        f"{files_block}"
    )

MAX_VALIDATION_RETRIES = 3
MAX_VALIDATION_ATTEMPTS = 1 + MAX_VALIDATION_RETRIES
TEST_OUTPUT_MAX_CHARS = 12000
VALIDATION_COMMAND_CONTRACT = "`npm run typecheck` -> `npm run build` -> `npm run test` -> `npm run tests:e2e`"
VALIDATION_COMMANDS = (
    ["npm", "run", "typecheck"],
    ["npm", "run", "build"],
    ["npm", "run", "test"],
    ["npm", "run", "tests:e2e"],
)

def run_phase_tests(
    *,
    repo: str,
    issue: int,
    phase: str,
    branch_override: str | None = None,
    issue_data: dict[str, Any] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run repository validation commands for a phase using the same checkout/branch context."""
    context = (
        prepare_phase_execution_context(repo, phase, issue, issue_data=issue_data)
        if branch_override is None
        else prepare_branch_context(repo, branch=branch_override, branch_log_label="Resolved explicit target branch", issue_data=issue_data)
    )
    ensure_playwright_test_prerequisites(context.local_path)
    combined_stdout: list[str] = []
    combined_stderr: list[str] = []

    for command in VALIDATION_COMMANDS:
        command_preview = " ".join(command)
        log_info(f"Running validation command: {command_preview}")
        result = subprocess.run(
            command,
            cwd=context.local_path,
            text=True,
            capture_output=True,
            timeout=1200,
        )
        if result.stdout:
            combined_stdout.append(f"$ {command_preview}\n{result.stdout}")
        if result.stderr:
            combined_stderr.append(f"$ {command_preview}\n{result.stderr}")
        if result.returncode != 0:
            return subprocess.CompletedProcess(
                args=command,
                returncode=result.returncode,
                stdout="\n".join(combined_stdout),
                stderr="\n".join(combined_stderr),
            )

    return subprocess.CompletedProcess(
        args=["validation"],
        returncode=0,
        stdout="\n".join(combined_stdout),
        stderr="\n".join(combined_stderr),
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

def build_single_retry_fix_task(test_output: str, *, retry_number: int) -> str:
    """Build a scoped retry task sent to the runner after a failed validation run."""
    return (
        "Your previous changes were applied, but required repository validation failed.\n\n"
        "Run and satisfy exactly this command contract:\n"
        f"- {VALIDATION_COMMAND_CONTRACT}\n\n"
        f"This is retry attempt {retry_number} of {MAX_VALIDATION_RETRIES}.\n\n"
        "Failure output:\n"
        "```text\n"
        f"{test_output}\n"
        "```\n\n"
        "Do not expand scope beyond fixing these validation failures.\n"
        f"Apply minimal code changes to make {VALIDATION_COMMAND_CONTRACT} pass, then finish."
    )

def ensure_playwright_test_prerequisites(local_path: Path) -> None:
    """Ensure the repository has local dependencies installed for Playwright test runs."""
    local_playwright = local_path / "node_modules" / ".bin" / "playwright"
    if local_playwright.exists():
        return

    log_info("Playwright CLI unavailable; running npm ci to install test dependencies")
    install_result = subprocess.run(
        ["npm", "ci"],
        cwd=local_path,
        text=True,
        capture_output=True,
        timeout=1200,
    )
    if install_result.returncode != 0:
        raise SystemExit(
            "Failed to install npm dependencies required for tests.\n"
            f"stdout:\n{install_result.stdout}\n"
            f"stderr:\n{install_result.stderr}"
        )

    if not local_playwright.exists():
        playwright_version_result = subprocess.run(
            ["npx", "playwright", "--version"],
            cwd=local_path,
            text=True,
            capture_output=True,
            timeout=120,
        )
        raise SystemExit(
            "Playwright CLI is still unavailable in node_modules after `npm ci`.\n"
            f"stdout:\n{playwright_version_result.stdout}\n"
            f"stderr:\n{playwright_version_result.stderr}"
        )
