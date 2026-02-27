from __future__ import annotations

from dataclasses import dataclass

from .domain import Issue
from .policy import PolicyError, TransitionResult
from .service import InMemoryIssueService


REQUIRED_ARTIFACTS_BY_PHASE: dict[str, tuple[str, ...]] = {
    "phase:triad": ("queen:structured",),
    "phase:arbiter": ("triad:personas",),
    "phase:contract": ("story:narrative",),
    "sparc:spec": ("contract:bdd",),
    "sparc:pseudo": ("spec:mapping",),
    "sparc:arch": ("pseudo:flows",),
    "sparc:refine": ("arch:plan",),
    "sparc:done": ("refine:aligned",),
}


@dataclass(frozen=True, slots=True)
class TransitionContext:
    has_open_questions: bool = False
    requires_semantic_contract_change: bool = False
    mapping_insufficient: bool = False
    persona_failure: bool = False
    ambiguity_or_missing_info: bool = False
    scope_change: bool = False
    tests_green: bool = True
    conformance_aligned: bool = True
    semantic_wording_change: bool = False
    fixable_in_refine: bool = False


class IssueExecutor:
    """Applies preflight gates and executes lock-safe transitions."""

    def __init__(self, service: InMemoryIssueService):
        self.service = service

    def preflight(self, issue: Issue, artifacts: set[str]) -> tuple[bool, str]:
        try:
            phase = self.service.policy.validate_single_phase_label(issue)
        except PolicyError as exc:
            return False, str(exc)

        if "needs:human" in issue.labels:
            return False, "Issue has needs:human"
        if phase == "sparc:done" and "blocked" in issue.labels:
            return False, "Completion cannot run while issue is blocked"

        required = REQUIRED_ARTIFACTS_BY_PHASE.get(phase, ())
        missing = [artifact for artifact in required if artifact not in artifacts]
        if missing:
            return False, f"Missing required artifact(s): {', '.join(missing)}"

        return True, "ok"

    def process(
        self,
        issue: Issue,
        *,
        owner: str,
        artifacts: set[str],
        context: TransitionContext | None = None,
    ) -> TransitionResult:
        valid, reason = self.preflight(issue, artifacts)
        if not valid:
            issue.add_labels({"needs:human"})
            return TransitionResult(add=("needs:human",), remove=(), reason=f"Preflight failed: {reason}")

        ctx = context or TransitionContext()
        return self.service.process_transition(
            issue,
            owner=owner,
            has_open_questions=ctx.has_open_questions,
            requires_semantic_contract_change=ctx.requires_semantic_contract_change,
            mapping_insufficient=ctx.mapping_insufficient,
            persona_failure=ctx.persona_failure,
            ambiguity_or_missing_info=ctx.ambiguity_or_missing_info,
            scope_change=ctx.scope_change,
            tests_green=ctx.tests_green,
            conformance_aligned=ctx.conformance_aligned,
            semantic_wording_change=ctx.semantic_wording_change,
            fixable_in_refine=ctx.fixable_in_refine,
        )
