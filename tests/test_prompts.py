from openhands_swarm.prompts import (
    build_arch_prompt,
    build_arbiter_prompt,
    build_completion_prompt,
    build_contract_prompt,
    build_pseudo_prompt,
    build_queen_prompt,
    build_refine_prompt,
    build_spec_prompt,
    build_triad_aggregate_prompt,
    build_triad_persona_prompt,
)


def test_phase_prompts_include_canonical_marker_and_structure() -> None:
    prompts = [
        build_queen_prompt("Epic", "Details"),
        build_triad_persona_prompt("advocate", "Epic", "Details", "queen content"),
        build_triad_aggregate_prompt("Epic", "Details", "a", "p", "s"),
        build_arbiter_prompt("Epic", "Details", "triad aggregate"),
        build_contract_prompt("Story", "Body"),
        build_spec_prompt("Story", "Body", "bdd"),
        build_pseudo_prompt("Story", "Body", "mapping"),
        build_arch_prompt("Story", "Body", "flows"),
        build_refine_prompt("Story", "Body", "arch", "bdd"),
        build_completion_prompt("Story", "Body", "aligned"),
    ]

    assert all("<!-- openhands-swarm:artifact:" in prompt for prompt in prompts)
    assert all("Output rules:" in prompt for prompt in prompts)
    assert "## Structured Epic" in prompts[0]
    assert "## Triad Persona: Advocate" in prompts[1]
    assert "## Triad Aggregate" in prompts[2]
    assert "## Prioritized Story Index" in prompts[3]
    assert "## BDD Scenarios" in prompts[4]
    assert "## Scenario Mapping" in prompts[5]
    assert "## Pseudocode Flows" in prompts[6]
    assert "## Architecture Plan" in prompts[7]
    assert "## Traceability Report" in prompts[8]
    assert "## Completion Package" in prompts[9]
