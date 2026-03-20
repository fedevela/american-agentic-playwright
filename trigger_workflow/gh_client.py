from __future__ import annotations

import json
import subprocess
from typing import Any

from .logging_utils import log_info

def gh_failure_details(result: subprocess.CompletedProcess[str]) -> str:
    """Build a single error detail string from GitHub CLI output."""
    return (result.stderr or result.stdout or "").strip() or "gh returned no output"


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


def parse_repo(repo: str) -> tuple[str, str]:
    """Split an owner/repo string into owner and repository name."""
    if repo.count("/") != 1:
        raise SystemExit(f"Invalid repository identifier '{repo}'. Expected 'owner/repo'.")
    owner, repo_name = repo.split("/", 1)
    if not owner or not repo_name:
        raise SystemExit(f"Invalid repository identifier '{repo}'. Expected 'owner/repo'.")
    return owner, repo_name
