from openhands_swarm.domain import Issue, Phase
from openhands_swarm.service import InMemoryIssueService, LockError


def test_lock_acquire_release_happy_path() -> None:
    service = InMemoryIssueService()
    issue = Issue(number=1, labels={Phase.QUEEN.value})

    service.acquire_lock(issue, owner="run-1")
    assert issue.lock is not None
    assert issue.lock.owner == "run-1"
    assert "lock" in issue.labels

    service.release_lock(issue, owner="run-1")
    assert issue.lock is None
    assert "lock" not in issue.labels


def test_lock_rejects_competing_owner() -> None:
    service = InMemoryIssueService()
    issue = Issue(number=1, labels={Phase.QUEEN.value})
    service.acquire_lock(issue, owner="run-1")

    try:
        service.acquire_lock(issue, owner="run-2")
        assert False, "Expected LockError"
    except LockError:
        assert True


def test_process_transition_applies_and_releases_lock() -> None:
    service = InMemoryIssueService()
    issue = Issue(number=2, labels={Phase.CONTRACT.value})

    result = service.process_transition(issue, owner="run-1")

    assert result.add == (Phase.SPEC.value,)
    assert Phase.SPEC.value in issue.labels
    assert Phase.CONTRACT.value not in issue.labels
    assert "lock" not in issue.labels
    assert issue.lock is None
