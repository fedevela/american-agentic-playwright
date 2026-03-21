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
    git_run_strict,
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
) -> tuple[str, str]:
    """Commit and push phase changes, then return a summary suitable for a GitHub issue comment, plus the git diff."""
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
    git_run_strict(
        local_path, 
        ["rev-parse", "--verify", origin_base], 
        failure_message=f"Missing required base branch '{pr_base}' for delivery of issue #{issue}",
        capture_output=True
    )

    merge_result = git_run(local_path, ["merge", origin_base], capture_output=True)
    if merge_result.returncode != 0:
        if "CONFLICT" in (merge_result.stdout or "") or "CONFLICT" in (merge_result.stderr or ""):
             log_error("Merge conflicts detected during delivery auto-merge.")
        raise SystemExit(f"Failed to auto-merge '{pr_base}' into '{branch}' before delivery. Check for conflicts.")

    status_result = git_run_strict(
        local_path, 
        ["status", "--short"], 
        failure_message=f"Failed to inspect git status before delivery finalization in {local_path}",
        capture_output=True
    )
    status_lines = [line.rstrip() for line in (status_result.stdout or "").splitlines() if line.strip()]
    if not status_lines:
        raise SystemExit(
            f"Phase {phase.upper()} finished without repository changes. "
            "Refusing to advance phase without a commit."
        )

    git_run_strict(
        local_path, 
        ["add", "-A"], 
        failure_message=f"Failed to stage changes for phase {phase.upper()} delivery in {local_path}",
        capture_output=True
    )

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
    git_run_strict(
        local_path, 
        ["commit", "-m", commit_message], 
        failure_message=f"Failed to commit changes for phase {phase.upper()} delivery in {local_path}",
        capture_output=True
    )

    push_result = git_run_strict(
        local_path, 
        ["push", "origin", branch], 
        failure_message=f"Failed to push branch '{branch}' for phase {phase.upper()} delivery. Human intervention required",
        capture_output=True
    )
    if (push_result.stdout or "").strip():
        log_info(f"Push output: {(push_result.stdout or '').strip()}")
    if (push_result.stderr or "").strip():
        log_info(f"Push diagnostics: {(push_result.stderr or '').strip()}")

    head_sha_result = git_run_strict(
        local_path, 
        ["rev-parse", "HEAD"], 
        failure_message=f"Failed to resolve HEAD sha after push for branch '{branch}'",
        capture_output=True
    )
    head_sha = (head_sha_result.stdout or "").strip()

    remote_sha_result = git_run_strict(
        local_path, 
        ["ls-remote", "--heads", "origin", f"refs/heads/{branch}"], 
        failure_message=f"Failed to verify remote head for branch '{branch}' after push",
        capture_output=True
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

    sha_result = git_run_strict(
        local_path, 
        ["rev-parse", "--short", "HEAD"], 
        failure_message=f"Failed to resolve HEAD sha after delivery push for branch '{branch}'",
        capture_output=True
    )
    short_sha = (sha_result.stdout or "").strip()

    changed_files_result = git_run_strict(
        local_path, 
        ["show", "--name-only", "--pretty=format:", "HEAD"], 
        failure_message="Failed to read committed file list for delivery summary",
        capture_output=True
    )
    changed_files = [line.strip() for line in changed_files_result.stdout.splitlines() if line.strip()]

    files_block = "\n".join(f"- `{path}`" for path in changed_files) if changed_files else "- `(no file list available)`"
    file_count = len(changed_files)
    
    summary_str = (
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

    diff_result = git_run_strict(
        local_path,
        ["show", "--format=", "HEAD"],
        failure_message="Failed to extract commit diff for delivery summary",
        capture_output=True
    )
    commit_diff = (diff_result.stdout or "").strip()

    return summary_str, commit_diff
