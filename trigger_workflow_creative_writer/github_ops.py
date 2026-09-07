from __future__ import annotations

import json
import re
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
    issue = run_gh_json(
        ["issue", "view", str(issue_number), "--repo", repo, "--json", "id,title,body,number,labels"],
        failure_message=f"Failed to fetch issue #{issue_number} from {repo}",
        expect_type=dict,
    )
    # Recursive histories may exceed the GraphQL connection included by `gh
    # issue view`. REST pagination preserves every cycle and subsequent reply.
    comments = fetch_paginated_items(repo, f"issues/{issue_number}/comments")
    issue["comments"] = [
        {**comment, "author": comment.get("user"),
         "createdAt": comment.get("created_at"), "updatedAt": comment.get("updated_at"),
         "url": comment.get("html_url")}
        for comment in comments
    ]
    return issue



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


def clear_issue_labels_except(
    repo: str,
    issue_number: int,
    current_labels: list[str],
    *,
    keep: list[str],
) -> None:
    """Remove all labels from an issue except those explicitly listed in 'keep'."""
    to_remove = [label for label in current_labels if label not in keep]
    if not to_remove:
        log_info(f"No labels to remove from issue #{issue_number} (preserving: {', '.join(keep)})")
        return

    log_info(f"Clearing labels from issue #{issue_number} (preserving: {', '.join(keep)})")
    edit_issue_labels(repo, issue_number, remove=to_remove)
    log_info("Labels cleared")


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
    payload = fetch_paginated_items(repo, f"issues/{parent_issue_number}/sub_issues")

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


def fetch_paginated_items(repo: str, endpoint: str) -> list[dict[str, Any]]:
    """Read every REST page; incomplete or malformed discovery must stop delivery."""
    parse_repo(repo)
    pages = run_gh_json(
        ["api", f"repos/{repo}/{endpoint}", "--paginate", "--slurp"],
        failure_message=f"Failed to reconcile {endpoint}",
        expect_type=list,
    )
    if any(not isinstance(page, list) for page in pages):
        raise SystemExit(f"Invalid paginated response for {endpoint}.")
    items = [item for page in pages for item in page]
    if any(not isinstance(item, dict) for item in items):
        raise SystemExit(f"Invalid record in {endpoint}.")
    return items


def create_child_issues(
    repo: str,
    parent_issue: int,
    sub_issues: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Deliver validated assignments and reconcile interrupted creates and links.

    The caller validates dramatic coverage and renders assignment bodies. This
    boundary requires explicit scope, readiness and a stable cycle/element key;
    narrative words never determine routing. Seasons are human-created only.
    """
    prepared = []
    keys: set[str] = set()
    for item in sub_issues:
        scope, readiness, key = (item.get(field) for field in ("scope", "readiness", "delivery_key"))
        if scope not in {"episode", "act", "scene"} or readiness not in {"ready", "develop"}:
            raise SystemExit("Child assignments require structured scope and readiness; re-establish legacy work through Keter.")
        if readiness == "ready" and scope != "scene":
            raise SystemExit("Only scene assignments can be ready for Netzach.")
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]+", key) or key in keys:
            raise SystemExit("Child assignments require unique stable delivery keys.")
        keys.add(key)
        if any(not isinstance(item.get(field), str) or not item[field].strip() for field in ("title", "body")):
            raise SystemExit("Child assignment title and body must be nonempty.")
        marker = f"<!-- creative-child:{key} -->"
        title = normalize_tiferet_child_title(item["title"])
        body = (
            f"Automatically created by Phase 4/Tiferet from parent issue #{parent_issue}.\n"
            f"Parent issue: #{parent_issue}\n{marker}\n\n{item['body'].strip()}"
        )
        labels = ["phase:netzach" if readiness == "ready" else "phase:keter", f"size:{scope}"]
        prepared.append((title, body, marker, key, labels))

    if not prepared:
        return []
    existing = fetch_paginated_items(repo, "issues?state=all&per_page=100")
    comments = fetch_issue_data(repo, parent_issue).get("comments")
    if not isinstance(comments, list) or any(not isinstance(comment, dict) for comment in comments):
        raise SystemExit("Cannot reconcile child delivery records: invalid parent comments.")
    records: dict[str, dict[str, Any]] = {}
    delivered_keys: set[str] = set()
    for comment in comments:
        comment_body = str(comment.get("body") or "")
        delivered_keys.update(re.findall(r"<!-- creative-child-delivered:([A-Za-z0-9_.:-]+) -->", comment_body))
        for encoded in re.findall(r"<!-- creative-child-record:(.*?) -->", comment_body):
            try:
                record = json.loads(encoded)
            except ValueError as exc:
                raise SystemExit("Malformed child delivery record; reconciliation required.") from exc
            if (not isinstance(record, dict) or record.get("parent") != parent_issue
                    or not isinstance(record.get("key"), str)
                    or not re.fullmatch(r"[A-Za-z0-9_.:-]+", record["key"])
                    or type(record.get("id")) is not int or type(record.get("number")) is not int):
                raise SystemExit("Invalid child delivery record; reconciliation required.")
            key = record["key"]
            if key in records and records[key] != record:
                raise SystemExit("Conflicting child delivery records; reconciliation required.")
            records[key] = record
    if delivered_keys != set(records):
        raise SystemExit("Incomplete child delivery records; reconciliation required.")
    for key, record in records.items():
        matches = [item for item in existing if "pull_request" not in item
                   and f"<!-- creative-child:{key} -->" in str(item.get("body") or "")]
        if (len(matches) != 1 or matches[0].get("id") != record["id"]
                or matches[0].get("number") != record["number"]):
            raise SystemExit(f"Recorded child {key} is missing or changed; reconciliation required.")
    attached = fetch_parent_sub_issue_ids(repo, parent_issue)
    # Check every existing assignment before any mutation, including later items.
    matched = []
    for title, body, marker, key, labels in prepared:
        matches = [item for item in existing if marker in str(item.get("body") or "") and "pull_request" not in item]
        if len(matches) > 1:
            raise SystemExit(f"Duplicate child delivery marker {key}; human reconciliation required.")
        payload = matches[0] if matches else None
        if payload is not None and (payload.get("title") != title or payload.get("body") != body):
            raise SystemExit(f"Conflicting child delivery {key}; human reconciliation required.")
        matched.append(payload)

    created = []
    for (title, body, marker, key, labels), payload in zip(prepared, matched):
        if payload is None:
            payload = create_issue_via_api(repo, title, body, labels=labels)
        try:
            number, issue_id, url = int(payload["number"]), int(payload["id"]), str(payload["html_url"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SystemExit(f"Invalid child metadata for {key}; reconcile before retrying.") from exc
        record = {"title": title, "url": url, "number": number, "id": issue_id}
        record_marker = f"<!-- creative-child-delivered:{key} -->"
        if not any(record_marker in str(comment.get("body") or "") for comment in comments):
            ownership = json.dumps({"parent": parent_issue, "number": number, "id": issue_id, "key": key}, separators=(",", ":"))
            post_issue_comment(repo, parent_issue, f"{record_marker}\n<!-- creative-child-record:{ownership} -->\nCreated child #{number}: {title} ({url}); GitHub issue ID: {issue_id}.")
        if issue_id not in attached:
            add_sub_issue_relationship(repo, parent_issue, issue_id)
            attached.add(issue_id)
        dependencies = fetch_paginated_items(repo, f"issues/{parent_issue}/dependencies/blocked_by")
        if issue_id not in {item.get("id") for item in dependencies}:
            add_blocked_by_dependency(repo, parent_issue, issue_id)
        created.append(record)

    missing = verify_parent_sub_issue_ids(repo, parent_issue, [item["id"] for item in created])
    if missing:
        numbers = ", ".join(f"#{item['number']}" for item in created if item["id"] in missing)
        raise SystemExit(f"Created child issues were not all attached to parent #{parent_issue}. Missing sub-issue links: {numbers}.")
    return created


def _close_completed_issue(repo: str, issue: dict[str, Any], closed: list[int]) -> None:
    if issue.get("state_reason") == "not_planned":
        raise SystemExit("Cannot complete a cancelled issue without human reconciliation.")
    if issue.get("state") == "closed":
        return
    if issue.get("state") != "open":
        raise SystemExit("Cannot complete an issue with unknown state.")
    number = int(issue["number"])
    result = run_gh(["issue", "close", str(number), "--repo", repo, "--reason", "completed"], capture_output=True)
    if result.returncode:
        raise SystemExit(f"Failed to close completed issue #{number}: {gh_failure_details(result)}")
    closed.append(number)


def _fetch_parent_issue(repo: str, issue_number: int) -> dict[str, Any] | None:
    result = run_gh(["api", f"repos/{repo}/issues/{issue_number}/parent"], capture_output=True)
    if result.returncode:
        # GitHub returns 404 when no parent exists. Other failures must never be
        # interpreted as successful completion of the enclosing hierarchy.
        if "HTTP 404" in (result.stderr or ""):
            return None
        raise SystemExit(f"Failed to fetch parent of #{issue_number}: {gh_failure_details(result)}")
    try:
        parent = json.loads(result.stdout)
    except (ValueError, TypeError) as exc:
        raise SystemExit(f"Invalid parent response for #{issue_number}.") from exc
    if not isinstance(parent, dict) or not isinstance(parent.get("number"), int):
        raise SystemExit(f"Invalid parent response for #{issue_number}.")
    if str(parent.get("repository_url", "")).lower() != f"https://api.github.com/repos/{repo}".lower():
        raise SystemExit("Cross-repository parent completion requires human reconciliation.")
    return parent


def _owns_child_delivery(parent_number: int, children: list[dict[str, Any]], comments: list[dict[str, Any]]) -> bool:
    """Require a complete structured delivery record and matching child markers.

    This is operational provenance, not protection against forged GitHub edits.
    Legacy prose records and unrelated manually attached children are insufficient.
    """
    records: dict[int, dict[str, Any]] = {}
    for comment in comments:
        for encoded in re.findall(r"<!-- creative-child-record:(.*?) -->", str(comment.get("body") or "")):
            try:
                record = json.loads(encoded)
            except ValueError:
                return False
            if not isinstance(record, dict) or record.get("parent") != parent_number:
                return False
            issue_id = record.get("id")
            if not isinstance(issue_id, int) or (issue_id in records and records[issue_id] != record):
                return False
            records[issue_id] = record
    if not records or set(records) != {child.get("id") for child in children}:
        return False
    for child in children:
        record = records[child["id"]]
        key = record.get("key")
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]+", key):
            return False
        body = str(child.get("body") or "")
        if (record.get("number") != child.get("number")
                or f"<!-- creative-child:{key} -->" not in body
                or f"Parent issue: #{parent_number}" not in body.splitlines()):
            return False
    return True


def complete_scene_and_roll_up(repo: str, issue_number: int) -> list[int]:
    """Close a delivered scene, then complete owned ancestors whose work is closed.

    Call only after successful final phase-10 delivery. Returns newly closed
    issue numbers, in scene-to-root order. A retry skips already closed issues
    but still reconciles ancestors. Discovery and close failures raise SystemExit.
    """
    parse_repo(repo)
    issue = run_gh_json(["api", f"repos/{repo}/issues/{issue_number}"],
                         failure_message=f"Failed to fetch completed scene #{issue_number}", expect_type=dict)
    scopes = [label.get("name") for label in issue.get("labels", [])
              if isinstance(label, dict) and str(label.get("name", "")).startswith("size:")]
    if scopes != ["size:scene"]:
        raise SystemExit("Final delivery completion requires exactly size:scene.")
    from .cycles import ready_assignment, bind_issue
    bind_issue(issue, repo, issue_number)
    ready_assignment(issue)
    children = fetch_paginated_items(repo, f"issues/{issue_number}/sub_issues")
    dependencies = fetch_paginated_items(repo, f"issues/{issue_number}/dependencies/blocked_by")
    if any(item.get("state") != "closed" or item.get("state_reason") == "not_planned"
           for item in children + dependencies):
        raise SystemExit("Scene has unfinished or cancelled child work or blocking dependencies.")
    closed: list[int] = []
    _close_completed_issue(repo, issue, closed)
    return _complete_parent_chain(repo, _fetch_parent_issue(repo, issue_number), closed, {issue_number})


def reconcile_parent_completion(repo: str, parent_issue: int) -> list[int]:
    """Reconcile completed decomposition after Tiferet retires its active label.

    This never closes a leaf. Recorded ownership, child/dependency completion and
    phase guards are identical to final-scene ancestor completion.
    """
    parse_repo(repo)
    parent = run_gh_json(["api", f"repos/{repo}/issues/{parent_issue}"],
                          failure_message=f"Failed to reconcile parent #{parent_issue}", expect_type=dict)
    return _complete_parent_chain(repo, parent, [], set())


def _complete_parent_chain(repo: str, parent: dict[str, Any] | None,
                           closed: list[int], visited: set[int]) -> list[int]:
    while parent is not None:
        parent_number = parent["number"]
        if parent_number in visited:
            raise SystemExit("Issue parent cycle detected; human reconciliation required.")
        visited.add(parent_number)
        labels = {label.get("name") for label in parent.get("labels", []) if isinstance(label, dict)}
        scopes = {label for label in labels if isinstance(label, str) and label.startswith("size:")}
        if len(scopes) != 1 or not scopes <= {"size:season", "size:episode", "size:act", "size:scene"}:
            return closed
        if any(isinstance(label, str) and label.startswith("phase:") for label in labels):
            return closed
        children = fetch_paginated_items(repo, f"issues/{parent_number}/sub_issues")
        dependencies = fetch_paginated_items(repo, f"issues/{parent_number}/dependencies/blocked_by")
        if not children or any(item.get("state") != "closed" or item.get("state_reason") == "not_planned"
                               for item in children + dependencies):
            return closed
        child_ids = {child.get("id") for child in children}
        if not child_ids <= {dependency.get("id") for dependency in dependencies}:
            return closed
        comments = fetch_paginated_items(repo, f"issues/{parent_number}/comments")
        if not _owns_child_delivery(parent_number, children, comments):
            return closed
        _close_completed_issue(repo, parent, closed)
        parent = _fetch_parent_issue(repo, parent_number)
    return closed
