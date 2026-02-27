from __future__ import annotations

from dataclasses import dataclass, field

from .domain import Issue, LockInfo
from .policy import StateMachinePolicy, TransitionResult


class LockError(RuntimeError):
    """Raised when lock operations are invalid."""


@dataclass(slots=True)
class InMemoryIssueService:
    policy: StateMachinePolicy = field(default_factory=StateMachinePolicy)
    issues: dict[int, Issue] = field(default_factory=dict)

    def get_or_create_issue(self, number: int, labels: set[str] | None = None) -> Issue:
        if number not in self.issues:
            self.issues[number] = Issue(number=number, labels=labels or set())
        else:
            if labels:
                self.issues[number].add_labels(labels)
        return self.issues[number]

    def acquire_lock(self, issue: Issue, owner: str) -> None:
        if issue.lock and issue.lock.owner != owner:
            raise LockError(
                f"Issue #{issue.number} already locked by {issue.lock.owner}; cannot acquire for {owner}"
            )
        issue.lock = LockInfo(owner=owner)
        issue.add_labels({"lock"})

    def release_lock(self, issue: Issue, owner: str) -> None:
        if issue.lock is None:
            return
        if issue.lock.owner != owner:
            raise LockError(
                f"Issue #{issue.number} lock owned by {issue.lock.owner}; cannot release for {owner}"
            )
        issue.lock = None
        issue.remove_labels({"lock"})

    def apply_transition(self, issue: Issue, result: TransitionResult) -> Issue:
        issue.remove_labels(result.remove)
        issue.add_labels(result.add)
        return issue

    def process_transition(
        self,
        issue: Issue,
        *,
        owner: str,
        has_open_questions: bool = False,
        requires_semantic_contract_change: bool = False,
        mapping_insufficient: bool = False,
    ) -> TransitionResult:
        """Acquire lock, evaluate policy transition, mutate labels, and release lock."""
        self.acquire_lock(issue, owner)
        try:
            result = self.policy.transition(
                issue,
                has_open_questions=has_open_questions,
                requires_semantic_contract_change=requires_semantic_contract_change,
                mapping_insufficient=mapping_insufficient,
            )
            self.apply_transition(issue, result)
            return result
        finally:
            self.release_lock(issue, owner)
