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


def test_triad_persona_failure_adds_blocked_and_keeps_phase() -> None:
    policy = StateMachinePolicy()
    issue = Issue(number=4, labels={Phase.TRIAD.value})
    result = policy.transition(issue, persona_failure=True)
    assert result.add == ("blocked",)
    assert result.remove == ()


def test_contract_ambiguity_adds_needs_human_and_keeps_phase() -> None:
    policy = StateMachinePolicy()
    issue = Issue(number=5, labels={Phase.CONTRACT.value})
    result = policy.transition(issue, ambiguity_or_missing_info=True)
    assert result.add == ("needs:human",)
    assert result.remove == ()


def test_arch_scope_change_requests_restart_contract() -> None:
    policy = StateMachinePolicy()
    issue = Issue(number=6, labels={Phase.ARCH.value})
    result = policy.transition(issue, scope_change=True)
    assert set(result.add) == {"restart:contract", "needs:human"}
    assert result.remove == (Phase.ARCH.value,)


def test_refine_fixable_failures_stay_in_refine() -> None:
    policy = StateMachinePolicy()
    issue = Issue(number=7, labels={Phase.REFINE.value})
    result = policy.transition(
        issue,
        tests_green=False,
        conformance_aligned=False,
        fixable_in_refine=True,
    )
    assert result.add == ()
    assert result.remove == ()


def test_refine_semantic_wording_change_restarts_contract() -> None:
    policy = StateMachinePolicy()
    issue = Issue(number=8, labels={Phase.REFINE.value})
    result = policy.transition(
        issue,
        tests_green=False,
        conformance_aligned=False,
        semantic_wording_change=True,
    )
    assert set(result.add) == {"restart:contract", "needs:human"}
    assert result.remove == (Phase.REFINE.value,)
