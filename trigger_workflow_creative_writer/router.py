from .models import PhaseExecutionRequest
from .execution import (
    run_comment_phase,
    run_json_phase,
    run_implementation_phase,
    finalize_delivery,
)
from .core import (
    conversation_scope_for_phase,
    describe_phase_conversation_policy,
    log_prompt_size_and_conversation_policy,
    build_phase_prompt_and_conversation_scope,
    build_phase_execution_prompt,
    post_phase_machine_comment,
    execute_phase_with_needs_human_tagging,
    run_labeled_issue_phase,
    run_labeled_issue_phase_with_mode,
    resolve_phase_execution_request,
    select_phase_prompt_builder,
    build_phase_prompt_for_issue,
    render_prompt_only_output,
    label_for_phase_id,
    preview_phase_execution_plan,
    execute_comment_phase_handoff,
    execute_tiferet_specification_phase,
    execute_implementation_phase_task,
)
from .cli import run_trigger_cli
from .logging_utils import log_info, log_multiline
from .github_ops import advance_issue_label


def execute_malkhut_performance_phase(request: PhaseExecutionRequest) -> None:
    """Perform first; journal all delivery/handoff effects under the run lock."""
    from . import config
    from .artifact_validation import validate_required_artifacts
    from .runner_utils import prepare_phase_execution_context

    config.require_enabled_provider()
    if request.phase != "9":
        raise ValueError("Malkhut performance handler requires phase 9")
    context = prepare_phase_execution_context(
        request.repo, request.phase, request.issue, issue_data=request.issue_data,
    )
    validate_required_artifacts(context.local_path)
    from .roundtable import perform_scene
    from .scene_materials import load_scene

    scene = load_scene(context.local_path, request.issue, config.SCENE_PATH)
    relative_scene = str(scene.directory.relative_to(context.local_path.resolve()))

    def deliver() -> str:
        rendered_script = (scene.directory / "script.md").read_bytes()

        def before_commit(checkout) -> None:
            final_scene = load_scene(checkout, request.issue, relative_scene)
            if final_scene.scene_id != scene.scene_id or final_scene.fingerprint != scene.fingerprint:
                raise ValueError("Scene input fingerprint changed before delivery; reconciliation required")
            if (final_scene.directory / "script.md").read_bytes() != rendered_script:
                raise ValueError("Rendered script changed before delivery; reconciliation required")

        summary = finalize_delivery(
            repo=request.repo, issue=request.issue, phase=request.phase,
            issue_title=str(request.issue_data.get("title") or ""),
            issue_data=request.issue_data,
            before_commit=before_commit,
        )
        post_phase_machine_comment(request, summary)
        advance_issue_label(request.repo, request.issue, request.label)
        return summary

    result = perform_scene(
        repo=request.repo, issue=request.issue, cwd=context.local_path,
        state_root=config.WORKSPACE / "workspace" / "roundtable",
        scene_path=config.SCENE_PATH, run_id=config.PERFORMANCE_RUN,
        new_performance=config.NEW_PERFORMANCE, model=config.CODEX_MODEL,
        max_calls=config.MAX_ROLE_CALLS, timeout=config.ROLE_TIMEOUT,
        max_no_progress=config.MAX_NO_PROGRESS, deliver=deliver,
    )
    log_info(f"Performance status: {result.get('status', 'completed')}")

__all__ = [
    "PhaseExecutionRequest",
    "run_comment_phase",
    "run_json_phase",
    "run_implementation_phase",
    "finalize_delivery",
    "conversation_scope_for_phase",
    "describe_phase_conversation_policy",
    "log_prompt_size_and_conversation_policy",
    "build_phase_prompt_and_conversation_scope",
    "build_phase_execution_prompt",
    "post_phase_machine_comment",
    "execute_phase_with_needs_human_tagging",
    "run_labeled_issue_phase",
    "run_labeled_issue_phase_with_mode",
    "resolve_phase_execution_request",
    "select_phase_prompt_builder",
    "build_phase_prompt_for_issue",
    "render_prompt_only_output",
    "label_for_phase_id",
    "preview_phase_execution_plan",
    "execute_comment_phase_handoff",
    "execute_tiferet_specification_phase",
    "execute_implementation_phase_task",
    "execute_malkhut_performance_phase",
    "run_trigger_cli",
]
