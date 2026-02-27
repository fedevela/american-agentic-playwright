from openhands_swarm.domain import Issue, Phase
from openhands_swarm.executor import IssueExecutor, TransitionContext
from openhands_swarm.orchestrator import SwarmOrchestrator
from openhands_swarm.queue import StaggeredQueue
from openhands_swarm.service import InMemoryIssueService


def test_orchestrator_skips_duplicate_issue_in_same_batch() -> None:
    service = InMemoryIssueService()
    executor = IssueExecutor(service)
    queue = StaggeredQueue(max_parallel=3, stagger_seconds=0.5)
    orchestrator = SwarmOrchestrator(executor, queue)

    issue = Issue(number=1, labels={Phase.TRIAD.value})
    issue_lookup = {1: issue}
    artifacts = {1: {"queen:structured"}}

    orchestrator.enqueue(1, "run-a")
    orchestrator.enqueue(1, "run-b")
    orchestrator.enqueue(1, "run-c")

    reports = orchestrator.process_batch(issue_lookup=issue_lookup, artifacts_by_issue=artifacts)
    assert len(reports) == 3
    assert reports[0].applied is True
    assert reports[1].applied is False
    assert reports[2].applied is False
    assert "Duplicate issue" in reports[1].reason


def test_orchestrator_applies_offsets_and_transitions() -> None:
    service = InMemoryIssueService()
    executor = IssueExecutor(service)
    queue = StaggeredQueue(max_parallel=2, stagger_seconds=1.25)
    orchestrator = SwarmOrchestrator(executor, queue)

    issue_a = Issue(number=10, labels={Phase.CONTRACT.value})
    issue_b = Issue(number=11, labels={Phase.REFINE.value})

    issue_lookup = {
        10: issue_a,
        11: issue_b,
    }
    artifacts = {
        10: {"story:narrative"},
        11: {"arch:plan"},
    }
    contexts = {
        11: TransitionContext(
            tests_green=False,
            conformance_aligned=False,
            fixable_in_refine=True,
        )
    }

    orchestrator.enqueue(10, "run-1")
    orchestrator.enqueue(11, "run-2")

    reports = orchestrator.process_batch(
        issue_lookup=issue_lookup,
        artifacts_by_issue=artifacts,
        context_by_issue=contexts,
    )

    assert [r.offset_seconds for r in reports] == [0.0, 1.25]
    assert Phase.SPEC.value in issue_a.labels
    assert Phase.REFINE.value in issue_b.labels
    assert reports[0].applied is True
    assert reports[1].applied is True
