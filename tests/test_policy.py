from openhands_swarm.domain import Issue, Phase
from openhands_swarm.policy import PolicyError, StateMachinePolicy


def test_validate_single_phase_ok() -> None:
    policy = StateMachinePolicy()
    issue = Issue(number=1, labels={Phase.QUEEN.value})
    assert policy.validate_single_phase_label(issue) == Phase.QUEEN.value


def test_validate_single_phase_fails_on_multiple() -> None:
    policy = StateMachinePolicy()
    issue = Issue(number=1, labels={Phase.QUEEN.value, Phase.TRIAD.value})
    try:
        policy.validate_single_phase_label(issue)
        assert False, "Expected PolicyError"
    except PolicyError:
        assert True


def test_queen_open_questions_goes_to_needs_human() -> None:
    policy = StateMachinePolicy()
    issue = Issue(number=1, labels={Phase.QUEEN.value})
    result = policy.transition(issue, has_open_questions=True)
    assert result.add == ("needs:human",)
    assert result.remove == (Phase.QUEEN.value,)


def test_forward_story_transition_spec_to_pseudo() -> None:
    policy = StateMachinePolicy()
    issue = Issue(number=2, labels={Phase.SPEC.value})
    result = policy.transition(issue)
    assert result.add == (Phase.PSEUDO.value,)
    assert result.remove == (Phase.SPEC.value,)


def test_spec_semantic_change_requests_restart_contract() -> None:
    policy = StateMachinePolicy()
    issue = Issue(number=3, labels={Phase.SPEC.value})
    result = policy.transition(issue, requires_semantic_contract_change=True)
    assert set(result.add) == {"restart:contract", "needs:human"}
    assert result.remove == (Phase.SPEC.value,)
