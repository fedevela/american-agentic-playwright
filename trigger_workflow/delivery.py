from __future__ import annotations

import json
import subprocess
from typing import Any

from .config import (
    PHASE_DISPLAY_NAME_MAP,
    TIFERET_AUTO_ISSUE_PREFIX,
)
from .git_client import (
    extract_parent_issue,
    git_run,
    prepare_branch_context,
    prepare_phase_execution_context,
    resolve_target_repo_config,
)
from .logging_utils import log_error, log_info


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
        prepare_phase_execution_context(repo, phase, issue, issue_data=issue_data)
        if branch_override is None
        else prepare_branch_context(repo, branch=branch_override, branch_log_label="Resolved explicit target branch", issue_data=issue_data)
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
