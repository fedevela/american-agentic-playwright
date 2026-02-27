#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from openhands_swarm.prompts import (  # noqa: E402
    PromptPayload,
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


PHASE_LABELS = {
    "phase:queen",
    "phase:triad",
    "phase:arbiter",
    "phase:contract",
    "sparc:spec",
    "sparc:pseudo",
    "sparc:arch",
    "sparc:refine",
    "sparc:done",
    "sparc:completed",
}

PERSONAS = ("advocate", "pragmatist", "skeptic")

COMMAND_PHASE_LABEL = {
    "queen": "phase:queen",
    "triad-persona": "phase:triad",
    "triad-aggregate": "phase:triad",
    "arbiter": "phase:arbiter",
    "contract": "phase:contract",
    "spec": "sparc:spec",
    "pseudo": "sparc:pseudo",
    "arch": "sparc:arch",
    "refine": "sparc:refine",
    "completion": "sparc:done",
}

COMMAND_ARTIFACT = {
    "queen": "queen:structured",
    "triad-aggregate": "triad:personas",
    "arbiter": "arbiter:stories",
    "contract": "contract:bdd",
    "spec": "spec:mapping",
    "pseudo": "pseudo:flows",
    "arch": "arch:plan",
    "refine": "refine:traceability",
    "completion": "completion:pr",
}


@dataclass
class Context:
    repo: str
    issue_number: int
    owner: str
    run_url: str


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=check, text=True, capture_output=True)


def _gh_json(args: list[str]) -> Any:
    result = _run(["gh", *args])
    if not result.stdout.strip():
        return None
    return json.loads(result.stdout)


def _gh_api_json(method: str, endpoint: str, fields: dict[str, str] | None = None) -> Any:
    cmd = ["gh", "api", "-X", method, endpoint]
    if fields:
        for key, value in fields.items():
            cmd.extend(["-f", f"{key}={value}"])
    result = _run(cmd)
    if not result.stdout.strip():
        return None
    return json.loads(result.stdout)


def _issue_endpoint(ctx: Context, suffix: str = "") -> str:
    root = f"repos/{ctx.repo}/issues/{ctx.issue_number}"
    return f"{root}{suffix}"


def _get_issue(ctx: Context) -> dict[str, Any]:
    return _gh_api_json("GET", _issue_endpoint(ctx))


def _labels(issue: dict[str, Any]) -> set[str]:
    return {label["name"] for label in issue.get("labels", [])}


def _phase_labels(labels: set[str]) -> set[str]:
    return {label for label in labels if label in PHASE_LABELS}


def _list_comments(ctx: Context) -> list[dict[str, Any]]:
    data = _gh_api_json("GET", f"{_issue_endpoint(ctx, '/comments')}?per_page=100")
    return data or []


def _find_comment_by_marker(ctx: Context, marker: str) -> dict[str, Any] | None:
    for comment in _list_comments(ctx):
        if marker in comment.get("body", ""):
            return comment
    return None


def _upsert_comment(ctx: Context, marker: str, body: str) -> None:
    full_body = f"{marker}\n{body}".strip()
    current = _find_comment_by_marker(ctx, marker)
    if current:
        _gh_api_json(
            "PATCH",
            f"repos/{ctx.repo}/issues/comments/{current['id']}",
            fields={"body": full_body},
        )
    else:
        _gh_api_json("POST", _issue_endpoint(ctx, "/comments"), fields={"body": full_body})


def _artifact_marker(name: str) -> str:
    return f"<!-- openhands-swarm:artifact:{name} -->"


def has_artifact(ctx: Context, name: str) -> bool:
    return _find_comment_by_marker(ctx, _artifact_marker(name)) is not None


def write_artifact(ctx: Context, name: str, body: str) -> None:
    _upsert_comment(ctx, _artifact_marker(name), body)


def read_artifact(ctx: Context, name: str) -> str | None:
    marker = _artifact_marker(name)
    comment = _find_comment_by_marker(ctx, marker)
    if not comment:
        return None
    body = comment.get("body", "")
    if body.startswith(marker):
        body = body[len(marker) :].lstrip()
    return body


def _fallback_artifact_content(payload: PromptPayload) -> str:
    return (
        "## Fallback Artifact\n"
        f"- Phase: `{payload.phase}`\n"
        f"- Artifact: `{payload.artifact_name}`\n\n"
        "OpenHands response was unavailable, so this deterministic fallback was generated."
    )


def _resolve_artifact_content(payload: PromptPayload, supplied_content: str | None = None) -> str:
    resolved = (supplied_content or os.environ.get("PHASE_ARTIFACT_CONTENT", "")).strip()
    if resolved:
        return resolved
    return _fallback_artifact_content(payload)


def report(ctx: Context, phase: str, status: str, detail: str) -> None:
    marker = f"<!-- openhands-swarm:report:{phase} -->"
    body = (
        f"## {phase} report\n"
        f"- Status: `{status}`\n"
        f"- Owner: `{ctx.owner}`\n"
        f"- Run: {ctx.run_url}\n\n"
        f"{detail}"
    )
    _upsert_comment(ctx, marker, body)


def add_labels(ctx: Context, labels: list[str]) -> None:
    if not labels:
        return
    _run(
        [
            "gh",
            "issue",
            "edit",
            str(ctx.issue_number),
            "--repo",
            ctx.repo,
            "--add-label",
            ",".join(labels),
        ]
    )


def remove_label(ctx: Context, label: str) -> None:
    _run(
        [
            "gh",
            "issue",
            "edit",
            str(ctx.issue_number),
            "--repo",
            ctx.repo,
            "--remove-label",
            label,
        ],
        check=False,
    )


def remove_labels(ctx: Context, labels: list[str]) -> None:
    for label in labels:
        remove_label(ctx, label)


def _parse_lock_owner(ctx: Context) -> str | None:
    lock_comment = _find_comment_by_marker(ctx, "<!-- openhands-swarm:lock -->")
    if not lock_comment:
        return None
    match = re.search(r"Owner:\s*`([^`]+)`", lock_comment.get("body", ""))
    return match.group(1) if match else None


def acquire_lock(ctx: Context) -> bool:
    add_labels(ctx, ["lock"])
    _upsert_comment(
        ctx,
        "<!-- openhands-swarm:lock -->",
        (
            "## Lock\n"
            f"- Owner: `{ctx.owner}`\n"
            f"- Run: {ctx.run_url}\n"
            "- State: held"
        ),
    )
    return True


def release_lock(ctx: Context) -> None:
    existing_owner = _parse_lock_owner(ctx)
    if existing_owner != ctx.owner:
        return
    remove_label(ctx, "lock")
    _upsert_comment(
        ctx,
        "<!-- openhands-swarm:lock -->",
        (
            "## Lock\n"
            f"- Owner: `{ctx.owner}`\n"
            f"- Run: {ctx.run_url}\n"
            "- State: released"
        ),
    )


def preflight(ctx: Context, expected_phase: str, *, require_unblocked: bool = False) -> tuple[bool, dict[str, Any], str]:
    issue = _get_issue(ctx)
    labels = _labels(issue)
    phases = _phase_labels(labels)

    if len(phases) != 1:
        add_labels(ctx, ["needs:human"])
        report(
            ctx,
            expected_phase,
            "halted",
            f"Single-phase invariant violated. Found phase labels: {sorted(phases)}",
        )
        return False, issue, "single-phase-invariant"

    current = next(iter(phases))
    if current != expected_phase:
        return False, issue, f"phase-mismatch:{current}"

    if "needs:human" in labels:
        report(ctx, expected_phase, "halted", "`needs:human` present; skipping automation.")
        return False, issue, "needs-human"

    if require_unblocked and "blocked" in labels:
        report(ctx, expected_phase, "halted", "`blocked` present; skipping automation.")
        return False, issue, "blocked"

    return True, issue, "ok"


def transition(ctx: Context, current: str, add: list[str], remove_extra: list[str] | None = None) -> None:
    remove_labels(ctx, [current, *(remove_extra or [])])
    add_labels(ctx, add)


def generate_prompt_payload(
    ctx: Context,
    command: str,
    *,
    issue: dict[str, Any] | None = None,
    persona: str = "",
) -> PromptPayload:
    if command not in COMMAND_PHASE_LABEL:
        raise ValueError(f"Unsupported prompt command {command}")

    issue_data = issue or _get_issue(ctx)
    issue_title = issue_data.get("title", "")
    issue_body = issue_data.get("body", "")

    if command == "queen":
        artifact_name = COMMAND_ARTIFACT[command]
        prompt = build_queen_prompt(issue_title, issue_body)
    elif command == "triad-persona":
        if persona not in PERSONAS:
            raise ValueError(f"Unsupported persona {persona}")
        artifact_name = f"triad:{persona}"
        prompt = build_triad_persona_prompt(persona, issue_title, issue_body, read_artifact(ctx, "queen:structured"))
    elif command == "triad-aggregate":
        artifact_name = COMMAND_ARTIFACT[command]
        prompt = build_triad_aggregate_prompt(
            issue_title,
            issue_body,
            read_artifact(ctx, "triad:advocate"),
            read_artifact(ctx, "triad:pragmatist"),
            read_artifact(ctx, "triad:skeptic"),
        )
    elif command == "arbiter":
        artifact_name = COMMAND_ARTIFACT[command]
        prompt = build_arbiter_prompt(issue_title, issue_body, read_artifact(ctx, "triad:personas"))
    elif command == "contract":
        artifact_name = COMMAND_ARTIFACT[command]
        prompt = build_contract_prompt(issue_title, issue_body)
    elif command == "spec":
        artifact_name = COMMAND_ARTIFACT[command]
        prompt = build_spec_prompt(issue_title, issue_body, read_artifact(ctx, "contract:bdd"))
    elif command == "pseudo":
        artifact_name = COMMAND_ARTIFACT[command]
        prompt = build_pseudo_prompt(issue_title, issue_body, read_artifact(ctx, "spec:mapping"))
    elif command == "arch":
        artifact_name = COMMAND_ARTIFACT[command]
        prompt = build_arch_prompt(issue_title, issue_body, read_artifact(ctx, "pseudo:flows"))
    elif command == "refine":
        artifact_name = COMMAND_ARTIFACT[command]
        prompt = build_refine_prompt(
            issue_title,
            issue_body,
            read_artifact(ctx, "arch:plan"),
            read_artifact(ctx, "contract:bdd"),
        )
    else:
        artifact_name = COMMAND_ARTIFACT[command]
        prompt = build_completion_prompt(issue_title, issue_body, read_artifact(ctx, "refine:aligned"))

    return PromptPayload(phase=COMMAND_PHASE_LABEL[command], artifact_name=artifact_name, prompt=prompt)


def queen(ctx: Context, artifact_content: str | None = None) -> int:
    ok, issue, _ = preflight(ctx, "phase:queen")
    if not ok:
        return 0
    if not acquire_lock(ctx):
        report(ctx, "phase:queen", "skipped", "Could not acquire `lock`.")
        return 0

    try:
        body = issue.get("body", "")
        has_open_questions = "- [ ]" in body or "OPEN QUESTION" in body.upper()
        payload = generate_prompt_payload(ctx, "queen", issue=issue)
        write_artifact(ctx, payload.artifact_name, _resolve_artifact_content(payload, artifact_content))
        if has_open_questions:
            transition(ctx, "phase:queen", ["needs:human"])
            report(ctx, "phase:queen", "needs-human", "Open questions detected; waiting for human input.")
        else:
            transition(ctx, "phase:queen", ["phase:triad"])
            report(ctx, "phase:queen", "completed", "Structured epic created; transitioned to `phase:triad`.")
    finally:
        release_lock(ctx)
    return 0


def triad_persona(ctx: Context, persona: str, artifact_content: str | None = None) -> int:
    if persona not in PERSONAS:
        raise ValueError(f"Unsupported persona {persona}")
    ok, _, _ = preflight(ctx, "phase:triad")
    if not ok:
        return 0
    if not has_artifact(ctx, "queen:structured"):
        report(ctx, "phase:triad", "halted", "Missing `queen:structured`; cannot run persona analysis.")
        return 1

    payload = generate_prompt_payload(ctx, "triad-persona", persona=persona)
    write_artifact(ctx, payload.artifact_name, _resolve_artifact_content(payload, artifact_content))
    report(ctx, "phase:triad", "in-progress", f"Persona `{persona}` analysis refreshed.")
    return 0


def triad_aggregate(ctx: Context, persona_failure: bool, artifact_content: str | None = None) -> int:
    ok, _, _ = preflight(ctx, "phase:triad")
    if not ok:
        return 0
    if not acquire_lock(ctx):
        report(ctx, "phase:triad", "skipped", "Could not acquire `lock` for aggregation.")
        return 0

    try:
        missing = [p for p in PERSONAS if not has_artifact(ctx, f"triad:{p}")]
        if persona_failure or missing:
            add_labels(ctx, ["blocked"])
            report(
                ctx,
                "phase:triad",
                "blocked",
                f"Triad persona failure detected. Missing artifacts: {missing}",
            )
            return 0

        payload = generate_prompt_payload(ctx, "triad-aggregate")
        write_artifact(ctx, payload.artifact_name, _resolve_artifact_content(payload, artifact_content))
        transition(ctx, "phase:triad", ["phase:arbiter"])
        report(ctx, "phase:triad", "completed", "Triad aggregate complete; moved to `phase:arbiter`.")
    finally:
        release_lock(ctx)
    return 0


def arbiter(ctx: Context, artifact_content: str | None = None) -> int:
    ok, issue, _ = preflight(ctx, "phase:arbiter")
    if not ok:
        return 0
    if not acquire_lock(ctx):
        report(ctx, "phase:arbiter", "skipped", "Could not acquire `lock`.")
        return 0

    try:
        if not has_artifact(ctx, "triad:personas"):
            add_labels(ctx, ["blocked"])
            report(ctx, "phase:arbiter", "blocked", "Missing triad aggregate artifact.")
            return 0

        title = issue.get("title", "Epic")
        story_titles = [
            f"[Story] {title} - Slice A",
            f"[Story] {title} - Slice B",
            f"[Story] {title} - Slice C",
        ]

        created_links: list[str] = []
        for story_title in story_titles:
            payload = {
                "title": story_title,
                "body": (
                    f"Parent Epic: #{ctx.issue_number}\n\n"
                    "Story narrative and constraints go here."
                ),
                "labels[]": "phase:contract",
            }
            created = _gh_api_json("POST", f"repos/{ctx.repo}/issues", fields=payload)
            created_links.append(created.get("html_url", ""))

        payload = generate_prompt_payload(ctx, "arbiter", issue=issue)
        generated = _resolve_artifact_content(payload, artifact_content)
        if generated == _fallback_artifact_content(payload):
            generated = "## Prioritized Story Index\n" + "\n".join(f"- {link}" for link in created_links)
        write_artifact(ctx, payload.artifact_name, generated)
        transition(ctx, "phase:arbiter", ["epic:ready"])
        report(ctx, "phase:arbiter", "completed", "Child stories created and epic marked `epic:ready`.")
    finally:
        release_lock(ctx)
    return 0


def contract(ctx: Context, artifact_content: str | None = None) -> int:
    ok, issue, _ = preflight(ctx, "phase:contract")
    if not ok:
        return 0
    if not acquire_lock(ctx):
        report(ctx, "phase:contract", "skipped", "Could not acquire `lock`.")
        return 0

    try:
        remove_labels(ctx, ["restart:contract", "restart:spec", "restart:pseudo", "restart:arch"])
        body = issue.get("body", "")
        ambiguity = "TODO" in body or "TBD" in body
        payload = generate_prompt_payload(ctx, "contract", issue=issue)
        write_artifact(ctx, payload.artifact_name, _resolve_artifact_content(payload, artifact_content))
        if ambiguity:
            add_labels(ctx, ["needs:human"])
            report(ctx, "phase:contract", "needs-human", "Ambiguity detected (TODO/TBD remains).")
        else:
            transition(ctx, "phase:contract", ["sparc:spec"])
            report(ctx, "phase:contract", "completed", "BDD contract present; moved to `sparc:spec`.")
    finally:
        release_lock(ctx)
    return 0


def spec(ctx: Context, artifact_content: str | None = None) -> int:
    ok, issue, _ = preflight(ctx, "sparc:spec")
    if not ok:
        return 0
    if not acquire_lock(ctx):
        report(ctx, "sparc:spec", "skipped", "Could not acquire `lock`.")
        return 0

    try:
        if not has_artifact(ctx, "contract:bdd"):
            add_labels(ctx, ["needs:human"])
            report(ctx, "sparc:spec", "needs-human", "Missing `contract:bdd` artifact.")
            return 0

        if "[contract-flawed]" in issue.get("body", ""):
            transition(ctx, "sparc:spec", ["restart:contract", "needs:human"])
            report(ctx, "sparc:spec", "restart", "Contract flaw marker detected; restart requested.")
            return 0

        payload = generate_prompt_payload(ctx, "spec", issue=issue)
        write_artifact(ctx, payload.artifact_name, _resolve_artifact_content(payload, artifact_content))
        transition(ctx, "sparc:spec", ["sparc:pseudo"])
        report(ctx, "sparc:spec", "completed", "Spec mapping complete; moved to `sparc:pseudo`.")
    finally:
        release_lock(ctx)
    return 0


def pseudo(ctx: Context, artifact_content: str | None = None) -> int:
    ok, issue, _ = preflight(ctx, "sparc:pseudo")
    if not ok:
        return 0
    if not acquire_lock(ctx):
        report(ctx, "sparc:pseudo", "skipped", "Could not acquire `lock`.")
        return 0

    try:
        if not has_artifact(ctx, "spec:mapping"):
            add_labels(ctx, ["needs:human"])
            report(ctx, "sparc:pseudo", "needs-human", "Missing `spec:mapping` artifact.")
            return 0

        if "[mapping-insufficient]" in issue.get("body", ""):
            transition(ctx, "sparc:pseudo", ["restart:spec"])
            report(ctx, "sparc:pseudo", "restart", "Mapping insufficiency marker detected.")
            return 0

        payload = generate_prompt_payload(ctx, "pseudo", issue=issue)
        write_artifact(ctx, payload.artifact_name, _resolve_artifact_content(payload, artifact_content))
        transition(ctx, "sparc:pseudo", ["sparc:arch"])
        report(ctx, "sparc:pseudo", "completed", "Pseudocode complete; moved to `sparc:arch`.")
    finally:
        release_lock(ctx)
    return 0


def arch(ctx: Context, artifact_content: str | None = None) -> int:
    ok, issue, _ = preflight(ctx, "sparc:arch")
    if not ok:
        return 0
    if not acquire_lock(ctx):
        report(ctx, "sparc:arch", "skipped", "Could not acquire `lock`.")
        return 0

    try:
        if not has_artifact(ctx, "pseudo:flows"):
            add_labels(ctx, ["needs:human"])
            report(ctx, "sparc:arch", "needs-human", "Missing `pseudo:flows` artifact.")
            return 0

        if "[scope-change]" in issue.get("body", ""):
            transition(ctx, "sparc:arch", ["restart:contract", "needs:human"])
            report(ctx, "sparc:arch", "restart", "Scope-change marker detected.")
            return 0

        payload = generate_prompt_payload(ctx, "arch", issue=issue)
        write_artifact(ctx, payload.artifact_name, _resolve_artifact_content(payload, artifact_content))
        transition(ctx, "sparc:arch", ["sparc:refine"])
        report(ctx, "sparc:arch", "completed", "Architecture plan complete; moved to `sparc:refine`.")
    finally:
        release_lock(ctx)
    return 0


def _collect_scenarios(ctx: Context) -> list[str]:
    comment = _find_comment_by_marker(ctx, _artifact_marker("contract:bdd"))
    if not comment:
        return []
    scenarios = re.findall(r"^###\s+Scenario:\s+(.+)$", comment.get("body", ""), flags=re.MULTILINE)
    return [scenario.strip() for scenario in scenarios]


def _traceability_matrix(scenarios: list[str]) -> tuple[str, bool]:
    test_files = list(Path("tests").glob("test_*.py"))
    test_content = {path.name: path.read_text(encoding="utf-8") for path in test_files if path.is_file()}
    lines = ["| BDD Scenario | Test(s) |", "|---|---|"]
    complete = True
    for scenario in scenarios:
        tokens = [token.lower() for token in re.findall(r"[A-Za-z0-9_]+", scenario) if len(token) > 3]
        matched = []
        for test_name, content in test_content.items():
            lowered = content.lower()
            if tokens and any(token in lowered for token in tokens):
                matched.append(test_name)
        if not matched:
            complete = False
            lines.append(f"| {scenario} | _none_ |")
        else:
            lines.append(f"| {scenario} | {', '.join(sorted(set(matched)))} |")
    if not scenarios:
        complete = False
        lines.append("| _none found_ | _none_ |")
    return "\n".join(lines), complete


def refine(ctx: Context, artifact_content: str | None = None) -> int:
    ok, issue, _ = preflight(ctx, "sparc:refine")
    if not ok:
        return 0
    if not acquire_lock(ctx):
        report(ctx, "sparc:refine", "skipped", "Could not acquire `lock`.")
        return 0

    try:
        if not has_artifact(ctx, "arch:plan"):
            add_labels(ctx, ["needs:human"])
            report(ctx, "sparc:refine", "needs-human", "Missing `arch:plan` artifact.")
            return 0

        semantic_change_required = (
            "restart:contract" in _labels(_get_issue(ctx))
            or "[semantic-change-required]" in issue.get("body", "")
        )
        if semantic_change_required:
            transition(ctx, "sparc:refine", ["restart:contract", "needs:human"])
            report(ctx, "sparc:refine", "restart", "Semantic contract change required.")
            return 0

        pytest_run = _run([sys.executable, "-m", "pytest"], check=False)
        tests_green = pytest_run.returncode == 0
        scenarios = _collect_scenarios(ctx)
        matrix, traceability_complete = _traceability_matrix(scenarios)
        conformance_aligned = tests_green and traceability_complete

        payload = generate_prompt_payload(ctx, "refine", issue=issue)
        generated = _resolve_artifact_content(payload, artifact_content)
        if generated == _fallback_artifact_content(payload):
            generated = (
                "## Traceability Report\n"
                f"- Tests green: `{tests_green}`\n"
                f"- Conformance aligned: `{conformance_aligned}`\n\n"
                f"{matrix}\n\n"
                "### Verification Evidence\n"
                "```text\n"
                f"{pytest_run.stdout[-4000:]}\n{pytest_run.stderr[-1000:]}"
                "\n```"
            )
        write_artifact(ctx, payload.artifact_name, generated)

        if conformance_aligned:
            write_artifact(ctx, "refine:aligned", "Refine checks are green and aligned.")
            transition(ctx, "sparc:refine", ["sparc:done"])
            report(ctx, "sparc:refine", "completed", "Refine checks passed; moved to `sparc:done`.")
        else:
            report(
                ctx,
                "sparc:refine",
                "retry",
                "Fixable verification failures detected; staying in `sparc:refine` for rerun.",
            )
    finally:
        release_lock(ctx)
    return 0


def _find_existing_pr_url(ctx: Context) -> str | None:
    query = quote_plus(f"repo:{ctx.repo} is:pr \"#{ctx.issue_number}\" in:body")
    data = _gh_api_json("GET", f"search/issues?q={query}&per_page=1")
    items = data.get("items", []) if data else []
    if not items:
        return None
    return items[0].get("html_url")


def _create_pr(ctx: Context) -> str | None:
    repo_data = _gh_api_json("GET", f"repos/{ctx.repo}")
    default_branch = repo_data.get("default_branch", "main")
    head_branch = f"story/{ctx.issue_number}"

    branch_check = _run(["git", "ls-remote", "--heads", "origin", head_branch], check=False)
    if not branch_check.stdout.strip():
        return None

    body = (
        f"Implements story #{ctx.issue_number}.\n\n"
        "## Acceptance Evidence\n"
        "- See linked phase artifacts and traceability report in issue comments."
    )
    result = _run(
        [
            "gh",
            "pr",
            "create",
            "--repo",
            ctx.repo,
            "--base",
            default_branch,
            "--head",
            head_branch,
            "--title",
            f"Story #{ctx.issue_number}: completion package",
            "--body",
            body,
            "--draft",
        ],
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip().splitlines()[-1].strip()


def completion(ctx: Context, artifact_content: str | None = None) -> int:
    ok, _, _ = preflight(ctx, "sparc:done", require_unblocked=True)
    if not ok:
        return 0
    if not acquire_lock(ctx):
        report(ctx, "sparc:done", "skipped", "Could not acquire `lock`.")
        return 0

    try:
        if not has_artifact(ctx, "refine:aligned"):
            add_labels(ctx, ["needs:human"])
            report(ctx, "sparc:done", "needs-human", "Missing `refine:aligned` artifact.")
            return 0

        pr_url = _find_existing_pr_url(ctx) or _create_pr(ctx)
        if not pr_url:
            add_labels(ctx, ["needs:human"])
            report(
                ctx,
                "sparc:done",
                "needs-human",
                "Unable to create PR automatically (expected branch `story/<issue-number>`).",
            )
            return 0

        payload = generate_prompt_payload(ctx, "completion")
        generated = _resolve_artifact_content(payload, artifact_content)
        if generated == _fallback_artifact_content(payload):
            generated = f"PR: {pr_url}"
        write_artifact(ctx, payload.artifact_name, generated)
        _gh_api_json(
            "POST",
            _issue_endpoint(ctx, "/comments"),
            fields={"body": f"Completion packaging ready: {pr_url}"},
        )
        transition(ctx, "sparc:done", ["sparc:completed"])
        report(ctx, "sparc:done", "completed", f"PR linked and issue transitioned to `sparc:completed`: {pr_url}")
    finally:
        release_lock(ctx)
    return 0


def emit_prompt(ctx: Context, command: str, *, persona: str = "") -> int:
    payload = generate_prompt_payload(ctx, command, persona=persona)
    print(
        json.dumps(
            {
                "phase": payload.phase,
                "artifact_name": payload.artifact_name,
                "prompt": payload.prompt,
            }
        )
    )
    return 0


def finalize_phase(
    ctx: Context,
    command: str,
    *,
    persona: str = "",
    persona_failure: bool = False,
    artifact_content: str | None = None,
) -> int:
    dispatch = {
        "queen": lambda: queen(ctx, artifact_content=artifact_content),
        "triad-persona": lambda: triad_persona(ctx, persona, artifact_content=artifact_content),
        "triad-aggregate": lambda: triad_aggregate(
            ctx,
            persona_failure,
            artifact_content=artifact_content,
        ),
        "arbiter": lambda: arbiter(ctx, artifact_content=artifact_content),
        "contract": lambda: contract(ctx, artifact_content=artifact_content),
        "spec": lambda: spec(ctx, artifact_content=artifact_content),
        "pseudo": lambda: pseudo(ctx, artifact_content=artifact_content),
        "arch": lambda: arch(ctx, artifact_content=artifact_content),
        "refine": lambda: refine(ctx, artifact_content=artifact_content),
        "completion": lambda: completion(ctx, artifact_content=artifact_content),
    }
    if command not in dispatch:
        raise ValueError(f"Unknown finalize phase {command}")
    return dispatch[command]()


def _read_content_file(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OpenHands Swarm phase runner")
    parser.add_argument("command")
    parser.add_argument("--phase", default="")
    parser.add_argument("--persona", default="")
    parser.add_argument("--persona-failure", choices=["true", "false"], default="false")
    parser.add_argument("--artifact-content", default="")
    parser.add_argument("--artifact-content-file", default="")
    return parser.parse_args()


def build_context() -> Context:
    repo = os.environ["GITHUB_REPOSITORY"]
    issue_number = int(os.environ.get("ISSUE_NUMBER", "0"))
    if issue_number <= 0:
        raise ValueError("ISSUE_NUMBER must be set")
    run_id = os.environ.get("GITHUB_RUN_ID", "local")
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    run_url = f"{server}/{repo}/actions/runs/{run_id}"
    owner = f"run-{run_id}"
    return Context(repo=repo, issue_number=issue_number, owner=owner, run_url=run_url)


def main() -> int:
    args = parse_args()
    ctx = build_context()

    artifact_content = args.artifact_content
    if args.artifact_content_file:
        artifact_content = _read_content_file(args.artifact_content_file)

    if args.command == "prompt":
        if not args.phase:
            raise ValueError("--phase is required for `prompt`")
        return emit_prompt(ctx, args.phase, persona=args.persona)

    if args.command == "finalize":
        if not args.phase:
            raise ValueError("--phase is required for `finalize`")
        return finalize_phase(
            ctx,
            args.phase,
            persona=args.persona,
            persona_failure=args.persona_failure == "true",
            artifact_content=artifact_content,
        )

    dispatch = {
        "queen": lambda: finalize_phase(ctx, "queen", artifact_content=artifact_content),
        "triad-persona": lambda: finalize_phase(
            ctx,
            "triad-persona",
            persona=args.persona,
            artifact_content=artifact_content,
        ),
        "triad-aggregate": lambda: finalize_phase(
            ctx,
            "triad-aggregate",
            persona_failure=args.persona_failure == "true",
            artifact_content=artifact_content,
        ),
        "arbiter": lambda: finalize_phase(ctx, "arbiter", artifact_content=artifact_content),
        "contract": lambda: finalize_phase(ctx, "contract", artifact_content=artifact_content),
        "spec": lambda: finalize_phase(ctx, "spec", artifact_content=artifact_content),
        "pseudo": lambda: finalize_phase(ctx, "pseudo", artifact_content=artifact_content),
        "arch": lambda: finalize_phase(ctx, "arch", artifact_content=artifact_content),
        "refine": lambda: finalize_phase(ctx, "refine", artifact_content=artifact_content),
        "completion": lambda: finalize_phase(ctx, "completion", artifact_content=artifact_content),
    }
    if args.command not in dispatch:
        raise ValueError(f"Unknown command {args.command}")
    return dispatch[args.command]()


if __name__ == "__main__":
    raise SystemExit(main())
