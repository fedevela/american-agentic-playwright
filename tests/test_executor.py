from openhands_swarm.domain import Issue, Phase
from openhands_swarm.executor import IssueExecutor, TransitionContext
from openhands_swarm.service import InMemoryIssueService


def test_preflight_fails_without_required_artifact() -> None:
    service = InMemoryIssueService()
    executor = IssueExecutor(service)
    issue = Issue(number=1, labels={Phase.TRIAD.value})

    valid, reason = executor.preflight(issue, artifacts=set())
    assert valid is False
    assert "queen:structured" in reason


def test_preflight_passes_with_required_artifact() -> None:
    service = InMemoryIssueService()
    executor = IssueExecutor(service)
    issue = Issue(number=2, labels={Phase.TRIAD.value})

    valid, reason = executor.preflight(issue, artifacts={"queen:structured"})
    assert valid is True
    assert reason == "ok"


def test_process_adds_needs_human_on_preflight_failure() -> None:
    service = InMemoryIssueService()
    executor = IssueExecutor(service)
    issue = Issue(number=3, labels={Phase.SPEC.value})

    result = executor.process(issue, owner="run-1", artifacts=set())
    assert "needs:human" in issue.labels
    assert result.add == ("needs:human",)


def test_process_refine_fixable_failures_stays_in_refine() -> None:
    service = InMemoryIssueService()
    executor = IssueExecutor(service)
    issue = Issue(number=4, labels={Phase.REFINE.value})

    result = executor.process(
        issue,
        owner="run-1",
        artifacts={"arch:plan"},
        context=TransitionContext(
            tests_green=False,
            conformance_aligned=False,
            fixable_in_refine=True,
        ),
    )
    assert result.add == ()
    assert result.remove == ()
    assert Phase.REFINE.value in issue.labels
