from __future__ import annotations

import json
import subprocess
from typing import Any

from .config import NEXT_LABEL_MAP, PHASE_LABELS, PHASE_LABEL_METADATA
from .logging_utils import log_error, log_info


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
    result = run_gh(
        ["issue", "view", str(issue_number), "--repo", repo, "--json", "id,title,body,number,labels,comments"],
        capture_output=True,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        details = stderr or stdout or "gh returned no output"
        raise SystemExit(f"Failed to fetch issue #{issue_number} from {repo}: {details}")
    if not result.stdout:
        raise SystemExit(f"Failed to fetch issue #{issue_number} from {repo}: gh returned empty output.")
    return json.loads(result.stdout)


def fetch_repo_labels(repo: str) -> list[dict[str, Any]]:
    """Fetch repository label metadata from GitHub."""
    log_info("Fetching repository label metadata")
    result = run_gh(
        ["label", "list", "--repo", repo, "--json", "name,description,color"],
        capture_output=True,
    )
    if result.returncode != 0 or not result.stdout:
        raise SystemExit(f"Could not query labels in {repo}.")

    labels = json.loads(result.stdout)
    if not isinstance(labels, list):
        raise SystemExit(f"Invalid label payload for {repo}.")
    return labels


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

    for label_name in PHASE_LABELS:
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

    log_info(f"Canonical labels ensured: {len(PHASE_LABELS)} total, {created} created, {updated} updated")


def resolve_issue_by_label(repo: str, label: str) -> int:
    """Resolve a single open issue by label."""
    log_info(f"Looking up open issue for label '{label}'")
    result = run_gh(
        ["issue", "list", "--repo", repo, "--label", label, "--state", "open", "--json", "number,title"],
        capture_output=True,
    )
    if result.returncode != 0 or not result.stdout:
        raise SystemExit(f"Could not query open issues labeled '{label}' in {repo}.")

    issues = json.loads(result.stdout)
    if not isinstance(issues, list) or not issues:
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
    result = run_gh(
        ["issue", "list", "--repo", repo, "--state", "open", "--json", "number,title,createdAt,labels"],
        capture_output=True,
    )
    if result.returncode != 0 or not result.stdout:
        raise SystemExit(f"Could not query open issues in {repo}.")

    issues = json.loads(result.stdout)
    if not isinstance(issues, list):
        raise SystemExit(f"Invalid issue list payload for {repo}.")

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


def advance_issue_label(repo: str, issue_number: int, current_label: str) -> None:
    """Advance the issue from its current phase label to the configured next label."""
    next_label = NEXT_LABEL_MAP.get(current_label)
    if not next_label:
        log_info("No next label defined (final phase)")
        return

    log_info(f"Removing label '{current_label}'")
    log_info(f"Adding label '{next_label}'")
    result = run_gh(
        [
            "issue",
            "edit",
            str(issue_number),
            "--repo",
            repo,
            "--remove-label",
            current_label,
            "--add-label",
            next_label,
        ]
    )
    if result.returncode != 0:
        raise SystemExit(
            f"Posted the phase comment to {repo}#{issue_number}, but failed to hand off label "
            f"from '{current_label}' to '{next_label}'."
        )
    log_info("Label handoff complete")


def parse_repo(repo: str) -> tuple[str, str]:
    """Split an owner/repo string into owner and repository name."""
    return repo.split("/", 1)


def create_issue_via_api(repo: str, title: str, body: str) -> dict[str, Any]:
    """Create an issue through the REST API and return its full metadata."""
    owner, repo_name = parse_repo(repo)
    result = run_gh(
        [
            "api",
            f"repos/{owner}/{repo_name}/issues",
            "--method",
            "POST",
            "-f",
            f"title={title}",
            "-f",
            f"body={body}",
        ],
        capture_output=True,
    )
    if result.returncode != 0 or not result.stdout:
        raise SystemExit(f"Failed to create child issue '{title}'.")
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict):
        raise SystemExit(f"Invalid payload returned while creating child issue '{title}'.")
    return payload


def add_sub_issue_relationship(repo: str, parent_issue_number: int, sub_issue_id: int) -> None:
    """Attach a child issue to its parent using GitHub's sub-issue relationship."""
    owner, repo_name = parse_repo(repo)
    result = run_gh(
        [
            "api",
            f"repos/{owner}/{repo_name}/issues/{parent_issue_number}/sub_issues",
            "--method",
            "POST",
            "-f",
            f"sub_issue_id={sub_issue_id}",
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        raise SystemExit(f"Failed to attach sub-issue id {sub_issue_id} to parent issue #{parent_issue_number}.")
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
            "-f",
            f"issue_id={blocking_issue_id}",
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        raise SystemExit(f"Failed to mark issue #{issue_number} as blocked by issue id {blocking_issue_id}.")
    log_info(f"  → Added blocked-by dependency to issue #{issue_number}")


def create_child_issues(
    repo: str,
    parent_issue: int,
    sub_issues: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Create ordered child issues, attach them to the parent, and wire predecessor dependencies."""
    log_info(f"Creating {len(sub_issues)} child issues in implementation order...")
    created: list[dict[str, Any]] = []

    for i, item in enumerate(sub_issues, 1):
        log_info(f"Creating ordered child issue #{i}: {item['title'][:50]}")
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

        payload = create_issue_via_api(repo, item["title"].strip(), body)
        issue_number = int(payload["number"])
        issue_id = int(payload["id"])
        url = str(payload["html_url"]).strip()
        log_info(f"  → Created issue #{issue_number}: {url}")
        created.append({"title": item["title"].strip(), "url": url, "number": issue_number, "id": issue_id})

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

    log_info(f"All {len(created)} child issues created, attached, and dependency-linked successfully")
    return created

