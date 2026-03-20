from __future__ import annotations

from ..gh_client import run_gh
from ..logging_utils import log_error, log_info

def post_issue_comment(repo: str, issue_number: int, body: str) -> None:
    """Post a GitHub comment to the target issue."""
    log_info(f"Posting issue comment to #{issue_number}")
    result = run_gh(["issue", "comment", str(issue_number), "--repo", repo, "--body", body])
    if result.returncode != 0:
        log_error(f"Failed to post comment to {repo}#{issue_number}")
        raise SystemExit(f"Failed to post comment to {repo}#{issue_number}.")