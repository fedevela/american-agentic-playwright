from __future__ import annotations

from .config import DISCUSSION_PHASES, SPECIFICATION_PHASE
from .context import PhaseExecutionRequest, describe_phase_conversation_policy
from .execution import (
    build_phase_execution_prompt,
    select_phase_prompt_builder,
)
from .logging_utils import log_info, log_multiline
from .prompts import (
    build_comment_phase_prompt,
    build_tiferet_specification_prompt,
    build_implementation_phase_prompt,
)


def preview_phase_execution_plan(request: PhaseExecutionRequest) -> None:
    """Render manual-mode instructions without running agent or mutating GitHub."""
    phase = request.phase
    if phase in DISCUSSION_PHASES:
        prompt, session_scope = build_phase_execution_prompt(request, build_comment_phase_prompt)
        log_multiline("Manual mode prompt for gemini (discussion)", prompt)
        log_info(f"Session scope metadata: '{session_scope or '(shared issue scope)'}'")
        log_multiline(
            "Manual mode planned actions",
            "\n".join(
                [
                    "1. Run agent with the prompt above and capture the final assistant message.",
                    "2. Post that message to the issue as a phase comment wrapper.",
                    "3. Advance the issue label to the next phase.",
                ]
            ),
        )
        return

    if phase == SPECIFICATION_PHASE:
        prompt, session_scope = build_phase_execution_prompt(request, build_tiferet_specification_prompt)
        log_multiline("Manual mode prompt for gemini (specification JSON)", prompt)
        log_info(f"Session scope metadata: '{session_scope or '(shared issue scope)'}'")
        log_multiline(
            "Manual mode planned actions",
            "\n".join(
                [
                    "1. Run agent with the prompt above and capture the final assistant message as JSON.",
                    "2. Validate JSON payload structure and requirement traceability.",
                    "3. Post the parent phase comment from `payload.comment`.",
                    "4. Create ordered child issues from `payload.sub_issues` and create child branches.",
                    "5. Post the generated child issue summary comment.",
                    "6. Remove the parent phase label from the parent issue.",
                ]
            ),
        )
        return

    prompt, session_scope = build_phase_execution_prompt(request, build_implementation_phase_prompt)
    log_multiline("Manual mode prompt for gemini (implementation)", prompt)
    log_info(f"Session scope metadata: '{session_scope or '(shared issue scope)'}'")
    log_multiline(
        "Manual mode planned actions",
        "\n".join(
            [
                "1. Run agent with the prompt above on the resolved issue branch.",
                "2. Run trigger validation flow for phases 6-9 (`typecheck -> build -> test:e2e`).",
                "3. Finalize delivery (git add/commit/push and PR create/lookup).",
                "4. Post the delivery summary as a wrapped phase comment.",
                "5. Advance the issue label to the next phase.",
            ]
        ),
    )


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
            "2. Validate JSON payload structure and requirement traceability.",
            "3. Post the parent phase comment from `payload.comment`.",
            "4. Create ordered child issues from `payload.sub_issues` and create child branches.",
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
