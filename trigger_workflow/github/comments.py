from __future__ import annotations

from ..gh_client import run_gh_strict
from ..logging_utils import log_info
from .constants import GH_CMD_ISSUE, GH_FLAG_REPO

def post_issue_comment(repo: str, issue_number: int, body: str) -> None:
    """Post a GitHub comment to the target issue."""
    log_info(f"Posting issue comment to #{issue_number}")
    run_gh_strict(
        [GH_CMD_ISSUE, "comment", str(issue_number), GH_FLAG_REPO, repo, "--body", body],
        failure_message=f"Failed to post comment to {repo}#{issue_number}"
    )