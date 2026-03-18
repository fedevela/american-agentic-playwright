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
    """
    Execute phase 9/Malkhut using the Multi-Session Performance Loop.
    This explicitly relieves the LLM from managing loops, enforcing the Slice Principle.
    The Python trigger acts as the Information Broker here.
    """
    log_info("Building Malkhut orchestration loop...")
    
    # How the Trigger Orchestrates Phase 9:
    
    # 1. The Parse: The Python trigger reads skeleton.md and identifies the required character personas.
    # skeleton_content = read_skeleton_file()
    # required_personas = extract_required_personas(skeleton_content)
    
    # 2. The Session Dictionary: The Python trigger initializes an array of persistent API conversation histories.
    # session_dict = {
    #     "stage_master": create_persistent_session("malkhut_stage_master"),
    #     "souls": {p: create_persistent_session(f"malkhut_soul_{p}") for p in required_personas}
    # }
    
    # 3. The Loop: Programmatically bounce prompts between distinct conversation histories.
    # current_stimulus = initial_tags
    # while not scene_complete:
    #     # 1. Stage Master narrates the environment/action and explicitly designates the next speaker
    #     stage_output = prompt_session(session_dict["stage_master"], current_stimulus)
    #
    #     # 2. The Stage Master MUST narrate back to every persona what is happening
    #     for p in required_personas:
    #         prompt_session(session_dict["souls"][p], f"Stage Master Narration: {stage_output.narration}")
    #
    #     # 3. The Python trigger reads the Stage Master's decision on who acts next
    #     active_soul = stage_output.next_speaker
    #     if not active_soul:
    #         break # Scene over
    #
    #     # 4. Prompt the chosen Character Soul to react (dialogue, action, or parenthetical)
    #     soul_output = prompt_session(session_dict["souls"][active_soul], "It is your turn to act/speak.")
    #
    #     # 5. Extract dialogue/actions and write to the final script buffer
    #     append_to_script(stage_output.narration, soul_output.external_manifestation)
    #
    #     # 6. Feed the soul's external manifestation back to the Stage Master as the new stimulus for the next loop
    #     current_stimulus = f"Character {active_soul} did/said: {soul_output.external_manifestation}"
    # 
    # write_final_script_md()  # Bypassing the need for a general-purpose headless agent entirely.

    log_info("Finalizing git delivery (commit + push)...")
    delivery_summary = finalize_delivery(
        repo=request.repo,
        issue=request.issue,
        phase=request.phase,
        issue_title=str(request.issue_data.get("title") or ""),
        issue_data=request.issue_data,
    )
    log_multiline("Delivery summary", delivery_summary)
    post_phase_machine_comment(request, delivery_summary)
    advance_issue_label(request.repo, request.issue, request.label)
    log_info("Label advanced")


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
