from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import re

from .config import (
    IMPLEMENTATION_PHASES,
    PRE_IMPLEMENTATION_PHASES,
    TargetRepoConfig,
)
from .logging_utils import log_error, log_info


@dataclass(frozen=True)
class RunnerTargetContext:
    """Describe the verified local checkout and branch a runner should use for a phase run."""
    local_path: Path
    branch: str


def resolve_target_repo_config(repo: str) -> TargetRepoConfig:
    """Return a TargetRepoConfig for the current working directory."""
    return TargetRepoConfig(
        local_path=Path.cwd(),
        main_branch="main",
        issue_branch_prefix="issue/",
    )


def resolve_phase_execution_branch(repo: str, phase: str, issue: int) -> str:
    """Return the branch that should back this phase run."""
    config = resolve_target_repo_config(repo)
    return f"{config.issue_branch_prefix}{issue}"


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
    """Switch to the requested branch, creating it from base_branch if it does not exist."""
    active_branch = current_branch(local_path)
    if active_branch == branch:
        log_info(f"Git branch already active: {branch}")
        return

    if branch_exists(local_path, branch):
        log_info(f"Switching target repository to existing branch '{branch}'")
        result = git_run(local_path, ["switch", branch], capture_output=True)
        if result.returncode != 0:
            log_error(f"Failed to switch {local_path} to branch '{branch}': {result.stderr or result.stdout or 'no output'}")
            raise SystemExit(f"Failed to switch {local_path} to branch '{branch}'.")
        return

    if branch == base_branch:
        raise SystemExit(f"Base branch '{base_branch}' does not exist locally in {local_path}.")

    log_info(f"Branch '{branch}' does not exist; creating it from '{base_branch}'.")
    
    # Try creating from local base_branch first
    result = git_run(local_path, ["switch", "-c", branch, base_branch], capture_output=True)
    if result.returncode != 0:
        # Fallback to origin/base_branch if local doesn't exist
        log_info(f"Failed to create from local '{base_branch}', trying 'origin/{base_branch}'...")
        git_run(local_path, ["fetch", "origin", base_branch])
        result = git_run(local_path, ["switch", "-c", branch, f"origin/{base_branch}"], capture_output=True)
        if result.returncode != 0:
            log_error(f"Failed to create branch '{branch}' from 'origin/{base_branch}': {result.stderr or result.stdout or 'no output'}")
            raise SystemExit(f"Failed to create branch '{branch}' from '{base_branch}'.")
    
    log_info(f"Pushing new branch '{branch}' to origin...")
    git_run(local_path, ["push", "-u", "origin", branch])


def prepare_target_repo_checkout(repo: str) -> tuple[TargetRepoConfig, Path]:
    """Resolve the current directory as the target repository."""
    config = resolve_target_repo_config(repo)
    local_path = config.local_path
    if not (local_path / ".git").exists():
        raise SystemExit(f"Current directory is not a git checkout: {local_path}")
    log_info(f"Using current directory as target repository: {local_path}")
    return config, local_path


def extract_parent_issue(issue_body: str) -> int | None:
    """Parse the parent issue number from an issue body if it contains the parent-marker."""
    match = re.search(r"Parent issue: #(\d+)", issue_body)
    if match:
        return int(match.group(1))
    return None


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
            raise SystemExit(f"Missing required base branch '{base_branch}' for issue.")

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


def create_issue_branches_for_child_issues(repo: str, parent_issue: int, issue_numbers: list[int]) -> None:
    """Create missing issue branches for Tiferet-created child issues, branching from the parent issue branch."""
    config = resolve_target_repo_config(repo)
    _, local_path = prepare_target_repo_checkout(repo)
    
    # The parent issue branch name (e.g. issue/51)
    parent_branch = f"{config.issue_branch_prefix}{parent_issue}"
    
    # Ensure the parent branch exists, creating it from main if necessary
    ensure_git_branch(local_path, parent_branch, base_branch=config.main_branch)

    for issue_number in issue_numbers:
        branch_name = f"{config.issue_branch_prefix}{issue_number}"
        # This will create the child branch from the parent branch if it doesn't exist
        ensure_git_branch(local_path, branch_name, base_branch=parent_branch)
        # Switch back to parent branch to continue the loop smoothly, though ensure_git_branch switches to the target.
        # Actually it's fine, we can just switch back at the end or just let it be since this is Tiferet.
        
    # Return to the parent branch to finish Tiferet phase
    ensure_git_branch(local_path, parent_branch, base_branch=config.main_branch)
