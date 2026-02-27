from __future__ import annotations

import argparse

from .domain import Issue
from .policy import PolicyError, StateMachinePolicy
from .service import InMemoryIssueService


def _csv_labels(value: str | None) -> set[str]:
    if not value:
        return set()
    return {part.strip() for part in value.split(",") if part.strip()}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openhands-swarm")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="Validate single-phase invariant")
    validate.add_argument("--phase-labels", default="")
    validate.add_argument("--meta-labels", default="")

    transition = subparsers.add_parser("transition", help="Simulate policy transition")
    transition.add_argument("--phase", required=True)
    transition.add_argument("--open-questions", choices=["true", "false"], default="false")
    transition.add_argument("--semantic-change", choices=["true", "false"], default="false")
    transition.add_argument("--mapping-insufficient", choices=["true", "false"], default="false")
    transition.add_argument("--persona-failure", choices=["true", "false"], default="false")
    transition.add_argument("--ambiguity", choices=["true", "false"], default="false")
    transition.add_argument("--scope-change", choices=["true", "false"], default="false")
    transition.add_argument("--tests-green", choices=["true", "false"], default="true")
    transition.add_argument("--conformance-aligned", choices=["true", "false"], default="true")
    transition.add_argument("--semantic-wording-change", choices=["true", "false"], default="false")
    transition.add_argument("--fixable-in-refine", choices=["true", "false"], default="false")

    lock = subparsers.add_parser("lock", help="Acquire lock in simulation")
    lock.add_argument("--owner", required=True)

    unlock = subparsers.add_parser("unlock", help="Release lock in simulation")
    unlock.add_argument("--owner", required=True)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "validate":
        policy = StateMachinePolicy()
        labels = _csv_labels(args.phase_labels) | _csv_labels(args.meta_labels)
        issue = Issue(number=1, labels=labels)
        try:
            phase = policy.validate_single_phase_label(issue)
            print(f"valid: {phase}")
            return 0
        except PolicyError as exc:
            print(f"invalid: {exc}")
            return 2

    service = InMemoryIssueService()
    issue = service.get_or_create_issue(1, labels={"phase:queen"})

    if args.command == "lock":
        service.acquire_lock(issue, args.owner)
        print(f"lock acquired by {args.owner}")
        return 0

    if args.command == "unlock":
        service.acquire_lock(issue, args.owner)
        service.release_lock(issue, args.owner)
        print(f"lock released by {args.owner}")
        return 0

    if args.command == "transition":
        issue.remove_labels(issue.phase_labels())
        issue.add_labels({args.phase})

        result = service.process_transition(
            issue,
            owner="cli-run",
            has_open_questions=args.open_questions == "true",
            requires_semantic_contract_change=args.semantic_change == "true",
            mapping_insufficient=args.mapping_insufficient == "true",
            persona_failure=args.persona_failure == "true",
            ambiguity_or_missing_info=args.ambiguity == "true",
            scope_change=args.scope_change == "true",
            tests_green=args.tests_green == "true",
            conformance_aligned=args.conformance_aligned == "true",
            semantic_wording_change=args.semantic_wording_change == "true",
            fixable_in_refine=args.fixable_in_refine == "true",
        )
        print(f"add={list(result.add)} remove={list(result.remove)} reason={result.reason}")
        print(f"labels={sorted(issue.labels)}")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
