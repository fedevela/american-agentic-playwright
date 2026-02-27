from __future__ import annotations

from dataclasses import dataclass

from .domain import Issue
from .executor import IssueExecutor, TransitionContext
from .policy import TransitionResult


@dataclass(frozen=True, slots=True)
class WorkflowInput:
    issue: Issue
    owner: str
    artifacts: set[str]


class WorkflowEngine:
    """High-level phase handlers that mirror the 9 workflow intent without YAML."""

    def __init__(self, executor: IssueExecutor):
        self.executor = executor

    def run(self, data: WorkflowInput, *, context: TransitionContext | None = None) -> TransitionResult:
        return self.executor.process(
            data.issue,
            owner=data.owner,
            artifacts=data.artifacts,
            context=context,
        )

    def run_queen(self, data: WorkflowInput, *, open_questions: bool) -> TransitionResult:
        data.artifacts.add("queen:structured")
        return self.run(data, context=TransitionContext(has_open_questions=open_questions))

    def run_triad(self, data: WorkflowInput, *, persona_failure: bool) -> TransitionResult:
        if not persona_failure:
            data.artifacts.add("triad:personas")
        return self.run(data, context=TransitionContext(persona_failure=persona_failure))

    def run_arbiter(self, data: WorkflowInput) -> TransitionResult:
        data.artifacts.add("arbiter:stories")
        return self.run(data)

    def run_contract(self, data: WorkflowInput, *, ambiguity: bool) -> TransitionResult:
        if not ambiguity:
            data.artifacts.add("contract:bdd")
        return self.run(data, context=TransitionContext(ambiguity_or_missing_info=ambiguity))

    def run_spec(self, data: WorkflowInput, *, semantic_contract_change: bool) -> TransitionResult:
        if not semantic_contract_change:
            data.artifacts.add("spec:mapping")
        return self.run(
            data,
            context=TransitionContext(requires_semantic_contract_change=semantic_contract_change),
        )

    def run_pseudo(self, data: WorkflowInput, *, mapping_insufficient: bool) -> TransitionResult:
        if not mapping_insufficient:
            data.artifacts.add("pseudo:flows")
        return self.run(data, context=TransitionContext(mapping_insufficient=mapping_insufficient))

    def run_arch(self, data: WorkflowInput, *, scope_change: bool) -> TransitionResult:
        if not scope_change:
            data.artifacts.add("arch:plan")
        return self.run(data, context=TransitionContext(scope_change=scope_change))

    def run_refine(
        self,
        data: WorkflowInput,
        *,
        tests_green: bool,
        conformance_aligned: bool,
        semantic_wording_change: bool,
        fixable_in_refine: bool,
    ) -> TransitionResult:
        result = self.run(
            data,
            context=TransitionContext(
                tests_green=tests_green,
                conformance_aligned=conformance_aligned,
                semantic_wording_change=semantic_wording_change,
                fixable_in_refine=fixable_in_refine,
            ),
        )
        if tests_green and conformance_aligned and not semantic_wording_change:
            data.artifacts.add("refine:aligned")
        return result

    def run_completion(self, data: WorkflowInput) -> TransitionResult:
        data.artifacts.add("completion:pr")
        return self.run(data)
