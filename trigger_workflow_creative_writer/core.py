from __future__ import annotations

from typing import Any, Callable, Optional

from . import config
from .config import (
    DEFAULT_REPO,
    DISCUSSION_PHASES,
    LABEL_PHASE_MAP,
    NEEDS_HUMAN_LABEL,
    NEXT_LABEL_MAP,
    PHASE_DISPLAY_NAME_MAP,
    PRE_IMPLEMENTATION_PHASES,
    SPECIFICATION_PHASE,
    STRICTLY_INDEPENDENT_PHASES,
)
from .github_ops import (
    advance_issue_label,
    edit_issue_labels,
    clear_issue_labels_except,
    create_child_issues,
    complete_scene_and_roll_up,
    reconcile_parent_completion,
    ensure_phase_labels,
    fetch_issue_data,
    issue_has_label,
    issue_phase_labels,
    post_issue_comment,
    remove_issue_label,
    resolve_issue_by_label,
    resolve_oldest_phased_issue,
    tag_issue_needs_human,
)
from .logging_utils import log_error, log_info, log_multiline, log_section, log_step
from .models import PhaseExecutionRequest
from .execution import (
    run_comment_phase,
    run_json_phase,
    run_implementation_phase,
    finalize_delivery,
)
from .openhands_runner import create_issue_branches_for_child_issues
from .prompts import (
    build_implementation_phase_prompt,
    build_comment_phase_prompt,
    build_phase_four_summary,
    build_tiferet_specification_prompt,
    determine_phase_from_label,
    format_phase_comment,
    read_microagent_for_label,
)
from .validation import validate_tiferet_specification_payload_structure, validate_result
from . import cycles


def conversation_scope_for_phase(phase: str) -> str:
    """Return the OpenHands session scope policy for the given phase."""
    if phase in STRICTLY_INDEPENDENT_PHASES:
        return f"phase-{phase}"
    return ""


def describe_phase_conversation_policy(phase: str, session_scope: str) -> str:
    """Preparation is fresh; a performance owns explicit native participant UUIDs."""
    if phase == "9":
        return "separate native director and character sessions, resumed only within this performance"
    return f"fresh independent Codex session ({session_scope or 'current phase'}); never resume preparation"


def log_prompt_size_and_conversation_policy(prompt: str, phase: str) -> str:
    """Log the prompt size and session behavior, then return the resolved session scope."""
    log_info(f"Prompt built ({len(prompt)} chars)")
    session_scope = conversation_scope_for_phase(phase)
    log_info(f"Session policy: {describe_phase_conversation_policy(phase, session_scope)}")
    return session_scope


def build_phase_prompt_and_conversation_scope(
    phase: str,
    builder: Callable[..., str],
    *args: Any,
) -> tuple[str, str]:
    """Build a phase prompt and return it with the resolved session-scope policy."""
    prompt = builder(*args)
    return prompt, log_prompt_size_and_conversation_policy(prompt, phase)


def build_phase_execution_prompt(
    request: PhaseExecutionRequest,
    prompt_builder: Callable[..., str],
) -> tuple[str, str]:
    """Build a phase prompt using the common execution request payload."""
    cycles.bind_issue(request.issue_data, request.repo, request.issue)
    return build_phase_prompt_and_conversation_scope(
        request.phase,
        prompt_builder,
        request.label,
        request.issue,
        request.repo,
        request.microagent_content,
        request.phase,
        request.issue_data,
    )


def post_phase_machine_comment(request: PhaseExecutionRequest, body: str) -> None:
    """Post a wrapped phase comment back to the parent issue."""
    post_issue_comment(
        request.repo,
        request.issue,
        format_phase_comment(request.phase, request.label, body),
    )


def execute_phase_with_needs_human_tagging(
    request: PhaseExecutionRequest,
    executor: Callable[[PhaseExecutionRequest], None],
) -> None:
    """Execute a phase and mark pre-Netzach failures for explicit human intervention."""
    try:
        executor(request)
    except SystemExit:
        if request.phase in PRE_IMPLEMENTATION_PHASES:
            log_error(
                f"Phase {request.phase.upper()} failed before Netzach; tagging issue for human intervention."
            )
            tag_issue_needs_human(request.repo, request.issue)
        raise


def run_labeled_issue_phase(label: Optional[str] = None, issue: Optional[int] = None, repo: Optional[str] = None) -> None:
    """Route the label to the correct phase workflow."""
    run_labeled_issue_phase_with_mode(label=label, issue=issue, repo=repo, manual=False)


def run_labeled_issue_phase_with_mode(
    label: Optional[str] = None,
    issue: Optional[int] = None,
    repo: Optional[str] = None,
    *,
    manual: bool = False,
) -> None:
    """Route the label to the correct phase workflow with optional manual preview mode."""
    request = resolve_phase_execution_request(
        label=label,
        issue=issue,
        repo=repo,
        manual=manual,
    )

    log_step("Step 4: Executing phase workflow")
    if manual:
        log_info("Manual mode: previewing prompt and planned actions only")
        preview_phase_execution_plan(request)
        return

    from .runner_utils import managed_repo_path, prepare_phase_execution_context, prepare_initial_season_work, resolve_target_repo_config
    from .season_branches import checkout_lock
    with checkout_lock(managed_repo_path(request.repo)):
        context = prepare_phase_execution_context(request.repo, request.phase, request.issue, issue_data=request.issue_data)
        recovering = request.phase == "9" and bool(config.PERFORMANCE_RUN)
        allowed_recovery_paths = set()
        if recovering:
            from .roundtable import recovery_paths
            allowed_recovery_paths = recovery_paths(
                repo=request.repo, issue=request.issue, cwd=context.local_path,
                state_root=config.WORKSPACE / "workspace" / "roundtable",
                run_id=config.PERFORMANCE_RUN, scene_path=config.SCENE_PATH,
            )
        prepare_initial_season_work(context.local_path, resolve_target_repo_config(request.repo).main_branch,
                                    recovery=recovering, recovery_paths=allowed_recovery_paths)
        _execute_prepared_phase(request)


def _execute_prepared_phase(request: PhaseExecutionRequest) -> None:
    """Dispatch while the caller holds the checkout lock through delivery."""
    if request.phase in DISCUSSION_PHASES:
        log_info(f"Running discussion workflow for phase {request.phase.upper()}")
        execute_phase_with_needs_human_tagging(
            request,
            execute_comment_phase_handoff,
        )
        return

    if request.phase == SPECIFICATION_PHASE:
        log_info("Running specification workflow for phase 4")
        execute_phase_with_needs_human_tagging(
            request,
            execute_tiferet_specification_phase,
        )
        return

    if request.phase == "9":
        log_info("Running Multi-Session Performance Loop for phase 9 (Malkhut)")
        from .router import execute_malkhut_performance_phase
        execute_phase_with_needs_human_tagging(
            request,
            execute_malkhut_performance_phase,
        )
        return

    log_info(f"Running implementation workflow for phase {request.phase.upper()}")
    execute_implementation_phase_task(request)


def resolve_phase_execution_request(
    label: Optional[str] = None,
    issue: Optional[int] = None,
    repo: Optional[str] = None,
    *,
    manual: bool = False,
    include_base_persona: bool = True,
) -> PhaseExecutionRequest:
    """Resolve and validate issue/label context into a reusable phase execution request."""
    config.require_enabled_provider()
    repo = repo or DEFAULT_REPO
    log_section("STARTING PHASE EXECUTION")
    log_info(f"Repository: {repo}")

    if manual:
        log_step("Step 0: Manual mode enabled")
        log_info("Skipping canonical phase label synchronization to avoid GitHub mutations")
    else:
        log_step("Step 0: Ensuring canonical phase labels exist")
        ensure_phase_labels(repo)

    log_step("Step 1: Resolving issue and label context")
    if issue is None and label is None:
        log_info("No issue or label provided; finding oldest phased issue...")
        issue, label = resolve_oldest_phased_issue(repo)
        log_info(f"Selected issue #{issue} with label '{label}'")
    elif issue is None and label is not None:
        log_info(f"Label '{label}' provided; finding oldest issue carrying this label...")
        issue = resolve_issue_by_label(repo, label)
        log_info(f"Selected issue #{issue} for label '{label}'")
    elif issue is not None and label is None:
        log_info(f"Issue #{issue} provided; resolving phase label from issue metadata...")
    else:
        log_info(f"Issue #{issue} and label '{label}' provided; will verify label on issue...")

    log_step("Step 2: Fetching issue data from GitHub")
    issue_data = fetch_issue_data(repo, issue)
    cycles.bind_issue(issue_data, repo, issue)
    log_info(f"Issue #{issue} fetched: '{issue_data.get('title', 'Unknown')}'")

    if label is None:
        # Resolve label from issue_data
        labels = issue_phase_labels(issue_data)
        if not labels:
            log_error(f"Issue #{issue} in {repo} has no phase labels. Cannot determine phase.")
            raise SystemExit(1)
        if len(labels) > 1:
            log_error(
                f"Issue #{issue} in {repo} has multiple phase labels: {', '.join(labels)}. "
                "Pass --label explicitly to select one."
            )
            raise SystemExit(1)
        label = labels[0]
        log_info(f"Resolved label '{label}' from issue #{issue}")
    else:
        # Verify label on issue_data
        if not issue_has_label(issue_data, label):
            if manual or (getattr(config, "NEW_CYCLE", False) and label == "phase:keter"):
                log_info(
                    f"Manual mode label override: issue #{issue} is not labeled '{label}', "
                    "but continuing with the requested label for preview."
                )
            else:
                log_error(f"Issue #{issue} in {repo} is not labeled '{label}'. Skipping phase execution.")
                raise SystemExit(1)
        else:
            log_info("Label verification: PASSED")

    log_step("Step 3: Determining phase id")
    phase = determine_phase_from_label(label)
    if not phase:
        raise SystemExit(f"Unknown label '{label}'. Cannot determine phase.")
    log_info(f"Label '{label}' → Phase {phase.upper()} ({PHASE_DISPLAY_NAME_MAP.get(phase, 'Unknown')})")

    log_step("Sequence Context")
    log_info(f"Current: Phase {phase.upper()}")
    next_phase_label = NEXT_LABEL_MAP.get(label, "")
    next_phase = determine_phase_from_label(next_phase_label) if next_phase_label else None
    if next_phase:
        log_info(f"Next: Phase {next_phase.upper()} ({PHASE_DISPLAY_NAME_MAP.get(next_phase, 'Unknown')})")
    else:
        log_info("Next: Final phase (no further handoff)")

    log_step("Step 4: Reading microagent prompt")
    microagent_content = read_microagent_for_label(label, phase, include_base_persona=include_base_persona)
    log_info(f"Microagent prompt loaded ({len(microagent_content)} bytes)")

    label_names = [l.get("name", "") for l in issue_data.get("labels", []) if l.get("name")]
    log_info(f"Current labels: {', '.join(label_names) if label_names else '(none)'}")

    if getattr(config, "NEW_CYCLE", False):
        if phase != "1":
            raise SystemExit("--new-cycle requires --phase 1 (Keter).")
        issue_data["_start_new_cycle"] = not manual
        if manual:
            issue_data["_preview_cycle"] = cycles.new_cycle(issue_data)
    request = PhaseExecutionRequest(
        label=label,
        issue=issue,
        repo=repo,
        microagent_content=microagent_content,
        phase=phase,
        issue_data=issue_data,
    )
    return request


def select_phase_prompt_builder(phase: str) -> Callable[..., str]:
    """Resolve which prompt builder is used for the given phase family."""
    if phase in DISCUSSION_PHASES:
        return build_comment_phase_prompt
    if phase == SPECIFICATION_PHASE:
        return build_tiferet_specification_prompt
    return build_implementation_phase_prompt


def build_phase_prompt_for_issue(
    label: Optional[str] = None,
    issue: Optional[int] = None,
    repo: Optional[str] = None,
    *,
    manual: bool = True,
) -> str:
    """Resolve issue context and return only the generated phase prompt text."""
    request = resolve_phase_execution_request(
        label=label,
        issue=issue,
        repo=repo,
        manual=manual,
    )
    prompt, _ = build_phase_execution_prompt(request, select_phase_prompt_builder(request.phase))
    return prompt


def render_prompt_only_output(request: PhaseExecutionRequest, prompt: str) -> str:
    """Return prompt-only output including next-action instructions by phase family."""
    if request.phase in DISCUSSION_PHASES:
        actions = [
            "1. Prepare a commit message with the above prompt.",
            "5. Generate the gh command to post the comment to the issue in md format.",
            "3. Generate the issue label to the next phase.",
        ]
    elif request.phase == SPECIFICATION_PHASE:
        actions = [
            "1. Prepare a commit message with the above prompt.",
            "2. Validate current-cycle source coverage, scope, readiness and ordered beats; pause for questions.",
            "3. Persist the accepted structured result and Python-rendered dramatic comment.",
            "4. Reconcile and create ready scenes or recursive assignments, ownership dependencies on the shared season branch.",
            "5. Generate the gh command to post the comment to the issue in md format.",
            "6. Remove the parent phase label from the parent issue.",
        ]
    else:
        actions = [
            "1. Prepare a commit message with the above prompt.",
            "2. Generate a commit message and keep the trigger format: "
            f"`phase:{request.phase} issue #{request.issue}: <short summary>`.",
            "3. Generate a phase delivery comment body summarizing changes and validation.",
            "4. Commit and push the branch updates.",
            "5. Generate the gh command to post the comment to the issue in md format.",
            "6. Advance the issue label to the next phase.",
        ]

    return "\n\n".join(
        [
            prompt,
            "Prompt-only planned actions:\n" + "\n".join(actions),
        ]
    )


def label_for_phase_id(phase: str) -> str:
    """Resolve canonical label for a canonical phase id."""
    raw_phase = phase.strip()
    normalized_phase = {
        "2a": "2A",
        "2b": "2B",
        "2c": "2C",
    }.get(raw_phase.lower(), raw_phase.upper() if raw_phase.lower() in {"2a", "2b", "2c"} else raw_phase)
    for label_name, phase_id in LABEL_PHASE_MAP.items():
        if phase_id == normalized_phase:
            return label_name
    expected = ", ".join(sorted(set(LABEL_PHASE_MAP.values())))
    raise SystemExit(f"Unknown phase '{phase}'. Expected one of: {expected}.")


def preview_phase_execution_plan(request: PhaseExecutionRequest) -> None:
    """Render manual-mode instructions without running agent or mutating GitHub."""
    from .season_branches import resolve_season_root
    from .runner_utils import resolve_target_repo_config
    root = resolve_season_root(request.repo, request.issue, request.issue_data)
    target = resolve_target_repo_config(request.repo)
    log_info(f"Validated season #{root.number}: {root.title}; shared branch {target.issue_branch_prefix}{root.number}; PR base {target.main_branch}")
    phase = request.phase
    if phase in DISCUSSION_PHASES:
        prompt, session_scope = build_phase_execution_prompt(request, build_comment_phase_prompt)
        log_multiline(f"Manual mode prompt for {config.RUNNER_TYPE} (discussion)", prompt)
        log_info(f"Session scope metadata: '{session_scope or '(shared issue scope)'}'")
        log_multiline(
            "Manual mode planned actions",
            "\n".join(
                [
                    f"1. Run {config.RUNNER_TYPE} with the prompt above and capture the final assistant message.",
                    "2. Validate structured outcome and source coverage, then publish the Python-rendered phase comment.",
                    "3. Advance only accepted completion; questions pause and development returns to Keter.",
                ]
            ),
        )
        return

    if phase == SPECIFICATION_PHASE:
        prompt, session_scope = build_phase_execution_prompt(request, build_tiferet_specification_prompt)
        log_multiline(f"Manual mode prompt for {config.RUNNER_TYPE} (specification JSON)", prompt)
        log_info(f"Session scope metadata: '{session_scope or '(shared issue scope)'}'")
        log_multiline(
            "Manual mode planned actions",
            "\n".join(
                [
                    f"1. Run {config.RUNNER_TYPE} with the prompt above and capture the final assistant message as JSON.",
                    "2. Validate current-cycle source coverage, scope, readiness and ordered beats; pause for questions.",
                    "3. Persist the accepted structured result and Python-rendered dramatic comment.",
                    "4. Reconcile and create ready scenes or recursive assignments, ownership dependencies on the shared season branch.",
                    "5. Post the generated child issue summary comment.",
                    "6. Remove the parent phase label from the parent issue.",
                ]
            ),
        )
        return

    prompt, session_scope = build_phase_execution_prompt(request, build_implementation_phase_prompt)
    log_multiline(f"Manual mode prompt for {config.RUNNER_TYPE} (implementation)", prompt)
    log_info(f"Session scope metadata: '{session_scope or '(shared issue scope)'}'")
    log_multiline(
        "Manual mode planned actions",
        "\n".join(
            [
                f"1. Run {config.RUNNER_TYPE} with the prompt above on the resolved issue branch.",
                (
                    "2. Validate source handoff, perform with separate native sessions, and check explicit completion and moment coverage."
                    if phase == "9" else
                    "2. Validate dramatic-action brief and preserved performance artifacts (no npm gates)."
                    if phase in {"7", "8"} else
                    "2. Run the existing phase validation command contract."
                ),
                "3. Finalize delivery (git add/commit/push and PR create/lookup).",
                "4. Post the delivery summary as a wrapped phase comment.",
                "5. Advance the issue label to the next phase.",
            ]
        ),
    )


def _persist_record(request: PhaseExecutionRequest, record: dict, body: str) -> None:
    """Publish durable state before any label or child-delivery effect."""
    wrapped = format_phase_comment(request.phase, request.label, body)
    post_issue_comment(request.repo, request.issue, wrapped)
    # Keep the current tick consistent with the durable issue (also for direct callers).
    comments = request.issue_data.setdefault("comments", [])
    if not comments or comments[-1].get("body") != wrapped:
        comments.append({"body": wrapped})


def _ensure_cycle(request: PhaseExecutionRequest) -> dict:
    cycles.bind_issue(request.issue_data, request.repo, request.issue)
    restart = request.issue_data.pop("_start_new_cycle", False)
    current = None if restart else cycles.current_cycle(request.issue_data)
    if request.phase == "1" and (current is None or restart):
        current = cycles.new_cycle(request.issue_data)
        request.issue_data["_pending_cycle"] = current
        if restart:
            edit_issue_labels(request.repo, request.issue, add=["phase:keter"],
                              remove=[l for l in issue_phase_labels(request.issue_data) if l != "phase:keter"] + ["phase:askQuestion"])
    if current is None:
        raise SystemExit("Legacy work must be re-established through Keter before continuing.")
    return current


def _publish_phase_result(request: PhaseExecutionRequest, result: dict, *, next_cycle: dict | None = None) -> None:
    """Publish narrative and its tracing metadata together, never a startup comment."""
    pending = request.issue_data.get("_pending_cycle")
    body = cycles.render_result(result)
    if pending is not None:
        body = cycles.encode_record(pending) + "\n\n" + body
    if next_cycle is not None:
        body += "\n\n" + cycles.encode_record(next_cycle)
    _persist_record(request, result, body)
    request.issue_data.pop("_pending_cycle", None)


def _restart_development(request: PhaseExecutionRequest, result: dict, accepted: dict) -> None:
    # Durable develop results are replayed here if cycle publication was interrupted.
    next_cycle = cycles.new_cycle(request.issue_data, development={"prior_result":result,
        "prior_work":accepted, "development_question":result["development_question"], "return_reason":result["return_reason"]})
    _publish_phase_result(request, result, next_cycle=next_cycle)
    edit_issue_labels(request.repo, request.issue, add=["phase:keter"],
                      remove=([request.label] if request.label != "phase:keter" else []) + ["phase:askQuestion"])


def _phase_result(request: PhaseExecutionRequest, builder: Callable[..., str]) -> dict | None:
    cycle = _ensure_cycle(request)
    if request.phase != "1" and cycles.current_result(request.issue_data, "1") is None:
        edit_issue_labels(request.repo, request.issue, add=["phase:keter"], remove=[request.label, "phase:askQuestion"])
        return None
    previous = cycles.current_result(request.issue_data, request.phase)
    if cycles.waiting_for_partner(request.issue_data, request.phase):
        edit_issue_labels(request.repo, request.issue, add=["phase:askQuestion"])
        log_info("Waiting for the partner's reply; no phase execution or advancement.")
        return None
    accepted = cycles.accepted_results(request.issue_data)
    if previous and previous.get("outcome") == "develop":
        _restart_development(request, previous, accepted)
        return None
    if previous and previous.get("outcome") == "complete":
        # A failed label update or interrupted child delivery reuses accepted output.
        edit_issue_labels(request.repo, request.issue, remove=["phase:askQuestion"])
        return accepted[request.phase]
    prompt, session_scope = build_phase_execution_prompt(request, builder)
    payload = run_json_phase(prompt, repo=request.repo, issue=request.issue, phase=request.phase,
                             session_scope=session_scope, issue_data=request.issue_data)
    # Models supply dramatic content, never issue ownership or legacy transport tags.
    for key in ('issue_ref', 'season_ref', 'kind', 'version', 'phase'):
        payload.pop(key, None)
    inherited = cycles.source_context(request.issue_data)
    if request.phase == "1" and not set(inherited["canon_refs"]) <= set(payload.get("canon_refs", [])):
        raise SystemExit("Inherited canon references must be preserved.")
    result = validate_result(payload, phase=request.phase, cycle_id=cycle["cycle_id"], scope=cycle["scope"],
                             accepted=accepted, inherited=inherited["anchors"] if inherited else [])
    result['issue_ref'] = cycles.issue_reference(request.issue_data)
    if request.issue_data.get('_season_ref') is not None:
        result['season_ref'] = dict(request.issue_data['_season_ref'])
    if result['outcome'] == 'develop':
        _restart_development(request, result, accepted)
        return None
    _publish_phase_result(request, result)
    if result["outcome"] == "question":
        edit_issue_labels(request.repo, request.issue, add=["phase:askQuestion"])
        return None
    if result["outcome"] == "failure":
        raise SystemExit(result["narrative"])
    if previous and previous.get("outcome") == "question":
        edit_issue_labels(request.repo, request.issue, remove=["phase:askQuestion"])
    return result


def execute_comment_phase_handoff(request: PhaseExecutionRequest) -> None:
    """Publish a validated dramatic result; human questions pause advancement."""
    result = _phase_result(request, build_comment_phase_prompt)
    if result is not None:
        advance_issue_label(request.repo, request.issue, request.label)


def execute_tiferet_specification_phase(request: PhaseExecutionRequest) -> None:
    """Deliver ready scene leaves and recursive assignments from accepted organization."""
    result = _phase_result(request, build_tiferet_specification_prompt)
    if result is None:
        return
    validate_tiferet_specification_payload_structure(result)
    assignments = cycles.child_assignments(result, parent_issue=request.issue,
        accepted=cycles.accepted_results(request.issue_data), inherited=cycles.source_context(request.issue_data))
    created = create_child_issues(request.repo, request.issue, assignments)
    create_issue_branches_for_child_issues(request.repo, request.issue, [int(item["number"]) for item in created])
    post_phase_machine_comment(request, build_phase_four_summary(created))
    remove_issue_label(request.repo, request.issue, request.label)
    reconcile_parent_completion(request.repo, request.issue)


def execute_implementation_phase_task(request: PhaseExecutionRequest) -> None:
    """Execute phases 5-9 headlessly in the configured runner."""
    if request.phase == "10" and any(r.get("kind") == "final-delivery" and r.get("issue") == request.issue for r in cycles.issue_records(request.issue_data)):
        complete_scene_and_roll_up(request.repo, request.issue)
        return
    if request.phase == "5":
        cycles.ready_assignment(request.issue_data)
    log_info("Building agent prompt...")
    prompt, session_scope = build_phase_execution_prompt(request, build_implementation_phase_prompt)

    log_info(f"Running {config.RUNNER_TYPE} agent...")
    run_implementation_phase(
        prompt,
        repo=request.repo,
        issue=request.issue,
        phase=request.phase,
        session_scope=session_scope,
        issue_data=request.issue_data,
    )
    log_info("Agent execution complete")
    log_info("Finalizing git delivery (commit + push)...")
    delivery_summary = finalize_delivery(
        repo=request.repo,
        issue=request.issue,
        phase=request.phase,
        issue_title=str(request.issue_data.get("title") or ""),
        issue_data=request.issue_data,
    )
    log_multiline("Delivery summary", delivery_summary)
    log_info("Posting delivery summary comment...")
    if request.phase == "10":
        record = {"kind":"final-delivery", "version":1, "issue":request.issue, "summary":delivery_summary}
        _persist_record(request, record, delivery_summary + "\n\n" + cycles.encode_record(record))
        complete_scene_and_roll_up(request.repo, request.issue)
        return
    post_phase_machine_comment(request, delivery_summary)
    log_info("Delivery summary comment posted")
    log_info("Advancing to next phase label...")
    advance_issue_label(request.repo, request.issue, request.label)
    log_info("Label advanced")
