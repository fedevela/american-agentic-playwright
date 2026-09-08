"""Validated season ownership and serialization of the shared writing checkout."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
from pathlib import Path
import re

from . import cycles, github_ops


@dataclass(frozen=True)
class SeasonRoot:
    number: int
    title: str
    ancestry: tuple[int, ...]


def resolve_season_root(repo: str, issue: int, issue_data: dict | None = None) -> SeasonRoot:
    """Require GitHub parent links and recorded delivery ownership to agree."""
    visited: list[int] = []
    data = issue_data if issue_data is not None else github_ops.fetch_issue_data(repo, issue)
    original_data = data
    season_claims = []
    while True:
        if issue in visited:
            raise SystemExit('Issue parent cycle detected; season reconciliation required.')
        visited.append(issue)
        cycles.bind_issue(data, repo, issue)
        url = data.get('repository_url')
        if url is not None and str(url).lower() != f'https://api.github.com/repos/{repo}'.lower():
            raise SystemExit('Cross-repository season ownership requires reconciliation.')
        if not isinstance(data.get('id'), int):
            identity = github_ops.run_gh_json(['api', f'repos/{repo}/issues/{issue}'], failure_message=f'Cannot verify issue #{issue} ownership', expect_type=dict)
            if identity.get('number') != issue or not isinstance(identity.get('id'), int) or str(identity.get('repository_url', '')).lower() != f'https://api.github.com/repos/{repo}'.lower():
                raise SystemExit('Invalid or cross-repository GitHub issue ownership.')
            data = {**data, 'id': identity['id']}
        season_claims.extend(record['season_ref'] for record in cycles.issue_records(data) if record.get('season_ref') is not None)
        scope = cycles.issue_scope(data)
        assignment = cycles.inherited_assignment(data)
        if assignment and assignment.get("season_ref") is not None:
            season_claims.append(assignment["season_ref"])
        parent = github_ops._fetch_parent_issue(repo, issue)
        markers = re.findall(r'^Parent issue: #(\d+)\s*$', str(data.get('body') or ''), re.MULTILINE)
        if scope == 'season':
            if parent is not None or assignment is not None or markers or '<!-- creative-child:' in str(data.get('body') or ''):
                raise SystemExit('Season must be a human-created root without parent ownership.')
            title = ' '.join(str(data.get('title') or '').split())
            if not title:
                raise SystemExit('Season root title is required for shared delivery.')
            reference = {"repo": repo, "number": issue, "scope": "season"}
            if any(claim != reference for claim in season_claims):
                raise SystemExit("Persisted season ownership conflicts with GitHub ancestry.")
            original_data["_season_ref"] = reference
            return SeasonRoot(issue, title, tuple(visited))
        if parent is None:
            raise SystemExit(f'Issue #{issue} has no validated parent leading to a season root.')
        parent_number = parent['number']
        if (markers and markers != [str(parent_number)]) or (not markers and assignment is None):
            raise SystemExit(f'Issue #{issue} has missing or conflicting parent ownership markers.')
        if assignment is not None and (assignment.get('parent_issue') != parent_number or assignment.get('parent_ref', {}).get('repo', repo) != repo):
            raise SystemExit('Assignment parent ownership conflicts with GitHub parent.')
        parent_data = github_ops.fetch_issue_data(repo, parent_number)
        if assignment is None or not github_ops._owns_child_delivery(parent_number, [data]):
            raise SystemExit(f'Issue #{issue} lacks a valid parent assignment link.')
        issue, data = parent_number, parent_data


@contextmanager
def checkout_lock(path: Path):
    """Hold an exclusive lock outside the checkout, including clone preparation."""
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.parent / f'.{path.name}.creative-checkout.lock'
    with lock_path.open('a+') as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SystemExit(f'Creative checkout is already in use: {path}. Retry after the active run finishes.') from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
