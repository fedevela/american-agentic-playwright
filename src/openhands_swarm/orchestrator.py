from __future__ import annotations

from dataclasses import dataclass

from .domain import Issue
from .executor import IssueExecutor, TransitionContext
from .policy import TransitionResult
from .queue import StaggeredQueue, WorkItem


@dataclass(frozen=True, slots=True)
class ExecutionReport:
    issue_number: int
    owner: str
    offset_seconds: float
    applied: bool
    reason: str
    add: tuple[str, ...] = ()
    remove: tuple[str, ...] = ()


class SwarmOrchestrator:
    """Coordinates queue-batch processing while preventing duplicate issue grabs."""

    def __init__(self, executor: IssueExecutor, queue: StaggeredQueue):
        self.executor = executor
        self.queue = queue

    def process_batch(
        self,
        *,
        issue_lookup: dict[int, Issue],
        artifacts_by_issue: dict[int, set[str]],
        context_by_issue: dict[int, TransitionContext] | None = None,
    ) -> list[ExecutionReport]:
        context_by_issue = context_by_issue or {}
        batch = self.queue.pop_batch()
        offsets = self.queue.schedule_offsets(len(batch))
        seen: set[int] = set()
        reports: list[ExecutionReport] = []

        for item, offset in zip(batch, offsets):
            if item.issue_number in seen:
                reports.append(
                    ExecutionReport(
                        issue_number=item.issue_number,
                        owner=item.owner,
                        offset_seconds=offset,
                        applied=False,
                        reason="Duplicate issue in same batch; skipped",
                    )
                )
                continue
            seen.add(item.issue_number)

            issue = issue_lookup[item.issue_number]
            artifacts = artifacts_by_issue.get(item.issue_number, set())
            context = context_by_issue.get(item.issue_number, TransitionContext())

            result: TransitionResult = self.executor.process(
                issue,
                owner=item.owner,
                artifacts=artifacts,
                context=context,
            )
            reports.append(
                ExecutionReport(
                    issue_number=item.issue_number,
                    owner=item.owner,
                    offset_seconds=offset,
                    applied=True,
                    reason=result.reason,
                    add=result.add,
                    remove=result.remove,
                )
            )

        return reports

    def enqueue(self, issue_number: int, owner: str) -> None:
        self.queue.enqueue(WorkItem(issue_number=issue_number, owner=owner))
