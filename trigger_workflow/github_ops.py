from __future__ import annotations

import json
import subprocess
import time
from typing import Any

from .config import NEEDS_HUMAN_LABEL, NEXT_LABEL_MAP, PHASE_LABELS, PHASE_LABEL_METADATA, TIFERET_AUTO_ISSUE_PREFIX
from .logging_utils import log_error, log_info


SUB_ISSUE_VERIFICATION_ATTEMPTS = 5
SUB_ISSUE_VERIFICATION_DELAY_SECONDS = 2.0


def gh_failure_details(result: subprocess.CompletedProcess[str]) -> str:
    """Build a single error detail string from GitHub CLI output."""
    return (result.stderr or result.stdout or "").strip() or "gh returned no output"


def run_gh_json(
    args: list[str],
    *,
    failure_message: str,
    expect_type: type[list[Any]] | type[dict[str, Any]],
) -> list[Any] | dict[str, Any]:
    """Run a GitHub CLI command and parse the JSON response."""
    result = run_gh(args, capture_output=True)
    if result.returncode != 0 or not result.stdout:
        raise SystemExit(f"{failure_message}: {gh_failure_details(result)}")

    payload = json.loads(result.stdout)
    if not isinstance(payload, expect_type):
        expected_name = "array" if expect_type is list else "object"
        raise SystemExit(f"{failure_message}: expected JSON {expected_name} response.")
    return payload


def run_gh(args: list[str], *, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    """Run a GitHub CLI command with a short preview log."""
    preview = " ".join(args[:5])
    log_info(f"GitHub CLI: gh {preview}{' ...' if len(args) > 5 else ''}")
    return subprocess.run(
        ["gh", *args],
        text=True,
        capture_output=capture_output,
        timeout=120,
    )


def fetch_issue_data(repo: str, issue_number: int) -> dict[str, Any]:
    """Fetch the issue payload used by prompt construction and label checks."""
    log_info(f"Fetching issue #{issue_number} with labels and comments")
    return run_gh_json(
        ["issue", "view", str(issue_number), "--repo", repo, "--json", "id,title,body,number,labels,comments"],
        failure_message=f"Failed to fetch issue #{issue_number} from {repo}",
        expect_type=dict,
    )


def fetch_repo_labels(repo: str) -> list[dict[str, Any]]:
    """Fetch repository label metadata from GitHub."""
    log_info("Fetching repository label metadata")
    payload = run_gh_json(
        ["label", "list", "--repo", repo, "--json", "name,description,color"],
        failure_message=f"Could not query labels in {repo}",
        expect_type=list,
    )
    return [item for item in payload if isinstance(item, dict)]


def ensure_phase_labels(repo: str) -> None:
    """Create or repair the canonical phase labels required by the workflow."""
    existing_labels = fetch_repo_labels(repo)
    existing_by_name = {
        item["name"]: item
        for item in existing_labels
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    created = 0
    updated = 0

    canonical_labels = tuple(PHASE_LABEL_METADATA.keys())
    for label_name in canonical_labels:
        expected = PHASE_LABEL_METADATA[label_name]
        current = existing_by_name.get(label_name)

        if current is None:
            log_info(f"Creating missing canonical label '{label_name}'")
            result = run_gh(
                [
                    "label",
                    "create",
                    label_name,
                    "--repo",
                    repo,
                    "--description",
                    expected["description"],
                    "--color",
                    expected["color"],
                ]
            )
            if result.returncode != 0:
                raise SystemExit(f"Failed to create label '{label_name}' in {repo}.")
            created += 1
            continue

        current_description = (current.get("description") or "").strip()
        current_color = (current.get("color") or "").strip().lstrip("#").upper()
        expected_description = expected["description"]
        expected_color = expected["color"].upper()
        if current_description == expected_description and current_color == expected_color:
            continue

        log_info(f"Repairing canonical label metadata for '{label_name}'")
        result = run_gh(
            [
                "label",
                "edit",
                label_name,
                "--repo",
                repo,
                "--description",
                expected_description,
                "--color",
                expected_color,
            ]
        )
        if result.returncode != 0:
            raise SystemExit(f"Failed to update label '{label_name}' in {repo}.")
        updated += 1

    log_info(f"Canonical labels ensured: {len(canonical_labels)} total, {created} created, {updated} updated")


def resolve_issue_by_label(repo: str, label: str) -> int:
    """Resolve a single open issue by label."""
    log_info(f"Looking up open issue for label '{label}'")
    issues = run_gh_json(
        ["issue", "list", "--repo", repo, "--label", label, "--state", "open", "--json", "number,title"],
        failure_message=f"Could not query open issues labeled '{label}' in {repo}",
        expect_type=list,
    )
    if not issues:
        raise SystemExit(f"No open issues labeled '{label}' found in {repo}.")
    if len(issues) > 1:
        issue_refs = ", ".join(f"#{item['number']}" for item in issues if isinstance(item, dict) and "number" in item)
        raise SystemExit(
            f"Multiple open issues labeled '{label}' found in {repo}: {issue_refs}. "
            "Pass --issue to select one."
        )

    issue = issues[0]
    if not isinstance(issue, dict) or "number" not in issue:
        raise SystemExit(f"Invalid issue payload while resolving label '{label}' in {repo}.")
    return int(issue["number"])


def issue_has_label(issue_data: dict[str, Any], label: str) -> bool:
    """Return True when the issue currently carries the requested label."""
    labels = issue_data.get("labels") or []
    return any(item.get("name") == label for item in labels if isinstance(item, dict))


def issue_phase_labels(issue_data: dict[str, Any]) -> list[str]:
    """Return known phase labels attached to an issue."""
    labels = issue_data.get("labels") or []
    return [
        item["name"]
        for item in labels
        if isinstance(item, dict) and item.get("name") in PHASE_LABELS
    ]


def resolve_oldest_phased_issue(repo: str) -> tuple[int, str]:
    """Resolve the oldest open issue carrying exactly one known phase label."""
    log_info("Looking up the oldest open issue carrying a canonical phase label")
    issues = run_gh_json(
        ["issue", "list", "--repo", repo, "--state", "open", "--json", "number,title,createdAt,labels"],
        failure_message=f"Could not query open issues in {repo}",
        expect_type=list,
    )

    phased_issues: list[dict[str, Any]] = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        labels = issue_phase_labels(issue)
        if labels:
            phased_issues.append(issue)

    if not phased_issues:
        raise SystemExit(f"No open issues with a phase label found in {repo}.")

    log_info(f"Found {len(phased_issues)} phased issues; sorting by creation date")
    phased_issues.sort(key=lambda item: item.get("createdAt", ""))
    selected = phased_issues[0]
    labels = issue_phase_labels(selected)
    if len(labels) != 1:
        issue_number = selected.get("number", "?")
        raise SystemExit(
            f"Issue #{issue_number} in {repo} has multiple phase labels: {', '.join(labels)}. "
            "Pass --label and --issue explicitly."
        )

    log_info(f"Selected oldest: issue #{selected['number']} with label '{labels[0]}'")
    return int(selected["number"]), labels[0]


def post_issue_comment(repo: str, issue_number: int, body: str) -> None:
    """Post a GitHub comment to the target issue."""
    log_info(f"Posting issue comment to #{issue_number}")
    result = run_gh(["issue", "comment", str(issue_number), "--repo", repo, "--body", body])
    if result.returncode != 0:
        log_error(f"Failed to post comment to {repo}#{issue_number}")
        raise SystemExit(f"Failed to post comment to {repo}#{issue_number}.")


def edit_issue_labels(
    repo: str,
    issue_number: int,
    *,
    add: list[str] | None = None,
    remove: list[str] | None = None,
) -> None:
    """Apply add/remove label edits to an issue in one GitHub API call."""
    add_labels = [item for item in (add or []) if item]
    remove_labels = [item for item in (remove or []) if item]
    if not add_labels and not remove_labels:
        return

    args = [
        "issue",
        "edit",
        str(issue_number),
        "--repo",
        repo,
    ]
    for label in remove_labels:
        args.extend(["--remove-label", label])
    for label in add_labels:
        args.extend(["--add-label", label])

    additions = ", ".join(f"'{label}'" for label in add_labels) or "(none)"
    removals = ", ".join(f"'{label}'" for label in remove_labels) or "(none)"
    log_info(f"Editing labels on issue #{issue_number}: add {additions}; remove {removals}")
    result = run_gh(args)
    if result.returncode != 0:
        raise SystemExit(
            f"Failed to edit labels on {repo}#{issue_number} (add: {additions}; remove: {removals})."
        )


def advance_issue_label(repo: str, issue_number: int, current_label: str) -> None:
    """Advance the issue from its current phase label to the configured next label."""
    next_label = NEXT_LABEL_MAP.get(current_label)
    if not next_label:
        log_info("No next label defined (final phase)")
        return

    log_info(f"Advancing label: '{current_label}' -> '{next_label}'")
    edit_issue_labels(repo, issue_number, add=[next_label], remove=[current_label])
    log_info("Label handoff complete")


def remove_issue_label(repo: str, issue_number: int, label: str) -> None:
    """Remove a specific label from an issue."""
    log_info(f"Removing label '{label}' from issue #{issue_number}")
    edit_issue_labels(repo, issue_number, remove=[label])
    log_info("Label removed")


def tag_issue_needs_human(repo: str, issue_number: int) -> None:
    """Tag an issue for explicit human intervention."""
    log_info(f"Tagging issue #{issue_number} with '{NEEDS_HUMAN_LABEL}'")
    edit_issue_labels(repo, issue_number, add=[NEEDS_HUMAN_LABEL])
    log_info("Human intervention label applied")


def parse_repo(repo: str) -> tuple[str, str]:
    """Split an owner/repo string into owner and repository name."""
    if repo.count("/") != 1:
        raise SystemExit(f"Invalid repository identifier '{repo}'. Expected 'owner/repo'.")
    owner, repo_name = repo.split("/", 1)
    if not owner or not repo_name:
        raise SystemExit(f"Invalid repository identifier '{repo}'. Expected 'owner/repo'.")
    return owner, repo_name


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
