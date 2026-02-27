from __future__ import annotations

from dataclasses import dataclass

from .domain import Issue, Phase


class PolicyError(ValueError):
    """Raised when an invariant or transition rule is violated."""


@dataclass(frozen=True, slots=True)
class TransitionResult:
    add: tuple[str, ...]
    remove: tuple[str, ...]
    reason: str


class StateMachinePolicy:
    EPIC_TRANSITIONS: dict[str, str] = {
        Phase.QUEEN.value: Phase.TRIAD.value,
        Phase.TRIAD.value: Phase.ARBITER.value,
    }
    STORY_TRANSITIONS: dict[str, str] = {
        Phase.CONTRACT.value: Phase.SPEC.value,
        Phase.SPEC.value: Phase.PSEUDO.value,
        Phase.PSEUDO.value: Phase.ARCH.value,
        Phase.ARCH.value: Phase.REFINE.value,
        Phase.REFINE.value: Phase.DONE.value,
        Phase.DONE.value: Phase.COMPLETED.value,
    }

    def validate_single_phase_label(self, issue: Issue) -> str:
        phases = issue.phase_labels()
        if len(phases) != 1:
            raise PolicyError(
                f"Issue #{issue.number} must have exactly one phase label; found {sorted(phases)}"
            )
        return next(iter(phases))

    def can_advance(self, issue: Issue) -> None:
        if "needs:human" in issue.labels:
            raise PolicyError("Issue is blocked by needs:human")

    def next_phase(self, issue: Issue) -> str:
        current = self.validate_single_phase_label(issue)
        if current == Phase.ARBITER.value:
            return "epic:ready"

        if current in self.EPIC_TRANSITIONS:
            return self.EPIC_TRANSITIONS[current]

        if current in self.STORY_TRANSITIONS:
            return self.STORY_TRANSITIONS[current]

        raise PolicyError(f"No forward transition configured for {current}")

    def transition(
        self,
        issue: Issue,
        *,
        has_open_questions: bool = False,
        requires_semantic_contract_change: bool = False,
        mapping_insufficient: bool = False,
    ) -> TransitionResult:
        current = self.validate_single_phase_label(issue)

        if current == Phase.QUEEN.value and has_open_questions:
            return TransitionResult(
                add=("needs:human",),
                remove=(Phase.QUEEN.value,),
                reason="Open questions require human input",
            )

        if current == Phase.SPEC.value and requires_semantic_contract_change:
            return TransitionResult(
                add=("restart:contract", "needs:human"),
                remove=(Phase.SPEC.value,),
                reason="Spec discovered contract ambiguity",
            )

        if current == Phase.PSEUDO.value and mapping_insufficient:
            return TransitionResult(
                add=("restart:spec",),
                remove=(Phase.PSEUDO.value,),
                reason="Pseudo needs stronger spec mapping",
            )

        if current in {Phase.ARCH.value, Phase.REFINE.value} and requires_semantic_contract_change:
            return TransitionResult(
                add=("restart:contract", "needs:human"),
                remove=(current,),
                reason="Semantic contract change required",
            )

        self.can_advance(issue)
        target = self.next_phase(issue)
        return TransitionResult(
            add=(target,),
            remove=(current,),
            reason=f"Forward transition {current} -> {target}",
        )
