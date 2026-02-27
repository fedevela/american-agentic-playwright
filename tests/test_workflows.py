from openhands_swarm.domain import Issue, Phase
from openhands_swarm.executor import IssueExecutor
from openhands_swarm.service import InMemoryIssueService
from openhands_swarm.workflows import WorkflowEngine, WorkflowInput


def _engine() -> WorkflowEngine:
    return WorkflowEngine(IssueExecutor(InMemoryIssueService()))


def test_queen_open_questions_stops_for_human() -> None:
    engine = _engine()
    issue = Issue(number=1, labels={Phase.QUEEN.value})
    data = WorkflowInput(issue=issue, owner="run-1", artifacts=set())

    result = engine.run_queen(data, open_questions=True)

    assert "needs:human" in issue.labels
    assert result.remove == (Phase.QUEEN.value,)


def test_happy_path_story_to_completion() -> None:
    engine = _engine()
    issue = Issue(number=2, labels={Phase.CONTRACT.value})
    artifacts = {"story:narrative"}
    data = WorkflowInput(issue=issue, owner="run-1", artifacts=artifacts)

    engine.run_contract(data, ambiguity=False)
    assert Phase.SPEC.value in issue.labels

    engine.run_spec(data, semantic_contract_change=False)
    assert Phase.PSEUDO.value in issue.labels

    engine.run_pseudo(data, mapping_insufficient=False)
    assert Phase.ARCH.value in issue.labels

    engine.run_arch(data, scope_change=False)
    assert Phase.REFINE.value in issue.labels

    engine.run_refine(
        data,
        tests_green=True,
        conformance_aligned=True,
        semantic_wording_change=False,
        fixable_in_refine=False,
    )
    assert Phase.DONE.value in issue.labels
    assert "refine:aligned" in artifacts

    engine.run_completion(data)
    assert Phase.COMPLETED.value in issue.labels
    assert "completion:pr" in artifacts


def test_refine_fixable_failures_stays_in_refine() -> None:
    engine = _engine()
    issue = Issue(number=3, labels={Phase.REFINE.value})
    data = WorkflowInput(issue=issue, owner="run-1", artifacts={"arch:plan"})

    result = engine.run_refine(
        data,
        tests_green=False,
        conformance_aligned=False,
        semantic_wording_change=False,
        fixable_in_refine=True,
    )

    assert result.add == ()
    assert result.remove == ()
    assert Phase.REFINE.value in issue.labels
