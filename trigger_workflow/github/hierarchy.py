from __future__ import annotations

import time
from typing import Any

from ..config import TIFERET_AUTO_ISSUE_PREFIX
from ..gh_client import gh_failure_details, run_gh, run_gh_json, parse_repo
from ..logging_utils import log_info

SUB_ISSUE_VERIFICATION_ATTEMPTS = 5
SUB_ISSUE_VERIFICATION_DELAY_SECONDS = 2.0

def create_issue_via_api(repo: str, title: str, body: str, *, labels: list[str] | None = None) -> dict[str, Any]:
    """Create an issue through the REST API and return its full metadata."""
    owner, repo_name = parse_repo(repo)
    args = [
        "api",
        f"repos/{owner}/{repo_name}/issues",
        "--method",
        "POST",
        "-f",
        f"title={title}",
        "-f",
        f"body={body}",
    ]
    for label in labels or []:
        args.extend(["-f", f"labels[]={label}"])
    return run_gh_json(
        args,
        failure_message=f"Failed to create child issue '{title}'",
        expect_type=dict,
    )

def normalize_tiferet_child_title(title: str) -> str:
    """Ensure Tiferet-created child issues are visibly distinct from human-authored issues."""
    normalized = title.strip()
    if not normalized.startswith(TIFERET_AUTO_ISSUE_PREFIX):
        normalized = f"{TIFERET_AUTO_ISSUE_PREFIX}{normalized}"
    return normalized

def add_sub_issue_relationship(repo: str, parent_issue_number: int, sub_issue_id: int) -> None:
    """Attach a child issue to its parent using GitHub's sub-issue relationship."""
    owner, repo_name = parse_repo(repo)
    result = run_gh(
        [
            "api",
            f"repos/{owner}/{repo_name}/issues/{parent_issue_number}/sub_issues",
            "--method",
            "POST",
            "-F",
            f"sub_issue_id={sub_issue_id}",
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        raise SystemExit(
            f"Failed to attach sub-issue id {sub_issue_id} to parent issue #{parent_issue_number}: "
            f"{gh_failure_details(result)}"
        )
    log_info(f"  → Attached as sub-issue under parent #{parent_issue_number}")

def add_blocked_by_dependency(repo: str, issue_number: int, blocking_issue_id: int) -> None:
    """Mark an issue as blocked by another issue using GitHub's issue dependency API."""
    owner, repo_name = parse_repo(repo)
    result = run_gh(
        [
            "api",
            f"repos/{owner}/{repo_name}/issues/{issue_number}/dependencies/blocked_by",
            "--method",
            "POST",
            "-F",
            f"issue_id={blocking_issue_id}",
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        raise SystemExit(
            f"Failed to mark issue #{issue_number} as blocked by issue id {blocking_issue_id}: "
            f"{gh_failure_details(result)}"
        )
    log_info(f"  → Added blocked-by dependency to issue #{issue_number}")

def fetch_parent_sub_issue_ids(repo: str, parent_issue_number: int) -> set[int]:
    """Return the child issue ids currently attached to a parent issue."""
    owner, repo_name = parse_repo(repo)
    payload = run_gh_json(
        [
            "api",
            f"repos/{owner}/{repo_name}/issues/{parent_issue_number}/sub_issues",
        ],
        failure_message=f"Failed to fetch sub-issues for parent issue #{parent_issue_number}",
        expect_type=list,
    )

    attached_ids: set[int] = set()
    for item in payload:
        if isinstance(item, dict) and isinstance(item.get("id"), int):
            attached_ids.add(int(item["id"]))
    return attached_ids

def verify_parent_sub_issue_ids(
    repo: str,
    parent_issue_number: int,
    expected_child_ids: list[int],
    *,
    attempts: int = SUB_ISSUE_VERIFICATION_ATTEMPTS,
    delay_seconds: float = SUB_ISSUE_VERIFICATION_DELAY_SECONDS,
) -> list[int]:
    """Retry parent-child attachment verification to tolerate API consistency lag."""
    if attempts < 1:
        raise SystemExit("Sub-issue verification attempts must be at least 1.")
    if delay_seconds < 0:
        raise SystemExit("Sub-issue verification delay must be non-negative.")

    missing_ids = expected_child_ids[:]
    for attempt in range(1, attempts + 1):
        attached_ids = fetch_parent_sub_issue_ids(repo, parent_issue_number)
        missing_ids = [issue_id for issue_id in expected_child_ids if issue_id not in attached_ids]
        if not missing_ids:
            return []
        if attempt < attempts:
            log_info(
                f"Parent #{parent_issue_number} is still missing {len(missing_ids)} sub-issue link(s) "
                f"after verification attempt {attempt}/{attempts}; retrying in {delay_seconds:.1f}s"
            )
            time.sleep(delay_seconds)
    return missing_ids

def create_child_issues(
    repo: str,
    parent_issue: int,
    sub_issues: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Create ordered child issues, attach them to the parent, and wire predecessor dependencies."""
    log_info(f"Creating {len(sub_issues)} child issues in implementation order...")
    created: list[dict[str, Any]] = []

    for i, item in enumerate(sub_issues, 1):
        original_title = item["title"].strip()
        normalized_title = normalize_tiferet_child_title(original_title)
        if normalized_title != original_title:
            log_info(
                f"Creating ordered child issue #{i}: normalized title to '{normalized_title[:70]}'"
            )
        else:
            log_info(f"Creating ordered child issue #{i}: {normalized_title[:70]}")
        body = item["body"].strip()
        auto_created_marker = f"Automatically created by Phase 4/Tiferet from parent issue #{parent_issue}."
        parent_marker = f"Parent issue: #{parent_issue}"
        prefix_lines: list[str] = []
        if auto_created_marker not in body:
            prefix_lines.append(auto_created_marker)
        if parent_marker not in body:
            prefix_lines.append(parent_marker)
        if prefix_lines:
            body = "\n".join(prefix_lines) + f"\n\n{body}"

        payload = create_issue_via_api(repo, normalized_title, body, labels=["phase:netzach"])
        issue_number = int(payload["number"])
        issue_id = int(payload["id"])
        url = str(payload["html_url"]).strip()
        log_info(f"  → Created issue #{issue_number}: {url}")
        created.append({"title": normalized_title, "url": url, "number": issue_number, "id": issue_id})

    for i, item in enumerate(created, 1):
        issue_number = int(item["number"])
        issue_id = int(item["id"])
        log_info(f"Linking child issue #{issue_number} to parent #{parent_issue} as a sub-issue")
        add_sub_issue_relationship(repo, parent_issue, issue_id)

        if i > 1:
            previous_issue = created[i - 2]
            previous_number = int(previous_issue["number"])
            previous_id = int(previous_issue["id"])
            log_info(f"Linking child issue #{issue_number} as blocked by preceding issue #{previous_number}")
            add_blocked_by_dependency(repo, issue_number, previous_id)

    log_info(f"Verifying that all {len(created)} child issues are attached to parent #{parent_issue}")
    missing_ids = verify_parent_sub_issue_ids(
        repo,
        parent_issue,
        [int(item["id"]) for item in created],
    )
    if missing_ids:
        missing_numbers = [f"#{item['number']}" for item in created if int(item["id"]) in missing_ids]
        raise SystemExit(
            f"Created child issues were not all attached to parent #{parent_issue}. Missing sub-issue links: {', '.join(missing_numbers)}."
        )
    log_info(f"Verified parent #{parent_issue} has all {len(created)} child issues attached")

    log_info(f"All {len(created)} child issues created, attached, and dependency-linked successfully")
    return created