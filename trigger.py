#!/usr/bin/env python3
"""
GitHub Label -> Phase Router

Workflow:
- Phases 1-3: ask OpenHands for the phase response, then post that response as a
  GitHub issue comment.
- Phase 4: ask OpenHands for a JSON payload containing a parent comment and one
  or more child issues, post the comment, then create the child issues.
- Phases 5-9: run OpenHands headlessly for implementation/validation work.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

WORKSPACE = Path(__file__).parent
MICROAGENTS_DIR = WORKSPACE / ".openhands" / "microagents"
DEFAULT_REPO = "fedevela/particle-life-3d"
SESSION_STATE_PATH = WORKSPACE / "workspace" / ".session-state.json"
PHASE_DISPLAY_NAME_MAP = {
    1: "Keter",
    2: "Chokhmah/Binah/Chesed",
    3: "Gevurah",
    4: "Tiferet",
    5: "Netzach",
    6: "Hod",
    7: "Yesod-Orchestration",
    8: "Yesod-Embodiment",
    9: "Malkhut",
}
NEXT_LABEL_MAP = {
    "phase:keter": "phase:chokhmah",
    "phase:chokhmah": "phase:binah",
    "phase:binah": "phase:chesed",
    "phase:chesed": "phase:gevurah",
    "phase:gevurah": "phase:tiferet",
}
PHASE_LABELS = tuple(NEXT_LABEL_MAP.keys()) + (
    "phase:tiferet",
    "phase:netzach",
    "phase:hod",
    "phase:yesod-orchestration",
    "phase:yesod-embodiment",
    "phase:malkhut",
)


def trigger_agent(label: Optional[str] = None, issue: Optional[int] = None, repo: Optional[str] = None) -> None:
    """Route the label to the correct phase workflow."""
    repo = repo or DEFAULT_REPO
    if label is None:
        issue, label = resolve_oldest_phased_issue(repo)

    phase = determine_phase_from_label(label)
    if not phase:
        print(f"Unknown label '{label}'. Cannot determine phase.")
        sys.exit(1)

    if issue is None:
        issue = resolve_issue_by_label(repo, label)

    print(f"Triggering phase {phase} for label '{label}' on {repo}#{issue}")

    microagent_content = read_microagent_for_label(label, phase)
    if not microagent_content:
        print("No microagent found for this label.")
        sys.exit(1)

    issue_data = fetch_issue_data(repo, issue)
    if not issue_data:
        print(f"Could not fetch issue #{issue} from {repo}.")
        sys.exit(1)
    if not issue_has_label(issue_data, label):
        print(f"Issue #{issue} in {repo} is not labeled '{label}'. Skipping phase execution.")
        sys.exit(1)

    if phase <= 3:
        prompt = build_discussion_prompt(label, issue, repo, microagent_content, phase, issue_data)
        comment = run_openhands_for_comment(prompt, repo=repo, issue=issue)
        post_issue_comment(repo, issue, format_phase_comment(phase, label, comment))
        advance_issue_label(repo, issue, label)
        return

    if phase == 4:
        prompt = build_spec_prompt(label, issue, repo, microagent_content, phase, issue_data)
        payload = run_openhands_for_json(prompt, repo=repo, issue=issue)
        validate_phase_four_payload(payload)
        post_issue_comment(repo, issue, format_phase_comment(phase, label, payload["comment"].strip()))
        created = create_child_issues(repo, issue, payload["sub_issues"])
        post_issue_comment(repo, issue, format_phase_comment(phase, label, build_phase_four_summary(created)))
        return

    prompt = build_agent_prompt(label, issue, repo, microagent_content, phase, issue_data)
    run_openhands_task(prompt, repo=repo, issue=issue)


def fetch_issue_data(repo: str, issue_number: int) -> dict[str, Any]:
    """Fetch issue title and body from GitHub."""
    result = run_gh(
        ["issue", "view", str(issue_number), "--repo", repo, "--json", "title,body,number,labels,comments"],
        capture_output=True,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        details = stderr or stdout or "gh returned no output"
        raise SystemExit(f"Failed to fetch issue #{issue_number} from {repo}: {details}")
    if not result.stdout:
        raise SystemExit(f"Failed to fetch issue #{issue_number} from {repo}: gh returned empty output.")
    return json.loads(result.stdout)


def resolve_issue_by_label(repo: str, label: str) -> int:
    """Resolve a single open issue by label."""
    result = run_gh(
        ["issue", "list", "--repo", repo, "--label", label, "--state", "open", "--json", "number,title"],
        capture_output=True,
    )
    if result.returncode != 0 or not result.stdout:
        raise SystemExit(f"Could not query open issues labeled '{label}' in {repo}.")

    issues = json.loads(result.stdout)
    if not isinstance(issues, list) or not issues:
        raise SystemExit(f"No open issues labeled '{label}' found in {repo}.")
    if len(issues) > 1:
        issue_refs = ", ".join(f"#{item['number']}" for item in issues if isinstance(item, dict) and "number" in item)
        raise SystemExit(
            f"Multiple open issues labeled '{label}' found in {repo}: {issue_refs}. "
            "Pass --issue to select one."
        )

    issue = issues[0]
    if not isinstance(issue, dict) or "number" not in issue:
        raise SystemExit(f"Invalid issue payload while resolving label '{label}' in {repo}.")
    return int(issue["number"])


def issue_has_label(issue_data: dict[str, Any], label: str) -> bool:
    """Return True when the issue currently carries the requested label."""
    labels = issue_data.get("labels") or []
    return any(item.get("name") == label for item in labels if isinstance(item, dict))


def issue_phase_labels(issue_data: dict[str, Any]) -> list[str]:
    """Return known phase labels attached to an issue."""
    labels = issue_data.get("labels") or []
    return [
        item["name"]
        for item in labels
        if isinstance(item, dict) and item.get("name") in PHASE_LABELS
    ]


def extract_phase_1_comment(issue_data: dict[str, Any]) -> Optional[str]:
    """Extract the Phase 1 comment body from issue comments."""
    # The comment data should be embedded in issue_data when fetched with --comments
    # If not present, return None and adjust fetch_issue_data call accordingly
    comments = issue_data.get("comments") or []
    for comment in comments:
        if not isinstance(comment, dict):
            continue
        body = comment.get("body", "")
        if not body:
            continue
        # Check for Phase 1 comment marker
        if "<!-- phase:1:start" in body:
            # Extract content between markers
            start_marker = f"<!-- phase:1:start"
            end_marker = "<!-- phase:1:end"
            if start_marker in body and end_marker in body:
                start_idx = body.find(start_marker)
                end_idx = body.find(end_marker, start_idx)
                if end_idx > start_idx:
                    content = body[start_idx:end_idx]
                    # Extract just the content after the ### Phase 1: Keter header
                    lines = content.split("\n")
                    for i, line in enumerate(lines):
                        if line.startswith("### Phase 1:"):
                            # Return everything after this header and blank line
                            return "\n".join(lines[i + 2:]).strip() if i + 2 < len(lines) else ""
                    return content
    return None


def resolve_oldest_phased_issue(repo: str) -> tuple[int, str]:
    """Resolve the oldest open issue carrying exactly one known phase label."""
    result = run_gh(
        ["issue", "list", "--repo", repo, "--state", "open", "--json", "number,title,createdAt,labels"],
        capture_output=True,
    )
    if result.returncode != 0 or not result.stdout:
        raise SystemExit(f"Could not query open issues in {repo}.")

    issues = json.loads(result.stdout)
    if not isinstance(issues, list):
        raise SystemExit(f"Invalid issue list payload for {repo}.")

    phased_issues: list[dict[str, Any]] = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        labels = issue_phase_labels(issue)
        if labels:
            phased_issues.append(issue)

    if not phased_issues:
        raise SystemExit(f"No open issues with a phase label found in {repo}.")

    phased_issues.sort(key=lambda item: item.get("createdAt", ""))
    selected = phased_issues[0]
    labels = issue_phase_labels(selected)
    if len(labels) != 1:
        issue_number = selected.get("number", "?")
        raise SystemExit(
            f"Issue #{issue_number} in {repo} has multiple phase labels: {', '.join(labels)}. "
            "Pass --label and --issue explicitly."
        )

    return int(selected["number"]), labels[0]


def determine_phase_from_label(label: str) -> Optional[int]:
    """Determine phase number from label."""
    label_phase_map = {
        "phase:keter": 1,
        "phase:chokhmah": 2,
        "phase:binah": 2,
        "phase:chesed": 2,
        "phase:gevurah": 3,
        "phase:tiferet": 4,
        "phase:netzach": 5,
        "phase:hod": 6,
        "phase:yesod-orchestration": 7,
        "phase:yesod-embodiment": 8,
        "phase:malkhut": 9,
    }
    return label_phase_map.get(label)


def read_microagent_for_label(label: str, phase: Optional[int]) -> Optional[str]:
    """Read the microagent prompt for a given label."""
    if phase:
        pattern = f"phase_{phase:02d}*.md"
        microagent_files = list(MICROAGENTS_DIR.glob(pattern))
        if microagent_files:
            return microagent_files[0].read_text()

    label_name = label.replace("phase:", "")
    for md_file in MICROAGENTS_DIR.glob("*.md"):
        content = md_file.read_text()
        if label_name in content.lower():
            return content

    return None


def build_runtime_context(
    label: str,
    issue: int,
    repo: str,
    phase: int,
    issue_data: dict[str, Any],
) -> str:
    """Build shared runtime context for prompts."""
    title = issue_data.get("title", "Untitled")
    body = issue_data.get("body", "").strip()
    return f"""## Runtime Context
- Repository: {repo}
- Trigger label: {label}
- Issue number: #{issue}
- Phase: {phase}

## Issue Content

**Title:** {title}

**Body:**
{body}
"""


def strip_microagent(microagent: str) -> str:
    """Normalize the microagent content before embedding."""
    microagent_stripped = microagent.strip()
    if microagent_stripped.endswith("EOF"):
        microagent_stripped = microagent_stripped[:-3].strip()
    return microagent_stripped


def build_discussion_prompt(
    label: str,
    issue: int,
    repo: str,
    microagent: str,
    phase: int,
    issue_data: dict[str, Any],
) -> str:
    """Build a prompt for phases 1-3 that returns only a comment body."""
    requirements = [
        "- Be concise and authoritative.",
        "- Do not mention tool limitations, environment limitations, or inability to post.",
        "- Do not describe yourself as unable to act.",
        "- Do not wrap the answer in code fences.",
        "- Keep the content appropriate for a single GitHub issue comment.",
    ]

    if phase == 1:
        requirements.extend(
            [
                "- Produce a comprehensive clarification comment, not an ACK.",
                "- Start with a short statement that the requirement has been clarified.",
                "- Include these exact section headings: `Clarified Requirement`, `Constraints and Invariants`, `Acceptance Signals`, and `Phase 2 Handoff`.",
                "- `Clarified Requirement` must describe the feature behavior in one coherent paragraph.",
                "- `Constraints and Invariants` must be a flat bullet list covering preserved behavior, determinism/seed expectations, UI placement, and boundary behavior when applicable.",
                "- `Acceptance Signals` must be a flat bullet list of observable outcomes a reviewer can verify.",
                "- `Phase 2 Handoff` must state that generative expansion can proceed.",
            ]
        )
    elif phase == 2:
        # For Phase 2 agents, include Phase 1 comment as their input context
        phase_1_comment = extract_phase_1_comment(issue_data)
        if phase_1_comment:
            requirements.insert(
                0,
                f"## Phase 1 Input (do not repeat or re-post this content, use it as context for your response)\n\n{phase_1_comment}\n---",
            )

    return f"""{strip_microagent(microagent)}

{build_runtime_context(label, issue, repo, phase, issue_data)}

Return only the GitHub comment body for this phase.

Requirements:
{chr(10).join(requirements)}
"""


def build_spec_prompt(
    label: str,
    issue: int,
    repo: str,
    microagent: str,
    phase: int,
    issue_data: dict[str, Any],
) -> str:
    """Build a prompt for phase 4 that returns JSON for the parent comment and child issues."""
    return f"""{strip_microagent(microagent)}

{build_runtime_context(label, issue, repo, phase, issue_data)}

Return valid JSON only. No markdown fences. No explanation outside JSON.

Use this exact schema:
{{
  "comment": "GitHub comment body for the parent issue",
  "sub_issues": [
    {{
      "title": "Short actionable issue title",
      "body": "Gherkin-oriented child issue body with Given/When/Then scenarios"
    }}
  ]
}}

Requirements:
- `comment` must summarize the specification and explain that child issues were spawned.
- `sub_issues` must contain one or more items.
- Each child issue body must use Gherkin language with explicit `Given`, `When`, and `Then` sections.
- Do not mention tool limitations, environment limitations, or inability to post.
"""


def build_agent_prompt(
    label: str,
    issue: int,
    repo: str,
    microagent: str,
    phase: int,
    issue_data: dict[str, Any],
) -> str:
    """Build the prompt for phases 5-9."""
    return f"""{strip_microagent(microagent)}

{build_runtime_context(label, issue, repo, phase, issue_data)}

Execute your phase logic now.
"""


def openhands_env() -> dict[str, str]:
    """Build subprocess env for headless OpenHands runs."""
    conversations_dir = WORKSPACE / ".openhands" / "conversations"
    conversations_dir.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    env["OPENHANDS_CONVERSATIONS_DIR"] = str(conversations_dir)
    env["OPENHANDS_DISABLE_UPDATE_CHECK"] = "1"

    if env.get("DASHSCOPE_API_KEY") and not env.get("LLM_API_KEY"):
        env["LLM_API_KEY"] = env["DASHSCOPE_API_KEY"]
    if env.get("DASHSCOPE_API_BASE") and not env.get("LLM_BASE_URL"):
        env["LLM_BASE_URL"] = env["DASHSCOPE_API_BASE"]
    if env.get("DASHSCOPE_API_KEY") and not env.get("LLM_MODEL"):
        env["LLM_MODEL"] = "dashscope/qwen3-coder-plus"

    return env


def session_key(repo: str, issue: int) -> str:
    """Build a stable key for issue-scoped OpenHands sessions."""
    return f"{repo}#{issue}"


def load_session_state() -> dict[str, str]:
    """Load persisted issue -> conversation id mappings."""
    if not SESSION_STATE_PATH.exists():
        return {}
    try:
        return json.loads(SESSION_STATE_PATH.read_text())
    except json.JSONDecodeError:
        return {}


def save_session_state(state: dict[str, str]) -> None:
    """Persist issue -> conversation id mappings."""
    SESSION_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SESSION_STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True))


def extract_conversation_id(output: str) -> str:
    """Extract the conversation id from OpenHands output."""
    marker = "Conversation ID:"
    for line in output.splitlines():
        if marker in line:
            return line.split(marker, 1)[1].strip()
    return ""


def run_openhands(prompt: str, *, repo: str, issue: int) -> subprocess.CompletedProcess[str]:
    """Run OpenHands headlessly and capture output."""
    state = load_session_state()
    conversation_id = state.get(session_key(repo, issue), "")

    command = ["openhands"]
    if conversation_id:
        command.extend(["--resume", conversation_id])
    command.extend(
        [
            "--task",
            prompt,
            "--headless",
            "--json",
            "--override-with-envs",
            "--exit-without-confirmation",
        ]
    )

    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
        timeout=600,
        env=openhands_env(),
    )
    new_conversation_id = extract_conversation_id(result.stdout)
    if new_conversation_id:
        state[session_key(repo, issue)] = new_conversation_id
        save_session_state(state)
    return result


def extract_message_events(output: str) -> list[dict[str, Any]]:
    """Extract JSON event payloads from OpenHands stdout."""
    events: list[dict[str, Any]] = []
    marker = "--JSON Event--"
    decoder = json.JSONDecoder()
    cursor = 0

    while True:
        marker_index = output.find(marker, cursor)
        if marker_index == -1:
            break

        search_index = marker_index + len(marker)
        brace_index = output.find("{", search_index)
        if brace_index == -1:
            break

        try:
            event, consumed = decoder.raw_decode(output[brace_index:])
        except json.JSONDecodeError:
            cursor = search_index
            continue

        if isinstance(event, dict):
            events.append(event)
        cursor = brace_index + consumed

    return events


def last_assistant_message(output: str) -> str:
    """Return the last assistant message text from OpenHands JSON events."""
    message = ""
    for event in extract_message_events(output):
        if event.get("kind") != "MessageEvent":
            continue
        llm_message = event.get("llm_message") or {}
        if llm_message.get("role") != "assistant":
            continue
        content = llm_message.get("content") or []
        chunks = [item.get("text", "") for item in content if isinstance(item, dict)]
        if chunks:
            message = "".join(chunks).strip()
    return message


def run_openhands_for_comment(prompt: str, *, repo: str, issue: int) -> str:
    """Run OpenHands and return the assistant reply text."""
    result = run_openhands(prompt, repo=repo, issue=issue)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        sys.exit(result.returncode)

    comment = last_assistant_message(result.stdout)
    if not comment:
        print(result.stdout)
        print("OpenHands returned no assistant message.", file=sys.stderr)
        sys.exit(1)
    return comment


def run_openhands_for_json(prompt: str, *, repo: str, issue: int) -> dict[str, Any]:
    """Run OpenHands and parse the final assistant reply as JSON."""
    content = run_openhands_for_comment(prompt, repo=repo, issue=issue)
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        print(content)
        raise SystemExit(f"OpenHands did not return valid JSON for phase 4: {exc}") from exc


def run_openhands_task(task: str, *, repo: str, issue: int) -> None:
    """Run OpenHands agent with the task."""
    print("=" * 60)
    print("OpenHands Agent Execution")
    print("=" * 60)
    print(f"Task: {task[:200]}...")
    print("=" * 60)

    result = run_openhands(task, repo=repo, issue=issue)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    if result.returncode != 0:
        sys.exit(result.returncode)

    print("\nAgent execution complete.")


def validate_phase_four_payload(payload: dict[str, Any]) -> None:
    """Validate the minimal schema for phase 4 child issue creation."""
    if not isinstance(payload, dict):
        raise SystemExit("Phase 4 payload must be a JSON object.")
    if not isinstance(payload.get("comment"), str) or not payload["comment"].strip():
        raise SystemExit("Phase 4 payload must include a non-empty `comment`.")
    sub_issues = payload.get("sub_issues")
    if not isinstance(sub_issues, list) or not sub_issues:
        raise SystemExit("Phase 4 payload must include at least one `sub_issues` entry.")
    for item in sub_issues:
        if not isinstance(item, dict):
            raise SystemExit("Each phase 4 child issue must be an object.")
        if not isinstance(item.get("title"), str) or not item["title"].strip():
            raise SystemExit("Each phase 4 child issue must include a non-empty `title`.")
        if not isinstance(item.get("body"), str) or not item["body"].strip():
            raise SystemExit("Each phase 4 child issue must include a non-empty `body`.")


def run_gh(args: list[str], *, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    """Run a GitHub CLI command."""
    return subprocess.run(
        ["gh", *args],
        text=True,
        capture_output=capture_output,
        timeout=120,
    )


def phase_display_name(phase: int, label: str) -> str:
    """Build a stable display name for a phase comment boundary."""
    if phase == 2:
        return label.replace("phase:", "").capitalize()
    return PHASE_DISPLAY_NAME_MAP.get(phase, label.replace("phase:", "").capitalize())


def format_phase_comment(phase: int, label: str, body: str) -> str:
    """Wrap a posted comment with visible and machine-readable phase boundaries."""
    display_name = phase_display_name(phase, label)
    normalized_body = body.strip()
    return "\n".join(
        [
            f"<!-- phase:{phase}:start label={label} name={display_name} -->",
            f"### Phase {phase}: {display_name}",
            "",
            normalized_body,
            "",
            f"<!-- phase:{phase}:end label={label} name={display_name} -->",
        ]
    )


def post_issue_comment(repo: str, issue_number: int, body: str) -> None:
    """Post a GitHub comment to the target issue."""
    result = run_gh(["issue", "comment", str(issue_number), "--repo", repo, "--body", body])
    if result.returncode != 0:
        raise SystemExit(f"Failed to post comment to {repo}#{issue_number}.")


def advance_issue_label(repo: str, issue_number: int, current_label: str) -> None:
    """Advance the issue to the next configured phase label."""
    next_label = NEXT_LABEL_MAP.get(current_label)
    if not next_label:
        return

    result = run_gh(
        [
            "issue",
            "edit",
            str(issue_number),
            "--repo",
            repo,
            "--remove-label",
            current_label,
            "--add-label",
            next_label,
        ]
    )
    if result.returncode != 0:
        raise SystemExit(
            f"Posted the phase comment to {repo}#{issue_number}, but failed to hand off label "
            f"from '{current_label}' to '{next_label}'."
        )


def create_child_issues(repo: str, parent_issue: int, sub_issues: list[dict[str, str]]) -> list[dict[str, str]]:
    """Create child issues and attach a parent reference in the body."""
    created: list[dict[str, str]] = []

    for item in sub_issues:
        body = item["body"].strip()
        if f"Parent issue: #{parent_issue}" not in body:
            body = f"Parent issue: #{parent_issue}\n\n{body}"

        result = run_gh(
            ["issue", "create", "--repo", repo, "--title", item["title"].strip(), "--body", body],
            capture_output=True,
        )
        if result.returncode != 0:
            raise SystemExit(f"Failed to create child issue '{item['title']}'.")
        created.append({"title": item["title"].strip(), "url": result.stdout.strip()})

    return created


def build_phase_four_summary(created: list[dict[str, str]]) -> str:
    """Build a short summary comment listing created child issues."""
    lines = ["Spawned child issues:"]
    for item in created:
        lines.append(f"- {item['title']}: {item['url']}")
    return "\n".join(lines)


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Trigger OpenHands / GitHub phase workflow")
    parser.add_argument("--label", help="GitHub label triggering the phase")
    parser.add_argument("--issue", type=int, help="Issue number")
    parser.add_argument("--repo", help="Repository owner/repo")
    args = parser.parse_args()

    trigger_agent(args.label, args.issue, args.repo)


if __name__ == "__main__":
    main()
