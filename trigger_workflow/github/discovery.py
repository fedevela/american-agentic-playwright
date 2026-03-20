from __future__ import annotations

from typing import Any

from ..config import PHASE_LABELS
from ..gh_client import run_gh_json
from ..logging_utils import log_info
from .constants import (
    GH_CMD_ISSUE,
    GH_FLAG_JSON,
    GH_FLAG_REPO,
    GH_STATE_OPEN,
    KEY_COMMENTS,
    KEY_CREATED_AT,
    KEY_ID,
    KEY_LABELS,
    KEY_NAME,
    KEY_NUMBER,
    KEY_TITLE,
    KEY_BODY,
)

def fetch_issue_data(repo: str, issue_number: int) -> dict[str, Any]:
    """Fetch the issue payload used by prompt construction and label checks."""
    log_info(f"Fetching issue #{issue_number} with labels and comments")
    fields = f"{KEY_ID},{KEY_TITLE},{KEY_BODY},{KEY_NUMBER},{KEY_LABELS},{KEY_COMMENTS}"
    return run_gh_json(
        [GH_CMD_ISSUE, "view", str(issue_number), GH_FLAG_REPO, repo, GH_FLAG_JSON, fields],
        failure_message=f"Failed to fetch issue #{issue_number} from {repo}",
        expect_type=dict,
    )

def resolve_issue_by_label(repo: str, label: str) -> int:
    """Resolve a single open issue by label."""
    log_info(f"Looking up open issue for label '{label}'")
    fields = f"{KEY_NUMBER},{KEY_TITLE}"
    issues = run_gh_json(
        [GH_CMD_ISSUE, "list", GH_FLAG_REPO, repo, "--label", label, "--state", GH_STATE_OPEN, GH_FLAG_JSON, fields],
        failure_message=f"Could not query open issues labeled '{label}' in {repo}",
        expect_type=list,
    )
    if not issues:
        raise SystemExit(f"No open issues labeled '{label}' found in {repo}.")
    if len(issues) > 1:
        issue_refs = ", ".join(f"#{item[KEY_NUMBER]}" for item in issues if isinstance(item, dict) and KEY_NUMBER in item)
        raise SystemExit(
            f"Multiple open issues labeled '{label}' found in {repo}: {issue_refs}. "
            "Pass --issue to select one."
        )

    issue = issues[0]
    if not isinstance(issue, dict) or KEY_NUMBER not in issue:
        raise SystemExit(f"Invalid issue payload while resolving label '{label}' in {repo}.")
    return int(issue[KEY_NUMBER])

def issue_has_label(issue_data: dict[str, Any], label: str) -> bool:
    """Return True when the issue currently carries the requested label."""
    labels = issue_data.get(KEY_LABELS) or []
    return any(item.get(KEY_NAME) == label for item in labels if isinstance(item, dict))

def issue_phase_labels(issue_data: dict[str, Any]) -> list[str]:
    """Return known phase labels attached to an issue."""
    labels = issue_data.get(KEY_LABELS) or []
    return [
        item[KEY_NAME]
        for item in labels
        if isinstance(item, dict) and item.get(KEY_NAME) in PHASE_LABELS
    ]

def resolve_oldest_phased_issue(repo: str) -> tuple[int, str]:
    """Resolve the oldest open issue carrying exactly one known phase label."""
    log_info("Looking up the oldest open issue carrying a canonical phase label")
    fields = f"{KEY_NUMBER},{KEY_TITLE},{KEY_CREATED_AT},{KEY_LABELS}"
    issues = run_gh_json(
        [GH_CMD_ISSUE, "list", GH_FLAG_REPO, repo, "--state", GH_STATE_OPEN, GH_FLAG_JSON, fields],
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
    phased_issues.sort(key=lambda item: item.get(KEY_CREATED_AT, ""))
    selected = phased_issues[0]
    labels = issue_phase_labels(selected)
    if len(labels) != 1:
        issue_number = selected.get(KEY_NUMBER, "?")
        raise SystemExit(
            f"Issue #{issue_number} in {repo} has multiple phase labels: {', '.join(labels)}. "
            "Pass --label and --issue explicitly."
        )

    log_info(f"Selected oldest: issue #{selected[KEY_NUMBER]} with label '{labels[0]}'")
    return int(selected[KEY_NUMBER]), labels[0]