from __future__ import annotations

from typing import Any

from ..config import NEEDS_HUMAN_LABEL, NEXT_LABEL_MAP, PHASE_LABEL_METADATA
from ..gh_client import run_gh, run_gh_json
from ..logging_utils import log_info


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