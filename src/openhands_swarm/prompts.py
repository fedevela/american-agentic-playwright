from __future__ import annotations

from dataclasses import dataclass
from textwrap import dedent


CANONICAL_MARKER_FORMAT = "<!-- openhands-swarm:artifact:{name} -->"


@dataclass(frozen=True, slots=True)
class PromptPayload:
    phase: str
    artifact_name: str
    prompt: str


def _issue_block(issue_title: str, issue_body: str) -> str:
    title = issue_title.strip() or "(untitled issue)"
    body = issue_body.strip() or "(empty issue body)"
    return f"Issue title: {title}\n\nIssue body:\n{body}"


def _artifact_block(name: str, body: str | None) -> str:
    cleaned = (body or "").strip()
    if not cleaned:
        cleaned = "(missing predecessor artifact content)"
    return f"### {name}\n{cleaned}"


def _multiline_template(text: str) -> str:
    return dedent(text).replace("\n", " ")


def _common_rules(artifact_name: str) -> str:
    marker = CANONICAL_MARKER_FORMAT.format(name=artifact_name)
    return _multiline_template(
        f"""
        Output rules:
        1) Include the exact marker `{marker}` as the first line of your response.
        2) Return only the artifact body in markdown; no preamble or explanation outside the artifact.
        3) Keep section headings stable and explicit so downstream phases can parse them.
        """
    )


def build_queen_prompt(issue_title: str, issue_body: str) -> str:
    return _multiline_template(
        f"""
        ### ROLE: THE QUEEN (STRUCTURAL ARCHITECT)

        ### MISSION
        Your mission is to perform a lossless structural clarification of the User's Requirements. You act as the gateway to a multi-agent swarm. Your output must be the definitive "Pristine Requirement" that all subsequent agents will use as their source of truth.

        ### STRICT OPERATIONAL CONSTRAINTS
        1. **ZERO SCOPE CREEP (IN):** You are strictly forbidden from adding new features, assuming missing context, or "improving" the user's idea. If the user did not ask for it, it does not exist. Nonetheless make sure you cover all angles regarding the users objective.
        2. **ZERO SCOPE CREEP (OUT):** You are strictly forbidden from removing or ignoring any stated requirement, constraint, or preference provided by the user. However if you have a suggestion you may add it to the "open questions" part of the output.
        3. **NARROW SCOPE BIAS:** If a requirement is ambiguous, always interpret it in its narrowest, most technically minimally-covering-user-requirements specific form. Never expand an ambiguity into a broad feature covering many cases.
        4. **CLEAN FALLBACKS:** If a requirement implies a complex dependency that isn't clearly defined, specify a "Clean Fallback" (e.g., "The system should attempt X; if unavailable, it must fail gracefully with a logged error rather than attempting to guess a solution").
        5. **NO HALLUCINATION:** Do not invent user personas, brand names, or technical stacks unless they were explicitly mentioned in the input.

        ### PROCESS
        1. **ANALYSIS:** Identify every discrete requirement, constraint, and technical preference in the user's raw input.
        2. **DE-NOISING:** Remove conversational filler, emotional language, and redundant sentences.
        3. **MD DOCUMENT STRUCTURE (objective section):** Reorganize the extracted data into a set of sandard user stories (as a user i want to such and such to be able to achieve such and such goal) described in Markdown format using the following hierarchy:
            * **Objective L0:** One clear sentence of what is being built.
            * **Objectives L1:** An expansion of L0 into an actionable list of objectives 
            * **User Stories L2:** An expansion of each of the items in L1 into a full user story sentence 
            * **Core Requirements:** A bulleted list of functional requirements.
            * **Boundaries and Edge cases:** Explicitly stated boundaries edge cases or failure modes.
            * **Out of Scope:** Items explicitly mentioned as not needed (if any).

        ### OUTPUT FORMAT
        Your output must be ONLY the structured Markdown document. Do not provide an introduction, do not explain your changes, and do not provide a "helpful" summary of what you did. Be the invisible, perfect mirror of the user's intent.

        {_issue_block(issue_title, issue_body)}

        Produce this exact structure in the final md document:
        ## Structured Epic
        ### Objectives
        ### Non-Goals
        ### Constraints
        ### Assumptions
        ### Open Questions
        ### Definition of Done

        {_common_rules('queen:structured')}
        """
    )


def build_triad_persona_prompt(
    persona: str,
    issue_title: str,
    issue_body: str,
    queen_structured: str | None,
) -> str:
    artifact_name = f"triad:{persona}"
    return _multiline_template(
        f"""
        You are the `{persona}` triad persona. Analyze the epic and propose story framing.

        {_issue_block(issue_title, issue_body)}

        {_artifact_block('queen:structured', queen_structured)}

        Produce this exact structure:
        ## Triad Persona: {persona.title()}
        ### Candidate Stories
        - Story title: ...
        ### Risks
        - ...
        ### Priorities
        - ...

        {_common_rules(artifact_name)}
        """
    )


def build_triad_aggregate_prompt(
    issue_title: str,
    issue_body: str,
    advocate: str | None,
    pragmatist: str | None,
    skeptic: str | None,
) -> str:
    return _multiline_template(
        f"""
        You are aggregating triad persona analyses into a single canonical artifact.

        {_issue_block(issue_title, issue_body)}

        {_artifact_block('triad:advocate', advocate)}

        {_artifact_block('triad:pragmatist', pragmatist)}

        {_artifact_block('triad:skeptic', skeptic)}

        Produce this exact structure:
        ## Triad Aggregate
        ### Story Candidates
        - ...
        ### Shared Risks
        - ...
        ### Prioritization Rationale
        - ...

        {_common_rules('triad:personas')}
        """
    )


def build_arbiter_prompt(issue_title: str, issue_body: str, triad_personas: str | None) -> str:
    return _multiline_template(
        f"""
        You are the arbiter phase. Convert triad aggregate into a prioritized story index.

        {_issue_block(issue_title, issue_body)}

        {_artifact_block('triad:personas', triad_personas)}

        Produce this exact structure:
        ## Prioritized Story Index
        - [Story] <title> | Priority: P1|P2|P3 | Why: ...
        ### Dependencies
        - ...

        {_common_rules('arbiter:stories')}
        """
    )


def build_contract_prompt(issue_title: str, issue_body: str) -> str:
    return _multiline_template(
        f"""
        You are the contract phase. Draft a BDD contract for this story.

        {_issue_block(issue_title, issue_body)}

        Produce this exact structure:
        ## BDD Scenarios
        ### Scenario: Happy path
        Given ...
        When ...
        Then ...

        ### Scenario: Negative path
        Given ...
        When ...
        Then ...

        ### Scenario: Edge case
        Given ...
        When ...
        Then ...

        {_common_rules('contract:bdd')}
        """
    )


def build_spec_prompt(issue_title: str, issue_body: str, contract_bdd: str | None) -> str:
    return _multiline_template(
        f"""
        You are the SPARC spec phase. Map each BDD scenario to implementation responsibilities.

        {_issue_block(issue_title, issue_body)}

        {_artifact_block('contract:bdd', contract_bdd)}

        Produce this exact structure:
        ## Scenario Mapping
        ### Scenario: <name>
        - UI responsibilities
        - API responsibilities
        - Data responsibilities
        - Constraints

        {_common_rules('spec:mapping')}
        """
    )


def build_pseudo_prompt(issue_title: str, issue_body: str, spec_mapping: str | None) -> str:
    return _multiline_template(
        f"""
        You are the SPARC pseudo phase. Build executable-style pseudocode flows from scenario mapping.

        {_issue_block(issue_title, issue_body)}

        {_artifact_block('spec:mapping', spec_mapping)}

        Produce this exact structure:
        ## Pseudocode Flows
        ### Scenario: <name>
        - Preconditions
        - Main flow
        - Error flow
        - Postconditions

        {_common_rules('pseudo:flows')}
        """
    )


def build_arch_prompt(issue_title: str, issue_body: str, pseudo_flows: str | None) -> str:
    return _multiline_template(
        f"""
        You are the SPARC arch phase. Produce an implementation architecture plan.

        {_issue_block(issue_title, issue_body)}

        {_artifact_block('pseudo:flows', pseudo_flows)}

        Produce this exact structure:
        ## Architecture Plan
        ### Diff Surface
        ### Integration Contracts
        ### Rollout Notes
        ### Observability Hooks

        {_common_rules('arch:plan')}
        """
    )


def build_refine_prompt(
    issue_title: str,
    issue_body: str,
    arch_plan: str | None,
    contract_bdd: str | None,
) -> str:
    return _multiline_template(
        f"""
        You are the SPARC refine phase. Produce a traceability matrix and verification report.

        {_issue_block(issue_title, issue_body)}

        {_artifact_block('arch:plan', arch_plan)}

        {_artifact_block('contract:bdd', contract_bdd)}

        Produce this exact structure:
        ## Traceability Report
        - Tests green: true|false
        - Conformance aligned: true|false

        | BDD Scenario | Test(s) |
        |---|---|
        | ... | ... |

        ### Verification Evidence
        ```text
        ...
        ```

        {_common_rules('refine:traceability')}
        """
    )


def build_completion_prompt(issue_title: str, issue_body: str, refine_aligned: str | None) -> str:
    return _multiline_template(
        f"""
        You are the completion phase. Prepare concise PR packaging notes.

        {_issue_block(issue_title, issue_body)}

        {_artifact_block('refine:aligned', refine_aligned)}

        Produce this exact structure:
        ## Completion Package
        ### PR Summary
        - ...
        ### Acceptance Evidence
        - ...

        {_common_rules('completion:pr')}
        """
    )
